"""Tests for inverter factory pattern (INF-01)."""

import pytest

from custom_components.eeg_energy_optimizer.inverter import (
    INVERTER_TYPES,
    create_inverter,
)
from custom_components.eeg_energy_optimizer.inverter.base import InverterBase


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
