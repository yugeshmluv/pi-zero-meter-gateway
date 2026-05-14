"""
Placeholder tests for uploader service.

Phase 3 implementation will contain MQTT/cloud upload tests.
"""

import pytest


@pytest.mark.unit
def test_uploader_import() -> None:
    """Test that uploader package can be imported."""
    from uploader.meterhub_uploader import main

    assert main is not None
