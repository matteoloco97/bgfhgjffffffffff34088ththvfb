#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_optimizations.py — Tests for Phase 1 Performance Optimizations

Tests for:
- Memory retrieval with relevance filtering
- Reasoning traces performance (DummyTracer)
- Italian NLP utilities
- Semantic context pruning
"""

import sys
import os
import time
import asyncio

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_italian_nlp():
    """Test Italian NLP grammar fixes and intent detection."""
    print("\n" + "=" * 70)
    print("TEST 1: Italian NLP Module")
    print("=" * 70)
    
    from core.italian_nlp import (
        fix_italian_grammar,
        detect_italian_intent_keywords,
        italian_aware_summarization,
        normalize_italian_text
    )
    
    # Test grammar fixes
    test_cases = [
        ("qual'è il problema?", "qual è il problema?"),
        ("Voglio un'altro caffè", "Voglio un altro caffè"),
        ("Non ne posso pò", "Non ne posso po'"),
        ("perchè non funziona?", "perché non funziona?"),
    ]
    
    print("\n✓ Grammar Fixes:")
    for original, expected in test_cases:
        fixed = fix_italian_grammar(original)
        status = "✅" if fixed == expected else "❌"
        print(f"  {status} '{original}' → '{fixed}'")
        if fixed != expected:
            print(f"     Expected: '{expected}'")
    
    # Test intent detection
    print("\n✓ Intent Detection:")
    test_query = "Cerca il meteo di oggi a Roma"
    intents = detect_italian_intent_keywords(test_query)
    print(f"  Query: '{test_query}'")
    print(f"  Detected intents: {list(intents.keys())}")
    assert "search" in intents or "weather" in intents, "Should detect search or weather intent"
    
    # Test summarization
    print("\n✓ Summarization:")
    long_text = " ".join(["Questa è una frase di test."] * 20)
    summary = italian_aware_summarization(long_text, max_words=20)
    word_count = len(summary.split())
    print(f"  Original: {len(long_text.split())} words")
    print(f"  Summary: {word_count} words")
    assert word_count <= 25, f"Summary should be <= 25 words, got {word_count}"
    
    print("\n✅ Italian NLP tests passed!")


def test_reasoning_tracer_performance():
    """Test DummyTracer for zero overhead when disabled."""
    print("\n" + "=" * 70)
    print("TEST 2: Reasoning Tracer Performance")
    print("=" * 70)
    
    # Import here to avoid early initialization
    import importlib
    import core.reasoning_traces
    
    # Test with disabled tracer (should get DummyTracer)
    print("\n✓ Testing DummyTracer (disabled):")
    os.environ["ENABLE_REASONING_TRACES"] = "0"
    
    # Force reload to reset module state
    importlib.reload(core.reasoning_traces)
    
    from core.reasoning_traces import get_reasoning_tracer, DummyTracer
    
    tracer = get_reasoning_tracer()
    print(f"  Tracer type: {type(tracer).__name__}")
    assert isinstance(tracer, DummyTracer), "Should return DummyTracer when disabled"
    
    # Measure overhead
    iterations = 10000
    start = time.perf_counter()
    for _ in range(iterations):
        trace = tracer.start_trace("test query")
        step = tracer.add_step(None, "test", "content")
        tracer.complete_step(step)
        tracer.complete_trace()
    
    duration_ms = (time.perf_counter() - start) * 1000
    per_op_us = (duration_ms * 1000) / iterations
    
    print(f"  {iterations} operations: {duration_ms:.2f}ms")
    print(f"  Per-operation: {per_op_us:.2f}µs")
    assert per_op_us < 10, f"DummyTracer overhead should be <10µs, got {per_op_us:.2f}µs"
    
    # Test with enabled tracer
    print("\n✓ Testing ReasoningTracer (enabled):")
    os.environ["ENABLE_REASONING_TRACES"] = "1"
    
    # Force reload to reset module state
    importlib.reload(core.reasoning_traces)
    from core.reasoning_traces import get_reasoning_tracer as get_tracer_enabled
    
    tracer = get_tracer_enabled()
    print(f"  Tracer type: {type(tracer).__name__}")
    assert tracer.__class__.__name__ == "ReasoningTracer", "Should return ReasoningTracer when enabled"
    
    print("\n✅ Reasoning tracer tests passed!")


def test_memory_relevance_filtering():
    """Test memory retrieval with relevance filtering."""
    print("\n" + "=" * 70)
    print("TEST 3: Memory Relevance Filtering")
    print("=" * 70)
    
    from core.user_profile_memory import MEMORY_MIN_RELEVANCE
    
    print("\n✓ Configuration:")
    print(f"  MEMORY_MIN_RELEVANCE: {MEMORY_MIN_RELEVANCE}")
    
    # Test that the parameter exists and has correct default
    assert MEMORY_MIN_RELEVANCE >= 0 and MEMORY_MIN_RELEVANCE <= 1, \
        "MEMORY_MIN_RELEVANCE should be between 0 and 1"
    
    print(f"  Default threshold: {MEMORY_MIN_RELEVANCE} ✓")
    
    # Note: Full integration test would require ChromaDB setup
    # Here we just verify the implementation exists
    from core.user_profile_memory import query_user_profile
    import inspect
    
    sig = inspect.signature(query_user_profile)
    params = list(sig.parameters.keys())
    
    print("\n✓ Function signature:")
    print(f"  Parameters: {params}")
    assert "min_relevance" in params, "query_user_profile should have min_relevance parameter"
    
    print("\n✅ Memory filtering tests passed!")


async def test_semantic_context_pruning():
    """Test semantic context pruning."""
    print("\n" + "=" * 70)
    print("TEST 4: Semantic Context Pruning")
    print("=" * 70)
    
    from core.conversational_memory import (
        ConversationalMemory,
        Message,
        approx_tokens
    )
    
    # Create test messages
    messages = [
        Message(role="user", content="Ciao, come stai?", timestamp=1000),
        Message(role="assistant", content="Bene grazie! Come posso aiutarti?", timestamp=1001),
        Message(role="user", content="Parlami di Python", timestamp=1002),
        Message(role="assistant", content="Python è un linguaggio di programmazione molto popolare", timestamp=1003),
        Message(role="user", content="Che tempo fa oggi?", timestamp=1004),
        Message(role="assistant", content="Non ho accesso ai dati meteo in tempo reale", timestamp=1005),
        Message(role="user", content="Spiegami come funziona Python", timestamp=1006),
        Message(role="assistant", content="Python è interpretato e facile da imparare", timestamp=1007),
    ]
    
    print(f"\n✓ Test setup:")
    print(f"  Total messages: {len(messages)}")
    print(f"  Total tokens: {sum(m.tokens for m in messages)}")
    
    # Test pruning
    memory = ConversationalMemory()
    current_query = "Come posso imparare Python?"
    max_tokens = 100
    
    print(f"\n✓ Pruning with query: '{current_query}'")
    print(f"  Max tokens: {max_tokens}")
    
    pruned = await memory.prune_context_semantically(
        messages=messages,
        current_query=current_query,
        max_tokens=max_tokens
    )
    
    print(f"\n✓ Results:")
    print(f"  Pruned messages: {len(pruned)}")
    print(f"  Pruned tokens: {sum(approx_tokens(m.content) for m in pruned)}")
    
    # Verify constraints
    assert len(pruned) > 0, "Should return at least some messages"
    assert len(pruned) <= len(messages), "Should not add messages"
    
    # Verify first and last messages are preserved (if enough messages)
    if len(messages) > 5:
        assert pruned[0].timestamp == messages[0].timestamp, "Should keep first message"
        assert pruned[-1].timestamp == messages[-1].timestamp, "Should keep last message"
    
    # Verify token limit
    total_tokens = sum(approx_tokens(m.content) for m in pruned)
    # Allow some tolerance for approximation
    assert total_tokens <= max_tokens * 1.2, f"Should respect token limit (got {total_tokens}, max {max_tokens})"
    
    print("\n✅ Semantic pruning tests passed!")


def run_all_tests():
    """Run all optimization tests."""
    print("\n" + "=" * 70)
    print("QUANTUMDEV PHASE 1 OPTIMIZATION TESTS")
    print("=" * 70)
    
    try:
        # Test 1: Italian NLP
        test_italian_nlp()
        
        # Test 2: Reasoning Tracer Performance
        test_reasoning_tracer_performance()
        
        # Test 3: Memory Relevance Filtering
        test_memory_relevance_filtering()
        
        # Test 4: Semantic Context Pruning
        asyncio.run(test_semantic_context_pruning())
        
        print("\n" + "=" * 70)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        return 0
        
    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
