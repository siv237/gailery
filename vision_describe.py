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
from config import LLAMA_CPP_DIR, MODELS_DIR, PHOTO_SHARE_PATH, VIDEO_EXTS
PROJECT_ROOT = Path(__file__).parent.resolve()

LLAMA_SERVER_BIN = str(LLAMA_CPP_DIR / "build" / "bin" / "llama-server")
MODEL_PATH = str(MODELS_DIR / "gguf" / "Qwen3.5-4B-Q4_K_M.gguf")
MMPROJ_PATH = str(MODELS_DIR / "gguf" / "mmproj-BF16.gguf")
LLAMA_PORT = 8101
NP_SLOTS = 6
CTX_SIZE = 16384

BATCH_SIZE = 6
MAX_NEW_TOKENS = 1024
SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
LOG_FILE = str(PROJECT_ROOT / "logs" / "pipeline.log")

_vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
LD_LIBRARY_PATH = ":".join([
    _vnvidia + "/cublas/lib",
    _vnvidia + "/cuda_runtime/lib",
    "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
    str(LLAMA_CPP_DIR / "build" / "bin"),
])

SYSTEM_PROMPT = """Ты описатель фотографий. Описывай только то что реально видно — без фантазии.
ВНИМАНИЕ: В данных ниже перечислены люди на фото С ИХ ИМЕНАМИ. Ты ОБЯЗАТЕЛЬНО используешь эти имена в описании.
Если в списке указано имя — ты пишешь это имя, а не 'женщина' или 'мужчина'.
Безымянные ('ещё N чел. без имени') — описывай по внешности.
Возраст — только если указан в данных рядом с именем. Не определяй возраст по внешности.
Если возраст указан и это девочка до 12 лет — пиши 'девочка', 13-17 — 'девушка', мальчик до 12 — 'мальчик', 13-17 — 'юноша'. Взрослых (18+) без возраста — 'женщина'/'мужчина'.
Только факты: кто, что делает, где, предметы. Без атмосферы, без эмоций, без 'вероятно'.
Без выдуманного повода. Без квадратных скобок. Начинай сразу текстом."""

_DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPT

def get_system_prompt():
    try:
        from database import get_db
        custom = get_db().get_setting("prompt_vlm_system")
        if custom:
            return custom
    except Exception:
        pass
    return _DEFAULT_SYSTEM_PROMPT


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


_AI_LOG_BATCH_ID = None

def describe_one(img_b64, photo_path, agent_context=""):
    from vlm_log import log_ai_call
    sys_prompt = get_system_prompt()
    _ch = ""
    try:
        from database import DatabaseManager as _DM
        _db = _DM()
        _r = _db.sqlite.execute("SELECT content_hash FROM catalog_files WHERE abs_path=? AND is_canonical=1 LIMIT 1", (str(photo_path),)).fetchone()
        if _r: _ch = _r[0] or ""
        _db.sqlite.close()
    except Exception:
        pass
    user_text = "Опиши что видно на фото. Перечисли видимые предметы, мебель, одежду, детали. Кто (имена из данных — используй обязательно). Не пиши про то чего не видно. Начинай сразу с описания, без скобок, без заголовка. Не короче 4 предложений. Возраст — только из данных, не угадывай по внешности. Девочка/девушка/женщина — по возрасту из данных."
    if agent_context:
        user_text += "\n\n" + agent_context
    data = {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                {"type": "text", "text": user_text},
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
        log_ai_call(
            call_type="vlm_describe",
            photo_path=str(photo_path),
            content_hash=_ch,
            batch_id=_AI_LOG_BATCH_ID,
            request_json={
                "url": f"http://localhost:{LLAMA_PORT}/v1/chat/completions",
                "method": "POST",
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,<{len(img_b64)} chars base64>"}},
                        {"type": "text", "text": user_text},
                    ]},
                ],
                "max_tokens": MAX_NEW_TOKENS,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
                "model": "Qwen3.5-4B-Q4_K_M",
                "image_bytes": len(img_b64),
            },
            response_json=result,
            agent_context=agent_context,
            parsed_result=parsed,
            elapsed_sec=round(elapsed, 2),
            success=1,
        )
        return photo_path, parsed, elapsed, pps, None
    except Exception as e:
        elapsed = time.time() - t0
        log_ai_call(
            call_type="vlm_describe",
            photo_path=str(photo_path),
            content_hash=_ch,
            batch_id=_AI_LOG_BATCH_ID,
            request_json=data,
            agent_context=agent_context,
            elapsed_sec=round(elapsed, 2),
            error=str(e),
            success=0,
        )
        return photo_path, None, elapsed, 0, str(e)


VLM_MAX_SIZE = 1280
VLM_JPEG_QUALITY = 85


def _bbox_to_position(bbox, img_width=3000):
    x_center = (bbox[0] + bbox[2]) / 2 / max(img_width, 1)
    if x_center < 0.33:
        return "слева"
    elif x_center > 0.67:
        return "справа"
    return "в центре"


def _get_photo_context(photo_path, db):
    if not db:
        return ""
    parts = []
    try:
        row = db.sqlite.execute(
            "SELECT p.manual_date, p.date, cr.alias "
            "FROM photos p "
            "LEFT JOIN catalog_files cf ON cf.abs_path = p.path AND cf.is_canonical = 1 "
            "LEFT JOIN catalog_roots cr ON cf.root_id = cr.root_id "
            "WHERE p.path = ? AND p.deleted = 0",
            (photo_path,)
        ).fetchone()
        if row:
            date_val = row[0] or row[1]
            if date_val:
                date_str = str(date_val)[:10]
                parts.append(f"Дата съёмки: {date_str}.")
            if row[2]:
                parts.append(f"Папка: {row[2]}.")
    except Exception:
        pass
    path = Path(photo_path)
    parent = path.parent.name
    if parent and not any(c in parent for c in ('DCIM', 'Camera', 'OpenCamera', '100ANDRO')):
        parts.append(f"Подпапка: {parent}.")
    return " ".join(parts)


_RU_MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
}


def _parse_birth_date(comment):
    """Парсит дату рождения из comment. Форматы: 'DD месяц YYYY', 'YYYY-MM-DD', 'YYYY год'."""
    import re
    if not comment:
        return None
    m = re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', comment)
    if m:
        return int(m.group(3)), _RU_MONTHS[m.group(2)], int(m.group(1))
    m = re.search(r'(\d{4})[-.](\d{2})[-.](\d{2})', comment)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.search(r'(\d{4})\s+год', comment, re.IGNORECASE)
    if m:
        return int(m.group(1)), 7, 1
    return None


def _calc_age(comment, photo_date=None):
    bd = _parse_birth_date(comment)
    if not bd or not photo_date:
        return None
    birth_year, birth_month, birth_day = bd
    try:
        pd = photo_date[:10]
        parts = pd.split('-')
        if len(parts) != 3:
            return None
        py, pm, pdd = int(parts[0]), int(parts[1]), int(parts[2])
    except Exception:
        return None

    total_months = (py - birth_year) * 12 + (pm - birth_month)
    if total_months < 0 or total_months >= 216:
        return None

    years = total_months // 12
    months = total_months % 12

    if years < 7:
        if years == 0:
            if months == 0: return "меньше месяца"
            if months == 1: return "1 месяц"
            elif months in (2,3,4): return f"{months} месяца"
            else: return f"{months} месяцев"
        elif months == 0:
            if years == 1: return "1 год"
            elif years in (2,3,4): return f"{years} года"
            else: return f"{years} лет"
        else:
            if years == 1: y_str = "1 год"
            elif years in (2,3,4): y_str = f"{years} года"
            else: y_str = f"{years} лет"
            if months == 1: m_str = "1 месяц"
            elif months in (2,3,4): m_str = f"{months} месяца"
            else: m_str = f"{months} месяцев"
            return f"{y_str} {m_str}"
    else:
        return f"{years} лет"


def _is_birthday(comment, photo_date):
    """Проверяет совпадает ли дата фото с днём рождения (месяц+день)."""
    bd = _parse_birth_date(comment)
    if not bd or not photo_date:
        return False
    _, birth_month, birth_day = bd
    try:
        pd = photo_date[:10]
        parts = pd.split('-')
        if len(parts) != 3:
            return False
        _, pm, pdd = int(parts[0]), int(parts[1]), int(parts[2])
        return pm == birth_month and pdd == birth_day
    except Exception:
        return False


def _get_face_context(content_hash, img_width, db, photo_date=None):
    if not content_hash or not db:
        return ""
    try:
        rows = db.sqlite.execute(
            "SELECT f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, p.display_name, p.comment "
            "FROM faces f LEFT JOIN personas p ON f.persona_id = p.persona_id "
            "WHERE f.content_hash = ?",
            (content_hash,)
        ).fetchall()
    except Exception:
        return ""
    if not rows:
        return ""
    parts = []
    named_count = 0
    unnamed_count = 0
    for r in rows:
        bbox = [r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0]
        pos = _bbox_to_position(bbox, img_width)
        name = r[4]
        comment = r[5] or ""
        if name:
            age_str = _calc_age(comment, photo_date)
            entry = f"{name} ({pos}"
            if age_str:
                entry += f", {age_str}"
            entry += ")"
            if comment:
                entry += f" [{comment}]"
            parts.append(entry)
            named_count += 1
        else:
            unnamed_count += 1
    lines = []
    if named_count > 0:
        lines.append(f"На фото обнаружены лица: {', '.join(parts)}.")
    if unnamed_count > 0:
        lines.append(f"Также {unnamed_count} лиц без имён.")
    if lines:
        lines.append("Используй имена в описании.")
    return " ".join(lines)


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
    return img_b64, None, w


def _build_agent_context(photo_path, db):
    if not db:
        return ""
    parts = []
    try:
        ch_row = db.sqlite.execute(
            "SELECT content_hash FROM catalog_files WHERE abs_path=? AND content_hash IS NOT NULL AND is_canonical=1 LIMIT 1",
            (photo_path,)).fetchone()
        if not ch_row:
            return ""
        content_hash = ch_row[0]
        photo = db.sqlite.execute(
            "SELECT COALESCE(manual_date, date) FROM photos WHERE path=? AND deleted=0 LIMIT 1",
            (photo_path,)).fetchone()
        photo_date = str(photo[0])[:10] if photo and photo[0] else None

        faces_done_row = db.sqlite.execute(
            "SELECT faces_done FROM catalog_files WHERE abs_path=? AND is_canonical=1 LIMIT 1",
            (photo_path,)).fetchone()
        faces_done = faces_done_row[0] if faces_done_row else 0

        rows = db.sqlite.execute(
            "SELECT f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, per.display_name, per.comment, per.persona_id "
            "FROM faces f LEFT JOIN personas per ON f.persona_id=per.persona_id WHERE f.content_hash=?",
            (content_hash,)).fetchall()

        img_w_row = db.sqlite.execute("SELECT img_width FROM photos WHERE path=? AND deleted=0 LIMIT 1", (photo_path,)).fetchone()
        img_width = img_w_row[0] if img_w_row and img_w_row[0] else 0
        if not img_width and rows:
            img_width = max((r[2] or 0) for r in rows) + 100
        if not img_width:
            img_width = 3000

        named = []
        named_names = []
        unnamed = 0
        if faces_done:
            for r in rows:
                name = r[4]
                comment = r[5] or ""
                pid = r[6]
                pos = _bbox_to_position([r[0] or 0, r[1] or 0, r[2] or 0, r[3] or 0], img_width)
                pcnt = 0
                if pid:
                    pc = db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE persona_id=?", (pid,)).fetchone()
                    pcnt = pc[0] if pc else 0
                age_str = _calc_age(comment, photo_date) if name and comment else None
                is_bday = _is_birthday(comment, photo_date) if name and comment else False
                bday_date = _parse_birth_date(comment) if name and comment else None

                if not comment and name and photo_date:
                    ff = db.get_setting("family_facts")
                    if ff:
                        for ff_line in ff.strip().split("\n"):
                            ff_line = ff_line.strip()
                            if ff_line.startswith(name):
                                age_str = _calc_age(ff_line, photo_date)
                                is_bday = _is_birthday(ff_line, photo_date)
                                bday_date = _parse_birth_date(ff_line)
                                comment = ff_line
                                break

                if name:
                    line = name
                    if pos: line += f" ({pos})"
                    if is_bday:
                        bday_str = f"{bday_date[2]:02d}.{bday_date[1]:02d}.{bday_date[0]}" if bday_date else ""
                        line += f", день рождения ({bday_str}, фото {photo_date})"
                        if age_str:
                            line += f", {age_str}"
                    elif age_str:
                        line += f", {age_str}"
                    named.append(line)
                    named_names.append(name)
                else:
                    unnamed += 1
        else:
            unnamed = len(rows)

        if named:
            for n in named:
                if ' (' in n:
                    nm = n.split(' (')[0]
                    rest = n[len(nm)+2:]
                    pos_str = rest.split(')')[0]
                    extra = rest.split(')',1)[1] if ')' in rest else ''
                    extra = extra.strip().lstrip(',').strip()
                    stmt = f"На фото {pos_str} — {nm}"
                    if extra:
                        stmt += f", {extra}"
                    stmt += "."
                    parts.append(stmt)
                else:
                    parts.append(f"На фото — {n}.")
        if unnamed:
            parts.append(f"Также на фото ещё {unnamed} чел. без имени.")

        if faces_done and named_names:
            ff = db.get_setting("family_facts")
            if ff:
                import re as _re
                ff_lines = []
                for line in ff.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    matched = False
                    for nn in named_names:
                        if nn and line.startswith(nn):
                            matched = True
                            break
                    if not matched:
                        continue
                    if photo_date:
                        m = _re.search(r'(\d{1,2})\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})', line)
                        if m:
                            line = _re.sub(r'\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4}', '', line).strip()
                            line = _re.sub(r'\s+', ' ', line).strip()
                    ff_lines.append(line)
                log(f"  DEBUG family_facts filter: named_names={named_names}, ff_total={len(ff.strip().split(chr(10)))}, ff_matched={len(ff_lines)}")
                if ff_lines:
                    parts.append("Семья:")
                    parts.extend(ff_lines)

        alias_row = db.sqlite.execute(
            "SELECT cr.alias FROM catalog_roots cr JOIN catalog_files cf ON cf.root_id=cr.root_id WHERE cf.abs_path=? AND cf.is_canonical=1 LIMIT 1",
            (photo_path,)).fetchone()
        if alias_row and alias_row[0]:
            parts.append(f"Папка: {alias_row[0]}")
        if photo_date:
            parts.append(f"Дата съёмки: {photo_date}")

    except Exception:
        pass
    return "\n".join(parts)


def describe_batch(image_paths, db=None):
    import uuid as _uuid
    global _AI_LOG_BATCH_ID
    _AI_LOG_BATCH_ID = str(_uuid.uuid4())[:8]
    images_b64 = []
    valid_paths = []
    invalid_paths = []
    agent_contexts = []
    for p in image_paths:
        try:
            fsize = os.path.getsize(p)
            if fsize < 1024:
                log(f"  Skip {p}: too small ({fsize} bytes)")
                invalid_paths.append(p)
                continue
            img_b64, err, img_w = prepare_image(p)
            if err:
                log(f"  Skip {p}: not an image ({err})")
                invalid_paths.append(p)
                continue
            ac = _build_agent_context(str(p), db) if db else ""
            images_b64.append(img_b64)
            valid_paths.append(p)
            agent_contexts.append(ac)
        except Exception as e:
            log(f"  Cannot read {p}: {e}")
            invalid_paths.append(p)

    results = []
    for p in invalid_paths:
        results.append((p, {
            "description": "[не изображение: файл повреждён или не является фото]",
            "photo_type": "other", "has_faces": False, "has_issues": True, "issue_type": "corrupted",
        }))

    if not valid_paths:
        return results
    with ThreadPoolExecutor(max_workers=NP_SLOTS) as pool:
        futs = {pool.submit(describe_one, images_b64[i], valid_paths[i], agent_contexts[i]): i for i in range(len(valid_paths))}
        for fut in as_completed(futs):
            path, parsed, elapsed, pps, err = fut.result()
            if err:
                log(f"  API error for {path}: {err}")
                results.append((path, {
                    "description": f"[VLM error: {err}]", "photo_type": "other",
                    "has_faces": False, "has_issues": True, "issue_type": "other",
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


def get_undescribed_photos(db, photo_dir, limit=0, content_hash=None):
    cur = db.sqlite.cursor()
    where_extra = ""
    params = []
    if photo_dir:
        where_extra = " AND cf.abs_path LIKE ?"
        params.append(str(photo_dir) + "/%")
    if content_hash:
        where_extra += " AND cf.content_hash = ?"
        params.append(content_hash)
    sql = ("SELECT p.path FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path "
           "WHERE (p.description IS NULL OR p.description = '' OR cf.described = 0) AND p.deleted = 0 "
           "AND cf.is_canonical = 1 AND (p.media_type IS NULL OR p.media_type != 'video')" + where_extra + " ORDER BY RANDOM()")
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
            faces_done_row = db.sqlite.execute(
                "SELECT faces_done FROM catalog_files WHERE abs_path = ? AND is_canonical = 1 LIMIT 1",
                (path_str,)
            ).fetchone()
            faces_done = faces_done_row[0] if faces_done_row else 0
            if faces_done:
                faces_present_val = photo.get("faces_present", 0)
            else:
                faces_present_val = int(parsed["has_faces"])
            db.update_photo(
                photo["photo_id"],
                description=parsed["description"],
                faces_present=faces_present_val,
                has_issues=int(parsed["has_issues"]),
                issue_type=parsed.get("issue_type"),
                photo_type=parsed.get("photo_type", "photo"),
            )
            db.sqlite.execute("UPDATE photos SET embedded = 0 WHERE photo_id = ?", (photo["photo_id"],))
            db.sqlite.commit()
            db.update_catalog_file_by_path(path_str, described=1)
        else:
            print(f"[WARN] Photo not in DB, skipping: {path_str}", flush=True)
    except Exception as e:
        print(f"[WARN] DB save failed for {path_str}: {e}", flush=True)


def process_single(photo_path):
    db = get_db()
    server = start_llama_server()
    if not server:
        print("Failed to start llama-server", flush=True)
        return
    try:
        results = describe_batch([photo_path], db=db)
        for path, parsed in results:
            print(f"DESC:{parsed['description']}", flush=True)
            print(f"FACES:{parsed['has_faces']}", flush=True)
            print(f"ISSUES:{parsed['has_issues']}", flush=True)
            save_description(db, path, parsed)
    finally:
        stop_llama_server(server)


def process_directory(photo_dir, batch_size=BATCH_SIZE, limit=0, content_hash=None):
    db = get_db()

    photos = get_undescribed_photos(db, photo_dir, limit, content_hash=content_hash)
    total = len(photos)

    if total == 0:
        log("No new photos to describe")
        return

    from database import DatabaseManager
    db2 = DatabaseManager()
    total_undescribed = db2.sqlite.execute(
        "SELECT COUNT(*) FROM photos p JOIN catalog_files cf ON cf.abs_path = p.path "
        "WHERE (p.description IS NULL OR p.description = '' OR cf.described = 0) AND p.deleted = 0 AND cf.is_canonical = 1"
    ).fetchone()[0]
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
                results = describe_batch(batch_paths, db=db)
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
                    if ext in VIDEO_EXTS:
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
    parser.add_argument("--hash", type=str, default="", help="Process single photo by content_hash")
    parser.add_argument("--no-gpu-lock", action="store_true", help="Skip GPU lock acquire (already held by caller)")
    args = parser.parse_args()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("describe")
        if not args.no_gpu_lock and mq:
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
        process_directory(args.path, batch_size=args.batch_size, limit=args.limit, content_hash=args.hash or None)

    if mq:
        mq.release_gpu()
        mq.shutdown()


if __name__ == "__main__":
    main()
