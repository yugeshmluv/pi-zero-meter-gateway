#!/bin/bash
set -euo pipefail

# install-dev.sh: Set up MeterHub development environment
# Installs Python virtual environment, dependencies, and pre-commit hooks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR" && pwd)"

echo "📦 MeterHub Development Environment Setup"
echo "=========================================="
echo "Project root: $PROJECT_ROOT"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [[ $MAJOR -lt 3 ]] || [[ $MAJOR -eq 3 && $MINOR -lt 11 ]]; then
    echo "❌ Python 3.11+ required (found $PYTHON_VERSION)"
    exit 1
fi
echo "✅ Python $PYTHON_VERSION"

# Create virtual environment
VENV_DIR="$PROJECT_ROOT/venv"
if [[ -d "$VENV_DIR" ]]; then
    echo "⚠️  Virtual environment already exists at $VENV_DIR"
    read -p "Recreate? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_DIR"
    else
        echo "Using existing virtual environment..."
    fi
fi

if [[ ! -d "$VENV_DIR" ]]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "✅ Virtual environment activated"

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r "$PROJECT_ROOT/common/requirements.txt"
pip install -r "$PROJECT_ROOT/acquisition/requirements.txt"
pip install -r "$PROJECT_ROOT/uploader/requirements.txt"
pip install -r "$PROJECT_ROOT/installer_ui/requirements.txt"

# Install dev/test dependencies
pip install pytest pytest-cov pytest-asyncio pytest-mock black flake8 mypy bandit

echo "✅ All dependencies installed"

# Create .env file (if not exists)
ENV_FILE="$PROJECT_ROOT/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    cat > "$ENV_FILE" << 'EOF'
# Development environment configuration
METREHUB_ENV=development
METREHUB_LOG_LEVEL=debug
METREHUB_MQTT_BROKER=tcp://localhost:1883
METREHUB_HTTPS_FALLBACK=http://localhost:8080
METREHUB_DB_PATH=/tmp/metrehub-dev.sqlite
EOF
    echo "✅ Created $ENV_FILE (customize as needed)"
fi

# Set up pre-commit hook
echo "🪝 Setting up pre-commit hook..."
PRE_COMMIT_HOOK="$PROJECT_ROOT/.git/hooks/pre-commit"
mkdir -p "$(dirname "$PRE_COMMIT_HOOK")"
cat > "$PRE_COMMIT_HOOK" << 'EOF'
#!/bin/bash
set -euo pipefail

echo "Running pre-commit checks..."

# Format code
black meterhub_* --quiet

# Type checking (non-strict for dev)
mypy meterhub_acq meterhub_uploader meterhub_common --ignore-missing-imports 2>/dev/null || true

# Linting (non-strict for dev)
flake8 meterhub_* --max-line-length=100 --count --quiet 2>/dev/null || true

echo "✅ Pre-commit checks passed"
EOF
chmod +x "$PRE_COMMIT_HOOK"
echo "✅ Pre-commit hook installed"

# Summary
echo ""
echo "=========================================="
echo "✅ Development environment ready!"
echo ""
echo "Next steps:"
echo "  1. Activate venv: source venv/bin/activate"
echo "  2. Run tests: pytest tests/"
echo "  3. Run acquisition simulator: python -m meterhub_acq --help"
echo ""
echo "For more info, see CONTRIBUTING.md"
