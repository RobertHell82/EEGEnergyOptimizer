"""SolarEdge StorEdge inverter control via solaredge-modbus-multi integration.

Uses command mode switching + power limit entities for battery control.
Commands persist in non-volatile memory — async_stop_forcible() MUST be called
to restore normal operation (no auto-revert like Huawei/SolaX).

Entity prefix varies by installation — resolved from config or SOLAREDGE_ENTITY_DEFAULTS.
All power values converted from InverterBase kW to SolarEdge Watts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SOLAREDGE_DOMAIN = "solaredge_modbus_multi"

# Default entity IDs (prefix varies per installation)
SOLAREDGE_ENTITY_DEFAULTS = {
    "storage_command_mode": "select.solaredge_storage_command_mode",
    "storage_charge_limit": "number.solaredge_storage_charge_limit",
    "storage_discharge_limit": "number.solaredge_storage_discharge_limit",
    "storage_backup_reserve": "number.solaredge_storage_backup_reserve",
}

# Command modes (from solaredge-modbus-multi select entity)
MODE_SELF_CONSUMPTION = "Maximize Self Consumption"
MODE_MAXIMIZE_EXPORT = "Maximize Export"
MODE_DISCHARGE_EXPORT = "Discharge to Maximize Export"


class SolarEdgeInverter(InverterBase):
    """SolarEdge StorEdge battery control via solaredge-modbus-multi."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        # Store original values on init for reliable restoration
        self._original_backup_reserve: float | None = None
        self._max_charge_power: float | None = None
        self._max_discharge_power: float | None = None
        self._read_original_values()

    def _read_original_values(self) -> None:
        """Read and store current limit values for later restoration.

        For charge/discharge limits, prefer the 'max' attribute (hardware maximum)
        over the current state value which may have been modified.
        """
        for key, attr in [
            ("storage_backup_reserve", "_original_backup_reserve"),
            ("storage_charge_limit", "_max_charge_power"),
            ("storage_discharge_limit", "_max_discharge_power"),
        ]:
            entity_id = self._resolve_entity(key)
            state = self._hass.states.get(entity_id)
            if state is None:
                continue
            try:
                setattr(self, attr, float(state.state))
            except (ValueError, TypeError):
                pass
            # For charge/discharge limits, prefer the max attribute (hardware max)
            if attr in ("_max_charge_power", "_max_discharge_power"):
                max_val = state.attributes.get("max")
                if max_val is not None:
                    try:
                        setattr(self, attr, float(max_val))
                    except (ValueError, TypeError):
                        pass

    def _resolve_entity(self, config_key: str) -> str:
        """Resolve entity ID from config or defaults."""
        return self._config.get(
            f"solaredge_{config_key}", SOLAREDGE_ENTITY_DEFAULTS[config_key]
        )

    async def _set_number(self, config_key: str, value: float) -> None:
        """Set a number entity value. Resolves entity from config or defaults."""
        entity_id = self._resolve_entity(config_key)
        await self._hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    async def _set_select(self, config_key: str, option: str) -> None:
        """Set a select entity option. Resolves entity from config or defaults."""
        entity_id = self._resolve_entity(config_key)
        await self._hass.services.async_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Block or limit battery charging.

        power_kw=0: Set command mode to "Maximize Export" (full charge block,
                    PV surplus goes to grid for EEG morning feed-in).
        power_kw>0: Set storage_charge_limit to given power.
        """
        try:
            if power_kw == 0:
                await self._set_select(
                    "storage_command_mode", MODE_MAXIMIZE_EXPORT
                )
            else:
                power_w = int(power_kw * 1000)
                await self._set_number("storage_charge_limit", power_w)
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to set charge limit")
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force battery discharge to grid.

        Sets command mode to "Discharge to Maximize Export" with power ceiling.
        target_soc sets storage_backup_reserve as discharge floor (min 0%).
        Sets backup reserve BEFORE changing command mode per research pitfall 7.
        """
        try:
            if target_soc is not None:
                await self._set_number(
                    "storage_backup_reserve", max(int(target_soc), 0)
                )
            power_w = int(power_kw * 1000)
            await self._set_number("storage_discharge_limit", power_w)
            await self._set_select(
                "storage_command_mode", MODE_DISCHARGE_EXPORT
            )
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Return to normal self-consumption mode.

        Restores command mode and original limit values.
        Critical for SolarEdge: commands persist in NVRAM — without this call,
        the battery stays in the last commanded mode indefinitely.
        """
        try:
            await self._set_select(
                "storage_command_mode", MODE_SELF_CONSUMPTION
            )
            if self._max_charge_power is not None:
                await self._set_number(
                    "storage_charge_limit", self._max_charge_power
                )
            if self._max_discharge_power is not None:
                await self._set_number(
                    "storage_discharge_limit", self._max_discharge_power
                )
            if self._original_backup_reserve is not None:
                await self._set_number(
                    "storage_backup_reserve", self._original_backup_reserve
                )
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the SolarEdge Modbus Multi integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(SOLAREDGE_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
