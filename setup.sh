#!/bin/bash
# QuantumDev Quick Setup Script
# This script helps you get started with QuantumDev quickly

set -e  # Exit on error

echo "🚀 QuantumDev Quick Setup"
echo "========================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "ℹ $1"
}

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    print_error "Python 3.10+ is required. You have Python $PYTHON_VERSION"
    exit 1
fi

print_success "Python $PYTHON_VERSION found"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv venv
    print_success "Virtual environment created"
else
    print_warning "Virtual environment already exists"
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source venv/bin/activate
print_success "Virtual environment activated"

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
print_success "pip upgraded"

# Install dependencies
echo ""
print_info "Installing dependencies..."
echo "This may take a few minutes..."

if pip install -r requirements.txt > /dev/null 2>&1; then
    print_success "Core dependencies installed"
else
    print_error "Failed to install core dependencies"
    exit 1
fi

# Ask about development dependencies
echo ""
read -p "Install development dependencies? (y/N): " install_dev
if [[ $install_dev =~ ^[Yy]$ ]]; then
    if pip install -r requirements-dev.txt > /dev/null 2>&1; then
        print_success "Development dependencies installed"
    else
        print_warning "Failed to install development dependencies"
    fi
fi

# Setup environment file
echo ""
if [ ! -f ".env" ]; then
    print_info "Setting up environment configuration..."
    read -p "Copy example environment file? (y/N): " copy_env
    if [[ $copy_env =~ ^[Yy]$ ]]; then
        cp .env.example .env
        print_success ".env file created"
        print_warning "Please edit .env file with your actual configuration"
    fi
else
    print_warning ".env file already exists"
fi

# Check Redis
echo ""
print_info "Checking Redis..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping > /dev/null 2>&1; then
        print_success "Redis is running"
    else
        print_warning "Redis is installed but not running"
        print_info "Start Redis with: redis-server"
    fi
else
    print_warning "Redis is not installed"
    print_info "Install Redis: sudo apt-get install redis-server (Ubuntu/Debian)"
    print_info "              brew install redis (macOS)"
fi

# Create necessary directories
echo ""
print_info "Creating necessary directories..."
mkdir -p data/archive
mkdir -p data/chroma
mkdir -p logs
print_success "Directories created"

# Setup git hooks (if pre-commit is installed)
if command -v pre-commit &> /dev/null; then
    echo ""
    read -p "Setup pre-commit hooks? (y/N): " setup_hooks
    if [[ $setup_hooks =~ ^[Yy]$ ]]; then
        pre-commit install > /dev/null 2>&1
        print_success "Pre-commit hooks installed"
    fi
fi

# Summary
echo ""
echo "================================"
echo "✓ Setup Complete!"
echo "================================"
echo ""
print_info "Next steps:"
echo "  1. Edit .env file with your configuration"
echo "  2. Start Redis: redis-server"
echo "  3. Run the application:"
echo "     - API: python backend/quantum_api.py"
echo "     - Or: uvicorn backend.quantum_api:app --reload"
echo ""
print_info "Documentation: See README.md and docs/"
print_info "Quick start: docs/quickstart/QUICKSTART.md"
echo ""

# Ask if user wants to run tests
read -p "Run tests to verify installation? (y/N): " run_tests
if [[ $run_tests =~ ^[Yy]$ ]]; then
    echo ""
    print_info "Running tests..."
    if command -v pytest &> /dev/null; then
        pytest --version
        pytest -v
    else
        print_warning "pytest not installed (install with: pip install pytest)"
    fi
fi

echo ""
print_success "Happy coding! 🎉"
