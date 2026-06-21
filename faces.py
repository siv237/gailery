#!/usr/bin/env python3
"""
faces.py - Detect faces, generate embeddings, cluster into personas.
Processes all photos with faces_done=0 (not yet processed by InsightFace).

Usage:
    python faces.py
    python faces.py --limit 50
    python faces.py --no-cluster
"""

import argparse
import os
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

os.environ['OMP_NUM_THREADS'] = '4'

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import MODELS_DIR, PHOTO_SHARE_PATH, VIDEO_EXTS
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "faces")


def log(msg):
    line = f"[{datetime.now().isoformat()}] [FACES] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


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


def get_undetected_photos(db, limit=0, content_hash=None):
    cur = db.sqlite.cursor()
    sql = """
        SELECT p.photo_id, p.path, p.description, cf.content_hash
        FROM photos p
        JOIN catalog_files cf ON cf.abs_path = p.path
        WHERE cf.faces_done = 0 AND p.deleted = 0 AND (p.media_type IS NULL OR p.media_type != 'video')
          AND cf.is_canonical = 1 AND cf.deleted = 0
          AND NOT EXISTS (
            SELECT 1 FROM faces f
            WHERE f.content_hash = cf.content_hash
               OR f.photo_id = p.path
          )
    """
    params = []
    if content_hash:
        sql += " AND cf.content_hash = ?"
        params.append(content_hash)
    sql += " ORDER BY p.path"
    if limit and limit > 0:
        sql += f" LIMIT {limit}"
    rows = cur.execute(sql, params).fetchall()
    result = []
    for r in rows:
        if not Path(r[1]).exists():
            continue
        result.append({
            "photo_id": r[0],
            "path": r[1],
            "description": r[2],
            "content_hash": r[3],
        })
    return result


def _init_insightface():
    from insightface.app import FaceAnalysis
    cuda_opts = {
        'device_id': 0,
        'arena_extend_strategy': 'kSameAsRequested',
        'cudnn_conv_algo_search': 'EXHAUSTIVE',
        'do_copy_in_default_stream': False,
        'cudnn_conv_use_max_workspace': '1',
        'gpu_mem_limit': 6*1024*1024*1024,
    }
    insightface_root = str(MODELS_DIR / "insightface")
    app = FaceAnalysis(name='buffalo_l', root=insightface_root, providers=[('CUDAExecutionProvider', cuda_opts), 'CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(640, 640))
    log(f"InsightFace loaded on GPU (optimized CUDA provider)")
    return app


def _check_existing_faces(db, photo_id, path):
    existing = db.get_faces_for_photo(photo_id)
    if existing:
        try:
            db.update_catalog_file_by_path(path, faces_done=1)
        except Exception:
            pass
        log(f"  skip {os.path.basename(path)} (faces already exist)")
        return True
    return False


def _load_and_detect(app, img_path):
    from PIL import Image
    import numpy as np
    t_read = time.time()
    img = Image.open(img_path).convert("RGB")
    img_array = np.array(img)
    dt_read = time.time() - t_read

    t_det = time.time()
    log(f"  detecting {os.path.basename(img_path)}...")
    faces = app.get(img_array)
    log(f"  detected {len(faces)} faces")
    dt_det = time.time() - t_det
    return faces, img, dt_read, dt_det


def _handle_detection_error(db, e, photo, content_hash, rel_path, ext):
    log(f"ERROR {os.path.basename(rel_path)}: {e}")
    try:
        if ext in VIDEO_EXTS:
            db.sqlite.execute("UPDATE photos SET media_type = 'video', faces_present = 0, description = NULL WHERE path = ? AND deleted = 0", (rel_path,))
            db.sqlite.commit()
            log(f"  set media_type=video (not an image)")
        else:
            db.sqlite.execute("UPDATE photos SET faces_present = 0, deleted = 1 WHERE path = ? AND deleted = 0", (rel_path,))
            db.sqlite.execute("UPDATE catalog_files SET deleted = 1, deleted_type = 'auto_corrupted' WHERE abs_path = ? AND deleted = 0", (rel_path,))
            db.sqlite.commit()
            log(f"  marked as deleted (corrupted file)")
    except Exception:
        pass


def _process_detected_faces(db, faces, photo_id, path, content_hash):
    import numpy as np
    t_sql = time.time()
    saved = 0
    vectors_batch = []
    face_details = []
    for face in faces:
        if face.embedding is None:
            continue
        embedding = face.embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        bbox = face.bbox.astype(float).tolist()
        face_id = hashlib.md5(f"{path}_{bbox}".encode()).hexdigest()

        face_id, inserted = db.add_face_sqlite_only(
            photo_id=photo_id,
            face_id=face_id,
            bbox=bbox,
            confidence=float(face.det_score) if face.det_score is not None else 0.0,
            persona_id=None,
            content_hash=content_hash,
        )
        if inserted:
            vectors_batch.append({"face_id": face_id, "embedding": embedding.tolist()})
        face_details.append({"bbox": [round(c,1) for c in bbox], "confidence": round(float(face.det_score or 0), 3), "embedding_dim": len(embedding)})
        saved += 1
    dt_sql = time.time() - t_sql
    return saved, vectors_batch, face_details, dt_sql


def _update_photo_flags(db, photo, saved_count, content_hash, rel_path, faces_count):
    t_cleanup = time.time()
    dt_sql_upd = 0.0
    if saved_count > 0:
        try:
            photo = db.get_photo_by_path(rel_path)
            if photo:
                t_upd = time.time()
                db.sqlite.execute("UPDATE photos SET embedded = 0, faces_present = 1 WHERE photo_id = ?", (photo["photo_id"],))
                db.sqlite.commit()
                dt_sql_upd = time.time() - t_upd
        except Exception:
            pass
    elif faces_count == 0:
        try:
            photo = db.get_photo_by_path(rel_path)
            if photo:
                db.update_photo(photo["photo_id"], faces_present=0)
        except Exception:
            pass
    try:
        db.update_catalog_file_by_path(rel_path, faces_done=1)
    except Exception:
        pass
    dt_cleanup = time.time() - t_cleanup
    return dt_sql_upd


def _optimize_lancedb(db):
    try:
        import lancedb as _ldb
        _db = _ldb.connect(str(Path(__file__).parent / "data" / "lancedb"))
        _tbl = _db.open_table('face_vectors')
        from datetime import timedelta as _td
        try:
            _tbl.optimize(cleanup_older_than=_td(seconds=0))
        except Exception:
            try:
                _tbl.compact_files()
                _tbl.cleanup_old_versions()
            except Exception:
                pass
        import os as _os
        _data_dir = str(Path(__file__).parent / "data" / "lancedb" / "face_vectors.lance" / "data")
        _nfrags = len([f for f in _os.listdir(_data_dir) if f.endswith('.lance')])
        log(f"LanceDB optimized: {_tbl.count_rows()} rows, {_nfrags} fragments")
    except Exception as e:
        log(f"LanceDB optimize warning: {e}")


def run_detection(photos):
    from database import DatabaseManager

    app = _init_insightface()

    db = DatabaseManager()
    total_saved = 0
    processed = 0
    t0 = time.time()

    for p in photos:
        path = p.get("path", "")
        content_hash = p.get("content_hash", "")
        if not Path(path).exists():
            continue

        photo_id = str(Path(path).relative_to(PHOTO_SHARE_PATH)) if path.startswith(str(PHOTO_SHARE_PATH) + "/") else path
        if _check_existing_faces(db, photo_id, path):
            continue

        try:
            faces, img, dt_read, dt_det = _load_and_detect(app, path)
        except Exception as e:
            ext = os.path.splitext(path)[1].lower()
            _handle_detection_error(db, e, p, content_hash, path, ext)
            continue

        saved, vectors_batch, face_details, dt_sql = _process_detected_faces(db, faces, photo_id, path, content_hash)

        t_lancedb = time.time()
        if vectors_batch:
            log(f"  lance write {len(vectors_batch)} vectors...")
            db.add_face_vectors_batch(vectors_batch)
            log(f"  lance write done")
        dt_lancedb = time.time() - t_lancedb

        dt_sql_upd = _update_photo_flags(db, None, saved, content_hash, path, len(faces))

        total_saved += saved
        processed += 1

        log(f"[{processed}] {os.path.basename(path)}: {len(faces)} det, {saved} saved | read={dt_read:.2f}s det={dt_det:.2f}s sql={dt_sql:.2f}s lance={dt_lancedb:.2f}s sql_upd={dt_sql_upd:.2f}s")

        try:
            from vlm_log import log_ai_call
            log_ai_call(
                call_type="face_detect",
                photo_path=path,
                content_hash=content_hash,
                photo_id=photo_id,
                input_image={"original_size": list(img.size) if hasattr(img, 'size') else None, "det_size": [640, 640]},
                model_params={"model": "insightface buffalo_l", "provider": "CUDA"},
                output_extra={"faces_detected": len(faces), "faces_saved": saved, "face_details": face_details},
                elapsed_sec=round(dt_det, 3),
                success=1,
            )
        except Exception:
            pass

    elapsed = time.time() - t0
    log(f"Detection done: {processed} photos, {total_saved} faces in {elapsed:.0f}s")

    _optimize_lancedb(db)

    return total_saved


def run_clustering():
    from cluster_personas import cluster_faces
    log("Running DBSCAN clustering (eps=0.4)...")
    cluster_faces(eps=0.4, min_samples=2)
    log("Clustering done")


def main():
    parser = argparse.ArgumentParser(description="Face detection + embedding + clustering")
    parser.add_argument("--limit", type=int, default=0, help="Limit photos (0=all)")
    parser.add_argument("--hash", type=str, default="", help="Process single photo by content_hash")
    parser.add_argument("--no-cluster", action="store_true", help="Skip clustering after detection")
    parser.add_argument("--no-gpu-lock", action="store_true", help="Skip GPU lock acquire (already held by caller)")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()
    set_flag()
    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("faces")
    except Exception:
        mq = None
    try:
        return _main(db, args, mq)
    finally:
        clear_flag()
        if mq:
            mq.shutdown()


def _main(db, args, mq=None):

    if mq and not args.no_gpu_lock:
        if not mq.acquire_gpu(timeout=60):
            log("GPU занят, faces не может запуститься")
            return 1

    photos = get_undetected_photos(db, limit=args.limit, content_hash=args.hash or None)
    if not photos:
        log("No photos need face detection")
        if not args.no_cluster:
            run_clustering()
        if mq:
            mq.release_gpu()
        return 0

    log(f"Found {len(photos)} photos needing face detection")
    run_detection(photos)

    if not args.no_cluster:
        gpu_for_cluster = _try_gpu_for_clustering()
        if gpu_for_cluster:
            log("Clustering on GPU (holding GPU lock)")
            run_clustering()
            if mq:
                mq.release_gpu()
                log("GPU released after GPU clustering")
        else:
            if mq:
                mq.release_gpu()
                log("GPU released, clustering on CPU")
            run_clustering()
    else:
        if mq:
            mq.release_gpu()

    return 0


def _try_gpu_for_clustering():
    try:
        import torch
        if not torch.cuda.is_available():
            return False
        t = torch.zeros(1, device='cuda:0')
        del t
        torch.cuda.empty_cache()
        free_mem, total_mem = torch.cuda.mem_get_info()
        if free_mem < 1 * 1024 * 1024 * 1024:
            log(f"GPU free VRAM too low for clustering: {free_mem/1e9:.1f}GB")
            return False
        return True
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
