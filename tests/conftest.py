"""
Pytest Configuration for MeterHub

Provides fixtures, test helpers, and configuration for all test suites.
"""

import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
        db_path = f.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
    if os.path.exists(f"{db_path}-wal"):
        os.remove(f"{db_path}-wal")
    if os.path.exists(f"{db_path}-shm"):
        os.remove(f"{db_path}-shm")


@pytest.fixture
def temp_config_dir():
    """Temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_meter_reading():
    """Sample meter reading for tests."""
    return {
        "timestamp_utc": "2026-04-28T14:55:00Z",
        "totalizer_kwh": 45678.234,
        "instant_kw": 12.45,
        "frequency_hz": 49.98,
        "voltage": {
            "l1_v": 230.5,
            "l2_v": 231.2,
            "l3_v": 229.8,
        },
        "current": {
            "l1_a": 15.3,
            "l2_a": 14.8,
            "l3_a": 15.1,
        },
        "power_factor": {
            "total": 0.98,
            "l1": 0.98,
            "l2": 0.98,
            "l3": 0.97,
        },
    }


@pytest.fixture
def mock_heartbeat():
    """Sample heartbeat payload for tests."""
    return {
        "device_id": "test-device-001",
        "society_id": "test-society",
        "panel_id": "test-panel-01",
        "timestamp_utc": "2026-04-28T14:55:00Z",
        "event_type": "heartbeat",
        "firmware_version": "1.0.0",
        "uptime_seconds": 86400,
        "system": {
            "cpu_percent": 8.5,
            "ram_mb": 150,
            "temperature_c": 52.3,
        },
        "meter": {
            "meter_online": True,
            "last_read_age_seconds": 0,
        },
    }


# Markers for test organization
def pytest_configure(config):
    """Register pytest markers."""
    config.addinivalue_line("markers", "unit: unit tests (fast, no I/O)")
    config.addinivalue_line("markers", "integration: integration tests (slower, may use files/DB)")
    config.addinivalue_line("markers", "fault_injection: power-loss and failure scenario tests")
    config.addinivalue_line("markers", "soak: long-running stability tests")
    config.addinivalue_line("markers", "slow: slow tests (>1 second)")
