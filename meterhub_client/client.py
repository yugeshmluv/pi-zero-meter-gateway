"""
MeterHub Python Client SDK

Provides easy access to MeterHub devices for:
- Reading real-time meter data
- Retrieving historical readings
- Device configuration and management
- OTA update management
- Cloud status monitoring

Usage:
    from meterhub_client import MeterHubClient

    client = MeterHubClient(device_ip="192.168.1.100")
    readings = client.get_latest_readings()
    print(f"Current power: {readings.instant_kw} kW")
"""

import asyncio
import json
import ssl
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import logging

import aiohttp
import certifi

logger = logging.getLogger(__name__)


@dataclass
class MeterReading:
    """Single meter reading."""

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
    pf_total: float = 0.98
    meter_online: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MeterReading":
        """Create from dictionary."""
        return cls(
            timestamp_utc=datetime.fromisoformat(data["timestamp_utc"]),
            totalizer_kwh=data["totalizer_kwh"],
            instant_kw=data["instant_kw"],
            frequency_hz=data["frequency_hz"],
            voltage_l1=data.get("voltage_l1", 0.0),
            voltage_l2=data.get("voltage_l2", 0.0),
            voltage_l3=data.get("voltage_l3", 0.0),
            current_l1=data.get("current_l1", 0.0),
            current_l2=data.get("current_l2", 0.0),
            current_l3=data.get("current_l3", 0.0),
            pf_total=data.get("pf_total", 0.98),
            meter_online=data.get("meter_online", True),
        )


@dataclass
class DeviceStatus:
    """Device health status."""

    device_id: str
    uptime_seconds: int
    memory_mb: float
    cpu_percent: float
    temperature_c: float
    sd_free_mb: int
    wifi_signal_strength: int  # dBm (-30 to -90)
    mqtt_connected: bool
    last_reading_timestamp: datetime | None
    queue_depth: int  # Pending uploads
    last_cloud_sync: datetime | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceStatus":
        """Create from dictionary."""
        return cls(
            device_id=data["device_id"],
            uptime_seconds=data["uptime_seconds"],
            memory_mb=data["memory_mb"],
            cpu_percent=data["cpu_percent"],
            temperature_c=data.get("temperature_c", 0.0),
            sd_free_mb=data["sd_free_mb"],
            wifi_signal_strength=data.get("wifi_signal_strength", -50),
            mqtt_connected=data["mqtt_connected"],
            last_reading_timestamp=(
                datetime.fromisoformat(data["last_reading_timestamp"])
                if data.get("last_reading_timestamp")
                else None
            ),
            queue_depth=data["queue_depth"],
            last_cloud_sync=(
                datetime.fromisoformat(data["last_cloud_sync"])
                if data.get("last_cloud_sync")
                else None
            ),
        )


@dataclass
class DailyConsumption:
    """Daily consumption summary."""

    date: str  # YYYY-MM-DD
    energy_kwh: float
    peak_power_kw: float
    avg_power_kw: float
    min_power_kw: float
    max_power_kw: float
    uptime_percent: float
    offline_duration_seconds: int


class MeterHubClient:
    """
    Python client for MeterHub devices.

    Supports both direct device access (local network) and
    cloud API access (remote monitoring).
    """

    def __init__(
        self,
        device_ip: str | None = None,
        cloud_api_url: str | None = None,
        device_id: str | None = None,
        api_key: str | None = None,
        timeout_s: float = 10.0,
        verify_ssl: bool = True,
    ):
        """
        Initialize MeterHub client.

        Args:
            device_ip: Local device IP (for direct access)
            cloud_api_url: Cloud API endpoint (for remote access)
            device_id: Device identifier
            api_key: API key for authentication
            timeout_s: Request timeout in seconds
            verify_ssl: Verify SSL certificates

        Raises:
            ValueError: If neither device_ip nor cloud_api_url is provided
            TypeError: If device_ip is not a string
        """
        # Validate configuration: need at least one access method
        if not device_ip and not cloud_api_url:
            raise ValueError(
                "Either 'device_ip' (for direct access) or 'cloud_api_url' "
                "(for cloud access) must be configured"
            )

        # Type validation
        if device_ip and not isinstance(device_ip, str):
            raise TypeError(f"device_ip must be string, got {type(device_ip)}")
        if cloud_api_url and not isinstance(cloud_api_url, str):
            raise TypeError(f"cloud_api_url must be string, got {type(cloud_api_url)}")

        self.device_ip = device_ip
        self.cloud_api_url = cloud_api_url or "https://api.meterhub.io/v1"
        self.device_id = device_id
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self.verify_ssl = verify_ssl
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure HTTP session is initialized."""
        if self._session is None or self._session.closed:
            connector_kwargs = {}
            if not self.verify_ssl:
                connector_kwargs["ssl"] = ssl.create_default_context()
                connector_kwargs["ssl"].check_hostname = False
                connector_kwargs["ssl"].verify_mode = ssl.CERT_NONE

            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=aiohttp.TCPConnector(**connector_kwargs),
            )
        return self._session

    async def close(self) -> None:
        """Close the client session."""
        if self._session:
            await self._session.close()

    async def _get_device_url(self, endpoint: str) -> str:
        """Build device URL."""
        if not self.device_ip:
            raise ValueError("device_ip not configured for direct access")
        return f"http://{self.device_ip}:5000{endpoint}"

    async def _get_cloud_url(self, endpoint: str) -> str:
        """Build cloud API URL."""
        if not self.device_id:
            raise ValueError("device_id not configured for cloud access")
        return f"{self.cloud_api_url}/devices/{self.device_id}{endpoint}"

    async def get_device_status(self, use_cloud: bool = False) -> DeviceStatus:
        """
        Get current device status.

        Args:
            use_cloud: Use cloud API (True) or direct access (False)

        Returns:
            Device status
        """
        session = await self._ensure_session()

        url = (
            await self._get_cloud_url("/status")
            if use_cloud
            else await self._get_device_url("/api/status")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to get status: {resp.status}")
            data = await resp.json()
            return DeviceStatus.from_dict(data)

    async def get_latest_reading(self, use_cloud: bool = False) -> MeterReading | None:
        """
        Get the latest meter reading.

        Args:
            use_cloud: Use cloud API or direct access

        Returns:
            Latest reading or None if no data available
        """
        session = await self._ensure_session()

        url = (
            await self._get_cloud_url("/readings/latest")
            if use_cloud
            else await self._get_device_url("/api/readings/latest")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, headers=headers) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise RuntimeError(f"Failed to get reading: {resp.status}")
            data = await resp.json()
            return MeterReading.from_dict(data)

    async def get_readings_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
        use_cloud: bool = False,
    ) -> list[MeterReading]:
        """
        Get readings within a time range.

        Args:
            start_time: Start timestamp (UTC)
            end_time: End timestamp (UTC)
            limit: Maximum readings to return
            use_cloud: Use cloud API or direct access

        Returns:
            List of readings
        """
        session = await self._ensure_session()

        params = {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "limit": limit,
        }

        url = (
            await self._get_cloud_url("/readings")
            if use_cloud
            else await self._get_device_url("/api/readings")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to get readings: {resp.status}")
            data = await resp.json()
            return [MeterReading.from_dict(r) for r in data.get("readings", [])]

    async def get_hourly_summary(
        self,
        date: str,  # YYYY-MM-DD
        use_cloud: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get hourly consumption summary for a day.

        Args:
            date: Date in YYYY-MM-DD format
            use_cloud: Use cloud API or direct access

        Returns:
            List of hourly summaries
        """
        session = await self._ensure_session()

        url = (
            await self._get_cloud_url(f"/summary/hourly/{date}")
            if use_cloud
            else await self._get_device_url(f"/api/summary/hourly?date={date}")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to get summary: {resp.status}")
            data = await resp.json()
            return data.get("hourly", [])

    async def get_daily_consumption(
        self,
        date: str,  # YYYY-MM-DD
        use_cloud: bool = False,
    ) -> DailyConsumption | None:
        """
        Get daily consumption summary.

        Args:
            date: Date in YYYY-MM-DD format
            use_cloud: Use cloud API or direct access

        Returns:
            Daily consumption or None if no data
        """
        session = await self._ensure_session()

        url = (
            await self._get_cloud_url(f"/summary/daily/{date}")
            if use_cloud
            else await self._get_device_url(f"/api/summary/daily?date={date}")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, headers=headers) as resp:
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise RuntimeError(f"Failed to get summary: {resp.status}")
            data = await resp.json()
            return DailyConsumption(**data)

    async def check_ota_update(self, use_cloud: bool = False) -> dict[str, Any]:
        """
        Check for available OTA updates.

        Args:
            use_cloud: Use cloud API or direct access

        Returns:
            Update info or empty dict if no updates
        """
        session = await self._ensure_session()

        url = (
            await self._get_cloud_url("/ota/check")
            if use_cloud
            else await self._get_device_url("/api/ota/check")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, headers=headers) as resp:
            if resp.status == 204:  # No update available
                return {}
            if resp.status != 200:
                raise RuntimeError(f"Failed to check OTA: {resp.status}")
            data = await resp.json()
            return data

    async def trigger_ota_update(
        self,
        version: str,
        use_cloud: bool = False,
    ) -> dict[str, Any]:
        """
        Trigger OTA update to specific version.

        Args:
            version: Target version (e.g., "1.2.1")
            use_cloud: Use cloud API or direct access

        Returns:
            OTA status
        """
        session = await self._ensure_session()

        payload = {"version": version}

        url = (
            await self._get_cloud_url("/ota/update")
            if use_cloud
            else await self._get_device_url("/api/ota/update")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status not in [200, 202]:
                raise RuntimeError(f"Failed to trigger OTA: {resp.status}")
            data = await resp.json()
            return data

    async def get_system_logs(
        self,
        lines: int = 100,
        service: str | None = None,
        use_cloud: bool = False,
    ) -> list[str]:
        """
        Get system logs.

        Args:
            lines: Number of log lines
            service: Specific service to query (None = all)
            use_cloud: Use cloud API or direct access

        Returns:
            List of log lines
        """
        session = await self._ensure_session()

        params = {"lines": lines}
        if service:
            params["service"] = service

        url = (
            await self._get_cloud_url("/logs")
            if use_cloud
            else await self._get_device_url("/api/logs")
        )

        headers = {}
        if self.api_key and use_cloud:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with session.get(url, params=params, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Failed to get logs: {resp.status}")
            data = await resp.json()
            return data.get("logs", [])

    async def export_readings_csv(
        self,
        start_time: datetime,
        end_time: datetime,
        output_path: str,
        use_cloud: bool = False,
    ) -> None:
        """
        Export readings to CSV file.

        Args:
            start_time: Start timestamp
            end_time: End timestamp
            output_path: Path to save CSV
            use_cloud: Use cloud API or direct access
        """
        readings = await self.get_readings_range(
            start_time, end_time, limit=10000, use_cloud=use_cloud
        )

        import csv

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp_utc",
                    "totalizer_kwh",
                    "instant_kw",
                    "frequency_hz",
                    "voltage_l1",
                    "voltage_l2",
                    "voltage_l3",
                    "current_l1",
                    "current_l2",
                    "current_l3",
                    "pf_total",
                ],
            )
            writer.writeheader()
            for reading in readings:
                row = asdict(reading)
                row["timestamp_utc"] = reading.timestamp_utc.isoformat()
                writer.writerow(row)

        logger.info(f"Exported {len(readings)} readings to {output_path}")


# Synchronous wrapper for convenience
class MeterHubClientSync:
    """Synchronous wrapper around async MeterHubClient."""

    def __init__(self, *args, **kwargs):
        """Initialize sync client."""
        self._client = MeterHubClient(*args, **kwargs)
        self._loop: asyncio.AbstractEventLoop | None = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def get_device_status(self, use_cloud: bool = False) -> DeviceStatus:
        """Get device status (synchronous)."""
        loop = self._get_loop()
        return loop.run_until_complete(self._client.get_device_status(use_cloud=use_cloud))

    def get_latest_reading(self, use_cloud: bool = False) -> MeterReading | None:
        """Get latest reading (synchronous)."""
        loop = self._get_loop()
        return loop.run_until_complete(self._client.get_latest_reading(use_cloud=use_cloud))

    def get_readings_range(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
        use_cloud: bool = False,
    ) -> list[MeterReading]:
        """Get readings in range (synchronous)."""
        loop = self._get_loop()
        return loop.run_until_complete(
            self._client.get_readings_range(start_time, end_time, limit=limit, use_cloud=use_cloud)
        )

    def close(self) -> None:
        """Close client."""
        if self._loop:
            self._loop.run_until_complete(self._client.close())


if __name__ == "__main__":
    # Example usage
    import asyncio

    async def main():
        # Example 1: Direct device access
        async with MeterHubClient(device_ip="192.168.1.100") as client:
            status = await client.get_device_status()
            print(f"Device {status.device_id}: {status.uptime_seconds}s uptime")

            reading = await client.get_latest_reading()
            if reading:
                print(f"Latest: {reading.instant_kw} kW at {reading.timestamp_utc}")

        # Example 2: Cloud API access
        async with MeterHubClient(
            cloud_api_url="https://api.meterhub.io/v1",
            device_id="meter-001",
            api_key="your-api-key",
        ) as client:
            yesterday = datetime.utcnow() - timedelta(days=1)
            readings = await client.get_readings_range(
                start_time=yesterday, end_time=datetime.utcnow(), use_cloud=True
            )
            print(f"Got {len(readings)} readings from cloud")

    asyncio.run(main())
