"""
MeterHub Common Utilities

Shared code for acquisition, uploader, installer UI, and OTA services.

Modules:
- models.py: Dataclass definitions (Reading, Heartbeat, etc.)
- meter_profile_schema.py: Modbus register schema and YAML loader
- modbus_client.py: Modbus RTU async client with retry
- sqlite_db.py: SQLite WAL integration, crash-safe storage
- aws_mqtt_client.py: AWS IoT Core MQTT client (TLS, QoS1)
- https_uploader.py: HTTPS fallback uploader (OAuth2)
- image_signer.py: Ed25519 image signing and verification
- mender_boot_manager.py: Mender A/B boot partition management
- db.py: SQLite WAL integration, schema, migrations
- config.py: Config loading from /etc/meterhub/
- secrets.py: Secrets management (device key, cloud token, etc.)
- logger.py: Unified structured logging
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

from .aws_mqtt_client import AWSIoTMQTTClient

from .https_uploader import HTTPSFallbackUploader

from .image_signer import ImageSigner

from .mender_boot_manager import MenderBootManager, BootPartition, BootState

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
    "AWSIoTMQTTClient",
    "HTTPSFallbackUploader",
    "ImageSigner",
    "MenderBootManager",
    "BootPartition",
    "BootState",
]
