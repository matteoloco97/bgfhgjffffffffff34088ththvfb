#!/usr/bin/env python3
"""
Unit tests for multi-level cache integration.

Tests the cache functionality without requiring a running server.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_cache_import():
    """Test that multi-level cache can be imported."""
    print("Test 1: Testing cache import...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        print("  ✅ Successfully imported get_multi_level_cache")
        return True
    except Exception as e:
        print(f"  ❌ Failed to import: {e}")
        return False


def test_cache_initialization():
    """Test that cache can be initialized."""
    print("\nTest 2: Testing cache initialization...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        cache = get_multi_level_cache()
        print(f"  ✅ Cache initialized successfully")
        print(f"     L1 enabled: {cache.l1_enabled}")
        print(f"     L2 enabled: {cache.l2_enabled}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to initialize: {e}")
        return False


def test_cache_get_set():
    """Test cache get/set operations."""
    print("\nTest 3: Testing cache get/set operations...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        cache = get_multi_level_cache()
        
        # Test key
        test_key = "test:user1:hello world"
        test_value = "This is a test response"
        
        # Should return None for non-existent key
        result = cache.get(test_key)
        if result is None:
            print("  ✅ Cache miss for non-existent key")
        else:
            print(f"  ❌ Expected None, got: {result}")
            return False
        
        # Set value
        cache.set(test_key, test_value)
        print("  ✅ Value set in cache")
        
        # Should return value
        result = cache.get(test_key)
        if result == test_value:
            print("  ✅ Cache hit returns correct value")
        else:
            print(f"  ❌ Expected '{test_value}', got: '{result}'")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Cache get/set failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_key_isolation():
    """Test that different cache keys are isolated."""
    print("\nTest 4: Testing cache key isolation...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        cache = get_multi_level_cache()
        
        # Set values for different users
        cache.set("test:user1:hello", "Response for user 1")
        cache.set("test:user2:hello", "Response for user 2")
        
        # Verify isolation
        result1 = cache.get("test:user1:hello")
        result2 = cache.get("test:user2:hello")
        
        if result1 == "Response for user 1":
            print("  ✅ User 1 cache correct")
        else:
            print(f"  ❌ User 1 cache incorrect: {result1}")
            return False
        
        if result2 == "Response for user 2":
            print("  ✅ User 2 cache correct")
        else:
            print(f"  ❌ User 2 cache incorrect: {result2}")
            return False
        
        print("  ✅ Cache keys are properly isolated")
        return True
    except Exception as e:
        print(f"  ❌ Key isolation test failed: {e}")
        return False


def test_cache_stats():
    """Test cache statistics."""
    print("\nTest 5: Testing cache statistics...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        cache = get_multi_level_cache()
        
        # Reset stats for clean test
        cache.reset_stats()
        
        # Perform operations
        cache.get("test:stats:key1")  # Miss
        cache.set("test:stats:key1", "value1")
        cache.get("test:stats:key1")  # Hit
        cache.get("test:stats:key2")  # Miss
        
        stats = cache.get_stats()
        
        print(f"  Total requests: {stats.get('total_requests')}")
        print(f"  L1 hits: {stats.get('l1_hits')}")
        print(f"  L1 misses: {stats.get('l1_misses')}")
        print(f"  L1 size: {stats.get('l1_size')}")
        print(f"  Hit rate: {stats.get('hit_rate', 0):.2%}")
        
        # Verify stats make sense
        if stats['total_requests'] >= 3:  # At least 3 get operations
            print("  ✅ Total requests tracked")
        else:
            print(f"  ⚠️  Expected at least 3 requests, got {stats['total_requests']}")
        
        if stats['l1_hits'] >= 1:
            print("  ✅ Cache hits recorded")
        else:
            print(f"  ⚠️  Expected at least 1 hit, got {stats['l1_hits']}")
        
        return True
    except Exception as e:
        print(f"  ❌ Stats test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_cache_clear():
    """Test cache clearing."""
    print("\nTest 6: Testing cache clearing...")
    try:
        from core.multi_level_cache import get_multi_level_cache
        cache = get_multi_level_cache()
        
        # Add some items
        cache.set("test:clear:key1", "value1")
        cache.set("test:clear:key2", "value2")
        cache.set("test:clear:key3", "value3")
        
        # Check size before
        stats_before = cache.get_stats()
        size_before = stats_before['l1_size']
        print(f"  L1 size before clear: {size_before}")
        
        # Clear L1
        cleared = cache.clear_l1()
        print(f"  Cleared {cleared} items")
        
        # Check size after
        stats_after = cache.get_stats()
        size_after = stats_after['l1_size']
        print(f"  L1 size after clear: {size_after}")
        
        if size_after == 0:
            print("  ✅ Cache cleared successfully")
            return True
        else:
            print(f"  ❌ Cache not empty after clear: {size_after} items remain")
            return False
    except Exception as e:
        print(f"  ❌ Clear test failed: {e}")
        return False


def test_quantum_api_integration():
    """Test that quantum_api.py has the cache integrated."""
    print("\nTest 7: Testing quantum_api.py integration...")
    try:
        # Import the module
        from backend import quantum_api
        
        # Check that ml_cache is defined
        if hasattr(quantum_api, 'ml_cache'):
            print("  ✅ ml_cache variable exists in quantum_api")
        else:
            print("  ❌ ml_cache variable not found in quantum_api")
            return False
        
        # Check that it's initialized
        if quantum_api.ml_cache is not None:
            print("  ✅ ml_cache is initialized")
        else:
            print("  ❌ ml_cache is None")
            return False
        
        # Verify it has the expected methods
        required_methods = ['get', 'set', 'get_stats', 'clear_l1']
        missing_methods = [m for m in required_methods if not hasattr(quantum_api.ml_cache, m)]
        
        if not missing_methods:
            print(f"  ✅ All required methods present: {required_methods}")
        else:
            print(f"  ❌ Missing methods: {missing_methods}")
            return False
        
        return True
    except Exception as e:
        print(f"  ❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("🧪 MULTI-LEVEL CACHE UNIT TESTS")
    print("=" * 70)
    
    tests = [
        test_cache_import,
        test_cache_initialization,
        test_cache_get_set,
        test_cache_key_isolation,
        test_cache_stats,
        test_cache_clear,
        test_quantum_api_integration,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback
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
    exit(main())
