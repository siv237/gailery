#!/usr/bin/env python3
"""
watchdog.py - Сторожевой пёс пайплайна Gailray.

Логика:
  - Проверяет факт работы pipeline (systemctl is-active)
  - Если pipeline не работает и НЕТ флага no_restart — запускает
  - Если есть флаг no_restart (ручная остановка) — сидит молча
  - Убирает stale-флаги воркеров
  - Публикует свой режим (active/sleeping) через MQTT

Запуск:
    python watchdog.py
    systemctl start gailray-watchdog
"""

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

CHECK_INTERVAL = 10
NO_RESTART_FLAG = FLAG_DIR / "no_restart"
PIPELINE_SERVICE = "gailray-pipeline"

_crash_log = []
_pipeline_restarts = []


def is_no_restart():
    return NO_RESTART_FLAG.exists()


def is_pipeline_active():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", PIPELINE_SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "active"
    except Exception:
        return False


def ensure_pipeline_enabled():
    try:
        r = subprocess.run(
            ["systemctl", "is-enabled", PIPELINE_SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        if "enabled" not in r.stdout.strip():
            logger.info("Pipeline disabled — восстанавливаю enable")
            subprocess.run(["systemctl", "enable", PIPELINE_SERVICE], check=False, timeout=5)
    except Exception:
        pass


def start_pipeline():
    if is_no_restart():
        logger.info("no_restart — запуск заблокирован (ручная остановка)")
        return False
    now = time.time()
    recent = [t for t in _pipeline_restarts if now - t < 300]
    if len(recent) >= 3:
        logger.warning("Слишком много рестартов за 5 минут, пропускаю")
        return False
    _pipeline_restarts.append(now)
    ensure_pipeline_enabled()
    logger.info("Pipeline не работает — запускаю")
    log_incident("PIPELINE START: пёс запускает неработающий pipeline")
    subprocess.run(["systemctl", "start", PIPELINE_SERVICE], check=False, timeout=10)
    return True


def log_incident(msg):
    line = f"[{datetime.now().isoformat()}] [WATCHDOG] {msg}"
    with open(str(LOG_FILE), "a") as f:
        f.write(line + "\n")
    _crash_log.append({"ts": datetime.now().isoformat(), "msg": msg})
    if len(_crash_log) > 100:
        _crash_log.pop(0)


def check_stale_flags():
    flag_dir = str(FLAG_DIR)
    if not os.path.isdir(flag_dir):
        return
    for fname in os.listdir(flag_dir):
        if fname == "no_restart":
            continue
        fpath = os.path.join(flag_dir, fname)
        if not os.path.isfile(fpath):
            continue
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
            log_incident(f"STALE FLAG: {fname} — удаляю")
            os.remove(fpath)


def main():
    logger.info("Сторожевой пёс запущен")

    try:
        from mqtt_client import WorkerMQTT, _topic
        mq = WorkerMQTT("watchdog")
        mq.connect()
        time.sleep(2)
        mq.publish_status("running")
        _mqtt = True
    except Exception:
        _mqtt = False
        mq = None

    if not is_no_restart() and not is_pipeline_active():
        start_pipeline()

    try:
        while True:
            mode = "sleeping" if is_no_restart() else "active"

            if not is_no_restart() and not is_pipeline_active():
                logger.info("Pipeline не работает! Запускаю...")
                start_pipeline()
                mode = "active"

            if _mqtt:
                try:
                    mq.publish(_topic("watchdog", "mode"), mode, retain=True)
                except Exception:
                    pass

            check_stale_flags()
            log_incident(f"HEARTBEAT: pipeline={'active' if is_pipeline_active() else 'dead'}, mode={mode}")

            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Остановлен по Ctrl+C")
    finally:
        if _mqtt:
            try:
                mq.shutdown()
            except Exception:
                pass


if __name__ == "__main__":
    main()
