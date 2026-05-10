"""MeterHub Uploader Service

MQTT primary, HTTPS fallback store-and-forward service.
Batches 5-minute readings and uploads to cloud.

Handles network outages with 7-day queue survivability.

Phase 3 Implementation:
- MQTT TLS client (HiveMQ Cloud or AWS IoT Core)
- 5-min batch aggregation from readings DB
- HTTPS fallback with exponential backoff (1m -> 5m -> 30m -> 1h)
- SQLite-backed queue (survives 7-day outages)
- Ed25519 message signing
- Heartbeat every 5 min (device health metrics)
Mode: systemd service, depends-on acquisition service
"""

__version__ = "1.0.0"
__all__ = ["main"]
