"""
QR Code Generator for MeterHub Device Provisioning

Generates QR codes for:
- Device credentials (device_id, society_id, panel_id)
- Wi-Fi provisioning (WiFi QR standard)
- Cloud endpoints (MQTT, HTTPS)
"""

import json
import logging
from io import BytesIO
from typing import Any

logger = logging.getLogger(__name__)

# Optional: depends on qrcode library
try:
    import qrcode
    from qrcode.image import svg

    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False
    logger.warning("qrcode library not available, using placeholder QR codes")


class QRCodeGenerator:
    """Generate QR codes for provisioning flows."""

    def __init__(self) -> None:
        """Initialize QR code generator."""
        self.version = 1
        self.error_correction = qrcode.constants.ERROR_CORRECT_M if HAS_QRCODE else None

    def generate_device_qr(
        self,
        device_id: str,
        society_id: str,
        panel_id: str,
        format: str = "svg",
    ) -> dict[str, Any]:
        """
        Generate QR code for device credentials.

        Args:
            device_id: Device identifier
            society_id: Society/building identifier
            panel_id: EnergyPanel identifier
            format: Output format ('svg', 'png', 'ascii')

        Returns:
            Dict with qr_code and data fields
        """
        device_data = {
            "device_id": device_id,
            "society_id": society_id,
            "panel_id": panel_id,
        }
        device_json = json.dumps(device_data, separators=(",", ":"))

        if not HAS_QRCODE:
            return {
                "qr_code": self._placeholder_svg(),
                "data": device_json,
                "format": format,
            }

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=self.error_correction,
                box_size=10,
                border=4,
            )
            qr.add_data(device_json)
            qr.make(fit=True)

            if format == "svg":
                img = qr.make_image(image_factory=svg.SvgPathImage)
            elif format == "ascii":
                return {
                    "qr_code": qr.get_matrix(),
                    "data": device_json,
                    "format": "ascii",
                }
            else:
                img = qr.make_image(fill_color="black", back_color="white")

            return {
                "qr_code": self._image_to_string(img),
                "data": device_json,
                "format": format,
            }

        except Exception as e:
            logger.error(f"QR generation failed: {e}")
            return {
                "qr_code": self._placeholder_svg(),
                "data": device_json,
                "format": format,
            }

    def generate_wifi_qr(
        self,
        ssid: str,
        password: str = "",
        security: str = "WPA",
        hidden: bool = False,
    ) -> dict[str, Any]:
        """
        Generate QR code for Wi-Fi provisioning (WiFi QR Standard).

        Format: WIFI:T:WPA;S:SSID;P:PASSWORD;H:true;;

        Args:
            ssid: Network name
            password: Network password
            security: Security type (WPA, WEP, nopass)
            hidden: Whether network is hidden

        Returns:
            Dict with qr_code and wifi_string fields
        """
        # Escape special characters
        ssid_safe = self._escape_wifi_string(ssid)
        password_safe = self._escape_wifi_string(password)

        # Build WiFi string
        wifi_string = f"WIFI:T:{security};S:{ssid_safe};P:{password_safe};"
        if hidden:
            wifi_string += "H:true;"
        wifi_string += ";"

        if not HAS_QRCODE:
            return {
                "qr_code": self._placeholder_svg(),
                "wifi_string": wifi_string,
                "ssid": ssid,
            }

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=self.error_correction,
                box_size=10,
                border=4,
            )
            qr.add_data(wifi_string)
            qr.make(fit=True)

            img = qr.make_image(image_factory=svg.SvgPathImage)

            return {
                "qr_code": self._image_to_string(img),
                "wifi_string": wifi_string,
                "ssid": ssid,
            }

        except Exception as e:
            logger.error(f"WiFi QR generation failed: {e}")
            return {
                "qr_code": self._placeholder_svg(),
                "wifi_string": wifi_string,
                "ssid": ssid,
            }

    def generate_provisioning_qr(
        self,
        device_id: str,
        mqtt_endpoint: str,
        https_endpoint: str,
    ) -> dict[str, Any]:
        """
        Generate QR code for cloud provisioning (endpoints + credentials).

        Args:
            device_id: Device identifier
            mqtt_endpoint: MQTT broker endpoint
            https_endpoint: HTTPS API endpoint

        Returns:
            Dict with qr_code and provisioning_data fields
        """
        provisioning_data = {
            "device_id": device_id,
            "mqtt_endpoint": mqtt_endpoint,
            "https_endpoint": https_endpoint,
        }
        prov_json = json.dumps(provisioning_data, separators=(",", ":"))

        if not HAS_QRCODE:
            return {
                "qr_code": self._placeholder_svg(),
                "provisioning_data": prov_json,
            }

        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=self.error_correction,
                box_size=10,
                border=4,
            )
            qr.add_data(prov_json)
            qr.make(fit=True)

            img = qr.make_image(image_factory=svg.SvgPathImage)

            return {
                "qr_code": self._image_to_string(img),
                "provisioning_data": prov_json,
            }

        except Exception as e:
            logger.error(f"Provisioning QR generation failed: {e}")
            return {
                "qr_code": self._placeholder_svg(),
                "provisioning_data": prov_json,
            }

    @staticmethod
    def _escape_wifi_string(s: str) -> str:
        """
        Escape special characters for WiFi QR string.

        WiFi QR format requires escaping: ; : \\ , " '
        """
        if not s:
            return ""

        # Order matters: escape backslash first
        s = s.replace("\\", "\\\\")
        s = s.replace(";", "\\;")
        s = s.replace(":", "\\:")
        s = s.replace(",", "\\,")
        s = s.replace('"', '\\"')
        s = s.replace("'", "\\'")

        return s

    @staticmethod
    def _placeholder_svg() -> str:
        """Return placeholder SVG for when qrcode is unavailable."""
        return """
        <svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
            <rect width="200" height="200" fill="white"/>
            <text x="100" y="100" text-anchor="middle" font-size="14" fill="black">
                QR Code (Placeholder)
            </text>
        </svg>
        """

    @staticmethod
    def _image_to_string(img: Any) -> str:
        """Serialize a qrcode image object to text."""
        buffer = BytesIO()
        img.save(buffer)
        return buffer.getvalue().decode("utf-8")
