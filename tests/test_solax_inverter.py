"""Tests for SolaX Gen4+ inverter implementation."""

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.solax import (
    SOLAX_DOMAIN,
    SOLAX_ENTITY_DEFAULTS,
    SolaXInverter,
)


@pytest.fixture
def solax_config():
    """Standard config for SolaX inverter tests."""
    return {}


@pytest.fixture
def inverter(mock_hass, solax_config):
    """Create a SolaXInverter instance with mocked hass."""
    return SolaXInverter(mock_hass, solax_config)


class TestSolaXInverterBase:
    """Verify SolaXInverter inherits from InverterBase."""

    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(SolaXInverter, InverterBase)


class TestAsyncSetChargeLimit:
    """Tests for async_set_charge_limit — two-phase write model."""

    async def test_block_charging_sets_active_power_zero(self, inverter, mock_hass):
        """power_kw=0 sends Battery Control with active_power=0."""
        result = await inverter.async_set_charge_limit(0)
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 4  # select, number, number, button

        # Phase 1: set params
        assert calls[0] == call(
            "select", "select_option",
            {"entity_id": "select.solax_remotecontrol_power_control", "option": "Enabled Battery Control"},
            blocking=True,
        )
        assert calls[1] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_active_power", "value": 0},
            blocking=True,
        )
        assert calls[2] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_autorepeat_duration", "value": 60},
            blocking=True,
        )
        # Phase 2: trigger
        assert calls[3] == call(
            "button", "press",
            {"entity_id": "button.solax_remotecontrol_trigger"},
            blocking=True,
        )

    async def test_partial_charge_converts_kw_to_w(self, inverter, mock_hass):
        """power_kw=3.0 sends active_power=3000 (W)."""
        result = await inverter.async_set_charge_limit(3.0)
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 4

        # active_power should be 3000W (positive for charging)
        assert calls[1] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_active_power", "value": 3000},
            blocking=True,
        )

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """Returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))
        result = await inverter.async_set_charge_limit(0)
        assert result is False


class TestAsyncSetDischarge:
    """Tests for async_set_discharge — negative power + min SOC."""

    async def test_discharge_with_target_soc(self, inverter, mock_hass):
        """power_kw=3.0, target_soc=20 sends correct calls."""
        result = await inverter.async_set_discharge(3.0, target_soc=20)
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 5  # min_soc, select, number, number, button

        # Min SOC floor
        assert calls[0] == call(
            "number", "set_value",
            {"entity_id": "number.solax_selfuse_discharge_min_soc", "value": 20},
            blocking=True,
        )
        # Battery Control mode
        assert calls[1] == call(
            "select", "select_option",
            {"entity_id": "select.solax_remotecontrol_power_control", "option": "Enabled Battery Control"},
            blocking=True,
        )
        # Negative power for discharge: -3000W
        assert calls[2] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_active_power", "value": -3000},
            blocking=True,
        )
        # Autorepeat duration
        assert calls[3] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_autorepeat_duration", "value": 60},
            blocking=True,
        )
        # Trigger
        assert calls[4] == call(
            "button", "press",
            {"entity_id": "button.solax_remotecontrol_trigger"},
            blocking=True,
        )

    async def test_discharge_min_soc_clamped_to_10(self, inverter, mock_hass):
        """target_soc < 10 is clamped to 10 (SolaX minimum)."""
        await inverter.async_set_discharge(2.0, target_soc=5)
        calls = mock_hass.services.async_call.call_args_list
        # First call sets min_soc = max(5, 10) = 10
        assert calls[0] == call(
            "number", "set_value",
            {"entity_id": "number.solax_selfuse_discharge_min_soc", "value": 10},
            blocking=True,
        )

    async def test_discharge_without_target_soc(self, inverter, mock_hass):
        """Without target_soc, skips min_soc setting."""
        result = await inverter.async_set_discharge(2.0)
        assert result is True
        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 4  # No min_soc call

    async def test_discharge_ensures_negative_power(self, inverter, mock_hass):
        """Power is always negative for discharge, even if passed positive."""
        await inverter.async_set_discharge(3.0)
        calls = mock_hass.services.async_call.call_args_list
        # active_power call
        active_power_call = [c for c in calls if c[0][1] == "set_value" and "active_power" in str(c)]
        assert active_power_call[0][0][2]["value"] == -3000

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """Returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))
        result = await inverter.async_set_discharge(3.0)
        assert result is False


class TestAsyncStopForcible:
    """Tests for async_stop_forcible — Disabled + autorepeat=0."""

    async def test_stop_forcible_calls(self, inverter, mock_hass):
        """Stop sends Disabled, power=0, autorepeat=0, then trigger."""
        result = await inverter.async_stop_forcible()
        assert result is True

        calls = mock_hass.services.async_call.call_args_list
        assert len(calls) == 4

        assert calls[0] == call(
            "select", "select_option",
            {"entity_id": "select.solax_remotecontrol_power_control", "option": "Disabled"},
            blocking=True,
        )
        assert calls[1] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_active_power", "value": 0},
            blocking=True,
        )
        assert calls[2] == call(
            "number", "set_value",
            {"entity_id": "number.solax_remotecontrol_autorepeat_duration", "value": 0},
            blocking=True,
        )
        assert calls[3] == call(
            "button", "press",
            {"entity_id": "button.solax_remotecontrol_trigger"},
            blocking=True,
        )

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """Returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(side_effect=Exception("Service error"))
        result = await inverter.async_stop_forcible()
        assert result is False


class TestIsAvailable:
    """Tests for is_available property."""

    def test_available_when_loaded(self, mock_hass, solax_config):
        """Returns True when solax_modbus is loaded."""
        entry = MagicMock()
        entry.state.value = "loaded"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])

        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is True

    def test_unavailable_when_not_loaded(self, mock_hass, solax_config):
        """Returns False when solax_modbus is not loaded."""
        entry = MagicMock()
        entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])

        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is False

    def test_unavailable_when_no_entries(self, mock_hass, solax_config):
        """Returns False when no solax_modbus entries exist."""
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])

        inv = SolaXInverter(mock_hass, solax_config)
        assert inv.is_available is False


class TestEntityResolution:
    """Tests for entity ID resolution from config overrides vs defaults."""

    async def test_uses_config_override(self, mock_hass):
        """Config key overrides default entity ID."""
        config = {
            "solax_remotecontrol_power_control": "select.custom_prefix_remotecontrol_power_control",
            "solax_remotecontrol_active_power": "number.custom_prefix_remotecontrol_active_power",
            "solax_remotecontrol_autorepeat_duration": "number.custom_prefix_remotecontrol_autorepeat_duration",
            "solax_remotecontrol_trigger": "button.custom_prefix_remotecontrol_trigger",
        }
        inv = SolaXInverter(mock_hass, config)
        await inv.async_set_charge_limit(0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0][0][2]["entity_id"] == "select.custom_prefix_remotecontrol_power_control"
        assert calls[1][0][2]["entity_id"] == "number.custom_prefix_remotecontrol_active_power"
        assert calls[2][0][2]["entity_id"] == "number.custom_prefix_remotecontrol_autorepeat_duration"
        assert calls[3][0][2]["entity_id"] == "button.custom_prefix_remotecontrol_trigger"

    async def test_uses_defaults_when_no_config(self, mock_hass):
        """Falls back to SOLAX_ENTITY_DEFAULTS when config keys are empty."""
        inv = SolaXInverter(mock_hass, {})
        await inv.async_set_charge_limit(0)

        calls = mock_hass.services.async_call.call_args_list
        assert calls[0][0][2]["entity_id"] == SOLAX_ENTITY_DEFAULTS["remotecontrol_power_control"]
        assert calls[1][0][2]["entity_id"] == SOLAX_ENTITY_DEFAULTS["remotecontrol_active_power"]
        assert calls[2][0][2]["entity_id"] == SOLAX_ENTITY_DEFAULTS["remotecontrol_autorepeat_duration"]
        assert calls[3][0][2]["entity_id"] == SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]


class TestKWToWConversion:
    """Tests for kW to W unit conversion accuracy."""

    async def test_fractional_kw_converted(self, inverter, mock_hass):
        """2.5 kW -> 2500 W."""
        await inverter.async_set_charge_limit(2.5)
        calls = mock_hass.services.async_call.call_args_list
        assert calls[1][0][2]["value"] == 2500

    async def test_discharge_fractional_kw(self, inverter, mock_hass):
        """1.5 kW discharge -> -1500 W."""
        await inverter.async_set_discharge(1.5)
        calls = mock_hass.services.async_call.call_args_list
        power_call = [c for c in calls if "active_power" in str(c[0][2].get("entity_id", ""))][0]
        assert power_call[0][2]["value"] == -1500

    async def test_small_values(self, inverter, mock_hass):
        """0.1 kW -> 100 W."""
        await inverter.async_set_charge_limit(0.1)
        calls = mock_hass.services.async_call.call_args_list
        assert calls[1][0][2]["value"] == 100
