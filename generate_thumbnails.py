#!/usr/bin/env python3
"""
generate_thumbnails.py - Batch thumbnail generation using pyvips

Usage:
    python generate_thumbnails.py --all          # Generate for all photos
    python generate_thumbnails.py --missing       # Only missing thumbnails
    python generate_thumbnails.py --limit 1000    # First 1000 photos
    python generate_thumbnails.py --size sm       # Only small size
    python generate_thumbnails.py --format webp   # Only WebP format
    python generate_thumbnails.py --workers 8     # 8 parallel processes
    python generate_thumbnails.py --year 2016     # Only 2016 photos
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / "src"))

LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "thumbnails")


def log(msg):
    line = f"[{datetime.now().isoformat()}] [THUMBS] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def set_flag():
    os.makedirs(os.path.dirname(FLAG_FILE), exist_ok=True)
    open(FLAG_FILE, "w").close()


def clear_flag():
    try:
        os.remove(FLAG_FILE)
    except OSError:
        pass


def generate_one(args):
    path_str, size_name, fmt = args
    try:
        from thumbnails import ThumbnailGenerator

        gen = ThumbnailGenerator()
        p = Path(path_str)
        if not p.exists():
            return False, path_str, "file missing"

        if size_name:
            result = gen.generate(p, size_name=size_name, fmt=fmt)
        else:
            result = gen.generate(p, fmt=fmt)

        return result is not None, path_str, ""
    except (ImportError, OSError, ValueError, RuntimeError) as e:
        return False, path_str, str(e)


def _parse_args():
    parser = argparse.ArgumentParser(description="Batch thumbnail generation with pyvips")
    parser.add_argument("--all", action="store_true", help="Generate for all photos")
    parser.add_argument("--missing", action="store_true", help="Only generate missing thumbnails")
    parser.add_argument("--limit", type=int, default=0, help="Max photos to process")
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker processes")
    parser.add_argument("--size", type=str, default=None, help="Size: sm/md/lg")
    parser.add_argument("--format", type=str, default=None, help="Format: webp/jpg")
    parser.add_argument("--year", type=str, default=None, help="Only photos from this year")
    return parser.parse_args()


def _fetch_photo_paths(db, year):
    query = "SELECT path FROM photos"
    conditions = []
    if year:
        conditions.append(f"path LIKE '%/{year}/%'")
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY path"
    rows = db.sqlite.execute(query).fetchall()
    return [r[0] for r in rows if r[0]]


def _filter_missing(paths, size_name, fmt):
    from thumbnails import ThumbnailGenerator, SIZES

    gen = ThumbnailGenerator()
    filtered = []
    for p_str in paths:
        p = Path(p_str)
        if not p.exists():
            continue
        needs = False
        sizes = {size_name: SIZES[size_name]} if size_name else SIZES
        fmts = [fmt] if fmt else ["webp", "jpg"]
        for sname in sizes:
            for f in fmts:
                if gen.needs_regeneration(p, sname, f):
                    needs = True
                    break
            if needs:
                break
        if needs:
            filtered.append(p_str)
    return filtered


def _process_batch(paths, workers, size_name, fmt):
    from concurrent.futures import ProcessPoolExecutor, as_completed

    work_items = [(p, size_name, fmt) for p in paths]
    done = 0
    failed = 0
    t0 = time.time()

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(generate_one, item): item[0] for item in work_items}
        for future in as_completed(futures):
            ok, path_str, err = future.result()
            if ok:
                done += 1
            else:
                failed += 1
                if failed <= 10:
                    log(f"  FAILED: {path_str}: {err}")

            total = done + failed
            if total % 1000 == 0:
                elapsed = time.time() - t0
                rate = total / max(elapsed, 1)
                pct = total / len(paths) * 100
                log(
                    f"  [{total}/{len(paths)}] {done} ok, {failed} fail "
                    f"({pct:.0f}%, {rate:.0f}/s)"
                )

    elapsed = time.time() - t0
    log(
        f"Done: {done} generated, {failed} failed in {elapsed:.1f}s "
        f"({done / max(elapsed, 1):.0f}/s)"
    )
    return failed


def main():
    args = _parse_args()

    from database import DatabaseManager

    db = DatabaseManager()
    paths = _fetch_photo_paths(db, args.year)

    if args.missing:
        paths = _filter_missing(paths, args.size, args.format)
        log(f"Missing thumbnails: {len(paths)} photos")
    else:
        paths = [p for p in paths if Path(p).exists()]

    if args.limit > 0:
        paths = paths[: args.limit]

    if not paths:
        log("No photos to process")
        return 0

    log(
        f"Starting: {len(paths)} photos, workers={args.workers}, "
        f"size={args.size or 'all'}, format={args.format or 'all'}"
    )

    set_flag()
    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("thumbnails")
    except (ImportError, OSError, ConnectionError):
        mq = None

    failed = _process_batch(paths, args.workers, args.size, args.format)

    clear_flag()
    if mq:
        mq.shutdown()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
