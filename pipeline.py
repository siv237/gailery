#!/usr/bin/env python3
"""
pipeline.py - Batch worker: loops through chain until 100% or stopped.
Single DB writer: only pipeline writes to SQLite. API sends DB commands via MQTT.
Chain: Ingest -> Describe -> Faces -> EXIF -> Embed

Usage:
    python pipeline.py
    python pipeline.py --ingest 200 --describe 50
    python pipeline.py --batch 200
"""

import argparse
import json
import os
import sys
import subprocess
import time
import threading
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
_db = None


def log(msg):
    line = f"[{datetime.now().isoformat()}] [PIPELINE] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_db():
    global _db
    if _db is None:
        from database import DatabaseManager
        _db = DatabaseManager()
    return _db


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
    db = get_db()
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


def _close_db():
    global _db
    if _db is not None:
        try:
            _db.sqlite.close()
        except Exception:
            pass
        _db = None


def run_step(name, cmd):
    if stopped():
        return -1
    log(f"  START: {name}")
    _close_db()
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


def _execute_db_cmd(cmd, params):
    db = get_db()
    try:
        if cmd == "insert_system_metric":
            db.insert_system_metric(params)
            return {"ok": True}

        elif cmd == "control_reset":
            step = params.get("step", "")
            reset_map = {
                "describe": [
                    "UPDATE photos SET description=NULL, faces_present=0, embedded=0, rich_description=NULL WHERE deleted=0",
                    "UPDATE catalog_files SET described=0 WHERE is_canonical=1 AND deleted=0",
                ],
                "faces": [
                    "DELETE FROM faces",
                    "UPDATE catalog_files SET faces_done=0 WHERE is_canonical=1 AND deleted=0",
                    "DELETE FROM personas",
                ],
                "exif": [
                    "UPDATE photos SET exif_checked=0 WHERE deleted=0",
                    "UPDATE catalog_files SET exif_done=0 WHERE is_canonical=1 AND deleted=0",
                ],
                "embed": [
                    "UPDATE photos SET embedded=0 WHERE deleted=0",
                    "UPDATE catalog_files SET embedded=0 WHERE is_canonical=1 AND deleted=0",
                ],
            }
            sqls = reset_map.get(step)
            if not sqls:
                return {"ok": False, "error": f"unknown step: {step}"}
            affected = 0
            for sql in sqls:
                cur = db.sqlite.execute(sql)
                affected += cur.rowcount
            db.sqlite.commit()
            return {"ok": True, "step": step, "affected": affected}

        elif cmd == "set_setting":
            db.set_setting(params.get("key", ""), params.get("value", ""))
            return {"ok": True}

        elif cmd == "update_photo":
            photo_id = params.get("photo_id", "")
            updates = params.get("updates", {})
            if not photo_id or not updates:
                return {"ok": False, "error": "photo_id and updates required"}
            photo = db.get_photo(photo_id)
            if not photo:
                photo = db.get_photo_by_path(photo_id)
            if not photo:
                return {"ok": False, "error": "Photo not found"}
            db.update_photo(photo["photo_id"], **updates)
            return {"ok": True}

        elif cmd == "set_gps":
            photo_id = params.get("photo_id")
            lat = params.get("lat")
            lon = params.get("lon")
            if not photo_id or lat is None or lon is None:
                return {"ok": False, "error": "photo_id, lat, lon required"}
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET gps_lat = ?, gps_lon = ?, manual_gps = 1 WHERE photo_id = ?", (float(lat), float(lon), row[0]))
            db.sqlite.commit()
            return {"ok": True}

        elif cmd == "clear_gps":
            photo_id = params.get("photo_id")
            if not photo_id:
                return {"ok": False, "error": "photo_id required"}
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET gps_lat = NULL, gps_lon = NULL, manual_gps = 0 WHERE photo_id = ?", (row[0],))
            db.sqlite.commit()
            return {"ok": True}

        elif cmd == "set_date":
            photo_id = params.get("photo_id")
            manual_date = params.get("manual_date")
            if not photo_id or not manual_date:
                return {"ok": False, "error": "photo_id, manual_date required"}
            if len(manual_date) == 10 and manual_date[4] == '-' and manual_date[7] == '-':
                manual_date += " 00:00:00"
            elif len(manual_date) == 16 and manual_date[10] == ' ':
                manual_date += ":00"
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET manual_date = ? WHERE photo_id = ?", (manual_date, row[0]))
            db.sqlite.commit()
            return {"ok": True, "manual_date": manual_date}

        elif cmd == "clear_date":
            photo_id = params.get("photo_id")
            if not photo_id:
                return {"ok": False, "error": "photo_id required"}
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET manual_date = NULL WHERE photo_id = ?", (row[0],))
            db.sqlite.commit()
            return {"ok": True}

        elif cmd == "mark_deleted":
            photo_id = params.get("photo_id")
            if not photo_id:
                return {"ok": False, "error": "photo_id required"}
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET deleted = 1 WHERE photo_id = ?", (row[0],))
            db.sqlite.commit()
            return {"ok": True}

        elif cmd == "undelete":
            photo_id = params.get("photo_id")
            if not photo_id:
                return {"ok": False, "error": "photo_id required"}
            row = db.sqlite.execute("SELECT photo_id FROM photos WHERE photo_id = ? OR path LIKE ?", (photo_id, '%' + photo_id)).fetchone()
            if not row:
                return {"ok": False, "error": "Photo not found"}
            db.sqlite.execute("UPDATE photos SET deleted = 0 WHERE photo_id = ?", (row[0],))
            db.sqlite.commit()
            return {"ok": True}

        elif cmd == "update_persona":
            persona = db.update_persona(
                params.get("persona_id"),
                display_name=params.get("display_name"),
                comment=params.get("comment"),
                clear_display_name=params.get("clear_display_name", False),
                clear_comment=params.get("clear_comment", False),
            )
            if not persona:
                return {"ok": False, "error": "Person not found"}
            fc_map = db.face_count_map()
            return {"ok": True, "persona": dict(persona), "face_count": fc_map.get(persona["persona_id"], 0)}

        elif cmd == "merge_personas":
            source = params.get("source_persona_id")
            target = params.get("target_persona_id")
            if not source or not target:
                return {"ok": False, "error": "source_persona_id and target_persona_id required"}
            success = db.merge_personas(source, target)
            if success:
                db.invalidate_embeddings_for_persona(target)
                return {"ok": True}
            return {"ok": False, "error": "Failed to merge"}

        elif cmd == "add_catalog_root":
            import uuid
            root_id = str(uuid.uuid4())
            db.add_catalog_root(
                root_id=root_id,
                root_path=params.get("root_path", ""),
                alias=params.get("alias", ""),
            )
            return {"ok": True, "root_id": root_id}

        elif cmd == "delete_catalog_root":
            db.delete_catalog_root(params.get("root_id", ""))
            return {"ok": True}

        elif cmd == "update_catalog_root":
            db.update_catalog_root(
                params.get("root_id", ""),
                enabled=params.get("enabled"),
            )
            return {"ok": True}

        elif cmd == "add_edit":
            edit_id = db.add_edit(
                params.get("content_hash", ""),
                params.get("action", ""),
                params.get("params", {}),
            )
            return {"ok": True, "edit_id": edit_id}

        elif cmd == "clear_edits":
            db.clear_edits(params.get("content_hash", ""), params.get("action", ""))
            return {"ok": True}

        elif cmd == "remove_edit":
            db.remove_edit(params.get("edit_id"))
            return {"ok": True}

        elif cmd == "dedup_embeddings":
            before, after, removed = db.dedup_photo_embeddings()
            return {"ok": True, "before": before, "after": after, "removed": removed}

        elif cmd == "compact_embeddings":
            db.compact_photo_embeddings()
            return {"ok": True}

        elif cmd == "vacuum":
            before = os.path.getsize(str(Path(__file__).parent / "data" / "gallery.db"))
            db.sqlite.execute("VACUUM")
            after = os.path.getsize(str(Path(__file__).parent / "data" / "gallery.db"))
            return {"ok": True, "before": before, "after": after, "freed": before - after}

        else:
            return {"ok": False, "error": f"unknown db command: {cmd}"}
    except Exception as e:
        try:
            db.sqlite.rollback()
        except Exception:
            pass
        log(f"DB_CMD error: {cmd}: {e}")
        return {"ok": False, "error": str(e)}


_db_cmd_queue = []
_db_cmd_lock = threading.Lock()


def _on_db_cmd(payload, msg):
    try:
        data = json.loads(payload)
    except Exception:
        return
    with _db_cmd_lock:
        _db_cmd_queue.append(data)


def _process_db_cmds():
    with _db_cmd_lock:
        cmds = list(_db_cmd_queue)
        _db_cmd_queue.clear()
    for data in cmds:
        cmd = data.get("cmd", "")
        params = data.get("params", {})
        request_id = data.get("request_id", "")
        result = _execute_db_cmd(cmd, params)
        if request_id and _mq:
            from mqtt_client import db_result_topic
            _mq.publish(db_result_topic(request_id), result, retain=False)


def _collect_metrics():
    try:
        from system_monitor import collect_metrics
        db = get_db()
        data = collect_metrics()
        db.insert_system_metric(data)
    except Exception as e:
        log(f"METRICS error: {e}")


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
    root_path_arg = []
    if args.root:
        _r = get_db().get_catalog_root(args.root)
        if _r:
            root_path_arg = ["--dir", _r["root_path"]]

    os.makedirs(str(Path(__file__).parent / "logs"), exist_ok=True)
    set_flag()

    global _mq
    try:
        from mqtt_client import create_worker_mqtt, DB_CMD_TOPIC
        _mq = create_worker_mqtt("pipeline")
        _mq.subscribe(DB_CMD_TOPIC, _on_db_cmd)
    except Exception:
        _mq = None

    log("=" * 60)
    log(f"Pipeline loop started (batch={args.batch}, ingest={ingest_n}, describe={describe_n})")

    last_metrics = 0

    try:
        iteration = 0
        while not stopped():
            _process_db_cmds()

            now = time.time()
            if now - last_metrics >= 60:
                _collect_metrics()
                last_metrics = now

            iteration += 1
            progress = get_progress(root_id=args.root or None)

            log(f"--- Итерация {iteration} ---")
            for step, val in progress.items():
                if isinstance(val, tuple):
                    done, total, pct = val
                    log(f"  {step}: {done}/{total} ({pct:.1f}%)")
                else:
                    log(f"  {step}: {val}")

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
                sleep_until = time.time() + 300
                while time.time() < sleep_until and not stopped():
                    _process_db_cmds()
                    if time.time() - last_metrics >= 60:
                        _collect_metrics()
                        last_metrics = time.time()
                    time.sleep(5)
                try:
                    _idle_flag.unlink()
                except Exception:
                    pass
                continue

            if progress["describe"][2] < 100:
                db = get_db()
                _cur = db.sqlite.execute("UPDATE photos SET description='[видео]' WHERE media_type='video' AND (description IS NULL OR description='') AND deleted=0")
                if _cur.rowcount > 0:
                    db.sqlite.execute("UPDATE catalog_files SET described=1 WHERE abs_path IN (SELECT path FROM photos WHERE media_type='video' AND description='[видео]') AND is_canonical=1")
                    db.sqlite.commit()
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

            if not stopped():
                t0 = time.time()
                try:
                    db = get_db()
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
                sleep_until = time.time() + 30
                while time.time() < sleep_until and not stopped():
                    _process_db_cmds()
                    if time.time() - last_metrics >= 60:
                        _collect_metrics()
                        last_metrics = time.time()
                    time.sleep(2)

        log("Pipeline loop завершён")
    finally:
        clear_flag()
        if _mq:
            _mq.shutdown()


if __name__ == "__main__":
    main()
