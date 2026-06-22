"""Тесты для mqtt_client.py — unit-тесты с моками MQTT."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestTopicFunctions:
    def test_worker_status_topic(self):
        from mqtt_client import worker_status_topic, PREFIX
        assert worker_status_topic("faces") == f"{PREFIX}/worker/faces/status"

    def test_worker_progress_topic(self):
        from mqtt_client import worker_progress_topic, PREFIX
        assert worker_progress_topic("embed") == f"{PREFIX}/worker/embed/progress"

    def test_worker_pid_topic(self):
        from mqtt_client import worker_pid_topic, PREFIX
        assert worker_pid_topic("describe") == f"{PREFIX}/worker/describe/pid"

    def test_worker_gpu_held_topic(self):
        from mqtt_client import worker_gpu_held_topic, PREFIX
        assert worker_gpu_held_topic("enrich") == f"{PREFIX}/worker/enrich/gpu_held"

    def test_gpu_lock_topic(self):
        from mqtt_client import gpu_lock_topic, PREFIX
        assert gpu_lock_topic() == f"{PREFIX}/gpu/lock"

    def test_control_start_topic(self):
        from mqtt_client import control_start_topic, PREFIX
        assert control_start_topic() == f"{PREFIX}/control/start"

    def test_control_stop_topic(self):
        from mqtt_client import control_stop_topic, PREFIX
        assert control_stop_topic() == f"{PREFIX}/control/stop"

    def test_control_pause_topic(self):
        from mqtt_client import control_pause_topic, PREFIX
        assert control_pause_topic() == f"{PREFIX}/control/pause"

    def test_control_resume_topic(self):
        from mqtt_client import control_resume_topic, PREFIX
        assert control_resume_topic() == f"{PREFIX}/control/resume"

    def test_watchdog_mode_topic(self):
        from mqtt_client import watchdog_mode_topic, PREFIX
        assert watchdog_mode_topic() == f"{PREFIX}/watchdog/mode"

    def test_db_cmd_topic(self):
        from mqtt_client import DB_CMD_TOPIC, PREFIX
        assert DB_CMD_TOPIC == f"{PREFIX}/db/cmd"

    def test_db_result_topic(self):
        from mqtt_client import db_result_topic, DB_RESULT_PREFIX
        assert db_result_topic("req123") == f"{DB_RESULT_PREFIX}/req123"


class TestPublish:
    def _make_mq(self):
        """Создаёт GailrayMQTT с моком клиента."""
        from mqtt_client import GailrayMQTT
        with patch("mqtt_client.mqtt"):
            mq = GailrayMQTT()
            mq.client = MagicMock()
            mq._connected = True
            return mq

    def test_publish_dict(self):
        """publish с dict сериализует в JSON."""
        mq = self._make_mq()
        mq.publish("test/topic", {"key": "value"})
        call_args = mq.client.publish.call_args
        assert json.loads(call_args.args[1]) == {"key": "value"}

    def test_publish_bool(self):
        """publish с bool → 'true'/'false'."""
        mq = self._make_mq()
        mq.publish("test/topic", True)
        assert mq.client.publish.call_args.args[1] == "true"

        mq.publish("test/topic", False)
        assert mq.client.publish.call_args.args[1] == "false"

    def test_publish_int(self):
        """publish с int → str."""
        mq = self._make_mq()
        mq.publish("test/topic", 42)
        assert mq.client.publish.call_args.args[1] == "42"

    def test_publish_float(self):
        """publish с float → str."""
        mq = self._make_mq()
        mq.publish("test/topic", 3.14)
        assert mq.client.publish.call_args.args[1] == "3.14"

    def test_publish_str(self):
        """publish со str без преобразования."""
        mq = self._make_mq()
        mq.publish("test/topic", "hello")
        assert mq.client.publish.call_args.args[1] == "hello"

    def test_publish_retain_qos(self):
        """publish передаёт retain и qos."""
        mq = self._make_mq()
        mq.publish("test/topic", "data", retain=False, qos=2)
        kwargs = mq.client.publish.call_args.kwargs
        assert kwargs["retain"] is False
        assert kwargs["qos"] == 2


class TestWorkerMQTT:
    def _make_worker(self, name="test_worker"):
        """Создаёт WorkerMQTT с моком."""
        from mqtt_client import WorkerMQTT
        with patch("mqtt_client.mqtt"):
            mq = WorkerMQTT(name)
            mq.client = MagicMock()
            mq._connected = True
            return mq

    def test_stop_requested_all(self):
        """_handle_stop с step='all' ставит _stop_requested."""
        mq = self._make_worker()
        msg = MagicMock()
        mq._handle_stop('{"step":"all"}', msg)
        assert mq.stopped() is True

    def test_stop_requested_specific(self):
        """_handle_stop с конкретным step совпадает."""
        mq = self._make_worker("faces")
        msg = MagicMock()
        mq._handle_stop('{"step":"faces"}', msg)
        assert mq.stopped() is True

    def test_stop_requested_other(self):
        """_handle_stop с чужим step не останавливает."""
        mq = self._make_worker("faces")
        msg = MagicMock()
        mq._handle_stop('{"step":"embed"}', msg)
        assert mq.stopped() is False

    def test_stop_requested_bad_json(self):
        """_handle_stop с некорректным JSON не крашит."""
        mq = self._make_worker()
        msg = MagicMock()
        mq._handle_stop("not json", msg)
        assert mq.stopped() is False

    def test_stop_requested_empty_payload(self):
        """_handle_stop с пустым payload не крашит."""
        mq = self._make_worker()
        msg = MagicMock()
        mq._handle_stop("", msg)
        assert mq.stopped() is False

    def test_pause(self):
        """_handle_pause ставит _pause_requested."""
        mq = self._make_worker()
        msg = MagicMock()
        mq._handle_pause("{}", msg)
        assert mq.paused() is True

    def test_resume(self):
        """_handle_resume снимает _pause_requested."""
        mq = self._make_worker()
        mq._handle_pause("{}", MagicMock())
        assert mq.paused() is True
        mq._handle_resume("{}", MagicMock())
        assert mq.paused() is False

    def test_publish_status(self):
        """publish_status публикует статус."""
        mq = self._make_worker("faces")
        mq.publish_status("running")
        topic = mq.client.publish.call_args.args[0]
        assert "faces" in topic
        assert mq.client.publish.call_args.args[1] == "running"

    def test_publish_progress(self):
        """publish_progress публикует done/total/pct."""
        mq = self._make_worker("embed")
        mq.publish_progress(50, 100)
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["done"] == 50
        assert payload["total"] == 100
        assert payload["pct"] == 50.0

    def test_publish_progress_extra(self):
        """publish_progress с extra добавляет поля."""
        mq = self._make_worker()
        mq.publish_progress(10, 20, extra={"phase": "detecting"})
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["phase"] == "detecting"

    def test_publish_progress_zero_total(self):
        """publish_progress с total=0 не крашит (max(total,1) = 1)."""
        mq = self._make_worker()
        mq.publish_progress(5, 0)
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["pct"] == 500.0

    def test_publish_pid(self):
        """publish_pid публикует PID процесса."""
        mq = self._make_worker()
        mq.publish_pid()
        assert mq.client.publish.call_args.args[1] == str(os.getpid())

    def test_publish_gpu_held(self):
        """publish_gpu_held публикует bool."""
        mq = self._make_worker()
        mq.publish_gpu_held(True)
        assert mq.client.publish.call_args.args[1] == "true"
        mq.publish_gpu_held(False)
        assert mq.client.publish.call_args.args[1] == "false"

    def test_publish_progress_extra_overwrites(self):
        """publish_progress extra может перезаписать done/total."""
        mq = self._make_worker()
        mq.publish_progress(5, 10, extra={"done": 999})
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["done"] == 999

    def test_release_gpu_non_gpu_worker(self):
        """release_gpu для не-GPU воркера — no-op."""
        mq = self._make_worker("exif")
        # exif not in GPU_WORKERS
        mq.release_gpu()  # не должно крашить


class TestApiMQTT:
    def _make_api(self):
        """Создаёт ApiMQTT с моком."""
        from mqtt_client import ApiMQTT, WORKER_NAMES
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
            return mq

    def test_worker_states_init(self):
        """ApiMQTT инициализирует состояния всех воркеров."""
        from mqtt_client import WORKER_NAMES
        mq = self._make_api()
        states = mq.get_worker_states()
        for name in WORKER_NAMES:
            assert name in states
            assert states[name]["status"] == "idle"
            assert states[name]["progress"] is None
            assert states[name]["pid"] is None
            assert states[name]["gpu_held"] is False

    def test_is_worker_alive_idle(self):
        """Воркер в idle — не живой."""
        mq = self._make_api()
        assert mq.is_worker_alive("faces") is False

    def test_is_worker_alive_running_no_pid(self):
        """Воркер running без pid — живой (fallback)."""
        mq = self._make_api()
        mq._worker_states["faces"]["status"] = "running"
        assert mq.is_worker_alive("faces") is True

    def test_is_worker_alive_running_with_live_pid(self):
        """Воркер running с живым pid — живой."""
        mq = self._make_api()
        mq._worker_states["faces"]["status"] = "running"
        mq._worker_states["faces"]["pid"] = os.getpid()  # текущий процесс
        assert mq.is_worker_alive("faces") is True

    def test_is_worker_alive_running_with_dead_pid(self):
        """Воркер running с мёртвым pid — мёртв, статус→dead."""
        mq = self._make_api()
        mq._worker_states["faces"]["status"] = "running"
        mq._worker_states["faces"]["pid"] = 999999  # несуществующий PID
        assert mq.is_worker_alive("faces") is False
        assert mq._worker_states["faces"]["status"] == "dead"

    def test_is_worker_alive_done(self):
        """Воркер done — не живой."""
        mq = self._make_api()
        mq._worker_states["embed"]["status"] = "done"
        assert mq.is_worker_alive("embed") is False

    def test_is_worker_alive_dead(self):
        """Воркер dead — не живой."""
        mq = self._make_api()
        mq._worker_states["describe"]["status"] = "dead"
        assert mq.is_worker_alive("describe") is False

    def test_is_worker_alive_paused_with_pid(self):
        """Воркер paused с живым pid — живой."""
        mq = self._make_api()
        mq._worker_states["faces"]["status"] = "paused"
        mq._worker_states["faces"]["pid"] = os.getpid()
        assert mq.is_worker_alive("faces") is True

    def test_get_current_step_idle(self):
        """Все idle — current_step=idle."""
        mq = self._make_api()
        assert mq.get_current_step() == "idle"

    def test_get_current_step_running(self):
        """Один воркер running — current_step=имя воркера."""
        mq = self._make_api()
        mq._worker_states["faces"]["status"] = "running"
        assert mq.get_current_step() == "faces"

    def test_get_current_step_first_running(self):
        """Первый running воркер из списка — current_step."""
        mq = self._make_api()
        mq._worker_states["describe"]["status"] = "running"
        mq._worker_states["embed"]["status"] = "running"
        step = mq.get_current_step()
        # describe раньше embed в WORKER_NAMES
        assert step == "describe"

    def test_send_start(self):
        """send_start публикует команду start."""
        mq = self._make_api()
        mq.send_start("faces", {"limit": 60})
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["step"] == "faces"
        assert payload["params"]["limit"] == 60

    def test_send_start_no_params(self):
        """send_start без params."""
        mq = self._make_api()
        mq.send_start("exif")
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["step"] == "exif"
        assert "params" not in payload

    def test_send_stop(self):
        """send_stop публикует команду stop."""
        mq = self._make_api()
        mq.send_stop("all")
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["step"] == "all"

    def test_send_pause(self):
        """send_pause публикует команду pause."""
        mq = self._make_api()
        mq.send_pause("gpu_yield")
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload["reason"] == "gpu_yield"

    def test_send_resume(self):
        """send_resume публикует команду resume."""
        mq = self._make_api()
        mq.send_resume()
        payload = json.loads(mq.client.publish.call_args.args[1])
        assert payload == {}

    def test_release_gpu_from_api(self):
        """release_gpu_from_api очищает lock и шлёт resume."""
        mq = self._make_api()
        mq.release_gpu_from_api()
        # Должен опубликовать resume
        publish_calls = mq.client.publish.call_args_list
        topics = [c.args[0] for c in publish_calls]
        assert any("resume" in t for t in topics)

    def test_get_watchdog_mode(self):
        """get_watchdog_mode возвращает текущий режим."""
        mq = self._make_api()
        assert mq.get_watchdog_mode() is None
        mq._watchdog_mode = "active"
        assert mq.get_watchdog_mode() == "active"

    def test_is_db_writing_default(self):
        """is_db_writing по умолчанию False."""
        mq = self._make_api()
        assert mq.is_db_writing() is False

    def test_make_handler_status(self):
        """_make_handler для status обновляет состояние."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("faces", "status")
        handler("running", MagicMock())
        assert mq._worker_states["faces"]["status"] == "running"

    def test_make_handler_progress(self):
        """_make_handler для progress парсит JSON."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("embed", "progress")
        handler('{"done": 50, "total": 100}', MagicMock())
        assert mq._worker_states["embed"]["progress"]["done"] == 50

    def test_make_handler_progress_bad_json(self):
        """_make_handler для progress с плохим JSON → None."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("embed", "progress")
        handler("not json", MagicMock())
        assert mq._worker_states["embed"]["progress"] is None

    def test_make_handler_pid(self):
        """_make_handler для pid парсит int."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("faces", "pid")
        handler("12345", MagicMock())
        assert mq._worker_states["faces"]["pid"] == 12345

    def test_make_handler_pid_bad(self):
        """_make_handler для pid с не-int → None."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("faces", "pid")
        handler("abc", MagicMock())
        assert mq._worker_states["faces"]["pid"] is None

    def test_make_handler_gpu_held(self):
        """_make_handler для gpu_held парсит bool."""
        from mqtt_client import ApiMQTT
        with patch("mqtt_client.mqtt"):
            mq = ApiMQTT()
            mq.client = MagicMock()
            mq._connected = True
        handler = mq._make_handler("describe", "gpu_held")
        handler("true", MagicMock())
        assert mq._worker_states["describe"]["gpu_held"] is True
        handler("false", MagicMock())
        assert mq._worker_states["describe"]["gpu_held"] is False


class TestConstants:
    def test_worker_names(self):
        from mqtt_client import WORKER_NAMES
        assert "ingest" in WORKER_NAMES
        assert "describe" in WORKER_NAMES
        assert "faces" in WORKER_NAMES
        assert "exif" in WORKER_NAMES
        assert "embed" in WORKER_NAMES
        assert "pipeline" in WORKER_NAMES

    def test_gpu_workers(self):
        from mqtt_client import GPU_WORKERS
        assert "describe" in GPU_WORKERS
        assert "faces" in GPU_WORKERS
        assert "embed" in GPU_WORKERS
        assert "enrich" in GPU_WORKERS
        assert "exif" not in GPU_WORKERS

    def test_pipeline_gpu_procs(self):
        from mqtt_client import PIPELINE_GPU_PROCS
        assert "faces.py" in PIPELINE_GPU_PROCS
        assert "embed.py" in PIPELINE_GPU_PROCS
        assert "describe.py" in PIPELINE_GPU_PROCS
