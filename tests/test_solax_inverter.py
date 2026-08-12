"""Tests for SolaX Gen4+ inverter implementation.

Phase 12: async_set_charge_limit blockiert das Laden nun via
battery_charge_max_current=0 statt Mode-1-Idle. async_stop_forcible
restoriert den Originalwert aus einem Store. async_set_discharge bleibt
unverändert auf Mode 1 mit negativer active_power.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.solax import (
    SOLAX_DOMAIN,
    SOLAX_ENTITY_DEFAULTS,
    SolaXInverter,
    SolaXStateStore,
)


SELECT_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_power_control"]
ACTIVE_POWER_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_active_power"]
DURATION_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_duration"]
AUTOREPEAT_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_autorepeat_duration"]
TRIGGER_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]
MAX_CURRENT_ENTITY = SOLAX_ENTITY_DEFAULTS["battery_charge_max_current"]


def _calls_by_entity(mock_hass) -> dict[str, dict]:
    """Index recorded service calls by their entity_id for easier assertion."""
    out: dict[str, dict] = {}
    for c in mock_hass.services.async_call.call_args_list:
        payload = c.args[2] if len(c.args) > 2 else {}
        eid = payload.get("entity_id")
        if eid:
            out[eid] = payload
    return out


class _NoopStore:
    """In-memory Store-Ersatz für Tests, die Storage nicht prüfen."""

    def __init__(self):
        self.saved: list[dict] = []
        self._data: dict = {}

    async def async_load(self):
        return self._data

    async def async_save(self, data):
        self._data = dict(data)
        self.saved.append(dict(data))


def _install_noop_store(inv: SolaXInverter) -> _NoopStore:
    noop = _NoopStore()
    if inv._state_store is not None:
        inv._state_store._store = noop
        inv._state_store._data = {}
        inv._state_store._loaded = False
    return noop


@pytest.fixture
def solax_config():
    return {}


@pytest.fixture
def inverter(mock_hass, solax_config):
    inv = SolaXInverter(mock_hass, solax_config)
    _install_noop_store(inv)
    return inv


class TestSolaXInverterBase:
    """Verify SolaXInverter inherits from InverterBase."""

    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(SolaXInverter, InverterBase)


class TestAsyncSetChargeLimit:
    """Charge-Block ist nun battery_charge_max_current-basiert (Phase 12)."""

    async def test_block_charging_sets_max_current_to_zero(self, inverter, mock_hass):
        """power_kw=0 → battery_charge_max_current=0 + remotecontrol_power_control=Disabled.

        NEU in Phase 12: KEIN Mode-1-Idle mehr — nur Charge blockieren, Self-Use
        läuft weiter und entlädt bei Bedarf.
        """
        mock_state = MagicMock()
        mock_state.state = "30.0"
        mock_state.attributes = {"max": 30}
        mock_hass.states.get = MagicMock(return_value=mock_state)

        result = await inverter.async_set_charge_limit(0)
        assert result is True

        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == 0

        select_calls = [
            c for c in mock_hass.services.async_call.call_args_list
            if c.args[0] == "select" and c.args[1] == "select_option"
        ]
        assert any(
            c.args[2].get("option") == "Disabled" for c in select_calls
        ), "remotecontrol_power_control must be set to Disabled"
        assert not any(
            c.args[2].get("option") == "Enabled Battery Control" for c in select_calls
        ), "Mode 1 must NOT be activated for charge block"

    async def test_partial_charge_writes_amps_to_max_current(self, inverter, mock_hass):
        """power_kw=3.0 → battery_charge_max_current in Ampere (kW über Spannung → A).

        Bei 400V Default-Fallback: 3000W / 400V = 7.5 A.
        """
        voltage_state = MagicMock()
        voltage_state.state = "400.0"
        voltage_state.attributes = {}

        max_current_state = MagicMock()
        max_current_state.state = "30.0"
        max_current_state.attributes = {"max": 30}

        def states_get(entity_id):
            if "voltage" in entity_id:
                return voltage_state
            return max_current_state

        mock_hass.states.get = MagicMock(side_effect=states_get)

        result = await inverter.async_set_charge_limit(3.0)
        assert result is True

        payloads = _calls_by_entity(mock_hass)
        written = payloads[MAX_CURRENT_ENTITY]["value"]
        assert written == pytest.approx(7.5, rel=0.01)

    async def test_partial_charge_clamped_to_hardware_max(self, inverter, mock_hass):
        """Falls kW/V die Hardware-Max-Stromstärke überschreitet, wird auf max geclampt."""
        voltage_state = MagicMock()
        voltage_state.state = "400.0"
        voltage_state.attributes = {}

        max_current_state = MagicMock()
        max_current_state.state = "30.0"
        max_current_state.attributes = {"max": 30}

        def states_get(entity_id):
            if "voltage" in entity_id:
                return voltage_state
            return max_current_state

        mock_hass.states.get = MagicMock(side_effect=states_get)

        # 20 kW / 400 V = 50 A → muss auf 30 A geclampt werden
        await inverter.async_set_charge_limit(20.0)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == pytest.approx(30.0, rel=0.01)

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_charge_limit(0)
        assert result is False

    async def test_caches_original_on_first_call(self, inverter, mock_hass):
        """Erster Eingriff mit State > 0 cached den Wert im Store."""
        save_calls = []

        class FakeStore:
            async def async_load(self):
                return {}

            async def async_save(self, data):
                save_calls.append(dict(data))

        inverter._state_store._store = FakeStore()
        inverter._state_store._loaded = False
        inverter._state_store._data = {}

        mock_state = MagicMock()
        mock_state.state = "25.0"
        mock_state.attributes = {"max": 30}
        mock_hass.states.get = MagicMock(return_value=mock_state)

        await inverter.async_set_charge_limit(0)
        assert len(save_calls) == 1
        assert save_calls[0]["battery_charge_max_current_original"] == 25.0

    async def test_skips_cache_when_state_is_zero(self, inverter, mock_hass):
        """Reboot-Schutz: aktueller State 0 darf bestehenden Cache nicht überschreiben."""
        save_calls = []

        class FakeStore:
            async def async_load(self):
                return {"battery_charge_max_current_original": 30.0}

            async def async_save(self, data):
                save_calls.append(dict(data))

        inverter._state_store._store = FakeStore()
        inverter._state_store._loaded = False
        inverter._state_store._data = {}

        mock_state = MagicMock()
        mock_state.state = "0.0"
        mock_state.attributes = {"max": 30}
        mock_hass.states.get = MagicMock(return_value=mock_state)

        await inverter._state_store.async_load()
        assert inverter._state_store.original_current == 30.0

        await inverter.async_set_charge_limit(0)
        # Kein save_call mit 0 als Original-Wert
        assert all(
            c.get("battery_charge_max_current_original") != 0 for c in save_calls
        )


class TestAsyncSetDischarge:
    """Discharge bleibt auf Mode 1 mit negativer active_power (regression guard)."""

    async def test_discharge_uses_negative_active_power(self, inverter, mock_hass):
        """power_kw=3.0 → active_power=-3000."""
        result = await inverter.async_set_discharge(3.0)
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 5

        assert calls[0].args == (
            "select",
            "select_option",
            {"entity_id": SELECT_ENTITY, "option": "Enabled Battery Control"},
        )
        assert calls[1].args == (
            "number",
            "set_value",
            {"entity_id": ACTIVE_POWER_ENTITY, "value": -3000},
        )
        assert calls[2].args == (
            "number",
            "set_value",
            {"entity_id": DURATION_ENTITY, "value": 300},
        )
        assert calls[3].args == (
            "number",
            "set_value",
            {"entity_id": AUTOREPEAT_ENTITY, "value": 60},
        )
        assert calls[4].args == (
            "button",
            "press",
            {"entity_id": TRIGGER_ENTITY},
        )

    async def test_target_soc_argument_is_ignored(self, inverter, mock_hass):
        """target_soc is part of the InverterBase contract but unused on SolaX."""
        result = await inverter.async_set_discharge(2.0, target_soc=20)
        assert result is True
        assert len(mock_hass.services.async_call.call_args_list) == 5

    async def test_positive_input_still_emits_negative_power(self, inverter, mock_hass):
        """Positive power input is still encoded as negative discharge."""
        await inverter.async_set_discharge(2.0)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == -2000

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_discharge(3.0)
        assert result is False


class TestAsyncStopForcible:
    """Stop beendet Mode 1 und restoriert battery_charge_max_current (Phase 12)."""

    async def test_stop_forcible_disables_mode_one(self, inverter, mock_hass):
        """Disabled-Sequenz + duration=20 + autorepeat=0 + trigger."""
        # mock_hass.states.get liefert per Default MagicMock; attributes.max
        # parst dann nicht zu float, sodass kein Restore-Aufruf erfolgt.
        result = await inverter.async_stop_forcible()
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        # 5 Mode-1-Calls + ggf. 1 Restore-Call (hier ohne State → 5)
        assert calls[0].args == (
            "select",
            "select_option",
            {"entity_id": SELECT_ENTITY, "option": "Disabled"},
        )
        assert calls[1].args == (
            "number",
            "set_value",
            {"entity_id": ACTIVE_POWER_ENTITY, "value": 0},
        )
        assert calls[2].args == (
            "number",
            "set_value",
            {"entity_id": DURATION_ENTITY, "value": 20},
        )
        assert calls[3].args == (
            "number",
            "set_value",
            {"entity_id": AUTOREPEAT_ENTITY, "value": 0},
        )
        assert calls[4].args == (
            "button",
            "press",
            {"entity_id": TRIGGER_ENTITY},
        )

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_stop_forcible()
        assert result is False

    async def test_stop_forcible_restores_original_from_store(self, inverter, mock_hass):
        """stop_forcible restoriert gecachten battery_charge_max_current."""

        class FakeStore:
            async def async_load(self):
                return {"battery_charge_max_current_original": 25.0}

            async def async_save(self, data):
                pass

        inverter._state_store._store = FakeStore()
        inverter._state_store._loaded = False
        inverter._state_store._data = {}

        await inverter.async_stop_forcible()

        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == 25.0

    async def test_stop_forcible_uses_max_fallback_when_no_cache(self, inverter, mock_hass):
        """Wenn Store leer, nutzt stop_forcible attributes.max."""

        class FakeStore:
            async def async_load(self):
                return {}

            async def async_save(self, data):
                pass

        inverter._state_store._store = FakeStore()
        inverter._state_store._loaded = False
        inverter._state_store._data = {}

        mock_state = MagicMock()
        mock_state.state = "0.0"
        mock_state.attributes = {"max": 30}
        mock_hass.states.get = MagicMock(return_value=mock_state)

        await inverter.async_stop_forcible()
        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == 30.0


class TestIsAvailable:
    """is_available depends on whether solax_modbus has a loaded config entry."""

    def test_available_when_loaded(self, mock_hass, solax_config):
        entry = MagicMock()
        entry.state.value = "loaded"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is True

    def test_unavailable_when_not_loaded(self, mock_hass, solax_config):
        entry = MagicMock()
        entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is False

    def test_unavailable_when_no_entries(self, mock_hass, solax_config):
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is False


class TestEntityResolution:
    """Entity IDs may be overridden via solax_<key> config keys; otherwise defaults apply."""

    async def test_uses_config_override_on_discharge(self, mock_hass):
        """Discharge respektiert solax_<key>-Overrides (5-Write-Pattern)."""
        config = {
            "solax_remotecontrol_power_control": "select.custom_power_control",
            "solax_remotecontrol_active_power": "number.custom_active_power",
            "solax_remotecontrol_duration": "number.custom_duration",
            "solax_remotecontrol_autorepeat_duration": "number.custom_autorepeat",
            "solax_remotecontrol_trigger": "button.custom_trigger",
        }
        inv = SolaXInverter(mock_hass, config)
        _install_noop_store(inv)
        await inv.async_set_discharge(1.0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0].args[2]["entity_id"] == "select.custom_power_control"
        assert calls[1].args[2]["entity_id"] == "number.custom_active_power"
        assert calls[2].args[2]["entity_id"] == "number.custom_duration"
        assert calls[3].args[2]["entity_id"] == "number.custom_autorepeat"
        assert calls[4].args[2]["entity_id"] == "button.custom_trigger"

    async def test_charge_block_respects_battery_charge_max_current_override(self, mock_hass):
        """Phase 12: solax_battery_charge_max_current-Override wird respektiert."""
        config = {
            "solax_battery_charge_max_current": "number.custom_max_current",
            "solax_remotecontrol_power_control": "select.custom_power_control",
        }
        inv = SolaXInverter(mock_hass, config)
        _install_noop_store(inv)
        await inv.async_set_charge_limit(0)

        payloads = _calls_by_entity(mock_hass)
        assert "number.custom_max_current" in payloads
        assert payloads["number.custom_max_current"]["value"] == 0
        assert payloads["select.custom_power_control"]["option"] == "Disabled"

    async def test_uses_defaults_when_no_config_on_discharge(self, mock_hass):
        """Without overrides, all entity IDs come from SOLAX_ENTITY_DEFAULTS."""
        inv = SolaXInverter(mock_hass, {})
        _install_noop_store(inv)
        await inv.async_set_discharge(1.0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0].args[2]["entity_id"] == SELECT_ENTITY
        assert calls[1].args[2]["entity_id"] == ACTIVE_POWER_ENTITY
        assert calls[2].args[2]["entity_id"] == DURATION_ENTITY
        assert calls[3].args[2]["entity_id"] == AUTOREPEAT_ENTITY
        assert calls[4].args[2]["entity_id"] == TRIGGER_ENTITY


class TestKWToAmpsConversion:
    """kW→A conversion für battery_charge_max_current (Phase 12)."""

    async def test_fractional_kw_charge(self, inverter, mock_hass):
        """2.5 kW Charge @ 400V Default → 6.25 A auf battery_charge_max_current."""
        # states.get → None → keine kaputten MagicMock-Floats; max_a-Fallback = 30 A
        mock_hass.states.get = MagicMock(return_value=None)
        await inverter.async_set_charge_limit(2.5)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == pytest.approx(6.25, rel=0.01)

    async def test_small_charge_value(self, inverter, mock_hass):
        """0.1 kW @ 400V Default → 0.25 A."""
        mock_hass.states.get = MagicMock(return_value=None)
        await inverter.async_set_charge_limit(0.1)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[MAX_CURRENT_ENTITY]["value"] == pytest.approx(0.25, rel=0.01)


class TestKWToWConversionDischarge:
    """Discharge bleibt kW→W (Mode-1-Pfad)."""

    async def test_fractional_kw_discharge(self, inverter, mock_hass):
        """1.5 kW Discharge → −1500 W."""
        await inverter.async_set_discharge(1.5)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == -1500


class TestSolaXStateStore:
    """SolaXStateStore-Klasse persistiert den Original-Wert."""

    async def test_load_empty_store_yields_none(self, mock_hass):
        store = SolaXStateStore(mock_hass)
        store._store = _NoopStore()
        await store.async_load()
        assert store.original_current is None

    async def test_save_persists_value(self, mock_hass):
        store = SolaXStateStore(mock_hass)
        noop = _NoopStore()
        store._store = noop
        await store.async_load()
        await store.async_save_original_current(27.5)
        assert noop.saved[-1]["battery_charge_max_current_original"] == 27.5
        assert store.original_current == 27.5

    async def test_load_returns_existing_value(self, mock_hass):
        store = SolaXStateStore(mock_hass)
        noop = _NoopStore()
        noop._data = {"battery_charge_max_current_original": 30.0}
        store._store = noop
        await store.async_load()
        assert store.original_current == 30.0


# ---------------------------------------------------------------------------
# Versionstolerante Entity-Auflösung (solax_modbus ≥2025.x Mode-Suffixe)
# ---------------------------------------------------------------------------

class _FakeState:
    def __init__(self, entity_id: str):
        self.entity_id = entity_id


# Entity-Landschaft einer realen Anlage mit neuer solax_modbus-Benennung
# (Mode-Suffixe + *_direct-Varianten, beobachtet auf X3-Hybrid Gen4, 2026-08).
NEW_STYLE_ENTITIES = {
    "select": [
        "select.solax_inverter_remotecontrol_power_control_mode_1",
        "select.solax_inverter_remotecontrol_power_control_mode_mode_8_9",
        "select.solax_inverter_remotecontrol_power_control_mode_mode_8_9_direct",
        "select.solax_inverter_modbus_power_control_direct",
    ],
    "number": [
        "number.solax_inverter_remotecontrol_active_power_mode_1",
        "number.solax_inverter_remotecontrol_active_power_mode_1_direct",
        "number.solax_inverter_remotecontrol_autorepeat_duration_mode_1_9",
        "number.solax_inverter_remotecontrol_duration_mode_1_8",
        "number.solax_inverter_battery_charge_max_current",
        "number.solax_inverter_selfuse_discharge_min_soc",
    ],
    "button": [
        "button.solax_inverter_remotecontrol_trigger_mode_1_7",
        "button.solax_inverter_powercontrolmode_trigger_mode_8_9",
    ],
}

OLD_STYLE_ENTITIES = {
    "select": ["select.solax_remotecontrol_power_control"],
    "number": [
        "number.solax_remotecontrol_active_power",
        "number.solax_remotecontrol_autorepeat_duration",
        "number.solax_remotecontrol_duration",
        "number.solax_battery_charge_max_current",
        "number.solax_selfuse_discharge_min_soc",
    ],
    "button": ["button.solax_remotecontrol_trigger"],
}


def _install_states(mock_hass, entities: dict) -> None:
    all_ids = {eid for ids in entities.values() for eid in ids}
    mock_hass.states.async_all = MagicMock(
        side_effect=lambda domain: [_FakeState(e) for e in entities.get(domain, [])]
    )
    mock_hass.states.get = MagicMock(
        side_effect=lambda eid: _FakeState(eid) if eid in all_ids else None
    )


class TestFindSolaxControlEntity:
    """find_solax_control_entity matcht alte und neue solax_modbus-Benennung."""

    def test_new_style_entities_resolved(self, mock_hass):
        from custom_components.eeg_energy_optimizer.inverter.solax import (
            find_solax_control_entity,
        )
        _install_states(mock_hass, NEW_STYLE_ENTITIES)
        expected = {
            "remotecontrol_power_control": "select.solax_inverter_remotecontrol_power_control_mode_1",
            "remotecontrol_active_power": "number.solax_inverter_remotecontrol_active_power_mode_1",
            "remotecontrol_autorepeat_duration": "number.solax_inverter_remotecontrol_autorepeat_duration_mode_1_9",
            "remotecontrol_duration": "number.solax_inverter_remotecontrol_duration_mode_1_8",
            "remotecontrol_trigger": "button.solax_inverter_remotecontrol_trigger_mode_1_7",
            "battery_charge_max_current": "number.solax_inverter_battery_charge_max_current",
            "selfuse_discharge_min_soc": "number.solax_inverter_selfuse_discharge_min_soc",
        }
        for key, entity_id in expected.items():
            assert find_solax_control_entity(mock_hass, key) == entity_id, key

    def test_old_style_entities_resolved(self, mock_hass):
        from custom_components.eeg_energy_optimizer.inverter.solax import (
            find_solax_control_entity,
        )
        _install_states(mock_hass, OLD_STYLE_ENTITIES)
        assert (
            find_solax_control_entity(mock_hass, "remotecontrol_power_control")
            == "select.solax_remotecontrol_power_control"
        )
        assert (
            find_solax_control_entity(mock_hass, "remotecontrol_trigger")
            == "button.solax_remotecontrol_trigger"
        )

    def test_direct_and_mode89_variants_not_matched(self, mock_hass):
        from custom_components.eeg_energy_optimizer.inverter.solax import (
            find_solax_control_entity,
        )
        _install_states(mock_hass, {
            "select": [
                "select.solax_inverter_remotecontrol_power_control_mode_mode_8_9",
                "select.solax_inverter_remotecontrol_power_control_mode_mode_8_9_direct",
            ],
            "number": ["number.solax_inverter_remotecontrol_active_power_mode_1_direct"],
        })
        assert find_solax_control_entity(mock_hass, "remotecontrol_power_control") is None
        assert find_solax_control_entity(mock_hass, "remotecontrol_active_power") is None

    def test_no_states_yields_none(self, mock_hass):
        from custom_components.eeg_energy_optimizer.inverter.solax import (
            find_solax_control_entity,
        )
        _install_states(mock_hass, {})
        assert find_solax_control_entity(mock_hass, "remotecontrol_trigger") is None


class TestSolaXEntityResolution:
    """_resolve_entity: Config → Suffix-Scan → Default."""

    def test_configured_entity_wins_when_it_exists(self, mock_hass):
        entities = {
            **NEW_STYLE_ENTITIES,
            "number": NEW_STYLE_ENTITIES["number"] + ["number.custom_active_power"],
        }
        _install_states(mock_hass, entities)
        inv = SolaXInverter(
            mock_hass, {"solax_remotecontrol_active_power": "number.custom_active_power"}
        )
        assert inv._resolve_entity("remotecontrol_active_power") == "number.custom_active_power"

    def test_stale_config_falls_back_to_scan(self, mock_hass):
        """Nach solax_modbus-Update zeigt die Config auf eine umbenannte Entity."""
        _install_states(mock_hass, NEW_STYLE_ENTITIES)
        inv = SolaXInverter(
            mock_hass,
            {"solax_remotecontrol_active_power": "number.solax_inverter_remotecontrol_active_power"},
        )
        assert (
            inv._resolve_entity("remotecontrol_active_power")
            == "number.solax_inverter_remotecontrol_active_power_mode_1"
        )

    def test_no_match_falls_back_to_default(self, mock_hass):
        _install_states(mock_hass, {})
        inv = SolaXInverter(mock_hass, {})
        assert (
            inv._resolve_entity("remotecontrol_trigger")
            == SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]
        )

    async def test_discharge_targets_new_style_entities(self, mock_hass):
        _install_states(mock_hass, NEW_STYLE_ENTITIES)
        inv = SolaXInverter(mock_hass, {})
        _install_noop_store(inv)
        assert await inv.async_set_discharge(3.0) is True
        payloads = _calls_by_entity(mock_hass)
        assert payloads["select.solax_inverter_remotecontrol_power_control_mode_1"]["option"] == "Enabled Battery Control"
        assert payloads["number.solax_inverter_remotecontrol_active_power_mode_1"]["value"] == -3000
        assert payloads["number.solax_inverter_remotecontrol_duration_mode_1_8"]["value"] == 300
        assert payloads["number.solax_inverter_remotecontrol_autorepeat_duration_mode_1_9"]["value"] == 60
        assert "button.solax_inverter_remotecontrol_trigger_mode_1_7" in payloads


class TestFindSolaxPrefix:
    """_find_solax_prefix (websocket_api) leitet den Prefix aus alter wie neuer Benennung ab."""

    def test_prefix_from_new_style_name(self, mock_hass):
        from custom_components.eeg_energy_optimizer.websocket_api import _find_solax_prefix
        _install_states(mock_hass, NEW_STYLE_ENTITIES)
        assert _find_solax_prefix(mock_hass) == "solax_inverter_"

    def test_prefix_from_old_style_name(self, mock_hass):
        from custom_components.eeg_energy_optimizer.websocket_api import _find_solax_prefix
        _install_states(mock_hass, OLD_STYLE_ENTITIES)
        assert _find_solax_prefix(mock_hass) == "solax_"

    def test_prefix_none_without_entities(self, mock_hass):
        from custom_components.eeg_energy_optimizer.websocket_api import _find_solax_prefix
        _install_states(mock_hass, {})
        assert _find_solax_prefix(mock_hass) is None
