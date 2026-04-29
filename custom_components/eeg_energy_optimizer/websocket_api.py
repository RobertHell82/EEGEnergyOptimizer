"""WebSocket API for EEG Energy Optimizer panel."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    COMBINED_BATTERY_POWER_SENSOR_ID,
    COMBINED_GRID_POWER_SENSOR_ID,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_POWER_CHARGE_SENSOR,
    CONF_BATTERY_POWER_DISCHARGE_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_GRID_POWER_EXPORT_SENSOR,
    CONF_GRID_POWER_IMPORT_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    CONF_PV_POWER_SENSOR_2,
    CONF_TELEMETRY_ENABLED,
    DOMAIN,
    INVERTER_TYPE_HUAWEI,
    INVERTER_TYPE_SOLAX,
    INVERTER_TYPE_SOLAREDGE,
    INVERTER_TYPE_FRONIUS,
    TELEMETRY_SETTINGS_KEYS,
)
# I-4: Der shared Profile-Builder lebt in __init__.py. Da __init__.py uns
# importiert, würde ein direkter `from . import _build_telemetry_profile`
# einen Zirkular-Import erzeugen. Stattdessen: lazy lookup über das Modul-
# Objekt zur Laufzeit (siehe `_get_build_telemetry_profile()` unten).
def _get_build_telemetry_profile():
    """Hole den shared Profile-Builder aus __init__.py.

    I-4 / W-3 — eine einzige Quelle der Wahrheit. Tests können die Funktion
    via patch.object(websocket_api, "_build_telemetry_profile", ...)
    überschreiben — siehe `_build_telemetry_profile = ...` unter dem Import.
    """
    from . import _build_telemetry_profile as _impl
    # Spiegele die aktuelle Referenz ins Modul, damit Tests via patch.object
    # auf `websocket_api._build_telemetry_profile` zugreifen können.
    return _impl


# Modulvariable, die Tests via patch.object überschreiben können (I-4 / W-3
# Single-Source-Pin in test_websocket_telemetry.py::test_enable_uses_shared_profile_helper).
# Wird zur Laufzeit aus __init__.py gefüllt — der Import erfolgt lazy beim
# ersten Aufruf des Befehls (siehe ws_telemetry_enable unten).
_build_telemetry_profile = None  # type: ignore[assignment]

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
#
# Multiple suffixes per conf_key cover the different naming variants that
# show up in the wild:
#   - English unique-id style (post-2024 HA core integration default):
#     state_of_charge, power_photovoltaics, power_grid, power_battery,
#     capacity_maximum
#   - Localized (DE) friendly-name slugs as seen on installations that
#     were set up before HA stopped translating entity_ids, or where the
#     user has manually renamed entities to the German friendly names:
#     ladezustand, pv_leistung, leistung_netz, leistung_batterie,
#     maximale_kapazitat, ausgelegte_kapazitat
#   - "battery_level" / "soc" as widely-used short aliases
#
# Lookup order matters: first match wins, so the more specific / canonical
# English suffixes are listed first.
FRONIUS_SENSOR_SUFFIXES: dict[str, list[str]] = {
    CONF_BATTERY_SOC_SENSOR: [
        "state_of_charge",
        "battery_state_of_charge",
        "ladezustand",
        "battery_level",
        "_soc",
    ],
    CONF_PV_POWER_SENSOR: [
        "power_photovoltaics",
        "pv_power",
        "pv_leistung",
        "photovoltaikleistung",
    ],
    CONF_GRID_POWER_SENSOR: [
        "power_grid",
        "grid_power",
        "leistung_netz",
        "netzleistung",
    ],
    CONF_BATTERY_POWER_SENSOR: [
        "power_battery",
        "battery_power",
        "leistung_batterie",
        "batterieleistung",
    ],
    CONF_BATTERY_CAPACITY_SENSOR: [
        "capacity_maximum",
        "maximum_capacity",
        "maximale_kapazitat",
        "ausgelegte_kapazitat",
        "designed_capacity",
    ],
}

# Fronius pair-sensor suffixes — directional, always-positive sensors that
# come in matched pairs. When both sides are detected, the wizard records
# them in CONF_*_CHARGE/DISCHARGE / CONF_*_EXPORT/IMPORT and points the
# canonical CONF_BATTERY_POWER_SENSOR / CONF_GRID_POWER_SENSOR at the
# synthetic combined sensors created at setup time.
FRONIUS_PAIR_SUFFIXES: dict[tuple[str, str], list[tuple[str, str]]] = {
    # battery: (charge_key, discharge_key) → list of (charge_suffix, discharge_suffix)
    (CONF_BATTERY_POWER_CHARGE_SENSOR, CONF_BATTERY_POWER_DISCHARGE_SENSOR): [
        ("battery_power_charging", "battery_power_discharging"),
        ("ladeleistung", "entladeleistung"),
    ],
    # grid: (export_key, import_key) → list of (export_suffix, import_suffix)
    (CONF_GRID_POWER_EXPORT_SENSOR, CONF_GRID_POWER_IMPORT_SENSOR): [
        ("leistung_netzeinspeisung", "leistung_netzbezug"),
        ("grid_power_export", "grid_power_import"),
    ],
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
    websocket_api.async_register_command(hass, ws_probe_fronius)
    websocket_api.async_register_command(hass, ws_manual_stop)
    websocket_api.async_register_command(hass, ws_manual_discharge)
    websocket_api.async_register_command(hass, ws_manual_block_charge)
    websocket_api.async_register_command(hass, ws_set_test_overrides)
    websocket_api.async_register_command(hass, ws_get_test_overrides)
    websocket_api.async_register_command(hass, ws_clear_test_overrides)
    websocket_api.async_register_command(hass, ws_get_activity_log)
    websocket_api.async_register_command(hass, ws_get_feedin_statistics)
    websocket_api.async_register_command(hass, ws_get_peakshare_communities)
    websocket_api.async_register_command(hass, ws_get_peakshare_data)
    websocket_api.async_register_command(hass, ws_get_consumption_profile_status)
    websocket_api.async_register_command(hass, ws_refresh_consumption_profile)
    # Phase 8 — Telemetry-Steuerung (D-32 / D-33)
    websocket_api.async_register_command(hass, ws_telemetry_get_status)
    websocket_api.async_register_command(hass, ws_telemetry_enable)
    websocket_api.async_register_command(hass, ws_telemetry_disable)
    websocket_api.async_register_command(hass, ws_telemetry_forget)


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

    # Pair-sensor → synthetic-sensor redirection. If the user (or auto-detect)
    # filled the directional pair config keys, point the canonical battery_/
    # grid_power_sensor at the synthetic combined sensor created at setup
    # time. Downstream consumers (Hausverbrauch, optimizer watchdog,
    # statistics, dashboard) then read one consistent signed source —
    # exactly like a single-sensor inverter would.
    if (new_data.get(CONF_BATTERY_POWER_CHARGE_SENSOR)
            and new_data.get(CONF_BATTERY_POWER_DISCHARGE_SENSOR)):
        new_data[CONF_BATTERY_POWER_SENSOR] = COMBINED_BATTERY_POWER_SENSOR_ID
    if (new_data.get(CONF_GRID_POWER_EXPORT_SENSOR)
            and new_data.get(CONF_GRID_POWER_IMPORT_SENSOR)):
        new_data[CONF_GRID_POWER_SENSOR] = COMBINED_GRID_POWER_SENSOR_ID

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
        # Detect Fronius sensors by restricting to entities owned by the
        # `fronius` Core integration. Pure suffix matching plus loose name
        # heuristics (fronius/solarnet/power_flow/byd) used to leak in
        # standalone BYD BMS entities or other integrations that happen to
        # ship a `state_of_charge` sensor — only used as wizard suggestions
        # but confusing for users with mixed setups.
        fronius_entry_ids = {e.entry_id for e in fronius_entries}
        ent_reg = er.async_get(hass)
        fronius_entity_ids = {
            entry.entity_id
            for entry in ent_reg.entities.values()
            if entry.config_entry_id in fronius_entry_ids
        }

        # Pre-collect all candidate Fronius-owned sensors for faster scanning.
        candidate_states = [
            s for s in hass.states.async_all("sensor")
            if s.entity_id in fronius_entity_ids
            and s.state not in ("unavailable", "unknown")
        ]

        # Suffix matching with word boundary check. Plain endswith() is
        # ambiguous: "entladeleistung" endswith "ladeleistung" is True, which
        # would mis-classify the discharge sensor as the charge sensor.
        # Require the suffix to start its own word — preceded by "_" or "."
        # (or to be the entire entity_id), unless the suffix already starts
        # with "_" (then the boundary is built in).
        def _suffix_matches(entity_id: str, suffix: str) -> bool:
            if not entity_id.endswith(suffix):
                return False
            if suffix.startswith("_"):
                return True
            head = entity_id[: -len(suffix)]
            return head == "" or head.endswith("_") or head.endswith(".")

        sensors = {}
        for conf_key, suffixes in FRONIUS_SENSOR_SUFFIXES.items():
            for suffix in suffixes:
                for state in candidate_states:
                    if _suffix_matches(state.entity_id, suffix):
                        sensors[conf_key] = state.entity_id
                        break
                if conf_key in sensors:
                    break

        # Detect directional pair sensors (charge/discharge, export/import).
        # When a complete pair is found, fill the dedicated pair config keys
        # AND point the canonical battery_/grid_power_sensor at the synthetic
        # combined sensor — that sensor is created at setup time when both
        # pair keys are present.
        for (pos_key, neg_key), pairs in FRONIUS_PAIR_SUFFIXES.items():
            for pos_suf, neg_suf in pairs:
                pos_match = next(
                    (s.entity_id for s in candidate_states
                     if _suffix_matches(s.entity_id, pos_suf)),
                    None,
                )
                neg_match = next(
                    (s.entity_id for s in candidate_states
                     if _suffix_matches(s.entity_id, neg_suf)),
                    None,
                )
                if pos_match and neg_match:
                    sensors[pos_key] = pos_match
                    sensors[neg_key] = neg_match
                    break
            # If the pair was filled, redirect the canonical key at the
            # synthetic combined sensor (overrides any single-sensor hit
            # the suffix scan above might have produced).
            if pos_key == CONF_BATTERY_POWER_CHARGE_SENSOR and pos_key in sensors:
                sensors[CONF_BATTERY_POWER_SENSOR] = COMBINED_BATTERY_POWER_SENSOR_ID
            if pos_key == CONF_GRID_POWER_EXPORT_SENSOR and pos_key in sensors:
                sensors[CONF_GRID_POWER_SENSOR] = COMBINED_GRID_POWER_SENSOR_ID

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


def _registers_to_string(registers) -> str:
    """Decode a sequence of 16-bit Modbus registers as ASCII (big-endian)."""
    chars = []
    for reg in registers:
        chars.append(chr((reg >> 8) & 0xFF))
        chars.append(chr(reg & 0xFF))
    return "".join(chars).rstrip("\x00 ").strip()


async def _probe_fronius_modbus(host: str, port: int, slave_id: int = 1) -> dict:
    """Read-only probe: connect to host:port, verify SunSpec ID, read the
    Common Block (Model 1) to identify the manufacturer and model. Closes
    the connection at the end. No writes ever happen here.
    """
    import asyncio
    result: dict = {"success": False}
    try:
        from pymodbus.client import AsyncModbusTcpClient
    except ImportError:
        result["error"] = "pymodbus nicht installiert."
        return result

    client = AsyncModbusTcpClient(host, port=port)
    try:
        try:
            await asyncio.wait_for(client.connect(), timeout=5)
        except asyncio.TimeoutError:
            result["error"] = f"Timeout beim Verbindungsaufbau zu {host}:{port}."
            return result
        if not client.connected:
            result["error"] = f"Keine Modbus-TCP-Verbindung zu {host}:{port}."
            return result

        # pymodbus 3.9+ renamed `slave` to `device_id`. Probe the signature
        # once and use whichever keyword the active client accepts.
        import inspect
        try:
            sig = inspect.signature(client.read_holding_registers)
            slave_kw = {"device_id": slave_id} if "device_id" in sig.parameters else {"slave": slave_id}
        except (TypeError, ValueError):
            slave_kw = {"slave": slave_id}

        # SunSpec header at 40000-40001 must read "SunS"
        r = await asyncio.wait_for(
            client.read_holding_registers(address=40000, count=2, **slave_kw),
            timeout=5,
        )
        if r.isError():
            result["error"] = "Modbus-Fehler beim Lesen des SunSpec-Headers."
            return result
        if r.registers[0] != 0x5375 or r.registers[1] != 0x6E53:
            result["error"] = (
                f"Kein SunSpec-Gerät unter {host}:{port} "
                f"(Header: 0x{r.registers[0]:04X} 0x{r.registers[1]:04X})."
            )
            return result

        # Common Block (Model 1) starts at 40002. Layout:
        #   40002 model_id (=1)  40003 length (=66)
        #   40004..40019 Manufacturer (16 regs / 32 chars)
        #   40020..40035 Model (16 regs)
        r = await asyncio.wait_for(
            client.read_holding_registers(address=40002, count=34, **slave_kw),
            timeout=5,
        )
        if r.isError():
            result["error"] = "Modbus-Fehler beim Lesen des Common Blocks."
            return result
        if r.registers[0] != 1:
            result["error"] = (
                f"Common Block fehlt (Model-ID = {r.registers[0]}, erwartet 1)."
            )
            return result

        manufacturer = _registers_to_string(r.registers[2:18])
        model_name = _registers_to_string(r.registers[18:34])

        result["success"] = True
        result["manufacturer"] = manufacturer
        result["model"] = model_name
        result["is_fronius"] = "fronius" in manufacturer.lower()
        return result
    except Exception as exc:
        result["error"] = f"Verbindungsfehler: {exc}"
        return result
    finally:
        try:
            client.close()
        except Exception:
            pass


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/probe_fronius",
        vol.Required("host"): str,
        vol.Optional("port", default=502): int,
    }
)
@websocket_api.async_response
async def ws_probe_fronius(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Read-only probe of a Fronius Gen24 over Modbus TCP.

    Used by the wizard's "Weiter" step to verify that the entered IP
    actually points at a Fronius inverter before saving the config.
    """
    host = (msg.get("host") or "").strip()
    port = int(msg.get("port") or 502)
    if not host:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Keine IP-Adresse angegeben.",
        })
        return
    result = await _probe_fronius_modbus(host, port)
    connection.send_result(msg["id"], result)


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


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_peakshare_communities",
    }
)
@websocket_api.async_response
async def ws_get_peakshare_communities(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return list of PeakShare community names for the dropdown."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    peakshare = data.get("peakshare")
    if not peakshare:
        # Fetch directly if no provider yet (during setup wizard)
        from .peakshare import PeakShareProvider

        temp = PeakShareProvider(hass, "temp")
        api_data = await temp.async_fetch()
        communities = [
            c["name"]
            for c in (api_data or {}).get("communities", [])
            if isinstance(c, dict) and "name" in c
        ]
    else:
        communities = peakshare.get_communities()
        if not communities:
            await peakshare.async_fetch()
            communities = peakshare.get_communities()

    connection.send_result(msg["id"], {"communities": communities})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_peakshare_data",
    }
)
@websocket_api.async_response
async def ws_get_peakshare_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return PeakShare forecast data for dashboard display."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    peakshare = data.get("peakshare")
    config = dict(entry.data)
    community_name = config.get("peakshare_community", "BEG")

    if not peakshare or not peakshare._cache:
        connection.send_result(msg["id"], {
            "community": community_name,
            "hours": [],
            "cache_age_minutes": None,
            "discharge_plan": None,
        })
        return

    # Find selected community hours
    communities = peakshare._cache.get("communities", [])
    hours = []
    for c in communities:
        if isinstance(c, dict) and c.get("name") == community_name:
            hours = c.get("hours", [])
            break

    # Cache age
    cache_age = None
    if peakshare._cache_time:
        from datetime import datetime, timezone
        age_sec = (datetime.now(timezone.utc) - peakshare._cache_time).total_seconds()
        cache_age = round(age_sec / 60)

    # Discharge plan if computed
    plan_info = None
    if peakshare._discharge_plan_date and peakshare._discharge_plan:
        plan_start, plan_end = peakshare._discharge_plan
        plan_info = {
            "start": plan_start.strftime("%H:%M"),
            "end": plan_end.strftime("%H:%M"),
            "date": peakshare._discharge_plan_date,
            "jitter": peakshare._jitter_today,
        }

    connection.send_result(msg["id"], {
        "community": community_name,
        "hours": hours,
        "cache_age_minutes": cache_age,
        "discharge_plan": plan_info,
    })


def _consumption_status_payload(coordinator) -> dict:
    return {
        "last_refresh": coordinator.last_update_iso,
        "duration_ms": coordinator.last_duration_ms,
        "stats_count": coordinator.stats_count,
        "lookback_weeks": coordinator.lookback_weeks,
        "is_running": coordinator.is_running,
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/get_consumption_profile_status",
    }
)
@websocket_api.async_response
async def ws_get_consumption_profile_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Status der Verbrauchsprofil-Berechnung (für Panel-Anzeige)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    coordinator = data.get("coordinator")
    if coordinator is None:
        connection.send_result(msg["id"], {
            "available": False,
        })
        return

    payload = _consumption_status_payload(coordinator)
    payload["available"] = True
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "eeg_optimizer/refresh_consumption_profile",
    }
)
@websocket_api.async_response
async def ws_refresh_consumption_profile(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Verbrauchsprofil komplett neu aus dem Recorder berechnen.

    Berücksichtigt das aktuell gespeicherte Lookback-Fenster (lookback_weeks).
    Liefert nach Abschluss den aktualisierten Status. Wenn bereits ein
    Refresh läuft, wird sofort mit busy=True geantwortet (kein Warten).
    """
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return

    refresh = data.get("refresh_consumption_profile")
    coordinator = data.get("coordinator")
    lock = data.get("consumption_refresh_lock")

    if refresh is None or coordinator is None:
        connection.send_result(msg["id"], {
            "success": False,
            "error": "Verbrauchsprofil-Komponente nicht initialisiert.",
        })
        return

    if lock is not None and lock.locked():
        payload = _consumption_status_payload(coordinator)
        payload["success"] = False
        payload["busy"] = True
        connection.send_result(msg["id"], payload)
        return

    try:
        await refresh()
    except Exception as exc:
        _LOGGER.exception("Consumption profile refresh failed")
        connection.send_result(msg["id"], {
            "success": False,
            "error": f"Fehler bei der Neuberechnung: {exc}",
        })
        return

    payload = _consumption_status_payload(coordinator)
    payload["success"] = True
    connection.send_result(msg["id"], payload)


# ---------------------------------------------------------------------------
# Phase 8 — Telemetry control (D-32 / D-33)
# ---------------------------------------------------------------------------
#
# 4 neue WebSocket-Befehle, die das Panel (08-04) ansteuert:
#   - telemetry_get_status   → Status-Anzeige (registered? enabled? buffer?)
#   - telemetry_enable       → Initial-Register, setzt CONF_TELEMETRY_ENABLED=True
#   - telemetry_disable      → Pausiert Senden, Identity bleibt erhalten
#   - telemetry_forget       → DELETE Backend + lokale Cleanup
#
# I-4 / W-3: ws_telemetry_enable nutzt den OBEN importierten
# `_build_telemetry_profile` aus __init__.py — KEIN lokaler Profile-Builder.


@websocket_api.websocket_command(
    {vol.Required("type"): "eeg_optimizer/telemetry_get_status"}
)
@websocket_api.async_response
async def ws_telemetry_get_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Liefert den aktuellen Telemetrie-Status für die Panel-Anzeige."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    reporter = data.get("telemetry_reporter") if data else None
    buffer = data.get("telemetry_buffer") if data else None
    config = {**entry.data, **entry.options}
    identity = buffer.get_identity() if buffer is not None else None
    prefix = identity["installation_id"][:8] if identity else None
    snap_q = data.get("snapshot_queue") if data else None
    snap_q = snap_q if snap_q is not None else []
    buf_size = buffer.size() if buffer is not None else 0
    connection.send_result(msg["id"], {
        "configured": bool(reporter and getattr(reporter, "is_configured", False)),
        "enabled": bool(config.get(CONF_TELEMETRY_ENABLED, False)),
        "registered": bool(identity),
        "installation_id_prefix": prefix,
        "registered_at": identity.get("registered_at") if identity else None,
        "queue_size": len(snap_q) + buf_size,
        "buffer_size": buf_size,
        "last_send_at": data.get("telemetry_last_send_at") if data else None,
    })


@websocket_api.websocket_command(
    {vol.Required("type"): "eeg_optimizer/telemetry_enable"}
)
@websocket_api.async_response
async def ws_telemetry_enable(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Aktiviert die Telemetrie — Initial-Register beim Backend (D-30)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    reporter = data.get("telemetry_reporter") if data else None
    buffer = data.get("telemetry_buffer") if data else None
    if reporter is None or buffer is None:
        connection.send_result(msg["id"], {
            "success": False, "error": "telemetry_unavailable",
        })
        return
    if not getattr(reporter, "is_configured", False):
        connection.send_result(msg["id"], {
            "success": False, "error": "backend_not_configured",
        })
        return
    # Idempotent: schon aktiv → kein erneutes Register
    if buffer.identity_known() and entry.data.get(CONF_TELEMETRY_ENABLED):
        ident = buffer.get_identity() or {}
        prefix = ident.get("installation_id", "")[:8] or None
        connection.send_result(msg["id"], {
            "success": True,
            "already_active": True,
            "installation_id_prefix": prefix,
        })
        return

    # I-4 / W-3 — der gemeinsame Profile-Builder. Modulvariable wird beim
    # ersten Aufruf gefüllt (kein Zirkular-Import zur Laufzeit, weil
    # __init__.py jetzt vollständig geladen ist). Tests können die
    # Modulvariable via patch.object überschreiben.
    global _build_telemetry_profile
    if _build_telemetry_profile is None:
        _build_telemetry_profile = _get_build_telemetry_profile()
    identity = buffer.get_identity() or {}
    profile = _build_telemetry_profile(
        hass, entry, identity_registered_at=identity.get("registered_at"),
    )
    try:
        ok = await reporter.register(profile)
    except Exception:
        _LOGGER.exception("Telemetry: register call raised")
        ok = False
    if not ok:
        connection.send_result(msg["id"], {
            "success": False, "error": "register_failed",
        })
        return

    new_data = {**entry.data, CONF_TELEMETRY_ENABLED: True}
    hass.config_entries.async_update_entry(entry, data=new_data)
    ident = buffer.get_identity() or {}
    prefix = ident.get("installation_id", "")[:8] if ident else None
    connection.send_result(msg["id"], {
        "success": True,
        "installation_id_prefix": prefix,
    })


@websocket_api.websocket_command(
    {vol.Required("type"): "eeg_optimizer/telemetry_disable"}
)
@websocket_api.async_response
async def ws_telemetry_disable(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Pausiert die Telemetrie — Identity bleibt erhalten (D-32)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    new_data = {**entry.data, CONF_TELEMETRY_ENABLED: False}
    hass.config_entries.async_update_entry(entry, data=new_data)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {vol.Required("type"): "eeg_optimizer/telemetry_forget"}
)
@websocket_api.async_response
async def ws_telemetry_forget(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Vergisst die Installation — DELETE Backend + lokale Cleanup (D-31, D-33)."""
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    reporter = data.get("telemetry_reporter") if data else None
    backend_deleted = False
    if reporter is not None:
        try:
            backend_deleted = bool(await reporter.forget())
        except Exception:
            _LOGGER.exception("Telemetry: forget call raised")
            backend_deleted = False
    new_data = {**entry.data, CONF_TELEMETRY_ENABLED: False}
    hass.config_entries.async_update_entry(entry, data=new_data)
    # Erfolg auch bei Backend-Fehler (lokale Cleanup ist passiert)
    connection.send_result(msg["id"], {
        "success": True,
        "backend_deleted": backend_deleted,
    })
