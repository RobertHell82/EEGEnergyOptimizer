"""Number entity for battery feed-in power (Einspeiseleistung)."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DATA_OPTIMIZER, DOMAIN

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
    """Set up the feed-in power number entity."""
    async_add_entities([EinspeiseleistungNumber(hass)], True)


class EinspeiseleistungNumber(NumberEntity, RestoreEntity):
    """Controls battery discharge power in kW.

    On every value change, syncs to Fronius via the shared sync function.
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Einspeiseleistung"
    _attr_unique_id = "energieoptimierung_einspeiseleistung"
    _attr_icon = "mdi:flash"
    _attr_native_min_value = 0
    _attr_native_max_value = 12
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "kW"
    _attr_mode = NumberMode.BOX

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._attr_native_value = 0.0

    async def async_added_to_hass(self) -> None:
        """Restore previous value."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in ("unknown", "unavailable", None):
            try:
                self._attr_native_value = float(last_state.state)
                _LOGGER.info("Einspeiseleistung restored to %s kW", self._attr_native_value)
            except (ValueError, TypeError):
                pass

    async def async_set_native_value(self, value: float) -> None:
        """Set new value and sync to Fronius."""
        self._attr_native_value = value
        self.async_write_ha_state()
        _LOGGER.info("Einspeiseleistung → %s kW", value)

        # Trigger Fronius sync
        from .fronius_sync import async_sync_to_fronius
        await async_sync_to_fronius(self.hass)
