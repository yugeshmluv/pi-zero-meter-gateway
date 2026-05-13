#!/usr/bin/env python3
"""
MeterHub Release Builder

Automated CI/CD pipeline for building and releasing MeterHub images.

Usage:
    ./build_release.py --version 1.2.3 --channel stable
    ./build_release.py --version 1.2.3 --channel beta --no-sign
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

# Add build directory to path
sys.path.insert(0, str(Path(__file__).parent))

from build.meterhub_build_manager.image_builder import ImageBuilder, ImageConfig
from build.meterhub_build_manager.security_hardening import (
    SecureBootConfig,
    AideConfig,
    ApparmorProfile,
    KernelHardening,
)


class ReleaseBuilder:
    """Orchestrate MeterHub release builds."""

    def __init__(self, version: str, channel: str = "stable"):
        """
        Initialize release builder.

        Args:
            version: Semantic version (e.g., "1.2.3")
            channel: Release channel (stable, beta, dev)
        """
        self.version = version
        self.channel = channel
        self.build_dir = Path("/builds/meterhub") / version
        self.dist_dir = self.build_dir / "dist"
        self.logs_dir = self.build_dir / "logs"

        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.dist_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.build_manifest: Dict = {
            "version": version,
            "channel": channel,
            "timestamp": datetime.utcnow().isoformat(),
            "images": {},
        }

    async def build_release(
        self,
        sign: bool = True,
        publish: bool = False,
    ) -> bool:
        """
        Build complete release.

        Args:
            sign: Whether to sign images
            publish: Whether to publish to cloud

        Returns:
            True if build successful
        """
        print(f"\n{'='*70}")
        print(f"MeterHub Release Build: v{self.version} ({self.channel})")
        print(f"{'='*70}\n")

        try:
            # Step 1: Build OS images
            print("📦 Building OS images...")
            images = await self._build_images()
            if not images:
                print("❌ Image build failed")
                return False

            # Step 2: Sign images
            if sign:
                print("\n🔐 Signing images...")
                if not await self._sign_images(images):
                    print("❌ Image signing failed")
                    return False

            # Step 3: Generate manifests
            print("\n📋 Generating manifests...")
            await self._generate_manifests(images)

            # Step 4: Publish (if requested)
            if publish:
                print("\n🚀 Publishing release...")
                if not await self._publish_release():
                    print("⚠️  Publish failed (images built successfully)")

            print(f"\n✅ Release build complete: {self.dist_dir}")
            return True

        except Exception as e:
            print(f"\n❌ Release build failed: {e}")
            return False

    async def _build_images(self):
        """Build OS images for different targets."""
        builder = ImageBuilder(work_dir=self.build_dir / "build")

        # Check prerequisites
        if not await builder.check_prerequisites():
            print("❌ Prerequisites not met")
            return None

        images = {}

        # Build ARMv8 image (RPi Zero 2W)
        print("  → Building ARMv8 image (RPi Zero 2W)...")
        config = ImageConfig(
            output_path=self.dist_dir / f"meterhub-v{self.version}-armv8.img",
            hostname=f"meterhub-v{self.version}",
            kernel_variant="v8",
            compressed=True,
        )

        image_path = await builder.build_image(config)
        if image_path:
            hashes = await builder.compute_image_hash(image_path)
            info = builder.get_build_info(image_path)

            images["armv8"] = {
                "path": str(image_path),
                "info": info,
                "hashes": hashes,
            }
            print(f"     ✓ Built: {image_path.name} ({info['size_mb']:.1f} MB)")
        else:
            print("     ❌ Build failed")

        return images if images else None

    async def _sign_images(self, images: Dict) -> bool:
        """Sign built images."""
        from common.meterhub_common.image_signer import ImageSigner

        try:
            signer = ImageSigner()
            signer.generate_keypair()

            for arch, image_info in images.items():
                image_path = Path(image_info["path"])
                signature = signer.sign_image(image_path)

                if signature:
                    image_info["signature"] = signature

                    # Save signature file
                    sig_file = image_path.parent / f"{image_path.name}.sig"
                    sig_file.write_text(signature)

                    print(f"  ✓ Signed: {arch} ({len(signature)} chars)")
                else:
                    print(f"  ❌ Signing failed: {arch}")
                    return False

            return True

        except Exception as e:
            print(f"  ❌ Signing error: {e}")
            return False

    async def _generate_manifests(self, images: Dict) -> bool:
        """Generate release manifests."""
        try:
            # OTA manifest
            ota_manifest = {
                "version": self.version,
                "channel": self.channel,
                "timestamp": self.build_manifest["timestamp"],
                "device_types": ["rpi-zero-2w"],
                "images": images,
                "release_notes": f"MeterHub {self.version} Release",
            }

            manifest_path = self.dist_dir / "manifest.json"
            manifest_path.write_text(json.dumps(ota_manifest, indent=2))

            print(f"  ✓ OTA manifest: {manifest_path.name}")

            # Checksum file
            checksums = []
            for arch, image_info in images.items():
                if "hashes" in image_info:
                    path = Path(image_info["path"])
                    checksums.append(
                        f"{image_info['hashes']['sha256']}  {path.name}"
                    )

            checksum_file = self.dist_dir / "SHA256SUMS"
            checksum_file.write_text("\n".join(checksums))

            print(f"  ✓ Checksums: {checksum_file.name}")

            return True

        except Exception as e:
            print(f"  ❌ Manifest generation error: {e}")
            return False

    async def _publish_release(self) -> bool:
        """Publish release to cloud."""
        try:
            # TODO: Implement cloud publishing
            # - Upload to S3 bucket
            # - Update release database
            # - Notify devices of new version
            print("  ⓘ Cloud publishing not yet implemented")
            return True

        except Exception as e:
            print(f"  ❌ Publish error: {e}")
            return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MeterHub Release Builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./build_release.py --version 1.2.3
  ./build_release.py --version 1.2.3 --channel beta
  ./build_release.py --version 1.2.3 --channel dev --no-sign
        """,
    )

    parser.add_argument(
        "--version",
        required=True,
        help="Semantic version (e.g., 1.2.3)",
    )
    parser.add_argument(
        "--channel",
        default="stable",
        choices=["stable", "beta", "dev"],
        help="Release channel (default: stable)",
    )
    parser.add_argument(
        "--no-sign",
        action="store_true",
        help="Skip image signing",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish release to cloud",
    )

    args = parser.parse_args()

    # Build release
    builder = ReleaseBuilder(version=args.version, channel=args.channel)
    success = await builder.build_release(
        sign=not args.no_sign,
        publish=args.publish,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
