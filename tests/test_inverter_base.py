"""Tests for InverterBase ABC contract (INF-01)."""

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase


class TestInverterBaseABC:
    """Verify the abstract base class enforces all required methods."""

    def test_cannot_instantiate_base_directly(self, mock_hass):
        """InverterBase cannot be instantiated directly."""
        with pytest.raises(TypeError):
            InverterBase(mock_hass, {})

    def test_incomplete_subclass_missing_charge_limit(self, mock_hass):
        """A subclass missing async_set_charge_limit raises TypeError."""

        class Incomplete(InverterBase):
            async def async_set_discharge(self, power_kw, target_soc=None):
                return True

            async def async_stop_forcible(self):
                return True

            @property
            def is_available(self):
                return True

        with pytest.raises(TypeError):
            Incomplete(mock_hass, {})

    def test_incomplete_subclass_missing_discharge(self, mock_hass):
        """A subclass missing async_set_discharge raises TypeError."""

        class Incomplete(InverterBase):
            async def async_set_charge_limit(self, power_kw):
                return True

            async def async_stop_forcible(self):
                return True

            @property
            def is_available(self):
                return True

        with pytest.raises(TypeError):
            Incomplete(mock_hass, {})

    def test_incomplete_subclass_missing_stop(self, mock_hass):
        """A subclass missing async_stop_forcible raises TypeError."""

        class Incomplete(InverterBase):
            async def async_set_charge_limit(self, power_kw):
                return True

            async def async_set_discharge(self, power_kw, target_soc=None):
                return True

            @property
            def is_available(self):
                return True

        with pytest.raises(TypeError):
            Incomplete(mock_hass, {})

    def test_incomplete_subclass_missing_is_available(self, mock_hass):
        """A subclass missing is_available raises TypeError."""

        class Incomplete(InverterBase):
            async def async_set_charge_limit(self, power_kw):
                return True

            async def async_set_discharge(self, power_kw, target_soc=None):
                return True

            async def async_stop_forcible(self):
                return True

        with pytest.raises(TypeError):
            Incomplete(mock_hass, {})

    def test_complete_subclass_instantiates(self, mock_hass):
        """A complete subclass implementing all 4 members can be instantiated."""

        class Complete(InverterBase):
            async def async_set_charge_limit(self, power_kw):
                return True

            async def async_set_discharge(self, power_kw, target_soc=None):
                return True

            async def async_stop_forcible(self):
                return True

            @property
            def is_available(self):
                return True

        inverter = Complete(mock_hass, {"test": "config"})
        assert isinstance(inverter, InverterBase)
        assert inverter._hass is mock_hass
        assert inverter._config == {"test": "config"}
