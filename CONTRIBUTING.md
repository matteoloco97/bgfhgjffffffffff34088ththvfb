# Contributing to QuantumDev

Thank you for considering contributing to QuantumDev! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Development Setup

1. **Fork and clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/quantumdev.git
   cd quantumdev
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Set up pre-commit hooks** (optional but recommended)
   ```bash
   pre-commit install
   ```

## 🧪 Development Workflow

### Code Style

We use several tools to maintain consistent code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **Ruff**: Fast Python linter
- **mypy**: Static type checking

Before submitting a PR, run:

```bash
# Format code
black .
isort .

# Check linting
ruff check .

# Type check
mypy .
```

### Testing

All new features should include tests. Run tests with:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_memory_system.py

# Run tests matching a pattern
pytest -k "test_memory"
```

### Security

Security is critical. Before submitting:

```bash
# Run security scans
bandit -r .
pip-audit
safety check
```

Never commit:
- API keys or secrets
- Personal data
- Credentials

Use environment variables for all sensitive configuration.

## 📝 Commit Guidelines

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat(agents): add cryptocurrency trading agent

Implements a new agent for real-time crypto market analysis
and trading signal generation.

Closes #123
```

```
fix(memory): resolve memory leak in conversation context

The context manager was not properly releasing ChromaDB
connections, causing memory growth over time.
```

## 🏗️ Architecture Guidelines

### Adding a New Agent

1. Create a new file in `agents/` directory
2. Inherit from base agent class (if applicable)
3. Implement required methods
4. Add configuration options to environment examples
5. Write tests in `tests/`
6. Update documentation

Example structure:
```python
# agents/my_new_agent.py
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class MyNewAgent:
    """
    Brief description of what this agent does.
    
    Attributes:
        config: Configuration dictionary
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    async def execute(self, query: str) -> Dict[str, Any]:
        """
        Execute the agent's main functionality.
        
        Args:
            query: User query or task description
            
        Returns:
            Dictionary containing results
        """
        # Implementation
        pass
```

### Adding Core Functionality

1. Place new modules in `core/` directory
2. Keep modules focused and single-purpose
3. Use type hints
4. Write comprehensive docstrings
5. Add unit tests

### Code Organization

- `agents/`: Domain-specific agents (self-contained)
- `backend/`: API endpoints and request handlers
- `core/`: Reusable core functionality
- `utils/`: Helper functions and utilities
- `scripts/`: Standalone scripts and tools
- `tests/`: Test suites
- `config/`: Configuration templates

## 📚 Documentation

### Docstrings

Use Google-style docstrings:

```python
def function_name(param1: str, param2: int) -> bool:
    """
    Brief description of the function.
    
    More detailed description if needed, explaining the
    purpose and behavior of the function.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When invalid input is provided
        
    Examples:
        >>> function_name("test", 42)
        True
    """
    pass
```

### Updating Documentation

When adding features:

1. Update relevant documentation in `docs/`
2. Add examples to guides if applicable
3. Update README.md if it affects main features
4. Consider adding a quickstart guide

## 🔍 Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Make your changes**
   - Write clean, documented code
   - Add tests
   - Update documentation

3. **Test thoroughly**
   ```bash
   pytest
   black .
   isort .
   ruff check .
   bandit -r .
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push to your fork**
   ```bash
   git push origin feature/my-new-feature
   ```

6. **Create a Pull Request**
   - Use a descriptive title
   - Reference related issues
   - Describe what changed and why
   - Include screenshots for UI changes

### PR Checklist

Before submitting, ensure:

- [ ] Code follows project style guidelines
- [ ] All tests pass
- [ ] New tests added for new features
- [ ] Documentation updated
- [ ] No security issues introduced
- [ ] Commit messages follow conventions
- [ ] Branch is up to date with main

## 🐛 Reporting Bugs

When reporting bugs, include:

1. **Description**: Clear description of the issue
2. **Steps to Reproduce**: Detailed steps to reproduce
3. **Expected Behavior**: What should happen
4. **Actual Behavior**: What actually happens
5. **Environment**: Python version, OS, relevant configuration
6. **Logs**: Relevant log output or error messages

Use the issue template when available.

## 💡 Suggesting Features

For feature requests:

1. Check if it already exists in issues
2. Describe the use case clearly
3. Explain why it would be valuable
4. Consider implementation approach
5. Be open to discussion

## 🤔 Questions?

- Check existing documentation first
- Search closed issues
- Open a new issue with the "question" label
- Be specific and provide context

## 📜 Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow project guidelines

## 🙏 Thank You!

Your contributions make this project better for everyone. We appreciate your time and effort!

---

**Note**: These guidelines may evolve. Check back periodically for updates.
