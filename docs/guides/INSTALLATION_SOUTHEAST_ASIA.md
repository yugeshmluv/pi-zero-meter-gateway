# MeterHub Installation Guide: Southeast Asia & International

**Version:** 1.0  
**Date:** May 2026  
**Target Regions:** Thailand, Vietnam, Philippines, Indonesia, Malaysia

---

## 🌏 Region Quick Reference

| Region | Grid Voltage | Frequency | Power Quality | WiFi Bands | Special Considerations |
|--------|-------------|-----------|--------------|-----------|------------------------|
| **Thailand** | 220V/380V | 50 Hz | Fair (surges) | 2.4G | Single-phase distribution |
| **Vietnam** | 220V/380V | 50 Hz | Poor (unstable) | 2.4G | Frequent brownouts |
| **Philippines** | 220V/480V | 60 Hz | Poor (variable) | 2.4G/5G | **Frequency different** (60 Hz) |
| **Indonesia** | 220V/380V | 50 Hz | Variable | 2.4G | Island isolation |
| **Malaysia** | 230V/400V | 50 Hz | Good | 2.4G/5G | Best power quality |

---

## 🔌 Voltage & Frequency Considerations

### Critical: Philippines (60 Hz vs. 50 Hz)

The Philippines uses **60 Hz grid frequency** (unique in region):

```yaml
# /etc/meterhub/grid_config.yaml
grid:
  frequency_hz: 60.0  # NOT 50 Hz!
  frequency_tolerance: 0.5
  nominal_voltage: 220  # Single-phase
  
acquisition:
  meter_profile: "schneider-em6400-60hz"  # Special variant
  frequency_check_enabled: true  # Monitor grid quality
```

**Consequence:** Standard 50 Hz configs will cause frequency tracking errors.

### Vietnam & Thailand (Power Quality Issues)

Both countries experience frequent voltage sags and surges:

```yaml
# /etc/meterhub/power_quality.yaml
power_monitoring:
  voltage_sag_threshold: 180  # V (below 180V triggers alert)
  voltage_surge_threshold: 240  # V (above 240V triggers alert)
  sag_duration_threshold_ms: 500  # Sustained sags only
  recording_enabled: true  # Log all sags/surges
  
acquisition:
  retry_on_low_voltage: true
  voltage_range: [180, 245]  # Extended tolerance
```

---

## 🌡️ Tropical Climate Adaptations

### High Humidity (80-95% in monsoon)

All Southeast Asian countries experience monsoon humidity:

```yaml
hardware:
  humidity_check_interval_hours: 4
  humidity_alert_threshold: 80
  desiccant_replacement_interval_days: 30  # Monthly in monsoon
  
storage:
  # More aggressive log rotation in humidity
  log_rotation_size_mb: 10
  log_retention_days: 7
  sd_health_check_interval_days: 14
  
firmware:
  # Reduced CPU load in humid conditions (less heat dissipation)
  cpu_frequency_scaling: true
  max_cpu_freq_mhz: 900  # Reduced from 1000
```

**Enclosure Preparation:**
- Use enclosure with IP65 rating (splash-proof, not dustproof only)
- Desiccant pack: Replace monthly during wet season
- Ventilation: 6-8 small holes (1cm diameter) to allow air circulation
- Silicone sealant on all cable entries (marine-grade)

### Extreme Heat (35-40°C common)

```yaml
hardware:
  thermal_throttle_temp: 50  # Reduce frequency at 50°C
  thermal_shutdown_temp: 55  # Shut down at 55°C
  
acquisition:
  polling_interval_offset: +30  # Increase to 90s in extreme heat
  modbus_timeout_s: 8  # Longer timeouts at high temp
  
storage:
  # SD card endurance is reduced at high temps
  log_rotation_size_mb: 5  # Smaller logs
  trim_enabled: true  # TRIM data for longevity
```

**Physical Mitigation:**
- Mount enclosure with white paint (reduces temp by ~10°C vs. black)
- Add passive heat sink if multiple enclosures stacked
- Avoid direct sun; prefer north-facing wall mount

---

## 🌐 Internet Connectivity (Region-Specific)

### Vietnam (Unstable ISPs)

Vietnam ISPs frequently drop connections (VDSL instability):

```yaml
network:
  # Aggressive connection recovery
  connection_timeout_s: 15  # Quick detection of failure
  reconnect_backoff_base_ms: 1000
  reconnect_backoff_max_ms: 30000
  max_reconnect_attempts: 10
  
cloud:
  # MQTT with extended offline buffering
  mqtt_fallback_to_https: true
  offline_queue_days: 7  # 7 days worth of readings
  queue_compression: true  # Reduce storage space
```

### Philippines (DNS & Routing)

Philippines has unreliable DNS; use IP-based fallback:

```yaml
network:
  primary_dns: "8.8.8.8"  # Google
  secondary_dns: "1.1.1.1"  # Cloudflare
  ntp_server: "0.pool.ntp.org"  # Global pool
  
  # Use hardcoded IPs as fallback
  mqtt_endpoint_ip: "52.123.45.67"  # Your AWS region IP
  mqtt_endpoint_dns: "iot.us-east-1.amazonaws.com"
```

### Indonesia (Island Isolation)

Many sites have no internet backup:

```yaml
cloud:
  # Extended offline resilience
  offline_queue_days: 14  # 2 weeks of readings
  local_analytics_enabled: true  # Compute locally
  sync_retry_days: 30  # Retry for 30 days if no connection
  
storage:
  # Reserve space for extended buffering
  min_free_space_mb: 200  # Keep 200MB always free
  aggressive_cleanup: false  # Don't delete old readings
```

---

## 🔐 Country-Specific Compliance

### Thailand (NBTC Certification)

Thailand's NBTC (National Broadcasting and Telecommunications Commission) regulates WiFi:

```yaml
hardware:
  wifi_country_code: "TH"
  wifi_tx_power_dbm: 20  # Max in Thailand
  channel_set: "1-13"  # Thai regulatory domain
```

### Indonesia (No Specific Requirements)

Indonesia allows broader WiFi use but power instability requires monitoring:

```yaml
hardware:
  wifi_country_code: "ID"
```

### Malaysia (MCMC Compliance)

Malaysia's MCMC requires proper WiFi certification:

```yaml
hardware:
  wifi_country_code: "MY"
  tls_version: "1.2"  # Malaysia enforces TLS 1.2+
```

---

## 📦 Meter Profile Selection by Region

| Region | Recommended Meters | Status | Notes |
|--------|-------------------|--------|-------|
| **Thailand** | Schneider EM6400, Siemens 7KM | Supported | Single-phase common |
| **Vietnam** | Schneider EM6400, Landis Gyr | Supported | Industrial 3-phase |
| **Philippines** | Schneider EM6400-60Hz | **60 Hz variant** | Must use 60Hz profile |
| **Indonesia** | Schneider EM6400, ABB A44 | Supported | Broad meter support |
| **Malaysia** | Schneider EM6400, ABB A44 | Supported | High power quality |

**Important:** Philippines requires special 60 Hz meter profile.

---

## 🛠️ Installation Steps (Region-Specific)

### Step 1: Pre-Installation Environment Check

```bash
# Check local power quality (if available)
# 1. Measure voltage with multimeter
#    - Should be within ±10% of nominal (220V ± 22V)
# 2. Check for visible interference near panel
#    - Industrial machinery running? 
#    - Heavy load equipment nearby?

# 3. WiFi signal survey
#    - Use phone WiFi analyzer app
#    - Look for 2.4 GHz availability (all regions)
#    - Note interference from microwaves, cordless phones
```

### Step 2: Regional Hardware Configuration

```bash
# Edit regional config BEFORE powering on
nano /boot/meterhub_config.yaml

# For Philippines: MUST specify 60 Hz
grid_frequency_hz: 60.0

# For Vietnam/Thailand: Extended voltage range
voltage_range: [180, 245]

# For Indonesia: Extended offline mode
offline_queue_days: 14
```

### Step 3: Initial Power-On Verification

```bash
# Boot pi and let it run for 2 minutes
# 1. Check meter readings are stable
sudo journalctl -u meterhub-acquisition -n 50

# 2. Verify grid frequency detection
sqlite3 /var/cache/meterhub/telemetry.db \
  "SELECT AVG(frequency_hz) FROM meter_readings;"

# In Philippines: Should be ~60.0
# In other regions: Should be ~50.0
```

---

## 📞 Regional Support & Escalation

### Thailand Support
- **Language:** Thai & English
- **Hours:** 8 AM - 5 PM (Bangkok Time)
- **Email:** support-thailand@meterhub.io
- **Hotline:** +66-XXXX-XXXX
- **Common Issues:** Power surges, WiFi interference from factories

### Vietnam Support
- **Language:** Vietnamese & English
- **Hours:** 7 AM - 6 PM (Hanoi Time)
- **Email:** support-vietnam@meterhub.io
- **Common Issues:** Connection drops, DNS failures, frequent brownouts

### Philippines Support
- **Language:** English & Tagalog
- **Hours:** 8 AM - 5 PM (Manila Time)
- **Email:** support-philippines@meterhub.io
- **Hotline:** +63-XXX-XXXX
- **Common Issues:** 60 Hz compatibility, island isolation, power instability

### Indonesia Support
- **Language:** Indonesian & English
- **Hours:** 8 AM - 5 PM (Jakarta Time)
- **Email:** support-indonesia@meterhub.io
- **Common Issues:** Island isolation, extended offline buffering, meter variety

### Malaysia Support
- **Language:** English & Malay
- **Hours:** 8 AM - 5 PM (Kuala Lumpur Time)
- **Email:** support-malaysia@meterhub.io
- **Common Issues:** None (best power quality); mostly expansion questions

---

## ⚠️ Critical Configuration Mistakes by Region

| Mistake | Impact | Fix |
|---------|--------|-----|
| Using 50 Hz profile in **Philippines (60 Hz)** | Frequency tracking off by 20%; meter appears offline | Use `schneider-em6400-60hz` profile |
| Not monitoring voltage in **Vietnam/Thailand** | Undersized readings during sags | Enable `voltage_sag_monitoring` |
| Sealed enclosure in **humid regions** | Condensation damage in 2-3 months | Drill 6-8 ventilation holes |
| Standard desiccant in **monsoon season** | Desiccant saturates in 1-2 weeks | Replace monthly, use indicating packs |
| Hardcoded DNS in **Philippines** | Cloud sync fails when ISP DNS down | Use hardcoded IP fallback |

---

## ✅ Regional Validation Checklist

### General (All Regions)
- [ ] Device boots within 60 seconds
- [ ] Meter polling stable for >1 hour
- [ ] No readings are negative or zero
- [ ] Frequency reading is within ±0.2 Hz
- [ ] WiFi connection stable >2 hours

### Philippines ONLY
- [ ] Frequency reading is ~60.0 Hz (NOT 50 Hz)
- [ ] Meter profile contains "60hz" in filename
- [ ] No frequency stability errors in logs

### Vietnam/Thailand ONLY
- [ ] Monitor voltage sag detection working
- [ ] Extended offline queue configured
- [ ] Connection recovery tested (simulate WiFi cut)

### Indonesia ONLY
- [ ] Offline queue configured for 14+ days
- [ ] SD card space adequate (minimum 500 MB free)
- [ ] Monthly backup to cloud tested (when available)

### Malaysia ONLY
- [ ] Standard configuration working
- [ ] Optional: Enable 5 GHz WiFi (if router supports)
