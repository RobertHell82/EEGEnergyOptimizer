"""Tests for the EntscheidungsSensor (decision sensor)."""
from unittest.mock import MagicMock
from types import SimpleNamespace
import pytest

from custom_components.eeg_energy_optimizer.sensor import EntscheidungsSensor
from custom_components.eeg_energy_optimizer.const import DOMAIN


def _make_decision(**overrides):
    """Create a mock Decision with default values."""
    defaults = {
        "timestamp": "2026-03-21T15:30:00",
        "zustand": "Normal",
        "überschuss_faktor": 1.8,
        "energiebedarf_kwh": 5.0,
        "ladung_blockiert": False,
        "entladung_aktiv": False,
        "entladeleistung_kw": 0.0,
        "min_soc_berechnet": 25.0,
        "nächste_aktion": "Normalbetrieb",
        "markdown": "## Status\nNormalbetrieb",
        "ausführung": True,
        "block_reasons": [],
        # Morning delay status card
        "morning_status": "deaktiviert",
        "morning_reason": "",
        "morning_in_window": False,
        "morning_pv_today_kwh": 0.0,
        "morning_threshold_kwh": 0.0,
        "morning_consumption_kwh": 0.0,
        "morning_buffer_kwh": 0.0,
        "morning_battery_kwh": 0.0,
        "morning_end_time": "",
        "morning_sunrise_tomorrow": "",
        # Discharge status card
        "discharge_status": "deaktiviert",
        "discharge_reasons": [],
        "discharge_soc": 0.0,
        "discharge_min_soc": 0.0,
        "discharge_pv_tomorrow_kwh": 0.0,
        "discharge_demand_overnight_kwh": 0.0,
        "discharge_consumption_daylight_kwh": 0.0,
        "discharge_safety_buffer_kwh": 0.0,
        "discharge_battery_charge_needed_kwh": 0.0,
        "discharge_demand_total_kwh": 0.0,
        "discharge_power_kw": 0.0,
        "discharge_start_time": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestEntscheidungsSensor:
    def test_initial_state_is_none(self):
        sensor = EntscheidungsSensor("test_entry")
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {}

    def test_unique_id(self):
        sensor = EntscheidungsSensor("test_entry")
        assert sensor._attr_unique_id == f"{DOMAIN}_test_entry_entscheidung"

    def test_device_info_identifiers(self):
        sensor = EntscheidungsSensor("test_entry")
        assert (DOMAIN, "test_entry") in sensor._attr_device_info["identifiers"]

    def test_update_sets_state(self):
        sensor = EntscheidungsSensor("test_entry")
        decision = _make_decision(nächste_aktion="Abend-Entladung 20:00")
        sensor.update_from_decision(decision)
        assert sensor._attr_native_value == "Abend-Entladung 20:00"

    def test_update_sets_markdown(self):
        sensor = EntscheidungsSensor("test_entry")
        md = "## Status\nAbend-Entladung\n\n### Details\n- SOC: 85%"
        decision = _make_decision(markdown=md)
        sensor.update_from_decision(decision)
        assert sensor._attr_extra_state_attributes["markdown"] == md

    def test_update_sets_all_attributes(self):
        sensor = EntscheidungsSensor("test_entry")
        decision = _make_decision(
            entladung_aktiv=True,
            ladung_blockiert=False,
            min_soc_berechnet=32.0,
            entladeleistung_kw=3.0,
            ausführung=True,
            timestamp="2026-03-21T20:00:00",
        )
        sensor.update_from_decision(decision)
        attrs = sensor._attr_extra_state_attributes
        assert attrs["zustand"] == "Normal"
        assert attrs["entladung_aktiv"] is True
        assert attrs["ladung_blockiert"] is False
        assert attrs["min_soc"] == 32.0
        assert attrs["entladeleistung_kw"] == 3.0
        assert attrs["ausführung"] is True
        assert attrs["letzte_aktualisierung"] == "2026-03-21T20:00:00"

    def test_discharge_preview_in_attributes(self):
        sensor = EntscheidungsSensor("test_entry")
        decision = _make_decision(
            entladung_aktiv=True,
            entladeleistung_kw=3.0,
            min_soc_berechnet=28.0,
            nächste_aktion="Abend-Entladung 20:00",
        )
        sensor.update_from_decision(decision)
        attrs = sensor._attr_extra_state_attributes
        assert attrs["entladung_aktiv"] is True
        assert attrs["entladeleistung_kw"] == 3.0
        assert attrs["min_soc"] == 28.0

    def test_morning_block_in_attributes(self):
        sensor = EntscheidungsSensor("test_entry")
        decision = _make_decision(
            ladung_blockiert=True,
            zustand="Morgen-Einspeisung",
            nächste_aktion="Morgen-Einspeisung bis 10:00",
        )
        sensor.update_from_decision(decision)
        attrs = sensor._attr_extra_state_attributes
        assert attrs["ladung_blockiert"] is True
        assert attrs["zustand"] == "Morgen-Einspeisung"
