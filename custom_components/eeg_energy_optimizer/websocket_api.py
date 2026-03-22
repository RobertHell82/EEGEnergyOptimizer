"""WebSocket API for EEG Optimizer panel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    DOMAIN,
    INVERTER_TYPE_HUAWEI,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Known default entity IDs per inverter type.
# If these entities exist, they are pre-selected during auto-detection.
HUAWEI_DEFAULTS = {
    CONF_BATTERY_SOC_SENSOR: "sensor.batteries_batterieladung",
    CONF_BATTERY_CAPACITY_SENSOR: "sensor.batterien_akkukapazitat",
    CONF_PV_POWER_SENSOR: "sensor.inverter_eingangsleistung",
}


def _find_huawei_battery_device(hass: HomeAssistant) -> str | None:
    """Auto-detect the Huawei Solar battery device ID."""
    registry = dr.async_get(hass)
    for device in registry.devices.values():
        if any(
            domain == "huawei_solar"
            for domain, _ in device.identifiers
        ):
            if device.name and "batter" in device.name.lower():
                return device.id
    # Fallback: return first huawei_solar device
    for device in registry.devices.values():
        if any(
            domain == "huawei_solar"
            for domain, _ in device.identifiers
        ):
            return device.id
    return None


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket commands for the EEG Optimizer panel."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_save_config)
    websocket_api.async_register_command(hass, ws_check_prerequisites)
    websocket_api.async_register_command(hass, ws_detect_sensors)
    websocket_api.async_register_command(hass, ws_test_inverter)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_config",
    }
)
@websocket_api.async_response
async def ws_get_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return current config entry data."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_configured", "No config entry found")
        return

    entry = entries[0]
    config = {**entry.data, **entry.options}
    config["entry_id"] = entry.entry_id
    config["setup_complete"] = entry.data.get("setup_complete", False)
    connection.send_result(msg["id"], config)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/save_config",
        vol.Required("config"): dict,
    }
)
@websocket_api.async_response
async def ws_save_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Update config entry with new data."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_configured", "No config entry found")
        return

    entry = entries[0]
    new_data = {**entry.data, **msg["config"]}
    hass.config_entries.async_update_entry(entry, data=new_data)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/check_prerequisites",
    }
)
@websocket_api.async_response
async def ws_check_prerequisites(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Check which prerequisite integrations are installed and loaded."""
    check_domains = ["huawei_solar", "solcast_solar", "forecast_solar"]
    result = {}

    for domain in check_domains:
        entries = hass.config_entries.async_entries(domain)
        loaded = any(e.state.value == "loaded" for e in entries)
        result[domain] = loaded

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/detect_sensors",
    }
)
@websocket_api.async_response
async def ws_detect_sensors(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Auto-detect Huawei sensors and device ID."""
    # Check if Huawei Solar integration is loaded
    huawei_entries = hass.config_entries.async_entries("huawei_solar")
    huawei_loaded = any(e.state.value == "loaded" for e in huawei_entries)

    if not huawei_loaded:
        connection.send_result(msg["id"], {"detected": False, "sensors": {}})
        return

    # Detect sensors by checking state availability
    sensors: dict[str, str] = {}
    for conf_key, entity_id in HUAWEI_DEFAULTS.items():
        state = hass.states.get(entity_id)
        if state is not None:
            sensors[conf_key] = entity_id

    # Detect battery device
    device_id = _find_huawei_battery_device(hass)

    result: dict = {
        CONF_INVERTER_TYPE: INVERTER_TYPE_HUAWEI,
        "detected": True,
        "sensors": sensors,
    }
    if device_id:
        result[CONF_HUAWEI_DEVICE_ID] = device_id

    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/test_inverter",
    }
)
@websocket_api.async_response
async def ws_test_inverter(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Test inverter communication by calling stop_forcible (safe no-op).

    Returns success/failure and the inverter type.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_configured", "No config entry found")
        return

    entry = entries[0]
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    inverter = data.get("inverter")

    if inverter is None:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Kein Wechselrichter konfiguriert. Bitte zuerst die Einrichtung abschließen.",
        })
        return

    if not inverter.is_available:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Wechselrichter-Integration ist nicht geladen oder nicht erreichbar.",
        })
        return

    try:
        ok = await inverter.async_stop_forcible()
        if ok:
            connection.send_result(msg["id"], {
                "success": True,
                "message": "Verbindung zum Wechselrichter erfolgreich getestet.",
            })
        else:
            connection.send_result(msg["id"], {
                "success": False,
                "error": "Wechselrichter hat nicht wie erwartet reagiert.",
            })
    except Exception as exc:
        _LOGGER.exception("Inverter test failed")
        connection.send_result(msg["id"], {
            "success": False,
            "error": f"Fehler bei der Kommunikation: {exc}",
        })
