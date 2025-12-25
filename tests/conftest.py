#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/conftest.py - Shared test fixtures and mock utilities for QuantumDev.

This module provides:
- Mock LLM responses
- Mock Redis client
- Test fixtures for common data
- Async test utilities
- Setup/teardown helpers
"""

import os
import sys
import json
import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================

# Disable external services during tests
os.environ.setdefault("ENABLE_L2_CACHE", "0")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("OPENAI_API_KEY", "test-key-for-mocking")
os.environ.setdefault("PARALLEL_SYNTHESIS_ENABLED", "1")


# ============================================================================
# MOCK LLM RESPONSES
# ============================================================================

MOCK_LLM_RESPONSES = {
    "default": "This is a mock LLM response for testing purposes.",
    "weather": "The weather in Rome is sunny with temperatures around 25°C.",
    "search": "Based on my search, Python 3.12 introduces several new features including improved error messages.",
    "synthesis": "**TL;DR:** The document discusses key advancements in the topic.\n\n• Key point 1\n• Key point 2\n• Key point 3",
    "code": "```python\nprint('Hello, World!')\n```",
    "error": "",  # Empty response to simulate errors
}


class MockLLMResponse:
    """Mock LLM response object."""
    
    def __init__(self, content: str):
        self.content = content
        self.choices = [MagicMock(message=MagicMock(content=content))]
        self.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )


@pytest.fixture
def mock_llm_response():
    """Fixture that returns a factory for mock LLM responses."""
    def _create_response(response_type: str = "default") -> str:
        return MOCK_LLM_RESPONSES.get(response_type, MOCK_LLM_RESPONSES["default"])
    return _create_response


@pytest.fixture
def mock_reply_with_llm():
    """Fixture that mocks the reply_with_llm function."""
    async def _mock_reply(prompt: str, persona: str = "", **kwargs) -> str:
        # Return different responses based on prompt content
        prompt_lower = prompt.lower()
        if "weather" in prompt_lower:
            return MOCK_LLM_RESPONSES["weather"]
        elif "search" in prompt_lower or "python" in prompt_lower:
            return MOCK_LLM_RESPONSES["search"]
        elif "synthesize" in prompt_lower or "summary" in prompt_lower:
            return MOCK_LLM_RESPONSES["synthesis"]
        elif "code" in prompt_lower:
            return MOCK_LLM_RESPONSES["code"]
        return MOCK_LLM_RESPONSES["default"]
    
    return _mock_reply


# ============================================================================
# MOCK REDIS CLIENT
# ============================================================================

class MockRedisClient:
    """Mock Redis client for testing cache operations."""
    
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}
        self._connected = True
    
    def ping(self) -> bool:
        """Simulate Redis ping."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        return True
    
    def get(self, key: str) -> Optional[bytes]:
        """Get value from mock cache."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        value = self._data.get(key)
        if value is not None:
            return value.encode() if isinstance(value, str) else value
        return None
    
    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set value in mock cache."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        self._data[key] = value
        if ex:
            import time
            self._expiry[key] = time.time() + ex
        return True
    
    def delete(self, *keys: str) -> int:
        """Delete keys from mock cache."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        count = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                self._expiry.pop(key, None)
                count += 1
        return count
    
    def exists(self, *keys: str) -> int:
        """Check if keys exist in mock cache."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        return sum(1 for key in keys if key in self._data)
    
    def keys(self, pattern: str = "*") -> List[bytes]:
        """Get keys matching pattern."""
        if not self._connected:
            raise ConnectionError("Redis not connected")
        import fnmatch
        matching = [k for k in self._data.keys() if fnmatch.fnmatch(k, pattern)]
        return [k.encode() for k in matching]
    
    def flushdb(self) -> bool:
        """Clear all data."""
        self._data.clear()
        self._expiry.clear()
        return True
    
    def close(self):
        """Close connection."""
        self._connected = False
    
    def disconnect(self):
        """Alias for close."""
        self.close()


@pytest.fixture
def mock_redis():
    """Fixture that returns a mock Redis client."""
    return MockRedisClient()


@pytest.fixture
def mock_redis_patch(mock_redis):
    """Fixture that patches Redis throughout the application."""
    with patch("redis.Redis", return_value=mock_redis):
        yield mock_redis


# ============================================================================
# MOCK HTTP CLIENT
# ============================================================================

class MockHTTPResponse:
    """Mock HTTP response."""
    
    def __init__(self, status: int = 200, text: str = "", json_data: Optional[Dict] = None):
        self.status = status
        self.status_code = status
        self._text = text
        self._json_data = json_data
    
    async def text(self) -> str:
        return self._text
    
    async def json(self) -> Dict:
        if self._json_data:
            return self._json_data
        return json.loads(self._text) if self._text else {}
    
    async def read(self) -> bytes:
        return self._text.encode()
    
    def raise_for_status(self):
        if self.status >= 400:
            raise Exception(f"HTTP {self.status}")


class MockHTTPSession:
    """Mock aiohttp ClientSession."""
    
    def __init__(self, responses: Optional[Dict[str, MockHTTPResponse]] = None):
        self.responses = responses or {}
        self.closed = False
        self.requests = []
    
    async def get(self, url: str, **kwargs) -> MockHTTPResponse:
        self.requests.append(("GET", url, kwargs))
        return self.responses.get(url, MockHTTPResponse(status=200, text="OK"))
    
    async def post(self, url: str, **kwargs) -> MockHTTPResponse:
        self.requests.append(("POST", url, kwargs))
        return self.responses.get(url, MockHTTPResponse(status=200, text="OK"))
    
    async def close(self):
        self.closed = True
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *args):
        await self.close()


@pytest.fixture
def mock_http_session():
    """Fixture that returns a mock HTTP session."""
    return MockHTTPSession()


# ============================================================================
# SAMPLE TEST DATA
# ============================================================================

@pytest.fixture
def sample_chat_request():
    """Sample ChatRequest data."""
    return {
        "text": "What's the weather like in Rome?",
        "source": "api",
        "source_id": "test_user_123"
    }


@pytest.fixture
def sample_web_search_request():
    """Sample WebSearchRequest data."""
    return {
        "q": "Python 3.12 new features",
        "k": 5,
        "summarize_top": 2,
        "source": "api",
        "source_id": "test_user_123"
    }


@pytest.fixture
def sample_documents():
    """Sample documents for testing synthesis."""
    return [
        {
            "idx": 1,
            "title": "Introduction to Python",
            "url": "https://example.com/python-intro",
            "text": "Python is a versatile programming language known for its readability.",
        },
        {
            "idx": 2,
            "title": "Python Best Practices",
            "url": "https://example.com/python-best",
            "text": "Following PEP 8 guidelines ensures consistent and readable code.",
        },
        {
            "idx": 3,
            "title": "Python 3.12 Features",
            "url": "https://example.com/python-3.12",
            "text": "Python 3.12 introduces improved error messages and performance enhancements.",
        },
    ]


@pytest.fixture
def sample_memory_entries():
    """Sample memory entries for testing."""
    return [
        {
            "content": "User prefers concise answers",
            "metadata": {"type": "preference", "timestamp": 1700000000}
        },
        {
            "content": "Previous conversation about Python",
            "metadata": {"type": "context", "timestamp": 1700001000}
        },
    ]


# ============================================================================
# ASYNC UTILITIES
# ============================================================================

@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def async_client():
    """Async test client for API testing."""
    try:
        from httpx import AsyncClient, ASGITransport
        from backend.quantum_api import app
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    except ImportError:
        pytest.skip("httpx not available")


# ============================================================================
# CACHE FIXTURES
# ============================================================================

@pytest.fixture
def reset_cache_stats_fixture():
    """Reset cache stats before and after each test."""
    from core.cache_middleware import reset_cache_stats
    reset_cache_stats()
    yield
    reset_cache_stats()


@pytest.fixture
def mock_multi_level_cache():
    """Mock multi-level cache for testing."""
    class MockMultiLevelCache:
        def __init__(self):
            self._cache = {}
            self.stats = {
                'l1_hits': 0,
                'l1_misses': 0,
                'l2_hits': 0,
                'l2_misses': 0,
                'total_requests': 0,
                'l1_evictions': 0,
            }
        
        def get(self, key: str) -> Optional[str]:
            self.stats['total_requests'] += 1
            if key in self._cache:
                self.stats['l1_hits'] += 1
                return self._cache[key]
            self.stats['l1_misses'] += 1
            return None
        
        def set(self, key: str, value: str):
            self._cache[key] = value
        
        def get_stats(self) -> Dict:
            total = self.stats['total_requests']
            hits = self.stats['l1_hits'] + self.stats['l2_hits']
            return {
                **self.stats,
                'hit_rate': hits / total if total > 0 else 0.0,
                'l1_size': len(self._cache),
                'l1_max_size': 100,
                'l1_enabled': True,
                'l2_enabled': False,
            }
        
        def clear_l1(self) -> int:
            count = len(self._cache)
            self._cache.clear()
            return count
    
    return MockMultiLevelCache()


# ============================================================================
# METRICS FIXTURES
# ============================================================================

@pytest.fixture
def reset_metrics():
    """Reset Prometheus metrics before each test."""
    # Note: Prometheus metrics are cumulative and can't easily be reset
    # This fixture ensures test isolation where possible
    yield


# ============================================================================
# FASTAPI TEST CLIENT
# ============================================================================

@pytest.fixture
def test_client():
    """Synchronous test client for FastAPI."""
    try:
        from fastapi.testclient import TestClient
        from backend.quantum_api import app
        
        with TestClient(app) as client:
            yield client
    except ImportError:
        pytest.skip("FastAPI test client not available")


# ============================================================================
# CLEANUP FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_after_test():
    """Cleanup after each test."""
    yield
    # Add any global cleanup here if needed


@pytest.fixture
def temp_env_vars():
    """Temporarily set environment variables for a test."""
    original_env = os.environ.copy()
    
    def _set_env(**kwargs):
        for key, value in kwargs.items():
            os.environ[key] = str(value)
    
    yield _set_env
    
    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)
