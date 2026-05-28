"""Tests for SolarEdge StorEdge inverter — focus on multi-inverter discharge
distribution (proportional split with cap redistribution).

Historischer Hintergrund: vor diesem Algorithmus halbierte der Driver die
Total-Power stur über alle Inverter (`power_kw / num_inverters`). Bei
unterschiedlich großen Batterien (z. B. i1=24.25 kWh, i2=14.55 kWh, beide
mit 20 % Backup-Reserve) erreichte die kleinere viel früher das Backup —
danach lief nur noch der größere Inverter weiter, was nutzbare Energie
ungenutzt ließ. Die proportionale Verteilung mit Cap-Redistribution sorgt
dafür, dass beide Batterien etwa gleichzeitig die Backup-Reserve erreichen.
"""

from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.solaredge import (
    SolarEdgeInverter,
)


# ---------------------------------------------------------------------------
# Pure algorithm tests — kein HA-Mock nötig, _distribute_proportional ist
# statisch und arbeitet nur auf primitiven Dicts.
# ---------------------------------------------------------------------------


class TestDistributeProportional:
    """Verteilung der Discharge-Power proportional zur nutzbaren Restkapazität."""

    def test_single_inverter_within_cap(self):
        """Single inverter, power below cap — gets all power."""
        result = SolarEdgeInverter._distribute_proportional(
            5.0, [{"prefix": "i1", "usable_kwh": 10.0, "max_kw": 10.0}]
        )
        assert result == {"i1": pytest.approx(5.0)}

    def test_single_inverter_above_cap(self):
        """Single inverter, requested power above cap — clipped to cap."""
        result = SolarEdgeInverter._distribute_proportional(
            12.0, [{"prefix": "i1", "usable_kwh": 10.0, "max_kw": 5.0}]
        )
        assert result == {"i1": pytest.approx(5.0)}

    def test_two_equal_inverters_equal_split(self):
        """Two inverters with identical usable energy → exact 50/50."""
        result = SolarEdgeInverter._distribute_proportional(
            6.0,
            [
                {"prefix": "i1", "usable_kwh": 10.0, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 10.0, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(3.0)
        assert result["i2"] == pytest.approx(3.0)

    def test_real_world_slot_b_at_6kw(self):
        """Reales Szenario aus Slot B (heute Morgen):
        i1: SOC 66, Backup 20, Kapazität 24.25 → usable 11.15 kWh, max 5 kW
        i2: SOC 53, Backup 20, Kapazität 14.55 → usable 4.80 kWh, max 5 kW
        Bei 6 kW: keine Caps, proportional 4.19 / 1.81.
        """
        result = SolarEdgeInverter._distribute_proportional(
            6.0,
            [
                {"prefix": "i1", "usable_kwh": 11.15, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 4.80, "max_kw": 5.0},
            ],
        )
        # Proportional: 6 × 11.15/15.95 = 4.194, 6 × 4.80/15.95 = 1.806
        assert result["i1"] == pytest.approx(4.194, abs=0.01)
        assert result["i2"] == pytest.approx(1.806, abs=0.01)
        assert sum(result.values()) == pytest.approx(6.0)

    def test_real_world_slot_b_at_8kw_caps_redistribute(self):
        """Bei 8 kW: i1 würde proportional 5.59 kW kriegen → gecappt auf 5,
        Überschuss 0.59 + i2's regulärer Anteil = 3 kW für i2.
        Praxis: i2 läuft 1.6h bei 3 kW → genau am Slot-Ende auf Backup.
        """
        result = SolarEdgeInverter._distribute_proportional(
            8.0,
            [
                {"prefix": "i1", "usable_kwh": 11.15, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 4.80, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(5.0)
        assert result["i2"] == pytest.approx(3.0)
        assert sum(result.values()) == pytest.approx(8.0)

    def test_real_world_slot_b_at_10kw_both_capped(self):
        """Bei 10 kW: beide Inverter am Cap, Rest geht nicht weg → Sum 10 kW.
        i2 ist nach 0.96 h leer, der Cap-Schutz kommt vom Inverter selbst."""
        result = SolarEdgeInverter._distribute_proportional(
            10.0,
            [
                {"prefix": "i1", "usable_kwh": 11.15, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 4.80, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(5.0)
        assert result["i2"] == pytest.approx(5.0)

    def test_three_inverters_iterative_redistribution(self):
        """3 Inverter, mehrere Cap-Stufen: testet Iteration über mehrere Runden.
        i1=usable 10/cap 5, i2=usable 5/cap 5, i3=usable 2/cap 5, total 12.
        Round 1: i1 capped. Round 2: i2 capped. Round 3: i3 bekommt Rest 2.
        """
        result = SolarEdgeInverter._distribute_proportional(
            12.0,
            [
                {"prefix": "i1", "usable_kwh": 10.0, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 5.0, "max_kw": 5.0},
                {"prefix": "i3", "usable_kwh": 2.0, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(5.0)
        assert result["i2"] == pytest.approx(5.0)
        assert result["i3"] == pytest.approx(2.0)

    def test_inverter_with_zero_usable_gets_nothing(self):
        """Inverter unter Backup-Reserve (usable=0) bekommt keine Power —
        die anderen mit Headroom kriegen alles."""
        result = SolarEdgeInverter._distribute_proportional(
            6.0,
            [
                {"prefix": "i1", "usable_kwh": 10.0, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 0.0, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(5.0)  # capped
        assert result["i2"] == pytest.approx(0.0)

    def test_all_inverters_at_backup_fallback_equal_split(self):
        """Wenn alle Batterien am Backup sind: equal split als Fallback —
        wird in der Praxis durch den Inverter selbst gestoppt, aber der
        Driver schickt einen sinnvollen Wert."""
        result = SolarEdgeInverter._distribute_proportional(
            6.0,
            [
                {"prefix": "i1", "usable_kwh": 0.0, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 0.0, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(3.0)
        assert result["i2"] == pytest.approx(3.0)

    def test_empty_inverter_list(self):
        """Keine Inverter — leeres Dict, kein Crash."""
        result = SolarEdgeInverter._distribute_proportional(6.0, [])
        assert result == {}

    def test_zero_total_power(self):
        """0 kW total → alles 0."""
        result = SolarEdgeInverter._distribute_proportional(
            0.0,
            [
                {"prefix": "i1", "usable_kwh": 10.0, "max_kw": 5.0},
                {"prefix": "i2", "usable_kwh": 5.0, "max_kw": 5.0},
            ],
        )
        assert result["i1"] == pytest.approx(0.0)
        assert result["i2"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Integration mit den Sensor-Readern — über mock_hass states.
# ---------------------------------------------------------------------------


def _state(value):
    s = MagicMock()
    s.state = str(value) if value is not None else "unavailable"
    return s


def _setup_states(mock_hass, mapping: dict):
    """Configure mock_hass.states.get to return states from mapping."""
    def get(entity_id):
        return mapping.get(entity_id)
    mock_hass.states.get = MagicMock(side_effect=get)
    # async_all wird vom Fallback-Scan benötigt
    mock_hass.states.async_all = MagicMock(return_value=list(mapping.values()))
    # Each state object also needs its entity_id when scanned
    for eid, st in mapping.items():
        st.entity_id = eid


class TestComputeDischargeDistribution:
    """End-to-end: sensor lookups + verteilung kombiniert."""

    def test_proportional_split_from_real_sensors(self, mock_hass):
        """Heutige Werte aus ha.linzner.cloud — proportional split 6 kW total."""
        _setup_states(mock_hass, {
            # i1 — 23 kWh Batterie
            "sensor.solaredge_i1_b1_maximum_energy": _state(24.25),
            "sensor.solaredge_i1_b1_state_of_energy": _state(66.0),
            "sensor.solaredge_i1_b1_max_discharge_power": _state(5000.0),
            "number.solaredge_i1_backup_reserve": _state(20.0),
            # i2 — 14.55 kWh Batterie
            "sensor.solaredge_i2_b1_maximum_energy": _state(14.55),
            "sensor.solaredge_i2_b1_state_of_energy": _state(53.0),
            "sensor.solaredge_i2_b1_max_discharge_power": _state(5000.0),
            "number.solaredge_i2_backup_reserve": _state(20.0),
        })
        config = {
            "pv_power_sensor": "sensor.solaredge_i1_ac_power",
            "pv_power_sensor_2": "sensor.solaredge_i2_ac_power",
        }
        inv = SolarEdgeInverter(mock_hass, config)
        dist = inv._compute_discharge_distribution(
            6.0, ["solaredge_i1_", "solaredge_i2_"]
        )
        assert dist is not None
        assert dist["solaredge_i1_"] == pytest.approx(4.194, abs=0.01)
        assert dist["solaredge_i2_"] == pytest.approx(1.806, abs=0.01)

    def test_get_combined_battery_state_weighted(self, mock_hass):
        """Heutige Werte: i1 SOC 44 / 24.25 kWh, i2 SOC 19 / 14.55 kWh.
        Gewichtet: (44×24.25 + 19×14.55) / (24.25 + 14.55) = 34.62 %.
        Total cap: 38.8 kWh."""
        _setup_states(mock_hass, {
            "sensor.solaredge_i1_b1_maximum_energy": _state(24.25),
            "sensor.solaredge_i1_b1_state_of_energy": _state(44.0),
            "sensor.solaredge_i2_b1_maximum_energy": _state(14.55),
            "sensor.solaredge_i2_b1_state_of_energy": _state(19.0),
        })
        config = {
            "pv_power_sensor": "sensor.solaredge_i1_ac_power",
            "pv_power_sensor_2": "sensor.solaredge_i2_ac_power",
        }
        inv = SolarEdgeInverter(mock_hass, config)
        soc, cap = inv.get_combined_battery_state()
        assert soc == pytest.approx(34.62, abs=0.01)
        assert cap == pytest.approx(38.8, abs=0.01)

    def test_get_combined_battery_state_returns_none_on_missing_sensor(
        self, mock_hass
    ):
        """Wenn ein SOC-Sensor fehlt → (None, None) → Fallback auf Config-Sensor."""
        _setup_states(mock_hass, {
            "sensor.solaredge_i1_b1_maximum_energy": _state(24.25),
            "sensor.solaredge_i1_b1_state_of_energy": _state(44.0),
            "sensor.solaredge_i2_b1_maximum_energy": _state(14.55),
            "sensor.solaredge_i2_b1_state_of_energy": _state(None),  # missing
        })
        config = {
            "pv_power_sensor": "sensor.solaredge_i1_ac_power",
            "pv_power_sensor_2": "sensor.solaredge_i2_ac_power",
        }
        inv = SolarEdgeInverter(mock_hass, config)
        soc, cap = inv.get_combined_battery_state()
        assert soc is None
        assert cap is None

    def test_get_combined_battery_state_single_inverter(self, mock_hass):
        """Nur ein Inverter (kein _extra_prefix) — sollte trotzdem Werte liefern."""
        _setup_states(mock_hass, {
            "sensor.solaredge_i1_b1_maximum_energy": _state(24.25),
            "sensor.solaredge_i1_b1_state_of_energy": _state(50.0),
        })
        config = {"pv_power_sensor": "sensor.solaredge_i1_ac_power"}
        inv = SolarEdgeInverter(mock_hass, config)
        soc, cap = inv.get_combined_battery_state()
        assert soc == pytest.approx(50.0)
        assert cap == pytest.approx(24.25)

    def test_returns_none_when_capacity_sensor_unavailable(self, mock_hass):
        """Wenn ein Sensor unavailable ist → None (Driver fällt auf equal split zurück)."""
        _setup_states(mock_hass, {
            "sensor.solaredge_i1_b1_maximum_energy": _state(24.25),
            "sensor.solaredge_i1_b1_state_of_energy": _state(66.0),
            "sensor.solaredge_i1_b1_max_discharge_power": _state(5000.0),
            "number.solaredge_i1_backup_reserve": _state(20.0),
            # i2 — Kapazität fehlt
            "sensor.solaredge_i2_b1_maximum_energy": _state(None),
            "sensor.solaredge_i2_b1_state_of_energy": _state(53.0),
            "sensor.solaredge_i2_b1_max_discharge_power": _state(5000.0),
            "number.solaredge_i2_backup_reserve": _state(20.0),
        })
        config = {
            "pv_power_sensor": "sensor.solaredge_i1_ac_power",
            "pv_power_sensor_2": "sensor.solaredge_i2_ac_power",
        }
        inv = SolarEdgeInverter(mock_hass, config)
        dist = inv._compute_discharge_distribution(
            6.0, ["solaredge_i1_", "solaredge_i2_"]
        )
        assert dist is None
