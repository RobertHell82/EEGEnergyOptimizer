"""Shared test fixtures for EEG Energy Optimizer."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.services.async_call = AsyncMock(return_value=None)
    hass.data = {}
    return hass
