#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/encrypt_env.py - Secure Environment Variable Encryption

This script provides utilities to encrypt and decrypt .env files using Fernet
symmetric encryption (based on AES-128-CBC).

Usage:
    # Generate a new encryption key
    python scripts/encrypt_env.py --generate-key

    # Encrypt .env to .env.encrypted
    python scripts/encrypt_env.py --encrypt

    # Decrypt .env.encrypted to .env
    python scripts/encrypt_env.py --decrypt

    # Encrypt with custom paths
    python scripts/encrypt_env.py --encrypt --input .env --output .env.encrypted

Security Notes:
    - Store ENCRYPTION_KEY in a secure location (environment variable, secrets manager)
    - Never commit ENCRYPTION_KEY to version control
    - Rotate encryption keys periodically
    - Use different keys for different environments (dev, staging, prod)
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("ERROR: cryptography library not installed")
    print("Install it with: pip install cryptography")
    sys.exit(1)


class EnvEncryptor:
    """Handles encryption and decryption of .env files using Fernet."""

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize the encryptor with an encryption key.

        Args:
            encryption_key: Base64-encoded Fernet key. If None, reads from ENCRYPTION_KEY env var.

        Raises:
            ValueError: If no encryption key is provided or found.
        """
        if encryption_key is None:
            encryption_key = os.getenv("ENCRYPTION_KEY")

        if not encryption_key:
            raise ValueError(
                "No encryption key provided. Set ENCRYPTION_KEY environment variable "
                "or generate a new key with --generate-key"
            )

        try:
            self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key: {e}")

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            Base64-encoded encryption key as string.
        """
        return Fernet.generate_key().decode()

    def encrypt_file(self, input_path: str, output_path: str) -> None:
        """
        Encrypt a file.

        Args:
            input_path: Path to the file to encrypt (e.g., .env)
            output_path: Path to save encrypted file (e.g., .env.encrypted)

        Raises:
            FileNotFoundError: If input file doesn't exist.
            IOError: If file operations fail.
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Read the file
        with open(input_file, "rb") as f:
            data = f.read()

        # Encrypt the data
        encrypted_data = self.cipher.encrypt(data)

        # Write encrypted data
        with open(output_file, "wb") as f:
            f.write(encrypted_data)

        print(f"✓ Encrypted {input_path} -> {output_path}")
        print(f"  Original size: {len(data)} bytes")
        print(f"  Encrypted size: {len(encrypted_data)} bytes")

    def decrypt_file(self, input_path: str, output_path: str) -> None:
        """
        Decrypt a file.

        Args:
            input_path: Path to encrypted file (e.g., .env.encrypted)
            output_path: Path to save decrypted file (e.g., .env)

        Raises:
            FileNotFoundError: If input file doesn't exist.
            InvalidToken: If decryption fails (wrong key or corrupted data).
            IOError: If file operations fail.
        """
        input_file = Path(input_path)
        output_file = Path(output_path)

        if not input_file.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        # Read encrypted data
        with open(input_file, "rb") as f:
            encrypted_data = f.read()

        # Decrypt the data
        try:
            decrypted_data = self.cipher.decrypt(encrypted_data)
        except InvalidToken:
            raise ValueError(
                "Decryption failed. This could be due to:\n"
                "  - Wrong encryption key\n"
                "  - Corrupted encrypted file\n"
                "  - File is not encrypted"
            )

        # Write decrypted data
        with open(output_file, "wb") as f:
            f.write(decrypted_data)

        print(f"✓ Decrypted {input_path} -> {output_path}")
        print(f"  Encrypted size: {len(encrypted_data)} bytes")
        print(f"  Decrypted size: {len(decrypted_data)} bytes")


def main():
    """Main entry point for the encryption script."""
    parser = argparse.ArgumentParser(
        description="Encrypt and decrypt .env files using Fernet encryption",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate a new encryption key
  python scripts/encrypt_env.py --generate-key

  # Encrypt .env file
  export ENCRYPTION_KEY="your-key-here"
  python scripts/encrypt_env.py --encrypt

  # Decrypt .env.encrypted
  export ENCRYPTION_KEY="your-key-here"
  python scripts/encrypt_env.py --decrypt

  # Custom paths
  python scripts/encrypt_env.py --encrypt --input .env.production --output .env.prod.encrypted
        """,
    )

    parser.add_argument(
        "--generate-key",
        action="store_true",
        help="Generate a new encryption key and print it to stdout",
    )
    parser.add_argument(
        "--encrypt",
        action="store_true",
        help="Encrypt the input file",
    )
    parser.add_argument(
        "--decrypt",
        action="store_true",
        help="Decrypt the input file",
    )
    parser.add_argument(
        "--input",
        default=".env",
        help="Input file path (default: .env)",
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: .env.encrypted for encrypt, .env for decrypt)",
    )
    parser.add_argument(
        "--key",
        help="Encryption key (overrides ENCRYPTION_KEY environment variable)",
    )

    args = parser.parse_args()

    # Generate key mode
    if args.generate_key:
        key = EnvEncryptor.generate_key()
        print("Generated encryption key:")
        print(key)
        print("\nStore this key securely!")
        print("Set it as an environment variable:")
        print(f'export ENCRYPTION_KEY="{key}"')
        return

    # Validate arguments
    if not args.encrypt and not args.decrypt:
        parser.error("Must specify either --encrypt or --decrypt (or --generate-key)")

    if args.encrypt and args.decrypt:
        parser.error("Cannot specify both --encrypt and --decrypt")

    # Set default output path
    if args.output is None:
        if args.encrypt:
            args.output = args.input + ".encrypted"
        else:
            args.output = args.input.replace(".encrypted", "")

    try:
        # Initialize encryptor
        encryptor = EnvEncryptor(encryption_key=args.key)

        # Perform operation
        if args.encrypt:
            encryptor.encrypt_file(args.input, args.output)
            print(f"\n⚠️  Remember to add {args.output} to .gitignore")
        else:
            encryptor.decrypt_file(args.input, args.output)
            print(f"\n⚠️  Remember to add {args.output} to .gitignore")

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
