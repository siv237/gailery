#!/usr/bin/env python3
"""
describe.py - Generate VLM descriptions for photos in DB that lack them.
Runs vision_describe.py on the root photo dir once (one model load).

Usage:
    python describe.py --limit 100
    python describe.py --all
    python describe.py --batch-size 25
"""

import argparse
import os
import sys
import subprocess
import time
import base64
import json
import re
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import PHOTO_SHARE_PATH, LLAMA_CPP_DIR
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "describe")


def log(msg):
    line = f"[{datetime.now().isoformat()}] [DESCRIBE] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


SYSTEM_PROMPT = """Ты — автоматический анализатор фотографий. Анализируй изображение и вызови функцию describe_photo с результатами.

Обрати внимание:
- description: что происходит на фото, кто изображён, где, настроение. Пиши на русском.
- photo_type: классификация изображения. photo = обычная фотография, screenshot = скриншот экрана, document = документ/квитанция/скан/чек/сертификат/объявление, meme = мем/карточка с текстом, icon = иконка/аватарка, other = всё остальное
- has_faces: true если видны лица людей (даже частично), false если нет людей или лица не видны"""


def set_flag():
    import os
    os.makedirs(os.path.dirname(FLAG_FILE), exist_ok=True)
    open(FLAG_FILE, 'w').close()


def clear_flag():
    import os
    try:
        os.remove(FLAG_FILE)
    except Exception:
        pass


def count_undescribed():
    from database import DatabaseManager
    db = DatabaseManager()
    return db.sqlite.execute(
        "SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path "
        "WHERE (p.description IS NULL OR p.description = '') AND p.deleted = 0 AND cf.is_canonical = 1 AND (p.media_type IS NULL OR p.media_type != 'video')"
    ).fetchone()[0]


def _prepare_ollama_image(img_path):
    from PIL import Image
    img = Image.open(img_path)
    img_w, img_h = img.size
    max_dim = max(img.size)
    if max_dim > 1280:
        scale = 1280 / max_dim
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    import io
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=85)
    return base64.b64encode(buf.getvalue()).decode('utf-8'), img_w


def _bbox_to_position(bbox, img_width):
    x_center = (bbox[0] + bbox[2]) / 2 / max(img_width, 1)
    if x_center < 0.33:
        return "слева"
    elif x_center > 0.67:
        return "справа"
    return "в центре"


def _get_face_context(content_hash, img_width, db):
    if not content_hash or not db:
        return ""
    try:
        rows = db.sqlite.execute(
            "SELECT f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, p.display_name, p.comment "
            "FROM faces f LEFT JOIN personas p ON f.persona_id = p.persona_id "
            "WHERE f.content_hash = ?",
            (content_hash,)
        ).fetchall()
    except Exception:
        return ""
    if not rows:
        return ""
    parts = []
    named_count = 0
    unnamed_count = 0
    for r in rows:
        bbox = [r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0]
        pos = _bbox_to_position(bbox, img_width)
        name = r[4]
        comment = r[5]
        if name:
            entry = f"{name} ({pos})"
            if comment:
                entry += f", {comment}"
            parts.append(entry)
            named_count += 1
        else:
            unnamed_count += 1
    lines = []
    if named_count > 0:
        lines.append(f"На фото обнаружены лица: {', '.join(parts)}.")
    if unnamed_count > 0:
        lines.append(f"Также {unnamed_count} лиц без имён.")
    if lines:
        lines.append("Используй имена в описании если они подходят к людям на фото.")
    return " ".join(lines)


def _get_photo_context(photo_path, db):
    if not db:
        return ""
    parts = []
    try:
        row = db.sqlite.execute(
            "SELECT p.manual_date, p.date, cr.alias "
            "FROM photos p "
            "LEFT JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
            "LEFT JOIN catalog_roots cr ON cf.root_id = cr.root_id "
            "WHERE p.path = ? AND p.deleted = 0",
            (photo_path,)
        ).fetchone()
        if row:
            date_val = row[0] or row[1]
            if date_val:
                date_str = str(date_val)[:10]
                parts.append(f"Дата съёмки: {date_str}.")
            if row[2]:
                parts.append(f"Папка: {row[2]}.")
    except Exception:
        pass
    return " ".join(parts)


def _describe_ollama_request(img_b64, ollama_url, ollama_model, face_context=""):
    import urllib.request
    user_text = "Проанализируй эту фотографию."
    if face_context:
        user_text += " " + face_context
    body = json.dumps({
        "model": ollama_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text, "images": [img_b64]},
        ],
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.1, "num_predict": 256, "num_gpu": 20, "num_ctx": 2048},
    }).encode()
    req = urllib.request.Request(f"{ollama_url}/api/chat", data=body,
        headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=120)
    msg = json.loads(resp.read()).get("message", {}).get("content", "")
    try:
        data = json.loads(msg)
        desc = data.get("description", "")
        has_faces = data.get("has_faces", False)
    except json.JSONDecodeError:
        m = re.search(r'"description"\s*:\s*"(.+?)"', msg)
        desc = m.group(1) if m else msg[:500]
        has_faces = "has_faces" in msg and "true" in msg.lower()
    return desc, has_faces


def _save_description(db, photo_id, path, description, has_faces):
    cur = db.sqlite.cursor()
    faces_done_row = db.sqlite.execute(
        "SELECT faces_done FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 LIMIT 1",
        (path,)
    ).fetchone()
    faces_done = faces_done_row[0] if faces_done_row else 0
    if faces_done:
        photo = db.get_photo_by_path(path)
        faces_present_val = photo.get("faces_present", 0) if photo else 0
    else:
        faces_present_val = 1 if has_faces else 0
    cur.execute(
        "UPDATE photos SET description = ?, faces_present = ? WHERE photo_id = ? AND deleted = 0",
        (description, faces_present_val, photo_id),
    )
    db.sqlite.commit()
    log(f"  Saved: {Path(path).name} faces={has_faces} desc={description[:60]}...")


def _get_photos_to_describe(limit=0, dir_filter=""):
    from database import DatabaseManager
    db = DatabaseManager()
    sql = """
        SELECT p.photo_id, p.path FROM photos p
        JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0
WHERE (p.description IS NULL OR p.description = '') AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')
    """
    if dir_filter:
        dir_filter = dir_filter.rstrip('/')
        sql += f" AND p.path LIKE '{dir_filter}/%'"
    sql += " ORDER BY p.path"
    if limit > 0:
        sql += f" LIMIT {limit}"
    rows = db.sqlite.execute(sql).fetchall()
    return db, rows


def main():
    parser = argparse.ArgumentParser(description="Generate VLM descriptions")
    parser.add_argument("--limit", type=int, default=60, help="Max photos to describe (0=all)")
    parser.add_argument("--batch-size", type=int, default=6, help="VLM batch size (parallel slots)")
    parser.add_argument("--all", action="store_true", help="Describe all undescribed photos")
    parser.add_argument("--dir", type=str, default="", help="Only describe photos under this directory")
    args = parser.parse_args()

    from config import describe_backend as db_backend, OLLAMA_MODE, OLLAMA_BASE_URL, OLLAMA_DESCRIBE_MODEL
    be = db_backend or OLLAMA_MODE
    count = count_undescribed()
    if count == 0:
        log("No undescribed photos found")
        return 0

    log(f"Found {count} undescribed photos, backend={be}")
    set_flag()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("describe")
    except Exception:
        mq = None

    try:
        limit = 0 if args.all else args.limit
        t0 = time.time()

        if be == "ollama":
            return _main_ollama(db=None, limit=limit, dir_filter=args.dir, mq=mq, t0=t0,
                                batch_size=args.batch_size)
        else:
            return _main_local(args, mq=mq, t0=t0)
    finally:
        clear_flag()
        if mq:
            mq.shutdown()


def _main_local(args, mq, t0):
    cmd = [
        sys.executable, str(Path(__file__).parent / "vision_describe.py"),
        "--batch-size", str(args.batch_size),
    ]
    if args.dir:
        cmd.append(args.dir)
    limit = 0 if args.all else args.limit
    if limit > 0:
        cmd += ["--limit", str(limit)]

    log(f"Running: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent / "src")
    _vnvidia = str(Path(__file__).parent / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
    env["LD_LIBRARY_PATH"] = ":".join([
        _vnvidia + "/cublas/lib",
        _vnvidia + "/cuda_runtime/lib",
        "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
        str(LLAMA_CPP_DIR / "build" / "bin"),
    ])
    result = subprocess.run(cmd, env=env)
    elapsed = time.time() - t0
    remaining = count_undescribed()
    described = (args.limit if args.all else min(args.limit, args.limit)) - remaining
    log(f"Done: {described} described in {elapsed:.0f}s")
    return result.returncode


def _main_ollama(db, limit, dir_filter, mq, t0, batch_size=6):
    import urllib.request
    from config import OLLAMA_DESCRIBE_MODEL, OLLAMA_BASE_URL
    from concurrent.futures import ThreadPoolExecutor, as_completed

    url = OLLAMA_BASE_URL.rstrip('/')
    model = OLLAMA_DESCRIBE_MODEL
    batch_size = batch_size or 6

    db, rows = _get_photos_to_describe(limit=limit, dir_filter=dir_filter)

    # Preload model with correct VRAM params
    log(f"Preloading {model} with num_gpu=20 num_ctx=2048...")
    try:
        body = json.dumps({"model": model, "keep_alive": "5m",
            "options": {"num_gpu": 20, "num_ctx": 2048}}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/generate", data=body,
            headers={"Content-Type": "application/json"}), timeout=30)
        log("Model preloaded")
    except Exception as e:
        log(f"Preload failed (will load on first request): {e}")

    # Filter valid paths and prepare images FIRST (like vision_describe.py describe_batch)
    prepared = []
    for pid, p in rows:
        if not os.path.exists(p):
            log(f"  SKIP (missing): {Path(p).name}")
            continue
        try:
            fsize = os.path.getsize(p)
            if fsize < 1024:
                log(f"  SKIP (too small): {Path(p).name}")
                continue
            img_b64, img_w = _prepare_ollama_image(p)
            content_hash = None
            ch_row = db.sqlite.execute(
                "SELECT content_hash FROM catalog_files WHERE abs_path = ? AND content_hash IS NOT NULL LIMIT 1",
                (p,)
            ).fetchone()
            if ch_row:
                content_hash = ch_row[0]
            fc = _get_face_context(content_hash, img_w, db)
            pc = _get_photo_context(p, db)
            ctx = " ".join(filter(None, [fc, pc]))
            prepared.append((pid, p, img_b64, ctx))
        except Exception as e:
            log(f"  SKIP (image error): {Path(p).name}: {e}")

    total = len(prepared)
    described = 0
    failed = 0

    # Process in parallel batches — only HTTP requests in pool
    for batch_start in range(0, total, batch_size):
        batch = prepared[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        t_batch = time.time()
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futs = {}
            for photo_id, path, img_b64, fc in batch:
                futs[pool.submit(_describe_ollama_request, img_b64, url, model, fc)] = (photo_id, path)

            for fut in as_completed(futs):
                photo_id, path = futs[fut]
                try:
                    desc, has_faces = fut.result()
                    _save_description(db, photo_id, path, desc, has_faces)
                    described += 1
                    log(f"  [{described}/{total}] {Path(path).name}")
                except Exception as e:
                    log(f"  ERROR: {Path(path).name}: {e}")
                    failed += 1

                if mq and mq.stopped():
                    pool.shutdown(cancel_futures=True)
                    break

        dt_batch = time.time() - t_batch
        elapsed = time.time() - t0
        rate = described / max(elapsed, 1)
        pct = described / max(total, 1) * 100
        log(f"  Batch {batch_num}/{total_batches}: {dt_batch:.1f}s | [{described}/{total}] {pct:.1f}% | {elapsed:.0f}с, {rate:.2f}/с")

    elapsed = time.time() - t0
    log(f"Done (Ollama): {described} described, {failed} failed in {elapsed:.0f}s ({described/max(elapsed,1):.2f}/s)")

    # Unload model
    try:
        body = json.dumps({"model": model, "keep_alive": 0}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/api/generate", data=body,
            headers={"Content-Type": "application/json"}), timeout=10)
        log("Ollama model unloaded, VRAM freed")
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
