#!/usr/bin/env python3
"""
watchdog.py - Сторожевой пёс пайплайна Gailray.

Подписывается на MQTT, отслеживает LWT (dead) и PID-проверку.
При обнаружении падения:
  - Логирует инцидент
  - Очищает stale-флаги
  - Перезапускает pipeline если он упал нештатно

Запуск:
    python watchdog.py
    systemctl start gailray-watchdog
"""

import json
import os
import sys
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path

VENV_PYTHON = os.environ.get("GALLERY_VENV_PYTHON", str(Path(__file__).parent / "venv" / "bin" / "python3"))
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON, __file__] + sys.argv[1:])

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from config import FLAG_DIR, LOG_FILE

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [WATCHDOG] %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
logger = logging.getLogger(__name__)

from mqtt_client import (
    WorkerMQTT, WORKER_NAMES, GPU_WORKERS,
    worker_status_topic, worker_pid_topic,
    _topic,
)

CHECK_INTERVAL = 10
RESTART_COOLDOWN = 60
NO_RESTART_FLAG = FLAG_DIR / "no_restart"

_pipeline_restarts = []
_crash_log = []


def is_no_restart():
    if not NO_RESTART_FLAG.exists():
        return False
    for fname in ["pipeline", "describe", "faces", "exif", "embed", "ingest", "enrich"]:
        if (FLAG_DIR / fname).exists():
            return False
    return True


def log_incident(msg):
    line = f"[{datetime.now().isoformat()}] [WATCHDOG] {msg}"
    with open(str(LOG_FILE), "a") as f:
        f.write(line + "\n")
    _crash_log.append({"ts": datetime.now().isoformat(), "msg": msg})
    if len(_crash_log) > 100:
        _crash_log.pop(0)


def check_stale_flags():
    import os
    flag_dir = str(FLAG_DIR)
    if not os.path.isdir(flag_dir):
        return
    for fname in os.listdir(flag_dir):
        fpath = os.path.join(flag_dir, fname)
        if not os.path.isfile(fpath):
            continue
        if fname == "no_restart":
            continue
        worker_name = fname
        pid_path = os.path.join("/proc")
        alive = False
        pid_file = os.path.join(flag_dir, fname + ".pid")
        if os.path.exists(pid_file):
            try:
                pid = int(open(pid_file).read().strip())
                os.kill(pid, 0)
                alive = True
            except (ProcessLookupError, ValueError, FileNotFoundError, PermissionError):
                pass
        if not alive:
            try:
                pgrep = subprocess.run(
                    ["pgrep", "-f", fname.replace("describe", "vision_describe")],
                    capture_output=True, text=True,
                )
                if pgrep.stdout.strip():
                    alive = True
            except Exception:
                pass
        if not alive:
            logger.warning(f"Stale flag: {fname} (no live process)")
            log_incident(f"STALE FLAG: {fname} — флаг есть, процесса нет, удаляю")
            os.remove(fpath)


def restart_pipeline():
    if is_no_restart():
        logger.info("Флаг no_restart — перезапуск заблокирован (ручная остановка)")
        return
    now = time.time()
    recent = [t for t in _pipeline_restarts if now - t < 300]
    if len(recent) >= 3:
        logger.warning("Слишком много рестартов за 5 минут, пропускаю")
        return
    _pipeline_restarts.append(now)
    logger.info("Перезапуск pipeline через systemctl...")
    log_incident("PIPELINE RESTART: нештатное падение, перезапуск через systemctl")
    for fname in os.listdir(str(FLAG_DIR)):
        fpath = os.path.join(str(FLAG_DIR), fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
    time.sleep(2)
    subprocess.run(["systemctl", "restart", "gailray-pipeline"], check=False)


class WatchdogMQTT(WorkerMQTT):
    def __init__(self):
        super().__init__("watchdog")
        self._worker_statuses = {}
        self._worker_pids = {}
        self._last_mode = None
        for name in WORKER_NAMES:
            self._worker_statuses[name] = "idle"
            self._worker_pids[name] = None

    def publish_mode(self):
        mode = "sleeping" if is_no_restart() else "active"
        if mode != self._last_mode:
            self._last_mode = mode
            label = "дремлет" if mode == "sleeping" else "активен"
            logger.info(f"Режим: {label}")
            log_incident(f"MODE: пёс {label}")
        self.publish(_topic("watchdog", "mode"), mode, retain=True)

    def connect(self):
        result = super().connect()
        if result:
            for name in WORKER_NAMES:
                self.subscribe(worker_status_topic(name), self._make_status_handler(name))
                self.subscribe(worker_pid_topic(name), self._make_pid_handler(name))
        return result

    def _make_status_handler(self, name):
        def handler(payload, msg):
            old = self._worker_statuses.get(name, "idle")
            self._worker_statuses[name] = payload
            if payload == "dead" and old not in ("idle", "done", "dead", "", None):
                logger.warning(f"LWT DEAD: {name} был {old}, теперь dead!")
                log_incident(f"LWT DEAD: {name} упал нештатно (был {old} → dead)")
                if name == "pipeline":
                    if is_no_restart():
                        logger.info(f"no_restart: {name} не перезапускаю (ручная остановка)")
                    else:
                        restart_pipeline()
            if payload == "running" and old == "dead":
                logger.info(f"RECOVERY: {name} снова running")
                log_incident(f"RECOVERY: {name} восстановлен (dead → running)")
        return handler

    def _make_pid_handler(self, name):
        def handler(payload, msg):
            try:
                self._worker_pids[name] = int(payload)
            except (ValueError, TypeError):
                self._worker_pids[name] = None
        return handler

    def check_pids(self):
        for name in WORKER_NAMES:
            status = self._worker_statuses.get(name, "idle")
            pid = self._worker_pids.get(name)
            if status == "running" and pid:
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, PermissionError, OSError):
                    logger.warning(f"PID DEAD: {name} pid={pid} мёртв, но status=running")
                    log_incident(f"PID DEAD: {name} pid={pid} мёртв, статус не обновлён (стале)")
                    self._worker_statuses[name] = "dead"
                    if name == "pipeline":
                        if is_no_restart():
                            logger.info(f"no_restart: {name} не перезапускаю (ручная остановка)")
                        else:
                            restart_pipeline()

    def get_crash_log(self):
        return list(_crash_log)


def main():
    logger.info("Сторожевой пёс запущен")
    mq = WatchdogMQTT()
    mq.connect()
    time.sleep(2)
    mq.publish_status("running")

    try:
        while True:
            mq.publish_mode()
            mq.check_pids()
            check_stale_flags()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Остановлен по Ctrl+C")
    finally:
        mq.shutdown()


if __name__ == "__main__":
    main()
