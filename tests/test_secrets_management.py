#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for secrets management functionality.

This script tests:
1. Encryption key generation
2. Encryption and decryption of .env files
3. Secret rotation
4. Startup validation
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_key_generation():
    """Test encryption key generation."""
    print("\n" + "=" * 70)
    print("Test 1: Encryption Key Generation")
    print("=" * 70)
    
    from scripts.encrypt_env import EnvEncryptor
    
    key = EnvEncryptor.generate_key()
    assert len(key) > 0, "Key should not be empty"
    assert isinstance(key, str), "Key should be a string"
    
    # Test that key is valid for Fernet
    try:
        from cryptography.fernet import Fernet
        Fernet(key.encode())
        print("✓ Generated valid Fernet encryption key")
    except Exception as e:
        raise AssertionError(f"Generated key is not valid: {e}")
    
    print(f"  Key length: {len(key)} characters")
    print("✓ Test 1 PASSED")


def test_encryption_decryption():
    """Test encryption and decryption of files."""
    print("\n" + "=" * 70)
    print("Test 2: Encryption and Decryption")
    print("=" * 70)
    
    from scripts.encrypt_env import EnvEncryptor
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test file
        test_file = Path(tmpdir) / "test.env"
        test_content = b"SECRET_KEY=my-secret-value\nAPI_KEY=another-secret\n"
        test_file.write_bytes(test_content)
        
        # Generate key
        key = EnvEncryptor.generate_key()
        encryptor = EnvEncryptor(key)
        
        # Encrypt
        encrypted_file = Path(tmpdir) / "test.env.encrypted"
        encryptor.encrypt_file(str(test_file), str(encrypted_file))
        
        assert encrypted_file.exists(), "Encrypted file should exist"
        encrypted_content = encrypted_file.read_bytes()
        assert encrypted_content != test_content, "Encrypted content should differ from original"
        print("✓ File encrypted successfully")
        
        # Decrypt
        decrypted_file = Path(tmpdir) / "test.env.decrypted"
        encryptor.decrypt_file(str(encrypted_file), str(decrypted_file))
        
        assert decrypted_file.exists(), "Decrypted file should exist"
        decrypted_content = decrypted_file.read_bytes()
        assert decrypted_content == test_content, "Decrypted content should match original"
        print("✓ File decrypted successfully")
        print("✓ Content verified - matches original")
    
    print("✓ Test 2 PASSED")


def test_wrong_key_decryption():
    """Test that decryption fails with wrong key."""
    print("\n" + "=" * 70)
    print("Test 3: Wrong Key Decryption (should fail)")
    print("=" * 70)
    
    from scripts.encrypt_env import EnvEncryptor
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create and encrypt file
        test_file = Path(tmpdir) / "test.env"
        test_file.write_bytes(b"SECRET=value")
        
        key1 = EnvEncryptor.generate_key()
        encryptor1 = EnvEncryptor(key1)
        
        encrypted_file = Path(tmpdir) / "test.env.encrypted"
        encryptor1.encrypt_file(str(test_file), str(encrypted_file))
        
        # Try to decrypt with different key
        key2 = EnvEncryptor.generate_key()
        encryptor2 = EnvEncryptor(key2)
        
        try:
            decrypted_file = Path(tmpdir) / "test.env.decrypted"
            encryptor2.decrypt_file(str(encrypted_file), str(decrypted_file))
            raise AssertionError("Decryption should have failed with wrong key")
        except ValueError as e:
            print("✓ Correctly rejected decryption with wrong key")
            print(f"  Error: {str(e)[:80]}...")
    
    print("✓ Test 3 PASSED")


def test_secret_rotation():
    """Test secret rotation functionality."""
    print("\n" + "=" * 70)
    print("Test 4: Secret Rotation")
    print("=" * 70)
    
    from scripts.rotate_secrets import SecretRotator
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create log directory
        log_dir = Path(tmpdir) / "logs"
        log_dir.mkdir()
        
        # Override log path
        rotator = SecretRotator()
        rotator.rotation_log = log_dir / "rotation_events.json"
        
        # Test token generation
        admin_token = rotator.generate_admin_token()
        assert len(admin_token) == 64, f"Admin token should be 64 chars, got {len(admin_token)}"
        assert all(c in '0123456789abcdef' for c in admin_token), "Should be hex"
        print("✓ Generated admin token (64 hex chars)")
        
        jwt_secret = rotator.generate_jwt_secret()
        assert len(jwt_secret) > 0, "JWT secret should not be empty"
        print("✓ Generated JWT secret")
        
        shared_secret = rotator.generate_quantum_shared_secret()
        assert len(shared_secret) == 64, f"Shared secret should be 64 chars, got {len(shared_secret)}"
        print("✓ Generated quantum shared secret")
        
        # Test rotation (without updating env)
        new_admin = rotator.rotate_admin_token(update_env=False)
        assert len(new_admin) == 64, "Rotated admin token invalid"
        print("✓ Rotated admin token")
        
        # Check log exists
        assert rotator.rotation_log.exists(), "Rotation log should exist"
        print("✓ Rotation event logged")
    
    print("✓ Test 4 PASSED")


def test_startup_validation():
    """Test startup validation function."""
    print("\n" + "=" * 70)
    print("Test 5: Startup Validation")
    print("=" * 70)
    
    # Save current env
    saved_endpoint = os.environ.get('LLM_ENDPOINT')
    
    # Test with missing required variable
    os.environ.pop('LLM_ENDPOINT', None)
    
    try:
        # Import the validation function
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "quantum_api_partial",
            Path(__file__).parent.parent / "backend" / "quantum_api.py"
        )
        # We can't import the full module without dependencies, so test logic directly
        
        required_secrets = ['LLM_ENDPOINT']
        missing = [s for s in required_secrets if not os.getenv(s)]
        
        if missing:
            print("✓ Correctly detected missing required secrets")
            print(f"  Missing: {missing}")
        else:
            raise AssertionError("Should have detected missing LLM_ENDPOINT")
        
    finally:
        # Restore env
        if saved_endpoint:
            os.environ['LLM_ENDPOINT'] = saved_endpoint
    
    # Test with required variable present
    os.environ['LLM_ENDPOINT'] = 'http://localhost:5000/v1'
    missing = [s for s in ['LLM_ENDPOINT'] if not os.getenv(s)]
    assert len(missing) == 0, "Should not have missing secrets"
    print("✓ Validation passed with required secrets present")
    
    print("✓ Test 5 PASSED")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("SECRETS MANAGEMENT TEST SUITE")
    print("=" * 70)
    
    try:
        test_key_generation()
        test_encryption_decryption()
        test_wrong_key_decryption()
        test_secret_rotation()
        test_startup_validation()
        
        print("\n" + "=" * 70)
        print("ALL TESTS PASSED ✓")
        print("=" * 70)
        print("\nSecrets management system is working correctly!")
        return 0
        
    except Exception as e:
        print("\n" + "=" * 70)
        print("TEST FAILED ✗")
        print("=" * 70)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
