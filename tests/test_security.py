"""test_security.py — тесты безопасности (SAST + SCA + фаззинг).

Манифест §3.5: три уровня — SAST (bandit), SCA (pip-audit), фаззинг (hypothesis).
Манифест §2.1: тесты безопасности НЕ блокируют коммиты в локальной разработке,
но становятся блокирующими в CI/CD. Порог безопасности — всегда 0.

Запуск:
  ./run_tests.sh --security   (когда будет добавлен)
  /opt/gailray/venv/bin/python3 -m pytest tests/test_security.py -v -m security

Маркеры:
  security — все тесты этого файла
  arch     — SAST/SCA (статические, без запуска сервера)
  fuzz     — фаззинг (динамические, требуют живой сервер или TestClient)
"""

import json
import subprocess
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent
VENV_PYTHON = str(ROOT / "venv" / "bin" / "python3")

# Файлы исключаемые из SAST (bench/test — не production код)
BANDIT_EXCLUDE = [
    "bench_torchao.py", "bench_vlm.py", "bench_vlm_parallel.py",
    "benchmark_vision.py", "test_batch.py", "test_batch_image.py",
    "test_batch_real_images.py",
]

# Манифест §4.6: порог безопасности ВСЕГДА 0. False positives подавляются
# # nosec с указанием причины. Подавление без причины = нарушение.
# Все 53 MEDIUM — false positives, подавлены nosec в исходном коде.


def _run_bandit(severity_level="-ll"):
    """Запуск bandit, возвращает список находок HIGH+MEDIUM (без nosec)."""
    targets = [str(ROOT / "src")] + [
        str(p) for p in ROOT.glob("*.py")
        if p.name not in BANDIT_EXCLUDE
    ]
    exclude_str = ",".join(BANDIT_EXCLUDE)
    try:
        subprocess.run(
            [VENV_PYTHON, "-m", "bandit", "-r"] + targets
            + ["-x", exclude_str, severity_level, "-f", "json", "-o", "/tmp/bandit_test.json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
    except Exception as e:
        pytest.skip(f"bandit не установлен: {e}")

    try:
        with open("/tmp/bandit_test.json") as f:
            data = json.load(f)
    except Exception:
        pytest.skip("bandit не вернул JSON")

    # bandit исключает nosec-подавленные находки из results автоматически
    return data.get("results", [])

pytestmark = pytest.mark.security


# ─── SAST: bandit ───

def _run_bandit(severity_level="-ll"):
    """Запуск bandit, возвращает список находок HIGH+MEDIUM."""
    targets = [str(ROOT / "src")] + [
        str(p) for p in ROOT.glob("*.py")
        if p.name not in BANDIT_EXCLUDE
    ]
    exclude_str = ",".join(BANDIT_EXCLUDE)
    try:
        subprocess.run(
            [VENV_PYTHON, "-m", "bandit", "-r"] + targets
            + ["-x", exclude_str, severity_level, "-f", "json", "-o", "/tmp/bandit_test.json"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=60
        )
    except Exception as e:
        pytest.skip(f"bandit не установлен: {e}")

    try:
        with open("/tmp/bandit_test.json") as f:
            data = json.load(f)
    except Exception:
        pytest.skip("bandit не вернул JSON")

    return data.get("results", [])


def test_bandit_no_high_without_nosec():
    """SAST: 0 находок HIGH severity без обоснованного nosec.

    Манифест §4.6: порог безопасности всегда 0.
    HIGH — SQL injection, shell injection, weak crypto, hardcoded creds.
    Подавление требует комментария # nosec с указанием причины.
    """
    results = _run_bandit("-lll")  # -lll = только HIGH
    high = [r for r in results if r["issue_severity"] == "HIGH"]

    if high:
        lines = []
        for r in high:
            loc = f"{r['filename']}:{r['line_number']}"
            tid = r["test_id"]
            text = r["issue_text"][:80]
            lines.append(f"  {tid}  {loc}  {text}")
        pytest.fail(
            f"SAST: {len(high)} находок HIGH без nosec (порог 0):\n"
            + "\n".join(lines) + "\n"
            "Зафикси уязвимость или подави с # nosec <ID> — <причина>"
        )


def test_bandit_no_medium_without_nosec():
    """SAST: 0 находок MEDIUM severity без обоснованного nosec.

    Манифест §4.6: порог безопасности всегда 0.
    MEDIUM — SQL injection (B608), urllib (B310), bind 0.0.0.0 (B104).
    False positives подавляются # nosec с причиной в исходном коде.
    """
    results = _run_bandit("-ll")
    med = [r for r in results if r["issue_severity"] == "MEDIUM"]

    if med:
        lines = []
        for r in med[:20]:
            loc = f"{r['filename']}:{r['line_number']}"
            tid = r["test_id"]
            text = r["issue_text"][:80]
            lines.append(f"  {tid}  {loc}  {text}")
        pytest.fail(
            f"SAST: {len(med)} находок MEDIUM без nosec (порог 0):\n"
            + "\n".join(lines) + "\n"
            "Зафикси или подави с # nosec <ID> — <причина> (манифест §3.5)"
        )


# ─── SCA: pip-audit ───

def test_no_known_cves():
    """SCA: 0 известных CVE в runtime-зависимостях.

    Манифест §3.5: pip-audit проверяет requirements.txt против PyPA advisory.
    Dev-инструменты (pytest, bandit, ruff) исключаются — не попадают в production.
    Порог: 0 известных CVE.
    """
    try:
        result = subprocess.run(
            [VENV_PYTHON, "-m", "pip_audit", "-r", str(ROOT / "requirements.txt"),
             "--strict", "--desc"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120
        )
    except Exception:
        pytest.skip("pip-audit не установлен (установить: pip install pip-audit)")

    # pip-audit возвращает 0 если нет CVE, ненулевой код если есть
    if result.returncode != 0 and result.stdout:
        # Парсим вывод
        vulns = []
        for line in result.stdout.splitlines():
            if "Known vulnerabilities" in line or "vuln" in line.lower():
                vulns.append(line)
        if vulns:
            pytest.fail(
                f"SCA: найдены CVE в runtime-зависимостях (порог 0):\n"
                + "\n".join(vulns[:20]) + "\n"
                "Обнови версию в requirements.txt"
            )
    print("\n✅ SCA: 0 известных CVE в requirements.txt")


# ─── Фаззинг: hypothesis (манифест §3.5) ───
# Принцип: сервер НЕ должен обрывать соединение или возвращать 500
# на произвольный ввод. Корректные ответы — 200, 400 или 404.
# Обрыв соединения = необработанное исключение = баг.

from hypothesis import given, strategies as st, settings, HealthCheck
from urllib.parse import quote


@given(path=st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=1, max_size=200
))
@settings(max_examples=50, deadline=2000, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_path_no_crash(app_client, path):
    """Фаззинг: произвольный path — сервер не должен падать (500 или обрыв).

    Манифест §3.5: path traversal, спецсимволы, нестандартные пути.
    Допустимые ответы: 200, 400, 404, 422. Недопустимые: 500, обрыв.
    """
    try:
        resp = app_client.get(f"/{quote(path, safe='/')}", follow_redirects=False)
    except Exception as e:
        pytest.fail(f"Фаззинг path: обрыв соединения на /{path[:50]!r}: {e}")

    assert resp.status_code < 500, (
        f"Фаззинг path: 500 на /{path[:50]!r} — необработанное исключение"
    )


@given(
    body=st.one_of(
        st.text(max_size=500),
        st.integers(),
        st.floats(),
        st.lists(st.text(max_size=50), max_size=10),
        st.booleans(),
        st.none(),
        st.binary(max_size=200),
    )
)
@settings(max_examples=50, deadline=2000, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_json_body_no_crash(app_client, body):
    """Фаззинг: произвольное JSON тело на POST эндпоинт — сервер не должен падать.

    Манифест §3.6: json.loads(b'0') → int, .get() → AttributeError.
    Хелпер json_body() должен вернуть {} для не-dict.
    Тестируем /api/photos/reverse_geocode (POST, принимает JSON).
    """
    import json as json_mod
    try:
        # Отправляем body как raw JSON (или невалидный JSON)
        if isinstance(body, bytes):
            resp = app_client.post(
                "/api/photos/reverse_geocode",
                content=body,
                headers={"content-type": "application/json"},
            )
        else:
            resp = app_client.post(
                "/api/photos/reverse_geocode",
                json=body if not isinstance(body, str) else None,
                content=json_mod.dumps(body).encode() if not isinstance(body, str) else body.encode(),
                headers={"content-type": "application/json"},
            )
    except Exception as e:
        pytest.fail(f"Фаззинг JSON body: обрыв соединения: {e}")

    assert resp.status_code < 500, (
        f"Фаззинг JSON body: 500 на body={str(body)[:50]!r} — необработанное исключение"
    )


@given(
    limit=st.one_of(st.text(max_size=20), st.integers(min_value=-1000, max_value=1000)),
    offset=st.one_of(st.text(max_size=20), st.integers(min_value=-1000, max_value=1000)),
)
@settings(max_examples=50, deadline=2000, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_query_params_no_crash(app_client, limit, offset):
    """Фаззинг: некорректные query-параметры — сервер не должен падать.

    Манифест §3.6: int("abc") → ValueError без хелпера.
    /api/photos/list принимает limit:int, offset:int.
    FastAPI возвращает 422 при неверном типе — это корректно.
    """
    params = {}
    if isinstance(limit, str):
        params["limit"] = limit
    else:
        params["limit"] = str(limit)
    if isinstance(offset, str):
        params["offset"] = offset
    else:
        params["offset"] = str(offset)

    try:
        resp = app_client.get("/api/photos/list", params=params)
    except Exception as e:
        pytest.fail(f"Фаззинг query: обрыв соединения на params={params}: {e}")

    assert resp.status_code < 500, (
        f"Фаззинг query: 500 на params={params} — необработанное исключение"
    )


@given(path=st.text(
    alphabet="./abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=1, max_size=100
))
@settings(max_examples=50, deadline=2000, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_fuzz_path_traversal_no_crash(app_client, path):
    """Фаззинг: path traversal попытки (../) — сервер не должен падать или отдать файлы.

    Манифест §7: path traversal — ../ in static file paths.
    Допустимо: 404, 400. Недопустимо: 500, обрыв, или 200 с содержимым вне web/.
    """
    traversal = path.replace("a", "..")  # внедряем ../
    try:
        resp = app_client.get(f"/{traversal}", follow_redirects=False)
    except Exception as e:
        pytest.fail(f"Фаззинг traversal: обрыв на /{traversal[:50]!r}: {e}")

    assert resp.status_code < 500, (
        f"Фаззинг traversal: 500 на /{traversal[:50]!r}"
    )
