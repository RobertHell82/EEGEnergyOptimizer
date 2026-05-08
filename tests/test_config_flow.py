"""Tests for the EEG Energy Optimizer config flow.

The current flow is single-click — the heavy configuration lives in the
sidebar panel, not in the HA config flow. The flow only creates a stub
entry (`setup_complete=False`) so that the user has somewhere to land.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# The test environment does not have homeassistant installed.
# Mock the modules config_flow imports BEFORE importing the module.
_ha_mocks: dict[str, MagicMock] = {}
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


class _MockConfigFlow:
    """Stand-in for homeassistant.config_entries.ConfigFlow."""

    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._domain = domain

    def async_show_form(self, **kw):  # pragma: no cover - overridden in fixture
        return kw

    def async_create_entry(self, **kw):  # pragma: no cover - overridden in fixture
        return kw

    async def async_set_unique_id(self, uid):  # pragma: no cover
        return None

    def _abort_if_unique_id_configured(self):  # pragma: no cover
        pass


sys.modules["homeassistant.config_entries"].ConfigFlow = _MockConfigFlow
sys.modules["homeassistant.config_entries"].ConfigFlowResult = dict

from custom_components.eeg_energy_optimizer.config_flow import (  # noqa: E402
    EegEnergyOptimizerConfigFlow,
)
from custom_components.eeg_energy_optimizer.const import DOMAIN  # noqa: E402


@pytest.fixture
def flow(mock_hass):
    """Config flow instance with hass + the create_entry/show_form helpers stubbed."""
    flow = EegEnergyOptimizerConfigFlow()
    flow.hass = mock_hass
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    flow.async_show_form = MagicMock(
        side_effect=lambda **kwargs: {
            "type": "form",
            "step_id": kwargs.get("step_id"),
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


class TestConfigFlowMetadata:
    """Static metadata of the flow class."""

    def test_domain_matches_const(self):
        """The flow is registered under the same DOMAIN as the integration."""
        assert EegEnergyOptimizerConfigFlow._domain == DOMAIN

    def test_version_in_sync_with_migration(self):
        """VERSION must match the highest migration target in __init__.py.

        Latest migration: v17 (discharge_a_reserve_pct aus dem Schema entfernt;
        Slot A endet immer bei min_soc, Slot-B-Reserve wegrationalisiert).
        """
        assert EegEnergyOptimizerConfigFlow.VERSION == 17

    def test_config_flow_version_is_17(self):
        """Smoke: VERSION wurde von 16 auf 17 angehoben."""
        assert EegEnergyOptimizerConfigFlow.VERSION == 17


class TestStepUser:
    """The single setup step shown by the integration's add-button."""

    async def test_shows_form_when_no_input(self, flow):
        """First call (user_input=None) renders the confirmation form."""
        result = await flow.async_step_user(user_input=None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_creates_entry_on_confirmation(self, flow):
        """Second call (user_input != None) creates a stub entry."""
        result = await flow.async_step_user(user_input={})
        assert result["type"] == "create_entry"
        assert result["title"] == "EEG Energy Optimizer"
        # Setup intentionally incomplete — the panel finishes configuration.
        assert result["data"]["setup_complete"] is False

    async def test_unique_id_set_to_domain(self, flow):
        """Only one entry is allowed; uniqueness is enforced via DOMAIN as id."""
        await flow.async_step_user(user_input={})
        flow.async_set_unique_id.assert_awaited_once_with(DOMAIN)
        flow._abort_if_unique_id_configured.assert_called_once()
