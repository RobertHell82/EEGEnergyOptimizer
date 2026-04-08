"""SolarEdge StorEdge inverter control via solaredge-modbus-multi integration.

Uses command mode switching + power limit entities for battery control.
Commands persist in non-volatile memory — async_stop_forcible() MUST be called
to restore normal operation (no auto-revert like Huawei/SolaX).

Entity prefix varies by installation — resolved from config or SOLAREDGE_ENTITY_DEFAULTS.
All power values converted from InverterBase kW to SolarEdge Watts.
"""

from __future__ import annotations

import asyncio
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
    "storage_command_timeout": "number.solaredge_storage_command_timeout",
}

# Command timeout in seconds — set high enough to cover the longest
# possible discharge/charge-blocking window. Prevents the inverter from
# reverting to default mode mid-operation. Avoids periodic re-sends
# that would wear out the flash memory (NVRAM).
COMMAND_TIMEOUT_SECONDS = 14400  # 4 hours

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
        # Primary inverter prefix (e.g. "solaredge_i1_") for entity resolution
        self._prefix = config.get("solaredge_prefix", "")
        # Fallback: derive prefix from pv_power_sensor (e.g. sensor.solaredge_i1_ac_power)
        if not self._prefix:
            pv_id = config.get("pv_power_sensor", "")
            if pv_id and "solaredge" in pv_id and "ac_power" in pv_id:
                self._prefix = pv_id.replace("sensor.", "").replace("ac_power", "")
        # Additional inverter prefixes for multi-inverter setups
        self._extra_prefixes: list[str] = []
        pv2_id = config.get("pv_power_sensor_2", "")
        if pv2_id and "solaredge" in pv2_id and "ac_power" in pv2_id:
            extra_prefix = pv2_id.replace("sensor.", "").replace("ac_power", "")
            if extra_prefix != self._prefix:
                self._extra_prefixes.append(extra_prefix)
        self._original_control_mode: str | None = None
        self._original_discharge_limit: float | None = None
        self._extra_original_control_modes: dict[str, str] = {}
        self._extra_original_discharge_limits: dict[str, float] = {}
        self._timeout_set = False
        self._extra_timeout_set: set[str] = set()
        self._snapshot_original_values()

    def _read_max_discharge_power(self, prefix: str | None = None) -> float | None:
        """Read hardware max discharge power from b1_max_discharge_power sensor.

        This sensor is always available (doesn't require Remote Control mode).
        Returns value in Watts, or None if not found.
        Falls back to suffix scan if prefix-based lookup fails.
        """
        pfx = prefix or self._prefix
        # Try direct prefix-based lookup first
        if pfx:
            entity_id = f"sensor.{pfx}b1_max_discharge_power"
            state = self._hass.states.get(entity_id)
            if state and state.state not in ("unavailable", "unknown"):
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    pass
        # Fallback: scan all sensors for b1_max_discharge_power
        for state in self._hass.states.async_all("sensor"):
            if (state.entity_id.endswith("b1_max_discharge_power")
                    and "solaredge" in state.entity_id
                    and state.state not in ("unavailable", "unknown")):
                # If looking for a specific prefix, check it matches
                if pfx and pfx not in state.entity_id:
                    continue
                try:
                    return float(state.state)
                except (ValueError, TypeError):
                    pass
        return None

    def _snapshot_original_values(self) -> None:
        """Snapshot current values so we can restore them in async_stop_forcible."""
        # storage_control_mode — never store "Remote Control" as original
        # (if integration restarts during active control, we'd restore the wrong mode)
        entity_id = self._resolve_entity("storage_control_mode")
        state = self._hass.states.get(entity_id)
        if state and state.state not in ("unavailable", "unknown"):
            if state.state != CONTROL_MODE_REMOTE:
                self._original_control_mode = state.state

        # discharge_limit — read from b1_max_discharge_power sensor (always available)
        max_discharge = self._read_max_discharge_power()
        if max_discharge is not None:
            self._original_discharge_limit = max_discharge
            _LOGGER.debug("SolarEdge: primary max discharge power = %.0f W", max_discharge)

        # Snapshot extra inverters
        for prefix in self._extra_prefixes:
            eid = self._resolve_entity_for_prefix(prefix, "storage_control_mode")
            st = self._hass.states.get(eid)
            if st and st.state not in ("unavailable", "unknown"):
                self._extra_original_control_modes[prefix] = st.state

            max_discharge = self._read_max_discharge_power(prefix)
            if max_discharge is not None:
                self._extra_original_discharge_limits[prefix] = max_discharge
                _LOGGER.debug("SolarEdge: %s max discharge power = %.0f W", prefix, max_discharge)

    def _resolve_entity_for_prefix(self, prefix: str, config_key: str) -> str:
        """Resolve entity ID for a specific inverter prefix (e.g. solaredge_i2_)."""
        default = SOLAREDGE_ENTITY_DEFAULTS.get(config_key)
        if default:
            domain = default.split(".")[0]
            suffix = default.split("solaredge_", 1)[-1] if "solaredge_" in default else ""
            if suffix:
                entity_id = f"{domain}.{prefix}{suffix}"
                state = self._hass.states.get(entity_id)
                if state is not None:
                    return entity_id
        return default or SOLAREDGE_ENTITY_DEFAULTS.get(config_key, "")

    def _resolve_entity(self, config_key: str) -> str:
        """Resolve entity ID from config, prefix, or suffix scan.

        Resolution order:
        1. Explicit config value (from panel detection/wizard)
        2. Primary prefix + suffix (e.g. solaredge_i1_ + storage_control_mode)
        3. Default entity ID (without inverter prefix)
        4. Suffix variants (e.g. backup_reserve vs storage_backup_reserve)
        5. Generic suffix scan (prefers available entities, skips unavailable)
        """
        # 1. Check explicit config value
        config_val = self._config.get(f"solaredge_{config_key}")
        if config_val:
            state = self._hass.states.get(config_val)
            if state is not None:
                return config_val

        # 2. Try primary prefix (detected inverter, e.g. solaredge_i1_)
        default = SOLAREDGE_ENTITY_DEFAULTS.get(config_key)
        if self._prefix and default:
            domain = default.split(".")[0]
            suffix = default.split("solaredge_", 1)[-1] if "solaredge_" in default else ""
            if suffix:
                prefixed = f"{domain}.{self._prefix}{suffix}"
                state = self._hass.states.get(prefixed)
                if state is not None:
                    return prefixed

        # 3. Check default (works for installations without prefix)
        if default:
            state = self._hass.states.get(default)
            if state is not None:
                return default

        # 4. Try suffix variants (handles backup_reserve vs storage_backup_reserve)
        variants = SOLAREDGE_SUFFIX_VARIANTS.get(config_key, [])
        for variant_suffix in variants:
            for state in self._hass.states.async_all():
                if (state.entity_id.endswith(variant_suffix)
                        and "solaredge" in state.entity_id
                        and state.state not in ("unavailable", "unknown")):
                    _LOGGER.debug(
                        "SolarEdge: resolved %s via variant suffix -> %s",
                        config_key, state.entity_id,
                    )
                    return state.entity_id

        # 5. Generic suffix scan — skip unavailable entities
        if default:
            suffix = default.split("solaredge_", 1)[-1] if "solaredge_" in default else ""
            if suffix:
                domain = default.split(".")[0]
                for state in self._hass.states.async_all(domain):
                    if (state.entity_id.endswith(suffix)
                            and "solaredge" in state.entity_id
                            and state.state not in ("unavailable", "unknown")):
                        _LOGGER.info(
                            "SolarEdge: resolved %s via suffix scan -> %s",
                            config_key, state.entity_id,
                        )
                        return state.entity_id

        # 6. Final fallback: return config value or default (may be unavailable)
        return config_val or default or SOLAREDGE_ENTITY_DEFAULTS[config_key]

    async def _set_number(self, config_key: str, value: float, *, prefix: str | None = None) -> None:
        """Set a number entity value. Resolves entity from config or defaults."""
        entity_id = (
            self._resolve_entity_for_prefix(prefix, config_key)
            if prefix else self._resolve_entity(config_key)
        )
        _LOGGER.info("SolarEdge: setting %s (%s) = %s", config_key, entity_id, value)
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.error(
                "SolarEdge: cannot set %s — entity %s is %s",
                config_key, entity_id, state.state if state else "not found",
            )
            raise RuntimeError(f"Entity {entity_id} is not available")
        await self._hass.services.async_call(
            "number", "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )
        if prefix is None:
            self.register_writes += 1

    async def _set_select(self, config_key: str, option: str, *, prefix: str | None = None) -> None:
        """Set a select entity option. Resolves entity from config or defaults."""
        entity_id = (
            self._resolve_entity_for_prefix(prefix, config_key)
            if prefix else self._resolve_entity(config_key)
        )
        _LOGGER.info("SolarEdge: setting %s (%s) = %s", config_key, entity_id, option)
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            _LOGGER.error(
                "SolarEdge: cannot set %s — entity %s is %s",
                config_key, entity_id, state.state if state else "not found",
            )
            raise RuntimeError(f"Entity {entity_id} is not available")
        await self._hass.services.async_call(
            "select", "select_option",
            {"entity_id": entity_id, "option": option},
            blocking=True,
        )
        if prefix is None:
            self.register_writes += 1

    async def _wait_for_available(self, config_key: str, timeout: float = 10.0, *, prefix: str | None = None) -> bool:
        """Wait until an entity is no longer unavailable.

        After switching storage_control_mode to Remote Control, the command
        entities (storage_command_mode, storage_discharge_limit, etc.) need
        a few seconds to become available via Modbus polling.

        Returns True if entity became available, False on timeout.
        """
        entity_id = (
            self._resolve_entity_for_prefix(prefix, config_key)
            if prefix else self._resolve_entity(config_key)
        )
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            state = self._hass.states.get(entity_id)
            if state and state.state not in ("unavailable", "unknown"):
                return True
            await asyncio.sleep(1)
        _LOGGER.warning(
            "SolarEdge: %s (%s) still unavailable after %.0fs",
            config_key, entity_id, timeout,
        )
        return False

    async def _ensure_remote_control(self) -> None:
        """Ensure storage_control_mode is set to Remote Control.

        Must be called before any storage_command_mode or limit changes —
        those entities are unavailable unless control mode is Remote Control.
        After switching, waits for command entities to become available.
        On first activation, sets command_timeout to 4h (once per integration lifetime).
        """
        entity_id = self._resolve_entity("storage_control_mode")
        state = self._hass.states.get(entity_id)
        if state and state.state == CONTROL_MODE_REMOTE:
            return
        _LOGGER.info("SolarEdge: switching storage_control_mode to Remote Control")
        await self._set_select("storage_control_mode", CONTROL_MODE_REMOTE)
        # Command entities need time to become available after mode switch
        await self._wait_for_available("storage_command_mode")
        await asyncio.sleep(3)
        # Set command timeout once — persists in NVRAM, no need to repeat or restore
        if not self._timeout_set:
            try:
                await self._wait_for_available("storage_command_timeout")
                await self._set_number("storage_command_timeout", COMMAND_TIMEOUT_SECONDS)
                self._timeout_set = True
                await asyncio.sleep(3)
            except Exception:
                _LOGGER.warning("SolarEdge: could not set command_timeout (non-critical)")

    async def _ensure_remote_control_extra(self, prefix: str) -> None:
        """Ensure an additional inverter is in Remote Control mode."""
        entity_id = self._resolve_entity_for_prefix(prefix, "storage_control_mode")
        state = self._hass.states.get(entity_id)
        if state and state.state == CONTROL_MODE_REMOTE:
            return
        _LOGGER.info("SolarEdge: switching %s storage_control_mode to Remote Control", prefix)
        await self._set_select("storage_control_mode", CONTROL_MODE_REMOTE, prefix=prefix)
        await self._wait_for_available("storage_command_mode", prefix=prefix)
        await asyncio.sleep(3)
        if prefix not in self._extra_timeout_set:
            try:
                await self._wait_for_available("storage_command_timeout", prefix=prefix)
                await self._set_number("storage_command_timeout", COMMAND_TIMEOUT_SECONDS, prefix=prefix)
                self._extra_timeout_set.add(prefix)
                await asyncio.sleep(3)
            except Exception:
                _LOGGER.warning("SolarEdge: could not set command_timeout on %s (non-critical)", prefix)

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Block or limit battery charging.

        power_kw=0: Block charging — switches to "Charge from Clipped Solar Power"
                    so PV surplus goes to grid (EEG morning feed-in).
                    Battery only charges from clipped solar (inverter at power limit).
        power_kw>0: Set storage_charge_limit to given power.

        Multi-inverter: sets all inverters to the same command mode.

        Sequence per inverter (3s delay between each Modbus write):
        1. storage_control_mode → "Remote Control" + command_timeout (once)
        2. storage_command_mode → "Charge from Clipped Solar Power"
        """
        try:
            await self._ensure_remote_control()
            for prefix in self._extra_prefixes:
                await self._ensure_remote_control_extra(prefix)
            if power_kw == 0:
                await self._set_select(
                    "storage_command_mode", MODE_CHARGE_FROM_CLIPPED
                )
                for prefix in self._extra_prefixes:
                    await self._set_select(
                        "storage_command_mode", MODE_CHARGE_FROM_CLIPPED, prefix=prefix
                    )
            else:
                power_w = int(power_kw * 1000)
                await self._set_number("storage_charge_limit", power_w)
                for prefix in self._extra_prefixes:
                    await self._set_number("storage_charge_limit", power_w, prefix=prefix)
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to set charge limit")
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force battery discharge to grid.

        Sets command mode to "Discharge to Maximize Export" with power ceiling.
        target_soc is ignored — our optimizer handles min-SOC logic itself
        and stops calling discharge when SOC is reached. backup_reserve
        stays at the user's configured default.

        Multi-inverter: sets all inverters to same mode and discharge limit.

        Sequence per inverter (3s delay between each Modbus write):
        1. storage_control_mode → "Remote Control" + command_timeout (once)
        2. storage_discharge_limit → power in Watts
        3. storage_command_mode → "Discharge to Maximize Export"
        """
        try:
            await self._ensure_remote_control()
            for prefix in self._extra_prefixes:
                await self._ensure_remote_control_extra(prefix)

            await self._wait_for_available("storage_discharge_limit")
            num_inverters = 1 + len(self._extra_prefixes)
            power_per_inv_w = int(power_kw * 1000 / num_inverters)
            await self._set_number("storage_discharge_limit", power_per_inv_w)
            for prefix in self._extra_prefixes:
                await self._wait_for_available("storage_discharge_limit", prefix=prefix)
                await self._set_number("storage_discharge_limit", power_per_inv_w, prefix=prefix)

            await asyncio.sleep(3)
            await self._set_select(
                "storage_command_mode", MODE_DISCHARGE_EXPORT
            )
            for prefix in self._extra_prefixes:
                await self._set_select(
                    "storage_command_mode", MODE_DISCHARGE_EXPORT, prefix=prefix
                )
            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Return to normal self-consumption mode.

        Always restores the same values regardless of which command
        was active. Critical for SolarEdge: commands persist in NVRAM.
        Each step needs a delay for the inverter to process via Modbus.

        Multi-inverter: restores all inverters.

        Sequence per inverter (with delays between each step):
        1. storage_discharge_limit → original max value (while still in Remote Control)
        2. storage_command_mode → "Maximize Self Consumption"
        3. storage_control_mode → original (exit Remote Control) — MUST be last
        """
        try:
            # Primary inverter — discharge_limit first (needs Remote Control)
            if self._original_discharge_limit is not None:
                await self._set_number(
                    "storage_discharge_limit", self._original_discharge_limit
                )
                await asyncio.sleep(3)
            await self._set_select(
                "storage_command_mode", MODE_SELF_CONSUMPTION
            )
            await asyncio.sleep(3)
            restore_mode = self._original_control_mode or CONTROL_MODE_SELF_CONSUMPTION
            await self._set_select("storage_control_mode", restore_mode)

            # Extra inverters — same order: limit first, then modes
            for prefix in self._extra_prefixes:
                await asyncio.sleep(3)
                orig_discharge = self._extra_original_discharge_limits.get(prefix)
                if orig_discharge is not None:
                    await self._set_number(
                        "storage_discharge_limit", orig_discharge, prefix=prefix
                    )
                    await asyncio.sleep(3)
                await self._set_select(
                    "storage_command_mode", MODE_SELF_CONSUMPTION, prefix=prefix
                )
                await asyncio.sleep(3)
                orig_mode = self._extra_original_control_modes.get(
                    prefix, CONTROL_MODE_SELF_CONSUMPTION
                )
                await self._set_select("storage_control_mode", orig_mode, prefix=prefix)

            return True
        except Exception:
            _LOGGER.exception("SolarEdge: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the SolarEdge Modbus Multi integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(SOLAREDGE_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
