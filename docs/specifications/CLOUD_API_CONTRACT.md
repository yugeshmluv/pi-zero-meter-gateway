# MeterHub Cloud API Contract

**Document Version:** 1.0  
**Status:** Phase 1 — Specification (pre-implementation)  
**Audience:** Cloud backend team (to build in parallel with edge firmware)

---

## 1. Overview

The edge device (Raspberry Pi Zero W) communicates with the cloud backend via two channels:
1. **Primary:** MQTT (HiveMQ Cloud or AWS IoT Core) for real-time telemetry streaming
2. **Fallback:** HTTPS REST API for offline store-and-forward scenarios

All payloads are JSON. All timestamps in UTC ISO 8601 format. Device authentication uses Ed25519 device keypairs provisioned at image build or first boot, plus cloud-issued bearer tokens.

---

## 2. Authentication Model

### Device Identity
- **Device ID:** 128-bit hex string, e.g., `a1f29c3e7b5a2f8d1c9e4b7a3f6d8c2e`
- **Device EC Private Key:** Ed25519, stored in `/etc/meterhub/secrets/device.key` (mode 0600)
- **Device EC Public Key:** Available at `/opt/meterhub/public.key` (readable, used for device registration)

### Cloud-Issued Bearer Token
- Cloud provisions a bearer token during initial device registration (QR provisioning or manual setup).
- Token format: JWT or opaque string; cloud team to specify.
- Token stored in `/etc/meterhub/secrets/cloud_token` (mode 0600).
- Device refreshes token periodically (e.g., at heartbeat acceptance or explicit refresh endpoint).
- Expired token → device falls back to HTTPS with last-known-good token, escalates to fallback email after 24 h.

### Message Signing (Optional but Recommended)
- MQTT payloads: Include `signature` field (Ed25519 of payload JSON, base64-encoded).
- HTTPS payloads: Include `Authorization: Bearer {token}` header AND `X-Device-Signature` header (Ed25519 of request body, base64).
- Cloud verifies using public key from device registration.

---

## 3. MQTT Primary Path

### Broker Configuration
- **Endpoint:** HiveMQ Cloud managed endpoint or AWS IoT Core  
- **Port:** 8883 (TLS, no fallback to 1883)  
- **Client ID:** `meterhub_{device_id}`  
- **Protocol Version:** MQTT 3.1.1  
- **QoS:** 1 (at-least-once delivery)  
- **Persistent Session:** Enabled (`clean_session=false`)  
- **Keep-alive:** 60 seconds  
- **TLS Versions:** 1.2+ (self-signed certs not acceptable; use public CA)  
- **CA Bundle:** Include AWS, HiveMQ, or DigiCert root CAs in image

### Topic Schema

**Telemetry (from device to cloud):**

```
society/{society_id}/panel/{panel_id}/readings
```

**Subscribe Topics (from cloud to device):**

```
society/{society_id}/panel/{panel_id}/ota/manifest
society/{society_id}/panel/{panel_id}/config/update
society/{society_id}/panel/{panel_id}/command
```

### Payload: Telemetry Readings

Published every 5 minutes (configurable), contains:
- Last 5 minutes of minute-level readings (up to 5 records)
- Each record includes all meter phases + totalizer

```json
{
  "device_id": "a1f29c3e7b5a2f8d1c9e4b7a3f6d8c2e",
  "society_id": "mumbai-koramangala-01",
  "panel_id": "zone-03-phase-a",
  "sequence":"1047",
  "timestamp_batch_start_utc": "2026-04-28T14:50:00Z",
  "timestamp_batch_end_utc": "2026-04-28T14:55:00Z",
  "readings": [
    {
      "timestamp_utc": "2026-04-28T14:51:00Z",
      "meter_timestamp_device": "2026-04-28T14:51:00.123Z",
      "totalizer_kwh": 45678.234,
      "instant_kw": 12.45,
      "frequency_hz": 49.98,
      "voltage": {
        "l1_v": 230.5,
        "l2_v": 231.2,
        "l3_v": 229.8
      },
      "current": {
        "l1_a": 15.3,
        "l2_a": 14.8,
        "l3_a": 15.1
      },
      "power_factor": {
        "total": 0.98,
        "l1": 0.98,
        "l2": 0.98,
        "l3": 0.97
      },
      "power": {
        "active_kw": 12.45,
        "reactive_kvar": 1.23,
        "apparent_kva": 12.60
      },
      "quality": {
        "rssi_dbm": -45,
        "modbus_retry_count": 0,
        "meter_online": true
      }
    },
    {
      "timestamp_utc": "2026-04-28T14:52:00Z",
      "totalizer_kwh": 45678.456,
      "instant_kw": 12.47,
      "quality": { "modbus_retry_count": 1, "meter_online": true }
    }
  ],
  "signature": "base64_encoded_ed25519_signature"
}
```

**Key Design Notes:**
- Always include **totalizer_kwh** in every reading; cloud computes consumption from deltas.
- Sparse payloads: if phase data unchanged, only include delta fields (device optimization).
- `meter_online` flag: `false` if meter was offline during this minute; value indicates last-known reading.
- Device never loses data on power cut; SQLite persists all readings and re-uploads on reconnect.

### Payload: Heartbeat

Published every 5 minutes (may piggyback on readings batch or separate).

```json
{
  "device_id": "a1f29c3e7b5a2f8d1c9e4b7a3f6d8c2e",
  "society_id": "mumbai-koramangala-01",
  "panel_id": "zone-03-phase-a",
  "timestamp_utc": "2026-04-28T14:55:00Z",
  "event_type": "heartbeat",
  "firmware_version": "1.2.3",
  "uptime_seconds": 864000,
  "system": {
    "cpu_percent": 8.5,
    "ram_mb": 150,
    "ram_max_mb": 200,
    "disk_free_mb": 2840,
    "disk_total_mb": 29000,
    "temperature_c": 52.3,
    "thermal_state": "normal"
  },
  "wireless": {
    "wifi_rssi_dbm": -68,
    "wifi_connected": true,
    "connection_type": "wifi"
  },
  "meter": {
    "last_read_utc": "2026-04-28T14:55:00Z",
    "last_read_age_seconds": 0,
    "meter_online": true,
    "meter_profile": "schneider-em6400",
    "consecutive_failures": 0
  },
  "cloud": {
    "mqtt_connected": true,
    "mqtt_session_restored": true,
    "last_mqtt_publish_utc": "2026-04-28T14:54:30Z",
    "last_https_fallback_attempt": null,
    "queue_depth": 0,
    "queue_size_mb": 0.5
  },
  "storage": {
    "sd_card_writes_mb_today": 24.3,
    "sd_card_daily_limit_mb": 30,
    "sqlite_db_size_mb": 45.2,
    "log_size_mb": 12.1
  },
  "security": {
    "last_config_change_utc": "2026-04-26T10:30:00Z",
    "failed_login_attempts_24h": 0,
    "audit_log_entries": 127
  },
  "provisioning": {
    "device_provisioned": true,
    "device_registered_with_cloud": true,
    "qr_setup_complete": true
  },
  "signature": "base64_encoded_ed25519_signature"
}
```

**Cloud Actions on Heartbeat:**
- Acknowledge receipt via MQTT retained message on acknowledgement topic (optional).
- Update device "last seen" timestamp for fleet dashboard.
- Trigger alerts if `thermal_state` is `warning` (70°C) or `critical` (80°C+).
- Route high CPU/RAM utilization to ops dashboard.
- Log SD card write rate for wear analysis (predict lifespan).

### Subscribed Topics: OTA Manifest (Cloud → Device)

When cloud has an update, publish to:
```
society/{society_id}/panel/{panel_id}/ota/manifest
```

Payload:

```json
{
  "version": "1.2.4",
  "release_timestamp_utc": "2026-04-27T18:00:00Z",
  "critical": false,
  "min_prev_version": "1.0.0",
  "withdrawn": false,
  "manifest_url": "https://s3.amazonaws.com/meterhub-releases/v1.2.4/manifest.tar.gz.sig",
  "manifest_sha256_unsigned": "abcd1234...",
  "ed25519_signature": "base64_of_signature_over_entire_manifest",
  "public_key_id": "meterhub-prod-2026",
  "instructions": {
    "canary_delay_seconds": 21600,
    "fallback_if_health_check_fails": true,
    "revert_if_meter_offline": true
  },
  "metadata": {
    "release_notes": "Fix: thermal sensor race condition, improve MQTT reconnect",
    "deployed_regions": ["india-west", "india-south"]
  }
}
```

**Device Processing:**
1. Verify signature with public key from `/opt/meterhub/public.key`.
2. Check `version` against current version and `min_prev_version`.
3. If `critical=false`, apply canary delay (random 0–6 hours, re-poll manifest before downloading).
4. Download from `manifest_url`, verify signature.
5. Extract, run health check (acquisition reads meter, uploader sends heartbeat within 5 min).
6. On failure, revert symlink and restart previous version, report rollback via heartbeat.

---

## 4. HTTPS Fallback Path

Triggered when:
- MQTT broker unreachable for >15 minutes.
- Device explicitly configured for HTTPS-only operation.

### Endpoints

**POST /v1/readings**
- Sends batched telemetry readings (same schema as MQTT payload).
- **Headers:**
  - `Authorization: Bearer {cloud_token}`
  - `X-Device-Signature: {ed25519_signature_base64}`
  - `Content-Type: application/json`
- **Response:** `200 OK` with JSON ack including `next_batch_interval_seconds`.
- **Backoff on failure:** 1 min → 5 min → 30 min → 1 h (cap), resume MQTT when broker available.

**POST /v1/heartbeat**
- Same payload as MQTT heartbeat.
- **Response:** `200 OK` with `{"ack": true, "server_time_utc": "...", "recommended_check_interval_seconds": 300}`.

**GET /v1/ota/manifest**
- Query params: `device_id={device_id}&version={current_version}`.
- **Response:** Same manifest JSON as MQTT push (allows pull-based updates in restricted networks).

**POST /v1/config/fetch**
- Device can explicitly fetch config (Wi-Fi, cloud endpoint) without relying on provisioning.
- **Response:** JSON with `wifi_ssid` (optional, if changed), `cloud_endpoint`, `mqtt_broker`, fallback email recipient, etc.

**POST /v1/audit-log/upload**
- Batch upload local audit logs (config changes, logins, OTA events, fallback emails sent) once cloud reconnects.
- **Payload:** JSON array of audit events.
- **Response:** `200 OK`.

---

## 5. Provisioning API (Cloud ↔ Device)

### Pre-Deployment: Device Registration

Device public key is encoded in QR code at image build or first boot. Installer scans QR in mobile app → mobile app calls cloud API to pre-register device.

**POST /v1/provisioning/register**
- **Payload:**
  ```json
  {
    "device_id": "a1f29c3e7b5a2f8d1c9e4b7a3f6d8c2e",
    "public_key_ed25519": "base64_encoded_public_key",
    "setup_token": "ephemeral_token_from_qr"
  }
  ```
- **Response:** `201 Created` with JSON:
  ```json
  {
    "device_id": "...",
    "cloud_token": "jwt_or_opaque_token_with_24h_expiry",
    "cloud_endpoint": "your-cloud.example.com",
    "mqtt_broker_url": "a1b2c3.iot.hivemq.com:8883",
    "setup_wizard_config": {
      "society_id": "pre_filled_or_empty",
      "panel_id": "pre_filled_or_empty",
      "meter_profile": "schneider-em6400",
      "fallback_email_recipient": "operations@society.in"
    }
  }
  ```

### Post-Provisioning: Config Update

Device may update society/panel/email via installer UI or API.

**POST /v1/provisioning/config**
- **Headers:** `Authorization: Bearer {cloud_token}`
- **Payload:**
  ```json
  {
    "device_id": "...",
    "society_id": "mumbai-koramangala-01",
    "panel_id": "zone-03-phase-a",
    "fallback_email_recipient": "admin@society.in",
    "meter_profile": "schneider-em6400",
    "polling_interval_seconds": 60
  }
  ```
- **Response:** `200 OK`.

---

## 6. Cloud-Side Provisioning Flow (QR-Based)

```
Installer scans QR on Pi device label
  ↓ (device_id + setup_token encoded)
Mobile app / web UI
  ↓ POST /v1/provisioning/register (device_id, public_key, setup_token)
Cloud API validates setup token, creates device record
  ↓ returns cloud_token + MQTT broker + pre-filled config
Installer connects Pi to Wi-Fi AP on Pi
  ↓ opens captive portal at 192.168.4.1/setup
Installer UI on Pi fetches config from cloud (using cloud_token)
  ↓
Installer UI pre-fills society, panel, email, meter profile
  ↓ Installer reviews, confirms, submits
Pi stores config, restarts acquisition + uploader
  ↓ acquisition reads meter, uploader sends heartbeat
Cloud receives heartbeat, device marked "ready"
  ↓
Installer can close UI; Pi transitions to normal operation
```

**Alternative (Manual, No QR):**
- Installer manually enters society ID, panel ID, email in Pi UI.
- Cloud endpoint + bearer token: manually provided by ops team or pre-baked in image build.

---

## 7. Error Scenarios & Recovery

### Device Offline (MQTT Broker Unreachable)

1. Device attempts MQTT reconnect with exponential backoff (1 s → 5 s → 30 s → 2 min cap).
2. After 15 minutes of failure, downgrade to HTTPS fallback.
3. After 24 hours of cloud outage, trigger fallback email to admin (device-side only; no cloud involvement).
4. Once cloud reconnects, device resumes MQTT and uploads audit log of fallback events.

### Fallback Email Trigger

**Condition A: Cloud never configured (>24 h collecting data, no cloud connection ever successful)**
```
From: {shared_transactional_email}@sendgrid.net (AWS SES sender)
To: {admin_email_from_config}
Subject: MeterHub — {device_id} Offline Provisioning Alert
Body:
  Device ID: a1f29c3e7b5a2f8d1c9e4b7a3f6d8c2e
  Society: [Not yet configured]
  Panel: [Not yet configured]
  Status: Collecting readings locally, waiting for cloud config
  Last 24h Consumption: 123.45 kWh (estimated)
  Action: Complete setup wizard at meterhub-{device_id}.local (over LAN)
  Sent at: 2026-04-28 14:55 UTC
```

**Condition B: Cloud was working, now offline >24 h**
```
Subject: MeterHub — {device_id} Cloud Unreachable for >24 Hours
Body:
  Device ID: {device_id}
  Society: mumbai-koramangala-01
  Panel: zone-03-phase-a
  Status: Reading meter locally; cloud unreachable since 2026-04-27 14:55 UTC
  Last 24h Consumption: 234.56 kWh
  Queue Depth: 1,234 readings (~2.5 days of data)
  Troubleshooting:
    1. Check Wi-Fi connectivity: meterhub-{device_id}.local → Connection Status
    2. Verify cloud endpoint / MQTT broker availability
    3. Contact MeterHub ops: support@meterhub.io
  Sent at: {current_time} UTC
  Repeats: Every 24 hours until cloud reconnects
```

Device logs: "Fallback email sent (Condition A|B)", reports in next successful heartbeat.

---

## 8. Cloud-Side Responsibilities (Out of Scope for Edge, But Specified Here)

1. **MQTT Broker:** Maintain HiveMQ Cloud or AWS IoT Core, TLS certificates, retention policies.
2. **Data Ingestion Pipeline:** Consume MQTT payloads, decode, validate signatures, store in time-series DB (ClickHouse, TimescaleDB, etc.).
3. **Society-Level Aggregation:** Combine readings from N devices per society → society-level kWh, peak demand, tariff billing.
4. **Admin Dashboards:** Real-time consumption, device health, OTA deployment status, audit logs.
5. **Daily Admin Digest Email:** Summarize previous day's consumption per society, flag alarms (device offline >1 h, temp warnings, SD wear >80 %).
6. **OTA Release Management:** Build signed packages, publish to S3, manage canary vs. critical flags.
7. **Audit Log Archival:** Receive and store device-side audit logs from `/v1/audit-log/upload`.

---

## 9. Security Checklist

- [ ] All MQTT connections over TLS 1.2+.
- [ ] All HTTPS connections over TLS 1.2+, no self-signed certs.
- [ ] Device public keys validated on registration.
- [ ] Bearer tokens issued with short TTL (24 h recommended).
- [ ] Token refresh via heartbeat or explicit endpoint.
- [ ] Setup tokens are single-use, time-limited (30 min).
- [ ] Audit log uploaded to cloud for compliance (DPDP Act).
- [ ] OTA manifests always Ed25519-signed; device verifies before download.
- [ ] Payload signatures (Ed25519) verified server-side.
- [ ] Meter data + admin email: no tenant/resident PII on device.

---

## 10. Example Deployment Flow

```
Day 1: Image Build
  → Device ID + Ed25519 keypair generated
  → Public key encoded in QR label
  → Image flashed to 50 SD cards

Day 1–2: Fleet Provisioning
  For each Pi:
    1. Engineer scans QR → mobile app registers device with cloud
    2. Engineer connects Pi to Wi-Fi, opens meterhub-{device_id}.local
    3. UI pre-filled from cloud (society, panel, email, meter profile)
    4. Engineer confirms, Pi reboots
    5. Acquisition polls meter, uploader sends heartbeat
    6. Cloud acknowledges device is ready

Day 2+: Normal Operation
  → Acquisition reads meter every 60 s
  → Uploader batches 5-min readings, publishes MQTT
  → Heartbeat every 5 min
  → Cloud aggregates across devices → society dashboards
  → Cloud sends admin digest every 24 h

OTA Update Scenario:
  1. Cloud publishes manifest to MQTT `ota/manifest` topic
  2. Device sees manifest, waits canary delay (if non-critical)
  3. Device downloads package from S3, verifies signature
  4. Device runs health check (meter read + heartbeat)
  5. If health check passes: device updates symlink, restarts services
  6. If health check fails: device reverts symlink, reports rollback in heartbeat
```

---

## 11. Testing & Monitoring

### Cloud Team Test Matrix

- [ ] Test MQTT connection lifecycle (connect, subscribe, retain, disconnect, reconnect).
- [ ] Simulate broker outage >15 min → verify HTTPS fallback activates.
- [ ] Test OTA manifest push, canary delay, signature verification.
- [ ] Test bearer token expiry → device should refresh and retry.
- [ ] Test heartbeat processing pipeline and fleet dashboard updates.
- [ ] Verify audit log ingestion and compliance reporting.

### Edge Device Test Matrix (See `tests/` directory)

- [ ] Unit tests for Modbus polling logic.
- [ ] Integration test: simulator meter + MQTT broker stub.
- [ ] Power-loss fault injection: kill device randomly, verify on restart no data lost.
- [ ] 24 h soak test: continuous polling + upload simulation.
- [ ] Thermal throttling test: verify uploader pauses at 75°C.
- [ ] JWT refresh and bearer token retry logic.

---

## 12. Versioning & Evolution

**Current API Version:** v1 (April 2026)  
**Backward Compatibility:** Device firmware v1.x will only accept v1 API.  
**Future:** v2 API (if major changes) will have sunset notice and migration window.

**Keep in Contracts:**
- MQTT topic schema is stable; add new sub-topics as needed.
- JSON payloads are append-only; old fields never removed, new fields added.
- HTTP response status codes follow REST conventions (2xx success, 4xx client error, 5xx server error).
