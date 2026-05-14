"""
MeterHub OTA (Over-The-Air) Manager

Atomic OS updates with A/B partitions and automatic rollback.

OTA Manager - Update Orchestration

Handles:
- Downloading OTA images from cloud
- Verifying signatures and checksums
- Staging images to inactive partition
- Coordinating with acquisition/uploader services
- Rollback on failure
- Delta update support
"""

__version__ = "1.0.0"

import logging
import asyncio
import json
from typing import Optional, Dict, Tuple
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import aiohttp

logger = logging.getLogger(__name__)


class UpdateState(str, Enum):
    """OTA update state machine."""

    IDLE = "idle"
    CHECKING = "checking"  # Checking for updates
    DOWNLOADING = "downloading"  # Downloading image
    VERIFYING = "verifying"  # Verifying signature/checksum
    STAGING = "staging"  # Writing to inactive partition
    COMMITTED = "committed"  # Ready to reboot
    FAILED = "failed"  # Update failed
    ROLLED_BACK = "rolled_back"  # Rolled back to previous version


@dataclass
class UpdateProgress:
    """OTA update progress information."""

    state: UpdateState
    version: str
    bytes_downloaded: int
    bytes_total: int
    percent_complete: float
    error_message: str | None = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class OTAManager:
    """Main OTA update manager."""

    def __init__(
        self,
        device_id: str,
        cloud_endpoint: str,
        update_cache_dir: Path = Path("/var/cache/meterhub/updates"),
        state_db_path: Path = Path("/var/lib/meterhub/state.db"),
    ):
        """
        Initialize OTA manager.

        Args:
            device_id: Device identifier
            cloud_endpoint: Cloud OTA endpoint URL
            update_cache_dir: Directory for staging images
            state_db_path: Path to state database
        """
        self.device_id = device_id
        self.cloud_endpoint = cloud_endpoint
        self.update_cache_dir = Path(update_cache_dir)
        self.state_db_path = state_db_path

        self.update_cache_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.current_state = UpdateState.IDLE
        self.current_version = "1.0.0"
        self.progress: UpdateProgress | None = None

        # Import dependencies (deferred to avoid circular imports)
        self.boot_manager = None
        self.image_signer = None

    async def _initialize(self):
        """Initialize manager dependencies."""
        if not self.boot_manager:
            from common.meterhub_common.mender_boot_manager import MenderBootManager

            self.boot_manager = MenderBootManager()

        if not self.image_signer:
            from common.meterhub_common.image_signer import ImageSigner

            self.image_signer = ImageSigner()

    async def check_for_updates(self) -> dict[str, str]:
        """
        Check cloud for available updates.

        Returns:
            Dict with update metadata or empty dict if no updates
        """
        await self._initialize()

        self.current_state = UpdateState.CHECKING
        logger.info("Checking for updates...")

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.cloud_endpoint}/updates/{self.device_id}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        update_info = await resp.json()
                        logger.info(f"Update available: v{update_info.get('version')}")
                        return update_info
                    elif resp.status == 204:
                        logger.info("No updates available")
                        return {}
                    else:
                        logger.warning(f"Update check failed: HTTP {resp.status}")
                        return {}

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            self.current_state = UpdateState.FAILED
            return {}

    async def download_image(
        self,
        update_url: str,
        target_version: str,
    ) -> Path | None:
        """
        Download OTA image from cloud.

        Args:
            update_url: URL to image
            target_version: Version string for naming

        Returns:
            Path to downloaded image, or None on failure
        """
        await self._initialize()

        self.current_state = UpdateState.DOWNLOADING
        image_path = self.update_cache_dir / f"ota-{target_version}.img"

        logger.info(f"Downloading OTA image: {update_url}")

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    update_url,
                    timeout=aiohttp.ClientTimeout(total=3600),  # 1 hour
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Download failed: HTTP {resp.status}")
                        return None

                    total_size = int(resp.headers.get("Content-Length", 0))
                    bytes_downloaded = 0

                    with open(image_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                            bytes_downloaded += len(chunk)

                            percent = (bytes_downloaded / total_size * 100) if total_size > 0 else 0
                            self.progress = UpdateProgress(
                                state=UpdateState.DOWNLOADING,
                                version=target_version,
                                bytes_downloaded=bytes_downloaded,
                                bytes_total=total_size,
                                percent_complete=percent,
                            )

            logger.info(f"Downloaded image: {image_path} ({bytes_downloaded} bytes)")
            return image_path

        except TimeoutError:
            logger.error("Download timeout")
            self.current_state = UpdateState.FAILED
            return None
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self.current_state = UpdateState.FAILED
            return None

    async def verify_image(
        self,
        image_path: Path,
        manifest: dict,
    ) -> bool:
        """
        Verify image signature, checksum, and metadata.

        Args:
            image_path: Path to downloaded image
            manifest: OTA manifest dict with signature, hash, etc.

        Returns:
            True if image passes all verification
        """
        await self._initialize()

        self.current_state = UpdateState.VERIFYING
        logger.info("Verifying OTA image...")

        try:
            # Check file exists
            if not image_path.exists():
                logger.error(f"Image file not found: {image_path}")
                return False

            # Verify size
            image_size = image_path.stat().st_size
            expected_size = manifest.get("image_size_bytes", 0)
            if expected_size > 0 and image_size != expected_size:
                logger.error(f"Image size mismatch: expected {expected_size}, got {image_size}")
                return False

            # Verify SHA256
            if "image_sha256" in manifest:
                actual_hash = self.image_signer.compute_image_sha256(image_path)
                expected_hash = manifest["image_sha256"]
                if actual_hash != expected_hash:
                    logger.error(f"SHA256 mismatch: expected {expected_hash}, got {actual_hash}")
                    return False

            # Verify signature
            if "signature" in manifest and "public_key" in manifest:
                signature_valid = self.image_signer.verify_signature(
                    image_path,
                    manifest["signature"],
                    manifest.get("public_key"),
                )
                if not signature_valid:
                    logger.error("Signature verification failed")
                    return False

            logger.info("✓ Image verification passed")
            return True

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False

    async def stage_image(self, image_path: Path) -> bool:
        """
        Write image to inactive partition and stage for boot.

        Args:
            image_path: Path to verified image

        Returns:
            True if staging successful
        """
        await self._initialize()

        self.current_state = UpdateState.STAGING
        logger.info("Staging image to inactive partition...")

        try:
            # Get current boot state
            boot_state = await self.boot_manager.get_boot_state()
            target_partition = boot_state.active_partition.toggle()

            logger.info(f"Target partition: {target_partition}")

            # Write image to partition
            write_success = await self.boot_manager.write_image_to_partition(
                image_path,
                target_partition,
            )
            if not write_success:
                logger.error("Image write failed")
                self.current_state = UpdateState.FAILED
                return False

            # Stage partition for next boot
            stage_success = await self.boot_manager.stage_partition(target_partition)
            if not stage_success:
                logger.error("Partition staging failed")
                self.current_state = UpdateState.FAILED
                return False

            self.current_state = UpdateState.COMMITTED
            logger.info("✓ Image staged successfully, ready for reboot")
            return True

        except Exception as e:
            logger.error(f"Staging failed: {e}")
            self.current_state = UpdateState.FAILED
            return False

    async def commit_update(self) -> bool:
        """
        Mark staged update as committed (after successful boot).

        Returns:
            True if commit successful
        """
        await self._initialize()

        try:
            boot_state = await self.boot_manager.get_boot_state()

            if not boot_state.staged_partition:
                logger.warning("No staged partition to commit")
                return False

            success = await self.boot_manager.commit_partition(boot_state.staged_partition)

            if success:
                logger.info(f"✓ Update committed: {boot_state.staged_partition}")

            return success

        except Exception as e:
            logger.error(f"Commit failed: {e}")
            return False

    async def rollback_update(self) -> bool:
        """
        Rollback to previous version on boot failure.

        Returns:
            True if rollback successful
        """
        await self._initialize()

        logger.warning("Initiating update rollback...")

        try:
            success = await self.boot_manager.rollback()

            if success:
                self.current_state = UpdateState.ROLLED_BACK
                logger.warning("✓ Rolled back to previous partition")

            return success

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    async def reboot_for_update(self) -> bool:
        """
        Reboot system to apply staged update.

        Returns:
            True if reboot initiated (doesn't return)
        """
        await self._initialize()

        logger.info("Rebooting for OTA update...")

        try:
            success = await self.boot_manager.reboot()
            return success

        except Exception as e:
            logger.error(f"Reboot failed: {e}")
            return False

    async def pause_services(self) -> bool:
        """
        Pause acquisition and uploader services before update.

        Returns:
            True if services paused successfully
        """
        try:
            import subprocess

            # Stop services
            for service in ["meterhub-acquisition", "meterhub-uploader"]:
                result = subprocess.run(
                    ["systemctl", "stop", service],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to stop {service}")
                else:
                    logger.info(f"Stopped {service}")

            await asyncio.sleep(1)  # Let services clean up
            return True

        except Exception as e:
            logger.error(f"Failed to pause services: {e}")
            return False

    async def resume_services(self) -> bool:
        """
        Resume acquisition and uploader services after update.

        Returns:
            True if services resumed successfully
        """
        try:
            import subprocess

            # Start services
            for service in ["meterhub-acquisition", "meterhub-uploader"]:
                result = subprocess.run(
                    ["systemctl", "start", service],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    logger.warning(f"Failed to start {service}")
                else:
                    logger.info(f"Started {service}")

            return True

        except Exception as e:
            logger.error(f"Failed to resume services: {e}")
            return False

    async def perform_full_update(
        self,
        update_info: dict,
        public_key_pem: str | None = None,
    ) -> bool:
        """
        Perform complete OTA workflow (check → download → verify → stage → reboot).

        Args:
            update_info: Update metadata from cloud
            public_key_pem: Optional public key for signature verification

        Returns:
            True if update successful
        """
        logger.info(f"Starting OTA update to v{update_info.get('version')}")

        try:
            # Pause services
            await self.pause_services()

            # Download image
            image_path = await self.download_image(
                update_info["url"],
                update_info["version"],
            )
            if not image_path:
                await self.resume_services()
                return False

            # Add public key if provided
            if public_key_pem:
                update_info["public_key"] = public_key_pem

            # Verify image
            verify_success = await self.verify_image(image_path, update_info)
            if not verify_success:
                await self.resume_services()
                return False

            # Stage image
            stage_success = await self.stage_image(image_path)
            if not stage_success:
                await self.resume_services()
                return False

            # Reboot
            await self.reboot_for_update()
            # Note: Does not return from reboot

        except Exception as e:
            logger.error(f"OTA update failed: {e}")
            await self.resume_services()
            return False

    def get_progress(self) -> UpdateProgress:
        """Get current update progress."""
        if not self.progress:
            self.progress = UpdateProgress(
                state=self.current_state,
                version=self.current_version,
                bytes_downloaded=0,
                bytes_total=0,
                percent_complete=0,
            )
        return self.progress

    async def get_state(self) -> dict[str, str]:
        """Get OTA manager state."""
        bootstate = await self.boot_manager.get_boot_state() if self.boot_manager else None

        return {
            "update_state": self.current_state.value,
            "current_version": self.current_version,
            "boot_active": bootstate.active_partition.value if bootstate else "unknown",
            "boot_staged": (
                bootstate.staged_partition.value
                if bootstate and bootstate.staged_partition
                else None
            ),
        }
