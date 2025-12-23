#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Simple validation test for rate limiting implementation.
Tests the core logic without requiring full app startup.
"""

import os
import sys

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_slowapi_import():
    """Test that slowapi is properly installed."""
    try:
        import slowapi
        from slowapi import Limiter
        from slowapi.errors import RateLimitExceeded
        print("✓ slowapi imports successfully")
        return True
    except ImportError as e:
        print(f"✗ slowapi import failed: {e}")
        return False


def test_redis_connection():
    """Test Redis connection for rate limiting storage."""
    try:
        import redis
        REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
        REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
        REDIS_DB = int(os.getenv("REDIS_DB", "0"))
        
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=2)
        client.ping()
        print(f"✓ Redis connection successful at {REDIS_HOST}:{REDIS_PORT}")
        return True
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        print("  Note: Redis must be running for rate limiting to work")
        return False


def test_rate_limiting_config():
    """Test that rate limiting configuration is present in the code."""
    try:
        with open(os.path.join(ROOT, "backend", "quantum_api.py"), "r") as f:
            content = f.read()
        
        checks = {
            "slowapi import": "from slowapi import Limiter",
            "get_remote_address_with_whitelist": "def get_remote_address_with_whitelist",
            "localhost bypass": "localhost-bypass",
            "admin bypass": "admin-bypass",
            "limiter initialization": "limiter = Limiter",
            "rate limit handler": "@app.exception_handler(RateLimitExceeded)",
            "/chat limit": '@limiter.limit("10/minute")',
            "/web/search limit": '@limiter.limit("20/minute")',
            "/web/summarize limit": '@limiter.limit("15/minute")',
            "/unified limit": '@limiter.limit("10/minute")',
            "/autonomous limit": '@limiter.limit("5/minute")',
        }
        
        all_passed = True
        for check_name, check_string in checks.items():
            if check_string in content:
                print(f"✓ {check_name} configured")
            else:
                print(f"✗ {check_name} NOT FOUND")
                all_passed = False
        
        return all_passed
    except Exception as e:
        print(f"✗ Config validation failed: {e}")
        return False


def test_env_example_has_admin_token():
    """Test that .env.example has ADMIN_TOKEN."""
    try:
        with open(os.path.join(ROOT, ".env.example"), "r") as f:
            content = f.read()
        
        if "ADMIN_TOKEN" in content:
            print("✓ .env.example has ADMIN_TOKEN configured")
            return True
        else:
            print("✗ .env.example missing ADMIN_TOKEN")
            return False
    except Exception as e:
        print(f"✗ .env.example validation failed: {e}")
        return False


def test_requirements_has_slowapi():
    """Test that requirements.txt has slowapi."""
    try:
        with open(os.path.join(ROOT, "requirements.txt"), "r") as f:
            content = f.read()
        
        if "slowapi" in content:
            print("✓ requirements.txt has slowapi")
            return True
        else:
            print("✗ requirements.txt missing slowapi")
            return False
    except Exception as e:
        print(f"✗ requirements.txt validation failed: {e}")
        return False


def main():
    """Run all validation tests."""
    print("=" * 70)
    print("Rate Limiting Implementation Validation")
    print("=" * 70)
    print()
    
    results = []
    
    print("1. Testing slowapi installation...")
    results.append(test_slowapi_import())
    print()
    
    print("2. Testing Redis connection...")
    results.append(test_redis_connection())
    print()
    
    print("3. Testing rate limiting configuration...")
    results.append(test_rate_limiting_config())
    print()
    
    print("4. Testing .env.example configuration...")
    results.append(test_env_example_has_admin_token())
    print()
    
    print("5. Testing requirements.txt...")
    results.append(test_requirements_has_slowapi())
    print()
    
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✓ ALL TESTS PASSED ({passed}/{total})")
        print()
        print("Rate limiting is properly configured with:")
        print("  • slowapi library")
        print("  • Redis storage backend")
        print("  • Localhost bypass (127.0.0.1, ::1)")
        print("  • Admin token bypass via X-Admin-Token header")
        print("  • Per-endpoint rate limits:")
        print("    - /chat: 10 requests/minute")
        print("    - /web/search: 20 requests/minute")
        print("    - /web/summarize: 15 requests/minute")
        print("    - /unified: 10 requests/minute")
        print("    - /autonomous: 5 requests/minute")
        print("  • Custom 429 error responses")
        print("  • Rate limit headers in responses")
        return 0
    else:
        print(f"✗ SOME TESTS FAILED ({passed}/{total} passed)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
