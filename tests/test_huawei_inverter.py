"""Tests for Huawei SUN2000 inverter implementation (INF-02).

Charge limiting now writes the max charge power via the `number.set_value`
service on the `number.batteries_maximale_ladeleistung` entity (or its
`batterien_…` variant). Forced discharge still goes via the huawei_solar
service `forcible_discharge_soc`. Stopping is a two-call sequence:
restore the max charge power and then stop_forcible_charge.
"""

from unittest.mock import AsyncMock, MagicMock

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

    def test_requires_charge_entity(self, mock_hass):
        """No matching charge-power entity → ValueError (auto-detect failed)."""
        mock_hass.states.get = MagicMock(return_value=None)
        with pytest.raises(ValueError, match="Ladeleistungs-Entity"):
            HuaweiInverter(mock_hass, {"huawei_device_id": "dev"})

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
