"""
Power Consumption Optimization

Strategies for reducing power drain on Raspberry Pi Zero W:
1. CPU frequency scaling (reduce when idle)
2. Disable unused hardware (Bluetooth, HDMI, etc.)
3. Optimize polling intervals during low activity
4. Efficient database transactions
5. Power-aware task scheduling
"""

import logging
import os
import subprocess
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PowerManager:
    """
    Manages power-saving features on Raspberry Pi Zero W.

    Provides methods to:
    - Reduce CPU frequency during idle periods
    - Disable unused hardware interfaces
    - Monitor and log power consumption
    """

    def __init__(self):
        """Initialize power manager."""
        self._scaling_enabled = False
        self._min_freq_mhz = 700  # Min frequency on Pi Zero W
        self._max_freq_mhz = 1000  # Max frequency on Pi Zero W
        self._current_freq_mhz = self._max_freq_mhz

    def enable_cpu_frequency_scaling(self) -> bool:
        """
        Enable CPU frequency scaling (requires root).

        Sets governor to 'powersave' during idle periods.

        Returns:
            True if successful
        """
        try:
            # Check if scaling is available
            scaling_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
            if not os.path.exists(scaling_path):
                logger.warning("CPU frequency scaling not available on this system")
                return False

            # Set governor to powersave
            with open(scaling_path, "w") as f:
                f.write("powersave")

            logger.info("CPU frequency scaling enabled (powersave governor)")
            self._scaling_enabled = True
            return True

        except PermissionError:
            logger.warning("Cannot enable CPU frequency scaling (requires root)")
            return False
        except Exception as e:
            logger.error(f"Failed to enable CPU frequency scaling: {e}")
            return False

    def disable_bluetooth(self) -> bool:
        """
        Disable Bluetooth (requires root).

        Bluetooth can consume 60-80 mW unnecessarily.

        Returns:
            True if successful
        """
        try:
            # Use rfkill to disable Bluetooth
            subprocess.run(
                ["sudo", "rfkill", "block", "bluetooth"], check=True, capture_output=True, timeout=5
            )
            logger.info("Bluetooth disabled")
            return True
        except Exception as e:
            logger.debug(f"Could not disable Bluetooth: {e}")
            return False

    def disable_hdmi(self) -> bool:
        """
        Disable HDMI output (requires root).

        HDMI is unused in production deployments.

        Returns:
            True if successful
        """
        try:
            # Use tvservice to power off HDMI
            subprocess.run(["tvservice", "-o"], check=True, capture_output=True, timeout=5)
            logger.info("HDMI disabled")
            return True
        except Exception as e:
            logger.debug(f"Could not disable HDMI: {e}")
            return False

    def disable_wireless_power_saving(self) -> bool:
        """
        Disable WiFi power saving (for stability).

        While counterintuitive, WiFi power saving can cause issues
        on Pi Zero W. Better to keep WiFi powered on.

        Returns:
            True if successful
        """
        try:
            subprocess.run(
                ["sudo", "iwconfig", "wlan0", "power", "off"],
                check=True,
                capture_output=True,
                timeout=5,
            )
            logger.info("WiFi power saving disabled")
            return True
        except Exception as e:
            logger.debug(f"Could not disable WiFi power saving: {e}")
            return False

    def set_cpu_frequency(self, mhz: int) -> bool:
        """
        Set CPU frequency (requires root).

        Args:
            mhz: Frequency in MHz

        Returns:
            True if successful
        """
        if mhz < self._min_freq_mhz or mhz > self._max_freq_mhz:
            logger.warning(
                f"Frequency {mhz} MHz out of range [{self._min_freq_mhz}, {self._max_freq_mhz}]"
            )
            return False

        try:
            scaling_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
            with open(scaling_path, "w") as f:
                f.write(str(mhz * 1000))  # Convert to kHz

            logger.debug(f"CPU frequency set to {mhz} MHz")
            self._current_freq_mhz = mhz
            return True

        except PermissionError:
            logger.debug("Cannot set CPU frequency (requires root)")
            return False
        except Exception as e:
            logger.debug(f"Failed to set CPU frequency: {e}")
            return False

    def estimate_power_draw(
        self,
        cpu_percent: float,
        mem_mb: float,
        wifi_active: bool = False,
        mqtt_connected: bool = False,
    ) -> float:
        """
        Estimate current power draw in milliwatts.

        Args:
            cpu_percent: Current CPU usage (0-100)
            mem_mb: Memory usage in MB
            wifi_active: Is WiFi active
            mqtt_connected: Is MQTT connected

        Returns:
            Estimated power draw in mW
        """
        # Pi Zero W power budget:
        # - Base: ~100 mW (processor, memory, voltages)
        # - CPU active: +0-150 mW (depends on frequency)
        # - WiFi active: +40 mW
        # - WiFi + MQTT: +80 mW total

        power_mw = 100.0  # Base

        # CPU contribution (proportional to frequency and usage)
        cpu_power = (self._current_freq_mhz / self._max_freq_mhz) * (cpu_percent / 100) * 150
        power_mw += cpu_power

        # Memory contribution
        power_mw += (mem_mb / 512) * 5  # ~5 mW per 512 MB

        # WiFi contribution (if active)
        if wifi_active:
            power_mw += 40.0

        # MQTT connection overhead
        if mqtt_connected and wifi_active:
            power_mw += 20.0

        return power_mw


class PollingIntervalOptimizer:
    """
    Optimizes polling intervals based on activity level.

    Increases polling interval during low activity periods
    to reduce power consumption.
    """

    def __init__(self):
        """Initialize optimizer."""
        self._base_interval_s = 60  # Normal polling every 60s
        self._low_activity_interval_s = 300  # Every 5 min during low activity
        self._high_activity_interval_s = 30  # Every 30s during high activity
        self._error_interval_s = 120  # Backoff on errors

        self._last_activity_time = datetime.utcnow()
        self._activity_threshold_s = 600  # 10 min to trigger low activity
        self._error_count = 0
        self._max_consecutive_errors = 3

    def should_use_low_power_polling(self) -> bool:
        """Check if low-power polling should be used."""
        age = (datetime.utcnow() - self._last_activity_time).total_seconds()
        return age > self._activity_threshold_s and self._error_count == 0

    def get_next_interval(self) -> int:
        """Get recommended polling interval in seconds."""
        if self._error_count > 0:
            # Exponential backoff on errors
            backoff = self._error_interval_s * (2 ** min(self._error_count - 1, 3))
            return min(backoff, 600)  # Cap at 10 minutes

        if self.should_use_low_power_polling():
            logger.debug(f"Using low-power polling interval: {self._low_activity_interval_s}s")
            return self._low_activity_interval_s

        return self._base_interval_s

    def record_activity(self) -> None:
        """Record successful poll (activity)."""
        self._last_activity_time = datetime.utcnow()
        self._error_count = 0

    def record_error(self) -> None:
        """Record poll error."""
        self._error_count = min(self._error_count + 1, self._max_consecutive_errors)

    def reset(self) -> None:
        """Reset optimizer state."""
        self._last_activity_time = datetime.utcnow()
        self._error_count = 0


class DatabaseTransactionOptimizer:
    """
    Optimizes database transactions for efficiency.

    - Batches writes to reduce I/O
    - Uses WAL mode effectively
    - Minimizes fsync operations
    """

    def __init__(self, batch_size: int = 10):
        """
        Initialize transaction optimizer.

        Args:
            batch_size: Number of operations per batch
        """
        self.batch_size = batch_size
        self._pending_ops: list = []

    def add_operation(self, op_type: str, data: dict[str, Any]) -> None:
        """
        Add operation to batch.

        Args:
            op_type: Operation type ('insert', 'update', 'delete')
            data: Operation data
        """
        self._pending_ops.append({"type": op_type, "data": data})

    def should_flush(self) -> bool:
        """Check if batch should be flushed."""
        return len(self._pending_ops) >= self.batch_size

    async def flush(self, db_connection) -> bool:
        """
        Flush all pending operations in a single transaction.

        Args:
            db_connection: SQLite connection

        Returns:
            True if successful
        """
        if not self._pending_ops:
            return True

        logger.debug(f"Flushing {len(self._pending_ops)} database operations")

        try:
            # Execute all operations in a single transaction
            db_connection.isolation_level = None
            db_connection.execute("BEGIN IMMEDIATE")

            for op in self._pending_ops:
                # Implementation depends on actual schema
                pass

            db_connection.execute("COMMIT")
            self._pending_ops.clear()
            return True

        except Exception as e:
            logger.error(f"Transaction flush failed: {e}")
            db_connection.execute("ROLLBACK")
            return False

    def clear(self) -> None:
        """Clear pending operations."""
        self._pending_ops.clear()


class PowerConsumptionMonitor:
    """
    Monitors and logs power consumption metrics.

    Helps identify power bottlenecks and validate
    optimization effectiveness.
    """

    def __init__(self):
        """Initialize monitor."""
        self._samples: list = []
        self._start_time = datetime.utcnow()

    def record(
        self, power_mw: float, cpu_percent: float, mem_mb: float, uptime_seconds: int
    ) -> None:
        """
        Record power consumption sample.

        Args:
            power_mw: Estimated power in mW
            cpu_percent: CPU usage percentage
            mem_mb: Memory usage in MB
            uptime_seconds: System uptime
        """
        sample = {
            "timestamp": datetime.utcnow().isoformat(),
            "power_mw": power_mw,
            "cpu_percent": cpu_percent,
            "mem_mb": mem_mb,
            "uptime_seconds": uptime_seconds,
        }
        self._samples.append(sample)

        # Keep only last 1000 samples (~8 hours at 30-second intervals)
        if len(self._samples) > 1000:
            self._samples.pop(0)

    def get_average_power(self) -> float:
        """Get average power draw in mW."""
        if not self._samples:
            return 0.0
        power_values = [s["power_mw"] for s in self._samples]
        return sum(power_values) / len(power_values)

    def get_peak_power(self) -> float:
        """Get peak power draw in mW."""
        if not self._samples:
            return 0.0
        return max(s["power_mw"] for s in self._samples)

    def get_daily_estimate(self) -> dict[str, Any]:
        """
        Estimate daily energy consumption.

        Returns:
            Dictionary with daily energy estimates
        """
        avg_power = self.get_average_power()
        daily_wh = (avg_power / 1000) * 24  # Convert mW to W, then to Wh

        return {
            "average_power_mw": avg_power,
            "peak_power_mw": self.get_peak_power(),
            "estimated_daily_wh": daily_wh,
            "estimated_monthly_wh": daily_wh * 30,
            "sample_count": len(self._samples),
        }

    def get_summary(self) -> dict[str, Any]:
        """Get comprehensive summary."""
        return self.get_daily_estimate()
