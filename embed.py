#!/usr/bin/env python3
"""
embed.py - Generate text embeddings for semantic search.
Uses llama-server + GGUF model (Qwen3-Embedding-0.6B-F16.gguf).
Stores vectors in LanceDB.

Usage:
    python embed.py
    python embed.py --limit 50
    python embed.py --force    # re-embed all (ignore existing)
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import PHOTO_SHARE_PATH, LLAMA_CPP_DIR, MODELS_DIR
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "embed")

EMBED_PORT = 8102
GGUF_MODEL = str(MODELS_DIR / "gguf" / "Qwen3-Embedding-0.6B-F16.gguf")
LANCE_FLUSH_SIZE = 2048
LOG_INTERVAL = 10
EMBED_BATCH_SIZE = 64


def _fmt_dur(secs):
    s = int(secs)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return str(h) + "ч " + str(m) + "м"
    if m > 0:
        return str(m) + "м " + str(s) + "с"
    return str(s) + "с"


def _fmt_eta(elapsed, pct):
    if pct < 1 or pct >= 100:
        return ""
    remaining = elapsed / pct * (100 - pct)
    return ", осталось ~" + _fmt_dur(remaining)


def log(msg):
    line = f"[{datetime.now().isoformat()}] [EMBED] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def set_flag():
    os.makedirs(os.path.dirname(FLAG_FILE), exist_ok=True)
    open(FLAG_FILE, 'w').close()


def clear_flag():
    try:
        os.remove(FLAG_FILE)
    except Exception:
        pass


def stopped():
    return not os.path.exists(FLAG_FILE)


def start_embed_server():
    if not Path(GGUF_MODEL).exists():
        log(f"GGUF model not found: {GGUF_MODEL}")
        return None

    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = "0"

    proc = subprocess.Popen(
        [
            str(LLAMA_CPP_DIR / "build" / "bin" / "llama-server"),
            "-m", GGUF_MODEL,
            "--embedding", "--pooling", "last",
            "-ngl", "99", "--no-mmap",
            "--port", str(EMBED_PORT), "-t", "4", "-np", str(EMBED_BATCH_SIZE),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    log(f"llama-server started pid={proc.pid} port={EMBED_PORT}")

    for i in range(60):
        try:
            resp = urllib.request.urlopen(f"http://localhost:{EMBED_PORT}/health", timeout=3)
            if json.loads(resp.read()).get("status") == "ok":
                log(f"llama-server ready ({i+1}s)")
                return proc
        except Exception:
            pass
        time.sleep(1)

    log("llama-server failed to start")
    try:
        proc.kill()
    except Exception:
        pass
    return None


def encode_batch(texts, max_length=512):
    payload = json.dumps({
        "input": texts,
        "max_length": max_length,
    }).encode()
    req = urllib.request.Request(
        f"http://localhost:{EMBED_PORT}/v1/embeddings",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=120)
    data = json.loads(resp.read())
    vectors = []
    for item in data.get("data", []):
        vectors.append(item["embedding"])
    return vectors


def build_search_text(photo, faces_for_photo, persona_map):
    parts = []

    face_names = []
    for f in faces_for_photo:
        pers_id = f.get("persona_id")
        if not pers_id:
            continue
        pers = persona_map.get(pers_id, {})
        name = pers.get("display_name") or pers.get("name") or pers_id
        if name not in face_names:
            face_names.append(name)
    if face_names:
        parts.append(", ".join(face_names))

    desc = photo.get("description")
    if desc:
        parts.append(desc)

    path = photo.get("path", "")
    if path:
        p = Path(path)
        parts_from_path = []
        for i, part in enumerate(p.parts):
            if part in ("mnt", "share", "Foto", "/"):
                continue
            if i == len(p.parts) - 1:
                continue
            try:
                int(part)
                continue
            except ValueError:
                parts_from_path.append(part)
        if parts_from_path:
            parts.append(" | ".join(parts_from_path))

    date = photo.get("manual_date") or photo.get("date")
    if date and date != "0000:00:00 00:00:00":
        parts.append(date[:10].replace(":", "-"))

    cam = photo.get("camera_model")
    if cam:
        make = photo.get("camera_make", "")
        parts.append(f"{make} {cam}".strip())

    lat = photo.get("gps_lat")
    lon = photo.get("gps_lon")
    if lat is not None and lon is not None:
        parts.append(f"{lat:.4f}, {lon:.4f}")

    return " | ".join(parts)


def compute_meta_hash(search_text):
    return hashlib.md5(search_text.encode()).hexdigest()[:12]


def get_unembedded_photos_sql(db, limit=0, offset=0):
    cur = db.sqlite.cursor()
    sql = """
        SELECT p.photo_id, p.path, p.description, COALESCE(p.manual_date, p.date) as date,
               p.camera_make, p.camera_model, p.gps_lat, p.gps_lon,
               p.faces_present, c.content_hash
        FROM photos p
        JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0
        WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0
        ORDER BY p.path
    """
    if limit > 0:
        sql += f" LIMIT {limit} OFFSET {offset}"
    rows = cur.execute(sql).fetchall()
    cols = ["photo_id", "path", "description", "date",
            "camera_make", "camera_model", "gps_lat", "gps_lon", "faces_present", "content_hash"]
    return [dict(zip(cols, r)) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Generate text embeddings for semantic search")
    parser.add_argument("--limit", type=int, default=0, help="Max photos (0=all)")
    parser.add_argument("--force", action="store_true", help="Re-embed all photos")
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH_SIZE, help="Embedding batch size")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()
    set_flag()
    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("embed")
    except Exception:
        mq = None
    try:
        return _main(db, args, mq)
    finally:
        clear_flag()
        if mq:
            mq.shutdown()


def _main(db, args, mq=None):

    log("Loading personas data...")
    all_personas = db.get_all_personas()
    persona_map = {p["persona_id"]: p for p in all_personas}
    log(f"Loaded {len(all_personas)} personas")

    if args.force:
        all_photos = db.get_all_photos()
        photos = all_photos[:args.limit] if args.limit > 0 else all_photos
    else:
        cur = db.sqlite.cursor()
        total_unembedded = cur.execute(
            "SELECT COUNT(*) FROM photos p JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0 WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0"
        ).fetchone()[0]
        log(f"Found {total_unembedded} photos to embed (SQL query)")
        photos = None

    if not args.force and total_unembedded == 0:
        log("All photos already embedded")
        return 0

    total_to_embed = total_unembedded if not args.force else len(photos)

    PREFIX = str(PHOTO_SHARE_PATH) + "/"

    if mq:
        log("Acquiring GPU...")
        if not mq.acquire_gpu(timeout=60):
            log("GPU занят, embed не может запуститься")
            return 1
        log("GPU acquired")

    log("Starting embed server...")
    embed_server = start_embed_server()
    if not embed_server:
        log("Failed to start embedding server")
        if mq:
            mq.release_gpu()
        return 1
    log("Embed server started, beginning processing...")

    batch_texts = []
    batch_meta = []
    lance_buffer = []
    embedded = 0
    skipped = 0
    t0 = time.time()
    last_log_t = t0
    processed = 0
    fetch_size = 5000
    offset = 0

    try:
        while True:
            if mq and (mq.stopped() or mq.paused()):
                if mq.stopped():
                    break
                if mq.paused():
                    mq.publish_gpu_held(False)
                mq.wait_while_paused()
                if not mq.stopped():
                    mq.publish_gpu_held(True)
                continue
            if stopped():
                break

            if args.force:
                if photos is None:
                    break
                chunk = photos[offset:offset + fetch_size]
                if not chunk:
                    break
            else:
                chunk = get_unembedded_photos_sql(db, limit=fetch_size, offset=0)
                if not chunk:
                    break

            chunk_hashes = [p.get("content_hash", "") for p in chunk if p.get("content_hash")]
            photo_faces = {}
            if chunk_hashes:
                ph = ",".join("?" * len(chunk_hashes))
                face_rows = db.sqlite.execute(
                    f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2 FROM faces WHERE content_hash IN ({ph})",
                    chunk_hashes
                ).fetchall()
                for fr in face_rows:
                    ch = fr[2] or fr[1] or ""
                    if ch:
                        photo_faces.setdefault(ch, []).append({
                            "face_id": fr[0], "photo_id": fr[1], "content_hash": fr[2],
                            "persona_id": fr[3], "bbox_x1": fr[4], "bbox_y1": fr[5],
                            "bbox_x2": fr[6], "bbox_y2": fr[7],
                        })

            for p in chunk:
                if mq and (mq.stopped() or mq.paused()):
                    if mq.stopped():
                        break
                    mq.publish_gpu_held(False)
                    mq.wait_while_paused()
                    if not mq.stopped():
                        mq.publish_gpu_held(True)
                if stopped():
                    break

                path = p.get("path", "")
                content_hash = p.get("content_hash", "")
                faces = photo_faces.get(content_hash, [])

                search_text = build_search_text(p, faces, persona_map)

                if not search_text.strip():
                    skipped += 1
                    cur = db.sqlite.cursor()
                    cur.execute("UPDATE photos SET embedded = 1 WHERE photo_id = ?", (p["photo_id"],))
                    db.sqlite.commit()
                    processed += 1
                    continue

                meta_hash = compute_meta_hash(search_text)

                batch_texts.append(search_text)
                batch_meta.append({
                    "photo_id": p["photo_id"],
                    "path": path,
                    "search_text": search_text,
                    "meta_hash": meta_hash,
                    "embedded_at": datetime.now().isoformat(),
                })

                if len(batch_texts) >= args.batch_size:
                    vectors = encode_batch(batch_texts)
                    for meta, vec in zip(batch_meta, vectors):
                        lance_buffer.append({
                            "photo_id": meta["photo_id"],
                            "search_text": meta["search_text"],
                            "embedding": vec,
                            "meta_hash": meta["meta_hash"],
                            "embedded_at": meta["embedded_at"],
                        })
                        embedded += 1

                    _mark_embedded(db, batch_meta)
                    batch_texts = []
                    batch_meta = []

                processed += 1

                if len(lance_buffer) >= LANCE_FLUSH_SIZE:
                    db.add_photo_embeddings_batch(lance_buffer)
                    lance_buffer = []

                now = time.time()
                if now - last_log_t >= LOG_INTERVAL:
                    elapsed = now - t0
                    rate = embedded / max(elapsed, 1)
                    pct = embedded / max(total_to_embed, 1) * 100
                    elapsed_fmt = _fmt_dur(elapsed)
                    eta_fmt = _fmt_eta(elapsed, pct)
                    log(f"  [{embedded}/{total_to_embed}] {pct:.1f}% | {elapsed_fmt} пройдено, {rate:.0f}/с{eta_fmt}")
                    last_log_t = now

            if args.force:
                offset += fetch_size
            else:
                remaining = cur.execute(
                    "SELECT COUNT(*) FROM photos p JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0 WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0"
                ).fetchone()[0]
                if remaining == 0:
                    break

        if batch_texts:
            vectors = encode_batch(batch_texts)
            for meta, vec in zip(batch_meta, vectors):
                lance_buffer.append({
                    "photo_id": meta["photo_id"],
                    "search_text": meta["search_text"],
                    "embedding": vec,
                    "meta_hash": meta["meta_hash"],
                    "embedded_at": meta["embedded_at"],
                })
                embedded += 1
            _mark_embedded(db, batch_meta)

        if lance_buffer:
            db.add_photo_embeddings_batch(lance_buffer)

        elapsed = time.time() - t0
        log(f"Embedding done: {embedded} встроено, {skipped} пропущено за {_fmt_dur(elapsed)} ({embedded/max(elapsed,1):.0f}/с)")

        try:
            db.photo_embeddings.create_index(
                vector_column_name="embedding",
                index_type="IVF_FLAT",
                metric="cosine",
            )
            log("Vector index created on photo_embeddings")
        except Exception as e:
            log(f"Index creation note: {e}")

        try:
            db.compact_photo_embeddings()
            log("Compacted photo_embeddings LanceDB fragments")
        except Exception as e:
            log(f"Compact note: {e}")

    finally:
        if embed_server:
            embed_server.kill()
            log("llama-server stopped")
        if mq:
            mq.release_gpu()

    return 0


def _mark_embedded(db, records):
    cur = db.sqlite.cursor()
    for r in records:
        cur.execute("UPDATE photos SET embedded = 1 WHERE photo_id = ?", (r["photo_id"],))
    db.sqlite.commit()


if __name__ == "__main__":
    sys.exit(main())
