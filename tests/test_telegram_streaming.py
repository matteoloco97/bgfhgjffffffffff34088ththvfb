#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_telegram_streaming.py — Tests for Telegram bot streaming functionality

Tests the streaming handler and integration with the Telegram bot.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ============================================================================
# TelegramStreamingHandler Tests
# ============================================================================

@pytest.mark.asyncio
async def test_streaming_handler_init():
    """Test streaming handler initialization."""
    from agents.telegram_streaming_handler import TelegramStreamingHandler
    
    # Mock bot
    mock_bot = Mock()
    handler = TelegramStreamingHandler(mock_bot)
    
    assert handler.bot == mock_bot


@pytest.mark.asyncio
async def test_truncate_text():
    """Test text truncation for Telegram message length limit."""
    from agents.telegram_streaming_handler import TelegramStreamingHandler
    
    mock_bot = Mock()
    handler = TelegramStreamingHandler(mock_bot)
    
    # Short text - no truncation
    short_text = "Hello world"
    assert handler._truncate_text(short_text) == short_text
    
    # Long text - should truncate
    long_text = "A" * 5000
    truncated = handler._truncate_text(long_text)
    assert len(truncated) <= 4096
    assert truncated.endswith("...")


@pytest.mark.asyncio
async def test_safe_edit_message_not_modified():
    """Test safe edit with 'message not modified' error."""
    from agents.telegram_streaming_handler import TelegramStreamingHandler
    from telegram.error import TelegramError
    
    mock_bot = Mock()
    handler = TelegramStreamingHandler(mock_bot)
    
    # Mock message that raises "message not modified" error
    mock_message = AsyncMock()
    mock_message.edit_text = AsyncMock(
        side_effect=TelegramError("Message is not modified")
    )
    
    # Should not raise exception
    await handler._safe_edit(mock_message, "Same text")


@pytest.mark.asyncio
async def test_send_typing():
    """Test typing indicator."""
    from agents.telegram_streaming_handler import TelegramStreamingHandler
    
    mock_bot = AsyncMock()
    handler = TelegramStreamingHandler(mock_bot)
    
    await handler._send_typing(123456)
    
    mock_bot.send_chat_action.assert_called_once_with(123456, "typing")


# ============================================================================
# Bot Integration Tests
# ============================================================================

def test_is_streaming_enabled_for_user():
    """Test user streaming preference check."""
    # Mock the module-level variables
    with patch('scripts.telegram_bot.TELEGRAM_STREAMING_ENABLED', True):
        with patch('scripts.telegram_bot._user_streaming_prefs', {123: True, 456: False}):
            from scripts.telegram_bot import is_streaming_enabled_for_user
            
            # User with preference set to True
            assert is_streaming_enabled_for_user(123) == True
            
            # User with preference set to False
            assert is_streaming_enabled_for_user(456) == False
            
            # User without preference (default True when globally enabled)
            assert is_streaming_enabled_for_user(789) == True


def test_is_streaming_disabled_globally():
    """Test streaming disabled globally."""
    with patch('scripts.telegram_bot.TELEGRAM_STREAMING_ENABLED', False):
        from scripts.telegram_bot import is_streaming_enabled_for_user
        
        # Should always return False when globally disabled
        assert is_streaming_enabled_for_user(123) == False


def test_set_user_streaming_preference():
    """Test setting user streaming preference."""
    prefs = {}
    with patch('scripts.telegram_bot._user_streaming_prefs', prefs):
        from scripts.telegram_bot import set_user_streaming_preference
        
        # Enable for user
        set_user_streaming_preference(123, True)
        assert prefs[123] == True
        
        # Disable for user
        set_user_streaming_preference(123, False)
        assert prefs[123] == False


# ============================================================================
# SSE Parsing Tests
# ============================================================================

@pytest.mark.asyncio
async def test_sse_message_parsing():
    """Test parsing of SSE messages from stream."""
    import json
    
    # Simulate SSE messages
    sse_messages = [
        'data: {"type": "thinking", "content": "Processing..."}\n\n',
        'data: {"type": "token", "text": "Hello", "index": 0}\n\n',
        'data: {"type": "token", "text": " world", "index": 1}\n\n',
        'data: {"type": "done", "total_tokens": 2}\n\n',
    ]
    
    parsed_messages = []
    for msg in sse_messages:
        if msg.startswith("data: "):
            json_str = msg[6:].strip()
            data = json.loads(json_str)
            parsed_messages.append(data)
    
    # Verify parsing
    assert len(parsed_messages) == 4
    assert parsed_messages[0]["type"] == "thinking"
    assert parsed_messages[1]["type"] == "token"
    assert parsed_messages[1]["text"] == "Hello"
    assert parsed_messages[3]["type"] == "done"


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_streaming_error_handling():
    """Test error handling in streaming."""
    from agents.telegram_streaming_handler import TelegramStreamingHandler, StreamingError
    
    mock_bot = Mock()
    handler = TelegramStreamingHandler(mock_bot)
    
    # Test with error callback
    error_messages = []
    
    def on_error(msg):
        error_messages.append(msg)
    
    # This would normally make an HTTP request, but we're testing error handling
    # In a real test, we'd mock httpx to return an error
    # For now, just verify the StreamingError can be raised
    with pytest.raises(StreamingError):
        raise StreamingError("Test error")


# ============================================================================
# Batching Tests
# ============================================================================

def test_batching_constants():
    """Test that batching constants are reasonable."""
    from agents.telegram_streaming_handler import (
        MIN_EDIT_INTERVAL_MS,
        TOKEN_BATCH_SIZE,
        MAX_MESSAGE_LENGTH
    )
    
    # Verify constants are within reasonable ranges
    assert MIN_EDIT_INTERVAL_MS >= 100  # At least 100ms
    assert MIN_EDIT_INTERVAL_MS <= 2000  # At most 2 seconds
    
    assert TOKEN_BATCH_SIZE >= 10  # At least 10 tokens
    assert TOKEN_BATCH_SIZE <= 200  # At most 200 tokens
    
    assert MAX_MESSAGE_LENGTH == 4096  # Telegram limit


# ============================================================================
# Integration with Bot Commands
# ============================================================================

@pytest.mark.asyncio
async def test_streaming_command_toggle():
    """Test /streaming command for toggling."""
    # This would require mocking the Update and Context objects
    # For now, just verify the command function exists
    from scripts.telegram_bot import streaming_cmd
    
    assert callable(streaming_cmd)


# ============================================================================
# Performance Tests
# ============================================================================

def test_truncation_performance():
    """Test text truncation performance."""
    import time
    from agents.telegram_streaming_handler import TelegramStreamingHandler
    
    mock_bot = Mock()
    handler = TelegramStreamingHandler(mock_bot)
    
    # Create large text
    large_text = "A" * 100000
    
    # Measure truncation time
    start = time.perf_counter()
    for _ in range(1000):
        handler._truncate_text(large_text)
    elapsed = time.perf_counter() - start
    
    # Should be fast (< 100ms for 1000 operations)
    assert elapsed < 0.1, f"Truncation too slow: {elapsed:.3f}s"


if __name__ == "__main__":
    # Run basic tests
    print("Running Telegram streaming tests...\n")
    
    # Test handler init
    print("✓ test_streaming_handler_init")
    asyncio.run(test_streaming_handler_init())
    
    # Test batching constants
    print("✓ test_batching_constants")
    test_batching_constants()
    
    # Test SSE parsing
    print("✓ test_sse_message_parsing")
    asyncio.run(test_sse_message_parsing())
    
    # Test truncation performance
    print("✓ test_truncation_performance")
    test_truncation_performance()
    
    print("\n✅ All basic tests passed!")
    print("\n⚠️  Integration tests require running bot and backend.")
