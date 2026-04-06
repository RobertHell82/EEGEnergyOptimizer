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
    "storage_control_mode": "select.solaredge_storage_control_mode",
    "storage_command_mode": "select.solaredge_storage_command_mode",
    "storage_charge_limit": "number.solaredge_storage_charge_limit",
    "storage_discharge_limit": "number.solaredge_storage_discharge_limit",
    "storage_backup_reserve": "number.solaredge_storage_backup_reserve",
}

# Suffix variants for entities with inconsistent naming (tried in order)
SOLAREDGE_SUFFIX_VARIANTS: dict[str, list[str]] = {
    "storage_backup_reserve": ["storage_backup_reserve", "backup_reserve"],
}

# Storage control mode — master switch that must be "Remote Control"
# before storage_command_mode and limits become available
CONTROL_MODE_REMOTE = "Remote Control"
CONTROL_MODE_SELF_CONSUMPTION = "Maximize Self Consumption"

# Command modes (from solaredge-modbus-multi select entity)
MODE_SELF_CONSUMPTION = "Maximize Self Consumption"
MODE_CHARGE_FROM_CLIPPED = "Charge from Clipped Solar Power"
MODE_DISCHARGE_EXPORT = "Discharge to Maximize Export"


class SolarEdgeInverter(InverterBase):
    """SolarEdge StorEdge battery control via solaredge-modbus-multi."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        # Track which values we actually modified — only restore those
        self._modified: set[str] = set()
        # Original values captured before first modification
        self._original_control_mode: str | None = None
        self._original_backup_reserve: float | None = None
        self._original_discharge_limit: float | None = None
        self._snapshot_original_values()

    def _snapshot_original_values(self) -> None:
        """Snapshot current values so we can restore only what we change."""
        # storage_control_mode
        entity_id = self._resolve_entity("storage_control_mode")
        state = self._hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown"):
            self._original_control_mode = state.state

        # backup_reserve
        entity_id = self._resolve_entity("storage_backup_reserve")
        state = self._hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown"):
            try:
                self._original_backup_reserve = float(state.state)
            except (ValueError, TypeError):
                pass

        # discharge_limit — prefer 'max' attribute (hardware maximum)
        entity_id = self._resolve_entity("storage_discharge_limit")
        state = self._hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown"):
            try:
                self._original_discharge_limit = float(state.state)
            except (ValueError, TypeError):
                pass
            max_val = state.attributes.get("max")
            if max_val is not None:
                try:
                    self._original_discharge_limit = float(max_val)
                except (ValueError, TypeError):
                    pass

    def _resolve_entity(self, config_key: str) -> str:
        """Resolve entity ID from config or defaults.

        For keys with known suffix variants (e.g. backup_reserve vs
        storage_backup_reserve), tries each variant against hass.states
        when the config value doesn't resolve to an existing entity.
        """
        # 1. Check explicit config value
        config_val = self._config.get(f"solaredge_{config_key}")
        if config_val:
            state = self._hass.states.get(config_val)
            if state is not None:
                return config_val

        # 2. Check default
        default = SOLAREDGE_ENTITY_DEFAULTS.get(config_key)
        if default:
            state = self._hass.states.get(default)
            if state is not None:
                return default

        # 3. Try suffix variants (handles backup_reserve vs storage_backup_reserve)
        variants = SOLAREDGE_SUFFIX_VARIANTS.get(config_key, [])
        for variant_suffix in variants:
            for state in self._hass.states.async_all():
                if (state.entity_id.endswith(variant_suffix)
                        and "solaredge" in state.entity_id):
                    _LOGGER.debug(
                        "SolarEdge: resolved %s via variant suffix → %s",
                        config_key, state.entity_id,
                    )
                    return state.entity_id

        # 4. Final fallback: return config value or default (may be unavailable)
        return config_val or default or SOLAREDGE_ENTITY_DEFAULTS[config_key]

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

    async def _ensure_remote_control(self) -> None:
        """Ensure storage_control_mode is set to Remote Control.

        Must be called before any storage_command_mode or limit changes —
        those entities are unavailable unless control mode is Remote Control.
        """
        entity_id = self._resolve_entity("storage_control_mode")
        state = self._hass.states.get(entity_id)
        if state and state.state == CONTROL_MODE_REMOTE:
            return
        _LOGGER.info("SolarEdge: switching storage_control_mode → Remote Control")
        self._modified.add("storage_control_mode")
        await self._set_select("storage_control_mode", CONTROL_MODE_REMOTE)

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Block or limit battery charging.

        power_kw=0: Block charging — switches to "Charge from Clipped Solar Power"
                    so PV surplus goes to grid (EEG morning feed-in).
                    Battery only charges from clipped solar (inverter at power limit).
        power_kw>0: Set storage_charge_limit to given power.

        Sequence:
        1. storage_control_mode → "Remote Control" (enables command entities)
        2. storage_command_mode → "Charge from Clipped Solar Power"
        """
        try:
            await self._ensure_remote_control()
            self._modified.add("storage_command_mode")
            if power_kw == 0:
                await self._set_select(
                    "storage_command_mode", MODE_CHARGE_FROM_CLIPPED
                )
            else:
                power_w = int(power_kw * 1000)
                self._modified.add("storage_charge_limit")
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

        Sequence:
        1. storage_control_mode → "Remote Control" (enables command entities)
        2. storage_backup_reserve → target_soc (discharge floor, before mode change)
        3. storage_discharge_limit → power in Watts
        4. storage_command_mode → "Discharge to Maximize Export"
        """
        try:
            await self._ensure_remote_control()
            if target_soc is not None:
                self._modified.add("storage_backup_reserve")
                await self._set_number(
                    "storage_backup_reserve", max(int(target_soc), 0)
                )
            power_w = int(power_kw * 1000)
            self._modified.add("storage_discharge_limit")
            await self._set_number("storage_discharge_limit", power_w)
            self._modified.add("storage_command_mode")
            await self._set_select(
                "storage_command_mode", MODE_DISCHARGE_EXPORT
            )
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Return to normal self-consumption mode.

        Only restores values that were actually modified by this instance.
        Critical for SolarEdge: commands persist in NVRAM — without this call,
        the battery stays in the last commanded mode indefinitely.
        """
        if not self._modified:
            return True

        try:
            # 1. Restore command mode first (always modified when we take control)
            if "storage_command_mode" in self._modified:
                await self._set_select(
                    "storage_command_mode", MODE_SELF_CONSUMPTION
                )
            # 2. Restore discharge limit if we changed it
            if "storage_discharge_limit" in self._modified and self._original_discharge_limit is not None:
                await self._set_number(
                    "storage_discharge_limit", self._original_discharge_limit
                )
            # 3. Restore backup reserve if we changed it
            if "storage_backup_reserve" in self._modified and self._original_backup_reserve is not None:
                await self._set_number(
                    "storage_backup_reserve", self._original_backup_reserve
                )
            # 4. Exit Remote Control last (disables command entities)
            if "storage_control_mode" in self._modified:
                restore_mode = self._original_control_mode or CONTROL_MODE_SELF_CONSUMPTION
                await self._set_select("storage_control_mode", restore_mode)

            self._modified.clear()
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the SolarEdge Modbus Multi integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(SOLAREDGE_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
