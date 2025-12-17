#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_streaming_demo.py — Demo script for testing streaming functionality

This script demonstrates the SSE streaming capabilities:
1. Shows SSE message formatting
2. Simulates streaming flow
3. Can be extended to test against running server

Usage:
    python scripts/test_streaming_demo.py
"""

import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.streaming_utils import (
    format_sse_message,
    create_thinking_message,
    create_token_message,
    create_done_message,
    create_error_message,
    get_sse_headers,
)


def demo_sse_formatting():
    """Demonstrate SSE message formatting."""
    print("=" * 70)
    print("SSE Message Formatting Demo")
    print("=" * 70)
    
    # 1. Thinking message
    print("\n1. Thinking Phase Message:")
    thinking = create_thinking_message("Analyzing your question...")
    print(thinking)
    
    # 2. Token messages
    print("2. Token Stream (simulated):")
    tokens = ["Hello", " ", "world", "!", " ", "How", " ", "are", " ", "you", "?"]
    for i, token in enumerate(tokens):
        msg = create_token_message(token, index=i)
        # Print without newlines for visual effect
        print(msg, end="", flush=True)
    
    # 3. Done message
    print("\n3. Completion Message:")
    done = create_done_message(
        total_tokens=len(tokens),
        metadata={
            "elapsed_ms": 1234,
            "model": "test-model"
        }
    )
    print(done)
    
    # 4. Error message (example)
    print("4. Error Message (example):")
    error = create_error_message("Connection timeout", "timeout")
    print(error)
    
    # 5. SSE headers
    print("5. SSE Response Headers:")
    headers = get_sse_headers()
    for key, value in headers.items():
        print(f"   {key}: {value}")


async def demo_async_streaming():
    """Demonstrate async streaming pattern."""
    print("\n" + "=" * 70)
    print("Async Streaming Pattern Demo")
    print("=" * 70)
    
    async def mock_llm_stream():
        """Mock LLM streaming generator."""
        # Simulate thinking
        yield {"type": "thinking", "content": "Processing..."}
        await asyncio.sleep(0.1)
        
        # Simulate token generation
        response = "This is a simulated streaming response from the LLM."
        words = response.split()
        
        for i, word in enumerate(words):
            yield {
                "type": "token",
                "text": word + " ",
                "index": i
            }
            await asyncio.sleep(0.05)  # Simulate token generation delay
        
        # Completion
        yield {
            "type": "done",
            "total_tokens": len(words),
            "text": response
        }
    
    print("\nSimulated streaming output:")
    print("-" * 70)
    
    async for chunk in mock_llm_stream():
        chunk_type = chunk.get("type")
        
        if chunk_type == "thinking":
            print(f"\n[Thinking: {chunk.get('content')}]", end="", flush=True)
        elif chunk_type == "token":
            print(chunk.get("text", ""), end="", flush=True)
        elif chunk_type == "done":
            total = chunk.get("total_tokens", 0)
            print(f"\n\n[Complete: {total} tokens]")


def demo_sse_parsing():
    """Demonstrate parsing SSE messages (client-side)."""
    print("\n" + "=" * 70)
    print("SSE Message Parsing Demo (Client-Side)")
    print("=" * 70)
    
    # Simulate SSE stream
    sse_stream = [
        'data: {"type": "thinking", "content": "Processing..."}\n\n',
        'data: {"type": "token", "text": "Hello", "index": 0}\n\n',
        'data: {"type": "token", "text": " world", "index": 1}\n\n',
        'data: {"type": "done", "total_tokens": 2}\n\n',
    ]
    
    print("\nParsing SSE stream:")
    for line in sse_stream:
        if line.startswith("data: "):
            json_str = line[6:].strip()
            data = json.loads(json_str)
            
            msg_type = data.get("type")
            if msg_type == "thinking":
                print(f"[Thinking] {data.get('content')}")
            elif msg_type == "token":
                print(f"[Token {data.get('index')}] {data.get('text')!r}")
            elif msg_type == "done":
                print(f"[Done] Total tokens: {data.get('total_tokens')}")


async def demo_error_handling():
    """Demonstrate error handling in streaming."""
    print("\n" + "=" * 70)
    print("Error Handling Demo")
    print("=" * 70)
    
    async def faulty_stream():
        """Simulate a stream that fails mid-way."""
        yield {"type": "token", "text": "Starting..."}
        await asyncio.sleep(0.1)
        
        yield {"type": "token", "text": " processing..."}
        await asyncio.sleep(0.1)
        
        # Simulate error
        yield {
            "type": "error",
            "message": "Simulated connection error",
            "code": "connection_error"
        }
    
    print("\nSimulated error scenario:")
    async for chunk in faulty_stream():
        chunk_type = chunk.get("type")
        
        if chunk_type == "token":
            print(chunk.get("text", ""), end="", flush=True)
        elif chunk_type == "error":
            print(f"\n\n❌ Error: {chunk.get('message')} (code: {chunk.get('code')})")
            break


def demo_performance():
    """Demonstrate performance characteristics."""
    import time
    
    print("\n" + "=" * 70)
    print("Performance Characteristics Demo")
    print("=" * 70)
    
    # Test formatting speed
    print("\nFormatting 10,000 messages:")
    start = time.perf_counter()
    for i in range(10000):
        format_sse_message({"type": "token", "text": f"Token {i}"})
    elapsed = time.perf_counter() - start
    
    print(f"  Time: {elapsed:.3f}s")
    print(f"  Rate: {10000/elapsed:.0f} messages/sec")
    
    # Message sizes
    print("\nMessage sizes:")
    msgs = {
        "Thinking": create_thinking_message("Processing..."),
        "Token": create_token_message("hello", 0),
        "Done": create_done_message(100),
        "Error": create_error_message("Test error", "test"),
    }
    
    for name, msg in msgs.items():
        print(f"  {name}: {len(msg)} bytes")


async def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("QuantumDev Streaming Response Infrastructure Demo")
    print("=" * 70)
    
    # 1. SSE Formatting
    demo_sse_formatting()
    
    # 2. Async streaming
    await demo_async_streaming()
    
    # 3. SSE Parsing
    demo_sse_parsing()
    
    # 4. Error handling
    await demo_error_handling()
    
    # 5. Performance
    demo_performance()
    
    print("\n" + "=" * 70)
    print("✅ Demo Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Start the FastAPI server: uvicorn backend.quantum_api:app --reload")
    print("2. Test streaming endpoint: POST http://localhost:8000/chat/stream")
    print("3. Use curl or a web client to see SSE in action")
    print("\nExample curl command:")
    print('  curl -X POST http://localhost:8000/chat/stream \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"text": "Hello", "source": "test", "source_id": "demo"}\'')
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
