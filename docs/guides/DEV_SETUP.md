# Development Setup Guide

**Last Updated:** May 10, 2026  
**For:** Developers contributing to MeterHub Phase 2–6

---

## Prerequisites

- **OS:** macOS, Linux (Ubuntu 20.04+), or WSL2
- **Python:** 3.11 or 3.12
- **Git:** Latest
- **Optional:** Docker (for isolated testing environment)

---

## Quick Start (5 minutes)

```bash
# 1. Clone repository
git clone https://github.com/your-org/meterhub.git
cd meterhub

# 2. Run dev setup script (creates venv, installs deps)
./scripts/install-dev.sh
source venv/bin/activate

# 3. Verify installation
python -c "from meterhub_common import MeterReading; print('✓ Import works')"

# 4. Run test suite
pytest tests/ -v

# 5. Install pre-commit hooks (auto-format on commit)
pre-commit install
```

---

## Detailed Setup

### Step 1: Virtual Environment

```bash
# Create isolated Python 3.11 environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Upgrade pip & install Poetry
pip install --upgrade pip poetry
```

### Step 2: Install Dependencies

```bash
# Install all dependencies (prod + dev)
poetry install --with dev

# Or, install only production dependencies
poetry install
```

### Step 3: Verify Installation

```bash
# Test imports
python -c "from meterhub_common import MeterReading, Heartbeat, DeviceConfig; print('✓ Common models')"
python -c "from meterhub_acq import main; print('✓ Acquisition service')"
python -c "from meterhub_uploader import main; print('✓ Uploader service')"
python -c "from meterhub_ui import app; print('✓ Installer UI')"
```

### Step 4: Setup Pre-commit Hooks (Optional but Recommended)

```bash
# Install pre-commit framework
pip install pre-commit

# Install hooks defined in .pre-commit-config.yaml
pre-commit install

# Manually run all hooks on all files (first time)
pre-commit run --all-files
```

**What pre-commit does on every commit:**
- ✅ Auto-formats code with Black
- ✅ Checks syntax with flake8
- ✅ Type-checks with mypy
- ✅ Security scans with bandit
- ⛔ Fails commit if issues found (can override with `git commit --no-verify`)

---

## Running Tests

### Unit Tests (Fast)

```bash
# Run all unit tests
pytest tests/ -v

# Run only acquisition tests
pytest acquisition/tests/ -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=html

# View coverage in browser
open htmlcov/index.html
```

### Integration Tests

```bash
# Run all tests marked as integration
pytest -m integration

# Run acquisition + uploader integration tests
pytest acquisition/tests/ uploader/tests/ -m integration -v
```

### Test Categories

```yaml
Unit Tests:
  - Fast (<100ms each)
  - Mock external dependencies (Modbus, MQTT, DB)
  - Run on every commit
  
Integration Tests:
  - Slower (1–5s each)
  - Use real SQLite (temp DB)
  - Use mock Modbus server (pymodbus simulator)
  - Run on PR submission

Fault Injection Tests:
  - Simulate power cuts, network outages
  - Verify data integrity
  - Run nightly

Soak Tests:
  - Run for 24+ hours
  - Monitor memory leaks, CPU creep
  - Run before release
```

---

## Code Quality Checks

### Formatting (Black)

```bash
# Auto-format all Python files
black acquisition uploader installer_ui common tests

# Check without modifying
black acquisition uploader installer_ui common tests --check
```

### Linting (Flake8)

```bash
# Check for style violations
flake8 acquisition uploader installer_ui common --max-line-length=100

# Show statistics
flake8 acquisition uploader installer_ui common --statistics --count
```

### Type Checking (Mypy)

```bash
# Strict type checking (enforced)
mypy acquisition uploader installer_ui common --strict --ignore-missing-imports

# Show per-file errors
mypy acquisition --strict --show-error-codes
```

### Security Scanning (Bandit)

```bash
# Scan for security issues
bandit -r acquisition uploader installer_ui common

# Output as JSON
bandit -r acquisition uploader installer_ui common -f json -o bandit-report.json
```

### All Checks at Once

```bash
# Run complete quality pipeline (as CI/CD does)
black --check acquisition uploader installer_ui common
flake8 acquisition uploader installer_ui common --max-line-length=100
mypy acquisition uploader installer_ui common --strict --ignore-missing-imports
bandit -r acquisition uploader installer_ui common
pytest tests/ --cov=.
```

---

## Running Services Locally

### Acquisition Service (Phase 2)

```bash
# Start acquisition service (stub, doesn't poll real meter yet)
python acquisition/meterhub_acq/main.py

# Logs go to console (development mode)
```

### Uploader Service (Phase 3)

```bash
# Requires: acquisition service running
# Start uploader service (stub, doesn't connect to cloud yet)
python uploader/meterhub_uploader/main.py
```

### Installer UI (Phase 4)

```bash
# Start FastAPI server
python -m uvicorn installer_ui.meterhub_ui.main:app --reload --host 0.0.0.0 --port 8080

# Browse to: http://localhost:8080
```

---

## Docker Development (Isolated Testing)

### Build Docker Image

```bash
docker build -t meterhub:dev .
```

### Run Tests in Docker

```bash
# Run entire test suite in container
docker run --rm meterhub:dev

# Run specific tests
docker run --rm meterhub:dev pytest acquisition/tests/ -v

# Interactive shell in container
docker run --rm -it meterhub:dev bash
```

---

## Environment Configuration

### Development .env

```bash
# Copy template
cp .env.example .env

# Edit for local development
nano .env  # or: open -a "Visual Studio Code" .env
```

**Key variables:**
```
METERHUB_ENV=development         # Dev vs. production
METERHUB_DEBUG=true              # Enable debug logging
METERHUB_DB_PATH=/tmp/meterhub-dev.sqlite   # Local DB
METERHUB_LOG_LEVEL=debug         # Verbose logging
```

---

## IDE Setup

### Visual Studio Code

**Extensions to install:**
- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Black Formatter (ms-python.black-formatter)
- Flake8 (ms-python.flake8)
- MyPy (ms-python.mypy-type-checker)

**Settings (.vscode/settings.json):**
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.linting.mypyEnabled": true,
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": ["--max-line-length=100"],
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": "explicit"
    }
  }
}
```

---

## File Structure During Development

```
meterhub/
├── venv/                     ← Python virtual environment (git-ignored)
├── acquisition/
│   ├── meterhub_acq/
│   │   ├── __init__.py      ← Package exports
│   │   ├── main.py          ← Entry point (Phase 2)
│   │   └── modbus_client.py ← Modbus logic (Phase 2)
│   └── tests/
├── uploader/
│   ├── meterhub_uploader/
│   │   ├── __init__.py
│   │   ├── main.py          ← Entry point (Phase 3)
│   │   ├── mqtt_uploader.py ← MQTT logic (Phase 3)
│   │   └── https_fallback.py ← HTTPS fallback (Phase 3)
│   └── tests/
├── installer_ui/
│   ├── meterhub_ui/
│   │   ├── __init__.py
│   │   ├── main.py          ← FastAPI app (Phase 4)
│   │   ├── routes/
│   │   └── templates/
│   └── tests/
├── common/
│   ├── meterhub_common/
│   │   ├── models.py        ← Data models (Phase 1 ✓)
│   │   ├── db.py            ← SQLite layer (Phase 2)
│   │   ├── config.py        ← Config loading
│   │   ├── logger.py        ← Structured logging
│   │   ├── modbus_profiles/ ← YAML loading
│   │   └── mqtt_client.py   ← MQTT wrapper
│   └── requirements.txt
├── tests/
│   ├── conftest.py          ← Pytest fixtures (Phase 1 ✓)
│   └── test_*.py            ← Integration tests
├── .github/workflows/
│   └── test.yml             ← CI/CD pipeline (Phase 1 ✓)
├── .env.example             ← Config template (Phase 1 ✓)
├── .pre-commit-config.yaml  ← Pre-commit hooks (Phase 1 ✓)
├── pyproject.toml           ← Dependencies (Phase 1 ✓)
└── README.md
```

---

## Common Development Tasks

### Add a New Dependency

```bash
# Add to project (updates pyproject.toml)
poetry add requests

# Add dev-only dependency
poetry add --group dev pytest-cov

# Update lock file
poetry lock
poetry install
```

### Bump Version

```bash
# Edit meterhub_version.py
nano meterhub_version.py

# Also update pyproject.toml
```

### Run Single Test File

```bash
pytest acquisition/tests/test_modbus_client.py::test_retry_backoff -v
```

### Debug Test with pdb

```bash
# Add breakpoint in test
import pdb; pdb.set_trace()

# Run with output capture disabled
pytest acquisition/tests/test_modbus.py -v -s
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'meterhub_common'"

**Solution:** Ensure you've run `poetry install` and activated venv:
```bash
# Recreate venv if needed
rm -rf venv/
poetry install
source venv/bin/activate
```

### "Black/flake8/mypy command not found"

**Solution:** Reinstall dev dependencies:
```bash
poetry install --with dev
```

### "Pre-commit hook failed"

**Solution:** Fix issues manually or see what changed:
```bash
# See detailed diff
black --check --diff acquisition/

# Auto-fix formatting
black acquisition/

# Re-attempt commit
git commit -m "message"
```

### Tests pass locally but fail in CI

**Solution:** Run the exact CI command locally:
```bash
# This is what GitHub Actions runs:
black --check acquisition uploader installer_ui common
flake8 acquisition uploader installer_ui common --max-line-length=100
mypy acquisition uploader installer_ui common --strict --ignore-missing-imports
pytest tests/ acquisition/tests/ uploader/tests/ -v --cov
```

---

## Next Steps

1. **Read CONTRIBUTING.md** — Code style guidelines and branch naming
2. **Read docs/ARCHITECTURE.md** — System design before diving into code
3. **Pick a Phase 2–6 task** — See README.md for build order
4. **Open a PR** — Include tests, docstrings, and type hints

---

**Questions?** Refer to [docs/QUICK_REFERENCE.md](../QUICK_REFERENCE.md) or reach out to the team.
