"""Tests that the runtime environment has correct dependency versions.

P104-100 (Pascal SM 6.1) constraints:
- onnxruntime-gpu 1.18.0 + cuDNN 8.x — единственная работающая комбинация
- numpy < 2 — onnxruntime 1.18.0 собран с numpy 1.x API
- opencv < 4.11 — совместим с numpy < 2
"""

import json
import os
import pytest
import pkg_resources
from pathlib import Path

_dotenv = Path(__file__).parent.parent / ".env"
if _dotenv.exists():
    with open(_dotenv) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

_svc_name = os.environ.get("GALLERY_SERVICE_NAME", "gailery")


REQUIRED_VERSIONS = {
    "onnxruntime-gpu": "==1.18.0",
    "numpy": "<2",
    "opencv-python": "<4.11",
    "opencv-python-headless": "<4.11",
}


def _check_version(name, spec):
    try:
        dist = pkg_resources.get_distribution(name)
        version = dist.version
    except pkg_resources.DistributionNotFound:
        pytest.fail(f"Пакет {name} не установлен")

    parsed_specs = list(pkg_resources.parse_requirements(f"x{spec}"))
    if not parsed_specs:
        return
    specifier = parsed_specs[0].specifier
    parsed_version = pkg_resources.parse_version(version)
    if parsed_version not in specifier:
        pytest.fail(
            f"{name}: требуется {spec}, установлена {version}"
        )


def test_numpy_below_2():
    """Проверяет что numpy < 2.0.

    Почему нельзя numpy>=2:
    - onnxruntime-gpu 1.18.0 собран с numpy 1.x ABI
    - При numpy>=2 падает с 'AttributeError: _ARRAY_API not found'
    - А обновить onnxruntime нельзя — версии >1.18 требуют cuDNN 9.x,
      который не работает на P104-100 (Pascal SM 6.1)
    """
    _check_version("numpy", "<2")


def test_onnxruntime_gpu_pinned():
    """Проверяет что onnxruntime-gpu строго 1.18.0.

    Почему нельзя другую версию:
    - 1.18.0 — последняя версия совместимая с cuDNN 8.x
    - >1.18 требуют cuDNN 9.x → P104-100 не поддерживает
    - <1.18 могут не иметь нужных фиксов/фич для InsightFace
    """
    _check_version("onnxruntime-gpu", "==1.18.0")


def test_opencv_python_works():
    """Проверяет что opencv-python совместим с текущим numpy."""
    import importlib.metadata, numpy
    v = importlib.metadata.version("opencv-python")
    import cv2
    assert cv2.__version__ == v, f"opencv-python {v} импортируется, numpy {numpy.__version__}"


def test_opencv_headless_works():
    """Проверяет что opencv-python-headless совместим с текущим numpy."""
    import importlib.metadata, numpy
    v = importlib.metadata.version("opencv-python-headless")
    import cv2
    assert cv2.__version__ == v, f"opencv-python-headless {v} импортируется, numpy {numpy.__version__}"
    _check_version("opencv-python-headless", "<4.11")


def test_insightface_importable():
    """Проверяет что insightface импортируется без ошибок.

    Этот тест валидирует всю цепочку зависимостей разом:
    numpy → onnxruntime → opencv → insightface.
    Если любой из пакетов несовместим — импорт упадёт здесь,
    а не в рантайме на продакшене.
    """
    from insightface.app import FaceAnalysis
    assert FaceAnalysis is not None


def test_all_dependencies_list():
    """Сводная проверка всех критических зависимостей одним тестом.

    Выводит список ВСЕХ нарушений в одном сообщении,
    чтобы не гонять тесты по одному при отладке.
    Показывает какая версия стоит и какая нужна.
    """
    errors = []
    for name, spec in REQUIRED_VERSIONS.items():
        try:
            dist = pkg_resources.get_distribution(name)
            version = dist.version
        except pkg_resources.DistributionNotFound:
            errors.append(f"{name}: не установлен")
            continue
        parsed_specs = list(pkg_resources.parse_requirements(f"x{spec}"))
        if parsed_specs:
            specifier = parsed_specs[0].specifier
            if pkg_resources.parse_version(version) not in specifier:
                errors.append(f"{name}: нужно {spec}, стоит {version}")
    if errors:
        pytest.fail(
            "Нарушены версии зависимостей:\n" + "\n".join(errors)
            + "\n\nP104-100 Pascal SM 6.1 не поддерживает cuDNN 9.x. "
            "onnxruntime>1.18 требует cuDNN 9. numpy>=2 ломает onnxruntime 1.18."
        )


# ── Проверка что systemd-сервисы запущены и отвечают ──


REQUIRED_SERVICES = [
    f"{_svc_name}.service",
    f"{_svc_name}-watchdog.service",
    "mosquitto.service",
]


def _systemctl_is_active(unit):
    import subprocess
    r = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip() == "active"


def test_api_service_active():
    assert _systemctl_is_active(f"{_svc_name}.service"), (
        f"{_svc_name}.service не active!\n"
        f"Проверь: systemctl status {_svc_name}\n"
        f"Возможно нужно: systemctl restart {_svc_name}"
    )


def test_watchdog_service_active():
    """watchdog.service должен быть active — иначе pipeline не следит.
    """
    assert _systemctl_is_active(f"{_svc_name}-watchdog.service"), (
        f"{_svc_name}-watchdog.service не active!\n"
        f"Проверь: systemctl status {_svc_name}-watchdog"
    )


def test_mosquitto_service_active():
    """mosquitto.service (MQTT broker) должен быть active.

    Без MQTT не работает GPU-арбитраж, статусы воркеров,
    панель «Воркеры MQTT» показывает dead для всех.
    """
    assert _systemctl_is_active("mosquitto.service"), (
        "mosquitto.service не active!\n"
        "Проверь: systemctl status mosquitto"
    )


def test_all_services_active():
    """Сводная: все три сервиса активны одним тестом."""
    dead = [s for s in REQUIRED_SERVICES if not _systemctl_is_active(s)]
    if dead:
        pytest.fail(
            "Неактивные сервисы: " + ", ".join(dead) +
            "\nПроверь: systemctl status " + " ".join(dead)
        )


def test_api_health_responds():
    """Health-check API отвечает на localhost:8000.

    Если пакеты обновлены, а сервис не перезапущен —
    старый процесс работает со старыми версиями, может вести себя странно.
    """
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/health", timeout=5)
        data = json.loads(resp.read())
        assert data.get("status") in ("ok", "healthy"), f"API health: {data}"
    except Exception as e:
        pytest.fail(
            f"API не отвечает на :8000/health: {e}\n"
            f"Проверь: systemctl status {_svc_name}\n"
            f"systemctl restart {_svc_name}"
        )


def test_mqtt_broker_reachable():
    """MQTT брокер доступен на localhost:1883."""
    import socket
    try:
        s = socket.create_connection(("127.0.0.1", 1883), timeout=3)
        s.close()
    except Exception as e:
        pytest.fail(
            f"MQTT брокер не слушает :1883: {e}\n"
            "Проверь: systemctl status mosquitto"
        )


def _pgrep(script_name):
    import subprocess
    r = subprocess.run(
        ["pgrep", "-f", f"python3.*{script_name}"],
        capture_output=True, text=True, timeout=5,
    )
    pids = [pid for pid in r.stdout.strip().split() if pid]
    return pids


def test_pipeline_process_exists():
    """Процесс pipeline.py запущен ИЛИ idle (все шаги завершены).

    Если pipeline_idle флаг стоит — pipeline закончивший, это нормально.
    Если нет флага и нет процесса — проблема, watchdog должен перезапустить.
    """
    pids = _pgrep("pipeline.py")
    try:
        from config import FLAG_DIR
        is_idle = (FLAG_DIR / "pipeline_idle").exists()
    except Exception:
        is_idle = False
    if is_idle:
        return
    assert len(pids) >= 1, (
        "pipeline.py не запущен и не idle!\n"
        "Проверь: ps aux | grep pipeline.py\n"
        "Watchdog должен перезапустить автоматически."
    )


def test_watchdog_process_exists():
    """Процесс watchdog.py запущен."""
    pids = _pgrep("watchdog.py")
    assert len(pids) >= 1, (
        "watchdog.py не запущен!\n"
        f"Проверь: systemctl status {_svc_name}-watchdog"
    )


def test_api_status_returns_data():
    """Статус API возвращает ненулевые счётчики фото."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/status", timeout=10)
        data = json.loads(resp.read())
        assert data.get("photos_total", 0) > 1000, (
            f"photos_total={data.get('photos_total')} — слишком мало, "
            "похоже API не видит реальную БД"
        )
        assert data.get("catalog_total", 0) > 1000
    except Exception as e:
        pytest.fail(f"/api/status не отвечает: {e}")


def test_gallery_search_works():
    """Галерея: /api/photos/search возвращает валидный JSON с фото."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/api/photos/search?limit=3", timeout=15)
        data = json.loads(resp.read())
        photos = data if isinstance(data, list) else data.get("photos", data.get("results", []))
        assert isinstance(photos, list), f"/api/photos/search вернул не список: {type(photos)}"
    except Exception as e:
        pytest.fail(
            f"/api/photos/search не работает: {e}\n"
            "Галерея недоступна! Проверь логи API."
        )


def test_gallery_photos_api_works():
    """Галерея: ключевые API фото возвращают 200 + JSON."""
    import urllib.request
    endpoints = [
        "/api/photos/dates",
        "/api/persons/",
    ]
    for ep in endpoints:
        try:
            resp = urllib.request.urlopen(f"http://localhost:8000{ep}", timeout=10)
            body = resp.read()
            json.loads(body)
        except Exception as e:
            pytest.fail(f"{ep} не работает: {e}")


def test_gallery_page_renders():
    """Галерея: /gallery отдаёт HTML (не 500)."""
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:8000/gallery", timeout=10)
        html = resp.read().decode()
        assert "Gailery" in html or "gallery" in html.lower(), "/gallery не содержит контент галереи"
    except Exception as e:
        pytest.fail(f"/gallery не отдаётся: {e}")


def test_watchdog_mode_consistent_with_flags():
    """mode из API согласован с реальным состоянием: sleeping/waiting/active."""
    import urllib.request
    data = json.loads(urllib.request.urlopen(
        "http://localhost:8000/api/watchdog/crashes", timeout=30).read())
    no_restart = data["no_restart"]
    mode = data["mode"]
    valid_modes = {"sleeping", "waiting", "active"}
    assert mode in valid_modes, (
        f"mode={mode} — неизвестный режим, ожидался один из {valid_modes}"
    )
    if no_restart:
        assert mode == "sleeping", (
            f"no_restart={no_restart} но mode={mode}, "
            f"ожидался 'sleeping'"
        )


def test_persons_api_includes_unnamed():
    """Без named_only API персон возвращает и именованных и неименованных.

    Если тест падает — кто-то поставил named_only=true в fetch страницы /persons
    и неименованные кластеры показывают 0. Уже было: persona.html loadPersonas().
    """
    import urllib.request
    resp = urllib.request.urlopen(
        "http://localhost:8000/api/persons/?limit=200", timeout=10)
    data = json.loads(resp.read())
    named = [p for p in data["persons"] if p.get("display_name")]
    unnamed = [p for p in data["persons"] if not p.get("display_name")]
    assert len(named) >= 1, "нет именованных персон в выборке"
    assert len(unnamed) >= 1, (
        f"unnamed=0 из {len(data['persons'])} — "
        "проверь что loadPersonas НЕ ставит named_only=true"
    )


def test_admin_js_valid():
    """Все JS модули админки не содержат синтаксических ошибок — проверяется через Node.js."""
    import subprocess, glob
    js_files = sorted(glob.glob(str(Path(__file__).parent.parent / 'web' / 'admin' / 'js' / '*.js')))
    for f in js_files:
        r = subprocess.run(["node", "--check", f], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            pytest.fail(f"{f} содержит ошибку синтаксиса:\n{r.stderr.strip()}")


# ── Проверка что все ключевые API отдают валидный JSON ──

GALLERY_ENDPOINTS = [
    ("/admin", "админка", False),  # HTML, not JSON
    ("/api/photos/search?limit=5&sort=date_desc", "поиск фото (главная галерея)", True),
    ("/api/photos/dates", "гистограмма дат (таймлайн)", True),
    ("/api/status", "статус пайплайна", True),
    ("/api/persons/?limit=5", "список персон", True),
    ("/api/persons/names", "имена персон (автокомплит)", True),
    ("/api/catalog/roots", "корни каталога", True),
    ("/api/catalog/stats", "статистика каталога", True),
    ("/api/photos/map", "карта с GPS-фото", True),
    ("/api/config", "конфиг (панель управления)", True),
    ("/api/photos/search?has_faces=true&limit=3", "фильтр по лицам", True),
    ("/api/photos/search?has_gps=true&limit=3", "фильтр по GPS", True),
    ("/api/photos/search?has_description=true&limit=3", "фильтр по описанию", True),
]


def test_all_gallery_endpoints_return_json():
    """Все ключевые API эндпоинты отдают валидный JSON — без этого
    фронтенд падает с 'JSON.parse: unexpected character'.

    Проверяет каждый эндпоинт отдельно и перечисляет все сломанные.
    """
    import urllib.request
    errors = []
    for url, desc, is_json in GALLERY_ENDPOINTS:
        try:
            resp = urllib.request.urlopen(
                f"http://localhost:8000{url}", timeout=15)
            body = resp.read()
            if is_json:
                json.loads(body)
            elif not body:
                errors.append(f"{desc}: пустой ответ ({url})")
        except json.JSONDecodeError:
            errors.append(f"{desc}: не JSON ({url})")
            errors.append(f"  тело: {body[:200]}")
        except Exception as e:
            errors.append(f"{desc}: ошибка запроса ({url})")
            errors.append(f"  {e}")

    if errors:
        pytest.fail(
            "Эндпоинты отдают не-JSON — фронтенд сломан:\n" +
            "\n".join(errors) +
            "\n\nПроверь: БД не повреждена, сервис перезапущен после изменений."
        )