"""API endpoints for semantic search"""

from fastapi import APIRouter

import logging
import threading
import time
import config

from .photos import _enrich_photo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/photos", tags=["search"])


def _get_mqtt_api():
    try:
        from mqtt_client import create_api_mqtt
        from main import _get_api_mqtt
        return _get_api_mqtt()
    except Exception:
        return None


_embed_engine = None
_embed_lock = None


def _get_embed_engine():
    global _embed_engine, _embed_lock
    if _embed_lock is None:
        _embed_lock = threading.Lock()
    with _embed_lock:
        if _embed_engine is None:
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from embed import EmbedEngine
            be = config.search_backend or config.OLLAMA_MODE
            _embed_engine = EmbedEngine(backend=be)
            logger.info(f"[SEMSEARCH] EmbedEngine loaded, backend={be}")
        return _embed_engine


def _unload_embed_engine():
    global _embed_engine
    if _embed_engine is not None:
        _embed_engine.cleanup()
        _embed_engine = None
        logger.info("[SEMSEARCH] EmbedEngine unloaded, GPU memory released")


def _embed_query(query_text):
    engine = _get_embed_engine()
    vec = engine.encode_single(query_text)
    return vec.tolist()


@router.get("/semantic_search")
async def semantic_search(q: str = "", limit: int = 20, threshold: float = 1.0):
    from database import get_db

    if not q:
        return {"total": 0, "photos": [], "query": q}

    logger.info(f"[SEMSEARCH] Start: q={q!r} threshold={threshold} limit={limit}")

    db = get_db()

    task = "Retrieve photographs matching the description, including people, places, events, and scenes"
    query_text = "Instruct: " + task + "\nQuery: " + q

    mq = _get_mqtt_api()
    gpu_acquired = False
    gpu_t0 = time.time()
    if mq and _embed_engine is None:
        gpu_acquired = mq.request_gpu_gentle(worker_name="semantic_search", timeout=30)
        if gpu_acquired:
            logger.info(f"[SEMSEARCH] GPU acquired gently in {time.time()-gpu_t0:.1f}s")
        else:
            logger.warning("[SEMSEARCH] GPU busy, search unavailable now")
            return {"total": 0, "photos": [], "query": q, "error": "GPU busy, try again later"}
    else:
        logger.warning("[SEMSEARCH] No MQTT, proceeding without GPU lock")

    q_emb = None
    try:
        q_emb = _embed_query(query_text)
        logger.info(f"[SEMSEARCH] Got embedding size={len(q_emb)}")
    except Exception as e:
        logger.error(f"[SEMSEARCH] Error getting embedding: {e}")
        _unload_embed_engine()
        return {"total": 0, "photos": [], "query": q, "error": str(e)}
    finally:
        if mq and gpu_acquired:
            mq.release_gpu_from_api()
            logger.info("[SEMSEARCH] GPU released via MQTT")

    if q_emb is None:
        logger.error("[SEMSEARCH] No embedding obtained")
        return {"total": 0, "photos": [], "query": q, "error": "no embedding"}

    logger.info(f"[SEMSEARCH] Searching LanceDB with threshold={threshold}")
    try:
        results = db.search_photo_embeddings(q_emb, limit=limit * 2)
    except RuntimeError as e:
        err_msg = str(e)
        logger.error(f"[SEMSEARCH] LanceDB RuntimeError: {err_msg}")
        if "open files" in err_msg.lower() or "Too many" in err_msg:
            try:
                db._open_vector_tables()
                logger.info("[SEMSEARCH] Reopened LanceDB tables after FD exhaustion, retrying search")
                results = db.search_photo_embeddings(q_emb, limit=limit * 2)
            except Exception as e2:
                logger.error(f"[SEMSEARCH] Retry after reopen also failed: {e2}")
                return {"total": 0, "photos": [], "query": q, "error": "LanceDB unavailable (too many open files), please try again"}
        else:
            return {"total": 0, "photos": [], "query": q, "error": f"LanceDB error: {err_msg[:200]}"}
    except Exception as e:
        logger.error(f"[SEMSEARCH] LanceDB error: {e}")
        return {"total": 0, "photos": [], "query": q, "error": str(e)[:200]}
    logger.info(f"[SEMSEARCH] LanceDB returned {len(results)} raw results")
    if results:
        top_dist = results[0].get("_distance", results[0].get("_relevance_score", "?"))
        logger.info(f"[SEMSEARCH] Top distance={top_dist}")

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
        out_list.append((photo, score))
        if len(out_list) >= limit:
            break

    hashes = [p.get("content_hash", "") for p, _ in out_list if p.get("content_hash")]
    persona_ids_needed = set()
    photo_faces = {}
    if hashes:
        ph = ",".join("?" * len(hashes))
        face_rows = db.sqlite.execute(
            f"SELECT face_id, photo_id, content_hash, persona_id, bbox_x1, bbox_y1, bbox_x2, bbox_y2, confidence FROM faces WHERE content_hash IN ({ph})",
            hashes
        ).fetchall()
        face_cols = ["face_id", "photo_id", "content_hash", "persona_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "confidence"]
        for fr in face_rows:
            fd = dict(zip(face_cols, fr))
            ch = fd.get("content_hash") or ""
            if ch:
                photo_faces.setdefault(ch, []).append(fd)
            pid_legacy = fd.get("photo_id", "")
            if pid_legacy:
                photo_faces.setdefault(pid_legacy, []).append(fd)
            if fd.get("persona_id"):
                persona_ids_needed.add(fd["persona_id"])

    persona_map = {}
    if persona_ids_needed:
        pids = list(persona_ids_needed)
        pid_ph = ",".join("?" * len(pids))
        for pr in db.sqlite.execute(f"SELECT persona_id, name, display_name, comment FROM personas WHERE persona_id IN ({pid_ph})", pids).fetchall():
            persona_map[pr[0]] = {"persona_id": pr[0], "name": pr[1], "display_name": pr[2], "comment": pr[3]}

    enriched_list = []
    for photo, score in out_list:
        ep = _enrich_photo(photo, photo_faces, persona_map, include_created=True, include_score=True, score=score)
        hash_val = db.sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE abs_path = ? AND content_hash IS NOT NULL",
            (photo.get("path", ""),)
        ).fetchone()
        if hash_val:
            ep["duplicate_paths"] = db.get_duplicate_paths(hash_val[0])
        else:
            ep["duplicate_paths"] = []
        enriched_list.append(ep)

    logger.info(f"[SEMSEARCH] Final: {len(enriched_list)} results (skipped: no_photo={skipped_no_photo}, not_embedded={skipped_not_embedded}, threshold={skipped_threshold})")
    return {"total": len(enriched_list), "photos": enriched_list, "query": q}
