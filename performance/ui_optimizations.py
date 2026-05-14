"""
Installer UI Service Optimizations

Strategies for reducing memory and startup time:
1. Lazy load FastAPI and Uvicorn
2. Defer template compilation until needed
3. Optimize QR code generation (cache, reduce resolution)
4. Reduce imported modules at startup
5. Efficient network scanning (cached results)
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


class LazyFastAPIApp:
    """
    Lazy initialization of FastAPI application.

    Defers FastAPI and Uvicorn setup until the UI service
    actually needs to start, reducing startup time.
    """

    def __init__(self):
        """Initialize lazy app holder."""
        self._app = None
        self._initialized = False

    async def init_app(self, **config) -> Any:
        """
        Initialize FastAPI application.

        Args:
            **config: FastAPI configuration

        Returns:
            FastAPI application instance
        """
        if self._initialized:
            return self._app

        logger.debug("Initializing FastAPI app (lazy)")
        try:
            from fastapi import FastAPI
            from fastapi.responses import FileResponse

            self._app = FastAPI(
                title=config.get("title", "MeterHub Installer UI"),
                version=config.get("version", "1.0.0"),
            )
            self._initialized = True
            logger.info("FastAPI app initialized")
        except Exception as e:
            logger.error(f"Failed to initialize FastAPI app: {e}")
            raise

        return self._app

    def get_app(self) -> Any:
        """Get initialized app (raises if not initialized)."""
        if not self._initialized:
            raise RuntimeError("FastAPI app not initialized. Call init_app() first.")
        return self._app


class TemplateCache:
    """
    Caches compiled Jinja2 templates.

    Avoids repeated template parsing and compilation overhead.
    """

    def __init__(self, cache_size: int = 20):
        """
        Initialize template cache.

        Args:
            cache_size: Maximum templates to cache
        """
        self.cache_size = cache_size
        self._cache: dict[str, str] = {}
        self._access_times: dict[str, datetime] = {}

    def get(self, template_name: str) -> str | None:
        """
        Get cached template.

        Args:
            template_name: Template identifier

        Returns:
            Cached template string, or None
        """
        if template_name in self._cache:
            self._access_times[template_name] = datetime.utcnow()
            return self._cache[template_name]
        return None

    def put(self, template_name: str, template_content: str) -> None:
        """
        Cache a template.

        Args:
            template_name: Template identifier
            template_content: Template string content
        """
        if len(self._cache) >= self.cache_size:
            # LRU eviction
            lru_name = min(self._access_times.keys(), key=lambda k: self._access_times[k])
            del self._cache[lru_name]
            del self._access_times[lru_name]
            logger.debug(f"Evicted template from cache: {lru_name}")

        self._cache[template_name] = template_content
        self._access_times[template_name] = datetime.utcnow()
        logger.debug(f"Template cached: {template_name}")

    def clear(self) -> None:
        """Clear all cached templates."""
        self._cache.clear()
        self._access_times.clear()


class QRCodeGeneratorOptimized:
    """
    Optimized QR code generator with caching and reduced size.

    Caches generated QR codes to avoid regeneration overhead,
    and uses reduced resolution for faster generation.
    """

    def __init__(self, cache_size: int = 10):
        """
        Initialize optimized QR generator.

        Args:
            cache_size: Number of QR codes to cache
        """
        self.cache_size = cache_size
        self._cache: dict[str, bytes] = {}  # data -> PNG bytes
        self._access_times: dict[str, datetime] = {}

    def generate(self, data: str, version: int = 1, box_size: int = 5) -> bytes:
        """
        Generate QR code PNG with caching.

        Args:
            data: Data to encode
            version: QR code version (affects size, 1-40)
            box_size: Module size in pixels

        Returns:
            PNG image bytes
        """
        cache_key = f"{data}_{version}_{box_size}"

        if cache_key in self._cache:
            self._access_times[cache_key] = datetime.utcnow()
            logger.debug(f"QR code cache hit for {data[:20]}")
            return self._cache[cache_key]

        logger.debug(f"Generating QR code for {data[:20]}")
        try:
            import qrcode
            import io

            qr = qrcode.QRCode(
                version=version,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=box_size,
                border=1,
            )
            qr.add_data(data)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            png_buffer = io.BytesIO()
            img.save(png_buffer, format="PNG")
            png_bytes = png_buffer.getvalue()

            # Cache it
            if len(self._cache) >= self.cache_size:
                lru_key = min(self._access_times.keys(), key=lambda k: self._access_times[k])
                del self._cache[lru_key]
                del self._access_times[lru_key]

            self._cache[cache_key] = png_bytes
            self._access_times[cache_key] = datetime.utcnow()

            logger.debug(f"QR code generated and cached ({len(png_bytes)} bytes)")
            return png_bytes

        except Exception as e:
            logger.error(f"QR code generation failed: {e}")
            raise

    def clear_cache(self) -> None:
        """Clear QR code cache."""
        self._cache.clear()
        self._access_times.clear()


class NetworkScanCache:
    """
    Caches network scan results.

    Wi-Fi scanning is slow (~2 seconds). Cache results
    to avoid repeated scans in quick succession.
    """

    def __init__(self, cache_ttl_s: int = 30):
        """
        Initialize network scan cache.

        Args:
            cache_ttl_s: Cache TTL in seconds
        """
        self.cache_ttl = cache_ttl_s
        self._cached_networks: list[dict[str, Any]] | None = None
        self._cached_time: datetime | None = None

    def is_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._cached_networks is None:
            return False

        age = (datetime.utcnow() - self._cached_time).total_seconds()
        return age < self.cache_ttl

    def get(self) -> list[dict[str, Any]] | None:
        """Get cached networks if valid."""
        if self.is_valid():
            logger.debug("Network scan cache hit")
            return self._cached_networks
        return None

    def put(self, networks: list[dict[str, Any]]) -> None:
        """Cache network scan results."""
        self._cached_networks = networks
        self._cached_time = datetime.utcnow()
        logger.debug(f"Cached {len(networks)} networks")

    def invalidate(self) -> None:
        """Invalidate cache."""
        self._cached_time = None


class ModuleImportOptimizer:
    """
    Optimizes module imports for faster startup.

    Uses lazy imports for heavy modules (QR, networking, crypto)
    to defer their loading until actually needed.
    """

    _lazy_modules: dict[str, Any | None] = {
        "qrcode": None,
        "aiofiles": None,
        "cryptography": None,
        "yaml": None,
    }

    @classmethod
    def get_module(cls, module_name: str) -> Any:
        """
        Get a module, lazy-loading if needed.

        Args:
            module_name: Module name (from _lazy_modules)

        Returns:
            Imported module

        Raises:
            ImportError if module not available
        """
        if module_name not in cls._lazy_modules:
            raise ValueError(f"Unknown lazy module: {module_name}")

        if cls._lazy_modules[module_name] is None:
            logger.debug(f"Lazy-loading module: {module_name}")
            cls._lazy_modules[module_name] = __import__(module_name)

        return cls._lazy_modules[module_name]


class MemoryEfficientProvisioning:
    """
    Efficient provisioning state management.

    Uses minimal memory for state tracking and avoids
    unnecessary object allocations.
    """

    def __init__(self):
        """Initialize provisioning state."""
        self._state_dict: dict[str, Any] = {
            "status": "not_started",
            "step": 0,
            "device_id": None,
            "society_id": None,
            "panel_id": None,
            "wi_fi_ssid": None,
            "updated_at": datetime.utcnow().isoformat(),
        }

    def get_state(self) -> dict[str, Any]:
        """Get current state as dict."""
        return self._state_dict.copy()

    def update(self, **updates) -> None:
        """Update state fields."""
        for key, value in updates.items():
            if key in self._state_dict:
                self._state_dict[key] = value
        self._state_dict["updated_at"] = datetime.utcnow().isoformat()

    def get_memory_usage(self) -> int:
        """Estimate memory usage in bytes."""
        # Rough estimate: ~100 bytes per key-value pair
        return len(self._state_dict) * 100


class UIResourceMonitor:
    """
    Monitors UI resource usage and alerts on anomalies.

    Helps identify memory leaks and performance bottlenecks
    in the web UI service.
    """

    def __init__(self, threshold_mb: int = 100):
        """
        Initialize resource monitor.

        Args:
            threshold_mb: Memory warning threshold in MB
        """
        self.threshold_mb = threshold_mb
        self._snapshots: list[dict[str, Any]] = []
        self._max_memory = 0

    def snapshot(self) -> None:
        """Take a resource snapshot."""
        try:
            import psutil

            process = psutil.Process()
            mem_info = process.memory_info()
            memory_mb = mem_info.rss / (1024 * 1024)

            snap = {
                "timestamp": datetime.utcnow().isoformat(),
                "memory_mb": memory_mb,
                "cpu_percent": process.cpu_percent(interval=0.1),
                "open_files": process.num_fds() if hasattr(process, "num_fds") else 0,
            }

            self._snapshots.append(snap)
            self._max_memory = max(self._max_memory, memory_mb)

            if memory_mb > self.threshold_mb:
                logger.warning(
                    f"High memory usage: {memory_mb:.1f}MB (threshold: {self.threshold_mb}MB)"
                )

        except Exception as e:
            logger.debug(f"Resource snapshot failed: {e}")

    def get_peak_memory(self) -> float:
        """Get peak memory usage in MB."""
        return self._max_memory

    def get_recent_snapshots(self, count: int = 10) -> list[dict[str, Any]]:
        """Get recent snapshots."""
        return self._snapshots[-count:]
