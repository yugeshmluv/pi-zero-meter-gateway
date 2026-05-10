"""
Main entry point for MeterHub Uploader Service

Store-and-forward uploader: batches readings from SQLite and ships to cloud.
Primary path: MQTT TLS (HiveMQ Cloud / AWS IoT Core)
Fallback path: HTTPS (triggered after 15 min MQTT failure)

Manages persistent queue for 7-day cloud outage survivability.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def main():
    """Main uploader loop (to be implemented in Phase 3)."""
    logger.info("MeterHub Uploader Service starting...")
    # Phase 3: Implement MQTT + HTTPS fallback
    while True:
        await asyncio.sleep(300)  # Upload every 5 min


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
