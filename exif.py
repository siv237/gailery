#!/usr/bin/env python3
"""
exif.py - Read EXIF metadata for photos not yet checked.
Marks exif_checked=True even if no EXIF found (won't re-check).
Extracts: date, GPS, camera make/model, orientation, flash, ISO, focal length.
Multi-threaded I/O for HDD throughput.

Usage:
    python exif.py
    python exif.py --limit 100
    python exif.py --all
    python exif.py --recheck    # re-check all (ignores exif_checked flag)
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import VIDEO_EXTS
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "exif")

EXIF_READ_THREADS = 8
EXIF_HEADER_SIZE = 65536
DATE_CONFLICT_THRESHOLD = 2

_exifread_logger_configured = False

_RU_MONTHS = {
    'январь': 1, 'февраль': 2, 'март': 3, 'апрель': 4, 'май': 5, 'июнь': 6,
    'июль': 7, 'август': 8, 'сентябрь': 9, 'октябрь': 10, 'ноябрь': 11, 'декабрь': 12,
    'янв': 1, 'фев': 2, 'мар': 3, 'апр': 4, 'мая': 5, 'июн': 6, 'июл': 7,
    'авг': 8, 'сен': 9, 'окт': 10, 'ноя': 11, 'дек': 12,
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
}
_EN_MONTHS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
}


def extract_date_from_path(path_str):
    import re
    p = path_str.replace('\\', '/')
    parts = p.split('/')

    for part in parts:
        m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', part)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = re.match(r'^(\d{4})\.(\d{2})\.(\d{2})$', part)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))
        m = re.match(r'^(\d{2})\.(\d{2})\.(\d{2,4})$', part)
        if m:
            y = int(m.group(3))
            if y < 100: y += 2000
            return y, int(m.group(2)), int(m.group(1))
        m = re.match(r'^(\d{4})_(\d{2})_(\d{2})', part)
        if m:
            return int(m.group(1)), int(m.group(2)), int(m.group(3))

    for part in parts:
        stripped = re.sub(r'\bat\s+\d{1,2}\.\d{2}\.\d{2}', '', part)
        m = re.search(r'(\d{2})\.(\d{2})\.(\d{2})', stripped)
        if m:
            d_val, mo_val, y_val = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= mo_val <= 12 and 1 <= d_val <= 31:
                year = 2000 + y_val
                if 1990 <= year <= 2030:
                    return year, mo_val, d_val

    for i in range(len(parts) - 2):
        y_m = re.match(r'^(\d{4})$', parts[i])
        d_m = re.match(r'^(\d{1,2})$', parts[i + 1])
        dd_m = d_m and int(parts[i + 1]) >= 1 and int(parts[i + 1]) <= 12
        if y_m and dd_m:
            year = int(parts[i])
            month = int(parts[i + 1])
            day = 1
            dd_match = re.match(r'^(\d{1,2})', parts[i + 2]) if i + 2 < len(parts) else None
            if dd_match and 1 <= int(dd_match.group(1)) <= 31:
                day = int(dd_match.group(1))
            return year, month, day

    for i in range(len(parts) - 1):
        y_m = re.match(r'^(\d{4})$', parts[i])
        if y_m:
            year = int(parts[i])
            lower = parts[i + 1].lower().split()[0].rstrip('.,')
            month = _RU_MONTHS.get(lower) or _EN_MONTHS.get(lower)
            if month:
                return year, month, 1
            return year, 1, 1

    fname = parts[-1] if parts else ''
    patterns = [
        r'IMG[_\-](\d{4})(\d{2})(\d{2})',
        r'IMG[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'DSC[_\-](\d{4})(\d{2})(\d{2})',
        r'photo[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'photo[_\-](\d{4})(\d{2})(\d{2})',
        r'Screenshot[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'Signal[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'VID[_\-](\d{4})(\d{2})(\d{2})',
        r'video[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'Screen[_\-](\d{4})[_\-](\d{2})[_\-](\d{2})',
        r'(\d{4})[_\-](\d{2})[_\-](\d{2})',
    ]
    for pat in patterns:
        m = re.search(pat, fname)
        if m:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1990 <= y <= 2030 and 1 <= mo <= 12 and 1 <= d <= 31:
                return y, mo, d

    return None


def normalize_exif_date(date_str):
    import re
    if not date_str:
        return None
    m = re.match(r'^(\d{4})[:\-](\d{2})[:\-](\d{2})\s*(\d{2}):(\d{2}):(\d{2})', date_str)
    if not m:
        return None
    y, mo, d, h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
    if y < 1990 or y > 2030 or mo < 1 or mo > 12 or d < 1 or d > 31:
        return None
    if mo == 1 and d == 1 and h == 0 and mi == 0 and s == 0:
        return None
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"


def resolve_date(exif_date, path_str, mtime=None):
    norm_exif = normalize_exif_date(exif_date)
    path_date = extract_date_from_path(path_str)

    if norm_exif and path_date:
        exif_year = int(norm_exif[:4])
        if abs(exif_year - path_date[0]) > DATE_CONFLICT_THRESHOLD:
            return f"{path_date[0]:04d}-{path_date[1]:02d}-{path_date[2]:02d} 00:00:00", True
        return norm_exif, False

    if norm_exif:
        return norm_exif, False

    if path_date:
        return f"{path_date[0]:04d}-{path_date[1]:02d}-{path_date[2]:02d} 00:00:00", False

    if mtime:
        from datetime import datetime
        dt = datetime.fromtimestamp(mtime)
        if dt.year >= 1990:
            return dt.strftime("%Y-%m-%d %H:%M:%S"), False

    return None, False


def log(msg):
    line = f"[{datetime.now().isoformat()}] [EXIF] {msg}"
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


def _configure_exifread_logger():
    global _exifread_logger_configured
    if not _exifread_logger_configured:
        import logging
        logging.getLogger('exifread').setLevel(logging.ERROR)
        _exifread_logger_configured = True


def read_exif_one(photo_path):
    _configure_exifread_logger()
    import exifread
    import io

    try:
        with open(photo_path, 'rb') as f:
            header = f.read(EXIF_HEADER_SIZE)
        tags = exifread.process_file(io.BytesIO(header), details=False, strict=False)
        if not tags:
            return None
    except Exception:
        return None

    result = {"date": None, "gps": None, "camera": None, "exif_raw": {}}

    dt = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
    if dt:
        result["date"] = str(dt)

    make = tags.get("Image Make")
    model = tags.get("Image Model")
    if make or model:
        result["camera"] = {}
        if make:
            result["camera"]["make"] = str(make).strip()
        if model:
            result["camera"]["model"] = str(model).strip()

    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")
    if lat_tag and lon_tag:
        def to_deg(val, ref):
            def _ratio(v):
                if hasattr(v, 'den'):
                    if v.den == 0:
                        return 0.0
                    return float(v.num) / float(v.den)
                try:
                    return float(v)
                except (ZeroDivisionError, ValueError):
                    return 0.0
            d = _ratio(val.values[0])
            m = _ratio(val.values[1])
            s = _ratio(val.values[2])
            deg = d + m / 60.0 + s / 3600.0
            if ref and str(ref) in ('S', 'W'):
                deg = -deg
            return deg
        lat_ref_str = str(lat_ref) if lat_ref else 'N'
        lon_ref_str = str(lon_ref) if lon_ref else 'E'
        result["gps"] = {"lat": to_deg(lat_tag, lat_ref_str), "lon": to_deg(lon_tag, lon_ref_str)}

    skip_prefixes = ('JPEGThumbnail', 'TIFFThumbnail', 'Thumbnail', 'Interoperability', 'PrintIM', 'EXIF MakerNote', 'MakerNote')
    skip_keys = {'Image ExifOffset', 'Image PrintIM', 'EXIF ExifVersion', 'EXIF FlashPixVersion',
                 'EXIF ComponentsConfiguration', 'EXIF InteroperabilityOffset',
                 'EXIF CompressedBitsPerPixel', 'Image YCbCrPositioning', 'Image ResolutionUnit',
                 'EXIF ColorSpace', 'EXIF SubjectDistanceRange', 'EXIF CustomRendered'}
    for k, v in tags.items():
        if any(k.startswith(p) for p in skip_prefixes):
            continue
        if k in skip_keys:
            continue
        result["exif_raw"][k] = str(v)

    has_data = result["date"] or result["gps"] or result["camera"]
    return result if has_data else None


def read_exif_batch(items):
    results = []
    for photo_id, path in items:
        if not path or not Path(path).exists():
            results.append((photo_id, path, None, True))
            continue
        exif = read_exif_one(path)
        results.append((photo_id, path, exif, False))
    return results


def main():
    parser = argparse.ArgumentParser(description="Read EXIF metadata")
    parser.add_argument("--limit", type=int, default=0, help="Max photos (0=all)")
    parser.add_argument("--all", action="store_true", help="Process all")
    parser.add_argument("--recheck", action="store_true", help="Re-check even exif_checked photos")
    args = parser.parse_args()

    from database import DatabaseManager
    db = DatabaseManager()
    set_flag()
    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("exif")
    except Exception:
        mq = None
    try:
        return _main(db, args, mq)
    finally:
        clear_flag()
        if mq:
            mq.shutdown()


def _main(db, args, mq=None):

    if args.recheck:
        need_exif = db.get_all_photos()
    else:
        rows = db.sqlite.execute(
            "SELECT p.photo_id, p.path FROM photos p "
            "JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 AND cf.deleted = 0 "
            "WHERE p.exif_checked = 0 AND p.deleted = 0 ORDER BY p.path"
        ).fetchall()
        need_exif = [{"photo_id": r[0], "path": r[1]} for r in rows]

    log(f"Found {len(need_exif)} photos to check for EXIF (threads={EXIF_READ_THREADS})")

    if not need_exif:
        return 0

    limit = 0 if args.all or args.recheck else args.limit
    if limit > 0:
        need_exif = need_exif[:limit]
        log(f"Processing first {limit}")

    with_data = 0
    empty = 0
    missing = 0
    gps_found = 0
    batch_updates = []
    cat_done_paths = []
    t0 = time.time()
    last_log_t = t0
    processed = 0
    BATCH_SIZE = 500
    LOG_INTERVAL = 10

    work_items = [(p["photo_id"], p.get("path", "")) for p in need_exif]

    with ThreadPoolExecutor(max_workers=EXIF_READ_THREADS) as pool:
        chunk_size = max(BATCH_SIZE // EXIF_READ_THREADS, 50)
        chunks = [work_items[i:i + chunk_size] for i in range(0, len(work_items), chunk_size)]

        futures = [pool.submit(read_exif_batch, chunk) for chunk in chunks]

        for future in as_completed(futures):
            results = future.result()

            for photo_id, path, exif, is_missing in results:
                updates = {"exif_checked": 1}

                # --- video metadata (if file is a video) ---
                is_video = any(path.endswith(ext) for ext in VIDEO_EXTS)

                if is_video:
                    from video_metadata import extract_metadata, extract_video_date
                    v_meta = extract_metadata(path)
                    if v_meta:
                        updates["media_type"] = "video"
                        updates["duration_seconds"] = v_meta["duration_seconds"]
                        if v_meta["width"] and v_meta["height"]:
                            updates["img_width"] = v_meta["width"]
                            updates["img_height"] = v_meta["height"]
                        updates["camera_model"] = v_meta.get("codec", "")
                        v_date = extract_video_date(path)
                        mtime = None
                        if path and Path(path).exists():
                            try:
                                mtime = os.stat(path).st_mtime
                            except Exception:
                                pass
                        resolved, conflict = resolve_date(v_date or None, path, mtime)
                        if resolved:
                            updates["date"] = resolved
                        if conflict:
                            updates["date_conflict"] = 1
                        with_data += 1
                    batch_updates.append((photo_id, updates))
                    if path:
                        cat_done_paths.append(path)
                    continue

                # --- photo EXIF processing ---
                if is_missing:
                    missing += 1
                    batch_updates.append((photo_id, updates))
                    if path:
                        cat_done_paths.append(path)
                    continue

                exif_date = exif.get("date") if exif else None
                mtime = None
                if path and Path(path).exists():
                    try:
                        mtime = os.stat(path).st_mtime
                    except Exception:
                        pass
                resolved, conflict = resolve_date(exif_date, path, mtime)
                if resolved:
                    updates["date"] = resolved
                if conflict:
                    updates["date_conflict"] = 1

                if exif:
                    gps = exif.get("gps")
                    if gps:
                        updates["gps_lat"] = gps["lat"]
                        updates["gps_lon"] = gps["lon"]
                        gps_found += 1
                    camera = exif.get("camera")
                    if camera:
                        if camera.get("make"):
                            updates["camera_make"] = camera["make"]
                        if camera.get("model"):
                            updates["camera_model"] = camera["model"]
                    for key in ["exposure_time", "f_number", "iso", "focal_length", "orientation", "flash", "software"]:
                        val = exif.get(key)
                        if val:
                            updates[key] = val
                    if exif.get("exif_raw"):
                        import json
                        updates["exif_raw"] = json.dumps(exif["exif_raw"], ensure_ascii=False)
                    with_data += 1
                else:
                    empty += 1

                batch_updates.append((photo_id, updates))
                cat_done_paths.append(path)
                processed += 1

            if len(batch_updates) >= BATCH_SIZE:
                flush_batch(db, batch_updates, cat_done_paths)
                batch_updates = []
                cat_done_paths = []

            now = time.time()
            if now - last_log_t >= LOG_INTERVAL:
                pct = processed / len(need_exif) * 100
                elapsed = now - t0
                rate = processed / max(elapsed, 1)
                log(f"  [{processed}/{len(need_exif)}] {with_data} с данными, {empty} пустые, {gps_found} GPS, {missing} нет файла ({pct:.0f}%, {rate:.0f}/s)")
                last_log_t = now

    if batch_updates:
        flush_batch(db, batch_updates, cat_done_paths)

    elapsed = time.time() - t0
    log(f"EXIF done: {with_data} с данными, {empty} пустые, {gps_found} GPS, {missing} нет файла in {elapsed:.0f}s ({len(need_exif)/max(elapsed,1):.0f}/s)")
    return 0


def flush_batch(db, batch_updates, cat_done_paths):
    from datetime import datetime, timezone
    cur = db.sqlite.cursor()
    now = datetime.now(timezone.utc).isoformat()
    for photo_id, updates in batch_updates:
        if not updates:
            continue
        skip = {"exif_checked", "embedded"}
        for k, v in updates.items():
            if k in skip or v is None:
                continue
            cur.execute(
                "INSERT INTO changes (photo_id, field, value, changed_at) VALUES (?, ?, ?, ?)",
                (photo_id, k, str(v)[:200], now)
            )
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [photo_id]
        cur.execute(f"UPDATE photos SET {sets} WHERE photo_id = ?", vals)

    if cat_done_paths:
        for path in cat_done_paths:
            cur.execute("UPDATE catalog_files SET exif_done = 1 WHERE abs_path = ?", (path,))

    db.sqlite.commit()


if __name__ == "__main__":
    main()
