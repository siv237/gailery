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

    root_filter = ""
    root_params = []
    if root_id:
        root = db.get_catalog_root(root_id)
        if root:
            root_path = root["root_path"]
            root_filter = " AND (path LIKE ?)"
            root_params = [root_path + "/%"]

    img_exts = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif', '.webp', '.heic', '.heif', '.avif', '.cr2', '.nef', '.arw', '.dng', '.rw2', '.orf')
    img_exts_all = img_exts + tuple(e.upper() for e in img_exts)
    ext_placeholders = ','.join(['?'] * len(img_exts_all))

    if root_id:
        cat_total = cur.execute(
            f"SELECT COUNT(*) FROM catalog_files WHERE ext IN ({ext_placeholders}) AND root_id = ? AND is_canonical = 1",
            img_exts_all + (root_id,)).fetchone()[0]
    else:
        cat_total = cur.execute(f"SELECT COUNT(*) FROM catalog_files WHERE ext IN ({ext_placeholders}) AND is_canonical = 1", img_exts_all).fetchone()[0]

    ingested = cur.execute(f"SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE cf.is_canonical = 1 AND p.deleted = 0").fetchone()[0]
    described = cur.execute(f"SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE p.description IS NOT NULL AND cf.is_canonical = 1").fetchone()[0]
    exif_checked = cur.execute(f"SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE p.exif_checked = 1 AND cf.is_canonical = 1").fetchone()[0]
    faces_flagged = cur.execute(f"SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path WHERE p.faces_present = 1 AND cf.is_canonical = 1").fetchone()[0]
    faces_with_persona = cur.execute(
        f"SELECT COUNT(DISTINCT f.photo_id) FROM faces f JOIN photos p ON f.photo_id = p.path OR f.photo_id = substr(p.path, length(?) + 2) WHERE f.persona_id IS NOT NULL{root_filter.replace('path', 'p.path')}",
        [str(db._get_photo_share_path()) + "/"] + root_params).fetchone()[0] if root_filter else cur.execute("SELECT COUNT(DISTINCT photo_id) FROM faces WHERE persona_id IS NOT NULL").fetchone()[0]
    faces_done = cur.execute(f"SELECT COUNT(DISTINCT photo_id) FROM faces").fetchone()[0]
    faces_pending = faces_flagged - faces_done
    if root_id:
        embedded = cur.execute("SELECT COUNT(*) FROM catalog_files WHERE embedded = 1 AND ingested = 1 AND root_id = ? AND is_canonical = 1", (root_id,)).fetchone()[0]
    else:
        embedded = cur.execute("SELECT COUNT(*) FROM catalog_files WHERE embedded = 1 AND ingested = 1 AND is_canonical = 1").fetchone()[0]

    p_ingest = ingested / max(cat_total, 1) * 100
    p_describe = described / max(ingested, 1) * 100
    p_exif = exif_checked / max(ingested, 1) * 100
    p_faces = faces_with_persona / max(faces_flagged, 1) * 100 if faces_flagged > 0 else 100
    p_embed = embedded / max(ingested, 1) * 100

    return {
        "ingest": (ingested, cat_total, p_ingest),
        "describe": (described, ingested, p_describe),
        "exif": (exif_checked, ingested, p_exif),
        "faces": (faces_with_persona, faces_flagged, p_faces),
        "faces_pending": faces_pending,
        "embed": (embedded, ingested, p_embed),
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

            all_done = all(pct >= 100 for _, _, pct in progress.values())
            if all_done:
                log("Все шаги 100% — цикл завершён")
                break

            if progress["ingest"][2] < 100:
                remaining = progress["ingest"][1] - progress["ingest"][0]
                n = min(ingest_n, remaining) if remaining > 0 else ingest_n
                run_step("INGEST", [VENV_PYTHON, f"{SCRIPTS_DIR}/ingest.py", "--random", str(n)] + root_args)
                if stopped():
                    break

            if progress["describe"][2] < 100:
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
            if not any_changed and not all(pct >= 100 for _, _, pct in progress2.values()):
                log("Прогресса нет, засыпаю 30с...")
                time.sleep(30)

        log("Pipeline loop завершён")
    finally:
        clear_flag()
        if _mq:
            _mq.shutdown()


if __name__ == "__main__":
    main()
