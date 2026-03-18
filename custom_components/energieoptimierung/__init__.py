"""
Energieoptimierung – Verbrauchsprognose, Batterie, Puffer & Optimizer.

Berechnet den geschätzten Stromverbrauch basierend auf stündlichen
Langzeit-Statistiken. Der Optimizer steuert Heizstab, Batterie-Ladelimit
und Einspeisung nach einer prädiktiven Tagesstrategie.
"""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import DOMAIN, DATA_OPTIMIZER
from .optimizer import EnergyOptimizer

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "number"]

DATA_CANCEL_TIMER = "cancel_optimizer_timer"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    conf = entry.data | entry.options
    hass.data[DOMAIN][entry.entry_id] = conf

    # Instantiate optimizer
    optimizer = EnergyOptimizer(hass, conf)
    hass.data[DOMAIN][DATA_OPTIMIZER] = optimizer

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Sofort eine Read-Only-Berechnung damit Strategie und Faktor nicht leer sind
    await optimizer.async_run_cycle(execute=False)

    # Start the 60-second calculation timer (always runs).
    # The optimizer checks the switch state to decide execute vs. read-only.
    async def _optimizer_cycle(_now=None):
        switch_entity = hass.states.get("switch.energieoptimierung_optimizer")
        execute = switch_entity is not None and switch_entity.state == "on"
        await optimizer.async_run_cycle(execute=execute)

    # Nochmal nach 10s (dann sind alle Sensoren sicher initialisiert)
    async_call_later(hass, 10, _optimizer_cycle)

    # Then every 60 seconds
    cancel = async_track_time_interval(hass, _optimizer_cycle, timedelta(seconds=60))
    hass.data[DOMAIN][DATA_CANCEL_TIMER] = cancel

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update – reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Cancel optimizer timer
    cancel = hass.data[DOMAIN].pop(DATA_CANCEL_TIMER, None)
    if cancel:
        cancel()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(DATA_OPTIMIZER, None)
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
