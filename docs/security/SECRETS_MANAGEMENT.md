# Secrets Management Guide

This guide explains how to securely manage secrets and API keys in QuantumDev using encryption and best practices.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Encryption Setup](#encryption-setup)
- [Secret Rotation](#secret-rotation)
- [Environment Variables](#environment-variables)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

QuantumDev implements secure secrets management using:

- **Fernet Encryption**: Symmetric encryption (AES-128-CBC) for `.env` files
- **Environment-based Keys**: Encryption keys stored separately from encrypted data
- **Automated Rotation**: Scripts to generate and rotate secrets
- **Startup Validation**: Fail-fast checks for missing required secrets
- **Audit Logging**: All rotation events are logged for compliance

### Security Architecture

```
┌─────────────────┐
│   .env.example  │  (Template, committed to git)
└─────────────────┘
         │
         ▼
┌─────────────────┐
│      .env       │  (Your secrets, NOT in git)
└─────────────────┘
         │
         ▼ encrypt
┌─────────────────┐
│ .env.encrypted  │  (Encrypted, can be committed)
└─────────────────┘
         │
         ▼ decrypt (with ENCRYPTION_KEY)
┌─────────────────┐
│      .env       │  (Restored for use)
└─────────────────┘
```

## Quick Start

### 1. Initial Setup

```bash
# Copy the template
cp .env.example .env

# Edit .env with your actual secrets
nano .env
```

### 2. Generate Encryption Key

```bash
# Generate a new encryption key
python scripts/encrypt_env.py --generate-key

# Output example:
# Generated encryption key:
# 5XqZw_vN8Yb2mK9fT3hL6pR1dS4nJ7cA0uV2gE5xM8y=
#
# Store this key securely!
# Set it as an environment variable:
# export ENCRYPTION_KEY="5XqZw_vN8Yb2mK9fT3hL6pR1dS4nJ7cA0uV2gE5xM8y="
```

### 3. Store Encryption Key

**Important**: Never commit the encryption key to git!

Choose one of these methods:

#### Option A: Environment Variable (Development)

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export ENCRYPTION_KEY="your-key-here"

# Or use direnv (recommended)
echo 'export ENCRYPTION_KEY="your-key-here"' >> .envrc
direnv allow
```

#### Option B: Secrets Manager (Production)

Store the encryption key in:
- AWS Secrets Manager
- Azure Key Vault
- Google Cloud Secret Manager
- HashiCorp Vault

```bash
# Example: AWS Secrets Manager
aws secretsmanager create-secret \
    --name quantumdev/encryption-key \
    --secret-string "your-key-here"

# Retrieve it in your deployment
export ENCRYPTION_KEY=$(aws secretsmanager get-secret-value \
    --secret-id quantumdev/encryption-key \
    --query SecretString --output text)
```

### 4. Encrypt Your Secrets

```bash
# Set the encryption key
export ENCRYPTION_KEY="your-key-here"

# Encrypt .env
python scripts/encrypt_env.py --encrypt

# Output:
# ✓ Encrypted .env -> .env.encrypted
#   Original size: 2458 bytes
#   Encrypted size: 2584 bytes
```

### 5. Decrypt When Needed

```bash
# Decrypt .env.encrypted to .env
python scripts/encrypt_env.py --decrypt

# Output:
# ✓ Decrypted .env.encrypted -> .env
#   Encrypted size: 2584 bytes
#   Decrypted size: 2458 bytes
```

## Encryption Setup

### Encrypting Environment Files

```bash
# Basic usage (encrypts .env to .env.encrypted)
python scripts/encrypt_env.py --encrypt

# Custom input/output paths
python scripts/encrypt_env.py --encrypt \
    --input .env.production \
    --output .env.prod.encrypted

# Specify encryption key via argument (not recommended - use env var)
python scripts/encrypt_env.py --encrypt --key "your-key-here"
```

### Decrypting Environment Files

```bash
# Basic usage (decrypts .env.encrypted to .env)
python scripts/encrypt_env.py --decrypt

# Custom paths
python scripts/encrypt_env.py --decrypt \
    --input .env.prod.encrypted \
    --output .env.production
```

### Automated Decryption on Startup

Add this to your application startup or deployment script:

```bash
#!/bin/bash
# startup.sh

# Check if ENCRYPTION_KEY is set
if [ -z "$ENCRYPTION_KEY" ]; then
    echo "ERROR: ENCRYPTION_KEY not set"
    exit 1
fi

# Decrypt .env file
python scripts/encrypt_env.py --decrypt --input .env.encrypted --output .env

# Start the application
python -m uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000
```

## Secret Rotation

Regular secret rotation is a security best practice. Use the rotation script to generate new secrets.

### Rotate All Secrets

```bash
# Rotate all secrets and update .env
python scripts/rotate_secrets.py --all

# Output:
# ====================================================
# Generated Secrets (SAVE THESE SECURELY!):
# ====================================================
# ADMIN_TOKEN=a1b2c3d4e5f6...
# JWT_SECRET=X9Y8Z7W6V5U4...
# QUANTUM_SHARED_SECRET=m9n8o7p6q5r4...
# ====================================================
```

### Rotate Specific Secret

```bash
# Rotate admin token
python scripts/rotate_secrets.py --service admin_token

# Rotate JWT secret (invalidates all existing tokens!)
python scripts/rotate_secrets.py --service jwt_secret

# Rotate quantum shared secret
python scripts/rotate_secrets.py --service quantum_shared_secret
```

### Dry-Run (Generate Without Updating)

```bash
# Generate new secret without updating .env
python scripts/rotate_secrets.py --generate-only --service admin_token

# Output:
# ====================================================
# Generated Secret for ADMIN_TOKEN:
# ====================================================
# f9e8d7c6b5a4938271605948372615048392716...
# ====================================================
# ⚠️  DRY RUN - .env file was NOT updated
```

### Rotation Best Practices

1. **Backup First**: Always backup `.env` before rotation
   ```bash
   cp .env .env.backup-$(date +%Y%m%d-%H%M%S)
   ```

2. **Test in Staging**: Rotate in staging environment first

3. **Update All Services**: After rotating, update all dependent services immediately

4. **Monitor Logs**: Check `logs/rotation_events.json` for audit trail

5. **Schedule Regular Rotations**: Set up a rotation schedule:
   - Admin tokens: Every 90 days
   - JWT secrets: Every 180 days
   - API keys: As needed or when compromised

### Rotation Workflow Example

```bash
# 1. Backup current secrets
cp .env .env.backup-$(date +%Y%m%d-%H%M%S)

# 2. Generate new secrets (dry-run first to preview)
python scripts/rotate_secrets.py --generate-only --all

# 3. Actually rotate
python scripts/rotate_secrets.py --all

# 4. Re-encrypt with new secrets
python scripts/encrypt_env.py --encrypt

# 5. Restart services to pick up new secrets
systemctl restart quantumdev

# 6. Verify everything works
curl -H "X-Admin-Token: NEW_TOKEN" http://localhost:8000/health
```

## Environment Variables

### Required Secrets

These secrets **must** be set for the application to start:

| Variable | Type | Description | Example |
|----------|------|-------------|---------|
| `LLM_ENDPOINT` | URL | LLM API endpoint | `http://localhost:5000/v1` |
| `ENCRYPTION_KEY` | String | Fernet encryption key | (see generation) |

### Optional Secrets

| Variable | Type | Description | Default |
|----------|------|-------------|---------|
| `OPENAI_API_KEY` | String | OpenAI API key | None |
| `BRAVE_API_KEY` | String | Brave Search API key | None |
| `TELEGRAM_BOT_TOKEN` | String | Telegram bot token | None |
| `AWS_ACCESS_KEY_ID` | String | AWS access key | None |
| `AWS_SECRET_ACCESS_KEY` | String | AWS secret key | None |
| `REDIS_PASSWORD` | String | Redis password | None |
| `ADMIN_TOKEN` | String | Admin bypass token | `""` |
| `JWT_SECRET` | String | JWT signing secret | None |
| `QUANTUM_SHARED_SECRET` | String | Inter-service auth | `""` |

### Validation on Startup

The application validates required secrets on startup and fails fast if any are missing:

```python
# In backend/quantum_api.py
def validate_required_secrets():
    """Validate that all required secrets are present."""
    required = ["LLM_ENDPOINT"]
    optional_but_recommended = ["ENCRYPTION_KEY", "ADMIN_TOKEN"]
    
    missing = [var for var in required if not os.getenv(var)]
    
    if missing:
        logger.error(f"Missing required secrets: {', '.join(missing)}")
        raise ValueError(f"Required secrets missing: {missing}")
    
    # Warn about recommended secrets
    missing_recommended = [var for var in optional_but_recommended if not os.getenv(var)]
    if missing_recommended:
        logger.warning(f"Missing recommended secrets: {', '.join(missing_recommended)}")
```

## Best Practices

### 1. Never Commit Secrets

```bash
# Add to .gitignore (already done)
.env
.env.local
*.env.backup
.env.encrypted  # If you don't want to commit encrypted versions
*.key
encryption.key
```

### 2. Use Different Keys Per Environment

```bash
# Development
export ENCRYPTION_KEY="dev-key-here"

# Staging
export ENCRYPTION_KEY="staging-key-here"

# Production
export ENCRYPTION_KEY="prod-key-here"
```

### 3. Rotate Regularly

Set up a rotation schedule:

```bash
# Add to crontab for monthly rotation
0 2 1 * * /path/to/rotate_secrets.sh
```

### 4. Use Secrets Managers in Production

Don't store secrets in environment variables in production. Use:

- **AWS Secrets Manager**
- **Azure Key Vault**
- **Google Cloud Secret Manager**
- **HashiCorp Vault**

Example integration:

```python
import boto3

def load_secrets():
    """Load secrets from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId='quantumdev/secrets')
    secrets = json.loads(response['SecretString'])
    
    for key, value in secrets.items():
        os.environ[key] = value
```

### 5. Audit Secret Access

Monitor and log secret access:

```bash
# Check rotation logs
tail -f logs/rotation_events.json

# Filter for specific service
jq '.[] | select(.service=="admin_token")' logs/rotation_events.json
```

### 6. Implement Least Privilege

- Give each service only the secrets it needs
- Use separate secrets for different environments
- Rotate compromised secrets immediately

## Troubleshooting

### "No encryption key provided" Error

**Problem**: Missing `ENCRYPTION_KEY` environment variable

**Solution**:
```bash
# Generate a new key
python scripts/encrypt_env.py --generate-key

# Set it
export ENCRYPTION_KEY="your-key-here"
```

### "Decryption failed" Error

**Problem**: Wrong encryption key or corrupted file

**Solutions**:
1. Verify you're using the correct key
2. Check if `.env.encrypted` is corrupted
3. Restore from backup

```bash
# Try with correct key
export ENCRYPTION_KEY="correct-key-here"
python scripts/encrypt_env.py --decrypt

# Restore from backup if needed
cp .env.backup .env
```

### "Missing required secrets" on Startup

**Problem**: Application can't find required environment variables

**Solution**:
```bash
# Check which secrets are missing
python -c "
import os
required = ['LLM_ENDPOINT', 'ENCRYPTION_KEY']
missing = [v for v in required if not os.getenv(v)]
if missing:
    print(f'Missing: {missing}')
"

# Add missing secrets to .env
nano .env
```

### Secrets Not Loading

**Problem**: `.env` file not being loaded

**Solutions**:
1. Check file location (should be in project root)
2. Verify file name is exactly `.env`
3. Check file permissions

```bash
# Check file exists and is readable
ls -la .env
cat .env

# Fix permissions if needed
chmod 600 .env
```

### Rotation Script Fails

**Problem**: Cannot update `.env` file

**Solutions**:
```bash
# Check file permissions
chmod 644 .env

# Check file exists
ls -la .env

# Create logs directory
mkdir -p logs
```

## Security Checklist

- [ ] `.env` is in `.gitignore`
- [ ] Encryption key is stored securely (not in git)
- [ ] Different keys for dev/staging/prod
- [ ] Regular rotation schedule set up
- [ ] Secrets manager configured for production
- [ ] Audit logging enabled
- [ ] Backup process in place
- [ ] Team trained on secret handling
- [ ] Incident response plan documented

## Additional Resources

- [Fernet Encryption Specification](https://github.com/fernet/spec)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_CheatSheet.html)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)

## Support

If you encounter issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs: `logs/rotation_events.json`
3. Open an issue on GitHub
4. Contact the security team
