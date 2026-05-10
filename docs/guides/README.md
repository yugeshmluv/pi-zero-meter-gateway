# Development Guides & References

Complete guides for developers contributing to MeterHub across all phases.

## Quick Links

- **[DEV_SETUP.md](DEV_SETUP.md)** — Development environment setup (Read first!)
  - Python 3.11+ virtual environment
  - Poetry dependency management
  - Pre-commit hooks & code quality
  - Running tests locally
  - Docker for isolated testing
  
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Contribution guidelines
  - Code style (Black, Flake8, Mypy)
  - Branch naming & commit messages
  - Testing requirements
  - Deployment checklist
  
- **[METER_PROFILES.md](METER_PROFILES.md)** — Meter Profile Authoring
  - YAML schema for new meters
  - Register mapping & scaling
  - Commissioning checklist

- **[INSTALLATION.md](INSTALLATION.md)** — Installation & Setup
  - System setup instructions
  - Hardware integration

## Getting Started (5 Steps)

1. **Clone & Setup** → Run `./scripts/install-dev.sh` (see [DEV_SETUP.md](DEV_SETUP.md))
2. **Environment** → Copy `.env.example` to `.env` and customize
3. **Dependencies** → Run `poetry install --with dev`
4. **Pre-commit** → Run `pre-commit install` (auto-format on commit)
5. **Tests** → Run `pytest tests/ -v` to verify setup

## Code Quality Standards

| Tool | Purpose | Command |
|------|---------|---------|
| **Black** | Formatting | `black --check acquisition uploader installer_ui common` |
| **Flake8** | Linting | `flake8 acquisition uploader installer_ui common --max-line-length=100` |
| **Mypy** | Type checking | `mypy acquisition uploader installer_ui common --strict` |
| **Bandit** | Security | `bandit -r acquisition uploader installer_ui common` |
| **Pytest** | Testing | `pytest tests/ -v --cov` |

**All checks must pass before PR merge!**

## Build Order (Phases)

1. ✅ **Phase 1** (Complete) - Architecture, specs, scaffolding
2. ⏳ **Phase 2** - Acquisition service (Modbus polling)
3. ⏳ **Phase 3** - Uploader service (MQTT + HTTPS)
4. ⏳ **Phase 4** - Installer UI (FastAPI web)
5. ⏳ **Phase 5** - OTA updates & provisioning
6. ⏳ **Phase 6** - Image builder & hardening

See [README.md](../../README.md) for detailed phase scopes.

## Services at a Glance

| Service | Port | Scope | Status |
|---------|------|-------|--------|
| **Acquisition** | N/A (local) | Modbus polling → SQLite | Phase 2 |
| **Uploader** | N/A (local) | SQLite → Cloud (MQTT/HTTPS) | Phase 3 |
| **Installer UI** | 8443 | Web UI for commissioning | Phase 4 |

All run as systemd services on the Pi.

## Testing Strategy

```
Unit Tests         → Fast, mocked, on every commit
Integration Tests  → Slower, real SQLite, on PR
Fault Injection    → Power cuts, network outages, pre-release
Soak Tests         → 24+ hours, monitor stability, pre-release
```

See [DEV_SETUP.md](DEV_SETUP.md) for detailed test execution.

---

**Start here:** [DEV_SETUP.md](DEV_SETUP.md) ← Complete development environment guide
5. Phase 5 - OTA updates
6. Phase 6 - Image builder & hardening

Each phase has its own test suite. Don't move forward until tests pass.
