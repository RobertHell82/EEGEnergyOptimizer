"""Switch entities for Energieoptimierung."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, DOMAIN)},
    name="Energieoptimierung",
    manufacturer="Custom",
    model="Energieoptimierung",
    entry_type=DeviceEntryType.SERVICE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches."""
    async_add_entities([EinspeisungSwitch(hass)], True)


class EinspeisungSwitch(SwitchEntity, RestoreEntity):
    """Switch to enable/disable battery feed-in (Einspeisung).

    On every state change, syncs to Fronius API.
    When ON + Einspeiseleistung > 0: Fronius goes to manual mode (HYB_EM_MODE=1).
    When OFF: Fronius returns to auto mode (HYB_EM_MODE=0).
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Einspeisung"
    _attr_unique_id = "energieoptimierung_einspeisung"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore previous state (default: OFF)."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            self._attr_is_on = True

    async def async_turn_on(self, **kwargs) -> None:
        """Enable feed-in and sync to Fronius."""
        self._attr_is_on = True
        self.async_write_ha_state()
        _LOGGER.info("Einspeisung → AN")

        from .fronius_sync import async_sync_to_fronius
        await async_sync_to_fronius(self.hass)

    async def async_turn_off(self, **kwargs) -> None:
        """Disable feed-in and sync to Fronius."""
        self._attr_is_on = False
        self.async_write_ha_state()
        _LOGGER.info("Einspeisung → AUS")

        from .fronius_sync import async_sync_to_fronius
        await async_sync_to_fronius(self.hass)
