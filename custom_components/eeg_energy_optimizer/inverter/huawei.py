"""Huawei SUN2000 inverter control via HA Huawei Solar services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HUAWEI_DOMAIN = "huawei_solar"
MAX_CHARGE_POWER_CANDIDATES = [
    "number.batteries_maximale_ladeleistung",
    "number.batterien_maximale_ladeleistung",
]
# Die Entity-ID hängt von HA-Sprache und Gerätename zum Erstellzeitpunkt ab —
# Fallback-Suche über sprachtypische Suffixe (DE/EN) statt exakter IDs.
MAX_CHARGE_POWER_SUFFIXES = (
    "maximale_ladeleistung",
    "maximum_charging_power",
)


class HuaweiInverter(InverterBase):
    """Huawei SUN2000 inverter control via HA Huawei Solar services."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        device_id = config.get("huawei_device_id")
        if not device_id:
            raise ValueError(
                "HuaweiInverter requires 'huawei_device_id' in config — "
                "device was not auto-detected. Re-run setup wizard to detect the Huawei device."
            )
        self._device_id: str = device_id
        self._max_charge_entity: str | None = self._resolve_charge_entity()
        if self._max_charge_entity is None:
            _LOGGER.warning(
                "Huawei: Kein Ladeleistungs-Entity gefunden (erwartet: %s). "
                "Laden-Blockieren (Morgen-Einspeisung) bleibt deaktiviert, bis das "
                "Entity verfügbar ist. Prüfe, ob die huawei_solar-Integration mit "
                "erweiterten Berechtigungen (Installer-Login) eingerichtet ist.",
                MAX_CHARGE_POWER_CANDIDATES,
            )

    def _resolve_charge_entity(self) -> str | None:
        """Find the max charge power entity, or None if not (yet) available."""
        for entity_id in MAX_CHARGE_POWER_CANDIDATES:
            if self._hass.states.get(entity_id) is not None:
                _LOGGER.debug("Huawei: Using charge power entity %s", entity_id)
                return entity_id
        for state in self._hass.states.async_all("number"):
            if any(
                state.entity_id.endswith(f"_{suffix}")
                for suffix in MAX_CHARGE_POWER_SUFFIXES
            ):
                _LOGGER.debug(
                    "Huawei: Using charge power entity %s (suffix match)",
                    state.entity_id,
                )
                return state.entity_id
        return None

    def _ensure_charge_entity(self) -> str | None:
        """Re-resolve lazily — the entity may appear after a slow huawei_solar start."""
        if self._max_charge_entity is None:
            self._max_charge_entity = self._resolve_charge_entity()
            if self._max_charge_entity is not None:
                _LOGGER.info(
                    "Huawei: Ladeleistungs-Entity nachträglich gefunden: %s",
                    self._max_charge_entity,
                )
        return self._max_charge_entity

    async def _get_max_charge_power(self) -> float:
        """Read the max value of the charge power number entity."""
        state = self._hass.states.get(self._max_charge_entity)
        if state is None:
            return 5000.0
        return float(state.attributes.get("max", 5000))

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery max charge power via number entity.

        power_kw=0 blocks charging, any other value sets the limit.
        """
        entity_id = self._ensure_charge_entity()
        if entity_id is None:
            _LOGGER.warning(
                "Huawei: Ladelimit %.1f kW nicht gesetzt — kein Ladeleistungs-Entity verfügbar",
                power_kw,
            )
            return False
        power_w = int(power_kw * 1000)
        try:
            await self._hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": entity_id,
                    "value": power_w,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set charge limit via %s", entity_id)
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Start forced battery discharge at given power and target SOC."""
        power_w = str(int(power_kw * 1000))
        soc = max(int(target_soc) if target_soc is not None else 12, 12)
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "forcible_discharge_soc",
                {
                    "device_id": self._device_id,
                    "power": power_w,
                    "target_soc": soc,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Resets max charge power to hardware maximum and stops any
        forcible charge/discharge mode.
        """
        entity_id = self._ensure_charge_entity()
        try:
            # Restore max charge power (skip if the entity is unavailable —
            # stopping the forcible mode must still go through)
            if entity_id is not None:
                max_power = await self._get_max_charge_power()
                await self._hass.services.async_call(
                    "number",
                    "set_value",
                    {
                        "entity_id": entity_id,
                        "value": max_power,
                    },
                    blocking=True,
                )
            # Stop forcible discharge if active
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "stop_forcible_charge",
                {"device_id": self._device_id},
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the Huawei Solar integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(HUAWEI_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
