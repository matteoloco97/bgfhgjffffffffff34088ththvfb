#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/gpu_alerts.py — GPU Alerting System

Monitors GPU metrics and sends alerts via Telegram for critical conditions:
- VRAM > 90% for 2 minutes → Warning
- VRAM > 95% for 30 seconds → Critical
- Temperature > 80°C → Warning
- Temperature > 85°C → Critical
- GPU offline > 5 minutes → Critical

Includes rate limiting and auto-resolution of alerts.
"""

from __future__ import annotations

import os
import time
import logging
import threading
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from collections import deque

log = logging.getLogger(__name__)

# Try to import Redis for alert history storage
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    log.warning("redis not available - alert history will not be persisted")

# Try to import Telegram bot for notifications
try:
    from agents.telegram_bot_agent import TelegramBotAgent
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    log.warning("telegram_bot_agent not available - alerts will only be logged")


# ======================== Configuration ========================

GPU_ALERT_CHECK_INTERVAL = int(os.getenv("GPU_ALERT_CHECK_INTERVAL", "60"))  # seconds
GPU_ALERT_VRAM_WARNING = float(os.getenv("GPU_ALERT_VRAM_WARNING", "90"))
GPU_ALERT_VRAM_CRITICAL = float(os.getenv("GPU_ALERT_VRAM_CRITICAL", "95"))
GPU_ALERT_TEMP_WARNING = float(os.getenv("GPU_ALERT_TEMP_WARNING", "80"))
GPU_ALERT_TEMP_CRITICAL = float(os.getenv("GPU_ALERT_TEMP_CRITICAL", "85"))
GPU_ALERT_OFFLINE_CRITICAL_MINUTES = int(os.getenv("GPU_ALERT_OFFLINE_CRITICAL_MINUTES", "5"))
GPU_ALERT_VRAM_WARNING_DURATION = int(os.getenv("GPU_ALERT_VRAM_WARNING_DURATION", "120"))  # 2 minutes
GPU_ALERT_VRAM_CRITICAL_DURATION = int(os.getenv("GPU_ALERT_VRAM_CRITICAL_DURATION", "30"))  # 30 seconds
GPU_ALERT_RATE_LIMIT_SECONDS = int(os.getenv("GPU_ALERT_RATE_LIMIT_SECONDS", "900"))  # 15 minutes
GPU_ALERT_HISTORY_TTL_DAYS = int(os.getenv("GPU_ALERT_HISTORY_TTL_DAYS", "7"))
GPU_ALERT_ENABLED = os.getenv("GPU_ALERT_ENABLED", "1") == "1"

# Telegram configuration
TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

# Redis configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)


# ======================== Alert Types ========================

class AlertLevel:
    """Alert severity levels."""
    WARNING = "warning"
    CRITICAL = "critical"
    INFO = "info"


class AlertCondition:
    """Alert condition definitions."""
    VRAM_WARNING = "vram_warning"
    VRAM_CRITICAL = "vram_critical"
    TEMP_WARNING = "temp_warning"
    TEMP_CRITICAL = "temp_critical"
    GPU_OFFLINE = "gpu_offline"
    GPU_NO_DETECT = "gpu_no_detect"


# ======================== GPU Alert Manager ========================

class GPUAlertManager:
    """
    Manages GPU monitoring alerts with rate limiting and history tracking.
    
    Features:
    - Background task checking GPU metrics every 60 seconds
    - Alert conditions with duration thresholds
    - Rate limiting (max 1 alert per condition per 15 minutes)
    - Auto-resolve notifications when conditions clear
    - Store alert history in Redis with TTL
    - Send Telegram notifications to admin
    """
    
    def __init__(self):
        """Initialize GPU alert manager."""
        # Alert state tracking
        self._active_alerts: Dict[str, Dict[str, Any]] = {}  # condition -> alert info
        self._alert_history: deque = deque(maxlen=1000)
        self._condition_states: Dict[str, Dict[str, Any]] = {}  # condition -> state info
        self._last_alert_times: Dict[str, float] = {}  # condition -> last alert timestamp
        
        # Locks for thread safety
        self._state_lock = threading.Lock()
        self._history_lock = threading.Lock()
        
        # Background thread
        self._background_thread: Optional[threading.Thread] = None
        self._stop_background = threading.Event()
        
        # Redis connection
        self._redis_client: Optional[Any] = None
        if REDIS_AVAILABLE:
            try:
                self._redis_client = redis.Redis(
                    host=REDIS_HOST,
                    port=REDIS_PORT,
                    db=REDIS_DB,
                    password=REDIS_PASSWORD,
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                # Test connection
                self._redis_client.ping()
                log.info("Redis connected for GPU alert history")
            except Exception as e:
                log.warning(f"Failed to connect to Redis for GPU alerts: {e}")
                self._redis_client = None
        
        # Telegram bot
        self._telegram_bot: Optional[TelegramBotAgent] = None
        if TELEGRAM_AVAILABLE and TELEGRAM_ADMIN_CHAT_ID:
            try:
                self._telegram_bot = TelegramBotAgent()
                log.info("Telegram bot initialized for GPU alerts")
            except Exception as e:
                log.warning(f"Failed to initialize Telegram bot for GPU alerts: {e}")
                self._telegram_bot = None
    
    def start_monitoring(self) -> None:
        """Start background monitoring thread."""
        if not GPU_ALERT_ENABLED:
            log.info("GPU alerting is disabled via GPU_ALERT_ENABLED")
            return
        
        if self._background_thread is not None and self._background_thread.is_alive():
            log.warning("GPU alert monitoring thread already running")
            return
        
        self._stop_background.clear()
        self._background_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="gpu-alert-monitor",
        )
        self._background_thread.start()
        log.info(f"GPU alert monitoring started (check interval: {GPU_ALERT_CHECK_INTERVAL}s)")
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring thread."""
        if self._background_thread is None or not self._background_thread.is_alive():
            return
        
        self._stop_background.set()
        if self._background_thread:
            self._background_thread.join(timeout=5.0)
        log.info("GPU alert monitoring stopped")
    
    def _monitoring_loop(self) -> None:
        """Background loop that checks GPU metrics and triggers alerts."""
        while not self._stop_background.is_set():
            try:
                self._check_and_alert()
            except Exception as e:
                log.error(f"Error in GPU alert monitoring loop: {e}")
            
            # Wait for next check interval
            self._stop_background.wait(timeout=GPU_ALERT_CHECK_INTERVAL)
    
    def _check_and_alert(self) -> None:
        """Check GPU metrics and trigger alerts if needed."""
        try:
            from core.gpu_monitor import get_gpu_monitor
            
            monitor = get_gpu_monitor()
            metrics = monitor.get_metrics()
            
            current_time = time.time()
            status = metrics.get("status", "unknown")
            gpus = metrics.get("gpus", [])
            
            # Track conditions to check for auto-resolution
            checked_conditions: Set[str] = set()
            
            # Check if GPU is offline
            if status not in ("ok", "cached"):
                self._check_condition(
                    AlertCondition.GPU_OFFLINE,
                    AlertLevel.CRITICAL,
                    f"GPU monitoring offline: {metrics.get('error', 'unknown')}",
                    duration_threshold=GPU_ALERT_OFFLINE_CRITICAL_MINUTES * 60,
                    is_active=True,
                    current_time=current_time,
                )
                checked_conditions.add(AlertCondition.GPU_OFFLINE)
            else:
                # GPU is online - resolve offline alert if active
                self._check_condition(
                    AlertCondition.GPU_OFFLINE,
                    AlertLevel.CRITICAL,
                    "GPU monitoring offline",
                    duration_threshold=0,
                    is_active=False,
                    current_time=current_time,
                )
                checked_conditions.add(AlertCondition.GPU_OFFLINE)
            
            # Check if no GPUs detected
            if status in ("ok", "cached") and len(gpus) == 0:
                self._check_condition(
                    AlertCondition.GPU_NO_DETECT,
                    AlertLevel.CRITICAL,
                    "No GPUs detected",
                    duration_threshold=0,
                    is_active=True,
                    current_time=current_time,
                )
                checked_conditions.add(AlertCondition.GPU_NO_DETECT)
            else:
                # GPUs detected - resolve alert if active
                self._check_condition(
                    AlertCondition.GPU_NO_DETECT,
                    AlertLevel.CRITICAL,
                    "No GPUs detected",
                    duration_threshold=0,
                    is_active=False,
                    current_time=current_time,
                )
                checked_conditions.add(AlertCondition.GPU_NO_DETECT)
            
            # Check each GPU
            for gpu in gpus:
                gpu_id = gpu.get("index", 0)
                gpu_name = gpu.get("name", "Unknown")
                vram_percent = gpu.get("memory_percent", 0)
                temp = gpu.get("temperature", 0)
                
                # VRAM Critical (>95% for 30s)
                vram_crit_condition = f"{AlertCondition.VRAM_CRITICAL}_gpu{gpu_id}"
                self._check_condition(
                    vram_crit_condition,
                    AlertLevel.CRITICAL,
                    f"GPU {gpu_id} ({gpu_name}): CRITICAL VRAM usage {vram_percent:.1f}% (threshold: {GPU_ALERT_VRAM_CRITICAL}%)",
                    duration_threshold=GPU_ALERT_VRAM_CRITICAL_DURATION,
                    is_active=(vram_percent >= GPU_ALERT_VRAM_CRITICAL),
                    current_time=current_time,
                )
                checked_conditions.add(vram_crit_condition)
                
                # VRAM Warning (>90% for 2 minutes)
                vram_warn_condition = f"{AlertCondition.VRAM_WARNING}_gpu{gpu_id}"
                self._check_condition(
                    vram_warn_condition,
                    AlertLevel.WARNING,
                    f"GPU {gpu_id} ({gpu_name}): WARNING VRAM usage {vram_percent:.1f}% (threshold: {GPU_ALERT_VRAM_WARNING}%)",
                    duration_threshold=GPU_ALERT_VRAM_WARNING_DURATION,
                    is_active=(vram_percent >= GPU_ALERT_VRAM_WARNING and vram_percent < GPU_ALERT_VRAM_CRITICAL),
                    current_time=current_time,
                )
                checked_conditions.add(vram_warn_condition)
                
                # Temperature Critical (>85°C)
                temp_crit_condition = f"{AlertCondition.TEMP_CRITICAL}_gpu{gpu_id}"
                self._check_condition(
                    temp_crit_condition,
                    AlertLevel.CRITICAL,
                    f"GPU {gpu_id} ({gpu_name}): CRITICAL temperature {temp:.1f}°C (threshold: {GPU_ALERT_TEMP_CRITICAL}°C)",
                    duration_threshold=0,  # immediate
                    is_active=(temp >= GPU_ALERT_TEMP_CRITICAL),
                    current_time=current_time,
                )
                checked_conditions.add(temp_crit_condition)
                
                # Temperature Warning (>80°C)
                temp_warn_condition = f"{AlertCondition.TEMP_WARNING}_gpu{gpu_id}"
                self._check_condition(
                    temp_warn_condition,
                    AlertLevel.WARNING,
                    f"GPU {gpu_id} ({gpu_name}): WARNING temperature {temp:.1f}°C (threshold: {GPU_ALERT_TEMP_WARNING}°C)",
                    duration_threshold=0,  # immediate
                    is_active=(temp >= GPU_ALERT_TEMP_WARNING and temp < GPU_ALERT_TEMP_CRITICAL),
                    current_time=current_time,
                )
                checked_conditions.add(temp_warn_condition)
            
            # Auto-resolve any alerts that are no longer active
            with self._state_lock:
                # Get all tracked conditions
                all_conditions = set(self._condition_states.keys())
                
                # Resolve conditions that were not checked this iteration
                for condition in all_conditions - checked_conditions:
                    if condition in self._active_alerts:
                        self._resolve_alert(condition, current_time)
        
        except Exception as e:
            log.error(f"Error checking GPU alerts: {e}")
    
    def _check_condition(
        self,
        condition: str,
        level: str,
        message: str,
        duration_threshold: int,
        is_active: bool,
        current_time: float,
    ) -> None:
        """
        Check a specific alert condition and trigger/resolve alerts as needed.
        
        Args:
            condition: Unique condition identifier
            level: Alert level (warning, critical, info)
            message: Alert message
            duration_threshold: How long condition must be active before alerting (seconds)
            is_active: Whether the condition is currently active
            current_time: Current timestamp
        """
        with self._state_lock:
            # Initialize condition state if not exists
            if condition not in self._condition_states:
                self._condition_states[condition] = {
                    "first_seen": None,
                    "last_seen": None,
                    "level": level,
                    "message": message,
                }
            
            state = self._condition_states[condition]
            
            if is_active:
                # Condition is active
                if state["first_seen"] is None:
                    # First time seeing this condition
                    state["first_seen"] = current_time
                    state["last_seen"] = current_time
                else:
                    # Update last seen time
                    state["last_seen"] = current_time
                
                # Check if duration threshold is met
                duration = current_time - state["first_seen"]
                
                if duration >= duration_threshold:
                    # Duration threshold met - trigger alert if not already active
                    if condition not in self._active_alerts:
                        self._trigger_alert(condition, level, message, current_time)
            else:
                # Condition is no longer active
                if state["first_seen"] is not None:
                    # Reset condition state
                    state["first_seen"] = None
                    state["last_seen"] = None
                
                # Resolve alert if active
                if condition in self._active_alerts:
                    self._resolve_alert(condition, current_time)
    
    def _trigger_alert(
        self,
        condition: str,
        level: str,
        message: str,
        current_time: float,
    ) -> None:
        """
        Trigger an alert for a condition.
        
        Args:
            condition: Condition identifier
            level: Alert level
            message: Alert message
            current_time: Current timestamp
        """
        # Check rate limiting
        last_alert_time = self._last_alert_times.get(condition, 0)
        time_since_last = current_time - last_alert_time
        
        if time_since_last < GPU_ALERT_RATE_LIMIT_SECONDS:
            # Rate limited - skip this alert
            log.debug(
                f"Alert for condition '{condition}' rate limited "
                f"(last alert {time_since_last:.0f}s ago, limit {GPU_ALERT_RATE_LIMIT_SECONDS}s)"
            )
            return
        
        # Create alert
        alert = {
            "condition": condition,
            "level": level,
            "message": message,
            "triggered_at": current_time,
            "triggered_at_iso": datetime.fromtimestamp(current_time, tz=timezone.utc).isoformat(),
            "resolved": False,
            "resolved_at": None,
        }
        
        # Mark as active
        self._active_alerts[condition] = alert
        self._last_alert_times[condition] = current_time
        
        # Add to history
        with self._history_lock:
            self._history.append(alert.copy())
        
        # Store in Redis
        if self._redis_client:
            try:
                alert_key = f"gpu_alert:{condition}:{int(current_time)}"
                self._redis_client.setex(
                    alert_key,
                    GPU_ALERT_HISTORY_TTL_DAYS * 86400,
                    str(alert),
                )
            except Exception as e:
                log.warning(f"Failed to store alert in Redis: {e}")
        
        # Send notification
        self._send_notification(level, message, is_resolution=False)
        
        log.warning(f"GPU Alert triggered: [{level.upper()}] {message}")
    
    def _resolve_alert(self, condition: str, current_time: float) -> None:
        """
        Resolve an active alert.
        
        Args:
            condition: Condition identifier
            current_time: Current timestamp
        """
        if condition not in self._active_alerts:
            return
        
        alert = self._active_alerts[condition]
        
        # Update alert
        alert["resolved"] = True
        alert["resolved_at"] = current_time
        alert["resolved_at_iso"] = datetime.fromtimestamp(current_time, tz=timezone.utc).isoformat()
        
        # Remove from active
        del self._active_alerts[condition]
        
        # Add resolved alert to history
        with self._history_lock:
            self._history.append(alert.copy())
        
        # Store in Redis
        if self._redis_client:
            try:
                alert_key = f"gpu_alert_resolved:{condition}:{int(current_time)}"
                self._redis_client.setex(
                    alert_key,
                    GPU_ALERT_HISTORY_TTL_DAYS * 86400,
                    str(alert),
                )
            except Exception as e:
                log.warning(f"Failed to store resolved alert in Redis: {e}")
        
        # Send resolution notification
        message = f"RESOLVED: {alert['message']}"
        self._send_notification(AlertLevel.INFO, message, is_resolution=True)
        
        log.info(f"GPU Alert resolved: {alert['message']}")
    
    def _send_notification(self, level: str, message: str, is_resolution: bool) -> None:
        """
        Send alert notification via Telegram.
        
        Args:
            level: Alert level
            message: Alert message
            is_resolution: Whether this is a resolution notification
        """
        if not self._telegram_bot or not TELEGRAM_ADMIN_CHAT_ID:
            return
        
        try:
            # Format message with emoji
            if is_resolution:
                emoji = "✅"
            elif level == AlertLevel.CRITICAL:
                emoji = "🚨"
            elif level == AlertLevel.WARNING:
                emoji = "⚠️"
            else:
                emoji = "ℹ️"
            
            formatted_message = f"{emoji} **GPU Alert**\n\n{message}"
            
            # Send to Telegram
            self._telegram_bot.send_message(TELEGRAM_ADMIN_CHAT_ID, formatted_message)
            
        except Exception as e:
            log.error(f"Failed to send Telegram notification: {e}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """
        Get list of currently active alerts.
        
        Returns:
            List of active alert dictionaries
        """
        with self._state_lock:
            return [alert.copy() for alert in self._active_alerts.values()]
    
    def get_alert_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get alert history for specified time window.
        
        Args:
            hours: Number of hours of history to retrieve
        
        Returns:
            List of historical alerts
        """
        cutoff_time = time.time() - (hours * 3600)
        
        with self._history_lock:
            history = []
            for alert in self._history:
                triggered_at = alert.get("triggered_at", 0)
                if triggered_at >= cutoff_time:
                    history.append(alert.copy())
            
            return history
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current alerting system status.
        
        Returns:
            Dictionary with status information
        """
        with self._state_lock:
            active_count = len(self._active_alerts)
            conditions_tracked = len(self._condition_states)
        
        with self._history_lock:
            history_count = len(self._history)
        
        return {
            "enabled": GPU_ALERT_ENABLED,
            "running": self._background_thread is not None and self._background_thread.is_alive(),
            "active_alerts": active_count,
            "conditions_tracked": conditions_tracked,
            "history_count": history_count,
            "check_interval_seconds": GPU_ALERT_CHECK_INTERVAL,
            "rate_limit_seconds": GPU_ALERT_RATE_LIMIT_SECONDS,
            "redis_available": self._redis_client is not None,
            "telegram_available": self._telegram_bot is not None,
        }


# ======================== Singleton Instance ========================

_GPU_ALERT_MANAGER_INSTANCE: Optional[GPUAlertManager] = None
_GPU_ALERT_MANAGER_LOCK = threading.Lock()


def get_gpu_alert_manager() -> GPUAlertManager:
    """
    Get singleton GPU alert manager instance.
    
    Returns:
        GPUAlertManager instance
    """
    global _GPU_ALERT_MANAGER_INSTANCE
    
    with _GPU_ALERT_MANAGER_LOCK:
        if _GPU_ALERT_MANAGER_INSTANCE is None:
            _GPU_ALERT_MANAGER_INSTANCE = GPUAlertManager()
            # Start monitoring automatically
            _GPU_ALERT_MANAGER_INSTANCE.start_monitoring()
        
        return _GPU_ALERT_MANAGER_INSTANCE
