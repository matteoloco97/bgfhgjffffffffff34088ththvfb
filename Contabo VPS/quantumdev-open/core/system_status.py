#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/system_status.py — System Status Monitoring

Provides real-time system metrics (CPU, RAM, disk, GPU, uptime).
All functions are designed to never raise exceptions to the caller.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# psutil for system metrics (required)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# pynvml for GPU metrics (optional)
try:
    import pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False

log = logging.getLogger(__name__)


def get_cpu_metrics() -> Dict[str, Any]:
    """
    Get CPU usage metrics.
    
    Returns:
        Dictionary with CPU metrics including:
        - percent: CPU usage percentage
        - load_average: List [1min, 5min, 15min] (if available)
        - cores_logical: Number of logical cores
        - cores_physical: Number of physical cores
    """
    if not PSUTIL_AVAILABLE:
        return {
            "percent": 0.0,
            "load_average": [0.0, 0.0, 0.0],
            "cores_logical": 0,
            "cores_physical": 0,
            "error": "psutil_not_available"
        }
    
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        
        # Load average (Unix-like systems only)
        load_avg = [0.0, 0.0, 0.0]
        try:
            if hasattr(os, 'getloadavg'):
                raw_load = os.getloadavg()
                load_avg = [round(raw_load[0], 2), round(raw_load[1], 2), round(raw_load[2], 2)]
        except Exception:
            # Silently use fallback - this is expected on Windows
            pass
        
        return {
            "percent": round(cpu_percent, 2),
            "load_average": load_avg,
            "cores_logical": cpu_count or 0,
            "cores_physical": cpu_count_physical or 0,
        }
    except Exception as e:
        log.error(f"Error reading CPU metrics: {e}")
        return {
            "percent": 0.0,
            "load_average": [0.0, 0.0, 0.0],
            "cores_logical": 0,
            "cores_physical": 0,
            "error": f"cpu_read_failed: {str(e)}"
        }


def get_memory_metrics() -> Dict[str, Any]:
    """
    Get RAM and swap memory metrics.
    
    Returns:
        Dictionary with memory metrics including:
        - total: Total RAM in bytes
        - used: Used RAM in bytes
        - percent: RAM usage percentage
        - swap_total: Total swap in bytes
        - swap_used: Used swap in bytes
        - swap_percent: Swap usage percentage
    """
    if not PSUTIL_AVAILABLE:
        return {
            "total": 0,
            "used": 0,
            "percent": 0.0,
            "swap_total": 0,
            "swap_used": 0,
            "swap_percent": 0.0,
            "error": "psutil_not_available"
        }
    
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "total": int(mem.total),
            "used": int(mem.used),
            "percent": round(mem.percent, 2),
            "swap_total": int(swap.total),
            "swap_used": int(swap.used),
            "swap_percent": round(swap.percent, 2),
        }
    except Exception as e:
        log.error(f"Error reading memory metrics: {e}")
        return {
            "total": 0,
            "used": 0,
            "percent": 0.0,
            "swap_total": 0,
            "swap_used": 0,
            "swap_percent": 0.0,
            "error": f"memory_read_failed: {str(e)}"
        }


def get_disk_metrics() -> Dict[str, Any]:
    """
    Get disk usage for main partition.
    
    Returns:
        Dictionary with disk metrics including:
        - total: Total disk space in bytes
        - used: Used disk space in bytes
        - percent: Disk usage percentage
    """
    if not PSUTIL_AVAILABLE:
        return {
            "total": 0,
            "used": 0,
            "percent": 0.0,
            "error": "psutil_not_available"
        }
    
    try:
        # Get disk usage for root partition
        disk = psutil.disk_usage('/')
        
        return {
            "total": int(disk.total),
            "used": int(disk.used),
            "percent": round(disk.percent, 2),
        }
    except Exception as e:
        log.error(f"Error reading disk metrics: {e}")
        return {
            "total": 0,
            "used": 0,
            "percent": 0.0,
            "error": f"disk_read_failed: {str(e)}"
        }


def get_uptime_metrics() -> Dict[str, Any]:
    """
    Get system uptime.
    
    Returns:
        Dictionary with uptime metrics including:
        - seconds: Uptime in seconds
    """
    if not PSUTIL_AVAILABLE:
        return {
            "seconds": 0,
            "error": "psutil_not_available"
        }
    
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        return {
            "seconds": int(uptime_seconds),
        }
    except Exception as e:
        log.error(f"Error reading uptime metrics: {e}")
        return {
            "seconds": 0,
            "error": f"uptime_read_failed: {str(e)}"
        }


def get_gpu_metrics() -> Dict[str, Any]:
    """
    Get GPU metrics using pynvml (NVIDIA GPUs).
    
    Returns:
        Dictionary with GPU metrics including:
        - gpus: List of GPU info dictionaries
        - error: Error message if pynvml is not available or failed
        
        Each GPU dict contains:
        - index: GPU index
        - name: GPU name
        - memory_total: Total VRAM in bytes
        - memory_used: Used VRAM in bytes
        - memory_percent: VRAM usage percentage
        - utilization_percent: GPU utilization percentage (or None)
        - temperature: GPU temperature in Celsius (or None)
    """
    if not PYNVML_AVAILABLE:
        return {
            "gpus": [],
            "error": "pynvml_not_installed"
        }
    
    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        if device_count == 0:
            pynvml.nvmlShutdown()
            return {
                "gpus": [],
                "error": "no_gpu_detected"
            }
        
        gpus = []
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                
                # Memory info
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_vram = int(mem_info.total)
                used_vram = int(mem_info.used)
                vram_percent = round((mem_info.used / mem_info.total) * 100, 2) if mem_info.total > 0 else 0.0
                
                # Utilization
                util_percent = None
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    util_percent = float(util.gpu)
                except Exception:
                    pass
                
                # Temperature
                temp = None
                try:
                    temp = float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU))
                except Exception:
                    pass
                
                gpu_info: Dict[str, Any] = {
                    "index": i,
                    "name": name if isinstance(name, str) else name.decode('utf-8'),
                    "memory_total": total_vram,
                    "memory_used": used_vram,
                    "memory_percent": vram_percent,
                    "utilization_percent": util_percent,
                    "temperature": temp,
                }
                
                gpus.append(gpu_info)
                
            except Exception as e:
                log.warning(f"Error reading GPU {i} metrics: {e}")
                gpus.append({
                    "index": i,
                    "name": f"GPU {i}",
                    "memory_total": 0,
                    "memory_used": 0,
                    "memory_percent": 0.0,
                    "utilization_percent": None,
                    "temperature": None,
                    "error": f"gpu_{i}_read_failed: {str(e)}",
                })
        
        pynvml.nvmlShutdown()
        
        return {
            "gpus": gpus,
            "error": None,
        }
        
    except Exception as e:
        log.error(f"Error initializing GPU monitoring: {e}")
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        return {
            "gpus": [],
            "error": f"nvml_init_failed: {str(e)}"
        }


def get_system_status() -> Dict[str, Any]:
    """
    Get comprehensive system status including CPU, RAM, disk, GPU, and uptime.
    
    This function never raises exceptions - all errors are captured and returned
    in the result dictionary.
    
    RETURNS STRUCTURE (JSON-safe):
    {
        "ok": bool,                      # true if psutil/core metrics available
        "psutil_available": bool,
        "pynvml_available": bool,
        "cpu": {
            "percent": float,
            "load_average": [float, float, float],  # 1,5,15 min
            "cores_logical": int,
            "cores_physical": int
        },
        "memory": {
            "total": int,                # bytes
            "used": int,                 # bytes
            "percent": float,
            "swap_total": int,           # bytes
            "swap_used": int,            # bytes
            "swap_percent": float
        },
        "disk": {
            "total": int,                # bytes
            "used": int,                 # bytes
            "percent": float
        },
        "gpu": {
            "gpus": [
                {
                    "index": int,
                    "name": str,
                    "memory_total": int,
                    "memory_used": int,
                    "memory_percent": float,
                    "utilization_percent": float | None,
                    "temperature": float | None
                }
            ],
            "error": str | None
        },
        "uptime": {
            "seconds": int
        }
    }
    
    Returns:
        Dictionary with system status as described above
    """
    # Collect all metrics (they never raise exceptions)
    cpu = get_cpu_metrics()
    memory = get_memory_metrics()
    disk = get_disk_metrics()
    uptime = get_uptime_metrics()
    gpu = get_gpu_metrics()
    
    # Determine overall status
    # ok = True only if we can read basic CPU and RAM metrics AND psutil is available
    ok = (
        PSUTIL_AVAILABLE
        and "error" not in cpu
        and "error" not in memory
    )
    
    return {
        "ok": ok,
        "psutil_available": PSUTIL_AVAILABLE,
        "pynvml_available": PYNVML_AVAILABLE,
        "cpu": cpu,
        "memory": memory,
        "disk": disk,
        "gpu": gpu,
        "uptime": uptime,
    }
