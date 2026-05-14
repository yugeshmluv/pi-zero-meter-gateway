"""
MeterHub Performance Profiler

Measures startup time, memory footprint, and resource usage across services.
Used for identifying optimization opportunities and validating improvements.

Features:
- Startup time profiling (service initialization stages)
- Memory usage tracking (RSS, VMS, peak)
- CPU usage monitoring
- SQLite operation timing
- Modbus request timing
- Network latency (MQTT, HTTPS)
- Power consumption estimation
"""

import asyncio
import os
import sys
import time
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StartupMetric:
    """Single startup timing measurement."""

    stage: str
    duration_ms: float
    memory_mb: float
    cpu_percent: float
    timestamp: datetime


@dataclass
class ResourceSnapshot:
    """Snapshot of resource usage at a point in time."""

    timestamp: datetime
    memory_mb: float
    cpu_percent: float
    open_fds: int
    io_read_bytes: int
    io_write_bytes: int


class PerformanceProfiler:
    """Central profiler for MeterHub services."""

    def __init__(self, service_name: str = "meterhub"):
        """
        Initialize profiler.

        Args:
            service_name: Name of service being profiled
        """
        self.service_name = service_name
        self.process = psutil.Process(os.getpid())
        self.start_time = time.perf_counter()
        self.metrics: list[StartupMetric] = []
        self.snapshots: list[ResourceSnapshot] = []

    def mark_stage(self, stage_name: str) -> None:
        """Mark a startup stage completion."""
        elapsed = (time.perf_counter() - self.start_time) * 1000
        mem_info = self.process.memory_info()
        memory_mb = mem_info.rss / (1024 * 1024)

        try:
            cpu_percent = self.process.cpu_percent(interval=0.1)
        except:
            cpu_percent = 0.0

        metric = StartupMetric(
            stage=stage_name,
            duration_ms=elapsed,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            timestamp=datetime.utcnow(),
        )
        self.metrics.append(metric)
        logger.info(
            f"[{stage_name}] {elapsed:.1f}ms, "
            f"memory: {memory_mb:.1f}MB, "
            f"cpu: {cpu_percent:.1f}%"
        )

    def snapshot(self) -> ResourceSnapshot:
        """Take a resource snapshot."""
        mem_info = self.process.memory_info()
        memory_mb = mem_info.rss / (1024 * 1024)

        try:
            cpu_percent = self.process.cpu_percent(interval=0.05)
            open_fds = self.process.num_fds()
        except:
            cpu_percent = 0.0
            open_fds = 0

        try:
            io_counters = self.process.io_counters()
            io_read_bytes = io_counters.read_bytes
            io_write_bytes = io_counters.write_bytes
        except:
            io_read_bytes = 0
            io_write_bytes = 0

        snap = ResourceSnapshot(
            timestamp=datetime.utcnow(),
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            open_fds=open_fds,
            io_read_bytes=io_read_bytes,
            io_write_bytes=io_write_bytes,
        )
        self.snapshots.append(snap)
        return snap

    def get_peak_memory(self) -> float:
        """Get peak memory usage in MB."""
        if not self.metrics and not self.snapshots:
            return 0.0

        metric_mem = [m.memory_mb for m in self.metrics] if self.metrics else [0.0]
        snapshot_mem = [s.memory_mb for s in self.snapshots] if self.snapshots else [0.0]
        return max(metric_mem + snapshot_mem)

    def get_startup_duration(self) -> float:
        """Get total startup duration in milliseconds."""
        if not self.metrics:
            return 0.0
        return self.metrics[-1].duration_ms

    def report(self) -> dict:
        """Generate profiling report."""
        return {
            "service": self.service_name,
            "total_startup_ms": self.get_startup_duration(),
            "peak_memory_mb": self.get_peak_memory(),
            "stages": [
                {
                    "name": m.stage,
                    "duration_ms": m.duration_ms,
                    "memory_mb": m.memory_mb,
                    "cpu_percent": m.cpu_percent,
                }
                for m in self.metrics
            ],
            "snapshots_count": len(self.snapshots),
        }

    def log_report(self) -> None:
        """Log profiling report."""
        report = self.report()
        logger.info(f"\n=== Performance Report: {report['service']} ===")
        logger.info(f"Total startup: {report['total_startup_ms']:.1f}ms")
        logger.info(f"Peak memory: {report['peak_memory_mb']:.1f}MB")
        for stage in report["stages"]:
            logger.info(
                f"  {stage['name']:<30} "
                f"{stage['duration_ms']:>7.1f}ms "
                f"{stage['memory_mb']:>7.1f}MB"
            )


class ModbusOperationTimer:
    """Times individual Modbus operations."""

    def __init__(self, name: str = "modbus_op"):
        self.name = name
        self.start_time = None
        self.duration_ms = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000
        if self.duration_ms > 100:  # Log slow operations
            logger.warning(f"Slow {self.name}: {self.duration_ms:.1f}ms")


class DatabaseOperationTimer:
    """Times SQLite database operations."""

    def __init__(self, operation: str):
        self.operation = operation
        self.start_time = None
        self.duration_ms = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000
        if self.duration_ms > 50:  # Log slow DB operations
            logger.debug(f"DB {self.operation}: {self.duration_ms:.2f}ms")


class NetworkLatencyMeasurer:
    """Measures network latency for MQTT and HTTPS."""

    @staticmethod
    async def measure_mqtt_latency(endpoint: str, timeout_s: float = 5.0) -> float | None:
        """
        Measure MQTT connection latency.

        Returns:
            Latency in milliseconds, or None if failed
        """
        start = time.perf_counter()
        try:
            import socket

            host, port = endpoint.split(":") if ":" in endpoint else (endpoint, 8883)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_s)
            await asyncio.wait_for(
                asyncio.get_event_loop().sock_connect(sock, (host, int(port))), timeout=timeout_s
            )
            sock.close()
            elapsed = (time.perf_counter() - start) * 1000
            return elapsed
        except Exception as e:
            logger.debug(f"MQTT latency measure failed: {e}")
            return None

    @staticmethod
    async def measure_https_latency(endpoint: str, timeout_s: float = 5.0) -> float | None:
        """
        Measure HTTPS connection latency.

        Returns:
            Latency in milliseconds, or None if failed
        """
        start = time.perf_counter()
        try:
            import socket
            from urllib.parse import urlparse

            parsed = urlparse(endpoint)
            host = parsed.hostname or endpoint
            port = parsed.port or 443

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_s)
            await asyncio.wait_for(
                asyncio.get_event_loop().sock_connect(sock, (host, port)), timeout=timeout_s
            )
            sock.close()
            elapsed = (time.perf_counter() - start) * 1000
            return elapsed
        except Exception as e:
            logger.debug(f"HTTPS latency measure failed: {e}")
            return None


def estimate_power_consumption(
    cpu_percent: float, memory_mb: float, devices_active: dict[str, bool]
) -> float:
    """
    Estimate power consumption in milliwatts.

    Args:
        cpu_percent: Current CPU usage percentage
        memory_mb: Memory usage in MB
        devices_active: Dict of device states (uart, wifi, etc.)

    Returns:
        Estimated power in mW
    """
    # Pi Zero W base: ~100 mW idle
    base_power = 100.0

    # CPU contribution: ~150 mW at 100%
    cpu_power = (cpu_percent / 100.0) * 150.0

    # Memory contribution: ~10 mW per 100MB
    memory_power = (memory_mb / 100.0) * 10.0

    # Device contributions
    device_power = 0.0
    if devices_active.get("uart", False):
        device_power += 20.0  # UART: ~20 mW
    if devices_active.get("wifi", False):
        device_power += 80.0  # WiFi: ~80 mW
    if devices_active.get("bluetooth", False):
        device_power += 60.0  # Bluetooth: ~60 mW

    total = base_power + cpu_power + memory_power + device_power
    return total


if __name__ == "__main__":
    # Example usage
    profiler = PerformanceProfiler("example_service")

    profiler.mark_stage("initialization")
    time.sleep(0.1)

    profiler.mark_stage("load_config")
    time.sleep(0.05)

    profiler.mark_stage("connect_db")
    time.sleep(0.08)

    profiler.mark_stage("ready")

    profiler.log_report()
    print(profiler.report())
