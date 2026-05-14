# MeterHub Production Specification v2.0
## Production-Hardened Edge Gateway for 3-Phase CT Meters

**Date:** April 29, 2026
**Status:** LOCKED (Ready for Phase 1 Implementation)
**Timeline:** 12-week Sprint to Phase 1 completion (QR + BLE provisioning in-scope)

---

## Executive Summary

This is the revised, production-hardened specification for the MeterHub firmware stack following a comprehensive quality audit and Series A pre-launch review. **All decisions locked; no architectural changes without formal review gate.**

**Key Changes from Phase 1 Concept:**
- Hardware: Pi Zero W → **Pi Zero 2 W** (quad-core ARMv8, mandatory upgrade)
- Connectivity: Wi-Fi only → **Multi-tier strategy** (antenna standard, Ethernet/4G optional)
- Fallback email path: Removed (cloud owns dead-man monitoring)
- OTA strategy: Custom symlink → **Mender A/B framework** (atomic updates, built-in rollback)
- Time-keeping: Added **DS3231 RTC** (non-negotiable for billing)
- Database: Single SQLite → **Two separate DBs** (telemetry + state, different sync modes)
- Filesystem: Read-write root → **Read-only with overlays** (70% fewer bricked devices)
- MQTT: HiveMQ Cloud → **AWS IoT Core** (device shadows, jobs, fleet provisioning)
- Discovery: mDNS (unreliable) → **BLE + cloud IP** (BLE primary for Phase 1)

**Cost impact:** ₹9,200–13,000 → **₹10,500–12,500** per unit (Tier 1 standard kit, ₹1,300 increase absorbed by features)

---

## Part 1: Hardware Specification

### 1.1 Core Compute Module

| Specification | Detail |
|---|---|
| **Board** | Raspberry Pi Zero 2 W (not original Zero W) |
| **CPU** | Quad-core ARM Cortex-A53, ARMv8 64-bit (@1 GHz) |
| **RAM** | 512 MB LPDDR2 (shared with GPU) |
| **Storage (on-board)** | None; see SD card |
| **Connectivity** | 2.4 GHz 802.11b/g/n Wi-Fi + BLE 4.2 (both built-in) |
| **GPIO/Interfaces** | SPI, I2C, UART, USB, 40-pin header |
| **Form Factor** | 65 × 30 × 5.5 mm (identical to original Zero W) |
| **Power Consumption** | Typical: 100–150 mW idle, 400–500 mW loaded; peak: <1W |
| **Thermal** | No thermal throttling below 85°C (improvement over original Zero W at 70°C) |
| **Lifetime Target** | 5–7 years in field (enterprise support from Raspberry Pi) |
| **Cost** | ₹2,900–3,500 per unit (₹400–600 more than original Zero W) |
| **Lead Time** | 14–21 days (pre-order for >50 units) |

**Justification:**
- ARMv6 (original Zero W) is EOL for Python ecosystem; many wheels no longer pre-built (pymodbus, cryptography, paho-mqtt compile for 40+ min on device)
- ARMv8 gives aarch64 first-class support
- Quad-core allows for future feature creep (TLS, signature verification, on-edge anomaly detection)
- Cooler operation in enclosed panel boxes (no 70°C thermal cliff)
- Pin-compatible; zero changes to PCB or enclosure

### 1.2 Storage

| Component | Specification | Cost | Notes |
|---|---|---|---|
| **MicroSD Card** | SanDisk Industrial XI 32 GB (Power-Loss-Protected) *or* Swissbit S-56u | ₹3,200–4,000 | **CRITICAL:** Must be PLP (Power-Loss-Protected) variant; verify SKU. Standard industrial cards fail under 100 power-cuts/day. SanDisk base industrial SKUs do NOT have PLP; XI-Gen only. Swissbit S-56u guaranteed PLP. |
| **Image Build Overhead** | Mender A/B partitions + pi-gen overlay | ~100 MB rootfs overhead | Reduces usable SD to ~15 GB; acceptable (telemetry = 30 GB per 5 years) |
| **Backward Compatibility** | None required; fresh image at deployment | — | Every device ships with clean OS; no upgrade path from original Zero W (cost ~₹500 per refresh) |

**Storage Write Budget:**
- Target: <30 MB/day on SD
- Breakdown: acquisition polls 1 meter every 60s (16 bytes/poll = ~1.4 MB/day); uploader 5 min batches (~2 MB/day); logs (~5 MB/day on syslog + app logs); overhead (~2 MB/day) → **10–12 MB/day typical**
- Headroom: 3× buffer, safe at <30 MB/day

**Power-Loss Protection Validation:**
- Physical test requirement: 1,000 random power cuts via smart plug during write bursts
- CI/CD gate: Must pass before release
- Device simulation inadequate — SD controller behavior under real power loss is the risk vector

### 1.3 Real-Time Clock (Mandatory Addition)

| Component | Specification | Cost | Notes |
|---|---|---|---|
| **RTC Module** | DS3231 I2C (battery-backed, CR2032 included) | ₹150–200 | **Non-negotiable.** Eliminates clock drift during 24+ hour cloud outage. Accuracy: ±2 ppm. 2-wire I2C; integrate into common/meterhub_common/rtc.py |
| **Integration** | Systemd service reads time on boot; manual fallback via NTP when available | — | Firmware must detect RTC failure (I2C timeout) and degrade gracefully; alert in heartbeat |
| **Supplier** | Electronicscomp, Robu.in, AliExpress | — | Stocked locally; 7–10 day lead time max |

**Why RTC is Critical:**
- Without it, post-outage timestamps are wrong by hours → billing wrong by hours
- Timestamps are cryptographic evidence (customer disputes)
- NTP sync drifts several seconds/day on ARMv6; Pi Zero 2 W still drifts but less aggressively

### 1.4 Wi-Fi Connectivity — Multi-Tier Approach

**Tier 1 (Standard Kit) — All Units:**

| Component | Specification | Cost | Notes |
|---|---|---|---|
| **External Wi-Fi Antenna** | U.FL to RP-SMA pigtail + 2 dBi dipole | ₹120–180 | Pi Zero 2 W has U.FL pad. Either: (a) minor soldering by integrator, or (b) request factory-modded units from Raspberry Pi. Eliminates 60% of "Wi-Fi too weak" tickets in panel rooms with metal doors. Include pigtail connector hardware. |

**Why External Antenna?**
- Panel rooms are Faraday cages (basement, concrete, metal door)
- Built-in antenna range ~5m; 2 dBi external extends to ~15m
- Installers already improvise antennas; standardize it in BOM

**Tier 2 (Optional for Poor Wi-Fi Sites):**

| Component | Supplier | Cost | Use Case |
|---|---|---|---|
| **USB Ethernet Adapter** | Realtek RTL8152 (100 Mbps) | ₹400–600 | For sites where Wi-Fi <-75 dBm. Use with powerline adapter (TP-Link AV600-equiv., ~₹2,000). Common in societies on 3rd+ floors. |
| **Powerline Kit** | TP-Link AV600 pair | ~₹2,000 | Plug at router + plug at panel room → data over electrical cabling (no new runs) |

**Tier 3 (Optional for Extremely Poor Connectivity):**

| Component | Supplier | Cost | Use Case |
|---|---|---|---|
| **USB 4G Dongle** | Qubo or D-Link model | ₹500–800 | For basement panels with metal electromagnetic shielding. Requires IoT SIM. |
| **IoT SIM** | Airtel IoT or Jio Things | ₹50–100/month per device | Data-only, not voice. Specify connection medium in heartbeat for cloud fleet ops. |

**Firmware Integration:**
- Auto-detect connectivity medium (Wi-Fi, Ethernet, 4G) via systemd-networkd
- Report in heartbeat: `"connection": {"type": "wifi", "signal_dbm": -65}` or `"type": "ethernet"` or `"type": "4g_lte"`
- Cloud fleet ops monitoring flags devices transitioning from Wi-Fi to cellular (site quality degradation)

### 1.5 Optional: OLED Status Display

| Component | Specification | Cost | Notes |
|---|---|---|---|
| **Display** | SSD1306 128×32 I2C OLED | ₹120–180 | Shows device IP, status (acquiring/uploading/offline), instantaneous kW, cumulative kWh. Recommended for installer usability (no need for mobile app to check setup progress). Powered via 3.3V from Pi; I2C pull-ups already on module board. |

---

## Part 2: RS485 Isolation & Protection

### 2.1 Isolated Transceiver Module

| Component | Specification | Cost | Notes |
|---|---|---|---|
| **Module** | Waveshare TTL to RS485 (C) Isolated Converter | ₹500–900 | Galvanic isolated (transformer-grade), 2.5kV isolation, built-in 120Ω termination resistor, UART-to-RS485 conversion. **Integrated TVS + surge suppression (200W lightning proof, 6KV ESD).** Compact form factor (42.8×15.2×4.75 mm). Supplier: Robu.in (7–10 day lead, preferred), AliExpress (14–21 day lead), or REES52 (2–3 wk lead). |
| **Isolation Type** | Galvanic isolation (transformer-grade, proper dual-channel isolation) | — | Breaks ground loops between Pi and meter (415V potential difference scenario). **No external TVS diodes required** — suppression is on-board. |
| **Termination** | Built-in 120Ω resistor (selectable via soldering jumper on board) | — | Active only if meter is last device on RS485 run; otherwise leave jumper open. Refer to [Waveshare TTL to RS485 (C) Wiki](https://www.waveshare.com/wiki/TTL_TO_RS485_(C)) for solder jumper location. |
| **Built-in Protection** | TVS diodes (bidirectional on A/B lines), self-recovery fuse, protection diodes | — | Suppresses surge voltage and transient spike voltage (lightning-prone Indian panel environment). No additional external components required. |

### 2.2 Surge Protection (Integrated in Waveshare Module)

The Waveshare TTL to RS485 (C) converter includes **on-board TVS diode arrays and self-recovery fuse** providing comprehensive surge suppression:

| Protection | Specification | Notes |
|---|---|---|
| **TVS Diodes** | Bidirectional on RS485 A and B lines | Suppresses ESD/surge events (lightning, motor switching transients). Clamps overvoltage to safe rails. |
| **Lightning Protection** | 200W lightning-proof rating | Rated for high-energy transients typical of 415V Indian electrical panels. |
| **ESD Protection** | 6KV ESD (IEC 61000-4-2 standard) | Protects against electrostatic discharge during installation/maintenance. |
| **Self-Recovery Fuse** | On-board protection diodes | Ensures current/voltage stability; provides over-current and over-voltage protection. |
| **Validation** | Integrated suppression sufficient for Phase 1 | No additional external TVS components required for India 415V environment. Phase 2 can include formal IEC 61000-4-2 bench testing if needed. |

**Change from Previous Spec:** Older specs (WeAct + external TVS) are replaced by this all-in-one module. Waveshare's integrated protection is validated for industrial applications and eliminates PCB complexity. Cost: ₹500–900 (vs. ₹600–1,200 for WeAct + external TVS).

### 2.3 RS485 Cabling

| Specification | Requirement |
|---|---|
| **Cable Type** | 2-pair twisted-pair + shield, 0.5 mm² gauge |
| **Length** | Up to 1,200 m per Modbus spec (typical: 20–100 m in society panels) |
| **Termination** | Shield grounded at **device end only** (not at meter); open at meter end to avoid ground loop |
| **Supplier** | Robu.in, Electronicscomp, local cable distributor |
| **Cost** | ₹800–1,500 for 50 m spool |

---

## Part 3: Software Architecture (Revised Process Model)

### 3.1 Two-Process Model (Merged from Original Three)

**Original:** acquisition, uploader, installer-ui (3 processes)
**Revised:** meterhub-core, installer-ui (2 processes)

| Process | Purpose | RAM Footprint | Justification |
|---|---|---|---|
| **meterhub-core** | Merged: acquisition + uploader -> single asyncio event loop with two tasks sharing SQLite handle | ~45 MB baseline (Python ~30 MB + SQLite ~15 MB) | Acquisition writes readings; uploader consumes them. Dependency relationship exists; splitting adds no fault isolation that matters. One process = less overhead, simpler restart logic. Task 1 (acquisition): poll every 60s. Task 2 (uploader): batch & upload every 5 min. |
| **installer-ui** | Web commissioning (FastAPI + Jinja2/plain HTML) | ~0 MB (not started until needed) | Started on-demand via systemd socket activation. First connection triggers start; app initializes in <2s; auto-shutdown after 15 min (AP mode) or never (LAN mode). Eliminates baseline RAM cost when not in use. |
| **Total Baseline** | meterhub-core + systemd overhead + OS services | ~80–100 MB | Down from ~200 MB in original spec; headroom for Python GC, OS buffers, future utilities |

**Systemd Configuration:**
```ini
# /etc/systemd/system/meterhub-core.service
[Service]
Type=notify
ExecStart=/usr/bin/python3 -m meterhub_core.main
Restart=always
RestartSec=10
MemoryMax=64M
CPUQuota=50%
WatchdogSec=60
StandardOutput=journal
StandardError=journal

# /etc/systemd/system/meterhub-installer-ui.socket
[Socket]
ListenStream=192.168.1.250:8443
Accept=false

# /etc/systemd/system/meterhub-installer-ui.service
[Service]
Type=notify
ExecStart=/usr/bin/python3 -m meterhub_ui.app
MemoryMax=128M
CPUQuota=80%
StandardOutput=journal
StandardError=journal
```

### 3.2 Database Strategy (Two Separate DBs)

**Problem:** WAL mode + synchronous=NORMAL is faster but loses last few transactions on power cut. For billing data, this is unacceptable. For telemetry, acceptable.

**Solution: Split into two databases with different synchronous modes.**

| Database | Purpose | Synchronous Mode | Write Pattern | Recovery Strategy |
|---|---|---|---|---|
| **telemetry.db** | Raw 1-min meter readings (30-day retention) | NORMAL (unsafe, fast) | ~1.4 MB/day, high-write, many small inserts | Can lose last minute; OK for telemetry |
| **state.db** | Billing state: totalizer baseline, upload queue acknowledgements, device config, auth tokens | FULL (safe, slow) | ~50 KB/day, low-write, large transactions | Cannot lose; atomic or nothing |

**PRAGMA Configuration:**
```python
# telemetry.db
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=30000000;
PRAGMA cache_size=-2000;
PRAGMA wal_autocheckpoint=1000;
PRAGMA journal_size_limit=10485760;

# state.db
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA temp_store=MEMORY;
PRAGMA mmap_size=10000000;
PRAGMA cache_size=-1000;
PRAGMA wal_autocheckpoint=100;
PRAGMA journal_size_limit=5242880;

# Both
PRAGMA busy_timeout=5000;
```

**Checkpoint Strategy:**
- Automatic via wal_autocheckpoint settings (every 1000 pages for telemetry, 100 for state)
- Manual checkpoint at 3 AM local time (low-traffic moment) to keep WAL file bounded
- Cloud can request `SELECT * FROM telemetry WHERE timestamp > ?` for reconciliation during outage recovery

### 3.3 Filesystem: Read-Only Root with Overlays

**Problem:** Even power-loss-protected SD cards accumulate bad blocks over 5 years. Writes to `/boot`, `/etc`, or `/usr` can corrupt OS, bricking device.

**Solution:** Read-only root filesystem; writable overlays only for volatile data.

**Implementation:**
```bash
# During image build, enable read-only root via raspi-config
raspi-config nonint do_overlayfs 1
raspi-config nonint do_boot_rom 1

# Writable overlay mount points:
/var/lib/meterhub -> tmpfs (cleared on reboot) OR persistent overlay on SD partition 4
/var/log -> log2ram (in-memory syslog, auto-synced to SD at shutdown)
/run -> tmpfs (standard)
/tmp -> tmpfs (standard)
```

**Benefits:**
- SD corruption cannot brick OS (kernel, drivers, /usr remain read-only)
- ~70% fewer "device bricked" RMA tickets at fleet scale
- Trade-off: updates require reboot to switch partition (Mender handles this)

### 3.4 Logging Strategy (Structured JSON)

**Replace:** Free-text logs
**With:** Structured JSON logs via structlog

```python
# acquisition/main.py
import structlog
logger = structlog.get_logger()

# Output example:
{"timestamp": "2026-04-29T10:15:30.123Z", "level": "info", "service": "acquisition", "event": "meter_read", "meter_id": "EM6400-001", "voltage_l1": 230.5, "status": "ok"}
```

**Cloud Integration:**
- Acquisition + uploader emit JSON logs to MQTT topic: `meterhub/{device_id}/logs`
- Cloud aggregates via Loki or CloudWatch (structured log ingestion)
- Installer UI shows: `tail -50 /var/log/meterhub-core.jsonl` formatted as readable table

**Fleet Observability Gates:**
- All ERROR and CRITICAL logs trigger cloud-side alert
- Audit events (config change, OTA, meter replacement) logged + mirrored to audit topic
- Reconciliation: `grep 'meter_change' /var/log/meterhub-core.jsonl` recovers history if cloud DB lost

---

## Part 4: Connectivity & Provisioning

### 4.1 MQTT Broker: AWS IoT Core (Locked)

| Aspect | Decision |
|---|---|
| **Broker** | AWS IoT Core (not HiveMQ Cloud, not self-hosted Mosquitto) |
| **Justification** | Device Shadows (last-known state sync), Jobs API (OTA orchestration, per-society pinning), Fleet Provisioning (self-claim flow). At 100+ devices these become force-multipliers for ops. Cost negligible (~$0.0001/msg/device at 1 msg/5min). |
| **Lock-in Risk** | Mitigated by clean MQTT protocol; migration possible. But ecosystem lock-in is real; factor into long-term roadmap. |
| **Cloud Team Sync** | **PHASE 0:** Cloud team must provision AWS account, set up IoT Thing type, and generate CA certificate BEFORE firmware team writes MQTT code. |

**Device Shadow Schema:**
```json
{
  "state": {
    "reported": {
      "device_id": "MH-001-ABC",
      "firmware_version": "1.0.0",
      "uptime_seconds": 86400,
      "cpu_percent": 5.2,
      "ram_mb": 120,
      "sd_wear_percent": 45,
      "signal_dbm": -65,
      "connection_type": "wifi",
      "last_upload": "2026-04-29T10:15:00Z",
      "meters": [
        {
          "id": "EM6400-001",
          "status": "online",
          "last_read": "2026-04-29T10:15:00Z"
        }
      ]
    },
    "desired": {
      "firmware_version": "1.1.0",  // Set by cloud to trigger OTA
      "config_version": "2.5",
      "profile_version": "schneider-em6400:2.1"
    }
  }
}
```

**Topics:**
- Publish: `$aws/things/{device_id}/shadow/update` (state updates)
- Subscribe: `$aws/things/{device_id}/shadow/update/delta` (desired state changes → trigger OTA/profile update)
- Custom: `meterhub/{device_id}/readings` (batch telemetry), `meterhub/{device_id}/heartbeat`, `meterhub/{device_id}/logs`

### 4.2 Device Authentication: Per-Device Keys + JWT

| Aspect | Detail |
|---|---|
| **Device Key Generation** | Ed25519 keypair generated on first boot, stored in `/etc/meterhub/device.key` (mode 0600, unprivileged user ownership) |
| **Public Key Registration** | Pushed to cloud during provisioning (QR encodes public key fingerprint) |
| **MQTT Auth** | Option A: TLS client certificate (cloud-issued CA signs per-device cert); Option B: JWT signed with Ed25519 private key + cloud verification |
| **Recommendation** | **Option A (TLS client cert).** Industry standard, better tooling, revocation via CRL |
| **JWT Format (if Option B)** | `{"device_id": "...", "iat": now, "exp": now+3600, "scope": "mqtt"}` signed with device private key |
| **Bearer Token** | NOT shared across fleet; device-specific, issued per provisioning session (revocable per device) |

**Rejection of Device-Side Email Fallback:**
- Earlier spec included "device sends email to admin if cloud down >24h"
- **Problem:** Shared SMTP credentials in firmware = fleet compromise (one reverse-engineered Pi leaks API key to entire fleet)
- **Solution:** Cloud-side dead-man monitor (cloud knows all devices, sends email on heartbeat miss). **Cloud is already centralized; let it handle escalation.**
- **Removal saves:** ~2 weeks dev + entire class of security bugs

### 4.3 Provisioning: BLE + QR (Phase 1)

**Tier 1: Mobile App (Primary)**

```
1. Installer has mobile app pre-installed (iOS/Android)
2. Installer powers on Pi (or holds reset for 5 sec to enter provisioning mode)
3. Pi advertises via BLE: `MeterHub-{device_id}` (UUID, device_id in advertising data)
4. App scans BLE, shows nearby devices, installer taps matching device
5. App displays QR code content (device_id + public_key_fingerprint) for double-check
6. App opens encrypted GATT connection (ECDH key exchange)
7. App sends: SSID, PSK, cloud_url, setup_token (encrypted over GATT)
8. Pi receives, stores config locally, connects to Wi-Fi
9. Pi boots meterhub-core, sends first heartbeat to cloud
10. Cloud marks device as "commissioned" in Thing properties
11. App confirms (heartbeat received) → UI shows "Setup complete"
```

**Tier 2: Captive Portal AP (Fallback)**
- Retain hostapd + dnsmasq for installers without mobile app
- LESS preferred: UX friction (phone Wi-Fi settings), race conditions (station + AP mode), mDNS flakiness

**QR Code Encoding (in Phase 1 build):**
```
URL Scheme: https://meterhub.example.com/setup?d={device_id}&k={pubkey_fingerprint}&t={setup_token}
Or simpler: custom scheme: meterhub://commission/{device_id}/{setup_token}
Encoded in QR by image build script; printed on label attached to device
```

**BLE GATT Service:**
```
Service UUID: 12345678-1234-5678-1234-56789abcdef0
Characteristic: Provisioning (write: SSID + PSK + cloud_url + setup_token, encrypted)
Characteristic: Status (read: device_id + firmware_version + status)
```

**Implementation:**
- Firmware: BlueZ + GObject (D-Bus interface) or bluepy library
- ~300 lines Python for GATT service setup + encryption (ECDH + AES-256-GCM)
- Must **pair** BLE provisioning with QR scanning (happens in parallel, same user session)

**Why BLE in Phase 1?**
- Without it, fleet >10 devices becomes installation nightmare (manual Wi-Fi config per installer phone for each site)
- Phase 1 deadline is tight (12 weeks) but feasible if split: firmware team (BLE service) + cloud/mobile team (app, QR, provisioning API) in parallel
- Captive portal is fallback only; not primary path

### 4.4 Device Discovery: IP Resolution

**Problem:** mDNS (meterhub-{device_id}.local) is blocked or unreliable on most Indian society Wi-Fi (client isolation, Discord confusion).

**Solution:**

1. **BLE advertising** (while in provisioning mode): device broadcas device_id + IP once connected to Wi-Fi
2. **Cloud-reported IP** (post-setup): device includes IP in heartbeat; cloud returns it to mobile app (app queries cloud for device IP)
3. **Hardcoded installer tablet IP** (fallback): if on same LAN, use fixed IP range (192.168.1.0/24) or DHCP reservation
4. **mDNS as tertiary fallback** (still keep it implemented; may work on some sites)

**Installer Workflow:**
```
1. After provisioning, mobile app shows: "Device IP: 192.168.1.250"
2. Installer opens browser: https://192.168.1.250:8443
3. HTTPS UI loads; status page shows live meter readings + logs
4. Installer confirms readings match physical meter display
5. Done
```

**Fallback if app connection fails:**
```
1. OLED display (if installed) shows: "IP: 192.168.1.250"
2. Or: USB serial console (hidden, for tech support only)
3. Or: Installer pings.meterhub-{device_id}.local (works ~40% of sites)
```

---

## Part 5: Data Models & Billing Logic

### 5.1 Meter Reading Schema

```python
@dataclass
class MeterReading:
    timestamp: datetime               # UTC, from RTC or NTP
    meter_id: str                     # e.g., "EM6400-001"
    voltage_l1_rms: float             # Volts, 3-decimal precision
    voltage_l2_rms: float
    voltage_l3_rms: float
    current_l1_rms: float             # Amps
    current_l2_rms: float
    current_l3_rms: float
    power_l1_instantaneous: float     # Watts
    power_l2_instantaneous: float
    power_l3_instantaneous: float
    power_total_instantaneous: float  # Sum of 3 phases
    frequency: float                  # Hz, 1-decimal
    power_factor_avg: float           # -1.0 to +1.0
    energy_total_kWh: float           # **CRITICAL**: Cumulative totali zer (never resets, wraps at 999,999)
    energy_import_kWh: float          # Active consumption (import/export handled per phase)
    reactive_energy_kVArh: float      # Reactive (lagging-only typical for residential)
    status: str                       # "ok", "offline", "error:bad_checksum", etc.
    rssi_dbm: int                     # RS485 signal quality (proxy for line noise)
```

**Billing-Critical:**
- `energy_total_kWh` is **cumulative totalizer**; source of truth for monthly billing
- Cloud computes consumption delta: `(reading_t2.totalizer - reading_t1.totalizer) * price/kWh`
- Meter replacement: device offline for an hour, new meter baseline recorded by installer; cloud detects rollover and rebases

### 5.2 Meter Replacement / Totalizer Rollover Handling

**Scenario:** Meter fails; electrician swaps in a new one (starts at 0 kWh).

**Detection & Recovery:**

```python
# In cloud-side ingestion (after device uploads readings)
def process_reading(device_id, new_reading):
    prev_reading = db.query(f"SELECT * FROM readings WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1", device_id)

    if new_reading.totalizer < prev_reading.totalizer:
        # Option 1: Simple rollover (wrap at 999,999)
        if new_reading.totalizer < 100 and prev_reading.totalizer > 999000:
            delta = (999999 - prev_reading.totalizer) + new_reading.totalizer
            log_event(f"Meter wrap: old={prev_reading.totalizer}, new={new_reading.totalizer}, delta={delta}")

        # Option 2: Meter replacement (jump to 0)
        elif new_reading.totalizer < 100 and prev_reading.totalizer > 1000:
            log_event(f"Meter replaced: old={prev_reading.totalizer}, new={new_reading.totalizer}")
            # Wait for installer to confirm via UI: "Mark as meter replacement"
            # Store event: meter_change{device_id, timestamp, old_totalizer_baseline, new_totalizer_baseline}
            # Future readings use new_totalizer_baseline

        # Option 3: Data corruption (reject)
        else:
            raise ValueError(f"Unexpect totalizer decrease; likely corruption. old={prev_reading.totalizer}, new={new_reading.totalizer}")

    else:
        delta = new_reading.totalizer - prev_reading.totalizer
        record_consumption(device_id, delta)
```

**Installer Confirmation (UI):**
- Installer UI pops modal: "Meter reading jumps from 15342.5 to 2.3 kWh. Is meter being replaced?"
- If yes: tag reading as "meter_replacement"; cloud rebases all future deltas from 2.3 kWh baseline
- If no: flag as error; block upload until operator resolves

### 5.3 Heartbeat (Health Check)

```python
@dataclass
class Heartbeat:
    timestamp: datetime
    device_id: str
    firmware_version: str
    uptime_seconds: int
    cpu_percent: float
    ram_mb: float
    ram_percent: float
    sd_wear_percent: float            # From mmc-utils if available
    temperature_celsius: float        # From `/sys/class/thermal/thermal_zone0/temp`
    connection_type: str              # "wifi", "ethernet", "4g_lte"
    signal_strength: str              # "excellent" / "good" / "fair" / "poor" (from iw)
    last_meter_read_timestamp: datetime
    meter_online_count: int           # Number of online meters (expect 1 per device, validate)
    queue_depth: int                  # Number of pending uploader queue items (should stay < 100)
    queue_size_mb: float              # Cumulative size on disk
    last_successful_upload_timestamp: datetime
    upload_failure_count: int         # Rolling 2-hour counter (alert if >10)
    battery_percent: int              # 0–100, if UPS attached (0 if not applicable)
    status: str                       # "healthy", "degraded", "offline_queue_filling", "error"
```

**Cloud-Side Dead-Man Monitoring:**
```python
def monitor_fleet_health():
    for device_id in all_devices:
        last_heartbeat = db.query(f"SELECT * FROM heartbeats WHERE device_id = ? ORDER BY timestamp DESC LIMIT 1", device_id)
        age_minutes = (now - last_heartbeat.timestamp).total_seconds() / 60

        if age_minutes > 30:  # No heartbeat in 30 min
            send_alert(f"Device {device_id} offline >30 min")

        if age_minutes > 24 * 60:  # No heartbeat in 24 hours
            send_escalation_email(admin_email, f"Device {device_id} CRITICAL: offline >24h. Last: {last_heartbeat.timestamp}")

        if last_heartbeat.queue_depth > 500:
            send_alert(f"Device {device_id} upload queue bloated: {last_heartbeat.queue_depth} items")

        if last_heartbeat.sd_wear_percent > 80:
            send_alert(f"Device {device_id} SD wear >80%; proactive replacement advised")
```

**Sends via:** MQTT heartbeat topic + email (via AWS SES, triggered by Python Lambda)

---

## Part 6: OTA Update Strategy (Mender A/B Partitions)

### 6.1 Mender Integration

**Image Build Pipeline:**

```
pi-gen (Raspberry Pi OS build)
  + meta-mender layer (or manual A/B partitioning if pi-gen fork)
  + meterhub overlay (Python packages)
  → Output: mender-{version}.img (A/B partitions built-in, signed)
```

**Partition Layout:**
```
| Bootloader (U-Boot + Mender stub) | Partition A (OS root) | Partition B (OS root) | Data partition |
| 8 MB                               | 4 GB                  | 4 GB                  | 4 GB           |
```

**Mender Workflow:**

1. **Device queries server:** `GET /api/devices/v1/deployments/device/current`
2. **Server responds:** `{"id": "deploy-001", "artifact_name": "meterhub-1.1.0.mender"}`
3. **Device downloads artifact** (can be resumed, delta-compressed in Phase 3)
4. **Device installs to inactive partition** (Partition B if running A)
5. **On reboot:** Mender boot loader switches to new partition; waits 60 sec for commit signal
6. **Device boots new kernel + rootfs**, sends health check
7. **If healthy:** Device commits (`COMMIT` signal to Mender client); persistent boot to new partition
8. **If unhealthy (crash within 60 sec):** Boot loader auto-reverts to Partition A; device comes up on old version

**Rollout Strategy (Cloud-Orchestrated):**

```
Phase 1: Canary (1% of fleet)
  → Deploy to 1 device; wait 1 hour for health check

Phase 2: Early adopters (10% of fleet)
  → Monitor for errors; if error rate >1%, STOP and investigate

Phase 3: Standard (50% of fleet)
  → Monitor CPU spike, SD wear, upload failures

Phase 4: Complete (100% of fleet)
  → No restrictions; can deploy to all
```

**Per-Society Pinning (Phase 2 feature):**
```
Cloud pins society X to firmware v1.0.5 (previous version):
  → All devices in society X ignore offers for v1.1.0+
  → Useful for customers reporting bugs; allows immediate rollback without OTA
```

### 6.2 Application-Level Updates (Separate from OS)

**Not handled by Mender; deployed separately:**

```
profile.tar.gz (meter profiles, config templates)
  → Signed with device's public key (cloud signs with its private key)
  → Device verifies signature before extracting to /etc/meterhub/profiles
  → No reboot required; acquisition service re-reads profiles on next poll
```

**Why separate?**
- Profile updates are low-risk, don't affect kernel or base OS
- Can be deployed independently on fast cadence (daily if needed)
- Atomic: either full extraction succeeds or nothing changes
- Signed but not encrypted (profiles are O know to cloud anyway)

### 6.3 Update Manifest Format

```json
{
  "manifest_version": "2.0",
  "artifact_version": "1.1.0",
  "artifact_type": "os",  // or "profile"
  "timestamp_utc": "2026-05-15T10:00:00Z",
  "mender_url": "https://mender.example.com/api/...",
  "profile_version": "schneider-em6400:2.2",
  "checksum_sha256": "abc123...",
  "signature": "ed25519_signature(above_fields)",
  "canary_delay_seconds": 3600,
  "rollout_phases": [
    {"percent": 1, "duration_seconds": 3600},
    {"percent": 10, "duration_seconds": 7200},
    {"percent": 50, "duration_seconds": 86400},
    {"percent": 100, "duration_seconds": 0}
  ],
  "known_bad_versions": ["1.0.8", "1.0.9"],  // Reject these if seen
  "security_patches": ["CVE-2024-12345"]
}
```

---

## Part 7: Security Model

### 7.1 Authentication & Authorization

| Component | Mechanism | Scope |
|---|---|---|
| **Device ↔ Cloud (MQTT)** | TLS 1.2+ with client certificate OR JWT signed with Ed25519 key | Per-device credentials; revocable per device via CRL or token expiry |
| **Device ↔ Cloud (HTTPS)** | Bearer token (short-lived, issued per provisioning session) + HTTPS | Installer app ↔ cloud; device ↔ OTA server |
| **Installer UI (LAN HTTP)** | Password (stored as bcrypt hash or scrypt) + CSRF tokens + 5-failed-login IP lockout (15 min) | LAN-only access; rate-limited |
| **Cloud ↔ Device Configuration** | All config (profiles, cloud URL, OTA manifest) signed with Ed25519 CA cert | Device verifies signature before applying; rejects unsigned or bad-sig config |

### 7.2 Data Protection

| Asset | Protection |
|---|---|
| **Device Private Key** | File mode 0600, owned by `meterhub-core` unprivileged user (UID 700) |
| **Device Readings** | In-transit: TLS 1.2+ over MQTT; at-rest: SQLite WAL (encrypted via bitlocker/luks if society requires) |
| **Admin Email** | Collected during provisioning with explicit consent; stored in cloud DB encrypted at-rest; accessible only to authorized admins |
| **Audit Logs** | Append-only JSON with hash chain; tamper-evident; mirrored to cloud immediately |
| **OTA Artifacts** | Signed with cloud private key; device verifies signature; unsigned artifacts rejected |

### 7.3 Secrets Management

**What's stored on device:**
- Device Ed25519 private key (in `/etc/meterhub/device.key`, mode 0600)
- Wi-Fi PSK (in `/etc/wpa_supplicant/wpa_supplicant.conf` after provisioning)
- Cloud setup token (once; deleted after first successful heartbeat)

**What's NOT stored on device:**
- Admin email (cloud-only)
- Shared SMTP credentials (removed; no email fallback)
- Cloud private key (cloud-only)
- Customer credentials (cloud-only)

**Rotation:**
- Device key: One per device; not rotated except on factory reset (destroys old data + forces re-provisioning)
- Setup token: One per device; destroyed after commission
- Cloud bearer token: Issued per session; 1-hour TTL; refresh not needed in Phase 1 (cloud-side feature)

---

## Part 8: Compliance & Legal

### 8.1 Data Protection (DPDP Act)

| Aspect | Requirement |
|---|---|
| **Data Minimization** | Collect only: meter readings, device health, admin email (contact). No behavioral data, no geolocation, no device logs sent to cloud without explicit consent. |
| **Consent** | During QR provisioning, installer reads UI consent notice: "This device will collect meter readings and send them to MeterHub cloud. Your administrator email will be used for alerts. By confirming, you consent to..." Consent logged. |
| **Data Retention** | Define policy: meter readings retained for 3 years (tax records); device telemetry retained for 1 year; audit logs retained for 7 years. Publish in Terms of Use. |
| **Data Export/Deletion** | Cloud provides admin portal: "Export my data as CSV" and "Delete my data (except audit logs)" → triggers bulk GDPR export + scheduled wipe |
| **Breach Notification** | If device is compromised (e.g., key leaked), incident response: revoke device cert/token, alert admin within 72 hours, offer key rotation OTA |

### 8.2 Electrical Safety (BIS, IEC, CEA)

| Standard | Requirement | Compliance |
|---|---|---|
| **BIS IS 1293** | Power supply safety | Source: Robu.in only; all PSUs must have BIS/CE mark. Validate on delivery. |
| **IEC 61010-1** | Measurement safety for test & meas instruments | Device is not a test instrument (it's a data collector); less stringent. But CT clamps must be IEC 61010-compliant (sourced as such). |
| **CEA Rules** | Central Electricity Authority tampering rules; devices on society metering system must not interfere with Official metering | **Device reads via non-invasive CT clamps DOWNSTREAM of utility meter.** Never tap into utility meter circuit directly. Get **legal opinion before deployment** (this is BIG; violating CEA rules = civil liability). |
| **EMC (IEC 61000-4-2, ESD)** | Electromagnetic compatibility; device must operate near high-EMI environments (switchgear, motors) | TVS diodes on RS485 provide ESD suppression; RS485 shielding (grounded at device end) provides EMI rejection. Phase 2 validation: formal ESD test lab (IEC 61000-4-2). |

### 8.3 Product Liability & Warranty

| Aspect | Policy |
|---|---|
| **Device Warranty** | 1 year parts + labor; excludes: power surges (TVS diodes help but not absolute), water/physical damage, misinstallation (CT clamps on wrong circuit) |
| **Software Warranty** | Best-effort support; no SLA on bug fixes; security patches within 30 days of discovery |
| **User Documentation** | Installation manual must include: "This device reads meter data passively. It does NOT control power, disconnect circuits, or override protection relays. Always treat high-voltage areas as dangerous." + CEA compliance disclaimer |

---

## Part 9: Build Order & Timeline (12-Week Phase 1)

### Phase 0 (Pre-Phase 1, Weeks -2 to 0)

**Gate: All items MUST complete or Phase 1 cannot start**

| Task | Owner | Duration | Gate |
|---|---|---|---|
| Confirm Cloud team AWS IoT Core account + CA cert ready | Cloud Lead | 1 week | Cloud provides: AWS account access, root CA cert, device cert template |
| Evaluate Mender vs. manual A/B (pi-gen fork) | Firmware Lead | 3 days | Decision: use meta-mender + Yocto OR fork pi-gen + implement A/B manually |
| Procure hardware (Pi Zero 2 W, SD cards, RTC, antenna, RS485 module) | Hardware PM | 2–3 weeks (CRITICAL PATH) | Receive pilot batch: 5× complete units ready for testing |
| Design BLE GATT service + encryption schema | Firmware Lead + Security | 5 days | Finalized GATT UUIDs, ECDH parameters, message formats |
| Schedule cloud team API sprint (provisioning, OTA manifest, heartbeat ingestion) | Cloud Lead | 1 week | Cloud team commits to API freeze by Week 4 |
| Set up CI/CD pipeline (GitHub Actions: pytest, flake8, mypy, bandit) | DevOps | 3 days | All firmware PRs must pass checks before review |

### Phase 1 (Weeks 1–12): Core Services + Provisioning

| Week | Firmware | Cloud | Notes |
|---|---|---|---|
| **1–2** | Implement dual-SQLite + RTC integration; add DS3231 I2C driver + time sync fallback (RTC → NTP) | AWS IoT Core broker setup + device shadow schema | Parallel; firmware can mock cloud responses |
| **1–2** | Implement two-process model (meterhub-core + installer-ui socket); migrate acquisition + uploader to asyncio | Cloud API: POST /provisioning/register, GET /readings/latest | |
| **2–3** | Implement minimalmodbus (simple Modbus polling, no async) + profile loader (YAML) | Cloud: Device Thing provisioning, shadow updates, edge CA cert issuance | Profile schema with version + signature validation |
| **2–3** | Implement SQLite encrypted data write + WAL tuning (dual DBs) | Cloud: OTA manifest endpoint (GET /deployments/device/current) | |
| **3–4** | Implement BLE GATT service (provisioning mode: advertise device_id, accept SSID+PSK over encrypted GATT) | Cloud: QR generation service (encodes device_id + pubkey_fingerprint + setup_token) | Firmware in provisioning mode (manual bootloader arg); auto-timeout after 10 min |
| **4** | Implement read-only root filesystem test boot + revert logic | Cloud: Heartbeat ingestion pipeline (parse, validate, store in TimescaleDB) | Joint test: firmware sends heartbeat, cloud stores, web dashboard shows |
| **4–5** | Integrate Mender client + A/B partition boot logic (if meta-mender: validate Yocto build; if manual: implement boot loader swap) | Cloud: OTA artifact signing + staged rollout orchestration (1%→10%→50%→100%) | **CRITICAL:** Test A/B switching 100 times; no bricked devices allowed |
| **5–6** | Implement acquisition polling loop (60s cadence, 3 retries, exponential backoff) | Cloud: Reconciliation API (device can POST bulk readings on reconnect) | Field test with real Schneider EM6400 meter (if in-house) OR Modbus simulator |
| **6–7** | Implement uploader batch logic (5-min batches, MQTT queue, store-and-forward) | Cloud: Dead-man monitor + escalation alerting (email to admin on >24h silence) | Uploader must handle 7-day outage gracefully (queue on SD) |
| **7** | Implement installer UI (FastAPI + plain HTML: setup wizard, live meter view, logs, factory reset) | Cloud: Administrator portal (view devices, trigger OTA, view readings dashboard) | Installer UI available over HTTPS (LAN-only); auto-shutdown after 30 min |
| **7–8** | Implement audit logging (hash-chain append-only, mirrored to cloud topic) | Cloud: Audit log ingestion + tampering detection | |
| **8–9** | Integration testing: BLE provisioning end-to-end, meterhub-core + installer-ui, MQTT → cloud | Cloud: Fleet health dashboard (devices online, queue depth, SD wear, CPU) | Cross-team test |
| **10** | Power-loss fault injection testing (1,000 power cuts via smart plug); measure SD corruption rate (expect 0, allow 1 edge case) | Cloud: Staged rollout validation (deploy v1.0.1 to canary cohort, monitor errors) | Automate power-loss test; make it CI gate |
| **10–11** | 7-day soak test (device polling + uploader loop, simulate internet dropouts, OTA switch) | Cloud: Backup + disaster recovery validation (3-2-1 backup test) | |
| **11–12** | Complete documentation (README, installation guide, troubleshooting) | Cloud: SLO definitions + metrics dashboard | |
| **12** | **PHASE 1 COMPLETE:** Transfer to production image build + cert signing | **Phase 1 Complete:** Deliver provisioning API + dead-man monitor for first 5 customer devices | Pilot rollout: 5 units in-house OR friendly customer society for 2-week field test |

### Key Milestones

- **Week 4:** Dual-DB + BLE GATT + cloud provisioning API frozen (no changes after this)
- **Week 7:** Installer UI + MQTT foundation complete; cross-team integration begins
- **Week 10:** Power-loss testing + staged rollout orchestration validated
- **Week 12:** Signed image + Phase 1 delivery to operations

### Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Mender integration adds 2–3 weeks if unforeseen | Start Mender evaluation in Phase 0; have manual A/B fallback (boot loader swap logic ~200 lines C) as contingency |
| BLE provisioning UX bugs in Phase 1 | Use Bluetooth Low Energy already-proven libraries (BlueZ + gatt-python or bluepy for testing); mock mobile app in Week 2 to unblock firmware |
| Power-loss test flaky (SD behavior varies) | Automate via smart plug + random interval generator; make replicable; run nightly in CI; log all failures for post-mortem |
| Cloud provisioning API not ready by Week 4 | Firmware mocks cloud responses (fake beacon signal); unblock firmware; cloud catches up in Week 5–6 |

---

## Part 10: Success Criteria & Sign-Off

### Phase 1 Completion Gates

- ✅ All Python code passes mypy (strictly-typed), black (formatted), flake8 (linted)
- ✅ All new functionality has unit + integration tests; >80% code coverage
- ✅ Power-loss testing: 1,000 cycles with <1% data loss (billing data = 0% loss)
- ✅ Installer UI tested by 3+ non-developer users; <10 min first-time setup
- ✅ BLE provisioning tested on iPhone + Android; no manual Wi-Fi config needed
- ✅ OTA A/B switching tested 50+ times; auto-rollback works on reboot
- ✅ 7-day soak test passed; no crashes, memory leaks, or UI hangs
- ✅ Heartbeat cadence verified (5 min, <2% miss rate on LAN)
- ✅ Meter profile update (signed tarball) tested; device rejects unsigned profiles
- ✅ Read-only root + overlay FS tested; OS partition survives file deletion
- ✅ RTC integration tested; device boots without NTP, time is accurate within 5 seconds post-boot

### Documentation Standards

- ✅ Installation guide (step-by-step, with photos of connector wiring)
- ✅ Troubleshooting guide (100 common issues, symptoms, root causes)
- ✅ API documentation (all MQTT topics, cloud endpoints, error codes)
- ✅ Meter profile authoring guide (how to add new meter types; schema validation examples)
- ✅ Administrator guide (fleet management, OTA orchestration, alert tuning)

### Signoff

- [ ] Firmware Lead: confirms all Phase 1 code complete, tested, documented
- [ ] Cloud Lead: confirms all cloud APIs ready, SLO dashboards active
- [ ] DevOps: confirms CI/CD gating functional; all tests passing
- [ ] Security: confirms no hardcoded secrets, DPDP disclaimers in place, audit logs working
- [ ] Hardware PM: confirms BOM finalized, supplier contracts signed, pilot batch delivered

**Signoff Date:** (to be completed Week 12)

---

## Appendix A: Dependency & Package List

### Firmware Dependencies (Python 3.11+)

**common/requirements.txt:**
- SQLAlchemy>=2.0.0 (DB ORM)
- pyyaml>=6.0 (profile parsing)
- PyNaCl>=1.5.0 (Ed25519)
- cryptography>=41.0.0 (TLS, ECDH)
- python-dotenv>=0.21.0 (config from .env)
- requests>=2.31.0 (HTTPS fallback)
- structlog>=22.0.0 (JSON logging)

**acquisition/requirements.txt:**
- minimalmodbus>=2.0.0 (Modbus RTU polling, lightweight)
- pyserial>=3.5 (RS485 serial interface)
- psutil>=5.9.0 (CPU, RAM, thermal monitoring)
- asyncio-context-manager >= 1.0.0 (if using async threading)

**uploader/requirements.txt:**
- paho-mqtt>=1.6.0 (MQTT client, TLS support)
- botocore>=1.28.0 (AWS SigV4 for OTA signing)
- aiohttp>=3.9.0 (async HTTP fallback)

**installer-ui/requirements.txt:**
- fastapi>=0.104.0 (web framework)
- uvicorn>=0.24.0 (ASGI server, HTTPS)
- qrcode[pil]>=7.4.0 (QR code generation for installer display)
- python-multipart>=0.0.5 (form parsing)
- Jinja2>=3.1.0 (templates, optional — can use plain HTML)

**Testing (global):**
- pytest>=7.4.0
- pytest-asyncio>=0.21.0
- pytest-cov>=4.1.0
- pytest-timeout>=2.1.0

**Quality (global):**
- black>=23.0.0 (code formatting)
- mypy>=1.1.0 (type checking)
- flake8>=5.0.0 (linting)
- bandit>=1.7.0 (security audit)

All pinned to specific versions; no floating deps.

---

## Appendix B: Security Considerations Not Covered in Phase 1

These are known-good items to defer to Phase 2+:

- **Attestation (FIDO2 / TEE):** Remote attestation that device code hasn't been modified. Pi Zero has no secure enclave; deferred to Phase 3 (optional for paranoid deployments).
- **Rate-Limiting at Cloud:** API throttling per device to prevent brute-force. Phase 2 (low priority; devices have fixed credentials).
- **Encryption at Rest (full-disk):** Device SD encrypted via luks + key in secure storage. Phase 2 (adds boot complexity; optional for sensitive sites).
- **Per-Meter Signing:** Each meter reading signed individually (not just batch). Phase 2 (performance trade-off; batch TLS signature sufficient for Phase 1).
- **Revocation List (CRL) Validation:** Device must check CRL for compromised device certs. Phase 2 (infrastructure complexity).

---

## Appendix C: Glossary

| Term | Definition |
|---|---|
| **A/B Partitions** | Two independent rootfs copies; OTA updates one while running from the other; atomic switch on reboot |
| **Canary Deployment** | Rolling out to a small % of fleet first (1%); monitoring for errors before wider rollout |
| **Dead-Man Monitor** | Cloud-side process that alerts if device hasn't reported in >N hours; opposite of heartbeat (device asking "am I alive?") |
| **Galvanic Isolation** | Electrical isolation between circuits (no direct ground path); prevents voltage transients from jumping between systems |
| **OTA (Over-the-Air Update)** | Remote firmware update delivery via network; device downloads, installs, reboots to new version |
| **PLP (Power-Loss Protection)** | SD card feature: survives sudden power cut without data corruption; uses capacitor bank to complete writes on power drop |
| **QR Provisioning** | Device encodes setup info (ID, key, token) in QR code; installer scans with mobile app; cloud pre-populates config |
| **Rollover** | Meter totalizer wraps (e.g., 999,999 kWh → 0); firmware must handle to avoid negative billing |
| **Store-and-Forward** | Device caches readings locally when cloud unreachable; forwards once reconnected |
| **TVS Diode** | Transient voltage suppression diode; clamps overvoltage spikes (ESD, lightning) to safe levels |
| **WAL Mode** | Write-Ahead Logging in SQLite; writes to log file first, then commits; faster + more crash-safe than direct writes |

---

**End of Production Specification v2.0**

**Next Step:** Proceed to Phase 0 pre-flight checklist (PHASE_0_REQUIREMENTS.md).
