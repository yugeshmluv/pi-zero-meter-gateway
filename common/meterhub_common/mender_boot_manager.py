"""
Mender A/B Boot Manager

Handles:
- A/B partition switching (atomic boot transitions)
- Bootloader environment variables (U-Boot)
- Boot attempt tracking and rollback
- Device tree blob (DTB) selection
- Reboot coordination
"""

import logging
import subprocess
from typing import Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class BootPartition(str, Enum):
    """Boot partition enumeration."""

    A = "a"
    B = "b"

    def toggle(self) -> "BootPartition":
        """Toggle between A and B."""
        return BootPartition.B if self == BootPartition.A else BootPartition.A


@dataclass
class BootState:
    """Current boot state information."""

    active_partition: BootPartition
    staged_partition: BootPartition | None
    boot_count: int  # Number of boot attempts on staged partition
    boot_attempts: int  # Maximum allowed boot attempts
    committed: bool  # Whether current boot is committed


class MenderBootManager:
    """Manage Mender A/B boot partitions."""

    def __init__(self, fw_env_config: Path = Path("/etc/fw_env.config")) -> None:
        """
        Initialize Mender boot manager.

        Args:
            fw_env_config: Path to U-Boot fw_env.config
        """
        self.fw_env_config = fw_env_config
        self.fw_setenv = Path("/usr/bin/fw_setenv")
        self.fw_printenv = Path("/usr/bin/fw_printenv")

        # Partition paths
        self.partition_a = Path("/dev/mmcblk0p2")  # Main (slot A)
        self.partition_b = Path("/dev/mmcblk0p3")  # Backup (slot B)

        # Boot environment variables
        self.boot_env_active = "mender_boot_part"
        self.boot_env_staged = "mender_staging_part"
        self.boot_env_attempts = "bootcount"

    async def get_boot_state(self) -> BootState:
        """
        Get current boot state.

        Returns:
            BootState with active/staged partitions and boot counts
        """
        try:
            active = await self._get_active_partition()
            staged = await self._get_staged_partition()
            boot_count = await self._get_boot_count()

            state = BootState(
                active_partition=active,
                staged_partition=staged,
                boot_count=boot_count,
                boot_attempts=3,  # Standard Mender value
                committed=staged is None,
            )

            logger.info(f"Boot state: {state}")
            return state

        except Exception as e:
            logger.error(f"Failed to read boot state: {e}")
            return BootState(
                active_partition=BootPartition.A,
                staged_partition=None,
                boot_count=0,
                boot_attempts=3,
                committed=True,
            )

    async def _get_active_partition(self) -> BootPartition:
        """Get currently active boot partition."""
        try:
            result = subprocess.run(
                ["fw_printenv", self.boot_env_active],
                capture_output=True,
                text=True,
                timeout=5,
            )

            value = result.stdout.strip().split("=")[-1]
            return BootPartition(value)

        except Exception as e:
            logger.warning(f"Could not read active partition: {e}")
            return BootPartition.A

    async def _get_staged_partition(self) -> BootPartition | None:
        """Get staged partition (if any)."""
        try:
            result = subprocess.run(
                ["fw_printenv", self.boot_env_staged],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            value = result.stdout.strip().split("=")[-1]
            return BootPartition(value) if value else None

        except Exception:
            return None

    async def _get_boot_count(self) -> int:
        """Get current boot attempt count."""
        try:
            result = subprocess.run(
                ["fw_printenv", self.boot_env_attempts],
                capture_output=True,
                text=True,
                timeout=5,
            )

            value = result.stdout.strip().split("=")[-1]
            return int(value)

        except Exception:
            return 0

    async def stage_partition(self, target: BootPartition) -> bool:
        """
        Stage partition for next boot (atomic).

        Args:
            target: Target partition (A or B)

        Returns:
            True if staging successful
        """
        try:
            # Get current active
            active = await self._get_active_partition()

            if target == active:
                logger.warning(f"Target partition {target} is already active")
                return False

            # Set staged partition
            result = subprocess.run(
                ["fw_setenv", self.boot_env_staged, target.value],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.error(f"Failed to stage partition: {result.stderr}")
                return False

            # Reset boot count
            subprocess.run(
                ["fw_setenv", self.boot_env_attempts, "0"],
                timeout=5,
            )

            logger.info(f"Staged partition {target} for next boot")
            return True

        except Exception as e:
            logger.error(f"Failed to stage partition: {e}")
            return False

    async def commit_partition(self, partition: BootPartition) -> bool:
        """
        Commit partition as active (after successful boot).

        Args:
            partition: Partition to commit

        Returns:
            True if commit successful
        """
        try:
            # Set as active
            result = subprocess.run(
                ["fw_setenv", self.boot_env_active, partition.value],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.error(f"Failed to commit partition: {result.stderr}")
                return False

            # Clear staged partition
            subprocess.run(
                ["fw_setenv", self.boot_env_staged, ""],
                timeout=5,
            )

            # Reset boot count
            subprocess.run(
                ["fw_setenv", self.boot_env_attempts, "0"],
                timeout=5,
            )

            logger.info(f"Committed partition {partition}")
            return True

        except Exception as e:
            logger.error(f"Failed to commit partition: {e}")
            return False

    async def rollback(self) -> bool:
        """
        Rollback to previous partition on boot failure.

        Returns:
            True if rollback successful
        """
        try:
            state = await self.get_boot_state()

            if not state.staged_partition:
                logger.warning("No staged partition to rollback from")
                return False

            # Revert to active partition
            msg = f"Rolling back from {state.staged_partition} to {state.active_partition}"
            logger.warning(msg)
            result = subprocess.run(
                ["fw_setenv", self.boot_env_staged, ""],
                capture_output=True,
                text=True,
                timeout=5,
            )

            return result.returncode == 0

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def reboot(self, target_partition: BootPartition | None = None) -> bool:
        """
        Reboot system (after staging partition).

        Args:
            target_partition: If specified, stage before rebooting

        Returns:
            True if reboot command issued (doesn't return)
        """
        try:
            if target_partition:
                success = await self.stage_partition(target_partition)
                if not success:
                    return False

            logger.warning("Initiating system reboot...")
            subprocess.run(["shutdown", "-r", "now"], timeout=5)
            return True

        except Exception as e:
            logger.error(f"Reboot failed: {e}")
            return False

    async def get_partition_info(self) -> dict[BootPartition, dict[str, Any]]:
        """Get information about A/B partitions."""
        try:
            partition_info = {}

            for partition in [BootPartition.A, BootPartition.B]:
                partition_path = (
                    self.partition_a if partition == BootPartition.A else self.partition_b
                )

                # Get partition size
                result = subprocess.run(
                    ["blockdev", "--getsize64", str(partition_path)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                size_bytes = int(result.stdout.strip()) if result.returncode == 0 else 0

                partition_info[partition] = {
                    "path": str(partition_path),
                    "size_bytes": size_bytes,
                    "size_gb": size_bytes / (1024**3),
                }

            return partition_info

        except Exception as e:
            logger.error(f"Failed to get partition info: {e}")
            return {}

    async def write_image_to_partition(
        self,
        image_path: Path,
        target_partition: BootPartition,
    ) -> bool:
        """
        Write OS image to target partition (destructive).

        Args:
            image_path: Path to OS image file
            target_partition: Target partition (A or B)

        Returns:
            True if write successful
        """
        try:
            partition_path = (
                self.partition_a if target_partition == BootPartition.A else self.partition_b
            )

            logger.warning(f"Writing image to {partition_path}...")

            # Use dd to write image
            result = subprocess.run(
                [
                    "dd",
                    f"if={image_path}",
                    f"of={partition_path}",
                    "bs=4M",
                    "conv=fsync",
                ],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
            )

            if result.returncode != 0:
                logger.error(f"Image write failed: {result.stderr}")
                return False

            logger.info(f"Image written to {partition_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to write image: {e}")
            return False

    async def verify_partition_signature(
        self,
        partition: BootPartition,
        expected_hash: str,
    ) -> bool:
        """
        Verify partition has expected SHA256 hash.

        Args:
            partition: Partition to verify
            expected_hash: Expected SHA256 hash (hex)

        Returns:
            True if hash matches
        """
        try:
            import hashlib

            partition_path = self.partition_a if partition == BootPartition.A else self.partition_b

            sha256 = hashlib.sha256()
            with open(partition_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)

            actual_hash = sha256.hexdigest()

            if actual_hash == expected_hash:
                logger.info(f"✓ Partition {partition} hash verified")
                return True
            else:
                logger.error(
                    f"✗ Partition {partition} hash mismatch: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
                return False

        except Exception as e:
            logger.error(f"Hash verification failed: {e}")
            return False
