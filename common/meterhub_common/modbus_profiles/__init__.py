"""
Modbus Meter Profiles (YAML-based)

Meter-specific register definitions for Modbus RTU communication.
No code changes needed to support new meters: add YAML profile to /etc/meterhub/profiles/

Device loads profiles from /etc/meterhub/profiles/*.yaml dynamically at startup.
Cloud team can add new meter models without touching edge firmware.
"""

__all__: list[str] = []
