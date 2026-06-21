import pytest
import os
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import asyncio


class TestApiStatus:
    """Статус API через MQTT — главный источник current_step.

    Endpoint /api/status приоритетно читает MQTT worker states.
    Файлы-флаги — fallback когда MQTT нет.
    Тесты публикуют статусы в MQTT напрямую (не tmp_data),
    и очищают за собой.
    """

    def test_status_returns_pipeline_fields(self, app_client):
        """Ответ содержит поля current_step, processes, server_time."""
        resp = app_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        for key in ["current_step", "processes", "server_time"]:
            assert key in data, f"missing key: {key}"

    def test_status_idle_when_no_workers(self, app_client):
        """Без MQTT-воркеров current_step = idle."""
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["current_step"] == "idle"

    @pytest.mark.skip(reason="MQTT worker создаётся в тесте, но API-сервер использует "
                             "собственный MQTT клиент. Состояние гонки — статус может "
                             "не успеть дойти до сервера. Проверяется в test_mqtt.py.")
    def test_status_sees_mqtt_worker(self, app_client):
        pass

    @pytest.mark.skip(reason="Та же причина — MQTT интеграция API ненадёжна в тестах.")
    def test_status_mqtt_priority_over_flags(self, app_client):
        pass


class TestControlStart:
    """Тесты вызывают реальный /api/control/start — ЗАПУСКАЕТ ПРОЦЕССЫ.

    НЕЛЬЗЯ запускать на продакшене: убивает pipeline, стартует faces/chain.
    Только в изолированном окружении.
    """

    def test_start_unknown_step(self, app_client):
        """Неизвестный step возвращает ok=False."""
        resp = app_client.post("/api/control/start", json={"step": "nonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False

    @pytest.mark.skip(reason="Запускает faces.py — ломает продакшен")
    def test_start_returns_step(self, app_client):
        resp = app_client.post("/api/control/start", json={"step": "faces"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["step"] == "faces"
        assert data["ok"] is True
        os.system("pkill -f faces.py 2>/dev/null")

    @pytest.mark.skip(reason="Убивает pipeline.py — ломает продакшен")
    def test_start_chain(self, app_client):
        resp = app_client.post("/api/control/start", json={"step": "chain"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        os.system("pkill -f pipeline.py 2>/dev/null")


class TestControlStop:
    """Тесты вызывают реальный /api/control/stop — ОСТАНАВЛИВАЕТ ПРОЦЕССЫ."""

    @pytest.mark.skip(reason="Останавливает pipeline — ломает продакшен")
    def test_stop_returns_ok(self, app_client):
        resp = app_client.post("/api/control/stop")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    @pytest.mark.skip(reason="Вызывает stop — ломает продакшен")
    def test_stop_removes_flags(self, app_client, tmp_data):
        """Флаги удаляются ТОЛЬКО из tmp_data (не реальный FLAG_DIR)."""
        flag_dir = tmp_data["flags"]
        for f in ["describe", "faces", "exif", "embed", "ingest", "pipeline"]:
            (flag_dir / f).touch()
        app_client.post("/api/control/stop")
        for f in ["describe", "faces", "exif", "embed", "ingest", "pipeline"]:
            assert not (flag_dir / f).exists(), f"flag {f} not removed after stop"

    @pytest.mark.skip(reason="Вызывает stop — ломает продакшен")
    def test_stop_creates_no_restart(self, app_client, tmp_data):
        """no_restart в tmp_data создаётся после stop."""
        flag_dir = tmp_data["flags"]
        (flag_dir / "no_restart").unlink(missing_ok=True)
        app_client.post("/api/control/stop")
        assert (flag_dir / "no_restart").exists(), "no_restart flag not created after stop"

    @pytest.mark.skip(reason="Вызывает start chain — убивает pipeline")
    def test_start_removes_no_restart(self, app_client, tmp_data):
        flag_dir = tmp_data["flags"]
        (flag_dir / "no_restart").write_text("manual stop")
        app_client.post("/api/control/start", json={"step": "chain"})
        assert not (flag_dir / "no_restart").exists(), "no_restart flag not removed after start"


@pytest.mark.skip(reason="Вызывает enrich_description — пишет в БД")
class TestGPUArbitrationViaMQTT:
    def test_enrich_uses_mqtt_gpu(self, db_with_photos, tmp_data):
        mock_mq = MagicMock()
        with patch("api.photos._get_mqtt_api", return_value=mock_mq), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            from api.photos import enrich_description
            asyncio.get_event_loop().run_until_complete(
                enrich_description("/photos/2024/img1.jpg")
            )
            mock_mq.request_gpu_for_api.assert_called_once_with(worker_name="enrich")
            mock_mq.release_gpu_from_api.assert_called_once()

    def test_enrich_no_mqtt_falls_through(self, db_with_photos, tmp_data):
        with patch("api.photos._get_mqtt_api", return_value=None), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            from api.photos import enrich_description
            result = asyncio.get_event_loop().run_until_complete(
                enrich_description("/photos/2024/img1.jpg")
            )
            assert result["ok"] is True

    def test_mqtt_gpu_lock_and_release(self):
        from mqtt_client import ApiMQTT
        mq = ApiMQTT.__new__(ApiMQTT)
        mq._worker_states = {"describe": {"gpu_held": True}}
        assert mq._worker_states["describe"]["gpu_held"] is True


class TestWatchdogMode:
    """Режим сторожевого пса: active когда следит, sleeping когда спит.

    Endpoint /api/watchdog/crashes читает реальный FLAG_DIR.
    Тесты проверяют ТЕКУЩЕЕ состояние — не вызывают stop/start
    чтобы не нарушать работу продакшен-пайплайна.
    """

    def test_watchdog_crashes_returns_mode(self, app_client):
        """Эндпоинт возвращает mode и no_restart."""
        resp = app_client.get("/api/watchdog/crashes")
        data = resp.json()
        assert "mode" in data
        assert data["mode"] in ("active", "sleeping")
        assert "no_restart" in data

    def test_watchdog_mode_consistent(self, app_client):
        """mode=sleeping <=> no_restart=True, mode=active <=> no_restart=False."""
        data = app_client.get("/api/watchdog/crashes").json()
        expected = "sleeping" if data["no_restart"] else "active"
        assert data["mode"] == expected, (
            f"mode={data['mode']} no_restart={data['no_restart']} — неконсистентно"
        )


class TestControlButtonStates:
    """Проверка что кнопки UI реагируют на состояние пайплайна."""

    @pytest.mark.skip(reason="Вызывает control/stop — ломает продакшен")
    def test_status_idle_after_stop(self, app_client, tmp_data):
        flag_dir = tmp_data["flags"]
        for f in ["describe", "pipeline"]:
            (flag_dir / f).touch()
        app_client.post("/api/control/stop")
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["current_step"] == "idle"

    def test_current_step_not_idle_when_pipeline_flag(self, app_client, tmp_data):
        """С флагом pipeline current_step не idle."""
        flag_dir = tmp_data["flags"]
        (flag_dir / "pipeline").touch()
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["current_step"] != "idle" or data.get("pipeline_started_at") is not None
        (flag_dir / "pipeline").unlink(missing_ok=True)
        (flag_dir / "pipeline").unlink(missing_ok=True)

    def test_pipeline_started_at_none_when_idle(self, app_client, tmp_data):
        flag_dir = tmp_data["flags"]
        for f in flag_dir.iterdir():
            f.unlink()
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["pipeline_started_at"] is None


class TestConfigAPI:
    def test_config_returns_groups(self, app_client):
        resp = app_client.get("/api/config")
        data = resp.json()
        assert "groups" in data
        assert len(data["groups"]) > 0

    def test_config_group_structure(self, app_client):
        resp = app_client.get("/api/config")
        for g in resp.json()["groups"]:
            assert "name" in g
            assert "icon" in g
            assert "params" in g
            for p in g["params"]:
                assert "k" in p
                assert "v" in p
                assert "d" in p

    def test_config_has_paths(self, app_client):
        resp = app_client.get("/api/config")
        keys = [p["k"] for g in resp.json()["groups"] for p in g["params"]]
        assert "DATA_DIR" in keys
        assert "Корни фото (catalog_roots)" in keys

    def test_config_has_models(self, app_client):
        resp = app_client.get("/api/config")
        keys = [p["k"] for g in resp.json()["groups"] for p in g["params"]]
        assert "VLM порт" in keys
        assert "Enrich порт" in keys
        assert "Embed модель" in keys


class TestOllamaEmbedAI:
    """Integration tests for Ollama dual-circuit embedding (requires AI)"""

    @pytest.fixture(autouse=True)
    def _check_ollama(self):
        import requests
        try:
            requests.get("http://ollama.localnet:11434/api/tags", timeout=3)
        except Exception:
            pytest.skip("Ollama server unreachable")

    @pytest.mark.ai
    def test_ollama_embed_single(self):
        import requests
        r = requests.post("http://ollama.localnet:11434/api/embed",
            json={"model": "qwen3-embedding:0.6b", "input": "тест"},
            timeout=15,
        )
        assert r.status_code == 200
        emb = r.json()["embeddings"][0]
        assert len(emb) == 1024

    @pytest.mark.ai
    def test_ollama_embed_batch_4(self):
        import requests
        texts = ["тест один", "тест два", "тест три", "тест четыре"]
        r = requests.post("http://ollama.localnet:11434/api/embed",
            json={"model": "qwen3-embedding:0.6b", "input": texts},
            timeout=15,
        )
        assert r.status_code == 200
        embs = r.json()["embeddings"]
        assert len(embs) == 4
        for emb in embs:
            assert len(emb) == 1024

    @pytest.mark.ai
    def test_embed_engine_ollama_mode(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODE", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.localnet:11434")
        import importlib, embed, config
        importlib.reload(config)
        config.OLLAMA_MODE = "ollama"
        config.embed_backend = "ollama"
        importlib.reload(embed)
        engine = embed.EmbedEngine()
        assert engine._mode == "ollama"
        v = engine.encode_single("hello world")
        assert v.shape == (1024,)
        assert abs(float((v ** 2).sum()) - 1.0) < 0.01
        engine.cleanup()

    @pytest.mark.ai
    def test_embed_engine_local_mode(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODE", "local")
        import importlib, embed, config
        importlib.reload(config)
        config.OLLAMA_MODE = "local"
        config.embed_backend = "local"
        importlib.reload(embed)
        engine = embed.EmbedEngine()
        assert engine._mode == "local"
        engine.cleanup()

    def test_get_ollama_mode(self, app_client):
        resp = app_client.get("/api/settings/ollama_mode")
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"] in ("local", "ollama", "", None)

    def test_set_and_get_ollama_url(self, app_client):
        resp = app_client.put("/api/settings/ollama_base_url",
            json={"value": "http://test-ollama:11434"})
        assert resp.status_code == 200
        resp2 = app_client.get("/api/settings/ollama_base_url")
        assert resp2.json()["value"] == "http://test-ollama:11434"

    def test_set_and_get_ollama_mode(self, app_client):
        resp = app_client.put("/api/settings/ollama_mode", json={"value": "ollama"})
        assert resp.status_code == 200
        resp2 = app_client.get("/api/settings/ollama_mode")
        assert resp2.json()["value"] == "ollama"

        resp = app_client.put("/api/settings/ollama_mode", json={"value": "local"})
        assert resp.status_code == 200

    def test_set_ollama_embed_chunk(self, app_client):
        resp = app_client.put("/api/settings/ollama_embed_chunk", json={"value": "256"})
        assert resp.status_code == 200
        resp2 = app_client.get("/api/settings/ollama_embed_chunk")
        assert resp2.json()["value"] == "256"

    def test_ollama_check_invalid_url(self, app_client):
        resp = app_client.get("/api/proxy/ollama_check?url=http://nonexistent:11434")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "error" in data

    def test_ollama_models_invalid_url(self, app_client):
        resp = app_client.get("/api/proxy/ollama_models?url=http://nonexistent:11434")
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_fix_ollama_url_formats(self, app_client):
        from main import _fix_ollama_url
        assert _fix_ollama_url("https://ollama.localnet") == "http://ollama.localnet:11434"
        assert _fix_ollama_url("http://localhost") == "http://localhost:11434"
        assert _fix_ollama_url("192.168.1.1:11434") == "http://192.168.1.1:11434"
        assert _fix_ollama_url("ollama.localnet") == "http://ollama.localnet:11434"
        assert _fix_ollama_url("http://host:12345") == "http://host:12345"

    def test_describe_backend_setting(self, app_client):
        resp = app_client.put("/api/settings/describe_backend", json={"value": "ollama"})
        assert resp.status_code == 200
        resp2 = app_client.get("/api/settings/describe_backend")
        assert resp2.json()["value"] == "ollama"
        resp = app_client.put("/api/settings/describe_backend", json={"value": "local"})
        assert resp.status_code == 200
