#!/usr/bin/env python3
"""
pipeline.py - Batch worker: loops through chain until 100% or stopped.
Chain: Ingest -> Describe -> Faces -> EXIF -> Embed

Usage:
    python pipeline.py
    python pipeline.py --ingest 200 --describe 50
    python pipeline.py --batch 200
"""

import argparse
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

_dotenv = Path(__file__).parent / ".env"
if _dotenv.exists():
    with open(_dotenv) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
LOG_FILE = str(Path(__file__).parent / "logs" / "pipeline.log")
FLAG_FILE = str(Path(__file__).parent / "data" / "pipeline_flags" / "pipeline")
SCRIPTS_DIR = str(Path(__file__).parent)

_mq = None


def log(msg):
    line = f"[{datetime.now().isoformat()}] [PIPELINE] {msg}"
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
    if not os.path.exists(FLAG_FILE):
        return True
    if _mq and _mq.stopped():
        return True
    return False


def get_progress(root_id=None):
    from database import DatabaseManager
    db = DatabaseManager()
    cur = db.sqlite.cursor()

    root_where = " AND cf.root_id = ?" if root_id else ""
    root_params = [root_id] if root_id else []

    base = f"FROM catalog_files cf JOIN photos p ON p.path = cf.abs_path WHERE cf.is_canonical = 1 AND cf.deleted = 0 AND p.deleted = 0{root_where}"
    photo_where = base + " AND (p.media_type IS NULL OR p.media_type != 'video')"

    cat_total = cur.execute(f"SELECT COUNT(*) FROM catalog_files cf WHERE cf.is_canonical = 1 AND cf.deleted = 0{root_where}", root_params).fetchone()[0]

    ingested = cur.execute(f"SELECT COUNT(*) {base}", root_params).fetchone()[0]
    ingested_photos = cur.execute(f"SELECT COUNT(*) {photo_where}", root_params).fetchone()[0]
    described = cur.execute(f"SELECT COUNT(*) {photo_where} AND p.description IS NOT NULL", root_params).fetchone()[0]
    exif_checked = cur.execute(f"SELECT COUNT(*) {photo_where} AND p.exif_checked = 1", root_params).fetchone()[0]
    faces_flagged = cur.execute(f"SELECT COUNT(*) {photo_where} AND p.faces_present = 1", root_params).fetchone()[0]
    faces_done = cur.execute(
        f"SELECT COUNT(*) {photo_where} AND p.faces_present = 1"
        f" AND EXISTS (SELECT 1 FROM faces f WHERE f.content_hash = cf.content_hash)",
        root_params).fetchone()[0]
    faces_pending = faces_flagged - faces_done
    embedded = cur.execute(f"SELECT COUNT(*) {photo_where} AND p.embedded = 1", root_params).fetchone()[0]

    video_where = base + " AND p.media_type = 'video'"
    videos_catalog = cur.execute(f"SELECT COUNT(*) FROM catalog_files cf WHERE cf.is_canonical = 1 AND cf.deleted = 0 AND cf.ext IN ('.mp4','.mov','.avi','.mkv','.webm','.3gp','.wmv','.mpg','.mpeg','.m4v','.flv','.vob','.ts','.MP4','.MOV','.AVI','.MKV','.WEBM','.3GP','.WMV','.MPG','.MPEG','.M4V','.FLV','.VOB','.TS'){root_where}", root_params).fetchone()[0]
    videos_ingested = cur.execute(f"SELECT COUNT(*) {video_where}", root_params).fetchone()[0]
    videos_exif = cur.execute(f"SELECT COUNT(*) {video_where} AND p.exif_checked = 1", root_params).fetchone()[0]
    p_videos_ingest = videos_ingested / max(videos_catalog, 1) * 100 if videos_catalog > 0 else 0
    p_videos_exif = videos_exif / max(videos_ingested, 1) * 100 if videos_ingested > 0 else 0

    p_ingest = ingested / max(cat_total, 1) * 100
    p_describe = described / max(ingested_photos, 1) * 100
    p_exif = exif_checked / max(ingested_photos, 1) * 100
    p_faces = faces_done / max(faces_flagged, 1) * 100 if faces_flagged > 0 else 100
    p_embed = embedded / max(ingested_photos, 1) * 100

    return {
        "ingest": (ingested, cat_total, p_ingest),
        "describe": (described, ingested_photos, p_describe),
        "exif": (exif_checked, ingested_photos, p_exif),
        "faces": (faces_done, faces_flagged, p_faces),
        "faces_pending": faces_pending,
        "embed": (embedded, ingested_photos, p_embed),
        "videos": {
            "catalog": videos_catalog,
            "ingested": videos_ingested,
            "exif": videos_exif,
            "p_ingest": p_videos_ingest,
            "p_exif": p_videos_exif,
        },
    }


def run_step(name, cmd):
    if stopped():
        return -1
    log(f"  START: {name}")
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=False, text=True, env=os.environ.copy())
        elapsed = time.time() - t0
        if result.returncode == 0:
            log(f"  DONE: {name} ({elapsed:.0f}s)")
        else:
            log(f"  FAILED: {name} rc={result.returncode} ({elapsed:.0f}s)")
        return result.returncode
    except Exception as e:
        log(f"  ERROR: {name}: {e}")
        return 1


def kill_orphan_llama_servers():
    try:
        result = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True, text=True)
        for pid_str in result.stdout.strip().split():
            if not pid_str:
                continue
            pid = int(pid_str)
            try:
                ppid = int(open(f"/proc/{pid}/stat").read().split()[3])
                if ppid == 1:
                    os.kill(pid, 9)
                    log(f"Killed orphan llama-server pid={pid}")
            except (ProcessLookupError, FileNotFoundError, ValueError, PermissionError):
                pass
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Gailery batch worker loop")
    parser.add_argument("--batch", type=int, default=60, help="Photos per iteration (ingest/describe)")
    parser.add_argument("--ingest", type=int, default=0, help="Override ingest batch size (0=use --batch)")
    parser.add_argument("--describe", type=int, default=0, help="Override describe batch size (0=use --batch)")
    parser.add_argument("--batch-size", type=int, default=6, help="VLM batch size for describe")
    parser.add_argument("--root", type=str, default="", help="Only process files from this root_id")
    args = parser.parse_args()

    ingest_n = args.ingest or args.batch
    describe_n = args.describe or args.batch
    root_args = ["--root", args.root] if args.root else []
    root_path_arg = []
    if args.root:
        from database import DatabaseManager as _DB
        _r = _DB().get_catalog_root(args.root)
        if _r:
            root_path_arg = ["--dir", _r["root_path"]]

    os.makedirs(str(Path(__file__).parent / "logs"), exist_ok=True)
    set_flag()

    global _mq
    try:
        from mqtt_client import create_worker_mqtt
        _mq = create_worker_mqtt("pipeline")
    except Exception:
        _mq = None

    log("=" * 60)
    log(f"Pipeline loop started (batch={args.batch}, ingest={ingest_n}, describe={describe_n})")

    try:
        iteration = 0
        while not stopped():
            iteration += 1
            progress = get_progress(root_id=args.root or None)

            log(f"--- Итерация {iteration} ---")
            for step, val in progress.items():
                if isinstance(val, tuple):
                    done, total, pct = val
                    log(f"  {step}: {done}/{total} ({pct:.1f}%)")
                else:
                    log(f"  {step}: {val}")

            # Always scan at start of iteration to discover new files immediately
            scan_args = [VENV_PYTHON, f"{SCRIPTS_DIR}/scan_catalog.py", "--scan"]
            run_step("QUICK SCAN", scan_args)
            if stopped():
                break
            progress = get_progress()

            all_done = all(pct >= 100 for _, _, pct in [v for v in progress.values() if isinstance(v, tuple)])
            if all_done:
                _idle_flag = Path(FLAG_FILE).parent / "pipeline_idle"
                _idle_flag.parent.mkdir(parents=True, exist_ok=True)
                _idle_flag.touch()
                log("Все шаги 100% — засыпаю 5 минут, жду новых фото...")
                if not stopped():
                    time.sleep(300)
                try:
                    _idle_flag.unlink()
                except Exception:
                    pass
                continue

            if progress["describe"][2] < 100:
                from database import DatabaseManager as _DB
                _db = _DB()
                _cur = _db.sqlite.execute("UPDATE photos SET description='[видео]' WHERE media_type='video' AND (description IS NULL OR description='') AND deleted=0")
                if _cur.rowcount > 0:
                    _db.sqlite.execute("UPDATE catalog_files SET described=1 WHERE abs_path IN (SELECT path FROM photos WHERE media_type='video' AND description='[видео]') AND is_canonical=1")
                    _db.sqlite.commit()
                    log(f"MIGRATE: set description='[видео]' for {_cur.rowcount} videos")
                kill_orphan_llama_servers()
                remaining = progress["describe"][1] - progress["describe"][0]
                n = min(describe_n, remaining) if remaining > 0 else describe_n
                run_step("DESCRIBE", [VENV_PYTHON, f"{SCRIPTS_DIR}/describe.py", "--limit", str(n), "--batch-size", str(args.batch_size)] + root_path_arg)
                if stopped():
                    break

            if progress["faces"][2] < 100 or progress.get("faces_pending", 0) > 0:
                kill_orphan_llama_servers()
                run_step("FACES", [VENV_PYTHON, f"{SCRIPTS_DIR}/faces.py"])
                if stopped():
                    break

            if progress["exif"][2] < 100:
                run_step("EXIF", [VENV_PYTHON, f"{SCRIPTS_DIR}/exif.py", "--all"])
                if stopped():
                    break

            if progress["embed"][2] < 100:
                kill_orphan_llama_servers()
                run_step("EMBED", [VENV_PYTHON, f"{SCRIPTS_DIR}/embed.py"])
                if stopped():
                    break

            # Deduplicate + optimize photo embeddings at end of each cycle
            if not stopped():
                t0 = time.time()
                try:
                    from database import DatabaseManager
                    db = DatabaseManager()
                    before, after, removed = db.dedup_photo_embeddings()
                    db.compact_photo_embeddings()
                    elapsed = time.time() - t0
                    if removed > 0:
                        log(f"DEDUP: removed {removed} duplicate embeddings ({before} → {after}) in {elapsed:.1f}s")
                    else:
                        log(f"DEDUP: no duplicates ({before} rows), optimized in {elapsed:.1f}s")
                except Exception as e:
                    log(f"DEDUP: error: {e}")

            progress2 = get_progress()
            any_changed = any(
                (isinstance(progress2[k], tuple) and isinstance(progress[k], tuple) and progress2[k][0] != progress[k][0])
                for k in progress
            )
            if not any_changed and not all(pct >= 100 for _, _, pct in [v for v in progress2.values() if isinstance(v, tuple)]):
                log("Прогресса нет, засыпаю 30с...")
                time.sleep(30)

        log("Pipeline loop завершён")
    finally:
        clear_flag()
        if _mq:
            _mq.shutdown()


if __name__ == "__main__":
    main()
