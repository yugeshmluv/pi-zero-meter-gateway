"""
MeterHub Client SDK

Python library for interacting with MeterHub devices and cloud API.

Examples:
    Async usage:
        async with MeterHubClient(device_ip="192.168.1.100") as client:
            status = await client.get_device_status()
            reading = await client.get_latest_reading()

    Sync usage:
        client = MeterHubClientSync(device_ip="192.168.1.100")
        status = client.get_device_status()
        reading = client.get_latest_reading()
        client.close()
"""

__version__ = "1.0.0"
__author__ = "MeterHub Team"

from .client import (
    MeterHubClient,
    MeterHubClientSync,
    MeterReading,
    DeviceStatus,
    DailyConsumption,
)

__all__ = [
    "MeterHubClient",
    "MeterHubClientSync",
    "MeterReading",
    "DeviceStatus",
    "DailyConsumption",
]
