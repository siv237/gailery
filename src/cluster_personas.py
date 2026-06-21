#!/usr/bin/env python3
"""
cluster_personas.py - Incremental face clustering into personas.

Strategy:
  1. Existing persona assignments are NEVER changed.
  2. New faces (no persona_id) are matched to existing personas by centroid.
  3. Remaining unmatched faces are DBSCAN-clustered among themselves.
  4. New clusters get unique IDs that never collide with old ones.
  5. Noise faces (DBSCAN -1) keep persona_id=NULL (no spam personas).

GPU acceleration:
  - Centroid matching: batch cosine distance via PyTorch matrix multiply
  - DBSCAN: batch pairwise cosine distances on GPU → sparse adjacency → BFS DBSCAN
  - Auto-detect GPU, fall back to CPU sklearn if unavailable
"""

import sys
import time
import logging
import numpy as np
from datetime import datetime
from sklearn.cluster import DBSCAN
from sklearn.metrics.pairwise import cosine_distances

from database import DatabaseManager
from config import LOG_FILE, PHOTO_SHARE_PATH

def _log(msg):
    from datetime import datetime
    line = f"[{datetime.now().isoformat()}] [CLUSTER] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [CLUSTER] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

MATCH_THRESHOLD = 0.4
DBSCAN_EPS = 0.4
DBSCAN_MIN_SAMPLES = 2


def _try_gpu():
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        t = torch.zeros(1, device='cuda:0')
        del t
        torch.cuda.empty_cache()
        return torch.device('cuda:0')
    except Exception:
        return None


def _gpu_match_to_centroids(new_faces, centroids, match_threshold, device):
    import torch

    centroid_ids = list(centroids.keys())
    if not centroid_ids:
        return {}, []

    centroid_matrix = np.array([centroids[pid] for pid in centroid_ids], dtype=np.float32)
    new_embs = np.array([f["embedding"] for f in new_faces], dtype=np.float32)

    new_t = torch.tensor(new_embs, device=device)
    cent_t = torch.tensor(centroid_matrix, device=device)

    new_t = new_t / new_t.norm(dim=1, keepdim=True).clamp(min=1e-8)
    cent_t = cent_t / cent_t.norm(dim=1, keepdim=True).clamp(min=1e-8)

    batch_size = 4000
    N = len(new_faces)
    match_map = {}

    for start in range(0, N, batch_size):
        end = min(start + batch_size, N)
        sims = torch.mm(new_t[start:end], cent_t.T)
        dists = 1.0 - sims
        min_dists, min_idx = dists.min(dim=1)
        mask = min_dists < match_threshold

        for local_i in mask.nonzero(as_tuple=True)[0].cpu().numpy():
            gi = int(start + local_i)
            match_map[gi] = (
                centroid_ids[min_idx[local_i].item()],
                min_dists[local_i].item(),
            )

    del new_t, cent_t
    torch.cuda.empty_cache()

    unmatched_indices = [i for i in range(N) if i not in match_map]
    return match_map, unmatched_indices


def _gpu_dbscan(embeddings_np, eps, min_samples, device):
    import torch
    from scipy.sparse import csr_matrix

    N, D = embeddings_np.shape
    _log(f"GPU DBSCAN: {N} faces, {D} dims, eps={eps}, min_samples={min_samples}")

    emb_t = torch.tensor(embeddings_np, dtype=torch.float32, device=device)
    norms = emb_t.norm(dim=1, keepdim=True).clamp(min=1e-8)
    emb_t = emb_t / norms

    batch_size = min(2000, N)
    rows_list = []
    cols_list = []

    for start in range(0, N, batch_size):
        end = min(start + batch_size, N)
        sims = torch.mm(emb_t[start:end], emb_t.T)
        dists = 1.0 - sims
        mask = (dists < eps)

        rows, cols = mask.nonzero(as_tuple=True)
        rows_global = rows + start
        keep = rows_global <= cols
        rows_list.append(rows_global[keep].cpu().numpy())
        cols_list.append(cols[keep].cpu().numpy())

        del sims, dists, mask
        if start > 0 and start % 10000 == 0:
            torch.cuda.empty_cache()

    del emb_t
    torch.cuda.empty_cache()

    rows_np = np.concatenate(rows_list) if rows_list else np.array([], dtype=np.int64)
    cols_np = np.concatenate(cols_list) if cols_list else np.array([], dtype=np.int64)

    upper = csr_matrix(
        (np.ones(len(rows_np), dtype=np.int8), (rows_np, cols_np)),
        shape=(N, N),
    )
    adj = upper + upper.T
    adj.data = np.minimum(adj.data, 1)

    _log(f"Sparse adjacency: {adj.nnz} non-zeros ({adj.nnz / max(N * N, 1) * 100:.3f}% density)")

    labels = _sparse_dbscan(adj, min_samples)
    return labels


def _sparse_dbscan(adj_csr, min_samples):
    from collections import deque

    N = adj_csr.shape[0]
    degrees = np.array(adj_csr.sum(axis=1)).flatten() - 1
    core_mask = degrees >= min_samples - 1

    _log(f"Core points: {core_mask.sum()}/{N} (degree>={min_samples})")

    labels = np.full(N, -1, dtype=np.int32)
    cluster_id = 0

    for i in range(N):
        if not core_mask[i] or labels[i] != -1:
            continue
        queue = deque([i])
        labels[i] = cluster_id
        while queue:
            current = queue.popleft()
            for neighbor in adj_csr[current].indices:
                if labels[neighbor] != -1:
                    continue
                labels[neighbor] = cluster_id
                if core_mask[neighbor]:
                    queue.append(neighbor)
        cluster_id += 1

    return labels


def compute_centroids(assigned_faces):
    persona_embeddings = {}
    for f in assigned_faces:
        pid = f.get("persona_id")
        if not pid:
            continue
        persona_embeddings.setdefault(pid, []).append(np.array(f["embedding"]))

    centroids = {}
    for pid, embs in persona_embeddings.items():
        arr = np.array(embs)
        c = arr.mean(axis=0)
        norm = np.linalg.norm(c)
        if norm > 0:
            centroids[pid] = c / norm
        else:
            centroids[pid] = c
    return centroids


def next_persona_id(db):
    personas = db.get_all_personas()
    max_num = 0
    for p in personas:
        pid = p["persona_id"]
        if pid.startswith("persona_"):
            try:
                n = int(pid.split("_")[1])
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
        elif pid.startswith("cluster_"):
            try:
                n = int(pid.split("_")[1])
                if n > max_num:
                    max_num = n
            except ValueError:
                pass
    return max_num + 1


def _batch_commit(db, faces_to_update, photos_to_reset):
    if not faces_to_update and not photos_to_reset:
        return

    if faces_to_update:
        db.sqlite.executemany(
            "UPDATE faces SET persona_id = ? WHERE face_id = ?",
            faces_to_update
        )

    if photos_to_reset:
        photo_list = list(photos_to_reset)
        id_list = ", ".join(f"'{pid}'" for pid in photo_list)
        try:
            db.photo_embeddings.delete(f"photo_id IN ({id_list})")
        except Exception as e:
            _log(f"LanceDB batch delete warning: {e}")

        db.sqlite.executemany(
            "UPDATE photos SET embedded = 0 WHERE photo_id = ?",
            [(pid,) for pid in photo_list]
        )

    db.sqlite.commit()

    try:
        db.compact_photo_embeddings()
    except Exception as e:
        _log(f"LanceDB compact warning: {e}")


def _build_path_to_uuid_map(db):
    path_to_uuid = {}
    prefix = str(PHOTO_SHARE_PATH) + "/"
    for row in db.sqlite.execute("SELECT photo_id, path FROM photos").fetchall():
        pid, path = row[0], row[1]
        path_to_uuid[path] = pid
        if path.startswith(prefix):
            rel = path[len(prefix):]
            path_to_uuid[rel] = pid
    return path_to_uuid


def _match_to_existing_personas(assigned_faces, new_faces, centroids, match_threshold, device, path_to_uuid):
    matched = 0
    unmatched = []
    faces_to_update = []
    photos_to_reset = set()

    if not centroids:
        return [], set(), list(new_faces), 0

    centroid_ids = list(centroids.keys())

    if device:
        t0 = time.time()
        _log(f"GPU centroid matching: {len(new_faces)} faces vs {len(centroids)} centroids")
        match_map, unmatched_indices = _gpu_match_to_centroids(new_faces, centroids, match_threshold, device)
        for gi, (pid, dist) in match_map.items():
            f = new_faces[gi]
            faces_to_update.append((pid, f["face_id"]))
            photo_uuid = path_to_uuid.get(f.get("photo_id"))
            if photo_uuid: photos_to_reset.add(photo_uuid)
            matched += 1
            if matched <= 20 or matched % 2000 == 0:
                _log(f"Matched {f['face_id'][:12]}... → {pid} (dist={dist:.3f})")
        unmatched = [new_faces[i] for i in unmatched_indices]
        _log(f"GPU matched {matched} faces in {time.time()-t0:.1f}s, {len(unmatched)} unmatched")
    else:
        centroid_matrix = np.array([centroids[pid] for pid in centroid_ids])
        for f in new_faces:
            emb = np.array(f["embedding"]).reshape(1, -1)
            dists = cosine_distances(emb, centroid_matrix)[0]
            min_idx = np.argmin(dists)
            min_dist = dists[min_idx]
            if min_dist < match_threshold:
                best_pid = centroid_ids[min_idx]
                faces_to_update.append((best_pid, f["face_id"]))
                photo_uuid = path_to_uuid.get(f.get("photo_id"))
                if photo_uuid: photos_to_reset.add(photo_uuid)
                matched += 1
                _log(f"Matched {f['face_id'][:12]}... → {best_pid} (dist={min_dist:.3f})")
            else:
                unmatched.append(f)
        _log(f"Matched {matched} faces to existing personas, {len(unmatched)} unmatched")

    return faces_to_update, photos_to_reset, unmatched, matched


def _run_dbscan(embeddings, eps, min_samples, device):
    if device:
        t0 = time.time()
        try:
            labels = _gpu_dbscan(embeddings, eps, min_samples, device)
            _log(f"GPU DBSCAN completed in {time.time()-t0:.1f}s")
            return labels, device
        except RuntimeError as e:
            if "out of memory" in str(e).lower() or "CUDA" in str(e):
                _log(f"GPU OOM during DBSCAN, falling back to CPU: {e}")
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                device = None
            else:
                raise
    _log(f"CPU DBSCAN on {len(embeddings)} faces (eps={eps})")
    t0 = time.time()
    labels = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine").fit_predict(embeddings)
    _log(f"CPU DBSCAN completed in {time.time()-t0:.1f}s")
    return labels, device


def _create_new_personas(db, labels):
    counter = next_persona_id(db)
    cluster_to_persona = {}
    persona_rows = []
    for cluster_id in sorted(set(labels)):
        if cluster_id == -1:
            continue
        persona_id = f"cluster_{counter}"
        counter += 1
        cluster_to_persona[cluster_id] = persona_id
        persona_rows.append((persona_id, persona_id, None, None, datetime.now().isoformat()))
    if persona_rows:
        db.sqlite.executemany(
            "INSERT OR IGNORE INTO personas (persona_id,name,display_name,comment,created_at) VALUES (?,?,?,?,?)",
            persona_rows,
        )
        db.sqlite.commit()
    return cluster_to_persona


def cluster_faces(eps=DBSCAN_EPS, min_samples=DBSCAN_MIN_SAMPLES, match_threshold=MATCH_THRESHOLD):
    t_total = time.time()
    db = DatabaseManager()

    t0 = time.time()
    faces = db.get_all_face_embeddings()
    _log(f"Loaded {len(faces)} face embeddings in {time.time()-t0:.1f}s")

    faces = sorted(faces, key=lambda f: f["face_id"])
    _log(f"Found {len(faces)} faces total")

    if not faces:
        return

    assigned_faces = [f for f in faces if f.get("persona_id")]
    new_faces = [f for f in faces if not f.get("persona_id")]
    _log(f"Already assigned: {len(assigned_faces)}, New: {len(new_faces)}")

    if not new_faces:
        _log("No new faces to cluster")
        return

    t0 = time.time()
    path_to_uuid = _build_path_to_uuid_map(db)
    _log(f"Path mapping built in {time.time()-t0:.1f}s")

    t0 = time.time()
    centroids = compute_centroids(assigned_faces)
    _log(f"Computed {len(centroids)} centroids in {time.time()-t0:.1f}s")

    device = _try_gpu()

    faces_to_update, photos_to_reset, unmatched, matched = _match_to_existing_personas(
        assigned_faces, new_faces, centroids, match_threshold, device, path_to_uuid
    )

    if not unmatched:
        _log("All faces assigned")
        _batch_commit(db, faces_to_update, photos_to_reset)
        _log(f"Total time: {time.time()-t_total:.1f}s")
        return

    embeddings = np.array([f["embedding"] for f in unmatched], dtype=np.float32)

    labels, device = _run_dbscan(embeddings, eps, min_samples, device)

    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    noise_count = list(labels).count(-1)
    _log(f"DBSCAN found {n_clusters} new clusters, {noise_count} noise faces")

    cluster_to_persona = _create_new_personas(db, labels)

    t0 = time.time()
    for i, f in enumerate(unmatched):
        cluster_id = labels[i]
        if cluster_id == -1:
            continue
        persona_id = cluster_to_persona[cluster_id]
        faces_to_update.append((persona_id, f["face_id"]))
        photo_uuid = path_to_uuid.get(f.get("photo_id"))
        if photo_uuid:
            photos_to_reset.add(photo_uuid)

    _batch_commit(db, faces_to_update, photos_to_reset)
    clustered_count = len([l for l in labels if l != -1])
    _log(f"Clustering complete. {matched} matched + {clustered_count} clustered + {noise_count} noise = {len(new_faces)} total ({time.time()-t_total:.1f}s)")


if __name__ == "__main__":
    eps = float(sys.argv[1]) if len(sys.argv) > 1 else DBSCAN_EPS
    min_samples = int(sys.argv[2]) if len(sys.argv) > 2 else DBSCAN_MIN_SAMPLES
    cluster_faces(eps=eps, min_samples=min_samples)
