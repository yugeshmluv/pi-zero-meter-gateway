# MeterHub Documentation Structure

## New Directory Organization

```
docs/
├── specifications/      # Technical & API specs (locked documents)
│   ├── PRODUCTION_SPEC.md    → Hardware, software, connectivity details
│   ├── CLOUD_API_CONTRACT.md → API for cloud team (FROZEN)
│   └── README.md            → Index for this folder
│
├── hardware/           # Hardware documentation
│   ├── BOM.md               → Bill of materials (parts, suppliers, pricing)
│   └── README.md            → Index for this folder
│
├── guides/             # How-to guides & tutorials
│   ├── CONTRIBUTING.md      → Development guidelines, code style
│   ├── METER_PROFILES.md    → How to create new meter profiles
│   ├── INSTALLATION.md      → Installation & repo structure
│   └── README.md            → Index for this folder
│
├── project/            # Project management & status
│   ├── PHASE_1_SUMMARY.md         → Phase 1 delivery report
│   ├── PHASE_1_COMPLETE.md        → Phase 1 completion details
│   ├── PHASE_1_VERIFICATION.md    → QA checklist
│   ├── PROJECT_REVIEW_COMPLETE.md → Comprehensive review audit
│   ├── AUDIT_REPORT.md            → Quality audit findings
│   └── README.md                  → Index for this folder
│
├── ARCHITECTURE.md     → Core system design (6-layer model)
└── QUICK_REFERENCE.md  → Navigation index (in root)

README.md (root)        → Entry point, quick start, links to docs/
```

## File Movement Summary

**Moved to docs/specifications/**
- PRODUCTION_SPEC.md
- CLOUD_API_CONTRACT.md

**Moved to docs/hardware/**
- HARDWARE_BOM.md (now BOM.md)

**Moved to docs/guides/**
- CONTRIBUTING.md
- METER_PROFILES.md
- INSTALLATION.md

**Moved to docs/project/**
- PHASE_1_SUMMARY.md
- PHASE_1_COMPLETE.md
- PHASE_1_VERIFICATION.md
- PROJECT_REVIEW_COMPLETE.md
- AUDIT_REPORT.md

**Stays in root/**
- README.md (main entry point)
- QUICK_REFERENCE.md (can stay as index)
- LICENSE (legal, not doc)

**Stays in docs/**
- ARCHITECTURE.md (fundamental design)

---

## Updated README.md Structure

The root README.md will be streamlined to:
1. Project overview (1-2 paragraphs)
2. Quick start (3-4 steps)
3. Documentation index (links to docs/ folders)
4. Hardware requirements (summary table)
5. Architecture diagram (Mermaid)
6. Build order & phases
7. Key features

All detailed docs link to their respective folders in docs/

---

## Benefits of This Structure

✅ Clean root directory (only README.md, config, source code)  
✅ Logical grouping (specifications, hardware, guides, project status)  
✅ Easy navigation (each folder has README.md index)  
✅ Scalable (can add more folders as project grows)  
✅ Clear separation of concerns  
✅ Professional appearance (docs/ is standard Python project convention)

---

**Last Updated:** April 30, 2026  
**Move Status:** In Progress
