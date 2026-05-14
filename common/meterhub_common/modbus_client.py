"""
Modbus RTU Client for MeterHub Acquisition

Implements Modbus RTU protocol with:
- Type-safe register reading
- Exponential backoff retry (3 attempts)
- Data type conversion (uint16, int16, uint32, float32, float64)
- Connection pooling and timeouts
- CRC16 validation (delegated to pymodbus library)
"""

import asyncio
import struct
from typing import Type, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import logging

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException, ConnectionException

from common.meterhub_common.meter_profile_schema import MeterProfile, DataType
from types import TracebackType

logger = logging.getLogger(__name__)


@dataclass
class ModbusRegisterValue:
    """Result of a single register read."""

    register_name: str
    raw_value: Any  # Raw bytes/value from register
    scaled_value: float  # After scaling and offset applied
    unit: str
    timestamp: datetime
    read_successful: bool
    retry_count: int = 0
    error_message: Optional[str] = None


class ModbusRTUClient:
    """
    Asyncio-based Modbus RTU client for meter communication.

    Supports:
    - Multiple data types (uint16, int16, uint32, float32, float64)
    - Exponential backoff retry on communication failures
    - Connection timeout management
    - Register caching (optional)
    """

    # Exponential backoff delays (milliseconds)
    BACKOFF_MS = [100, 500, 2000]

    def __init__(
        self,
        device: str,  # e.g., "/dev/ttyUSB0"
        meter_profile: MeterProfile,
        slave_id: int = 1,
        enable_cache: bool = False,
        cache_ttl_seconds: int = 30,
    ) -> None:
        """
        Initialize Modbus RTU client.

        Args:
            device: Serial device path
            meter_profile: MeterProfile with register definitions
            slave_id: Modbus slave ID (1-247)
            enable_cache: Cache register values
            cache_ttl_seconds: Cache TTL in seconds
        """
        self.device = device
        self.meter_profile = meter_profile
        self.slave_id = slave_id
        self.enable_cache = enable_cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache: Dict[str, tuple] = {}  # {register_name: (value, timestamp)}

        # Serial client connection
        self.client = AsyncModbusSerialClient(
            port=device,
            baudrate=meter_profile.baud_rate,
            bytesize=meter_profile.data_bits,
            parity=self._parse_parity(meter_profile.parity),
            stopbits=meter_profile.stop_bits,
            timeout=meter_profile.timeout_ms / 1000.0,
            retries=0,  # We handle retries manually
        )

        self.connected = False
        self.last_error: Optional[str] = None
        self.connection_failed_count = 0

    @staticmethod
    def _parse_parity(parity_str: str) -> str:
        """Convert parity string to pymodbus format."""
        parity_map = {"even": "E", "odd": "O", "none": "N"}
        return parity_map.get(parity_str.lower(), "E")

    async def connect(self) -> bool:
        """Establish connection to Modbus device."""
        try:
            self.connected = await self.client.connect()
            if self.connected:
                self.connection_failed_count = 0
                logger.info(
                    f"Modbus connected: {self.device} (slave {self.slave_id})"
                )
            else:
                self.connection_failed_count += 1
                self.last_error = "Failed to connect to Modbus device"
                logger.error(self.last_error)
            return self.connected
        except Exception as e:
            self.connection_failed_count += 1
            self.last_error = str(e)
            logger.error(f"Connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Close connection."""
        if self.client:
            self.client.close()
            self.connected = False
            logger.info(f"Modbus disconnected: {self.device}")

    async def read_register(
        self, register_name: str, force_refresh: bool = False
    ) -> ModbusRegisterValue:
        """
        Read a single register by name (with retry and scaling).

        Args:
            register_name: Name of register (must exist in meter_profile.registers)
            force_refresh: Bypass cache

        Returns:
            ModbusRegisterValue with scaled value and metadata
        """
        # Check cache
        if not force_refresh and self.enable_cache:
            cached = self._check_cache(register_name)
            if cached:
                return cached

        # Get register definition
        if register_name not in self.meter_profile.registers:
            return ModbusRegisterValue(
                register_name=register_name,
                raw_value=None,
                scaled_value=0.0,
                unit="",
                timestamp=datetime.utcnow(),
                read_successful=False,
                error_message=f"Register '{register_name}' not found in profile",
            )

        register_def = self.meter_profile.registers[register_name]

        # Read with retry
        result = await self._read_with_retry(register_def)

        # Cache result
        if self.enable_cache and result.read_successful:
            self.cache[register_name] = (result, datetime.utcnow())

        return result

    async def read_all_registers(
        self, force_refresh: bool = False
    ) -> Dict[str, ModbusRegisterValue]:
        """
        Read all registers defined in the meter profile.

        Returns:
            Dict mapping register_name -> ModbusRegisterValue
        """
        results = {}
        for reg_name in self.meter_profile.registers.keys():
            result = await self.read_register(reg_name, force_refresh)
            results[reg_name] = result
        return results

    async def _read_with_retry(
        self, register_def
    ) -> ModbusRegisterValue:
        """Read register with exponential backoff retry."""
        max_retries = len(self.BACKOFF_MS)
        last_error = None

        for attempt in range(max_retries):
            try:
                # Ensure connected
                if not self.connected:
                    await self.connect()
                    if not self.connected:
                        raise ConnectionException("Cannot connect to Modbus device")

                # Read from device
                raw_value = await self._read_raw_register(register_def)

                # Convert to scaled value
                scaled_value = self._apply_scaling(raw_value, register_def)

                return ModbusRegisterValue(
                    register_name=register_def.name,
                    raw_value=raw_value,
                    scaled_value=scaled_value,
                    unit=register_def.unit,
                    timestamp=datetime.utcnow(),
                    read_successful=True,
                    retry_count=attempt,
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Retry {attempt + 1}/{max_retries} for {register_def.name}: {e}"
                )

                # Exponential backoff
                if attempt < max_retries - 1:
                    await asyncio.sleep(self.BACKOFF_MS[attempt] / 1000.0)

        # All retries failed
        self.connection_failed_count += 1
        self.last_error = last_error
        return ModbusRegisterValue(
            register_name=register_def.name,
            raw_value=None,
            scaled_value=0.0,
            unit=register_def.unit,
            timestamp=datetime.utcnow(),
            read_successful=False,
            retry_count=max_retries,
            error_message=last_error,
        )

    async def _read_raw_register(self, register_def) -> Any:
        """Read raw register value (handle multi-register types)."""
        address = register_def.address
        data_type = register_def.data_type

        if data_type == DataType.UINT16 or data_type == DataType.INT16:
            # Single 16-bit register
            result = await self.client.read_holding_registers(address, 1, self.slave_id)
            if result.isError():
                raise ModbusException(f"Failed to read register {address}")
            return result.registers[0]

        elif data_type == DataType.UINT32 or data_type == DataType.INT32:
            # Two 16-bit registers (big-endian)
            result = await self.client.read_holding_registers(address, 2, self.slave_id)
            if result.isError():
                raise ModbusException(f"Failed to read registers {address}-{address + 1}")
            high = result.registers[0]
            low = result.registers[1]
            return (high << 16) | low

        elif data_type == DataType.FLOAT32:
            # Two 16-bit registers as IEEE 754 float
            result = await self.client.read_holding_registers(address, 2, self.slave_id)
            if result.isError():
                raise ModbusException(f"Failed to read float32 at {address}")
            high = result.registers[0]
            low = result.registers[1]
            # Combine and interpret as float
            combined = struct.pack(">HH", high, low)
            return struct.unpack(">f", combined)[0]

        elif data_type == DataType.FLOAT64:
            # Four 16-bit registers as IEEE 754 double
            result = await self.client.read_holding_registers(address, 4, self.slave_id)
            if result.isError():
                raise ModbusException(f"Failed to read float64 at {address}")
            combined = struct.pack(
                ">HHHH",
                result.registers[0],
                result.registers[1],
                result.registers[2],
                result.registers[3],
            )
            return struct.unpack(">d", combined)[0]

        else:
            raise ValueError(f"Unsupported data type: {data_type}")

    @staticmethod
    def _apply_scaling(raw_value: Any, register_def) -> float:
        """Apply scale and offset to raw value."""
        if raw_value is None:
            return 0.0

        # Handle signed integers
        if register_def.data_type == DataType.INT16:
            if raw_value > 32767:
                raw_value = raw_value - 65536

        elif register_def.data_type == DataType.INT32:
            if raw_value > 2147483647:
                raw_value = raw_value - 4294967296

        # Apply scaling and offset
        scaled = (raw_value * register_def.scale) + register_def.offset
        return float(scaled)

    def _check_cache(self, register_name: str) -> Optional[ModbusRegisterValue]:
        """Check if cached value is fresh."""
        if register_name not in self.cache:
            return None

        cached_value, cached_time = self.cache[register_name]
        age = (datetime.utcnow() - cached_time).total_seconds()

        if age < self.cache_ttl_seconds:
            return cached_value
        else:
            del self.cache[register_name]
            return None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[TracebackType]) -> None:
        """Async context manager exit."""
        await self.disconnect()
