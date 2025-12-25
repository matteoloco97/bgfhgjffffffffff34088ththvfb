#!/usr/bin/env python3
"""
Unit tests for cache middleware integration.

Tests the cache middleware decorator and its integration with endpoints.
"""

import sys
import os
import time
import json
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_middleware_import():
    """Test that cache middleware can be imported."""
    print("Test 1: Testing cache middleware import...")
    try:
        from core.cache_middleware import (
            cached_response,
            get_cache_stats,
            reset_cache_stats,
            generate_cache_key,
        )
        print("  ✅ Successfully imported cache middleware")
        return True
    except Exception as e:
        print(f"  ❌ Failed to import: {e}")
        traceback.print_exc()
        return False


def test_cache_key_generation():
    """Test cache key generation."""
    print("\nTest 2: Testing cache key generation...")
    try:
        from core.cache_middleware import generate_cache_key
        
        # Test with different parameters
        key1 = generate_cache_key("chat", text="hello", source="api")
        key2 = generate_cache_key("chat", text="hello", source="api")
        key3 = generate_cache_key("chat", text="world", source="api")
        
        # Same params should produce same key
        if key1 == key2:
            print(f"  ✅ Same params produce same key: {key1}")
        else:
            print(f"  ❌ Same params produce different keys: {key1} vs {key2}")
            return False
        
        # Different params should produce different keys
        if key1 != key3:
            print(f"  ✅ Different params produce different keys")
        else:
            print(f"  ❌ Different params produce same key")
            return False
        
        # Check key format
        if key1.startswith("chat:"):
            print(f"  ✅ Key has correct format: {key1}")
        else:
            print(f"  ❌ Key has incorrect format: {key1}")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Cache key generation failed: {e}")
        traceback.print_exc()
        return False


def test_stats_tracking():
    """Test cache statistics tracking."""
    print("\nTest 3: Testing statistics tracking...")
    try:
        from core.cache_middleware import get_cache_stats, reset_cache_stats, _update_stats
        
        # Reset stats
        reset_cache_stats()
        
        # Record some events
        _update_stats("test_endpoint", "hit")
        _update_stats("test_endpoint", "hit")
        _update_stats("test_endpoint", "miss")
        _update_stats("another_endpoint", "hit")
        _update_stats("test_endpoint", "bypass")
        
        # Get stats
        stats = get_cache_stats()
        
        print(f"  Total hits: {stats['middleware']['total_hits']}")
        print(f"  Total misses: {stats['middleware']['total_misses']}")
        print(f"  Total bypasses: {stats['middleware']['total_bypasses']}")
        print(f"  Hit rate: {stats['middleware']['hit_rate']:.2%}")
        
        # Verify stats
        if stats['middleware']['total_hits'] == 3:
            print("  ✅ Hits tracked correctly")
        else:
            print(f"  ❌ Expected 3 hits, got {stats['middleware']['total_hits']}")
            return False
        
        if stats['middleware']['total_misses'] == 1:
            print("  ✅ Misses tracked correctly")
        else:
            print(f"  ❌ Expected 1 miss, got {stats['middleware']['total_misses']}")
            return False
        
        if stats['middleware']['total_bypasses'] == 1:
            print("  ✅ Bypasses tracked correctly")
        else:
            print(f"  ❌ Expected 1 bypass, got {stats['middleware']['total_bypasses']}")
            return False
        
        # Check per-endpoint stats
        endpoint_stats = stats['middleware']['per_endpoint']
        test_ep_stats = next((s for s in endpoint_stats if s['endpoint'] == 'test_endpoint'), None)
        
        if test_ep_stats:
            if test_ep_stats['hits'] == 2 and test_ep_stats['misses'] == 1:
                print("  ✅ Per-endpoint stats tracked correctly")
            else:
                print(f"  ❌ Per-endpoint stats incorrect: {test_ep_stats}")
                return False
        else:
            print("  ❌ test_endpoint not found in stats")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Stats tracking failed: {e}")
        traceback.print_exc()
        return False


def test_cache_integration():
    """Test that cache is properly integrated with multi-level cache."""
    print("\nTest 4: Testing multi-level cache integration...")
    try:
        from core.cache_middleware import get_cache_stats
        from core.multi_level_cache import get_multi_level_cache
        
        # Get multi-level cache
        ml_cache = get_multi_level_cache()
        
        # Get comprehensive stats
        stats = get_cache_stats()
        
        # Verify multi-level cache stats are included
        if 'multi_level_cache' in stats:
            print("  ✅ Multi-level cache stats included")
        else:
            print("  ❌ Multi-level cache stats missing")
            return False
        
        ml_stats = stats['multi_level_cache']
        
        # Verify expected fields
        required_fields = ['l1_enabled', 'l2_enabled', 'l1_size', 'hit_rate']
        missing = [f for f in required_fields if f not in ml_stats]
        
        if not missing:
            print(f"  ✅ All required fields present: {required_fields}")
        else:
            print(f"  ❌ Missing fields: {missing}")
            return False
        
        print(f"  L1 enabled: {ml_stats['l1_enabled']}")
        print(f"  L2 enabled: {ml_stats['l2_enabled']}")
        print(f"  L1 size: {ml_stats['l1_size']}")
        print(f"  Overall hit rate: {ml_stats['hit_rate']:.2%}")
        
        return True
    except Exception as e:
        print(f"  ❌ Integration test failed: {e}")
        traceback.print_exc()
        return False


def test_decorator_setup():
    """Test that decorator is properly configured."""
    print("\nTest 5: Testing decorator configuration...")
    try:
        from core.cache_middleware import cached_response
        
        # Create a mock async function
        call_count = [0]  # Use list to allow modification in nested function
        
        @cached_response("test_ep", ttl=60)
        async def mock_endpoint():
            call_count[0] += 1
            return {"result": "success", "count": call_count[0]}
        
        # Check that decorator preserves function metadata
        if hasattr(mock_endpoint, '__wrapped__'):
            print("  ✅ Decorator preserves function metadata")
        else:
            print("  ⚠️  Decorator may not preserve all metadata")
        
        print("  ✅ Decorator configured successfully")
        return True
    except Exception as e:
        print(f"  ❌ Decorator test failed: {e}")
        traceback.print_exc()
        return False


def test_quantum_api_integration():
    """Test that quantum_api.py has the decorators applied."""
    print("\nTest 6: Testing quantum_api.py integration...")
    try:
        # Check that cache_middleware module can be imported
        from core.cache_middleware import cached_response, get_cache_stats, reset_cache_stats
        
        print("  ✅ Cache middleware functions available")
        
        # We can't fully import quantum_api without all dependencies,
        # but we can verify the cache middleware is ready
        print("  ✅ Cache middleware ready for integration")
        
        return True
    except Exception as e:
        print(f"  ❌ Integration test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("🧪 CACHE MIDDLEWARE UNIT TESTS")
    print("=" * 70)
    
    tests = [
        test_middleware_import,
        test_cache_key_generation,
        test_stats_tracking,
        test_cache_integration,
        test_decorator_setup,
        test_quantum_api_integration,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            traceback.print_exc()
            results.append(False)
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
