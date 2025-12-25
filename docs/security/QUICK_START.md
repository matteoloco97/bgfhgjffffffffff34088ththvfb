# Secrets Management Quick Reference

## Quick Start (5 minutes)

### 1. Generate Encryption Key
```bash
python scripts/encrypt_env.py --generate-key
```
Save the output somewhere secure (password manager, secrets vault, etc.)

### 2. Set Encryption Key
```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc, etc.)
export ENCRYPTION_KEY="paste-your-key-here"

# Or use a .envrc file (with direnv)
echo 'export ENCRYPTION_KEY="paste-your-key-here"' >> .envrc
direnv allow
```

### 3. Set Up Your Environment
```bash
# Copy the template
cp .env.example .env

# Edit with your actual secrets
nano .env
```

### 4. Encrypt Your Secrets (Optional but Recommended)
```bash
python scripts/encrypt_env.py --encrypt
```

## Common Operations

### Decrypt .env for Local Development
```bash
python scripts/encrypt_env.py --decrypt
```

### Rotate Secrets (Every 90 days recommended)
```bash
# Backup first
cp .env .env.backup-$(date +%Y%m%d)

# Rotate all secrets
python scripts/rotate_secrets.py --all

# Copy new secrets to .env file
```

### Check Rotation History
```bash
cat logs/rotation_events.json | python -m json.tool
```

## Required Environment Variables

Only **one** required variable:
- `LLM_ENDPOINT` - Your LLM API endpoint

Recommended (but optional):
- `ENCRYPTION_KEY` - For encrypted .env support
- `ADMIN_TOKEN` - For admin API access

## Security Checklist

- [ ] Generated and saved encryption key
- [ ] Set ENCRYPTION_KEY environment variable
- [ ] Created .env from .env.example
- [ ] Verified .env is in .gitignore (not committed)
- [ ] Tested encryption/decryption works
- [ ] Set up secret rotation schedule
- [ ] Read full documentation: docs/security/SECRETS_MANAGEMENT.md

## Troubleshooting

### "No encryption key provided"
```bash
export ENCRYPTION_KEY="your-key-here"
```

### "Missing required secrets: LLM_ENDPOINT"
Add to .env:
```
LLM_ENDPOINT=http://localhost:5000/v1
```

### "Decryption failed"
You're using the wrong encryption key. Check your ENCRYPTION_KEY value.

## Production Deployment

For production, use a secrets manager instead of .env files:
- AWS Secrets Manager
- Azure Key Vault  
- Google Cloud Secret Manager
- HashiCorp Vault

See docs/security/SECRETS_MANAGEMENT.md for integration examples.

## Full Documentation

📖 Complete guide: `docs/security/SECRETS_MANAGEMENT.md`
