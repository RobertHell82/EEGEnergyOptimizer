"""Tests for EEG Energy Optimizer config flow (INF-03)."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock homeassistant modules before importing config_flow
# The dev environment does not have homeassistant installed
_ha_mocks = {}
for mod_name in [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.selector",
]:
    if mod_name not in sys.modules:
        _ha_mocks[mod_name] = MagicMock()
        sys.modules[mod_name] = _ha_mocks[mod_name]

# Create a proper ConfigFlow mock base class that accepts domain= keyword
class _MockConfigFlow:
    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._domain = domain

    def async_show_form(self, **kw):
        return kw

    def async_create_entry(self, **kw):
        return kw

    async def async_set_unique_id(self, uid):
        return None

    def _abort_if_unique_id_configured(self):
        pass

sys.modules["homeassistant.config_entries"].ConfigFlow = _MockConfigFlow
sys.modules["homeassistant.config_entries"].ConfigFlowResult = dict

# Mock selectors as simple pass-through classes
for selector_name in [
    "SelectSelector", "SelectSelectorConfig", "SelectSelectorMode",
    "EntitySelector", "EntitySelectorConfig",
    "DeviceSelector", "DeviceSelectorConfig",
]:
    setattr(sys.modules["homeassistant.helpers.selector"], selector_name, MagicMock())

from custom_components.eeg_energy_optimizer.config_flow import (
    EegEnergyOptimizerConfigFlow,
)
from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    DOMAIN,
)


@pytest.fixture
def flow(mock_hass):
    """Create config flow instance with mocked hass."""
    flow = EegEnergyOptimizerConfigFlow()
    flow.hass = mock_hass
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_show_form = MagicMock(
        side_effect=lambda **kwargs: {
            "type": "form",
            "step_id": kwargs.get("step_id"),
            "errors": kwargs.get("errors", {}),
            "data_schema": kwargs.get("data_schema"),
        }
    )
    flow.async_create_entry = MagicMock(
        side_effect=lambda **kwargs: {
            "type": "create_entry",
            "title": kwargs.get("title"),
            "data": kwargs.get("data"),
        }
    )
    return flow


def _make_loaded_entry():
    """Create a mock config entry with loaded state."""
    entry = MagicMock()
    entry.state = MagicMock()
    entry.state.value = "loaded"
    return entry


class TestStepUser:
    """Tests for config flow step 'user' (inverter type selection)."""

    async def test_shows_form_on_first_call(self, flow):
        """Step 'user' shows form when user_input is None."""
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_advances_to_sensors_with_valid_prerequisite(self, flow, mock_hass):
        """Step 'user' advances to 'sensors' when prerequisite is loaded."""
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[_make_loaded_entry()]
        )
        result = await flow.async_step_user(
            user_input={CONF_INVERTER_TYPE: "huawei_sun2000"}
        )
        # Should advance to sensors step (show sensors form)
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

    async def test_returns_error_without_prerequisite(self, flow, mock_hass):
        """Step 'user' returns error when prerequisite is not installed."""
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        result = await flow.async_step_user(
            user_input={CONF_INVERTER_TYPE: "huawei_sun2000"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == "prerequisite_not_installed"

    async def test_returns_error_when_prerequisite_not_loaded(self, flow, mock_hass):
        """Step 'user' returns error when prerequisite exists but is not loaded."""
        entry = MagicMock()
        entry.state = MagicMock()
        entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        result = await flow.async_step_user(
            user_input={CONF_INVERTER_TYPE: "huawei_sun2000"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == "prerequisite_not_installed"


class TestStepSensors:
    """Tests for config flow step 'sensors' (sensor mapping)."""

    async def test_shows_form_on_first_call(self, flow):
        """Step 'sensors' shows form when user_input is None."""
        flow._data = {CONF_INVERTER_TYPE: "huawei_sun2000"}
        result = await flow.async_step_sensors(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

    async def test_creates_entry_with_all_data(self, flow):
        """Step 'sensors' creates entry with merged data from both steps."""
        flow._data = {CONF_INVERTER_TYPE: "huawei_sun2000"}
        sensor_input = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_PV_POWER_SENSOR: "sensor.pv_power",
            CONF_HUAWEI_DEVICE_ID: "device_123",
        }
        result = await flow.async_step_sensors(user_input=sensor_input)
        assert result["type"] == "create_entry"
        assert result["title"] == "EEG Energy Optimizer"
        data = result["data"]
        assert data[CONF_INVERTER_TYPE] == "huawei_sun2000"
        assert data[CONF_BATTERY_SOC_SENSOR] == "sensor.battery_soc"
        assert data[CONF_BATTERY_CAPACITY_SENSOR] == "sensor.battery_capacity"
        assert data[CONF_PV_POWER_SENSOR] == "sensor.pv_power"
        assert data[CONF_HUAWEI_DEVICE_ID] == "device_123"


class TestAbortAlreadyConfigured:
    """Tests for unique_id abort behavior."""

    async def test_sets_unique_id(self, flow, mock_hass):
        """Config flow sets unique_id to DOMAIN."""
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[_make_loaded_entry()]
        )
        await flow.async_step_user(
            user_input={CONF_INVERTER_TYPE: "huawei_sun2000"}
        )
        flow.async_set_unique_id.assert_called_once_with(DOMAIN)
        flow._abort_if_unique_id_configured.assert_called_once()
