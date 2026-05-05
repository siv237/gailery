#!/usr/bin/env python3
"""system_monitor.py — сбор системных метрик раз в 60 секунд."""

import asyncio
import os
import platform
import socket
import subprocess
import time
from datetime import datetime, timezone

import psutil

_first_net = None
_first_disk = None
_last_collect_time = None


def _net_gb():
    global _first_net
    net = psutil.net_io_counters()
    if _first_net is None:
        _first_net = (net.bytes_recv, net.bytes_sent)
    return (net.bytes_recv - _first_net[0]) / 1e9, (net.bytes_sent - _first_net[1]) / 1e9


def _net_speed():
    global _first_net, _last_collect_time
    net = psutil.net_io_counters()
    now = time.time()
    if _first_net is None or _last_collect_time is None:
        _first_net = (net.bytes_recv, net.bytes_sent)
        _last_collect_time = now
        return 0.0, 0.0
    dt = now - _last_collect_time
    if dt <= 0:
        return 0.0, 0.0
    rx_mbps = ((net.bytes_recv - _first_net[0]) * 8) / (dt * 1_000_000)
    tx_mbps = ((net.bytes_sent - _first_net[1]) * 8) / (dt * 1_000_000)
    _first_net = (net.bytes_recv, net.bytes_sent)
    _last_collect_time = now
    return round(rx_mbps, 2), round(tx_mbps, 2)


def _disk_io_speed():
    global _first_disk
    io = psutil.disk_io_counters()
    if io is None:
        return 0.0, 0.0
    if _first_disk is None:
        _first_disk = (io.read_bytes, io.write_bytes, time.time())
        return 0.0, 0.0
    prev_read, prev_write, prev_time = _first_disk
    now = time.time()
    dt = now - prev_time
    if dt <= 0:
        return 0.0, 0.0
    read_mb_s = (io.read_bytes - prev_read) / (dt * 1024 * 1024)
    write_mb_s = (io.write_bytes - prev_write) / (dt * 1024 * 1024)
    _first_disk = (io.read_bytes, io.write_bytes, now)
    return round(read_mb_s, 1), round(write_mb_s, 1)


def _nvidia_smi(*fields):
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=" + ",".join(fields),
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        return [p.strip() for p in out.stdout.strip().split(", ")]
    except Exception:
        return ["0"] * len(fields)


def _gpu_metrics():
    vals = _nvidia_smi(
        "utilization.gpu", "memory.used", "memory.total",
        "temperature.gpu", "power.draw", "fan.speed",
        "clocks.current.sm", "clocks.current.memory",
    )
    try:
        return {
            "gpu_load": float(vals[0]) if vals[0] else 0,
            "gpu_vram_mb": float(vals[1]) if vals[1] else 0,
            "gpu_vram_total": float(vals[2]) if vals[2] else 0,
            "gpu_temp": float(vals[3]) if vals[3] else 0,
            "gpu_power_w": float(vals[4]) if vals[4] else 0,
            "gpu_fan": float(vals[5]) if vals[5] else 0,
            "gpu_sm_clock": float(vals[6]) if vals[6] else 0,
            "gpu_mem_clock": float(vals[7]) if vals[7] else 0,
        }
    except (ValueError, IndexError):
        return {"gpu_load": 0, "gpu_vram_mb": 0, "gpu_vram_total": 0,
                "gpu_temp": 0, "gpu_power_w": 0, "gpu_fan": 0,
                "gpu_sm_clock": 0, "gpu_mem_clock": 0}


_sys_info_cache = None


def _sys_info():
    global _sys_info_cache
    if _sys_info_cache:
        return _sys_info_cache
    info = {
        "hostname": socket.gethostname(),
        "kernel": platform.release(),
        "cpu_model": platform.processor() or "x86_64",
        "cpu_count": os.cpu_count() or 0,
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
    }
    for label, path in [("disk_root_gb", "/"), ("disk_share_gb", "/mnt/share")]:
        try:
            info[label] = round(psutil.disk_usage(path).total / (1024**3), 1)
        except Exception:
            info[label] = 0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,pcie.link.gen.current,pcie.link.width.current",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        parts = [p.strip() for p in out.stdout.strip().split(", ")]
        info["gpu_name"] = parts[0] if len(parts) > 0 else "NVIDIA GPU"
        info["driver_ver"] = parts[1] if len(parts) > 1 else "?"
        info["pcie_gen"] = parts[2] if len(parts) > 2 else "?"
        info["pcie_width"] = parts[3] if len(parts) > 3 else "?"
    except Exception:
        info["gpu_name"] = "NVIDIA GPU"
        info["driver_ver"] = "?"
        info["pcie_gen"] = "?"
        info["pcie_width"] = "?"
    _sys_info_cache = info
    return info


def _cpu_metrics():
    cpu = psutil.cpu_percent(interval=0.1)
    temps = psutil.sensors_temperatures()
    max_temp = 0
    for name, entries in temps.items():
        for e in entries:
            if e.current > max_temp:
                max_temp = e.current
    load = os.getloadavg()
    return {
        "cpu_percent": cpu, "cpu_temp_max": max_temp,
        "load1": load[0], "load5": load[1], "load15": load[2],
    }


def _mem_metrics():
    mem = psutil.virtual_memory()
    return {
        "mem_percent": mem.percent,
        "mem_avail_gb": mem.available / (1024**3),
    }


def _disk_metrics():
    result = {}
    for label, path in [("disk_root", "/"), ("disk_share", "/mnt/share")]:
        try:
            usage = psutil.disk_usage(path)
            result[label] = usage.percent
        except Exception:
            result[label] = 0
    return result


def collect_metrics():
    now = datetime.now(timezone.utc).isoformat()
    gpu = _gpu_metrics()
    cpu = _cpu_metrics()
    mem = _mem_metrics()
    disk = _disk_metrics()
    net_rx, net_tx = _net_gb()
    net_rx_mbps, net_tx_mbps = _net_speed()
    disk_read_mbps, disk_write_mbps = _disk_io_speed()

    return {
        "timestamp": now,
        "cpu_percent": cpu["cpu_percent"],
        "cpu_temp_max": cpu["cpu_temp_max"],
        "mem_percent": mem["mem_percent"],
        "mem_avail_gb": mem["mem_avail_gb"],
        "gpu_load": gpu["gpu_load"],
        "gpu_vram_mb": gpu["gpu_vram_mb"],
        "gpu_temp": gpu["gpu_temp"],
        "gpu_power_w": gpu["gpu_power_w"],
        "gpu_fan": gpu["gpu_fan"],
        "gpu_sm_clock": gpu["gpu_sm_clock"],
        "gpu_mem_clock": gpu["gpu_mem_clock"],
        "disk_root": disk["disk_root"],
        "disk_share": disk["disk_share"],
        "load1": cpu["load1"],
        "load5": cpu["load5"],
        "load15": cpu["load15"],
        "net_rx_gb": net_rx,
        "net_tx_gb": net_tx,
        "net_rx_mbps": net_rx_mbps,
        "net_tx_mbps": net_tx_mbps,
        "disk_read_mbps": disk_read_mbps,
        "disk_write_mbps": disk_write_mbps,
    }


def collect_live():
    data = collect_metrics()
    data["system_info"] = _sys_info()
    data["uptime_seconds"] = int(time.time() - psutil.boot_time())
    return data