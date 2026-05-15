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
    <html>
    <head>
        <title>MeterHub Installer</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f2f6fb;
                color: #1d2635;
            }
            .container {
                max-width: 1100px;
                margin: 0 auto;
                padding: 20px;
                background: #ffffff;
                border-radius: 18px;
                box-shadow: 0 24px 80px rgba(15, 23, 42, 0.08);
            }
            h1 { margin-top: 0; font-size: 2rem; }
            .info-row {
                display: flex;
                flex-wrap: wrap;
                gap: 16px;
                margin-bottom: 24px;
            }
            .info-card {
                flex: 1 1 220px;
                min-width: 220px;
                padding: 18px;
                background: #f5fbff;
                border: 1px solid #d8e7f6;
                border-radius: 16px;
            }
            .info-card strong {
                display: block;
                margin-bottom: 6px;
                color: #0f4fa8;
            }
            .card {
                background: #fbfdff;
                border: 1px solid #dde6f0;
                border-radius: 18px;
                padding: 22px;
                margin-bottom: 24px;
            }
            .card h2 { margin-top: 0; font-size: 1.35rem; }
            .form-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 18px;
            }
            .button-row {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                margin-top: 16px;
            }
            .button-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                gap: 12px;
                margin-top: 16px;
            }
            button {
                appearance: none;
                border: none;
                border-radius: 12px;
                padding: 12px 16px;
                background: #1e5de0;
                color: white;
                cursor: pointer;
                font-size: 0.95rem;
                transition: transform 0.12s ease, background 0.12s ease,
                    box-shadow 0.12s ease;
            }
            button:hover {
                background: #104bbe;
                transform: translateY(-1px);
                box-shadow: 0 10px 30px rgba(16, 75, 190, 0.18);
            }
            button.secondary { background: #535f70; }
            button.secondary:hover { background: #3f4c5c; }
            label {
                display: block;
                font-weight: 600;
                margin-bottom: 8px;
                color: #2d3a4d;
            }
            input, select {
                width: 100%;
                padding: 12px 14px;
                border: 1px solid #cdd8e9;
                border-radius: 12px;
                background: white;
                color: #1d2635;
                box-sizing: border-box;
            }
            .qr-panel {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }
            .qr-card {
                background: #ffffff;
                border: 1px solid #d9e4ee;
                border-radius: 18px;
                padding: 20px;
                text-align: center;
                min-height: 260px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .qr-card h3 { margin-top: 0; }
            .qr-placeholder {
                color: #6b7c94;
                font-size: 0.98rem;
            }
            .qr-code {
                margin: 0 auto;
                width: 100%;
                max-width: 340px;
            }
            .qr-code svg {
                width: 100%;
                height: auto;
                border-radius: 16px;
                border: 1px solid #d8e6f2;
            }
            .qr-details pre {
                background: #f7fbff;
                color: #1a2640;
                padding: 16px;
                border-radius: 16px;
                border: 1px solid #d7e5f1;
                min-height: 136px;
                overflow-x: auto;
                text-align: left;
            }
            pre#output {
                background: #11151f;
                color: #ecf5ff;
                padding: 18px;
                border-radius: 18px;
                border: 1px solid #2f4156;
                min-height: 220px;
                overflow-x: auto;
            }
            @media (max-width: 900px) {
                .form-grid,
                .qr-panel {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MeterHub Installer</h1>
            <div class="info-row">
                <div class="info-card">
                    <strong>Status</strong>
                    <span id="status">Loading…</span>
                </div>
                <div class="info-card">
                    <strong>Step</strong>
                    <span id="step">0 / 5</span>
                </div>
                <div class="info-card">
                    <strong>Tip</strong>
                    <span>Save configuration before generating QR codes.</span>
                </div>
            </div>

            <div class="card">
                <h2>Device Configuration</h2>
                <div class="form-grid">
                    <div>
                        <label for="device_id">Device ID</label>
                        <input id="device_id" value="meter-001">
                    </div>
                    <div>
                        <label for="society_id">Society ID</label>
                        <input id="society_id" value="test-society">
                    </div>
                    <div>
                        <label for="panel_id">Panel ID</label>
                        <input id="panel_id" value="main-panel">
                    </div>
                    <div>
                        <label for="wi_fi_ssid">Wi-Fi SSID</label>
                        <input id="wi_fi_ssid" value="test-wifi">
                    </div>
                    <div>
                        <label for="wi_fi_password">Wi-Fi Password</label>
                        <input id="wi_fi_password" type="password" value="">
                    </div>
                    <div>
                        <label for="mqtt_endpoint">MQTT Endpoint</label>
                        <input id="mqtt_endpoint" value="test.mosquitto.org">
                    </div>
                    <div>
                        <label for="https_endpoint">HTTPS Endpoint</label>
                        <input id="https_endpoint" value="https://api.example.com/v1">
                    </div>
                    <div>
                        <label for="oauth2_token">OAuth2 Token</label>
                        <input id="oauth2_token" value="test-token">
                    </div>
                    <div>
                        <label for="device_secret">Device Secret</label>
                        <input id="device_secret" value="test-secret">
                    </div>
                    <div>
                        <label for="meter_type">Meter Profile</label>
                        <select id="meter_type">
                            <option value="schneider-em6400">schneider-em6400</option>
                        </select>
                    </div>
                    <div>
                        <label for="meter_device">Meter Device</label>
                        <input id="meter_device" value="/dev/ttyUSB0">
                    </div>
                </div>
                <div class="button-row">
                    <button onclick="saveConfig()">Save Config</button>
                    <button class="secondary" onclick="loadConfig()">Load Config</button>
                </div>
            </div>

            <div class="card">
                <h2>Diagnostics</h2>
                <div class="button-grid">
                    <button onclick="callApi('/health')">Health</button>
                    <button onclick="callApi('/info')">Info</button>
                    <button onclick="callApi('/api/system/status')">System</button>
                    <button onclick="callApi('/api/system/logs?lines=80')">Logs</button>
                    <button onclick="callApi('/api/network/scan')">Network Scan</button>
                    <button onclick="callApi('/api/network/status')">Network Status</button>
                    <button onclick="callApi('/api/meter/devices')">Serial Devices</button>
                    <button onclick="callApi('/api/meter/profiles')">Meter Profiles</button>
                    <button onclick="callApi('/api/services/status')">Service Status</button>
                    <button onclick="testMeter()">Meter Test</button>
                    <button onclick="callApi('/api/qrcode/device')">Device QR</button>
                    <button onclick="callApi('/api/qrcode/wifi')">Wi-Fi QR</button>
                    <button onclick="registerDevice()">Register</button>
                </div>
            </div>

            <div class="qr-panel">
                <div class="qr-card">
                    <h3>QR Code Preview</h3>
                    <div id="qr_output" class="qr-code">
                        <div class="qr-placeholder">Click a QR button to render the SVG here.</div>
                    </div>
                </div>
                <div class="qr-card">
                    <h3>QR Metadata</h3>
                    <div id="qr_details" class="qr-details">
                        <pre>No QR generated yet.</pre>
                    </div>
                </div>
            </div>

            <div class="card">
                <h2>API Response</h2>
                <pre id="output">Results appear here.</pre>
            </div>
        </div>
        <script>
            const fields = [
                'device_id',
                'society_id',
                'panel_id',
                'wi_fi_ssid',
                'wi_fi_password',
                'mqtt_endpoint',
                'https_endpoint',
                'oauth2_token',
                'device_secret',
                'meter_type',
                'meter_device',
            ];

            function sanitizeObject(obj) {
                if (obj === null || obj === undefined) {
                    return obj;
                }
                if (Array.isArray(obj)) {
                    return obj.map(sanitizeObject);
                }
                if (typeof obj !== 'object') {
                    return obj;
                }
                const sanitized = {};
                for (const [key, value] of Object.entries(obj)) {
                    if (/password|secret|token|auth/i.test(key)) {
                        sanitized[key] = '[REDACTED]';
                    } else if (key === 'wifi_string') {
                        continue;
                    } else {
                        sanitized[key] = sanitizeObject(value);
                    }
                }
                return sanitized;
            }

            function updateQrPreview(svg, details) {
                const qrOutput = document.getElementById('qr_output');
                const qrDetails = document.getElementById('qr_details');
                qrOutput.innerHTML = svg ||
                    '<div class="qr-placeholder">No QR available.</div>';
                qrDetails.innerHTML =
                    '<pre>' + JSON.stringify(details, null, 2) + '</pre>';
            }

            function show(data) {
                const output = document.getElementById('output');
                const payload = data && typeof data === 'object' && data.body
                    ? data.body
                    : data;
                const hasQr = payload && typeof payload === 'object'
                    && typeof payload.qr_code === 'string';

                if (hasQr) {
                    const details = { status: data.status };
                    if (payload.ssid) {
                        details.type = 'Wi-Fi QR Code';
                        details.ssid = payload.ssid;
                    } else if (payload.data) {
                        details.type = 'Device QR Code';
                        try {
                            details.data = JSON.parse(payload.data);
                        } catch {
                            details.data = payload.data;
                        }
                    }
                    updateQrPreview(payload.qr_code, details);
                    output.innerText = JSON.stringify(sanitizeObject(details), null, 2);
                    return;
                }

                updateQrPreview(null, { message: 'No QR generated.' });
                output.innerText = typeof payload === 'string'
                    ? payload
                    : JSON.stringify(sanitizeObject(payload), null, 2);
            }

            async function callApi(path, opts = {}) {
                try {
                    const r = await fetch(path, opts);
                    const text = await r.text();
                    let data;
                    try {
                        data = JSON.parse(text);
                    } catch {
                        data = text;
                    }
                    show({ status: r.status, body: data });
                } catch (e) {
                    show(String(e));
                }
            }

            async function loadStatus() {
                const r = await fetch('/api/provisioning/status');
                const d = await r.json();
                document.getElementById('status').innerText = d.status;
                document.getElementById('step').innerText = `${d.step} / 5`;
            }

            async function nextStep() {
                await fetch('/api/provisioning/step/next', { method: 'POST' });
                await loadStatus();
            }

            async function resetProvisioning() {
                await fetch('/api/provisioning/reset', { method: 'POST' });
                await loadStatus();
            }

            function readConfigForm() {
                return fields.reduce((config, id) => {
                    config[id] = document.getElementById(id).value;
                    return config;
                }, {});
            }

            async function saveConfig() {
                await callApi('/api/config/set', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(readConfigForm()),
                });
                await loadStatus();
            }

            async function loadConfig() {
                const r = await fetch('/api/config/get');
                const config = await r.json();
                for (const id of fields) {
                    if (config[id] !== undefined) {
                        document.getElementById(id).value = config[id];
                    }
                }
                show({ status: r.status, body: config });
            }

            async function loadProfiles() {
                const r = await fetch('/api/meter/profiles');
                const data = await r.json();
                const select = document.getElementById('meter_type');
                select.innerHTML = '';
                for (const profile of data.profiles || []) {
                    const option = document.createElement('option');
                    option.value = profile;
                    option.innerText = profile;
                    select.appendChild(option);
                }
            }

            async function testMeter() {
                const device = encodeURIComponent(
                    document.getElementById('meter_device').value
                );
                const profile = encodeURIComponent(
                    document.getElementById('meter_type').value
                );
                const meterTestUrl =
                    '/api/meter/test?device=' + device + '&profile=' + profile;
                await callApi(meterTestUrl, { method: 'POST' });
            }

            async function registerDevice() {
                const registrationBody = JSON.stringify({
                    device_id: document.getElementById('device_id').value,
                    oauth2_token: document.getElementById('oauth2_token').value,
                });
                await callApi('/api/registration/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: registrationBody,
                });
            }

            loadStatus();
            loadProfiles();
            loadConfig();
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
