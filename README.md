# MeterHub — Production-Grade Firmware for Raspberry Pi Zero W Edge Gateway

![Build Status](https://img.shields.io/badge/status-phase1-blue) ![License](https://img.shields.io/badge/license-proprietary-red)

A complete, hardened firmware stack for reading single 3-phase CT meters via RS485/Modbus RTU and streaming data to a cloud backend. Designed for fleet deployment across Indian electrical panels with cloud-side aggregation, daily admin digests, and automated OTA updates.

**The Pi is dumb and reliable. All customer intelligence lives in the cloud.**

---

## 🎯 Quick Start

### For Installation Engineers (Commissioning)

1. Flash a pre-built image to an industrial SD card.
2. Power on the Pi in the electrical panel.
3. Connect to the Wi-Fi AP (SSID: `MeterHub-{device_id}`).
4. Open the captive portal or navigate to `http://192.168.4.1/setup`.
5. Scan the QR code on the device label → mobile app pre-fills configuration.
6. Confirm society ID, panel zone, admin email, meter profile.
7. Meter is polled every 60 seconds; first reading uploaded to cloud within 5 minutes.
8. Device transitions to normal operation; Wi-Fi AP shuts down after 30 minutes.

### For Developers & DevOps

**Prerequisites:**
- Raspberry Pi OS Lite (32-bit, Bookworm)
- Python 3.11+
- systemd
- SQLite 3.40+

**Install from source (development):**
```bash
git clone https://github.com/your-org/meterhub.git
cd meterhub
./scripts/install-dev.sh
```

**Build production image:**
```bash
cd pi-gen-overlay
./build-image.sh
# Outputs: meterhub-v1.2.3-$(date +%Y%m%d).img.xz
```

**Deploy OTA update to fleet:**
```bash
./scripts/release-ota.sh v1.2.4 --critical=false --canary-delay=21600
```

---

## 📋 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                Raspberry Pi Zero W                       │
│  ┌──────────┬──────────────┬──────────────────────────┐ │
│  │Acquisition│   Uploader   │  Installer UI            │ │
│  │(asyncio)  │(store-&-fwd) │  (FastAPI + Jinja2)     │ │
│  └──────────┴──────────────┴──────────────────────────┘ │
│          ↓            ↓                  ↓              │
│  ┌─────────────────────────────────────────────────┐   │
│  │         SQLite WAL (crash-safe)                 │   │
│  │  30-day min-level, 1-year hourly retention      │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
         ↓                       ↓
   ┌─────────────────────┐  ┌─────────────┐
   │ Waveshare TTL to    │  │  Wi-Fi      │
   │ RS485 (C) Converter │  │  LAN/AP     │
   │ (Isolated, TVS)     │  │             │
   └─────────────────────┘  └─────────────┘
         ↓                        ↓
   ┌─────────────┐       ┌─────────────────┐
   │  3-Phase CT │       │   Cloud API     │
   │   Meter     │       │  (MQTT primary, │
   │  (Modbus)   │       │  HTTPS fallback)│
   └─────────────┘       └─────────────────┘
```

**Three independent systemd services** communicating via SQLite and Unix domain sockets:
- **meterhub-acquisition:** Reads Modbus every 60 s, writes raw readings to DB. No external dependencies.
- **meterhub-uploader:** Uploads batched readings to cloud every 5 min (primary MQTT, fallback HTTPS).
- **meterhub-installer-ui:** Web UI for setup, commissioning, health monitoring, OTA updates.

**Process isolation:** A crash or bug in one service does not affect the others.

---

## � Documentation Index

**Core Documentation:**
- 🔧 [CONTRIBUTING.md](docs/guides/CONTRIBUTING.md) — Developer setup, code style, testing checklist
- 🏗️ [System Architecture](docs/ARCHITECTURE.md) — 6-layer design, IPC, data flows, security model
- 📊 [Production Specification](docs/specifications/PRODUCTION_SPEC.md) — Complete hardware & software spec (LOCKED)
- ☁️ [Cloud API Contract](docs/specifications/CLOUD_API_CONTRACT.md) — API endpoints & payload schemas (FROZEN for cloud team)
- 🔩 [Hardware BOM](docs/hardware/BOM.md) — Parts list with India suppliers & pricing
- 📋 [Meter Profiles](docs/guides/METER_PROFILES.md) — How to author new meter definitions (YAML)

**Project Status:**
- ✅ [Phase 1 Summary](docs/project/PHASE_1_SUMMARY.md) — Delivery report & sign-off
- ✅ [Phase 1 Verification](docs/project/PHASE_1_VERIFICATION.md) — Quality audit & checklist
- 📋 [Quick Reference](docs/QUICK_REFERENCE.md) — All links at a glance

---

## �🔧 Key Features

✅ **Hardware**
- Isolated RS485 transceiver (safety-critical) + TVS diodes  
- Industrial-grade SD card (SanDisk/ATP/Swissbit)  
- IP54 DIN-rail enclosure with passive ventilation  
- Thermal monitoring: warn at 70°C, throttle at 75°C, pause at 80°C  

✅ **Reliability**
- Crash-safe SQLite (WAL mode, no corruption on power cuts)  
- Store-and-forward queue: survives 7-day cloud outages  
- Modbus 3 retries with exponential backoff  
- Fallback email to admin if offline >24 h  

✅ **Performance**
- CPU <10% average, <30% peak  
- RAM <200 MB total  
- SD writes <30 MB/day (wear optimized)  
- Runs on 512 MB RAM without swap  

✅ **Security**
- HTTPS-only installer UI (self-signed cert auto-generated)  
- Ed25519 device signing; cloud token bearer auth  
- Audit log (config changes, logins, OTA events)  
- SSH disabled by default; key-only when enabled  
- DPDP Act compliant (no resident PII on device)  

✅ **Fleet Management**
- QR-code provisioning (device ID + public key in QR)  
- OTA updates with Ed25519 signature verification  
- Canary delays for non-critical updates  
- Health-check rollback on update failure  
- Cloud-side telemetry: CPU, RAM, temp, SD wear, queue depth  

✅ **Cloud Integration** (Specified for parallel cloud team)
- MQTT (HiveMQ Cloud / AWS IoT Core) primary path  
- HTTPS fallback for restricted networks  
- Heartbeat every 5 min with health metrics  
- Per-device audit logs uploaded on reconnect  

---

## 📁 Repository Structure

```
meterhub/
├── acquisition/              # Modbus polling service
│   ├── meterhub_acq/         # Python package
│   ├── requirements.txt       # Python dependencies
│   ├── tests/               # Unit + integration tests
│   └── systemd/             # meterhub-acquisition.service
├── uploader/                 # MQTT + HTTPS store-and-forward
│   ├── meterhub_uploader/
│   ├── requirements.txt
│   ├── tests/
│   └── systemd/
├── installer_ui/             # FastAPI web UI (commissioning)
│   ├── app/                 # FastAPI + Jinja2
│   ├── templates/           # HTML forms (no SPA)
│   ├── static/              # CSS, minimal JS
│   ├── requirements.txt
│   └── systemd/
├── common/                   # Shared utilities
│   ├── meterhub_common/
│   │   ├── db.py            # SQLite helpers
│   │   ├── config.py        # Config loading
│   │   ├── secrets.py       # Secrets & keystore
│   │   ├── logger.py        # Unified logging
│   │   ├── modbus_profiles/ # YAML meter definitions
│   │   └── mqtt_client.py   # MQTT wrapper
│   └── requirements.txt
├── profiles/                 # Meter profiles (YAML)
│   ├── schneider-em6400.yaml
│   ├── lt-4400.yaml
│   ├── selec-mfm383c.yaml
│   └── README.md            # Profile authoring guide
├── ota/                      # OTA update pipeline
│   ├── build-package.sh     # Create signed .tar.gz
│   ├── release-ota.sh       # Publish to S3, notify cloud
│   ├── manifest-schema.json # Manifest format spec
│   └── tests/
├── pi-gen-overlay/           # Raspberry Pi image build
│   ├── build-image.sh       # Orchestrate image creation
│   ├── overlay/             # Custom services, configs
│   │   ├── etc/meterhub/    # Config templates
│   │   ├── opt/meterhub/    # Application code
│   │   └── ...
│   └── README.md
├── scripts/                  # Tooling & automation
│   ├── install-dev.sh       # Dev environment setup
│   ├── install-prod.sh      # Fresh Pi OS → production
│   ├── meterhub-erase.sh    # Secure SD card wipe
│   ├── gen-device-keys.sh   # Generate Ed25519 keypair
│   ├── qr-provisioning.md   # QR setup flow
│   └── provision-cloud.py   # Cloud registration client
├── tests/                    # System-level tests
│   ├── test_acquisition.py  # Unit + simulator tests
│   ├── test_uploader.py     # Queue + MQTT fallback
│   ├── test_fault_injection.py # Power-loss scenarios
│   ├── test_soak_24h.py     # Long-run stability
│   └── conftest.py
├── docs/                     # Documentation
│   ├── ARCHITECTURE.md      # Design decisions
│   ├── COMMISSIONING.md     # Installer guide
│   ├── TROUBLESHOOTING.md   # Common issues
│   ├── METER_PROFILES.md    # How to author profiles
│   ├── CLOUD_API_CONTRACT.md # (Shared with cloud team)
│   ├── OTA_DEPLOYMENT.md    # Release process
│   └── COMPLIANCE.md        # DPDP, BIS, electrical safety
├── HARDWARE_BOM.md          # Bill of materials
├── CLOUD_API_CONTRACT.md    # (Main copy)
├── LICENSE                  # Proprietary
├── CONTRIBUTING.md
└── README.md                # This file
```

---

## 📦 Hardware Requirements

| Item | Model | Supplier | Cost (₹) |
|------|-------|----------|----------|
| Raspberry Pi Zero 2 W | v1.0+ | Robu.in, Element14 | 2,900–3,500 |
| Isolated RS485 Converter | Waveshare TTL to RS485 (C) | Robu.in, AliExpress, REES52 | 500–900 |
| Industrial SD Card (PLP) | SanDisk Industrial XI 32 GB | Electronicscomp, Robu.in | 3,200–4,000 |
| IP54 DIN-Rail Enclosure | 200×150×100 mm, IP54 min | Robu.in | 2,000–3,500 |
| Power Adapter | 5V/2A industrial PSU | Robu.in, Electronicscomp | 600–1,200 |
| Heatsink + Thermal Pad | 25×25×15 mm aluminum | Robu.in | 300–600 |
| **Total (Tier 1 Standard Kit)** | | | **₹10,500–12,500** |

See [HARDWARE_BOM.md](HARDWARE_BOM.md) for India-specific suppliers, full part numbers, bulk pricing, and optional Tier 2/3 connectivity.

---

## 🚀 Building & Deployment

### Phase 1: Architecture Approval (Current Status)
- ✅ System architecture diagram
- ✅ BOM with India sourcing
- ✅ Cloud API contract
- ⏳ Repository structure initialized

### Phase 2: Core Acquisition & Storage
- [ ] Acquisition service (asyncio + pymodbus)
- [ ] Schneider EM6400 profile (primary test meter)
- [ ] SQLite integration, retention policies
- [ ] Unit tests + simulator

### Phase 3: Cloud Integration
- [ ] Uploader service (MQTT primary)
- [ ] HTTPS fallback + store-and-forward queue
- [ ] Heartbeat + telemetry schema
- [ ] Integration tests against mock cloud

### Phase 4: Installer UI & Provisioning
- [ ] FastAPI UI (setup wizard, status pages)
- [ ] QR provisioning flow
- [ ] Meter test page

### Phase 5: OTA & Hardening
- [ ] OTA package builder + signature verification
- [ ] Canary delays, rollback on health check failure
- [ ] Thermal + SD wear monitoring
- [ ] Fault injection tests (power cuts, MQTT outages)

### Phase 6: Image & Fleet
- [ ] pi-gen overlay + image builder
- [ ] Per-device ID injection at flash time
- [ ] Production install script
- [ ] 24 h soak test

---

## 📝 How to Contribute

1. **Understand the Architecture:** Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
2. **Follow the Build Order:** Work on phases sequentially.
3. **Test Everything:** Unit tests + integration tests + power-loss fault injection.
4. **Document Changes:** Update [CLOUD_API_CONTRACT.md](CLOUD_API_CONTRACT.md) if you modify any cloud-facing interfaces.
5. **Avoid Feature Creep:** The Pi is dumb. All intelligence lives in the cloud.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 🔐 Security

- **Firmware Updates:** Ed25519 signed only; cloud verifies on every update.
- **Device Identity:** Unique Ed25519 keypair per device, provisioned at build time.
- **Cloud Authentication:** Bearer tokens + device signatures.
- **Audit Trail:** All config changes, logins, OTA events logged locally and mirrored to cloud.
- **Compliance:** DPDP Act (single admin email, no resident PII on device).

See [docs/COMPLIANCE.md](docs/COMPLIANCE.md) for full security checklist.

---

## 📊 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| CPU Average | <10% | 1 meter polled every 60 s |
| CPU Peak | <30% | Concurrent OTA download + meter read |
| RAM (all services) | <200 MB | acquisition <40, uploader <40, UI <60 |
| SD Card Writes/day | <30 MB | With log2ram, batched writes |
| Installer UI First Paint | <3 s | On LAN over Wi-Fi |
| Uptime (continuous) | 90 days | Without intervention |
| Power Failures Survived | 100/day | No DB corruption |

---

## 🐛 Troubleshooting

### Device Offline from Cloud >24 h

1. Check Wi-Fi: `nmcli device wifi list` over serial console.
2. Verify MQTT broker reachable: via installer UI → Connection Status.
3. Check queue depth: if >1000 readings, network issue likely.
4. Review logs: `journalctl -u meterhub-uploader -n 100` over console or via UI.

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed flowchart.

---

## 📄 License

Proprietary. Usage restricted to authorized fleet deployments. See [LICENSE](LICENSE).

---

## 📞 Support

- **Installation Issues:** Refer to [docs/COMMISSIONING.md](docs/COMMISSIONING.md).
- **Meter Profile Bugs:** See [docs/METER_PROFILES.md](docs/METER_PROFILES.md) for authoring guide.
- **Cloud Integration:** Check [CLOUD_API_CONTRACT.md](CLOUD_API_CONTRACT.md) for API spec.
- **OTA Releases:** See [docs/OTA_DEPLOYMENT.md](docs/OTA_DEPLOYMENT.md).

For issues or questions, contact the MeterHub engineering team.

---

## 🎓 Credits

Designed for fleet deployment across Indian housing societies. Built on production learnings from edge IoT, distributed systems, and electrical metering standards.
