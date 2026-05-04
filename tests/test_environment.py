"""Tests that the runtime environment has correct dependency versions.

P104-100 (Pascal SM 6.1) constraints:
- onnxruntime-gpu 1.18.0 + cuDNN 8.x — единственная работающая комбинация
- numpy < 2 — onnxruntime 1.18.0 собран с numpy 1.x API
- opencv < 4.11 — совместим с numpy < 2
"""

import json
import pytest
import pkg_resources


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


def test_opencv_python_below_4_11():
    """Проверяет что opencv-python < 4.11.

    Почему нельзя >=4.11:
    - opencv >=4.11 требует numpy>=2
    - При numpy<2 (нужно для onnxruntime) opencv>=4.11 не импортируется
    """
    _check_version("opencv-python", "<4.11")


def test_opencv_headless_below_4_11():
    """Проверяет что opencv-python-headless < 4.11.

    Та же причина что и opencv-python:
    - >=4.11 требует numpy>=2, конфликтует с onnxruntime 1.18.0
    """
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
    "gailray.service",
    "gailray-watchdog.service",
    "mosquitto.service",
]


def _systemctl_is_active(unit):
    import subprocess
    r = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip() == "active"


def test_gailray_service_active():
    """gailray.service (FastAPI) должен быть active — иначе API не отвечает.

    Если тест падает — проверь: systemctl status gailray.
    Частая причина: сервис не перезапущен после обновления кода
    или зависимостей — работает старый код со старыми версиями пакетов.
    """
    assert _systemctl_is_active("gailray.service"), (
        "gailray.service не active!\n"
        "Проверь: systemctl status gailray\n"
        "Возможно нужно: systemctl restart gailray"
    )


def test_watchdog_service_active():
    """gailray-watchdog.service должен быть active — иначе pipeline не следит.

    Без watchdog pipeline не перезапускается при падении.
    """
    assert _systemctl_is_active("gailray-watchdog.service"), (
        "gailray-watchdog.service не active!\n"
        "Проверь: systemctl status gailray-watchdog"
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
            "Проверь: systemctl status gailray\n"
            "systemctl restart gailray"
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
    """Процесс pipeline.py запущен — без него не работает обработка.

    Если тест падает, а сервисы active — watchdog запустит pipeline сам
    при следующем цикле. Панель «Воркеры MQTT» покажет dead пока pipeline
    не переподключится после рестарта.
    """
    pids = _pgrep("pipeline.py")
    assert len(pids) >= 1, (
        "pipeline.py не запущен!\n"
        "Проверь: ps aux | grep pipeline.py\n"
        "Watchdog должен перезапустить автоматически."
    )


def test_watchdog_process_exists():
    """Процесс watchdog.py запущен."""
    pids = _pgrep("watchdog.py")
    assert len(pids) >= 1, (
        "watchdog.py не запущен!\n"
        "Проверь: systemctl status gailray-watchdog"
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


def test_watchdog_mode_consistent_with_flags():
    """mode активен <=> no_restart флаг отсутствует. Проверяет консистентность."""
    import urllib.request
    data = json.loads(urllib.request.urlopen(
        "http://localhost:8000/api/watchdog/crashes", timeout=5).read())
    no_restart = data["no_restart"]
    mode = data["mode"]
    expected = "sleeping" if no_restart else "active"
    assert mode == expected, (
        f"mode={mode} но no_restart={no_restart}, "
        f"ожидалось {expected}"
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
    """app.js не содержит синтаксических ошибок — проверяется через Node.js.

    Если тест падает — в app.js ошибка синтаксиса JavaScript.
    Браузер покажет 'Uncaught SyntaxError' и админка не заработает.
    """
    import subprocess
    r = subprocess.run(
        ["node", "-e",
         "new Function(require('fs').readFileSync("
         "'/opt/gailray/web/admin/js/app.js','utf8'))"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        pytest.fail(
            f"app.js содержит ошибку синтаксиса:\n{r.stderr.strip()}"
        )


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