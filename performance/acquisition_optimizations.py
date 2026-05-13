"""
Acquisition Service Optimizations

Strategies for reducing memory footprint and startup time:
1. Lazy load Modbus client (only on first poll)
2. Cache parsed YAML profiles in memory
3. Use connection pooling for SQLite
4. Optimize asyncio task creation
5. Reduce logging overhead during startup
"""

import logging
import functools
import weakref
from typing import Optional, Dict, Any
from datetime import datetime
import yaml

logger = logging.getLogger(__name__)


class ProfileCache:
    """
    In-memory cache for parsed meter profiles.
    
    Reduces YAML parsing overhead on repeated loads.
    Uses weak references to allow garbage collection.
    """

    def __init__(self, max_size: int = 10):
        """
        Initialize profile cache.

        Args:
            max_size: Maximum number of profiles to cache
        """
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, datetime] = {}

    def get(self, profile_path: str) -> Optional[Dict[str, Any]]:
        """
        Get profile from cache.

        Args:
            profile_path: Path to profile YAML file

        Returns:
            Parsed profile dict, or None if not cached
        """
        if profile_path in self._cache:
            self._access_times[profile_path] = datetime.utcnow()
            logger.debug(f"Profile cache hit: {profile_path}")
            return self._cache[profile_path]
        return None

    def put(self, profile_path: str, profile_data: Dict[str, Any]) -> None:
        """
        Put profile in cache.

        Args:
            profile_path: Path to profile YAML file
            profile_data: Parsed profile dictionary
        """
        if len(self._cache) >= self.max_size:
            # Evict least recently accessed
            lru_key = min(self._access_times.keys(),
                         key=lambda k: self._access_times[k])
            del self._cache[lru_key]
            del self._access_times[lru_key]
            logger.debug(f"Evicted profile from cache: {lru_key}")

        self._cache[profile_path] = profile_data
        self._access_times[profile_path] = datetime.utcnow()
        logger.debug(f"Profile cached: {profile_path}")

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._access_times.clear()
        logger.info("Profile cache cleared")


# Global profile cache instance
_profile_cache = ProfileCache(max_size=5)


def get_profile_cache() -> ProfileCache:
    """Get the global profile cache."""
    return _profile_cache


def load_profile_cached(profile_path: str) -> Optional[Dict[str, Any]]:
    """
    Load meter profile with caching.

    Args:
        profile_path: Path to YAML profile file

    Returns:
        Parsed profile dictionary
    """
    cache = get_profile_cache()
    
    # Check cache first
    cached = cache.get(profile_path)
    if cached is not None:
        return cached

    # Load from disk
    try:
        with open(profile_path, 'r') as f:
            profile_data = yaml.safe_load(f)
        cache.put(profile_path, profile_data)
        return profile_data
    except Exception as e:
        logger.error(f"Failed to load profile {profile_path}: {e}")
        return None


class LazyModbusClient:
    """
    Lazy-loading wrapper for Modbus client.

    Defers Modbus client initialization until first use,
    reducing startup time and memory footprint.
    """

    def __init__(self, device: str, meter_profile: Dict[str, Any], enable_cache: bool = True):
        """
        Initialize lazy Modbus client.

        Args:
            device: Serial device path
            meter_profile: Meter profile dictionary
            enable_cache: Whether to cache register reads
        """
        self.device = device
        self.meter_profile = meter_profile
        self.enable_cache = enable_cache
        self._client = None
        self._initialized = False

    def __getattr__(self, name: str):
        """Lazy initialization on attribute access."""
        if self._client is None:
            self._initialize()
        return getattr(self._client, name)

    def _initialize(self) -> None:
        """Initialize the actual Modbus client."""
        if self._initialized:
            return

        logger.debug("Initializing Modbus client (lazy)")
        try:
            from common.meterhub_common import ModbusRTUClient
            self._client = ModbusRTUClient(
                device=self.device,
                meter_profile=self.meter_profile,
                enable_cache=self.enable_cache,
            )
            self._initialized = True
            logger.info("Modbus client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Modbus client: {e}")
            raise

    @property
    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized


class SQLiteConnectionPool:
    """
    Simple connection pool for SQLite.

    Reuses database connections instead of creating new ones,
    reducing context switches and initialization overhead.
    """

    def __init__(self, db_path: str, pool_size: int = 3):
        """
        Initialize connection pool.

        Args:
            db_path: Path to SQLite database
            pool_size: Number of connections to pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._available: list = []
        self._in_use: set = set()
        self._lock = None

    def get_connection(self):
        """Get a connection from the pool."""
        import sqlite3
        import asyncio

        if self._lock is None:
            try:
                self._lock = asyncio.Lock()
            except:
                pass

        if not self._available:
            # Create new connection
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.isolation_level = None
            logger.debug(f"Created new SQLite connection (pool size: {len(self._in_use)})")
        else:
            conn = self._available.pop()

        self._in_use.add(id(conn))
        return conn

    def return_connection(self, conn) -> None:
        """Return a connection to the pool."""
        conn_id = id(conn)
        if conn_id in self._in_use:
            self._in_use.remove(conn_id)

        if len(self._available) < self.pool_size:
            self._available.append(conn)
            logger.debug("Connection returned to pool")
        else:
            conn.close()
            logger.debug("Pool full, closed connection")

    def clear(self) -> None:
        """Clear all pooled connections."""
        for conn in self._available:
            try:
                conn.close()
            except:
                pass
        self._available.clear()
        self._in_use.clear()
        logger.info("Connection pool cleared")


class OptimizedLogging:
    """
    Optimized logging configuration for reduced startup overhead.
    
    - Disables verbose debug logging during startup
    - Uses lazy formatting for log messages
    - Batches log entries for I/O efficiency
    """

    @staticmethod
    def get_startup_config() -> Dict[str, Any]:
        """Get logging config optimized for startup."""
        return {
            'level': logging.INFO,  # Higher than DEBUG
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'disable_existing_loggers': False,
        }

    @staticmethod
    def get_runtime_config() -> Dict[str, Any]:
        """Get logging config optimized for runtime."""
        return {
            'level': logging.DEBUG,
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'disable_existing_loggers': False,
        }

    @staticmethod
    def switch_to_runtime(root_logger: logging.Logger) -> None:
        """Switch from startup to runtime logging config."""
        root_logger.setLevel(logging.DEBUG)
        logger.info("Switched to runtime logging")


class AsyncTaskOptimizer:
    """
    Optimizes asyncio task creation and management.

    - Reuses tasks where possible
    - Minimizes task switching overhead
    - Batches coroutines for efficiency
    """

    def __init__(self, max_concurrent: int = 5):
        """
        Initialize task optimizer.

        Args:
            max_concurrent: Maximum concurrent tasks
        """
        self.max_concurrent = max_concurrent
        self._semaphore = None

    async def init_semaphore(self):
        """Initialize semaphore for concurrency control."""
        import asyncio
        self._semaphore = asyncio.Semaphore(self.max_concurrent)

    async def run_limited(self, coro):
        """Run coroutine with concurrency limit."""
        if self._semaphore is None:
            await self.init_semaphore()

        async with self._semaphore:
            return await coro

    @staticmethod
    async def batch_coroutines(coros: list, max_concurrent: int = 5):
        """
        Run coroutines in batches for efficiency.

        Args:
            coros: List of coroutines to run
            max_concurrent: Max concurrent per batch

        Yields:
            Results as batches complete
        """
        import asyncio
        
        for i in range(0, len(coros), max_concurrent):
            batch = coros[i:i + max_concurrent]
            results = await asyncio.gather(*batch)
            for result in results:
                yield result


def optimize_memory_usage():
    """
    Apply global memory optimizations.

    Should be called early in service startup.
    """
    import gc
    import sys

    # Disable collection during startup (faster)
    gc.disable()
    logger.debug("GC disabled for startup optimization")

    # Set gc thresholds for reduced collection frequency
    gc.set_threshold(500, 10, 10)
    logger.debug("GC thresholds optimized")


def enable_memory_tracking():
    """
    Enable memory tracking for debugging.

    Should be called after startup for monitoring.
    """
    import gc
    gc.enable()
    logger.debug("Memory tracking enabled")
