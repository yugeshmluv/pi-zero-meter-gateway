"""
MeterHub Version Information
"""

__version__ = "1.2.0"
__status__ = "Phase 6: Image Builder & Security Hardening"
__release_date__ = "2026-05-12"
__author__ = "MeterHub Team"
__license__ = "Proprietary"

# Semantic versioning
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_PATCH = 0
VERSION_PRERELEASE = ""  # alpha, beta, rc, etc.

def get_version() -> str:
    """Return full version string."""
    version = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
    if VERSION_PRERELEASE:
        version += f"-{VERSION_PRERELEASE}"
    return version
