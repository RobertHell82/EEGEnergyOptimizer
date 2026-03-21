"""Select platform for EEG Energy Optimizer."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .const import DOMAIN, MODE_AUS, MODE_EIN, MODE_TEST, OPTIMIZER_MODES

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

# HA imports guarded for test environment
try:
    from homeassistant.components.select import SelectEntity
    from homeassistant.helpers.device_registry import DeviceEntryType
    from homeassistant.helpers.entity import DeviceInfo
    from homeassistant.helpers.restore_state import RestoreEntity
except ImportError:

    class SelectEntity:  # type: ignore[no-redef]
        _attr_has_entity_name: bool = False
        _attr_name: str = ""
        _attr_unique_id: str = ""
        _attr_options: list[str] = []
        _attr_current_option: str | None = None
        _attr_device_info: Any = None
        _attr_icon: str | None = None

        async def async_select_option(self, option: str) -> None:
            pass

        def async_write_ha_state(self) -> None:
            pass

    class RestoreEntity:  # type: ignore[no-redef]
        async def async_get_last_state(self):
            return None

    class DeviceEntryType:  # type: ignore[no-redef]
        SERVICE = "service"

    class DeviceInfo(dict):  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)


class OptimizerModeSelect(SelectEntity, RestoreEntity):
    """Select entity for optimizer mode: Ein / Test / Aus."""

    _attr_has_entity_name = True
    _attr_name = "Optimizer"
    _attr_icon = "mdi:robot"
    _attr_options = OPTIMIZER_MODES
    _attr_current_option = MODE_AUS

    def __init__(self, entry_id: str) -> None:
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_optimizer"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="EEG Energy Optimizer",
            manufacturer="Custom",
            model="EEG Energy Optimizer",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        """Restore previous state (default: Aus)."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
            _LOGGER.info("Restored optimizer mode: %s", last_state.state)

    async def async_select_option(self, option: str) -> None:
        """Handle mode change."""
        self._attr_current_option = option
        self.async_write_ha_state()
        _LOGGER.info("Optimizer mode changed to: %s", option)


async def async_setup_entry(
    hass: Any,
    entry: Any,
    async_add_entities: Any,
) -> None:
    """Set up select platform for EEG Energy Optimizer."""
    select = OptimizerModeSelect(entry.entry_id)
    hass.data[DOMAIN][entry.entry_id]["select"] = select
    async_add_entities([select])
