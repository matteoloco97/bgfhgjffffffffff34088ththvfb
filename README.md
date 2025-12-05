# QuantumDev - Jarvis AI Platform

A comprehensive AI platform combining autonomous web interaction (autoweb), personal memory systems, and GPU-accelerated language models. Built for production deployment with enterprise-grade features and commercial vertical integration.

## 🎯 Vision

**QuantumDev** is the foundation for "Jarvis" - an advanced AI assistant platform with multiple capabilities:

- **Autoweb**: Autonomous web interaction and research
- **Personal Memory**: Context-aware conversational memory system
- **GPU Inference**: High-performance LLM serving with quantized models
- **Commercial Verticals**: Price tracking, sports scores, news aggregation, scheduling, and more

The platform is designed to scale across multiple commercial use cases while maintaining a unified, production-grade architecture.

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- For GPU setup: NVIDIA GPU with 48GB+ VRAM, CUDA 11.8+
- Redis (for caching)
- ChromaDB (for vector memory)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/matteoloco97/bgfhgjffffffffff34088ththvfb.git
   cd bgfhgjffffffffff34088ththvfb
   ```

2. **Install dependencies**
   ```bash
   # Core dependencies
   pip install -r requirements.txt
   
   # Development dependencies (optional)
   pip install -r requirements-dev.txt
   ```

3. **Configure environment variables**
   ```bash
   # For GPU setup
   cp .env.example .env
   # Edit .env and add your configuration
   ```

### Running the Platform

#### CPU/Backend (QuantumDev Open)

The main platform runs on CPU servers and is located in `Contabo VPS/quantumdev-open/`:

```bash
cd "Contabo VPS/quantumdev-open"
# See the README.md in that directory for detailed setup instructions
```

For detailed documentation, see:
- [QuantumDev Open Quickstart](Contabo%20VPS/quantumdev-open/QUICKSTART.md)
- [Integration Guide](Contabo%20VPS/quantumdev-open/INTEGRATION_GUIDE.md)
- [Testing Guide](Contabo%20VPS/quantumdev-open/TESTING_GUIDE.md)

#### GPU Setup

The GPU setup script automates model downloading and vLLM server deployment on high-VRAM GPUs (48GB+):

```bash
cd " gpu 48VRAM"
python3 setup_gpu.py
```

**GPU Requirements:**
- NVIDIA GPU with 48GB+ VRAM (e.g., A6000, A100, RTX 6000 Ada)
- CUDA 11.8 or higher (12.1+ recommended)
- Ubuntu 20.04+ or similar Linux distribution
- 100GB+ free disk space for model storage

The script will:
1. Set up a Python virtual environment
2. Install PyTorch, vLLM, and dependencies
3. Download the Dolphin-24B-Venice AWQ model (~13GB)
4. Start the vLLM OpenAI-compatible API server
5. Optionally establish SSH tunnel to CPU server
6. Register the GPU endpoint with the backend

## 📚 Documentation

Comprehensive documentation is available in the `Contabo VPS/quantumdev-open/` directory:

- **[JARVIS_ROADMAP.md](Contabo%20VPS/quantumdev-open/JARVIS_ROADMAP.md)**: Live agents implementation roadmap
- **[ENV_REFERENCE.md](Contabo%20VPS/quantumdev-open/ENV_REFERENCE.md)**: Environment variable reference
- **[SECURITY_SUMMARY.md](Contabo%20VPS/quantumdev-open/SECURITY_SUMMARY.md)**: Security considerations
- **[EXAMPLES_AND_BEST_PRACTICES.md](Contabo%20VPS/quantumdev-open/EXAMPLES_AND_BEST_PRACTICES.md)**: Usage examples

## 🔒 Security Notice

**IMPORTANT**: This platform handles sensitive data and credentials. Follow these security best practices:

1. **Environment Variables**: Never hardcode secrets in source code. Use environment variables for all credentials, API keys, and secrets.

2. **`.env` File**: Copy `.env.example` to `.env` and fill in your actual values. The `.env` file is gitignored and should NEVER be committed.

3. **GPU Setup**: The GPU setup script requires several environment variables:
   - `CPU_HOST`: CPU server hostname/IP
   - `BACKEND_API`: Backend API endpoint
   - `GPU_SSH_PRIVATE_KEY`: SSH private key for tunnel (optional)
   - `SHARED_SECRET`: Backend authentication secret (optional)

4. **SSH Keys**: Store SSH private keys securely. Use environment variables or secret management systems, never commit keys to version control.

5. **Production Deployment**: 
   - Use HTTPS/TLS for all external communications
   - Implement proper authentication and authorization
   - Regularly update dependencies for security patches
   - Monitor and log all security-relevant events

See [SECURITY_SUMMARY.md](Contabo%20VPS/quantumdev-open/SECURITY_SUMMARY.md) for more details.

## 🛠️ Development

### Code Quality

The project uses modern Python tooling:

- **Linting**: ruff
- **Formatting**: black
- **Testing**: pytest
- **Security**: pip-audit

Run quality checks:
```bash
# Lint code
ruff check .

# Format code
black --check .

# Run tests
pytest

# Security audit
pip-audit
```

### CI/CD

GitHub Actions workflows automatically run on every push:
- Code linting and formatting checks
- Test suite execution
- Security vulnerability scanning

## 🌍 Internationalization

The codebase is designed to be international-friendly:
- Documentation is primarily in English
- Code comments may be bilingual (English/Italian)
- User-facing messages are neutral and English-first

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all quality checks pass
5. Submit a pull request

## 📧 Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation in `Contabo VPS/quantumdev-open/`
- Review examples and best practices

---

**Note**: This is a production platform under active development. The folder structure (including the space-prefixed ` gpu 48VRAM` directory) is intentional and should be preserved.
