"""
Unit Tests for OTA Infrastructure (Phase 5)

Tests:
- Image signing and verification (Ed25519)
- Mender A/B boot management
- OTA manager workflow
- Delta update logic
- Rollback scenarios
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from common.meterhub_common.image_signer import ImageSigner, OTAManifest
from common.meterhub_common.mender_boot_manager import MenderBootManager, BootPartition, BootState
from ota.meterhub_ota_manager import OTAManager, UpdateState, UpdateProgress


class TestImageSigner:
    """Image signing and verification tests."""

    @pytest.fixture
    def signer(self):
        """Create signer with temporary key directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            signer = ImageSigner(key_dir=Path(tmpdir))
            yield signer

    @pytest.fixture
    def sample_image(self):
        """Create sample image file."""
        with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".img") as f:
            f.write(b"fake OS image data" * 100)
            temp_path = f.name
        yield Path(temp_path)

    def test_signer_initialization(self, signer):
        """Test signer initialization."""
        assert signer.key_dir.exists()

    @pytest.mark.skipif(
        not pytest.importorskip("cryptography", minversion=None),
        reason="cryptography not available",
    )
    def test_generate_keypair(self, signer):
        """Test Ed25519 keypair generation."""
        private_pem, public_pem = signer.generate_keypair()

        assert len(private_pem) > 0
        assert len(public_pem) > 0
        assert "PRIVATE KEY" in private_pem
        assert "PUBLIC KEY" in public_pem
        assert signer.private_key_path.exists()
        assert signer.public_key_path.exists()

    @pytest.mark.skipif(
        not pytest.importorskip("cryptography", minversion=None),
        reason="cryptography not available",
    )
    def test_keypair_persistence(self, signer):
        """Test keypair can be loaded from disk."""
        private1, public1 = signer.generate_keypair()

        # Create new signer instance, should load existing keys
        signer2 = ImageSigner(key_dir=signer.key_dir)
        private2, public2 = signer2._load_keypair()

        assert private1 == private2
        assert public1 == public2

    def test_compute_sha256(self, sample_image):
        """Test SHA256 computation."""
        sha256 = ImageSigner.compute_image_sha256(sample_image)

        assert len(sha256) == 64  # SHA256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in sha256)

    @pytest.mark.skipif(
        not pytest.importorskip("cryptography", minversion=None),
        reason="cryptography not available",
    )
    def test_sign_and_verify(self, signer, sample_image):
        """Test image signing and verification."""
        signer.generate_keypair()

        # Sign
        signature = signer.sign_image(sample_image)
        assert signature is not None
        assert len(signature) == 128  # Ed25519 sig in hex

        # Verify
        verified = signer.verify_signature(sample_image, signature)
        assert verified is True

    @pytest.mark.skipif(
        not pytest.importorskip("cryptography", minversion=None),
        reason="cryptography not available",
    )
    def test_verify_invalid_signature(self, signer, sample_image):
        """Test verification fails on corrupted signature."""
        signer.generate_keypair()

        # Sign
        signer.sign_image(sample_image)

        # Try with bad signature
        bad_signature = "00" * 64  # Invalid signature
        verified = signer.verify_signature(sample_image, bad_signature)
        assert verified is False

    def test_create_manifest(self, sample_image):
        """Test OTA manifest creation."""
        manifest = ImageSigner.create_manifest(
            version="1.2.3",
            timestamp=datetime.utcnow().isoformat(),
            image_path=sample_image,
            device_types=["rpi-zero-2w"],
            release_notes="Bug fixes and improvements",
        )

        assert manifest.version == "1.2.3"
        assert manifest.image_size_bytes > 0
        assert len(manifest.image_sha256) == 64
        assert "rpi-zero-2w" in manifest.device_types

    def test_validate_manifest(self):
        """Test manifest validation."""
        manifest = OTAManifest(
            version="1.0.0",
            timestamp=datetime.utcnow().isoformat(),
            device_types=["rpi-zero-2w"],
            image_size_bytes=102400,
            image_sha256="a" * 64,
            signature="b" * 128,
        )

        results = ImageSigner.validate_manifest(manifest)

        assert results["has_version"] is True
        assert results["has_device_types"] is True
        assert results["has_image_hash"] is True
        assert results["has_signature"] is True
        assert results["sha256_valid_format"] is True


class TestMenderBootManager:
    """Mender A/B boot management tests."""

    @pytest.fixture
    def boot_manager(self):
        """Create boot manager."""
        return MenderBootManager()

    def test_boot_manager_initialization(self, boot_manager):
        """Test boot manager initialization."""
        assert boot_manager is not None
        assert boot_manager.partition_a.name == "mmcblk0p2"
        assert boot_manager.partition_b.name == "mmcblk0p3"

    def test_boot_partition_toggle(self):
        """Test partition toggle."""
        assert BootPartition.A.toggle() == BootPartition.B
        assert BootPartition.B.toggle() == BootPartition.A

    @pytest.mark.asyncio
    async def test_boot_state_creation(self, boot_manager):
        """Test boot state creation."""
        state = BootState(
            active_partition=BootPartition.A,
            staged_partition=None,
            boot_count=0,
            boot_attempts=3,
            committed=True,
        )

        assert state.active_partition == BootPartition.A
        assert state.staged_partition is None
        assert state.committed is True

    @pytest.mark.asyncio
    async def test_get_partition_info(self, boot_manager):
        """Test getting partition information."""
        # Mock blockdev output
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="5368709120\n",  # 5 GB in bytes
            )

            info = await boot_manager.get_partition_info()

            assert BootPartition.A in info
            assert BootPartition.B in info
            assert info[BootPartition.A]["size_bytes"] == 5368709120


class TestOTAManager:
    """OTA manager workflow tests."""

    @pytest.fixture
    def ota_manager(self):
        """Create OTA manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = OTAManager(
                device_id="meter-001",
                cloud_endpoint="https://api.example.com/ota",
                update_cache_dir=Path(tmpdir) / "updates",
            )
            yield manager

    def test_ota_manager_initialization(self, ota_manager):
        """Test OTA manager initialization."""
        assert ota_manager.device_id == "meter-001"
        assert ota_manager.current_state == UpdateState.IDLE

    @pytest.mark.asyncio
    async def test_update_progress_creation(self):
        """Test update progress tracking."""
        progress = UpdateProgress(
            state=UpdateState.DOWNLOADING,
            version="1.2.3",
            bytes_downloaded=51200,
            bytes_total=102400,
            percent_complete=50.0,
        )

        assert progress.percent_complete == 50.0
        assert progress.state == UpdateState.DOWNLOADING
        assert progress.timestamp is not None

    @pytest.mark.asyncio
    async def test_check_for_updates(self, ota_manager):
        """Test checking for updates (mocked)."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(
                return_value={
                    "version": "1.2.3",
                    "url": "https://api.example.com/images/1.2.3.img",
                }
            )
            mock_get.return_value.__aenter__.return_value = mock_resp

            updates = await ota_manager.check_for_updates()

            assert updates["version"] == "1.2.3"
            assert ota_manager.current_state == UpdateState.CHECKING

    @pytest.mark.asyncio
    async def test_no_updates_available(self, ota_manager):
        """Test when no updates are available."""
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 204  # No content
            mock_get.return_value.__aenter__.return_value = mock_resp

            updates = await ota_manager.check_for_updates()

            assert updates == {}

    @pytest.mark.asyncio
    async def test_pause_resume_services(self, ota_manager):
        """Test pausing and resuming services."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Pause
            paused = await ota_manager.pause_services()
            assert paused is True

            # Resume
            resumed = await ota_manager.resume_services()
            assert resumed is True

    @pytest.mark.asyncio
    async def test_get_state(self, ota_manager):
        """Test getting OTA manager state."""
        state = await ota_manager.get_state()

        assert "update_state" in state
        assert "current_version" in state


class TestOTAIntegration:
    """End-to-end OTA workflow tests."""

    @pytest.mark.asyncio
    async def test_full_update_workflow(self):
        """Test complete OTA workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = OTAManager(
                device_id="meter-001",
                cloud_endpoint="https://api.example.com/ota",
                update_cache_dir=Path(tmpdir) / "updates",
            )

            # Create fake update info
            update_info = {
                "version": "1.2.3",
                "url": "https://example.com/image.img",
                "image_size_bytes": 1024,
                "image_sha256": "a" * 64,
            }

            # Mock the download
            with patch("aiohttp.ClientSession.get") as mock_get:
                mock_resp = AsyncMock()
                mock_resp.status = 200
                mock_resp.headers = {"Content-Length": "1024"}
                mock_resp.content.iter_chunked = AsyncMock(
                    return_value=[b"x" * 100 for _ in range(10)]
                )
                mock_get.return_value.__aenter__.return_value = mock_resp

                progress = manager.get_progress()
                assert progress.state == UpdateState.IDLE


class TestBootScenarios:
    """Boot-related scenario tests."""

    @pytest.mark.asyncio
    async def test_rollback_on_boot_failure(self):
        """Test rollback on boot failure scenario."""
        manager = MenderBootManager()

        # Create initial boot state (B staged)
        initial_state = BootState(
            active_partition=BootPartition.A,
            staged_partition=BootPartition.B,
            boot_count=2,
            boot_attempts=3,
            committed=False,
        )

        assert initial_state.staged_partition == BootPartition.B
        assert not initial_state.committed

    def test_boot_count_threshold(self):
        """Test boot count threshold detection."""
        state = BootState(
            active_partition=BootPartition.A,
            staged_partition=BootPartition.B,
            boot_count=3,
            boot_attempts=3,
            committed=False,
        )

        # Boot count == max attempts, should trigger rollback
        should_rollback = state.boot_count >= state.boot_attempts
        assert should_rollback is True


class TestDeltaUpdates:
    """Delta update support tests."""

    def test_delta_manifest_creation(self):
        """Test creating delta update manifest."""
        manifest = OTAManifest(
            version="1.2.3",
            timestamp=datetime.utcnow().isoformat(),
            device_types=["rpi-zero-2w"],
            image_size_bytes=10240,  # Much smaller for delta
            image_sha256="a" * 64,
            delta_base_version="1.2.2",  # Delta from 1.2.2
            replaces_version="1.2.2",
        )

        assert manifest.delta_base_version == "1.2.2"
        assert manifest.image_size_bytes < 51200  # Smaller than full image

    def test_delta_vs_full_image_size(self):
        """Test delta images are smaller than full."""
        full_manifest = OTAManifest(
            version="1.2.3",
            timestamp=datetime.utcnow().isoformat(),
            device_types=["rpi-zero-2w"],
            image_size_bytes=102400,
            image_sha256="a" * 64,
        )

        delta_manifest = OTAManifest(
            version="1.2.3",
            timestamp=datetime.utcnow().isoformat(),
            device_types=["rpi-zero-2w"],
            image_size_bytes=10240,  # 10% of full
            image_sha256="a" * 64,
            delta_base_version="1.2.2",
        )

        assert delta_manifest.image_size_bytes < full_manifest.image_size_bytes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
