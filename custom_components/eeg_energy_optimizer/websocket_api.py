"""WebSocket API for EEG Energy Optimizer panel."""

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
    CONF_PV_POWER_SENSOR_2,
    DOMAIN,
    INVERTER_TYPE_HUAWEI,
    INVERTER_TYPE_SOLAX,
    INVERTER_TYPE_SOLAREDGE,
    INVERTER_TYPE_FRONIUS,
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

SOLAX_DEFAULTS: dict[str, list[str]] = {
    CONF_BATTERY_SOC_SENSOR: [
        "sensor.solax_inverter_battery_capacity",
        "sensor.solax_battery_capacity",
    ],
    CONF_PV_POWER_SENSOR: [
        "sensor.solax_energy_dashboard_solax_solar_power",
        "sensor.solax_solar_power",
    ],
    CONF_GRID_POWER_SENSOR: [
        "sensor.solax_energy_dashboard_solax_grid_power",
        "sensor.solax_grid_power",
    ],
    CONF_BATTERY_POWER_SENSOR: [
        "sensor.solax_energy_dashboard_solax_battery_power",
        "sensor.solax_battery_power",
    ],
    CONF_PV_POWER_SENSOR_2: [
        "sensor.solax_inverter_meter_2_measured_power",
    ],
}

# SolarEdge sensor suffixes — used with detected prefix to build entity IDs.
# Each config key maps to candidate suffixes (first existing entity wins).
SOLAREDGE_SENSOR_SUFFIXES: dict[str, list[str]] = {
    CONF_BATTERY_SOC_SENSOR: ["b1_state_of_energy"],
    CONF_PV_POWER_SENSOR: ["ac_power", "dc_power"],
    CONF_GRID_POWER_SENSOR: ["m1_ac_power", "m2_ac_power"],
    CONF_BATTERY_POWER_SENSOR: ["b1_dc_power"],
    CONF_BATTERY_CAPACITY_SENSOR: ["b1_maximum_energy"],
}

# SolarEdge control entity suffixes — tried in order per config key.
SOLAREDGE_CONTROL_SUFFIXES: dict[str, list[tuple[str, str]]] = {
    # (domain, suffix) — tried in order, first existing entity wins
    "solaredge_storage_control_mode": [("select", "storage_control_mode")],
    "solaredge_storage_command_mode": [("select", "storage_command_mode")],
    "solaredge_storage_charge_limit": [("number", "storage_charge_limit")],
    "solaredge_storage_discharge_limit": [("number", "storage_discharge_limit")],
    "solaredge_storage_backup_reserve": [
        ("number", "storage_backup_reserve"),
        ("number", "backup_reserve"),
    ],
}

# Fronius native integration sensor suffixes — used to find entities.
# The Fronius integration creates entities like sensor.{device_name}_{key}.
# Prefix varies by installation (e.g. "solarnet_", "power_flow_0_192_168_100_211_").
FRONIUS_SENSOR_SUFFIXES: dict[str, list[str]] = {
    CONF_BATTERY_SOC_SENSOR: ["state_of_charge"],
    CONF_PV_POWER_SENSOR: ["power_photovoltaics"],
    CONF_GRID_POWER_SENSOR: ["power_grid"],
    CONF_BATTERY_POWER_SENSOR: ["power_battery"],
    CONF_BATTERY_CAPACITY_SENSOR: ["capacity_maximum"],
}


def _find_solaredge_prefix(hass: HomeAssistant) -> str | None:
    """Auto-detect the SolarEdge entity prefix by searching multiple known suffixes.

    Searches sensor and select domains for well-known SolarEdge suffixes.
    Handles varying prefixes like 'solaredge_', 'solaredge_i1_', etc.
    """
    # Search suffixes in order: most specific first
    search_targets = [
        ("select", "storage_command_mode"),
        ("select", "storage_control_mode"),
        ("sensor", "b1_state_of_energy"),
        ("sensor", "ac_power"),
        ("sensor", "m1_ac_power"),
    ]
    for domain, suffix in search_targets:
        for state in hass.states.async_all(domain):
            if state.entity_id.endswith(suffix):
                # e.g. "sensor.solaredge_i1_ac_power" -> "solaredge_i1_"
                prefix = state.entity_id.replace(f"{domain}.", "").replace(suffix, "")
                if prefix.startswith("solaredge"):
                    return prefix
    return None


def _find_solaredge_additional_inverters(
    hass: HomeAssistant, primary_prefix: str
) -> list[str]:
    """Find additional SolarEdge inverter prefixes beyond the primary one.

    Searches for other solaredge_iN_ac_power sensors to detect multi-inverter setups.
    Returns list of additional prefixes (e.g. ['solaredge_i2_']).
    """
    additional: list[str] = []
    for state in hass.states.async_all("sensor"):
        eid = state.entity_id
        if (eid.endswith("ac_power")
                and "solaredge" in eid
                and not eid.endswith("m1_ac_power")
                and not eid.endswith("m2_ac_power")):
            prefix = eid.replace("sensor.", "").replace("ac_power", "")
            if prefix.startswith("solaredge") and prefix != primary_prefix:
                additional.append(prefix)
    return sorted(additional)


def _find_solax_prefix(hass: HomeAssistant) -> str | None:
    """Auto-detect the SolaX entity prefix by searching for remotecontrol_power_control."""
    for state in hass.states.async_all("select"):
        if state.entity_id.endswith("remotecontrol_power_control"):
            # e.g. "select.solax_remotecontrol_power_control" -> "solax_"
            prefix = state.entity_id.replace("select.", "").replace("remotecontrol_power_control", "")
            return prefix
    return None


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
    """Register WebSocket commands for the EEG Energy Optimizer panel."""
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
    websocket_api.async_register_command(hass, ws_get_feedin_statistics)


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
    # Inject version from manifest
    try:
        import json, pathlib
        manifest = json.loads(
            (pathlib.Path(__file__).parent / "manifest.json").read_text()
        )
        config["version"] = manifest.get("version", "")
    except Exception:
        config["version"] = ""
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

    # SolarEdge: enforce minimum discharge power of 5 kW
    if new_data.get("inverter_type") == INVERTER_TYPE_SOLAREDGE:
        discharge_kw = new_data.get("discharge_power_kw")
        if discharge_kw is not None and float(discharge_kw) < 5.0:
            new_data["discharge_power_kw"] = 5.0

    # Fronius: server-side validation of the Modbus endpoint. The frontend
    # already checks "non-empty host", but we cannot trust the WebSocket
    # client. An empty/garbage host or out-of-range port would later surface
    # as opaque pymodbus connection errors; reject it here with a clear code.
    if new_data.get("inverter_type") == INVERTER_TYPE_FRONIUS:
        host = new_data.get("fronius_modbus_host", "")
        if not isinstance(host, str) or not host.strip() or len(host) > 255:
            connection.send_error(
                msg["id"], "invalid_config", "Invalid Fronius Modbus host"
            )
            return
        new_data["fronius_modbus_host"] = host.strip()
        port_raw = new_data.get("fronius_modbus_port", 502)
        try:
            port = int(port_raw)
        except (TypeError, ValueError):
            connection.send_error(
                msg["id"], "invalid_config", "Invalid Fronius Modbus port"
            )
            return
        if not 1 <= port <= 65535:
            connection.send_error(
                msg["id"], "invalid_config", "Fronius Modbus port out of range"
            )
            return
        new_data["fronius_modbus_port"] = port

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
    check_domains = ["huawei_solar", "solax_modbus", "solaredge_modbus_multi", "fronius", "solcast_solar", "forecast_solar"]
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
    """Auto-detect inverter sensors (Huawei or SolaX)."""
    # Check if Huawei Solar integration is loaded
    huawei_entries = hass.config_entries.async_entries("huawei_solar")
    huawei_loaded = any(e.state.value == "loaded" for e in huawei_entries)

    if huawei_loaded:
        # Detect Huawei sensors by checking state availability (first match wins)
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
        return

    # Check if SolaX Modbus integration is loaded
    solax_entries = hass.config_entries.async_entries("solax_modbus")
    solax_loaded = any(e.state.value == "loaded" for e in solax_entries)

    if solax_loaded:
        sensors = {}
        for conf_key, candidates in SOLAX_DEFAULTS.items():
            for entity_id in candidates:
                state = hass.states.get(entity_id)
                if state is not None:
                    sensors[conf_key] = entity_id
                    break

        # Detect SolaX entity prefix for control entities
        prefix = _find_solax_prefix(hass)

        result = {
            CONF_INVERTER_TYPE: INVERTER_TYPE_SOLAX,
            "detected": True,
            "sensors": sensors,
        }
        if prefix:
            result["solax_prefix"] = prefix
            # Pre-fill control entity IDs based on detected prefix
            result["solax_remotecontrol_power_control"] = f"select.{prefix}remotecontrol_power_control"
            result["solax_remotecontrol_active_power"] = f"number.{prefix}remotecontrol_active_power"
            result["solax_remotecontrol_autorepeat_duration"] = f"number.{prefix}remotecontrol_autorepeat_duration"
            result["solax_remotecontrol_duration"] = f"number.{prefix}remotecontrol_duration"
            result["solax_remotecontrol_trigger"] = f"button.{prefix}remotecontrol_trigger"
            result["solax_selfuse_discharge_min_soc"] = f"number.{prefix}selfuse_discharge_min_soc"

        connection.send_result(msg["id"], result)
        return

    # Check if SolarEdge Modbus Multi integration is loaded
    solaredge_entries = hass.config_entries.async_entries("solaredge_modbus_multi")
    solaredge_loaded = any(e.state.value == "loaded" for e in solaredge_entries)

    if solaredge_loaded:
        # Detect prefix first — used for both sensors and control entities
        prefix = _find_solaredge_prefix(hass)

        # Detect read-only sensors using prefix + suffix candidates
        sensors = {}
        for conf_key, suffixes in SOLAREDGE_SENSOR_SUFFIXES.items():
            for suffix in suffixes:
                # Try prefix-based entity first (handles solaredge_i1_, etc.)
                if prefix:
                    entity_id = f"sensor.{prefix}{suffix}"
                    state = hass.states.get(entity_id)
                    if state is not None:
                        sensors[conf_key] = entity_id
                        break
                # Fallback: scan all sensor states for this suffix
                if conf_key not in sensors:
                    for state in hass.states.async_all("sensor"):
                        if (state.entity_id.endswith(suffix)
                                and "solaredge" in state.entity_id):
                            sensors[conf_key] = state.entity_id
                            break

        result = {
            CONF_INVERTER_TYPE: INVERTER_TYPE_SOLAREDGE,
            "detected": True,
            "sensors": sensors,
        }
        if prefix:
            result["solaredge_prefix"] = prefix
            # Detect control entities — try suffix variants
            for config_key, candidates in SOLAREDGE_CONTROL_SUFFIXES.items():
                for domain, suffix in candidates:
                    entity_id = f"{domain}.{prefix}{suffix}"
                    state = hass.states.get(entity_id)
                    if state is not None:
                        result[config_key] = entity_id
                        break

            # Detect additional inverters (multi-inverter setups)
            extra_inverters = _find_solaredge_additional_inverters(hass, prefix)
            if extra_inverters:
                # Use the first additional inverter's ac_power as second PV sensor
                pv2_id = f"sensor.{extra_inverters[0]}ac_power"
                state = hass.states.get(pv2_id)
                if state is not None:
                    sensors[CONF_PV_POWER_SENSOR_2] = pv2_id

        connection.send_result(msg["id"], result)
        return

    # Check if Fronius native integration is loaded
    fronius_entries = hass.config_entries.async_entries("fronius")
    fronius_loaded = any(e.state.value == "loaded" for e in fronius_entries)

    if fronius_loaded:
        # Detect Fronius sensors by suffix scanning
        sensors = {}
        for conf_key, suffixes in FRONIUS_SENSOR_SUFFIXES.items():
            for suffix in suffixes:
                for state in hass.states.async_all("sensor"):
                    if (state.entity_id.endswith(suffix)
                            and state.state not in ("unavailable", "unknown")):
                        # Verify it's a Fronius entity by checking naming
                        eid = state.entity_id
                        if ("fronius" in eid or "solarnet" in eid
                                or "power_flow" in eid or "byd" in eid.lower()):
                            sensors[conf_key] = eid
                            break
                if conf_key in sensors:
                    break

        result = {
            CONF_INVERTER_TYPE: INVERTER_TYPE_FRONIUS,
            "detected": True,
            "sensors": sensors,
        }
        connection.send_result(msg["id"], result)
        return

    # Neither Huawei, SolaX, SolarEdge, nor Fronius detected
    connection.send_result(msg["id"], {"detected": False, "sensors": {}})


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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_feedin_statistics",
        vol.Optional("days", default=0): vol.Coerce(int),
    }
)
@websocket_api.async_response
async def ws_get_feedin_statistics(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return feed-in statistics for the requested period.

    Args (via msg):
        days: Number of days to return daily data for. 0 = all data (default).
    """
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    stats = data.get("feedin_stats")
    empty_state = {"kwh": 0.0, "count": 0, "duration_min": 0}
    empty = {"morning": dict(empty_state), "evening": dict(empty_state)}

    if not stats:
        connection.send_result(msg["id"], {
            "daily": {},
            "today": empty,
            "week": empty,
            "month": empty,
            "year": empty,
            "total": empty,
        })
        return

    days = msg.get("days", 0)
    from datetime import datetime, timedelta
    now_str = datetime.now().strftime("%Y-%m-%d")

    if days > 0:
        start_str = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        daily = stats.get_daily_stats(start_date=start_str, end_date=now_str)
    else:
        daily = stats.get_daily_stats()

    connection.send_result(msg["id"], {
        "daily": daily,
        "today": stats.get_summary(days=1),
        "week": stats.get_summary(days=7),
        "month": stats.get_summary(days=30),
        "year": stats.get_summary(days=365),
        "total": stats.get_summary(days=None),
    })
