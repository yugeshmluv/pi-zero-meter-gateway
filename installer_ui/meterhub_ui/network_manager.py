"""
Network Manager for Wi-Fi Configuration

Handles:
- Wi-Fi network scanning
- Wi-Fi connection management
- Network status monitoring
- DNS/DHCP configuration
- Static IP setup
"""

import logging
import subprocess
from typing import Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class WiFiNetwork:
    """Scanned Wi-Fi network information."""

    ssid: str
    signal_strength: int  # 0-100
    security: str  # WPA2, WPA, Open, WEP
    channel: int
    frequency_ghz: str  # 2.4 or 5
    bssid: str | None = None  # MAC address


@dataclass
class NetworkConfig:
    """Network configuration."""

    hostname: str
    wi_fi_ssid: str
    wi_fi_psk: str
    use_dhcp: bool = True
    static_ip: str | None = None
    gateway: str | None = None
    dns_servers: list[str] = field(default_factory=lambda: ["8.8.8.8", "8.8.4.4"])
    ntp_servers: list[str] = field(default_factory=lambda: ["pool.ntp.org"])

    def __post_init__(self) -> None:
        if self.dns_servers is None:
            self.dns_servers = ["8.8.8.8", "8.8.4.4"]
        if self.ntp_servers is None:
            self.ntp_servers = ["pool.ntp.org"]


class NetworkManager:
    """Manage network configuration for MeterHub device."""

    def __init__(self, use_nmcli: bool = True) -> None:
        """
        Initialize network manager.

        Args:
            use_nmcli: Use NetworkManager CLI (nmcli) if available,
                      else fall back to wpa_cli
        """
        self.use_nmcli = use_nmcli
        self.config_dir = Path("/etc/NetworkManager/conf.d")
        self.wpa_config_file = Path("/etc/wpa_supplicant/wpa_supplicant.conf")

    async def scan_networks(self) -> list[WiFiNetwork]:
        """
        Scan for available Wi-Fi networks.

        Returns:
            List of discovered networks
        """
        try:
            if self.use_nmcli:
                return await self._scan_nmcli()
            else:
                return await self._scan_iwlist()
        except Exception as e:
            logger.error(f"Network scan failed: {e}")
            return []

    async def _scan_nmcli(self) -> list[WiFiNetwork]:
        """Scan using nmcli (NetworkManager CLI)."""
        try:
            # List available networks (JSON output)
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,FREQ,BSSID", "dev", "wifi", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            networks = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split(":")
                if len(parts) >= 5:
                    ssid = parts[0].strip()
                    signal = int(parts[1].strip() or 0)
                    security = parts[2].strip() or "Open"
                    freq_str = parts[3].strip()
                    bssid = parts[4].strip() if len(parts) > 4 else None

                    # Determine frequency band
                    freq_ghz = "2.4" if int(freq_str or 2400) < 4000 else "5"

                    networks.append(
                        WiFiNetwork(
                            ssid=ssid,
                            signal_strength=signal,
                            security=security,
                            channel=self._freq_to_channel(int(freq_str or 2400)),
                            frequency_ghz=freq_ghz,
                            bssid=bssid,
                        )
                    )

            return networks

        except Exception as e:
            logger.error(f"nmcli scan failed: {e}")
            return []

    async def _scan_iwlist(self) -> list[WiFiNetwork]:
        """Scan using iwlist (fallback for systems without NetworkManager)."""
        try:
            result = subprocess.run(
                ["iwlist", "wlan0", "scan"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            networks = []
            # Parse iwlist output (line-by-line parsing)
            lines = result.stdout.split("\n")

            current_network: dict[str, Any] = {}
            for line in lines:
                line = line.strip()

                if "ESSID" in line and ":" in line:
                    essid = line.split(":", 1)[1].strip().strip('"')
                    if current_network:
                        networks.append(self._build_wifi_network(current_network))
                    current_network = {"ssid": essid}

                elif "Signal level" in line:
                    signal_str = line.split("=")[1].strip().split()[0]
                    signal = min(100, abs(int(signal_str)))
                    current_network["signal_strength"] = signal

                elif "Frequency" in line:
                    freq_str = line.split(":")[1].strip().split()[0]
                    current_network["frequency"] = float(freq_str) * 1000

            if current_network:
                networks.append(self._build_wifi_network(current_network))

            return networks

        except Exception as e:
            logger.error(f"iwlist scan failed: {e}")
            return []

    async def connect(self, ssid: str, psk: str) -> bool:
        """
        Connect to Wi-Fi network.

        Args:
            ssid: Network name
            psk: Pre-shared key (password)

        Returns:
            True if connection successful
        """
        try:
            if self.use_nmcli:
                return await self._connect_nmcli(ssid, psk)
            else:
                return await self._connect_wpa(ssid, psk)
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    async def _connect_nmcli(self, ssid: str, psk: str) -> bool:
        """Connect using nmcli."""
        try:
            # Delete existing connection (if any)
            subprocess.run(
                ["nmcli", "connection", "delete", ssid],
                capture_output=True,
                timeout=5,
            )

            # Create new connection
            result = subprocess.run(
                [
                    "nmcli",
                    "device",
                    "wifi",
                    "connect",
                    ssid,
                    "password",
                    psk,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info(f"Connected to {ssid}")
                return True
            else:
                logger.error(f"nmcli connection failed: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"nmcli connect error: {e}")
            return False

    async def _connect_wpa(self, ssid: str, psk: str) -> bool:
        """Connect using wpa_cli."""
        try:
            result = subprocess.run(
                [
                    "wpa_cli",
                    "-i",
                    "wlan0",
                    "add_network",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            network_id = result.stdout.strip()

            # Set SSID
            subprocess.run(
                ["wpa_cli", "-i", "wlan0", "set_network", network_id, "ssid", f'"{ssid}"'],
                timeout=5,
            )

            # Set PSK
            subprocess.run(
                ["wpa_cli", "-i", "wlan0", "set_network", network_id, "psk", f'"{psk}"'],
                timeout=5,
            )

            # Enable network
            subprocess.run(
                ["wpa_cli", "-i", "wlan0", "enable_network", network_id],
                timeout=5,
            )

            # Save config
            subprocess.run(
                ["wpa_cli", "-i", "wlan0", "save_config"],
                timeout=5,
            )

            logger.info(f"Connected to {ssid}")
            return True

        except Exception as e:
            logger.error(f"wpa_cli connect error: {e}")
            return False

    async def get_status(self) -> dict[str, Any]:
        """Get current network status."""
        try:
            if self.use_nmcli:
                return await self._status_nmcli()
            else:
                return await self._status_ip()
        except Exception as e:
            logger.error(f"Failed to get network status: {e}")
            return {"status": "unknown"}

    async def _status_nmcli(self) -> dict[str, Any]:
        """Get status using nmcli."""
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "IP4.ADDRESS,IP4.GATEWAY,IP4.DNS", "device", "show", "wlan0"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            ip_address = None
            gateway = None
            dns = []

            for line in result.stdout.split("\n"):
                if "IP4.ADDRESS" in line:
                    ip_address = line.split(":")[-1].strip()
                elif "IP4.GATEWAY" in line:
                    gateway = line.split(":")[-1].strip()
                elif "IP4.DNS" in line:
                    dns.append(line.split(":")[-1].strip())

            return {
                "status": "connected",
                "ip_address": ip_address,
                "gateway": gateway,
                "dns": dns,
            }

        except Exception as e:
            logger.error(f"nmcli status failed: {e}")
            return {"status": "unknown"}

    async def _status_ip(self) -> dict[str, Any]:
        """Get status using ip command."""
        try:
            result = subprocess.run(
                ["ip", "addr", "show", "wlan0"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            ip_address = None
            for line in result.stdout.split("\n"):
                if "inet " in line:
                    ip_address = line.strip().split()[1]
                    break

            return {
                "status": "connected" if ip_address else "disconnected",
                "ip_address": ip_address,
            }

        except Exception as e:
            logger.error(f"ip status failed: {e}")
            return {"status": "unknown"}

    @staticmethod
    def _freq_to_channel(freq_mhz: int) -> int:
        """Convert frequency (MHz) to Wi-Fi channel number."""
        if freq_mhz < 4000:  # 2.4 GHz band
            return (freq_mhz - 2407) // 5
        else:  # 5 GHz band
            return (freq_mhz - 5000) // 5

    @staticmethod
    def _build_wifi_network(data: dict[str, Any]) -> WiFiNetwork:
        """Build WiFiNetwork from parsed data."""
        freq_ghz = "2.4" if data.get("frequency", 2400) < 4000 else "5"
        return WiFiNetwork(
            ssid=data.get("ssid", "Unknown"),
            signal_strength=data.get("signal_strength", 0),
            security=data.get("security", "Unknown"),
            channel=NetworkManager._freq_to_channel(int(data.get("frequency", 2400))),
            frequency_ghz=freq_ghz,
        )
