"""EEG Energy Optimizer integration for Home Assistant."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import logging

from .const import DOMAIN, MODE_AUS
from .inverter import create_inverter
from .optimizer import EEGOptimizer
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.event import async_track_time_interval
except ImportError:
    async_track_time_interval = None  # type: ignore[assignment]

PLATFORMS: list[str] = ["sensor", "select"]

PANEL_FRONTEND_URL = "/eeg_optimizer_panel"
PANEL_ICON = "mdi:battery-charging-high"
PANEL_TITLE = "EEG Optimizer"
PANEL_URL_PATH = "eeg-optimizer"


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

    if entry.version < 4:
        new_data = {**entry.data}
        new_data.setdefault("setup_complete", False)
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)

    if entry.version < 5:
        new_data = {**entry.data}
        new_data.setdefault("enable_morning_delay", True)
        new_data.setdefault("enable_night_discharge", True)
        # ueberschuss_schwelle no longer used — safety_buffer_pct replaces it
        new_data.pop("ueberschuss_schwelle", None)
        hass.config_entries.async_update_entry(entry, data=new_data, version=5)

    if entry.version < 6:
        new_data = {**entry.data}
        new_data.setdefault("grid_power_sensor", "sensor.power_meter_wirkleistung")
        hass.config_entries.async_update_entry(entry, data=new_data, version=6)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EEG Energy Optimizer from a config entry."""
    from homeassistant.components.frontend import (
        async_register_built_in_panel,
        async_remove_panel,
    )
    from homeassistant.components.http import StaticPathConfig

    hass.data.setdefault(DOMAIN, {})
    config = {**entry.data, **entry.options}
    setup_complete = config.get("setup_complete", False)

    # Register WebSocket commands (always — panel needs them even before setup)
    async_register_websocket_commands(hass)

    # Register frontend panel (always — user needs panel to complete setup)
    frontend_path = str(Path(__file__).parent / "frontend")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_FRONTEND_URL, frontend_path, cache_headers=False)]
    )
    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": "eeg-optimizer-panel",
                    "embed_iframe": False,
                    "trust_external": False,
                    "js_url": f"{PANEL_FRONTEND_URL}/eeg-optimizer-panel.js",
                }
            },
            require_admin=False,
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "inverter": None,
        "platforms_loaded": False,
    }

    # If setup not complete, register panel only — skip platforms and optimizer
    if not setup_complete:
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        return True

    # Full setup: inverter, platforms, optimizer
    try:
        inverter = create_inverter(config.get("inverter_type", ""), hass, config)
    except ValueError as err:
        _LOGGER.error("Failed to create inverter: %s", err)
        from homeassistant.components.persistent_notification import async_create
        async_create(
            hass,
            f"EEG Optimizer: Wechselrichter konnte nicht erstellt werden — {err}",
            title="EEG Optimizer Fehler",
            notification_id="eeg_inverter_error",
        )
        return False
    hass.data[DOMAIN][entry.entry_id]["inverter"] = inverter

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.data[DOMAIN][entry.entry_id]["platforms_loaded"] = True

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
    else:
        missing = []
        if not coordinator:
            missing.append("Verbrauchsprofil (coordinator)")
        if not provider:
            missing.append("PV-Prognose (provider)")
        _LOGGER.error(
            "EEG Optimizer: Optimizer konnte nicht gestartet werden — "
            "fehlende Komponenten: %s",
            ", ".join(missing),
        )
        from homeassistant.components.persistent_notification import async_create
        async_create(
            hass,
            f"EEG Optimizer konnte nicht vollstaendig starten. "
            f"Fehlende Komponenten: {', '.join(missing)}. "
            f"Bitte Setup-Wizard erneut durchlaufen.",
            title="EEG Optimizer Warnung",
            notification_id="eeg_init_warning",
        )

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
    from homeassistant.components.frontend import async_remove_panel

    async_remove_panel(hass, PANEL_URL_PATH)

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    platforms_loaded = data.get("platforms_loaded", False)

    if platforms_loaded:
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )
    else:
        unload_ok = True

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
