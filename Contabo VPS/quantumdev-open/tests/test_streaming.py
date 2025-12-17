#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_streaming.py — Tests for streaming response infrastructure

Tests the SSE streaming functionality including:
- SSE message formatting
- Streaming utilities
- Chat streaming endpoint
"""

import pytest
import asyncio
import json
from typing import AsyncGenerator, Dict, Any


# ============================================================================
# SSE Message Formatting Tests
# ============================================================================

def test_format_sse_message():
    """Test SSE message formatting."""
    from core.streaming_utils import format_sse_message
    
    # Basic message
    result = format_sse_message({"type": "token", "text": "Hello"})
    assert result.startswith("data: ")
    assert result.endswith("\n\n")
    assert "Hello" in result
    
    # Parse JSON from result
    data_line = result.split("\n")[0]
    json_str = data_line[6:]  # Remove "data: " prefix
    data = json.loads(json_str)
    assert data["type"] == "token"
    assert data["text"] == "Hello"


def test_create_thinking_message():
    """Test thinking phase message creation."""
    from core.streaming_utils import create_thinking_message
    
    result = create_thinking_message("Processing...")
    assert "thinking" in result
    assert "Processing..." in result
    assert result.endswith("\n\n")


def test_create_token_message():
    """Test token message creation."""
    from core.streaming_utils import create_token_message
    
    result = create_token_message("world", index=5)
    data = json.loads(result.split("\n")[0][6:])
    assert data["type"] == "token"
    assert data["text"] == "world"
    assert data["index"] == 5


def test_create_done_message():
    """Test completion message creation."""
    from core.streaming_utils import create_done_message
    
    # Basic done message
    result = create_done_message(total_tokens=42)
    data = json.loads(result.split("\n")[0][6:])
    assert data["type"] == "done"
    assert data["total_tokens"] == 42
    
    # With metadata
    result = create_done_message(
        total_tokens=100,
        metadata={"elapsed_ms": 1500}
    )
    data = json.loads(result.split("\n")[0][6:])
    assert data["metadata"]["elapsed_ms"] == 1500


def test_create_error_message():
    """Test error message creation."""
    from core.streaming_utils import create_error_message
    
    result = create_error_message("Connection failed", "timeout")
    data = json.loads(result.split("\n")[0][6:])
    assert data["type"] == "error"
    assert data["code"] == "timeout"
    assert data["message"] == "Connection failed"


def test_get_sse_headers():
    """Test SSE headers."""
    from core.streaming_utils import get_sse_headers
    
    headers = get_sse_headers()
    assert headers["Content-Type"] == "text/event-stream"
    assert headers["Cache-Control"] == "no-cache"
    assert headers["Connection"] == "keep-alive"


def test_count_tokens_approx():
    """Test approximate token counting."""
    from core.streaming_utils import count_tokens_approx
    
    # Empty string
    assert count_tokens_approx("") == 1  # Min 1
    
    # Short text (should be ~1 token per 4 chars)
    text = "Hello world"
    tokens = count_tokens_approx(text)
    assert tokens >= 1
    assert tokens <= len(text)
    
    # Longer text
    long_text = "This is a much longer piece of text that should have more tokens."
    long_tokens = count_tokens_approx(long_text)
    assert long_tokens > tokens


# ============================================================================
# Streaming Utilities Tests
# ============================================================================

@pytest.mark.asyncio
async def test_stream_with_fallback_success():
    """Test stream_with_fallback with successful stream."""
    from core.streaming_utils import stream_with_fallback
    
    async def mock_generator():
        """Mock successful stream."""
        for i in range(3):
            yield f"data: {i}\n\n"
    
    results = []
    async for chunk in stream_with_fallback(mock_generator()):
        results.append(chunk)
    
    assert len(results) == 3
    assert "data: 0\n\n" in results


@pytest.mark.asyncio
async def test_stream_with_fallback_error():
    """Test stream_with_fallback with error."""
    from core.streaming_utils import stream_with_fallback
    
    async def failing_generator():
        """Mock failing stream."""
        yield "data: start\n\n"
        raise RuntimeError("Stream failed")
    
    results = []
    async for chunk in stream_with_fallback(failing_generator()):
        results.append(chunk)
    
    # Should have start message and error message
    assert len(results) >= 1
    assert "start" in results[0]


# ============================================================================
# Chat Engine Streaming Tests
# ============================================================================

@pytest.mark.asyncio
async def test_reply_with_llm_streaming_basic():
    """Test basic LLM streaming (integration test - requires LLM endpoint)."""
    pytest.skip("Requires running LLM endpoint")
    
    from core.chat_engine import reply_with_llm_streaming
    
    tokens = []
    async for chunk in reply_with_llm_streaming(
        "Say hello",
        "You are a helpful assistant."
    ):
        chunk_type = chunk.get("type")
        if chunk_type == "token":
            tokens.append(chunk.get("text", ""))
        elif chunk_type == "done":
            total = chunk.get("total_tokens", 0)
            assert total > 0
            break
        elif chunk_type == "error":
            pytest.fail(f"Stream error: {chunk.get('message')}")
    
    # Should have received some tokens
    full_text = "".join(tokens)
    assert len(full_text) > 0


# ============================================================================
# API Endpoint Tests
# ============================================================================

@pytest.mark.asyncio
async def test_chat_stream_endpoint_format():
    """Test /chat/stream endpoint response format (mock test)."""
    # This is a unit test for the endpoint structure
    # Integration tests would require running FastAPI server
    
    from core.streaming_utils import (
        create_thinking_message,
        create_token_message,
        create_done_message
    )
    
    # Simulate endpoint flow
    messages = []
    
    # 1. Thinking phase
    messages.append(create_thinking_message("Processing..."))
    
    # 2. Token streaming
    for i, token in enumerate(["Hello", " ", "world"]):
        messages.append(create_token_message(token, i))
    
    # 3. Completion
    messages.append(create_done_message(3))
    
    # Verify all messages are valid SSE format
    for msg in messages:
        assert msg.endswith("\n\n")
        assert "data: " in msg
        
        # Parse JSON
        json_str = msg.split("\n")[0][6:]
        data = json.loads(json_str)
        assert "type" in data


@pytest.mark.asyncio
async def test_chat_stream_payload_parsing():
    """Test payload parsing for streaming endpoint."""
    # Test different payload formats
    
    # OpenAI-style messages
    payload1 = {
        "messages": [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"}
        ],
        "source": "test",
        "source_id": "123"
    }
    
    # Extract user text (simulating endpoint logic)
    messages = payload1.get("messages", [])
    user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_text = m.get("content", "")
            break
    
    assert user_text == "Hello"
    
    # Legacy format
    payload2 = {
        "text": "Hello world",
        "source": "tg",
        "source_id": "456"
    }
    
    user_text = payload2.get("text", "")
    assert user_text == "Hello world"


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_sse_message_with_invalid_data():
    """Test SSE formatting with invalid data."""
    from core.streaming_utils import format_sse_message
    
    # Should handle errors gracefully
    result = format_sse_message({"data": object()})
    
    # Should return error message in SSE format
    assert result.endswith("\n\n")
    assert "data: " in result


@pytest.mark.asyncio
async def test_streaming_timeout_handling():
    """Test timeout handling in streaming."""
    pytest.skip("Requires LLM endpoint")
    
    from core.chat_engine import reply_with_llm_streaming
    
    # This would test timeout behavior with very short timeout
    # In practice, would need to mock the HTTP client
    pass


# ============================================================================
# Performance Tests
# ============================================================================

def test_sse_formatting_performance():
    """Test SSE message formatting performance."""
    import time
    from core.streaming_utils import format_sse_message
    
    # Format 1000 messages
    start = time.perf_counter()
    for i in range(1000):
        format_sse_message({"type": "token", "text": f"Token {i}"})
    elapsed = time.perf_counter() - start
    
    # Should be fast (< 100ms for 1000 messages)
    assert elapsed < 0.1, f"SSE formatting too slow: {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_stream_latency():
    """Test streaming latency (first token time)."""
    pytest.skip("Requires LLM endpoint")
    
    import time
    from core.chat_engine import reply_with_llm_streaming
    
    start = time.perf_counter()
    first_token_time = None
    
    async for chunk in reply_with_llm_streaming(
        "Say hi",
        "You are helpful."
    ):
        if chunk.get("type") == "token" and first_token_time is None:
            first_token_time = time.perf_counter() - start
            break
    
    # First token should arrive quickly (< 2s)
    assert first_token_time is not None
    assert first_token_time < 2.0


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_end_to_end_streaming():
    """Full end-to-end streaming test."""
    pytest.skip("Requires running FastAPI server and LLM endpoint")
    
    import aiohttp
    
    # Would test actual HTTP streaming from /chat/stream endpoint
    async with aiohttp.ClientSession() as session:
        payload = {
            "text": "Tell me a short joke",
            "source": "test",
            "source_id": "e2e_test"
        }
        
        async with session.post(
            "http://localhost:8000/chat/stream",
            json=payload
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "text/event-stream"
            
            tokens_received = 0
            async for line in response.content:
                line_str = line.decode('utf-8').strip()
                if line_str.startswith("data: "):
                    data = json.loads(line_str[6:])
                    if data["type"] == "token":
                        tokens_received += 1
                    elif data["type"] == "done":
                        break
            
            assert tokens_received > 0


if __name__ == "__main__":
    # Run basic tests
    print("Running SSE streaming tests...\n")
    
    print("✓ test_format_sse_message")
    test_format_sse_message()
    
    print("✓ test_create_thinking_message")
    test_create_thinking_message()
    
    print("✓ test_create_token_message")
    test_create_token_message()
    
    print("✓ test_create_done_message")
    test_create_done_message()
    
    print("✓ test_create_error_message")
    test_create_error_message()
    
    print("✓ test_get_sse_headers")
    test_get_sse_headers()
    
    print("✓ test_count_tokens_approx")
    test_count_tokens_approx()
    
    print("✓ test_sse_formatting_performance")
    test_sse_formatting_performance()
    
    print("\n✅ All basic tests passed!")
    print("\n⚠️  Integration tests require running LLM endpoint and are skipped.")
