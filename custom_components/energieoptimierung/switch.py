"""Switch to enable/disable the energy optimizer execution."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
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
    """Set up switches."""
    optimizer = hass.data[DOMAIN].get(DATA_OPTIMIZER)
    if optimizer is None:
        _LOGGER.warning("Optimizer not initialized – switches not created")
        return

    async_add_entities([
        OptimizerSwitch(hass, optimizer),
        EinspeisungSwitch(hass),
    ], True)


class OptimizerSwitch(SwitchEntity, RestoreEntity):
    """Switch to enable/disable optimizer EXECUTION.

    The optimizer always calculates decisions (visible in the decision sensor).
    When this switch is ON, it also writes to the actuators (heizstab, ladelimit, etc.).
    When OFF, it's read-only / dry-run mode.
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Optimizer"
    _attr_unique_id = "energieoptimierung_optimizer"
    _attr_icon = "mdi:robot"

    def __init__(self, hass: HomeAssistant, optimizer) -> None:
        self.hass = hass
        self._optimizer = optimizer
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        """Restore previous state (default: OFF)."""
        last_state = await self.async_get_last_state()
        if last_state and last_state.state == "on":
            self._attr_is_on = True
            _LOGGER.info("Optimizer restored to ON")

    async def async_turn_on(self, **kwargs) -> None:
        """Enable optimizer execution."""
        self._attr_is_on = True
        self.async_write_ha_state()
        _LOGGER.info("Optimizer execution enabled")

    async def async_turn_off(self, **kwargs) -> None:
        """Disable optimizer execution (calculations continue)."""
        self._attr_is_on = False
        self.async_write_ha_state()

        # Reset Fronius to auto mode when disabling
        from .fronius_sync import async_sync_to_fronius
        # Turn off Einspeisung switch
        einsp = self.hass.states.get("switch.energieoptimierung_einspeisung")
        if einsp and einsp.state == "on":
            await self.hass.services.async_call(
                "switch", "turn_off",
                {"entity_id": "switch.energieoptimierung_einspeisung"},
            )

        _LOGGER.info("Optimizer execution disabled (read-only mode)")

    @property
    def is_executing(self) -> bool:
        """Whether the optimizer should execute actions."""
        return self._attr_is_on


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
