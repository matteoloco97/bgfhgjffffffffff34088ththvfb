# QuantumDev Quick Reference Card

## 🚀 Getting Started

```bash
# Quick setup
git clone <repo-url>
cd quantumdev
./setup.sh

# Manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your settings
redis-server &
python backend/quantum_api.py
```

## 📁 Repository Structure

```
quantumdev/
├── agents/          # AI agents (trading, news, weather, etc.)
├── backend/         # FastAPI application
├── core/            # Core modules (memory, chat, etc.)
├── utils/           # Helper utilities
├── scripts/         # Standalone scripts
├── tests/           # Test suites
├── config/          # Configuration & examples
├── deployment/      # System service files
└── docs/            # All documentation
    ├── implementation/  # Technical details
    ├── guides/         # Feature guides
    ├── quickstart/     # Quick references
    ├── deployment/     # Deployment docs
    └── security/       # Security summaries
```

## 🔧 Common Commands

### Development
```bash
# Start API server (development)
python backend/quantum_api.py
uvicorn backend.quantum_api:app --reload

# Format code
black .
isort .

# Lint
ruff check .

# Type check
mypy .
```

### Testing
```bash
# Run all tests
pytest

# With coverage
pytest --cov=. --cov-report=html

# Specific tests
pytest tests/test_memory_system.py
pytest -k "test_cache"
```

### Database
```bash
# Start Redis
redis-server

# Check Redis
redis-cli ping

# Flush cache
python scripts/flush_cache.py
```

## 📖 Key Documentation Files

| File | Description |
|------|-------------|
| `README.md` | Project overview & quick start |
| `CONTRIBUTING.md` | How to contribute |
| `CLEANUP_SUMMARY.md` | Cleanup details & roadmap |
| `docs/README.md` | Documentation index |
| `docs/quickstart/QUICKSTART.md` | Detailed quick start |
| `docs/guides/INTEGRATION_GUIDE.md` | Integration guide |
| `docs/deployment/DEPLOYMENT_CHECKLIST.md` | Deploy checklist |
| `docs/deployment/GPU_NODE_SETUP.md` | GPU setup |

## ⚙️ Configuration

```bash
# Environment files location
config/env-examples/
├── ENV_OPTIMIZED_V4.env        # Production config
├── ENV_A6000_48GB_OPTIMIZED.env # GPU node
├── ENV_STREAMING_EXAMPLE.env   # Streaming setup
└── ...

# Copy example to use
cp config/env-examples/ENV_OPTIMIZED_V4.env .env
# Or use the template
cp .env.example .env
```

### Key Environment Variables
```bash
LLM_ENDPOINT=http://127.0.0.1:5000/v1
LLM_MODEL=gpt-4
REDIS_HOST=localhost
REDIS_PORT=6379
BRAVE_API_KEY=your-key
ENABLE_CONVERSATIONAL_MEMORY=true
```

## 🏗️ Architecture Overview

```
┌─────────────┐
│  Telegram   │
│    Bot      │
└──────┬──────┘
       │
       v
┌─────────────────────────────────┐
│      FastAPI Backend            │
│  (backend/quantum_api.py)       │
└────┬───────────┬────────────────┘
     │           │
     v           v
┌─────────┐  ┌──────────────┐
│ Agents  │  │ Core Systems │
│         │  │              │
│ Trading │  │ Memory       │
│ News    │  │ Chat Engine  │
│ Weather │  │ Web Search   │
│ Sports  │  │ Code Exec    │
└─────────┘  └──────────────┘
     │           │
     v           v
┌──────────────────────────────┐
│        Utilities             │
│  Cache │ ChromaDB │ Redis   │
└──────────────────────────────┘
```

## 🧪 Development Workflow

1. **Create branch**: `git checkout -b feature/my-feature`
2. **Make changes**: Edit code, add tests
3. **Format**: `black . && isort .`
4. **Lint**: `ruff check .`
5. **Test**: `pytest`
6. **Commit**: `git commit -m "feat: description"`
7. **Push**: `git push origin feature/my-feature`
8. **PR**: Create pull request on GitHub

## 🔒 Security Checklist

- [ ] Never commit `.env` file
- [ ] Use environment variables for secrets
- [ ] Run `bandit -r .` before commit
- [ ] Run `pip-audit` for dependency check
- [ ] Review security docs in `docs/security/`

## 🐛 Troubleshooting

### Redis Connection Failed
```bash
# Check if Redis is running
redis-cli ping
# If not, start it
redis-server
```

### Import Errors
```bash
# Ensure virtual environment is activated
source venv/bin/activate
# Reinstall dependencies
pip install -r requirements.txt
```

### GPU Connection Issues
```bash
# Check SSH tunnel (on VPS)
ssh -L 5000:localhost:5000 root@GPU_HOST -p PORT
# Test connection
curl http://localhost:5000/v1/models
```

## 📊 Project Statistics

- **Total Python Files**: 149
- **Lines of Code**: ~50,000+
- **Documentation Files**: 49
- **Test Files**: 35+
- **Agents**: 20+
- **Core Modules**: 40+

## 🎯 Quick Links

- **Main API**: `backend/quantum_api.py`
- **Config**: `config/`
- **Tests**: `tests/`
- **Scripts**: `scripts/`
- **Docs**: `docs/`

## 💡 Pro Tips

1. Use `setup.sh` for quick environment setup
2. Read `docs/README.md` for documentation navigation
3. Check `CLEANUP_SUMMARY.md` for enhancement ideas
4. Use `scripts/` for common tasks
5. Keep `.env` updated with latest `.env.example`

---

**Need Help?**
- Check `docs/` directory
- Read `CONTRIBUTING.md`
- Review `docs/guides/TESTING_GUIDE.md`
- See `CLEANUP_SUMMARY.md` for roadmap
