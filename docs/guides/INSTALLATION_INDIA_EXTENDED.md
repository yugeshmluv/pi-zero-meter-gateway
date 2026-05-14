# MeterHub Installation Guide: India (EXTENDED)

**Version:** 1.0
**Date:** May 2026
**Target Regions:** Pan-India (South, North, East, West, Northeast)

---

## 📍 Quick Region Selector

| Region | State/City | Meter Type | WiFi Freq | Grid Frequency | Special Notes |
|--------|-----------|-----------|----------|----------------|---------------|
| **South** | Bangalore, Chennai, Hyderabad | Schneider EM6400 | 2.4 GHz | 50 Hz | High humidity, industrial areas |
| **North** | Delhi, Noida, Pune | Schneider EM6400, Siemens | 2.4 GHz | 50 Hz | Variable power quality |
| **East** | Kolkata, Guwahati | Schneider EM6400 | 2.4 GHz | 50 Hz | High salt/moisture (coastal) |
| **West** | Mumbai, Gujarat | Schneider EM6400 | 2.4 GHz | 50 Hz | High ambient temperature |

---

## 🔧 Pre-Installation Checklist

### Hardware Requirements (Pan-India)

```
□ Raspberry Pi Zero W (1 GHz ARM11, 512 MB RAM)
□ Waveshare TTL to RS485 (C) Isolated Converter
  - Galvanic isolation 2.5 kV (mandatory for safety)
  - TVS diodes on A/B lines
  - Polarity: A=green, B=white, GND=black
□ Industrial SD card (32 GB, Class 10, rated for 1000+ P/E cycles)
  - Kingston Canvas Select, SanDisk Industrial, or equivalent
  - Avoid consumer-grade cards (high failure rate in panels)
□ DIN-rail mount (IP54 enclosure) for electrical panel
□ CAT-5e/CAT-6 shielded RS485 cable (Belden, Lemo, or equivalent)
  - Max 1000m per RS485 spec (typically <50m indoors)
  - Twisted pair for noise immunity
□ USB Power supply: 5V/2.5A (USB-C microB adapter)
  - Must be clean (no ripple >100mV)
□ Temp/humidity logger (optional, for diagnostics)
```

### Electrical Panel Access

**Safety Requirements:**
- [ ] Panel is de-energized or main breaker can be safely switched off
- [ ] Electrician or authorized person is present
- [ ] Proper PPE: insulated gloves, safety glasses, no metal jewelry
- [ ] Panel cover has adequate ventilation for Pi Zero W (does not need active cooling)

**Preferred Installation Location:**
- Inside enclosure, away from main breaker heat
- At least 30 cm from moisture sources
- Not directly above/below wet-running breakers

---

## 🌐 Region-Specific WiFi Configuration

### South India (Bangalore, Hyderabad, Chennai)

**Environmental Factors:**
- High humidity (60-80%)
- Industrial/IT park congestion (2.4 GHz crowded)
- Occasional power surges during monsoon

**Configuration:**

```yaml
# /etc/meterhub/network_config.yaml
wifi:
  ssid: "YourNetwork"
  psk: "secure_passphrase"
  country_code: "IN"
  frequency: "2.4G"  # Only 2.4 GHz supported on Pi Zero W
  tx_power: 20       # dBm (max allowed in India: +20 dBm)

network:
  static_ip: false
  dhcp_timeout_s: 30  # South India can be slow to assign IP
  ntp_server: "0.in.pool.ntp.org"  # India NTP pool

power:
  polling_interval_s: 60
  low_power_mode: true  # Recommended for industrial areas
```

**Recommended WiFi Bands (India):**
- 2.4 GHz: Channels 1-13 (ISM band, same as North America + channel 13)
- 5 GHz: NOT recommended for Pi Zero W (most don't have 5G module)

**WiFi Troubleshooting (South):**
- **Issue:** WiFi drops every ~5 minutes → Solution: Disable WiFi power saving (done by default in MeterHub)
- **Issue:** Very slow IP assignment → Solution: Increase DHCP timeout to 40-45s
- **Issue:** Weak signal in basement panels → Solution: Use WiFi repeater or Ethernet bridge via PoE

---

### North India (Delhi, Pune, Noida)

**Environmental Factors:**
- Extreme temperature variation (10°C winter → 45°C summer)
- Frequent power cuts and unpredictable surges
- Industrial areas with high electromagnetic interference (EMI)

**Configuration:**

```yaml
# /etc/meterhub/network_config.yaml
wifi:
  ssid: "YourNetwork"
  psk: "secure_passphrase"
  country_code: "IN"
  frequency: "2.4G"
  tx_power: 20

network:
  static_ip: true
  ip_address: "192.168.1.100"
  gateway: "192.168.1.1"
  dns: ["8.8.8.8", "8.8.4.4"]  # Google DNS (reliable in north)
  ntp_server: "0.in.pool.ntp.org"

power:
  polling_interval_s: 60
  low_power_mode: true  # Important for variable power supplies
  watchdog_enabled: true  # Recover from freezes

acquisition:
  modbus_timeout_s: 5  # Longer timeout for EMI-prone areas
  retry_count: 3
  backoff_strategy: "exponential"  # 100ms, 200ms, 500ms, 2s
```

**Temperature Considerations:**
- Pi Zero W operates 0-50°C (nominal)
- At 45°C+: Clock throttling kicks in (performance drops)
- Ensure DIN enclosure has ventilation holes (not sealed)
- SD card becomes slower >50°C (rare but monitor via SMART data)

**Power Quality Issues:**
- Many areas have frequent brownouts (220V → 200V sag)
- **Solution:** Use regulated PSU with wide input range (100-240V, ±10% tolerance)
- **Watchdog:** Enable systemd watchdog (auto-reboot on freeze every 10 min)

**EMI Mitigation:**
- Use shielded RS485 cable
- Ground the shield at panel entry point only (single-point grounding)
- Keep RS485 lines >30 cm from power lines (if possible)

---

### East India (Kolkata, Guwahati, Assam)

**Environmental Factors:**
- High humidity, salt air (coastal), frequent rain
- Mold/fungal growth in electronics (monsoon June-Sep)
- Occasional flooding in low-lying panel rooms

**Configuration:**

```yaml
# /etc/meterhub/network_config.yaml
wifi:
  ssid: "YourNetwork"
  psk: "secure_passphrase"
  country_code: "IN"
  frequency: "2.4G"
  tx_power: 20

network:
  dns: ["1.1.1.1", "1.0.0.1"]  # Cloudflare (lower latency than Google in east)

storage:
  # Extra conservative log rotation
  log_rotation_days: 3  # More frequent rotation
  temp_files_cleanup_hours: 6

hardware:
  humidity_threshold: 75  # Alert if enclosure humidity >75%
  temp_threshold: 40  # Alert at 40°C (lower margin for coastal areas)
  sd_health_check: true  # Monthly SMART checks
```

**Corrosion Prevention:**
- Use stainless steel hardware (not zinc-plated)
- Apply conformal coating on Pi board (Parylene-C recommended)
- Enclosure should have desiccant pack (silica gel, changed quarterly)
- RS485 connectors: M12 A-coded (food-grade stainless) for moisture seal

**Monsoon Preparation (June-September):**
- Monthly inspection of enclosure for condensation
- Test SD card backup recovery (SDcards fail more in humidity)
- Increase UPS battery capacity (power cuts are longer)
- Check GPS/NTP sync (cloud uptime critical for data)

---

### West India (Mumbai, Ahmedabad, Surat)

**Environmental Factors:**
- Extreme heat (40-45°C sustained in summer)
- High dust (industrial areas, ports)
- Salt air (coastal, especially Mumbai/Surat)
- Very high ambient humidity (Arabian Sea proximity)

**Configuration:**

```yaml
# /etc/meterhub/network_config.yaml
wifi:
  ssid: "YourNetwork"
  psk: "secure_passphrase"
  country_code: "IN"
  frequency: "2.4G"
  tx_power: 20

power:
  polling_interval_s: 60
  low_power_mode: true  # Essential in summer
  cpu_frequency_scale: true  # Reduce clock at 40°C+

hardware:
  # Thermal throttling thresholds
  temp_warning: 45
  temp_critical: 50

acquisition:
  # May see voltage fluctuations from AC compressor loads
  voltage_range: [190, 250]  # Wider acceptable range
  frequency_tolerance: 0.5  # Hz deviation tolerance
```

**Heat Management:**
- DIN enclosure must have ventilation (passive cooling only)
- Paint enclosure white (reflects ~40% more heat than black)
- Mount on south face of panel if possible (more air circulation)
- Consider adding radiant barrier behind enclosure
- SD card: Use industrial grade with high temp spec (0-60°C)

**Dust & Corrosion:**
- Use stainless steel RS485 connectors (not brass)
- Monthly air-blower cleaning (compressed air, 6 bar max)
- Conformal coating on Pi board (essential for port cities)
- Filter cloth over ventilation holes (prevents dust ingress)

---

## 🛠️ Installation Steps (Universal)

### Step 1: Prepare Hardware

```bash
# On your laptop/desktop:
# 1. Flash image to SD card
xzcat meterhub-v1.2.0-20260512.img.xz | sudo dd bs=4M of=/dev/sdX

# 2. Eject SD card
sudo eject /dev/sdX

# 3. Verify power supply (measure output voltage with multimeter)
# Should read 5.0V ±0.2V, no ripple
```

### Step 2: Mount Hardware in Panel

1. **Disconnect panel power** (or ensure main breaker)
2. **Mount Pi in DIN enclosure**
   - Ensure USB power header doesn't short on DIN rail
   - Leave 2-3 cm clearance above for airflow
3. **Connect RS485 converter to Pi Zero**
   ```
   Pi TX (GPIO 14) → TTL RX pin (green wire)
   Pi RX (GPIO 15) → TTL TX pin (blue wire)
   Pi GND → TTL GND pin (black wire)
   ```
4. **Route RS485 cable to meter**
   - A (green) to meter terminal A
   - B (white) to meter terminal B
   - GND (black) to meter ground or GND terminal
5. **Connect USB power to Pi**
   - Use regulated 5V PSU (2.5A minimum)
   - Power-on LED on Pi should light immediately

### Step 3: Configure Network (via Installer UI)

```
1. Power on Pi (boots in ~45 seconds)
2. Phone/tablet scans QR code on device label
3. Opens http://192.168.4.1/setup
4. Scan QR with meter profile → auto-fills settings
5. Select WiFi network, enter PSK
6. Choose meter profile (Schneider EM6400 default)
7. Test Modbus connection
8. Confirm and provision
```

### Step 4: Verify Installation

```bash
# SSH to device (once configured)
ssh meterhub@<device_ip>

# Check service status
sudo systemctl status meterhub-acquisition
sudo systemctl status meterhub-uploader
sudo systemctl status meterhub-installer-ui

# View real-time logs
sudo journalctl -u meterhub-acquisition -f

# Verify meter readings (should see one per minute)
sqlite3 /var/cache/meterhub/telemetry.db \
  "SELECT * FROM meter_readings ORDER BY id DESC LIMIT 5;"
```

---

## 📞 Support & Troubleshooting (by Region)

### South India
- **Contact:** support-south@meterhub.io
- **Response Time:** 4 hours (9 AM - 6 PM IST)
- **Common Issues:** WiFi dropout (solution: mesh network), DHCP slow assignment

### North India
- **Contact:** support-north@meterhub.io
- **Common Issues:** Power surges, EMI interference, temperature extremes

### East India
- **Contact:** support-east@meterhub.io
- **Common Issues:** Corrosion, humidity, monsoon water ingress

### West India
- **Contact:** support-west@meterhub.io
- **Common Issues:** Heat throttling, salt corrosion, dust accumulation

---

## 📊 Regional Performance Targets

| Metric | South | North | East | West |
|--------|-------|-------|------|------|
| **Availability** | 99.5% | 98.5% | 98.0% | 99.0% |
| **Polling Success** | >99.8% | >98.5% | >98.0% | >99.5% |
| **WiFi Uptime** | 99.2% | 97.5% | 97.0% | 98.5% |
| **Cloud Sync (MQTT)** | 99.1% | 98.0% | 97.5% | 98.8% |
| **Data Loss (24h)** | <0.5% | <2% | <3% | <1% |

---

## ✅ Regional Certification Checklist

- [ ] Device powers on within 2 seconds
- [ ] Meter polling starts within 30 seconds
- [ ] First cloud sync within 5 minutes
- [ ] WiFi connection stable >2 hours
- [ ] Temperature within spec (device + SD card)
- [ ] No SD card wear beyond expected (1% per month max)
- [ ] Voltage reading within ±2% of clamp meter
- [ ] Frequency stays within ±0.1 Hz of grid
