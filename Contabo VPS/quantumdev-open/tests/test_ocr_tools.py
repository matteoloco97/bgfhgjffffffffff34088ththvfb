#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_ocr_tools.py — Tests for OCR functionality (BLOCK 5)

This test suite validates:
1. OCR configuration and availability
2. OCR operations with disabled state
3. OCR error handling
"""

from __future__ import annotations

import sys
import os

# Ensure project root is in path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import OCR tools
from core.ocr_tools import (
    is_ocr_enabled,
    run_ocr_on_image_bytes,
    get_ocr_info,
    OCR_AVAILABLE,
    HAS_PIL,
    HAS_TESSERACT,
)


def test_ocr_info():
    """Test OCR info retrieval."""
    print("\n" + "=" * 70)
    print("TEST 1: OCR Info")
    print("=" * 70)
    
    info = get_ocr_info()
    
    print(f"  Enabled: {info['enabled']}")
    print(f"  Available: {info['available']}")
    print(f"  Dependencies:")
    print(f"    - PIL/Pillow: {info['dependencies']['pillow']}")
    print(f"    - pytesseract: {info['dependencies']['pytesseract']}")
    print(f"  Config:")
    print(f"    - Max Image Size: {info['config']['max_image_size_mb']} MB")
    print(f"    - Default Language: {info['config']['default_lang']}")
    
    if info.get("tesseract_version"):
        print(f"    - Tesseract Version: {info['tesseract_version']}")
    
    assert "enabled" in info
    assert "available" in info
    assert "dependencies" in info
    assert "config" in info
    
    print("✅ PASSED: OCR info structure is correct")
    return True


def test_ocr_disabled_behavior():
    """Test OCR behavior when disabled."""
    print("\n" + "=" * 70)
    print("TEST 2: OCR Disabled Behavior")
    print("=" * 70)
    
    # Create dummy image bytes
    dummy_image = b"fake_image_data"
    
    # If OCR is enabled, we'll need to mock it being disabled
    # For now, just test the function call
    result = run_ocr_on_image_bytes(dummy_image)
    
    print(f"  Result: {result}")
    
    assert "ok" in result
    assert "text" in result
    assert "error" in result
    assert "lang_used" in result
    
    # If OCR is not enabled or available, it should return ok=False
    if not is_ocr_enabled():
        assert result["ok"] is False
        assert result["error"] == "ocr_disabled"
        print("✅ PASSED: OCR correctly returns disabled status")
    elif not OCR_AVAILABLE:
        assert result["ok"] is False
        assert result["error"] == "ocr_dependency_missing"
        print("✅ PASSED: OCR correctly returns dependency missing status")
    else:
        # OCR is enabled and available, might fail with invalid data
        print("⚠️  OCR is enabled and available - cannot test disabled behavior")
    
    return True


def test_ocr_size_limits():
    """Test OCR size limit enforcement."""
    print("\n" + "=" * 70)
    print("TEST 3: OCR Size Limits")
    print("=" * 70)
    
    # Create large dummy data (11 MB, over default 10 MB limit)
    large_data = b"x" * (11 * 1024 * 1024)
    
    result = run_ocr_on_image_bytes(large_data)
    
    print(f"  Result for 11 MB data: {result}")
    
    if is_ocr_enabled() and OCR_AVAILABLE:
        assert result["ok"] is False
        assert result["error"] == "image_too_large"
        print("✅ PASSED: OCR correctly rejects oversized images")
    else:
        print("⚠️  OCR not enabled/available - size limit not tested")
    
    return True


def test_ocr_dependency_check():
    """Test OCR dependency availability check."""
    print("\n" + "=" * 70)
    print("TEST 4: OCR Dependencies")
    print("=" * 70)
    
    print(f"  PIL/Pillow available: {HAS_PIL}")
    print(f"  pytesseract available: {HAS_TESSERACT}")
    print(f"  OCR available: {OCR_AVAILABLE}")
    
    # OCR should only be available if both dependencies are present
    if HAS_PIL and HAS_TESSERACT:
        print("  Note: Both dependencies present, OCR might be available")
    else:
        assert not OCR_AVAILABLE
        print("✅ PASSED: OCR correctly unavailable when dependencies missing")
    
    return True


def run_all_tests():
    """Run all OCR tests."""
    print("\n" + "=" * 70)
    print("OCR TOOLS TEST SUITE")
    print("=" * 70)
    
    tests = [
        ("OCR Info", test_ocr_info),
        ("OCR Disabled Behavior", test_ocr_disabled_behavior),
        ("OCR Size Limits", test_ocr_size_limits),
        ("OCR Dependencies", test_ocr_dependency_check),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {name} - {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {name} - {e}")
            failed += 1
    
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"  Total: {len(tests)}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    
    if failed == 0:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
