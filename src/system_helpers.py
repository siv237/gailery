import os
import sys
import subprocess
import importlib
from pathlib import Path

from config import PROJECT_ROOT


def _determine_pipeline_step(flag_dir, mq, mqtt_states):
    import datetime as dt
    current_step = "idle"
    step_details = ""
    step_started_at = None
    pipeline_started_at = None

    mqtt_step = mq.get_current_step() if mq else "idle"
    if mqtt_step != "idle":
        current_step = mqtt_step
        step_details = mqtt_step.upper()
    else:
        pipeline_flag = os.path.join(flag_dir, "pipeline")
        if os.path.exists(pipeline_flag):
            try:
                mtime = os.path.getmtime(pipeline_flag)
                pipeline_started_at = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
            except Exception:
                pass
        for proc_name, fname in [("DESCRIBE", "describe"), ("INGEST", "ingest"), ("FACES", "faces"), ("EXIF", "exif"), ("EMBED", "embed"), ("PIPELINE", "pipeline")]:
            fpath = os.path.join(flag_dir, fname)
            if os.path.exists(fpath):
                current_step = proc_name.lower()
                step_details = proc_name
                try:
                    mtime = os.path.getmtime(fpath)
                    step_started_at = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
                except Exception:
                    pass
                break

    if mq and current_step != "idle":
        pipeline_state = mqtt_states.get("pipeline", {})
        if pipeline_state.get("status") == "running" and pipeline_state.get("pid"):
            try:
                mtime = os.path.getmtime(f"/proc/{pipeline_state['pid']}")
                pipeline_started_at = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
            except Exception:
                pass

    return current_step, step_details, step_started_at, pipeline_started_at


def _get_git_info():
    try:
        commit = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        date = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        return commit, date
    except Exception:
        return None, None


def _read_log_info(log_path):
    progress_info = {}
    tag_map = {"DESCRIBE": "describe", "INGEST": "ingest", "FACES": "faces", "EXIF": "exif", "EMBED": "embed"}
    faces_phase = ""
    faces_detail = ""
    try:
        with open(log_path, "r") as f:
            tail_lines = f.readlines()[-200:]
    except Exception:
        return {}, "", ""
    for line in tail_lines:
        for tag, key in tag_map.items():
            if "[" + tag + "]" in line:
                progress_info[key] = line.strip()
    for line in reversed(tail_lines[-100:]):
        if "[FACES]" in line or "[CLUSTER]" in line:
            stripped = line.strip()
            if "detecting " in stripped:
                faces_phase = "detecting"
                faces_detail = stripped.split("detecting ")[-1].replace("...", "")
                break
            elif "lance write " in stripped and "done" not in stripped:
                faces_phase = "lance_write"
                faces_detail = stripped.split("lance write ")[-1].replace(" vectors...", "") + " vectors"
                break
            elif "lance write done" in stripped:
                faces_phase = "lance_write"
                faces_detail = "done"
                break
            elif "Running DBSCAN" in stripped:
                faces_phase = "clustering"
                faces_detail = "DBSCAN"
                break
            elif "[CLUSTER]" in stripped and "DBSCAN on" in stripped:
                faces_phase = "clustering"
                faces_detail = "DBSCAN"
                break
            elif "[CLUSTER]" in stripped and "Matched" in stripped:
                faces_phase = "clustering"
                faces_detail = "matching"
                break
            elif "Detection done" in stripped:
                faces_phase = "detection_done"
                faces_detail = stripped.split("Detection done: ")[-1] if "Detection done: " in stripped else ""
                break
            elif "Clustering done" in stripped:
                faces_phase = "done"
                faces_detail = ""
                break
            elif "InsightFace loaded" in stripped:
                faces_phase = "loading"
                faces_detail = "InsightFace"
                break
            elif "Found " in stripped and "photos needing" in stripped:
                faces_phase = "loading"
                faces_detail = stripped.split("Found ")[-1].split(" photos")[0] + " photos"
                break
    return progress_info, faces_phase, faces_detail


def _collect_disks():
    import psutil
    disks = []
    skip_prefixes = ('/dev', '/proc', '/sys', '/run', '/boot', '/usr', '/lib', '/etc', '/tmp')
    skip_fstypes = ('tmpfs', 'devtmpfs', 'squashfs', 'overlay', 'aufs')
    seen_mounts = set()
    for mp in psutil.disk_partitions():
        mnt = mp.mountpoint
        if mnt in seen_mounts:
            continue
        if any(mnt.startswith(p + '/') or mnt == p for p in skip_prefixes):
            continue
        if mp.fstype in skip_fstypes or mp.device in ('none', 'tmpfs'):
            continue
        try:
            u = psutil.disk_usage(mnt)
            disks.append({
                "mount": mnt, "device": mp.device, "fstype": mp.fstype,
                "total_gib": round(u.total / (1024**3), 1), "used_gib": round(u.used / (1024**3), 1),
                "free_gib": round(u.free / (1024**3), 1), "percent": u.percent,
            })
            seen_mounts.add(mnt)
        except Exception:
            pass
    return disks


def _collect_gpu_processes():
    gpu_processes = []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        for line in out.stdout.strip().split("\n"):
            if not line.strip(): continue
            parts = [p.strip() for p in line.split(", ", 2)]
            if len(parts) >= 3:
                gpu_processes.append({"pid": parts[0], "name": parts[1], "vram_mb": parts[2]})
    except Exception:
        pass
    return gpu_processes


def _collect_top_procs():
    import psutil
    top_procs = []
    for p in sorted(psutil.process_iter(['pid','name','memory_percent','cpu_percent']),
                    key=lambda x: x.info.get('memory_percent', 0) or 0, reverse=True)[:8]:
        try:
            top_procs.append({
                "pid": p.info['pid'], "name": p.info['name'] or '?',
                "mem_pct": round(p.info['memory_percent'] or 0, 2),
                "cpu_pct": round(p.info['cpu_percent'] or 0, 1),
            })
        except Exception:
            pass
    return top_procs


def _collect_pipeline_stats(db):
    q = db.sqlite.execute
    pl = {
        "cf_total": q("SELECT COUNT(*) FROM catalog_files WHERE deleted = 0").fetchone()[0],
        "cf_canonical": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0").fetchone()[0],
        "cf_duplicates": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 0 AND deleted = 0").fetchone()[0],
        "cf_unhashed": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND content_hash IS NULL").fetchone()[0],
        "cf_empty": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND size = 0").fetchone()[0],
        "cf_deleted": q("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1").fetchone()[0],
        "cf_auto_missing": q("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1 AND deleted_type = 'auto_missing'").fetchone()[0],
        "cf_auto_empty": q("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1 AND deleted_type = 'auto_empty'").fetchone()[0],
        "cf_ingested": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND ingested = 1").fetchone()[0],
        "cf_described": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND described = 1").fetchone()[0],
        "cf_faces_done": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND faces_done = 1").fetchone()[0],
        "cf_embedded": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND embedded = 1").fetchone()[0],
        "cf_exif_done": q("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND exif_done = 1").fetchone()[0],
        "p_alive": q("SELECT COUNT(*) FROM photos WHERE deleted = 0").fetchone()[0],
        "p_video": q("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND media_type = 'video'").fetchone()[0],
        "p_photo": q("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND (media_type IS NULL OR media_type != 'video')").fetchone()[0],
        "p_described": q("SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE cf.is_canonical = 1 AND cf.described = 1 AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')").fetchone()[0],
        "p_faces_done": q("SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE cf.is_canonical = 1 AND cf.faces_done = 1 AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')").fetchone()[0],
        "p_faces_present": q("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND faces_present = 1").fetchone()[0],
        "p_embedded": q("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND embedded = 1").fetchone()[0],
        "p_exif": q("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND exif_checked = 1").fetchone()[0],
        "f_total": q("SELECT COUNT(*) FROM faces").fetchone()[0],
        "f_with_persona": q("SELECT COUNT(*) FROM faces WHERE persona_id IS NOT NULL").fetchone()[0],
        "f_with_hash": q("SELECT COUNT(*) FROM faces WHERE content_hash IS NOT NULL").fetchone()[0],
        "personas_total": q("SELECT COUNT(*) FROM personas").fetchone()[0],
        "personas_named": q("SELECT COUNT(*) FROM personas WHERE display_name IS NOT NULL AND display_name != ''").fetchone()[0],
        "pct_described": 0, "pct_faces": 0, "pct_embedded": 0, "pct_exif": 0,
    }
    pp = max(pl["p_photo"], 1)
    pl["pct_described"] = round(pl["p_described"] / pp * 100, 1)
    pl["pct_faces"] = round(pl["p_faces_done"] / pp * 100, 1)
    pl["pct_embedded"] = round(pl["p_embedded"] / pp * 100, 1)
    pl["pct_exif"] = round(pl["cf_exif_done"] / max(pl["cf_canonical"], 1) * 100, 1)
    return pl


def _get_prompts():
    from database import get_db
    db = get_db()
    prompts = []
    _project_root = str(Path(__file__).parent.parent)
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    for mod_name in ("vision_describe", "enrich_description"):
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass
    try:
        vd = importlib.import_module("vision_describe")
        vlm_prompt = db.get_setting("prompt_vlm_system") or vd.SYSTEM_PROMPT.strip()
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": vlm_prompt, "d": "Системный промт описания фото (без имён)", "env_key": "prompt_vlm_system", "editable": True, "default": vd.SYSTEM_PROMPT.strip()})
        vlm_prompt_names = db.get_setting("prompt_vlm_system_names") or vd.SYSTEM_PROMPT_WITH_NAMES.strip()
        prompts.append({"k": "VLM SYSTEM_PROMPT (с именами)", "v": vlm_prompt_names, "d": "Промт когда есть распознанные лица", "env_key": "prompt_vlm_system_names", "editable": True, "default": vd.SYSTEM_PROMPT_WITH_NAMES.strip()})
    except Exception as e:
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт описания фото"})
    try:
        ed = importlib.import_module("enrich_description")
        enrich_prompt = db.get_setting("prompt_enrich_system") or ed.SYSTEM_PROMPT.strip()
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": enrich_prompt, "d": "Системный промт обогащения описания", "env_key": "prompt_enrich_system", "editable": True, "default": ed.SYSTEM_PROMPT.strip()})
        tools = getattr(ed, "TOOLS", None)
        if tools:
            for t in tools:
                fn = t.get("function", {})
                name = fn.get("name", "?")
                desc = fn.get("description", "")
                params = fn.get("parameters", {}).get("properties", {})
                param_str = ", ".join(f"{p}: {d.get('type','?')}" for p, d in params.items()) if params else "нет"
                env_key = f"prompt_enrich_tool_{name}"
                tool_val = db.get_setting(env_key) or f"{desc} | Параметры: {param_str}"
                tool_default = f"{desc} | Параметры: {param_str}"
                prompts.append({"k": f"Enrich tool: {name}", "v": tool_val, "d": "Инструмент обогащения", "env_key": env_key, "editable": True, "default": tool_default})
    except Exception as e:
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт обогащения описания"})
    return prompts


def _build_config_groups():
    from config import (
        PHOTO_SHARE_PATH, DATA_DIR, THUMBNAILS_DIR, LOGS_DIR, LLAMA_CPP_DIR,
        VENV_PYTHON, MQTT_HOST, MQTT_PORT, MQTT_WS_PORT, GPU_LOCK_TIMEOUT,
        THUMBNAIL_SIZE, THUMBNAIL_FORMAT, SUPPORTED_EXTENSIONS,
        FACE_DETECTION_MODEL, FACE_CONFIDENCE_THRESHOLD,
        EMBEDDING_MODEL, EMBEDDING_DIM, BATCH_SIZE, MAX_WORKERS,
        LANCEDB_PATH, FLAG_DIR, LOG_FILE,
        SERVICE_NAME, MQTT_PREFIX,
        OLLAMA_MODE, OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL, OLLAMA_EMBED_CHUNK, OLLAMA_DESCRIBE_MODEL,
    )
    try:
        from config import embed_backend, search_backend, describe_backend
    except ImportError:
        embed_backend = search_backend = describe_backend = ""
    from database import get_db
    return [
        {
            "name": "Сервис",
            "icon": "\U0001f3e0",
            "params": [
                {"k": "GALLERY_SERVICE_NAME", "v": SERVICE_NAME, "d": "Имя сервиса (systemd, MQTT prefix по умолчанию)", "env_key": "GALLERY_SERVICE_NAME", "editable": True},
                {"k": "GALLERY_MQTT_PREFIX", "v": MQTT_PREFIX, "d": "MQTT префикс (топики: {prefix}/worker/...)", "env_key": "GALLERY_MQTT_PREFIX", "editable": True},
            ]
        },
        {
            "name": "Пути",
            "icon": "\U0001f4c1",
            "params": [
                {"k": "Корни фото (catalog_roots)", "v": ", ".join(r["root_path"] for r in get_db().get_catalog_roots()), "d": "Динамические корни из каталога", "path": True},
                {"k": "PHOTO_SHARE_PATH", "v": str(PHOTO_SHARE_PATH), "d": "Корневая папка фото", "path": True, "env_key": "PHOTO_SHARE_PATH", "editable": True},
                {"k": "DATA_DIR", "v": str(DATA_DIR), "d": "Директория данных (БД, LanceDB, флаги)", "path": True, "env_key": "GALLERY_DATA_DIR", "editable": True},
                {"k": "THUMBNAILS_DIR", "v": str(THUMBNAILS_DIR), "d": "Директория превью", "path": True, "env_key": "GALLERY_THUMBNAILS_DIR", "editable": True},
                {"k": "LOGS_DIR", "v": str(LOGS_DIR), "d": "Директория логов", "path": True, "env_key": "GALLERY_LOGS_DIR", "editable": True},
                {"k": "LLAMA_CPP_DIR", "v": str(LLAMA_CPP_DIR), "d": "Путь к llama.cpp", "path": True, "env_key": "LLAMA_CPP_DIR", "editable": True},
                {"k": "LANCEDB_PATH", "v": str(LANCEDB_PATH), "d": "Путь к LanceDB", "path": True},
                {"k": "LOG_FILE", "v": str(LOG_FILE), "d": "Файл лога пайплайна"},
                {"k": "FLAG_DIR", "v": str(FLAG_DIR), "d": "Директория флагов воркеров", "path": True},
            ]
        },
        {
            "name": "MQTT",
            "icon": "\U0001f4e1",
            "params": [
                {"k": "MQTT_HOST", "v": MQTT_HOST, "d": "Адрес MQTT брокера", "env_key": "GALLERY_MQTT_HOST", "editable": True},
                {"k": "MQTT_PORT", "v": str(MQTT_PORT), "d": "TCP порт MQTT", "env_key": "GALLERY_MQTT_PORT", "editable": True},
                {"k": "MQTT_WS_PORT", "v": str(MQTT_WS_PORT), "d": "WebSocket порт MQTT", "env_key": "GALLERY_MQTT_WS_PORT", "editable": True},
                {"k": "GPU_LOCK_TIMEOUT", "v": str(GPU_LOCK_TIMEOUT), "d": "Таймаут захвата GPU (сек)", "env_key": "GALLERY_GPU_LOCK_TIMEOUT", "editable": True},
            ]
        },
        {
            "name": "Маршрутизация AI",
            "icon": "\U0001f500",
            "params": [
                {"k": "OLLAMA_MODE", "v": OLLAMA_MODE, "d": "Режим: local | ollama (глобальный override)", "env_key": "OLLAMA_MODE", "editable": True},
                {"k": "OLLAMA_BASE_URL", "v": OLLAMA_BASE_URL, "d": "URL Ollama сервера", "url": True, "env_key": "OLLAMA_BASE_URL", "editable": True},
                {"k": "OLLAMA_EMBED_MODEL", "v": OLLAMA_EMBED_MODEL, "d": "Модель Ollama для эмбеддингов", "env_key": "OLLAMA_EMBED_MODEL", "editable": True},
                {"k": "OLLAMA_EMBED_CHUNK", "v": str(OLLAMA_EMBED_CHUNK), "d": "Размер чанка Ollama эмбеддингов", "env_key": "OLLAMA_EMBED_CHUNK", "editable": True},
                {"k": "OLLAMA_DESCRIBE_MODEL", "v": OLLAMA_DESCRIBE_MODEL, "d": "Модель Ollama для описания фото", "env_key": "OLLAMA_DESCRIBE_MODEL", "editable": True},
                {"k": "embed_backend", "v": embed_backend or "(из OLLAMA_MODE)", "d": "Бэкенд эмбеддингов: local | ollama", "env_key": "embed_backend", "editable": True},
                {"k": "search_backend", "v": search_backend or "(из OLLAMA_MODE)", "d": "Бэкенд поиска: local | ollama", "env_key": "search_backend", "editable": True},
                {"k": "describe_backend", "v": describe_backend or "(из OLLAMA_MODE)", "d": "Бэкенд описания: local | ollama", "env_key": "describe_backend", "editable": True},
            ]
        },
        {
            "name": "Модели",
            "icon": "\U0001f9e0",
            "params": [
                {"k": "FACE_DETECTION_MODEL", "v": FACE_DETECTION_MODEL, "d": "Модель детекции лиц"},
                {"k": "FACE_CONFIDENCE_THRESHOLD", "v": str(FACE_CONFIDENCE_THRESHOLD), "d": "Порог уверенности детекции лиц"},
                {"k": "EMBEDDING_MODEL (лица)", "v": "facenet", "d": "Модель эмбеддингов лиц"},
                {"k": "EMBEDDING_DIM (лица)", "v": "128", "d": "Размерность эмбеддингов лиц"},
                {"k": "EMBEDDING_MODEL (текст)", "v": EMBEDDING_MODEL, "d": "Модель текстовых эмбеддингов"},
                {"k": "EMBEDDING_DIM (текст)", "v": str(EMBEDDING_DIM), "d": "Размерность текстовых эмбеддингов"},
                {"k": "VLM модель", "v": "Qwen3.5-4B-Q4_K_M.gguf", "d": "VLM модель описания фото"},
                {"k": "VLM порт", "v": "8101", "d": "Порт llama-server VLM"},
                {"k": "VLM слоты", "v": "6", "d": "Параллельные слоты VLM"},
                {"k": "VLM контекст", "v": "8192", "d": "Размер контекста VLM (токенов)"},
                {"k": "VLM макс.токены", "v": "256", "d": "Макс. токенов генерации VLM"},
                {"k": "VLM температура", "v": "0.1", "d": "Температура сэмплирования VLM"},
                {"k": "VLM макс.размер фото", "v": "1280px", "d": "Макс. размер фото для VLM"},
                {"k": "VLM JPEG quality", "v": "85", "d": "Качество JPEG при подготовке фото"},
                {"k": "Enrich порт", "v": "8103", "d": "Порт llama-server обогащения"},
                {"k": "Enrich макс.токены", "v": "2048", "d": "Макс. токены обогащения"},
                {"k": "Enrich температура", "v": "0.4", "d": "Температура сэмплирования обогащения"},
                {"k": "Embed модель", "v": "Qwen3-Embedding-0.6B (transformers)", "d": "Модель семантической индексации"},
            ]
        },
        {
            "name": "Промты",
            "icon": "\U0001f4dd",
            "params": _get_prompts(),
        },
        {
            "name": "Лица и кластеризация",
            "icon": "\U0001f464",
            "params": [
                {"k": "InsightFace модель", "v": "buffalo_l", "d": "Модель анализа лиц"},
                {"k": "Детекция размер", "v": "640x640", "d": "Размер входа детекции"},
                {"k": "DBSCAN eps", "v": "0.4", "d": "Эпсилон кластеризации DBSCAN"},
                {"k": "DBSCAN min_samples", "v": "2", "d": "Мин. размер кластера DBSCAN"},
                {"k": "MATCH_THRESHOLD", "v": "0.4", "d": "Порог назначения лица персоне"},
            ]
        },
        {
            "name": "Обработка",
            "icon": "\u2699\ufe0f",
            "params": [
                {"k": "THUMBNAIL_SIZE", "v": str(THUMBNAIL_SIZE), "d": "Макс. размер превью (px)"},
                {"k": "THUMBNAIL_FORMAT", "v": THUMBNAIL_FORMAT, "d": "Формат превью"},
                {"k": "BATCH_SIZE", "v": str(BATCH_SIZE), "d": "Размер батча по умолчанию"},
                {"k": "MAX_WORKERS", "v": str(MAX_WORKERS), "d": "Макс. параллельных воркеров"},
                {"k": "EMBED_BATCH_SIZE", "v": "64", "d": "Батч эмбеддингов"},
                {"k": "LANCE_FLUSH_SIZE", "v": "2048", "d": "Размер буфера LanceDB"},
                {"k": "EXIF_READ_THREADS", "v": "8", "d": "Потоки чтения EXIF"},
                {"k": "SUPPORTED_EXTENSIONS", "v": ", ".join(sorted(SUPPORTED_EXTENSIONS)), "d": "Расширения фото"},
            ]
        },
        {
            "name": "Сторожевой пёс",
            "icon": "\U0001f436",
            "params": [
                {"k": "CHECK_INTERVAL", "v": "10", "d": "Интервал проверки (сек)"},
                {"k": "RESTART_COOLDOWN", "v": "60", "d": "Кулдаун рестарта (сек)"},
                {"k": "Макс. рестартов/5мин", "v": "3", "d": "Лимит рестартов за 5 минут"},
            ]
        },
        {
            "name": "Веб-сервер",
            "icon": "\U0001f310",
            "params": [
                {"k": "uvicorn порт", "v": "8000", "d": "Порт веб-сервера"},
                {"k": "CORS origins", "v": "*", "d": "Разрешённые CORS origins"},
                {"k": "STATUS_CACHE_TTL", "v": "5", "d": "Кэш статуса (сек)"},
            ]
        },
    ]
