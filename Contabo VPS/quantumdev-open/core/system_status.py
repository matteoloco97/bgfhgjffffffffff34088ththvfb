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
        Dictionary with CPU metrics or error information.
    """
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil_not_available"}
    
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        
        # Per-core usage (optional, can be expensive)
        per_core = None
        try:
            per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        except Exception:
            pass
        
        # Load average (Unix-like systems only)
        load_avg = None
        try:
            if hasattr(os, 'getloadavg'):
                load_avg = os.getloadavg()  # 1, 5, 15 min averages
        except Exception:
            pass
        
        result: Dict[str, Any] = {
            "percent": round(cpu_percent, 2),
            "count_logical": cpu_count,
            "count_physical": cpu_count_physical,
        }
        
        if per_core:
            result["per_core"] = [round(p, 2) for p in per_core]
        
        if load_avg:
            result["load_average"] = {
                "1min": round(load_avg[0], 2),
                "5min": round(load_avg[1], 2),
                "15min": round(load_avg[2], 2),
            }
        
        return result
    except Exception as e:
        log.error(f"Error reading CPU metrics: {e}")
        return {"error": f"cpu_read_failed: {str(e)}"}


def get_memory_metrics() -> Dict[str, Any]:
    """
    Get RAM and swap memory metrics.
    
    Returns:
        Dictionary with memory metrics or error information.
    """
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil_not_available"}
    
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "ram": {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent": round(mem.percent, 2),
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "free_gb": round(swap.free / (1024**3), 2),
                "percent": round(swap.percent, 2),
            },
        }
    except Exception as e:
        log.error(f"Error reading memory metrics: {e}")
        return {"error": f"memory_read_failed: {str(e)}"}


def get_disk_metrics() -> Dict[str, Any]:
    """
    Get disk usage for main partition.
    
    Returns:
        Dictionary with disk metrics or error information.
    """
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil_not_available"}
    
    try:
        # Get disk usage for root partition
        disk = psutil.disk_usage('/')
        
        return {
            "path": "/",
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": round(disk.percent, 2),
        }
    except Exception as e:
        log.error(f"Error reading disk metrics: {e}")
        return {"error": f"disk_read_failed: {str(e)}"}


def get_uptime_metrics() -> Dict[str, Any]:
    """
    Get system uptime.
    
    Returns:
        Dictionary with uptime metrics or error information.
    """
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil_not_available"}
    
    try:
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        # Calculate human-readable components
        days = int(uptime_seconds // 86400)
        hours = int((uptime_seconds % 86400) // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        
        boot_timestamp = datetime.fromtimestamp(boot_time, tz=timezone.utc)
        
        return {
            "seconds": round(uptime_seconds, 2),
            "boot_time_iso": boot_timestamp.isoformat(),
            "human_readable": f"{days}d {hours}h {minutes}m",
        }
    except Exception as e:
        log.error(f"Error reading uptime metrics: {e}")
        return {"error": f"uptime_read_failed: {str(e)}"}


def get_gpu_metrics() -> Dict[str, Any]:
    """
    Get GPU metrics using pynvml (NVIDIA GPUs).
    
    Returns:
        Dictionary with GPU metrics or error/unavailable information.
    """
    if not PYNVML_AVAILABLE:
        return {"available": False, "reason": "pynvml_not_installed"}
    
    try:
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        
        if device_count == 0:
            pynvml.nvmlShutdown()
            return {"available": False, "reason": "no_gpu_detected"}
        
        gpus = []
        for i in range(device_count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                name = pynvml.nvmlDeviceGetName(handle)
                
                # Memory info
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_vram_gb = round(mem_info.total / (1024**3), 2)
                used_vram_gb = round(mem_info.used / (1024**3), 2)
                free_vram_gb = round(mem_info.free / (1024**3), 2)
                vram_percent = round((mem_info.used / mem_info.total) * 100, 2)
                
                # Utilization
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_util = util.gpu
                mem_util = util.memory
                
                # Temperature
                try:
                    temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                except Exception:
                    temp = None
                
                gpu_info: Dict[str, Any] = {
                    "index": i,
                    "name": name if isinstance(name, str) else name.decode('utf-8'),
                    "vram": {
                        "total_gb": total_vram_gb,
                        "used_gb": used_vram_gb,
                        "free_gb": free_vram_gb,
                        "percent": vram_percent,
                    },
                    "utilization": {
                        "gpu_percent": gpu_util,
                        "memory_percent": mem_util,
                    },
                }
                
                if temp is not None:
                    gpu_info["temperature_c"] = temp
                
                gpus.append(gpu_info)
                
            except Exception as e:
                log.warning(f"Error reading GPU {i} metrics: {e}")
                gpus.append({
                    "index": i,
                    "error": f"gpu_{i}_read_failed: {str(e)}",
                })
        
        pynvml.nvmlShutdown()
        
        return {
            "available": True,
            "count": device_count,
            "gpus": gpus,
        }
        
    except Exception as e:
        log.error(f"Error initializing GPU monitoring: {e}")
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass
        return {"available": False, "reason": f"nvml_init_failed: {str(e)}"}


def get_system_status() -> Dict[str, Any]:
    """
    Get comprehensive system status including CPU, RAM, disk, GPU, and uptime.
    
    This function never raises exceptions - all errors are captured and returned
    in the result dictionary.
    
    Returns:
        Dictionary with:
            - ok: bool (true if basic CPU+RAM metrics were read successfully)
            - timestamp: ISO timestamp when metrics were collected
            - metrics: dict with cpu, ram, disk, gpu, uptime sub-sections
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    cpu = get_cpu_metrics()
    memory = get_memory_metrics()
    disk = get_disk_metrics()
    uptime = get_uptime_metrics()
    gpu = get_gpu_metrics()
    
    # Consider the system check successful if we can read basic CPU and RAM metrics
    ok = (
        "error" not in cpu
        and "error" not in memory
        and PSUTIL_AVAILABLE
    )
    
    return {
        "ok": ok,
        "timestamp": timestamp,
        "metrics": {
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "uptime": uptime,
            "gpu": gpu,
        },
    }
