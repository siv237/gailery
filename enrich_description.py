#!/usr/bin/env python3
"""
enrich_description.py - Generate rich description with named persons using LLM.

Combines VLM description + face/persona data + folder context into a prompt
for text-only LLM with tool-calling. The model can query:
- get_persona_info: how many photos, comment
- get_folder_context: what other personas appear in this folder
- get_nearby_photos: what faces appear in photos nearby by date

Usage:
    python enrich_description.py --photo "/path/to/photo.jpg"
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))
from config import LLAMA_CPP_DIR, PHOTO_SHARE_PATH
PROJECT_ROOT = Path(__file__).parent.resolve()

LLAMA_SERVER_BIN = str(LLAMA_CPP_DIR / "build" / "bin" / "llama-server")
MODEL_PATH = str(PROJECT_ROOT / "gguf" / "Qwen3.5-4B-Q4_K_M.gguf")
LLAMA_PORT = 8103

LOG_FILE = str(PROJECT_ROOT / "logs" / "pipeline.log")

_vnvidia = str(PROJECT_ROOT / "venv" / "lib" / "python3.12" / "site-packages" / "nvidia")
LD_LIBRARY_PATH = ":".join([
    _vnvidia + "/cublas/lib",
    _vnvidia + "/cuda_runtime/lib",
    "/usr/local/cuda-12.6/targets/x86_64-linux/lib",
    str(LLAMA_CPP_DIR / "build" / "bin"),
])

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_persona_info",
            "description": "Get info about a persona: how many photos they appear in, display name, comment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "persona_id": {
                        "type": "string",
                        "description": "persona_id from the faces list (e.g. cluster_62, persona_1259)"
                    }
                },
                "required": ["persona_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_folder_context",
            "description": "Get info about the photo folder: what named personas appear there, how many photos total.",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "Folder path like '2007/2007_12_15 - Сидоровы и Друзья'"
                    }
                },
                "required": ["folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_nearby_photos",
            "description": "Get faces from photos taken around the same time (±1 hour). Useful to find who was present at the event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date/time of the current photo in ISO format"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_family_facts",
            "description": "Search family facts: relationships, dates, events. Query by name or keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name or keyword, e.g. 'Иванова Виктория' or 'крёстный'"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

SYSTEM_PROMPT = """Ты — душа семейного архива. Ты знаешь эту семью как родную, помнишь каждого по имени, понимаешь что для них важно. Твоя задача — описать фото так, чтобы через 20 лет семья узнала: кто, что за повод, какие чувства. Ты пишешь не для машины, а для людей, которые любят друг друга.

Формат: [Событие, дата]. Краткое живое описание с именами.

Событие — из названия папки: "др Сергея" -> день рождения Сергея, "свадьба" -> свадьба, "медовый месяц" -> медовый месяц, "купаемся с мамой" -> купание, "парк Динамо с папой" -> прогулка с папой, "Крестины Алисы" -> крестины Алисы и т.д.

Инструменты: get_persona_info, get_folder_context, get_nearby_photos, search_family_facts — вызывай если нужно уточнить. Для детей вызови search_family_facts чтобы узнать возраст.

ИМЕНА — святое:
Каждое лицо с именем ОБЯЗАТЕЛЬНО упомянуть по имени. Это люди, не "мужчины" и "женщины".
"фото" в списке = сколько фото с этим человеком. Больше фото = ты увереннее в имени.
Безымянные — "мужчина"/"женщина"/"ребёнок", но с сочувствием.

Замена: "мужчина"/"женщина"/"девочка"/"мальчик"/"младенец"/"ребёнок" -> имя.
  "женщина в синей куртке" + "Петрова Мария" -> "Петрова Мария в синей куртке".
  НЕ "женщина Петрова". "смотрит на женщину" -> "смотрит на Петрову Марию".
  Имя ТОЧНО из списка — не искажай.
  Даже если "лицо не видно" — имя подставляй, лицо распознано!

Позиция: слева/в центре/справа (по bbox x).
Лиц >5 — основных по имени, остальных "и ещё N человек".
Не придумывай факты. Только из описания, данных инструментов и семейных фактов.
НЕ приписывай эмоции, чувства, выражения лиц — если в исходном описании этого нет.
НЕ придумывай повод — только из названия папки.
Если есть дата рождения из фактов — обязательно вычисли и укажи возраст ребёнка на момент фото. Пример: фото 2010-10-04, рождение 2009-05-07 → «Алиса, 1 год».
Опиши подробно что видно: кто, где стоит/сидит, что вокруг. Сохрани всё существенное из исходного описания, но с именами и связями."""


def log(msg):
    line = f"[{datetime.now().isoformat()}] [ENRICH] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_photo_data(db, photo_path):
    photo = db.get_photo_by_path(photo_path)
    if not photo:
        return None

    photo_id = photo["photo_id"]

    rel_path = photo_path
    _foto_prefix = str(PHOTO_SHARE_PATH) + "/"
    if photo_path.startswith(_foto_prefix):
        rel_path = photo_path[len(_foto_prefix):]

    faces_raw = db.sqlite.execute(
        "SELECT f.face_id, f.persona_id, f.bbox_x1, f.bbox_y1, f.bbox_x2, f.bbox_y2, f.confidence, "
        "per.display_name, per.comment "
        "FROM faces f LEFT JOIN personas per ON f.persona_id = per.persona_id "
        "WHERE f.photo_id = ? OR f.photo_id = ? OR f.photo_id = ? "
        "OR f.photo_id LIKE ? "
        "ORDER BY f.bbox_x1",
        (photo_id, photo_path, rel_path, '%' + os.path.basename(photo_path))
    ).fetchall()

    faces = []
    for f in faces_raw:
        name = f[7] or None
        comment = f[8] or None
        x1, y1, x2, y2 = f[1+1], f[2+1], f[3+1], f[4+1]
        conf = f[6]
        pid = f[1]
        photo_count = 0
        if pid:
            row = db.sqlite.execute("SELECT COUNT(*) FROM faces WHERE persona_id = ?", (pid,)).fetchone()
            if row:
                photo_count = row[0]
        faces.append({
            "persona_id": pid,
            "name": name,
            "comment": comment,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "confidence": conf,
            "photo_count": photo_count,
        })

    folder = ""
    _foto_prefix = str(PHOTO_SHARE_PATH) + "/"
    if photo_path.startswith(_foto_prefix):
        after = photo_path[len(_foto_prefix):]
        fparts = after.split("/")
        if len(fparts) >= 1:
            folder = fparts[0]
        if len(fparts) >= 2:
            folder += "/" + fparts[1]

    return {
        "description": photo.get("description", ""),
        "folder": folder,
        "date": photo.get("manual_date") or photo.get("date", ""),
        "faces": faces,
        "photo_id": photo_id,
    }


def format_faces(faces, img_width=None):
    if not faces:
        return "Лица не распознаны"

    lines = []
    for f in faces:
        x1 = f["x1"] or 0
        name = f["name"] or "(без имени)"
        pid = f.get("persona_id", "")
        comment = f" ({f['comment']})" if f.get("comment") else ""
        conf = f.get("confidence", 0)

        if img_width and img_width > 0:
            rel_x = x1 / img_width
            if rel_x < 0.33:
                pos = "слева"
            elif rel_x < 0.66:
                pos = "в центре"
            else:
                pos = "справа"
        else:
            if x1 < 1000:
                pos = "слева"
            elif x1 < 2000:
                pos = "в центре"
            else:
                pos = "справа"

        photo_count = f.get("photo_count", 0)
        lines.append(f"  - {name}{comment}, id={pid}, позиция: {pos} (x={x1:.0f}, фото={photo_count}, уверенность={conf:.2f})")

    return "\n".join(lines)


def execute_tool(db, tool_name, arguments):
    if tool_name == "get_persona_info":
        pid = arguments.get("persona_id", "")
        row = db.sqlite.execute(
            "SELECT display_name, comment FROM personas WHERE persona_id = ?",
            (pid,)
        ).fetchone()
        if not row:
            return json.dumps({"error": f"Persona {pid} not found"})
        count = db.sqlite.execute(
            "SELECT COUNT(*) FROM faces WHERE persona_id = ?",
            (pid,)
        ).fetchone()[0]
        result = {"persona_id": pid, "display_name": row[0], "comment": row[1], "photo_count": count}
        log(f"Tool get_persona_info({pid}) -> {result}")
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "get_folder_context":
        folder = arguments.get("folder", "")
        folder_like = "%" + folder.split("/")[-1] + "%"
        rows = db.sqlite.execute(
            "SELECT f.persona_id, per.display_name, COUNT(*) as cnt "
            "FROM faces f LEFT JOIN personas per ON f.persona_id = per.persona_id "
            "WHERE f.photo_id LIKE ? AND per.display_name IS NOT NULL "
            "GROUP BY f.persona_id ORDER BY cnt DESC LIMIT 5",
            (folder_like,)
        ).fetchall()
        personas = [{"persona_id": r[0], "name": r[1], "faces": r[2]} for r in rows]
        photo_count = db.sqlite.execute(
            "SELECT COUNT(DISTINCT f.photo_id) FROM faces f WHERE f.photo_id LIKE ?",
            (folder_like,)
        ).fetchone()[0]
        result = {"folder": folder, "photo_count": photo_count, "named_personas": personas}
        log(f"Tool get_folder_context({folder}) -> {len(personas)} personas")
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "get_nearby_photos":
        date_str = arguments.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return json.dumps({"error": f"Cannot parse date: {date_str}"})

        from datetime import timedelta
        dt_min = (dt - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        dt_max = (dt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")

        rows = db.sqlite.execute(
            "SELECT p.path, COALESCE(p.manual_date, p.date), f.persona_id, per.display_name "
            "FROM photos p JOIN faces f ON f.photo_id LIKE '%' || SUBSTR(p.path, LENGTH('" + str(PHOTO_SHARE_PATH) + "/')+1) "
            "LEFT JOIN personas per ON f.persona_id = per.persona_id "
            "WHERE COALESCE(p.manual_date, p.date) BETWEEN ? AND ? AND per.display_name IS NOT NULL "
            "ORDER BY COALESCE(p.manual_date, p.date) LIMIT 30",
            (dt_min, dt_max)
        ).fetchall()
        photos = {}
        for r in rows:
            ppath = r[0]
            if ppath not in photos:
                photos[ppath] = {"date": r[1], "faces": []}
            photos[ppath]["faces"].append({"persona_id": r[2], "name": r[3]})
        result = {"nearby_photos": list(photos.values())}
        log(f"Tool get_nearby_photos({date_str}) -> {len(photos)} photos")
        return json.dumps(result, ensure_ascii=False)

    elif tool_name == "search_family_facts":
        query = arguments.get("query", "").strip().lower()
        if not query:
            return json.dumps({"results": []})
        facts_text = db.get_setting("family_facts", "")
        if not facts_text:
            return json.dumps({"results": []})
        matches = []
        for line in facts_text.split("\n"):
            if query in line.lower():
                matches.append(line.strip())
        result = {"results": matches[:10]}
        log(f"Tool search_family_facts({query}) -> {len(matches)} matches")
        return json.dumps(result, ensure_ascii=False)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def start_server():
    kill_orphan_servers()
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = LD_LIBRARY_PATH

    proc = subprocess.Popen(
        [
            LLAMA_SERVER_BIN,
            "-m", MODEL_PATH,
            "-ngl", "99",
            "--no-mmap",
            "-c", "8192",
            "--port", str(LLAMA_PORT),
            "-t", "4",
            "-n", "8192",
            "--temp", "0.3",
            "-ctk", "q4_0",
            "-ctv", "q4_0",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    log(f"Starting llama-server for enrich (pid={proc.pid})...")
    for i in range(60):
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
    try:
        result = subprocess.run(["pgrep", "-f", "llama-server"], capture_output=True, text=True)
        for pid_str in result.stdout.strip().split():
            pid = int(pid_str)
            if pid != os.getpid():
                try:
                    cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
                    if f"--port {LLAMA_PORT}" in cmdline or f"--port\n{LLAMA_PORT}" in cmdline:
                        os.kill(pid, 9)
                except (ProcessLookupError, FileNotFoundError):
                    pass
    except Exception:
        pass


def stop_server(proc):
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def llm_request(server, messages, use_tools=True):
    data = {
        "messages": messages,
        "max_tokens": 2048,
        "temperature": 0.4,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if use_tools:
        data["tools"] = TOOLS
        data["tool_choice"] = "auto"

    req = urllib.request.Request(
        f"http://localhost:{LLAMA_PORT}/v1/chat/completions",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req, timeout=180)
    result = json.loads(resp.read())
    choice = result["choices"][0]
    finish = choice.get("finish_reason", "?")
    usage = result.get("usage", {})
    prompt_t = usage.get("prompt_tokens", "?")
    compl_t = usage.get("completion_tokens", "?")
    content_raw = choice["message"].get("content", "") or ""
    reasoning_raw = choice["message"].get("reasoning_content", "") or ""
    tool_calls_raw = choice["message"].get("tool_calls") or []
    log(f"LLM response: finish={finish} prompt={prompt_t} completion={compl_t} content={len(content_raw)} reasoning={len(reasoning_raw)} tools={len(tool_calls_raw)}")
    if finish == "length":
        log(f"WARNING: output truncated! content={content_raw[-200:]}")
    return choice["message"]


def run_llm(db, photo_data):
    server = start_server()
    if not server:
        return None

    try:
        faces_text = format_faces(photo_data["faces"])

        facts_text = db.get_setting("family_facts", "")
        facts_lines = []
        if facts_text:
            for f in photo_data["faces"]:
                name = f.get("name")
                if name and name != "(без имени)":
                    for line in facts_text.split("\n"):
                        if name.lower() in line.lower():
                            facts_lines.append(line.strip())
        facts_section = ""
        if facts_lines:
            unique = list(dict.fromkeys(facts_lines))
            facts_section = "\n\nФакты о людях на фото (используй для связей и возраста):\n" + "\n".join(unique)

        user_msg = f"""Базовое описание:
{photo_data['description']}

Название папки: {photo_data['folder']}

Дата: {photo_data['date']}

Распознанные лица (x - координата слева-направо, меньше = левее):
{faces_text}{facts_section}"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        max_rounds = 2
        for round_num in range(max_rounds):
            log(f"LLM round {round_num + 1}")
            msg = llm_request(server, messages, use_tools=True)

            tool_calls = msg.get("tool_calls", [])
            content = msg.get("content", "") or ""

            if not tool_calls:
                log(f"LLM direct answer ({len(content)} chars): {content[:200]}")
                content = content.strip()
                if content.startswith("<function=") or content.startswith("<parameter>"):
                    log("XML hallucination, retrying clean")
                    print("  [XML hallucination, retrying]")
                    clean_msgs = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ]
                    msg_clean = llm_request(server, clean_msgs, use_tools=False)
                    content = (msg_clean.get("content", "") or "").strip()
                    if not content or len(content) < 10:
                        return None
                content = re.sub(r'^```\w*\s*\n?', '', content)
                content = re.sub(r'\n?\s*```\s*$', '', content)
                content = content.strip()
                if not content or len(content) < 10:
                    reasoning = msg.get("reasoning_content", "") or ""
                    if reasoning:
                        log(f"Thinking only ({len(reasoning)} chars)")
                    if round_num == 0:
                        log("Empty on round 1, retrying")
                        continue
                    return None
                return content

            # Tool calls path
            log(f"LLM called {len(tool_calls)} tools")
            if content:
                messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": tool_calls})

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                tc_id = tc.get("id", "call_0")

                log(f"  Tool call: {fn_name}({fn_args})")
                print(f"  [Tool] {fn_name}({fn_args})")

                result = execute_tool(db, fn_name, fn_args)
                print(f"  [Result] {result[:200]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result,
                })

            # After tool results, always ask for final answer WITHOUT tools
            messages.append({"role": "user", "content": "Напиши итоговое обогащённое описание фото. Не вызывай инструменты."})
            log("Asking for final answer after tool results")
            msg_final = llm_request(server, messages, use_tools=False)
            content = (msg_final.get("content", "") or "").strip()
            reasoning = (msg_final.get("reasoning_content", "") or "").strip()

            if not content and reasoning:
                log(f"Thinking only after tools ({len(reasoning)} chars)")
                content = reasoning

            if content.startswith("<function=") or content.startswith("<parameter>"):
                log("XML hallucination after tools, retrying clean")
                clean_msgs = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ]
                msg_clean = llm_request(server, clean_msgs, use_tools=False)
                content = (msg_clean.get("content", "") or "").strip()

            content = re.sub(r'^```\w*\s*\n?', '', content)
            content = re.sub(r'\n?\s*```\s*$', '', content)
            content = content.strip()

            if not content or len(content) < 10:
                log("Empty after tools, retrying clean")
                clean_msgs = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ]
                msg_clean = llm_request(server, clean_msgs, use_tools=False)
                content = (msg_clean.get("content", "") or "").strip()
                if not content or len(content) < 10:
                    return None

            log(f"Final after tools ({len(content)} chars): {content}")
            return content

        log("Max rounds reached without answer")
        return None

    except Exception as e:
        log(f"LLM error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        stop_server(server)


def enrich_photo(db, photo_path):
    data = get_photo_data(db, photo_path)
    if not data:
        log(f"Photo not found: {photo_path}")
        return None

    if not data["description"]:
        log(f"No description for: {photo_path}")
        return None

    if not data["faces"]:
        log(f"No faces for: {photo_path}")
        return None

    log(f"Enriching: {os.path.basename(photo_path)} ({len(data['faces'])} faces)")

    rich = run_llm(db, data)
    if not rich:
        return None

    db.sqlite.execute(
        "UPDATE photos SET rich_description = ? WHERE path = ?",
        (rich, photo_path)
    )
    db.sqlite.commit()
    log(f"Saved rich_description: {rich[:100]}...")

    return rich


def main():
    parser = argparse.ArgumentParser(description="Enrich photo descriptions with named persons via LLM")
    parser.add_argument("--photo", type=str, help="Single photo path to enrich")
    parser.add_argument("--limit", type=int, default=0, help="Limit photos (0=all with faces+description)")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent / 'src'))
    from database import DatabaseManager
    db = DatabaseManager()

    try:
        from mqtt_client import create_worker_mqtt
        mq = create_worker_mqtt("enrich")
    except Exception:
        mq = None

    if args.photo:
        result = enrich_photo(db, args.photo)
        if result:
            print(f"RICH: {result}")
        else:
            print("FAILED")
        if mq:
            mq.shutdown()
        return

    rows = db.sqlite.execute(
        "SELECT path FROM photos "
        "WHERE description IS NOT NULL AND description != '' "
        "AND faces_present = 1 AND rich_description IS NULL "
        "ORDER BY RANDOM()"
    ).fetchall()

    photos = [r[0] for r in rows]
    if args.limit > 0:
        photos = photos[:args.limit]

    log(f"Found {len(photos)} photos to enrich")

    done = 0
    for path in photos:
        result = enrich_photo(db, path)
        if result:
            done += 1

    log(f"Enrichment done: {done}/{len(photos)}")
    if mq:
        mq.shutdown()


if __name__ == "__main__":
    main()
