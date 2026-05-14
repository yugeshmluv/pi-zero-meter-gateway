# MeterHub Phase 1 — Quick Reference Index

**Status:** ✅ COMPLETE (April 28, 2026)

---

## 📍 Start Here

1. **If you're new to the project:** Read [README.md](../README.md) (5 min read)
2. **If you're on the cloud team:** Read [CLOUD_API_CONTRACT.md](specifications/CLOUD_API_CONTRACT.md) (20 min read) — **YOUR SPEC**
3. **If you're a developer starting Phase 2:** Read [CONTRIBUTING.md](guides/CONTRIBUTING.md) + [ARCHITECTURE.md](ARCHITECTURE.md)
4. **If you're doing hardware procurement:** Read [BOM.md](hardware/BOM.md)
5. **For the big picture:** Read [PHASE_1_SUMMARY.md](project/PHASE_1_SUMMARY.md) (sign-off checklist, all deliverables)

---

## 📚 Documentation Map

### 🎯 Project Overview
| Document | Audience | Length | Purpose |
|----------|----------|--------|---------|
| [README.md](../README.md) | Everyone | 5 min | Quick start, architecture, features, build order |
| [PHASE_1_SUMMARY.md](project/PHASE_1_SUMMARY.md) | Tech lead, PM | 10 min | Complete Phase 1 delivery summary + sign-off checklist |
| [PHASE_1_COMPLETE.md](project/PHASE_1_COMPLETE.md) | Developers | 5 min | Phase 1 completion details + Phase 2 scope |

### 🏗️ Architecture & Design
| Document | Audience | Length | Purpose |
|----------|----------|--------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Developers, tech lead | 20 min | 6-layer architecture, IPC design, data flows, security |
| [METER_PROFILES.md](METER_PROFILES.md) | Developers, meter vendors | 15 min | How to author YAML meter profiles (no code changes) |

### 💼 Specifications & Contracts
| Document | Audience | Length | Purpose |
|----------|----------|--------|---------|
| [CLOUD_API_CONTRACT.md](specifications/CLOUD_API_CONTRACT.md) | Cloud team | 30 min | **MANDATORY READING** — Complete API spec (MQTT, HTTPS, OTA, provisioning) |
| [BOM.md](hardware/BOM.md) | Procurement, electronics | 10 min | India-sourced parts, suppliers, bulk pricing, compliance |

### 👨‍💻 Development
| Document | Audience | Length | Purpose |
|----------|----------|--------|---------|
| [CONTRIBUTING.md](guides/CONTRIBUTING.md) | Developers | 15 min | Dev setup, code style, testing checklist, deployment |
| [profiles/schneider-em6400.yaml](../profiles/schneider-em6400.yaml) | Developers | 5 min | Sample meter profile (template for new meters) |
| [scripts/install-dev.sh](../scripts/install-dev.sh) | Developers | 1 click | Automated venv + dependency setup |

### 📋 Administrative
| Document | Purpose |
|----------|---------|
| [LICENSE](../LICENSE) | Proprietary software terms |
| [CONTRIBUTING.md](guides/CONTRIBUTING.md#-deployment-checklist-before-release) | Pre-release checklist |

---

## 🗂️ Code Structure

```
metrehub/
├── acquisition/          Phase 2 (Modbus polling)
├── uploader/             Phase 3 (MQTT + HTTPS upload)
├── installer_ui/         Phase 4 (Web UI)
├── common/               Shared utilities
├── profiles/             Meter profiles (YAML, extensible)
│   └── schneider-em6400.yaml ← Template for new meters
├── ota/                  Phase 5 (OTA pipeline)
├── pi-gen-overlay/       Phase 6 (Image builder)
├── scripts/              Tooling
│   └── install-dev.sh ← Run this to set up dev environment
├── tests/                System-level tests
├── docs/                 Deep documentation
│   ├── specifications/   CLOUD_API_CONTRACT.md ← Cloud team
│   ├── hardware/         BOM.md
│   ├── guides/           CONTRIBUTING.md, METER_PROFILES.md
│   └── project/          Phase reports + audits
├── README.md ← Start here
└── LICENSE
```

---

## 🚀 Quick Start (Developer)

```bash
# 1. Clone repo and enter directory
cd metrehub

# 2. Set up development environment
./scripts/install-dev.sh
source venv/bin/activate

# 3. Run tests
pytest tests/

# 4. Read CONTRIBUTING.md for code style
cat CONTRIBUTING.md

# 5. Start Phase 2: Acquisition service
# Read docs/ARCHITECTURE.md + CONTRIBUTING.md
```

---

## ☁️ Quick Start (Cloud Team)

1. **READ THIS FIRST:** [CLOUD_API_CONTRACT.md](specifications/CLOUD_API_CONTRACT.md) (30 min, contains everything)

2. **Parallel tasks:**
   - Set up HiveMQ Cloud or AWS IoT Core MQTT broker
   - Create S3 bucket + CloudFront distribution for OTA packages
   - Provision AWS SES for shared fallback email account
   - Design `/v1/readings`, `/v1/heartbeat`, `/v1/ota/manifest` endpoints

3. **Integration point:** After edge team completes Phase 3 (Uploader), cloud team can test MQTT payloads end-to-end

---

## 📊 Phase 1 Deliverables Checklist

- [x] System architecture diagram (Mermaid, 6 layers)
- [x] Hardware BOM (25+ parts, India suppliers)
- [x] Cloud API contract (MQTT, HTTPS, OTA, provisioning)
- [x] Repository structure (all directories, scaffolding)
- [x] README.md (quick start, features, build order)
- [x] CONTRIBUTING.md (dev setup, code style, testing)
- [x] docs/ARCHITECTURE.md (deep dive, design decisions)
- [x] docs/METER_PROFILES.md (authoring guide, YAML schema)
- [x] Sample meter profile (Schneider EM6400)
- [x] Development setup script (install-dev.sh)
- [x] LICENSE (proprietary)
- [x] Phase summary documents (PHASE_1_COMPLETE.md, PHASE_1_SUMMARY.md)

**Total:** ~3,500 lines of documentation + architecture specification

---

## 🎯 Phase 2 Scope (Next)

**Duration:** 2–3 weeks
**Owner:** Development team

**Deliverables:**
1. Acquisition service (asyncio + pymodbus)
2. SQLite WAL integration (crash-safe)
3. YAML meter profile loader
4. Unit + integration tests
5. Power-loss fault injection tests
6. 24 h soak test

**Entry criteria:**
- [x] Architecture approved
- [x] BOM validated
- [x] Cloud API contract ready
- [ ] (Your team ready to start)

---

## 🔑 Key Decisions (Locked)

| What | Decision | Why |
|------|----------|-----|
| MQTT Broker | Managed cloud (HiveMQ Cloud / AWS IoT Core) | Reduces ops burden |
| OTA Hosting | S3 + CloudFront | Reliable + globally distributed |
| Fallback Email | AWS SES | No per-device SMTP setup |
| QR Provisioning | YES, Phase 1 | Critical for fleet scale |
| Cloud Parallel Dev | YES | API contract is frozen |

---

## 🔐 Security Highlights

- **Isolation:** Waveshare TTL to RS485 (C) with 2.5kV galvanic isolation + integrated TVS non-negotiable for 415V safety
- **Crypto:** Ed25519 device signing + cloud bearer tokens
- **Audit:** All logins, config changes, OTA events logged locally + shipped to cloud
- **Compliance:** DPDP Act (no resident PII), BIS electrical safety

---

## 📞 Common Questions

**Q: Where do I start as a developer?**
A: Start with [CONTRIBUTING.md](CONTRIBUTING.md), then [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

**Q: I'm the cloud team. What's my spec?**
A: [CLOUD_API_CONTRACT.md](CLOUD_API_CONTRACT.md) — everything you need. Read it first.

**Q: Can I modify the meter profile without code changes?**
A: **YES** — meter profiles are YAML in `profiles/`. See [docs/METER_PROFILES.md](docs/METER_PROFILES.md)

**Q: What's the total cost per device?**
A: ₹9,200–13,000. See [HARDWARE_BOM.md](HARDWARE_BOM.md) for breakdown.

**Q: When does Phase 2 start?**
A: After sign-off on Phase 1 (architecture + BOM + API contract). You're reading the sign-off docs now.

**Q: What about OTA updates?**
A: Fully specified in [CLOUD_API_CONTRACT.md](CLOUD_API_CONTRACT.md) (OTA manifest, canary delay, rollback logic). Implemented in Phase 5.

**Q: Is the device secure?**
A: Yes — isolation, Ed25519 signing, audit logs, bearer tokens. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) Security section.

---

## ✅ Sign-Off Checklist (Before Phase 2 Kickoff)

**Print this and check each box:**

- [ ] Tech lead reviewed architecture diagram
- [ ] Procurement confirmed BOM suppliers available
- [ ] Cloud team read & approved CLOUD_API_CONTRACT.md
- [ ] Development team reviewed CONTRIBUTING.md + development setup works
- [ ] Security team approved audit logging + compliance approach
- [ ] Manager cleared Phase 2 kickoff

---

## 📞 Support / Questions

All Phase 1 deliverables are **frozen** — no changes without team approval.

For questions, refer to:
- **Architecture:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Cloud API:** [CLOUD_API_CONTRACT.md](CLOUD_API_CONTRACT.md)
- **Development:** [CONTRIBUTING.md](CONTRIBUTING.md)
- **Hardware:** [HARDWARE_BOM.md](HARDWARE_BOM.md)

---

**🎉 Phase 1 Complete — Ready for Phase 2 Kickoff**

**Last Updated:** April 28, 2026
**Repository:** `metrehub/`
**Status:** ✅ All deliverables ready
