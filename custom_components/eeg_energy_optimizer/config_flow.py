"""Config flow for EEG Energy Optimizer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    DOMAIN,
    INVERTER_PREREQUISITES,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_INVERTER_TYPE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    {"value": "huawei_sun2000", "label": "Huawei SUN2000"},
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
    }
)

STEP_SENSORS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_BATTERY_SOC_SENSOR): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="battery")
        ),
        vol.Required(CONF_BATTERY_CAPACITY_SENSOR): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="energy")
        ),
        vol.Required(CONF_PV_POWER_SENSOR): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="power")
        ),
        vol.Required(CONF_HUAWEI_DEVICE_ID): DeviceSelector(
            DeviceSelectorConfig(integration="huawei_solar")
        ),
    }
)


class EegEnergyOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EEG Energy Optimizer.

    Step 1 (user): Select inverter type with prerequisite validation.
    Step 2 (sensors): Map SOC, capacity, PV sensors and Huawei device.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the inverter type selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            inverter_type = user_input[CONF_INVERTER_TYPE]
            required_domain = INVERTER_PREREQUISITES.get(inverter_type)

            if required_domain:
                entries = self.hass.config_entries.async_entries(required_domain)
                loaded = [e for e in entries if e.state.value == "loaded"]
                if not loaded:
                    errors["base"] = "prerequisite_not_installed"

            if not errors:
                self._data.update(user_input)
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the sensor mapping step."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="EEG Energy Optimizer",
                data=self._data,
            )

        return self.async_show_form(
            step_id="sensors",
            data_schema=STEP_SENSORS_SCHEMA,
        )
