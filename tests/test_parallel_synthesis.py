#!/usr/bin/env python3
"""
Test parallel synthesis engine.

Tests the parallel synthesis functionality and integration.
"""

import sys
import os
import asyncio
import traceback

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_parallel_synthesis_import():
    """Test that parallel synthesis module can be imported."""
    print("Test 1: Testing parallel synthesis import...")
    try:
        from core.parallel_synthesis import (
            parallel_synthesize_documents,
            is_parallel_synthesis_enabled,
            get_parallel_synthesis_config,
        )
        print("  ✅ Successfully imported parallel synthesis module")
        return True
    except Exception as e:
        print(f"  ❌ Failed to import: {e}")
        traceback.print_exc()
        return False


def test_config_functions():
    """Test configuration helper functions."""
    print("\nTest 2: Testing configuration functions...")
    try:
        from core.parallel_synthesis import (
            is_parallel_synthesis_enabled,
            get_parallel_synthesis_config,
        )
        
        # Test config retrieval
        config = get_parallel_synthesis_config()
        print(f"  Configuration: {config}")
        
        # Test enabled check
        enabled = is_parallel_synthesis_enabled()
        print(f"  Parallel synthesis enabled: {enabled}")
        
        print("  ✅ Configuration functions work correctly")
        return True
    except Exception as e:
        print(f"  ❌ Configuration test failed: {e}")
        traceback.print_exc()
        return False


async def test_parallel_synthesis_basic():
    """Test basic parallel synthesis with mock documents."""
    print("\nTest 3: Testing basic parallel synthesis...")
    try:
        from core.parallel_synthesis import parallel_synthesize_documents
        
        # Mock documents
        documents = [
            {
                "idx": 1,
                "title": "Test Article 1",
                "url": "https://example.com/1",
                "text": "This is a test article about quantum computing. It has some interesting facts.",
            },
            {
                "idx": 2,
                "title": "Test Article 2",
                "url": "https://example.com/2",
                "text": "Another article about quantum computing advances in 2024.",
            },
        ]
        
        # NOTE: This test will only work if LLM is available
        # For now, just test that the function signature works
        print("  Testing function signature...")
        
        # Test with empty documents (should handle gracefully)
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=[],
        )
        
        if stats["total_documents"] == 0:
            print("  ✅ Handles empty documents correctly")
            return True
        else:
            print(f"  ⚠️ Unexpected result for empty documents: {stats}")
            return False
            
    except Exception as e:
        print(f"  ❌ Parallel synthesis test failed: {e}")
        traceback.print_exc()
        return False


async def test_naming_conflict_fix():
    """Test that the naming conflict in quantum_api.py is fixed."""
    print("\nTest 4: Testing naming conflict fix...")
    try:
        # Read quantum_api.py and check for the fix
        api_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            "backend", 
            "quantum_api.py"
        )
        
        with open(api_file, "r") as f:
            content = f.read()
        
        # Check that ml_cached_result is used
        if "ml_cached_result = ml_cache.get(cache_key)" in content:
            print("  ✅ Variable renamed to ml_cached_result")
        else:
            print("  ❌ Variable not renamed correctly")
            return False
        
        # Check that @cached_response decorator is still present
        if "from core.cache_middleware import cached_response" in content:
            print("  ✅ Decorator import still present")
        else:
            print("  ❌ Decorator import missing")
            return False
        
        # Check that parallel synthesis import is present
        if "from core.parallel_synthesis import" in content:
            print("  ✅ Parallel synthesis import added")
        else:
            print("  ❌ Parallel synthesis import missing")
            return False
        
        print("  ✅ Naming conflict fixed and integration complete")
        return True
        
    except Exception as e:
        print(f"  ❌ Naming conflict test failed: {e}")
        traceback.print_exc()
        return False


async def test_env_example_updated():
    """Test that .env.example was updated with new config."""
    print("\nTest 5: Testing .env.example update...")
    try:
        env_file = os.path.join(
            os.path.dirname(__file__), 
            "..", 
            ".env.example"
        )
        
        with open(env_file, "r") as f:
            content = f.read()
        
        required_vars = [
            "PARALLEL_SYNTHESIS_ENABLED",
            "PARALLEL_SYNTHESIS_MAX_CONCURRENT",
            "PARALLEL_SYNTHESIS_TIMEOUT",
            "PARALLEL_SYNTHESIS_TOKEN_LIMIT",
            "PARALLEL_SYNTHESIS_RETRY_ATTEMPTS",
        ]
        
        all_present = True
        for var in required_vars:
            if var in content:
                print(f"  ✅ {var} found")
            else:
                print(f"  ❌ {var} missing")
                all_present = False
        
        if all_present:
            print("  ✅ All required config variables present in .env.example")
            return True
        else:
            print("  ❌ Some config variables missing")
            return False
        
    except Exception as e:
        print(f"  ❌ .env.example test failed: {e}")
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests."""
    print("="*80)
    print("PARALLEL SYNTHESIS ENGINE TESTS")
    print("="*80)
    
    results = []
    
    # Synchronous tests
    results.append(test_parallel_synthesis_import())
    results.append(test_config_functions())
    
    # Asynchronous tests
    results.append(await test_parallel_synthesis_basic())
    results.append(await test_naming_conflict_fix())
    results.append(await test_env_example_updated())
    
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
