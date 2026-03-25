"""WebSocket API for EEG Optimizer panel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_GRID_POWER_SENSOR,
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
# Each key maps to a list of candidates — first match wins.
HUAWEI_DEFAULTS: dict[str, list[str]] = {
    CONF_BATTERY_SOC_SENSOR: [
        "sensor.batteries_batterieladung",
        "sensor.batterien_batterieladung",
    ],
    CONF_BATTERY_CAPACITY_SENSOR: [
        "sensor.batterien_akkukapazitat",
        "sensor.batteries_akkukapazitat",
    ],
    CONF_PV_POWER_SENSOR: [
        "sensor.inverter_eingangsleistung",
        "sensor.wechselrichter_eingangsleistung",
    ],
    CONF_GRID_POWER_SENSOR: [
        "sensor.power_meter_wirkleistung",
        "sensor.stromzahler_wirkleistung",
    ],
    CONF_BATTERY_POWER_SENSOR: [
        "sensor.batteries_lade_entladeleistung",
        "sensor.batterien_lade_entladeleistung",
    ],
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


def _get_inverter(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Look up the inverter instance from hass.data, sending errors on failure.

    Returns the inverter or None (with error already sent to the client).
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_configured", "No config entry found")
        return None

    entry = entries[0]
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    inverter = data.get("inverter")

    if inverter is None:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Kein Wechselrichter konfiguriert. Bitte zuerst die Einrichtung abschließen.",
        })
        return None

    if not inverter.is_available:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Wechselrichter-Integration ist nicht geladen oder nicht erreichbar.",
        })
        return None

    return inverter


def _get_entry_data(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict):
    """Look up the config entry and its hass.data dict.

    Returns (entry, data) or (None, None) with error already sent.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_error(msg["id"], "not_configured", "No config entry found")
        return None, None

    entry = entries[0]
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    return entry, data


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register WebSocket commands for the EEG Optimizer panel."""
    websocket_api.async_register_command(hass, ws_get_config)
    websocket_api.async_register_command(hass, ws_save_config)
    websocket_api.async_register_command(hass, ws_check_prerequisites)
    websocket_api.async_register_command(hass, ws_detect_sensors)
    websocket_api.async_register_command(hass, ws_test_inverter)
    websocket_api.async_register_command(hass, ws_manual_stop)
    websocket_api.async_register_command(hass, ws_manual_discharge)
    websocket_api.async_register_command(hass, ws_manual_block_charge)
    websocket_api.async_register_command(hass, ws_set_test_overrides)
    websocket_api.async_register_command(hass, ws_get_test_overrides)
    websocket_api.async_register_command(hass, ws_clear_test_overrides)
    websocket_api.async_register_command(hass, ws_get_activity_log)


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

    # Detect sensors by checking state availability (first match wins)
    sensors: dict[str, str] = {}
    for conf_key, candidates in HUAWEI_DEFAULTS.items():
        for entity_id in candidates:
            state = hass.states.get(entity_id)
            if state is not None:
                sensors[conf_key] = entity_id
                break

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
    inverter = _get_inverter(hass, connection, msg)
    if inverter is None:
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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/manual_stop",
    }
)
@websocket_api.async_response
async def ws_manual_stop(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return inverter to automatic/normal operation."""
    inverter = _get_inverter(hass, connection, msg)
    if inverter is None:
        return

    try:
        ok = await inverter.async_stop_forcible()
        if ok:
            connection.send_result(msg["id"], {
                "success": True,
                "message": "Normalbetrieb aktiviert.",
            })
        else:
            connection.send_result(msg["id"], {
                "success": False,
                "error": "Wechselrichter hat nicht wie erwartet reagiert.",
            })
    except Exception as exc:
        _LOGGER.exception("Manual stop failed")
        connection.send_result(msg["id"], {
            "success": False,
            "error": f"Fehler bei der Kommunikation: {exc}",
        })


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/manual_discharge",
        vol.Required("power_kw"): vol.Coerce(float),
        vol.Optional("target_soc", default=10): vol.Coerce(float),
    }
)
@websocket_api.async_response
async def ws_manual_discharge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Start manual battery discharge at given power and target SOC."""
    inverter = _get_inverter(hass, connection, msg)
    if inverter is None:
        return

    power_kw = msg["power_kw"]
    target_soc = msg["target_soc"]

    try:
        ok = await inverter.async_set_discharge(power_kw, target_soc)
        if ok:
            connection.send_result(msg["id"], {
                "success": True,
                "message": f"Entladung gestartet: {power_kw} kW, Ziel-SOC: {target_soc}%.",
            })
        else:
            connection.send_result(msg["id"], {
                "success": False,
                "error": "Wechselrichter hat nicht wie erwartet reagiert.",
            })
    except Exception as exc:
        _LOGGER.exception("Manual discharge failed")
        connection.send_result(msg["id"], {
            "success": False,
            "error": f"Fehler bei der Kommunikation: {exc}",
        })


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/manual_block_charge",
    }
)
@websocket_api.async_response
async def ws_manual_block_charge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Block battery charging by setting charge limit to 0."""
    inverter = _get_inverter(hass, connection, msg)
    if inverter is None:
        return

    try:
        ok = await inverter.async_set_charge_limit(0)
        if ok:
            connection.send_result(msg["id"], {
                "success": True,
                "message": "Batterieladung blockiert.",
            })
        else:
            connection.send_result(msg["id"], {
                "success": False,
                "error": "Wechselrichter hat nicht wie erwartet reagiert.",
            })
    except Exception as exc:
        _LOGGER.exception("Manual block charge failed")
        connection.send_result(msg["id"], {
            "success": False,
            "error": f"Fehler bei der Kommunikation: {exc}",
        })


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/set_test_overrides",
        vol.Required("consumption_factor"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=3.0)
        ),
        vol.Optional("soc_override"): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
    }
)
@websocket_api.async_response
async def ws_set_test_overrides(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Set test overrides for optimizer simulation."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    overrides: dict = {"consumption_factor": msg["consumption_factor"]}
    if "soc_override" in msg:
        overrides["soc_override"] = msg["soc_override"]

    data["test_overrides"] = overrides

    # Trigger immediate optimizer cycle so dashboard updates instantly
    optimizer = data.get("optimizer")
    if optimizer:
        select = data.get("select")
        mode = select._attr_current_option if select else "Test"
        decision = await optimizer.async_run_cycle(mode)
        decision_sensor = data.get("decision_sensor")
        if decision_sensor and decision:
            decision_sensor.update_from_decision(decision)

    connection.send_result(msg["id"], {"success": True, "overrides": overrides})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_test_overrides",
    }
)
@websocket_api.async_response
async def ws_get_test_overrides(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return current test overrides (or null if none active)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    connection.send_result(msg["id"], {"overrides": data.get("test_overrides")})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/clear_test_overrides",
    }
)
@websocket_api.async_response
async def ws_clear_test_overrides(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Clear all test overrides."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    data.pop("test_overrides", None)

    # Trigger immediate optimizer cycle to restore real values
    optimizer = data.get("optimizer")
    if optimizer:
        select = data.get("select")
        mode = select._attr_current_option if select else "Test"
        decision = await optimizer.async_run_cycle(mode)
        decision_sensor = data.get("decision_sensor")
        if decision_sensor and decision:
            decision_sensor.update_from_decision(decision)

    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_activity_log",
        vol.Optional("offset", default=0): int,
        vol.Optional("limit", default=100): int,
    }
)
@websocket_api.async_response
async def ws_get_activity_log(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return a page of the activity log (newest first)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    log = data.get("activity_log")
    if not log:
        connection.send_result(msg["id"], {"entries": [], "total": 0})
        return

    total = len(log)
    # Convert deque to list in reverse (newest first), then slice
    all_entries = list(reversed(log))
    offset = msg.get("offset", 0)
    limit = msg.get("limit", 100)
    page = all_entries[offset:offset + limit]
    connection.send_result(msg["id"], {
        "entries": page,
        "total": total,
        "offset": offset,
        "has_more": offset + limit < total,
    })
