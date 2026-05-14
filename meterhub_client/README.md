# MeterHub Python Client SDK

**Version:** 1.0.0
**Python:** 3.8+

A simple, powerful Python client for interacting with MeterHub devices and cloud API.

---

## Installation

### From PyPI (coming soon)

```bash
pip install meterhub-client
```

### From source

```bash
git clone https://github.com/yugeshmluv/pi-zero-meter-gateway.git
cd pi-zero-meter-gateway
pip install -e meterhub_client/
```

### Dependencies

```bash
pip install aiohttp certifi
```

---

## Quick Start

### Async Usage (Recommended)

```python
import asyncio
from meterhub_client import MeterHubClient
from datetime import datetime, timedelta

async def main():
    # Connect to local device
    async with MeterHubClient(device_ip="192.168.1.100") as client:
        # Get current status
        status = await client.get_device_status()
        print(f"Device: {status.device_id}")
        print(f"Uptime: {status.uptime_seconds} seconds")
        print(f"Memory: {status.memory_mb:.1f} MB")
        print(f"WiFi: {status.wifi_signal_strength} dBm")

        # Get latest reading
        reading = await client.get_latest_reading()
        if reading:
            print(f"\nLatest Reading:")
            print(f"  Timestamp: {reading.timestamp_utc}")
            print(f"  Power: {reading.instant_kw} kW")
            print(f"  Frequency: {reading.frequency_hz} Hz")
            print(f"  Voltage L1: {reading.voltage_l1:.1f} V")

asyncio.run(main())
```

### Synchronous Usage

```python
from meterhub_client import MeterHubClientSync

# Connect to local device
client = MeterHubClientSync(device_ip="192.168.1.100")

# Get current status
status = client.get_device_status()
print(f"Device {status.device_id}: {status.uptime_seconds}s uptime")

# Get latest reading
reading = client.get_latest_reading()
if reading:
    print(f"Power: {reading.instant_kw} kW")

client.close()
```

---

## API Reference

### Connection Modes

#### Local Device Access (Direct)

Connect directly to a device on your network:

```python
client = MeterHubClient(
    device_ip="192.168.1.100",
    timeout_s=10.0
)
```

**Pros:**
- No authentication required
- Lowest latency
- Works even if cloud unreachable

**Cons:**
- Device must be on same network
- Only current status (no historical data in local mode)

#### Cloud API Access (Remote)

Connect via cloud API for remote access:

```python
client = MeterHubClient(
    cloud_api_url="https://api.meterhub.io/v1",
    device_id="meter-001",
    api_key="your-api-key-here",
    timeout_s=10.0
)
```

**Pros:**
- Access from anywhere
- Historical data available
- Multi-device management

**Cons:**
- Requires authentication
- Slightly higher latency
- Cloud must be online

### Core Methods

#### `get_device_status(use_cloud=False)`

Get current device health and status.

```python
status = await client.get_device_status()

print(f"Device: {status.device_id}")
print(f"Uptime: {status.uptime_seconds} seconds")
print(f"Memory: {status.memory_mb} MB")
print(f"CPU: {status.cpu_percent}%")
print(f"Temperature: {status.temperature_c}°C")
print(f"SD Free: {status.sd_free_mb} MB")
print(f"WiFi: {status.wifi_signal_strength} dBm")
print(f"MQTT Connected: {status.mqtt_connected}")
print(f"Queue Depth: {status.queue_depth} readings")
```

**Returns:** `DeviceStatus` object

**Raises:** `RuntimeError` on failure

---

#### `get_latest_reading(use_cloud=False)`

Get the most recent meter reading.

```python
reading = await client.get_latest_reading()

if reading:
    print(f"Timestamp: {reading.timestamp_utc}")
    print(f"Power: {reading.instant_kw} kW")
    print(f"Energy: {reading.totalizer_kwh} kWh")
    print(f"Frequency: {reading.frequency_hz} Hz")
    print(f"Voltage L1-L3: {reading.voltage_l1}, {reading.voltage_l2}, {reading.voltage_l3}")
    print(f"Current L1-L3: {reading.current_l1}, {reading.current_l2}, {reading.current_l3}")
    print(f"Power Factor: {reading.pf_total}")
else:
    print("No readings available yet")
```

**Returns:** `MeterReading` or `None`

---

#### `get_readings_range(start_time, end_time, limit=1000, use_cloud=False)`

Get readings within a time range.

```python
from datetime import datetime, timedelta

start = datetime.utcnow() - timedelta(hours=24)
end = datetime.utcnow()

readings = await client.get_readings_range(
    start_time=start,
    end_time=end,
    limit=1000,
    use_cloud=True  # Use cloud for historical data
)

print(f"Retrieved {len(readings)} readings")
for reading in readings:
    print(f"  {reading.timestamp_utc}: {reading.instant_kw} kW")
```

**Returns:** List of `MeterReading` objects

**Arguments:**
- `start_time`: Start datetime (UTC)
- `end_time`: End datetime (UTC)
- `limit`: Max readings to return (default: 1000)
- `use_cloud`: Use cloud API (cloud has more data)

---

#### `get_hourly_summary(date, use_cloud=False)`

Get hourly consumption breakdown for a specific day.

```python
hourly = await client.get_hourly_summary(
    date="2026-05-12",
    use_cloud=True
)

for hour in hourly:
    print(f"Hour {hour['hour']}: "
          f"{hour['energy_kwh']} kWh, "
          f"Peak {hour['peak_kw']} kW")
```

**Returns:** List of hourly summaries

---

#### `get_daily_consumption(date, use_cloud=False)`

Get daily consumption summary.

```python
daily = await client.get_daily_consumption(
    date="2026-05-12",
    use_cloud=True
)

if daily:
    print(f"Date: {daily.date}")
    print(f"Energy: {daily.energy_kwh} kWh")
    print(f"Peak: {daily.peak_power_kw} kW")
    print(f"Avg: {daily.avg_power_kw} kW")
    print(f"Uptime: {daily.uptime_percent}%")
    print(f"Offline: {daily.offline_duration_seconds}s")
else:
    print("No data for this date")
```

**Returns:** `DailyConsumption` or `None`

---

#### `check_ota_update(use_cloud=False)`

Check for available firmware updates.

```python
update = await client.check_ota_update(use_cloud=True)

if update:
    print(f"Update available: v{update['version']}")
    print(f"Release date: {update['release_date']}")
    print(f"Changelog: {update['changelog']}")
    print(f"Size: {update['size_mb']} MB")
else:
    print("No updates available")
```

**Returns:** Dict with update info or empty dict

---

#### `trigger_ota_update(version, use_cloud=False)`

Trigger a firmware update to a specific version.

```python
result = await client.trigger_ota_update(
    version="1.2.1",
    use_cloud=True
)

print(f"Update status: {result['status']}")
# status can be: "scheduled", "downloading", "installing", etc.
```

**Returns:** Dict with update status

**Important:** Update is non-blocking; check status with `check_ota_update()`

---

#### `get_system_logs(lines=100, service=None, use_cloud=False)`

Get device logs.

```python
# Get last 50 lines from all services
logs = await client.get_system_logs(lines=50)

for line in logs:
    print(line)

# Or get logs from specific service
acq_logs = await client.get_system_logs(
    lines=100,
    service="meterhub-acquisition"
)
```

**Returns:** List of log lines

**Service names:**
- `meterhub-acquisition` - Meter polling
- `meterhub-uploader` - Cloud sync
- `meterhub-installer-ui` - Web UI
- `system` - System logs
- `None` - All services

---

#### `export_readings_csv(start_time, end_time, output_path, use_cloud=False)`

Export readings to CSV file.

```python
from datetime import datetime, timedelta

start = datetime.utcnow() - timedelta(days=7)
end = datetime.utcnow()

await client.export_readings_csv(
    start_time=start,
    end_time=end,
    output_path="readings.csv",
    use_cloud=True
)

print("Exported to readings.csv")
```

**CSV Format:**
```
timestamp_utc,totalizer_kwh,instant_kw,frequency_hz,...
2026-05-12T12:00:00,1234.56,2.34,50.0,...
2026-05-12T12:01:00,1234.62,2.35,50.0,...
```

---

## Data Models

### `MeterReading`

```python
@dataclass
class MeterReading:
    timestamp_utc: datetime
    totalizer_kwh: float        # Cumulative kWh
    instant_kw: float          # Current power draw
    frequency_hz: float         # Grid frequency (50/60)
    voltage_l1: float          # Phase 1 voltage
    voltage_l2: float          # Phase 2 voltage
    voltage_l3: float          # Phase 3 voltage
    current_l1: float          # Phase 1 current
    current_l2: float          # Phase 2 current
    current_l3: float          # Phase 3 current
    pf_total: float            # Power factor
    meter_online: bool         # Is meter responding
```

### `DeviceStatus`

```python
@dataclass
class DeviceStatus:
    device_id: str
    uptime_seconds: int
    memory_mb: float           # Current memory usage
    cpu_percent: float         # CPU usage 0-100
    temperature_c: float       # CPU temperature
    sd_free_mb: int           # Free SD card space
    wifi_signal_strength: int  # Signal in dBm (-30 to -90)
    mqtt_connected: bool       # Cloud connection status
    last_reading_timestamp: Optional[datetime]
    queue_depth: int          # Pending cloud uploads
    last_cloud_sync: Optional[datetime]
```

### `DailyConsumption`

```python
@dataclass
class DailyConsumption:
    date: str                  # YYYY-MM-DD
    energy_kwh: float         # Total daily consumption
    peak_power_kw: float      # Max instantaneous power
    avg_power_kw: float       # Average power
    min_power_kw: float       # Min instantaneous power
    max_power_kw: float       # Max instantaneous power
    uptime_percent: float     # % of day device was online
    offline_duration_seconds: int  # Time offline
```

---

## Authentication

### API Key (Cloud)

For cloud API access, obtain an API key from your MeterHub account:

```python
client = MeterHubClient(
    cloud_api_url="https://api.meterhub.io/v1",
    device_id="meter-001",
    api_key="sk_live_abc123def456..."
)
```

### SSL Verification

To disable SSL verification (not recommended for production):

```python
client = MeterHubClient(
    device_ip="192.168.1.100",
    verify_ssl=False  # UNSAFE for cloud!
)
```

---

## Error Handling

```python
from meterhub_client import MeterHubClient

try:
    async with MeterHubClient(device_ip="192.168.1.100") as client:
        status = await client.get_device_status()
except RuntimeError as e:
    print(f"API Error: {e}")
except asyncio.TimeoutError:
    print("Request timed out")
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Examples

### Monitor Real-Time Power

```python
import asyncio
from meterhub_client import MeterHubClient

async def monitor_power():
    async with MeterHubClient(device_ip="192.168.1.100") as client:
        while True:
            reading = await client.get_latest_reading()
            if reading:
                print(f"Power: {reading.instant_kw:.2f} kW "
                      f"@ {reading.timestamp_utc.strftime('%H:%M:%S')}")
            await asyncio.sleep(5)

asyncio.run(monitor_power())
```

### Check Device Health

```python
async with MeterHubClient(device_ip="192.168.1.100") as client:
    status = await client.get_device_status()

    if status.temperature_c > 50:
        print("⚠️  WARNING: High temperature!")

    if status.sd_free_mb < 100:
        print("⚠️  WARNING: Low SD card space!")

    if not status.mqtt_connected:
        print("⚠️  WARNING: Cloud disconnected!")

    if status.queue_depth > 1000:
        print("⚠️  WARNING: Large sync queue!")
```

### Export Daily Report

```python
from datetime import datetime, timedelta

async def export_daily_report(date_str: str):
    async with MeterHubClient(
        cloud_api_url="https://api.meterhub.io/v1",
        device_id="meter-001",
        api_key="your-api-key"
    ) as client:
        # Get daily summary
        daily = await client.get_daily_consumption(date_str, use_cloud=True)

        if daily:
            print(f"=== Report for {daily.date} ===")
            print(f"Energy: {daily.energy_kwh:.2f} kWh")
            print(f"Peak: {daily.peak_power_kw:.2f} kW")
            print(f"Average: {daily.avg_power_kw:.2f} kW")
            print(f"Uptime: {daily.uptime_percent:.1f}%")

        # Export readings to CSV
        start = datetime.strptime(date_str, "%Y-%m-%d")
        end = start + timedelta(days=1)

        await client.export_readings_csv(
            start_time=start,
            end_time=end,
            output_path=f"report_{date_str}.csv",
            use_cloud=True
        )
```

---

## Testing

```bash
# Run unit tests
pytest meterhub_client/tests/

# Run with coverage
pytest --cov=meterhub_client meterhub_client/tests/
```

---

## Support

- **Documentation:** https://docs.meterhub.io/sdk/python
- **Issues:** https://github.com/yugeshmluv/pi-zero-meter-gateway/issues
- **Email:** support@meterhub.io

---

## License

Proprietary © 2026 MeterHub Team
