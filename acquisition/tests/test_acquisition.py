"""
Placeholder tests for acquisition service.

Phase 2 implementation will contain Modbus polling tests.
"""

import pytest


@pytest.mark.unit
def test_acquisition_import():
    """Test that acquisition package can be imported."""
    from acquisition.meterhub_acq import main
    assert main is not None
