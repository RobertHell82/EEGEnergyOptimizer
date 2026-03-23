"""Tests for EEG Energy Optimizer select entity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    DOMAIN,
    MODE_AUS,
    MODE_EIN,
    MODE_TEST,
    OPTIMIZER_MODES,
)
from custom_components.eeg_energy_optimizer.select import OptimizerModeSelect


ENTRY_ID = "test_entry_123"


@pytest.fixture
def select_entity():
    """Create an OptimizerModeSelect instance."""
    return OptimizerModeSelect(ENTRY_ID)


class TestOptimizerModeSelect:
    def test_options(self, select_entity):
        assert select_entity._attr_options == OPTIMIZER_MODES
        assert MODE_EIN in select_entity._attr_options
        assert MODE_TEST in select_entity._attr_options
        assert MODE_AUS not in select_entity._attr_options
        assert len(select_entity._attr_options) == 2

    def test_default_option_is_test(self, select_entity):
        assert select_entity._attr_current_option == MODE_TEST

    @pytest.mark.asyncio
    async def test_select_option_updates_current(self, select_entity):
        select_entity.async_write_ha_state = MagicMock()
        await select_entity.async_select_option(MODE_EIN)
        assert select_entity._attr_current_option == MODE_EIN

    @pytest.mark.asyncio
    async def test_restore_valid_state(self, select_entity):
        last_state = MagicMock()
        last_state.state = MODE_TEST
        select_entity.async_get_last_state = AsyncMock(return_value=last_state)
        await select_entity.async_added_to_hass()
        assert select_entity._attr_current_option == MODE_TEST

    @pytest.mark.asyncio
    async def test_restore_invalid_state_ignored(self, select_entity):
        last_state = MagicMock()
        last_state.state = "Garbage"
        select_entity.async_get_last_state = AsyncMock(return_value=last_state)
        await select_entity.async_added_to_hass()
        assert select_entity._attr_current_option == MODE_TEST

    @pytest.mark.asyncio
    async def test_restore_aus_state_rejected(self, select_entity):
        """Existing users with Aus saved state should fall back to Test."""
        last_state = MagicMock()
        last_state.state = MODE_AUS
        select_entity.async_get_last_state = AsyncMock(return_value=last_state)
        await select_entity.async_added_to_hass()
        assert select_entity._attr_current_option == MODE_TEST

    @pytest.mark.asyncio
    async def test_restore_none_state(self, select_entity):
        select_entity.async_get_last_state = AsyncMock(return_value=None)
        await select_entity.async_added_to_hass()
        assert select_entity._attr_current_option == MODE_TEST

    def test_device_info_identifiers(self, select_entity):
        info = select_entity._attr_device_info
        assert (DOMAIN, ENTRY_ID) in info.get("identifiers", set())

    def test_unique_id(self, select_entity):
        assert select_entity._attr_unique_id == f"{DOMAIN}_{ENTRY_ID}_optimizer"


class TestSelectSetupEntry:
    @pytest.mark.asyncio
    async def test_async_setup_entry(self, mock_hass):
        from custom_components.eeg_energy_optimizer.select import async_setup_entry

        entry = MagicMock()
        entry.entry_id = ENTRY_ID
        mock_hass.data[DOMAIN] = {ENTRY_ID: {"config": {}}}

        entities_added = []

        def fake_add(entities):
            entities_added.extend(entities)

        await async_setup_entry(mock_hass, entry, fake_add)
        assert len(entities_added) == 1
        assert isinstance(entities_added[0], OptimizerModeSelect)
        assert mock_hass.data[DOMAIN][ENTRY_ID]["select"] is entities_added[0]
