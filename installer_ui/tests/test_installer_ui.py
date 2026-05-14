"""
Unit Tests for MeterHub Installer UI

Tests:
- Provisioning workflow (6 steps)
- Device configuration save/load
- Service status endpoints
- Network endpoints
- Meter test endpoints
- QR code generation
"""

import pytest

from fastapi.testclient import TestClient

# Import app and modules
from installer_ui.meterhub_ui.app import app, InstallerService, StatusEnum
from installer_ui.meterhub_ui.qr_code_generator import QRCodeGenerator
from installer_ui.meterhub_ui.network_manager import NetworkManager


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def installer_service():
    """Fresh installer service instance."""
    service = InstallerService()
    return service


class TestHealth:
    """Health check tests."""

    def test_health_check(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "timestamp" in response.json()
        assert "uptime_seconds" in response.json()

    def test_device_info(self, client):
        """Test device info endpoint."""
        response = client.get("/info")
        assert response.status_code == 200
        data = response.json()
        assert "device_id" in data
        assert "provisioning_status" in data
        assert "provisioning_step" in data


class TestProvisioning:
    """Provisioning workflow tests."""

    def test_get_provisioning_status(self, client):
        """Test get provisioning status."""
        response = client.get("/api/provisioning/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == StatusEnum.NOT_STARTED
        assert data["step"] == 0

    def test_next_provisioning_step(self, client):
        """Test advancing provisioning step."""
        # Step 0 -> 1
        response = client.post("/api/provisioning/step/next")
        assert response.status_code == 200
        data = response.json()
        assert data["step"] == 1

        # Step 1 -> 2
        response = client.post("/api/provisioning/step/next")
        assert response.status_code == 200
        data = response.json()
        assert data["step"] == 2

    def test_provisioning_completion(self, client):
        """Test provisioning reaches completion."""
        # Advance through all steps
        for i in range(5):
            response = client.post("/api/provisioning/step/next")
            assert response.status_code == 200

        # Check final status
        response = client.get("/api/provisioning/status")
        data = response.json()
        assert data["step"] == 5
        assert data["status"] == StatusEnum.COMPLETED

    def test_reset_provisioning(self, client):
        """Test reset provisioning."""
        # Advance some steps
        client.post("/api/provisioning/step/next")
        client.post("/api/provisioning/step/next")

        # Reset
        response = client.post("/api/provisioning/reset")
        assert response.status_code == 200

        # Verify reset
        response = client.get("/api/provisioning/status")
        data = response.json()
        assert data["step"] == 0
        assert data["status"] == StatusEnum.NOT_STARTED


class TestConfiguration:
    """Device configuration tests."""

    @pytest.mark.asyncio
    async def test_set_device_config(self, client):
        """Test setting device configuration."""
        config = {
            "device_id": "meter-001",
            "society_id": "apt-001",
            "panel_id": "main-01",
            "wi_fi_ssid": "HomeWiFi",
            "mqtt_endpoint": "test.mosquitto.org",
            "https_endpoint": "https://api.example.com/v1",
            "oauth2_token": "token123",
            "device_secret": "secret123",
            "meter_type": "schneider-em6400",
            "meter_device": "/dev/ttyUSB0",
        }

        response = client.post("/api/config/set", json=config)
        assert response.status_code == 200
        assert "Device configured" in response.json()["message"]

    def test_get_device_config(self, client):
        """Test retrieving device configuration."""
        response = client.get("/api/config/get")
        # May be None if not configured
        assert response.status_code == 200


class TestServices:
    """Service status tests."""

    def test_get_services_status(self, client):
        """Test get services status."""
        response = client.get("/api/services/status")
        assert response.status_code == 200
        data = response.json()

        # Check all services present
        assert "acquisition" in data
        assert "uploader" in data
        assert "installer_ui" in data

        # Check service structure
        assert "status" in data["acquisition"]
        assert "name" in data["uploader"]
        assert "uptime_seconds" in data["installer_ui"]


class TestNetwork:
    """Network endpoint tests."""

    def test_scan_networks(self, client):
        """Test Wi-Fi network scanning."""
        response = client.get("/api/network/scan")
        assert response.status_code == 200
        data = response.json()
        assert "networks" in data
        # Placeholder data should have at least one network
        assert len(data["networks"]) >= 1

    def test_network_status(self, client):
        """Test get network status."""
        response = client.get("/api/network/status")
        assert response.status_code == 200
        data = response.json()

        assert "ip_address" in data
        assert "gateway" in data
        assert "dns" in data
        assert "wi_fi_connected" in data

        # Check types
        assert isinstance(data["ip_address"], str)
        assert isinstance(data["dns"], list)
        assert isinstance(data["wi_fi_connected"], bool)


class TestMeter:
    """Meter endpoint tests."""

    @pytest.mark.asyncio
    async def test_meter_test(self, client):
        """Test meter connectivity test."""
        response = client.post("/api/meter/test?device=/dev/ttyUSB0")
        assert response.status_code == 200
        data = response.json()

        assert "device" in data
        assert "connected" in data
        assert "registers_read" in data or "error" in data

    def test_list_meter_profiles(self, client):
        """Test list available meter profiles."""
        response = client.get("/api/meter/profiles")
        assert response.status_code == 200
        data = response.json()

        assert "profiles" in data
        assert isinstance(data["profiles"], list)
        assert len(data["profiles"]) > 0

        # Check known profiles
        assert "schneider-em6400.yaml" in data["profiles"]


class TestQRCode:
    """QR Code generation tests."""

    def test_device_qr_code(self, client):
        """Test device QR code generation."""
        response = client.get("/api/qrcode/device")
        assert response.status_code == 404  # Device not configured yet

    def test_wifi_qr_code(self, client):
        """Test Wi-Fi QR code generation."""
        response = client.get("/api/qrcode/wifi")
        assert response.status_code == 404  # No device config

    def test_qrcode_generator_device(self):
        """Test QRCodeGenerator device QR."""
        gen = QRCodeGenerator()
        result = gen.generate_device_qr(
            device_id="meter-001",
            society_id="apt-001",
            panel_id="main-01",
            format="svg",
        )

        assert "qr_code" in result
        assert "data" in result
        assert "meter-001" in result["data"]

    def test_qrcode_generator_wifi(self):
        """Test QRCodeGenerator Wi-Fi QR."""
        gen = QRCodeGenerator()
        result = gen.generate_wifi_qr(
            ssid="TestSSID",
            password="TestPassword123",
            security="WPA",
        )

        assert "qr_code" in result
        assert "wifi_string" in result
        assert "TestSSID" in result["wifi_string"]

    def test_qrcode_wifi_string_escaping(self):
        """Test Wi-Fi string special character escaping."""
        gen = QRCodeGenerator()

        # Test escaping special characters
        result = gen.generate_wifi_qr(
            ssid="Test;SSID:Special",
            password="Pass;word;123",
        )

        wifi_string = result["wifi_string"]
        # Semicolons should be escaped
        assert "\\;" in wifi_string

    def test_qrcode_generator_provisioning(self):
        """Test provisioning QR code."""
        gen = QRCodeGenerator()
        result = gen.generate_provisioning_qr(
            device_id="meter-001",
            mqtt_endpoint="test.mosquitto.org",
            https_endpoint="https://api.example.com",
        )

        assert "qr_code" in result
        assert "provisioning_data" in result
        assert "meter-001" in result["provisioning_data"]


class TestNetworkManager:
    """NetworkManager tests."""

    @pytest.mark.asyncio
    async def test_network_manager_init(self):
        """Test NetworkManager initialization."""
        nm = NetworkManager(use_nmcli=False)
        assert nm is not None

    def test_freq_to_channel_2_4ghz(self):
        """Test frequency to channel conversion (2.4 GHz)."""
        # 2.4 GHz channel 1 = 2412 MHz
        assert NetworkManager._freq_to_channel(2412) == 1
        # Channel 6 = 2437 MHz
        assert NetworkManager._freq_to_channel(2437) == 6
        # Channel 11 = 2462 MHz
        assert NetworkManager._freq_to_channel(2462) == 11

    def test_freq_to_channel_5ghz(self):
        """Test frequency to channel conversion (5 GHz)."""
        # 5 GHz channel 36 = 5180 MHz
        assert NetworkManager._freq_to_channel(5180) == 36
        # Channel 149 = 5745 MHz
        assert NetworkManager._freq_to_channel(5745) == 149

    def test_wifi_string_escaping(self):
        """Test Wi-Fi string escaping."""
        # Test escaping
        escaped = QRCodeGenerator._escape_wifi_string('Test;SSID:With"Quotes')
        assert "\\;" in escaped
        assert "\\:" in escaped
        assert '\\"' in escaped


class TestInstallerService:
    """InstallerService state management tests."""

    @pytest.mark.asyncio
    async def test_update_provisioning(self):
        """Test updating provisioning state."""
        service = InstallerService()

        await service.update_provisioning(
            step=2,
            device_id="meter-001",
            status=StatusEnum.IN_PROGRESS,
        )

        assert service.provisioning_state.step == 2
        assert service.provisioning_state.device_id == "meter-001"
        assert service.provisioning_state.status == StatusEnum.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_reset_provisioning(self):
        """Test reset provisioning."""
        service = InstallerService()

        # Modify state
        await service.update_provisioning(
            step=3,
            device_id="meter-001",
        )

        # Reset
        await service.reset_provisioning()

        assert service.provisioning_state.step == 0
        assert service.provisioning_state.device_id is None


# Integration tests
class TestProvisioningIntegration:
    """End-to-end provisioning flow tests."""

    def test_full_provisioning_flow(self, client):
        """Test complete provisioning workflow."""
        # Step 1: Start provisioning
        response = client.get("/api/provisioning/status")
        assert response.json()["step"] == 0

        # Step 2: Advance through all steps
        for i in range(5):
            response = client.post("/api/provisioning/step/next")
            assert response.status_code == 200
            assert response.json()["step"] == i + 1

        # Step 3: Verify completion
        response = client.get("/api/provisioning/status")
        data = response.json()
        assert data["step"] == 5
        assert data["status"] == StatusEnum.COMPLETED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
