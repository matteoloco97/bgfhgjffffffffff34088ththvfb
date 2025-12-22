#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/streaming_utils.py — Server-Sent Events (SSE) utilities for streaming responses

Provides helpers for formatting and streaming SSE messages in compliance with
the SSE specification (text/event-stream format).
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Any, AsyncGenerator

log = logging.getLogger(__name__)


def format_sse_message(data: Dict[str, Any], event: str = "message") -> str:
    """
    Format a message in SSE format.
    
    SSE format specification:
    - Each message starts with 'data: ' followed by JSON content
    - Each message ends with double newline '\n\n'
    - Optional 'event: ' field to specify event type
    
    Args:
        data: Dictionary to be sent as JSON payload
        event: Optional event type (default: "message")
    
    Returns:
        Formatted SSE message string
    
    Example:
        >>> format_sse_message({"type": "token", "text": "Hello"})
        'data: {"type": "token", "text": "Hello"}\\n\\n'
    """
    try:
        json_str = json.dumps(data, ensure_ascii=False)
        # Standard SSE format: "data: {json}\n\n"
        if event != "message":
            return f"event: {event}\ndata: {json_str}\n\n"
        return f"data: {json_str}\n\n"
    except Exception as e:
        log.error(f"Error formatting SSE message: {e}")
        # Return error message in SSE format
        error_data = {"type": "error", "message": str(e)}
        return f"data: {json.dumps(error_data)}\n\n"


def create_thinking_message(content: str) -> str:
    """
    Create a thinking phase SSE message.
    
    Args:
        content: Thinking phase description
    
    Returns:
        Formatted SSE message
    """
    return format_sse_message({
        "type": "thinking",
        "content": content
    })


def create_token_message(text: str, index: int = 0) -> str:
    """
    Create a token streaming SSE message.
    
    Args:
        text: Token text
        index: Token index in the stream
    
    Returns:
        Formatted SSE message
    """
    return format_sse_message({
        "type": "token",
        "text": text,
        "index": index
    })


def create_done_message(total_tokens: int = 0, metadata: Dict[str, Any] | None = None) -> str:
    """
    Create a completion SSE message.
    
    Args:
        total_tokens: Total number of tokens generated
        metadata: Optional metadata about the completion
    
    Returns:
        Formatted SSE message
    """
    data: Dict[str, Any] = {
        "type": "done",
        "total_tokens": total_tokens
    }
    if metadata:
        data["metadata"] = metadata
    return format_sse_message(data)


def create_error_message(error: str, code: str = "error") -> str:
    """
    Create an error SSE message.
    
    Args:
        error: Error message
        code: Error code
    
    Returns:
        Formatted SSE message
    """
    return format_sse_message({
        "type": "error",
        "code": code,
        "message": error
    })


async def stream_with_fallback(
    stream_generator: AsyncGenerator[str, None],
    fallback_message: str = "Stream interrupted"
) -> AsyncGenerator[str, None]:
    """
    Wrapper for streaming with automatic error handling.
    
    Catches exceptions in the stream and yields an error message
    before closing the stream gracefully.
    
    Args:
        stream_generator: The async generator to wrap
        fallback_message: Message to send if stream fails
    
    Yields:
        SSE formatted messages
    """
    try:
        async for chunk in stream_generator:
            yield chunk
    except Exception as e:
        log.error(f"Stream error: {e}")
        yield create_error_message(
            error=fallback_message,
            code="stream_error"
        )
        # Send done message to properly close stream
        yield create_done_message(total_tokens=0, metadata={"error": True})


def get_sse_headers() -> Dict[str, str]:
    """
    Get standard SSE headers for streaming responses.
    
    Returns:
        Dictionary of HTTP headers for SSE
    """
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # Disable nginx buffering
    }


# Token counting helper (simple approximation)
def count_tokens_approx(text: str) -> int:
    """
    Approximate token count for text.
    
    Uses simple heuristic: ~4 chars per token for English text.
    
    Args:
        text: Input text
    
    Returns:
        Approximate token count
    """
    return max(1, len(text) // 4)
