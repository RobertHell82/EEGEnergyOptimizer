"""PV forecast provider abstraction for EEG Energy Optimizer.

Supports reading PV production forecasts from Solcast Solar and
Forecast.Solar HA integrations via entity state reads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


@dataclass
class PVForecast:
    """PV forecast data container."""

    remaining_today_kwh: float | None
    tomorrow_kwh: float | None


def _read_float(hass: HomeAssistant, entity_id: str) -> float | None:
    """Read a float value from an entity state.

    Returns None for missing, unavailable, unknown, or non-numeric states.
    """
    state = hass.states.get(entity_id)
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


class ForecastProvider:
    """Base class for PV forecast providers."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def get_forecast(self) -> PVForecast:
        """Return current PV forecast. Must be overridden."""
        raise NotImplementedError


class SolcastProvider(ForecastProvider):
    """Read PV forecasts from Solcast Solar HA integration."""

    def __init__(
        self, hass: HomeAssistant, remaining_entity: str, tomorrow_entity: str
    ) -> None:
        super().__init__(hass)
        self._remaining_id = remaining_entity
        self._tomorrow_id = tomorrow_entity

    def get_forecast(self) -> PVForecast:
        """Return PV forecast from Solcast entity states."""
        return PVForecast(
            remaining_today_kwh=_read_float(self._hass, self._remaining_id),
            tomorrow_kwh=_read_float(self._hass, self._tomorrow_id),
        )


class ForecastSolarProvider(ForecastProvider):
    """Read PV forecasts from Forecast.Solar HA integration."""

    def __init__(
        self, hass: HomeAssistant, remaining_entity: str, tomorrow_entity: str
    ) -> None:
        super().__init__(hass)
        self._remaining_id = remaining_entity
        self._tomorrow_id = tomorrow_entity

    def get_forecast(self) -> PVForecast:
        """Return PV forecast from Forecast.Solar entity states."""
        return PVForecast(
            remaining_today_kwh=_read_float(self._hass, self._remaining_id),
            tomorrow_kwh=_read_float(self._hass, self._tomorrow_id),
        )
