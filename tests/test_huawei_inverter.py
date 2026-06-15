"""Tests for Huawei SUN2000 inverter implementation (INF-02).

Charge limiting now writes the max charge power via the `number.set_value`
service on the `number.batteries_maximale_ladeleistung` entity (or its
`batterien_…` variant, or any number entity matching a known DE/EN suffix).
A missing charge entity no longer fails construction — it is re-resolved
lazily on each control call, and charge limiting degrades to a no-op with
warning. Forced discharge still goes via the huawei_solar service
`forcible_discharge_soc`. Stopping is a two-call sequence:
restore the max charge power and then stop_forcible_charge.
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.huawei import (
    HUAWEI_DOMAIN,
    MAX_CHARGE_POWER_CANDIDATES,
    HuaweiInverter,
)


CHARGE_ENTITY = MAX_CHARGE_POWER_CANDIDATES[0]


def _state_with_max(value):
    state = MagicMock()
    state.attributes = {"max": value}
    return state


@pytest.fixture
def huawei_config():
    """Standard config for Huawei inverter tests."""
    return {"huawei_device_id": "test_device"}


@pytest.fixture
def inverter(mock_hass, huawei_config):
    """HuaweiInverter instance — needs the charge entity to exist for construction."""
    mock_hass.states.get = MagicMock(
        side_effect=lambda eid: _state_with_max(5000.0) if eid == CHARGE_ENTITY else None
    )
    return HuaweiInverter(mock_hass, huawei_config)


class TestConstruction:
    """Construction-time validations."""

    def test_requires_device_id(self, mock_hass):
        """Missing huawei_device_id raises ValueError before resolving entities."""
        with pytest.raises(ValueError, match="huawei_device_id"):
            HuaweiInverter(mock_hass, {})

    def test_missing_charge_entity_does_not_raise(self, mock_hass):
        """No matching charge-power entity → construction succeeds (degraded mode)."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        assert inv._max_charge_entity is None

    def test_suffix_fallback_resolves_entity(self, mock_hass):
        """Differently prefixed entity is found via the DE/EN suffix scan."""
        mock_hass.states.get = MagicMock(return_value=None)
        state = MagicMock()
        state.entity_id = "number.luna2000_maximum_charging_power"
        decoy = MagicMock()
        decoy.entity_id = "number.luna2000_maximum_discharging_power"
        mock_hass.states.async_all = MagicMock(return_value=[decoy, state])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        assert inv._max_charge_entity == "number.luna2000_maximum_charging_power"

    def test_falls_back_to_alt_charge_entity(self, mock_hass):
        """Alternate naming `batterien_…` is also accepted."""
        alt_entity = MAX_CHARGE_POWER_CANDIDATES[1]
        mock_hass.states.get = MagicMock(
            side_effect=lambda eid: _state_with_max(7000.0) if eid == alt_entity else None
        )
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        assert inv._max_charge_entity == alt_entity


class TestHuaweiInverterBase:
    """Verify HuaweiInverter inherits from InverterBase."""

    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(HuaweiInverter, InverterBase)


class TestAsyncSetChargeLimit:
    """Charge limit writes the W value to the max-charge-power number entity."""

    async def test_writes_number_set_value(self, inverter, mock_hass):
        """power_kw=5.0 → number.set_value with entity_id and value=5000."""
        result = await inverter.async_set_charge_limit(5.0)
        assert result is True
        mock_hass.services.async_call.assert_called_once_with(
            "number",
            "set_value",
            {"entity_id": CHARGE_ENTITY, "value": 5000},
            blocking=True,
        )

    async def test_zero_blocks_charging(self, inverter, mock_hass):
        """power_kw=0 writes value=0 (Morgen-Einspeisung block)."""
        result = await inverter.async_set_charge_limit(0)
        assert result is True
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["value"] == 0

    async def test_kw_to_w_conversion(self, inverter, mock_hass):
        """Fractional kW values are converted to integer W."""
        await inverter.async_set_charge_limit(2.5)
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["value"] == 2500

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_charge_limit(5.0)
        assert result is False

    async def test_returns_false_without_charge_entity(self, mock_hass):
        """No charge entity → no service call, returns False instead of crashing."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        result = await inv.async_set_charge_limit(0)
        assert result is False
        mock_hass.services.async_call.assert_not_called()

    async def test_lazy_resolution_after_entity_appears(self, mock_hass):
        """Entity missing at construction but present later → call succeeds."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        assert inv._max_charge_entity is None

        # huawei_solar finished its slow start — entity exists now
        mock_hass.states.get = MagicMock(
            side_effect=lambda eid: _state_with_max(5000.0) if eid == CHARGE_ENTITY else None
        )
        result = await inv.async_set_charge_limit(0)
        assert result is True
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["entity_id"] == CHARGE_ENTITY


class TestAsyncSetDischarge:
    """Forced discharge still goes via the huawei_solar service."""

    async def test_calls_correct_service_with_target_soc(self, inverter, mock_hass):
        """power_kw=3.0, target_soc=20 → forcible_discharge_soc with all params."""
        result = await inverter.async_set_discharge(3.0, target_soc=20)
        assert result is True
        mock_hass.services.async_call.assert_called_once_with(
            HUAWEI_DOMAIN,
            "forcible_discharge_soc",
            {
                "device_id": "test_device",
                "power": "3000",
                "target_soc": 20,
            },
            blocking=True,
        )

    async def test_target_soc_floor_is_12(self, inverter, mock_hass):
        """Huawei refuses target_soc<12, so the driver clamps to 12."""
        await inverter.async_set_discharge(3.0, target_soc=5)
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["target_soc"] == 12

    async def test_default_target_soc_is_12(self, inverter, mock_hass):
        """No target_soc → driver default 12 (matches inverter floor)."""
        await inverter.async_set_discharge(3.0)
        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["target_soc"] == 12

    async def test_power_is_string(self, inverter, mock_hass):
        """huawei_solar expects power as a string."""
        await inverter.async_set_discharge(2.5)
        call_args = mock_hass.services.async_call.call_args
        power_value = call_args[0][2]["power"]
        assert isinstance(power_value, str)
        assert power_value == "2500"

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_discharge(3.0, target_soc=20)
        assert result is False


class TestAsyncStopForcible:
    """Stop is a two-call sequence: restore max charge power, then stop_forcible_charge."""

    async def test_restores_max_then_stops_forcible(self, inverter, mock_hass):
        """First call restores the entity max value, second stops the service."""
        result = await inverter.async_stop_forcible()
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 2

        # Call 1: number.set_value back to the entity's hardware max
        assert calls[0].args == (
            "number",
            "set_value",
            {"entity_id": CHARGE_ENTITY, "value": 5000.0},
        )
        assert calls[0].kwargs == {"blocking": True}

        # Call 2: huawei_solar service to stop forcible discharge
        assert calls[1].args == (
            HUAWEI_DOMAIN,
            "stop_forcible_charge",
            {"device_id": "test_device"},
        )
        assert calls[1].kwargs == {"blocking": True}

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_stop_forcible()
        assert result is False

    async def test_stops_forcible_without_charge_entity(self, mock_hass):
        """No charge entity → restore step skipped, stop_forcible_charge still called."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})
        result = await inv.async_stop_forcible()
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 1
        assert calls[0].args == (
            HUAWEI_DOMAIN,
            "stop_forcible_charge",
            {"device_id": "dev"},
        )


def _reg_entry(entity_id, device_id):
    e = MagicMock()
    e.entity_id = entity_id
    e.device_id = device_id
    return e


def _state(state_val=None, max_attr=None):
    s = MagicMock()
    s.state = state_val
    s.attributes = {"max": max_attr} if max_attr is not None else {}
    return s


# Master ("M") + Slave ("S") setup: je ein Lade-/Entlade-Number-Entity und
# SOC-/Kapazitäts-Sensor pro Gerät. Slave-Entities tragen ein "_2"-Segment.
_CHARGE_M = "number.batteries_maximale_ladeleistung"
_CHARGE_S = "number.batteries_2_maximale_ladeleistung"
_DISCHARGE_M = "number.batteries_maximale_entladeleistung"
_DISCHARGE_S = "number.batteries_2_maximale_entladeleistung"
_SOC_M = "sensor.batteries_batterieladung"
_SOC_S = "sensor.batteries_2_batterieladung"
_CAP_M = "sensor.batterien_akkukapazitat"
_CAP_S = "sensor.batterien_2_akkukapazitat"

_REG_ENTRIES = [
    _reg_entry(_CHARGE_M, "M"), _reg_entry(_DISCHARGE_M, "M"),
    _reg_entry(_SOC_M, "M"), _reg_entry(_CAP_M, "M"),
    _reg_entry(_CHARGE_S, "S"), _reg_entry(_DISCHARGE_S, "S"),
    _reg_entry(_SOC_S, "S"), _reg_entry(_CAP_S, "S"),
]

# SOC: Master 80 % / Slave 40 %; Kapazität 10 / 5 kWh; max Entladeleistung 5 kW.
_STATES = {
    _CHARGE_M: _state(max_attr=5000), _CHARGE_S: _state(max_attr=5000),
    _DISCHARGE_M: _state(max_attr=5000), _DISCHARGE_S: _state(max_attr=5000),
    _SOC_M: _state("80"), _SOC_S: _state("40"),
    _CAP_M: _state("10"), _CAP_S: _state("5"),
}


@contextmanager
def _registry(entries=_REG_ENTRIES):
    reg = MagicMock()
    reg.entities.values.return_value = entries
    with patch(
        "homeassistant.helpers.entity_registry.async_get", return_value=reg
    ):
        yield


def _multi_inverter(mock_hass):
    """Construct a 2-device Huawei inverter with the registry + states mocked."""
    mock_hass.states.get = MagicMock(side_effect=lambda eid: _STATES.get(eid))
    with _registry():
        return HuaweiInverter(mock_hass, {"huawei_device_ids": ["M", "S"]})


class TestMultiDevice:
    """Master/Slave: alle Batterien werden gesteuert + gewichteter Combined-SOC."""

    def test_resolves_charge_entity_per_device(self, mock_hass):
        inv = _multi_inverter(mock_hass)
        assert inv._charge_entities == {"M": _CHARGE_M, "S": _CHARGE_S}

    def test_combined_soc_capacity_weighted(self, mock_hass):
        """Σ(SOC×Kap)/Σ(Kap) = (80·10 + 40·5)/15 = 66.67 %, Kapazität 15 kWh."""
        inv = _multi_inverter(mock_hass)
        with _registry():
            soc, cap = inv.get_combined_battery_state()
        assert soc == pytest.approx(1000 / 15)
        assert cap == pytest.approx(15.0)

    def test_combined_soc_uses_manual_capacity_when_sensor_empty(self, mock_hass):
        """Kein Kapazitäts-Sensorwert → manuelle Einzelkapazität greift.

        Reale Huawei-Anlagen liefern teils keinen akkukapazitat-Wert; dann muss
        die pro Gerät konfigurierte Kapazität die Gewichtung tragen.
        """
        states = dict(_STATES)
        states[_CAP_M] = _state("unknown")  # Sensor ohne Wert
        states[_CAP_S] = _state("unknown")
        mock_hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
        with _registry():
            inv = HuaweiInverter(mock_hass, {
                "huawei_device_ids": ["M", "S"],
                "huawei_battery_capacities": {"M": 10, "S": 15},
            })
            soc, cap = inv.get_combined_battery_state()
        # (80·10 + 40·15) / 25 = 56 %, Kapazität 25 kWh
        assert soc == pytest.approx((80 * 10 + 40 * 15) / 25)
        assert cap == pytest.approx(25.0)

    def test_combined_soc_falls_back_to_unweighted_without_capacity(self, mock_hass):
        """Ohne Kapazitäten (Sensor fehlt, keine manuelle) → ungewichteter SOC.

        Reale Huawei-Anlagen liefern teils gar keinen akkukapazitat-Sensor; der
        Combined-SOC darf dann nicht verschwinden, sondern mittelt ungewichtet.
        """
        states = dict(_STATES)
        states[_CAP_M] = _state("unknown")
        states[_CAP_S] = _state("unknown")
        mock_hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
        with _registry():
            inv = HuaweiInverter(mock_hass, {"huawei_device_ids": ["M", "S"]})
            soc, cap = inv.get_combined_battery_state()
        assert soc == pytest.approx((80 + 40) / 2)  # ungewichtet
        assert cap is None  # keine Kapazität gemeldet → Optimizer nutzt Fallback

    def test_combined_soc_uses_available_soc_when_one_device_missing(self, mock_hass):
        """Fehlt ein SOC, zählt nur das verfügbare Gerät (SOC geht nicht verloren)."""
        states = dict(_STATES)
        states[_SOC_S] = _state("unknown")
        mock_hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
        with _registry():
            inv = HuaweiInverter(mock_hass, {"huawei_device_ids": ["M", "S"]})
            soc, cap = inv.get_combined_battery_state()
        assert soc == pytest.approx(80.0)  # nur Master

    def test_combined_state_none_when_all_soc_missing(self, mock_hass):
        """Erst wenn KEIN Gerät einen SOC liefert → (None, None)."""
        inv = _multi_inverter(mock_hass)
        states = dict(_STATES)
        states[_SOC_M] = _state("unknown")
        states[_SOC_S] = _state("unknown")
        mock_hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
        with _registry():
            assert inv.get_combined_battery_state() == (None, None)

    def test_slave_sensors_with_trailing_index_suffix(self, mock_hass):
        """Slave-Sensoren enden bei huawei_solar auf _2 (batterien_…_2) —
        die Registry-Auflösung muss diesen Geräte-Index am Ende ignorieren."""
        soc_s_end = "sensor.batterien_batterieladung_2"
        cap_s_end = "sensor.batterien_akkukapazitat_2"
        reg = [
            _reg_entry(_CHARGE_M, "M"), _reg_entry(_SOC_M, "M"), _reg_entry(_CAP_M, "M"),
            _reg_entry("number.batterien_maximale_ladeleistung_2", "S"),
            _reg_entry(soc_s_end, "S"), _reg_entry(cap_s_end, "S"),
        ]
        states = {
            _CHARGE_M: _state(max_attr=5000), _SOC_M: _state("80"), _CAP_M: _state("10"),
            soc_s_end: _state("40"), cap_s_end: _state("5"),
        }
        mock_hass.states.get = MagicMock(side_effect=lambda eid: states.get(eid))
        with _registry(reg):
            inv = HuaweiInverter(mock_hass, {"huawei_device_ids": ["M", "S"]})
            soc, cap = inv.get_combined_battery_state()
        # Slave (…_2) gefunden → gewichtet (80·10 + 40·5)/15
        assert soc == pytest.approx((80 * 10 + 40 * 5) / 15)
        assert cap == pytest.approx(15.0)

    def test_single_device_returns_no_combined_state(self, mock_hass):
        """Single-Inverter → (None, None): Optimizer nutzt den Config-Sensor."""
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        inv = HuaweiInverter(mock_hass, {"huawei_device_id": "M"})
        assert inv.get_combined_battery_state() == (None, None)

    def test_has_combined_state_structural(self, mock_hass):
        """has_combined_battery_state ist strukturell (≥2 Geräte), NICHT wertbasiert.

        Entscheidend gegen die Race-Condition: huawei_solar exponiert die
        Sensoren beim Start teils erst nach >10s. Der Combined-Sensor muss
        trotzdem angelegt werden — also auch wenn gerade KEIN State da ist.
        """
        # Keine States verfügbar (wie kurz nach dem Start)
        mock_hass.states.get = MagicMock(return_value=None)
        mock_hass.states.async_all = MagicMock(return_value=[])
        with _registry():
            multi = HuaweiInverter(mock_hass, {"huawei_device_ids": ["M", "S"]})
            single = HuaweiInverter(mock_hass, {"huawei_device_id": "M"})
        assert multi.has_combined_battery_state is True   # trotz fehlender States
        assert single.has_combined_battery_state is False
        # Wertbasiert wäre hier (None, None) → Sensor würde fälschlich entfallen
        assert multi.get_combined_battery_state() == (None, None)

    async def test_charge_limit_writes_all_devices(self, mock_hass):
        inv = _multi_inverter(mock_hass)
        with _registry():
            result = await inv.async_set_charge_limit(0)
        assert result is True
        targets = {
            c.args[2]["entity_id"]: c.args[2]["value"]
            for c in mock_hass.services.async_call.call_args_list
        }
        assert targets == {_CHARGE_M: 0, _CHARGE_S: 0}

    async def test_discharge_proportional_split(self, mock_hass):
        """6 kW: usable 8 / 2 kWh → 4.8 / 1.2 kW (beide unter 5-kW-Cap)."""
        inv = _multi_inverter(mock_hass)
        with _registry():
            result = await inv.async_set_discharge(6.0)
        assert result is True
        by_device = {
            c.args[2]["device_id"]: c.args[2]["power"]
            for c in mock_hass.services.async_call.call_args_list
        }
        assert by_device == {"M": "4800", "S": "1200"}

    async def test_stop_forcible_all_devices(self, mock_hass):
        inv = _multi_inverter(mock_hass)
        with _registry():
            result = await inv.async_stop_forcible()
        assert result is True
        calls = mock_hass.services.async_call.call_args_list
        # 2 restore (number.set_value) + 2 stop (huawei_solar service)
        assert len(calls) == 4
        stop_devices = {
            c.args[2]["device_id"]
            for c in calls if c.args[0] == HUAWEI_DOMAIN
        }
        assert stop_devices == {"M", "S"}


class TestIsAvailable:
    """is_available depends on whether huawei_solar has a loaded config entry."""

    def test_returns_true_when_huawei_solar_loaded(self, inverter, mock_hass):
        entry = MagicMock()
        entry.state = MagicMock()
        entry.state.value = "loaded"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        assert inverter.is_available is True

    def test_returns_false_when_no_entries(self, inverter, mock_hass):
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        assert inverter.is_available is False

    def test_returns_false_when_not_loaded(self, inverter, mock_hass):
        entry = MagicMock()
        entry.state = MagicMock()
        entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        assert inverter.is_available is False
