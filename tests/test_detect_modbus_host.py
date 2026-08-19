"""Tests für Auto-Detection-Details von `ws_detect_sensors`.

1. Modbus-Host-Vorbefüllung: für Fronius / Kostal / SMA wird der Host aus
   dem Config-Entry der Quell-Integration mitgeliefert, damit das Panel das
   Modbus-IP-Feld vorbefüllen kann (`_source_entry_host` /
   `_first_loaded_entry_host`).
2. Kostal-PV-Sensor-Priorität: "Solar Power" (Dc_P) enthält auf Hybrid-
   Geräten die Batterieentladung — die Detection muss
   `sum_power_of_all_pv_dc_inputs` bevorzugen (Beta-Gerät 19.08.2026:
   solar_power 729 W bei echter PV 0 W und Entladung 727 W).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_SOC_SENSOR,
    CONF_KOSTAL_MODBUS_HOST,
    CONF_PV_POWER_SENSOR,
)
from custom_components.eeg_energy_optimizer.websocket_api import (
    _first_loaded_entry_host,
    _source_entry_host,
    ws_detect_sensors,
)


def _entry(host, state="loaded"):
    return SimpleNamespace(
        data={"host": host} if host is not None else {},
        state=SimpleNamespace(value=state),
    )


class TestSourceEntryHost:
    def test_plain_ip(self):
        assert _source_entry_host(_entry("192.168.1.42")) == "192.168.1.42"

    def test_hostname(self):
        assert _source_entry_host(_entry("plenticore.local")) == "plenticore.local"

    def test_strips_whitespace(self):
        assert _source_entry_host(_entry("  192.168.1.42 ")) == "192.168.1.42"

    def test_strips_scheme_and_path(self):
        # Fronius erlaubt bei der Einrichtung eine volle URL.
        assert _source_entry_host(_entry("http://192.168.1.5/")) == "192.168.1.5"
        assert (
            _source_entry_host(_entry("https://fronius.local/solar_api"))
            == "fronius.local"
        )

    def test_strips_trailing_slash(self):
        assert _source_entry_host(_entry("192.168.1.5/")) == "192.168.1.5"

    def test_missing_or_empty_host(self):
        assert _source_entry_host(_entry(None)) is None
        assert _source_entry_host(_entry("")) is None
        assert _source_entry_host(_entry("   ")) is None

    def test_non_string_host(self):
        assert _source_entry_host(_entry(502)) is None


class TestFirstLoadedEntryHost:
    def test_prefers_loaded_entry(self):
        entries = [
            _entry("10.0.0.1", state="setup_error"),
            _entry("10.0.0.2", state="loaded"),
        ]
        assert _first_loaded_entry_host(entries) == "10.0.0.2"

    def test_falls_back_to_first_entry_when_none_loaded(self):
        entries = [
            _entry("10.0.0.1", state="setup_error"),
            _entry("10.0.0.2", state="not_loaded"),
        ]
        assert _first_loaded_entry_host(entries) == "10.0.0.1"

    def test_empty_list(self):
        assert _first_loaded_entry_host([]) is None


# ---------------------------------------------------------------------------
# Kostal-Detection end-to-end (PV-Sensor-Priorität + Modbus-Host im Result)
# ---------------------------------------------------------------------------
def _state(entity_id, value="1"):
    return SimpleNamespace(entity_id=entity_id, state=value)


def _make_kostal_hass(entity_ids):
    """hass-Mock: nur kostal_plenticore geladen, mit den gegebenen Sensoren."""
    kostal_entry = SimpleNamespace(
        entry_id="kostal-1",
        state=SimpleNamespace(value="loaded"),
        data={"host": "192.168.1.50"},
    )
    hass = MagicMock()

    def _entries(domain=None):
        return [kostal_entry] if domain == "kostal_plenticore" else []

    hass.config_entries.async_entries = MagicMock(side_effect=_entries)
    hass.config_entries.async_get_entry = MagicMock(return_value=kostal_entry)
    hass.states.async_all = MagicMock(
        return_value=[_state(eid) for eid in entity_ids]
    )
    hass.states.get = MagicMock(return_value=None)

    registry = MagicMock()
    registry.entities = {
        eid: SimpleNamespace(entity_id=eid, config_entry_id="kostal-1")
        for eid in entity_ids
    }
    return hass, registry


async def _detect(hass, registry):
    connection = MagicMock()
    inner = getattr(ws_detect_sensors, "_func", ws_detect_sensors)
    with patch(
        "custom_components.eeg_energy_optimizer.websocket_api.er.async_get",
        return_value=registry,
    ):
        await inner(hass, connection, {"id": 1, "type": "eeg_optimizer/detect_sensors"})
    connection.send_result.assert_called_once()
    return connection.send_result.call_args[0][1]


@pytest.mark.asyncio
class TestKostalDetection:
    async def test_pv_prefers_dc_input_sum_over_solar_power(self):
        # Beide PV-Kandidaten vorhanden → der echte PV-Summensensor gewinnt,
        # obwohl solar_power (Dc_P, enthält Batterieentladung) auch matcht.
        hass, registry = _make_kostal_hass([
            "sensor.roman_battery_soc",
            "sensor.roman_solar_power",
            "sensor.roman_sum_power_of_all_pv_dc_inputs",
        ])
        result = await _detect(hass, registry)
        assert result["detected"] is True
        assert (
            result["sensors"][CONF_PV_POWER_SENSOR]
            == "sensor.roman_sum_power_of_all_pv_dc_inputs"
        )

    async def test_pv_falls_back_to_solar_power(self):
        # Summensensor deaktiviert/fehlend → Dc_P bleibt als Fallback.
        hass, registry = _make_kostal_hass([
            "sensor.roman_battery_soc",
            "sensor.roman_solar_power",
        ])
        result = await _detect(hass, registry)
        assert result["sensors"][CONF_PV_POWER_SENSOR] == "sensor.roman_solar_power"

    async def test_result_contains_modbus_host_from_source_entry(self):
        hass, registry = _make_kostal_hass([
            "sensor.roman_battery_soc",
            "sensor.roman_sum_power_of_all_pv_dc_inputs",
        ])
        result = await _detect(hass, registry)
        assert result[CONF_KOSTAL_MODBUS_HOST] == "192.168.1.50"

    async def test_battery_soc_detected(self):
        hass, registry = _make_kostal_hass([
            "sensor.roman_battery_soc",
            "sensor.roman_sum_power_of_all_pv_dc_inputs",
        ])
        result = await _detect(hass, registry)
        assert result["sensors"][CONF_BATTERY_SOC_SENSOR] == "sensor.roman_battery_soc"
