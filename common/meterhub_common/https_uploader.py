"""
HTTPS Fallback Uploader for MeterHub

Fallback cloud upload when MQTT is unavailable:
- TLS 1.2+ certificate validation
- OAuth2 bearer token authentication
- JSON payload with signature
- Exponential backoff retry (3 attempts)
- Connection pooling via aiohttp
"""

import asyncio
import json
import logging
from typing import Type, Dict, Any, Optional, Tuple
from datetime import datetime
import ssl

import aiohttp
from types import TracebackType

logger = logging.getLogger(__name__)


class HTTPSFallbackUploader:
    """
    HTTPS fallback uploader using OAuth2 bearer tokens.

    Uploads meter readings to cloud API when MQTT is unavailable.
    """

    # Exponential backoff (milliseconds)
    BACKOFF_MS = [100, 500, 2000]

    def __init__(
        self,
        endpoint: str,  # HTTPS URL (e.g., https://api.meterhub.example.com/v1)
        device_id: str,
        oauth2_token: str,  # Bearer token
        ca_path: Optional[str] = None,  # CA certificate for verification
        timeout_s: int = 10,
    ) -> None:
        """
        Initialize HTTPS uploader.

        Args:
            endpoint: HTTPS API endpoint URL
            device_id: Device identifier
            oauth2_token: OAuth2 bearer token
            ca_path: Path to CA certificate (optional, use system default if None)
            timeout_s: Request timeout in seconds
        """
        self.endpoint = endpoint
        self.device_id = device_id
        self.oauth2_token = oauth2_token
        self.ca_path = ca_path
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)

        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_error: Optional[str] = None
        self.connection_failed_count = 0

    async def connect(self) -> bool:
        """Create aiohttp session."""
        try:
            # Configure SSL context
            ssl_context = ssl.create_default_context()
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED

            if self.ca_path:
                ssl_context.load_verify_locations(self.ca_path)

            # Create connector with SSL
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=10,  # Connection pool size
                limit_per_host=5,
            )

            # Create session
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=self.timeout,
            )

            logger.info(f"HTTPS session created for {self.endpoint}")
            return True

        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Session creation failed: {e}")
            return False

    async def disconnect(self) -> None:
        """Close aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("HTTPS session closed")

    async def upload(
        self,
        payload: Dict[str, Any],
        endpoint_path: str = "/readings",
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload meter readings via HTTPS.

        Args:
            payload: CloudPayload dict to upload
            endpoint_path: API endpoint path (e.g., /readings)

        Returns:
            Tuple of (success: bool, response_message: str or None)
        """
        if not self.session:
            self.last_error = "Session not connected"
            logger.warning(self.last_error)
            return False, self.last_error

        url = f"{self.endpoint}{endpoint_path}"
        max_retries = len(self.BACKOFF_MS)

        for attempt in range(max_retries):
            try:
                # Prepare headers
                headers = {
                    "Authorization": f"Bearer {self.oauth2_token}",
                    "Content-Type": "application/json",
                    "User-Agent": f"MeterHub/1.0.0 ({self.device_id})",
                }

                # Serialize payload
                payload_json = json.dumps(payload)
                payload_bytes = payload_json.encode("utf-8")

                # POST request
                async with self.session.post(
                    url,
                    data=payload_bytes,
                    headers=headers,
                ) as response:
                    if response.status in (200, 201, 202):
                        # Success
                        response_data = await response.json()
                        logger.debug(
                            f"Upload successful: {response.status} " f"({len(payload_bytes)} bytes)"
                        )
                        return True, response_data.get("message")

                    elif response.status == 401:
                        # Authentication error
                        self.last_error = "Authentication failed (invalid token)"
                        logger.error(self.last_error)
                        return False, self.last_error

                    elif response.status == 413:
                        # Payload too large
                        self.last_error = "Payload too large"
                        logger.error(self.last_error)
                        return False, self.last_error

                    else:
                        # Server error or rate limit
                        raise RuntimeError(f"HTTP {response.status}: {await response.text()}")

            except asyncio.TimeoutError:
                logger.warning(f"Upload timeout (attempt {attempt + 1}/{max_retries})")
                self.last_error = "Request timeout"

                if attempt < max_retries - 1:
                    await asyncio.sleep(self.BACKOFF_MS[attempt] / 1000.0)

            except aiohttp.ClientSSLError as e:
                # TLS/certificate error
                self.last_error = f"SSL error: {e}"
                logger.error(self.last_error)
                return False, self.last_error

            except aiohttp.ClientConnectorError as e:
                # Connection error
                logger.warning(f"Connection error (attempt {attempt + 1}/{max_retries}): {e}")
                self.last_error = str(e)

                if attempt < max_retries - 1:
                    await asyncio.sleep(self.BACKOFF_MS[attempt] / 1000.0)

            except Exception as e:
                logger.error(f"Upload error: {e}")
                self.last_error = str(e)

                if attempt < max_retries - 1:
                    await asyncio.sleep(self.BACKOFF_MS[attempt] / 1000.0)

        self.connection_failed_count += 1
        return False, self.last_error

    async def heartbeat(self) -> bool:
        """Send heartbeat to HTTPS endpoint (health check)."""
        heartbeat_payload = {
            "device_id": self.device_id,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "status": "online",
        }

        success, msg = await self.upload(heartbeat_payload, "/heartbeat")
        return success

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()
