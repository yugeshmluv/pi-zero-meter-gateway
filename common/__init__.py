"""
MeterHub Common Package

Shared utilities for all MeterHub services.

Modules:
- models.py: Dataclass definitions
- meter_profile_schema.py: Modbus register schema
- modbus_client.py: Modbus RTU client
- sqlite_db.py: SQLite crash-safe storage
- aws_mqtt_client.py: AWS IoT Core MQTT client
- https_uploader.py: HTTPS fallback uploader
- image_signer.py: Ed25519 image signing
- mender_boot_manager.py: A/B boot partitions
"""

__version__ = "1.0.0"
