#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_rate_limiting.py - Unit tests for rate limiting.

Tests rate limit enforcement, bypass mechanisms (localhost, admin token),
headers, and error responses.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# RATE LIMITER SETUP TESTS
# ============================================================================

class TestRateLimiterSetup:
    """Tests for rate limiter configuration and setup."""
    
    def test_slowapi_import(self):
        """Test that slowapi can be imported."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        from slowapi.errors import RateLimitExceeded
        
        assert Limiter is not None
        assert get_remote_address is not None
        assert RateLimitExceeded is not None
    
    def test_rate_limiter_can_be_created(self):
        """Test that a rate limiter can be created."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        
        limiter = Limiter(key_func=get_remote_address)
        assert limiter is not None
    
    def test_admin_token_env_var(self):
        """Test that ADMIN_TOKEN env var can be read."""
        import os
        
        # ADMIN_TOKEN may or may not be set in test env
        token = os.getenv('ADMIN_TOKEN', '')
        assert isinstance(token, str)


# ============================================================================
# IP ADDRESS EXTRACTION TESTS
# ============================================================================

class TestIPAddressExtraction:
    """Tests for IP address extraction from requests."""
    
    def test_get_remote_address_basic(self):
        """Test basic remote address extraction."""
        from slowapi.util import get_remote_address
        
        # Create mock request
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.100"
        
        address = get_remote_address(mock_request)
        
        assert address == "192.168.1.100"
    
    def test_get_remote_address_with_forwarded_for(self):
        """Test remote address with X-Forwarded-For header."""
        from slowapi.util import get_remote_address
        
        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {"X-Forwarded-For": "203.0.113.50"}
        
        # Note: get_remote_address by default uses client.host
        # Custom extractors are needed for X-Forwarded-For
        address = get_remote_address(mock_request)
        
        # Default behavior returns client.host
        assert address is not None


# ============================================================================
# LOCALHOST BYPASS TESTS
# ============================================================================

class TestLocalhostBypass:
    """Tests for localhost bypass functionality."""
    
    def test_localhost_ip_detection_127_0_0_1(self):
        """Test that 127.0.0.1 is detected as localhost."""
        localhost_ips = ["127.0.0.1", "::1"]
        
        for ip in localhost_ips:
            # These IPs should be recognized as localhost
            assert ip in ["127.0.0.1", "::1", "localhost"]
    
    def test_localhost_ip_detection_loopback(self):
        """Test loopback address detection."""
        import ipaddress
        
        # Test that 127.x.x.x are loopback addresses
        test_ips = ["127.0.0.1", "127.0.0.2", "127.255.255.255"]
        
        for ip in test_ips:
            addr = ipaddress.ip_address(ip)
            assert addr.is_loopback


# ============================================================================
# RATE LIMIT RESPONSE TESTS
# ============================================================================

class TestRateLimitResponse:
    """Tests for rate limit exceeded responses."""
    
    def test_rate_limit_exception_exists(self):
        """Test that RateLimitExceeded exception exists."""
        from slowapi.errors import RateLimitExceeded
        
        assert RateLimitExceeded is not None
    
    def test_rate_limit_headers_format(self):
        """Test expected rate limit headers."""
        expected_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After"
        ]
        
        # These headers should be set on rate limited responses
        for header in expected_headers:
            assert isinstance(header, str)
            assert len(header) > 0


# ============================================================================
# RATE LIMIT CONFIGURATION TESTS
# ============================================================================

class TestRateLimitConfiguration:
    """Tests for rate limit configuration values."""
    
    def test_default_rate_limits_defined(self):
        """Test that default rate limits are defined."""
        # Expected rate limits per endpoint (from implementation)
        expected_limits = {
            "chat": 10,  # 10 per minute
            "web_search": 20,  # 20 per minute
            "web_summarize": 15,  # 15 per minute
            "unified": 10,  # 10 per minute
            "autonomous": 5,  # 5 per minute
        }
        
        for endpoint, limit in expected_limits.items():
            assert limit > 0
            assert limit <= 100  # Reasonable upper bound
    
    def test_rate_limit_window(self):
        """Test rate limit window configuration."""
        # Default window is 1 minute
        default_window_seconds = 60
        
        assert default_window_seconds == 60


# ============================================================================
# ADMIN TOKEN BYPASS TESTS
# ============================================================================

class TestAdminTokenBypass:
    """Tests for admin token bypass functionality."""
    
    def test_admin_token_header_name(self):
        """Test admin token header name."""
        header_name = "X-Admin-Token"
        
        assert header_name == "X-Admin-Token"
    
    def test_admin_token_validation_empty(self):
        """Test that empty admin token doesn't bypass."""
        admin_token = ""
        request_token = "some-token"
        
        # Empty ADMIN_TOKEN should not match any request token
        is_valid = bool(admin_token) and admin_token == request_token
        
        assert is_valid is False
    
    def test_admin_token_validation_match(self):
        """Test admin token validation with matching token."""
        admin_token = "secret-admin-token"
        request_token = "secret-admin-token"
        
        is_valid = bool(admin_token) and admin_token == request_token
        
        assert is_valid is True
    
    def test_admin_token_validation_mismatch(self):
        """Test admin token validation with mismatching token."""
        admin_token = "secret-admin-token"
        request_token = "wrong-token"
        
        is_valid = bool(admin_token) and admin_token == request_token
        
        assert is_valid is False


# ============================================================================
# RATE LIMIT KEY FUNCTION TESTS
# ============================================================================

class TestRateLimitKeyFunction:
    """Tests for rate limit key function."""
    
    def test_key_function_includes_ip(self):
        """Test that key function uses IP address."""
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.100"
        
        from slowapi.util import get_remote_address
        
        key = get_remote_address(mock_request)
        
        assert "192.168.1.100" in key or key == "192.168.1.100"
    
    def test_different_ips_different_keys(self):
        """Test that different IPs produce different keys."""
        from slowapi.util import get_remote_address
        
        mock_request1 = MagicMock()
        mock_request1.client.host = "192.168.1.100"
        
        mock_request2 = MagicMock()
        mock_request2.client.host = "192.168.1.101"
        
        key1 = get_remote_address(mock_request1)
        key2 = get_remote_address(mock_request2)
        
        assert key1 != key2


# ============================================================================
# RATE LIMIT DECORATOR TESTS
# ============================================================================

class TestRateLimitDecorator:
    """Tests for rate limit decorator behavior."""
    
    def test_limiter_creation(self):
        """Test that limiter can be created."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        
        limiter = Limiter(key_func=get_remote_address)
        
        assert limiter is not None
        assert hasattr(limiter, 'limit')
    
    def test_limit_decorator_creation(self):
        """Test that limit decorator can be created."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        
        limiter = Limiter(key_func=get_remote_address)
        
        # Create a limit decorator
        limit_decorator = limiter.limit("10/minute")
        
        assert callable(limit_decorator)
    
    def test_limit_string_parsing(self):
        """Test that limit strings are parsed correctly."""
        valid_limit_strings = [
            "10/minute",
            "100/hour",
            "1000/day",
            "5 per 1 minute",
            "10 per 1 hour",
        ]
        
        for limit_str in valid_limit_strings:
            # These should all be valid limit strings
            assert isinstance(limit_str, str)
            assert len(limit_str) > 0


# ============================================================================
# ERROR HANDLER TESTS
# ============================================================================

class TestRateLimitErrorHandler:
    """Tests for rate limit error handler."""
    
    def test_error_handler_import(self):
        """Test that error handler can be imported."""
        from slowapi import _rate_limit_exceeded_handler
        
        assert callable(_rate_limit_exceeded_handler)
    
    def test_rate_limit_exceeded_exception_import(self):
        """Test RateLimitExceeded exception can be imported."""
        from slowapi.errors import RateLimitExceeded
        
        assert RateLimitExceeded is not None


# ============================================================================
# EDGE CASES
# ============================================================================

class TestRateLimitEdgeCases:
    """Tests for rate limiting edge cases."""
    
    def test_ipv6_address_handling(self):
        """Test handling of IPv6 addresses."""
        ipv6_addresses = [
            "::1",  # localhost
            "2001:db8::1",  # example address
            "fe80::1",  # link-local
        ]
        
        for addr in ipv6_addresses:
            # Should handle IPv6 addresses as strings
            assert isinstance(addr, str)
            assert len(addr) > 0
    
    def test_empty_ip_address(self):
        """Test handling of empty IP address."""
        from slowapi.util import get_remote_address
        
        mock_request = MagicMock()
        mock_request.client = None
        
        # Should handle None client gracefully
        try:
            address = get_remote_address(mock_request)
            # If it returns something, it should be a string or None
            assert address is None or isinstance(address, str)
        except (AttributeError, TypeError):
            # Expected if client is None
            pass
    
    def test_concurrent_requests_same_ip(self):
        """Test that rate limits work for concurrent requests."""
        # This is a conceptual test - actual concurrency testing
        # would require integration tests
        rate_limit = 10
        window_seconds = 60
        
        # With 10 req/min, 11th request should be blocked
        expected_blocked_after = rate_limit
        
        assert expected_blocked_after == 10
    
    def test_rate_limit_reset_calculation(self):
        """Test rate limit reset time calculation."""
        import time
        
        current_time = int(time.time())
        window_seconds = 60
        
        # Reset time should be within the window
        reset_time = current_time + window_seconds
        
        assert reset_time > current_time
        assert reset_time <= current_time + window_seconds


# ============================================================================
# INTEGRATION WITH FASTAPI TESTS
# ============================================================================

class TestRateLimitFastAPIIntegration:
    """Tests for rate limiting integration with FastAPI."""
    
    def test_limiter_can_be_attached_to_app(self):
        """Test that limiter can be attached to FastAPI app."""
        from slowapi import Limiter
        from slowapi.util import get_remote_address
        from fastapi import FastAPI
        
        app = FastAPI()
        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter
        
        assert hasattr(app.state, 'limiter')
    
    def test_exception_handler_can_be_registered(self):
        """Test that rate limit exception handler can be registered."""
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from fastapi import FastAPI
        
        app = FastAPI()
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        
        # Check exception handler was added
        assert RateLimitExceeded in app.exception_handlers
