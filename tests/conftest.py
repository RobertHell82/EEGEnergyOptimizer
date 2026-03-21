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


@pytest.fixture
def mock_inverter():
    """Create a mock inverter."""
    inv = MagicMock()
    inv.async_set_charge_limit = AsyncMock(return_value=True)
    inv.async_set_discharge = AsyncMock(return_value=True)
    inv.async_stop_forcible = AsyncMock(return_value=True)
    inv.is_available = True
    return inv


@pytest.fixture
def mock_coordinator():
    """Create a mock consumption coordinator."""
    coord = MagicMock()
    coord.calculate_period = MagicMock(
        return_value={"verbrauch_kwh": 3.0, "stunden": 8.0, "stundenprofil": []}
    )
    return coord


@pytest.fixture
def mock_provider():
    """Create a mock forecast provider."""
    from custom_components.eeg_energy_optimizer.forecast_provider import PVForecast

    provider = MagicMock()
    provider.get_forecast = MagicMock(
        return_value=PVForecast(remaining_today_kwh=20.0, tomorrow_kwh=25.0)
    )
    return provider
