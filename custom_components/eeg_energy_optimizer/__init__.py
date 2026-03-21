"""EEG Energy Optimizer integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from .const import DOMAIN, MODE_AUS
from .inverter import create_inverter
from .optimizer import EEGOptimizer

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.event import async_track_time_interval
except ImportError:
    async_track_time_interval = None  # type: ignore[assignment]

PLATFORMS: list[str] = ["sensor", "select"]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from older versions."""
    if entry.version < 3:
        new_data = {**entry.data}
        # Add Phase 3 defaults for missing keys
        new_data.setdefault("ueberschuss_schwelle", 1.25)
        new_data.setdefault("morning_end_time", "10:00")
        new_data.setdefault("discharge_start_time", "20:00")
        new_data.setdefault("discharge_power_kw", 3.0)
        new_data.setdefault("min_soc", 10)
        new_data.setdefault("safety_buffer_pct", 25)
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EEG Energy Optimizer from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    config = {**entry.data, **entry.options}

    inverter = create_inverter(config["inverter_type"], hass, config)
    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "inverter": inverter,
        # "coordinator", "provider", "optimizer", "select" added by platform setup
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # After platforms are set up, coordinator/provider/select are available
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.get("coordinator")
    provider = data.get("provider")

    if coordinator and provider:
        optimizer = EEGOptimizer(hass, config, inverter, coordinator, provider)
        data["optimizer"] = optimizer

        async def _optimizer_cycle(_now=None):
            select = data.get("select")
            mode = select._attr_current_option if select else MODE_AUS
            if mode != MODE_AUS:
                decision = await optimizer.async_run_cycle(mode)
                # Update decision sensor if available
                decision_sensor = data.get("decision_sensor")
                if decision_sensor and decision:
                    decision_sensor.update_from_decision(decision)

        if async_track_time_interval is not None:
            unsub = async_track_time_interval(
                hass, _optimizer_cycle, timedelta(seconds=60)
            )
            entry.async_on_unload(unsub)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload EEG Energy Optimizer config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
