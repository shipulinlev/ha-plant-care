"""Core tests run without Home Assistant."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations() -> None:
    """Override the HA-only fixture from tests/conftest.py with a no-op."""
