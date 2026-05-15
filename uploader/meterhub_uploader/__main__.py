"""Executable module for ``python -m meterhub_uploader``."""

import asyncio
import logging

from meterhub_uploader.main import main


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
