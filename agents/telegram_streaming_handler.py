#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agents/telegram_streaming_handler.py — Streaming response handler for Telegram bot

Handles progressive message updates using Telegram's edit_message_text() API
with intelligent batching to avoid rate limits.

Features:
- SSE stream parsing from /chat/stream endpoint
- Smart batching (time-based + token accumulation)
- Rate limit protection (max 1 edit per 500ms)
- Graceful error handling with fallback
- Typing indicator during thinking phase
"""

import asyncio
import json
import logging
import time
from typing import Optional, Callable, Any
import httpx
from telegram import Bot, Message
from telegram.error import TelegramError

log = logging.getLogger(__name__)

# Batching configuration
MIN_EDIT_INTERVAL_MS = 500  # Minimum time between edits (Telegram rate limit protection)
TOKEN_BATCH_SIZE = 50        # Accumulate this many tokens before forcing an update
MAX_MESSAGE_LENGTH = 4096    # Telegram message length limit

# Timeouts
STREAM_TIMEOUT_S = 120       # Total timeout for stream
CONNECT_TIMEOUT_S = 10       # Connection timeout

# Message truncation
ELLIPSIS_LENGTH = 3          # Length of "..." for truncation


class StreamingError(Exception):
    """Exception raised when streaming fails."""
    pass


class TelegramStreamingHandler:
    """
    Handler for streaming responses to Telegram.
    
    Manages progressive message updates with intelligent batching
    to avoid hitting Telegram's rate limits.
    """
    
    def __init__(self, bot: Bot):
        """
        Initialize the streaming handler.
        
        Args:
            bot: Telegram Bot instance
        """
        self.bot = bot
    
    async def stream_response(
        self,
        chat_id: int,
        url: str,
        payload: dict,
        initial_message: Optional[Message] = None,
        on_error: Optional[Callable[[str], Any]] = None
    ) -> tuple[str, bool]:
        """
        Stream a response from the backend API to Telegram.
        
        Args:
            chat_id: Telegram chat ID
            url: Backend streaming endpoint URL
            payload: Request payload (same format as /chat)
            initial_message: Optional message to edit (if None, creates new)
            on_error: Optional callback for error handling
            
        Returns:
            Tuple of (final_text, success)
            
        Raises:
            StreamingError: If streaming fails and on_error is None
        """
        accumulated_text = ""
        last_edit_time = 0.0
        token_count = 0
        thinking_shown = False
        message = initial_message
        
        try:
            # Create HTTP client with streaming support
            timeout_config = httpx.Timeout(STREAM_TIMEOUT_S, connect=CONNECT_TIMEOUT_S)
            async with httpx.AsyncClient(timeout=timeout_config) as client:
                # Make streaming request
                async with client.stream("POST", url, json=payload) as response:
                    # Check response status
                    if response.status_code != 200:
                        error_msg = f"Backend returned {response.status_code}"
                        log.error(f"Streaming error: {error_msg}")
                        if on_error:
                            on_error(error_msg)
                            return "", False
                        raise StreamingError(error_msg)
                    
                    # Send initial message if needed
                    if not message:
                        message = await self.bot.send_message(
                            chat_id=chat_id,
                            text="🤔 Thinking..."
                        )
                    
                    # Parse SSE stream
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        
                        # Parse SSE format: "data: {json}"
                        if line.startswith("data: "):
                            json_str = line[6:].strip()
                            
                            try:
                                data = json.loads(json_str)
                            except json.JSONDecodeError as e:
                                log.warning(f"Failed to parse SSE data: {e}")
                                continue
                            
                            msg_type = data.get("type")
                            
                            # Handle different message types
                            if msg_type == "thinking":
                                # Show thinking indicator
                                content = data.get("content", "Thinking...")
                                if not thinking_shown:
                                    await self._send_typing(chat_id)
                                    if message:
                                        await self._safe_edit(message, f"🤔 {content}")
                                    thinking_shown = True
                                
                            elif msg_type == "token":
                                # Accumulate token
                                token_text = data.get("text", "")
                                accumulated_text += token_text
                                token_count += 1
                                
                                # Check if we should update message
                                current_time = time.time()
                                time_elapsed_ms = (current_time - last_edit_time) * 1000
                                
                                should_update = (
                                    # Time-based batching
                                    time_elapsed_ms >= MIN_EDIT_INTERVAL_MS
                                    or
                                    # Token-based batching
                                    token_count >= TOKEN_BATCH_SIZE
                                    or
                                    # First token (clear thinking indicator)
                                    (token_count == 1 and thinking_shown)
                                )
                                
                                if should_update and message:
                                    # Truncate if too long
                                    display_text = self._truncate_text(accumulated_text)
                                    await self._safe_edit(message, display_text)
                                    last_edit_time = current_time
                                    token_count = 0  # Reset token counter
                            
                            elif msg_type == "done":
                                # Final update
                                if message and accumulated_text:
                                    display_text = self._truncate_text(accumulated_text)
                                    await self._safe_edit(message, display_text)
                                
                                log.info(f"Stream completed: {data.get('total_tokens', 0)} tokens")
                                return accumulated_text, True
                            
                            elif msg_type == "error":
                                # Stream error
                                error_msg = data.get("message", "Unknown error")
                                log.error(f"Stream error: {error_msg}")
                                if on_error:
                                    on_error(error_msg)
                                    return accumulated_text, False
                                raise StreamingError(error_msg)
                    
                    # Stream ended without "done" message
                    if accumulated_text:
                        return accumulated_text, True
                    else:
                        raise StreamingError("Stream ended without content")
        
        except httpx.TimeoutException as e:
            error_msg = f"Stream timeout: {e}"
            log.error(error_msg)
            if on_error:
                on_error(error_msg)
                return accumulated_text, False
            raise StreamingError(error_msg)
        
        except httpx.HTTPError as e:
            error_msg = f"HTTP error: {e}"
            log.error(error_msg)
            if on_error:
                on_error(error_msg)
                return accumulated_text, False
            raise StreamingError(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            log.error(error_msg, exc_info=True)
            if on_error:
                on_error(error_msg)
                return accumulated_text, False
            raise StreamingError(error_msg)
    
    async def _send_typing(self, chat_id: int):
        """Send typing indicator to Telegram."""
        try:
            await self.bot.send_chat_action(chat_id, "typing")
        except Exception as e:
            log.warning(f"Failed to send typing indicator: {e}")
    
    async def _safe_edit(self, message: Message, text: str):
        """
        Safely edit a message, catching common Telegram errors.
        
        Args:
            message: Message to edit
            text: New text content
        """
        try:
            await message.edit_text(text, disable_web_page_preview=True)
        except TelegramError as e:
            # Common errors that can be safely ignored
            error_str = str(e).lower()
            if "message is not modified" in error_str:
                # Message content is the same, no need to edit
                pass
            elif "message to edit not found" in error_str:
                # Message was deleted, can't edit
                log.warning("Message to edit not found")
            elif "message can't be edited" in error_str:
                # Message is too old or otherwise not editable
                log.warning("Message can't be edited")
            else:
                # Other errors should be logged
                log.error(f"Failed to edit message: {e}")
        except Exception as e:
            log.error(f"Unexpected error editing message: {e}")
    
    def _truncate_text(self, text: str) -> str:
        """
        Truncate text to fit Telegram's message length limit.
        
        Args:
            text: Text to truncate
            
        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= MAX_MESSAGE_LENGTH:
            return text
        
        # Truncate and add ellipsis
        ellipsis = "..."
        truncate_at = MAX_MESSAGE_LENGTH - len(ellipsis)
        truncated = text[:truncate_at] + ellipsis
        log.warning(f"Text truncated from {len(text)} to {len(truncated)} chars")
        return truncated


async def test_streaming_handler():
    """Test function for the streaming handler (for development)."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # This is just a mock test - requires actual bot token and backend
    print("TelegramStreamingHandler test (mock)")
    print("- Smart batching: enabled (500ms minimum, 50 tokens)")
    print("- Rate limit protection: enabled")
    print("- Fallback support: enabled")
    print("✅ Module loaded successfully")


if __name__ == "__main__":
    asyncio.run(test_streaming_handler())
