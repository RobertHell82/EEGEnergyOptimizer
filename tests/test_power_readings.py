"""Tests für custom_components.eeg_energy_optimizer.power_readings.

Pinned das Verhalten des zentralen Power-Sensor-Helpers:
  - read_power_kw: robuste Unit-Erkennung (W/kW/MW + Aliase, case-insensitive)
  - compute_pv_now_kw: Dashboard-Parität — der Wert, der ans Telemetrie-
    Backend geht, ist IDENTISCH zu dem, was sensor.PVLeistungSensor anzeigt.

Hintergrund: Bei SolarEdge weicht der Telemetrie-Wert vom HA-Dashboard-
Wert ab, wenn der Reporter den rohen ac_power-Sensor sendet, statt die
``pv_includes_battery``-Korrektur anzuwenden. Backend ist unschuldig — es
speichert pv_now_kw 1:1.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_POWER_SENSOR,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    CONF_PV_POWER_SENSOR_2,
)
from custom_components.eeg_energy_optimizer.power_readings import (
    compute_pv_now_kw,
    read_power_kw,
)


def _make_state(value, unit: str = "kW"):
    """Build a hass-state mock that exposes .state and .attributes."""
    state = MagicMock()
    state.state = value
    state.attributes = {"unit_of_measurement": unit}
    return state


def _make_hass(states: dict):
    hass = MagicMock()
    hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
    return hass


# ---------------------------------------------------------------------------
# read_power_kw — Unit-Erkennung (robust)
# ---------------------------------------------------------------------------


class TestReadPowerKwUnits:
    """unit_of_measurement-Parsing case-insensitive + Aliase + MW."""

    @pytest.mark.parametrize(
        "unit,raw,expected",
        [
            # kW (and aliases)
            ("kW", "3.5", 3.5),
            ("kw", "3.5", 3.5),       # lower-case
            ("KW", "3.5", 3.5),       # all caps
            ("kilowatt", "3.5", 3.5),
            ("Kilowatts", "3.5", 3.5),
            # W (and aliases)
            ("W", "3500", 3.5),
            ("w", "3500", 3.5),
            ("Watt", "3500", 3.5),
            ("Watts", "3500", 3.5),
            # MW
            ("MW", "0.0035", 3.5),
            ("Megawatt", "0.0035", 3.5),
            # Whitespace + mixed case
            (" kW ", "3.5", 3.5),
            ("  W ", "3500", 3.5),
        ],
    )
    def test_unit_aliases_and_case_insensitivity(self, unit, raw, expected):
        hass = _make_hass({"sensor.x": _make_state(raw, unit)})
        assert read_power_kw(hass, "sensor.x") == pytest.approx(expected)

    def test_unknown_unit_is_treated_as_kw(self):
        """Defensive default: unbekannte/leere Einheit → Wert wird als kW interpretiert."""
        hass = _make_hass({"sensor.x": _make_state("3.5", "")})
        assert read_power_kw(hass, "sensor.x") == 3.5
        hass2 = _make_hass({"sensor.x": _make_state("3.5", "Joule/sec")})
        assert read_power_kw(hass2, "sensor.x") == 3.5

    def test_unavailable_states_return_none(self):
        for state_value in ("unknown", "unavailable", "", None):
            hass = _make_hass({"sensor.x": _make_state(state_value, "kW")})
            assert read_power_kw(hass, "sensor.x") is None

    def test_non_numeric_state_returns_none(self):
        hass = _make_hass({"sensor.x": _make_state("not-a-number", "kW")})
        assert read_power_kw(hass, "sensor.x") is None

    def test_empty_entity_id_returns_none(self):
        hass = _make_hass({})
        assert read_power_kw(hass, "") is None

    def test_missing_entity_returns_none(self):
        hass = _make_hass({})  # entity not in states
        assert read_power_kw(hass, "sensor.does_not_exist") is None

    def test_negative_value_passes_through(self):
        """read_power_kw clipped NICHT — Grid/Battery brauchen Negativwerte."""
        hass = _make_hass({"sensor.x": _make_state("-1.2", "kW")})
        assert read_power_kw(hass, "sensor.x") == -1.2


# ---------------------------------------------------------------------------
# compute_pv_now_kw — Dashboard-Parität
# ---------------------------------------------------------------------------


class TestComputePvNowKw:
    """Live-PV-Wert: deckungsgleich mit sensor.PVLeistungSensor."""

    def test_huawei_uses_raw_pv_sensor(self):
        """Huawei (pv_includes_battery=False): pv_now_kw == primärer Sensor-Wert."""
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_PV_POWER_SENSOR: "sensor.pv",
            CONF_BATTERY_POWER_SENSOR: "sensor.bat",
        }
        hass = _make_hass({
            "sensor.pv": _make_state("3.5", "kW"),
            "sensor.bat": _make_state("0.8", "kW"),  # darf NICHT auf PV draufgerechnet werden
        })
        assert compute_pv_now_kw(hass, cfg) == 3.5

    def test_solaredge_subtracts_battery_discharge_from_ac_power(self):
        """SolarEdge: ac_power 6.0 + battery_raw -1.8 (Entladung) → echte PV 4.2.

        Genau dieses Szenario erklärt die Diskrepanz, die der User berichtet:
        ohne Korrektur sendet der Reporter 6.0 kW, das Dashboard zeigt 4.2.
        """
        cfg = {
            CONF_INVERTER_TYPE: "solaredge_storedge",
            CONF_PV_POWER_SENSOR: "sensor.solaredge_i1_ac_power",
            CONF_BATTERY_POWER_SENSOR: "sensor.solaredge_i1_b1_dc_power",
        }
        hass = _make_hass({
            "sensor.solaredge_i1_ac_power": _make_state("6000", "W"),
            "sensor.solaredge_i1_b1_dc_power": _make_state("-1800", "W"),
        })
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(4.2)

    def test_solaredge_adds_battery_charge_to_ac_power(self):
        """Beim Laden: ac_power 4.0 + battery_raw +2.0 → echte PV 6.0
        (Inverter speist 2 kW von PV in die Batterie, ac_power zeigt nur den
        Anteil der ans Hausnetz/Grid geht)."""
        cfg = {
            CONF_INVERTER_TYPE: "solaredge_storedge",
            CONF_PV_POWER_SENSOR: "sensor.solaredge_i1_ac_power",
            CONF_BATTERY_POWER_SENSOR: "sensor.solaredge_i1_b1_dc_power",
        }
        hass = _make_hass({
            "sensor.solaredge_i1_ac_power": _make_state("4.0", "kW"),
            "sensor.solaredge_i1_b1_dc_power": _make_state("2.0", "kW"),
        })
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(6.0)

    def test_clips_negative_pv_to_zero(self):
        """Inverter-Eigenverbrauch in der Nacht ergibt -0.005 kW → Dashboard zeigt 0."""
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_PV_POWER_SENSOR: "sensor.pv",
        }
        hass = _make_hass({"sensor.pv": _make_state("-0.005", "kW")})
        assert compute_pv_now_kw(hass, cfg) == 0.0

    def test_multi_inverter_sums_second_pv_sensor(self):
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_PV_POWER_SENSOR: "sensor.pv1",
            CONF_PV_POWER_SENSOR_2: "sensor.pv2",
        }
        hass = _make_hass({
            "sensor.pv1": _make_state("3.0", "kW"),
            "sensor.pv2": _make_state("2.5", "kW"),
        })
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(5.5)

    def test_multi_inverter_solaredge_uses_both_batteries(self):
        """Multi-Inverter SolarEdge: zweiter Inverter hat eigene b1_dc_power-Quelle.
        Heuristik: pv2 endet auf 'ac_power' → ersetze durch 'b1_dc_power'.
        """
        cfg = {
            CONF_INVERTER_TYPE: "solaredge_storedge",
            CONF_PV_POWER_SENSOR: "sensor.solaredge_i1_ac_power",
            CONF_PV_POWER_SENSOR_2: "sensor.solaredge_i2_ac_power",
            CONF_BATTERY_POWER_SENSOR: "sensor.solaredge_i1_b1_dc_power",
        }
        hass = _make_hass({
            "sensor.solaredge_i1_ac_power": _make_state("3.0", "kW"),
            "sensor.solaredge_i2_ac_power": _make_state("2.0", "kW"),
            "sensor.solaredge_i1_b1_dc_power": _make_state("-1.0", "kW"),
            "sensor.solaredge_i2_b1_dc_power": _make_state("-0.5", "kW"),
        })
        # PV = (3.0 + 2.0) + (-1.0) + (-0.5) = 3.5
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(3.5)

    def test_returns_none_when_both_pv_sensors_unavailable(self):
        """Komplett dunkel: Backend bekommt None, nicht 0 (analytische Differenz)."""
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_PV_POWER_SENSOR: "sensor.pv",
            CONF_PV_POWER_SENSOR_2: "sensor.pv2",
        }
        hass = _make_hass({
            "sensor.pv": _make_state("unavailable", "kW"),
            "sensor.pv2": _make_state("unknown", "kW"),
        })
        assert compute_pv_now_kw(hass, cfg) is None

    def test_returns_zero_when_only_secondary_pv_available(self):
        """Eine fehlende Quelle wird als 0 behandelt — solange mindestens eine liest."""
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_PV_POWER_SENSOR: "sensor.pv1",
            CONF_PV_POWER_SENSOR_2: "sensor.pv2",
        }
        hass = _make_hass({
            "sensor.pv1": _make_state("unavailable", "kW"),
            "sensor.pv2": _make_state("2.0", "kW"),
        })
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(2.0)

    def test_unit_normalization_propagates_through_correction(self):
        """Wenn primärer Sensor in W, Batterie in kW: beide werden korrekt normalisiert."""
        cfg = {
            CONF_INVERTER_TYPE: "solaredge_storedge",
            CONF_PV_POWER_SENSOR: "sensor.solaredge_ac_power",
            CONF_BATTERY_POWER_SENSOR: "sensor.solaredge_battery",
        }
        hass = _make_hass({
            "sensor.solaredge_ac_power": _make_state("6000", "W"),     # 6.0 kW
            "sensor.solaredge_battery": _make_state("-1.8", "kW"),     # -1.8 kW
        })
        assert compute_pv_now_kw(hass, cfg) == pytest.approx(4.2)

    def test_solaredge_without_battery_sensor_is_uncorrected(self):
        """Wenn pv_includes_battery=True aber kein Batterie-Sensor konfiguriert,
        gibt es nichts zu subtrahieren — primärer Wert geht durch (geclamped)."""
        cfg = {
            CONF_INVERTER_TYPE: "solaredge_storedge",
            CONF_PV_POWER_SENSOR: "sensor.solaredge_ac_power",
            # kein CONF_BATTERY_POWER_SENSOR
        }
        hass = _make_hass({"sensor.solaredge_ac_power": _make_state("4.5", "kW")})
        assert compute_pv_now_kw(hass, cfg) == 4.5


# ---------------------------------------------------------------------------
# resolve_sign — zentrale Vorzeichen-Auflösung inkl. Huawei-EMMA-Sonderfall
# ---------------------------------------------------------------------------

from custom_components.eeg_energy_optimizer.power_readings import resolve_sign


class TestResolveSign:
    """Basis-Vorzeichen aus INVERTER_SIGN_CONVENTIONS, EMMA-Inversion bei Huawei."""

    def test_huawei_normal_sensor_keeps_base_sign(self):
        assert resolve_sign("huawei_sun2000", "sensor.power_meter_wirkleistung", "grid_sign") == 1
        assert resolve_sign("huawei_sun2000", "sensor.batteries_ladeleistung", "battery_sign") == 1

    def test_huawei_emma_sensor_inverts_grid_sign(self):
        assert resolve_sign("huawei_sun2000", "sensor.emma_einspeiseleistung", "grid_sign") == -1

    def test_huawei_emma_sensor_inverts_battery_sign(self):
        assert resolve_sign("huawei_sun2000", "sensor.emma_batterieleistung", "battery_sign") == -1

    def test_emma_prefix_case_insensitive(self):
        assert resolve_sign("huawei_sun2000", "SENSOR.EMMA_Einspeiseleistung", "grid_sign") == -1

    def test_emma_prefix_only_for_huawei(self):
        # SolaX-Basis grid_sign=-1; ein (untypischer) emma-Sensor ändert nichts,
        # weil die EMMA-Sonderlogik nur für Huawei greift.
        assert resolve_sign("solax_gen4", "sensor.emma_grid", "grid_sign") == -1

    def test_solax_base_signs(self):
        assert resolve_sign("solax_gen4", "sensor.solax_grid", "grid_sign") == -1
        assert resolve_sign("solax_gen4", "sensor.solax_bat", "battery_sign") == -1

    def test_none_or_empty_entity_keeps_base(self):
        assert resolve_sign("huawei_sun2000", None, "grid_sign") == 1
        assert resolve_sign("huawei_sun2000", "", "grid_sign") == 1

    def test_unknown_inverter_defaults_to_positive(self):
        assert resolve_sign("", "sensor.foo", "grid_sign") == 1


# ---------------------------------------------------------------------------
# resolve_backfill_signs — Vorzeichen für den Statistik-Backfill
# ---------------------------------------------------------------------------

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_POWER_CHARGE_SENSOR,
    CONF_BATTERY_POWER_DISCHARGE_SENSOR,
    CONF_GRID_POWER_EXPORT_SENSOR,
    CONF_GRID_POWER_IMPORT_SENSOR,
    CONF_GRID_POWER_SENSOR,
)
from custom_components.eeg_energy_optimizer.power_readings import (
    resolve_backfill_signs,
)


class TestResolveBackfillSigns:
    """Backfill nutzt dieselbe Vorzeichen-Logik wie die Live-Pfade.

    Regression für den EMMA-Bug: Der Backfill griff direkt auf
    INVERTER_SIGN_CONVENTIONS zu (ohne EMMA-Inversion) und überschrieb bei
    EMMA-Anlagen bei jedem HA-Start die Hausverbrauch-Statistik mit falsch
    berechneten Werten.
    """

    def test_huawei_normal_sensors(self):
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_POWER_SENSOR: "sensor.batteries_ladeleistung",
            CONF_GRID_POWER_SENSOR: "sensor.power_meter_wirkleistung",
        }
        assert resolve_backfill_signs(cfg) == (1, 1)

    def test_huawei_emma_sensors_invert_both(self):
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_POWER_SENSOR: "sensor.emma_batterieleistung",
            CONF_GRID_POWER_SENSOR: "sensor.emma_einspeiseleistung",
        }
        assert resolve_backfill_signs(cfg) == (-1, -1)

    def test_huawei_mixed_emma_grid_only(self):
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_POWER_SENSOR: "sensor.batteries_ladeleistung",
            CONF_GRID_POWER_SENSOR: "sensor.emma_einspeiseleistung",
        }
        assert resolve_backfill_signs(cfg) == (1, -1)

    def test_solax_single_sensors(self):
        cfg = {
            CONF_INVERTER_TYPE: "solax_gen4",
            CONF_BATTERY_POWER_SENSOR: "sensor.solax_bat",
            CONF_GRID_POWER_SENSOR: "sensor.solax_grid",
        }
        assert resolve_backfill_signs(cfg) == (-1, -1)

    def test_pairs_use_base_sign(self):
        """Paar-Konfiguration (Fronius): kanonische Kombination → Basis-Vorzeichen."""
        cfg = {
            CONF_INVERTER_TYPE: "fronius_gen24",
            CONF_BATTERY_POWER_CHARGE_SENSOR: "sensor.fronius_charging",
            CONF_BATTERY_POWER_DISCHARGE_SENSOR: "sensor.fronius_discharging",
            CONF_GRID_POWER_EXPORT_SENSOR: "sensor.fronius_einspeisung",
            CONF_GRID_POWER_IMPORT_SENSOR: "sensor.fronius_bezug",
        }
        assert resolve_backfill_signs(cfg) == (1, 1)

    def test_incomplete_pair_falls_back_to_single(self):
        """Nur ein Paar-Sensor gesetzt → Single-Pfad mit resolve_sign."""
        cfg = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_POWER_CHARGE_SENSOR: "sensor.only_charge",
            CONF_BATTERY_POWER_SENSOR: "sensor.emma_batterieleistung",
            CONF_GRID_POWER_SENSOR: "sensor.emma_einspeiseleistung",
        }
        assert resolve_backfill_signs(cfg) == (-1, -1)
