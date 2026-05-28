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
        self.register_writes: int = 0

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

    # ------------------------------------------------------------------
    # Optional: combined battery state for multi-inverter setups.
    # ------------------------------------------------------------------
    # Bei Multi-Inverter-Setups (aktuell nur SolarEdge mit i1+i2+…) liefert
    # jede Modbus-Integration nur den SOC einer einzelnen Batterie. Der
    # Optimizer braucht aber den kapazitätsgewichteten Gesamt-SOC und die
    # Gesamtkapazität — sonst entlädt er gegen einen falschen Maßstab
    # ("44 % SOC" bei i1 obwohl gewichtet nur 34.6 %).
    #
    # Default: (None, None) → der Driver hat keine Combined-Sicht (Huawei,
    # Fronius, SolaX: Single-Battery), Optimizer fällt auf den Config-Sensor
    # battery_soc_sensor + manual capacity zurück. Driver-Override liefert
    # ein Tupel ⇒ Optimizer überstimmt damit Config-Werte automatisch.
    def get_combined_battery_state(self) -> tuple[float | None, float | None]:
        """Return (combined_soc_pct, combined_capacity_kwh) or (None, None).

        Override in Multi-Battery-Drivers (z. B. SolarEdge) to provide a
        capacity-weighted SOC and the summed nominal capacity. Default
        (None, None) signals: no driver-side combination available — caller
        falls back to the configured battery_soc_sensor / battery_capacity_kwh.
        """
        return (None, None)
