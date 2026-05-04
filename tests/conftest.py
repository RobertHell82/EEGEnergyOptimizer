"""Shared test fixtures for EEG Energy Optimizer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_DISCHARGE_START_TIME,
)
from custom_components.eeg_energy_optimizer.optimizer import (
    EEGOptimizer,
    Snapshot,
)


# ---------------------------------------------------------------------------
# Module-level helpers (shared between test_optimizer.py and test_dual_window.py)
# ---------------------------------------------------------------------------
# Diese Helpers wurden ursprünglich in tests/test_optimizer.py definiert und
# nach hier extrahiert, damit Phase-11-Tests (test_dual_window.py) sie ohne
# Cross-Import aus einem Test-Modul nutzen können. Sie sind bewusst KEINE
# pytest-Fixtures, weil sie parametrisierbar sein müssen (Snapshot-Werte
# variieren pro Test-Methode).

def _make_config(**overrides):
    """Create a minimal optimizer config dict.

    Test-Default: discharge_start_time="20:00" — die meisten Bestands-Tests
    wurden gegen diesen alten Wert geschrieben und prüfen Pre-Midnight-
    Verhalten (z.B. now=21:00 → Fenster offen). Tests, die das neue 01:00-
    Verhalten verifizieren, überschreiben den Wert explizit.
    """
    base = {
        CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
        CONF_BATTERY_CAPACITY_SENSOR: "",
        CONF_BATTERY_CAPACITY_KWH: 10.0,
        CONF_DISCHARGE_START_TIME: "20:00",
    }
    base.update(overrides)
    return base


def _make_snapshot(**overrides):
    """Create a Snapshot with sensible defaults for testing."""
    now = overrides.pop("now", datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc))
    defaults = dict(
        now=now,
        battery_soc=50.0,
        battery_capacity_kwh=10.0,
        pv_remaining_today_kwh=20.0,
        pv_tomorrow_kwh=25.0,
        consumption_today_kwh=10.0,
        consumption_to_sunset_kwh=8.0,
        consumption_tomorrow_kwh=12.0,
        consumption_overnight_kwh=3.0,
        consumption_today_daylight_kwh=7.0,
        consumption_tomorrow_daylight_kwh=9.0,
        sunrise=now.replace(hour=5, minute=30),
        sunset=now.replace(hour=20, minute=30),
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider, config=None):
    """Create an EEGOptimizer instance with mocks."""
    cfg = config or _make_config()
    return EEGOptimizer(
        mock_hass,
        "test_entry_id",
        cfg,
        mock_inverter,
        mock_coordinator,
        mock_provider,
    )


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
