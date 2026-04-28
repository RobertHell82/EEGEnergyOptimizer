"""Tests for inverter factory pattern (INF-01)."""

import pytest

from custom_components.eeg_energy_optimizer.inverter import (
    INVERTER_TYPES,
    create_inverter,
)
from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.fronius import FroniusInverter
from custom_components.eeg_energy_optimizer.inverter.huawei import HuaweiInverter
from custom_components.eeg_energy_optimizer.inverter.solaredge import SolarEdgeInverter
from custom_components.eeg_energy_optimizer.inverter.solax import SolaXInverter


class TestInverterFactory:
    """Verify factory function creates inverters correctly."""

    def test_create_unknown_type_raises(self, mock_hass):
        """create_inverter with unknown type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown inverter type"):
            create_inverter("nonexistent", mock_hass, {})

    def test_inverter_types_dict_exists(self):
        """INVERTER_TYPES is a dict."""
        assert isinstance(INVERTER_TYPES, dict)

    def test_create_registered_type(self, mock_hass):
        """Manually registering a type in INVERTER_TYPES allows creation."""

        class MockInverter(InverterBase):
            async def async_set_charge_limit(self, power_kw):
                return True

            async def async_set_discharge(self, power_kw, target_soc=None):
                return True

            async def async_stop_forcible(self):
                return True

            @property
            def is_available(self):
                return True

        # Temporarily register
        INVERTER_TYPES["test_type"] = MockInverter
        try:
            inverter = create_inverter("test_type", mock_hass, {"key": "value"})
            assert isinstance(inverter, InverterBase)
            assert isinstance(inverter, MockInverter)
        finally:
            del INVERTER_TYPES["test_type"]


class TestRegisteredInverterTypes:
    """All four production inverter drivers are registered with the factory."""

    def test_huawei_registered(self):
        assert INVERTER_TYPES.get("huawei_sun2000") is HuaweiInverter

    def test_solax_registered(self):
        assert INVERTER_TYPES.get("solax_gen4") is SolaXInverter

    def test_solaredge_registered(self):
        assert INVERTER_TYPES.get("solaredge_storedge") is SolarEdgeInverter

    def test_fronius_registered(self):
        assert INVERTER_TYPES.get("fronius_gen24") is FroniusInverter

    def test_create_fronius_returns_instance(self, mock_hass):
        """Factory builds a FroniusInverter from the canonical type id."""
        inv = create_inverter(
            "fronius_gen24",
            mock_hass,
            {"fronius_modbus_host": "192.168.1.100", "fronius_modbus_port": 502},
        )
        assert isinstance(inv, FroniusInverter)
        assert isinstance(inv, InverterBase)
        assert inv._host == "192.168.1.100"
        assert inv._port == 502
