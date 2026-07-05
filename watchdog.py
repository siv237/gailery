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
    systemctl start <watchdog-service>
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

from config import FLAG_DIR, WATCHDOG_LOG_FILE, PIPELINE_SERVICE

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [WATCHDOG] %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
logger = logging.getLogger(__name__)

CHECK_INTERVAL = 10
NO_RESTART_FLAG = FLAG_DIR / "no_restart"
PIPELINE_IDLE_FLAG = FLAG_DIR / "pipeline_idle"

MEMORY_WARN_PCT = 85
MEMORY_CRIT_PCT = 93
RSS_LIMIT_GB = 5.0
WORKER_PROCESSES = ["faces.py", "describe.py", "embed.py", "exif.py", "ingest.py", "enrich_description.py", "vision_describe.py", "llama-server"]
PIPELINE_PROCESS = "pipeline.py"

_crash_log = []
_pipeline_restarts = []
_last_memory_check = 0
_memory_check_interval = 30


def is_no_restart():
    return NO_RESTART_FLAG.exists()


def is_pipeline_active():
    try:
        r = subprocess.run(
            ["systemctl", "is-active", PIPELINE_SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() == "active"
    except (OSError, subprocess.SubprocessError):
        return False


def is_pipeline_enabled():
    try:
        r = subprocess.run(
            ["systemctl", "is-enabled", PIPELINE_SERVICE],
            capture_output=True, text=True, timeout=5,
        )
        return "enabled" in r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def start_pipeline():
    if is_no_restart():
        logger.info("no_restart — запуск заблокирован (ручная остановка)")
        return False
    now = time.time()
    recent = [t for t in _pipeline_restarts if now - t < 600]
    if len(recent) >= 5:
        logger.warning("Слишком много рестартов за 10 минут, пропускаю")
        return False
    _pipeline_restarts.append(now)
    logger.info("Pipeline не работает — запускаю")
    log_incident("PIPELINE START: пёс запускает неработающий pipeline")
    try:
        subprocess.run(["systemctl", "start", PIPELINE_SERVICE], check=False, timeout=60)
    except subprocess.TimeoutExpired:
        logger.warning("systemctl start timeout (60s) — pipeline мог стартовать, продолжаю")
        log_incident("PIPELINE START TIMEOUT: systemctl start завис, но pipeline мог запуститься")
    time.sleep(3)
    if is_pipeline_active():
        _pipeline_restarts.clear()
        logger.info("Pipeline успешно запущен")
    else:
        logger.warning("Pipeline не стартовал после запуска")
    return True


def log_incident(msg):
    line = f"[{datetime.now().isoformat()}] [WATCHDOG] {msg}"
    with open(str(WATCHDOG_LOG_FILE), "a") as f:
        f.write(line + "\n")
    _crash_log.append({"ts": datetime.now().isoformat(), "msg": msg})
    if len(_crash_log) > 100:
        _crash_log.pop(0)


def _get_process_map():
    ps = subprocess.run(
        ["ps", "aux", "--no-headers"],
        capture_output=True, text=True, timeout=10,
    )
    procs = []
    for line in ps.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        _user, pid, cpu, mem, _vsz, rss, _tty, stat, start, _etime, cmd = parts
        procs.append({
            "pid": int(pid),
            "rss_mb": int(rss) // 1024,
            "pct_mem": float(mem),
            "pct_cpu": float(cpu),
            "cmd": cmd,
        })
    return procs


def _get_cgroup(pid):
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            return f.read().strip()
    except (OSError, UnicodeDecodeError):
        return ""


def check_duplicate_pipelines():
    procs = _get_process_map()
    pipelines = [p for p in procs if PIPELINE_PROCESS in p["cmd"]]
    if len(pipelines) <= 1:
        return
    logger.warning(f"Обнаружено {len(pipelines)} процессов pipeline.py!")
    log_incident(f"DUPLICATE PIPELINE: {len(pipelines)} инстанса pipeline.py")
    service_pids = set()
    try:
        r = subprocess.run(
            ["systemctl", "show", PIPELINE_SERVICE, "--property=MainPID", "--value"],
            capture_output=True, text=True, timeout=5,
        )
        main_pid = int(r.stdout.strip())
        if main_pid > 0:
            service_pids.add(main_pid)
            try:
                cg = _get_cgroup(main_pid)
                for p in pipelines:
                    if _get_cgroup(p["pid"]) == cg:
                        service_pids.add(p["pid"])
            except (OSError, ValueError):
                pass
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    for p in pipelines:
        if p["pid"] not in service_pids:
            logger.warning(f"Убиваю дублирующий pipeline PID={p['pid']} RSS={p['rss_mb']}MB")
            log_incident(f"KILL DUPLICATE: pipeline.py PID={p['pid']} RSS={p['rss_mb']}MB")
            try:
                os.kill(p["pid"], 9)
            except ProcessLookupError:
                pass


def check_orphan_workers():
    procs = _get_process_map()
    all_pids = {p["pid"] for p in procs}
    orphans = []
    for w in procs:
        if not any(wk in w["cmd"] for wk in WORKER_PROCESSES):
            continue
        try:
            with open(f"/proc/{w['pid']}/stat") as f:
                stat = f.read().split()
            ppid = int(stat[3])
            if ppid == 1:
                orphans.append(w)
            elif ppid not in all_pids:
                orphans.append(w)
        except (OSError, ValueError):
            continue
    if not orphans:
        return
    for w in orphans:
        logger.warning(f"Сирота: {w['cmd'][:60]} PID={w['pid']} RSS={w['rss_mb']}MB")
        log_incident(f"ORPHAN: PID={w['pid']} {w['cmd'][:60]} RSS={w['rss_mb']}MB — убиваю")
        try:
            os.kill(w["pid"], 9)
        except ProcessLookupError:
            pass


def check_memory_pressure():
    global _last_memory_check
    now = time.time()
    if now - _last_memory_check < _memory_check_interval:
        return
    _last_memory_check = now
    try:
        with open("/proc/meminfo") as f:
            mi = {}
            for line in f:
                parts = line.split()
                mi[parts[0].rstrip(":")] = int(parts[1])
        total = mi["MemTotal"]
        available = mi.get("MemAvailable", mi.get("MemFree", 0))
        used_pct = (total - available) / total * 100
    except (OSError, ValueError, KeyError):
        return
    if used_pct < MEMORY_WARN_PCT:
        return
    procs = _get_process_map()
    our_procs = [p for p in procs if any(
        name in p["cmd"] for name in WORKER_PROCESSES + [PIPELINE_PROCESS, "uvicorn"]
    )]
    our_procs.sort(key=lambda p: p["rss_mb"], reverse=True)
    top_summary = "; ".join(
        f"{p['cmd'].split('/')[-1][:20]}={p['rss_mb']}MB" for p in our_procs[:5]
    )
    if used_pct >= MEMORY_CRIT_PCT:
        logger.error(f"КРИТИЧЕСКАЯ память: {used_pct:.0f}%! Топ: {top_summary}")
        log_incident(f"MEMORY CRITICAL: {used_pct:.0f}% — убиваю процессы >{RSS_LIMIT_GB}GB")
        for p in our_procs:
            if p["rss_mb"] > RSS_LIMIT_GB * 1024 and "uvicorn" not in p["cmd"]:
                logger.warning(f"KILL: {p['cmd'][:60]} PID={p['pid']} RSS={p['rss_mb']}MB")
                log_incident(f"MEMORY KILL: PID={p['pid']} {p['cmd'][:60]} RSS={p['rss_mb']}MB")
                try:
                    os.kill(p["pid"], 9)
                except ProcessLookupError:
                    pass
    else:
        logger.warning(f"Высокая память: {used_pct:.0f}%. Топ: {top_summary}")
        log_incident(f"MEMORY WARNING: {used_pct:.0f}% — {top_summary}")
        for p in our_procs:
            if p["rss_mb"] > RSS_LIMIT_GB * 1024 * 1.5 and "uvicorn" not in p["cmd"]:
                logger.warning(f"KILL: {p['cmd'][:60]} PID={p['pid']} RSS={p['rss_mb']}MB (>1.5x limit)")
                log_incident(f"MEMORY KILL: PID={p['pid']} {p['cmd'][:60]} RSS={p['rss_mb']}MB")
                try:
                    os.kill(p["pid"], 9)
                except ProcessLookupError:
                    pass


def check_stale_flags():
    flag_dir = str(FLAG_DIR)
    if not os.path.isdir(flag_dir):
        return
    for fname in os.listdir(flag_dir):
        if fname in ("no_restart", "pipeline_idle"):
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
            except (OSError, subprocess.SubprocessError):
                pass
        if not alive:
            logger.warning(f"Stale flag: {fname} (no live process)")
            log_incident(f"STALE FLAG: {fname} — удаляю")
            os.remove(fpath)
            if fname == "pipeline":
                try:
                    os.remove(str(PIPELINE_IDLE_FLAG))
                except OSError:
                    pass


def _setup_watchdog_mqtt():
    try:
        from mqtt_client import WorkerMQTT
        mq = WorkerMQTT("watchdog")
        mq.connect()
        time.sleep(2)
        mq.publish_status("running")
        return mq, True
    except (ImportError, ConnectionError):
        return None, False


def _publish_watchdog_mode(mq, _mqtt, mode):
    if not _mqtt:
        return
    try:
        from mqtt_client import _topic
        mq.publish(_topic("watchdog", "mode"), mode, retain=True)
    except (RuntimeError, OSError):
        pass


def _run_health_checks():
    try:
        check_stale_flags()
        check_duplicate_pipelines()
        check_orphan_workers()
        check_memory_pressure()
    except (RuntimeError, OSError, ValueError) as e:
        logger.warning(f"Ошибка в check_*: {e}")


def _watchdog_loop_body(mq, _mqtt):
    if is_no_restart():
        _publish_watchdog_mode(mq, _mqtt, "sleeping")
        time.sleep(CHECK_INTERVAL)
        return

    is_idle = PIPELINE_IDLE_FLAG.exists()
    mode = "waiting" if is_idle else "active"

    if not is_pipeline_enabled():
        pass
    elif not is_pipeline_active() and not is_idle:
        logger.info("Pipeline не работает! Запускаю...")
        start_pipeline()

    _publish_watchdog_mode(mq, _mqtt, mode)
    _run_health_checks()

    if not is_idle:
        log_incident(f"HEARTBEAT: pipeline={'active' if is_pipeline_active() else 'dead'}, mode={mode}")

    time.sleep(CHECK_INTERVAL)


def main():
    logger.info("Сторожевой пёс запущен")

    mq, _mqtt = _setup_watchdog_mqtt()

    if not is_no_restart() and not is_pipeline_active():
        start_pipeline()

    try:
        while True:
            _watchdog_loop_body(mq, _mqtt)
    except KeyboardInterrupt:
        logger.info("Остановлен по Ctrl+C")
    finally:
        if _mqtt:
            try:
                mq.shutdown()
            except (RuntimeError, OSError):
                pass


if __name__ == "__main__":
    main()
