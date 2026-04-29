"""FastAPI application for Gailery Photo Gallery"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlparse
import logging
import importlib
import sys
import os

from database import DatabaseManager
from config import LANCEDB_PATH, LOG_FILE, FLAG_DIR, VENV_PYTHON, PROJECT_ROOT, DATA_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_manager
    logger.info("Starting application...")
    db_manager = DatabaseManager()
    logger.info("Database connected")
    yield
    logger.info("Shutting down application...")


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


@app.middleware("http")
async def redirect_api_errors_for_browsers(request: Request, call_next):
    response = await call_next(request)
    if response.status_code >= 400:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and request.url.path.startswith("/api/"):
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/gallery")
    return response


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
async def pipeline_log():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    log_html = Path(__file__).parent.parent / "web" / "log.html"
    if log_html.exists():
        with open(log_html) as f:
            return HTMLResponse(f.read(), headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    return {"error": "Page not found"}


@app.get("/control")
async def control_page():
    from pathlib import Path
    from fastapi.responses import HTMLResponse
    ctrl_html = Path(__file__).parent.parent / "web" / "control.html"
    if ctrl_html.exists():
        with open(ctrl_html) as f:
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
    log_path = Path(str(LOG_FILE))
    if not log_path.exists():
        return {"lines": [], "total": 0}
    with open(log_path) as f:
        all_lines = f.readlines()
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
_STATUS_TTL = 5
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
    now = _time.time()
    cache_key = "_all"
    if _status_cache.get(cache_key) and (now - _status_cache[cache_key]["ts"]) < _STATUS_TTL:
        return _status_cache[cache_key]["data"]

    import subprocess
    from database import DatabaseManager
    from datetime import datetime

    db = DatabaseManager()
    status = db.get_status()

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
        progress_info = {}
        tag_map = {"DESCRIBE": "describe", "INGEST": "ingest", "FACES": "faces", "EXIF": "exif", "EMBED": "embed"}
        with open(log_path, "r") as f:
            for line in f:
                for tag, key in tag_map.items():
                    if "[" + tag + "]" in line:
                        progress_info[key] = line.strip()
        status["progress_lines"] = progress_info
    except Exception:
        status["progress_lines"] = {}

    try:
        faces_phase = ""
        faces_detail = ""
        with open(str(LOG_FILE), "r") as f:
            lines = f.readlines()
        for line in reversed(lines[-100:]):
            if "[FACES]" in line or "[CLUSTER]" in line:
                stripped = line.strip()
                if "detecting " in stripped:
                    fname = stripped.split("detecting ")[-1].replace("...", "")
                    faces_phase = "detecting"
                    faces_detail = fname
                    break
                elif "lance write " in stripped and "done" not in stripped:
                    nvec = stripped.split("lance write ")[-1].replace(" vectors...", "")
                    faces_phase = "lance_write"
                    faces_detail = nvec + " vectors"
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
                    m = stripped.split("Detection done: ")[-1] if "Detection done: " in stripped else ""
                    faces_detail = m
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
                    m = stripped.split("Found ")[-1].split(" photos")[0]
                    faces_detail = m + " photos"
                    break
        status["faces_phase"] = faces_phase
        status["faces_detail"] = faces_detail
    except Exception:
        status["faces_phase"] = ""
        status["faces_detail"] = ""

    _status_cache[cache_key] = {"data": status, "ts": now}
    return status


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
    return {"workers": result, "current_step": mq.get_current_step()}


@app.get("/api/watchdog/crashes")
async def watchdog_crashes():
    try:
        with open(str(LOG_FILE), "r") as f:
            lines = f.readlines()
    except Exception:
        return {"crashes": [], "no_restart": False, "mode": "active"}
    crashes = []
    for line in reversed(lines[-500:]):
        if "[WATCHDOG]" in line and ("DEAD" in line or "STALE" in line or "RESTART" in line or "RECOVERY" in line):
            crashes.append(line.strip())
    no_restart = (FLAG_DIR / "no_restart").exists()
    if no_restart:
        for fname in ["pipeline", "describe", "faces", "exif", "embed", "ingest", "enrich"]:
            if (FLAG_DIR / fname).exists():
                no_restart = False
                break
    mode = "sleeping" if no_restart else "active"
    return {"crashes": crashes[:50], "no_restart": no_restart, "mode": mode}


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
        exif = "--exif" if body.get("exif") == "1" else ""
        root = f"--root {body['root_id']}" if body.get("root_id") else ""
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/ingest.py --random {n} {exif} {root} >> {_lf} 2>&1 &"
    elif step == "describe":
        n = body.get("desc_limit", 60)
        bs = body.get("batch_size", 6)
        root_dir = ""
        if body.get("root_id"):
            try:
                db_temp = DatabaseManager()
                r = db_temp.get_catalog_root(body["root_id"])
                if r:
                    root_dir = f"--dir {r['root_path']}"
            except Exception:
                pass
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/describe.py --limit {n} --batch-size {bs} {root_dir} >> {_lf} 2>&1 &"
    elif step == "faces":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/faces.py >> {_lf} 2>&1 &"
    elif step == "exif":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/exif.py --all >> {_lf} 2>&1 &"
    elif step == "embed":
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/embed.py >> {_lf} 2>&1 &"
    elif step == "chain":
        n = body.get("ingest_limit", 100)
        dl = body.get("desc_limit", 60)
        bs = body.get("batch_size", 6)
        root = f"--root {body['root_id']}" if body.get("root_id") else ""
        cmd = f"/usr/bin/nohup {VENV_PYTHON} {_pr}/pipeline.py --ingest {n} --describe {dl} --batch-size {bs} {root} >> {_lf} 2>&1 &"

    if cmd:
        try:
            (FLAG_DIR / "no_restart").unlink()
        except FileNotFoundError:
            pass
        os.system("systemctl enable gailray-pipeline 2>/dev/null")
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
    mq = _get_api_mqtt()
    if mq:
        mq.send_stop("all")
    os.system("systemctl stop gailray-pipeline 2>/dev/null")
    os.system("systemctl disable gailray-pipeline 2>/dev/null")
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


@app.get("/api/changes")
async def get_changes(limit: int = 100):
    from database import DatabaseManager
    db = DatabaseManager()
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


from api import photos, persons, catalog
app.include_router(photos.router)
app.include_router(persons.router)
app.include_router(catalog.router)


@app.get("/api/settings/{key}")
async def get_setting(key: str):
    from database import DatabaseManager
    db = DatabaseManager()
    value = db.get_setting(key)
    return {"key": key, "value": value or ""}


@app.put("/api/settings/{key}")
async def set_setting(key: str, request: Request):
    from database import DatabaseManager
    body = await request.json()
    value = body.get("value", "")
    db = DatabaseManager()
    db.set_setting(key, value)
    return {"key": key, "value": value}


@app.get("/api/settings/{key}/top_personas")
async def top_personas_for_facts(key: str):
    from database import DatabaseManager
    db = DatabaseManager()
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
static_dir = Path(__file__).parent / "frontend"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

web_dir = Path(__file__).parent.parent / "web"

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
    p = web_dir / "logo-dark.png"
    if p.exists():
        return FileResponse(str(p), media_type="image/x-icon")
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
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        before, after, removed = db.dedup_photo_embeddings()
        return {"ok": True, "before": before, "after": after, "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_prompts():
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
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": vd.SYSTEM_PROMPT.strip(), "d": "Системный промт описания фото"})
    except Exception as e:
        prompts.append({"k": "VLM SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт описания фото"})
    try:
        ed = importlib.import_module("enrich_description")
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": ed.SYSTEM_PROMPT.strip(), "d": "Системный промт обогащения описания"})
        tools = getattr(ed, "TOOLS", None)
        if tools:
            for t in tools:
                fn = t.get("function", {})
                name = fn.get("name", "?")
                desc = fn.get("description", "")
                params = fn.get("parameters", {}).get("properties", {})
                param_str = ", ".join(f"{p}: {d.get('type','?')}" for p, d in params.items()) if params else "нет"
                prompts.append({"k": f"Enrich tool: {name}", "v": f"{desc} | Параметры: {param_str}", "d": "Инструмент обогащения"})
    except Exception as e:
        prompts.append({"k": "Enrich SYSTEM_PROMPT", "v": f"Ошибка загрузки: {e}", "d": "Системный промт обогащения описания"})
    return prompts


@app.get("/api/config")
async def get_config():
    from config import (
        PHOTO_SHARE_PATH, DATA_DIR, THUMBNAILS_DIR, LOGS_DIR, LLAMA_CPP_DIR,
        VENV_PYTHON, MQTT_HOST, MQTT_PORT, MQTT_WS_PORT, GPU_LOCK_TIMEOUT,
        THUMBNAIL_SIZE, THUMBNAIL_FORMAT, SUPPORTED_EXTENSIONS,
        FACE_DETECTION_MODEL, FACE_CONFIDENCE_THRESHOLD,
        EMBEDDING_MODEL, EMBEDDING_DIM, BATCH_SIZE, MAX_WORKERS,
        LANCEDB_PATH, FLAG_DIR, LOG_FILE,
    )
    groups = [
        {
            "name": "Пути",
            "icon": "\U0001f4c1",
            "params": [
                {"k": "Корни фото (catalog_roots)", "v": ", ".join(r["root_path"] for r in DatabaseManager().get_catalog_roots()), "d": "Динамические корни из каталога"},
                {"k": "PHOTO_SHARE_PATH", "v": str(PHOTO_SHARE_PATH), "d": "Корневая папка фото"},
                {"k": "DATA_DIR", "v": str(DATA_DIR), "d": "Директория данных (БД, LanceDB, флаги)"},
                {"k": "THUMBNAILS_DIR", "v": str(THUMBNAILS_DIR), "d": "Директория превью"},
                {"k": "LOGS_DIR", "v": str(LOGS_DIR), "d": "Директория логов"},
                {"k": "LLAMA_CPP_DIR", "v": str(LLAMA_CPP_DIR), "d": "Путь к llama.cpp"},
                {"k": "LANCEDB_PATH", "v": str(LANCEDB_PATH), "d": "Путь к LanceDB"},
                {"k": "LOG_FILE", "v": str(LOG_FILE), "d": "Файл лога пайплайна"},
                {"k": "FLAG_DIR", "v": str(FLAG_DIR), "d": "Директория флагов воркеров"},
            ]
        },
        {
            "name": "MQTT",
            "icon": "\U0001f4e1",
            "params": [
                {"k": "MQTT_HOST", "v": MQTT_HOST, "d": "Адрес MQTT брокера"},
                {"k": "MQTT_PORT", "v": str(MQTT_PORT), "d": "TCP порт MQTT"},
                {"k": "MQTT_WS_PORT", "v": str(MQTT_WS_PORT), "d": "WebSocket порт MQTT"},
                {"k": "GPU_LOCK_TIMEOUT", "v": str(GPU_LOCK_TIMEOUT), "d": "Таймаут захвата GPU (сек)"},
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
                {"k": "Embed порт", "v": "8102", "d": "Порт llama-server эмбеддингов"},
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
    return {"groups": groups}


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
