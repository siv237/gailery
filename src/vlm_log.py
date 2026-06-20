"""
vlm_log.py — логирование всех AI-вызовов в отдельную SQLite базу.
База создаётся автоматически. Удалена — пересоздастся. Никаких миграций.

Хранит СЫРОЙ JSON запроса и ответа — всё что ушло в модель и всё что пришло:
  - system prompt, user prompt, tool definitions
  - image base64 (длина), model params
  - reasoning_content (размышление модели)
  - tool_calls + tool_results
  - finish_reason, usage (tokens), timings
  - parsed result (что сохранилось в БД)
  - agent_context (данные из БД: лица, факты, папка)
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

_DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = str(_DATA_DIR / "ai_log.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    call_type       TEXT NOT NULL,
    called_at       TEXT NOT NULL,
    photo_path      TEXT,
    content_hash    TEXT,
    photo_id        TEXT,
    batch_id        TEXT,

    request_json    TEXT,
    response_json   TEXT,

    agent_context   TEXT,
    parsed_result   TEXT,
    tool_results    TEXT,

    elapsed_sec     REAL,
    error           TEXT,
    success         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ai_type  ON ai_calls(call_type);
CREATE INDEX IF NOT EXISTS idx_ai_path  ON ai_calls(photo_path);
CREATE INDEX IF NOT EXISTS idx_ai_hash  ON ai_calls(content_hash);
CREATE INDEX IF NOT EXISTS idx_ai_at    ON ai_calls(called_at);
CREATE INDEX IF NOT EXISTS idx_ai_batch ON ai_calls(batch_id);
"""


def _connect():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def log_ai_call(
    call_type,
    photo_path=None,
    content_hash=None,
    photo_id=None,
    batch_id=None,
    request_json=None,
    response_json=None,
    agent_context=None,
    parsed_result=None,
    tool_results=None,
    elapsed_sec=None,
    error=None,
    success=None,
):
    """Записать AI-вызов в лог. Никогда не падает."""
    try:
        def _s(v):
            if v is None: return None
            if isinstance(v, str): return v
            return json.dumps(v, ensure_ascii=False, default=str)

        conn = _connect()
        conn.execute("""
            INSERT INTO ai_calls (
                call_type, called_at, photo_path, content_hash, photo_id, batch_id,
                request_json, response_json, agent_context, parsed_result, tool_results,
                elapsed_sec, error, success
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            call_type,
            datetime.now().isoformat(),
            photo_path, content_hash, photo_id, batch_id,
            _s(request_json), _s(response_json),
            _s(agent_context), _s(parsed_result), _s(tool_results),
            elapsed_sec, error, success,
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass
