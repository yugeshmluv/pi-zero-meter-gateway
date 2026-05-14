"""
MeterHub Performance & Optimization Module

Comprehensive performance profiling and optimization strategies for:
- Memory footprint reduction
- Startup time optimization
- Power consumption minimization
- Resource monitoring and tracking

Components:
- performance_profiler: Startup timing and resource tracking
- acquisition_optimizations: Acquisition service-specific optimizations
- uploader_optimizations: Uploader service-specific optimizations
- ui_optimizations: Installer UI service-specific optimizations
- power_optimization: Power consumption management and monitoring
"""

__all__ = [
    "PerformanceProfiler",
    "ProfileCache",
    "LazyModbusClient",
    "SQLiteConnectionPool",
    "LazyCloudClientInitializer",
    "EfficientPayloadBuilder",
    "LazyFastAPIApp",
    "TemplateCache",
    "QRCodeGeneratorOptimized",
    "NetworkScanCache",
    "PowerManager",
    "PollingIntervalOptimizer",
    "PowerConsumptionMonitor",
]

from .performance_profiler import (
    PerformanceProfiler,
    ModbusOperationTimer,
    DatabaseOperationTimer,
    NetworkLatencyMeasurer,
    estimate_power_consumption,
)

from .acquisition_optimizations import (
    ProfileCache,
    LazyModbusClient,
    SQLiteConnectionPool,
    OptimizedLogging,
    AsyncTaskOptimizer,
    optimize_memory_usage,
    enable_memory_tracking,
)

from .uploader_optimizations import (
    LazyCloudClientInitializer,
    EfficientPayloadBuilder,
    BatchedDatabaseQueries,
    ConnectionReuse,
    QueueDepthOptimizer,
    UploadMetrics,
)

from .ui_optimizations import (
    LazyFastAPIApp,
    TemplateCache,
    QRCodeGeneratorOptimized,
    NetworkScanCache,
    ModuleImportOptimizer,
    MemoryEfficientProvisioning,
    UIResourceMonitor,
)

from .power_optimization import (
    PowerManager,
    PollingIntervalOptimizer,
    DatabaseTransactionOptimizer,
    PowerConsumptionMonitor,
)
