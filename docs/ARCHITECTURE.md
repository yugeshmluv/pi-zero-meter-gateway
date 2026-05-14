# MeterHub System Architecture

**Document Version:** 1.0
**Date:** April 2026
**Status:** Phase 1 Specification

---

## Core Design Principles

1. **The device is dumb, the cloud is smart:** All customer-facing intelligence (dashboards, billing, analytics, anomaly detection) lives in the cloud. The Pi merely collects and forwards raw data.

2. **Reliability over features:** A meter that reliably records consumption every 60 seconds for 90 days is worth far more than a device with 50 features that crashes once a week.

3. **Process isolation:** Three independent systemd-managed services ensure a bug in the web UI cannot break meter polling or cloud uploads.

4. **Crash-safe by design:** SQLite WAL mode + power-loss fault injection tests eliminate any data loss scenario.

5. **Offline-first:** Device logs data locally even with no Wi-Fi. Cloud is a "nice to have" for real-time dashboards; local storage is the source of truth until proven otherwise.

---

## Architecture Layers

### Layer 1: Hardware (Physical)

```
3-Phase CT Meter (Modbus RTU)
    ↓ (RS485 A/B lines)
Waveshare TTL to RS485 (C) Isolated Converter
(Galvanic isolated 2.5kV, integrated TVS diodes)
    ↓ (TTL serial)
Raspberry Pi Zero W UART (/dev/serial0)
```

**Safety-critical choices:**
- Isolation is **mandatory** (415 V three-phase can destroy non-isolated Pi on ground fault).
- TVS diodes on A/B lines protect against surge.
- DIN-rail enclosure (IP54) isolates Pi from moisture and dust in electrical panels.

### Layer 2: OS & Firmware (Pi SD Card)

```
Boot → /boot/cmdline.txt (dtoverlay=disable-bt, tvservice -o)
         ↓
systemd (init)
    ├─ meterhub-acquisition.service
    ├─ meterhub-uploader.service
    ├─ meterhub-installer-ui.service
    └─ system services (networking, log2ram, watchdog)
```

**Design:**
- Services run as unprivileged `metrehub` user (UID 499).
- SQLite database in `/var/lib/meterhub/readings.db` (owned by `metrehub`).
- Configuration in `/etc/metrehub/` (mode 0755), secrets in `/etc/meterhub/secrets/` (mode 0700).

### Layer 3: Service Communication (IPC)

```
┌─────────────────────────────────────────┐
│     meterhub-acquisition               │
│  (reads meter, writes SQLite)           │
│  Memory: <40 MB, CPU: <5% avg          │
└──────────────┬──────────────────────────┘
               │ (SQLite WAL writes)
        ┌──────▼─────────┐
        │  SQLite WAL DB  │
        │ /var/lib/...    │
        └──────┬──────────┘
               │ (SQLite reads)
┌──────────────▼────────────────────────┐  ┌──────────────────────────┐
│  meterhub-uploader                  │  │  meterhub-installer-ui   │
│  (batches & uploads to cloud)       │  │  (setup wizard, status)   │
│  Memory: <40 MB, CPU: <8% avg       │  │  Memory: <60 MB           │
└──────────────┬──────────────────────┘  └──────────────────────────┘
               │
        ┌──────▼────────────┐
        │  MQTT / HTTPS     │
        │  (Cloud Backend)  │
        └───────────────────┘
```

**Design Rationale:**
- **SQLite (not message queues):** ACID transactions ensure no data loss on power cuts. WAL mode allows concurrent reads and writes without blocking.
- **Systemd socket activation (optional):** Each service can expose a Unix domain socket for future inter-process communication without adding complexity today.
- **No shared memory:** Shared-memory IPC introduces synchronization complexity and potential race conditions. SQLite is the single source of truth.

### Layer 4: Local Storage (Persistence)

```
SQLite Database (/var/lib/metrehub/readings.db)
├─ readings (1 row per minute)
│   ├─ timestamp_utc
│   ├─ meter_address (e.g., 1)
│   ├─ totalizer_kwh
│   ├─ instant_kw
│   ├─ voltage_l1 / l2 / l3
│   ├─ current_l1 / l2 / l3
│   ├─ pf_total
│   ├─ frequency_hz
│   └─ modbus_retry_count
├─ readings_hourly (aggregated from daily job)
│   ├─ hour_start_utc
│   ├─ avg_kw
│   ├─ min_kw
│   ├─ max_kw
│   └─ totalizer_kwh_delta
├─ readings_daily (aggregates)
│   ├─ date_utc
│   ├─ totalizer_kwh_delta
│   └─ peak_kw
├─ device_config
│   ├─ device_id
│   ├─ society_id
│   ├─ panel_id
│   ├─ meter_profile
│   ├─ cloud_endpoint
│   └─ fallback_email_recipient
├─ cloud_queue (store-and-forward)
│   ├─ sequence
│   ├─ payload (JSON blob)
│   ├─ timestamp_queued
│   └─ retry_count
├─ audit_log
│   ├─ timestamp_utc
│   ├─ event_type (config_change, login, ota, fallback_email)
│   ├─ user_id (for UI logins)
│   └─ details (JSON blob)
└─ device_health
    ├─ timestamp_utc
    ├─ cpu_percent
    ├─ ram_mb
    ├─ temperature_c
    └─ sd_writes_mb
```

**WAL Mode Configuration:**
```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;     -- Balances safety & performance
PRAGMA journal_size_limit = 10485760;  -- 10 MB cap
PRAGMA wal_autocheckpoint = 1000;  -- Checkpoint every 1000 pages
```

**Retention Policy:**
- Minute-level: 30 days (43,200 rows at ~4 KB/row = ~172 MB max)
- Hourly: 1 year (8,760 rows)
- Daily: 5 years (1,825 rows)
- Old data auto-deleted by maintenance job (daily, 02:00 UTC)

### Layer 5: Cloud Upload Path

```
┌─────────────────┐
│  metrehub-      │
│  uploader       │
└────────┬────────┘
         │
    ┌────▼──────────┐
    │ Check MQTT    │
    │ broker        │
    └────┬───┬──────┘
         │ OK│ FAIL
         │   └──────┐
     ┌───▼──┐   ┌───▼──────┐
     │ MQTT │   │ HTTPS    │
     │ Path │   │ Fallback │
     └───┬──┘   └───┬──────┘
         │          │
         │          ├─ Backoff: 1m → 5m → 30m → 1h
         │          └─ SQlite queue for >24h outage
         │
    ┌────▼──────────────────┐
    │ Cloud: MQTT Broker or │
    │ HTTPS API             │
    └─────────────────────────┘
```

**Primary Path (MQTT):**
- TLS 1.2+, QoS 1, persistent session
- Topic: `society/{society_id}/panel/{panel_id}/readings`
- Batched every 5 min with up to 5 minute-level readings
- Heartbeat every 5 min on separate topic

**Fallback Path (HTTPS):**
- Triggered after 15 min of MQTT failure
- Same telemetry schema, POST to `/v1/readings`
- Exponential backoff with SQLite-backed queue
- No data lost during outages

**Fallback Email (Device-Initiated):**
- Only triggered: (a) cloud never configured AND 24 h of readings collected, OR (b) cloud offline >24 h
- Shared transactional email account (AWS SES)
- Email contains: device ID, society, panel, last 24 h consumption, troubleshooting hints
- Repeats every 24 h until cloud reconnects

### Layer 6: Installer UI

```
┌─────────────────────────────────┐
│  Wi-Fi AP (first 30 min)        │
│  SSID: meterhub-{device_id}     │
│  Password: random or QR-encoded │
└─────────────────┬───────────────┘
                  │
         ┌────────▼─────────┐
         │ Captive Portal   │
         │ 192.168.4.1      │
         └────────┬─────────┘
                  │
    ┌─────────────┴──────────────┐
    │ Setup Wizard Form          │
    │ - Society ID               │
    │ - Panel Zone               │
    │ - Meter Profile            │
    │ - Admin Email              │
    └─────────────┬──────────────┘
                  │
    ┌─────────────▼──────────────┐
    │ Device Config updated      │
    │ Services restarted         │
    └─────────────┬──────────────┘
                  │
        ┌─────────▼────────────┐
        │ Wi-Fi AP disabled    │
        │ mDNS available       │
        │ meterhub-{id}.local  │
        └──────────────────────┘
```

**After provisioning:**
- mDNS discovery: `meterhub-{device_id}.local` on LAN
- HTTPS only (self-signed cert, browser warning OK for engineering tool)
- Installer authentication: default username / device-side password (in `/etc/metrehub/installer_pwd`)
- Pages:
  - Setup wizard (reconfigurable)
  - Meter test (single Modbus shot)
  - Connection status (Wi-Fi, MQTT, HTTPS fallback)
  - System health (CPU, RAM, temp, disk, SD wear)
  - Logs (tail 500 lines from each service)
  - OTA update (check, install, rollback)
  - Factory reset (with confirmation)

---

## Data Flow Examples

### Scenario 1: Normal Operation (Wi-Fi + Cloud Available)

```
14:50:00 UTC
  Meter: totalizer=45678.234 kWh, instant=12.45 kW
         ↓ modbus_read (async)
  Acquisition: write to SQLite
         ↓ (every minute, 60 rows queued)
14:55:00 UTC
  Uploader: read last 5 min of SQLite
         ↓ (batch into JSON payload)
  MQTT: publish to brocker
         ↓ (QoS 1, ack required)
  Cloud: consume from MQTT
         ↓ (ingest into time-series DB)
  Society dashboard: updated in real-time
```

**Data on the wire (MQTT):**
```json
{
  "device_id": "a1f29c3e7b...",
  "society_id": "mumbai-koramangala-01",
  "panel_id": "zone-03-phase-a",
  "timestamp_batch_start_utc": "2026-04-28T14:50:00Z",
  "readings": [
    {
      "timestamp_utc": "2026-04-28T14:50:00Z",
      "totalizer_kwh": 45678.234,
      "instant_kw": 12.45,
      "...": "..."
    },
    {
      "timestamp_utc": "2026-04-28T14:51:00Z",
      "totalizer_kwh": 45678.456,
      "instant_kw": 12.47
    },
    { "...": "..." }
  ]
}
```

### Scenario 2: MQTT Broker Unreachable, HTTPS Fallback Activated

```
14:55:00
  Uploader attempts MQTT connection
  → DNS resolution fails
  → Retry backoff: 1s, 5s, 30s, 2min cap
         ↓ (15 min later)
15:10:00
  MQTT still unavailable
  → Downgrade to HTTPS fallback
  → POST /v1/readings with same payload
  → 200 OK, cloud acks
  → Uploader updates queue tracking
  → Continue polling & batching locally

15:35:00
  MQTT broker comes back online
  → Next heartbeat detects Wi-Fi/connectivity OK
  → Switches back to MQTT primary
  → Continues normal operation
```

**Local SQLite queue (store-and-forward):**
```
queued: 15:10:00 → 200 readings (2.5 hours)
queued: 15:20:00 → 200 readings (follow-on batches)
... (no data lost)
uploaded: 15:40:00 via HTTPS (finally connected)
```

### Scenario 3: Power Cut

```
Device powered during meter read
  → Acquisition: mid-transaction on SQLite
  → Uploader: possibly mid-MQTT publish
  → Power to zero

Device powered back on
  → Systemd recovers SQLite WAL checkpoints
  → No corruption (PRAGMA synchronous=NORMAL ensures durability)
  → Acquisition restarts, polls meter at next interval
  → Uploader catches up on queue
  → Cloud receives all readings with no gaps
```

---

## Thermal & Resource Management

### CPU Governor

```
Energy Mode: ondemand
  ↓
  CPUfreq scaling:
    Idle:     600 MHz (200 mW)
    Light:    800 MHz (300 mW)
    Normal:  1000 MHz (400 mW)
    Peak:    1000 MHz (500 mW)
```

### Memory Budgets (Strict Enforced)

```
System total: <200 MB
├─ acquisition: <40 MB (process watcher enforces via systemd MemoryMax=42MB)
├─ uploader: <40 MB
├─ installer-ui: <60 MB
├─ system services: ~40 MB
└─ buffer: 20 MB

Watchdog: If any process exceeds 1.5× budget, systemd restarts it.
```

### Thermal Monitoring

```
Every 60 seconds:
  1. Read /sys/class/thermal/thermal_zone0/temp
  2. Decision tree:
     <70°C  → normal operation
     70–75°C → warn in heartbeat, advisory logs
     75–80°C → pause uploader (still acquire), resume on cool
     >80°C  → stop acquisition & uploader, alert in heartbeat
  3. Report in next heartbeat

Cold boot soak tests:
  - 45°C ambient (typical panel room)
  - 24 h continuous polling
  - Heatsink + passive ventilation maintains <65°C steady-state
```

### SD Card Wear Control

```
MOUNT OPTIONS:
  noatime,nodiratime  (never update access times)

LOG MANAGEMENT:
  /var/log mounted ON tmpfs (40 MB max, hourly sync to SD)

BATCH WRITES:
  SQLite WAL + journal_size_limit prevents excessive small writes

DAILY MONITORING:
  Monitor /sys/block/mmcblk0/stat → bytes_written
  Report in heartbeat; cloud tracks trajectory

Expected:
  ~24 MB/day (min-level readings 1440/day × ~17 KB/batch)
  Industrial SD: lifespan estimate 10+ years at this rate
```

---

## OTA Update Flow

```
Cloud publishes manifest to MQTT:
  {
    "version": "1.2.4",
    "critical": false,
    "manifest_url": "https://s3.../v1.2.4/metrehub.tar.gz.sig",
    "instructions": { "canary_delay_seconds": 21600 }
  }
    ↓
Device detects manifest on MQTT
    ↓
Non-critical → apply random 0–6 h delay (canary protection)
    ↓
Download from S3 + verify Ed25519 signature
    ↓
Extract to /opt/metrehub/v1.2.4/
    ↓
Run health check:
  - Trigger meter read (must succeed)
  - Send heartbeat (must receive ack within 5 min)
    ↓
On success:
  - Update symlink: /opt/meterhub/current → v1.2.4
  - Restart all services
  - Report update success in next heartbeat
    ↓
On failure:
  - Revert symlink to previous version
  - Restart services with old version
  - Report rollback in heartbeat
  - Try update again at next manifest poll
```

---

## Security Architecture

```
Threats & Mitigations:

1. Meter Data Tampering
   → Device signs all payloads (Ed25519)
   → Cloud verifies signature with public key

2. Unauthorized Access to Installer UI
   → Default credentials + forced password change
   → Fail2ban-style 5-failed-login → 15 min IP lockout
   → HTTPS only (self-signed cert OK for engineering tool)

3. OTA Package Tampering
   → All OTA packages Ed25519-signed
   → Device verifies signature before installation
   → Signed public key baked into image at build time

4. Cloud Credential Compromise
   → Cloud bearer token + device Ed25519 keypair
   → Token refresh every 24 h
   → Device side-by-side verify on reconnect

5. Local Secrets Leakage
   → `/etc/metrehub/secrets/` owned by metrehub:metrehub, mode 0700
   → No logging of secret material
   → Audit log for all config changes (audit trail mandated)

6. Electrical Safety
   → Isolated RS485 (no ground loops)
   → TVS diodes on signal lines
   → Pi in 415V panel == very bad without isolation
```

---

## Testing Strategy

### Unit Tests (Per-Service)
- Modbus polling with retry logic
- SQLite transaction safety
- MQTT connection state machine
- HTTPS fallback backoff logic

### Integration Tests
- Acquisition → SQLite → Uploader → Cloud
- Power-loss fault injection (kill -9 during mid-transaction)
- MQTT broker failure → fallback activation
- OTA signature verification & rollback

### Soak Tests
- 24 h continuous operation at normal polling interval
- Monitor CPU, RAM, disk I/O, temperature
- Verify no data loss, no memory leaks

### Security Tests
- Brute-force login attempts (expect lockout)
- Unsigned OTA package rejection
- Meter data tampering detection

---

## Deployment Checklist

- [ ] Isolated RS485 module confirmed functional
- [ ] SDcard tested with power-loss fault injection
- [ ] All systemd services stable for 24 h
- [ ] Installer UI first-boot setup wizard works
- [ ] QR provisioning end-to-end
- [ ] OTA update success + rollback on health check failure
- [ ] Thermal throttling tested at 45°C soak
- [ ] Fallback email triggered correctly on cloud outage
- [ ] All audit events logged and transmitted to cloud
- [ ] Cloud team API contract tested end-to-end
