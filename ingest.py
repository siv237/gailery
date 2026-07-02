#!/usr/bin/env python3
"""
ingest.py - Ingest photos from catalog into LanceDB photos table.
Reads from catalog_files table (not filesystem), marks ingested files.

Usage:
    python ingest.py --random 100       # 100 random not-ingested files from catalog
    python ingest.py --sequential 50    # first 50 by path
    python ingest.py --all              # all not-ingested
    python ingest.py --random 100 --exif # also read EXIF
    python ingest.py --year 2016        # only files from 2016 dirs
    python ingest.py --dir школоло      # only files under this dir
    python ingest.py --dry-run --random 20
"""

import argparse
import os
import random
import sys
import time
from pathlib import Path
from datetime import datetime

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "ingest")


def log(msg):
    line = f"[{datetime.now().isoformat()}] [INGEST] {msg}"
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
    except OSError:
        pass


def stopped():
    return not os.path.exists(FLAG_FILE)


def read_exif(photo_path):
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS
        img = Image.open(photo_path)
        exif_data = img._getexif()
        if not exif_data:
            return None
    except (OSError, ImportError):
        return None

    result = {"date": None, "gps": None, "camera": None}

    for tag_id, value in exif_data.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "DateTimeOriginal" and value:
            result["date"] = str(value).replace(":", "-", 2)
        elif tag == "DateTime" and not result["date"] and value:
            result["date"] = str(value).replace(":", "-", 2)
        elif tag == "Make" and value:
            if not result["camera"]:
                result["camera"] = {}
            result["camera"]["make"] = str(value).strip()
        elif tag == "Model" and value:
            if not result["camera"]:
                result["camera"] = {}
            result["camera"]["model"] = str(value).strip()
        elif tag == "GPSInfo" and value:
            gps = {}
            for gps_tag_id in value.keys():
                gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                gps[gps_tag] = value[gps_tag_id]
            lat = gps.get("GPSLatitude")
            lat_ref = gps.get("GPSLatitudeRef")
            lon = gps.get("GPSLongitude")
            lon_ref = gps.get("GPSLongitudeRef")
            if lat and lon:
                def to_deg(v, ref):
                    d, m, s = v
                    deg = float(d) + float(m) / 60.0 + float(s) / 3600.0
                    if ref in ('S', 'W'):
                        deg = -deg
                    return deg
                result["gps"] = {
                    "lat": to_deg(lat, lat_ref),
                    "lon": to_deg(lon, lon_ref),
                }

    return result if any(result.values()) else None


def get_uningested(db, year=None, dir_filter=None, root_id=None):
    """Get catalog files not yet ingested, optionally filtered."""
    all_files = db.get_catalog_files()
    enabled_roots = {r["root_id"] for r in db.get_catalog_roots() if r.get("enabled", 1)}
    if root_id:
        all_files = [f for f in all_files if f.get("root_id") == root_id]
    else:
        all_files = [f for f in all_files if f.get("root_id") in enabled_roots]
    candidates = [f for f in all_files if not f.get("ingested") and f.get("is_canonical", 1)]

    if year:
        candidates = [f for f in candidates if year in f.get("parent_dir", "")]
    if dir_filter:
        candidates = [f for f in candidates if dir_filter in f.get("parent_dir", "") or dir_filter in f.get("rel_path", "")]

    return candidates


def mark_ingested_batch(db, file_ids):
    if not file_ids:
        return
    for fid in file_ids:
        db.update_catalog_file(fid, ingested=1)


def ingest(catalog_files, db, total_catalog, read_exif_flag=False, dry_run=False):
    added = 0
    skipped = 0
    ingested_ids = []
    batch_records = []
    t0 = time.time()

    for i, cf in enumerate(catalog_files, 1):
        abs_path = cf.get("abs_path", "")
        path_str = abs_path

        if not Path(abs_path).exists():
            skipped += 1
            continue

        date = None
        gps = None
        camera = None
        date_conflict = False

        if read_exif_flag:
            exif = read_exif(Path(abs_path))
            raw_date = exif.get("date") if exif else None
            if raw_date:
                raw_date = raw_date.replace(":", "-", 2)
            gps = exif.get("gps") if exif else None
            camera = exif.get("camera") if exif else None
            mtime = None
            try:
                import os
                mtime = os.stat(abs_path).st_mtime
            except OSError:
                pass
            from exif import resolve_date
            resolved, conflict = resolve_date(raw_date, path_str, mtime)
            date = resolved
            date_conflict = conflict

        if dry_run:
            print(f"  [{i}] DRY: {cf.get('rel_path','')}" + (f" date={date}" if date else ""), flush=True)
            added += 1
            continue

        import uuid
        from datetime import datetime as dt
        batch_records.append({
            "photo_id": str(uuid.uuid4()),
            "path": path_str,
            "thumbnail_path": "",
            "date": date,
            "gps_lat": gps.get("lat") if gps else None,
            "gps_lon": gps.get("lon") if gps else None,
            "camera_make": camera.get("make") if camera else None,
            "camera_model": camera.get("model") if camera else None,
            "created_at": dt.now().isoformat(),
            "description": None,
            "faces_present": False,
            "date_conflict": int(date_conflict),
            "root_id": cf.get("root_id"),
        })
        ingested_ids.append(cf["file_id"])
        added += 1

        if len(batch_records) >= 50:
            db.add_photos_batch(batch_records)
            batch_records = []

        if added % 10 == 0:
            pct = (added / len(catalog_files) * 100) if catalog_files else 0
            overall_pct = (added / total_catalog * 100) if total_catalog else 0
            print(f"  [{i}/{len(catalog_files)}] added {added}, skipped {skipped} ({pct:.0f}% batch, {overall_pct:.2f}% catalog)", flush=True)

    if batch_records and not dry_run:
        db.add_photos_batch(batch_records)

    if ingested_ids and not dry_run:
        mark_ingested_batch(db, ingested_ids)

    elapsed = time.time() - t0
    print(f"\n{'='*50}", flush=True)
    print(f"  DONE: {added} added, {skipped} skipped", flush=True)
    print(f"  Time: {elapsed:.1f}s ({added/max(elapsed,0.001):.0f}/s)", flush=True)
    print(f"{'='*50}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Ingest photos from catalog into DB")
    parser.add_argument("--random", type=int, default=0, metavar="N",
                        help="Pick N random not-ingested files from catalog")
    parser.add_argument("--sequential", type=int, default=0, metavar="N",
                        help="Take first N not-ingested by path")
    parser.add_argument("--all", action="store_true",
                        help="Ingest all not-ingested files")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Alias for --random N")
    parser.add_argument("--exif", action="store_true",
                        help="Read EXIF metadata (date, GPS, camera)")
    parser.add_argument("--year", type=str, default="",
                        help="Only files from directories with this year")
    parser.add_argument("--dir", type=str, default="",
                        help="Only files under this directory substring")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing")
    parser.add_argument("--root", type=str, default="",
                        help="Only ingest files from this root_id")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()
    set_flag()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("ingest")
    except (ImportError, ConnectionError):
        mq = None

    candidates = get_uningested(db, year=args.year or None, dir_filter=args.dir or None, root_id=args.root or None)
    total_catalog = db.count_catalog_files()
    total_not_ingested = len(candidates)
    log(f"Catalog: {total_catalog} files, {total_not_ingested} not ingested")

    if not candidates:
        log("Nothing to ingest")
        return 0

    n = args.random or args.limit
    if n > 0:
        candidates = random.sample(candidates, min(n, len(candidates)))
        log(f"Random sample: {len(candidates)} files")
    elif args.sequential > 0:
        candidates = sorted(candidates, key=lambda f: f.get("rel_path", ""))[:args.sequential]
        log(f"Sequential first {len(candidates)} files")
    elif not args.all:
        log("Specify --random N, --sequential N, --all, or --limit N")
        return 1

    ingest(candidates, db, total_catalog=total_catalog, read_exif_flag=args.exif, dry_run=args.dry_run)
    clear_flag()
    if mq:
        mq.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
