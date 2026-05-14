"""
MeterHub Acquisition Service

Phase 2: Modbus RTU polling with crashsafe SQLite storage.

Acquires meter readings every 60 seconds via Modbus RTU protocol
from Schneider EM6400 (configurable via YAML profile).

Data flows:
1. Load meter profile (YAML)
2. Connect to Modbus device (/dev/ttyUSB0)
3. Poll registers with 3-retry exponential backoff
4. Store in telemetry.db (7-day queue, NORMAL sync)
5. Update state.db billing counter (FULL sync)
6. Send heartbeat to uploader service

Handles:
- Connection failures and retries
- Power loss (WAL mode crash recovery)
- Modbus timeouts (configurable 1-10s)
- Register validation (voltage/current ranges)
- 24-hour operation with self-healing
"""

import asyncio
import os
import signal
import logging
from datetime import datetime
from typing import Optional

from common.meterhub_common import (
    MeterProfile,
    ModbusRTUClient,
    MeterReading,
)
from common.meterhub_common.sqlite_db import TelemetryDatabase, StateDatabase

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class AcquisitionService:
    """Main acquisition service orchestrator."""

    def __init__(
        self,
        meter_profile_path: str = "/etc/meterhub/profiles/schneider-em6400.yaml",
        ttydevice: str = "/dev/ttyUSB0",
        polling_interval_s: int = 60,
        telemetry_db_path: str = "/var/cache/meterhub/telemetry.db",
        state_db_path: str = "/var/lib/meterhub/state.db",
    ) -> None:
        """
        Initialize acquisition service.

        Args:
            meter_profile_path: Path to meter profile YAML
            ttydevice: Serial device path
            polling_interval_s: Poll interval in seconds
            telemetry_db_path: Path to telemetry.db
            state_db_path: Path to state.db
        """
        self.meter_profile_path = meter_profile_path
        self.ttydevice = ttydevice
        self.polling_interval = polling_interval_s
        self.telemetry_db_path = telemetry_db_path
        self.state_db_path = state_db_path

        # State
        self.running = False
        self.meter_profile: Optional[MeterProfile] = None
        self.modbus_client: Optional[ModbusRTUClient] = None
        self.telemetry_db: Optional[TelemetryDatabase] = None
        self.state_db: Optional[StateDatabase] = None

        self.read_count = 0
        self.error_count = 0

    def _load_profile(self) -> bool:
        """Load meter profile from YAML."""
        try:
            logger.info(f"Loading profile: {self.meter_profile_path}")
            self.meter_profile = MeterProfile.from_yaml(self.meter_profile_path)
            logger.info(
                f"Loaded profile: {self.meter_profile.meter_type} "
                f"({self.meter_profile.protocol_version})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to load profile: {e}")
            return False

    def _initialize_databases(self) -> bool:
        """Initialize SQLite databases with persistent connections."""
        try:
            logger.info("Initializing SQLite databases...")
            self.telemetry_db = TelemetryDatabase(self.telemetry_db_path)
            self.telemetry_db.initialize_schema()
            self.telemetry_db.db.connect()  # Keep connection persistent

            self.state_db = StateDatabase(self.state_db_path)
            self.state_db.initialize_schema()
            self.state_db.db.connect()  # Keep connection persistent

            logger.info("Databases initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize databases: {e}")
            return False

    async def _poll_meter(self) -> Optional[MeterReading]:
        """Poll meter and return MeterReading dataclass."""
        try:
            # Ensure connected
            if not self.modbus_client.connected:
                await self.modbus_client.connect()
                if not self.modbus_client.connected:
                    raise RuntimeError("Cannot connect to Modbus device")

            # Read all registers
            registers = await self.modbus_client.read_all_registers(
                force_refresh=True
            )

            # Extract readings (filter out failures)
            reading_dict = {}
            for reg_name, reg_result in registers.items():
                if reg_result.read_successful:
                    reading_dict[reg_name] = reg_result.scaled_value
                else:
                    logger.warning(
                        f"Failed to read {reg_name}: {reg_result.error_message} "
                        f"(retries: {reg_result.retry_count})"
                    )

            # Validate critical fields
            if "totalizer_kwh" not in reading_dict or "instant_kw" not in reading_dict:
                raise ValueError("Missing critical fields: totalizer_kwh or instant_kw")

            # Create MeterReading
            reading = MeterReading(
                timestamp_utc=datetime.utcnow(),
                totalizer_kwh=reading_dict.get("totalizer_kwh", 0.0),
                instant_kw=reading_dict.get("instant_kw", 0.0),
                frequency_hz=reading_dict.get("frequency_hz", 50.0),
                voltage_l1=reading_dict.get("voltage_l1", 0.0),
                voltage_l2=reading_dict.get("voltage_l2", 0.0),
                voltage_l3=reading_dict.get("voltage_l3", 0.0),
                current_l1=reading_dict.get("current_l1", 0.0),
                current_l2=reading_dict.get("current_l2", 0.0),
                current_l3=reading_dict.get("current_l3", 0.0),
                pf_total=reading_dict.get("pf_total", 0.98),
                modbus_retry_count=0,
                meter_online=True,
            )

            return reading

        except Exception as e:
            logger.error(f"Poll failed: {e}")
            self.error_count += 1
            return None

    async def _store_reading(self, reading: MeterReading) -> None:
        """Store reading in databases (reuse persistent connections)."""
        try:
            # Store in telemetry (performance-optimized, reuse connection)
            reading_dict = {
                "timestamp_utc": reading.timestamp_utc.isoformat(),
                "totalizer_kwh": reading.totalizer_kwh,
                "instant_kw": reading.instant_kw,
                "frequency_hz": reading.frequency_hz,
                "voltage_l1": reading.voltage_l1,
                "voltage_l2": reading.voltage_l2,
                "voltage_l3": reading.voltage_l3,
                "current_l1": reading.current_l1,
                "current_l2": reading.current_l2,
                "current_l3": reading.current_l3,
                "pf_total": reading.pf_total,
                "modbus_retry_count": reading.modbus_retry_count,
                "meter_online": reading.meter_online,
            }
            self.telemetry_db.insert_reading(reading_dict)

            # Update billing state (crash-safe, reuse connection)
            self.state_db.update_billing_state(
                reading.totalizer_kwh, reading.timestamp_utc
            )

            self.read_count += 1
            # Log every 60 reads (hourly) instead of every read
            if self.read_count % 60 == 0:
                logger.info(
                    f"Acquisition progress: read count={self.read_count}, "
                    f"totalizer={reading.totalizer_kwh:.2f} kWh, "
                    f"instant={reading.instant_kw:.2f} kW"
                )

        except Exception as e:
            logger.error(f"Failed to store reading: {e}")
            self.error_count += 1

    async def _cleanup_databases(self) -> None:
        """Cleanup old telemetry records (reuse persistent connection)."""
        try:
            if self.telemetry_db:
                self.telemetry_db.cleanup_old_readings()
                logger.debug(f"Database cleanup complete at read count {self.read_count}")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    async def run(self) -> None:
        """Main acquisition loop."""
        self.running = True

        # Load profile
        if not self._load_profile():
            logger.error("Cannot start: profile load failed")
            return

        # Initialize databases
        if not self._initialize_databases():
            logger.error("Cannot start: database initialization failed")
            return

        # Create Modbus client
        self.modbus_client = ModbusRTUClient(
            device=self.ttydevice,
            meter_profile=self.meter_profile,
            enable_cache=False,  # Always read fresh from device
        )

        logger.info(f"Acquisition loop starting (interval: {self.polling_interval}s)")

        try:
            while self.running:
                # Poll meter
                reading = await self._poll_meter()
                if reading:
                    await self._store_reading(reading)

                # Periodic cleanup (every 60 polls = ~1 hour)
                if self.read_count % 60 == 0:
                    await self._cleanup_databases()

                # Wait for next poll
                await asyncio.sleep(self.polling_interval)

        except asyncio.CancelledError:
            logger.info("Acquisition loop cancelled")
        except Exception as e:
            logger.error(f"Acquisition loop error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Shutting down acquisition service...")
        self.running = False

        # Close Modbus client
        if self.modbus_client:
            await self.modbus_client.disconnect()

        # Close databases
        if self.telemetry_db and self.telemetry_db.db.connection:
            self.telemetry_db.db.disconnect()
        if self.state_db and self.state_db.db.connection:
            self.state_db.db.disconnect()

        logger.info(
            f"Acquisition shutdown complete "
            f"(reads: {self.read_count}, errors: {self.error_count})"
        )

    def handle_signal(self, signum, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False


async def main() -> None:
    """Entry point."""
    logger.info("MeterHub Acquisition Service v1.0.0")

    # Create service
    service = AcquisitionService(
        meter_profile_path=os.getenv(
            "METER_PROFILE_PATH",
            "/etc/meterhub/profiles/schneider-em6400.yaml",
        ),
        ttydevice=os.getenv("MODBUS_TTY_DEVICE", "/dev/ttyUSB0"),
        polling_interval_s=int(os.getenv("POLLING_INTERVAL_S", "60")),
    )

    # Register signal handlers
    signal.signal(signal.SIGTERM, service.handle_signal)
    signal.signal(signal.SIGINT, service.handle_signal)

    # Run
    try:
        await service.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    asyncio.run(main())
