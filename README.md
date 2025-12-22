# QuantumDev - Advanced AI Research Assistant

QuantumDev is an advanced AI-powered research and automation system that combines multiple AI capabilities including web research, knowledge graph management, code execution, and conversational memory.

## 🌟 Features

- **🧠 Advanced LLM Integration**: Support for local and cloud-based LLMs with OpenAI-compatible API
- **🔍 Multi-Engine Web Search**: Parallel web scraping and intelligent synthesis
- **📚 Knowledge Graph**: Semantic knowledge representation with ChromaDB and NetworkX
- **💾 Conversational Memory**: Context-aware long-term memory system
- **🤖 Specialized Agents**: Modular agents for trading, news, weather, sports, and more
- **📊 Real-time Analytics**: GPU monitoring and system performance tracking
- **💬 Telegram Integration**: Bot interface with streaming responses
- **🔒 Security-First**: Built-in security scanning and safe code execution
- **📝 OCR Support**: Document and image text extraction

## 🏗️ Architecture

The system follows a modular architecture with clear separation of concerns:

```
quantumdev/
├── agents/          # Specialized AI agents (web research, trading, news, etc.)
├── backend/         # Core API and synthesis engines
├── core/            # Core functionality (memory, chat, calculators, etc.)
├── utils/           # Utility modules (caching, analytics, database handlers)
├── scripts/         # Standalone scripts and tools
├── tests/           # Test suites
├── config/          # Configuration files and examples
├── deployment/      # System service configurations
└── docs/            # Documentation
```

### Deployment Architecture

QuantumDev is designed to run in a distributed setup:

- **VPS Node (Contabo)**: Runs the main application logic, API endpoints, and manages agents
- **GPU Node (Vast.ai/A6000)**: Handles LLM inference via SSH tunnel (optional)

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Redis server
- (Optional) GPU with 24GB+ VRAM for local LLM inference

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd quantumdev
   ```

2. **Install dependencies**
   ```bash
   # Core dependencies
   pip install -r requirements.txt
   
   # Development dependencies (optional)
   pip install -r requirements-dev.txt
   ```

3. **Configure environment**
   ```bash
   cp config/env-examples/ENV_OPTIMIZED_V4.env .env
   # Edit .env with your API keys and configuration
   ```

4. **Start Redis**
   ```bash
   redis-server
   ```

5. **Run the application**
   ```bash
   # Start the API server
   python backend/quantum_api.py
   
   # Or use uvicorn for production
   uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000
   ```

## 📖 Documentation

Comprehensive documentation is available in the `docs/` directory:

### Quick References
- [Quick Start Guide](docs/quickstart/QUICKSTART.md)
- [Quick Reference](docs/quickstart/QUICK_REFERENCE.md)
- [Memory System Quick Start](docs/quickstart/MEMORY_QUICKSTART.md)
- [Knowledge Graph Quick Start](docs/quickstart/KNOWLEDGE_GRAPH_QUICKSTART.md)

### Guides
- [Integration Guide](docs/guides/INTEGRATION_GUIDE.md)
- [Testing Guide](docs/guides/TESTING_GUIDE.md)
- [GPU Monitoring Guide](docs/guides/GPU_MONITORING_GUIDE.md)
- [Telegram Bot Guide](docs/guides/TELEGRAM_AUTOWEB_GUIDE.md)
- [Examples and Best Practices](docs/guides/EXAMPLES_AND_BEST_PRACTICES.md)

### Deployment
- [Deployment Checklist](docs/deployment/DEPLOYMENT_CHECKLIST.md)
- [GPU Node Setup Guide](docs/deployment/STEP2_DEPLOYMENT_GUIDE.md)

### Implementation Details
- [Implementation Summaries](docs/implementation/)
- [Security Summaries](docs/security/)

### Project Planning
- [Project Roadmap](docs/JARVIS_ROADMAP.md)
- [Changelog](CHANGELOG.md)

## 🔧 Configuration

The system uses environment variables for configuration. Example configurations are provided in `config/env-examples/`:

- `ENV_OPTIMIZED_V4.env` - Production-ready configuration
- `ENV_A6000_48GB_OPTIMIZED.env` - GPU node configuration
- `ENV_STREAMING_EXAMPLE.env` - Streaming response setup
- `ENV_STEP2_AUTOWEB.env` - Autonomous web research setup

Key configuration areas:
- **LLM Settings**: API endpoints, model selection, token limits
- **Database**: Redis, ChromaDB, vector store configuration
- **Search**: Brave Search API, web scraping settings
- **Security**: API keys, authentication, rate limiting
- **Monitoring**: GPU metrics, system analytics

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test modules
pytest tests/test_memory_system.py
```

See [Testing Guide](docs/guides/TESTING_GUIDE.md) for more details.

## 🛠️ Development

### Code Quality

The project uses several tools to maintain code quality:

```bash
# Format code
black .
isort .

# Linting
ruff check .

# Type checking
mypy .

# Security scanning
bandit -r .
pip-audit
```

### Project Structure

- **agents/**: Specialized agents handle specific domains (trading, news, weather, etc.)
- **backend/**: FastAPI application and synthesis engines
- **core/**: Core modules for memory, chat, autonomous agents, calculators
- **utils/**: Helper modules for caching, database operations, analytics
- **scripts/**: Standalone scripts for testing and utilities

## 🤝 Contributing

Contributions are welcome! Please ensure:

1. Code follows the existing style (use `black` and `isort`)
2. All tests pass (`pytest`)
3. New features include tests
4. Security best practices are followed

## 📝 Key Components

### Agents
- **Web Research Agent**: Advanced web scraping and synthesis
- **Trading Agent**: Market data and trading analysis
- **News Agent**: Real-time news aggregation
- **Weather Agent**: Weather data from Open-Meteo
- **Sports Agent**: Sports data and betting analysis
- **Code Agent**: Code analysis and execution

### Core Systems
- **Conversational Memory**: Long-term context management
- **Knowledge Graph**: Semantic relationship mapping
- **Autonomous Agent**: Self-directed task execution
- **Chat Engine**: Conversation management with streaming
- **Code Executor**: Safe Python code execution sandbox

### Utilities
- **Redis Cache**: High-performance caching layer
- **ChromaDB Handler**: Vector database operations
- **Search Analytics**: Search query analysis and optimization

## 🔒 Security

Security is a top priority:

- API key management via environment variables
- Safe code execution sandbox
- Input validation and sanitization
- Regular security audits with `bandit` and `pip-audit`
- See [Security Summary](docs/security/SECURITY_SUMMARY.md) for details

## 📊 Performance

The system is optimized for:
- Parallel web scraping with adaptive throttling
- Efficient token management for LLM calls
- Redis caching to reduce API calls
- GPU monitoring for optimal resource usage

## 📄 License

[Add your license here]

## 🙏 Acknowledgments

Built with:
- FastAPI for the web framework
- OpenAI API for LLM integration
- ChromaDB for vector storage
- Redis for caching
- And many other great open-source projects

## 📞 Support

For issues, questions, or contributions, please use the GitHub issue tracker.

---

**Note**: This is an active development project. Features and APIs may change.
