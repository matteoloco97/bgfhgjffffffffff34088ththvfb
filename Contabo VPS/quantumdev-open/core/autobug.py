#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/autobug.py — AutoBug Health Checks

Systematic health checks for all major subsystems:
- LLM inference
- Web search
- Redis cache
- ChromaDB
- System status

Each check is isolated and never crashes the entire process.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ======================== Configuration ========================

AUTOBUG_ENABLED = os.getenv("AUTOBUG_ENABLED", "1") == "1"
AUTOBUG_ENABLE_LLM = os.getenv("AUTOBUG_ENABLE_LLM", "1") == "1"
AUTOBUG_ENABLE_WEB_SEARCH = os.getenv("AUTOBUG_ENABLE_WEB_SEARCH", "1") == "1"
AUTOBUG_ENABLE_REDIS = os.getenv("AUTOBUG_ENABLE_REDIS", "1") == "1"
AUTOBUG_ENABLE_CHROMA = os.getenv("AUTOBUG_ENABLE_CHROMA", "1") == "1"
AUTOBUG_ENABLE_SYSTEM = os.getenv("AUTOBUG_ENABLE_SYSTEM", "1") == "1"

AUTOBUG_LLM_TIMEOUT_S = float(os.getenv("AUTOBUG_LLM_TIMEOUT_S", "15.0"))
AUTOBUG_WEB_TIMEOUT_S = float(os.getenv("AUTOBUG_WEB_TIMEOUT_S", "10.0"))
AUTOBUG_REDIS_TIMEOUT_S = float(os.getenv("AUTOBUG_REDIS_TIMEOUT_S", "5.0"))
AUTOBUG_CHROMA_TIMEOUT_S = float(os.getenv("AUTOBUG_CHROMA_TIMEOUT_S", "10.0"))


# ======================== Check Result ========================

@dataclass
class CheckResult:
    """Result of a single health check."""
    name: str
    ok: bool
    latency_ms: float
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


# ======================== Individual Checks ========================

def check_llm() -> CheckResult:
    """
    Test LLM inference with a simple ping request.
    
    Returns:
        CheckResult with test outcome.
    """
    start = time.monotonic()
    
    if not AUTOBUG_ENABLE_LLM:
        return CheckResult(
            name="llm",
            ok=False,
            latency_ms=0.0,
            error="check_disabled",
        )
    
    try:
        # Import the chat engine
        from core.chat_engine import reply_with_llm
        
        # Make a minimal test call
        result = reply_with_llm(
            user_text="ping",
            system_prompt="You are a helpful assistant. Reply with just 'pong'.",
        )
        
        latency_ms = (time.monotonic() - start) * 1000
        
        # Check if we got a response
        response_text = result.get("text", "") if isinstance(result, dict) else str(result)
        
        if response_text and len(response_text) > 0:
            return CheckResult(
                name="llm",
                ok=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "response_length": len(response_text),
                    "sample": response_text[:50],
                },
            )
        else:
            return CheckResult(
                name="llm",
                ok=False,
                latency_ms=round(latency_ms, 2),
                error="empty_response",
            )
            
    except ImportError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="llm",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"import_failed: {str(e)}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(f"LLM check failed: {e}")
        return CheckResult(
            name="llm",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"llm_call_failed: {str(e)}",
        )


def check_web_search() -> CheckResult:
    """
    Test web search functionality.
    
    Returns:
        CheckResult with test outcome.
    """
    start = time.monotonic()
    
    if not AUTOBUG_ENABLE_WEB_SEARCH:
        return CheckResult(
            name="web_search",
            ok=False,
            latency_ms=0.0,
            error="check_disabled",
        )
    
    try:
        # Import web search
        from core.web_search import search
        
        # Perform a simple, stable search query
        results = search("Wikipedia", num=3)
        
        latency_ms = (time.monotonic() - start) * 1000
        
        # Check if we got results
        if results and len(results) > 0:
            # Validate structure
            first_result = results[0]
            has_url = "url" in first_result or "link" in first_result
            has_content = any(k in first_result for k in ["snippet", "title", "description"])
            
            if has_url and has_content:
                return CheckResult(
                    name="web_search",
                    ok=True,
                    latency_ms=round(latency_ms, 2),
                    details={
                        "result_count": len(results),
                        "first_url": first_result.get("url") or first_result.get("link", "")[:50],
                    },
                )
            else:
                return CheckResult(
                    name="web_search",
                    ok=False,
                    latency_ms=round(latency_ms, 2),
                    error="invalid_result_structure",
                )
        else:
            return CheckResult(
                name="web_search",
                ok=False,
                latency_ms=round(latency_ms, 2),
                error="no_results",
            )
            
    except ImportError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="web_search",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"import_failed: {str(e)}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(f"Web search check failed: {e}")
        return CheckResult(
            name="web_search",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"search_failed: {str(e)}",
        )


def check_redis() -> CheckResult:
    """
    Test Redis cache connectivity and operations.
    
    Returns:
        CheckResult with test outcome.
    """
    start = time.monotonic()
    
    if not AUTOBUG_ENABLE_REDIS:
        return CheckResult(
            name="redis",
            ok=False,
            latency_ms=0.0,
            error="check_disabled",
        )
    
    try:
        import redis
        
        # Get Redis configuration from environment
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        
        # Create a test client with timeout
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            socket_connect_timeout=AUTOBUG_REDIS_TIMEOUT_S,
            socket_timeout=AUTOBUG_REDIS_TIMEOUT_S,
        )
        
        # Test SET operation
        test_key = f"autobug:test:{int(time.time())}"
        test_value = "autobug_healthcheck"
        client.setex(test_key, 60, test_value)  # 60 second TTL
        
        # Test GET operation
        retrieved = client.get(test_key)
        
        # Cleanup
        client.delete(test_key)
        
        latency_ms = (time.monotonic() - start) * 1000
        
        # Verify the value
        if retrieved and retrieved.decode('utf-8') == test_value:
            return CheckResult(
                name="redis",
                ok=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "host": redis_host,
                    "port": redis_port,
                    "db": redis_db,
                },
            )
        else:
            return CheckResult(
                name="redis",
                ok=False,
                latency_ms=round(latency_ms, 2),
                error="value_mismatch",
            )
            
    except ImportError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="redis",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"redis_not_installed: {str(e)}",
        )
    except redis.ConnectionError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="redis",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"connection_failed: {str(e)}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(f"Redis check failed: {e}")
        return CheckResult(
            name="redis",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"redis_operation_failed: {str(e)}",
        )


def check_chroma() -> CheckResult:
    """
    Test ChromaDB connectivity and basic operations.
    
    Returns:
        CheckResult with test outcome.
    """
    start = time.monotonic()
    
    if not AUTOBUG_ENABLE_CHROMA:
        return CheckResult(
            name="chroma",
            ok=False,
            latency_ms=0.0,
            error="check_disabled",
        )
    
    try:
        # Import chroma handler
        from utils.chroma_handler import _col, FACTS
        
        # Try to get the facts collection (will auto-create if needed)
        collection = _col(FACTS)
        
        # Test a simple heartbeat operation - try to count documents
        try:
            count = collection.count()
        except Exception:
            # If count() is not available, try get() with limit=1
            result = collection.get(limit=1)
            count = len(result.get("ids", [])) if result else 0
        
        latency_ms = (time.monotonic() - start) * 1000
        
        return CheckResult(
            name="chroma",
            ok=True,
            latency_ms=round(latency_ms, 2),
            details={
                "collection": FACTS,
                "document_count": count,
            },
        )
        
    except ImportError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="chroma",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"import_failed: {str(e)}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(f"ChromaDB check failed: {e}")
        return CheckResult(
            name="chroma",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"chroma_operation_failed: {str(e)}",
        )


def check_system_status() -> CheckResult:
    """
    Test system status monitoring.
    
    Returns:
        CheckResult with test outcome.
    """
    start = time.monotonic()
    
    if not AUTOBUG_ENABLE_SYSTEM:
        return CheckResult(
            name="system_status",
            ok=False,
            latency_ms=0.0,
            error="check_disabled",
        )
    
    try:
        from core.system_status import get_system_status
        
        status = get_system_status()
        
        latency_ms = (time.monotonic() - start) * 1000
        
        # Check if the system status call was successful
        ok = status.get("ok", False)
        
        if ok:
            # Extract some key metrics for the details
            metrics = status.get("metrics", {})
            cpu = metrics.get("cpu", {})
            memory = metrics.get("memory", {})
            
            return CheckResult(
                name="system_status",
                ok=True,
                latency_ms=round(latency_ms, 2),
                details={
                    "cpu_percent": cpu.get("percent"),
                    "ram_percent": memory.get("ram", {}).get("percent"),
                },
            )
        else:
            return CheckResult(
                name="system_status",
                ok=False,
                latency_ms=round(latency_ms, 2),
                error="system_metrics_unavailable",
            )
            
    except ImportError as e:
        latency_ms = (time.monotonic() - start) * 1000
        return CheckResult(
            name="system_status",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"import_failed: {str(e)}",
        )
    except Exception as e:
        latency_ms = (time.monotonic() - start) * 1000
        log.error(f"System status check failed: {e}")
        return CheckResult(
            name="system_status",
            ok=False,
            latency_ms=round(latency_ms, 2),
            error=f"status_check_failed: {str(e)}",
        )


# ======================== Master Function ========================

def run_autobug_checks() -> Dict[str, Any]:
    """
    Run all configured health checks.
    
    This function never raises exceptions - all errors are captured in check results.
    
    Returns:
        Dictionary with:
            - ok: bool (true if all checks passed)
            - started_at: ISO timestamp
            - finished_at: ISO timestamp
            - duration_ms: total runtime in milliseconds
            - checks: list of CheckResult dictionaries
            - summary: dict with passed/failed counts
            - system_status: optional system status dict
    """
    if not AUTOBUG_ENABLED:
        return {
            "ok": False,
            "error": "autobug_disabled",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "checks": [],
        }
    
    started_at = datetime.now(timezone.utc)
    start_time = time.monotonic()
    
    log.info("Starting AutoBug health checks...")
    
    # Run all checks in sequence
    checks: List[CheckResult] = []
    
    # 1. System Status (fast, foundational)
    checks.append(check_system_status())
    
    # 2. Redis (fast)
    checks.append(check_redis())
    
    # 3. ChromaDB (medium speed)
    checks.append(check_chroma())
    
    # 4. Web Search (medium-slow)
    checks.append(check_web_search())
    
    # 5. LLM (can be slow)
    checks.append(check_llm())
    
    finished_at = datetime.now(timezone.utc)
    duration_ms = (time.monotonic() - start_time) * 1000
    
    # Calculate summary
    passed = sum(1 for c in checks if c.ok)
    failed = len(checks) - passed
    all_ok = all(c.ok for c in checks)
    
    # Log results
    log.info(
        f"AutoBug checks completed: {passed}/{len(checks)} passed, "
        f"{failed} failed, duration: {duration_ms:.0f}ms"
    )
    
    if failed > 0:
        for check in checks:
            if not check.ok:
                log.warning(f"Check '{check.name}' failed: {check.error}")
    
    # Get full system status if the system check passed
    system_status_full = None
    try:
        from core.system_status import get_system_status
        system_status_full = get_system_status()
    except Exception as e:
        log.warning(f"Could not get full system status: {e}")
    
    return {
        "ok": all_ok,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": round(duration_ms, 2),
        "checks": [c.to_dict() for c in checks],
        "summary": {
            "total": len(checks),
            "passed": passed,
            "failed": failed,
        },
        "system_status": system_status_full,
    }
