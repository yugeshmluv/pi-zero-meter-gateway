"""
Unit tests for MeterHub data models.

Tests for dataclass validation and serialization.
"""

import pytest
from datetime import datetime
from common.meterhub_common.models import (
    MeterReading,
    Heartbeat,
    DeviceConfig,
    CloudPayload,
    OTAManifest,
    AuditLogEntry,
)
from common.meterhub_common.meter_profile_schema import MeterProfile


@pytest.mark.unit
def test_meter_reading_creation():
    """Test MeterReading dataclass instantiation."""
    reading = MeterReading(
        timestamp_utc=datetime(2026, 4, 28, 14, 55, 0),
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


@pytest.mark.unit
def test_heartbeat_creation():
    """Test Heartbeat dataclass instantiation."""
    hb = Heartbeat(
        device_id="test-device-001",
        society_id="test-society",
        panel_id="test-panel-01",
        timestamp_utc=datetime(2026, 4, 28, 14, 55, 0),
        firmware_version="1.0.0",
        uptime_seconds=86400,
        cpu_percent=8.5,
        ram_mb=150,
        temperature_c=52.3,
        disk_free_mb=500,
        mqtt_connected=True,
        queue_depth=0,
        last_meter_read_age_seconds=0,
        sd_writes_mb_today=45.2,
    )
    assert hb.device_id == "test-device-001"
    assert hb.mqtt_connected is True


@pytest.mark.unit
def test_device_config_creation():
    """Test DeviceConfig dataclass instantiation."""
    config = DeviceConfig(
        device_id="test-device-001",
        society_id="test-society",
        panel_id="test-panel-01",
        meter_address=1,
        meter_profile="schneider-em6400",
        cloud_endpoint="mqtt.aws-iot.example.com",
    )
    assert config.device_id == "test-device-001"
    assert config.polling_interval_seconds == 60  # default


@pytest.mark.unit
def test_cloud_payload_creation():
    """Test CloudPayload dataclass instantiation."""
    payload = CloudPayload(
        device_id="test-device-001",
        timestamp_utc=datetime(2026, 4, 28, 14, 55, 0),
        readings=[],
    )
    assert payload.device_id == "test-device-001"
    assert payload.heartbeat is None


@pytest.mark.unit
def test_ota_manifest_creation():
    """Test OTAManifest dataclass instantiation."""
    manifest = OTAManifest(
        version="1.0.1",
        timestamp_utc=datetime(2026, 4, 28, 14, 55, 0),
        package_url="https://example.com/v1.0.1.tar.gz",
        checksum_sha256="abc123",
        signature_ed25519="sig123",
        size_bytes=1024000,
    )
    assert manifest.version == "1.0.1"
    assert manifest.canary_delay_seconds == 0  # default


@pytest.mark.unit
def test_audit_log_entry_creation():
    """Test AuditLogEntry dataclass instantiation."""
    entry = AuditLogEntry(
        timestamp_utc=datetime(2026, 4, 28, 14, 55, 0),
        event_type="config_change",
        device_id="test-device-001",
    )
    assert entry.event_type == "config_change"
    assert entry.details == {}  # default


@pytest.mark.unit
def test_flow_meter_profile_loads():
    """Japsin electromagnetic flow meter profile loads with input registers."""
    profile = MeterProfile.from_yaml("profiles/japsin-jii-bhi-electromagnetic-flowmeter.yaml")

    assert profile.meter_type == "japsin-jii-bhi-electromagnetic-flowmeter"
    assert "flow_rate_m3_h" in profile.registers
    assert profile.registers["flow_rate_m3_h"].function_code == 4
    assert profile.registers["flow_rate_m3_h"].unit == "m3/h"
