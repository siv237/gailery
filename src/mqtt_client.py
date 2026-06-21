"""
mqtt_client.py - Shared MQTT client for Gailray pipeline workers and API.

Topics:
  {PREFIX}/worker/{name}/status     - retained: idle|running|paused|done|failed|dead
  {PREFIX}/worker/{name}/progress   - retained: {"done":N,"total":M,"pct":P}
  {PREFIX}/worker/{name}/pid        - retained: <pid>
  {PREFIX}/worker/{name}/gpu_held   - retained: true|false
  {PREFIX}/gpu/lock                 - retained: {"holder":"<name>","since":"<iso>","pid":N} or empty
  {PREFIX}/control/start            - command: {"step":"<name>","params":{...}}
  {PREFIX}/control/stop             - command: {"step":"<name>"} or {"step":"all"}
  {PREFIX}/control/pause            - command: {"reason":"gpu_yield"}
  {PREFIX}/control/resume           - command: {}
"""

import json
import os
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

_MQTT_HOST = os.environ.get("GALLERY_MQTT_HOST", "127.0.0.1")
_MQTT_PORT = int(os.environ.get("GALLERY_MQTT_PORT", "1883"))
_MQTT_WS_PORT = int(os.environ.get("GALLERY_MQTT_WS_PORT", "9001"))

PREFIX = os.environ.get("GALLERY_MQTT_PREFIX", "gailery")

WORKER_NAMES = [
    "ingest", "describe", "faces", "exif", "embed",
    "pipeline", "thumbnails", "scan_catalog", "enrich",
]

GPU_WORKERS = ["describe", "faces", "embed", "enrich"]


def _topic(*parts):
    return "/".join([PREFIX] + list(parts))


def worker_status_topic(name):
    return _topic("worker", name, "status")


def worker_progress_topic(name):
    return _topic("worker", name, "progress")


def worker_pid_topic(name):
    return _topic("worker", name, "pid")


def worker_gpu_held_topic(name):
    return _topic("worker", name, "gpu_held")


def gpu_lock_topic():
    return _topic("gpu", "lock")


def control_start_topic():
    return _topic("control", "start")


def control_stop_topic():
    return _topic("control", "stop")


def control_pause_topic():
    return _topic("control", "pause")


def control_resume_topic():
    return _topic("control", "resume")


def watchdog_mode_topic():
    return _topic("watchdog", "mode")


class GailrayMQTT:
    def __init__(self, client_id=None, host=None, port=None):
        self.host = host or _MQTT_HOST
        self.port = port or _MQTT_PORT
        cid = client_id or f"{PREFIX}-{os.getpid()}"
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=cid,
            protocol=mqtt.MQTTv311,
        )
        self.client.enable_logger(logger)
        self._connected = False
        self._sub_handlers = {}
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, _userdata, _flags, rc, _properties=None):
        if rc == 0:
            self._connected = True
            logger.info(f"MQTT connected to {self.host}:{self.port}")
            for topic in self._sub_handlers:
                client.subscribe(topic, qos=1)
        else:
            logger.error(f"MQTT connect failed rc={rc}")

    def _on_message(self, client, _userdata, msg):
        topic = msg.topic
        if topic in self._sub_handlers:
            try:
                payload = msg.payload.decode("utf-8")
            except Exception:
                payload = msg.payload
            self._sub_handlers[topic](payload, msg)

    def connect(self):
        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()
        for _ in range(50):
            if self._connected:
                return True
            time.sleep(0.1)
        logger.warning("MQTT connection timeout, continuing without MQTT")
        return False

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic, payload, retain=True, qos=1):
        if isinstance(payload, dict):
            payload = json.dumps(payload, ensure_ascii=False)
        elif isinstance(payload, bool):
            payload = "true" if payload else "false"
        elif isinstance(payload, (int, float)):
            payload = str(payload)
        elif not isinstance(payload, str):
            payload = str(payload)
        try:
            self.client.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logger.error(f"MQTT publish error: {e}")

    def subscribe(self, topic, handler, qos=1):
        self._sub_handlers[topic] = handler
        if self._connected:
            self.client.subscribe(topic, qos=qos)

    def clear_topic(self, topic):
        self.publish(topic, "", retain=True, qos=1)


class WorkerMQTT(GailrayMQTT):
    def __init__(self, worker_name, host=None, port=None):
        self.worker_name = worker_name
        super().__init__(
            client_id=f"{PREFIX}-{worker_name}-{os.getpid()}",
            host=host,
            port=port,
        )
        self._stop_requested = False
        self._pause_requested = False
        lwt_topic = worker_status_topic(worker_name)
        lwt_payload = "dead"
        self.client.will_set(lwt_topic, lwt_payload, qos=1, retain=True)

    def connect(self):
        result = super().connect()
        if result:
            self.subscribe(control_stop_topic(), self._handle_stop)
            self.subscribe(control_pause_topic(), self._handle_pause)
            self.subscribe(control_resume_topic(), self._handle_resume)
            stop_topic = _topic("control", "stop", self.worker_name)
            self.subscribe(stop_topic, self._handle_stop)
        return result

    def _handle_stop(self, payload, msg):
        try:
            data = json.loads(payload) if payload.startswith("{") else {}
        except Exception:
            data = {}
        step = data.get("step", "")
        if step == "all" or step == self.worker_name:
            self._stop_requested = True
            logger.info(f"[MQTT] Stop requested for {self.worker_name}")

    def _handle_pause(self, payload, msg):
        self._pause_requested = True
        logger.info(f"[MQTT] Pause requested for {self.worker_name}")

    def _handle_resume(self, payload, msg):
        self._pause_requested = False
        logger.info(f"[MQTT] Resume for {self.worker_name}")

    def stopped(self):
        return self._stop_requested

    def paused(self):
        return self._pause_requested

    def wait_while_paused(self, timeout=300):
        t0 = time.time()
        while self._pause_requested and not self._stop_requested:
            time.sleep(1)
            if time.time() - t0 > timeout:
                logger.warning(f"[MQTT] Pause timeout for {self.worker_name}")
                break
        return not self._stop_requested

    def publish_status(self, status):
        self.publish(worker_status_topic(self.worker_name), status)

    def publish_progress(self, done, total, extra=None):
        data = {"done": done, "total": total, "pct": round(done / max(total, 1) * 100, 1)}
        if extra:
            data.update(extra)
        self.publish(worker_progress_topic(self.worker_name), data)

    def publish_pid(self):
        self.publish(worker_pid_topic(self.worker_name), os.getpid())

    def publish_gpu_held(self, held):
        self.publish(worker_gpu_held_topic(self.worker_name), held)

    def _read_gpu_lock(self):
        lock_topic = gpu_lock_topic()
        try:
            from paho.mqtt.properties import ConnectProperties
        except Exception:
            pass
        result = {"_empty": True}

        class _Temp:
            payload = None
        temp = _Temp()

        def _on_msg(client, _userdata, msg):
            if msg.topic == lock_topic:
                temp.payload = msg.payload.decode("utf-8") if msg.payload else ""

        self.client.message_callback_add(lock_topic, _on_msg)
        self.client.subscribe(lock_topic, qos=1)
        time.sleep(0.3)
        self.client.message_callback_remove(lock_topic)
        if temp.payload and temp.payload.strip():
            try:
                result = json.loads(temp.payload)
                result["_empty"] = False
            except Exception:
                pass
        return result

    def acquire_gpu(self, timeout=120):
        if self.worker_name not in GPU_WORKERS:
            return True
        lock_topic = gpu_lock_topic()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.stopped():
                return False
            lock = self._read_gpu_lock()
            holder = lock.get("holder", "")
            if lock.get("_empty", True) or not holder:
                self.client.publish(
                    lock_topic,
                    json.dumps({
                        "holder": self.worker_name,
                        "since": datetime.now(timezone.utc).isoformat(),
                        "pid": os.getpid(),
                    }),
                    qos=1,
                    retain=True,
                )
                time.sleep(0.2)
                verify = self._read_gpu_lock()
                if verify.get("holder") == self.worker_name:
                    self.publish_gpu_held(True)
                    logger.info(f"[MQTT] GPU acquired by {self.worker_name}")
                    return True
                logger.warning(f"[MQTT] GPU race: expected {self.worker_name}, got {verify.get('holder')}")
            else:
                holder_pid = lock.get("pid")
                if holder_pid:
                    try:
                        os.kill(holder_pid, 0)
                    except (ProcessLookupError, PermissionError, OSError):
                        logger.info(f"[MQTT] GPU holder '{holder}' pid={holder_pid} dead, clearing stale lock")
                        self.clear_topic(lock_topic)
                        continue
            logger.info(f"[MQTT] GPU held by '{holder}', waiting... ({time.time()-t0:.0f}s/{timeout}s)")
            time.sleep(2)
        logger.warning(f"[MQTT] GPU acquire timeout for {self.worker_name}")
        return False

    def release_gpu(self):
        if self.worker_name not in GPU_WORKERS:
            return
        lock = self._read_gpu_lock()
        if lock.get("holder") == self.worker_name:
            self.clear_topic(gpu_lock_topic())
        self.publish_gpu_held(False)

    def shutdown(self):
        self.clear_topic(worker_status_topic(self.worker_name))
        self.clear_topic(worker_pid_topic(self.worker_name))
        self.clear_topic(worker_progress_topic(self.worker_name))
        self.clear_topic(worker_gpu_held_topic(self.worker_name))
        self.release_gpu()
        try:
            self.client.will_set(
                worker_status_topic(self.worker_name),
                payload="", qos=1, retain=True,
            )
        except Exception:
            pass
        self.disconnect()


class ApiMQTT(GailrayMQTT):
    def __init__(self, host=None, port=None):
        super().__init__(
            client_id=f"{PREFIX}-api-{os.getpid()}",
            host=host,
            port=port,
        )
        self._worker_states = {}
        self._watchdog_mode = None
        for name in WORKER_NAMES:
            self._worker_states[name] = {
                "status": "idle",
                "progress": None,
                "pid": None,
                "gpu_held": False,
            }

    def connect(self):
        result = super().connect()
        if result:
            for name in WORKER_NAMES:
                self.subscribe(worker_status_topic(name), self._make_handler(name, "status"))
                self.subscribe(worker_progress_topic(name), self._make_handler(name, "progress"))
                self.subscribe(worker_pid_topic(name), self._make_handler(name, "pid"))
                self.subscribe(worker_gpu_held_topic(name), self._make_handler(name, "gpu_held"))
            self.subscribe(gpu_lock_topic(), self._gpu_lock_handler)
            self.subscribe(watchdog_mode_topic(), self._watchdog_mode_handler)
            self.subscribe(DB_WRITING_TOPIC, self._db_writing_handler)
        return result

    def _make_handler(self, name, field):
        def handler(payload, msg):
            if field == "progress":
                try:
                    self._worker_states[name][field] = json.loads(payload)
                except Exception:
                    self._worker_states[name][field] = None
            elif field == "pid":
                try:
                    self._worker_states[name][field] = int(payload)
                except Exception:
                    self._worker_states[name][field] = None
            elif field == "gpu_held":
                self._worker_states[name][field] = payload.lower() == "true"
            else:
                self._worker_states[name][field] = payload
        return handler

    def _gpu_lock_handler(self, payload, msg):
        pass

    def _watchdog_mode_handler(self, payload, msg):
        self._watchdog_mode = payload

    def _db_writing_handler(self, payload, msg):
        self._db_writing = payload.lower() == "true"

    def is_db_writing(self):
        return getattr(self, '_db_writing', False)

    def get_watchdog_mode(self):
        return self._watchdog_mode

    def get_worker_states(self):
        return dict(self._worker_states)

    def is_worker_alive(self, name):
        state = self._worker_states.get(name, {})
        status = state.get("status", "idle")
        pid = state.get("pid")
        if status in ("idle", "done", "dead", ""):
            return False
        if status in ("running", "paused"):
            if pid:
                try:
                    os.kill(pid, 0)
                    return True
                except (ProcessLookupError, PermissionError, OSError):
                    self._worker_states[name]["status"] = "dead"
                    return False
            return status == "running"
        return False

    def get_current_step(self):
        for name in WORKER_NAMES:
            if self.is_worker_alive(name):
                return name
        return "idle"

    def get_gpu_holder(self):
        return self._worker_states

    def send_start(self, step, params=None):
        data = {"step": step}
        if params:
            data["params"] = params
        self.publish(control_start_topic(), data, retain=False)

    def send_stop(self, step="all"):
        self.publish(control_stop_topic(), {"step": step}, retain=False)

    def send_pause(self, reason="gpu_yield"):
        self.publish(control_pause_topic(), {"reason": reason}, retain=False)

    def send_resume(self):
        self.publish(control_resume_topic(), {}, retain=False)

    def request_gpu_for_api(self, worker_name="api", timeout=3):
        t0 = time.time()
        self.send_pause(reason="gpu_yield")
        while time.time() - t0 < timeout:
            any_gpu = False
            for name in GPU_WORKERS:
                if self._worker_states.get(name, {}).get("gpu_held", False):
                    any_gpu = True
                    break
            if not any_gpu:
                break
            time.sleep(0.3)
        if any_gpu:
            logger.warning(f"[MQTT] GPU still held after {time.time()-t0:.1f}s, forcing pkill")
            os.system("pkill -9 -f 'llama-server' 2>/dev/null")
            for pattern in PIPELINE_GPU_PROCS:
                os.system(f"pkill -f '{pattern}' 2>/dev/null")
            time.sleep(0.5)
        logger.info(f"[MQTT] GPU acquired for {worker_name} in {time.time()-t0:.1f}s")
        self.publish(gpu_lock_topic(), json.dumps({
            "holder": worker_name,
            "since": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }), retain=True)

    def request_gpu_gentle(self, worker_name="api", timeout=30):
        t0 = time.time()
        logger.info(f"[MQTT] Gentle GPU request for {worker_name}, waiting up to {timeout}s")
        self.send_pause(reason="gpu_yield")
        wait_deadline = t0 + 5
        while time.time() < wait_deadline:
            any_gpu = False
            for name in GPU_WORKERS:
                if self._worker_states.get(name, {}).get("gpu_held", False):
                    any_gpu = True
                    break
            if not any_gpu:
                break
            time.sleep(0.5)
        if any_gpu:
            logger.warning(f"[MQTT] GPU still held after {time.time()-t0:.1f}s — killing llama-server")
            os.system("pkill -9 -f 'llama-server' 2>/dev/null")
            time.sleep(1)
        self.send_resume()
        self.publish(gpu_lock_topic(), json.dumps({
            "holder": worker_name,
            "since": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
        }), retain=True)
        logger.info(f"[MQTT] GPU acquired gently for {worker_name} in {time.time()-t0:.1f}s")
        return True

    def release_gpu_from_api(self):
        self.clear_topic(gpu_lock_topic())
        self.send_resume()

    def db_write(self, cmd, params=None, timeout=30):
        request_id = f"{os.getpid()}_{int(time.time()*1000)}"
        result_topic = db_result_topic(request_id)
        result_box = {"data": None}
        done_event = threading.Event()

        def _on_result(payload, msg):
            try:
                result_box["data"] = json.loads(payload)
            except Exception:
                result_box["data"] = {"ok": False, "error": f"bad json: {payload[:200]}"}
            done_event.set()

        self.subscribe(result_topic, _on_result)
        self.publish(DB_CMD_TOPIC, {
            "cmd": cmd,
            "params": params or {},
            "request_id": request_id,
        }, retain=False)

        got = done_event.wait(timeout=timeout)
        try:
            self.client.unsubscribe(result_topic)
        except Exception:
            pass

        if not got:
            return {"ok": False, "error": f"db_write timeout ({timeout}s) for cmd={cmd}"}
        return result_box["data"]


PIPELINE_GPU_PROCS = [
    "face_pipeline", "faces.py", "faces",
    "vision_describe", "describe.py", "describe",
    "embed.py", "embed",
    "enrich_description.py", "enrich_description",
]

DB_CMD_TOPIC = _topic("db", "cmd")
DB_RESULT_PREFIX = _topic("db", "result")
DB_WRITING_TOPIC = _topic("db", "writing")


def db_result_topic(request_id):
    return f"{DB_RESULT_PREFIX}/{request_id}"


def create_worker_mqtt(name, host=None, port=None):
    mq = WorkerMQTT(name, host=host, port=port)
    mq.connect()
    mq.publish_status("running")
    mq.publish_pid()
    return mq


def create_api_mqtt(host=None, port=None):
    mq = ApiMQTT(host=host, port=port)
    mq.connect()
    return mq
