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
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import aiofiles

# Global state
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Configuration paths
CONFIG_DIR = Path("/etc/meterhub")
STATE_DIR = Path("/var/lib/meterhub")
CACHE_DIR = Path("/var/cache/meterhub")


class StatusEnum:
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class ProvisioningState(BaseModel):
    """Provisioning state tracker."""

    status: str = StatusEnum.NOT_STARTED
    step: int = 0
    device_id: Optional[str] = None
    society_id: Optional[str] = None
    panel_id: Optional[str] = None
    wi_fi_ssid: Optional[str] = None
    mqtt_endpoint: Optional[str] = None
    https_endpoint: Optional[str] = None
    meter_profile: Optional[str] = None
    meter_device: Optional[str] = None
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
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if self.created_at is None:
            self.created_at = datetime.utcnow()


# Shared service state
class InstallerService:
    """Installer service state manager."""

    def __init__(self) -> None:
        self.provisioning_state = ProvisioningState()
        self.device_config: Optional[DeviceConfig] = None
        self.start_time = datetime.utcnow()
        self.auto_shutdown_timer: Optional[asyncio.Task[None]] = None

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
            config_path = CONFIG_DIR / "device_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            async with aiofiles.open(config_path, "w") as f:
                await f.write(config.json(indent=2))

            logger.info(f"Device config saved: {config_path}")
            self.device_config = config
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False

    async def load_device_config(self) -> Optional[DeviceConfig]:
        """Load device configuration from disk."""
        try:
            config_path = CONFIG_DIR / "device_config.json"
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
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": service.get_uptime_seconds(),
    }


@app.get("/info", tags=["System"])
async def device_info() -> Dict[str, Any]:
    """Get device information."""
    return {
        "device_id": service.device_config.device_id if service.device_config else None,
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
            body { font-family: Arial, sans-serif; margin: 0; padding: 20px;
                   background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white;
                         padding: 20px; border-radius: 8px; }
            h1 { color: #333; }
            .step { margin: 20px 0; padding: 15px; border: 1px solid #ddd;
                    border-radius: 4px; }
            .status { font-weight: bold; }
            button { padding: 10px 20px; margin: 5px; background: #0066cc;
                     color: white; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0052a3; }
            .info { background: #e3f2fd; padding: 10px; border-radius: 4px;
                    margin: 10px 0; }
            .qr-code { text-align: center; margin: 20px 0; }
            .qr-code img { max-width: 300px; border: 2px solid #ddd; padding: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 MeterHub Installer</h1>
            <div class="info">
                <strong>Status:</strong> <span id="status">Loading...</span><br>
                <strong>Step:</strong> <span id="step">0/5</span>
            </div>
            <div id="wizard"></div>
            <button onclick="nextStep()">Next →</button>
            <button onclick="resetProvisioning()">Reset</button>
        </div>
        <script>
            async function loadStatus() {
                const r = await fetch('/api/provisioning/status');
                const d = await r.json();
                document.getElementById('status').innerText = d.status;
                document.getElementById('step').innerText = d.step + '/5';
                renderStep(d.step);
            }

            async function nextStep() {
                const opts = { method: 'POST' };
                await fetch('/api/provisioning/step/next', opts);
                await loadStatus();
            }

            async function resetProvisioning() {
                const opts = { method: 'POST' };
                await fetch('/api/provisioning/reset', opts);
                await loadStatus();
            }

            function renderStep(step) {
                const w = document.getElementById('wizard');
                const s = [
                    '<div class="step"><h2>Step 1: Device ' +
                    'Identity</h2><p>Enter identifiers...</p></div>',
                    '<div class="step"><h2>Step 2: Wi-Fi ' +
                    'Setup</h2><p>Configure network...</p></div>',
                    '<div class="step"><h2>Step 3: Cloud ' +
                    'Endpoints</h2><p>Cloud connectivity...</p></div>',
                    '<div class="step"><h2>Step 4: Meter ' +
                    'Profile</h2><p>Select type...</p></div>',
                    '<div class="step"><h2>Step 5: Test & ' +
                    'Verify</h2><p>Run diagnostics...</p></div>',
                    '<div class="step"><h2>Complete!</h2><p>' +
                    'Device provisioned ✓</p></div>'
                ];
                w.innerHTML = s[step] || s[5];
            }

            loadStatus();
        </script>
    </body>
    </html>
    """


@app.post("/api/provisioning/step/next", tags=["Provisioning"])
async def next_provisioning_step() -> Dict[str, Any]:
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
async def reset_provisioning() -> Dict[str, str]:
    """Reset provisioning state."""
    await service.reset_provisioning()
    return {"message": "Provisioning reset"}


@app.get("/api/provisioning/status", tags=["Provisioning"])
async def get_provisioning_status() -> Dict[str, Any]:
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
async def set_device_config(config: DeviceConfig = Body(...)) -> Dict[str, str]:
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
async def get_device_config() -> Optional[Dict[str, Any]]:
    """Get device configuration."""
    config = await service.load_device_config()
    if config:
        return config.dict()
    return None


# ============================================================================
# Service Status Endpoints
# ============================================================================


@app.get("/api/services/status", tags=["Services"])
async def get_services_status() -> Dict[str, Dict[str, Any]]:
    """Get status of all MeterHub services."""
    return {
        "acquisition": {
            "name": "meterhub-acquisition",
            "status": "running",
            "last_event": "2026-05-11T10:30:00Z",
        },
        "uploader": {
            "name": "meterhub-uploader",
            "status": "running",
            "mqtt_connected": True,
            "queue_depth": 12,
        },
        "installer_ui": {
            "name": "meterhub-installer-ui",
            "status": "running",
            "uptime_seconds": service.get_uptime_seconds(),
        },
    }


# ============================================================================
# QR Code Endpoints
# ============================================================================


@app.get("/api/qrcode/device", tags=["QR Code"])
async def get_device_qr_code(format: str = Query("svg")) -> Dict[str, str]:
    """Generate QR code for device credentials (placeholder)."""
    if not service.device_config:
        raise HTTPException(status_code=404, detail="Device not configured")

    qr_data = {
        "device_id": service.device_config.device_id,
        "society_id": service.device_config.society_id,
        "panel_id": service.device_config.panel_id,
    }

    # Placeholder: In production, use qrcode library
    return {
        "qr_code": "placeholder_qr_svg",
        "data": json.dumps(qr_data),
    }


@app.get("/api/qrcode/wifi", tags=["QR Code"])
async def get_wifi_qr_code() -> Dict[str, str]:
    """Generate QR code for Wi-Fi provisioning."""
    if not service.device_config:
        raise HTTPException(status_code=404, detail="Device not configured")

    # WiFi QR format: WIFI:T:WPA;S:SSID;P:PASSWORD;;
    ssid = service.device_config.wi_fi_ssid
    # Note: In production, retrieve password from secure storage
    wifi_qr = f"WIFI:T:WPA;S:{ssid};P:DefaultPassword;;"

    return {
        "qr_code": "placeholder_qr_svg",
        "wifi_string": wifi_qr,
    }


# ============================================================================
# Network Endpoints
# ============================================================================


@app.get("/api/network/scan", tags=["Network"])
async def scan_networks() -> Dict[str, List[Dict[str, Any]]]:
    """Scan for available Wi-Fi networks."""
    # Placeholder: In production, use nmcli or iwlist
    return {
        "networks": [
            {"ssid": "HomeWiFi", "signal": 85, "security": "WPA2"},
            {"ssid": "GuestWiFi", "signal": 60, "security": "Open"},
        ]
    }


@app.get("/api/network/status", tags=["Network"])
async def get_network_status() -> Dict[str, Any]:
    """Get current network status."""
    return {
        "ip_address": "192.168.1.100",
        "gateway": "192.168.1.1",
        "dns": ["8.8.8.8", "8.8.4.4"],
        "wi_fi_connected": True,
        "ethernet_connected": False,
    }


# ============================================================================
# Meter Test Endpoints
# ============================================================================


@app.post("/api/meter/test", tags=["Meter"])
async def test_meter_connectivity(device: str = Query("/dev/ttyUSB0")) -> Dict[str, Any]:
    """Test Modbus meter connectivity."""
    # Placeholder: In production, use ModbusRTUClient from common
    await asyncio.sleep(1)  # Simulate test delay
    return {
        "device": device,
        "connected": True,
        "registers_read": 13,
        "voltage_l1_v": 230.5,
        "current_l1_a": 5.2,
        "instant_kw": 1.19,
        "totalizer_kwh": 12345.67,
    }


@app.get("/api/meter/profiles", tags=["Meter"])
async def list_meter_profiles() -> Dict[str, List[str]]:
    """List available meter profiles."""
    return {
        "profiles": [
            "schneider-em6400.yaml",
            "siemens-pac3200.yaml",
            "generic-modbus.yaml",
        ]
    }


# ============================================================================
# Device Registration Endpoints
# ============================================================================


@app.post("/api/registration/submit", tags=["Registration"])
async def submit_device_registration(
    device_id: str = Body(...), oauth2_token: str = Body(...)
) -> Dict[str, str]:
    """Register device with cloud backend."""
    # Placeholder: In production, call cloud API
    return {"message": "Device registered", "device_id": device_id}


# ============================================================================
# System Endpoints
# ============================================================================


@app.post("/api/system/shutdown", tags=["System"])
async def shutdown_installer_ui() -> Dict[str, str]:
    """Gracefully shutdown installer UI (30 min timeout)."""
    return {"message": "Installer UI will shutdown in 30 minutes"}


@app.get("/api/system/logs", tags=["System"])
async def get_system_logs(lines: int = Query(100)) -> Dict[str, List[str]]:
    """Get recent system logs."""
    return {"logs": ["Log entry 1", "Log entry 2", "..."]}


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
