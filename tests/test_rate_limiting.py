#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test suite for rate limiting implementation with slowapi.

Tests:
1. External IP rate limiting (should be blocked after limit)
2. Localhost bypass (127.0.0.1 should NEVER be rate limited)
3. Admin token bypass (with X-Admin-Token header)
4. Rate limit headers in responses
5. 429 error responses with proper format
"""

import pytest
import time
import os
from fastapi.testclient import TestClient

# Import the FastAPI app
import sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.quantum_api import app, ADMIN_TOKEN


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestRateLimiting:
    """Test rate limiting functionality."""
    
    def test_chat_endpoint_rate_limit(self, client):
        """Test /chat endpoint rate limiting (10 req/min)."""
        # Make 10 requests (should succeed)
        for i in range(10):
            response = client.post(
                "/chat",
                json={"text": f"test message {i}", "source": "test", "source_id": "test_user"},
                headers={"X-Forwarded-For": "192.168.1.100"}  # Simulate external IP
            )
            # May fail due to missing LLM, but should not be rate limited
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        
        # 11th request should be rate limited
        response = client.post(
            "/chat",
            json={"text": "test message 11", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.100"}
        )
        assert response.status_code == 429, "Expected rate limit after 10 requests"
        
        # Check 429 error format
        data = response.json()
        assert "error" in data
        assert data["error"] == "rate_limit_exceeded"
        assert "retry_after_seconds" in data
        assert "endpoint" in data
        
        # Check headers
        assert "Retry-After" in response.headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
    
    def test_localhost_bypass(self, client):
        """Test that localhost (127.0.0.1) is NEVER rate limited."""
        # Make 20 requests from localhost (more than any limit)
        for i in range(20):
            response = client.post(
                "/chat",
                json={"text": f"localhost test {i}", "source": "telegram", "source_id": "bot"},
                # Don't set X-Forwarded-For, will use client.host which is localhost in tests
            )
            # Should NEVER be rate limited
            assert response.status_code != 429, f"Localhost was rate limited on request {i+1}! This breaks Telegram Bot!"
    
    def test_localhost_explicit_ip(self, client):
        """Test localhost bypass with explicit 127.0.0.1."""
        # Make 20 requests from explicit localhost IP
        for i in range(20):
            response = client.post(
                "/web/search",
                json={"q": f"localhost test {i}", "source": "telegram", "source_id": "bot"},
                headers={"X-Forwarded-For": "127.0.0.1"}  # Explicit localhost
            )
            # Should NEVER be rate limited
            assert response.status_code != 429, f"127.0.0.1 was rate limited on request {i+1}!"
    
    def test_admin_token_bypass(self, client):
        """Test admin token bypass with X-Admin-Token header."""
        if not ADMIN_TOKEN:
            pytest.skip("ADMIN_TOKEN not configured")
        
        # Make 20 requests with admin token (more than any limit)
        for i in range(20):
            response = client.post(
                "/autonomous",
                json={"goal": f"admin test {i}", "source": "api", "source_id": "admin"},
                headers={
                    "X-Admin-Token": ADMIN_TOKEN,
                    "X-Forwarded-For": "203.0.113.1"  # External IP
                }
            )
            # Should NEVER be rate limited with valid admin token
            assert response.status_code != 429, f"Admin token bypass failed on request {i+1}!"
    
    def test_web_search_rate_limit(self, client):
        """Test /web/search endpoint rate limiting (20 req/min)."""
        # Make 20 requests (should succeed)
        for i in range(20):
            response = client.post(
                "/web/search",
                json={"q": f"test query {i}", "source": "test", "source_id": "test_user"},
                headers={"X-Forwarded-For": "192.168.1.101"}
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        
        # 21st request should be rate limited
        response = client.post(
            "/web/search",
            json={"q": "test query 21", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.101"}
        )
        assert response.status_code == 429, "Expected rate limit after 20 requests"
    
    def test_web_summarize_rate_limit(self, client):
        """Test /web/summarize endpoint rate limiting (15 req/min)."""
        # Make 15 requests (should succeed)
        for i in range(15):
            response = client.post(
                "/web/summarize",
                json={"q": f"summarize test {i}", "source": "test", "source_id": "test_user"},
                headers={"X-Forwarded-For": "192.168.1.102"}
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        
        # 16th request should be rate limited
        response = client.post(
            "/web/summarize",
            json={"q": "summarize test 16", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.102"}
        )
        assert response.status_code == 429, "Expected rate limit after 15 requests"
    
    def test_unified_rate_limit(self, client):
        """Test /unified endpoint rate limiting (10 req/min)."""
        # Make 10 requests (should succeed)
        for i in range(10):
            response = client.post(
                "/unified",
                json={"q": f"unified test {i}", "source": "test", "source_id": "test_user"},
                headers={"X-Forwarded-For": "192.168.1.103"}
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        
        # 11th request should be rate limited
        response = client.post(
            "/unified",
            json={"q": "unified test 11", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.103"}
        )
        assert response.status_code == 429, "Expected rate limit after 10 requests"
    
    def test_autonomous_rate_limit(self, client):
        """Test /autonomous endpoint rate limiting (5 req/min)."""
        # Make 5 requests (should succeed)
        for i in range(5):
            response = client.post(
                "/autonomous",
                json={"goal": f"autonomous test {i}", "source": "test", "source_id": "test_user"},
                headers={"X-Forwarded-For": "192.168.1.104"}
            )
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"
        
        # 6th request should be rate limited
        response = client.post(
            "/autonomous",
            json={"goal": "autonomous test 6", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.104"}
        )
        assert response.status_code == 429, "Expected rate limit after 5 requests"
    
    def test_rate_limit_headers_present(self, client):
        """Test that rate limit headers are present in responses."""
        response = client.post(
            "/chat",
            json={"text": "test message", "source": "test", "source_id": "test_user"},
            headers={"X-Forwarded-For": "192.168.1.105"}
        )
        
        # Check for rate limit headers (may be set by middleware or slowapi)
        # At minimum, we should have some indication
        assert "X-RateLimit-Limit" in response.headers or response.headers.get("X-RateLimit-Limit") is not None
    
    def test_different_ips_independent_limits(self, client):
        """Test that different IPs have independent rate limits."""
        # IP 1: Make 10 requests
        for i in range(10):
            response = client.post(
                "/chat",
                json={"text": f"test {i}", "source": "test", "source_id": "user1"},
                headers={"X-Forwarded-For": "192.168.1.106"}
            )
            assert response.status_code != 429
        
        # IP 1: 11th should be blocked
        response = client.post(
            "/chat",
            json={"text": "test 11", "source": "test", "source_id": "user1"},
            headers={"X-Forwarded-For": "192.168.1.106"}
        )
        assert response.status_code == 429
        
        # IP 2: Should still work (independent limit)
        response = client.post(
            "/chat",
            json={"text": "test from IP2", "source": "test", "source_id": "user2"},
            headers={"X-Forwarded-For": "192.168.1.107"}
        )
        assert response.status_code != 429, "Different IP should have independent rate limit"


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
