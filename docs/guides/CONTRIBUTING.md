# Contributing to MeterHub

## Philosophy

MeterHub is built on a single core principle: **The GPIO device is dumb and reliable. All customer-facing intelligence lives in the cloud.**

Every feature addition must justify itself against this principle. Before you code:

1. **Is this logic in the right place?** Should it be in the cloud instead?
2. **Does it increase RAM/CPU/SD wear?** Performance budgets are strict.
3. **Can it break the meter polling loop?** Process isolation is non-negotiable.
4. **Have you tested it without power?** Crash-safety is mandatory.

## Development Setup

### Prerequisites

- Python 3.11+
- systemd
- SQLite 3.40+
- Git

### Install Development Environment

```bash
cd meterhub
./scripts/install-dev.sh
```

This installs:
- Python virtual environment
- Development dependencies for all three services
- Pre-commit hooks (code style, type checking)
- Test fixtures (pymodbus simulator, mock MQTT broker)

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with fault injection (power-loss scenarios)
pytest tests/test_fault_injection.py -v

# Run single test file
pytest tests/test_acquisition.py

# Generate coverage report
pytest tests/ --cov=meterhub_acq --cov=meterhub_uploader --cov=meterhub_common
```

### Testing Against Simulated Meter

```bash
# Terminal 1: Start pymodbus simulator (Schneider EM6400 profile)
python -m pymodbus.server --host 127.0.0.1 --port 5020

# Terminal 2: Run acquisition service in dev mode
python -m meterhub_acq --meter-address=127.0.0.1:5020 --profile=schneider-em6400 --log-level=debug
```

## Build Order (Do Not Deviate)

Follow the Phase structure in README.md strictly:

1. **Phase 1:** Architecture + BOM + API contract (complete)
2. **Phase 2:** Acquisition service
3. **Phase 3:** Uploader + cloud integration
4. **Phase 4:** Installer UI
5. **Phase 5:** OTA + provisioning
6. **Phase 6:** Hardening + image build

Each phase includes its own test suite. Don't move to the next phase until all tests pass.

## Code Style

### Python

- **Type hints:** Every function must have input/output type hints.
- **Linting:** `black` for formatting, `flake8` for style, `mypy` for static type checking.
- **Line Length:** 100 characters max.
- **Docstrings:** Google-style, including return type and side effects.

Pre-commit hook will run automatically on `git commit`. To check manually:

```bash
black meterhub_acq meterhub_uploader meterhub_common
flake8 meterhub_acq meterhub_uploader meterhub_common
mypy meterhub_acq meterhub_uploader meterhub_common
```

### Commit Messages

Format: `TYPE(scope): short description`

- `feat(acquisition)`: New feature in acquisition service
- `fix(uploader)`: Bug fix in uploader
- `test(all)`: Add / update tests
- `docs(provisioning)`: Documentation update
- `refactor(common)`: Code refactoring (no behavior change)

Example:
```
feat(acquisition): add retry with exponential backoff for Modbus timeouts

- Implement 3 retries with 100 ms → 500 ms → 2 s backoff
- Mark meter offline after 5 consecutive failures
- Report retry count in meter quality field

Closes #42
```

## Process-Specific Guidelines

### meterhub-acquisition

- **Single responsibility:** Read meter, write SQLite.
- **Asyncio-based:** Use `async`/`await`; no blocking calls.
- **No external I/O:** No HTTP, no MQTT, no cloud requests.
- **No user-facing secrets:** Configuration loaded from `/etc/meterhub/config.yml`.
- **Retention:** Always write cumulative totalizer + instantaneous values.

### meterhub-uploader

- **Primary path:** MQTT with TLS.
- **Fallback path:** HTTPS (triggered after 15 min MQTT failure).
- **Store-and-forward:** SQLite-backed queue; nothing lost on power cuts.
- **Not a web server:** No HTTP listen port. Passive outbound only.
- **Throttling:** Pause at 75°C, measured every minute.

### meterhub-installer-ui

- **Engineering tool only:** Not a customer product.
- **Minimal dependencies:** FastAPI + Jinja2 only. No Chart.js, React, Vue.
- **Plain HTML forms:** No JavaScript frameworks.
- **HTTPS only:** Auto-generate self-signed cert on first boot.
- **Auto-shutdown:** Wi-Fi AP mode off after 30 minutes.

## Testing Checklist

Every PR must include:

- [ ] Unit tests for new functions.
- [ ] Integration test (acquisition + SQLite, or uploader + queue).
- [ ] Test against pymodbus simulator (if Modbus-related).
- [ ] Manual test on actual Pi Zero W (if possible).
- [ ] Power-loss fault injection (if storage-related).
- [ ] Coverage report (target: >90% for critical paths).

Example test structure:

```python
def test_acquisition_meter_offline_after_5_failures():
    """Meter marked offline after 5 consecutive Modbus failures."""
    # Arrange
    mock_modbus = MagicMock()
    mock_modbus.read_registers = side_effect([Exception()] * 5)
    db = MemoryDatabase()
    
    # Act
    result = read_meter(mock_modbus, "schneider-em6400", db)
    
    # Assert
    assert result.offline is True
    assert db.get_meter_status().consecutive_failures == 5
```

## Database Schema Changes

SQLite schema is versioned. If you add/modify tables:

1. Update schema version in `common/meterhub_common/db.py`.
2. Write a migration function `migrate_v{N}_to_{N+1}()`.
3. Include data preservation logic (never drop columns without migration).
4. Test on a real device with populated DB (no data loss).
5. Document in [docs/DATABASE.md](../DATABASE.md).

## API Contract Changes

If you modify any of these, you **must** update [CLOUD_API_CONTRACT.md](../specifications/CLOUD_API_CONTRACT.md):

- MQTT payload schema (fields, types, units)
- Heartbeat format
- HTTPS fallback endpoints
- Error responses
- Authentication changes

Run the contract validation script:

```bash
python scripts/validate-cloud-contract.py
```

This ensures cloud team is never surprised.

## Security Checklist

Every feature must satisfy:

- [ ] No credentials in code; all secrets in `/etc/meterhub/secrets/`.
- [ ] All external I/O is TLS 1.2+ (MQTT, HTTPS).
- [ ] Payload signatures (Ed25519) where applicable.
- [ ] Audit log entry for user-facing actions (config change, login, OTA).
- [ ] No console output of secrets (even in debug mode).
- [ ] Meter data + admin email only; no resident PII on device.

## Performance Review

Before submitting a PR, benchmark against these targets:

- **CPU:** Run 24 h at polling interval, measure idle + peak during MQTT/SD writes.
- **RAM:** Check resident set size (RSS) and max heap.
- **SD writes:** Monitor `/sys/block/mmcblk0/stat` before/after test.

Example:

```bash
# In separate terminal, monitor every 10 seconds
watch -n 10 'ps aux | grep meterhub'

# Simultaneously run workload
python tests/test_soak_24h.py --duration=3600 --meter-interval=60

# Post-test, check SD wear
tail -1 /proc/diskstats | grep mmcblk0
```

If you exceed budgets, optimize: reduce logging verbosity, batch operations, defer non-critical work to cloud.

## Provisioning & QR Code

If you add setup fields:

1. Update [scripts/qr-provisioning.md](../../scripts/qr-provisioning.md) with new fields.
2. Update cloud provisioning API spec in [CLOUD_API_CONTRACT.md](../specifications/CLOUD_API_CONTRACT.md).
3. Update installer UI setup wizard form.
4. Test QR code generation: `python scripts/gen-qr-code.py --device-id=... --token=...`

## Meter Profile Authoring

New meter profiles (YAML) go in `profiles/`. See [METER_PROFILES.md](METER_PROFILES.md) for format.

**Do not hard-code register mappings in Python.** All meter definitions live in YAML.

Example: `profiles/schneider-em6400.yaml`

```yaml
meter_name: "Schneider Electric EM6400"
modbus_address: 1
protocol_version: "RTU"
registers:
  totalizer_kwh:
    address: 45568
    type: uint32_big_endian
    scale: 0.01
    unit: "kWh"
  instant_kw:
    address: 3520
    type: float32_big_endian
    unit: "kW"
  # ... more fields
```

## OTA Testing

Before publishing an OTA package:

1. Generate manifest: `./scripts/release-ota.sh v1.2.4 --dry-run`
2. Verify Ed25519 signature: `python scripts/verify-manifest.py manifest.json`
3. Test on physical Pi Zero W:
   - Manual upload via installer UI
   - Verify health check (meter read + heartbeat)
   - Verify rollback on health check failure

## Deployment Checklist (Before Release)

- [ ] All tests pass: `pytest tests/ --cov`
- [ ] Code review by 2+ team members
- [ ] Type checking: `mypy meterhub_* --strict`
- [ ] Linting: `black . && flake8 . --max-line-length=100`
- [ ] Security audit: `bandit -r meterhub_*/`
- [ ] OTA manifest signed and verified
- [ ] Canary deployment tested (if non-critical)
- [ ] Cloud API contract updated and validated
- [ ] Documentation updated

## Questions?

- **Architecture:** See [ARCHITECTURE.md](../ARCHITECTURE.md)
- **Commissioning:** See [COMMISSIONING.md](../COMMISSIONING.md)
- **Troubleshooting:** See [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
- **Cloud API:** See [CLOUD_API_CONTRACT.md](../specifications/CLOUD_API_CONTRACT.md)

**Golden Rule:** When in doubt, ask: "Does this make the device dumb-er or smarter?" If it's making it smarter, move it to the cloud.
