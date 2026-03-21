"""Tests for Huawei SUN2000 inverter implementation (INF-02)."""

from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.huawei import (
    HUAWEI_DOMAIN,
    HuaweiInverter,
)


@pytest.fixture
def huawei_config():
    """Standard config for Huawei inverter tests."""
    return {"huawei_device_id": "test_device"}


@pytest.fixture
def inverter(mock_hass, huawei_config):
    """Create a HuaweiInverter instance with mocked hass."""
    return HuaweiInverter(mock_hass, huawei_config)


class TestHuaweiInverterBase:
    """Verify HuaweiInverter inherits from InverterBase."""

    def test_is_instance_of_inverter_base(self, inverter):
        """HuaweiInverter is an instance of InverterBase."""
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        """HuaweiInverter is a subclass of InverterBase."""
        assert issubclass(HuaweiInverter, InverterBase)


class TestAsyncSetChargeLimit:
    """Tests for async_set_charge_limit service calls."""

    async def test_calls_correct_service(self, inverter, mock_hass):
        """async_set_charge_limit calls forcible_charge_soc with correct params."""
        result = await inverter.async_set_charge_limit(5.0)

        mock_hass.services.async_call.assert_called_once_with(
            "huawei_solar",
            "forcible_charge_soc",
            {
                "device_id": "test_device",
                "power": "5000",
                "target_soc": 100,
            },
            blocking=True,
        )
        assert result is True

    async def test_returns_true_on_success(self, inverter):
        """async_set_charge_limit returns True on success."""
        result = await inverter.async_set_charge_limit(3.0)
        assert result is True

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """async_set_charge_limit returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(
            side_effect=Exception("Service error")
        )
        result = await inverter.async_set_charge_limit(5.0)
        assert result is False

    async def test_power_is_string(self, inverter, mock_hass):
        """Power parameter is always passed as string type."""
        await inverter.async_set_charge_limit(5.0)
        call_args = mock_hass.services.async_call.call_args
        power_value = call_args[0][2]["power"]
        assert isinstance(power_value, str)
        assert power_value == "5000"


class TestAsyncSetDischarge:
    """Tests for async_set_discharge service calls."""

    async def test_calls_correct_service_with_target_soc(self, inverter, mock_hass):
        """async_set_discharge calls forcible_discharge_soc with target_soc."""
        result = await inverter.async_set_discharge(3.0, target_soc=20)

        mock_hass.services.async_call.assert_called_once_with(
            "huawei_solar",
            "forcible_discharge_soc",
            {
                "device_id": "test_device",
                "power": "3000",
                "target_soc": 20,
            },
            blocking=True,
        )
        assert result is True

    async def test_defaults_target_soc_to_10(self, inverter, mock_hass):
        """async_set_discharge without target_soc defaults to soc=10."""
        await inverter.async_set_discharge(3.0)

        call_args = mock_hass.services.async_call.call_args
        assert call_args[0][2]["target_soc"] == 10

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """async_set_discharge returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(
            side_effect=Exception("Service error")
        )
        result = await inverter.async_set_discharge(3.0, target_soc=20)
        assert result is False

    async def test_power_is_string(self, inverter, mock_hass):
        """Power parameter is always passed as string type."""
        await inverter.async_set_discharge(2.5)
        call_args = mock_hass.services.async_call.call_args
        power_value = call_args[0][2]["power"]
        assert isinstance(power_value, str)
        assert power_value == "2500"


class TestAsyncStopForcible:
    """Tests for async_stop_forcible service calls."""

    async def test_calls_correct_service(self, inverter, mock_hass):
        """async_stop_forcible calls stop_forcible_charge."""
        result = await inverter.async_stop_forcible()

        mock_hass.services.async_call.assert_called_once_with(
            "huawei_solar",
            "stop_forcible_charge",
            {"device_id": "test_device"},
            blocking=True,
        )
        assert result is True

    async def test_returns_false_on_exception(self, inverter, mock_hass):
        """async_stop_forcible returns False when service call raises."""
        mock_hass.services.async_call = AsyncMock(
            side_effect=Exception("Service error")
        )
        result = await inverter.async_stop_forcible()
        assert result is False


class TestIsAvailable:
    """Tests for is_available property."""

    def test_returns_true_when_huawei_solar_loaded(self, inverter, mock_hass):
        """is_available returns True when huawei_solar has a loaded config entry."""
        mock_entry = MagicMock()
        mock_entry.state = MagicMock()
        mock_entry.state.value = "loaded"
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[mock_entry]
        )
        assert inverter.is_available is True

    def test_returns_false_when_no_entries(self, inverter, mock_hass):
        """is_available returns False when huawei_solar has no entries."""
        mock_hass.config_entries.async_entries = MagicMock(return_value=[])
        assert inverter.is_available is False

    def test_returns_false_when_not_loaded(self, inverter, mock_hass):
        """is_available returns False when entry state is not loaded."""
        mock_entry = MagicMock()
        mock_entry.state = MagicMock()
        mock_entry.state.value = "setup_error"
        mock_hass.config_entries.async_entries = MagicMock(
            return_value=[mock_entry]
        )
        assert inverter.is_available is False
