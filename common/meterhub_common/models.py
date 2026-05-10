"""
Common Data Models for MeterHub

Dataclasses for readings, heartbeats, configurations, etc.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class MeterReading:
    """Single meter reading (1 minute)."""
    
    timestamp_utc: datetime
    totalizer_kwh: float
    instant_kw: float
    frequency_hz: float
    voltage_l1: float
    voltage_l2: float
    voltage_l3: float
    current_l1: float
    current_l2: float
    current_l3: float
    pf_total: float
    modbus_retry_count: int = 0
    meter_online: bool = True


@dataclass
class Heartbeat:
    """Device heartbeat (sent every 5 min)."""
    
    device_id: str
    society_id: str
    panel_id: str
    timestamp_utc: datetime
    firmware_version: str
    uptime_seconds: int
    cpu_percent: float
    ram_mb: int
    temperature_c: float
    disk_free_mb: int
    mqtt_connected: bool
    queue_depth: int
    last_meter_read_age_seconds: int
    sd_writes_mb_today: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceConfig:
    """Device configuration."""
    
    device_id: str
    society_id: str
    panel_id: str
    meter_address: str
    meter_profile: str
    cloud_endpoint: str
    fallback_email_recipient: Optional[str] = None
    polling_interval_seconds: int = 60


@dataclass
class CloudPayload:
    """Batched cloud upload payload (5-minute batch)."""
    
    device_id: str
    timestamp_utc: datetime
    readings: list  # List[MeterReading]
    heartbeat: Optional['Heartbeat'] = None
    signature: Optional[str] = None  # Ed25519


@dataclass
class OTAManifest:
    """OTA update manifest."""
    
    version: str
    timestamp_utc: datetime
    package_url: str
    checksum_sha256: str
    signature_ed25519: str
    size_bytes: int
    rollback_version: Optional[str] = None
    canary_delay_seconds: int = 0


@dataclass
class AuditLogEntry:
    """Audit trail for configuration changes, logins, OTA events."""
    
    timestamp_utc: datetime
    event_type: str  # config_change, login, ota_start, ota_complete, etc.
    device_id: str
    user_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
