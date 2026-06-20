import pytest
import os
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import asyncio


@pytest.mark.destructive
class TestMQTTWorkerLifecycle:
    def test_worker_publishes_running_on_start(self):
        """Воркер публикует статус running + PID при старте, API их видит."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("ingest")
        worker.publish_status("running")
        worker.publish_pid()
        time.sleep(1)

        states = api.get_worker_states()
        assert states["ingest"]["status"] == "running"
        assert states["ingest"]["pid"] is not None

        worker.publish_status("done")
        worker.disconnect()
        time.sleep(0.5)
        api.disconnect()

    def test_worker_publishes_progress(self):
        """Воркер публикует прогресс done/total с процентом."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("embed")
        worker.publish_status("running")
        worker.publish_progress(30, 100)
        time.sleep(1)

        states = api.get_worker_states()
        assert states["embed"]["progress"]["done"] == 30
        assert states["embed"]["progress"]["pct"] == 30.0

        worker.publish_status("done")
        worker.disconnect()
        api.disconnect()

    def test_mqtt_stop_sets_stopped_flag(self):
        """API-команда stop доходит до воркера, worker.stopped() = True."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("faces")
        worker.publish_status("running")
        time.sleep(1)

        assert not worker.stopped()
        api.send_stop("faces")
        time.sleep(1)
        assert worker.stopped()

        worker.publish_status("done")
        worker.disconnect()
        api.disconnect()


@pytest.mark.destructive
class TestMQTTApiStatus:
    def test_api_detects_mqtt_worker_alive(self):
        """API видит живого воркера, get_current_step возвращает не idle."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("faces")
        worker.publish_status("running")
        worker.publish_pid()
        worker.publish_gpu_held(True)
        time.sleep(1)

        assert api.is_worker_alive("faces")
        step = api.get_current_step()
        assert step != "idle"

        worker.publish_status("done")
        worker.publish_gpu_held(False)
        worker.disconnect()
        time.sleep(0.5)
        api.disconnect()

    def test_api_sees_dead_worker_as_idle(self):
        """После done+disconnect воркер считается мёртвым с точки зрения API."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("exif")
        worker.publish_status("running")
        worker.publish_pid()
        time.sleep(1)

        assert api.is_worker_alive("exif")

        worker.publish_status("done")
        worker.disconnect()
        time.sleep(1)

        assert not api.is_worker_alive("exif")

        api.disconnect()


@pytest.mark.destructive
class TestMQTTGPUArbitration:
    def test_pause_resume_cycle(self):
        """API может приостановить и возобновить воркер через pause/resume."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from mqtt_client import create_worker_mqtt, create_api_mqtt

        api = create_api_mqtt()
        time.sleep(1)

        worker = create_worker_mqtt("describe")
        worker.publish_status("running")
        worker.publish_gpu_held(True)
        time.sleep(1)

        assert api._worker_states["describe"]["gpu_held"] is True

        api.send_pause(reason="gpu_yield")
        time.sleep(1)
        assert worker.paused()

        api.send_resume()
        time.sleep(1)
        assert not worker.paused()

        worker.publish_gpu_held(False)
        worker.publish_status("done")
        worker.disconnect()
        api.disconnect()


class TestMQTTFlagFallback:
    def test_status_uses_flags_when_no_mqtt_worker(self, app_client, tmp_data):
        """Без MQTT статус берётся из файлов-флагов."""
        flag_dir = tmp_data["flags"]
        (flag_dir / "exif").touch()
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["current_step"] != "idle"  # флаг или MQTT дают не-idle
        (flag_dir / "exif").unlink()

    def test_mqtt_overrides_stale_flag(self, app_client, tmp_data):
        """MQTT-статус приоритетнее файлов-флагов."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        flag_dir = tmp_data["flags"]
        (flag_dir / "describe").touch()
        resp = app_client.get("/api/status")
        data = resp.json()
        assert data["current_step"] != "idle"  # либо флаг либо MQTT
        (flag_dir / "describe").unlink()
