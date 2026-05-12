#!/usr/bin/env python3
"""
vision_describe.py - Batch image description with Qwen3.5-4B via llama.cpp.
Extracts: description, faces present, image issues (blur, corrupted, not_photo).

Uses llama-server on-demand: starts, processes batch of 6 parallel, stops.
No persistent server, no VRAM waste between runs.

Usage:
    python vision_describe.py /path/to/photos/some_dir
    python vision_describe.py /path/to/photos/some_dir --batch-size 6
    python vision_describe.py --single /path/to/photos/photo.jpg
"""

import argparse
import base64
import io
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import LLAMA_CPP_DIR, MODELS_DIR, PHOTO_SHARE_PATH
PROJECT_ROOT = Path(__file__).parent.resolve()

LLAMA_SERVER_BIN = str(LLAMA_CPP_DIR / "build" / "bin" / "llama-server")
MODEL_PATH = str(MODELS_DIR / "gguf" / "Qwen3.5-4B-Q4_K_M.gguf")
MMPROJ_PATH = str(MODELS_DIR / "gguf" / "mmproj-BF16.gguf")
LLAMA_PORT = 8101
NP_SLOTS = 6
CTX_SIZE = 8192

BATCH_SIZE = 6
MAX_NEW_TOKENS = 256
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
LOG_FILE = str(PROJECT_ROOT / "logs" / "pipeline.log")

_vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
LD_LIBRARY_PATH = ":".join([
    _vnvidia + "/cublas/lib",
    _vnvidia + "/cuda_runtime/lib",
    "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
    str(LLAMA_CPP_DIR / "build" / "bin"),
])

SYSTEM_PROMPT = """Ты — автоматический анализатор фотографий. Анализируй изображение и вызови функцию describe_photo с результатами.

Обрати внимание:
- description: что происходит на фото, кто изображён, где, настроение. Пиши на русском.
- photo_type: классификация изображения. photo = обычная фотография, screenshot = скриншот экрана, document = документ/квитанция/скан/чек/сертификат/объявление, meme = мем/карточка с текстом, icon = иконка/аватарка, other = всё остальное
- has_faces: true если видны лица людей (даже частично), false если нет людей или лица не видны
- has_issues: true если фото с проблемой — размыто, битое, пересвет, слишком тёмное
- issue_type: укажи тип проблемы только если has_issues=true

Если photo_type=document или на фото виден документ/чек/квитанция/сертификат/объявление/расписание:
- В description полностью перепиши весь распознанный текст с документа, сохраняя структуру (абзацы, таблицы, списки).
- Укажи тип документа (чек, квитанция, сертификат, диплом, объявление, расписание и т.д.).
- Если есть суммы, даты, номера, имена — все обязательно перепиши точно.
- Если текст частично не виден или размыт — укажи что именно не удалось разобрать."""


def log(msg):
    line = f"[{datetime.now().isoformat()}] [VLM] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def start_llama_server():
    kill_orphan_servers()
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH

    proc = subprocess.Popen(
        [
            LLAMA_SERVER_BIN,
            "-m", MODEL_PATH,
            "--mmproj", MMPROJ_PATH,
            "-ngl", "99",
            "--no-mmap",
            "-c", str(CTX_SIZE),
            "--image-max-tokens", "512",
            "--port", str(LLAMA_PORT),
            "-np", str(NP_SLOTS),
            "-t", "4",
            "-n", str(MAX_NEW_TOKENS),
            "--temp", "0.1",
            "-fit", "off",
            "-ctk", "q4_0",
            "-ctv", "q4_0",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    log(f"Starting llama-server (pid={proc.pid}, np={NP_SLOTS}, ctx={CTX_SIZE})...")
    for i in range(90):
        try:
            resp = urllib.request.urlopen(f"http://localhost:{LLAMA_PORT}/health", timeout=3)
            if json.loads(resp.read())["status"] == "ok":
                log(f"llama-server ready ({i+1}s)")
                return proc
        except Exception:
            time.sleep(1)

    log("llama-server FAILED to start")
    proc.kill()
    proc.wait()
    return None


def kill_orphan_servers():
    import subprocess
    try:
        result = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True, text=True)
        for pid_str in result.stdout.strip().split():
            pid = int(pid_str)
            if pid != os.getpid():
                try:
                    cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
                    if f"--port {LLAMA_PORT}" in cmdline or f"--port\n{LLAMA_PORT}" in cmdline:
                        os.kill(pid, 9)
                        log(f"Killed orphan llama-server on port {LLAMA_PORT} pid={pid}")
                except (ProcessLookupError, FileNotFoundError):
                    pass
    except Exception:
        pass


def stop_llama_server(proc):
    if proc is None:
        return
    log("Stopping llama-server...")
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    log("llama-server stopped")


def describe_one(img_b64, photo_path):
    data = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": "Проанализируй эту фотографию."},
            ]},
        ],
        "max_tokens": MAX_NEW_TOKENS,
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(
        f"http://localhost:{LLAMA_PORT}/v1/chat/completions",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        result = json.loads(resp.read())
        elapsed = time.time() - t0
        content = result["choices"][0]["message"].get("content", "")
        pps = result.get("timings", {}).get("predicted_per_second", 0)
        parsed = parse_tool_call(content)
        return photo_path, parsed, elapsed, pps, None
    except Exception as e:
        elapsed = time.time() - t0
        return photo_path, None, elapsed, 0, str(e)


VLM_MAX_SIZE = 1280
VLM_JPEG_QUALITY = 85


def prepare_image(path):
    from PIL import Image
    try:
        img = Image.open(path)
        img.verify()
        img = Image.open(path)
    except Exception:
        return None, "corrupted"
    try:
        if hasattr(img, '_getexif'):
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    w, h = img.size
    if w == 0 or h == 0:
        return None, "corrupted"
    max_dim = max(w, h)
    if max_dim > VLM_MAX_SIZE:
        scale = VLM_MAX_SIZE / max_dim
        new_w = int(w * scale)
        new_h = int(h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=VLM_JPEG_QUALITY)
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return img_b64, None


def describe_batch(image_paths):
    images_b64 = []
    valid_paths = []
    invalid_paths = []
    for p in image_paths:
        try:
            fsize = os.path.getsize(p)
            if fsize < 1024:
                log(f"  Skip {p}: too small ({fsize} bytes)")
                invalid_paths.append(p)
                continue
            img_b64, err = prepare_image(p)
            if err:
                log(f"  Skip {p}: not an image ({err})")
                invalid_paths.append(p)
                continue
            images_b64.append(img_b64)
            valid_paths.append(p)
        except Exception as e:
            log(f"  Cannot read {p}: {e}")
            invalid_paths.append(p)

    results = []
    for p in invalid_paths:
        results.append((p, {
            "description": "[не изображение: файл повреждён или не является фото]",
            "photo_type": "other",
            "has_faces": False,
            "has_issues": True,
            "issue_type": "corrupted",
        }))

    if not valid_paths:
        return results
    with ThreadPoolExecutor(max_workers=NP_SLOTS) as pool:
        futs = {pool.submit(describe_one, images_b64[i], valid_paths[i]): i for i in range(len(valid_paths))}
        for fut in as_completed(futs):
            path, parsed, elapsed, pps, err = fut.result()
            if err:
                log(f"  API error for {path}: {err}")
                results.append((path, {
                    "description": f"[VLM error: {err}]",
                    "photo_type": "other",
                    "has_faces": False,
                    "has_issues": True,
                    "issue_type": "other",
                }))
            else:
                results.append((path, parsed))

    return results


def strip_md_fences(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r'^```\w*\s*\n?', '', raw)
        raw = re.sub(r'\n?\s*```\s*$', '', raw)
    return raw.strip()


def parse_tool_call(raw):
    result = {
        "description": "",
        "photo_type": "photo",
        "has_faces": False,
        "has_issues": False,
        "issue_type": None,
    }

    raw = strip_md_fences(raw)

    params = {}
    for m in re.finditer(r'<parameter=(\w+)>\s*([\s\S]*?)\s*</parameter>', raw):
        key = m.group(1)
        val = m.group(2).strip()
        params[key] = val

    if "description" in params:
        result["description"] = params["description"]
        result["photo_type"] = params.get("photo_type", "photo")
        result["has_faces"] = params.get("has_faces", "False").lower() in ("true", "да")
        result["has_issues"] = params.get("has_issues", "False").lower() in ("true", "да")
        if result["has_issues"] and params.get("issue_type"):
            result["issue_type"] = params["issue_type"].strip()
        return result

    try:
        m = re.search(r'\{[\s\S]*"description"[\s\S]*\}', raw)
        if m:
            data = json.loads(m.group(0))
            result["description"] = data.get("description", "")
            result["photo_type"] = data.get("photo_type", "photo")
            result["has_faces"] = bool(data.get("has_faces", False))
            result["has_issues"] = bool(data.get("has_issues", False))
            result["issue_type"] = data.get("issue_type")
            return result
    except (json.JSONDecodeError, AttributeError):
        pass

    for line in raw.split("\n"):
        line = line.strip()
        if line.upper().startswith("ОПИСАНИЕ:"):
            result["description"] = line[len("ОПИСАНИЕ:"):].strip()
        elif line.upper().startswith("ЛИЦА:"):
            val = line[len("ЛИЦА:"):].strip().upper()
            result["has_faces"] = val.startswith("Д")
        elif line.upper().startswith("ПРОБЛЕМА:"):
            val = line[len("ПРОБЛЕМА:"):].strip().upper()
            result["has_issues"] = val.startswith("Д")

    if not result["description"]:
        result["description"] = raw.strip()

    return result


def get_db():
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from database import DatabaseManager
    return DatabaseManager()


def get_undescribed_photos(db, photo_dir, limit=0):
    cur = db.sqlite.cursor()
    where_extra = ""
    params = []
    if photo_dir:
        where_extra = " AND cf.abs_path LIKE ?"
        params.append(str(photo_dir) + "/%")
    sql = ("SELECT p.path FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path "
           "WHERE (p.description IS NULL OR p.description = '') AND p.deleted = 0 "
           "AND cf.is_canonical = 1" + where_extra + " ORDER BY RANDOM()")
    if limit > 0:
        sql += f" LIMIT {limit}"
    rows = cur.execute(sql, params).fetchall()
    result = []
    for r in rows:
        if Path(r[0]).exists():
            result.append(Path(r[0]))
    return result


def save_description(db, photo_path, parsed):
    path_str = str(photo_path)
    try:
        photo = db.get_photo_by_path(path_str)
        if photo:
            db.update_photo(
                photo["photo_id"],
                description=parsed["description"],
                faces_present=int(parsed["has_faces"]),
                has_issues=int(parsed["has_issues"]),
                issue_type=parsed.get("issue_type"),
                photo_type=parsed.get("photo_type", "photo"),
            )
            db.sqlite.execute("UPDATE photos SET embedded = 0 WHERE photo_id = ?", (photo["photo_id"],))
            db.sqlite.commit()
            db.update_catalog_file_by_path(path_str, described=1, faces_done=int(parsed["has_faces"]))
        else:
            print(f"[WARN] Photo not in DB, skipping: {path_str}", flush=True)
    except Exception as e:
        print(f"[WARN] DB save failed for {path_str}: {e}", flush=True)


def process_single(photo_path):
    server = start_llama_server()
    if not server:
        print("Failed to start llama-server", flush=True)
        return
    try:
        results = describe_batch([photo_path])
        for path, parsed in results:
            print(f"DESC:{parsed['description']}", flush=True)
            print(f"FACES:{parsed['has_faces']}", flush=True)
            print(f"ISSUES:{parsed['has_issues']}", flush=True)
    finally:
        stop_llama_server(server)


def process_directory(photo_dir, batch_size=BATCH_SIZE, limit=0):
    db = get_db()

    photos = get_undescribed_photos(db, photo_dir, limit)
    total = len(photos)

    if total == 0:
        log("No new photos to describe")
        return

    from database import DatabaseManager
    db2 = DatabaseManager()
    total_undescribed = db2.count_photos("description IS NULL OR description = ''")
    total_all = db2.count_photos()
    described_pct = (total_all - total_undescribed) / total_all * 100 if total_all else 0

    log(f"Start: {total} photos to describe, batch={batch_size}, np={NP_SLOTS}")
    log(f"Progress: {total_undescribed}/{total_all} undescribed ({described_pct:.1f}% described)")

    server = start_llama_server()
    if not server:
        log("Failed to start llama-server, aborting")
        return

    total_gen_tokens = 0
    total_time = 0.0
    processed = 0
    failed = 0
    faces_found = 0
    issues_found = 0
    global_t0 = time.time()

    try:
        for batch_start in range(0, total, batch_size):
            batch_paths = photos[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size

            t0 = time.time()
            try:
                results = describe_batch(batch_paths)
            except Exception as e:
                log(f"Batch {batch_num} FAILED: {e}")
                failed += len(batch_paths)
                continue
            elapsed = time.time() - t0

            batch_gen_tokens = 0
            for path, parsed in results:
                if parsed["description"].startswith("[VLM error:"):
                    failed += 1
                    continue
                t_save = time.time()
                save_description(db, path, parsed)
                if parsed.get("issue_type") == "corrupted":
                    ext = os.path.splitext(str(path))[1].lower()
                    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp", ".wmv", ".mpg", ".mpeg", ".m4v", ".flv", ".vob", ".ts"}:
                        db.sqlite.execute("UPDATE photos SET media_type = 'video', description = '[видео]', faces_present = 0 WHERE path = ? AND deleted = 0", (str(path),))
                        db.sqlite.commit()
                        db.update_catalog_file_by_path(str(path), described=1, faces_done=0)
                        log(f"    set media_type=video (not an image), description='[видео]'")
                        continue
                    db.sqlite.execute("UPDATE photos SET deleted = 1 WHERE path = ? AND deleted = 0", (str(path),))
                    db.sqlite.execute("UPDATE catalog_files SET deleted = 1, deleted_type = 'auto_corrupted' WHERE abs_path = ? AND deleted = 0", (str(path),))
                    db.sqlite.commit()
                    log(f"    marked as deleted (corrupted file)")
                dt_save = time.time() - t_save
                processed += 1
                desc_len = len(parsed["description"])
                desc_words = len(parsed["description"].split())
                face_mark = "F" if parsed["has_faces"] else " "
                issue_mark = "I" if parsed["has_issues"] else " "
                if parsed["has_faces"]: faces_found += 1
                if parsed["has_issues"]: issues_found += 1

                rel = str(path).replace(str(PHOTO_SHARE_PATH) + "/", "")
                log(f"  {face_mark}{issue_mark} [{processed}/{total}] {rel}")
                log(f"    desc ({desc_words}w): {parsed['description'][:120]}...")
                if parsed['has_issues']:
                    log(f"    issue: {parsed.get('issue_type', '?')}, type: {parsed.get('photo_type', '?')}")
                log(f"    save={dt_save:.2f}s")

                batch_gen_tokens += desc_words
                total_gen_tokens += desc_words

            total_time += elapsed
            agg_tps = batch_gen_tokens / elapsed if elapsed > 0 else 0
            cum_tps = total_gen_tokens / total_time if total_time > 0 else 0

            remaining_photos = total - processed - failed
            if processed > 0:
                avg_per_photo = total_time / processed
                eta_min = remaining_photos * avg_per_photo / 60
            else:
                eta_min = -1

            log(f"  Batch {batch_num}/{total_batches}: {elapsed:.1f}s, {agg_tps:.1f} word/s, cumulative {cum_tps:.1f} w/s")
            log(f"  Stats: {processed}/{total} done, {faces_found} faces, {issues_found} issues, {failed} failed")
            if eta_min > 0:
                log(f"  ETA: ~{eta_min:.0f} min remaining")

    finally:
        stop_llama_server(server)

    global_elapsed = time.time() - global_t0
    db3 = DatabaseManager()
    final_undescribed = db3.count_photos("description IS NULL OR description = ''")
    final_all = db3.count_photos()
    final_pct = (final_all - final_undescribed) / final_all * 100 if final_all else 0

    log(f"=")
    log(f"DONE: {processed}/{total} described, {failed} failed, {faces_found} faces, {issues_found} issues")
    log(f"Time: {global_elapsed:.0f}s ({processed/max(global_elapsed,1):.2f} photo/s, {total_gen_tokens/max(global_elapsed,1):.1f} word/s)")
    log(f"Overall: {final_undescribed}/{final_all} remaining ({final_pct:.1f}% described)")
    log(f"=")


def main():
    parser = argparse.ArgumentParser(description="Batch image description - Qwen3.5-4B via llama.cpp")
    parser.add_argument("path", nargs="?", default="", help="Directory with photos or single photo path")
    parser.add_argument("--single", action="store_true", help="Process single photo")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Batch size (default: {BATCH_SIZE})")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of photos (0=all)")
    args = parser.parse_args()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("describe")
        if not mq.acquire_gpu(timeout=60):
            log("GPU занят, describe не может запуститься")
            if mq:
                mq.shutdown()
            return
    except Exception:
        mq = None

    if args.single:
        process_single(args.path)
    else:
        process_directory(args.path, batch_size=args.batch_size, limit=args.limit)

    if mq:
        mq.release_gpu()
        mq.shutdown()


if __name__ == "__main__":
    main()
