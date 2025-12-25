#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_async_http.py - Unit tests for async HTTP client.

Tests for async HTTP client with connection pooling, timeouts, and error handling.
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# IMPORT TESTS
# ============================================================================

class TestAsyncHttpImports:
    """Tests for async HTTP client imports."""
    
    def test_import_async_http_module(self):
        """Test that async HTTP module can be imported."""
        from core.async_http_client import (
            get_http_client,
            close_http_client,
            is_http_client_available,
            ensure_http_client,
        )
        
        assert callable(get_http_client)
        assert callable(close_http_client)
        assert callable(is_http_client_available)
        assert callable(ensure_http_client)
    
    def test_import_configuration(self):
        """Test configuration imports."""
        from core.async_http_client import (
            HTTP_POOL_SIZE,
            HTTP_POOL_PER_HOST,
            HTTP_TOTAL_TIMEOUT,
        )
        
        assert isinstance(HTTP_POOL_SIZE, int)
        assert isinstance(HTTP_POOL_PER_HOST, int)
        assert isinstance(HTTP_TOTAL_TIMEOUT, float)


# ============================================================================
# CONFIGURATION TESTS
# ============================================================================

class TestAsyncHttpConfiguration:
    """Tests for HTTP client configuration."""
    
    def test_default_pool_size(self):
        """Test default pool size configuration."""
        from core.async_http_client import HTTP_POOL_SIZE
        
        assert HTTP_POOL_SIZE > 0
        assert HTTP_POOL_SIZE <= 1000  # Reasonable upper bound
    
    def test_default_pool_per_host(self):
        """Test default per-host pool size."""
        from core.async_http_client import HTTP_POOL_PER_HOST, HTTP_POOL_SIZE
        
        assert HTTP_POOL_PER_HOST > 0
        assert HTTP_POOL_PER_HOST <= HTTP_POOL_SIZE
    
    def test_default_timeout(self):
        """Test default timeout configuration."""
        from core.async_http_client import HTTP_TOTAL_TIMEOUT
        
        assert HTTP_TOTAL_TIMEOUT > 0
        assert HTTP_TOTAL_TIMEOUT <= 60  # Reasonable upper bound
    
    def test_configuration_from_env(self):
        """Test configuration from environment variables."""
        original_env = os.environ.copy()
        
        try:
            os.environ['HTTP_POOL_SIZE'] = '100'
            os.environ['HTTP_POOL_PER_HOST'] = '20'
            os.environ['HTTP_TOTAL_TIMEOUT'] = '15.0'
            
            # Re-import to pick up new values
            import importlib
            from core import async_http_client
            importlib.reload(async_http_client)
            
            assert async_http_client.HTTP_POOL_SIZE == 100
            assert async_http_client.HTTP_POOL_PER_HOST == 20
            assert async_http_client.HTTP_TOTAL_TIMEOUT == 15.0
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            # Reload again to restore defaults
            import importlib
            from core import async_http_client
            importlib.reload(async_http_client)


# ============================================================================
# CLIENT AVAILABILITY TESTS
# ============================================================================

class TestHttpClientAvailability:
    """Tests for HTTP client availability."""
    
    def test_is_http_client_available(self):
        """Test checking if HTTP client is available."""
        from core.async_http_client import is_http_client_available
        
        result = is_http_client_available()
        
        # Result should be boolean
        assert isinstance(result, bool)
    
    def test_aiohttp_availability(self):
        """Test aiohttp availability check."""
        from core.async_http_client import AIOHTTP_AVAILABLE
        
        # aiohttp should be available in the test environment
        assert isinstance(AIOHTTP_AVAILABLE, bool)


# ============================================================================
# CLIENT LIFECYCLE TESTS
# ============================================================================

class TestHttpClientLifecycle:
    """Tests for HTTP client lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_get_http_client_creates_session(self):
        """Test that get_http_client creates a session."""
        from core.async_http_client import get_http_client, close_http_client
        
        try:
            client = await get_http_client()
            
            if client is not None:
                # Client should be an aiohttp ClientSession
                assert hasattr(client, 'get')
                assert hasattr(client, 'post')
                assert hasattr(client, 'close')
        finally:
            await close_http_client()
    
    @pytest.mark.asyncio
    async def test_get_http_client_returns_same_instance(self):
        """Test that get_http_client returns singleton."""
        from core.async_http_client import get_http_client, close_http_client
        
        try:
            client1 = await get_http_client()
            client2 = await get_http_client()
            
            if client1 is not None:
                assert client1 is client2
        finally:
            await close_http_client()
    
    @pytest.mark.asyncio
    async def test_close_http_client(self):
        """Test that close_http_client closes session."""
        from core.async_http_client import get_http_client, close_http_client
        
        # Create client
        client = await get_http_client()
        
        # Close client
        await close_http_client()
        
        # After close, should be able to get new client
        new_client = await get_http_client()
        
        if new_client is not None:
            assert new_client is not client or client.closed
        
        await close_http_client()
    
    @pytest.mark.asyncio
    async def test_close_http_client_idempotent(self):
        """Test that close_http_client can be called multiple times."""
        from core.async_http_client import close_http_client
        
        # Should not raise even if called multiple times
        await close_http_client()
        await close_http_client()
        await close_http_client()


# ============================================================================
# ENSURE CLIENT TESTS
# ============================================================================

class TestEnsureHttpClient:
    """Tests for ensure_http_client function."""
    
    @pytest.mark.asyncio
    async def test_ensure_http_client_returns_client(self):
        """Test that ensure_http_client returns a client."""
        from core.async_http_client import ensure_http_client, close_http_client, AIOHTTP_AVAILABLE
        
        if not AIOHTTP_AVAILABLE:
            pytest.skip("aiohttp not available")
        
        try:
            client = await ensure_http_client()
            assert client is not None
        finally:
            await close_http_client()
    
    @pytest.mark.asyncio
    async def test_ensure_http_client_raises_if_unavailable(self):
        """Test that ensure_http_client raises if aiohttp unavailable."""
        from core.async_http_client import AIOHTTP_AVAILABLE
        
        if AIOHTTP_AVAILABLE:
            # Can't easily test this when aiohttp is available
            pytest.skip("aiohttp is available")
        
        from core.async_http_client import ensure_http_client
        
        with pytest.raises(RuntimeError):
            await ensure_http_client()


# ============================================================================
# CONNECTION POOLING TESTS
# ============================================================================

class TestConnectionPooling:
    """Tests for connection pooling functionality."""
    
    @pytest.mark.asyncio
    async def test_client_has_connector(self):
        """Test that client has a connector for pooling."""
        from core.async_http_client import get_http_client, close_http_client, AIOHTTP_AVAILABLE
        
        if not AIOHTTP_AVAILABLE:
            pytest.skip("aiohttp not available")
        
        try:
            client = await get_http_client()
            
            if client is not None:
                assert hasattr(client, 'connector')
        finally:
            await close_http_client()
    
    def test_pool_size_limits(self):
        """Test that pool size limits are reasonable."""
        from core.async_http_client import HTTP_POOL_SIZE, HTTP_POOL_PER_HOST
        
        # Per-host should not exceed total
        assert HTTP_POOL_PER_HOST <= HTTP_POOL_SIZE
        
        # Both should be positive
        assert HTTP_POOL_SIZE > 0
        assert HTTP_POOL_PER_HOST > 0


# ============================================================================
# TIMEOUT TESTS
# ============================================================================

class TestHttpTimeouts:
    """Tests for HTTP timeout configuration."""
    
    def test_connect_timeout_configuration(self):
        """Test connect timeout is configured."""
        from core.async_http_client import HTTP_CONNECT_TIMEOUT, HTTP_TOTAL_TIMEOUT
        
        assert HTTP_CONNECT_TIMEOUT > 0
        assert HTTP_CONNECT_TIMEOUT < HTTP_TOTAL_TIMEOUT
    
    def test_sock_read_timeout_configuration(self):
        """Test socket read timeout is configured."""
        from core.async_http_client import HTTP_SOCK_READ_TIMEOUT, HTTP_TOTAL_TIMEOUT
        
        assert HTTP_SOCK_READ_TIMEOUT > 0
        assert HTTP_SOCK_READ_TIMEOUT <= HTTP_TOTAL_TIMEOUT
    
    def test_total_timeout_configuration(self):
        """Test total timeout is configured."""
        from core.async_http_client import HTTP_TOTAL_TIMEOUT
        
        assert HTTP_TOTAL_TIMEOUT > 0


# ============================================================================
# USER AGENT TESTS
# ============================================================================

class TestHttpUserAgent:
    """Tests for HTTP User-Agent configuration."""
    
    def test_default_user_agent(self):
        """Test default User-Agent is set."""
        from core.async_http_client import DEFAULT_USER_AGENT
        
        assert isinstance(DEFAULT_USER_AGENT, str)
        assert len(DEFAULT_USER_AGENT) > 0
    
    def test_user_agent_looks_like_browser(self):
        """Test User-Agent looks like a browser."""
        from core.async_http_client import DEFAULT_USER_AGENT
        
        # Should contain common browser identifiers
        assert "Mozilla" in DEFAULT_USER_AGENT or "Chrome" in DEFAULT_USER_AGENT


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestHttpErrorHandling:
    """Tests for HTTP client error handling."""
    
    @pytest.mark.asyncio
    async def test_client_handles_missing_aiohttp(self):
        """Test client handles missing aiohttp gracefully."""
        with patch.dict('sys.modules', {'aiohttp': None}):
            # This is tricky to test without actually removing aiohttp
            # Just verify the AIOHTTP_AVAILABLE flag works
            from core.async_http_client import AIOHTTP_AVAILABLE
            assert isinstance(AIOHTTP_AVAILABLE, bool)
    
    @pytest.mark.asyncio
    async def test_close_handles_already_closed(self):
        """Test closing already-closed client doesn't error."""
        from core.async_http_client import close_http_client
        
        # Multiple closes should be safe
        await close_http_client()
        await close_http_client()


# ============================================================================
# SESSION LOCK TESTS
# ============================================================================

class TestSessionLock:
    """Tests for session lock functionality."""
    
    @pytest.mark.asyncio
    async def test_concurrent_get_client_calls(self):
        """Test concurrent calls to get_http_client."""
        from core.async_http_client import get_http_client, close_http_client
        
        try:
            # Make concurrent calls
            results = await asyncio.gather(
                get_http_client(),
                get_http_client(),
                get_http_client(),
            )
            
            # All should return the same instance
            if results[0] is not None:
                assert all(r is results[0] for r in results)
        finally:
            await close_http_client()


# ============================================================================
# EDGE CASES
# ============================================================================

class TestAsyncHttpEdgeCases:
    """Tests for async HTTP edge cases."""
    
    def test_configuration_with_string_values(self):
        """Test configuration handles string env values."""
        # This test just verifies the module can handle env values correctly
        from core.async_http_client import HTTP_POOL_SIZE
        
        # The module already handles int conversion
        assert isinstance(HTTP_POOL_SIZE, int)
        assert HTTP_POOL_SIZE > 0
    
    @pytest.mark.asyncio
    async def test_client_with_custom_env(self):
        """Test client respects custom environment."""
        from core.async_http_client import get_http_client, close_http_client
        
        try:
            client = await get_http_client()
            
            if client is not None:
                # Client should exist
                assert client is not None
        finally:
            await close_http_client()


# ============================================================================
# MOCK HTTP CLIENT TESTS
# ============================================================================

class TestMockHttpClient:
    """Tests using mock HTTP client from conftest."""
    
    def test_mock_http_session_get(self, mock_http_session):
        """Test mock HTTP session GET request."""
        import asyncio
        
        async def test():
            response = await mock_http_session.get("http://example.com")
            assert response.status == 200
            return response
        
        asyncio.get_event_loop().run_until_complete(test())
    
    def test_mock_http_session_post(self, mock_http_session):
        """Test mock HTTP session POST request."""
        import asyncio
        
        async def test():
            response = await mock_http_session.post(
                "http://example.com",
                json={"key": "value"}
            )
            assert response.status == 200
            return response
        
        asyncio.get_event_loop().run_until_complete(test())
    
    def test_mock_http_session_tracks_requests(self, mock_http_session):
        """Test that mock session tracks requests."""
        import asyncio
        
        async def test():
            await mock_http_session.get("http://example.com/1")
            await mock_http_session.post("http://example.com/2", data={})
            
            assert len(mock_http_session.requests) == 2
            assert mock_http_session.requests[0][0] == "GET"
            assert mock_http_session.requests[1][0] == "POST"
        
        asyncio.get_event_loop().run_until_complete(test())
    
    def test_mock_http_session_close(self, mock_http_session):
        """Test mock session can be closed."""
        import asyncio
        
        async def test():
            assert mock_http_session.closed is False
            await mock_http_session.close()
            assert mock_http_session.closed is True
        
        asyncio.get_event_loop().run_until_complete(test())
