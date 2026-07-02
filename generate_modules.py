#!/usr/bin/env python3
"""generate_modules.py — генерация MODULES.md из исходников.

Манифест §2.3: test.sh --map — перегенерация MODULES.md.
MODULES.md — карта модулей для агентов: что где находится, зависимости, публичный API.

Автоматически извлекает из AST:
- HTTP endpoint'ы (@router.get/post/put/delete)
- Публичные функции (без _) — API модуля
- Внутренние хелперы (с _) — количество
- Классы с публичными методами
- Зависимости от других модулей проекта
- Docstrings (если есть)

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

# Модули проекта — для отслеживания внутренних зависимостей
PROJECT_MODULES = {
    "database", "config", "main", "mqtt_client", "system_helpers",
    "system_monitor", "persona", "thumbnails", "flir_parser",
    "video_metadata", "vlm_log", "scanner", "face_detection",
    "face_embeddings", "cluster_personas", "describe_photo",
    "describe_photo_ollama", "process_photos", "match_personas",
    "api", "api.photos", "api.persons", "api.catalog", "api.models",
    "api.search", "api.video", "api.flir", "api.validators",
}


def _collect_py_files():
    result = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                result.append(Path(dirpath) / f)
    return sorted(result)


def _extract_endpoints(tree):
    """Извлекает HTTP endpoint'ы из @router/@app декораторов."""
    endpoints = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            method = None
            path = None
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Attribute):
                    method = func.attr
                    if method in ("get", "post", "put", "delete", "patch"):
                        if dec.args:
                            arg = dec.args[0]
                            if isinstance(arg, ast.Constant):
                                path = arg.value
                            elif isinstance(arg, ast.JoinedStr):
                                path = ast.unparse(arg)
            if method and path:
                endpoints.append({
                    "method": method.upper(),
                    "path": path,
                    "func": node.name,
                    "line": node.lineno,
                })
    return endpoints


def _extract_functions(tree):
    """Разделяет функции на публичные (API) и внутренние (_)."""
    public = []
    private_count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.col_offset == 0:  # top-level only
                doc = ast.get_docstring(node)
                doc_short = doc.split("\n")[0][:80] if doc else ""
                if node.name.startswith("_"):
                    private_count += 1
                else:
                    public.append({
                        "name": node.name,
                        "line": node.lineno,
                        "doc": doc_short,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                    })
    return public, private_count


def _extract_classes(tree):
    """Извлекает классы с публичными методами."""
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            public_methods = []
            private_count = 0
            doc = ast.get_docstring(node)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_"):
                        private_count += 1
                    else:
                        mdoc = ast.get_docstring(item)
                        public_methods.append({
                            "name": item.name,
                            "doc": mdoc.split("\n")[0][:60] if mdoc else "",
                        })
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "public": public_methods,
                "private_count": private_count,
                "doc": doc.split("\n")[0][:80] if doc else "",
            })
    return classes


def _extract_deps(tree):
    """Извлекает зависимости от других модулей проекта."""
    deps = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module in PROJECT_MODULES or any(
                node.module.startswith(m + ".") for m in PROJECT_MODULES
            ):
                deps.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in PROJECT_MODULES:
                    deps.add(alias.name)
    return sorted(deps)


def _analyze_module(path):
    """Полный анализ модуля через AST."""
    info = {
        "path": str(path.relative_to(ROOT)),
        "lines": 0,
        "endpoints": [],
        "public_funcs": [],
        "private_func_count": 0,
        "classes": [],
        "deps": [],
        "module_doc": "",
    }
    try:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        info["lines"] = source.count("\n") + 1
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return info

    info["module_doc"] = (ast.get_docstring(tree) or "").split("\n")[0][:100]
    info["endpoints"] = _extract_endpoints(tree)
    info["public_funcs"], info["private_func_count"] = _extract_functions(tree)
    info["classes"] = _extract_classes(tree)
    info["deps"] = _extract_deps(tree)

    return info


def _format_module(m):
    """Форматирует один модуль как секцию MODULES.md."""
    lines = []
    fname = Path(m["path"]).name
    rel = m["path"]

    # Заголовок
    lines.append(f"#### `{fname}` ({m['lines']} строк)")
    if m["module_doc"]:
        lines.append(f"*{m['module_doc']}*")
    lines.append(f"`{rel}`")
    lines.append("")

    # Зависимости
    if m["deps"]:
        deps_str = ", ".join(f"`{d}`" for d in m["deps"])
        lines.append(f"**Зависит от:** {deps_str}")
        lines.append("")

    # Endpoint'ы
    if m["endpoints"]:
        lines.append("**Endpoint'ы:**")
        lines.append("| Method | Path | Handler |")
        lines.append("|--------|------|---------|")
        for e in m["endpoints"]:
            lines.append(f"| {e['method']} | `{e['path']}` | {e['func']} |")
        lines.append("")

    # Публичные функции
    if m["public_funcs"]:
        lines.append("**Публичные функции:**")
        lines.append("| Функция | Описание |")
        lines.append("|---------|----------|")
        for f in m["public_funcs"]:
            async_tag = "async " if f["is_async"] else ""
            lines.append(f"| {async_tag}`{f['name']}` | {f['doc']} |")
        lines.append("")

    # Внутренние хелперы
    if m["private_func_count"]:
        lines.append(f"**Внутренние хелперы:** {m['private_func_count']} (_-функций)")
        lines.append("")

    # Классы
    for c in m["classes"]:
        total = len(c["public"]) + c["private_count"]
        lines.append(f"**Класс `{c['name']}`** ({total} методов: {len(c['public'])} публичных, {c['private_count']} внутренних)")
        if c["doc"]:
            lines.append(f"*{c['doc']}*")
        if c["public"]:
            lines.append("| Метод | Описание |")
            lines.append("|-------|----------|")
            for meth in c["public"]:
                lines.append(f"| `{meth['name']}` | {meth['doc']} |")
        lines.append("")

    return lines


def generate():
    files = _collect_py_files()
    modules = [_analyze_module(p) for p in files]

    # Группировка по директориям
    by_dir = defaultdict(list)
    for m in modules:
        d = str(Path(m["path"]).parent)
        by_dir[d].append(m)

    total_lines = sum(m["lines"] for m in modules)
    total_endpoints = sum(len(m["endpoints"]) for m in modules)
    total_public = sum(len(m["public_funcs"]) for m in modules)

    lines = [
        "# MODULES.md — карта модулей проекта",
        "",
        "> Сгенерировано `generate_modules.py` (манифест §2.3: --map режим).",
        "> Не редактировать вручную — перегенерировать: `./run_tests.sh --map`",
        "",
        f"Всего Python файлов: {len(modules)} | Строк: {total_lines} | Endpoint'ов: {total_endpoints} | Публичных функций: {total_public}",
        "",
        "## Структура по директориям",
        "",
    ]

    for directory in sorted(by_dir.keys()):
        mods = by_dir[directory]
        dir_total = sum(m["lines"] for m in mods)
        dir_endpoints = sum(len(m["endpoints"]) for m in mods)
        dir_display = directory if directory != "." else "/ (корень)"

        lines.append(f"### `{dir_display}` ({dir_total} строк, {len(mods)} файлов, {dir_endpoints} endpoints)")
        lines.append("")

        # Сводная таблица
        lines.append("| Файл | Строк | Endpoints | Публ.функций | Хелперов | Классы |")
        lines.append("|------|-------|-----------|-------------|----------|--------|")
        for m in sorted(mods, key=lambda x: -x["lines"]):
            fname = Path(m["path"]).name
            n_ep = len(m["endpoints"])
            n_pub = len(m["public_funcs"])
            n_priv = m["private_func_count"]
            cls_names = ", ".join(c["name"] for c in m["classes"]) or "—"
            lines.append(f"| {fname} | {m['lines']} | {n_ep} | {n_pub} | {n_priv} | {cls_names} |")
        lines.append("")

        # Детали по каждому модулю
        for m in sorted(mods, key=lambda x: -x["lines"]):
            # Пропускаем тривиальные файлы (< 20 строк, 0 endpoints, 0 public funcs, 0 classes)
            if (m["lines"] < 20 and not m["endpoints"] and not m["public_funcs"] and not m["classes"]):
                continue
            lines.extend(_format_module(m))

    # God Objects
    lines.append("## God Objects (классы с >20 методов)")
    lines.append("")
    big_classes = []
    for m in modules:
        for c in m["classes"]:
            total = len(c["public"]) + c["private_count"]
            if total > 20:
                big_classes.append((total, len(c["public"]), c["private_count"], m["path"], c["name"]))
    big_classes.sort(reverse=True)
    if big_classes:
        lines.append("| Всего | Публ. | Внутр. | Файл | Класс |")
        lines.append("|-------|-------|--------|------|-------|")
        for total, pub, priv, path, name in big_classes:
            lines.append(f"| {total} | {pub} | {priv} | {path} | {name} |")
    else:
        lines.append("Нет классов с >20 методов.")
    lines.append("")

    # Топ-10 файлов
    lines.append("## Топ-10 файлов по размеру")
    lines.append("")
    big_files = sorted(modules, key=lambda x: -x["lines"])[:10]
    lines.append("| Строк | Файл | Endpoints | Хелперов |")
    lines.append("|-------|------|-----------|----------|")
    for m in big_files:
        lines.append(f"| {m['lines']} | {m['path']} | {len(m['endpoints'])} | {m['private_func_count']} |")
    lines.append("")

    output = "\n".join(lines)
    out_path = ROOT / "MODULES.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"✅ MODULES.md сгенерирован: {out_path} ({len(modules)} модулей, {total_endpoints} endpoints)")


if __name__ == "__main__":
    generate()
