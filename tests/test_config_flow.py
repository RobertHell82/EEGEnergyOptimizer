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
    "NumberSelector", "NumberSelectorConfig", "NumberSelectorMode",
    "TimeSelector", "TimeSelectorConfig",
]:
    setattr(sys.modules["homeassistant.helpers.selector"], selector_name, MagicMock())

from custom_components.eeg_energy_optimizer.config_flow import (
    EegEnergyOptimizerConfigFlow,
)
from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_CONSUMPTION_SENSOR,
    CONF_DISCHARGE_POWER_KW,
    CONF_DISCHARGE_START_TIME,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_SOURCE,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_LOOKBACK_WEEKS,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_PV_POWER_SENSOR,
    CONF_SAFETY_BUFFER_PCT,
    CONF_UEBERSCHUSS_SCHWELLE,
    CONF_UPDATE_INTERVAL_FAST,
    CONF_UPDATE_INTERVAL_SLOW,
    DEFAULT_CONSUMPTION_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_UPDATE_INTERVAL_FAST,
    DEFAULT_UPDATE_INTERVAL_SLOW,
    DOMAIN,
    FORECAST_SOURCE_SOLCAST,
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

    async def test_advances_to_forecast_with_valid_data(self, flow):
        """Step 'sensors' advances to 'forecast' when valid data provided."""
        flow._data = {CONF_INVERTER_TYPE: "huawei_sun2000"}
        sensor_input = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_PV_POWER_SENSOR: "sensor.pv_power",
            CONF_HUAWEI_DEVICE_ID: "device_123",
        }
        result = await flow.async_step_sensors(user_input=sensor_input)
        # Should advance to forecast step (show forecast form)
        assert result["type"] == "form"
        assert result["step_id"] == "forecast"
        # Data should be accumulated
        assert flow._data[CONF_INVERTER_TYPE] == "huawei_sun2000"
        assert flow._data[CONF_BATTERY_SOC_SENSOR] == "sensor.battery_soc"


class TestStepForecast:
    """Tests for config flow step 'forecast' (forecast source selection)."""

    async def test_shows_form_on_first_call(self, flow):
        """Step 'forecast' shows form when user_input is None."""
        result = await flow.async_step_forecast(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "forecast"

    async def test_forecast_step_solcast_valid(self, flow, mock_hass):
        """Step 'forecast' advances to 'consumption' when Solcast is installed."""
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[_make_loaded_entry()]
        )
        flow._data = {CONF_INVERTER_TYPE: "huawei_sun2000"}
        result = await flow.async_step_forecast(user_input={
            CONF_FORECAST_SOURCE: "solcast_solar",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.solcast_pv_forecast_remaining_today",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.solcast_pv_forecast_tomorrow",
        })
        assert result["type"] == "form"
        assert result["step_id"] == "consumption"
        assert flow._data[CONF_FORECAST_SOURCE] == "solcast_solar"
        assert flow._data[CONF_FORECAST_REMAINING_ENTITY] == "sensor.solcast_pv_forecast_remaining_today"

    async def test_forecast_step_not_installed(self, flow, mock_hass):
        """Step 'forecast' returns error when forecast integration not installed."""
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        result = await flow.async_step_forecast(user_input={
            CONF_FORECAST_SOURCE: "solcast_solar",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.solcast_pv_forecast_remaining_today",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.solcast_pv_forecast_tomorrow",
        })
        assert result["type"] == "form"
        assert result["step_id"] == "forecast"
        assert result["errors"]["base"] == "forecast_not_installed"

    async def test_forecast_step_not_loaded(self, flow, mock_hass):
        """Step 'forecast' returns error when forecast integration exists but not loaded."""
        entry = MagicMock()
        entry.state = MagicMock()
        entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(return_value=[entry])
        result = await flow.async_step_forecast(user_input={
            CONF_FORECAST_SOURCE: "forecast_solar",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.energy_production_today_remaining",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.energy_production_tomorrow",
        })
        assert result["type"] == "form"
        assert result["step_id"] == "forecast"
        assert result["errors"]["base"] == "forecast_not_installed"


class TestStepConsumption:
    """Tests for config flow step 'consumption' (consumption sensor config)."""

    async def test_shows_form_on_first_call(self, flow):
        """Step 'consumption' shows form when user_input is None."""
        result = await flow.async_step_consumption(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "consumption"

    async def test_consumption_step_proceeds_to_optimizer(self, flow):
        """Step 'consumption' proceeds to optimizer step (no longer creates entry)."""
        flow._data = {
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_PV_POWER_SENSOR: "sensor.pv_power",
            CONF_FORECAST_SOURCE: "solcast_solar",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.solcast_remaining",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.solcast_tomorrow",
        }
        result = await flow.async_step_consumption(user_input={
            CONF_CONSUMPTION_SENSOR: "sensor.power_meter_verbrauch",
            CONF_LOOKBACK_WEEKS: 8,
            CONF_UPDATE_INTERVAL_FAST: 1,
            CONF_UPDATE_INTERVAL_SLOW: 15,
        })
        assert result["type"] == "form"
        assert result["step_id"] == "optimizer"


class TestFullFlow:
    """Tests for the complete 4-step config flow."""

    async def test_full_flow_5_steps(self, flow, mock_hass):
        """Full flow: user -> sensors -> forecast -> consumption -> optimizer -> entry created."""
        # Step 1: user (inverter type)
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[_make_loaded_entry()]
        )
        result = await flow.async_step_user(
            user_input={CONF_INVERTER_TYPE: "huawei_sun2000"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "sensors"

        # Step 2: sensors
        result = await flow.async_step_sensors(user_input={
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_PV_POWER_SENSOR: "sensor.pv_power",
        })
        assert result["type"] == "form"
        assert result["step_id"] == "forecast"

        # Step 3: forecast
        result = await flow.async_step_forecast(user_input={
            CONF_FORECAST_SOURCE: "solcast_solar",
            CONF_FORECAST_REMAINING_ENTITY: "sensor.solcast_remaining",
            CONF_FORECAST_TOMORROW_ENTITY: "sensor.solcast_tomorrow",
        })
        assert result["type"] == "form"
        assert result["step_id"] == "consumption"

        # Step 4: consumption -> optimizer form
        result = await flow.async_step_consumption(user_input={
            CONF_CONSUMPTION_SENSOR: "sensor.power_meter_verbrauch",
            CONF_LOOKBACK_WEEKS: 8,
            CONF_UPDATE_INTERVAL_FAST: 1,
            CONF_UPDATE_INTERVAL_SLOW: 15,
        })
        assert result["type"] == "form"
        assert result["step_id"] == "optimizer"

        # Step 5: optimizer -> creates entry
        result = await flow.async_step_optimizer(user_input={
            CONF_UEBERSCHUSS_SCHWELLE: 1.25,
            CONF_MORNING_END_TIME: "10:00",
            CONF_DISCHARGE_START_TIME: "20:00",
            CONF_DISCHARGE_POWER_KW: 3.0,
            CONF_MIN_SOC: 10,
            CONF_SAFETY_BUFFER_PCT: 25,
        })
        assert result["type"] == "create_entry"
        assert result["title"] == "EEG Energy Optimizer"
        data = result["data"]
        assert data[CONF_INVERTER_TYPE] == "huawei_sun2000"
        assert data[CONF_BATTERY_SOC_SENSOR] == "sensor.battery_soc"
        assert data[CONF_FORECAST_SOURCE] == "solcast_solar"
        assert data[CONF_CONSUMPTION_SENSOR] == "sensor.power_meter_verbrauch"
        assert data[CONF_LOOKBACK_WEEKS] == 8
        assert data[CONF_UEBERSCHUSS_SCHWELLE] == 1.25
        assert data[CONF_MORNING_END_TIME] == "10:00"
        assert data[CONF_DISCHARGE_START_TIME] == "20:00"


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
