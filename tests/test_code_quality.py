"""test_code_quality.py — структурная аналитика кода для ИИ-агентов.

Проверяет:
1. Размеры файлов — не больше порога (монолиты мешают агентам)
2. Длины функций — не больше порога (сложные функции ломаются при правке)
3. Cyclomatic complexity через radon
4. Maintainability Index через radon
5. Дублирование блоков кода между HTML файлами
6. Ruff: undefined names, repeated keys, bare except (баги)
7. Vulture: мёртвый код (100% confidence)

Пороги настроены мягко — warning при приближении, fail при превышении.
Цель: не блокировать работу, но показывать проблемы и следить тренд.

Запуск:
  ./run_tests.sh --quality              # только аналитика
  /opt/gailray/venv/bin/python3 -m pytest tests/test_code_quality.py -v
"""

import os
import ast
import re
import subprocess
import hashlib
import json
from pathlib import Path
from collections import defaultdict

import pytest

ROOT = Path(__file__).parent.parent
VENV_PYTHON = str(ROOT / "venv" / "bin" / "python3")

SKIP_DIRS = {
    "venv", "venv_vllm", "__pycache__", ".git", "node_modules",
    "data", "thumbnails", "logs", "gguf", ".pytest_cache",
    "build", "dist", ".ruff_cache",
}

HTML_FILES = [
    "web/gallery.html",
    "web/map.html",
    "web/personas.html",
    "web/photos.html",
    "web/catalog.html",
]

# ─── Пороги ───
FILE_MAX_LINES = 1500        # fail
FILE_WARN_LINES = 800        # warning
FUNC_MAX_LINES = 150         # fail
FUNC_WARN_LINES = 80         # warning
COMPLEXITY_MAX = 50          # fail (radon: E)
COMPLEXITY_WARN = 30         # warning (radon: D)
MI_MIN = 20                  # fail (radon: C и ниже)
MI_WARN = 50                 # warning (radon: B)
DUP_MAX_BLOCKS = 100         # fail — больше 100 дубликатов между HTML
DUP_WARN_BLOCKS = 40         # warning


def _collect_files(extensions):
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if any(f.endswith(ext) for ext in extensions):
                result.append(Path(dirpath) / f)
    return result


def _count_lines(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


# ─── 1. Размеры файлов ───

def test_no_critical_monoliths():
    """Файлы больше FILE_MAX_LINES — критичные монолиты."""
    big = []
    for path in _collect_files([".py", ".html", ".css", ".js"]):
        n = _count_lines(path)
        if n > FILE_MAX_LINES:
            big.append((n, str(path.relative_to(ROOT))))

    if big:
        big.sort(reverse=True)
        lines = "\n".join(f"  {n:5d}  {p}" for n, p in big)
        pytest.fail(f"Критичные монолиты (>{FILE_MAX_LINES} строк):\n{lines}\n"
                    f"Подумай о разбиении на модули.")


def test_file_sizes_report():
    """Отчёт по всем файлам > FILE_WARN_LINES — warning, не fail."""
    big = []
    for path in _collect_files([".py", ".html", ".css", ".js"]):
        n = _count_lines(path)
        if n > FILE_WARN_LINES:
            big.append((n, str(path.relative_to(ROOT))))

    big.sort(reverse=True)
    if big:
        lines = "\n".join(f"  {n:5d}  {p}" for n, p in big)
        print(f"\n⚠ Файлы > {FILE_WARN_LINES} строк (кандидаты на разбиение):\n{lines}")
    else:
        print(f"\n✅ Все файлы < {FILE_WARN_LINES} строк")


# ─── 2. Длины функций ───

def test_no_giant_functions():
    """Python функции > FUNC_MAX_LINES — критичные монстры."""
    giants = []
    for path in _collect_files([".py"]):
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = node.end_lineno - node.lineno + 1
                    if length > FUNC_MAX_LINES:
                        rel = str(path.relative_to(ROOT))
                        giants.append((length, f"{rel}:{node.lineno}", node.name))
        except Exception:
            pass

    if giants:
        giants.sort(reverse=True)
        lines = "\n".join(f"  {n:3d} строк  {loc}  {name}" for n, loc, name in giants)
        pytest.fail(f"Функции-монстры (>{FUNC_MAX_LINES} строк):\n{lines}\n"
                    f"Разбей на подфункции.")


def test_long_functions_report():
    """Отчёт по функциям > FUNC_WARN_LINES — warning, не fail."""
    long_funcs = []
    for path in _collect_files([".py"]):
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    length = node.end_lineno - node.lineno + 1
                    if length > FUNC_WARN_LINES:
                        rel = str(path.relative_to(ROOT))
                        long_funcs.append((length, f"{rel}:{node.lineno}", node.name))
        except Exception:
            pass

    long_funcs.sort(reverse=True)
    if long_funcs:
        lines = "\n".join(f"  {n:3d} строк  {loc}  {name}" for n, loc, name in long_funcs)
        print(f"\n⚠ Функции > {FUNC_WARN_LINES} строк (кандидаты на рефакторинг):\n{lines}")
    else:
        print(f"\n✅ Все функции < {FUNC_WARN_LINES} строк")


# ─── 3. Cyclomatic Complexity ───

def _radon_cc():
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "radon", "cc", "src/", "-nc", "-j"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def test_no_extreme_complexity():
    """Функции с complexity > COMPLEXITY_MAX — критичные."""
    data = _radon_cc()
    if not data:
        pytest.skip("radon не установлен или нет данных")

    bad = []
    for filepath, blocks in data.items():
        for block in blocks:
            if block.get("complexity", 0) > COMPLEXITY_MAX:
                name = block.get("name", "?")
                comp = block["complexity"]
                lineno = block.get("lineno", 0)
                bad.append((comp, f"{filepath}:{lineno}", name))

    if bad:
        bad.sort(reverse=True)
        lines = "\n".join(f"  {c:3d}  {loc}  {name}" for c, loc, name in bad)
        pytest.fail(f"Критичная сложность (>{COMPLEXITY_MAX}):\n{lines}")


def test_complexity_report():
    """Отчёт по функциям с complexity > COMPLEXITY_WARN."""
    data = _radon_cc()
    if not data:
        pytest.skip("radon не установлен")

    warn = []
    for filepath, blocks in data.items():
        for block in blocks:
            comp = block.get("complexity", 0)
            if comp > COMPLEXITY_WARN:
                name = block.get("name", "?")
                lineno = block.get("lineno", 0)
                grade = block.get("rank", "?")
                warn.append((comp, f"{filepath}:{lineno}", name, grade))

    warn.sort(reverse=True)
    if warn:
        lines = "\n".join(f"  {c:3d} [{g}]  {loc}  {name}" for c, loc, name, g in warn)
        print(f"\n⚠ Высокая сложность (>{COMPLEXITY_WARN}):\n{lines}")
    else:
        print(f"\n✅ Все функции < {COMPLEXITY_WARN} сложности")


# ─── 4. Maintainability Index ───

def _radon_mi():
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "radon", "mi", "src/", "-j"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def test_no_unmaintainable_files():
    """Файлы с MI < MI_MIN — непригодные для поддержки."""
    data = _radon_mi()
    if not data:
        pytest.skip("radon не установлен")

    bad = []
    for filepath, mi in data.items():
        if isinstance(mi, (int, float)) and mi < MI_MIN:
            bad.append((round(mi, 1), filepath))

    if bad:
        bad.sort()
        lines = "\n".join(f"  MI={m:5.1f}  {p}" for m, p in bad)
        pytest.fail(f"Непригодные для поддержки файлы (MI<{MI_MIN}):\n{lines}\n"
                    f"MI=0 означает что агент не может безопасно редактировать.")


def test_mi_report():
    """Отчёт по файлам с MI < MI_WARN."""
    data = _radon_mi()
    if not data:
        pytest.skip("radon не установлен")

    warn = []
    for filepath, mi in data.items():
        if isinstance(mi, (int, float)) and mi < MI_WARN:
            warn.append((round(mi, 1), filepath))

    warn.sort()
    if warn:
        lines = "\n".join(f"  MI={m:5.1f}  {p}" for m, p in warn)
        print(f"\n⚠ Низкая поддерживаемость (MI<{MI_WARN}):\n{lines}")
    else:
        print(f"\n✅ Все файлы MI>{MI_WARN}")


# ─── 5. Дублирование HTML ───

def _find_dup_blocks(files, min_lines=6):
    blocks = defaultdict(list)
    for fpath in files:
        full = ROOT / fpath
        if not full.exists():
            continue
        with open(full, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for i in range(len(lines) - min_lines):
            chunk = tuple(l.strip() for l in lines[i:i + min_lines] if l.strip())
            if len(chunk) < min_lines:
                continue
            h = hashlib.md5("\n".join(chunk).encode()).hexdigest()
            blocks[h].append((fpath, i + 1))
    return {h: locs for h, locs in blocks.items() if len({f for f, _ in locs}) > 1}


def test_html_duplication_not_critical():
    """Дублирование между HTML файлами > DUP_MAX_BLOCKS — критичное."""
    dups = _find_dup_blocks(HTML_FILES)
    count = len(dups)

    if count > DUP_MAX_BLOCKS:
        # Покажем топ дубликатов
        pair_counts = defaultdict(int)
        for locs in dups.values():
            files_involved = tuple(sorted(set(f for f, _ in locs)))
            pair_counts[files_involved] += 1

        lines = []
        for pair, c in sorted(pair_counts.items(), key=lambda x: -x[1])[:5]:
            lines.append(f"  {c:3d} дубликатов: {', '.join(pair)}")

        pytest.fail(f"Критичное дублирование HTML ({count}>{DUP_MAX_BLOCKS}):\n"
                    + "\n".join(lines) + "\nВынеси общий CSS/JS в shared файлы.")


def test_html_duplication_report():
    """Отчёт по дублированию HTML — warning."""
    dups = _find_dup_blocks(HTML_FILES)
    count = len(dups)

    if count > DUP_WARN_BLOCKS:
        pair_counts = defaultdict(int)
        for locs in dups.values():
            files_involved = tuple(sorted(set(f for f, _ in locs)))
            pair_counts[files_involved] += 1

        lines = []
        for pair, c in sorted(pair_counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  {c:3d} дубликатов: {', '.join(pair)}")

        print(f"\n⚠ Дублирование HTML ({count} блоков 6+ строк):\n" + "\n".join(lines))
    else:
        print(f"\n✅ Дублирование HTML в норме ({count} блоков)")


# ─── 6. Ruff: баги ───

def _ruff_check(select_codes):
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "ruff", "check", "src/", "--select", select_codes, "--output-format", "json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        if result.returncode == 0:
            return []
        return json.loads(result.stdout or "[]")
    except Exception:
        return []


def test_no_undefined_names():
    """Ruff F821 — undefined names (баг: обращение к несуществующей переменной)."""
    issues = _ruff_check("F821")
    # Также проверяем корневые .py
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "ruff", "check", ".", "--select", "F821", "--output-format", "json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        issues = json.loads(result.stdout or "[]")
    except Exception:
        pass

    if issues:
        lines = []
        for i in issues:
            loc = f"{i.get('filename','?')}:{i.get('location',{}).get('row','?')}"
            msg = i.get("message", "?")
            lines.append(f"  {loc}  {msg}")
        pytest.fail("Undefined names (F821) — баги:\n" + "\n".join(lines))


def test_no_repeated_dict_keys():
    """Ruff F601 — повтор ключа в dict (перезатирание значения)."""
    issues = _ruff_check("F601")
    if issues:
        lines = []
        for i in issues:
            loc = f"{i.get('filename','?')}:{i.get('location',{}).get('row','?')}"
            msg = i.get("message", "?")
            lines.append(f"  {loc}  {msg}")
        pytest.fail("Повтор ключей в dict (F601) — баги:\n" + "\n".join(lines))


def test_no_bare_except():
    """Ruff E722 — bare except (глушит все ошибки включая KeyboardInterrupt)."""
    issues = _ruff_check("E722")
    if issues:
        lines = []
        for i in issues:
            loc = f"{i.get('filename','?')}:{i.get('location',{}).get('row','?')}"
            lines.append(f"  {loc}")
        pytest.fail("Bare except (E722) — глушат ошибки:\n" + "\n".join(lines))


# ─── 7. Vulture: мёртвый код ───

def test_no_dead_code_100pct():
    """Vulture — мёртвый код с 100% confidence (точно неиспользуемое)."""
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "vulture", "src/", "--min-confidence", "100"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
    except Exception:
        pytest.skip("vulture не установлен")

    lines = [l for l in result.stdout.strip().split("\n") if l.strip() and "unused" in l.lower()]
    if lines:
        pytest.fail("Мёртвый код (100% confidence):\n" + "\n".join(f"  {l}" for l in lines))


def test_dead_code_report():
    """Отчёт по мёртвому коду — warning."""
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "vulture", "src/", "--min-confidence", "60"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
    except Exception:
        pytest.skip("vulture не установлен")

    lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
    # Фильтруем API роуты (false positives — FastAPI декораторы не видны vulture)
    filtered = [l for l in lines if not re.search(r"src/api/.*unused function", l)]
    if filtered:
        print(f"\n⚠ Возможный мёртвый код ({len(filtered)} пунктов):\n" +
              "\n".join(f"  {l}" for l in filtered[:30]))
    else:
        print("\n✅ Мёртвый код не найден")
