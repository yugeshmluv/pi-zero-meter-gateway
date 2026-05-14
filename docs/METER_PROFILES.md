# Meter Profile Authoring Guide

## Overview

Meter profiles define how MetreHub reads a specific 3-phase Modbus meter model. Profiles are YAML files in `/etc/meterhub/profiles/` and **require no code changes**—new meters are supported by adding profiles.

## Profile Schema

```yaml
###############################################################################
# Meter Profile: Schneider Electric EM6400
# Description: 3-phase power meter with Modbus RTU interface
# Version: 1.0
###############################################################################

meter_name: "Schneider Electric EM6400"
manufacturer: "Schneider Electric"
model_number: "EM6400"
modbus_address: 1  # Slave address (1-247)
protocol: "RTU"
protocol_version: "Modbus RTU/TCP v1.1b3"

# Meter model classification for cloud analytics
class: "industrial_3phase_ct"
regions_supported:
  - india
  - asia-se

# Total number of registers to read in one shot (optimization)
register_count_estimate: 30

# Communication parameters
communication:
  baud_rate: 9600  # Typical RS485 speeds: 9600, 19200, 38400
  data_bits: 8
  stop_bits: 1
  parity: "none"
  timeout_ms: 2000  # Modbus timeout
  response_timeout_ms: 2000

# Register definitions (ALL registers must include address + type + scale)
# NOTE: Always include 'totalizer_kwh' in every read
registers:

  # =========== ENERGY (MANDATORY) ===========
  totalizer_kwh:
    address: 45568
    count: 2
    type: "uint32_big_endian"
    scale: 0.01
    unit: "kWh"
    description: "Cumulative kilowatt-hours (export energy)"
    frequency_hz: 0.1  # Polled every 10 seconds typically

  totalizer_kvarh:
    address: 45570
    count: 2
    type: "uint32_big_endian"
    scale: 0.01
    unit: "kVARh"
    description: "Cumulative reactive energy"

  # =========== INSTANTANEOUS POWER ===========
  instant_kw:
    address: 3520
    count: 2
    type: "int32_big_endian"
    scale: 0.001
    unit: "kW"
    description: "Real power (3-phase total)"

  instant_kvar:
    address: 3522
    count: 2
    type: "int32_big_endian"
    scale: 0.001
    unit: "kVAR"
    description: "Reactive power (3-phase total)"

  instant_kva:
    address: 3524
    count: 2
    type: "uint32_big_endian"
    scale: 0.001
    unit: "kVA"
    description: "Apparent power (3-phase total)"

  # =========== VOLTAGE ===========
  voltage_l1_v:
    address: 3072
    count: 1
    type: "uint16"
    scale: 0.1
    unit: "V"
    description: "L1 RMS voltage"

  voltage_l2_v:
    address: 3073
    count: 1
    type: "uint16"
    scale: 0.1
    unit: "V"
    description: "L2 RMS voltage"

  voltage_l3_v:
    address: 3074
    count: 1
    type: "uint16"
    scale: 0.1
    unit: "V"
    description: "L3 RMS voltage"

  # =========== CURRENT ===========
  current_l1_a:
    address: 3076
    count: 1
    type: "uint16"
    scale: 0.01
    unit: "A"
    description: "L1 RMS current"

  current_l2_a:
    address: 3077
    count: 1
    type: "uint16"
    scale: 0.01
    unit: "A"
    description: "L2 RMS current"

  current_l3_a:
    address: 3078
    count: 1
    type: "uint16"
    scale: 0.01
    unit: "A"
    description: "L3 RMS current"

  # =========== FREQUENCY ===========
  frequency_hz:
    address: 3084
    count: 1
    type: "uint16"
    scale: 0.01
    unit: "Hz"
    description: "Supply frequency"

  # =========== POWER FACTOR (per phase + total) ===========
  pf_l1:
    address: 3080
    count: 1
    type: "int16"
    scale: 0.001
    unit: "PF"
    description: "Power factor L1 (signed: -1.0 to +1.0)"

  pf_l2:
    address: 3081
    count: 1
    type: "int16"
    scale: 0.001
    unit: "PF"
    description: "Power factor L2"

  pf_l3:
    address: 3082
    count: 1
    type: "int16"
    scale: 0.001
    unit: "PF"
    description: "Power factor L3"

  pf_total:
    address: 3083
    count: 1
    type: "int16"
    scale: 0.001
    unit: "PF"
    description: "Power factor (3-phase total)"

# Register reading optimization: group by address ranges to minimize MQTT calls
# (Device will read multiple addresses in one Modbus batch request)
read_groups:
  - name: "energy_batch"
    registers:
      - "totalizer_kwh"
      - "totalizer_kvarh"
    reason: "Contiguous addresses for efficiency"

  - name: "power_batch"
    registers:
      - "instant_kw"
      - "instant_kvar"
      - "instant_kva"

  - name: "voltage_current_batch"
    registers:
      - "voltage_l1_v"
      - "voltage_l2_v"
      - "voltage_l3_v"
      - "current_l1_a"
      - "current_l2_a"
      - "current_l3_a"
      - "pf_l1"
      - "pf_l2"
      - "pf_l3"
      - "pf_total"
      - "frequency_hz"

# Validation bounds (used to detect meter offline / malfunction)
validation:
  voltage_reasonable_range_v: [180, 280]  # Outside range = error
  current_max_reasonable_a: 100
  frequency_reasonable_range_hz: [48.5, 50.5]
  pf_valid_range: [-1.0, 1.0]  # PF always between -1 and +1

  # Special case: zero values are valid (no consumption)
  allow_zero_power: true
  allow_zero_current: true
  allow_zero_kvarh: true

# Error handling strategies
error_handling:
  # If Modbus CRC error or timeout occurs
  retry_strategy:
    max_retries: 3
    backoff_ms: [100, 500, 2000]  # 100ms, 500ms, 2000ms

  # If register read returns unreasonable value (out of validation bounds)
  bad_register_value_action: "skip_register"  # or "mark_meter_offline"

  # If >5 consecutive failures, mark meter offline in heartbeat
  offline_threshold_failures: 5

# Meter-specific quirks (for device firmware to handle)
quirks:
  # Some meters have register address gaps; reading contiguously may fail
  - name: "register_gap_at_3085"
    description: "Meter has unmapped registers 3085–3099; read as separate batch"

  # Some meters return wrong endianness for certain registers
  - name: "voltage_little_endian"
    description: "Voltage registers are little-endian (non-standard); adjust decoder"
    registers: ["voltage_l1_v", "voltage_l2_v", "voltage_l3_v"]

  # Some meters require write before read (initialization sequence)
  - name: "requires_modbus_preset"
    description: "Must write 0x0001 to register 100 before reading"
    preset_writes:
      - address: 100
        value: 0x0001

# Commissioning guidance for installation engineers
commissioning:
  checklist:
    - "Verify meter Modbus address matches profile (currently: {{ modbus_address }})"
    - "Connect RS485 A/B lines from Pi to meter"
    - "Ensure 120Ω termination resistor (if last device on bus)"
    - "Use installer UI → Meter Test to confirm communication"
    - "Verify all registers return reasonable values"
    - "Check kWh totalizer increments every minute"

  expected_first_read: "Takes <5 seconds via installer UI test page"
  troubleshooting_links:
    - "See HARDWARE_BOM.md for RS485 isolation confirm"
    - "Meter offline? Check: https://metrehub.local/troubleshoot"
    - "Register values weird? Profile may need adjustment"

# Known issues & workarounds
known_issues:
  - name: "Meter goes offline after 24h of continuous polling"
    workaround: "Oldest EM6400 firmware; upgrade to 2.x.x or add 30-second idle between polls"
    affected_firmware_versions: ["1.0.x"]

  - name: "KVARH register contains stale value (not updating)"
    workaround: "Quirk of this meter; cloud ignores KVARH, uses only KWH"

# Metadata for cloud analytics
metadata:
  rating_kva: 100
  max_current_a: 250
  phases: 3
  ctgear_turns_ratio: 5  # 5A output from 1000A primary (example)
  rs485_bus_termination_required: true
  typical_deployment_density: "1 per electrical panel"
  expected_lifespan_years: 10

# Document source & verification
source:
  document_title: "Schneider Electric EM6400 Modbus Communication Manual"
  document_version: "v3.0"
  document_date: "2024-01-15"
  verified_by: "MetreHub team, tested on real hardware 2026-04-01"
  testing_date: "2026-04-01"
  tester_notes: "Profile verified on actual EM6400 in production panel. All registers confirmed."
```

---

## Data Types Reference

| Type | Size | Byte Order | Python Example |
|------|------|------------|-----------------|
| `uint16` | 1 register (2 bytes) | N/A | `struct.unpack('>H', bytes)` |
| `int16` | 1 register | N/A | `struct.unpack('>h', bytes)` |
| `uint32_big_endian` | 2 registers | Big (ABCD) | Most common |
| `uint32_little_endian` | 2 registers | Little (DCBA) | Some Schneider meters |
| `int32_big_endian` | 2 registers | Big (ABCD) | Signed values |
| `float32_big_endian` | 2 registers | Big (ABCD) | IEEE 754 32-bit |
| `float32_little_endian` | 2 registers | Little (DCBA) | Uncommon |

---

## Common Meter Register Addresses (Quick Reference)

| Meter Model | Energy Reg | Power Reg | Voltage Reg | Notes |
|---|---|---|---|---|
| Schneider EM6400 | 45568 | 3520 | 3072 | STD 3-phase |
| L&T 4400/5060 | 32000 | 32012 | 32006 | Address gap at 32010 |
| Selec MFM383C | 0 | 100 | 50 | Check BAS file for details |
| Generic | Varies | Varies | Varies | Consult meter manual |

---

## Authoring Checklist

Before submitting a new profile:

- [ ] All `totalizer_kwh` and `instant_kw` (mandatory) defined
- [ ] All registers have `address`, `type`, `scale`, `unit`
- [ ] `validation` bounds are realistic for meter
- [ ] `read_groups` minimize Modbus batches
- [ ] `error_handling` includes `offline_threshold_failures`
- [ ] `commissioning` checklist is specific to meter
- [ ] `known_issues` documented if any
- [ ] Profile tested on real hardware (if possible)
- [ ] Meter manual referenced in `source`

---

## Example: Add L&T 4400 Profile

1. Copy `schneider-em6400.yaml` → `lt-4400.yaml`
2. Update:
   - `meter_name: "L&T 4400 Power Analyzer"`
   - `modbus_address: 1` (adjust if needed)
   - Register addresses (consult L&T manual)
   - `quirks` if any (L&T has register gap at 32010)
3. Test on real meter using installer UI → Meter Test
4. Commit to `profiles/` directory

Device automatically discovers `/etc/meterhub/profiles/*.yaml` and makes them available in setup wizard.
