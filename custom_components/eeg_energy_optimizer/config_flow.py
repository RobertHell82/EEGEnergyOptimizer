"""Config flow for EEG Energy Optimizer integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

from homeassistant.config_entries import ConfigFlow


class EegEnergyOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EEG Energy Optimizer.

    Single-click flow that creates the entry with defaults.
    Full configuration happens in the onboarding panel.
    """

    VERSION = 9

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single-click setup step."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="EEG Energy Optimizer",
                data={"setup_complete": False},
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
