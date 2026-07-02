#!/usr/bin/env python3
"""generate_modules.py — генерация MODULES.md из исходников.

Манифест §2.3: test.sh --map — перегенерация MODULES.md.
MODULES.md — карта модулей для агентов: что где находится, зависимости, размеры.

Запуск:
  /opt/gailray/venv/bin/python3 generate_modules.py
  ./run_tests.sh --map
"""

import ast
import os
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent
SKIP_DIRS = {
    "venv", "venv_vllm", "__pycache__", ".git", ".git_old",
    "llama.cpp", ".pytest_cache", ".ruff_cache", "data",
    "thumbnails", "logs", "build", "dist", "node_modules",
}


def _collect_py_files():
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                result.append(Path(dirpath) / f)
    return sorted(result)


def _analyze_module(path):
    """Анализирует Python модуль через AST."""
    info = {
        "path": str(path.relative_to(ROOT)),
        "lines": 0,
        "classes": [],
        "functions": [],
        "imports": [],
    }
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        info["lines"] = source.count("\n") + 1
        tree = ast.parse(source)
    except Exception:
        return info

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = sum(
                1 for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            info["classes"].append({"name": node.name, "methods": methods, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.col_offset == 0:
            info["functions"].append({"name": node.name, "line": node.lineno})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                if not node.module.startswith(("__", "typing")):
                    info["imports"].append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if not alias.name.startswith(("__", "typing")):
                        info["imports"].append(alias.name)

    return info


def generate():
    files = _collect_py_files()
    modules = [_analyze_module(p) for p in files]

    # Группировка по директориям
    by_dir = defaultdict(list)
    for m in modules:
        d = str(Path(m["path"]).parent)
        by_dir[d].append(m)

    lines = [
        "# MODULES.md — карта модулей проекта",
        "",
        "> Сгенерировано `generate_modules.py` (манифест §2.3: --map режим).",
        "> Не редактировать вручную — перегенерировать: `./run_tests.sh --map`",
        "",
        f"Всего Python файлов: {len(modules)}",
        f"Всего строк кода: {sum(m['lines'] for m in modules)}",
        "",
        "## Структура по директориям",
        "",
    ]

    for directory in sorted(by_dir.keys()):
        mods = by_dir[directory]
        total_lines = sum(m["lines"] for m in mods)
        dir_display = directory if directory != "." else "/ (корень)"
        lines.append(f"### `{dir_display}` ({total_lines} строк, {len(mods)} файлов)")
        lines.append("")
        lines.append("| Файл | Строк | Классы | Функции | Импорты |")
        lines.append("|------|-------|--------|---------|---------|")
        for m in sorted(mods, key=lambda x: -x["lines"]):
            fname = Path(m["path"]).name
            classes = len(m["classes"])
            funcs = len(m["functions"])
            imports = len(set(m["imports"]))
            lines.append(f"| {fname} | {m['lines']} | {classes} | {funcs} | {imports} |")
        lines.append("")

    # God Objects (классы с >20 методов)
    lines.append("## God Objects (классы с >20 методов)")
    lines.append("")
    big_classes = []
    for m in modules:
        for c in m["classes"]:
            if c["methods"] > 20:
                big_classes.append((c["methods"], m["path"], c["name"], c["line"]))
    big_classes.sort(reverse=True)
    if big_classes:
        lines.append("| Методов | Файл | Класс | Строка |")
        lines.append("|---------|------|-------|--------|")
        for count, path, name, line in big_classes:
            lines.append(f"| {count} | {path} | {name} | {line} |")
    else:
        lines.append("Нет классов с >20 методов.")
    lines.append("")

    # Топ-10 файлов по размеру
    lines.append("## Топ-10 файлов по размеру")
    lines.append("")
    big_files = sorted(modules, key=lambda x: -x["lines"])[:10]
    lines.append("| Строк | Файл |")
    lines.append("|-------|------|")
    for m in big_files:
        lines.append(f"| {m['lines']} | {m['path']} |")
    lines.append("")

    output = "\n".join(lines)
    out_path = ROOT / "MODULES.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"✅ MODULES.md сгенерирован: {out_path} ({len(modules)} модулей)")


if __name__ == "__main__":
    generate()
