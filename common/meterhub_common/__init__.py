"""
MeterHub Common Utilities

Shared code for acquisition, uploader, and installer UI services.

Modules:
- models.py: Dataclass definitions (Reading, Heartbeat, etc.)
- db.py: SQLite WAL integration, schema, migrations
- config.py: Config loading from /etc/meterhub/
- secrets.py: Secrets management (device key, cloud token, etc.)
- logger.py: Unified structured logging
- modbus_profiles.py: YAML meter profile loader
- mqtt_client.py: MQTT TLS wrapper (with callback handling)
"""

from .models import (
    MeterReading,
    Heartbeat,
    DeviceConfig,
    CloudPayload,
    OTAManifest,
    AuditLogEntry,
)

__version__ = "1.0.0"
__all__ = [
    "MeterReading",
    "Heartbeat",
    "DeviceConfig",
    "CloudPayload",
    "OTAManifest",
    "AuditLogEntry",
]
