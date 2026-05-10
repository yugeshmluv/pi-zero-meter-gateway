"""
Main entry point for MeterHub Acquisition Service

asyncio-based Modbus RTU polling loop.
Reads meter every polling_interval_seconds, writes to SQLite.

No external I/O (HTTP, MQTT, network): only Modbus + SQLite.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def main():
    """Main acquisition loop (to be implemented in Phase 2)."""
    logger.info("MeterHub Acquisition Service starting...")
    # Phase 2: Implement actual Modbus polling
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
