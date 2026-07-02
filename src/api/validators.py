"""validators.py — хелперы валидации ввода на сетевой границе.

Манифест §3.6: данные из HTTP-запроса не типизированы. Python не защищает
от int("abc") или обращения к .get() у результата json.loads(b'0') (int).
Каждая точка приёма должна валидировать тип ДО передачи в бизнес-логику.

Хелперы инкапсулируют валидацию — невалидный ввод возвращает безопасное
значение по умолчанию, НИКОГДА не бросает исключение.

Использование:
    from api.validators import json_body, int_param

    @router.post("/example")
    async def handler(request: Request):
        body = await json_body(request)  # dict, никогда не упадёт
        name = body.get("name", "")

    @router.get("/example")
    async def handler(request: Request):
        limit = int_param(request.query_params, "limit", 100)
"""

from typing import Any, Dict
import logging

logger = logging.getLogger(__name__)


async def json_body(request) -> Dict[str, Any]:
    """Безопасно парсит JSON тело запроса как dict.

    Возвращает {} если:
    - тело пустое
    - тело не валидный JSON
    - тело валидный JSON но не dict (например число, строка, список)

    Никогда не бросает исключение — это security-контроль (манифест §3.6).
    """
    try:
        body = await request.json()
    except (ValueError, TypeError, RuntimeError) as e:
        logger.debug("json_body: invalid JSON body — %s", e)
        return {}

    if isinstance(body, dict):
        return body

    return {}


def int_param(query_params, name: str, default: int = 0) -> int:
    """Безопасно парсит query-параметр как int.

    Возвращает default если:
    - параметр отсутствует
    - значение не конвертируется в int

    Никогда не бросает исключение (манифест §3.6).
    """
    raw = query_params.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def float_param(query_params, name: str, default: float = 0.0) -> float:
    """Безопасно парсит query-параметр как float."""
    raw = query_params.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


def str_param(query_params, name: str, default: str = "") -> str:
    """Безопасно парсит query-параметр как str (с защитой от не-str)."""
    raw = query_params.get(name)
    if raw is None:
        return default
    return str(raw) if not isinstance(raw, str) else raw
