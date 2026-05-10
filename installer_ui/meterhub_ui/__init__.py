"""MeterHub Installer UI

FastAPI-based web interface for device commissioning and status monitoring.
No JavaScript framework (plain Jinja2 + minimal CSS).

Runs on 192.168.4.1:8443 (self-signed HTTPS) in Wi-Fi AP mode during setup.

Phase 4 Implementation:
- FastAPI + Uvicorn HTTPS server
- Self-signed certificate auto-generation
- Setup wizard (society ID, panel, meter profile)
- Meter test page (live Modbus read with results)
- Status pages (CPU, RAM, disk, queue depth)
- OTA update interface
- Factory reset confirmation
- Installer login (bcrypt)
- Auto-shutdown after 30 min on Wi-Fi AP
Mode: systemd service, 8443 port, 80 CPU max
"""

__version__ = "1.0.0"
__all__ = ["app"]
