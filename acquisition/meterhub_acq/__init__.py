"""
MeterHub Acquisition Service

asyncio-based Modbus RTU polling service for 3-phase electrical meters.
Writes raw meter readings to SQLite database.

No external I/O (HTTP, MQTT): only Modbus reads and SQLite writes.

Phase 2 Implementation:
- Modbus RTU client with 3-retry exponential backoff
- Meter profile YAML loader (no hardcoded registers)
- SQLite WAL integration (crash-safe)
- CPU <10% average, <30% peak
- RAM <40 MB
Mode: systemd service, restarts on failure
"""

__version__ = "1.0.0"
__all__ = ["main"]
