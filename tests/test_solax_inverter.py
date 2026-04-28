"""Tests for SolaX Gen4+ inverter implementation.

The driver issues a five-write sequence per command:
  1. select.select_option   → power control mode
  2. number.set_value       → active_power (W, negative for discharge, 0 to idle)
  3. number.set_value       → remotecontrol_duration (s)
  4. number.set_value       → remotecontrol_autorepeat_duration (s)
  5. button.press           → trigger that flushes the params to the Modbus regs
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.solax import (
    SOLAX_DOMAIN,
    SOLAX_ENTITY_DEFAULTS,
    SolaXInverter,
)


SELECT_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_power_control"]
ACTIVE_POWER_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_active_power"]
DURATION_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_duration"]
AUTOREPEAT_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_autorepeat_duration"]
TRIGGER_ENTITY = SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]


def _calls_by_entity(mock_hass) -> dict[str, dict]:
    """Index recorded service calls by their entity_id for easier assertion."""
    out: dict[str, dict] = {}
    for c in mock_hass.services.async_call.call_args_list:
        payload = c.args[2] if len(c.args) > 2 else {}
        eid = payload.get("entity_id")
        if eid:
            out[eid] = payload
    return out


@pytest.fixture
def solax_config():
    return {}


@pytest.fixture
def inverter(mock_hass, solax_config):
    return SolaXInverter(mock_hass, solax_config)


class TestSolaXInverterBase:
    """Verify SolaXInverter inherits from InverterBase."""

    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(SolaXInverter, InverterBase)


class TestAsyncSetChargeLimit:
    """Charge limit: 5 writes, ending in a button press."""

    async def test_block_charging_writes_zero_active_power(self, inverter, mock_hass):
        """power_kw=0 → Enabled Battery Control + active_power=0."""
        result = await inverter.async_set_charge_limit(0)
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 5

        # Step 1: select power control mode
        assert calls[0].args == (
            "select",
            "select_option",
            {"entity_id": SELECT_ENTITY, "option": "Enabled Battery Control"},
        )
        # Step 2: active_power = 0 (battery idle)
        assert calls[1].args == (
            "number",
            "set_value",
            {"entity_id": ACTIVE_POWER_ENTITY, "value": 0},
        )
        # Step 3: remotecontrol_duration
        assert calls[2].args == (
            "number",
            "set_value",
            {"entity_id": DURATION_ENTITY, "value": 300},
        )
        # Step 4: autorepeat_duration
        assert calls[3].args == (
            "number",
            "set_value",
            {"entity_id": AUTOREPEAT_ENTITY, "value": 60},
        )
        # Step 5: trigger
        assert calls[4].args == (
            "button",
            "press",
            {"entity_id": TRIGGER_ENTITY},
        )

    async def test_partial_charge_kw_to_w(self, inverter, mock_hass):
        """power_kw=3.0 → active_power=3000 (positive = charge)."""
        result = await inverter.async_set_charge_limit(3.0)
        assert result is True
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == 3000

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_charge_limit(0)
        assert result is False


class TestAsyncSetDischarge:
    """Discharge: 5 writes with negative active_power (no min-SOC handling)."""

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
        # Same 5 calls as without target_soc — no min-SOC entity is written
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
    """Stop: Disabled mode + power=0 + duration=20 + autorepeat=0 + trigger."""

    async def test_stop_forcible_calls(self, inverter, mock_hass):
        result = await inverter.async_stop_forcible()
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 5

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
        # Stop uses a short duration (20s) and clears the autorepeat timer
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

    async def test_uses_config_override(self, mock_hass):
        """Each solax_<key> override is respected for the matching service call."""
        config = {
            "solax_remotecontrol_power_control": "select.custom_power_control",
            "solax_remotecontrol_active_power": "number.custom_active_power",
            "solax_remotecontrol_duration": "number.custom_duration",
            "solax_remotecontrol_autorepeat_duration": "number.custom_autorepeat",
            "solax_remotecontrol_trigger": "button.custom_trigger",
        }
        inv = SolaXInverter(mock_hass, config)
        await inv.async_set_charge_limit(0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0].args[2]["entity_id"] == "select.custom_power_control"
        assert calls[1].args[2]["entity_id"] == "number.custom_active_power"
        assert calls[2].args[2]["entity_id"] == "number.custom_duration"
        assert calls[3].args[2]["entity_id"] == "number.custom_autorepeat"
        assert calls[4].args[2]["entity_id"] == "button.custom_trigger"

    async def test_uses_defaults_when_no_config(self, mock_hass):
        """Without overrides, all entity IDs come from SOLAX_ENTITY_DEFAULTS."""
        inv = SolaXInverter(mock_hass, {})
        await inv.async_set_charge_limit(0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0].args[2]["entity_id"] == SELECT_ENTITY
        assert calls[1].args[2]["entity_id"] == ACTIVE_POWER_ENTITY
        assert calls[2].args[2]["entity_id"] == DURATION_ENTITY
        assert calls[3].args[2]["entity_id"] == AUTOREPEAT_ENTITY
        assert calls[4].args[2]["entity_id"] == TRIGGER_ENTITY


class TestKWToWConversion:
    """kW→W conversion for the active_power register."""

    async def test_fractional_kw_charge(self, inverter, mock_hass):
        """2.5 kW charge → +2500 W."""
        await inverter.async_set_charge_limit(2.5)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == 2500

    async def test_fractional_kw_discharge(self, inverter, mock_hass):
        """1.5 kW discharge → −1500 W."""
        await inverter.async_set_discharge(1.5)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == -1500

    async def test_small_charge_value(self, inverter, mock_hass):
        """0.1 kW → 100 W."""
        await inverter.async_set_charge_limit(0.1)
        payloads = _calls_by_entity(mock_hass)
        assert payloads[ACTIVE_POWER_ENTITY]["value"] == 100
