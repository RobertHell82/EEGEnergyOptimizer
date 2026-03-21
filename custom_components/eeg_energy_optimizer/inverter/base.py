"""Abstract base class for inverter battery control."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class InverterBase(ABC):
    """Abstract base class for inverter battery control.

    All inverter implementations must inherit from this class and implement
    the three write methods plus the is_available property.
    """

    def __init__(self, hass: Any, config: dict) -> None:
        """Initialize the inverter base.

        Args:
            hass: Home Assistant instance.
            config: Integration configuration dictionary.
        """
        self._hass = hass
        self._config = config

    @abstractmethod
    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit in kW.

        Instructs the inverter to charge the battery at up to power_kw.
        Returns True on success, False on failure.
        """

    @abstractmethod
    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Set battery discharge at given power in kW.

        Optional target_soc (0-100) as SOC floor for discharge.
        Returns True on success, False on failure.
        """

    @abstractmethod
    async def async_stop_forcible(self) -> bool:
        """Stop any forced charge/discharge, return to automatic mode.

        Returns True on success, False on failure.
        """

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the inverter connection/service is available."""
