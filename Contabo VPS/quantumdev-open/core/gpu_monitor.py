#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/gpu_monitor.py — Remote GPU Monitoring System for A6000 48GB

Monitors GPU metrics via SSH connection to remote GPU node (Vast.ai).
Provides real-time VRAM, utilization, temperature monitoring with caching.
"""

from __future__ import annotations

import os
import re
import time
import logging
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from collections import deque

log = logging.getLogger(__name__)

# Try to import paramiko for SSH connections
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    log.warning("paramiko not available - remote GPU monitoring disabled")


# ======================== Configuration ========================

GPU_SSH_HOST = os.getenv("GPU_SSH_HOST", "localhost")
GPU_SSH_PORT = int(os.getenv("GPU_SSH_PORT", "22"))
GPU_SSH_USER = os.getenv("GPU_SSH_USER", "root")
GPU_SSH_KEY_PATH = os.getenv("GPU_SSH_KEY_PATH", "")
GPU_SSH_PASSWORD = os.getenv("GPU_SSH_PASSWORD", "")
GPU_METRICS_CACHE_TTL = int(os.getenv("GPU_METRICS_CACHE_TTL", "10"))
GPU_BACKGROUND_UPDATE_INTERVAL = int(os.getenv("GPU_BACKGROUND_UPDATE_INTERVAL", "30"))
GPU_SSH_TIMEOUT = int(os.getenv("GPU_SSH_TIMEOUT", "10"))

# Alert thresholds
GPU_ALERT_VRAM_WARNING = float(os.getenv("GPU_ALERT_VRAM_WARNING", "90"))
GPU_ALERT_VRAM_CRITICAL = float(os.getenv("GPU_ALERT_VRAM_CRITICAL", "95"))
GPU_ALERT_TEMP_WARNING = float(os.getenv("GPU_ALERT_TEMP_WARNING", "80"))
GPU_ALERT_TEMP_CRITICAL = float(os.getenv("GPU_ALERT_TEMP_CRITICAL", "85"))

# History tracking
GPU_HISTORY_MAX_ENTRIES = int(os.getenv("GPU_HISTORY_MAX_ENTRIES", "1000"))


# ======================== GPU Monitor Class ========================

class GPUMonitor:
    """
    Remote GPU monitoring via SSH connection.
    
    Features:
    - Connect to GPU node via SSH (Vast.ai)
    - Execute nvidia-smi remotely and parse output
    - Cache metrics for configurable TTL (default 10s)
    - Background task updates cache every 30s
    - Fallback to cached data on connection errors
    - Track metrics history for time series
    """
    
    def __init__(
        self,
        ssh_host: Optional[str] = None,
        ssh_port: Optional[int] = None,
        ssh_user: Optional[str] = None,
        ssh_key_path: Optional[str] = None,
        ssh_password: Optional[str] = None,
        cache_ttl: Optional[int] = None,
    ):
        """
        Initialize GPU monitor.
        
        Args:
            ssh_host: SSH hostname or IP
            ssh_port: SSH port (default 22)
            ssh_user: SSH username
            ssh_key_path: Path to SSH private key (optional)
            ssh_password: SSH password (optional, use key auth preferred)
            cache_ttl: Cache TTL in seconds (default 10)
        """
        self.ssh_host = ssh_host or GPU_SSH_HOST
        self.ssh_port = ssh_port or GPU_SSH_PORT
        self.ssh_user = ssh_user or GPU_SSH_USER
        self.ssh_key_path = ssh_key_path or GPU_SSH_KEY_PATH
        self.ssh_password = ssh_password or GPU_SSH_PASSWORD
        self.cache_ttl = cache_ttl or GPU_METRICS_CACHE_TTL
        
        # Cache state
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_timestamp: float = 0.0
        self._cache_lock = threading.Lock()
        
        # History tracking (circular buffer)
        self._history: deque = deque(maxlen=GPU_HISTORY_MAX_ENTRIES)
        self._history_lock = threading.Lock()
        
        # Background update thread
        self._background_thread: Optional[threading.Thread] = None
        self._stop_background = threading.Event()
        
        # Connection state
        self._ssh_client: Optional[Any] = None
        self._last_connection_error: Optional[str] = None
        
        if not PARAMIKO_AVAILABLE:
            log.error("paramiko not available - GPU monitoring will not work")
    
    def start_background_updates(self) -> None:
        """Start background thread for periodic cache updates."""
        if self._background_thread is not None and self._background_thread.is_alive():
            log.warning("Background update thread already running")
            return
        
        self._stop_background.clear()
        self._background_thread = threading.Thread(
            target=self._background_update_loop,
            daemon=True,
            name="gpu-monitor-background",
        )
        self._background_thread.start()
        log.info("GPU monitor background updates started")
    
    def stop_background_updates(self) -> None:
        """Stop background update thread."""
        if self._background_thread is None or not self._background_thread.is_alive():
            return
        
        self._stop_background.set()
        if self._background_thread:
            self._background_thread.join(timeout=5.0)
        log.info("GPU monitor background updates stopped")
    
    def _background_update_loop(self) -> None:
        """Background loop that updates cache periodically."""
        while not self._stop_background.is_set():
            try:
                # Update cache
                self._update_cache_internal()
            except Exception as e:
                log.error(f"Error in background GPU metrics update: {e}")
            
            # Wait for next update interval
            self._stop_background.wait(timeout=GPU_BACKGROUND_UPDATE_INTERVAL)
    
    def _connect_ssh(self) -> bool:
        """
        Establish SSH connection to GPU node.
        
        Returns:
            True if connection successful, False otherwise
        """
        if not PARAMIKO_AVAILABLE:
            self._last_connection_error = "paramiko_not_available"
            return False
        
        try:
            # Close existing connection if any
            if self._ssh_client is not None:
                try:
                    self._ssh_client.close()
                except Exception:
                    pass
                self._ssh_client = None
            
            # Create new SSH client
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Prepare connection kwargs
            connect_kwargs: Dict[str, Any] = {
                "hostname": self.ssh_host,
                "port": self.ssh_port,
                "username": self.ssh_user,
                "timeout": GPU_SSH_TIMEOUT,
            }
            
            # Use key or password authentication
            if self.ssh_key_path and os.path.exists(self.ssh_key_path):
                connect_kwargs["key_filename"] = self.ssh_key_path
            elif self.ssh_password:
                connect_kwargs["password"] = self.ssh_password
            else:
                self._last_connection_error = "no_auth_method_configured"
                return False
            
            # Connect
            client.connect(**connect_kwargs)
            self._ssh_client = client
            self._last_connection_error = None
            
            log.debug(f"SSH connection established to {self.ssh_host}:{self.ssh_port}")
            return True
            
        except Exception as e:
            self._last_connection_error = str(e)
            log.error(f"Failed to connect to GPU node via SSH: {e}")
            return False
    
    def _execute_ssh_command(self, command: str) -> Tuple[bool, str, str]:
        """
        Execute command on remote GPU node via SSH.
        
        Args:
            command: Command to execute
        
        Returns:
            Tuple of (success, stdout, stderr)
        """
        if not PARAMIKO_AVAILABLE:
            return (False, "", "paramiko_not_available")
        
        if self._ssh_client is None:
            if not self._connect_ssh():
                return (False, "", self._last_connection_error or "connection_failed")
        
        try:
            stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=GPU_SSH_TIMEOUT)
            stdout_str = stdout.read().decode('utf-8', errors='ignore')
            stderr_str = stderr.read().decode('utf-8', errors='ignore')
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status == 0:
                return (True, stdout_str, stderr_str)
            else:
                return (False, stdout_str, stderr_str)
                
        except Exception as e:
            log.error(f"Error executing SSH command: {e}")
            # Connection might be broken, reset it
            try:
                if self._ssh_client:
                    self._ssh_client.close()
            except Exception:
                pass
            self._ssh_client = None
            return (False, "", str(e))
    
    def _parse_nvidia_smi_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse nvidia-smi output to extract GPU metrics.
        
        Args:
            output: Raw nvidia-smi output
        
        Returns:
            List of GPU info dictionaries
        """
        gpus = []
        
        try:
            # Split output into lines
            lines = output.strip().split('\n')
            
            # Look for GPU info lines
            # nvidia-smi output format (query mode):
            # index, name, memory.used, memory.total, utilization.gpu, temperature.gpu, power.draw
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Skip header lines
                if 'index' in line.lower() or '=' in line or '-' in line[:3]:
                    continue
                
                # Parse comma-separated values
                parts = [p.strip() for p in line.split(',')]
                
                if len(parts) < 6:
                    continue
                
                try:
                    # Extract values
                    index = int(parts[0]) if parts[0].isdigit() else 0
                    name = parts[1]
                    
                    # Parse memory (format: "12345 MiB")
                    memory_used_str = parts[2].replace('MiB', '').replace('MB', '').strip()
                    memory_total_str = parts[3].replace('MiB', '').replace('MB', '').strip()
                    memory_used = int(float(memory_used_str)) * 1024 * 1024 if memory_used_str.replace('.', '', 1).isdigit() else 0
                    memory_total = int(float(memory_total_str)) * 1024 * 1024 if memory_total_str.replace('.', '', 1).isdigit() else 0
                    
                    # Parse utilization (format: "75 %")
                    util_str = parts[4].replace('%', '').strip()
                    utilization = float(util_str) if util_str.replace('.', '', 1).isdigit() else 0.0
                    
                    # Parse temperature (format: "65 C" or just "65")
                    temp_str = parts[5].replace('C', '').strip()
                    temperature = float(temp_str) if temp_str.replace('.', '', 1).isdigit() else 0.0
                    
                    # Parse power draw if available (format: "250 W")
                    power_draw = None
                    if len(parts) > 6:
                        power_str = parts[6].replace('W', '').strip()
                        if power_str.replace('.', '', 1).isdigit():
                            power_draw = float(power_str)
                    
                    # Calculate VRAM percentage
                    memory_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0.0
                    
                    gpu_info: Dict[str, Any] = {
                        "index": index,
                        "name": name,
                        "memory_total": memory_total,
                        "memory_used": memory_used,
                        "memory_percent": round(memory_percent, 2),
                        "utilization_percent": round(utilization, 2),
                        "temperature": round(temperature, 2),
                        "power_draw": round(power_draw, 2) if power_draw is not None else None,
                    }
                    
                    gpus.append(gpu_info)
                    
                except (ValueError, IndexError) as e:
                    log.warning(f"Error parsing GPU line '{line}': {e}")
                    continue
            
        except Exception as e:
            log.error(f"Error parsing nvidia-smi output: {e}")
        
        return gpus
    
    def _fetch_gpu_metrics_remote(self) -> Dict[str, Any]:
        """
        Fetch GPU metrics from remote node via SSH.
        
        Returns:
            Dictionary with GPU metrics or error information
        """
        # Execute nvidia-smi with query format
        command = (
            "nvidia-smi --query-gpu=index,name,memory.used,memory.total,"
            "utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits"
        )
        
        success, stdout, stderr = self._execute_ssh_command(command)
        
        if not success:
            error_msg = stderr or "command_failed"
            return {
                "gpus": [],
                "status": "error",
                "error": error_msg,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        # Parse output
        gpus = self._parse_nvidia_smi_output(stdout)
        
        if not gpus:
            return {
                "gpus": [],
                "status": "no_gpu_detected",
                "error": "no_gpu_found_in_output",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        return {
            "gpus": gpus,
            "status": "ok",
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def _update_cache_internal(self) -> None:
        """Update cache with fresh GPU metrics (internal use)."""
        try:
            metrics = self._fetch_gpu_metrics_remote()
            
            with self._cache_lock:
                self._cache = metrics
                self._cache_timestamp = time.time()
            
            # Add to history
            with self._history_lock:
                self._history.append({
                    "timestamp": metrics["timestamp"],
                    "metrics": metrics,
                })
            
        except Exception as e:
            log.error(f"Error updating GPU metrics cache: {e}")
    
    def get_metrics(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get current GPU metrics.
        
        Args:
            force_refresh: If True, bypass cache and fetch fresh metrics
        
        Returns:
            Dictionary with GPU metrics including:
            - gpus: List of GPU info dictionaries
            - status: 'ok', 'error', 'cached', or 'unknown'
            - error: Error message if applicable
            - timestamp: ISO 8601 timestamp
            - cache_age_seconds: Age of cached data (if from cache)
        """
        # Check cache first
        with self._cache_lock:
            cache_age = time.time() - self._cache_timestamp
            
            # Use cache if valid and not forcing refresh
            if (
                not force_refresh
                and self._cache is not None
                and cache_age < self.cache_ttl
            ):
                result = self._cache.copy()
                result["status"] = "cached"
                result["cache_age_seconds"] = round(cache_age, 2)
                return result
        
        # Fetch fresh metrics
        try:
            metrics = self._fetch_gpu_metrics_remote()
            
            # Update cache
            with self._cache_lock:
                self._cache = metrics
                self._cache_timestamp = time.time()
            
            # Add to history
            with self._history_lock:
                self._history.append({
                    "timestamp": metrics["timestamp"],
                    "metrics": metrics,
                })
            
            metrics["cache_age_seconds"] = 0.0
            return metrics
            
        except Exception as e:
            log.error(f"Error fetching GPU metrics: {e}")
            
            # Return cached data if available (even if expired)
            with self._cache_lock:
                if self._cache is not None:
                    result = self._cache.copy()
                    result["status"] = "error_cached_fallback"
                    result["cache_age_seconds"] = round(time.time() - self._cache_timestamp, 2)
                    result["fetch_error"] = str(e)
                    return result
            
            # No cache available
            return {
                "gpus": [],
                "status": "unknown",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cache_age_seconds": None,
            }
    
    def get_metrics_history(self, minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Get historical GPU metrics for specified time window.
        
        Args:
            minutes: Number of minutes of history to retrieve
        
        Returns:
            List of historical metric snapshots
        """
        cutoff_time = datetime.now(timezone.utc).timestamp() - (minutes * 60)
        
        with self._history_lock:
            history = []
            for entry in self._history:
                try:
                    # Parse timestamp
                    ts = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
                    if ts.timestamp() >= cutoff_time:
                        history.append(entry)
                except Exception as e:
                    log.warning(f"Error parsing history entry timestamp: {e}")
                    continue
            
            return history
    
    def is_healthy(self) -> bool:
        """
        Check if GPU is healthy based on current metrics.
        
        Health criteria:
        - VRAM usage < 90%
        - Temperature < 85°C
        - Status is 'ok' or 'cached'
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            metrics = self.get_metrics()
            
            # Check status
            if metrics["status"] not in ["ok", "cached"]:
                return False
            
            # Check each GPU
            gpus = metrics.get("gpus", [])
            if not gpus:
                return False
            
            for gpu in gpus:
                # Check VRAM
                vram_percent = gpu.get("memory_percent", 0)
                if vram_percent >= GPU_ALERT_VRAM_WARNING:
                    return False
                
                # Check temperature
                temp = gpu.get("temperature", 0)
                if temp >= GPU_ALERT_TEMP_CRITICAL:
                    return False
            
            return True
            
        except Exception as e:
            log.error(f"Error checking GPU health: {e}")
            return False
    
    def should_alert(self) -> Tuple[bool, List[str]]:
        """
        Check if any alert conditions are met.
        
        Returns:
            Tuple of (should_alert, list_of_alert_messages)
        """
        alerts = []
        
        try:
            metrics = self.get_metrics()
            
            # Check if GPU is offline
            if metrics["status"] not in ["ok", "cached"]:
                alerts.append(f"GPU offline or unreachable: {metrics.get('error', 'unknown')}")
            
            # Check each GPU
            gpus = metrics.get("gpus", [])
            
            if not gpus and metrics["status"] in ["ok", "cached"]:
                alerts.append("No GPU detected")
            
            for gpu in gpus:
                gpu_id = gpu.get("index", 0)
                gpu_name = gpu.get("name", "Unknown")
                
                # Check VRAM
                vram_percent = gpu.get("memory_percent", 0)
                if vram_percent >= GPU_ALERT_VRAM_CRITICAL:
                    alerts.append(
                        f"GPU {gpu_id} ({gpu_name}): CRITICAL VRAM usage {vram_percent:.1f}% "
                        f"(threshold: {GPU_ALERT_VRAM_CRITICAL}%)"
                    )
                elif vram_percent >= GPU_ALERT_VRAM_WARNING:
                    alerts.append(
                        f"GPU {gpu_id} ({gpu_name}): WARNING VRAM usage {vram_percent:.1f}% "
                        f"(threshold: {GPU_ALERT_VRAM_WARNING}%)"
                    )
                
                # Check temperature
                temp = gpu.get("temperature", 0)
                if temp >= GPU_ALERT_TEMP_CRITICAL:
                    alerts.append(
                        f"GPU {gpu_id} ({gpu_name}): CRITICAL temperature {temp:.1f}°C "
                        f"(threshold: {GPU_ALERT_TEMP_CRITICAL}°C)"
                    )
                elif temp >= GPU_ALERT_TEMP_WARNING:
                    alerts.append(
                        f"GPU {gpu_id} ({gpu_name}): WARNING temperature {temp:.1f}°C "
                        f"(threshold: {GPU_ALERT_TEMP_WARNING}°C)"
                    )
            
        except Exception as e:
            log.error(f"Error checking GPU alerts: {e}")
            alerts.append(f"Error checking GPU status: {str(e)}")
        
        return (len(alerts) > 0, alerts)
    
    def close(self) -> None:
        """Close SSH connection and cleanup resources."""
        # Stop background updates
        self.stop_background_updates()
        
        # Close SSH connection
        if self._ssh_client is not None:
            try:
                self._ssh_client.close()
            except Exception as e:
                log.warning(f"Error closing SSH connection: {e}")
            self._ssh_client = None
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except Exception:
            pass


# ======================== Singleton Instance ========================

_GPU_MONITOR_INSTANCE: Optional[GPUMonitor] = None
_GPU_MONITOR_LOCK = threading.Lock()


def get_gpu_monitor() -> GPUMonitor:
    """
    Get singleton GPU monitor instance.
    
    Returns:
        GPUMonitor instance
    """
    global _GPU_MONITOR_INSTANCE
    
    with _GPU_MONITOR_LOCK:
        if _GPU_MONITOR_INSTANCE is None:
            _GPU_MONITOR_INSTANCE = GPUMonitor()
            # Start background updates automatically
            _GPU_MONITOR_INSTANCE.start_background_updates()
        
        return _GPU_MONITOR_INSTANCE
