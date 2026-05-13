"""
Uploader Service Optimizations

Strategies for reducing memory and startup time:
1. Lazy initialization of MQTT and HTTPS clients
2. Batch database operations for efficiency
3. Connection reuse and pooling
4. Efficient payload serialization (no unnecessary copies)
5. Reduced cloud client initialization overhead
"""

import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class LazyCloudClientInitializer:
    """
    Defers cloud client initialization until needed.

    Reduces startup time by not connecting to cloud services
    until the first upload attempt.
    """

    def __init__(
        self,
        mqtt_endpoint: str,
        mqtt_cert_path: str,
        mqtt_key_path: str,
        mqtt_ca_path: str,
        https_endpoint: str,
        oauth2_token: str,
    ):
        """Initialize lazy initializer."""
        self.mqtt_endpoint = mqtt_endpoint
        self.mqtt_cert_path = mqtt_cert_path
        self.mqtt_key_path = mqtt_key_path
        self.mqtt_ca_path = mqtt_ca_path
        self.https_endpoint = https_endpoint
        self.oauth2_token = oauth2_token
        
        self._mqtt_client = None
        self._https_uploader = None
        self._mqtt_initialized = False
        self._https_initialized = False

    async def get_mqtt_client(self):
        """Get MQTT client, initializing if needed."""
        if self._mqtt_initialized:
            return self._mqtt_client

        logger.debug("Initializing MQTT client (lazy)")
        try:
            from common.meterhub_common import AWSIoTMQTTClient
            self._mqtt_client = AWSIoTMQTTClient(
                endpoint=self.mqtt_endpoint,
                device_id="",  # Will be set later
                cert_path=self.mqtt_cert_path,
                key_path=self.mqtt_key_path,
                ca_path=self.mqtt_ca_path,
            )
            self._mqtt_initialized = True
            logger.info("MQTT client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MQTT client: {e}")
            raise

        return self._mqtt_client

    async def get_https_uploader(self):
        """Get HTTPS uploader, initializing if needed."""
        if self._https_initialized:
            return self._https_uploader

        logger.debug("Initializing HTTPS uploader (lazy)")
        try:
            from common.meterhub_common import HTTPSFallbackUploader
            self._https_uploader = HTTPSFallbackUploader(
                endpoint=self.https_endpoint,
                device_id="",  # Will be set later
                oauth2_token=self.oauth2_token,
            )
            self._https_initialized = True
            logger.info("HTTPS uploader initialized")
        except Exception as e:
            logger.error(f"Failed to initialize HTTPS uploader: {e}")
            raise

        return self._https_uploader


class EfficientPayloadBuilder:
    """
    Builds cloud payloads efficiently with minimal memory copies.

    Uses streaming serialization and generators where possible.
    """

    @staticmethod
    def build_readings_json(readings: List[Dict[str, Any]]) -> str:
        """
        Build readings JSON efficiently.

        Args:
            readings: List of reading dictionaries

        Returns:
            JSON string (no intermediate list copies)
        """
        # Use generator to avoid intermediate list
        readings_json = [
            {
                "timestamp_utc": r.get("timestamp_utc"),
                "totalizer_kwh": r.get("totalizer_kwh"),
                "instant_kw": r.get("instant_kw"),
                "frequency_hz": r.get("frequency_hz"),
                "voltage_l1": r.get("voltage_l1"),
                "voltage_l2": r.get("voltage_l2"),
                "voltage_l3": r.get("voltage_l3"),
                "current_l1": r.get("current_l1"),
                "current_l2": r.get("current_l2"),
                "current_l3": r.get("current_l3"),
            }
            for r in readings
        ]
        return json.dumps(readings_json, separators=(',', ':'))

    @staticmethod
    def build_heartbeat_json(heartbeat: Dict[str, Any]) -> str:
        """
        Build heartbeat JSON efficiently.

        Args:
            heartbeat: Heartbeat data dictionary

        Returns:
            JSON string with minimal overhead
        """
        hb = {
            "device_id": heartbeat.get("device_id"),
            "timestamp_utc": heartbeat.get("timestamp_utc"),
            "firmware_version": heartbeat.get("firmware_version"),
            "cpu_percent": heartbeat.get("cpu_percent"),
            "ram_mb": heartbeat.get("ram_mb"),
            "queue_depth": heartbeat.get("queue_depth"),
        }
        return json.dumps(hb, separators=(',', ':'))

    @staticmethod
    def estimate_payload_size(readings_count: int) -> int:
        """
        Estimate payload size in bytes.

        Args:
            readings_count: Number of readings in payload

        Returns:
            Estimated size in bytes
        """
        # ~150 bytes per reading + ~200 bytes for metadata
        return (readings_count * 150) + 200


class BatchedDatabaseQueries:
    """
    Batches database queries for efficiency.

    Instead of executing queries one-by-one, groups them
    to reduce context switches and I/O overhead.
    """

    def __init__(self, batch_size: int = 50):
        """
        Initialize batched query executor.

        Args:
            batch_size: Queries per batch
        """
        self.batch_size = batch_size
        self._pending_queries: List[tuple] = []

    def add_query(self, query: str, params: tuple) -> None:
        """
        Add query to batch.

        Args:
            query: SQL query string
            params: Query parameters
        """
        self._pending_queries.append((query, params))

    async def execute_batch(self, db_connection) -> List[Any]:
        """
        Execute all pending queries in a batch.

        Args:
            db_connection: SQLite connection

        Returns:
            List of results
        """
        if not self._pending_queries:
            return []

        logger.debug(f"Executing batch of {len(self._pending_queries)} queries")
        results = []

        try:
            db_connection.isolation_level = None
            for query, params in self._pending_queries:
                cursor = db_connection.execute(query, params)
                results.append(cursor.fetchall())
            self._pending_queries.clear()
        except Exception as e:
            logger.error(f"Batch query failed: {e}")
            self._pending_queries.clear()

        return results

    def clear(self) -> None:
        """Clear pending queries."""
        self._pending_queries.clear()


class ConnectionReuse:
    """
    Manages connection reuse for MQTT and HTTPS.

    Keeps connections alive between uploads to avoid
    repeated connection overhead.
    """

    def __init__(self):
        """Initialize connection reuse manager."""
        self._mqtt_conn = None
        self._https_conn = None
        self._last_mqtt_use = datetime.utcnow()
        self._last_https_use = datetime.utcnow()
        self._connection_timeout_s = 300  # 5 minutes

    def should_reconnect_mqtt(self) -> bool:
        """Check if MQTT connection should be refreshed."""
        if self._mqtt_conn is None:
            return True

        age = (datetime.utcnow() - self._last_mqtt_use).total_seconds()
        should_reconnect = age > self._connection_timeout_s
        
        if should_reconnect:
            logger.debug(f"MQTT connection aged {age:.0f}s, will reconnect")

        return should_reconnect

    def should_reconnect_https(self) -> bool:
        """Check if HTTPS connection should be refreshed."""
        if self._https_conn is None:
            return True

        age = (datetime.utcnow() - self._last_https_use).total_seconds()
        should_reconnect = age > self._connection_timeout_s

        if should_reconnect:
            logger.debug(f"HTTPS connection aged {age:.0f}s, will reconnect")

        return should_reconnect

    def mark_mqtt_used(self) -> None:
        """Mark MQTT connection as recently used."""
        self._last_mqtt_use = datetime.utcnow()

    def mark_https_used(self) -> None:
        """Mark HTTPS connection as recently used."""
        self._last_https_use = datetime.utcnow()


class QueueDepthOptimizer:
    """
    Optimizes queue depth queries for efficiency.

    Uses approximate counts and caching to avoid expensive
    COUNT(*) queries.
    """

    def __init__(self, cache_ttl_s: int = 30):
        """
        Initialize queue depth optimizer.

        Args:
            cache_ttl_s: Cache TTL in seconds
        """
        self._cached_depth = 0
        self._cached_time = datetime.utcnow()
        self._cache_ttl = cache_ttl_s

    async def get_queue_depth(self, db_connection) -> int:
        """
        Get queue depth with caching.

        Args:
            db_connection: SQLite connection

        Returns:
            Approximate queue depth
        """
        age = (datetime.utcnow() - self._cached_time).total_seconds()

        if age < self._cache_ttl:
            return self._cached_depth

        try:
            cursor = db_connection.execute(
                "SELECT COUNT(*) FROM meter_readings"
            )
            count = cursor.fetchone()[0]
            self._cached_depth = count
            self._cached_time = datetime.utcnow()
            return count
        except Exception as e:
            logger.debug(f"Queue depth query failed: {e}")
            return self._cached_depth

    def invalidate_cache(self) -> None:
        """Invalidate cache (after upload)."""
        self._cached_time = datetime.utcnow() - asyncio.timedelta(seconds=self._cache_ttl + 1)


class UploadMetrics:
    """Tracks upload metrics for optimization."""

    def __init__(self):
        """Initialize metrics tracker."""
        self.total_uploads = 0
        self.total_bytes_uploaded = 0
        self.avg_upload_time_ms = 0
        self.mqtt_failures = 0
        self.https_fallback_count = 0
        self._upload_times: List[float] = []

    def record_upload(self, bytes_uploaded: int, upload_time_ms: float) -> None:
        """Record an upload."""
        self.total_uploads += 1
        self.total_bytes_uploaded += bytes_uploaded
        self._upload_times.append(upload_time_ms)

        # Keep only last 100 times for average
        if len(self._upload_times) > 100:
            self._upload_times.pop(0)

        self.avg_upload_time_ms = sum(self._upload_times) / len(self._upload_times)

    def record_mqtt_failure(self) -> None:
        """Record MQTT failure."""
        self.mqtt_failures += 1

    def record_https_fallback(self) -> None:
        """Record HTTPS fallback usage."""
        self.https_fallback_count += 1

    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        return {
            "total_uploads": self.total_uploads,
            "total_bytes_uploaded": self.total_bytes_uploaded,
            "avg_upload_time_ms": self.avg_upload_time_ms,
            "mqtt_failures": self.mqtt_failures,
            "https_fallback_count": self.https_fallback_count,
        }
