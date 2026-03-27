"""SolaX Gen4+ inverter control via HA solax_modbus integration.

Uses Mode 1 Remote Control with two-phase write model:
  Phase 1: Set parameters via number.set_value / select.select_option (DATA_LOCAL)
  Phase 2: Press trigger button to write all params to Modbus registers

Entity prefix varies by installation — resolved from config or SOLAX_ENTITY_DEFAULTS.
All power values converted from InverterBase kW to SolaX Watts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SOLAX_DOMAIN = "solax_modbus"

# Entity Key -> Default Entity ID Mapping
SOLAX_ENTITY_DEFAULTS = {
    "remotecontrol_power_control": "select.solax_remotecontrol_power_control",
    "remotecontrol_active_power": "number.solax_remotecontrol_active_power",
    "remotecontrol_autorepeat_duration": "number.solax_remotecontrol_autorepeat_duration",
    "remotecontrol_trigger": "button.solax_remotecontrol_trigger",
    "selfuse_discharge_min_soc": "number.solax_selfuse_discharge_min_soc",
    "battery_charge_max_current": "number.solax_battery_charge_max_current",
}


class SolaXInverter(InverterBase):
    """SolaX Gen4+ inverter control via solax_modbus HA integration."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)

    async def _set_number(self, config_key: str, value: float) -> None:
        """Set a number entity value. Resolves entity from config or defaults."""
        entity_id = self._config.get(
            f"solax_{config_key}", SOLAX_ENTITY_DEFAULTS[config_key]
        )
        await self._hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    async def _set_select(self, config_key: str, option: str) -> None:
        """Set a select entity option. Resolves entity from config or defaults."""
        entity_id = self._config.get(
            f"solax_{config_key}", SOLAX_ENTITY_DEFAULTS[config_key]
        )
        await self._hass.services.async_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )

    async def _press_trigger(self) -> None:
        """Press the remote control trigger button to execute Modbus write."""
        entity_id = self._config.get(
            "solax_remotecontrol_trigger", SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]
        )
        await self._hass.services.async_call(
            "button", "press",
            {"entity_id": entity_id},
            blocking=True,
        )

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit. power_kw=0 blocks charging (battery idle).

        Uses "Enabled Battery Control" with active_power:
        - 0 = battery idle (PV surplus goes to grid for EEG morning feed-in)
        - positive = charge at given power
        """
        try:
            if power_kw == 0:
                await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
                await self._set_number("remotecontrol_active_power", 0)
            else:
                power_w = int(power_kw * 1000)
                await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
                await self._set_number("remotecontrol_active_power", power_w)
            await self._set_number("remotecontrol_autorepeat_duration", 60)
            await self._press_trigger()
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to set charge limit")
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Start forced battery discharge at given power.

        Uses "Enabled Battery Control" with negative active_power.
        Optional target_soc sets selfuse_discharge_min_soc floor (min 10%).
        """
        try:
            if target_soc is not None:
                min_soc = max(int(target_soc), 10)
                await self._set_number("selfuse_discharge_min_soc", min_soc)

            power_w = -abs(int(power_kw * 1000))
            await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
            await self._set_number("remotecontrol_active_power", power_w)
            await self._set_number("remotecontrol_autorepeat_duration", 60)
            await self._press_trigger()
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Sets autorepeat_duration=0 BEFORE trigger to clear autorepeat timer.
        """
        try:
            await self._set_select("remotecontrol_power_control", "Disabled")
            await self._set_number("remotecontrol_active_power", 0)
            await self._set_number("remotecontrol_autorepeat_duration", 0)
            await self._press_trigger()
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the SolaX Modbus integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(SOLAX_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
