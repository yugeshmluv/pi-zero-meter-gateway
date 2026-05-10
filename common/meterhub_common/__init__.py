"""
MeterHub Common Utilities

Shared code for acquisition, uploader, and installer UI services.

Modules:
- models.py: Dataclass definitions (Reading, Heartbeat, etc.)
- meter_profile_schema.py: Modbus register schema and YAML loader
- modbus_client.py: Modbus RTU async client with retry
- db.py: SQLite WAL integration, schema, migrations
- config.py: Config loading from /etc/meterhub/
- secrets.py: Secrets management (device key, cloud token, etc.)
- logger.py: Unified structured logging
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

from .meter_profile_schema import (
    MeterProfile,
    ModbusRegister,
    DataType,
)

from .modbus_client import ModbusRTUClient, ModbusRegisterValue

__version__ = "1.0.0"
__all__ = [
    "MeterReading",
    "Heartbeat",
    "DeviceConfig",
    "CloudPayload",
    "OTAManifest",
    "AuditLogEntry",
    "MeterProfile",
    "ModbusRegister",
    "DataType",
    "ModbusRTUClient",
    "ModbusRegisterValue",
]
