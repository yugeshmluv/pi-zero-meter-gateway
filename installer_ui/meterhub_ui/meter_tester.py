"""
Meter Connectivity Tester

Tests Modbus RTU meter connectivity during provisioning.
Used in installer UI for diagnostics and verification.
"""

import logging
from typing import Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MeterTestResult:
    """Result of meter connectivity test."""

    device: str
    connected: bool
    registers_read: int
    registers_failed: int
    test_duration_ms: float
    timestamp: datetime
    error_message: str | None = None
    sample_readings: dict[str, Any] | None = None
    modbus_timeout_ms: int = 5000


class MeterTester:
    """Test meter connectivity using Modbus RTU."""

    def __init__(self, modbus_client: Any | None = None) -> None:
        """
        Initialize meter tester.

        Args:
            modbus_client: ModbusRTUClient instance (optional, for testing)
        """
        self.modbus_client = modbus_client

    async def test_connectivity(
        self,
        device: str,
        meter_profile_path: str,
        slave_id: int = 1,
    ) -> MeterTestResult:
        """
        Test meter connectivity and read sample registers.

        Args:
            device: Serial device path (e.g., /dev/ttyUSB0)
            meter_profile_path: Path to meter profile YAML
            slave_id: Modbus slave ID

        Returns:
            MeterTestResult with test outcome
        """
        start_time = datetime.utcnow()
        start_ms = datetime.utcnow().timestamp() * 1000

        try:
            # Import common modules
            from common.meterhub_common import MeterProfile, ModbusRTUClient

            # Load meter profile
            profile = MeterProfile.from_yaml(meter_profile_path)
            logger.info(f"Loaded profile: {profile.meter_type}")

            # Create client
            client = ModbusRTUClient(
                device=device,
                meter_profile=profile,
                slave_id=slave_id,
            )

            # Connect
            await client.connect()
            if not client.connected:
                end_ms = datetime.utcnow().timestamp() * 1000
                return MeterTestResult(
                    device=device,
                    connected=False,
                    registers_read=0,
                    registers_failed=0,
                    test_duration_ms=end_ms - start_ms,
                    timestamp=start_time,
                    error_message="Failed to connect to device",
                )

            # Read sample registers
            sample_readings = {}
            registers_read = 0
            registers_failed = 0

            # Try to read key registers
            key_registers = [
                "voltage_l1",
                "current_l1",
                "instant_kw",
                "totalizer_kwh",
                "frequency_hz",
            ]

            for reg_name in key_registers:
                try:
                    result = await client.read_register(reg_name, force_refresh=True)
                    if result.read_successful:
                        sample_readings[reg_name] = {
                            "raw_value": result.raw_value,
                            "scaled_value": result.scaled_value,
                            "unit": result.unit,
                        }
                        registers_read += 1
                        logger.info(f"✓ {reg_name}: {result.scaled_value} {result.unit}")
                    else:
                        registers_failed += 1
                        logger.warning(
                            f"✗ {reg_name}: {result.error_message} "
                            f"(retries: {result.retry_count})"
                        )
                except Exception as e:
                    registers_failed += 1
                    logger.error(f"✗ {reg_name}: {e}")

            # Disconnect
            await client.disconnect()

            end_ms = datetime.utcnow().timestamp() * 1000

            # Determine success (at least 3 registers read)
            success = registers_read >= 3

            return MeterTestResult(
                device=device,
                connected=success,
                registers_read=registers_read,
                registers_failed=registers_failed,
                test_duration_ms=end_ms - start_ms,
                timestamp=start_time,
                error_message=None if success else f"Only {registers_read}/5 registers read",
                sample_readings=sample_readings,
            )

        except ImportError as e:
            logger.error(f"Failed to import common modules: {e}")
            end_ms = datetime.utcnow().timestamp() * 1000
            return MeterTestResult(
                device=device,
                connected=False,
                registers_read=0,
                registers_failed=0,
                test_duration_ms=end_ms - start_ms,
                timestamp=start_time,
                error_message=f"Import error: {e}",
            )

        except Exception as e:
            logger.error(f"Test failed: {e}")
            end_ms = datetime.utcnow().timestamp() * 1000
            return MeterTestResult(
                device=device,
                connected=False,
                registers_read=0,
                registers_failed=0,
                test_duration_ms=end_ms - start_ms,
                timestamp=start_time,
                error_message=str(e),
            )

    async def test_available_devices(self) -> dict[str, dict[str, Any]]:
        """
        Test all available serial devices.

        Returns:
            Dict mapping device paths to test results
        """
        import glob

        results = {}
        possible_devices = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyAMA*")

        for device in possible_devices:
            logger.info(f"Testing device: {device}")
            result = await self.test_connectivity(
                device=device,
                meter_profile_path="/etc/meterhub/profiles/schneider-em6400.yaml",
            )
            results[device] = {
                "connected": result.connected,
                "registers_read": result.registers_read,
                "test_duration_ms": result.test_duration_ms,
                "error": result.error_message,
            }

        return results

    async def test_baud_rates(
        self,
        device: str,
        meter_profile_path: str,
        baud_rates: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        """
        Test different baud rates to find correct configuration.

        Args:
            device: Serial device path
            meter_profile_path: Path to meter profile YAML
            baud_rates: List of baud rates to test (default: common rates)

        Returns:
            Dict mapping baud rates to test results
        """
        if baud_rates is None:
            baud_rates = [1200, 2400, 4800, 9600, 19200, 38400]

        results = {}

        for baud_rate in baud_rates:
            logger.info(f"Testing baud rate: {baud_rate}")

            try:
                from common.meterhub_common import MeterProfile, ModbusRTUClient

                # Load profile and override baud rate for testing
                profile = MeterProfile.from_yaml(meter_profile_path)
                profile.baud_rate = baud_rate

                # Create temporary client with test baud rate
                client = ModbusRTUClient(
                    device=device,
                    meter_profile=profile,
                    slave_id=1,
                )

                # Try to connect and read one register
                await client.connect()
                if not client.connected:
                    results[baud_rate] = {
                        "baud_rate": baud_rate,
                        "success": False,
                        "error": "Failed to connect at this baud rate",
                    }
                    continue

                # Try reading a simple register
                result = await client.read_register("voltage_l1", force_refresh=True)
                await client.disconnect()

                success = result.read_successful
                results[baud_rate] = {
                    "baud_rate": baud_rate,
                    "success": success,
                    "error": None if success else result.error_message,
                    "raw_value": result.raw_value if success else None,
                }

                if success:
                    logger.info(f"✓ Baud rate {baud_rate} working")

            except Exception as e:
                logger.error(f"Baud rate {baud_rate} test failed: {e}")
                results[baud_rate] = {
                    "baud_rate": baud_rate,
                    "success": False,
                    "error": str(e),
                }

        return results

    async def validate_modbus_slave_id(
        self,
        device: str,
        meter_profile_path: str,
        slave_ids: list[int] | None = None,
    ) -> dict[int, dict[str, Any]]:
        """
        Find correct Modbus slave ID by probing.

        Args:
            device: Serial device path
            meter_profile_path: Path to meter profile YAML
            slave_ids: List of slave IDs to probe (default: 1-32)

        Returns:
            Dict mapping slave IDs to test results
        """
        if slave_ids is None:
            slave_ids = list(range(1, 33))

        results = {}

        for slave_id in slave_ids:
            logger.info(f"Testing slave ID: {slave_id}")

            result = await self.test_connectivity(
                device=device,
                meter_profile_path=meter_profile_path,
                slave_id=slave_id,
            )

            results[slave_id] = {
                "slave_id": slave_id,
                "connected": result.connected,
                "registers_read": result.registers_read,
                "error": result.error_message,
            }

            if result.connected:
                logger.info(f"✓ Found meter at slave ID {slave_id}")
                break  # Stop on first successful connection

        return results
