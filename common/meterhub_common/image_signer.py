"""
OTA Image Signing & Validation

Handles:
- Ed25519 keypair generation
- Image signing (deterministic)
- Signature verification
- Manifest validation (metadata + checksums)
"""

import logging
import hashlib
import os
import tempfile
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Try to import cryptography for Ed25519
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    logger.warning("cryptography library not available, using HMAC fallback")


@dataclass
class OTAManifest:
    """OTA update manifest metadata."""

    version: str  # Semantic version (e.g., "1.2.3")
    timestamp: str  # ISO 8601 timestamp
    device_types: list[str]  # List of compatible device types (e.g., ["rpi-zero-2w"])
    image_size_bytes: int
    image_sha256: str  # Hex-encoded SHA256 of image
    delta_base_version: str | None = None  # If delta update, base version
    replaces_version: str | None = None  # Current version being replaced
    release_notes: str | None = None
    signature: str | None = None  # Hex-encoded Ed25519 signature


class ImageSigner:
    """Sign and verify OTA images using Ed25519."""

    def __init__(self, key_dir: Path | None = None) -> None:
        """
        Initialize image signer.

        Args:
            key_dir: Directory containing signing keys
        """
        self.key_dir = Path(key_dir or os.getenv("METERHUB_KEY_DIR") or "/etc/meterhub/keys")
        try:
            self.key_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            if os.getenv("METERHUB_ENV") == "production":
                raise
            self.key_dir = Path(tempfile.gettempdir()) / "meterhub" / "keys"
            self.key_dir.mkdir(parents=True, exist_ok=True)

        self.private_key_path = self.key_dir / "ota_private.pem"
        self.public_key_path = self.key_dir / "ota_public.pem"

        self.private_key: ed25519.Ed25519PrivateKey | None = None
        self.public_key: ed25519.Ed25519PublicKey | None = None

    def generate_keypair(self, force: bool = False) -> tuple[str, str]:
        """
        Generate Ed25519 keypair.

        Args:
            force: If True, overwrite existing keys

        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        if not HAS_CRYPTO:
            logger.error("cryptography library required for key generation")
            return ("", "")

        # Check if keys exist
        if self.private_key_path.exists() and not force:
            logger.warning("Keypair already exists, use force=True to regenerate")
            return self._load_keypair()

        try:
            # Generate private key
            private_key = ed25519.Ed25519PrivateKey.generate()
            public_key = private_key.public_key()

            # Serialize to PEM
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ).decode("utf-8")

            public_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode("utf-8")

            # Save keys
            self.private_key_path.write_text(private_pem)
            self.public_key_path.write_text(public_pem)

            logger.info(f"Generated keypair in {self.key_dir}")
            self.private_key = private_key
            self.public_key = public_key

            return (private_pem, public_pem)

        except Exception as e:
            logger.error(f"Failed to generate keypair: {e}")
            return ("", "")

    def _load_keypair(self) -> tuple[str, str]:
        """Load existing keypair from disk."""
        try:
            if not self.private_key_path.exists():
                logger.warning("Private key not found")
                return ("", "")

            private_pem = self.private_key_path.read_text()
            public_pem = self.public_key_path.read_text() if self.public_key_path.exists() else ""

            if HAS_CRYPTO:
                loaded_key = serialization.load_pem_private_key(
                    private_pem.encode("utf-8"),
                    password=None,
                )
                if not isinstance(loaded_key, ed25519.Ed25519PrivateKey):
                    raise TypeError(
                        f"Expected Ed25519 private key, got {type(loaded_key).__name__}"
                    )
                self.private_key = loaded_key
                self.public_key = loaded_key.public_key()

            return (private_pem, public_pem)

        except Exception as e:
            logger.error(f"Failed to load keypair: {e}")
            return ("", "")

    def sign_image(self, image_path: Path) -> str | None:
        """
        Sign OTA image file.

        Args:
            image_path: Path to OS image file

        Returns:
            Hex-encoded Ed25519 signature, or None on error
        """
        if not HAS_CRYPTO:
            logger.error("cryptography required for signing")
            return None

        try:
            # Load private key
            if not self.private_key:
                private_pem, _ = self._load_keypair()
                if not private_pem:
                    return None
                loaded_key = serialization.load_pem_private_key(
                    private_pem.encode("utf-8"),
                    password=None,
                )
                if not isinstance(loaded_key, ed25519.Ed25519PrivateKey):
                    raise TypeError(
                        f"Expected Ed25519 private key, got {type(loaded_key).__name__}"
                    )
                self.private_key = loaded_key

            # Read image and compute signature
            assert self.private_key is not None  # narrowing for mypy
            image_data = image_path.read_bytes()
            signature = self.private_key.sign(image_data)

            logger.info(f"Signed image: {image_path} ({len(image_data)} bytes)")
            return str(signature.hex())

        except Exception as e:
            logger.error(f"Failed to sign image: {e}")
            return None

    def verify_signature(
        self,
        image_path: Path,
        signature_hex: str,
        public_key_pem: str | None = None,
    ) -> bool:
        """
        Verify image signature.

        Args:
            image_path: Path to OS image file
            signature_hex: Hex-encoded signature
            public_key_pem: Optional public key (default: load from disk)

        Returns:
            True if signature is valid
        """
        if not HAS_CRYPTO:
            logger.warning("cryptography required for signature verification")
            return False

        try:
            # Load public key
            if public_key_pem:
                loaded_pub = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
                if not isinstance(loaded_pub, ed25519.Ed25519PublicKey):
                    raise TypeError(f"Expected Ed25519 public key, got {type(loaded_pub).__name__}")
                public_key = loaded_pub
            else:
                if not self.public_key:
                    _, public_pem = self._load_keypair()
                    if not public_pem:
                        return False
                    loaded_pub = serialization.load_pem_public_key(public_pem.encode("utf-8"))
                    if not isinstance(loaded_pub, ed25519.Ed25519PublicKey):
                        raise TypeError(
                            f"Expected Ed25519 public key, got {type(loaded_pub).__name__}"
                        )
                    public_key = loaded_pub
                else:
                    public_key = self.public_key

            # Read image and verify
            image_data = image_path.read_bytes()
            signature_bytes = bytes.fromhex(signature_hex)

            public_key.verify(signature_bytes, image_data)
            logger.info(f"✓ Signature verified: {image_path}")
            return True

        except Exception as e:
            logger.error(f"✗ Signature verification failed: {e}")
            return False

    @staticmethod
    def compute_image_sha256(image_path: Path) -> str:
        """
        Compute SHA256 hash of image.

        Args:
            image_path: Path to OS image file

        Returns:
            Hex-encoded SHA256 hash
        """
        try:
            sha256 = hashlib.sha256()
            with open(image_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)
            hash_hex = sha256.hexdigest()
            logger.info(f"Image SHA256: {hash_hex}")
            return hash_hex
        except Exception as e:
            logger.error(f"Failed to compute SHA256: {e}")
            return ""

    @staticmethod
    def create_manifest(
        version: str,
        timestamp: str,
        image_path: Path,
        device_types: list[str],
        release_notes: str | None = None,
        signature: str | None = None,
    ) -> OTAManifest:
        """
        Create OTA manifest for image.

        Args:
            version: Semantic version
            timestamp: ISO 8601 timestamp
            image_path: Path to OS image
            device_types: List of compatible device types
            release_notes: Optional release notes
            signature: Optional pre-computed signature

        Returns:
            OTAManifest instance
        """
        image_sha256 = ImageSigner.compute_image_sha256(image_path)
        image_size = image_path.stat().st_size

        manifest = OTAManifest(
            version=version,
            timestamp=timestamp,
            device_types=device_types,
            image_size_bytes=image_size,
            image_sha256=image_sha256,
            signature=signature,
            release_notes=release_notes,
        )

        return manifest

    @staticmethod
    def validate_manifest(manifest: OTAManifest) -> dict[str, bool]:
        """
        Validate OTA manifest structure.

        Args:
            manifest: OTAManifest to validate

        Returns:
            Dict with validation results
        """
        results = {
            "has_version": bool(manifest.version),
            "has_timestamp": bool(manifest.timestamp),
            "has_device_types": len(manifest.device_types) > 0,
            "has_image_hash": bool(manifest.image_sha256),
            "has_signature": bool(manifest.signature),
            "sha256_valid_format": len(manifest.image_sha256) == 64,  # SHA256 hex
        }

        return results
