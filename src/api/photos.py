"""API endpoints for photos"""

from fastapi import APIRouter, HTTPException, Response, Request
from pathlib import Path
from typing import Optional, List
import logging
import time
from config import PHOTO_SHARE_PATH, THUMBNAILS_DIR, FLAG_DIR, LLAMA_CPP_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["photos"])

FOTO_PREFIX = str(PHOTO_SHARE_PATH) + "/"


def _rel_path(abs_path):
    if abs_path and abs_path.startswith(FOTO_PREFIX):
        return abs_path[len(FOTO_PREFIX):]
    return abs_path or ""


def _enrich_photo(p, photo_faces, persona_map, include_created=False, include_thumbnail=False, include_score=False, score=None):
    rel = _rel_path(p.get("path", ""))
    faces = photo_faces.get(rel, [])
    personas_info = []
    seen_pids = set()
    faces_info = []
    for f in faces:
        pers_id = f.get("persona_id")
        faces_info.append({
            "face_id": f.get("face_id"),
            "persona_id": pers_id,
            "display_name": (persona_map.get(pers_id, {}).get("display_name")) if pers_id else None,
            "name": (persona_map.get(pers_id, {}).get("name") or pers_id) if pers_id else None,
            "bbox_x1": f.get("bbox_x1"),
            "bbox_y1": f.get("bbox_y1"),
            "bbox_x2": f.get("bbox_x2"),
            "bbox_y2": f.get("bbox_y2"),
        })
        if pers_id and pers_id not in seen_pids:
            seen_pids.add(pers_id)
            persona = persona_map.get(pers_id, {})
            personas_info.append({
                "persona_id": pers_id,
                "name": persona.get("name") or pers_id,
                "display_name": persona.get("display_name"),
                "face_count": sum(1 for ff in faces if ff.get("persona_id") == pers_id),
                "face_ids": [ff["face_id"] for ff in faces if ff.get("persona_id") == pers_id],
            })
    result = {
        "path": p.get("path", ""),
        "photo_id": rel,
        "db_id": p.get("photo_id"),
        "description": p.get("description"),
        "rich_description": p.get("rich_description"),
        "faces_present": bool(p.get("faces_present")),
        "date": p.get("manual_date") or p.get("date"),
        "original_date": p.get("date"),
        "manual_date": p.get("manual_date"),
        "gps_lat": p.get("gps_lat"),
        "gps_lon": p.get("gps_lon"),
        "manual_gps": bool(p.get("manual_gps")),
        "camera_make": p.get("camera_make"),
        "camera_model": p.get("camera_model"),
        "total_faces": len(faces),
        "personas": personas_info,
        "faces": faces_info,
        "img_width": p.get("img_width"),
        "img_height": p.get("img_height"),
        "photo_type": p.get("photo_type", "photo"),
        "has_issues": bool(p.get("has_issues")),
        "issue_type": p.get("issue_type"),
        "deleted": bool(p.get("deleted")),
        "exif_checked": bool(p.get("exif_checked")),
        "embedded": bool(p.get("embedded")),
        "exif_raw": p.get("exif_raw"),
    }
    if include_thumbnail:
        result["thumbnail_path"] = p.get("thumbnail_path")
    if include_created:
        result["created_at"] = p.get("created_at")
    if include_score and score is not None:
        result["score"] = round(score, 4)
    return result


@router.get("/")
async def get_photo(path: str):
    photo_path = PHOTO_SHARE_PATH / path
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Not a file")
    ext = photo_path.suffix.lower()
    content_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }.get(ext, "image/jpeg")
    try:
        with open(photo_path, "rb") as f:
            content = f.read()
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=31536000"}
        )
    except Exception as e:
        logger.error(f"Failed to read photo {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read photo")


@router.get("/thumbnail")
async def get_thumbnail(path: str, size: str = "sm", fit: bool = False):
    photo_path = PHOTO_SHARE_PATH / path
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    try:
        rel = str(photo_path.relative_to(PHOTO_SHARE_PATH))
    except ValueError:
        rel = photo_path.name

    from thumbnails import ThumbnailGenerator, SIZES
    gen = ThumbnailGenerator()

    if size not in SIZES:
        size = "sm"

    if fit:
        import asyncio
        loop = asyncio.get_event_loop()
        buf = await loop.run_in_executor(None, gen.generate_fit_buffer, photo_path, SIZES.get(size, 400))
        if not buf:
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        return Response(
            content=buf,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=31536000"}
        )

    for fmt in ["webp", "jpg"]:
        thumb_path = gen.get_thumbnail_path(photo_path, size, fmt)
        if thumb_path.exists():
            break
    else:
        import asyncio
        loop = asyncio.get_event_loop()
        thumb_path = await loop.run_in_executor(None, gen.generate, photo_path, size, None)
        if not thumb_path:
            raise HTTPException(status_code=404, detail="Thumbnail not found")

    fmt = thumb_path.suffix.lstrip(".")
    media_map = {"webp": "image/webp", "jpg": "image/jpeg", "jpeg": "image/jpeg"}

    try:
        with open(thumb_path, "rb") as f:
            content = f.read()
        return Response(
            content=content,
            media_type=media_map.get(fmt, "image/webp"),
            headers={"Cache-Control": "public, max-age=31536000"}
        )
    except Exception as e:
        logger.error(f"Failed to read thumbnail {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read thumbnail")


@router.get("/face/{face_id}")
async def get_face_crop(face_id: str, margin: float = 0.5):
    import asyncio
    from database import DatabaseManager

    db = DatabaseManager()
    face = db.get_face(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    photo_path = PHOTO_SHARE_PATH / face["photo_id"]
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    bbox = (int(face["bbox_x1"]), int(face["bbox_y1"]), int(face["bbox_x2"]), int(face["bbox_y2"]))

    def _crop():
        import pyvips
        img = pyvips.Image.new_from_file(str(photo_path), access="random")
        x1, y1, x2, y2 = bbox
        fw = x2 - x1
        fh = y2 - y1
        mx = int(fw * margin)
        my = int(fh * margin)
        ix1 = max(0, x1 - mx)
        iy1 = max(0, y1 - my)
        ix2 = min(img.width, x2 + mx)
        iy2 = min(img.height, y2 + int(fh * margin * 1.5))
        crop = img.crop(ix1, iy1, ix2 - ix1, iy2 - iy1)
        max_dim = 200
        if max(crop.width, crop.height) > max_dim:
            crop = crop.thumbnail_image(max_dim, crop="none")
        return crop.write_to_buffer(".webp", Q=85)

    try:
        loop = asyncio.get_event_loop()
        buf = await loop.run_in_executor(None, _crop)
        return Response(content=buf, media_type="image/webp",
                        headers={"Cache-Control": "public, max-age=31536000"})
    except Exception as e:
        logger.error(f"Failed to crop face {face_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to crop face")


@router.get("/face_context/{face_id}")
async def get_face_context(face_id: str, zoom: float = 3.0):
    from database import DatabaseManager
    import io

    db = DatabaseManager()
    face = db.get_face(face_id)
    if not face:
        raise HTTPException(status_code=404, detail="Face not found")

    photo_path = PHOTO_SHARE_PATH / face["photo_id"]
    if not photo_path.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    bbox = (float(face["bbox_x1"]), float(face["bbox_y1"]), float(face["bbox_x2"]), float(face["bbox_y2"]))

    def _context():
        import pyvips, io
        from PIL import Image as PILImage, ImageDraw
        img = pyvips.Image.new_from_file(str(photo_path), access="random")
        iw, ih = img.width, img.height
        x1, y1, x2, y2 = bbox
        fw, fh = x2 - x1, y2 - y1
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        vw, vh = fw * zoom, fh * zoom
        vx1 = max(0, int(cx - vw / 2))
        vy1 = max(0, int(cy - vh / 2))
        vx2 = min(iw, int(cx + vw / 2))
        vy2 = min(ih, int(cy + vh / 2))
        crop = img.crop(vx1, vy1, vx2 - vx1, vy2 - vy1)
        rx1, ry1 = int(x1 - vx1), int(y1 - vy1)
        rx2, ry2 = int(x2 - vx1), int(y2 - vy1)
        crop_buf = crop.write_to_buffer(".png")
        pil_crop = PILImage.open(io.BytesIO(crop_buf))
        draw = ImageDraw.Draw(pil_crop)
        draw.rectangle([rx1, ry1, rx2, ry2], outline="red", width=3)
        buf = io.BytesIO()
        pil_crop.save(buf, format='JPEG', quality=90)
        return buf.getvalue()

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, _context)
        return Response(content=content, media_type="image/jpeg",
                        headers={"Cache-Control": "public, max-age=31536000"})
    except Exception as e:
        logger.error(f"Failed to get face context {face_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get face context")


@router.get("/list")
async def list_photos(limit: int = 100, offset: int = 0, sort: str = "changed_desc"):
    from database import DatabaseManager
    from datetime import datetime

    db = DatabaseManager()

    actual_sort = "created_desc" if sort not in ("changed_desc", "changed_asc") else sort

    if sort == "changed_desc":
        recent_rows = db.sqlite.execute(
            "SELECT p.photo_id, MAX(c.changed_at) as cat FROM changes c "
            "JOIN photos p ON c.photo_id = p.photo_id "
            "GROUP BY p.photo_id ORDER BY cat DESC LIMIT ?",
            (limit,)
        ).fetchall()
        recent_pids = [r[0] for r in recent_rows]
        change_times = {r[0]: r[1] for r in recent_rows}
        photos = []
        for pid in recent_pids:
            row = db.sqlite.execute("SELECT * FROM photos WHERE photo_id=?", (pid,)).fetchone()
            if row:
                cols = [d[0] for d in db.sqlite.execute("SELECT * FROM photos LIMIT 0").description]
                photos.append(dict(zip(cols, row)))
        total = db.count_photos()
    else:
        total, photos = db.search_photos(sort="created_desc", limit=limit * 3, offset=0)

    all_faces = db.get_all_faces()
    all_personas = db.get_all_personas()
    persona_map = {p["persona_id"]: p for p in all_personas}

    photo_faces = {}
    for f in all_faces:
        photo_faces.setdefault(f.get("photo_id", ""), []).append(f)

    last_changes = {}
    if sort == "changed_desc":
        for p in photos:
            last_changes[p.get("path", "")] = change_times.get(p.get("photo_id"))
    else:
        rows = db.sqlite.execute(
            "SELECT photo_id, MAX(changed_at) as cat FROM changes GROUP BY photo_id"
        ).fetchall()
        change_by_pid = {r[0]: r[1] for r in rows}
        pid_to_path = {}
        for r in db.sqlite.execute("SELECT photo_id, path FROM photos").fetchall():
            pid_to_path[r[0]] = r[1]
        for pid, cat in change_by_pid.items():
            path = pid_to_path.get(pid)
            if path:
                last_changes[path] = cat

    enriched = []
    for p in photos:
        ep = _enrich_photo(p, photo_faces, persona_map, include_thumbnail=True)
        ep["changed_at"] = last_changes.get(p.get("path"))
        enriched.append(ep)

    if sort == "changed_desc":
        enriched.sort(key=lambda x: x.get("changed_at") or "", reverse=True)
        enriched = [e for e in enriched if e.get("changed_at")] + [e for e in enriched if not e.get("changed_at")]
    elif sort == "changed_asc":
        enriched.sort(key=lambda x: x.get("changed_at") or "", reverse=False)

    server_time = datetime.now().isoformat()
    return {"total": total, "photos": enriched[:limit], "server_time": server_time}


@router.get("/description")
async def get_description(path: str):
    from database import DatabaseManager

    db = DatabaseManager()
    if path.startswith("/"):
        photo = db.get_photo_by_path(path)
    else:
        photo = db.get_photo_by_path(str(PHOTO_SHARE_PATH / path))

    if photo and photo.get("description"):
        return {"path": path, "description": photo["description"]}

    return {"path": path, "description": None}


@router.get("/search")
async def search_photos(
    q: str = "",
    person: str = "",
    date_from: str = "",
    date_to: str = "",
    date_after: str = "",
    date_before: str = "",
    path_after: str = "",
    path_before: str = "",
    has_faces: Optional[bool] = None,
    no_description: Optional[bool] = None,
    has_issues: Optional[bool] = None,
    issue_type: Optional[str] = None,
    photo_type: Optional[str] = None,
    has_gps: Optional[bool] = None,
    no_date: Optional[bool] = None,
    has_description: Optional[bool] = None,
    deleted: Optional[bool] = None,
    deleted_only: Optional[bool] = None,
    sort: str = "date_desc",
    limit: int = 60,
    offset: int = 0,
):
    from database import DatabaseManager

    db = DatabaseManager()

    total, photos = db.search_photos(
        q=q or None,
        person=person or None,
        date_from=date_from or None,
        date_to=date_to or None,
        date_after=date_after or None,
        date_before=date_before or None,
        path_after=path_after or None,
        path_before=path_before or None,
        has_faces=has_faces,
        no_description=no_description,
        has_issues=has_issues,
        issue_type=issue_type,
        photo_type=photo_type,
        has_gps=has_gps,
        no_date=no_date,
        has_description=has_description,
        deleted=deleted,
        deleted_only=deleted_only,
        sort=sort,
        limit=limit,
        offset=offset,
    )

    all_faces = db.get_all_faces()
    all_personas = db.get_all_personas()
    persona_map = {p["persona_id"]: p for p in all_personas}

    photo_faces = {}
    for f in all_faces:
        photo_faces.setdefault(f.get("photo_id", ""), []).append(f)

    result = [_enrich_photo(p, photo_faces, persona_map, include_created=True) for p in photos]
    return {"total": total, "photos": result}


PIPELINE_GPU_PROCS = ["face_pipeline", "faces.py", "faces", "vision_describe", "describe.py", "describe"]


def _pause_pipeline():
    import os
    saved_flags = {}
    for fname in os.listdir(FLAG_DIR):
        path = os.path.join(FLAG_DIR, fname)
        if os.path.isfile(path):
            saved_flags[fname] = True
            os.remove(path)
    for pattern in PIPELINE_GPU_PROCS:
        os.system(f"pkill -f '{pattern}' 2>/dev/null")
    os.system("pkill -9 -f 'llama-server' 2>/dev/null")
    time.sleep(2)
    return saved_flags


def _resume_pipeline(saved_flags):
    import os
    for fname in saved_flags:
        path = os.path.join(FLAG_DIR, fname)
        os.makedirs(FLAG_DIR, exist_ok=True)
        open(path, 'w').close()


@router.get("/semantic_search")
async def semantic_search(q: str = "", limit: int = 20, threshold: float = 1.0):
    import json
    import subprocess
    import urllib.request
    from database import DatabaseManager

    if not q:
        return {"total": 0, "photos": [], "query": q}

    logger.info(f"[SEMSEARCH] Start: q={q!r} threshold={threshold} limit={limit}")

    db = DatabaseManager()

    task = "Retrieve photographs matching the description, including people, places, events, and scenes"
    query_text = "Instruct: " + task + "\nQuery: " + q

    _vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
    LD_LIBRARY_PATH = ":".join([
        _vnvidia + "/cublas/lib",
        _vnvidia + "/cuda_runtime/lib",
        "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
        str(LLAMA_CPP_DIR / "build" / "bin"),
    ])

    embed_port = 8102
    embed_server = None
    saved_flags = _pause_pipeline()
    logger.info(f"[SEMSEARCH] Pipeline paused, saved_flags={list(saved_flags.keys())}")

    q_emb = None
    try:
        import os
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH
        embed_server = subprocess.Popen(
            [
                str(LLAMA_CPP_DIR / "build" / "bin" / "llama-server"),
                "-m", str(PROJECT_ROOT / "gguf" / "Qwen3-Embedding-0.6B-F16.gguf"),
                "--embedding", "--pooling", "last",
                "-ngl", "99", "-c", "512",
                "--port", str(embed_port), "-t", "4", "-np", "4",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        logger.info(f"[SEMSEARCH] llama-server started pid={embed_server.pid}")
        started = False
        for i in range(60):
            try:
                resp = urllib.request.urlopen(f"http://localhost:{embed_port}/health", timeout=3)
                if json.loads(resp.read()).get("status") == "ok":
                    started = True
                    logger.info(f"[SEMSEARCH] llama-server ready ({i+1}s)")
                    break
            except Exception:
                time.sleep(1)

        if not started:
            stderr = embed_server.stderr.read().decode()[:500] if embed_server.stderr else ""
            logger.error(f"[SEMSEARCH] llama-server FAILED to start. stderr: {stderr}")
            return {"total": 0, "photos": [], "query": q, "error": "embedding server failed to start"}

        req = urllib.request.Request(
            f"http://localhost:{embed_port}/v1/embeddings",
            data=json.dumps({"input": [query_text], "model": "qwen3-embedding"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        result = json.loads(resp.read())
        q_emb = result["data"][0]["embedding"]
        logger.info(f"[SEMSEARCH] Got embedding size={len(q_emb)}")
    except Exception as e:
        logger.error(f"[SEMSEARCH] Error getting embedding: {e}")
        return {"total": 0, "photos": [], "query": q, "error": str(e)}
    finally:
        if embed_server is not None:
            try:
                embed_server.terminate()
                embed_server.wait(timeout=5)
                logger.info("[SEMSEARCH] llama-server terminated")
            except Exception:
                embed_server.kill()
                logger.info("[SEMSEARCH] llama-server killed")
        _resume_pipeline(saved_flags)
        logger.info("[SEMSEARCH] Pipeline resumed")

    if q_emb is None:
        logger.error("[SEMSEARCH] No embedding obtained")
        return {"total": 0, "photos": [], "query": q, "error": "no embedding"}

    logger.info(f"[SEMSEARCH] Searching LanceDB with threshold={threshold}")
    results = db.search_photo_embeddings(q_emb, limit=limit * 2)
    logger.info(f"[SEMSEARCH] LanceDB returned {len(results)} raw results")
    if results:
        top_dist = results[0].get("_distance", results[0].get("_relevance_score", "?"))
        logger.info(f"[SEMSEARCH] Top distance={top_dist}")

    all_faces = db.get_all_faces()
    all_personas = db.get_all_personas()
    persona_map = {p["persona_id"]: p for p in all_personas}

    photo_faces = {}
    for f in all_faces:
        photo_faces.setdefault(f.get("photo_id", ""), []).append(f)

    out_list = []
    seen_pids = set()
    skipped_no_photo = 0
    skipped_not_embedded = 0
    skipped_threshold = 0
    for r in results:
        pid = r.get("photo_id", "")
        if pid in seen_pids:
            continue
        seen_pids.add(pid)
        photo = db.get_photo(pid)
        if not photo:
            skipped_no_photo += 1
            continue
        if not photo.get("embedded"):
            skipped_not_embedded += 1
            continue
        score = r.get("_distance", r.get("_relevance_score", 999))
        if score > threshold:
            skipped_threshold += 1
            continue
        enriched = _enrich_photo(photo, photo_faces, persona_map, include_created=True, include_score=True, score=score)
        out_list.append(enriched)
        if len(out_list) >= limit:
            break

    logger.info(f"[SEMSEARCH] Final: {len(out_list)} results (skipped: no_photo={skipped_no_photo}, not_embedded={skipped_not_embedded}, threshold={skipped_threshold})")
    return {"total": len(out_list), "photos": out_list, "query": q}


@router.post("/{photo_id}/enrich")
async def enrich_description(photo_id: str):
    import subprocess, os
    from database import DatabaseManager
    db = DatabaseManager()
    photo = db.get_photo(photo_id)
    if not photo:
        photo = db.get_photo_by_path(photo_id)
    if not photo:
        return {"ok": False, "error": "photo not found"}

    path = photo.get("path", "")
    if not path:
        return {"ok": False, "error": "no path"}

    from config import VENV_PYTHON as VENV
    cmd = [VENV, str(PROJECT_ROOT / "enrich_description.py"), "--photo", path]
    env = os.environ.copy()
    _vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
    env["LD_LIBRARY_PATH"] = ":".join([
        _vnvidia + "/cublas/lib",
        _vnvidia + "/cuda_runtime/lib",
        "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
        str(LLAMA_CPP_DIR / "build" / "bin"),
    ])

    try:
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=90)
        db2 = DatabaseManager()
        updated = db2.get_photo(photo_id)
        if not updated:
            updated = db2.get_photo_by_path(path)
        rich = updated.get("rich_description") if updated else None
        return {"ok": True, "rich_description": rich}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("/{photo_id}/rich_description")
async def save_rich_description(photo_id: str, request: Request):
    from database import DatabaseManager

    body = await request.json()
    rich = body.get("rich_description")

    if rich is None:
        raise HTTPException(status_code=400, detail="rich_description is required")

    db = DatabaseManager()
    photo = db.get_photo(photo_id)
    if not photo:
        photo = db.get_photo_by_path(photo_id)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    db.update_photo(photo["photo_id"], rich_description=rich)
    return {"ok": True, "rich_description": rich}


@router.get("/dates")
async def get_date_histogram():
    from database import DatabaseManager

    db = DatabaseManager()
    return db.get_date_histogram()


@router.post("/describe")
async def describe_photos(paths: List[str], batch_size: int = 10):
    import subprocess
    import sys

    valid_paths = []
    for p in paths:
        full_path = PHOTO_SHARE_PATH / p
        if full_path.exists():
            valid_paths.append(str(full_path))

    if not valid_paths:
        raise HTTPException(status_code=400, detail="No valid photo paths")

    cmd = [
        sys.executable, str(PROJECT_ROOT / "vision_describe.py"),
        "--single" if len(valid_paths) == 1 else valid_paths[0],
    ]

    return {
        "status": "accepted",
        "count": len(valid_paths),
        "message": f"Use CLI: python {PROJECT_ROOT / 'vision_describe.py'} {PHOTO_SHARE_PATH}/dir --batch-size {batch_size}",
    }


@router.get("/map")
async def get_map_photos():
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        cur = db.sqlite.cursor()
        rows = cur.execute("""
            SELECT photo_id, path, description, gps_lat, gps_lon, COALESCE(manual_date, date) as date, camera_make, camera_model, img_width, img_height, manual_gps
            FROM photos
            WHERE gps_lat IS NOT NULL AND gps_lon IS NOT NULL
              AND gps_lat != 0 AND gps_lon != 0
              AND deleted = 0
        """).fetchall()
        result = []
        for r in rows:
            abs_path = r[1] or ""
            rel = abs_path[len(FOTO_PREFIX):] if abs_path.startswith(FOTO_PREFIX) else abs_path
            cam_parts = []
            if r[6]: cam_parts.append(r[6])
            if r[7]: cam_parts.append(r[7])
            result.append({
                "photo_id": r[0],
                "path": abs_path,
                "rel_path": rel,
                "description": r[2] or "",
                "lat": r[3],
                "lon": r[4],
                "date": r[5] or "",
                "camera": " ".join(cam_parts) if cam_parts else "",
                "w": r[8],
                "h": r[9],
                "manual_gps": r[10] or 0,
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/neighbor")
async def get_neighbor(date: str, dir: str = "next"):
    from database import DatabaseManager

    if dir not in ("next", "prev"):
        raise HTTPException(status_code=400, detail="dir must be next or prev")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    if dir == "next":
        row = cur.execute(
            "SELECT photo_id, path, description, COALESCE(manual_date, date) as effective_date, camera_make, camera_model, gps_lat, gps_lon "
            "FROM photos WHERE COALESCE(manual_date, date) > ? ORDER BY effective_date ASC LIMIT 1",
            (date,)
        ).fetchone()
    else:
        row = cur.execute(
            "SELECT photo_id, path, description, COALESCE(manual_date, date) as effective_date, camera_make, camera_model, gps_lat, gps_lon "
            "FROM photos WHERE COALESCE(manual_date, date) < ? ORDER BY effective_date DESC LIMIT 1",
            (date,)
        ).fetchone()

    if not row:
        return None

    abs_path = row[1] or ""
    rel = abs_path[len(FOTO_PREFIX):] if abs_path.startswith(FOTO_PREFIX) else abs_path
    cam_parts = []
    if row[4]: cam_parts.append(row[4])
    if row[5]: cam_parts.append(row[5])

    return {
        "photo_id": row[0],
        "path": abs_path,
        "rel_path": rel,
        "description": row[2] or "",
        "date": row[3] or "",
        "camera": " ".join(cam_parts) if cam_parts else "",
        "lat": row[6],
        "lon": row[7],
    }


@router.post("/reverse_geocode")
async def reverse_geocode(request: Request):
    import reverse_geocoder
    body = await request.json()
    if isinstance(body, list):
        coords = body
    else:
        coords = body.get("coords", [])
    points = [(c["lat"], c["lon"]) for c in coords]
    results = reverse_geocoder.search(points)
    out = []
    for r in results:
        parts = []
        if r.get("name"):
            parts.append(r["name"])
        if r.get("admin1") and r["admin1"] != r.get("name"):
            parts.append(r["admin1"])
        cc = r.get("cc", "")
        country_map = {
            "RU": "Россия", "UA": "Украина", "BY": "Беларусь", "KZ": "Казахстан",
            "GE": "Грузия", "AM": "Армения", "UZ": "Узбекистан", "KG": "Кыргызстан",
            "TJ": "Таджикистан", "MD": "Молдова", "AZ": "Азербайджан", "TR": "Турция",
            "TH": "Таиланд", "VN": "Вьетнам", "KR": "Корея", "KP": "КНДР",
            "CN": "Китай", "JP": "Япония", "DE": "Германия", "FR": "Франция",
            "IT": "Италия", "ES": "Испания", "GB": "Великобритания", "US": "США",
            "EG": "Египет", "TR": "Турция", "AE": "ОАЭ", "CZ": "Чехия",
            "PL": "Польша", "FI": "Финляндия", "SE": "Швеция", "NO": "Норвегия",
            "ME": "Черногория", "HR": "Хорватия", "RS": "Сербия", "BG": "Болгария",
            "GR": "Греция", "CY": "Кипр", "IL": "Израиль", "IN": "Индия",
            "CU": "Куба", "MX": "Мексика", "BR": "Бразилия", "AU": "Австралия",
        }
        country = country_map.get(cc, cc)
        if country and country != parts[-1] if parts else True:
            parts.append(country)
        out.append(", ".join(parts))
    return out


@router.post("/set_gps")
async def set_gps(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")
    lat = body.get("lat")
    lon = body.get("lon")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")
    if lat is None or lon is None:
        raise HTTPException(status_code=400, detail="lat and lon are required")

    try:
        lat = float(lat)
        lon = float(lon)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="lat and lon must be valid numbers")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET gps_lat = ?, gps_lon = ?, manual_gps = 1 WHERE photo_id = ?",
        (lat, lon, real_id)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/set_date")
async def set_date(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")
    manual_date = body.get("manual_date")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")
    if not manual_date:
        raise HTTPException(status_code=400, detail="manual_date is required")

    if len(manual_date) == 10 and manual_date[4] == '-' and manual_date[7] == '-':
        manual_date += " 00:00:00"
    elif len(manual_date) == 16 and manual_date[10] == ' ':
        manual_date += ":00"

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET manual_date = ? WHERE photo_id = ?",
        (manual_date, real_id)
    )
    db.sqlite.commit()

    return {"success": True, "manual_date": manual_date}


@router.post("/clear_date")
async def clear_date(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET manual_date = NULL WHERE photo_id = ?",
        (real_id,)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/clear_gps")
async def clear_gps(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    real_id = row[0]
    cur.execute(
        "UPDATE photos SET gps_lat = NULL, gps_lon = NULL, manual_gps = 0 WHERE photo_id = ?",
        (real_id,)
    )
    db.sqlite.commit()

    return {"success": True}


@router.post("/mark_deleted")
async def mark_deleted(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    cur.execute("UPDATE photos SET deleted = 1 WHERE photo_id = ?", (row[0],))
    db.sqlite.commit()

    return {"success": True}


@router.post("/undelete")
async def undelete(request: Request):
    from database import DatabaseManager

    body = await request.json()
    photo_id = body.get("photo_id")

    if not photo_id:
        raise HTTPException(status_code=400, detail="photo_id is required")

    db = DatabaseManager()
    cur = db.sqlite.cursor()

    row = cur.execute(
        "SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?",
        (photo_id, '%' + photo_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    cur.execute("UPDATE photos SET deleted = 0 WHERE photo_id = ?", (row[0],))
    db.sqlite.commit()

    return {"success": True}
