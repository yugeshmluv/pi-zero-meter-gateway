"""
MeterHub Installer UI - FastAPI Application (Phase 4)

Engineering commissioning interface: device provisioning, network setup, service monitoring.

Features:
- Setup wizard (multi-step provisioning)
- QR code generation for credentials and Wi-Fi
- Network configuration (SSID, DNS, static IP)
- Meter profile selection and connectivity test
- Service status dashboard
- Device registration with cloud backend
- Basic auth (single installer credential)
- HTTPS with self-signed certificate (auto-shutdown after 30 min)
"""

import logging
import json
import asyncio
import glob
import os
import socket
import subprocess
from datetime import datetime
from dataclasses import asdict
from typing import Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import aiofiles

from .meter_tester import MeterTester
from .network_manager import NetworkManager
from .qr_code_generator import QRCodeGenerator

# Global state
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Configuration paths
CONFIG_DIR = Path(os.getenv("METERHUB_CONFIG_DIR", "/etc/meterhub"))
STATE_DIR = Path(os.getenv("METERHUB_STATE_DIR", "/var/lib/meterhub"))
CACHE_DIR = Path(os.getenv("METERHUB_CACHE_DIR", "/var/cache/meterhub"))
LOG_DIR = Path(os.getenv("METERHUB_LOG_DIR", "/var/log/meterhub"))
PROFILE_DIR = CONFIG_DIR / "profiles"
REPO_PROFILE_DIR = Path(__file__).resolve().parents[2] / "profiles"
SERVICE_NAMES = {
    "acquisition": "meterhub-acquisition",
    "uploader": "meterhub-uploader",
    "installer_ui": "meterhub-installer-ui",
}


class StatusEnum:
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProvisioningState(BaseModel):
    """Provisioning state tracker."""

    status: str = StatusEnum.NOT_STARTED
    step: int = 0
    device_id: str | None = None
    society_id: str | None = None
    panel_id: str | None = None
    wi_fi_ssid: str | None = None
    mqtt_endpoint: str | None = None
    https_endpoint: str | None = None
    meter_profile: str | None = None
    meter_device: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = datetime.utcnow()
            self.updated_at = datetime.utcnow()


class DeviceConfig(BaseModel):
    """Device configuration."""

    device_id: str
    society_id: str
    panel_id: str
    wi_fi_ssid: str
    mqtt_endpoint: str
    https_endpoint: str
    oauth2_token: str
    device_secret: str
    meter_type: str
    meter_device: str
    meter_baud_rate: int = 9600
    meter_parity: str = "N"
    wi_fi_password: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = datetime.utcnow()


# Shared service state
def _run_command(command: list[str], timeout: int = 5) -> dict[str, Any]:
    """Run a local command and return a JSON-safe result."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except FileNotFoundError:
        return {"returncode": 127, "stdout": "", "stderr": f"{command[0]} not found"}
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": 124,
            "stdout": (e.stdout or "").strip() if isinstance(e.stdout, str) else "",
            "stderr": f"Timed out after {timeout}s",
        }


def _config_path(filename: str) -> Path:
    """Return writable config path, with a dev/test fallback outside /etc."""
    if os.getenv("METERHUB_ENV") == "production":
        return CONFIG_DIR / filename

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        probe = CONFIG_DIR / ".write-test"
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
        return CONFIG_DIR / filename
    except OSError:
        fallback = Path(os.getenv("METERHUB_DEV_CONFIG_DIR", "/tmp/meterhub"))
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / filename


def _systemctl_status(unit: str) -> dict[str, Any]:
    """Read systemd unit state if systemd is available."""
    active = _run_command(["systemctl", "is-active", unit], timeout=3)
    enabled = _run_command(["systemctl", "is-enabled", unit], timeout=3)
    show = _run_command(
        [
            "systemctl",
            "show",
            unit,
            "--property=LoadState,ActiveState,SubState,MainPID,NRestarts,ExecMainStatus",
            "--no-page",
        ],
        timeout=3,
    )
    details: dict[str, str] = {}
    for line in show["stdout"].splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            details[key] = value

    return {
        "name": unit,
        "unit": unit,
        "status": active["stdout"] or "unknown",
        "active": active["stdout"] or "unknown",
        "enabled": enabled["stdout"] or "unknown",
        "load_state": details.get("LoadState", "unknown"),
        "sub_state": details.get("SubState", "unknown"),
        "main_pid": int(details.get("MainPID") or 0),
        "restart_count": int(details.get("NRestarts") or 0),
        "exec_status": int(details.get("ExecMainStatus") or 0),
        "available": active["returncode"] != 127,
    }


def _list_profile_files() -> list[Path]:
    """List meter profile YAML files from installed config, then repo fallback."""
    profiles: dict[str, Path] = {}
    for directory in (PROFILE_DIR, REPO_PROFILE_DIR):
        if directory.exists():
            for path in sorted(directory.glob("*.yaml")):
                profiles.setdefault(path.name, path)
    return list(profiles.values())


def _serial_devices() -> list[dict[str, Any]]:
    """Return visible serial devices that may be used for Modbus RTU."""
    devices = []
    for pattern in ("/dev/ttyUSB*", "/dev/ttyAMA*", "/dev/ttyACM*", "/dev/serial/by-id/*"):
        for item in sorted(glob.glob(pattern)):
            path = Path(item)
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            devices.append(
                {
                    "path": str(path),
                    "resolved_path": str(resolved),
                    "exists": path.exists(),
                }
            )
    return devices


def _sqlite_count(db_path: Path, table: str) -> int | None:
    """Return a table row count if sqlite can open the database."""
    try:
        import sqlite3

        if not db_path.exists():
            return None
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0])
    except Exception:
        return None


class InstallerService:
    """Installer service state manager."""

    def __init__(self) -> None:
        self.provisioning_state = ProvisioningState()
        self.device_config: DeviceConfig | None = None
        self.start_time = datetime.utcnow()
        self.auto_shutdown_timer: asyncio.Task[None] | None = None

    async def reset_provisioning(self) -> None:
        """Reset to new provisioning session."""
        self.provisioning_state = ProvisioningState()
        logger.info("Provisioning state reset")

    async def update_provisioning(self, **updates: Any) -> None:
        """Update provisioning state."""
        for key, value in updates.items():
            if hasattr(self.provisioning_state, key):
                setattr(self.provisioning_state, key, value)
        self.provisioning_state.updated_at = datetime.utcnow()
        logger.info(f"Provisioning state updated: {updates}")

    async def save_device_config(self, config: DeviceConfig) -> bool:
        """Save device configuration to disk."""
        try:
            config_path = _config_path("device_config.json")
            config_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(config_path, "w") as f:
                await f.write(config.model_dump_json(indent=2))

            logger.info(f"Device config saved: {config_path}")
            self.device_config = config
            await self.update_provisioning(
                status=StatusEnum.IN_PROGRESS,
                device_id=config.device_id,
                society_id=config.society_id,
                panel_id=config.panel_id,
                wi_fi_ssid=config.wi_fi_ssid,
                mqtt_endpoint=config.mqtt_endpoint,
                https_endpoint=config.https_endpoint,
                meter_profile=config.meter_type,
                meter_device=config.meter_device,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    async def load_device_config(self) -> DeviceConfig | None:
        """Load device configuration from disk."""
        try:
            config_path = _config_path("device_config.json")
            if not config_path.exists():
                return None

            async with aiofiles.open(config_path, "r") as f:
                content = await f.read()
                data = json.loads(content)
                self.device_config = DeviceConfig(**data)
                return self.device_config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return None

    def get_uptime_seconds(self) -> int:
        """Get installer uptime."""
        return int((datetime.utcnow() - self.start_time).total_seconds())


# Global service instance
service = InstallerService()

# FastAPI app
app = FastAPI(
    title="MeterHub Installer UI",
    description="Device provisioning and commissioning interface",
    version="1.0.0",
)


# ============================================================================
# Health & Info Endpoints
# ============================================================================


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": service.get_uptime_seconds(),
    }


@app.get("/info", tags=["System"])
async def device_info() -> dict[str, Any]:
    """Get device information."""
    config = service.device_config or await service.load_device_config()
    return {
        "device_id": config.device_id if config else None,
        "hostname": socket.gethostname(),
        "provisioning_status": service.provisioning_state.status,
        "provisioning_step": service.provisioning_state.step,
        "uptime_seconds": service.get_uptime_seconds(),
    }


# ============================================================================
# Provisioning Wizard Endpoints
# ============================================================================


@app.get("/", response_class=HTMLResponse, tags=["UI"])
async def dashboard() -> str:
    """Main dashboard page (single-page app)."""
    return """
    <!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>MeterHub Provisioning Console</title>

            <style>
            :root{
                --bg:#edf2f7;
                --panel:#ffffff;
                --panel-2:#f8fafc;
                --border:#dbe4ee;
                --text:#0f172a;
                --muted:#64748b;
                --soft:#94a3b8;

                --primary:#2563eb;
                --primary-2:#1d4ed8;
                --primary-soft:#dbeafe;

                --success:#16a34a;
                --danger:#dc2626;
                --warning:#d97706;

                --shadow:
                    0 1px 2px rgba(0,0,0,.03),
                    0 8px 24px rgba(15,23,42,.06);

                --radius:18px;
                --radius-sm:12px;

                --mono:ui-monospace,SFMono-Regular,Menlo,monospace;
            }

            *{box-sizing:border-box;margin:0;padding:0}

            body{
                font-family:
                    Inter,
                    -apple-system,
                    BlinkMacSystemFont,
                    "Segoe UI",
                    sans-serif;

                background:
                    radial-gradient(circle at top left,#dbeafe 0%,transparent 28%),
                    radial-gradient(circle at bottom right,#e9d5ff 0%,transparent 22%),
                    var(--bg);

                color:var(--text);
                height:100vh;
                overflow:hidden;
                padding:14px;
            }

            /* ───────────────────────── APP ───────────────────────── */

            .app{
                display:grid;
                grid-template-columns:280px 1fr;
                gap:14px;
                height:100%;
            }

            /* ───────────────────── SIDEBAR ───────────────────────── */

            .sidebar{
                background:rgba(255,255,255,.78);
                backdrop-filter:blur(18px);
                border:1px solid rgba(255,255,255,.7);
                border-radius:28px;
                padding:18px;
                box-shadow:var(--shadow);

                display:flex;
                flex-direction:column;
                gap:18px;
            }

            .brand{
                display:flex;
                align-items:center;
                gap:12px;
            }

            .logo{
                width:44px;
                height:44px;
                border-radius:14px;

                background:
                    linear-gradient(135deg,#2563eb,#7c3aed);

                box-shadow:
                    inset 0 1px 0 rgba(255,255,255,.35),
                    0 6px 20px rgba(37,99,235,.28);

                position:relative;
            }

            .logo::after{
                content:'';
                position:absolute;
                inset:11px;
                border-radius:10px;
                background:white;
                opacity:.92;
            }

            .brand h1{
                font-size:1rem;
                line-height:1.1;
                letter-spacing:-.02em;
            }

            .brand small{
                color:var(--muted);
                font-size:.74rem;
            }

            .nav{
                display:flex;
                flex-direction:column;
                gap:8px;
            }

            .nav-btn{
                border:none;
                background:transparent;
                padding:14px 16px;
                border-radius:16px;
                text-align:left;
                cursor:pointer;

                display:flex;
                align-items:center;
                gap:12px;

                transition:.18s ease;
            }

            .nav-btn:hover{
                background:rgba(255,255,255,.65);
            }

            .nav-btn.active{
                background:white;
                box-shadow:var(--shadow);
            }

            .nav-icon{
                width:38px;
                height:38px;
                border-radius:12px;

                display:flex;
                align-items:center;
                justify-content:center;

                font-size:1rem;
                background:var(--primary-soft);
                color:var(--primary);
                flex-shrink:0;
            }

            .nav-meta{
                display:flex;
                flex-direction:column;
            }

            .nav-title{
                font-weight:700;
                font-size:.88rem;
            }

            .nav-sub{
                font-size:.72rem;
                color:var(--muted);
            }

            /* ───────────────────── STATUS ───────────────────────── */

            .status-card{
                margin-top:auto;

                background:
                    linear-gradient(135deg,#0f172a,#1e293b);

                color:white;
                border-radius:22px;
                padding:18px;
            }

            .status-row{
                display:flex;
                justify-content:space-between;
                margin-bottom:12px;
            }

            .status-label{
                color:rgba(255,255,255,.7);
                font-size:.74rem;
            }

            .progress{
                height:10px;
                border-radius:999px;
                background:rgba(255,255,255,.08);
                overflow:hidden;
            }

            .progress > div{
                height:100%;
                width:20%;
                background:
                    linear-gradient(90deg,#60a5fa,#818cf8);
            }

            /* ───────────────────── MAIN ───────────────────────── */

            .main{
                display:flex;
                flex-direction:column;
                gap:14px;
                overflow:hidden;
            }

            .hero{
                background:rgba(255,255,255,.82);
                backdrop-filter:blur(20px);

                border-radius:28px;
                padding:22px 26px;

                display:flex;
                justify-content:space-between;
                align-items:center;

                box-shadow:var(--shadow);
            }

            .hero h2{
                font-size:1.45rem;
                letter-spacing:-.03em;
            }

            .hero p{
                color:var(--muted);
                margin-top:4px;
                font-size:.9rem;
            }

            .hero-actions{
                display:flex;
                gap:10px;
            }

            button{
                border:none;
                border-radius:14px;
                padding:11px 18px;
                font-size:.82rem;
                font-weight:600;
                cursor:pointer;
                transition:.18s ease;
            }

            .primary{
                background:linear-gradient(135deg,#2563eb,#4f46e5);
                color:white;
                box-shadow:0 8px 20px rgba(37,99,235,.22);
            }

            .primary:hover{
                transform:translateY(-1px);
            }

            .ghost{
                background:white;
                color:var(--text);
                border:1px solid var(--border);
            }

            .ghost:hover{
                background:#f8fafc;
            }

            /* ───────────────────── CONTENT ───────────────────────── */

            .content{
                flex:1;
                min-height:0;
                display:grid;
                grid-template-columns:1.1fr .9fr;
                gap:14px;
            }

            .panel{
                background:rgba(255,255,255,.82);
                backdrop-filter:blur(18px);

                border-radius:28px;
                box-shadow:var(--shadow);

                overflow:hidden;

                display:flex;
                flex-direction:column;
            }

            .panel-head{
                padding:18px 22px;
                border-bottom:1px solid rgba(226,232,240,.9);

                display:flex;
                align-items:center;
                justify-content:space-between;
            }

            .panel-title{
                font-weight:800;
                letter-spacing:-.02em;
            }

            .panel-sub{
                color:var(--muted);
                font-size:.78rem;
                margin-top:2px;
            }

            /* ───────────────────── INSTALLER ───────────────────────── */

            .steps{
                padding:22px;
                display:grid;
                grid-template-columns:repeat(5,1fr);
                gap:12px;
            }

            .step{
                padding:16px;
                border-radius:20px;
                background:var(--panel-2);
                border:1px solid var(--border);

                position:relative;
                overflow:hidden;
            }

            .step.active{
                background:linear-gradient(135deg,#2563eb,#4f46e5);
                color:white;
                border:none;
            }

            .step-num{
                width:30px;
                height:30px;
                border-radius:10px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:rgba(255,255,255,.14);
                font-size:.78rem;
                font-weight:700;
                margin-bottom:12px;
            }

            .step h4{
                font-size:.86rem;
                margin-bottom:4px;
            }

            .step p{
                font-size:.72rem;
                opacity:.85;
                line-height:1.45;
            }

            /* ───────────────────── FORM ───────────────────────── */

            .form-wrap{
                padding:22px;
                overflow:auto;
            }

            .form-grid{
                display:grid;
                grid-template-columns:repeat(2,1fr);
                gap:14px;
            }

            .field{
                display:flex;
                flex-direction:column;
                gap:6px;
            }

            .field.full{
                grid-column:1/-1;
            }

            label{
                font-size:.72rem;
                font-weight:700;
                color:var(--muted);
            }

            input,select{
                width:100%;
                border:1px solid var(--border);
                background:white;
                border-radius:14px;
                padding:12px 14px;
                font-size:.86rem;
                transition:.18s ease;
            }

            input:focus,select:focus{
                outline:none;
                border-color:#93c5fd;
                box-shadow:0 0 0 5px rgba(37,99,235,.08);
            }

            .form-actions{
                margin-top:20px;
                display:flex;
                gap:10px;
            }

            /* ───────────────────── DIAGNOSTICS ───────────────────────── */

            .diag-grid{
                padding:22px;
                display:grid;
                grid-template-columns:repeat(3,1fr);
                gap:12px;
            }

            .diag-btn{
                background:white;
                border:1px solid var(--border);
                border-radius:20px;
                padding:18px;

                display:flex;
                flex-direction:column;
                gap:8px;

                cursor:pointer;
                transition:.18s ease;
            }

            .diag-btn:hover{
                transform:translateY(-2px);
                box-shadow:var(--shadow);
            }

            .diag-icon{
                width:44px;
                height:44px;
                border-radius:14px;

                display:flex;
                align-items:center;
                justify-content:center;

                background:var(--primary-soft);
                color:var(--primary);
                font-size:1rem;
            }

            .diag-btn h4{
                font-size:.84rem;
            }

            .diag-btn p{
                font-size:.72rem;
                color:var(--muted);
                line-height:1.45;
            }

            /* ───────────────────── OUTPUT ───────────────────────── */

            .output{
                padding:22px;
                overflow:auto;
                font-family:var(--mono);
                font-size:.8rem;
                line-height:1.65;
            }

            .output pre{
                white-space:pre-wrap;
                word-break:break-word;
            }

            .hidden{
                display:none !important;
            }

            /* ───────────────────── MOBILE ───────────────────────── */

            @media(max-width:1200px){
                .content{
                    grid-template-columns:1fr;
                }
            }

            @media(max-width:900px){

                body{
                    overflow:auto;
                    height:auto;
                }

                .app{
                    grid-template-columns:1fr;
                    height:auto;
                }

                .steps{
                    grid-template-columns:1fr 1fr;
                }

                .diag-grid{
                    grid-template-columns:1fr 1fr;
                }

                .form-grid{
                    grid-template-columns:1fr;
                }
            }

            </style>
            </head>

            <body>

            <div class="app">

                <!-- SIDEBAR -->
                <aside class="sidebar">

                    <div class="brand">
                        <div class="logo"></div>
                        <div>
                            <h1>MeterHub Console</h1>
                            <small>Provisioning Studio</small>
                        </div>
                    </div>

                    <div class="nav">

                        <button class="nav-btn active" onclick="showTab('installer', this)">
                            <div class="nav-icon">⚡</div>
                            <div class="nav-meta">
                                <div class="nav-title">Installer Flow</div>
                                <div class="nav-sub">Provisioning lifecycle</div>
                            </div>
                        </button>

                        <button class="nav-btn" onclick="showTab('config', this)">
                            <div class="nav-icon">🛠</div>
                            <div class="nav-meta">
                                <div class="nav-title">Configuration</div>
                                <div class="nav-sub">Save & edit forms</div>
                            </div>
                        </button>

                        <button class="nav-btn" onclick="showTab('diagnostics', this)">
                            <div class="nav-icon">📡</div>
                            <div class="nav-meta">
                                <div class="nav-title">Diagnostics</div>
                                <div class="nav-sub">Network & meter tools</div>
                            </div>
                        </button>

                    </div>

                    <div class="status-card">

                        <div class="status-row">
                            <div>
                                <div class="status-label">Device Status</div>
                                <div id="status_pill">Ready</div>
                            </div>

                            <div style="text-align:right">
                                <div class="status-label">Progress</div>
                                <div id="step_pill">1 / 5</div>
                            </div>
                        </div>

                        <div class="progress">
                            <div id="progress_bar"></div>
                        </div>

                    </div>

                </aside>

                <!-- MAIN -->
                <main class="main">

                    <section class="hero">
                        <div>
                            <h2>Provision & Monitor Devices</h2>
                            <p>
                                Modern installer workspace for MeterHub gateways,
                                diagnostics, Wi-Fi onboarding and QR provisioning.
                            </p>
                        </div>

                        <div class="hero-actions">
                            <button class="ghost">Export Config</button>
                            <button class="primary">Deploy Gateway</button>
                        </div>
                    </section>

                    <section class="content">

                        <!-- LEFT -->
                        <div class="panel">

                            <!-- INSTALLER TAB -->
                            <div id="installer" class="tab-view">

                                <div class="panel-head">
                                    <div>
                                        <div class="panel-title">Installer Workflow</div>
                                        <div class="panel-sub">
                                            Guided provisioning lifecycle
                                        </div>
                                    </div>
                                </div>

                                <div class="steps">

                                    <div class="step active">
                                        <div class="step-num">01</div>
                                        <h4>Initialize</h4>
                                        <p>Load provisioning state and validate hardware.</p>
                                    </div>

                                    <div class="step">
                                        <div class="step-num">02</div>
                                        <h4>Configure</h4>
                                        <p>Apply network, meter and cloud parameters.</p>
                                    </div>

                                    <div class="step">
                                        <div class="step-num">03</div>
                                        <h4>Register</h4>
                                        <p>Link gateway with cloud provisioning service.</p>
                                    </div>

                                    <div class="step">
                                        <div class="step-num">04</div>
                                        <h4>Validate</h4>
                                        <p>Test meter communication and MQTT handshake.</p>
                                    </div>

                                    <div class="step">
                                        <div class="step-num">05</div>
                                        <h4>Deploy</h4>
                                        <p>Finalize onboarding and activate telemetry.</p>
                                    </div>

                                </div>

                            </div>

                            <!-- CONFIG TAB -->
                            <div id="config" class="tab-view hidden">

                                <div class="panel-head">
                                    <div>
                                        <div class="panel-title">Gateway Configuration</div>
                                        <div class="panel-sub">
                                            Secure device provisioning form
                                        </div>
                                    </div>
                                </div>

                                <div class="form-wrap">

                                    <div class="form-grid">

                                        <div class="field">
                                            <label>Device ID</label>
                                            <input value="meter-001">
                                        </div>

                                        <div class="field">
                                            <label>Society ID</label>
                                            <input value="test-society">
                                        </div>

                                        <div class="field">
                                            <label>Panel ID</label>
                                            <input value="main-panel">
                                        </div>

                                        <div class="field">
                                            <label>Wi-Fi SSID</label>
                                            <input value="test-wifi">
                                        </div>

                                        <div class="field">
                                            <label>Wi-Fi Password</label>
                                            <input type="password">
                                        </div>

                                        <div class="field">
                                            <label>MQTT Endpoint</label>
                                            <input value="test.mosquitto.org">
                                        </div>

                                        <div class="field full">
                                            <label>HTTPS Endpoint</label>
                                            <input value="https://api.example.com/v1">
                                        </div>

                                        <div class="field">
                                            <label>OAuth2 Token</label>
                                            <input value="test-token">
                                        </div>

                                        <div class="field">
                                            <label>Device Secret</label>
                                            <input value="test-secret">
                                        </div>

                                        <div class="field">
                                            <label>Meter Profile</label>
                                            <select>
                                                <option>schneider-em6400</option>
                                            </select>
                                        </div>

                                        <div class="field">
                                            <label>Serial Device</label>
                                            <input value="/dev/ttyUSB0">
                                        </div>

                                    </div>

                                    <div class="form-actions">
                                        <button class="primary">
                                            Save Configuration
                                        </button>

                                        <button class="ghost">
                                            Load Saved Config
                                        </button>
                                    </div>

                                </div>

                            </div>

                            <!-- DIAGNOSTICS TAB -->
                            <div id="diagnostics" class="tab-view hidden">

                                <div class="panel-head">
                                    <div>
                                        <div class="panel-title">Diagnostics & Utilities</div>
                                        <div class="panel-sub">
                                            Real-time gateway tooling
                                        </div>
                                    </div>
                                </div>

                                <div class="diag-grid">

                                    <div class="diag-btn">
                                        <div class="diag-icon">💚</div>
                                        <h4>Health Check</h4>
                                        <p>Verify API and runtime health.</p>
                                    </div>

                                    <div class="diag-btn">
                                        <div class="diag-icon">📶</div>
                                        <h4>Wi-Fi Scan</h4>
                                        <p>Discover nearby networks.</p>
                                    </div>

                                    <div class="diag-btn">
                                        <div class="diag-icon">⚙️</div>
                                        <h4>System Status</h4>
                                        <p>CPU, memory and storage telemetry.</p>
                                    </div>

                                    <div class="diag-btn">
                                        <div class="diag-icon">📟</div>
                                        <h4>Meter Test</h4>
                                        <p>Validate Modbus communication.</p>
                                    </div>

                                    <div class="diag-btn">
                                        <div class="diag-icon">🧾</div>
                                        <h4>Logs</h4>
                                        <p>Inspect runtime service logs.</p>
                                    </div>

                                    <div class="diag-btn">
                                        <div class="diag-icon">🔳</div>
                                        <h4>QR Generator</h4>
                                        <p>Create Wi-Fi and device QR codes.</p>
                                    </div>

                                </div>

                            </div>

                        </div>

                        <!-- RIGHT -->
                        <div class="panel">

                            <div class="panel-head">
                                <div>
                                    <div class="panel-title">Response Console</div>
                                    <div class="panel-sub">
                                        API output, provisioning logs and QR previews
                                    </div>
                                </div>
                            </div>

                            <div class="output">
            <pre>{
            "status": "ready",
            "gateway": "meter-001",
            "network": "connected",
            "mqtt": "online",
            "meter": "detected",
            "cloud_sync": true
            }</pre>
                            </div>

                        </div>

                    </section>

                </main>

            </div>

            <script>

            function showTab(id, el){

                document.querySelectorAll('.tab-view')
                    .forEach(v => v.classList.add('hidden'));

                document.getElementById(id)
                    .classList.remove('hidden');

                document.querySelectorAll('.nav-btn')
                    .forEach(b => b.classList.remove('active'));

                el.classList.add('active');
            }

            </script>
            </body>
        </html>
    """


@app.post("/api/provisioning/step/next", tags=["Provisioning"])
async def next_provisioning_step() -> dict[str, Any]:
    """Advance to next provisioning step."""
    step = service.provisioning_state.step
    if step < 5:
        await service.update_provisioning(step=step + 1)
        if step == 4:
            await service.update_provisioning(status=StatusEnum.COMPLETED)
    return {
        "status": service.provisioning_state.status,
        "step": service.provisioning_state.step,
    }


@app.post("/api/provisioning/reset", tags=["Provisioning"])
async def reset_provisioning() -> dict[str, str]:
    """Reset provisioning state."""
    await service.reset_provisioning()
    return {"message": "Provisioning reset"}


@app.get("/api/provisioning/status", tags=["Provisioning"])
async def get_provisioning_status() -> dict[str, Any]:
    """Get current provisioning status."""
    return {
        "status": service.provisioning_state.status,
        "step": service.provisioning_state.step,
        "device_id": service.provisioning_state.device_id,
    }


# ============================================================================
# Device Configuration Endpoints
# ============================================================================


@app.post("/api/config/set", tags=["Configuration"])
async def set_device_config(config: DeviceConfig = Body(...)) -> dict[str, str]:
    """Save device configuration."""
    success = await service.save_device_config(config)
    if success:
        return {"message": "Device configured successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save configuration",
        )


@app.get("/api/config/get", tags=["Configuration"])
async def get_device_config() -> dict[str, Any] | None:
    """Get device configuration."""
    config = await service.load_device_config()
    if config:
        return config.model_dump(mode="json")
    return None


# ============================================================================
# Service Status Endpoints
# ============================================================================


@app.get("/api/services/status", tags=["Services"])
async def get_services_status() -> dict[str, dict[str, Any]]:
    """Get status of all MeterHub services."""
    services = {key: _systemctl_status(unit) for key, unit in SERVICE_NAMES.items()}
    services["installer_ui"]["uptime_seconds"] = service.get_uptime_seconds()
    services["acquisition"]["telemetry_rows"] = _sqlite_count(
        CACHE_DIR / "telemetry.db", "meter_readings"
    )
    services["uploader"]["queued_rows"] = _sqlite_count(
        CACHE_DIR / "telemetry.db", "meter_readings"
    )
    return services


@app.post("/api/services/{service_key}/{action}", tags=["Services"])
async def control_service(service_key: str, action: str) -> dict[str, Any]:
    """Start, stop, restart, enable, or disable a MeterHub systemd service."""
    if service_key not in SERVICE_NAMES:
        raise HTTPException(status_code=404, detail="Unknown service")
    if action not in {"start", "stop", "restart", "enable", "disable"}:
        raise HTTPException(status_code=400, detail="Unsupported action")

    unit = SERVICE_NAMES[service_key]
    command = ["systemctl", action, unit]
    if os.geteuid() != 0:
        command.insert(0, "sudo")
    result = _run_command(command, timeout=20)
    return {
        "service": service_key,
        "unit": unit,
        "action": action,
        "ok": result["returncode"] == 0,
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "status": _systemctl_status(unit),
    }


# ============================================================================
# QR Code Endpoints
# ============================================================================


@app.get("/api/qrcode/device", tags=["QR Code"])
async def get_device_qr_code(format: str = Query("svg")) -> dict[str, str]:
    """Generate QR code for device credentials."""
    config = service.device_config or await service.load_device_config()
    if not config:
        raise HTTPException(status_code=404, detail="Device not configured")

    return QRCodeGenerator().generate_device_qr(
        device_id=config.device_id,
        society_id=config.society_id,
        panel_id=config.panel_id,
        format=format,
    )


@app.get("/api/qrcode/wifi", tags=["QR Code"])
async def get_wifi_qr_code() -> dict[str, str]:
    """Generate QR code for Wi-Fi provisioning."""
    config = service.device_config or await service.load_device_config()
    if not config:
        raise HTTPException(status_code=404, detail="Device not configured")

    return QRCodeGenerator().generate_wifi_qr(
        ssid=config.wi_fi_ssid,
        password=config.wi_fi_password,
        security="WPA" if config.wi_fi_password else "nopass",
    )


# ============================================================================
# Network Endpoints
# ============================================================================


@app.get("/api/network/scan", tags=["Network"])
async def scan_networks() -> dict[str, list[dict[str, Any]]]:
    """Scan for available Wi-Fi networks."""
    networks = await NetworkManager(use_nmcli=True).scan_networks()
    if networks:
        return {"networks": [asdict(network) for network in networks]}

    networks = await NetworkManager(use_nmcli=False).scan_networks()
    return {
        "networks": [asdict(network) for network in networks],
    }


@app.get("/api/network/status", tags=["Network"])
async def get_network_status() -> dict[str, Any]:
    """Get current network status."""
    status_data = await NetworkManager(use_nmcli=True).get_status()
    if status_data.get("status") == "unknown":
        status_data = await NetworkManager(use_nmcli=False).get_status()

    route = _run_command(["ip", "route", "show", "default"], timeout=3)
    hostname = _run_command(["hostname", "-I"], timeout=3)
    status_data.update(
        {
            "hostname": socket.gethostname(),
            "addresses": hostname["stdout"].split(),
            "default_route": route["stdout"],
            "wi_fi_connected": bool(status_data.get("ip_address")),
            "ethernet_connected": Path("/sys/class/net/eth0/carrier").exists()
            and Path("/sys/class/net/eth0/carrier").read_text().strip() == "1",
        }
    )
    status_data.setdefault("gateway", None)
    status_data.setdefault("dns", [])
    if status_data.get("ip_address") is None:
        status_data["ip_address"] = ""
    return status_data


@app.post("/api/network/connect", tags=["Network"])
async def connect_network(ssid: str = Body(...), password: str = Body("")) -> dict[str, Any]:
    """Connect to a Wi-Fi network using the local network manager."""
    connected = await NetworkManager(use_nmcli=True).connect(ssid, password)
    if not connected:
        connected = await NetworkManager(use_nmcli=False).connect(ssid, password)
    return {
        "ssid": ssid,
        "connected": connected,
    }


# ============================================================================
# Meter Test Endpoints
# ============================================================================


@app.post("/api/meter/test", tags=["Meter"])
async def test_meter_connectivity(
    device: str = Query("/dev/ttyUSB0"),
    profile: str | None = Query(None),
) -> dict[str, Any]:
    """Test Modbus meter connectivity."""
    if not Path(device).exists():
        return {
            "device": device,
            "connected": False,
            "registers_read": 0,
            "registers_failed": 0,
            "test_duration_ms": 0,
            "timestamp": datetime.utcnow().isoformat(),
            "error_message": f"Serial device not found: {device}",
            "available_devices": _serial_devices(),
        }

    config = service.device_config or await service.load_device_config()
    profile_name = profile or (config.meter_type if config else "schneider-em6400.yaml")
    if not profile_name.endswith(".yaml"):
        profile_name = f"{profile_name}.yaml"

    profile_path = PROFILE_DIR / profile_name
    if not profile_path.exists():
        profiles = [path for path in _list_profile_files() if path.name == profile_name]
        if not profiles:
            profiles = _list_profile_files()
        if not profiles:
            raise HTTPException(status_code=404, detail="No meter profiles installed")
        profile_path = profiles[0]

    result = await MeterTester().test_connectivity(
        device=device,
        meter_profile_path=str(profile_path),
    )
    data = asdict(result)
    data["timestamp"] = result.timestamp.isoformat()
    return data


@app.get("/api/meter/profiles", tags=["Meter"])
async def list_meter_profiles() -> dict[str, list[str]]:
    """List available meter profiles."""
    profiles = _list_profile_files()
    return {
        "profiles": [path.name for path in profiles],
    }


@app.get("/api/meter/devices", tags=["Meter"])
async def list_meter_devices() -> dict[str, list[dict[str, Any]]]:
    """List available serial devices for RS485 adapters."""
    return {"devices": _serial_devices()}


# ============================================================================
# Device Registration Endpoints
# ============================================================================


@app.post("/api/registration/submit", tags=["Registration"])
async def submit_device_registration(
    device_id: str = Body(...), oauth2_token: str = Body(...)
) -> dict[str, str]:
    """Record device registration inputs for local commissioning."""
    registration_path = _config_path("registration.json")
    payload = {
        "device_id": device_id,
        "oauth2_token_set": bool(oauth2_token),
        "registered_at": datetime.utcnow().isoformat(),
        "mode": "local",
    }
    try:
        async with aiofiles.open(registration_path, "w") as f:
            await f.write(json.dumps(payload, indent=2))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save registration: {e}") from e

    return {"message": "Device registration saved locally", "device_id": device_id}


# ============================================================================
# System Endpoints
# ============================================================================


@app.post("/api/system/shutdown", tags=["System"])
async def shutdown_installer_ui() -> dict[str, str]:
    """Gracefully shutdown installer UI (30 min timeout)."""
    return {"message": "Installer UI will shutdown in 30 minutes"}


@app.get("/api/system/status", tags=["System"])
async def get_system_status() -> dict[str, Any]:
    """Get local system status for commissioning."""
    disk = _run_command(["df", "-h", "/"], timeout=3)
    memory = _run_command(["free", "-h"], timeout=3)
    temperature_path = Path("/sys/class/thermal/thermal_zone0/temp")
    temperature_c: float | None = None
    if temperature_path.exists():
        try:
            temperature_c = int(temperature_path.read_text().strip()) / 1000
        except ValueError:
            temperature_c = None

    return {
        "hostname": socket.gethostname(),
        "time_utc": datetime.utcnow().isoformat(),
        "uptime_seconds": service.get_uptime_seconds(),
        "disk": disk["stdout"],
        "memory": memory["stdout"],
        "temperature_c": temperature_c,
        "config_dir": str(CONFIG_DIR),
        "state_dir": str(STATE_DIR),
        "cache_dir": str(CACHE_DIR),
        "log_dir": str(LOG_DIR),
    }


@app.get("/api/system/logs", tags=["System"])
async def get_system_logs(lines: int = Query(100)) -> dict[str, list[str]]:
    """Get recent system logs."""
    safe_lines = max(1, min(lines, 500))
    result = _run_command(
        ["journalctl", "-u", "meterhub-installer-ui", "-n", str(safe_lines), "--no-pager"],
        timeout=5,
    )
    if result["returncode"] == 127:
        log_files = sorted(LOG_DIR.glob("*.log")) if LOG_DIR.exists() else []
        logs: list[str] = []
        for log_file in log_files:
            try:
                logs.extend(log_file.read_text().splitlines()[-safe_lines:])
            except OSError:
                continue
        return {"logs": logs[-safe_lines:]}

    return {"logs": result["stdout"].splitlines()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8443,
        ssl_keyfile="/etc/meterhub/certs/key.pem",
        ssl_certfile="/etc/meterhub/certs/cert.pem",
        log_level="info",
    )
