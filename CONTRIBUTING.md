# Contributing to MeterHub

Welcome to the MeterHub project! This guide explains how to contribute code, tests, and documentation.

---

## Development Setup

### Prerequisites
- Python 3.11+
- Poetry (dependency management)
- Git

### Initial Setup

```bash
git clone https://github.com/yugeshmluv/pi-zero-meter-gateway.git
cd pi-zero-meter-gateway
poetry install
```

### Activate Environment
```bash
poetry shell
```

---

## Code Organization

**Project Structure:**
```
acquisition/          → Modbus polling service
uploader/             → Cloud connectivity service
installer_ui/         → Web provisioning UI
common/               → Shared utilities
ota/                  → Over-the-air update manager
build/                → Image builder & security hardening
profiles/             → Meter Modbus definitions
docs/                 → Documentation
tests/                → Root-level tests
```

**Each service follows:**
- `service/meterhub_service/main.py` — Service entry point
- `service/meterhub_service/<modules>.py` — Implementation
- `service/tests/test_<module>.py` — Unit tests
- `service/requirements.txt` — Dependencies (optional, use pyproject.toml)

---

## Code Style Guidelines

### Python Standards

**1. Import Order**
```python
# Standard library
import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, Optional

# Third-party
import pytest
import yaml

# Local
from common.meterhub_common import MeterReading
```

**2. Type Hints (Required)**
```python
# ✓ Good
async def read_meter(device_path: str, timeout_s: int = 5) -> MeterReading:
    pass

# ✗ Bad
async def read_meter(device_path, timeout_s=5):
    pass
```

**3. Docstrings (Required)**
```python
def validate_reading(reading: MeterReading) -> bool:
    """
    Validate meter reading for sanity.
    
    Args:
        reading: MeterReading instance to validate
        
    Returns:
        True if valid, False otherwise
        
    Raises:
        ValueError: If timestamp is in future
    """
    pass
```

### Formatting

**Use Black:**
```bash
black .
```

**Use Flake8 (linting):**
```bash
flake8 . --max-line-length=100 --ignore=E203,W503
```

**Use Mypy (type checking):**
```bash
mypy . --strict --ignore-missing-imports
```

**Use Bandit (security):**
```bash
bandit -r . -ll
```

---

## Testing Requirements

### Unit Tests (Required)

All new code must include unit tests.

**Location:** `service/tests/test_module.py`

**Naming Convention:**
- Test files: `test_*.py`
- Test classes: `Test*` (e.g., `TestAcquisition`)
- Test methods: `test_*` (e.g., `test_modbus_connect`)

**Example:**
```python
import pytest
from acquisition.meterhub_acq.modbus_client import ModbusRTUClient

class TestModbusClient:
    """Modbus RTU client tests."""
    
    @pytest.mark.asyncio
    async def test_connect_success(self):
        """Test successful Modbus connection."""
        client = ModbusRTUClient(device="/dev/ttyUSB0", slave_id=1)
        success = await client.connect()
        assert success is True
        
    def test_invalid_device_path(self):
        """Test error handling for invalid device."""
        with pytest.raises(FileNotFoundError):
            client = ModbusRTUClient(device="/dev/invalid", slave_id=1)
```

### Test Coverage

Minimum coverage per module:
- Acquisition: 80%
- Uploader: 75%
- Installer UI: 70%
- Common utilities: 85%
- OTA manager: 80%

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest acquisition/tests/test_acquisition.py -v

# Run async tests
pytest -m asyncio acquisition/tests/
```

---

## Making a Contribution

### 1. Create a Feature Branch
```bash
git checkout -b feature/meter-profile-schneider
```

### 2. Make Changes
- Write code with type hints
- Add/update docstrings
- Write unit tests
- Run formatters and linters

### 3. Run CI/CD Locally
```bash
# Format code
black .

# Lint
flake8 .

# Type check
mypy .

# Security check
bandit -r .

# Run tests
pytest
```

### 4. Commit with Clear Messages
```bash
git commit -m "feat(phase5): Add Schneider EM6400 meter profile

- Support 3-phase CT readings via Modbus RTU
- Registers: voltage (L1-L3), current (L1-L3), power, frequency
- YAML definition with validation
- Unit tests with mock data"
```

**Commit Format:**
```
<type>(<scope>): <description>

<body (optional, detailed explanation)>

<footer (optional, related issues)>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `test`: Test addition/modification
- `docs`: Documentation
- `refactor`: Code restructuring
- `perf`: Performance improvement

**Scopes:**
- `acquisition`: Modbus polling service
- `uploader`: Cloud connectivity
- `installer_ui`: Web UI
- `common`: Shared utilities
- `ota`: Update manager
- `build`: Image builder
- `ci`: CI/CD configuration
- `docs`: Documentation

### 5. Push and Create Pull Request
```bash
git push origin feature/meter-profile-schneider
```

Then create a PR on GitHub with a clear description.

---

## Documentation Guidelines

### Code Documentation
- Docstrings for all public functions/classes
- Type hints on all parameters/returns
- Examples in docstrings for complex logic

### Markdown Documentation
- Clear section headings (# ## ###)
- Code examples with language tags
- Table of contents for long documents
- Links to related docs

### Architecture Decisions
Document in `docs/` with:
- Problem statement
- Proposed solution
- Trade-offs considered
- Implementation details

---

## Common Issues & Solutions

**Issue: Tests fail locally but pass in CI**
- Solution: Ensure dependencies are installed (`poetry install`)
- Check Python version (`python --version` should be 3.11+)

**Issue: Type checking errors**
- Solution: Use `mypy --show-error-codes` for details
- Add type: ignore comments only with justification

**Issue: Import errors in tests**
- Solution: Ensure `__init__.py` exists in package directories
- Run tests with `pytest` not `python -m pytest`

---

## Review Process

All PRs require:
- ✅ Tests passing (CI/CD)
- ✅ Code review (maintainer)
- ✅ Documentation updated
- ✅ No security issues (Bandit)

---

## Questions?

- **Documentation:** Check [docs/](docs/) directory
- **Architecture:** See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Issues:** Open a GitHub Issue

---

## License

By contributing, you agree that your contributions will be licensed under the project's Proprietary License.

---

**Happy coding! 🚀**
