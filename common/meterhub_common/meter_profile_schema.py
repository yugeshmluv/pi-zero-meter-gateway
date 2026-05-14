"""
Meter Profile Schema and Validator

Defines the YAML schema for Modbus meter profiles and validates profile files.
Supports Schneider EM6400, ABB, Siemens, and other 3-phase energy meter profiles.
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import yaml


class DataType(Enum):
    """Supported Modbus data types."""

    UINT16 = "uint16"  # 16-bit unsigned
    INT16 = "int16"  # 16-bit signed
    UINT32 = "uint32"  # 32-bit unsigned (2 registers, big-endian)
    INT32 = "int32"  # 32-bit signed
    FLOAT32 = "float32"  # 32-bit IEEE 754 (2 registers)
    FLOAT64 = "float64"  # 64-bit IEEE 754 (4 registers)


@dataclass
class ModbusRegister:
    """Single Modbus register mapping."""

    name: str  # Field name (e.g., "totalizer_kwh")
    address: int  # Starting register address (0-based)
    data_type: DataType  # Data type (uint16, float32, etc.)
    scale: float = 1.0  # Scale factor (raw_value * scale)
    offset: float = 0.0  # Offset to add after scaling
    unit: str = ""  # Unit of value (kWh, W, V, A, Hz, %)
    description: str = ""  # Human-readable description
    writable: bool = False  # Is this register writable?
    read_only: bool = True  # Is this register read-only?

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "address": self.address,
            "data_type": self.data_type.value,
            "scale": self.scale,
            "offset": self.offset,
            "unit": self.unit,
            "description": self.description,
            "writable": self.writable,
            "read_only": self.read_only,
        }


@dataclass
class MeterProfile:
    """Complete Modbus meter profile."""

    meter_type: str  # e.g., "Schneider EM6400", "ABB PowerOne"
    manufacturer: str  # Manufacturer name
    protocol_version: str  # Modbus RTU version (1.1, 2.0, etc.)
    baud_rate: int = 9600  # Serial baud rate
    parity: str = "even"  # odd, even, none
    stop_bits: int = 1  # 1 or 2
    data_bits: int = 8  # 7 or 8
    timeout_ms: int = 1000  # Modbus timeout
    registers: dict[str, ModbusRegister] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize registers dict if not provided."""
        if self.registers is None:
            self.registers = {}

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "MeterProfile":
        """Load profile from YAML file."""
        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty YAML file: {yaml_path}")

        # Validate required fields
        required = ["meter_type", "manufacturer", "protocol_version"]
        for required_field in required:
            if required_field not in data:
                raise ValueError(f"Missing required field '{required_field}' in {yaml_path}")

        # Parse registers
        registers = {}
        if "registers" in data:
            for reg_data in data["registers"]:
                name = reg_data.get("name")
                if not name:
                    raise ValueError("Register missing 'name' field")

                data_type_str = reg_data.get("data_type", "uint16")
                try:
                    data_type = DataType(data_type_str)
                except ValueError:
                    raise ValueError(f"Unknown data_type '{data_type_str}' for register '{name}'")

                reg = ModbusRegister(
                    name=name,
                    address=reg_data.get("address"),
                    data_type=data_type,
                    scale=reg_data.get("scale", 1.0),
                    offset=reg_data.get("offset", 0.0),
                    unit=reg_data.get("unit", ""),
                    description=reg_data.get("description", ""),
                    writable=reg_data.get("writable", False),
                    read_only=reg_data.get("read_only", True),
                )
                registers[name] = reg

        return cls(
            meter_type=data.get("meter_type"),
            manufacturer=data.get("manufacturer"),
            protocol_version=data.get("protocol_version"),
            baud_rate=data.get("baud_rate", 9600),
            parity=data.get("parity", "even"),
            stop_bits=data.get("stop_bits", 1),
            data_bits=data.get("data_bits", 8),
            timeout_ms=data.get("timeout_ms", 1000),
            registers=registers,
        )

    def to_yaml(self, yaml_path: str) -> None:
        """Save profile to YAML file."""
        data = {
            "meter_type": self.meter_type,
            "manufacturer": self.manufacturer,
            "protocol_version": self.protocol_version,
            "baud_rate": self.baud_rate,
            "parity": self.parity,
            "stop_bits": self.stop_bits,
            "data_bits": self.data_bits,
            "timeout_ms": self.timeout_ms,
            "registers": [reg.to_dict() for reg in self.registers.values()],
        }
        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# Helper function to load all profiles from a directory
def load_profiles_from_directory(directory: str) -> dict[str, MeterProfile]:
    """Load all .yaml profiles from a directory."""
    from pathlib import Path

    profiles = {}
    for yaml_file in Path(directory).glob("*.yaml"):
        try:
            profile = MeterProfile.from_yaml(str(yaml_file))
            profiles[profile.meter_type] = profile
        except Exception as e:
            raise ValueError(f"Error loading {yaml_file}: {e}")

    return profiles
