# MeterHub Installation & Commissioning Guide

**Version:** 1.2.0
**Last Updated:** May 11, 2026
**Audience:** Installation Engineers, Field Technicians, Commissioning Teams

---

## Overview

This guide provides step-by-step instructions for deploying, configuring, and commissioning MeterHub edge gateways in production environments.

---

## Table of Contents

1. [Pre-Installation Checklist](#pre-installation-checklist)
2. [Physical Installation](#physical-installation)
3. [Firmware Deployment](#firmware-deployment)
4. [Device Provisioning](#device-provisioning)
5. [Meter Configuration](#meter-configuration)
6. [Testing & Validation](#testing--validation)
7. [Troubleshooting](#troubleshooting)
8. [Support & Escalation](#support--escalation)

---

## Pre-Installation Checklist

### Hardware Requirements

- [ ] Raspberry Pi Zero 2W with SD card (≥16GB industrial grade)
- [ ] RS485/TTL converter (Waveshare 2.5kV isolated) with cable
- [ ] Power supply (5V, 2A, regulated)
- [ ] DIN-rail enclosure (IP54 minimum)
- [ ] RTC battery (CR2032) if RTC module included
- [ ] Heatsink for Pi (10-15mm, thermal paste)

### Site Survey

- [ ] Meter location accessible for RS485 connection
- [ ] Network connectivity (Ethernet or WiFi) available
- [ ] Power source (mains, isolated) accessible
- [ ] Installation environment: temperature -10°C to +50°C acceptable
- [ ] No corrosive fumes or excessive dust
- [ ] RS485 cable run ≤100 meters (exceeding requires repeater)

### Documentation Gathered

- [ ] Meter datasheet (Modbus registers, baud rate, parity)
- [ ] Site power readings or baseline consumption
- [ ] Provisioning credential set (device key, API endpoint)
- [ ] Network configuration details (WiFi SSID/PSK or static IP)
- [ ] GPS coordinates (if applicable, for commissioning reports)

---

## Physical Installation

### Step 1: Prepare Enclosure

1. Mount DIN-rail in weather-resistant, accessible location
2. Install heatsink on Raspberry Pi using thermal paste
3. Secure Pi to DIN-rail mount or enclosure wall
4. Position RS485 converter adjacent to Pi (minimize cable length)
5. Route RS485 cable along tray to meter location (separate from power lines ≥10 cm)

### Step 2: Connect Hardware

1. **Power**: 5V supply → Pi micro-USB (via 2A-rated fuse)
2. **RS485**: Converter TX+/TX- → Pi GPIO 4/17 (software UART) or USB serial adapter
3. **RTC** (if installed): I2C pins on GPIO
4. **Network** (Ethernet): USB-to-Ethernet adapter, or WiFi via USB dongle
5. **Status LED** (optional): GPIO 27 (positive via 330Ω resistor to 3.3V)

### Step 3: Secure Cabling

- Use crimped connectors on RS485 (prevent corrosion)
- Strain relief on all cable entries
- Label all connections with site ID and meter serial
- Photograph connections before enclosure closure
- Tape over unused GPIO pins (prevent short circuits)

---

## Firmware Deployment

### Step 1: Prepare SD Card

1. Download MeterHub OS image (v1.2.0 or latest from releases)
2. Flash to SD card using **Balena Etcher** or **dd**:
   ```bash
   # On Linux/macOS
   gunzip meterhub-v1.2.0-armv8.img.xz
   sudo dd if=meterhub-v1.2.0-armv8.img of=/dev/sdX bs=4M status=progress
   sync
   ```
3. Verify checksum matches release artifacts
4. Eject SD card safely

### Step 2: Boot Pi and Initial Setup

1. Insert SD card into Raspberry Pi
2. Power on Pi (allow 30-60 seconds for first boot)
3. Monitor console output (if connected to HDMI + keyboard):
   - Systemd startup sequence
   - Acquisition service starting
   - Uploader service initializing
   - Installer UI listening on http://0.0.0.0:8000

### Step 3: Access Installer UI

1. From site network, open browser to Pi IP address (discover via DHCP or static config):
   ```
   http://meterhub.local:8000
   ```
   or
   ```
   http://<pi-ip>:8000
   ```
2. Navigate to **Setup Wizard**
3. Follow on-screen instructions:
   - Select WiFi network (if applicable)
   - Enter provisioning credentials
   - Configure time zone and NTP server
   - Set meter communication parameters

---

## Device Provisioning

### Step 1: Generate Device Credentials

1. Contact cloud team or provisioning service
2. Provide:
   - Device serial (printed on Pi or in docs)
   - Site name and location
   - Meter model and Modbus protocol variant
3. Receive:
   - Device EC/ED25519 public key file
   - API endpoint URL
   - MQTT broker details (AWS IoT Core endpoint)
   - Fallback HTTPS OAuth2 credentials

### Step 2: Enter Provisioning Data in Installer UI

1. In Installer UI, paste provisioning credentials
2. Select meter model from dropdown (or upload custom YAML profile)
3. Test connection to cloud (verification ping)
4. Confirm configuration and save

### Step 3: Verify Cloud Connectivity

1. Check acquisition service logs:
   ```bash
   journalctl -u meterhub-acquisition -n 50 -f
   ```
2. Verify MQTT connection attempts:
   ```bash
   journalctl -u meterhub-uploader -n 50 -f
   ```
3. Confirm telemetry appearing in cloud dashboard within 5 minutes

---

## Meter Configuration

### Step 1: Validate Modbus Connection

1. In Installer UI, navigate to **Meter Testing**
2. Enter Modbus RTU parameters:
   - Baud rate (typically 9600 or 19200)
   - Data bits, parity, stop bits
   - Slave ID (typically 1 for single meter, 1-247 for multi-drop)
3. Click **Test Connection**
4. Verify response time <500 ms, no CRC errors

### Step 2: Configure Meter Profile

1. If meter is Schneider EM6400, profile is pre-loaded ✓
2. For custom meters:
   - Download template YAML from docs/guides/METER_PROFILES_AUTHORING.md
   - Define registers: voltage, current, active power, reactive power, frequency
   - Upload via Installer UI
   - Re-run meter test to validate new profile

### Step 3: Verify Power Readings

1. Take manual meter reading (if display available)
2. Compare to Installer UI live display
3. Typical variance: <2% (Schneider meters ±0.5%)
4. If variance >5%, verify:
   - Modbus baud rate correct
   - Meter multipliers in profile accurate
   - RS485 connection stable (no loose wires)
   - Meter not in sleep/standby mode

---

## Testing & Validation

### Functional Tests

| Test | Procedure | Expected Result |
|------|-----------|-----------------|
| **Local Read** | Use Installer UI meter test | Live power readings visible in <1 sec |
| **Periodic Polling** | Let acquisition run for 5 min | Readings stored in local SQLite (no errors in logs) |
| **Cloud Upload** | Wait for next 5-min upload cycle | Readings appear in cloud dashboard |
| **Offline Resilience** | Disconnect network for 30 min | Queue grows; recovers when reconnected |
| **OTA Readiness** | Check bootloader (Mender) | A/B partition present; rollback possible |

### Performance Benchmarks

- **Acquisition latency:** 50–100 ms per Modbus read
- **Upload frequency:** 5-minute window (configurable)
- **Uptime target:** 99.5% (accounting for planned maintenance)
- **Data loss tolerance:** None for billing; store-and-forward 7 days minimum
- **Response time (UI):** <200 ms for meter test, provisioning updates

### Security Checks

- [ ] Device Ed25519 key in secure storage (/opt/meterhub/.ssh/id_ed25519)
- [ ] MQTT TLS certificate verified (no self-signed warnings)
- [ ] HTTP fallback only if MQTT unavailable
- [ ] No credentials logged to syslog
- [ ] Firewall blocking non-essential ports (UFW enabled)

---

## Troubleshooting

### Pi Won't Boot

**Symptoms:** Red power LED lit, no green activity LED

**Checks:**
1. SD card corrupted? Reflash with correct image (verify checksum)
2. Power supply insufficient? Test with 2A-rated supply
3. Micro-USB cable bad? Try different cable/port

### Modbus Connection Failing

**Symptoms:** Installer UI meter test times out, "CRC Error"

**Checks:**
1. RS485 wiring correct? (A/B swapped is common)
2. Baud rate matches meter? (Check meter manual, typically 9600)
3. Meter responding on different slave ID? Try 0-247
4. RS485 cable run >100m? Add repeater or shorten

### Cloud Connectivity Lost

**Symptoms:** Uploader logs show MQTT timeout, no data in cloud

**Checks:**
1. Network connected? Test: `ping 8.8.8.8` on Pi
2. Credentials valid? Re-provision via Installer UI
3. AWS IoT endpoint reachable? Test: `openssl s_client -connect <endpoint>:8883`
4. Firewall blocking 8883 (MQTT)? Check ISP port restrictions

### High CPU Usage or Crashes

**Symptoms:** Pi unresponsive, uploader/acquisition restarting repeatedly

**Checks:**
1. Acquisition polling too fast? Increase interval in config (default 60 sec)
2. Meter broken? Times out every read → delays accumulate → high latency
3. Database lock? Check: `lsof | grep meterhub`
4. Insufficient RAM? Monitor: `free -m` (Pi Zero has 512MB)

### Data Missing from Cloud

**Symptoms:** Readings in Installer UI but not in cloud dashboard

**Checks:**
1. Uploader running? Check: `systemctl status meterhub-uploader`
2. Queue file growing? `ls -lh /opt/meterhub/queue.db`
3. Logs showing errors? Check: `journalctl -u meterhub-uploader -n 100`
4. Provisioning expired? Re-run setup wizard

---

## Support & Escalation

### First-Line Troubleshooting

1. Check systemd service logs (see above)
2. Verify physical connections (reseat USB, RS485 cables)
3. Power cycle Pi (5-10 second delay before reboot)
4. Reflash firmware if repeated crashes

### Escalation Path

**Level 1 (Field Tech):** Check checklist above, contact site administrator

**Level 2 (Site Admin):** Collect logs:
```bash
sudo journalctl -u meterhub-acquisition -n 1000 > acquisition.log
sudo journalctl -u meterhub-uploader -n 1000 > uploader.log
sudo journalctl -u meterhub-installer-ui -n 1000 > ui.log
```
Send logs + provisioning details to support

**Level 3 (Engineering):** Remote SSH access to Pi (VPN required), live debugging

### Contact Information

- **Cloud Team:** Provisioning issues, credential generation
- **DevOps Team:** OTA updates, firmware releases
- **Hardware Support:** Pi / RS485 converter issues
- **Integration Lab:** Custom meter profile development

---

## Appendix: Quick Checklists

### Pre-Site Checklist

```
Site Name: ___________________  Date: ___________
Installation Engineer: ________  Phone: __________

[ ] Site surveyed (power, network, RS485 run <100m)
[ ] Hardware verified (Pi, SD card, PSU, RS485 converter)
[ ] Documentation gathered (meter datasheet, credentials, site diagram)
[ ] Enclosure prepared (DIN-rail, heatsink, cabling routed)
[ ] Photos taken of connections before final closure
```

### Post-Deployment Checklist

```
Device Serial: _________________  Site ID: ___________
Firmware Version: _____________  Deployment Date: ________

[ ] SD card flashed and verified
[ ] Pi boots successfully (30-60 sec)
[ ] Installer UI accessible (web browser)
[ ] Network configured (DHCP or static IP)
[ ] Provisioning credentials entered
[ ] Meter test shows live readings within 2% tolerance
[ ] Cloud connection verified (telemetry in dashboard)
[ ] Firewall enabled (UFW active)
[ ] Offline queue tested (network disconnect/reconnect)
[ ] Performance baselines recorded
[ ] Site commissioning sign-off obtained
```

---

**Revision History:**
- v1.2.0 (May 11, 2026): Initial version for Phase 6 release

**Next Steps:**
- Phase 7: Fleet management dashboard
- Phase 8: Canary deployment tooling
- Phase 9: Advanced troubleshooting automation
