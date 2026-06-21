#!/usr/bin/env python3
"""
scan_catalog.py - Scan photo directories and populate the file catalog.

Фаза A: Сбор путей (БЫСТРО, без хешей) — catalog_files с content_hash=NULL
Фаза B: Хеширование батчами (--hash --limit N) — по N файлов за раз
Фаза C: Дедупликация + ingest (--dedup-ingest) — mark_canonical + add to photos

Usage:
    python scan_catalog.py --scan              # Фаза A: сбор путей (быстро)
    python scan_catalog.py --hash --limit 500  # Фаза B: хеширование батчами
    python scan_catalog.py --dedup-ingest      # Фаза C: дедупликация + ingest
    python scan_catalog.py --add /path         # зарегистрировать корень
    python scan_catalog.py --stats             # статистика
"""

import argparse
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import VIDEO_EXTS

LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".raw", ".cr2", ".nef", ".arw", ".dng", ".heic"} | VIDEO_EXTS


def compute_file_hash(path, chunk_size=65536):
    import xxhash
    h = xxhash.xxh128()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def log(msg):
    line = f"[{datetime.now().isoformat()}] [CATALOG] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_db():
    from database import DatabaseManager
    return DatabaseManager()


def add_root(db, root_path, alias=""):
    root_path = str(Path(root_path).resolve())
    existing_roots = db.get_catalog_roots()
    existing = [r for r in existing_roots if r.get("root_path") == root_path]
    if existing:
        log(f"Root already registered: {root_path}")
        return existing[0]["root_id"]

    root_id = str(uuid.uuid4())
    db.add_catalog_root(root_id, root_path, alias=alias or Path(root_path).name)
    log(f"Registered root: {root_path} (id={root_id})")
    return root_id


def _load_existing_files(db, root_id):
    cur = db.sqlite.cursor()
    rows = cur.execute(
        "SELECT rel_path, abs_path, file_id, content_hash, modified, size, deleted FROM catalog_files WHERE root_id = ?",
        (root_id,)
    ).fetchall()
    existing_map = {}
    for r in rows:
        existing_map[r[0]] = {
            "rel_path": r[0], "abs_path": r[1], "file_id": r[2],
            "content_hash": r[3], "modified": r[4], "size": r[5], "deleted": r[6],
        }
    return existing_map


def _process_existing_file(db, old, abs_path, rel_path, ext, file_size, mtime_str):
    if file_size == 0:
        if not old.get("deleted"):
            db.update_catalog_file(old["file_id"], deleted=1, deleted_type='auto_empty')
        return 'empty'
    if old.get("deleted"):
        db.update_catalog_file(old["file_id"], deleted=0, deleted_type=None, abs_path=abs_path, size=file_size, modified=mtime_str)
        return 'restored'
    if str(old.get("modified", "")) != mtime_str or old.get("size", 0) != file_size:
        db.update_catalog_file(old["file_id"], abs_path=abs_path, parent_dir=str(Path(rel_path).parent), ext=ext, size=file_size, modified=mtime_str, content_hash=None)
        return 'changed'
    return None


def _create_new_file_record(root_id, rel_path, abs_path, ext, file_size, mtime_str):
    return {
        "file_id": str(uuid.uuid4()),
        "root_id": root_id,
        "rel_path": rel_path,
        "abs_path": abs_path,
        "parent_dir": str(Path(rel_path).parent),
        "ext": ext,
        "size": file_size,
        "modified": mtime_str,
        "content_hash": None,
        "ingested": False,
        "described": False,
        "exif_done": False,
        "faces_done": False,
    }


def _mark_missing_files(db, existing_map, kept_rel):
    deleted_rel = set(existing_map.keys()) - kept_rel
    deleted_count = 0
    for rel in deleted_rel:
        old = existing_map[rel]
        if not old.get("deleted"):
            db.update_catalog_file(old["file_id"], deleted=1, deleted_type='auto_missing')
            pid_row = db.sqlite.execute("SELECT photo_id FROM photos WHERE path = ? AND deleted = 0", (old["abs_path"],)).fetchone()
            if pid_row:
                db.sqlite.execute("UPDATE photos SET deleted = 1 WHERE photo_id = ?", (pid_row[0],))
                db.sqlite.commit()
            deleted_count += 1
    if deleted_count:
        log(f"Marked {deleted_count} files as deleted (auto_missing)")
    return deleted_count


def scan_root(db, root_id, mq=None):
    """Фаза A: Сбор путей — БЫСТРО, без хеширования."""
    root = db.get_catalog_root(root_id)
    if not root:
        log(f"Root not found: {root_id}")
        return
    root_path = root["root_path"]
    scanned_at_str = root.get("scanned_at")
    scanned_at_ts = 0
    if scanned_at_str:
        try:
            scanned_at_ts = datetime.fromisoformat(scanned_at_str).timestamp()
        except Exception:
            pass

    if not Path(root_path).exists():
        log(f"Root path does not exist: {root_path}")
        return

    log(f"SCAN (paths only): {root_path}")

    existing_map = _load_existing_files(db, root_id)
    existing_rel = set(existing_map.keys())

    new_files = []
    kept_rel = set()
    changed_count = 0
    restored_count = 0
    scan_complete = False

    t0 = time.time()
    scanned = 0
    skipped_dirs = 0

    try:
        for dirpath, dirnames, filenames in os.walk(root_path):
            try:
                dir_stat = os.stat(dirpath)
                dir_mtime = dir_stat.st_mtime
            except OSError:
                dirnames.clear()
                continue

            if scanned_at_ts and dir_mtime < scanned_at_ts and dirpath != root_path:
                all_in_dir_are_old = True
                for fn in filenames:
                    ext = Path(fn).suffix.lower()
                    if ext not in SUPPORTED_EXTS:
                        continue
                    rel_path = os.path.relpath(os.path.join(dirpath, fn), root_path)
                    kept_rel.add(rel_path)
                    if rel_path not in existing_rel:
                        all_in_dir_are_old = False
                if all_in_dir_are_old:
                    skipped_dirs += 1
                    continue

            for fn in filenames:
                ext = Path(fn).suffix.lower()
                if ext not in SUPPORTED_EXTS:
                    continue
                abs_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(abs_path, root_path)
                kept_rel.add(rel_path)
                scanned += 1
                if scanned % 100 == 0:
                    elapsed = time.time() - t0
                    progress_msg = f"Scanned {scanned} files, new={len(new_files)}, changed={changed_count}, restored={restored_count}, dirs_skipped={skipped_dirs}, elapsed={elapsed:.1f}s"
                    log(progress_msg)
                    if mq:
                        try: mq.publish_progress(scanned, 0, {"new": len(new_files), "changed": changed_count, "restored": restored_count, "elapsed": round(elapsed, 1)})
                        except: pass

                try:
                    stat = os.stat(abs_path)
                    file_size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    continue

                mtime_str = str(mtime)

                if rel_path in existing_map:
                    result = _process_existing_file(db, existing_map[rel_path], abs_path, rel_path, ext, file_size, mtime_str)
                    if result == 'restored':
                        restored_count += 1
                    elif result == 'changed':
                        changed_count += 1
                else:
                    if file_size > 0:
                        new_files.append(_create_new_file_record(root_id, rel_path, abs_path, ext, file_size, mtime_str))

                if len(new_files) >= 200:
                    db.add_catalog_files_batch(new_files)
                    log(f"  Flushed {len(new_files)} new files to DB")
                    new_files = []

        scan_complete = True
    except Exception as e:
        log(f"Scan ABORTED: {e}")
        scan_complete = False

    if new_files:
        db.add_catalog_files_batch(new_files)
        log(f"  Flushed {len(new_files)} new files to DB")

    deleted_count = 0
    if scan_complete:
        deleted_count = _mark_missing_files(db, existing_map, kept_rel)
    else:
        log(f"Scan incomplete, skipping soft-delete step")

    if scan_complete:
        db.update_catalog_root(root_id, scanned_at=datetime.now().isoformat())

    elapsed = time.time() - t0
    new_count = len(kept_rel - existing_rel)
    del_str = f"{deleted_count} deleted" if scan_complete else "NO delete (scan incomplete)"
    log(f"Scan done in {elapsed:.1f}s: {scanned} scanned, {skipped_dirs} dirs skipped, {new_count} new, {changed_count} changed, {del_str}, {restored_count} restored")


def hash_batch(db, limit=500, mq=None):
    """Фаза B: Хеширование батчами — только N файлов за раз."""
    where = "content_hash IS NULL AND size > 0 AND deleted = 0"
    files = db.get_catalog_files(where=where)
    if not files:
        log("Hash: все файлы уже имеют хеш")
        return 0

    if limit > 0:
        files = files[:limit]

    total_unhashed = db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE content_hash IS NULL AND size > 0 AND deleted = 0").fetchone()[0]

    log(f"Hash: хешируем {len(files)} файлов (осталось без хеша: {total_unhashed})")
    t0 = time.time()
    done = 0
    batch = []
    for f in files:
        abs_path = f.get("abs_path", "")
        if not Path(abs_path).exists():
            continue
        try:
            h = compute_file_hash(abs_path)
            batch.append((h, f["file_id"]))
        except Exception:
            pass
        done += 1
        if len(batch) >= 200:
            db.sqlite.executemany("UPDATE catalog_files SET content_hash = ? WHERE file_id = ?", batch)
            db.sqlite.commit()
            batch = []
            elapsed = time.time() - t0
            log(f"  Hashed {done}/{len(files)} ({elapsed:.1f}s, {done/max(elapsed,1):.0f}/s)")
            if mq:
                try: mq.publish_progress(done, len(files), {"speed": f"{done/max(elapsed,1):.0f}/s"})
                except: pass

    if batch:
        db.sqlite.executemany("UPDATE catalog_files SET content_hash = ? WHERE file_id = ?", batch)
        db.sqlite.commit()

    elapsed = time.time() - t0
    log(f"Hash done: {done} files in {elapsed:.1f}s ({done/max(elapsed,1):.0f}/s)")
    return done


def dedup_ingest(db, root_id=None, mq=None):
    """Фаза C: Дедупликация + наполнение photos."""
    log("Dedup+Ingest: определяем canonical, добавляем в photos")

    groups, copies = db.mark_canonical_duplicates()
    db.invalidate_canonical_cache()
    if copies > 0:
        log(f"  Marked {copies} duplicate files (is_canonical=0) across {groups} groups")

    if root_id:
        _ingest_new_canonical(db, root_id)
    else:
        for root in db.get_catalog_roots():
            if root.get("enabled", 1):
                _ingest_new_canonical(db, root["root_id"])

    _cleanup_noncanonical_photos(db)

    canonical_hashed = db.sqlite.execute("SELECT COUNT(*) FROM catalog_files WHERE is_canonical=1 AND content_hash IS NOT NULL AND deleted=0").fetchone()[0]
    photos_count = db.sqlite.execute("SELECT COUNT(*) FROM photos WHERE deleted=0").fetchone()[0]
    log(f"Dedup+Ingest done: {canonical_hashed} canonical+hashed, {photos_count} in photos")


def _ingest_new_canonical(db, root_id):
    cur = db.sqlite.cursor()

    restored = cur.execute(
        "UPDATE photos SET deleted = 0 WHERE deleted = 1 AND path IN ("
        "SELECT cf.abs_path FROM catalog_files cf WHERE cf.is_canonical = 1 AND cf.deleted = 0 AND cf.root_id = ?"
        ")",
        (root_id,)
    ).rowcount
    if restored > 0:
        db.sqlite.commit()
        cur.execute(
            "UPDATE catalog_files SET ingested = 1 WHERE is_canonical = 1 AND deleted = 0 AND root_id = ? AND abs_path IN ("
            "SELECT path FROM photos WHERE deleted = 0)",
            (root_id,)
        )
        db.sqlite.commit()
        log(f"Restored {restored} canonical photos that were marked deleted")

    rows = cur.execute(
        "SELECT cf.abs_path, cf.root_id FROM catalog_files cf "
        "WHERE cf.is_canonical = 1 AND cf.ingested = 0 AND cf.deleted = 0 AND cf.root_id = ? AND cf.content_hash IS NOT NULL",
        (root_id,)
    ).fetchall()
    if not rows:
        return

    import uuid as _uuid
    batch = []
    file_ids = []
    for abs_path, rid in rows:
        ext = os.path.splitext(abs_path)[1].lower()
        is_video = ext in VIDEO_EXTS
        batch.append({
            "photo_id": str(_uuid.uuid4()),
            "path": abs_path,
            "thumbnail_path": "",
            "date": None,
            "gps_lat": None,
            "gps_lon": None,
            "camera_make": None,
            "camera_model": None,
            "created_at": datetime.now().isoformat(),
            "description": None,
            "faces_present": False,
            "date_conflict": 0,
            "root_id": rid,
            "media_type": "video" if is_video else "photo",
            "duration_seconds": 0,
        })
        fid_row = cur.execute("SELECT file_id FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 AND deleted = 0 AND content_hash IS NOT NULL", (abs_path,)).fetchone()
        if fid_row:
            file_ids.append(fid_row[0])

    db.add_photos_batch(batch)
    for fid in file_ids:
        db.update_catalog_file(fid, ingested=1)
    video_fids = []
    for abs_path, rid in rows:
        ext = os.path.splitext(abs_path)[1].lower()
        if ext in VIDEO_EXTS:
            fid_row = cur.execute("SELECT file_id FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 AND deleted = 0", (abs_path,)).fetchone()
            if fid_row:
                video_fids.append(fid_row[0])
    if video_fids:
        cur.executemany("UPDATE catalog_files SET faces_done = 1 WHERE file_id = ?", [(fid,) for fid in video_fids])
        db.sqlite.commit()
        log(f"Set faces_done=1 for {len(video_fids)} video files (N/A for video)")

    log(f"Ingested {len(batch)} new canonical files into photos")


def _cleanup_noncanonical_photos(db):
    db.sqlite.execute(
        "UPDATE photos SET deleted = 1 "
        "WHERE deleted = 0 AND path IN ("
        "SELECT p.path FROM photos p "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM catalog_files cf WHERE cf.abs_path = p.path AND cf.is_canonical = 1 AND cf.deleted = 0"
        "))"
    )
    db.sqlite.commit()


def show_stats(db):
    roots = db.get_catalog_roots()
    if not roots:
        print("No roots registered. Use --add <path> to add one.")
        return

    all_files = db.get_catalog_files()
    photos = db.get_all_photos()

    for root in roots:
        root_files = [f for f in all_files if f["root_id"] == root["root_id"]]
        total = len(root_files)
        with_hash = sum(1 for f in root_files if f.get("content_hash"))
        canonical = sum(1 for f in root_files if f.get("is_canonical"))
        ingested = sum(1 for f in root_files if f.get("ingested"))

        print(f"\n  Root: {root['root_path']}")
        print(f"  Last scan: {root.get('scanned_at', 'never')}")
        print(f"  Files: {total} (with hash: {with_hash}, canonical: {canonical}, ingested: {ingested})")

    print(f"\n  Total catalog: {len(all_files)}, photos: {len(photos)}")


def sync_ingest_flags(db):
    photos = db.get_all_photos()
    all_files = db.get_catalog_files()
    path_to_photo = {p.get("path", ""): p for p in photos}
    updated = 0
    for f in all_files:
        photo = path_to_photo.get(f.get("abs_path", ""))
        ingested = photo is not None
        described = bool(photo and photo.get("description"))
        if f.get("ingested") != int(ingested) or f.get("described") != int(described):
            db.update_catalog_file(f["file_id"], ingested=int(ingested), described=int(described))
            updated += 1
    log(f"Synced {updated} file flags from photos table")


def main():
    parser = argparse.ArgumentParser(description="Scan and manage photo file catalog")
    parser.add_argument("--add", metavar="PATH", help="Register a new root directory and scan it")
    parser.add_argument("--alias", default="", help="Alias for the root being added")
    parser.add_argument("--scan", action="store_true", help="Phase A: scan paths only (fast, no hashes)")
    parser.add_argument("--hash", action="store_true", help="Phase B: compute content_hash for files without one")
    parser.add_argument("--limit", type=int, default=500, help="Hash batch limit (0=all)")
    parser.add_argument("--dedup-ingest", action="store_true", help="Phase C: dedup + ingest canonical into photos")
    parser.add_argument("--stats", action="store_true", help="Show catalog statistics")
    parser.add_argument("--sync", action="store_true", help="Sync ingest/describe flags from photos table")
    args = parser.parse_args()

    db = get_db()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("scan_catalog")
    except Exception:
        mq = None

    if args.add:
        root_id = add_root(db, args.add, args.alias)
        scan_root(db, root_id, mq)
        if mq:
            mq.shutdown()
        return

    if args.scan:
        roots = db.get_catalog_roots()
        if not roots:
            print("No roots registered. Use --add <path> first.")
        else:
            for root in roots:
                if root.get("enabled", 1):
                    scan_root(db, root["root_id"], mq)
        if mq:
            mq.shutdown()
        return

    if args.hash:
        hash_batch(db, limit=args.limit, mq=mq)
        if mq:
            mq.shutdown()
        return

    if args.dedup_ingest:
        dedup_ingest(db, mq=mq)
        if mq:
            mq.shutdown()
        return

    if args.sync:
        sync_ingest_flags(db)
        if mq:
            mq.shutdown()
        return

    show_stats(db)


if __name__ == "__main__":
    main()
