#!/usr/bin/env python3
"""
embed.py - Generate text embeddings for semantic search.
Uses Qwen3-Embedding-0.6B via llama-cpp-python (GPU).
Ollama-style: pre-allocated KV slots, no memory_clear, tail-only seq_rm.
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
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import requests

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
import config as app_config
from config import PHOTO_SHARE_PATH
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "embed")

NUM_SEQ = 4
N_CTX = 512
MODEL_PATH = str(Path(__file__).parent / "models" / "gguf" / "Qwen3-Embedding-0.6B-Q8_0.gguf")
SEARCH_TEXT_MAX_LEN = 900
LANCE_FLUSH_SIZE = 2048
LOG_INTERVAL = 10


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


def _extract_description(desc):
    if not desc or not desc.lstrip().startswith("{"):
        return desc
    try:
        obj = json.loads(desc)
        return obj.get("description") or obj.get("text") or desc
    except (json.JSONDecodeError, AttributeError):
        return desc


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

    desc = _extract_description(photo.get("description"))
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

    text = " | ".join(parts)
    if len(text) > SEARCH_TEXT_MAX_LEN:
        text = text[:SEARCH_TEXT_MAX_LEN]
    return text


def compute_meta_hash(search_text):
    return hashlib.md5(search_text.encode()).hexdigest()[:12]


class EmbedEngine:
    _silent_cb = None

    @classmethod
    def _suppress_llama_log(cls):
        import ctypes
        import llama_cpp
        if cls._silent_cb is not None:
            return
        CB = ctypes.CFUNCTYPE(None, ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p)
        cls._silent_cb = CB(lambda level, text, ud: None)
        llama_cpp.llama_log_set(cls._silent_cb, ctypes.c_void_p(0))

    def __init__(self, backend=None):
        if backend:
            self._mode = backend
        else:
            self._mode = getattr(app_config, 'embed_backend', '') or getattr(app_config, 'OLLAMA_MODE', 'local')
        if self._mode == "ollama":
            self._init_ollama()
        else:
            self._init_local()

    def _init_ollama(self):
        url = app_config.OLLAMA_BASE_URL.strip()
        url = url.replace("https://", "http://")
        if not url.startswith("http://"):
            url = "http://" + url
        self._ollama_url = url.rstrip('/')
        self._ollama_model = app_config.OLLAMA_EMBED_MODEL
        self._n_embd = 1024
        log(f"Embed engine: Ollama mode → {self._ollama_url} model={self._ollama_model}")

    def _init_local(self):
        import llama_cpp

        self._suppress_llama_log()
        lc = llama_cpp
        self._lc = lc

        model_enc = MODEL_PATH.encode('utf-8')
        model_params = lc.llama_model_default_params()
        model_params.n_gpu_layers = 99
        self._model = lc.llama_model_load_from_file(model_enc, model_params)
        if not self._model:
            raise RuntimeError(f"Failed to load model {MODEL_PATH}")

        self._n_embd = lc.llama_model_n_embd(self._model)
        self._vocab = lc.llama_model_get_vocab(self._model)

        n_ctx_total = N_CTX * NUM_SEQ
        ctx_params = lc.llama_context_default_params()
        ctx_params.n_ctx = n_ctx_total
        ctx_params.n_batch = n_ctx_total
        ctx_params.n_ubatch = N_CTX
        ctx_params.n_seq_max = NUM_SEQ
        ctx_params.embeddings = True
        ctx_params.kv_unified = True
        ctx_params.flash_attn_type = 1
        ctx_params.n_threads = 4
        ctx_params.n_threads_batch = 4

        self._ctx = lc.llama_init_from_model(self._model, ctx_params)
        if not self._ctx:
            raise RuntimeError("Failed to create context")

        self._mem = lc.llama_get_memory(self._ctx)
        self._batch = lc.llama_batch_init(n_ctx_total, 0, NUM_SEQ)

        log(f"Model loaded, n_embd={self._n_embd}, n_seq_max={NUM_SEQ}, n_ctx_per_seq={N_CTX}")

    def encode(self, texts):
        if self._mode == "ollama":
            return self._encode_ollama(texts)
        return self._encode_local(texts)

    def _encode_ollama(self, texts):
        r = requests.post(
            f"{self._ollama_url}/api/embed",
            json={"model": self._ollama_model, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        items = r.json()["embeddings"]
        all_vecs = []
        for item in items:
            vec = np.array(item, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            all_vecs.append(vec)
        return np.stack(all_vecs, axis=0)

    def _encode_local(self, texts):
        lc = self._lc
        batch = self._batch

        batch.n_tokens = 0
        sizes = []
        for seq_id, text in enumerate(texts):
            lc.llama_memory_seq_rm(self._mem, seq_id, 0, -1)

            buf = (lc.llama_token * N_CTX)()
            n = lc.llama_tokenize(
                self._vocab, text.encode('utf-8'), len(text),
                buf, N_CTX, True, True, False
            )
            n = min(max(n, 0), N_CTX)
            sizes.append(n)
            if n > 0:
                n0 = batch.n_tokens; batch.n_tokens += n
                for t in range(n):
                    j = n0 + t
                    batch.token[j] = buf[t]
                    batch.pos[j] = t
                    batch.seq_id[j][0] = seq_id
                    batch.n_seq_id[j] = 1
                    batch.logits[j] = False
                batch.logits[n0 + n - 1] = True

        ret = lc.llama_decode(self._ctx, batch)
        if ret != 0:
            raise RuntimeError(f"llama_decode returned {ret}")

        all_vecs = []
        for seq_id in range(len(texts)):
            if sizes[seq_id] == 0:
                all_vecs.append(np.zeros(self._n_embd, dtype=np.float32))
                continue

            emb = lc.llama_get_embeddings_seq(self._ctx, seq_id)
            if emb:
                vec = np.array(emb[:self._n_embd], dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                all_vecs.append(vec)
            else:
                ith = sizes[seq_id] - 1
                emb2 = lc.llama_get_embeddings_ith(self._ctx, ith)
                if emb2:
                    vec = np.array(emb2[:self._n_embd], dtype=np.float32)
                    norm = np.linalg.norm(vec)
                    if norm > 0:
                        vec = vec / norm
                    all_vecs.append(vec)
                else:
                    all_vecs.append(np.zeros(self._n_embd, dtype=np.float32))

        return np.stack(all_vecs, axis=0)

    def encode_single(self, text):
        vecs = self.encode([text])
        return vecs[0]

    def cleanup(self):
        if self._mode == "ollama":
            return
        lc = self._lc
        lc.llama_batch_free(self._batch)
        lc.llama_free(self._ctx)
        lc.llama_model_free(self._model)
        log("GPU memory released")


def get_unembedded_photos_sql(db, limit=0, offset=0, content_hash=None):
    cur = db.sqlite.cursor()
    sql = """
        SELECT p.photo_id, p.path, p.description, COALESCE(p.manual_date, p.date) as date,
               p.camera_make, p.camera_model, p.gps_lat, p.gps_lon,
               p.faces_present, c.content_hash
        FROM photos p
        JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0
        WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')
    """
    params = []
    if content_hash:
        sql += " AND c.content_hash = ?"
        params.append(content_hash)
    sql += " ORDER BY p.path"
    if limit > 0:
        sql += f" LIMIT {limit} OFFSET {offset}"
    rows = cur.execute(sql, params).fetchall()
    cols = ["photo_id", "path", "description", "date",
            "camera_make", "camera_model", "gps_lat", "gps_lon", "faces_present", "content_hash"]
    return [dict(zip(cols, r)) for r in rows]


def main():
    parser = argparse.ArgumentParser(description="Generate text embeddings for semantic search")
    parser.add_argument("--limit", type=int, default=0, help="Max photos (0=all)")
    parser.add_argument("--force", action="store_true", help="Re-embed all photos")
    parser.add_argument("--hash", type=str, default="", help="Process single photo by content_hash")
    parser.add_argument("--no-gpu-lock", action="store_true", help="Skip GPU lock acquire (already held by caller)")
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
        content_hash = args.hash or None
        cur = db.sqlite.cursor()
        ch_where = " AND c.content_hash = ?" if content_hash else ""
        ch_params = [content_hash] if content_hash else []
        total_unembedded = cur.execute(
            "SELECT COUNT(*) FROM photos p JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0 WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0" + ch_where, ch_params
        ).fetchone()[0]
        log(f"Found {total_unembedded} photos to embed (SQL query)")
        photos = None

    if not args.force and total_unembedded == 0:
        log("All photos already embedded")
        return 0

    total_to_embed = total_unembedded if not args.force else len(photos)

    if mq and not args.no_gpu_lock:
        log("Acquiring GPU...")
        if not mq.acquire_gpu(timeout=60):
            log("GPU занят, embed не может запуститься")
            return 1
        log("GPU acquired")

    engine = None
    try:
        engine = EmbedEngine()

        lance_buffer = []
        mark_buffer = []
        embedded = 0
        skipped = 0
        t0 = time.time()
        last_log_t = t0
        processed = 0
        fetch_size = 5000
        offset = 0

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
                chunk = get_unembedded_photos_sql(db, limit=fetch_size, offset=0, content_hash=args.hash or None)
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

            # Batch encode: collect texts, encode in groups
            chunk_size = getattr(app_config, 'OLLAMA_EMBED_CHUNK', 64) if engine._mode == "ollama" else NUM_SEQ
            batch_texts = []
            batch_photos = []
            batch_hashes = []

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
                batch_photos.append(p)
                batch_hashes.append(meta_hash)

                try:
                    from vlm_log import log_ai_call
                    log_ai_call(
                        call_type="embed",
                        photo_path=path,
                        content_hash=content_hash,
                        photo_id=p.get("photo_id"),
                        input_extra={"search_text": search_text, "meta_hash": meta_hash},
                        success=1,
                    )
                except Exception:
                    pass

                if len(batch_texts) >= chunk_size:
                    # Encode batch
                    vecs = engine.encode(batch_texts)
                    for j, p2 in enumerate(batch_photos):
                        vec = vecs[j]
                        if j < len(batch_hashes):
                            meta = batch_hashes[j]
                        else:
                            meta = compute_meta_hash(build_search_text(p2, photo_faces.get(p2.get("content_hash",""), []), persona_map))
                        lance_buffer.append({
                            "photo_id": p2["photo_id"],
                            "search_text": batch_texts[j] if j < len(batch_texts) else "",
                            "embedding": vec.tolist(),
                            "meta_hash": meta,
                            "embedded_at": datetime.now().isoformat(),
                        })
                        embedded += 1
                        mark_buffer.append(p2["photo_id"])
                        if len(mark_buffer) >= 64:
                            _mark_embedded_batch(db, mark_buffer)
                            mark_buffer = []
                        processed += 1
                        if len(lance_buffer) >= LANCE_FLUSH_SIZE:
                            db.add_photo_embeddings_batch(lance_buffer)
                            lance_buffer = []

                    batch_texts = []
                    batch_photos = []
                    batch_hashes = []

                now = time.time()
                if now - last_log_t >= LOG_INTERVAL:
                    elapsed = now - t0
                    rate = embedded / max(elapsed, 1)
                    pct = embedded / max(total_to_embed, 1) * 100
                    elapsed_fmt = _fmt_dur(elapsed)
                    eta_fmt = _fmt_eta(elapsed, pct)
                    log(f"  [{embedded}/{total_to_embed}] {pct:.1f}% | {elapsed_fmt} пройдено, {rate:.0f}/с{eta_fmt}")
                    last_log_t = now

            # Encode remaining batch
            if batch_texts:
                vecs = engine.encode(batch_texts)
                for j, p2 in enumerate(batch_photos):
                    vec = vecs[j]
                    meta = batch_hashes[j] if j < len(batch_hashes) else compute_meta_hash(build_search_text(p2, photo_faces.get(p2.get("content_hash",""), []), persona_map))
                    lance_buffer.append({
                        "photo_id": p2["photo_id"],
                        "search_text": batch_texts[j],
                        "embedding": vec.tolist(),
                        "meta_hash": meta,
                        "embedded_at": datetime.now().isoformat(),
                    })
                    embedded += 1
                    mark_buffer.append(p2["photo_id"])
                    if len(mark_buffer) >= 64:
                        _mark_embedded_batch(db, mark_buffer)
                        mark_buffer = []
                    processed += 1
                    if len(lance_buffer) >= LANCE_FLUSH_SIZE:
                        db.add_photo_embeddings_batch(lance_buffer)
                        lance_buffer = []

            if args.force:
                offset += fetch_size
            else:
                remaining = cur.execute(
            "SELECT COUNT(*) FROM photos p JOIN catalog_files c ON p.path = c.abs_path AND c.is_canonical = 1 AND c.deleted = 0 WHERE (p.embedded = 0 OR p.embedded IS NULL) AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')"
                ).fetchone()[0]
                if remaining == 0:
                    break

        if mark_buffer:
            _mark_embedded_batch(db, mark_buffer)

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

    except Exception as e:
        log(f"FATAL: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if engine:
            engine.cleanup()
        if mq:
            mq.release_gpu()

    return 0


def _mark_embedded_batch(db, photo_ids):
    cur = db.sqlite.cursor()
    ph = ",".join("?" * len(photo_ids))
    cur.execute(f"UPDATE photos SET embedded = 1 WHERE photo_id IN ({ph})", photo_ids)
    cur.execute(f"UPDATE catalog_files SET embedded = 1 WHERE abs_path IN (SELECT path FROM photos WHERE photo_id IN ({ph}) AND is_canonical = 1)", photo_ids)
    db.sqlite.commit()


if __name__ == "__main__":
    sys.exit(main())
