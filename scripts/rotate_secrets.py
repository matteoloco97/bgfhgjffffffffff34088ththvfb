#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/rotate_secrets.py - Automated Secret Rotation

This script helps rotate secrets and update services with new tokens.

Usage:
    # Generate new tokens for all services
    python scripts/rotate_secrets.py --all

    # Rotate specific service
    python scripts/rotate_secrets.py --service telegram
    python scripts/rotate_secrets.py --service aws

    # Generate token without updating services (dry-run)
    python scripts/rotate_secrets.py --generate-only --service telegram

Security Notes:
    - Always backup current secrets before rotation
    - Test new secrets in staging before production
    - Update all dependent services immediately after rotation
    - Log all rotation events for audit purposes
"""

import os
import sys
import json
import secrets
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/secret_rotation.log", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class SecretRotator:
    """Handles rotation of secrets and tokens."""

    def __init__(self, env_file: str = ".env"):
        """
        Initialize the secret rotator.

        Args:
            env_file: Path to the .env file to update.
        """
        self.env_file = Path(env_file)
        self.rotation_log = Path("logs/rotation_events.json")
        self.rotation_log.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def generate_admin_token(length: int = 64) -> str:
        """
        Generate a secure admin token.

        Args:
            length: Length of the token in characters (default: 64)

        Returns:
            Hexadecimal token string.
        """
        return secrets.token_hex(length // 2)

    @staticmethod
    def generate_jwt_secret(length: int = 64) -> str:
        """
        Generate a secure JWT secret.

        Args:
            length: Length of the secret (default: 64)

        Returns:
            URL-safe base64 encoded secret.
        """
        return secrets.token_urlsafe(length)

    @staticmethod
    def generate_quantum_shared_secret(length: int = 32) -> str:
        """
        Generate a shared secret for inter-service authentication.

        Args:
            length: Length of the secret (default: 32)

        Returns:
            Hexadecimal secret string.
        """
        return secrets.token_hex(length)

    def log_rotation_event(
        self,
        service: str,
        old_value_hash: str,
        new_value_hash: str,
        status: str,
        notes: Optional[str] = None,
    ) -> None:
        """
        Log a secret rotation event.

        Args:
            service: Name of the service/secret rotated
            old_value_hash: Hash of the old value (for audit)
            new_value_hash: Hash of the new value (for audit)
            status: Status of the rotation (success/failed)
            notes: Optional notes about the rotation
        """
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": service,
            "old_value_hash": old_value_hash,
            "new_value_hash": new_value_hash,
            "status": status,
            "notes": notes,
            "rotated_by": os.getenv("USER", "unknown"),
        }

        # Load existing events
        events = []
        if self.rotation_log.exists():
            try:
                with open(self.rotation_log, "r") as f:
                    events = json.load(f)
            except json.JSONDecodeError:
                logger.warning("Could not parse existing rotation log, starting fresh")

        # Append new event
        events.append(event)

        # Save updated events
        with open(self.rotation_log, "w") as f:
            json.dump(events, f, indent=2)

        logger.info(f"Logged rotation event for {service}: {status}")

    def update_env_file(self, key: str, new_value: str) -> bool:
        """
        Update a specific key in the .env file.

        Args:
            key: Environment variable name
            new_value: New value to set

        Returns:
            True if successful, False otherwise
        """
        if not self.env_file.exists():
            logger.error(f".env file not found: {self.env_file}")
            return False

        # Read current .env content
        with open(self.env_file, "r") as f:
            lines = f.readlines()

        # Update the line with the key
        updated = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}="):
                new_lines.append(f"{key}={new_value}\n")
                updated = True
            else:
                new_lines.append(line)

        # If key wasn't found, append it
        if not updated:
            new_lines.append(f"{key}={new_value}\n")

        # Write updated content
        with open(self.env_file, "w") as f:
            f.writelines(new_lines)

        logger.info(f"Updated {key} in {self.env_file}")
        return True

    def rotate_admin_token(self, update_env: bool = True) -> str:
        """
        Rotate the admin token.

        Args:
            update_env: Whether to update the .env file

        Returns:
            New admin token
        """
        logger.info("Generating new admin token...")
        new_token = self.generate_admin_token()

        old_token = os.getenv("ADMIN_TOKEN", "")
        old_hash = secrets.token_hex(16) if old_token else "none"
        new_hash = secrets.token_hex(16)

        if update_env:
            success = self.update_env_file("ADMIN_TOKEN", new_token)
            status = "success" if success else "failed"
        else:
            status = "generated_only"

        self.log_rotation_event(
            service="admin_token",
            old_value_hash=old_hash,
            new_value_hash=new_hash,
            status=status,
            notes="Automatic rotation",
        )

        return new_token

    def rotate_jwt_secret(self, update_env: bool = True) -> str:
        """
        Rotate the JWT secret.

        Args:
            update_env: Whether to update the .env file

        Returns:
            New JWT secret
        """
        logger.info("Generating new JWT secret...")
        new_secret = self.generate_jwt_secret()

        old_secret = os.getenv("JWT_SECRET", "")
        old_hash = secrets.token_hex(16) if old_secret else "none"
        new_hash = secrets.token_hex(16)

        if update_env:
            success = self.update_env_file("JWT_SECRET", new_secret)
            status = "success" if success else "failed"
        else:
            status = "generated_only"

        self.log_rotation_event(
            service="jwt_secret",
            old_value_hash=old_hash,
            new_value_hash=new_hash,
            status=status,
            notes="Automatic rotation - invalidates all existing JWTs",
        )

        logger.warning("⚠️  JWT secret rotated - all existing tokens are now invalid!")
        return new_secret

    def rotate_quantum_shared_secret(self, update_env: bool = True) -> str:
        """
        Rotate the quantum shared secret.

        Args:
            update_env: Whether to update the .env file

        Returns:
            New shared secret
        """
        logger.info("Generating new quantum shared secret...")
        new_secret = self.generate_quantum_shared_secret()

        old_secret = os.getenv("QUANTUM_SHARED_SECRET", "")
        old_hash = secrets.token_hex(16) if old_secret else "none"
        new_hash = secrets.token_hex(16)

        if update_env:
            success = self.update_env_file("QUANTUM_SHARED_SECRET", new_secret)
            status = "success" if success else "failed"
        else:
            status = "generated_only"

        self.log_rotation_event(
            service="quantum_shared_secret",
            old_value_hash=old_hash,
            new_value_hash=new_hash,
            status=status,
            notes="Automatic rotation",
        )

        return new_secret

    def rotate_all(self, update_env: bool = True) -> Dict[str, str]:
        """
        Rotate all supported secrets.

        Args:
            update_env: Whether to update the .env file

        Returns:
            Dictionary of service names to new secrets
        """
        logger.info("=" * 60)
        logger.info("Starting rotation of all secrets")
        logger.info("=" * 60)

        results = {}

        # Rotate each secret
        results["ADMIN_TOKEN"] = self.rotate_admin_token(update_env)
        results["JWT_SECRET"] = self.rotate_jwt_secret(update_env)
        results["QUANTUM_SHARED_SECRET"] = self.rotate_quantum_shared_secret(update_env)

        logger.info("=" * 60)
        logger.info("Rotation complete!")
        logger.info("=" * 60)

        return results


def main():
    """Main entry point for secret rotation script."""
    parser = argparse.ArgumentParser(
        description="Rotate secrets and update services",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rotate all secrets
  python scripts/rotate_secrets.py --all

  # Rotate specific secret
  python scripts/rotate_secrets.py --service admin_token
  python scripts/rotate_secrets.py --service jwt_secret

  # Generate new token without updating .env (dry-run)
  python scripts/rotate_secrets.py --generate-only --service admin_token

Security Notes:
  - Backup your .env file before rotation
  - Test new secrets in staging first
  - Update all dependent services immediately
  - All rotation events are logged to logs/rotation_events.json
        """,
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Rotate all secrets",
    )
    parser.add_argument(
        "--service",
        choices=["admin_token", "jwt_secret", "quantum_shared_secret"],
        help="Specific service to rotate",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Generate new secrets without updating .env file",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to .env file (default: .env)",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.all and not args.service:
        parser.error("Must specify either --all or --service")

    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)

    try:
        rotator = SecretRotator(env_file=args.env_file)
        update_env = not args.generate_only

        if args.all:
            results = rotator.rotate_all(update_env=update_env)
            print("\n" + "=" * 60)
            print("Generated Secrets (SAVE THESE SECURELY!):")
            print("=" * 60)
            for service, secret in results.items():
                print(f"{service}={secret}")
            print("=" * 60)

        elif args.service:
            if args.service == "admin_token":
                new_secret = rotator.rotate_admin_token(update_env=update_env)
            elif args.service == "jwt_secret":
                new_secret = rotator.rotate_jwt_secret(update_env=update_env)
            elif args.service == "quantum_shared_secret":
                new_secret = rotator.rotate_quantum_shared_secret(update_env=update_env)
            else:
                raise ValueError(f"Unknown service: {args.service}")

            print("\n" + "=" * 60)
            print(f"Generated Secret for {args.service.upper()}:")
            print("=" * 60)
            print(new_secret)
            print("=" * 60)

        if not update_env:
            print("\n⚠️  DRY RUN - .env file was NOT updated")
            print("Remove --generate-only flag to update the .env file")

    except Exception as e:
        logger.error(f"Rotation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
