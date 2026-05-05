#!/usr/bin/env python3
"""
scan_catalog.py - Scan photo directories and populate the file catalog.
Stores the full directory tree in DB so other scripts don't need to scan filesystem.
Supports multiple roots. Detects new/deleted/changed files on re-scan.

Usage:
    python scan_catalog.py                        # scan all registered roots
    python scan_catalog.py --add /path/to/photos  # register and scan a root
    python scan_catalog.py --stats                # show catalog statistics
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
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".raw", ".cr2", ".nef", ".arw", ".dng", ".heic",
                    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp", ".wmv", ".MP4", ".MOV", ".AVI", ".MKV", ".WEBM", ".3GP", ".WMV"}


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


def scan_root(db, root_id):
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

    log(f"Scanning: {root_path}")

    cur = db.sqlite.cursor()
    existing_rows = cur.execute(
        "SELECT rel_path, abs_path, file_id, content_hash, modified, size, deleted FROM catalog_files WHERE root_id = ?",
        (root_id,)
    ).fetchall()
    existing_map = {}
    for r in existing_rows:
        existing_map[r[0]] = {
            "rel_path": r[0], "abs_path": r[1], "file_id": r[2],
            "content_hash": r[3], "modified": r[4], "size": r[5], "deleted": r[6],
        }

    existing_rel = set(existing_map.keys())

    new_files = []
    kept_rel = set()
    changed_count = 0
    restored_count = 0
    stale_count = 0
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
                if scanned % 10 == 0:
                    elapsed = time.time() - t0
                    progress_msg = f"Scanned {scanned} files, new={len(new_files)}, changed={changed_count}, restored={restored_count}, dirs_skipped={skipped_dirs}, elapsed={elapsed:.1f}s"
                    log(progress_msg)
                    print(progress_msg, flush=True)

                try:
                    stat = os.stat(abs_path)
                    file_size = stat.st_size
                    mtime = stat.st_mtime
                except OSError:
                    continue

                mtime_str = str(mtime)

                if rel_path in existing_map:
                    old = existing_map[rel_path]
                    if old.get("deleted"):
                        content_hash = compute_file_hash(abs_path) if file_size > 0 else None
                        if content_hash and content_hash == old.get("content_hash"):
                            db.update_catalog_file(old["file_id"], deleted=0, deleted_type=None, abs_path=abs_path, size=file_size, modified=mtime_str)
                            restored_count += 1
                        else:
                            db.update_catalog_file(old["file_id"], deleted=0, deleted_type=None, abs_path=abs_path, parent_dir=str(Path(rel_path).parent), ext=ext, size=file_size, modified=mtime_str, content_hash=content_hash)
                            _mark_stale(db, old["file_id"], old.get("content_hash"), content_hash, abs_path)
                            stale_count += 1
                    elif str(old.get("modified", "")) != mtime_str or old.get("size", 0) != file_size:
                        content_hash = compute_file_hash(abs_path) if file_size > 0 else None
                        old_hash = old.get("content_hash")
                        db.update_catalog_file(old["file_id"], abs_path=abs_path, parent_dir=str(Path(rel_path).parent), ext=ext, size=file_size, modified=mtime_str, content_hash=content_hash)
                        if content_hash and old_hash and content_hash != old_hash:
                            _mark_stale(db, old["file_id"], old_hash, content_hash, abs_path)
                            stale_count += 1
                        else:
                            changed_count += 1
                    elif not old.get("content_hash") and file_size > 0:
                        content_hash = compute_file_hash(abs_path)
                        db.update_catalog_file(old["file_id"], content_hash=content_hash)
                else:
                    content_hash = compute_file_hash(abs_path) if file_size > 0 else None
                    new_files.append({
                        "file_id": str(uuid.uuid4()),
                        "root_id": root_id,
                        "rel_path": rel_path,
                        "abs_path": abs_path,
                        "parent_dir": str(Path(rel_path).parent),
                        "ext": ext,
                        "size": file_size,
                        "modified": mtime_str,
                        "content_hash": content_hash,
                        "ingested": False,
                        "described": False,
                        "exif_done": False,
                        "faces_done": False,
                    })

                if len(new_files) >= 1000:
                    db.add_catalog_files_batch(new_files)
                    new_files = []

        scan_complete = True
    except Exception as e:
        log(f"Scan ABORTED: {e}")
        scan_complete = False

    if new_files:
        db.add_catalog_files_batch(new_files)

    if scan_complete:
        deleted_rel = existing_rel - kept_rel
        deleted_count = 0
        if deleted_rel:
            for rel in deleted_rel:
                old = existing_map[rel]
                if not old.get("deleted"):
                    db.update_catalog_file(old["file_id"], deleted=1, deleted_type='auto_missing')
                    pid_row = db.sqlite.execute("SELECT photo_id FROM photos WHERE path = ? AND deleted = 0", (old["abs_path"],)).fetchone()
                    if pid_row:
                        db.sqlite.execute("UPDATE photos SET deleted = 1 WHERE photo_id = ?", (pid_row[0],))
                        db.sqlite.commit()
                    deleted_count += 1
            log(f"Marked {deleted_count} files as deleted (auto_missing)")
    else:
        log(f"Scan incomplete, skipping soft-delete step")

    if scan_complete:
        db.update_catalog_root(root_id, scanned_at=datetime.now().isoformat())

    if scan_complete:
        groups, copies = db.mark_canonical_duplicates()
        db.invalidate_canonical_cache()
        if copies > 0:
            log(f"Marked {copies} duplicate files (is_canonical=0) across {groups} groups")

        _ingest_new_canonical(db, root_id)

        _cleanup_noncanonical_photos(db)

    elapsed = time.time() - t0
    new_count = len(kept_rel - existing_rel)
    del_str = f"{deleted_count} deleted" if scan_complete else "NO delete (scan incomplete)"
    log(f"Scan done in {elapsed:.1f}s: {scanned} scanned, {skipped_dirs} dirs skipped, {new_count} new, {changed_count} changed, {del_str}, {restored_count} restored, {stale_count} stale")
    video_exts_lower = {'.mp4','.mov','.avi','.mkv','.webm','.3gp','.wmv'}
    new_videos = db.sqlite.execute(
        "SELECT COUNT(*) FROM catalog_files WHERE root_id = ? AND ext IN ({}) AND is_canonical = 1".format(
            ','.join("'"+e+"'" for e in video_exts_lower)),
        (root_id,)).fetchone()[0]
    log(f"Video files in catalog: {new_videos}")


def _mark_stale(db, file_id, old_hash, new_hash, abs_path):
    db.sqlite.execute("UPDATE photos SET description = NULL, faces_present = 0, exif_checked = 0, embedded = 0 WHERE path = ? AND deleted = 0", (abs_path,))
    if old_hash:
        db.sqlite.execute("DELETE FROM faces WHERE content_hash = ?", (old_hash,))
    db.sqlite.execute("UPDATE catalog_files SET embedded = 0, described = 0, exif_done = 0, faces_done = 0 WHERE file_id = ?", (file_id,))
    db.sqlite.commit()
    log(f"  Stale: {abs_path} hash changed {old_hash[:12] if old_hash else '?'}..→{new_hash[:12] if new_hash else '?'}.., flags reset")


def _ingest_new_canonical(db, root_id):
    cur = db.sqlite.cursor()
    rows = cur.execute(
        "SELECT cf.abs_path, cf.root_id FROM catalog_files cf "
        "WHERE cf.is_canonical = 1 AND cf.ingested = 0 AND cf.deleted = 0 AND cf.root_id = ?",
        (root_id,)
    ).fetchall()
    if not rows:
        return

    import uuid as _uuid
    batch = []
    file_ids = []
    for abs_path, rid in rows:
        ext = os.path.splitext(abs_path)[1].lower()
        is_video = ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp", ".wmv"}
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
        fid_row = cur.execute("SELECT file_id FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 AND deleted = 0", (abs_path,)).fetchone()
        if fid_row:
            file_ids.append(fid_row[0])

    db.add_photos_batch(batch)
    for fid in file_ids:
        db.update_catalog_file(fid, ingested=1)

    log(f"Ingested {len(batch)} new canonical files into photos")


def _cleanup_noncanonical_photos(db):
    db.sqlite.execute(
        "UPDATE photos SET deleted = 1 "
        "WHERE deleted = 0 AND path IN ("
        "SELECT p.path FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path "
        "WHERE cf.is_canonical = 0)"
    )
    db.sqlite.commit()


def show_stats(db):
    roots = db.get_catalog_roots()
    if not roots:
        print("No roots registered. Use --add <path> to add one.")
        return

    all_files = db.get_catalog_files()
    photos = db.get_all_photos()
    photo_paths = set(p.get("path", "") for p in photos)
    described_paths = set(p.get("path", "") for p in photos if p.get("description"))

    for root in roots:
        root_files = [f for f in all_files if f["root_id"] == root["root_id"]]
        total = len(root_files)
        ingested = sum(1 for f in root_files if f.get("ingested"))
        described = sum(1 for f in root_files if f.get("described"))
        exif_done = sum(1 for f in root_files if f.get("exif_done"))
        faces_done = sum(1 for f in root_files if f.get("faces_done"))
        total_size = sum(f.get("size", 0) for f in root_files)

        dirs = set(f.get("parent_dir", "") for f in root_files)

        print(f"\n  Root: {root['root_path']}")
        print(f"  Alias: {root.get('alias', '')}")
        print(f"  Last scan: {root.get('scanned_at', 'never')}")
        print(f"  Files: {total}")
        print(f"  Dirs: {len(dirs)}")
        print(f"  Size: {total_size / 1e9:.1f} GB")
        print(f"  Ingested: {ingested}")
        print(f"  Described: {described}")
        print(f"  EXIF done: {exif_done}")
        print(f"  Faces done: {faces_done}")

        by_ext = {}
        for f in root_files:
            e = f.get("ext", "?")
            by_ext[e] = by_ext.get(e, 0) + 1
        print(f"  By ext: {', '.join(f'{k}:{v}' for k, v in sorted(by_ext.items(), key=lambda x: -x[1])[:10])}")

        by_year = {}
        for f in root_files:
            d = f.get("parent_dir", "")
            parts = d.split("/")
            for p in parts:
                if len(p) == 4 and p.isdigit():
                    by_year[p] = by_year.get(p, 0) + 1
                    break
        if by_year:
            print(f"  By year: {', '.join(f'{k}:{v}' for k, v in sorted(by_year.items()))}")

    print(f"\n  Total files in catalog: {len(all_files)}")
    print(f"  Total photos in DB: {len(photos)}")


def sync_ingest_flags(db):
    photos = db.get_all_photos()
    all_files = db.get_catalog_files()

    abs_to_file = {}
    for f in all_files:
        abs_to_file[f.get("abs_path", "")] = f

    path_to_photo = {}
    for p in photos:
        path_to_photo[p.get("path", "")] = p

    updated = 0
    for f in all_files:
        abs_path = f.get("abs_path", "")
        photo = path_to_photo.get(abs_path)

        ingested = photo is not None
        described = bool(photo and photo.get("description"))
        exif_done = bool(photo and photo.get("date"))
        faces_done = bool(photo and photo.get("faces_present"))

        if f.get("ingested") != int(ingested) or f.get("described") != int(described) or \
           f.get("exif_done") != int(exif_done) or f.get("faces_done") != int(faces_done):
            db.update_catalog_file(f["file_id"], ingested=int(ingested), described=int(described), exif_done=int(exif_done), faces_done=int(faces_done))
            updated += 1

        if updated % 500 == 0 and updated > 0:
            print(f"  Synced {updated}...", flush=True)

    log(f"Synced {updated} file flags from photos table")


def backfill_hashes(db, root_id=None):
    """Compute content_hash for catalog files that don't have one yet."""
    where = "content_hash IS NULL AND size > 0"
    if root_id:
        where += f" AND root_id = '{root_id}'"
    files = db.get_catalog_files(where=where)
    if not files:
        print("All files already have content_hash")
        return

    print(f"Hashing {len(files)} files...")
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
        if len(batch) >= 500:
            db.sqlite.executemany("UPDATE catalog_files SET content_hash = ? WHERE file_id = ?", batch)
            db.sqlite.commit()
            batch = []
            if done % 2000 == 0:
                elapsed = time.time() - t0
                print(f"  {done}/{len(files)} ({elapsed:.1f}s, {done/max(elapsed,1):.0f}/s)", flush=True)

    if batch:
        db.sqlite.executemany("UPDATE catalog_files SET content_hash = ? WHERE file_id = ?", batch)
        db.sqlite.commit()

    elapsed = time.time() - t0
    log(f"Backfill hashes: {done} files in {elapsed:.1f}s ({done/max(elapsed,1):.0f}/s)")
    print(f"Done: {done} hashes in {elapsed:.1f}s ({done/max(elapsed,1):.0f}/s)")


def main():
    parser = argparse.ArgumentParser(description="Scan and manage photo file catalog")
    parser.add_argument("--add", metavar="PATH", help="Register a new root directory and scan it")
    parser.add_argument("--alias", default="", help="Alias for the root being added")
    parser.add_argument("--scan", action="store_true", help="Re-scan all registered roots")
    parser.add_argument("--stats", action="store_true", help="Show catalog statistics")
    parser.add_argument("--sync", action="store_true", help="Sync ingest/describe flags from photos table")
    parser.add_argument("--hash", action="store_true", help="Backfill content_hash for files without one")
    args = parser.parse_args()

    db = get_db()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("scan_catalog")
    except Exception:
        mq = None

    if args.add:
        root_id = add_root(db, args.add, args.alias)
        scan_root(db, root_id)
        if mq:
            mq.shutdown()
        return

    if args.scan:
        roots = db.get_catalog_roots()
        if not roots:
            print("No roots registered. Use --add <path> first.")
        else:
            for root in roots:
                scan_root(db, root["root_id"])
        if mq:
            mq.shutdown()
        return

    if args.sync:
        sync_ingest_flags(db)
        if mq:
            mq.shutdown()
        return

    if args.hash:
        backfill_hashes(db)
        if mq:
            mq.shutdown()
        return

    show_stats(db)


if __name__ == "__main__":
    main()
