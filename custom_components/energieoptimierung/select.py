"""Select entity for optimizer mode."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DATA_OPTIMIZER,
    DOMAIN,
    MODE_AUS,
    MODE_EIN,
    OPTIMIZER_MODES,
)

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
    """Set up select entities."""
    optimizer = hass.data[DOMAIN].get(DATA_OPTIMIZER)
    if optimizer is None:
        _LOGGER.warning("Optimizer not initialized – select not created")
        return

    async_add_entities([OptimizerModeSelect(hass)], True)


class OptimizerModeSelect(SelectEntity, RestoreEntity):
    """Select entity for optimizer operating mode.

    - Ein: Full optimization (strategies, guards, night discharge, feed-in)
    - Eigenverbrauch Heizstab: Heizstab priority, no feed-in, no night discharge
    - Eigenverbrauch Batterie: Battery priority, Heizstab gets the rest
    - Eigenverbrauch Balanciert: Balance between battery and Heizstab based on fill levels
    - Aus: Read-only / dry-run mode
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Optimizer"
    _attr_unique_id = "energieoptimierung_optimizer"
    _attr_icon = "mdi:robot"
    _attr_options = OPTIMIZER_MODES
    _attr_current_option = MODE_AUS

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def async_added_to_hass(self) -> None:
        """Restore previous state (default: Aus)."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in OPTIMIZER_MODES:
            self._attr_current_option = last_state.state
            _LOGGER.info("Optimizer mode restored to %s", last_state.state)

    async def async_select_option(self, option: str) -> None:
        """Handle mode change."""
        old = self._attr_current_option
        self._attr_current_option = option
        self.async_write_ha_state()
        _LOGGER.info("Optimizer mode: %s → %s", old, option)

        # When switching to Aus, reset Fronius to auto
        if option == MODE_AUS and old != MODE_AUS:
            from .fronius_sync import async_sync_to_fronius
            einsp = self.hass.states.get("switch.energieoptimierung_einspeisung")
            if einsp and einsp.state == "on":
                await self.hass.services.async_call(
                    "switch", "turn_off",
                    {"entity_id": "switch.energieoptimierung_einspeisung"},
                )
            _LOGGER.info("Optimizer disabled – Fronius reset")
