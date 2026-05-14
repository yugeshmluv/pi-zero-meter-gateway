"""
Unit tests for MeterHub Acquisition Service.

Tests:
- Meter profile loading from YAML
- Modbus client register reading
- SQLite data persistence (non-power-loss cases)
- Service initialization and cleanup

Note: Power-loss and fault injection tests in test_acquisition_fault_injection.py
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from common.meterhub_common import (
    MeterProfile,
    MeterReading,
    DataType,
)
from common.meterhub_common.sqlite_db import TelemetryDatabase, StateDatabase
from acquisition.meterhub_acq.main import AcquisitionService


@pytest.mark.unit
def test_meter_profile_load() -> None:
    """Test loading Schneider EM6400 profile."""
    profile = MeterProfile.from_yaml("profiles/schneider-em6400.yaml")
    assert profile.meter_type == "Schneider EM6400"
    assert profile.manufacturer == "Schneider Electric"
    assert profile.baud_rate == 9600
    assert "totalizer_kwh" in profile.registers
    assert "instant_kw" in profile.registers


@pytest.mark.unit
def test_meter_profile_registers() -> None:
    """Test registers are properly defined."""
    profile = MeterProfile.from_yaml("profiles/schneider-em6400.yaml")

    # Check critical billing register
    totalizer = profile.registers["totalizer_kwh"]
    assert totalizer.name == "totalizer_kwh"
    assert totalizer.unit == "kWh"
    assert totalizer.read_only is True
    assert totalizer.data_type == DataType.FLOAT32

    # Check power register
    instant_kw = profile.registers["instant_kw"]
    assert instant_kw.unit == "kW"
    assert instant_kw.data_type == DataType.FLOAT32


@pytest.mark.unit
def test_meter_reading_creation() -> None:
    """Test MeterReading dataclass creation."""
    reading = MeterReading(
        timestamp_utc=datetime(2026, 5, 10, 14, 55, 0),
        totalizer_kwh=45678.234,
        instant_kw=12.45,
        frequency_hz=49.98,
        voltage_l1=230.5,
        voltage_l2=231.2,
        voltage_l3=229.8,
        current_l1=15.3,
        current_l2=14.8,
        current_l3=15.1,
        pf_total=0.98,
    )

    assert reading.totalizer_kwh == 45678.234
    assert reading.instant_kw == 12.45
    assert reading.meter_online is True
    assert reading.modbus_retry_count == 0


@pytest.mark.unit
def test_telemetry_database_init() -> None:
    """Test telemetry database initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        telem = TelemetryDatabase(str(db_path))
        telem.initialize_schema()

        # Check tables exist
        assert telem.db.connection is not None
        cursor = telem.db.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "meter_readings" in tables
        assert "heartbeats" in tables


@pytest.mark.unit
def test_telemetry_database_insert() -> None:
    """Test inserting meter readings into database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        telem = TelemetryDatabase(str(db_path))
        telem.initialize_schema()

        # Insert reading
        reading_dict = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "totalizer_kwh": 45678.234,
            "instant_kw": 12.45,
            "frequency_hz": 49.98,
            "voltage_l1": 230.5,
            "voltage_l2": 231.2,
            "voltage_l3": 229.8,
            "current_l1": 15.3,
            "current_l2": 14.8,
            "current_l3": 15.1,
            "pf_total": 0.98,
            "modbus_retry_count": 0,
            "meter_online": True,
        }
        telem.insert_reading(reading_dict)

        # Verify inserted
        assert telem.db.connection is not None
        cursor = telem.db.connection.execute("SELECT COUNT(*) FROM meter_readings")
        count = cursor.fetchone()[0]
        assert count == 1


@pytest.mark.unit
def test_state_database_billing() -> None:
    """Test billing state persistence."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "state.db"

        state = StateDatabase(str(db_path))
        state.initialize_schema()

        # Insert billing state
        timestamp = datetime.utcnow()
        state.update_billing_state(45678.234, timestamp)

        # Verify
        state_data = state.get_last_billing_state()
        assert state_data is not None
        assert state_data["totalizer_kwh"] == 45678.234


@pytest.mark.unit
def test_acquisition_service_init() -> None:
    """Test service initialization."""
    service = AcquisitionService(
        meter_profile_path="profiles/schneider-em6400.yaml",
        ttydevice="/dev/ttyUSB0",
        polling_interval_s=60,
    )

    assert service.ttydevice == "/dev/ttyUSB0"
    assert service.polling_interval == 60
    assert service.read_count == 0
    assert service.error_count == 0


@pytest.mark.unit
def test_acquisition_profile_load() -> None:
    """Test acquisition service profile loading."""
    service = AcquisitionService(meter_profile_path="profiles/schneider-em6400.yaml")

    assert service._load_profile()
    assert service.meter_profile is not None
    assert service.meter_profile.meter_type == "Schneider EM6400"
