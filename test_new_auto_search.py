#!/usr/bin/env python3
"""
Test script for the new LLM-powered auto_search_detector.

This script demonstrates:
1. New analyze_intent() method
2. Backward-compatible should_trigger_search() method
3. LLM decision-making vs fallback behavior
"""

import sys
import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Add project root to path
sys.path.insert(0, '.')

from core.auto_search_detector import get_auto_search_detector


async def test_new_interface():
    """Test the new analyze_intent() interface."""
    print("\n" + "="*70)
    print("🧪 Testing NEW Interface: analyze_intent()")
    print("="*70)
    
    detector = get_auto_search_detector()
    
    test_queries = [
        ("Prezzo Bitcoin adesso?", "Should detect live price need"),
        ("Che tempo fa a Milano?", "Should detect weather query"),
        ("Ultime notizie crypto", "Should detect news query"),
        ("Come funziona Bitcoin?", "Should NOT trigger search (general knowledge)"),
        ("Ciao!", "Should NOT trigger search (conversational)"),
    ]
    
    for query, expected in test_queries:
        print(f"\n📝 Query: '{query}'")
        print(f"   Expected: {expected}")
        
        result = await detector.analyze_intent(query)
        
        print(f"   ✓ Decision: should_search={result['should_search']}")
        print(f"   ✓ Search Type: {result['search_type']}")
        print(f"   ✓ Reason: {result['reason']}")
        print(f"   ✓ Source: {result['source']} (llm or fallback)")
        print(f"   ✓ Confidence: {result['confidence']:.2f}")
        print(f"   ✓ Optimized Query: '{result['optimized_query']}'")


async def test_backward_compatibility():
    """Test the old should_trigger_search() interface."""
    print("\n" + "="*70)
    print("🔄 Testing BACKWARD COMPATIBILITY: should_trigger_search()")
    print("="*70)
    
    detector = get_auto_search_detector()
    
    test_queries = [
        "Prezzo Ethereum?",
        "Chi ha creato Ethereum?",
    ]
    
    for query in test_queries:
        print(f"\n📝 Query: '{query}'")
        
        result = await detector.should_trigger_search(query, {}, {})
        
        print(f"   ✓ should_search: {result['should_search']}")
        print(f"   ✓ confidence: {result['confidence']:.2f}")
        print(f"   ✓ reason: {result['reason']}")
        print(f"   ✓ search_type: {result['search_type']}")
        print(f"   ✓ suggested_queries: {result['suggested_queries']}")
        print(f"   ✓ source: {result.get('source', 'N/A')}")


async def test_llm_vs_fallback():
    """Show LLM decision vs fallback decision."""
    print("\n" + "="*70)
    print("⚡ LLM vs Fallback Comparison")
    print("="*70)
    print("\nNote: In this test environment, LLM may not be available,")
    print("so you'll likely see 'fallback' as the source.")
    print("When deployed with actual LLM endpoint, it will show 'llm'.")
    print()
    
    detector = get_auto_search_detector()
    
    query = "What's the current price of Bitcoin in USD?"
    result = await detector.analyze_intent(query)
    
    print(f"Query: '{query}'")
    print(f"Source: {result['source']}")
    print(f"Should Search: {result['should_search']}")
    
    if result['source'] == 'llm':
        print("\n✨ LLM is making intelligent decisions!")
        print(f"   Reason: {result['reason']}")
    else:
        print("\n⚠️  Using fallback (LLM unavailable in this environment)")
        print("   This is expected behavior - fallback ensures reliability!")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("🚀 AUTO SEARCH DETECTOR v2.0 - LLM-Powered Test Suite")
    print("="*70)
    
    try:
        await test_new_interface()
        await test_backward_compatibility()
        await test_llm_vs_fallback()
        
        print("\n" + "="*70)
        print("✅ All tests completed successfully!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
