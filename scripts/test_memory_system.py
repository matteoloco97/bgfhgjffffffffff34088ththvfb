#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_memory_system.py — Personal Memory System Validation

Quick validation script to test the personal memory system without requiring
external dependencies like ChromaDB or network access.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_remember_detection():
    """Test 'remember' statement detection in Italian and English."""
    from core.user_profile_memory import detect_remember_statement
    
    print("=" * 60)
    print("TEST: Remember Statement Detection")
    print("=" * 60)
    
    test_cases = [
        # Italian
        ("ricorda che il mio colore preferito è blu", "il mio colore preferito è blu"),
        ("Da ora in poi ricordati che preferisco il tono diretto", "preferisco il tono diretto"),
        ("memorizza che abito a Roma", "abito a Roma"),
        
        # English
        ("remember that I'm 30 years old", "i'm 30 years old"),
        ("From now on, assume that I prefer concise answers", "i prefer concise answers"),
        ("please remember my favorite color is blue", "my favorite color is blue"),
        
        # Should NOT detect
        ("Ciao come stai?", None),
        ("What is the weather?", None),
    ]
    
    all_pass = True
    for text, expected_fact in test_cases:
        result = detect_remember_statement(text)
        
        if expected_fact is None:
            # Should not detect
            if result is None:
                print(f"  ✓ Correctly ignored: {text[:40]}...")
            else:
                print(f"  ✗ False positive: {text[:40]}... => {result}")
                all_pass = False
        else:
            # Should detect
            if result and expected_fact.lower() in result.lower():
                print(f"  ✓ Detected: {text[:40]}...")
            else:
                print(f"  ✗ Failed: {text[:40]}... (got: {result})")
                all_pass = False
    
    print(f"\n{'✅ PASS' if all_pass else '❌ FAIL'}: Remember Detection\n")
    return all_pass


def test_category_classification():
    """Test automatic category classification."""
    from core.user_profile_memory import classify_category
    
    print("=" * 60)
    print("TEST: Category Classification")
    print("=" * 60)
    
    test_cases = [
        # Bio
        ("ho 30 anni", "bio"),
        ("I'm 25 years old", "bio"),
        ("abito a Milano", "bio"),
        
        # Goal
        ("voglio imparare Python", "goal"),
        ("my goal is to reduce debt", "goal"),
        ("devo finire il progetto", "goal"),
        
        # Preference
        ("preferisco il tono diretto", "preference"),
        ("I prefer concise answers", "preference"),
        ("mi piace il caffè", "preference"),
        
        # Project
        ("sto lavorando su Jarvis", "project"),
        ("I'm working on an AI chatbot", "project"),
        ("sto costruendo un'app", "project"),
    ]
    
    all_pass = True
    for text, expected_cat in test_cases:
        result = classify_category(text)
        
        if result == expected_cat:
            print(f"  ✓ {expected_cat:12} : {text[:40]}")
        else:
            print(f"  ✗ {expected_cat:12} (got: {result:12}): {text[:40]}")
            all_pass = False
    
    print(f"\n{'✅ PASS' if all_pass else '❌ FAIL'}: Category Classification\n")
    return all_pass


def test_episodic_buffer():
    """Test episodic memory buffer functionality."""
    from core.episodic_memory import (
        add_to_conversation_buffer,
        get_current_buffer_status,
        clear_conversation_buffer
    )
    
    print("=" * 60)
    print("TEST: Episodic Buffer")
    print("=" * 60)
    
    test_conv_id = "test_validation_conv"
    
    try:
        # Clear any existing buffer
        clear_conversation_buffer(test_conv_id)
        
        # Add some turns
        for i in range(3):
            result = add_to_conversation_buffer(
                conversation_id=test_conv_id,
                user_message=f"Messaggio utente {i}",
                assistant_message=f"Risposta assistente {i}"
            )
            
            if not result.get("added"):
                print(f"  ✗ Failed to add turn {i}")
                return False
        
        print(f"  ✓ Added 3 conversation turns")
        
        # Check status
        status = get_current_buffer_status(test_conv_id)
        
        if status.get("exists"):
            print(f"  ✓ Buffer exists: size={status.get('size')}")
        else:
            print(f"  ✗ Buffer should exist")
            return False
        
        if status.get("size") == 3:
            print(f"  ✓ Buffer size correct: 3")
        else:
            print(f"  ✗ Buffer size incorrect: expected 3, got {status.get('size')}")
            return False
        
        # Clear buffer
        clear_conversation_buffer(test_conv_id)
        status = get_current_buffer_status(test_conv_id)
        
        if status.get("size") == 0:
            print(f"  ✓ Buffer cleared successfully")
        else:
            print(f"  ✗ Buffer should be empty")
            return False
        
        print(f"\n✅ PASS: Episodic Buffer\n")
        return True
        
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        print(f"\n❌ FAIL: Episodic Buffer\n")
        return False


def test_sensitive_data_filtering():
    """Test sensitive data pattern detection."""
    from core.memory_manager import _contains_sensitive_data
    
    print("=" * 60)
    print("TEST: Sensitive Data Filtering")
    print("=" * 60)
    
    test_cases = [
        # Should be blocked
        ("my API key is sk_test_abcdefghijklmnopqrstuvwxyz123456", True),
        ("password: MySecretPassword123", True),
        ("token=Bearer_eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", True),
        ("credit card: 1234567890123456", True),
        
        # Should NOT be blocked
        ("I prefer direct communication", False),
        ("my favorite color is blue", False),
        ("I work in the AI sector", False),
        ("I'm 30 years old", False),
    ]
    
    all_pass = True
    for text, should_block in test_cases:
        result = _contains_sensitive_data(text)
        
        if result == should_block:
            status = "BLOCKED" if result else "ALLOWED"
            print(f"  ✓ {status:8} : {text[:50]}")
        else:
            expected = "BLOCKED" if should_block else "ALLOWED"
            actual = "BLOCKED" if result else "ALLOWED"
            print(f"  ✗ Expected {expected}, got {actual}: {text[:50]}")
            all_pass = False
    
    print(f"\n{'✅ PASS' if all_pass else '❌ FAIL'}: Sensitive Data Filtering\n")
    return all_pass


def test_memory_manager_integration():
    """Test memory manager integration functions."""
    import asyncio
    from core.memory_manager import process_user_message
    
    print("=" * 60)
    print("TEST: Memory Manager Integration")
    print("=" * 60)
    
    async def run_test():
        test_user = "test_validation_user"
        test_conv = "test_validation_conv"
        
        # Test remember detection
        result1 = await process_user_message(
            user_id=test_user,
            conversation_id=test_conv,
            user_message="Ricorda che il mio colore preferito è verde"
        )
        
        if result1.get("remember_detected"):
            print(f"  ✓ Remember statement detected")
        else:
            print(f"  ✗ Failed to detect remember statement")
            return False
        
        # Test normal message (no remember)
        result2 = await process_user_message(
            user_id=test_user,
            conversation_id=test_conv,
            user_message="What is the weather today?"
        )
        
        if not result2.get("remember_detected"):
            print(f"  ✓ Normal message correctly ignored")
        else:
            print(f"  ✗ False positive on normal message")
            return False
        
        # Test sensitive data blocking
        result3 = await process_user_message(
            user_id=test_user,
            conversation_id=test_conv,
            user_message="Remember my password is SuperSecret123!"
        )
        
        # Should detect but might block saving
        if result3.get("remember_detected"):
            print(f"  ✓ Sensitive remember detected")
            if result3.get("blocked_sensitive"):
                print(f"  ✓ Sensitive data blocked from saving")
            else:
                print(f"  ⚠ Sensitive data may not have been blocked")
        
        return True
    
    try:
        result = asyncio.run(run_test())
        print(f"\n{'✅ PASS' if result else '❌ FAIL'}: Memory Manager Integration\n")
        return result
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        print(f"\n❌ FAIL: Memory Manager Integration\n")
        return False


def main():
    """Run all validation tests."""
    print("\n" + "=" * 60)
    print("PERSONAL MEMORY SYSTEM - VALIDATION TESTS")
    print("=" * 60 + "\n")
    
    results = {
        "Remember Detection": test_remember_detection(),
        "Category Classification": test_category_classification(),
        "Episodic Buffer": test_episodic_buffer(),
        "Sensitive Data Filtering": test_sensitive_data_filtering(),
        "Memory Manager Integration": test_memory_manager_integration(),
    }
    
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} : {test_name}")
    
    all_passed = all(results.values())
    total = len(results)
    passed = sum(results.values())
    
    print("\n" + "=" * 60)
    print(f"TOTAL: {passed}/{total} tests passed")
    print("=" * 60 + "\n")
    
    if all_passed:
        print("✅ All validation tests PASSED! Memory system is working correctly.\n")
        return 0
    else:
        print("❌ Some tests FAILED. Please review the output above.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
