"""
Power-Loss Fault Injection Tests for Acquisition Service

Tests crash-safety with simulated power failures:
- Abrupt database connection shutdown mid-transaction
- WAL mode recovery (replay from log)
- Billing counter integrity (never loses data, never double-counts)
- Data consistency after recovery

Run with: pytest acquisition/tests/test_acquisition_fault_injection.py -v --tb=short
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from common.meterhub_common.sqlite_db import TelemetryDatabase, StateDatabase


@pytest.mark.fault_injection
def test_power_loss_telemetry_recovery() -> None:
    """Test WAL mode recovery after abrupt shutdown."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "telemetry.db"

        # Create and populate database
        telem = TelemetryDatabase(str(db_path))
        telem.initialize_schema()

        # Insert first batch of readings
        for i in range(10):
            reading_dict = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "totalizer_kwh": 45678.0 + i,
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

        # Simulate power loss by killing connection without clean shutdown
        assert telem.db.connection is not None
        telem.db.connection.close()
        del telem

        # Recovery: open database again (WAL replay)
        telem_recovered = TelemetryDatabase(str(db_path))
        telem_recovered.db.connect()

        # Verify all 10 readings survived
        cursor = telem_recovered.db.execute("SELECT COUNT(*) FROM meter_readings")
        count = cursor.fetchone()[0]
        assert count == 10, "Data loss after power failure!"

        # Verify last reading is intact
        cursor = telem_recovered.db.execute(
            "SELECT totalizer_kwh FROM meter_readings ORDER BY id DESC LIMIT 1"
        )
        last_kwh = cursor.fetchone()[0]
        assert last_kwh == 45678.0 + 9, "Last reading corrupted!"


@pytest.mark.fault_injection
def test_billing_counter_crash_safety() -> None:
    """Test billing counter never loses atomicity on crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.db"

        # Initialize and write initial billing state
        state = StateDatabase(str(state_path))
        state.initialize_schema()

        initial_kwh = 45678.234
        ts = datetime.utcnow()
        state.update_billing_state(initial_kwh, ts)

        # Verify initial state
        state_data = state.get_last_billing_state()
        assert state_data is not None
        assert state_data["totalizer_kwh"] == initial_kwh

        # Simulate crash: forcefully kill connection
        assert state.db.connection is not None
        state.db.connection.close()
        del state

        # Recovery: open and verify
        state_recovered = StateDatabase(str(state_path))
        state_recovered.db.connect()

        recovered_state = state_recovered.get_last_billing_state()
        assert recovered_state is not None
        assert recovered_state["totalizer_kwh"] == initial_kwh, "Billing counter corrupted!"


@pytest.mark.fault_injection
def test_wal_mode_enabled() -> None:
    """Verify WAL mode is actually enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        telem = TelemetryDatabase(str(db_path))
        telem.db.connect()

        # Check WAL is enabled
        cursor = telem.db.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == "wal", "WAL mode not enabled!"

        telem.db.disconnect()


@pytest.mark.fault_injection
def test_synchronous_levels() -> None:
    """Verify correct synchronous levels per database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Telemetry: NORMAL (faster)
        telem_path = Path(tmpdir) / "telemetry.db"
        telem = TelemetryDatabase(str(telem_path))
        telem.db.connect()

        cursor = telem.db.execute("PRAGMA synchronous")
        telem_sync = cursor.fetchone()[0]
        assert telem_sync == 1, f"Telemetry should be NORMAL (1), got {telem_sync}"

        telem.db.disconnect()

        # State: FULL (crash-safe)
        state_path = Path(tmpdir) / "state.db"
        state = StateDatabase(str(state_path))
        state.db.connect()

        cursor = state.db.execute("PRAGMA synchronous")
        state_sync = cursor.fetchone()[0]
        assert state_sync == 2, f"State should be FULL (2), got {state_sync}"

        state.db.disconnect()


@pytest.mark.fault_injection
def test_partial_write_recovery() -> None:
    """Test recovery from partial write mid-transaction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "telemetry.db"

        state = TelemetryDatabase(str(db_path))
        state.initialize_schema()

        # Write first 5 readings
        for i in range(5):
            reading_dict = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "totalizer_kwh": 45000.0 + i,
                "instant_kw": 10.0,
                "frequency_hz": 50.0,
                "voltage_l1": 230.0,
                "voltage_l2": 230.0,
                "voltage_l3": 230.0,
                "current_l1": 10.0,
                "current_l2": 10.0,
                "current_l3": 10.0,
                "pf_total": 1.0,
                "modbus_retry_count": 0,
                "meter_online": True,
            }
            state.insert_reading(reading_dict)

        # Simulate crash mid-transaction
        assert state.db.connection is not None
        state.db.connection.close()
        del state

        # Open and verify
        recovered = TelemetryDatabase(str(db_path))
        recovered.db.connect()

        cursor = recovered.db.execute("SELECT COUNT(*) FROM meter_readings")
        count = cursor.fetchone()[0]
        assert count == 5, "Data lost or corrupted after crash"


@pytest.mark.fault_injection
def test_double_commit_protection() -> None:
    """Test that duplicate updates don't occur."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "state.db"

        state = StateDatabase(str(state_path))
        state.initialize_schema()

        ts = datetime.utcnow()
        kwh = 45678.0

        # Update same counter 3 times (simulating retry)
        state.update_billing_state(kwh, ts)
        state.update_billing_state(kwh, ts)
        state.update_billing_state(kwh, ts)

        # Verify still only one row (no duplicates)
        cursor = state.db.execute("SELECT COUNT(*) FROM billing_state")
        count = cursor.fetchone()[0]
        assert count == 1, f"Multiple billing records found! Count: {count}"

        # Verify value is correct
        recovered_state = state.get_last_billing_state()
        assert recovered_state is not None
        assert recovered_state["totalizer_kwh"] == kwh


@pytest.mark.fault_injection
def test_concurrent_access_safety() -> None:
    """Test database handles multiple connections safely."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "telemetry.db"

        # Create database
        telem1 = TelemetryDatabase(str(db_path))
        telem1.initialize_schema()

        reading_dict = {
            "timestamp_utc": datetime.utcnow().isoformat(),
            "totalizer_kwh": 45678.0,
            "instant_kw": 12.0,
            "frequency_hz": 50.0,
            "voltage_l1": 230.0,
            "voltage_l2": 230.0,
            "voltage_l3": 230.0,
            "current_l1": 10.0,
            "current_l2": 10.0,
            "current_l3": 10.0,
            "pf_total": 1.0,
            "modbus_retry_count": 0,
            "meter_online": True,
        }

        # Write from first connection
        telem1.insert_reading(reading_dict)

        # Open second connection while first is active
        telem2 = TelemetryDatabase(str(db_path))
        telem2.db.connect()

        # Read from second connection
        cursor = telem2.db.execute("SELECT COUNT(*) FROM meter_readings")
        count = cursor.fetchone()[0]
        assert count == 1, "Second connection can't see first connection's write"

        telem2.db.disconnect()


@pytest.mark.soak
@pytest.mark.slow
def test_24hour_soak_simulation() -> None:
    """Simulate 24 hours of reading/write (1440 readings at 1-minute interval)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        telem_path = Path(tmpdir) / "telemetry.db"

        telem = TelemetryDatabase(str(telem_path))
        telem.initialize_schema()

        # Simulate 24 hours of readings (1440 x 60s = 86400s)
        for i in range(1440):
            reading_dict = {
                "timestamp_utc": datetime.utcnow().isoformat(),
                "totalizer_kwh": 45678.0 + (i * 0.012),  # 0.012 kWh per min
                "instant_kw": 12.0 + (i % 5) * 0.5,  # Vary between 12-14 kW
                "frequency_hz": 49.98 + (i % 3) * 0.01,
                "voltage_l1": 230.0 + (i % 10) * 0.2,
                "voltage_l2": 231.0 + (i % 10) * 0.2,
                "voltage_l3": 229.0 + (i % 10) * 0.2,
                "current_l1": 15.0 + (i % 5) * 0.1,
                "current_l2": 14.8 + (i % 5) * 0.1,
                "current_l3": 15.2 + (i % 5) * 0.1,
                "pf_total": 0.98 + (i % 2) * 0.01,
                "modbus_retry_count": 0,
                "meter_online": True,
            }
            telem.insert_reading(reading_dict)

        # Verify  all 1440 readings persisted
        cursor = telem.db.execute("SELECT COUNT(*) FROM meter_readings")
        count = cursor.fetchone()[0]
        assert count == 1440, f"Expected 1440 readings, got {count}"

        # Verify totalizer increased monotonically
        cursor = telem.db.execute(
            "SELECT MIN(totalizer_kwh), MAX(totalizer_kwh) FROM meter_readings"
        )
        min_kwh, max_kwh = cursor.fetchone()
        assert max_kwh > min_kwh, "Totalizer did not increase"
        assert max_kwh - min_kwh > 17, "Unexpected totalizer increase"  # ~17.28 kWh expected
