"""FastAPI application for Gailery Photo Gallery"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse
import asyncio
import logging
import importlib
import sys
import os
import requests

from database import DatabaseManager, get_db
from config import LANCEDB_PATH, LOG_FILE, FLAG_DIR, VENV_PYTHON, PROJECT_ROOT, DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_manager = None
_monitor_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_manager, _monitor_task
    logger.info("Starting application...")
    db_manager = get_db()
    logger.info("Database connected")

    pass
    yield
    logger.info("Shutting down application...")
    if _monitor_task:
        _monitor_task.cancel()


app = FastAPI(
    title="Gailery Photo Gallery API",
    description="AI-powered photo gallery with face search",
    version="0.1.0",
    lifespan=lifespan
)


class BfcacheFixMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            raw = scope.get("raw_path", b"").decode() if scope.get("raw_path") else ""
            path = scope.get("path", "")
            if "http://" in path or "https://" in path or "http%3A" in raw.lower() or "http%3A" in path.lower():
                cleaned = raw.lstrip("/") if "http%3A" in raw.lower() else path.lstrip("/")
                if not cleaned:
                    cleaned = path.lstrip("/")
                decoded = unquote(cleaned) if "http%3A" in cleaned.lower() else cleaned
                parsed = urlparse(decoded)
                new_path = parsed.path or "/"
                logger.info(f"[BFCACHE-FIX] raw={raw!r} path={path!r} -> {new_path}")
                scope["path"] = new_path
                scope["raw_path"] = new_path.encode()
                if parsed.query:
                    scope["query_string"] = parsed.query.encode()
            if scope.get("method") == "HEAD":
                scope["method"] = "GET"
                async def send_head(message):
                    if message["type"] == "http.response.body":
                        message["body"] = b""
                    await send(message)
                await self.app(scope, receive, send_head)
                return
        await self.app(scope, receive, send)


app.add_middleware(BfcacheFixMiddleware)


class BrowserErrorRedirectMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope_headers = scope.get("headers", [])
            accept = ""
            path = scope.get("path", "")
            for k, v in scope_headers:
                if k == b"accept":
                    accept = v.decode()
            if "text/html" in accept and path.startswith("/api/"):
                captured_status = None
                async def send_with_check(message):
                    nonlocal captured_status
                    if message["type"] == "http.response.start":
                        captured_status = message.get("status", 200)
                    if captured_status is not None and captured_status >= 400 and message["type"] == "http.response.body" and not message.get("more_body", False):
                        redirect_msg_start = {"type": "http.response.start", "status": 302, "headers": [[b"location", b"/gallery"], [b"content-length", b"0"]]}
                        redirect_msg_body = {"type": "http.response.body", "body": b"", "more_body": False}
                        await send(redirect_msg_start)
                        await send(redirect_msg_body)
                        return
                    await send(message)
                await self.app(scope, receive, send_with_check)
                return
        await self.app(scope, receive, send)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/gallery")


@app.get("/catalog")
async def catalog_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    catalog_html = Path(__file__).parent.parent / "web" / "catalog.html"
    if catalog_html.exists():
        with open(catalog_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/gallery")
async def gallery_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    gallery_html = Path(__file__).parent.parent / "web" / "gallery.html"
    if gallery_html.exists():
        with open(gallery_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/persons")
async def persons_page():
    from pathlib import Path
    persons_html = Path(__file__).parent.parent / "web" / "personas.html"
    if persons_html.exists():
        from fastapi.responses import HTMLResponse
        with open(persons_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/monitor")
async def monitor_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    monitor_html = Path(__file__).parent.parent / "web" / "photos.html"
    if monitor_html.exists():
        with open(monitor_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/log")
async def log_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    admin_html = Path(__file__).parent.parent / "web" / "admin" / "index.html"
    if admin_html.exists():
        with open(admin_html) as f:
            content = f.read()
        content = content.replace('class="page" id="page-logs"', 'class="page active" id="page-logs"')
        return HTMLResponse(content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/admin")
async def admin_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    admin_html = Path(__file__).parent.parent / "web" / "admin" / "index.html"
    if admin_html.exists():
        with open(admin_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/map")
async def map_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    map_html = Path(__file__).parent.parent / "web" / "map.html"
    if map_html.exists():
        with open(map_html) as f:
            content = f.read()
        return HTMLResponse(content, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/api/log")
async def get_log(lines: int = 100):
    import asyncio
    log_path = Path(str(LOG_FILE))
    if not log_path.exists():
        return {"lines": [], "total": 0}

    def _read_tail():
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk_size = min(size, 65536 * 4)
            f.seek(max(0, size - chunk_size))
            raw = f.read()
        text = raw.decode("utf-8", errors="replace")
        all_lines = text.splitlines(True)
        if size > chunk_size and all_lines:
            all_lines = all_lines[1:]
        return all_lines

    loop = asyncio.get_event_loop()
    all_lines = await loop.run_in_executor(None, _read_tail)
    return {
        "lines": all_lines[-lines:],
        "total": len(all_lines),
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "database": "connected" if db_manager else "disconnected"
    }


_status_cache = {"data": None, "ts": 0}
_STATUS_TTL = 10
_api_mqtt = None


def _get_api_mqtt():
    global _api_mqtt
    if _api_mqtt is None:
        try:
            from mqtt_client import create_api_mqtt
            _api_mqtt = create_api_mqtt()
        except Exception:
            _api_mqtt = False
    return _api_mqtt if _api_mqtt else None


@app.get("/api/status")
async def get_status():
    import time as _time
    import asyncio
    now = _time.time()
    cache_key = "_all"
    if _status_cache.get(cache_key) and (now - _status_cache[cache_key]["ts"]) < _STATUS_TTL:
        return _status_cache[cache_key]["data"]

    import subprocess
    from database import DatabaseManager, get_db
    from datetime import datetime

    def _compute_status():
        db = get_db()
        import sqlite3
        conn = sqlite3.connect(str(db.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            return db.get_status(_thread_conn=conn)
        finally:
            conn.close()

    loop = asyncio.get_event_loop()
    status = await loop.run_in_executor(None, _compute_status)

    import os
    flag_dir = str(FLAG_DIR)
    os.makedirs(flag_dir, exist_ok=True)

    mq = _get_api_mqtt()
    mqtt_states = mq.get_worker_states() if mq else {}

    procs = {"vlm": False, "face_pipeline": False, "embed": False}
    for key, worker_name in [("vlm", "describe"), ("face_pipeline", "faces"), ("embed", "embed")]:
        if mq and mq.is_worker_alive(worker_name):
            procs[key] = True
        elif os.path.exists(os.path.join(flag_dir, worker_name)):
            procs[key] = True

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
                import datetime as dt
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
                    import datetime as dt
                    mtime = os.path.getmtime(fpath)
                    step_started_at = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
                except Exception:
                    pass
                break

    if mq and current_step != "idle":
        pipeline_state = mqtt_states.get("pipeline", {})
        if pipeline_state.get("status") == "running" and pipeline_state.get("pid"):
            try:
                import datetime as dt
                mtime = os.path.getmtime(f"/proc/{pipeline_state['pid']}")
                pipeline_started_at = dt.datetime.fromtimestamp(mtime, tz=dt.timezone.utc).isoformat()
            except Exception:
                pass

    status["processes"] = procs
    status["current_step"] = current_step
    status["step_details"] = step_details
    status["step_started_at"] = step_started_at
    status["pipeline_started_at"] = pipeline_started_at
    status["server_time"] = datetime.now().isoformat()

    try:
        git_commit = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        git_date = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "log", "-1", "--format=%cs"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        status["git_commit"] = git_commit
        status["git_date"] = git_date
    except Exception:
        pass

    if mq:
        mqtt_progress = {}
        for name in ["ingest", "describe", "faces", "exif", "embed"]:
            prog = mqtt_states.get(name, {}).get("progress")
            if prog:
                mqtt_progress[name] = f"[{name.upper()}] {prog.get('done',0)}/{prog.get('total',0)} ({prog.get('pct',0):.1f}%)"
        if mqtt_progress:
            status["mqtt_progress"] = mqtt_progress

    try:
        log_path = str(LOG_FILE)

        def _read_log_info():
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

        progress_info, faces_phase, faces_detail = await loop.run_in_executor(None, _read_log_info)
        status["progress_lines"] = progress_info
        status["faces_phase"] = faces_phase
        status["faces_detail"] = faces_detail
    except Exception:
        status["progress_lines"] = {}
        status["faces_phase"] = ""
        status["faces_detail"] = ""

    _status_cache[cache_key] = {"data": status, "ts": now}
    return status


@app.get("/api/monitoring")
async def get_monitoring():
    import asyncio
    from system_monitor import collect_live
    from database import DatabaseManager, get_db

    def _compute():
        db = get_db()
        live = collect_live()
        history = db.get_system_metrics(limit=120)
        return {"live": live, "history": history}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _compute)


@app.get("/api/system-report")
async def get_system_report():
    import asyncio
    from system_monitor import collect_live
    from database import DatabaseManager, get_db
    import psutil
    import os
    import subprocess

    def _report():
        db = get_db()
        live = collect_live()
        si = live.get("system_info", {})

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

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

        net = psutil.net_io_counters()
        boot = psutil.boot_time()

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

        gpu_processes = []
        try:
            import subprocess
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

        report = {
            "host": {
                "hostname": si.get("hostname", "?"),
                "kernel": si.get("kernel", "?"),
                "uptime_seconds": live.get("uptime_seconds", 0),
                "boot_time": boot,
                "cpu_model": si.get("cpu_model", "?"),
                "cpu_cores_logical": si.get("cpu_count", 0),
                "cpu_cores_physical": psutil.cpu_count(logical=False),
                "load_1m": live.get("load1", 0),
                "load_5m": live.get("load5", 0),
                "load_15m": live.get("load15", 0),
                "cpu_percent": live.get("cpu_percent", 0),
                "cpu_temp_max": live.get("cpu_temp_max", 0),
            },
            "memory": {
                "total_gib": round(mem.total / (1024**3), 1),
                "available_gib": round(mem.available / (1024**3), 1),
                "used_gib": round(mem.used / (1024**3), 1),
                "free_gib": round(mem.free / (1024**3), 1),
                "percent": mem.percent,
                "cached_gib": round((mem.cached + mem.buffers) / (1024**3), 1) if hasattr(mem, 'cached') else 0,
                "swap_total_gib": round(swap.total / (1024**3), 1),
                "swap_used_gib": round(swap.used / (1024**3), 1),
            },
            "gpu": {
                "name": si.get("gpu_name", "?"),
                "driver": si.get("driver_ver", "?"),
                "load_pct": live.get("gpu_load", 0),
                "vram_used_mb": live.get("gpu_vram_mb", 0),
                "vram_total_mb": live.get("gpu_vram_total", 8192),
                "temp_c": live.get("gpu_temp", 0),
                "power_w": live.get("gpu_power_w", 0),
                "fan_pct": live.get("gpu_fan", 0),
                "sm_clock_mhz": live.get("gpu_sm_clock", 0),
                "mem_clock_mhz": live.get("gpu_mem_clock", 0),
                "pcie_gen": si.get("pcie_gen", "?"),
                "pcie_width": si.get("pcie_width", "?"),
                "processes": gpu_processes,
            },
            "disks": disks,
            "network": {
                "rx_gb": round(net.bytes_recv / 1e9, 2),
                "tx_gb": round(net.bytes_sent / 1e9, 2),
                "packets_recv": net.packets_recv,
                "packets_sent": net.packets_sent,
                "rx_mbps": live.get("net_rx_mbps", 0),
                "tx_mbps": live.get("net_tx_mbps", 0),
            },
            "disk_io": {
                "read_mbps": live.get("disk_read_mbps", 0),
                "write_mbps": live.get("disk_write_mbps", 0),
            },
            "top_processes": top_procs,
            "app": {
                "photos": db.count_photos("deleted = 0"),
                "persons": db.sqlite.execute("SELECT COUNT(*) FROM personas").fetchone()[0],
                "faces": db.sqlite.execute("SELECT COUNT(*) FROM faces").fetchone()[0],
                "catalog_files": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE deleted = 0").fetchone()[0],
                "db_size_mb": round(os.path.getsize(str(DATA_DIR / "gallery.db")) / (1024**2), 1),
                "lancedb_size_mb": 0,
            },
            "pipeline": {
                "cf_total": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE deleted = 0").fetchone()[0],
                "cf_canonical": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0").fetchone()[0],
                "cf_duplicates": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 0 AND deleted = 0").fetchone()[0],
                "cf_unhashed": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND content_hash IS NULL").fetchone()[0],
                "cf_empty": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND size = 0").fetchone()[0],
                "cf_deleted": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1").fetchone()[0],
                "cf_auto_missing": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1 AND deleted_type = 'auto_missing'").fetchone()[0],
                "cf_auto_empty": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE deleted = 1 AND deleted_type = 'auto_empty'").fetchone()[0],
                "cf_ingested": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND ingested = 1").fetchone()[0],
                "cf_described": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND described = 1").fetchone()[0],
                "cf_faces_done": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND faces_done = 1").fetchone()[0],
                "cf_embedded": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND embedded = 1").fetchone()[0],
                "cf_exif_done": db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical = 1 AND deleted = 0 AND exif_done = 1").fetchone()[0],
                "p_alive": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0").fetchone()[0],
                "p_video": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND media_type = 'video'").fetchone()[0],
                "p_photo": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND (media_type IS NULL OR media_type != 'video')").fetchone()[0],
                "p_described": db.sqlite.execute("SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE cf.is_canonical = 1 AND cf.described = 1 AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')").fetchone()[0],
                "p_faces_done": db.sqlite.execute("SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE cf.is_canonical = 1 AND cf.faces_done = 1 AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')").fetchone()[0],
                "p_faces_present": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND faces_present = 1").fetchone()[0],
                "p_embedded": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND embedded = 1").fetchone()[0],
                "p_exif": db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted = 0 AND exif_checked = 1").fetchone()[0],
                "f_total": db.sqlite.execute("SELECT COUNT(*) FROM faces").fetchone()[0],
                "f_with_persona": db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE persona_id IS NOT NULL").fetchone()[0],
                "f_with_hash": db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE content_hash IS NOT NULL").fetchone()[0],
                "personas_total": db.sqlite.execute("SELECT COUNT(*) FROM personas").fetchone()[0],
                "personas_named": db.sqlite.execute("SELECT COUNT(*) FROM personas WHERE display_name IS NOT NULL AND display_name != ''").fetchone()[0],
                "pct_described": 0,
                "pct_faces": 0,
                "pct_embedded": 0,
                "pct_exif": 0,
            }
        }
        pl = report["pipeline"]
        pp = max(pl["p_photo"], 1)
        pl["pct_described"] = round(pl["p_described"] / pp * 100, 1)
        pl["pct_faces"] = round(pl["p_faces_done"] / pp * 100, 1)
        pl["pct_embedded"] = round(pl["p_embedded"] / pp * 100, 1)
        pl["pct_exif"] = round(pl["cf_exif_done"] / max(pl["cf_canonical"], 1) * 100, 1)
        try:
            total = int(subprocess.run(["du", "-s",
                str(DATA_DIR / "lancedb")], capture_output=True, text=True,
                timeout=10).stdout.split()[0])
            report["app"]["lancedb_size_mb"] = round(total / 1024, 1)
        except Exception:
            pass

        return report

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _report)


@app.get("/api/mqtt/workers")
async def mqtt_workers():
    mq = _get_api_mqtt()
    if not mq:
        return {"workers": {}, "gpu_lock": None}
    states = mq.get_worker_states()
    result = {}
    for name, state in states.items():
        alive = mq.is_worker_alive(name)
        result[name] = {
            "status": state.get("status", "idle"),
            "pid": state.get("pid"),
            "progress": state.get("progress"),
            "gpu_held": state.get("gpu_held", False),
            "alive": alive,
        }
    import json as _json
    lock_data = None
    try:
        lock_raw = states.get("__gpu_lock__")
    except Exception:
        pass
    return {"workers": result, "current_step": mq.get_current_step(), "db_writing": mq.is_db_writing()}


@app.get("/api/watchdog/crashes")
async def watchdog_crashes():
    import asyncio
    def _read_crashes():
        try:
            with open(str(LOG_FILE), "r") as f:
                lines = f.readlines()[-500:]
        except Exception:
            return []
        crashes = []
        for line in reversed(lines):
            if "[WATCHDOG]" in line and ("DEAD" in line or "STALE" in line or "RESTART" in line or "RECOVERY" in line):
                crashes.append(line.strip())
        return crashes
    loop = asyncio.get_event_loop()
    crashes = await loop.run_in_executor(None, _read_crashes)
    no_restart = (FLAG_DIR / "no_restart").exists()
    if no_restart:
        mode = "sleeping"
    else:
        mq = _get_api_mqtt()
        mqtt_mode = mq.get_watchdog_mode() if mq else None
        if mqtt_mode == "sleeping":
            mode = "sleeping"
        else:
            mode = "active"
    return {"crashes": crashes[:50], "no_restart": no_restart, "mode": mode}


@app.post("/api/watchdog/sleep")
async def watchdog_sleep():
    no_restart_path = FLAG_DIR / "no_restart"
    no_restart_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    no_restart_path.write_text(f"manual sleep {datetime.now().isoformat()}")
    return {"ok": True, "mode": "sleeping"}


@app.post("/api/watchdog/wake")
async def watchdog_wake():
    from config import PIPELINE_SERVICE, WATCHDOG_SERVICE
    try:
        (FLAG_DIR / "no_restart").unlink()
    except FileNotFoundError:
        pass
    await asyncio.create_subprocess_exec("systemctl", "enable", PIPELINE_SERVICE, stderr=asyncio.subprocess.DEVNULL)
    await asyncio.create_subprocess_exec("systemctl", "start", WATCHDOG_SERVICE, stderr=asyncio.subprocess.DEVNULL)
    return {"ok": True, "mode": "active"}


_SVC_LIST = None


def _get_svc_list():
    global _SVC_LIST
    if _SVC_LIST is not None:
        return _SVC_LIST
    from config import SERVICE_NAME
    _SVC_LIST = [
        {"id": SERVICE_NAME, "label": "API (веб-сервер)", "group": "gailery"},
        {"id": f"{SERVICE_NAME}-pipeline", "label": "Пайплайн", "group": "gailery"},
        {"id": f"{SERVICE_NAME}-watchdog", "label": "Сторожевой пёс", "group": "gailery"},
        {"id": "mosquitto", "label": "MQTT брокер", "group": "system"},
    ]
    return _SVC_LIST


async def _svc_status_async(name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "is-active", name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out = await proc.stdout.read()
        status = out.decode().strip()
    except Exception:
        status = "unknown"
    try:
        proc2 = await asyncio.create_subprocess_exec(
            "systemctl", "is-enabled", name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out2 = await proc2.stdout.read()
        enabled = out2.decode().strip()
    except Exception:
        enabled = "unknown"
    return {"status": status, "enabled": enabled}


@app.get("/api/services")
async def get_services():
    svcs = _get_svc_list()
    results = []
    for s in svcs:
        info = await _svc_status_async(s["id"])
        results.append({**s, **info})
    return {"services": results}


@app.post("/api/services/{name}/restart")
async def restart_service(name: str):
    valid = [s["id"] for s in _get_svc_list()]
    if name not in valid:
        return {"ok": False, "error": f"unknown service: {name}"}
    proc = await asyncio.create_subprocess_exec("systemctl", "restart", name, stderr=asyncio.subprocess.DEVNULL)
    await proc.wait()
    return {"ok": True, "service": name, "returncode": proc.returncode}


@app.get("/api/proxy/ollama_check")
async def ollama_check(url: str = ""):
    url = _fix_ollama_url(url)
    try:
        r = requests.get(f"{url}/api/version", timeout=5)
        if r.status_code == 200:
            return {"ok": True, "version": r.json().get("version", "?")}
        return {"ok": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/proxy/ollama_models")
async def ollama_models(url: str = ""):
    url = _fix_ollama_url(url)
    try:
        r = requests.get(f"{url}/api/tags", timeout=10)
        if r.status_code == 200:
            data = r.json()
            models = []
            for m in data.get("models", []):
                models.append({
                    "name": m.get("name", "?"),
                    "size": m.get("size", 0),
                })
            return {"models": models}
        return {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def _fix_ollama_url(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url
    url = url.replace("https://", "http://")
    if ":" not in url.split("/")[2] if "://" in url else True:
        url = url.rstrip("/") + ":11434"
    return url


@app.post("/api/control/start")
async def control_start(body: dict):
    import subprocess
    step = body.get("step", "")
    _lf = str(LOG_FILE)
    _pr = str(PROJECT_ROOT)
    cmd = None

    mq = _get_api_mqtt()

    if step == "ingest":
        n = body.get("ingest_limit", 100)
        root = f"--root {body['root_id']}" if body.get("root_id") else ""
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/scan_catalog.py --scan >> {_lf} 2>&1 &"
    elif step == "hash":
        n = body.get("hash_limit", 50)
        root = f"--root {body['root_id']}" if body.get("root_id") else ""
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/scan_catalog.py --hash --limit {n} {root} >> {_lf} 2>&1 &"
    elif step == "dedup_ingest":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/scan_catalog.py --dedup-ingest >> {_lf} 2>&1 &"
    elif step == "describe":
        n = body.get("desc_limit", 60)
        bs = body.get("batch_size", 6)
        root_dir = ""
        if body.get("root_id"):
            try:
                db_temp = get_db()
                r = db_temp.get_catalog_root(body["root_id"])
                if r:
                    root_dir = f"--dir {r['root_path']}"
            except Exception:
                pass
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/describe.py --limit {n} --batch-size {bs} {root_dir} >> {_lf} 2>&1 &"
    elif step == "faces":
        n = body.get("faces_limit", 600)
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/faces.py --limit {n} >> {_lf} 2>&1 &"
    elif step == "exif":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/exif.py --all >> {_lf} 2>&1 &"
    elif step == "embed":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/embed.py >> {_lf} 2>&1 &"
    elif step == "chain":
        from config import PIPELINE_SERVICE
        n = body.get("hash_limit", 50)
        dl = body.get("desc_limit", 60)
        bs = body.get("batch_size", 6)
        root = f"--root {body['root_id']}" if body.get("root_id") else ""
        subprocess.run(["pkill", "-f", "pipeline.py"], capture_output=True, timeout=5)
        subprocess.run(["systemctl", "stop", PIPELINE_SERVICE], capture_output=True, timeout=5)
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/pipeline.py --hash-limit {n} --describe {dl} --batch-size {bs} {root} >> {_lf} 2>&1 &"

    if cmd:
        is_chain = step == "chain"
        if is_chain:
            try:
                (FLAG_DIR / "no_restart").unlink()
            except FileNotFoundError:
                pass
            os.system(f"systemctl enable {PIPELINE_SERVICE} 2>/dev/null")
        gpu_steps = {"describe", "faces", "embed", "chain"}
        if step in gpu_steps:
            os.system("pkill -9 -f 'llama-server' 2>/dev/null")
        from datetime import datetime
        with open(_lf, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [CONTROL] Starting: {step}\n")
        os.system(cmd)
        if mq:
            mq.send_start(step, body)
        return {"ok": True, "step": step}
    return {"ok": False, "error": "unknown step"}


@app.post("/api/control/stop")
async def control_stop():
    from config import PIPELINE_SERVICE
    mq = _get_api_mqtt()
    if mq:
        mq.send_stop("all")
    os.system(f"systemctl stop {PIPELINE_SERVICE} 2>/dev/null")
    os.system(f"systemctl disable {PIPELINE_SERVICE} 2>/dev/null")
    for pattern in ["llama-server", "vision_describe", "face_pipeline", "faces.py", "faces", "ingest.py", "ingest", "exif.py", "exif", "embed.py", "embed", "pipeline.py", "describe.py", "describe", "enrich_description.py", "enrich"]:
        try:
            os.system(f"pkill -f '{pattern}' 2>/dev/null")
        except Exception:
            pass
    flag_dir = str(FLAG_DIR)
    for fname in ["describe", "ingest", "faces", "exif", "embed", "pipeline"]:
        try:
            os.remove(os.path.join(flag_dir, fname))
        except Exception:
            pass
    no_restart_path = FLAG_DIR / "no_restart"
    no_restart_path.parent.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    no_restart_path.write_text(f"manual stop {datetime.now().isoformat()}")
    with open(str(LOG_FILE), "a") as f:
        f.write(f"[{datetime.now().isoformat()}] [CONTROL] STOP ALL\n")
    return {"ok": True}


@app.post("/api/control/reset")
async def control_reset(body: dict):
    step = body.get("step", "")
    mq = _get_api_mqtt()
    if mq and mq.is_worker_alive("pipeline"):
        result = mq.db_write("control_reset", {"step": step}, timeout=10)
        if result.get("ok") or "timeout" not in result.get("error", "").lower():
            if result.get("ok"):
                from datetime import datetime
                with open(str(LOG_FILE), "a") as f:
                    f.write(f"[{datetime.now().isoformat()}] [CONTROL] RESET {step}: {result.get('affected', 0)} rows affected\n")
            return result
    result = _control_reset_direct(step)
    if result.get("ok"):
        from datetime import datetime
        with open(str(LOG_FILE), "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [CONTROL] RESET {step}: {result.get('affected', 0)} rows affected\n")
    return result


def _control_reset_direct(step):
    db = get_db()
    reset_map = {
        "describe": [
            "UPDATE photos SET description=NULL, embedded=0, rich_description=NULL WHERE deleted=0",
            "UPDATE catalog_files SET described=0 WHERE is_canonical=1 AND deleted=0",
        ],
        "faces": [
            "DELETE FROM faces",
            "UPDATE photos SET faces_present=0 WHERE deleted=0",
            "UPDATE catalog_files SET faces_done=0 WHERE is_canonical=1 AND deleted=0",
            "DELETE FROM personas",
        ],
        "exif": [
            "UPDATE photos SET exif_checked=0 WHERE deleted=0",
            "UPDATE catalog_files SET exif_done=0 WHERE is_canonical=1 AND deleted=0",
        ],
        "embed": [
            "UPDATE photos SET embedded=0 WHERE deleted=0",
            "UPDATE catalog_files SET embedded=0 WHERE is_canonical=1 AND deleted=0",
        ],
        "describe_with_faces": [
            "UPDATE photos SET description=NULL, embedded=0 WHERE path IN (SELECT DISTINCT cf.abs_path FROM catalog_files cf JOIN faces f ON f.content_hash = cf.content_hash JOIN personas p ON p.persona_id = f.persona_id WHERE p.display_name IS NOT NULL AND cf.is_canonical=1) AND deleted=0",
            "UPDATE catalog_files SET described=0, embedded=0 WHERE content_hash IN (SELECT DISTINCT f.content_hash FROM faces f JOIN personas p ON p.persona_id = f.persona_id WHERE p.display_name IS NOT NULL) AND is_canonical=1",
        ],
    }
    sqls = reset_map.get(step)
    if not sqls:
        return {"ok": False, "error": f"unknown step: {step}"}
    affected = 0
    for sql in sqls:
        cur = db.sqlite.execute(sql)
        affected += cur.rowcount
    db.sqlite.commit()
    if step == "faces":
        try:
            db.face_vectors.delete("face_id != ''")
        except Exception:
            pass
    return {"ok": True, "step": step, "affected": affected}


@app.post("/api/control/update")
async def control_update():
    import subprocess
    install_dir = str(PROJECT_ROOT)
    _lf = str(LOG_FILE)
    from datetime import datetime
    try:
        before = subprocess.run(
            ["git", "-C", install_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        subprocess.run(["git", "-C", install_dir, "fetch", "origin"], capture_output=True, text=True, timeout=60)
        subprocess.run(["git", "-C", install_dir, "reset", "--hard", "origin/main"], capture_output=True, text=True, timeout=30)
        subprocess.run(["git", "-C", install_dir, "clean", "-fd"], capture_output=True, text=True, timeout=30)
        after = subprocess.run(
            ["git", "-C", install_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        if before != after:
            with open(_lf, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] [CONTROL] UPDATE: {before} → {after}, scheduling restart\n")

            async def _delayed_restart():
                import asyncio
                await asyncio.sleep(1)
                await asyncio.create_subprocess_exec("systemctl", "restart", config.PIPELINE_SERVICE, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.create_subprocess_exec("systemctl", "restart", config.WATCHDOG_SERVICE, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.create_subprocess_exec("systemctl", "restart", config.SERVICE_NAME, stderr=asyncio.subprocess.DEVNULL)

            asyncio.ensure_future(_delayed_restart())
            return {"ok": True, "updated": True, "before": before[:8], "after": after[:8]}
        else:
            with open(_lf, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] [CONTROL] UPDATE: already up-to-date ({before[:8]})\n")
            return {"ok": True, "updated": False, "commit": before[:8]}
    except Exception as e:
        with open(_lf, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [CONTROL] UPDATE FAILED: {e}\n")
        return {"ok": False, "error": str(e)}


@app.get("/api/changes")
async def get_changes(limit: int = 100):
    from database import DatabaseManager, get_db
    db = get_db()
    cur = db.sqlite.cursor()
    rows = cur.execute(
        "SELECT c.photo_id, c.field, c.value, c.changed_at, p.path "
        "FROM changes c LEFT JOIN photos p ON c.photo_id = p.photo_id "
        "ORDER BY c.changed_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    from datetime import datetime
    result = []
    for r in rows:
        result.append({
            "photo_id": r[0], "field": r[1], "value": r[2],
            "changed_at": r[3], "path": r[4],
        })
    return {"changes": result, "server_time": datetime.now().isoformat()}


from api import photos, persons, catalog, models
app.include_router(photos.router)
app.include_router(persons.router)
app.include_router(catalog.router)
app.include_router(models.router)


@app.get("/api/settings/{key}")
async def get_setting(key: str):
    from database import DatabaseManager, get_db
    db = get_db()
    value = db.get_setting(key)
    return {"key": key, "value": value or ""}


@app.put("/api/settings/{key}")
async def set_setting(key: str, request: Request):
    body = await request.json()
    value = body.get("value", "")
    mq = _get_api_mqtt()
    if mq and mq.is_worker_alive("pipeline"):
        result = mq.db_write("set_setting", {"key": key, "value": value}, timeout=10)
        if result.get("ok"):
            return {"key": key, "value": value}
    db = get_db()
    db.set_setting(key, value)
    return {"key": key, "value": value}


@app.get("/api/settings/{key}/top_personas")
async def top_personas_for_facts(key: str):
    from database import DatabaseManager, get_db
    db = get_db()
    rows = db.sqlite.execute("""
        SELECT per.display_name, per.comment, SUM(subcnt) as total_faces
        FROM (
            SELECT persona_id, COUNT(*) as subcnt FROM faces WHERE persona_id IS NOT NULL GROUP BY persona_id
        ) f
        JOIN personas per ON f.persona_id = per.persona_id
        WHERE per.display_name IS NOT NULL AND per.display_name != ''
        GROUP BY per.display_name
        ORDER BY total_faces DESC
        LIMIT 10
    """).fetchall()
    lines = []
    for name, comment, total in rows:
        line = name
        if comment:
            line += f" — {comment}"
        lines.append(line)
    return {"text": "\n".join(lines)}

from pathlib import Path
# Admin static assets
admin_dir = Path(__file__).parent.parent / "web" / "admin"
app.mount("/admin/js", StaticFiles(directory=str(admin_dir / "js")), name="admin-js")
app.mount("/admin/css", StaticFiles(directory=str(admin_dir / "css")), name="admin-css")
# General static
static_dir = Path(__file__).parent / "frontend"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

web_dir = Path(__file__).parent.parent / "web"
lib_dir = web_dir / "lib"
if lib_dir.exists():
    app.mount("/lib", StaticFiles(directory=str(lib_dir)), name="lib")

@app.get("/logo-dark.png")
async def logo_dark():
    p = web_dir / "logo-dark.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/logo-light.png")
async def logo_light():
    p = web_dir / "logo-light.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/favicon.ico")
async def favicon():
    p = web_dir / "favicon.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    p = web_dir / "logo-dark.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/x-icon")
    raise HTTPException(status_code=404)

@app.get("/favicon.png")
async def favicon_png():
    p = web_dir / "favicon.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/apple-touch-icon.png")
async def apple_touch_icon():
    p = web_dir / "apple-touch-icon.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)

@app.get("/favicon-32.png")
async def favicon_32():
    p = web_dir / "favicon-32.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/png")
    raise HTTPException(status_code=404)


@app.get("/api/backup/download")
async def backup_download():
    import gzip, tempfile
    db_path = DATA_DIR / "gallery.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db.gz")
    try:
        with open(db_path, "rb") as f_in:
            with gzip.open(tmp.name, "wb", compresslevel=6) as f_out:
                while True:
                    chunk = f_in.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    f_out.write(chunk)
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return FileResponse(
            tmp.name,
            media_type="application/gzip",
            filename=f"gallery_backup_{ts}.db.gz",
            background=lambda: os.unlink(tmp.name) if os.path.exists(tmp.name) else None,
        )
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/backup/upload")
async def backup_upload(file: UploadFile = File(...)):
    import gzip, tempfile, shutil
    db_path = DATA_DIR / "gallery.db"
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    try:
        with open(tmp.name, "wb") as f_out:
            content = await file.read()
            if file.filename.endswith(".gz"):
                import io
                with gzip.GzipFile(fileobj=io.BytesIO(content)) as f_in:
                    f_out.write(f_in.read())
            else:
                f_out.write(content)
        if db_path.exists():
            bak = str(db_path) + ".bak"
            if os.path.exists(bak):
                os.unlink(bak)
            shutil.move(str(db_path), bak)
        shutil.move(tmp.name, str(db_path))
        return {"ok": True, "message": "Database restored. Restart service to apply."}
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/maintenance/stats")
async def maintenance_stats():
    import os
    stats = {}
    total_data = 0

    # SQLite files
    for name in ["gallery.db", "gallery.db-wal", "gallery.db-shm",
                 "gailray.db", "gailray.db-wal", "gailray.db-shm"]:
        p = DATA_DIR / name
        if p.exists():
            s = os.path.getsize(str(p))
            stats[name] = s
            total_data += s

    # LanceDB tables
    lance_tables = {}
    if LANCEDB_PATH.exists():
        for entry in os.listdir(LANCEDB_PATH):
            ep = LANCEDB_PATH / entry
            if ep.is_dir() and ep.suffix == ".lance":
                total = 0
                for root, dirs, files in os.walk(str(ep)):
                    for f in files:
                        total += os.path.getsize(os.path.join(root, f))
                lance_tables[entry.replace(".lance", "")] = total
                total_data += total
    stats["lance_tables"] = lance_tables

    # Other files in data/
    for entry in os.listdir(DATA_DIR):
        ep = DATA_DIR / entry
        if ep.is_dir() and entry != "lancedb":
            total = 0
            for root, dirs, files in os.walk(str(ep)):
                for f in files:
                    total += os.path.getsize(os.path.join(root, f))
            if total > 0:
                stats["dir_" + entry] = total
                total_data += total

    stats["data_total"] = total_data

    # Compact legacy flags
    stats["has_legacy_db"] = (DATA_DIR / "gailray.db").exists()
    stats["has_legacy_faces_lance"] = lance_tables.get("faces", 0) > 0 and lance_tables.get("face_vectors", 0) > 0

    return stats


@app.post("/api/maintenance/vacuum")
async def maintenance_vacuum():
    mq = _get_api_mqtt()
    if mq and mq.is_worker_alive("pipeline"):
        result = mq.db_write("vacuum", {}, timeout=60)
        if result.get("ok"):
            return result
    import sqlite3
    try:
        db_path = str(DATA_DIR / "gallery.db")
        before = os.path.getsize(db_path)
        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
        after = os.path.getsize(db_path)
        return {"ok": True, "before": before, "after": after, "freed": before - after}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/maintenance/dedup_embeddings")
async def maintenance_dedup_embeddings():
    mq = _get_api_mqtt()
    if mq and mq.is_worker_alive("pipeline"):
        result = mq.db_write("dedup_embeddings", {}, timeout=60)
        if result.get("ok"):
            return result
    try:
        from database import DatabaseManager, get_db
        db = get_db()
        before, after, removed = db.dedup_photo_embeddings()
        return {"ok": True, "before": before, "after": after, "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": vlm_prompt, "d": "Системный промт описания фото", "env_key": "prompt_vlm_system", "editable": True})
    except Exception as e:
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт описания фото"})
    try:
        ed = importlib.import_module("enrich_description")
        enrich_prompt = db.get_setting("prompt_enrich_system") or ed.SYSTEM_PROMPT.strip()
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": enrich_prompt, "d": "Системный промт обогащения описания", "env_key": "prompt_enrich_system", "editable": True})
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
                prompts.append({"k": f"Enrich tool: {name}", "v": tool_val, "d": "Инструмент обогащения", "env_key": env_key, "editable": True})
    except Exception as e:
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт обогащения описания"})
    return prompts


_config_cache = {"data": None, "ts": 0}
_CONFIG_TTL = 30


@app.get("/api/config")
async def get_config():
    import time as _time
    now = _time.time()
    if _config_cache["data"] and (now - _config_cache["ts"]) < _CONFIG_TTL:
        return _config_cache["data"]

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
    groups = [
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
    from pathlib import Path as _P
    for g in groups:
        for p in g["params"]:
            if p.get("path"):
                v = p["v"].split(",")[0].strip()
                p["exists"] = _P(v).is_dir() if v else False
    result = {"groups": groups}
    _config_cache["data"] = result
    _config_cache["ts"] = _time.time()
    return result


@app.post("/api/config/update")
async def config_update(request: Request):
    body = await request.json()
    env_key = body.get("env_key", "")
    value = body.get("value", "")
    if not env_key:
        return {"ok": False, "error": "env_key is required"}
    if env_key.startswith("prompt_"):
        from database import get_db
        db = get_db()
        db.set_setting(env_key, value)
        _config_cache["data"] = None
        _config_cache["ts"] = 0
        return {"ok": True, "env_key": env_key, "value": value}
    env_path = PROJECT_ROOT / ".env"
    lines = []
    found = False
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                s = line.strip()
                if s.startswith(env_key + "="):
                    lines.append(f"{env_key}={value}\n")
                    found = True
                else:
                    lines.append(line)
    if not found:
        lines.append(f"{env_key}={value}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)
    os.environ[env_key] = str(value)
    _config_cache["data"] = None
    _config_cache["ts"] = 0
    import importlib
    try:
        import config as _cfg_mod
        importlib.reload(_cfg_mod)
    except Exception:
        pass
    return {"ok": True, "env_key": env_key, "value": value}


@app.get("/api/ai-log")
async def ai_log(photo_path: str = "", content_hash: str = "", call_type: str = "", limit: int = 50):
    import sqlite3
    from vlm_log import DB_PATH
    if not __import__('os').path.exists(DB_PATH):
        return {"calls": [], "total": 0, "db_path": DB_PATH}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    where = []
    params = []
    if photo_path:
        where.append("photo_path LIKE ?")
        params.append("%" + photo_path + "%")
    if content_hash:
        where.append("content_hash = ?")
        params.append(content_hash)
    if call_type:
        where.append("call_type = ?")
        params.append(call_type)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM ai_calls{where_sql}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM ai_calls{where_sql} ORDER BY called_at DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return {
        "calls": [dict(r) for r in rows],
        "total": total,
        "db_path": DB_PATH,
    }


@app.get("/{path:path}")
async def spa_fallback(path: str, request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        from pathlib import Path
        from fastapi.responses import HTMLResponse
        gallery_html = Path(__file__).parent.parent / "web" / "gallery.html"
        if gallery_html.exists():
            with open(gallery_html) as f:
                return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    raise HTTPException(status_code=404, detail="Not found")


def main():
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
