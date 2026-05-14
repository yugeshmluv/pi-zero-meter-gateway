# MeterHub README for Installation

MeterHub firmware repository structure:

```
meterhub/
├── acquisition/              # Modbus polling service
│   ├── meterhub_acq/        # Python package
│   ├── tests/               # Service tests
│   └── requirements.txt
├── uploader/                # Cloud uploader service
│   ├── meterhub_uploader/   # Python package
│   ├── tests/               # Service tests
│   └── requirements.txt
├── installer_ui/            # Web UI for commissioning
│   ├── meterhub_ui/         # Python package
│   ├── templates/           # Jinja2 templates
│   ├── static/              # CSS, minimal JS
│   └── requirements.txt
├── common/                  # Shared utilities
│   ├── meterhub_common/     # Python package
│   ├── modbus_profiles/     # Meter definitions
│   └── requirements.txt
├── profiles/                # Meter YAML profiles
│   └── schneider-em6400.yaml
├── ota/                     # Over-the-air updates
├── pi-gen-overlay/          # Raspberry Pi image build
├── scripts/                 # Tooling
│   └── install-dev.sh       # Development setup
├── tests/                   # System-level tests
├── docs/                    # Documentation
├── .env.example             # Environment template
├── pyproject.toml          # Project configuration
├── .gitignore              # Git exclusions
├── CONTRIBUTING.md         # Development guide (see docs/guides/)
├── README.md               # Project overview
├── HARDWARE_BOM.md         # Parts list (see docs/hardware/)
├── CLOUD_API_CONTRACT.md   # Cloud specification (see docs/specifications/)
└── LICENSE                 # Proprietary license
```

See README.md for full documentation.
