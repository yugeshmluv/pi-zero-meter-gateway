# MeterHub Troubleshooting Runbook

**Version:** 1.0
**Date:** May 2026
**Updated:** May 12, 2026

---

## Quick Diagnosis Tool

```bash
# Run this first to gather diagnostics
cd /opt/meterhub && sudo ./diagnose.sh

# Or manually:
echo "=== SYSTEM STATUS ==="
systemctl status meterhub-acquisition meterhub-uploader meterhub-installer-ui

echo "=== RECENT ERRORS (Last 50 lines) ==="
journalctl -xe -n 50

echo "=== DISK SPACE ==="
df -h /

echo "=== MEMORY USAGE ==="
free -h

echo "=== MODBUS CONNECTION ==="
sqlite3 /var/cache/meterhub/telemetry.db "SELECT MAX(timestamp_utc) FROM meter_readings;"

echo "=== CLOUD UPLOADS ==="
sqlite3 /var/lib/meterhub/state.db "SELECT * FROM sync_state LIMIT 1;"
```

---

## Problem Categories

1. [Device Won't Boot](#1-device-wont-boot)
2. [Meter Polling Issues](#2-meter-polling-issues)
3. [Cloud Sync Failures](#3-cloud-sync-failures)
4. [WiFi/Network Problems](#4-wifinetwork-problems)
5. [Performance & Memory](#5-performance--memory)
6. [Hardware Issues](#6-hardware-issues)

---

## 1. Device Won't Boot

### Symptom: No LED lights, no activity

**Likely Cause:** Power supply failure or SD card issue

**Troubleshooting:**

1. **Check Power Supply**
   ```bash
   # Measure with multimeter at Pi's USB port
   # Should read: 5.0V ±0.2V (4.8-5.2V acceptable)
   # If <4.8V: PSU is undersized or cable has high resistance

   # Check PSU spec
   cat /proc/cpuinfo | grep "Revision"  # Check Pi version
   # Pi Zero W needs minimum 2.5A at 5V

   # Solution: Replace PSU with higher capacity (2.5A+)
   ```

2. **Test with Known-Good SD Card**
   ```bash
   # If available, use a different SD card
   # If this boots: Your original SD card is corrupted
   # Solution: Re-flash SD card with fresh image
   ```

3. **Check SD Card Slot**
   ```bash
   # SD card may be loose
   # Gently reinsert SD card with firm click
   # Reboot Pi
   ```

### Symptom: LED blinks once then nothing

**Likely Cause:** SD card not properly flashed or corrupted

**Troubleshooting:**

```bash
# On laptop, re-flash image:
xzcat meterhub-v1.2.0-20260512.img.xz | sudo dd bs=4M of=/dev/sdX status=progress

# Wait for dd to complete (no partial flashes)
sudo sync
sudo eject /dev/sdX

# Reinsert and boot Pi
```

### Symptom: LED on, but system hangs after 10 seconds

**Likely Cause:** Corrupted filesystem or hardware fault

**Troubleshooting:**

```bash
# Symptom 1: Pi reaches bootloader but kernel doesn't load
# → SD card filesystem corrupted
# → Solution: Re-flash SD card

# Symptom 2: Kernel loads, services fail
# → Check logs:
journalctl -b --no-pager | head -100

# Look for:
# - "modprobe: FATAL" → Missing kernel module
# - "meterhub: error" → Service error
# - "Out of memory" → RAM issue (rare on Pi Zero W)
```

---

## 2. Meter Polling Issues

### Symptom: No meter readings (telemetry.db empty)

**Likely Cause:** Modbus connection failure

**Troubleshooting:**

1. **Check Acquisition Service Status**
   ```bash
   systemctl status meterhub-acquisition

   # Output should show: active (running)
   # If failed: systemctl start meterhub-acquisition
   ```

2. **Check Modbus Connection**
   ```bash
   # View recent logs
   journalctl -u meterhub-acquisition -n 20

   # Look for:
   # - "Failed to open /dev/ttyUSB0" → Serial device issue
   # - "Modbus connection timeout" → Meter not responding
   # - "Register not found" → Meter profile mismatch
   ```

3. **Verify Serial Device Exists**
   ```bash
   ls -la /dev/ttyUSB* /dev/ttyAMA* /dev/serial*

   # Should show at least one device (e.g., /dev/ttyUSB0)
   # If empty: RS485 converter not connected or not detected
   # Solution: Check USB connection, try different USB port
   ```

4. **Check Meter Profile Configuration**
   ```bash
   cat /etc/meterhub/profiles/schneider-em6400.yaml

   # Verify:
   # - device_name matches actual meter
   # - slave_id matches meter's slave address (usually 1)
   # - registers list contains expected readings (totalizer_kwh, instant_kw)
   ```

5. **Test Modbus Connection Manually**
   ```bash
   # Install pymodbus CLI tool
   sudo pip install pymodbus

   # Query meter (example: slave 1, register 0 = frequency)
   python -m pymodbus.client.serial --device /dev/ttyUSB0 \
     --baudrate 9600 --address 1 --registers 0

   # Should return frequency value (50 Hz for India/SE Asia)
   # If timeout: Meter not responding
   # If value garbage: Baud rate or parity wrong
   ```

### Symptom: Readings only work sporadically (50% success rate)

**Likely Cause:** RS485 connection intermittent or power quality issue

**Troubleshooting:**

1. **Check RS485 Wiring**
   ```
   ✓ Correct:
     Pi TX → RS485 RX (converter input)
     Pi RX → RS485 TX (converter output)
     Pi GND → RS485 GND

   ✗ Common Mistake:
     Pi TX → RS485 TX (swapped!)
     Pi RX → RS485 RX (swapped!)
   ```

2. **Check Cable Quality**
   ```bash
   # Use continuity tester on RS485 A/B lines
   # Both should measure ~60 ohms resistance (twisted pair impedance)

   # If open (infinite): Cable broken
   # If shorted (<10Ω): Wires touching
   # If very high (>1000Ω): Corrosion in connectors
   ```

3. **Verify Termination Resistor**
   ```bash
   # For long cables (>100m), RS485 should have 120Ω terminator
   # At meter end: Connect 120Ω resistor between A and B
   # (Typically built into commercial Modbus meters)
   ```

4. **Check Power Quality**
   ```bash
   # Meter may not respond during voltage sags
   # Monitor: journalctl -u meterhub-acquisition -f
   # Look for: "Modbus timeout" during periods of readings

   # Enable power monitoring:
   # (Add to acquisition config)
   voltage_monitoring: true
   ```

### Symptom: Readings are all zeros or negative values

**Likely Cause:** Meter profile register mapping error

**Troubleshooting:**

```bash
# Check actual meter readings via Modbus
pymodbus /dev/ttyUSB0 --slave 1 --registers 0-20

# Compare with expected values in profile YAML
# Look for mismatched scale factors

# Example: If totalizer_kwh reads as 1000x actual:
# In YAML, check scale_factor: should be 1.0 not 1000.0

# Fix: Edit profile and verify scale factors
nano /etc/meterhub/profiles/schneider-em6400.yaml
systemctl restart meterhub-acquisition
```

### Symptom: Occasional CRC errors ("Modbus CRC failed")

**Likely Cause:** Electrical noise on RS485 lines

**Troubleshooting:**

1. **Check Cable Routing**
   ```
   ✗ Bad:  RS485 cable runs alongside 220V power lines
   ✓ Good: RS485 cable runs >30cm from power lines

   Solution: Reroute cable away from power lines
   ```

2. **Check Cable Shielding**
   ```bash
   # RS485 should use shielded twisted pair cable
   # Shield should be grounded at one end only (meter or Pi)
   # Not at both ends (creates ground loop)

   # If experiencing CRC errors:
   # - Check shield continuity (should be <1Ω)
   # - Verify ground connection at only one end
   ```

3. **Reduce Modbus Polling Frequency** (temporary)
   ```yaml
   # In acquisition config:
   acquisition:
     polling_interval_s: 120  # Increase from 60 to 120
     modbus_timeout_s: 10     # Increase timeout
     retry_count: 5           # Allow more retries

   # Slower polling may improve reliability
   # (Not ideal; indicates cable/noise problem)
   ```

---

## 3. Cloud Sync Failures

### Symptom: Readings stored locally but not syncing to cloud

**Likely Cause:** Cloud connectivity issue

**Troubleshooting:**

1. **Check Cloud Sync Service**
   ```bash
   systemctl status meterhub-uploader

   # If not running:
   systemctl start meterhub-uploader
   systemctl log -u meterhub-uploader -n 50
   ```

2. **Check WiFi Connection**
   ```bash
   ip link show wlan0
   # Should show: "state UP"

   # If state DOWN:
   sudo nmtui  # Network manager UI
   # Or:
   wifi scan  # Scan for networks
   wifi connect "YourSSID"
   ```

3. **Check Cloud Credentials**
   ```bash
   # Verify AWS IoT certificates exist
   ls -la /etc/meterhub/certs/
   # Should show: device.crt, device.key, ca.pem

   # If missing: Provisioning incomplete
   # Solution: Run provisioning again via installer-ui
   ```

4. **Test Connectivity to AWS IoT**
   ```bash
   # Test MQTT endpoint reachability
   openssl s_client -connect <mqtt_endpoint>:8883 \
     -cert /etc/meterhub/certs/device.crt \
     -key /etc/meterhub/certs/device.key \
     -CAfile /etc/meterhub/certs/ca.pem -brief

   # Should show: "Verify return code: 0 (ok)"
   # If "verify return code: 1": Certificate issue
   ```

5. **Check Queue Status**
   ```bash
   sqlite3 /var/cache/meterhub/telemetry.db \
     "SELECT COUNT(*) FROM meter_readings;"

   # Should show number of unsent readings
   # If stays same for >1 hour: Uploader stuck
   # Solution: systemctl restart meterhub-uploader
   ```

### Symptom: MQTT connects, but uploads fail

**Likely Cause:** Message format or payload size issue

**Troubleshooting:**

```bash
# Check recent upload errors
journalctl -u meterhub-uploader -n 50 | grep -i "publish\|fail"

# If message: "Payload too large"
# → Batch size too big
# → Reduce batch size in config:
uploading:
  batch_size: 3  # Reduce from 5 to 3

# If message: "Topic not found" or "Access denied"
# → Device not subscribed to correct topic
# → Check AWS IoT policy and topic settings
```

### Symptom: WiFi connected, but DNS resolution fails ("Cannot resolve api.meterhub...")

**Likely Cause:** DNS configuration issue

**Troubleshooting:**

```bash
# Check DNS servers
cat /etc/resolv.conf

# If empty or incorrect:
sudo nano /etc/resolv.conf
# Add: nameserver 8.8.8.8
# Add: nameserver 8.8.4.4

# Test DNS resolution
nslookup google.com
# Should return IP address

# If still fails: ISP DNS blocked
# Solution: Use hardcoded IP for cloud endpoint
nano /etc/meterhub/device_config.json
# Change mqtt_endpoint from DNS name to IP address
```

---

## 4. WiFi/Network Problems

### Symptom: WiFi shows "connected" but no internet

**Likely Cause:** DHCP failure or gateway issue

**Troubleshooting:**

```bash
# Check IP assignment
ip addr show wlan0

# If "inet" missing: No IP address assigned
# Force DHCP renewal:
sudo dhclient -v wlan0

# Check gateway
ip route show
# Should show: "default via <gateway_ip>"

# If missing:
sudo dhclient -r wlan0  # Release
sudo dhclient wlan0     # Renew

# Test connectivity
ping 8.8.8.8
# If works: DNS is issue (see above)
```

### Symptom: WiFi keeps dropping every 5-10 minutes

**Likely Cause:** Excessive power saving or interference

**Troubleshooting:**

1. **Check WiFi Power Saving**
   ```bash
   iw dev wlan0 get power_save
   # Should show: "Power save: off"

   # If on:
   iw dev wlan0 set power_save off
   ```

2. **Check for Interference**
   ```bash
   # Use WiFi analyzer on phone (WiFi Analyzer app)
   # Look for overlapping networks on same channel

   # If congested:
   # Change router to less-congested channel (1, 6, 11 for 2.4GHz)
   # Or use 5GHz band (if router supports and Pi has 5G module)
   ```

3. **Check WiFi Rate**
   ```bash
   iw dev wlan0 station dump | grep "bitrate"

   # Should be >6 Mbps
   # If <2 Mbps: Weak signal or interference
   # Solution: Move Pi closer to router or use WiFi extender
   ```

### Symptom: Connection fails after Pi reboot ("Failed to associate")

**Likely Cause:** PSK/passphrase issue or incomplete provisioning

**Troubleshooting:**

```bash
# Check saved WiFi credentials
nmcli con show
nmcli con show "YourSSID"

# If shows wrong password:
nmcli con delete "YourSSID"
sudo nmtui  # Re-enter credentials

# Or manually:
sudo nano /etc/NetworkManager/system-connections/<SSID>.nmconnection
# Verify: psk=<correct_password>
```

---

## 5. Performance & Memory

### Symptom: System becomes slow, becomes unresponsive

**Likely Cause:** Memory leak or high CPU usage

**Troubleshooting:**

```bash
# Check memory usage
free -h
# If <50 MB available: Memory issue

# Identify memory-hogging process
ps aux --sort=-%mem | head -10

# Check CPU usage
top -b -n 1 | head -20

# Look for processes using >20% CPU
# If meterhub-uploader uses >30% CPU:
# → Connection loop or large batch
# → Solution: Reduce batch_size or increase upload interval

# If meterhub-acquisition uses >15% CPU:
# → Modbus communication issue
# → Solution: Check meter connection, increase timeout
```

### Symptom: SD card fills up ("Disk /dev/mmcblk0p2 100% full")

**Likely Cause:** Excessive logging or database growth

**Troubleshooting:**

```bash
# Check disk usage
df -h
du -sh /var/log
du -sh /var/cache/meterhub
du -sh /var/lib/meterhub

# Clear old logs
sudo journalctl --vacuum=time=7d  # Keep only 7 days

# Archive old readings (optional)
sqlite3 /var/cache/meterhub/telemetry.db \
  "DELETE FROM meter_readings WHERE timestamp_utc < datetime('now', '-30 days');"

# Rebuild database (vacuum = defrag)
sqlite3 /var/cache/meterhub/telemetry.db "VACUUM;"
```

### Symptom: Pi reboots unexpectedly

**Likely Cause:** Watchdog timeout or thermal shutdown

**Troubleshooting:**

```bash
# Check for watchdog resets
journalctl -b -1 | grep -i "watchdog"

# If found: System was locked up
# → Increase watchdog timeout:
nano /etc/systemd/system.conf
# Set: RuntimeWatchdogSec=20

# Check for thermal throttling/shutdown
journalctl | grep -i "thermal"

# If throttling:
# → System temperature >85°C
# → Improve enclosure ventilation
# → Check for blocked fans (if any)
```

---

## 6. Hardware Issues

### Symptom: Meter reads correct voltages but power is zero

**Likely Cause:** Current transformer (CT) not connected properly

**Troubleshooting:**

```
✓ Correct CT connection:
  CT primary (from meter breaker) → Live conductor
  CT secondary → Meter current input

✗ Common mistakes:
  - CT on neutral line (reads zero current)
  - CT not fully engaged on conductor
  - CT terminals reversed (negative reading)

Check with clamp meter:
1. Measure voltage with clamp meter at breaker (should be ~220V)
2. Measure current with clamp meter on same conductor
3. Compare with Pi reading (should match within 5%)
4. If current=0 but clamp shows current: CT not connected
```

### Symptom: Meter intermittently shows "No response" status

**Likely Cause:** Loose connector or corroded terminals

**Troubleshooting:**

```bash
# Physical inspection:
1. Check RS485 A/B connector for loose pin
2. Gently wiggle connector while monitoring readings
3. If readings drop: Connector is loose
   → Apply dielectric grease and reconnect firmly
4. Check for corrosion (green/white deposits)
   → Clean with electronics contact cleaner
5. Replace connector if damaged
```

### Symptom: Flashing lights/LED on/off repeatedly

**Likely Cause:** Power supply voltage instability

**Troubleshooting:**

```bash
# Check power supply output with oscilloscope
# Should be stable 5.0V with <50mV ripple

# Temporarily use different PSU
# If problem goes away: Original PSU is faulty

# If no spare PSU:
# Try USB power from laptop (if provides ≥1A)
# If laptop USB works: PSU issue confirmed
# Solution: Replace PSU with industrial-grade unit
```

---

## Emergency Recovery Procedures

### If Cloud Sync Failed for >7 Days

Local queue will exceed 7-day limit and start dropping old readings:

```bash
# Check queue status
sqlite3 /var/cache/meterhub/telemetry.db \
  "SELECT MIN(timestamp_utc), COUNT(*) FROM meter_readings;"

# Check last sync time
sqlite3 /var/lib/meterhub/state.db \
  "SELECT last_sync_timestamp FROM sync_state;"

# Manually trigger upload
systemctl restart meterhub-uploader

# Monitor upload
journalctl -u meterhub-uploader -f

# Check completion
sqlite3 /var/lib/meterhub/state.db \
  "SELECT last_sync_timestamp FROM sync_state;"
```

### If SD Card Becomes Corrupted

```bash
# Boot from USB drive (if possible)
# Or use laptop to:

1. Copy database files for backup
   # Mount SD card on laptop
   # Copy /var/cache/meterhub/telemetry.db
   # Copy /var/lib/meterhub/state.db

2. Attempt filesystem repair
   sudo fsck -y /dev/mmcblk0p2

3. If repair fails:
   Re-flash SD card with fresh image
   Restore databases from backup (if available)
   Or restart fresh (lose last hours of readings)
```

### If Meter is Unresponsive for >1 Hour

```bash
# Hard reset Pi
sudo systemctl isolate rescue.target
# System enters minimal mode

# Check for errors
journalctl -xe

# Return to normal
sudo systemctl isolate multi-user.target

# If still stuck:
# Power off Pi completely (wait 10 seconds)
# Power back on (system should recover)
```

---

## Contacting Support

**When contacting support, provide:**

1. Output of diagnostic script
   ```bash
   /opt/meterhub/diagnose.sh > /tmp/diag.txt
   # Email this file
   ```

2. Last 100 lines of logs
   ```bash
   journalctl -xe -n 100 > /tmp/logs.txt
   ```

3. Device configuration (sanitized)
   ```bash
   cat /etc/meterhub/device_config.json  # Remove secrets
   ```

4. Details of when problem started
   - After power cut?
   - After WiFi change?
   - After firmware update?
   - Random?

**Support Response Times:**
- Critical (no readings >4 hours): 1 hour
- High (intermittent failures): 4 hours
- Medium (slow performance): 1 day
- Low (documentation questions): 2-3 days
