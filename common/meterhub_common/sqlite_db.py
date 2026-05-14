"""
SQLite Database Integration for MeterHub Acquisition

Implements crash-safe dual-database strategy:
- telemetry.db: Performance-optimized (PRAGMA synchronous=NORMAL), 7-day queue
- state.db: Crash-safe billing data (PRAGMA synchronous=FULL), persistent

Both use WAL (Write-Ahead Logging) for atomicity and recovery.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
import logging
from types import TracebackType

logger = logging.getLogger(__name__)


class SQLiteWALDatabase:
    """SQLite database with WAL mode and crash safety."""

    def __init__(self, db_path: str, synchronous: str = "NORMAL") -> None:
        """
        Initialize SQLite database with WAL mode.

        Args:
            db_path: Path to .db file
            synchronous: "NORMAL" (faster, 7-day queue) or "FULL" (crash-safe billing)
        """
        self.db_path = db_path
        self.synchronous = synchronous  # NORMAL or FULL
        self.connection: sqlite3.Connection | None

    def connect(self) -> None:
        """Open connection and configure WAL mode."""
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,  # 30 second lock timeout
        )

        # Enable WAL mode for crash safety
        self.connection.execute("PRAGMA journal_mode=WAL")

        # Set synchronous level
        # NORMAL: Good balance (fsync after every commit, not per write)
        # FULL: Maximum safety (fsync per write, slower)
        self.connection.execute(f"PRAGMA synchronous={self.synchronous}")

        # Cache size (negative = memory MB)
        self.connection.execute("PRAGMA cache_size=-2000")  # 2GB

        # Foreign keys
        self.connection.execute("PRAGMA foreign_keys=ON")

        logger.info(f"SQLite connected: {self.db_path} (WAL, synchronous={self.synchronous})")

    def disconnect(self) -> None:
        """Close connection and checkpoint WAL."""
        if self.connection:
            # Checkpoint WAL (merge WAL into main db)
            self.connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
            self.connection.close()
            self.connection = None
            logger.info(f"SQLite disconnected: {self.db_path}")

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> sqlite3.Cursor:
        """Execute SQL statement."""
        if not self.connection:
            raise RuntimeError("Database not connected")
        if params:
            return self.connection.execute(sql, params)
        return self.connection.execute(sql)

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> sqlite3.Cursor:
        """Execute multiple SQL statements."""
        if not self.connection:
            raise RuntimeError("Database not connected")
        return self.connection.executemany(sql, params)

    def commit(self) -> None:
        """Commit transaction."""
        if self.connection:
            self.connection.commit()

    def rollback(self) -> None:
        """Rollback transaction."""
        if self.connection:
            self.connection.rollback()

    def __enter__(self) -> "SQLiteWALDatabase":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Context manager exit."""
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.disconnect()


class TelemetryDatabase:
    """
    Performance-optimized telemetry storage (NORMAL sync).

    Stores:
    - Meter readings (1-minute snapshots)
    - Heartbeats (5-minute system health)
    - 7-day rolling queue (auto-delete old records)
    """

    def __init__(self, db_path: str = "/var/cache/meterhub/telemetry.db") -> None:
        """Initialize telemetry database."""
        self.db = SQLiteWALDatabase(db_path, synchronous="NORMAL")
        self.retention_days = 7

    def initialize_schema(self) -> None:
        """Create telemetry schema."""
        self.db.connect()

        # Meter readings table (1-minute snapshots)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS meter_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc DATETIME NOT NULL,
                totalizer_kwh REAL NOT NULL,
                instant_kw REAL NOT NULL,
                frequency_hz REAL,
                voltage_l1 REAL,
                voltage_l2 REAL,
                voltage_l3 REAL,
                current_l1 REAL,
                current_l2 REAL,
                current_l3 REAL,
                pf_total REAL,
                modbus_retry_count INTEGER,
                meter_online BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

        # Heartbeats table (5-minute system health)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS heartbeats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                society_id TEXT NOT NULL,
                panel_id TEXT NOT NULL,
                timestamp_utc DATETIME NOT NULL,
                firmware_version TEXT,
                uptime_seconds INTEGER,
                cpu_percent REAL,
                ram_mb INTEGER,
                temperature_c REAL,
                disk_free_mb INTEGER,
                mqtt_connected BOOLEAN,
                queue_depth INTEGER,
                last_meter_read_age_seconds INTEGER,
                sd_writes_mb_today REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

        # Create indices for fast queries
        idx1 = "CREATE INDEX IF NOT EXISTS idx_readings_ts"
        idx1 += " ON meter_readings(timestamp_utc DESC)"
        idx2 = "CREATE INDEX IF NOT EXISTS idx_heartbeats_ts"
        idx2 += " ON heartbeats(timestamp_utc DESC)"
        self.db.execute(idx1)
        self.db.execute(idx2)

        self.db.commit()
        logger.info("Telemetry schema initialized")

    def insert_reading(self, reading: dict[str, Any]) -> None:
        """Insert meter reading."""
        self.db.execute(
            """
            INSERT INTO meter_readings (
                timestamp_utc, totalizer_kwh, instant_kw, frequency_hz,
                voltage_l1, voltage_l2, voltage_l3,
                current_l1, current_l2, current_l3,
                pf_total, modbus_retry_count, meter_online
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading["timestamp_utc"],
                reading["totalizer_kwh"],
                reading["instant_kw"],
                reading.get("frequency_hz"),
                reading.get("voltage_l1"),
                reading.get("voltage_l2"),
                reading.get("voltage_l3"),
                reading.get("current_l1"),
                reading.get("current_l2"),
                reading.get("current_l3"),
                reading.get("pf_total"),
                reading.get("modbus_retry_count"),
                reading.get("meter_online", True),
            ),
        )
        self.db.commit()

    def cleanup_old_readings(self) -> None:
        """Delete readings older than retention period."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
        self.db.execute(
            "DELETE FROM meter_readings WHERE timestamp_utc < ?",
            (cutoff_date.isoformat(),),
        )
        deleted = self.db.connection.total_changes
        if deleted > 0:
            logger.debug(f"Deleted {deleted} old readings")
        self.db.commit()


class StateDatabase:
    """
    Crash-safe billing data storage (FULL sync).

    Stores:
    - Last successful totalizer reading (billing register)
    - Device configuration state
    - OTA update status
    - Crash-resistant with FULL synchronous mode
    """

    def __init__(self, db_path: str = "/var/lib/meterhub/state.db") -> None:
        """Initialize state database."""
        self.db = SQLiteWALDatabase(db_path, synchronous="FULL")

    def initialize_schema(self) -> None:
        """Create state schema."""
        self.db.connect()

        # Billing state (single row, immutable updates)
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS billing_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_totalizer_kwh REAL NOT NULL,
                last_totalizer_timestamp DATETIME NOT NULL,
                last_update_utc DATETIME DEFAULT CURRENT_TIMESTAMP,
                device_id TEXT,
                checksum TEXT DEFAULT NULL
            )
            """)

        # Device config state
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS device_config (
                device_id TEXT PRIMARY KEY,
                society_id TEXT,
                panel_id TEXT,
                meter_profile TEXT,
                cloud_endpoint TEXT,
                last_update_utc DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

        # OTA state
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS ota_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                current_version TEXT,
                pending_version TEXT DEFAULT NULL,
                ota_status TEXT DEFAULT 'idle',
                last_update_utc DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

        self.db.commit()
        logger.info("State schema initialized")

    def get_last_billing_state(self) -> dict[str, Any] | None:
        """Get last recorded billing totalizer."""
        query = "SELECT last_totalizer_kwh, last_totalizer_timestamp"
        query += " FROM billing_state WHERE id = 1"
        cursor = self.db.execute(query)
        row = cursor.fetchone()
        if row:
            return {
                "totalizer_kwh": row[0],
                "timestamp": row[1],
            }
        return None

    def update_billing_state(self, totalizer_kwh: float, timestamp: datetime) -> None:
        """
        Update billing totalizer (crash-safe).

        Uses INSERT OR REPLACE for atomic update.
        """
        # Get current device_id from config
        cursor = self.db.execute("SELECT device_id FROM device_config LIMIT 1")
        row = cursor.fetchone()
        device_id = row[0] if row else "unknown"

        self.db.execute(
            """INSERT OR REPLACE INTO billing_state
            (id, last_totalizer_kwh, last_totalizer_timestamp, device_id)
            VALUES (1, ?, ?, ?)""",
            (totalizer_kwh, timestamp.isoformat(), device_id),
        )
        self.db.commit()
        logger.debug(f"Billing state updated: {totalizer_kwh} kWh @ {timestamp}")


# Convenience functions for initialization
def initialize_databases(
    telemetry_path: str = "/var/cache/meterhub/telemetry.db",
    state_path: str = "/var/lib/meterhub/state.db",
) -> tuple[Any, ...]:
    """Initialize both databases."""
    # Create directories
    Path(telemetry_path).parent.mkdir(parents=True, exist_ok=True)
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)

    # Initialize
    telem = TelemetryDatabase(telemetry_path)
    telem.initialize_schema()

    state = StateDatabase(state_path)
    state.initialize_schema()

    logger.info(f"Databases initialized: {telemetry_path}, {state_path}")

    return telem, state
