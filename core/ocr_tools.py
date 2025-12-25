#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/ocr_tools.py — OCR (Optical Character Recognition) Tools for QuantumDev

Features:
- OCR on images (screenshots, photos, documents)
- Graceful failure when dependencies are missing
- Environment-based configuration
- Safe error handling

Author: QuantumDev (BLOCK 5)
Version: 1.0.0
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any, Optional
from io import BytesIO

log = logging.getLogger(__name__)

# === Configuration ===
TOOLS_OCR_ENABLED = os.getenv("TOOLS_OCR_ENABLED", "0") == "1"
OCR_MAX_IMAGE_SIZE_MB = int(os.getenv("OCR_MAX_IMAGE_SIZE_MB", "10"))
OCR_DEFAULT_LANG = os.getenv("OCR_DEFAULT_LANG", "eng+ita")

# === Dependency Check ===
OCR_AVAILABLE = False
HAS_PIL = False
HAS_TESSERACT = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    log.warning("PIL (Pillow) not available. OCR will be disabled.")

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    log.warning("pytesseract not available. OCR will be disabled.")

# Only mark OCR as available if both dependencies are present
if HAS_PIL and HAS_TESSERACT:
    try:
        # Test if tesseract binary is actually available
        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
        log.info("OCR system initialized successfully")
    except Exception as e:
        log.warning(f"Tesseract binary not found or not working: {e}")
        OCR_AVAILABLE = False


def is_ocr_enabled() -> bool:
    """
    Check if OCR is enabled via environment variable.
    
    Returns:
        True if OCR is enabled, False otherwise
    """
    return TOOLS_OCR_ENABLED


def run_ocr_on_image_bytes(
    data: bytes,
    lang: str = OCR_DEFAULT_LANG,
    max_size_mb: Optional[int] = None
) -> Dict[str, Any]:
    """
    Run OCR on image bytes.
    
    Args:
        data: Image data as bytes
        lang: Language(s) for OCR (e.g., 'eng', 'ita', 'eng+ita')
        max_size_mb: Maximum allowed image size in MB (overrides env default)
        
    Returns:
        Dictionary with:
        - ok: bool - Success status
        - text: str - Extracted text (empty if failed)
        - error: str | None - Error message if failed
        - lang_used: str - Language used for OCR
    """
    # Check if OCR is enabled
    if not is_ocr_enabled():
        return {
            "ok": False,
            "text": "",
            "error": "ocr_disabled",
            "lang_used": lang,
        }
    
    # Check if dependencies are available
    if not OCR_AVAILABLE:
        return {
            "ok": False,
            "text": "",
            "error": "ocr_dependency_missing",
            "lang_used": lang,
        }
    
    # Check file size
    max_bytes = (max_size_mb or OCR_MAX_IMAGE_SIZE_MB) * 1024 * 1024
    if len(data) > max_bytes:
        return {
            "ok": False,
            "text": "",
            "error": "image_too_large",
            "lang_used": lang,
        }
    
    try:
        # Load image from bytes
        image = Image.open(BytesIO(data))
        
        # Run OCR
        text = pytesseract.image_to_string(image, lang=lang)
        
        # Normalize whitespace
        text = text.strip()
        
        return {
            "ok": True,
            "text": text,
            "error": None,
            "lang_used": lang,
        }
        
    except Exception as e:
        log.error(f"OCR failed: {e}")
        return {
            "ok": False,
            "text": "",
            "error": str(e),
            "lang_used": lang,
        }


def get_ocr_info() -> Dict[str, Any]:
    """
    Get information about OCR system status.
    
    Returns:
        Dictionary with OCR system information
    """
    info = {
        "enabled": is_ocr_enabled(),
        "available": OCR_AVAILABLE,
        "dependencies": {
            "pillow": HAS_PIL,
            "pytesseract": HAS_TESSERACT,
        },
        "config": {
            "max_image_size_mb": OCR_MAX_IMAGE_SIZE_MB,
            "default_lang": OCR_DEFAULT_LANG,
        },
    }
    
    # Try to get tesseract version if available
    if OCR_AVAILABLE:
        try:
            version = pytesseract.get_tesseract_version()
            info["tesseract_version"] = str(version)
        except Exception:
            pass
    
    return info


# === Test ===
if __name__ == "__main__":
    print("🔍 OCR Tools Module - Test Suite\n")
    print("=" * 70)
    
    # Print OCR info
    info = get_ocr_info()
    print("OCR System Information:")
    print(f"  Enabled: {info['enabled']}")
    print(f"  Available: {info['available']}")
    print(f"  PIL/Pillow: {info['dependencies']['pillow']}")
    print(f"  pytesseract: {info['dependencies']['pytesseract']}")
    print(f"  Max Image Size: {info['config']['max_image_size_mb']} MB")
    print(f"  Default Language: {info['config']['default_lang']}")
    
    if info.get("tesseract_version"):
        print(f"  Tesseract Version: {info['tesseract_version']}")
    
    print("\n" + "=" * 70)
    
    if OCR_AVAILABLE:
        print("✅ OCR Tools Module - Ready")
    else:
        print("⚠️  OCR Tools Module - Dependencies Missing")
        print("   Install: pip install pytesseract pillow")
        print("   System: apt-get install tesseract-ocr")
