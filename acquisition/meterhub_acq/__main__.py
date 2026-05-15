"""Executable module for ``python -m meterhub_acq``."""

import asyncio

from meterhub_acq.main import main


if __name__ == "__main__":
    asyncio.run(main())
