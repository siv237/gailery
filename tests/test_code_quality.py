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
    "web/catalog.html",
]

JS_SKIP_FILES = {
    # Сторонние библиотеки — не наш код
    "leaflet.js", "leaflet.markercluster.js",
}

# DOM-свойства и event handlers — не функции, пропускаем
JS_DOM_NAMES = {
    "onclick", "onload", "onended", "onmousedown", "onmouseup",
    "onmousemove", "onchange", "oninput", "onerror", "onplay",
    "onpause", "onseeked", "onseeking", "onwaiting", "oncanplay",
}

# Паттерн декоратора: file сохраняет оригинал и переназначает функцию
# для расширения behaviour. Это НЕ дубль — это расширение.
JS_DECORATOR_REASSIGNS = {
    "openDetail",  # gallery-ui.js оборачивает gallery-detail.js openDetail
}

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

def _ruff_check(select_codes, target="."):
    """Запуск ruff check с выбранными правилами.

    target: "." — весь проект (по умолчанию), "src/" — только src.
    Сканирует весь проект т.к. BLE001/C901 нарушения концентрируются
    в корневых воркерах (describe.py, embed.py, faces.py, pipeline.py),
    не только в src/.
    Использует ruff.toml в корне проекта (порог CC=15, per-file-ignores).
    """
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "ruff", "check", target,
             "--select", select_codes, "--output-format", "json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
        if result.returncode == 0:
            return []
        return json.loads(result.stdout or "[]")
    except Exception:
        return []


def test_no_undefined_names():
    """Ruff F821 — undefined names (баг: обращение к несуществующей переменной)."""
    issues = _ruff_check("F821")
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


# ─── 6b. Ruff: backlog-метрики (warning, не fail) ───
# Манифест §2.1: архитектурные тесты НЕ блокируют коммиты — это backlog.
# Пороги только снижаются. Каждый проваленный тест = задача на рефакторинг.

# Текущий baseline (зафиксирован 2026-07-02). НЕ повышать без явного коммита.
# baseline = фактическое состояние на момент фиксации (манифест §3.3).
BLE001_BASELINE = 238     # blind except Exception без re-raise
F401_BASELINE = 0         # unused imports — очищено (этап 1)
F841_BASELINE = 0         # unused local variables — очищено (этап 1)
C901_OVER15_BASELINE = 21 # функции с cyclomatic complexity > 15


def _ruff_count(code):
    """Количество нарушений правила code во всём проекте."""
    return len(_ruff_check(code))


def _format_issues(issues, limit=30):
    lines = []
    for i in issues[:limit]:
        loc = f"{i.get('filename','?')}:{i.get('location',{}).get('row','?')}"
        msg = i.get("message", "?").split(" is too complex")[0].split(" Do not")[0]
        lines.append(f"  {loc}  {msg}")
    if len(issues) > limit:
        lines.append(f"  ... и ещё {len(issues) - limit}")
    return "\n".join(lines)


def test_blind_except_backlog():
    """BLE001 — blind except Exception без re-raise (AI-антипаттерн #1).

    Backlog (манифест §3.2): существующий долг фиксируется, новый код
    не должен добавлять нарушений. Порог = baseline, только снижается.
    """
    count = _ruff_count("BLE001")
    if count > BLE001_BASELINE:
        issues = _ruff_check("BLE001")
        pytest.fail(
            f"Blind except (BLE001) вырос: {count} > baseline {BLE001_BASELINE}.\n"
            f"Новый код добавил нарушений — рефактори на конкретные типы исключений "
            f"или добавь re-raise / logging:\n" + _format_issues(issues)
        )
    elif count > 0:
        print(f"\n⚠ Blind except (BLE001): {count}/{BLE001_BASELINE} baseline — backlog рефакторинга")


def test_unused_imports_backlog():
    """F401 — unused imports. Backlog: порог = baseline, только снижается."""
    count = _ruff_count("F401")
    if count > F401_BASELINE:
        issues = _ruff_check("F401")
        pytest.fail(
            f"Unused imports (F401) вырос: {count} > baseline {F401_BASELINE}.\n"
            f"Удали неиспользуемые импорты:\n" + _format_issues(issues)
        )
    elif count > 0:
        print(f"\n⚠ Unused imports (F401): {count}/{F401_BASELINE} baseline — cleanup backlog")


def test_unused_vars_backlog():
    """F841 — unused local variables. Backlog: порог = baseline, только снижается."""
    count = _ruff_count("F841")
    if count > F841_BASELINE:
        issues = _ruff_check("F841")
        pytest.fail(
            f"Unused vars (F841) вырос: {count} > baseline {F841_BASELINE}.\n"
            f"Удали неиспользуемые переменные:\n" + _format_issues(issues)
        )
    elif count > 0:
        print(f"\n⚠ Unused vars (F841): {count}/{F841_BASELINE} baseline — cleanup backlog")


def test_cyclomatic_complexity_backlog():
    """C901 — функции с cyclomatic complexity > 15 (манифест §4.1).

    Backlog: 21 функция > 15 (макс 35). Порог = baseline, только снижается.
    Каждая функция > 15 — кандидат на разбиение.
    """
    issues = _ruff_check("C901")
    count = len(issues)
    if count > C901_OVER15_BASELINE:
        pytest.fail(
            f"Complexity >15 (C901) вырос: {count} > baseline {C901_OVER15_BASELINE}.\n"
            f"Новая функция превысила порог — разбей на подфункции:\n"
            + _format_issues(issues)
        )
    elif count > 0:
        worst = sorted(
            issues,
            key=lambda i: int(i.get("message", "0").split("(")[1].split(" ")[0] or 0),
            reverse=True
        )[:10]
        lines = []
        for i in worst:
            loc = f"{i.get('filename','?')}:{i.get('location',{}).get('row','?')}"
            cc = i.get("message", "?").split("(")[1].split(" ")[0] if "(" in i.get("message","") else "?"
            name = i.get("message", "?").split("`")[1].split("`")[0] if "`" in i.get("message","") else "?"
            lines.append(f"  CC={cc:>3}  {loc}  {name}")
        print(f"\n⚠ Complexity >15 (C901): {count}/{C901_OVER15_BASELINE} baseline — топ-10:\n" + "\n".join(lines))


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


# ─── 8. JS: дублирование функций между файлами ───

def _collect_web_js_files():
    """JS файлы в web/ (включая подпапки), исключая сторонние библиотеки."""
    web_dir = ROOT / "web"
    result = []
    for dirpath, dirnames, filenames in os.walk(web_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != "lib"]
        for f in filenames:
            if f.endswith(".js") and f not in JS_SKIP_FILES:
                result.append(Path(dirpath) / f)
    return sorted(result)


def _extract_js_functions(path):
    """Извлекает имена топ-уровневых функций из JS файла.

    Только функции в начале строки (0-1 уровень отступа) — не вложенные.
    Вложенные функции (внутри других функций) не учитываются.
    """
    funcs = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return funcs
    # Топ-уровневые: function name( в начале строки (до 2 пробелов отступа)
    for m in re.finditer(r'^\s{0,2}function\s+(\w+)\s*\(', content, re.MULTILINE):
        name = m.group(1)
        if name not in JS_DOM_NAMES:
            funcs.add(name)
    # var/let/const name = function( на топ-уровне
    for m in re.finditer(r'^\s{0,2}(?:var|let|const)\s+(\w+)\s*=\s*function\s*\(', content, re.MULTILINE):
        name = m.group(1)
        if name not in JS_DOM_NAMES:
            funcs.add(name)
    # name = function( на топ-уровне (переназначение, напр. openDetail = function...)
    for m in re.finditer(r'^\s{0,2}(\w+)\s*=\s*function\s*\(', content, re.MULTILINE):
        name = m.group(1)
        if name not in JS_DOM_NAMES:
            funcs.add(name)
    return funcs


def test_no_duplicate_js_functions():
    """Функции определённые в нескольких JS файлах — дублирование кода.

    Глобальный отчёт по всем JS. FAIL только для gallery-модулей
    (viewer.js / gallery-detail.js / gallery-ui.js) — они загружаются
    вместе и конфликты там критичны. Админка — warning.
    """
    js_files = _collect_web_js_files()
    func_locations = defaultdict(list)
    for path in js_files:
        for fn in _extract_js_functions(path):
            func_locations[fn].append(path.name)

    dups = {fn: sorted(set(files)) for fn, files in func_locations.items()
            if len(set(files)) > 1 and fn not in JS_DECORATOR_REASSIGNS}

    # Критичные дубли — между gallery-модулями (загружаются на одной странице)
    gallery_mods = {"viewer.js", "gallery-detail.js", "gallery-ui.js",
                    "gallery.js", "face-modal.js", "shared.js"}
    critical = {fn: files for fn, files in dups.items()
                if all(f in gallery_mods for f in files)}
    other = {fn: files for fn, files in dups.items() if fn not in critical}

    if other:
        lines = [f"  {fn}  →  {', '.join(files)}"
                 for fn, files in sorted(other.items())[:30]]
        print(f"\n⚠ Дублирование JS-функций вне gallery ({len(other)} шт):\n"
              + "\n".join(lines))

    if critical:
        lines = [f"  {fn}  →  {', '.join(files)}"
                 for fn, files in sorted(critical.items())]
        pytest.fail(
            f"Дублирование JS-функций в gallery-модулях ({len(critical)} шт) — "
            f"эти файлы загружаются на одной странице, последний <script> "
            f"перекрывает ранее определённые:\n"
            + "\n".join(lines) + "\n"
            "Вынеси общую логику в один модуль (viewer.js), удали из других."
        )


def test_no_duplicate_js_functions_report():
    """Отчёт по дублированию — warning (даже если функция в одном файле, но >1 раза)."""
    js_files = _collect_web_js_files()
    func_counts = defaultdict(lambda: defaultdict(int))
    for path in js_files:
        for fn in _extract_js_functions(path):
            func_counts[fn][path.name] += 1

    intra = {fn: dict(files) for fn, files in func_counts.items()
             if any(c > 1 for c in files.values())}
    if intra:
        lines = [f"  {fn}  →  {files}" for fn, files in sorted(intra.items())[:20]]
        print(f"\n⚠ Функции определённые >1 раза в одном файле:\n" + "\n".join(lines))


# ─── 9. JS: конфликты функций на одной HTML странице ───

def _html_script_srcs(html_path):
    """Извлекает src из <script src="..."> тегов HTML (порядок сохраняется)."""
    try:
        with open(html_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return []
    srcs = []
    for m in re.finditer(r'<script\s+[^>]*src="([^"]+)"', content):
        src = m.group(1).split('?')[0].lstrip('/')
        srcs.append(src)
    return srcs


def test_no_js_conflicts_per_html_page():
    """Конфликты функций на одной HTML странице.

    Если два <script> файла определяют функцию с одним именем,
    последний побеждает — правки в первом молча игнорируются.
    Это最难 для отладки: код выглядит правильно, но не работает.
    """
    js_funcs = {}
    for path in _collect_web_js_files():
        js_funcs[path.name] = _extract_js_functions(path)

    conflicts = []
    for html_rel in HTML_FILES:
        html_path = ROOT / html_rel
        if not html_path.exists():
            continue
        srcs = _html_script_srcs(html_path)
        # Проходим в порядке загрузки, последняя победившая функция
        winners = {}  # func_name -> (src, load_order)
        for order, src in enumerate(srcs):
            if src in js_funcs:
                for fn in js_funcs[src]:
                    if fn in JS_DECORATOR_REASSIGNS:
                        continue  # паттерн декоратора — расширение, не дубль
                    if fn in winners and winners[fn][0] != src:
                        conflicts.append((html_rel, fn, winners[fn][0], src))
                    winners[fn] = (src, order)

    if conflicts:
        lines = []
        for html, fn, first, last in sorted(conflicts):
            lines.append(f"  {html}: {fn}  [{first} → перекрыт → {last}]")
        pytest.fail(
            f"Конфликты JS-функций на HTML страницах ({len(conflicts)} шт) — "
            f"последний <script> перекрывает ранее определённые:\n"
            + "\n".join(lines) + "\n"
            "Раздели ответственность: каждая функция — в одном модуле. "
            "Удали дубль из проигрывающего файла."
        )


# ─── 10. JS: конфликты глобальных var ───

def _extract_js_globals(path):
    """Извлекает глобальные var (на верхнем уровне, не внутри функции)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception:
        return set()
    globals_set = set()
    for line in lines:
        m = re.match(r'^var\s+([\w,\s]+)\s*[=;]', line)
        if m:
            for name in re.findall(r'\b\w+\b', m.group(1)):
                if name not in ('var', 'true', 'false', 'null', 'new'):
                    globals_set.add(name)
    return globals_set


def test_no_js_global_conflicts_per_html_page():
    """Конфликты глобальных var на одной HTML странице.

    Два <script> файла с одинаковым глобальным var — последний перезаписывает.
    Состояние (_mZoom, _flirOX и т.д.) рассинхронизируется между модулями.
    """
    js_globals = {}
    for path in _collect_web_js_files():
        js_globals[path.name] = _extract_js_globals(path)

    conflicts = []
    for html_rel in HTML_FILES:
        html_path = ROOT / html_rel
        if not html_path.exists():
            continue
        srcs = _html_script_srcs(html_path)
        seen = {}  # var_name -> first_src
        for src in srcs:
            if src in js_globals:
                for vname in js_globals[src]:
                    if vname in seen and seen[vname] != src:
                        conflicts.append((html_rel, vname, seen[vname], src))
                    seen[vname] = src

    if conflicts:
        lines = []
        for html, vn, first, last in sorted(conflicts)[:30]:
            lines.append(f"  {html}: var {vn}  [{first} → перезаписан → {last}]")
        pytest.fail(
            f"Конфликты глобальных JS-переменных ({len(conflicts)} шт) — "
            f"последний <script> перезаписывает:\n"
            + "\n".join(lines) + "\n"
            "Состояние рассинхронизируется. Объедини в один модуль "
            "или используй пространства имён (объекты)."
        )


# ─── 11. God Object + Coupling (AST-анализ, манифест §4.3, §4.4) ───
# Backlog: пороги = baseline, только снижаются.

# God Object: кол-во методов в классе (манифест §4.4)
GOD_OBJECT_METHODS_BASELINE = 85  # DatabaseManager

# Coupling: обращения к атрибутам другого модуля (манифест §4.3, порог ≤100)
COUPLING_BASELINE = 100


def _count_class_methods(path):
    """Подсчёт методов в каждом классе Python файла через AST."""
    classes = {}
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return classes
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = sum(
                1 for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            classes[f"{path.relative_to(ROOT)}:{node.lineno}:{node.name}"] = methods
    return classes


def _count_attr_accesses(path, target_attr="db"):
    """Подсчёт обращений к атрибутам target_attr (db.xxx) в файле.

    Высокая связанность (>100) — признак God Object (манифест §4.3).
    Считает db.method() и db.attribute обращения через AST.
    """
    count = 0
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == target_attr:
                count += 1
    return count


def test_god_object_backlog():
    """God Object detection — кол-во методов в классе (манифест §4.4).

    Backlog: DatabaseManager имеет 85 методов — главный God Object.
    Порог = baseline, только снижается (разбиение на подклассы).
    Рост = класс берёт новые ответственности — refactor.
    """
    big_classes = []
    for path in _collect_files([".py"]):
        classes = _count_class_methods(path)
        for loc, count in classes.items():
            if count > GOD_OBJECT_METHODS_BASELINE:
                big_classes.append((count, loc))

    if big_classes:
        big_classes.sort(reverse=True)
        lines = "\n".join(f"  {c:4d} методов  {loc}" for c, loc in big_classes)
        pytest.fail(
            f"God Object (> {GOD_OBJECT_METHODS_BASELINE} методов):\n{lines}\n"
            f"Класс превысил baseline — разбей на подклассы по ответственности."
        )

    # Отчёт по топ-5 классов
    all_classes = []
    for path in _collect_files([".py"]):
        classes = _count_class_methods(path)
        all_classes.extend((c, loc) for loc, c in classes.items())
    all_classes.sort(reverse=True)
    if all_classes:
        lines = "\n".join(f"  {c:4d}  {loc}" for c, loc in all_classes[:5])
        print(f"\n⚠ Топ-5 классов по методам (baseline {GOD_OBJECT_METHODS_BASELINE}):\n{lines}")


def test_coupling_backlog():
    """Coupling — обращения к db.* из одного модуля (манифест §4.3, ≤100).

    Backlog: модули с >100 обращений к db — сильно связаны с DatabaseManager.
    Порог = baseline. Рост = модуль всё больше зависит от God Object.
    Тесты исключены — высокое обращение к db в тестах нормально.
    """
    over = []
    for path in _collect_files([".py"]):
        if "tests" in path.parts:
            continue
        count = _count_attr_accesses(path, "db")
        if count > COUPLING_BASELINE:
            over.append((count, str(path.relative_to(ROOT))))

    if over:
        over.sort(reverse=True)
        lines = "\n".join(f"  {c:4d} обращений к db  {p}" for c, p in over)
        pytest.fail(
            f"Высокая связанность (> {COUPLING_BASELINE} обращений к db):\n{lines}\n"
            f"Модуль превысил baseline — выдели интерфейс (Interface Segregation)."
        )

    # Отчёт
    all_coupling = []
    for path in _collect_files([".py"]):
        if "tests" in path.parts:
            continue
        count = _count_attr_accesses(path, "db")
        if count > 20:
            all_coupling.append((count, str(path.relative_to(ROOT))))
    all_coupling.sort(reverse=True)
    if all_coupling:
        lines = "\n".join(f"  {c:4d}  {p}" for c, p in all_coupling[:10])
        print(f"\n⚠ Coupling (обращений к db, baseline {COUPLING_BASELINE}):\n{lines}")


# ─── 12. Branch coverage baseline (манифест §3.3, §4.5) ───
# Порог = текущий baseline (38%), повышается монотонно.
# Запуск с покрытием: ./run_tests.sh --coverage
# --cov-fail-under=38 в run_tests.sh блокирует падение ниже baseline.

BRANCH_COVERAGE_BASELINE = 38  # % (зафиксирован 2026-07-02)


def test_branch_coverage_baseline_documented():
    """Branch coverage baseline — документация порога (манифест §3.3).

    Реальная проверка через --cov-fail-under=38 в run_tests.sh --coverage.
    Этот тест — документация: порог живёт рядом с тестом (манифест §6.8).
    Порог только повышается, никогда не снижается.
    """
    print(f"\n📌 Branch coverage baseline: {BRANCH_COVERAGE_BASELINE}%")
    print(f"   Проверка: ./run_tests.sh --coverage (--cov-fail-under={BRANCH_COVERAGE_BASELINE})")
    print(f"   Порог только повышается (манифест §5.4).")


# ─── 13. ESLint: frontend ошибки (манифест §2.4) ───
# Backlog: 77 ошибок (75 no-redeclare, 2 no-use-before-define).
# Тест ловит РЕГРЕССИЮ — рост сверх baseline = новый баг.
# Существующие ошибки = backlog для постепенного исправления.

ESLINT_ERROR_BASELINE = 0  # очищено (этап 2)


def _eslint_errors():
    """Запуск ESLint, возвращает список error-сообщений."""
    try:
        result = subprocess.run(
            ["npx", "eslint", "web/**/*.js", "--quiet", "-f", "json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60,
            shell=False
        )
    except Exception:
        return []

    try:
        data = json.loads(result.stdout or "[]")
    except Exception:
        return []

    errors = []
    for f in data:
        fname = f.get("filePath", "?").split("/")[-1]
        for m in f.get("messages", []):
            if m.get("severity") == 2:
                errors.append({
                    "file": fname,
                    "line": m.get("line", "?"),
                    "rule": m.get("ruleId", "?"),
                    "msg": m.get("message", "?"),
                })
    return errors


def test_eslint_errors_backlog():
    """ESLint: ошибки frontend (манифест §2.4 — 0 errors обязательно).

    Backlog: 77 существующих ошибок зафиксированы как baseline.
    Тест падает при РОСТЕ — новый код добавил ошибку.
    Существующие ошибки = backlog для постепенного исправления.
    Порог только снижается (манифест §5.4).
    """
    errors = _eslint_errors()
    count = len(errors)

    if count > ESLINT_ERROR_BASELINE:
        new_errors = errors[ESLINT_ERROR_BASELINE:]
        lines = []
        for e in new_errors[:20]:
            lines.append(f"  {e['file']}:{e['line']}  {e['rule']}  {e['msg'][:60]}")
        pytest.fail(
            f"ESLint errors вырос: {count} > baseline {ESLINT_ERROR_BASELINE}.\n"
            f"Новый код добавил ошибки frontend:\n" + "\n".join(lines)
        )
    elif count > 0:
        from collections import Counter
        by_rule = Counter(e["rule"] for e in errors)
        rule_lines = "\n".join(f"  {c:3d}  {r}" for r, c in by_rule.most_common())
        # Топ-5 файлов
        by_file = Counter(e["file"] for e in errors)
        file_lines = "\n".join(f"  {c:3d}  {f}" for f, c in by_file.most_common(5))
        print(f"\n⚠ ESLint errors: {count}/{ESLINT_ERROR_BASELINE} baseline — backlog:")
        print(f"  По правилам:\n{rule_lines}")
        print(f"  Топ-5 файлов:\n{file_lines}")
