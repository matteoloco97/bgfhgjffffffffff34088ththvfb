#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_system_status_autobug.py — Tests for System Status and AutoBug

Test coverage for the new system monitoring and health check modules.
"""

import sys
import os
import unittest
from typing import Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSystemStatus(unittest.TestCase):
    """Test cases for system status module."""
    
    def test_get_system_status_structure(self):
        """Test that get_system_status returns correct structure."""
        from core.system_status import get_system_status
        
        result = get_system_status()
        
        # Check top-level keys
        self.assertIn("ok", result)
        self.assertIn("timestamp", result)
        self.assertIn("metrics", result)
        
        # Check metrics structure
        metrics = result["metrics"]
        self.assertIn("cpu", metrics)
        self.assertIn("memory", metrics)
        self.assertIn("disk", metrics)
        self.assertIn("uptime", metrics)
        self.assertIn("gpu", metrics)
    
    def test_get_cpu_metrics(self):
        """Test CPU metrics collection."""
        from core.system_status import get_cpu_metrics
        
        result = get_cpu_metrics()
        
        # Should either have metrics or an error
        if "error" not in result:
            self.assertIn("percent", result)
            self.assertIn("count_logical", result)
            self.assertIn("count_physical", result)
            
            # Verify values are reasonable
            self.assertGreaterEqual(result["percent"], 0)
            self.assertLessEqual(result["percent"], 100)
            self.assertGreater(result["count_logical"], 0)
    
    def test_get_memory_metrics(self):
        """Test memory metrics collection."""
        from core.system_status import get_memory_metrics
        
        result = get_memory_metrics()
        
        # Should either have metrics or an error
        if "error" not in result:
            self.assertIn("ram", result)
            self.assertIn("swap", result)
            
            ram = result["ram"]
            self.assertIn("total_gb", ram)
            self.assertIn("used_gb", ram)
            self.assertIn("percent", ram)
            
            # Verify values are reasonable
            self.assertGreater(ram["total_gb"], 0)
            self.assertGreaterEqual(ram["percent"], 0)
            self.assertLessEqual(ram["percent"], 100)
    
    def test_get_disk_metrics(self):
        """Test disk metrics collection."""
        from core.system_status import get_disk_metrics
        
        result = get_disk_metrics()
        
        # Should either have metrics or an error
        if "error" not in result:
            self.assertIn("path", result)
            self.assertIn("total_gb", result)
            self.assertIn("used_gb", result)
            self.assertIn("free_gb", result)
            self.assertIn("percent", result)
            
            # Verify values are reasonable
            self.assertEqual(result["path"], "/")
            self.assertGreater(result["total_gb"], 0)
    
    def test_get_uptime_metrics(self):
        """Test uptime metrics collection."""
        from core.system_status import get_uptime_metrics
        
        result = get_uptime_metrics()
        
        # Should either have metrics or an error
        if "error" not in result:
            self.assertIn("seconds", result)
            self.assertIn("boot_time_iso", result)
            self.assertIn("human_readable", result)
            
            # Uptime should be positive
            self.assertGreater(result["seconds"], 0)
    
    def test_get_gpu_metrics_graceful(self):
        """Test that GPU metrics handle missing GPU gracefully."""
        from core.system_status import get_gpu_metrics
        
        result = get_gpu_metrics()
        
        # Should always return a dict with available status
        self.assertIn("available", result)
        
        # If GPU is available, check structure
        if result["available"]:
            self.assertIn("count", result)
            self.assertIn("gpus", result)
    
    def test_system_status_never_raises(self):
        """Test that get_system_status never raises exceptions."""
        from core.system_status import get_system_status
        
        # Should not raise any exceptions
        try:
            result = get_system_status()
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"get_system_status raised an exception: {e}")


class TestAutoBug(unittest.TestCase):
    """Test cases for AutoBug health checks."""
    
    def test_run_autobug_checks_structure(self):
        """Test that run_autobug_checks returns correct structure."""
        from core.autobug import run_autobug_checks
        
        result = run_autobug_checks()
        
        # Check top-level keys
        self.assertIn("ok", result)
        self.assertIn("started_at", result)
        self.assertIn("finished_at", result)
        self.assertIn("duration_ms", result)
        self.assertIn("checks", result)
        self.assertIn("summary", result)
        
        # Check summary structure
        summary = result["summary"]
        self.assertIn("total", summary)
        self.assertIn("passed", summary)
        self.assertIn("failed", summary)
        
        # Verify counts
        total = summary["total"]
        passed = summary["passed"]
        failed = summary["failed"]
        self.assertEqual(total, passed + failed)
    
    def test_check_results_structure(self):
        """Test that individual checks return correct structure."""
        from core.autobug import run_autobug_checks
        
        result = run_autobug_checks()
        checks = result.get("checks", [])
        
        self.assertGreater(len(checks), 0, "Should have at least one check")
        
        for check in checks:
            self.assertIn("name", check)
            self.assertIn("ok", check)
            self.assertIn("latency_ms", check)
            
            # If check failed, should have error message
            if not check["ok"]:
                self.assertIn("error", check)
    
    def test_check_system_status(self):
        """Test the system status health check."""
        from core.autobug import check_system_status
        
        result = check_system_status()
        
        self.assertEqual(result.name, "system_status")
        self.assertIsInstance(result.ok, bool)
        self.assertGreaterEqual(result.latency_ms, 0)
    
    def test_check_redis(self):
        """Test the Redis health check."""
        from core.autobug import check_redis
        
        result = check_redis()
        
        self.assertEqual(result.name, "redis")
        self.assertIsInstance(result.ok, bool)
        self.assertGreaterEqual(result.latency_ms, 0)
        
        # If it failed, should have error message
        if not result.ok:
            self.assertIsNotNone(result.error)
    
    def test_check_chroma(self):
        """Test the ChromaDB health check."""
        from core.autobug import check_chroma
        
        result = check_chroma()
        
        self.assertEqual(result.name, "chroma")
        self.assertIsInstance(result.ok, bool)
        self.assertGreaterEqual(result.latency_ms, 0)
    
    def test_autobug_never_raises(self):
        """Test that run_autobug_checks never raises exceptions."""
        from core.autobug import run_autobug_checks
        
        # Should not raise any exceptions
        try:
            result = run_autobug_checks()
            self.assertIsInstance(result, dict)
        except Exception as e:
            self.fail(f"run_autobug_checks raised an exception: {e}")
    
    def test_autobug_respects_enabled_flag(self):
        """Test that AutoBug respects the AUTOBUG_ENABLED flag."""
        import os
        import importlib
        import sys
        
        # Temporarily disable autobug
        old_value = os.environ.get("AUTOBUG_ENABLED")
        os.environ["AUTOBUG_ENABLED"] = "0"
        
        try:
            # Reload module to pick up new env var
            if 'core.autobug' in sys.modules:
                importlib.reload(sys.modules['core.autobug'])
            from core.autobug import run_autobug_checks
            
            result = run_autobug_checks()
            
            # Should return error when disabled or have no checks run
            self.assertFalse(result.get("ok"))
            # When disabled, either has error or empty checks list
            has_error = "error" in result
            has_no_checks = len(result.get("checks", [])) == 0
            self.assertTrue(has_error or has_no_checks, 
                          "When disabled, should have error or no checks")
        finally:
            # Restore original value
            if old_value is None:
                os.environ.pop("AUTOBUG_ENABLED", None)
            else:
                os.environ["AUTOBUG_ENABLED"] = old_value
            # Reload module again to restore original state
            if 'core.autobug' in sys.modules:
                importlib.reload(sys.modules['core.autobug'])
    
    def test_individual_checks_isolation(self):
        """Test that individual checks don't affect each other."""
        from core.autobug import run_autobug_checks
        
        result = run_autobug_checks()
        checks = result.get("checks", [])
        
        # Even if some checks fail, others should still run
        self.assertGreater(len(checks), 0)
        
        # All checks should have been executed (not skipped due to errors)
        check_names = {c.get("name") for c in checks}
        # We expect at least these checks
        expected_checks = {"system_status", "redis", "chroma"}
        
        # At least some of the expected checks should be present
        self.assertTrue(
            len(check_names.intersection(expected_checks)) > 0,
            "Should have run at least some checks"
        )


class TestCheckResult(unittest.TestCase):
    """Test cases for CheckResult dataclass."""
    
    def test_check_result_to_dict(self):
        """Test CheckResult.to_dict() method."""
        from core.autobug import CheckResult
        
        check = CheckResult(
            name="test_check",
            ok=True,
            latency_ms=123.45,
            error=None,
            details={"foo": "bar"},
        )
        
        result = check.to_dict()
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result["name"], "test_check")
        self.assertEqual(result["ok"], True)
        self.assertEqual(result["latency_ms"], 123.45)
        self.assertIsNone(result["error"])
        self.assertEqual(result["details"], {"foo": "bar"})
    
    def test_check_result_with_error(self):
        """Test CheckResult with error."""
        from core.autobug import CheckResult
        
        check = CheckResult(
            name="failed_check",
            ok=False,
            latency_ms=50.0,
            error="something went wrong",
        )
        
        result = check.to_dict()
        
        self.assertEqual(result["name"], "failed_check")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "something went wrong")


if __name__ == "__main__":
    unittest.main()
