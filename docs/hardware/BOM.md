# MeterHub Hardware BOM — India Sourced (Production-Hardened)

**Document Version:** 2.0 (Production Review Locked)  
**Target Board:** Raspberry Pi Zero 2 W (quad-core ARMv8 aarch64, 512 MB RAM)  
**Typical Cost Estimate (Tier 1 Standard):** ₹10,500–12,500 per unit (excl. enclosure shipping)  
**Image Build:** Mender A/B partitions + pi-gen overlay (adds ~3 weeks integration, ~100 MB rootfs overhead)

---

## 1. Core Compute & Storage

| Item | Part Number / Model | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|-------------------|-----|---------------|----------|-------------|
| Raspberry Pi Zero 2 W | RPi Zero 2 W v1.0+ | 1 | 2,900–3,500 | Robu.in, Element14 India | **Mandatory upgrade from original Zero W.** Quad-core ARMv8 aarch64 (5× CPU), BLE built-in, no thermal cliff at 70°C. Wheel support (pymodbus, cryptography, paho-mqtt) first-class; ARMv6 EOL in Python ecosystem. Pin-compatible; same form factor + power envelope. |
| MicroSD Card (Industrial, Power-Loss Protected) | SanDisk Industrial XI 32 GB (PLP SKU) OR Swissbit S-56u | 1 | 3,200–4,000 | Electronicscomp, Robu.in (pre-order 4–6 weeks for bulk) | **CRITICAL:** Must be PLP (Power-Loss-Protected) variant. Standard industrial cards fail under 100 power-cuts/day. Verify SKU includes PLP; SanDisk Industrial XI-Gen (not base) or Swissbit S-56u both certified. ATP industrial does NOT guarantee PLP on all SKUs — verify datasheet. |
| USB Cable (Data) | Micro USB to USB-A | 1 | 150–300 | Any electronics store | For provisioning and USB serial console |
| Power Adapter | 5V/2A Micro USB (industrial PSU) | 1 | 600–1,200 | Robu.in, Electronicscomp | Mean Well or equivalent 5W PSU; not cheap phone charger |

---

## 2. RS485 Isolation & Protection (Safety-Critical)

| Item | Part Number / Model | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|-------------------|-----|---------------|----------|-------------|
| Galvanic Isolated TTL to RS485 Converter | Waveshare TTL to RS485 (C) Isolated Converter | 1 | 500–900 | Robu.in, AliExpress, REES52 (2–3 wk lead) | Galvanic isolated, 2.5kV isolation, built-in 120Ω termination resistor, **integrated TVS + surge suppression (200W lightning, 6KV ESD).** Compact form factor (42.8×15.2×4.75 mm). UART-to-RS485 conversion ready. Eliminates need for external TVS diodes. **Preferred over older WeAct module.** |
| Real-Time Clock (RTC) | DS3231 I2C Module, battery-backed | 1 | 150–200 | Electronicscomp, Robu.in, AliExpress | **Mandatory.** Eliminates clock drift during 24+ hour cloud outage. ±2 ppm accuracy; 2-wire I2C; CR2032 battery included. Non-negotiable for billing-grade timestamps. |
| M3 Mounting Bolts & DIN Rail Clips | M3 × 12 mm stainless | 4–6 | 15–30 | Robu.in, local hardware | For enclosure mounting on DIN rail + RTC breakout |

---

## 3. Wi-Fi Connectivity — Multi-Tier Approach

| Item | Description | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|------------|-----|---------------|----------|-------------|
| Wi-Fi Antenna (External, Tier 1 Standard) | U.FL to RP-SMA pigtail + 2 dBi dipole antenna | 1 | 120–180 | AliExpress, Robu.in | **Tier 1 (Standard Kit, all units).** Pi Zero 2 W has U.FL pad. Minor soldering or factory-modified units available. Eliminates 60% of "Wi-Fi too weak" tickets in panel rooms. Include U.FL-to-Pi connection hardware. |
| USB Ethernet Adapter (Tier 2 Optional) | Realtek RTL8152 chipset, 100 Mbps | 1 | 400–600 | Electronicscomp, Amazon India | **For sites with poor Wi-Fi.** Use with powerline adapter (TP-Link AV600 pair, ~₹2,000). |
| USB 4G Dongle (Tier 3 Optional) | Qubo or D-Link model | 1 | 500–800 | Amazon India, Flipkart | **For extremely poor Wi-Fi.** Requires IoT SIM (Airtel IoT or Jio Things, ₹50–100/month per device). Changes unit economics; know upfront. |
| Optional: OLED Status Display | SSD1306 128×32 I2C module | 1 | 120–180 | Robu.in, AliExpress | Shows device IP, status, current readings. Recommended for installer usability. |

---

## 4. Enclosure & Thermal

| Item | Description | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|------------|-----|---------------|----------|-------------|
| IP54 DIN-Rail Enclosure | Plastic or polycarbonate, 200×150×100 mm, IP54 min | 1 | 2,000–3,500 | Electronicscomp, Robu.in, Schneider Electric catalog | With 35 mm DIN rail. Passive ventilation slots on top/sides |
| Aluminum Heatsink (SoC) | 25×25×15 mm with adhesive or clip mount | 1 | 300–600 | Robu.in, AliExpress | For Pi SoC. Reduces thermal throttling. |
| Thermal Pad | 1 mm × 25×25 mm, silicone, ~3 W/mK | 1 | 100–200 | Robu.in | Between SoC and heatsink. Adhesive backing. |
| Ventilation Filter (optional) | Washable polyurethane foam pad | 1 | 200–400 | Robu.in | If deploying in dusty panel rooms; reduces enclosure lifespan at cost of airflow |
| Cable Glands | M20 × 1.5 (A/B lines + power) | 2 | 150–300 | Electronicscomp, Robu.in | For clean cable entry through enclosure bottom |
| Terminal Block (RS485 + GND) | 3.81 mm pitch, 4-pin (A, B, GND, Shield) | 1 | 100–200 | Robu.in | For meter wire termination |

---

## 5. Connectors & Wiring

| Item | Description | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|------------|-----|---------------|----------|-------------|
| RS485 Cable (Twisted Pair + Shield) | 2-pair (A, B) + shield, 0.5 mm², 50 m roll | 1 | 800–1,500 | Robu.in, Electronicscomp, local cable distributor | Use **only** twisted-pair RS485 cable (not generic 2-wire). Shield terminated at device end only. |
| Power Cable | 2-wire, 1.5 mm², 0.5 A rated, black/brown | 5 m | 200–400 | Any local hardware | For internal PSU-to-Pi wiring |
| USB Type-B (optional, for external antenna) | USB Type-B connector breakout | 1 | 150–300 | Robu.in | If adding external USB Ethernet or 4G modem for poor Wi-Fi sites |

---

## 6. Optional: Status & Factory Reset (GPIO)

| Item | Description | Qty | Unit Cost (₹) | Supplier | Link / Notes |
|------|------------|-----|---------------|----------|-------------|
| Status LED (Green) | 5 mm, 20 mA, through-hole | 1 | 10–20 | Any electronics store | PWM-driven via GPIO 17 (on SoC) |
| Reset Button | 6×6 mm momentary, 50 mA rated | 1 | 20–50 | Any electronics store | Wired to GPIO 27. Press >3 sec for factory reset. |
| Current-Limiting Resistor | 1/4 W, 330 Ω (LED) + 10 kΩ (button pull-up) | 2 | 5–10 | Any electronics store | Limit LED current; pull-up for button. |

---

## 7. Recommended Test Equipment (Commissioning)

| Item | Purpose | Est. Cost (₹) |
|------|---------|--------------|
| USB-to-Serial adapter (TTL/RS485 converter) | Debug console, Modbus protocol analysis | 500–2,000 |
| Multimeter (digital, 3.5 digit) | Continuity, voltage checking | 1,000–3,000 |
| Modbus RTU protocol sniffer (software) | Verify meter comms during install | Free (Modbus Poll demo) |
| Wi-Fi signal meter (mobile app or handheld) | Site survey before deployment | Free–5,000 |
| Smart plug with scheduling | Power-loss test automation (1,000 cycles) | 1,500–3,000 |

---

## 8. Shipping & Logistics Notes (Updated for Pi Zero 2 W & Multi-Tier)

**Lead Times (India)**
- Raspberry Pi Zero 2 W: 14–21 days from Robu.in (pre-order if large batch)  
- Waveshare TTL to RS485 (C) Converter: 7–10 days Robu.in, 14–21 days AliExpress (check local stock first)  
- Industrial SD cards (power-loss protected): **4–6 weeks** from distributors for bulk; plan ahead  
- RTC (DS3231): 7–10 days Robu.in; stocked at most electronics suppliers  
- Wi-Fi antenna (U.FL pigtail): 7–10 days AliExpress  
- Enclosures: 10–14 days from local DIN-rail suppliers

**Cost Summary (Single Unit, Tier 1 Standard Kit)**
- Core compute & storage: ₹6,200–7,200 (Pi Zero 2 W + industrial SD PLP)  
- RTC (DS3231): ₹150–200  
- Wi-Fi antenna (U.FL pigtail + 2 dBi): ₹120–180  
- RS485 isolation & protection: ₹500–900 (Waveshare TTL to RS485 C, integrated TVS)  
- Enclosure & thermal: ₹2,500–4,500  
- Optional OLED status display: ₹120–180  
- **Total material (Tier 1 Standard): ₹10,500–12,500 per unit**  
- **Tier 2 (add USB Ethernet + powerline): +₹2,400–3,000 per device**  
- **Tier 3 (add 4G dongle + IoT SIM): +₹500–800 hardware + ₹50–100/mo per device**  
- Add 20% for contingency, test fixtures, spares for production run of 50+ units.

**Bulk Procurement (100+ units for production)**
- **Critical path:** Pre-order power-loss-protected SD cards 6–8 weeks in advance (SanDisk XI or Swissbit); verify PLP SKU explicitly.  
- Negotiate 10–15% discount on Pi Zero 2 W with Robu.in, Element14 India.  
- Request bulk allocation from official Raspberry Pi distributors (allow 2–3 weeks for approval).  
- Order antenna components in bulk from AliExpress (250+ units = 20–25% discount).  
- Stagger tier 2/3 orders based on site survey results (don't overbuy 4G/Ethernet kits if most sites have adequate Wi-Fi).

---

## 9. Compliance & Certifications (Updated)

- **Electrical Safety:** BIS IS 1293 (power supply), IEC 61010-1 (measurement safety).  
- **Electromagnetic Compatibility (EMC):** Device operates adjacent to 415 V three-phase switchgear. RS485: double-insulated cable + shielded runs (shield grounded at device end only). TVS diodes on A/B lines provide surge suppression for 415V transients. **Do not rely on isolated module alone; TVS is mandatory.**  
- **CEA (Central Electricity Authority):** Devices tapped into society metering system technically fall under CEA rules. **Get legal opinion before deployment.** CT clamps must be downstream of utility meter, never integrated with utility meter itself.  
- **Environmental:** IP54 enclosure meets ingress protection for typical electrical panel rooms (35–50 °C, dust/moisture).  
- **Data Protection:** DPDP Act — device stores meter readings + admin email (contact during provisioning). Consent notice required during install. Data retention period: specify (recommended 3–7 years for tax records). Data subject rights: export/deletion via cloud portal.

---

## 10. Supplier Quick Reference (Updated)

| Supplier | Website | Minimum Order | Notes |
|----------|---------|----------------|-------|
| Robu.in | https://robu.in | None (retail) | Best for one-off, Arduino/Pi ecosystem, fast shipping NCR |
| Electronicscomp | https://www.electronicscomp.com | None (retail) | Nationwide, industrial components, DIN-rail stock |
| Element14 India | https://in.element14.com | None (retail) | Authorized distributor, premium pricing |
| Local DIN-Rail Distributor | Regional | 10+ units | Enclosures, terminal blocks, cable glands |
| AliExpress (China) | https://www.aliexpress.com | Variable (2–4 week lead) | Ultra-low-cost modules; use only for non-critical prototyping |
| Swissbit (Industrial SD) | Via Robu.in or Electronicscomp | 5+ cards | Premium alternative to SanDisk Industrial |

---

## 11. End-of-Life & Recycling

- Pi Zero 2 W: Electronic waste (e-waste) recycling per BIS standards. Data on internal flash wiped before disposal.  
- Industrial SD card: Can be securely wiped (meterhub-erase.sh tool provided) and reused in Tier 2/3 refresh or recycled. **For RMA units, extract SD for data recovery before recycling module.**  
- Enclosure: Recyclable plastic/aluminum.  
- RTC: Battery extraction required before e-waste disposal; CR2032 cells recyclable separately.
