"""Config flow for EEG Energy Optimizer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    DOMAIN,
    INVERTER_PREREQUISITES,
    INVERTER_TYPE_HUAWEI,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

from homeassistant.config_entries import ConfigFlow
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
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

# Known default entity IDs per inverter type.
# If these entities exist, they are pre-selected in the sensor step.
HUAWEI_DEFAULTS = {
    CONF_BATTERY_SOC_SENSOR: "sensor.batteries_batterieladung",
    CONF_BATTERY_CAPACITY_SENSOR: "sensor.batterien_akkukapazitat",
    CONF_PV_POWER_SENSOR: "sensor.inverter_eingangsleistung",
}


def _find_huawei_battery_device(hass) -> str | None:
    """Auto-detect the Huawei Solar battery device ID."""
    registry = dr.async_get(hass)
    for device in registry.devices.values():
        if any(
            domain == "huawei_solar"
            for domain, _ in device.identifiers
        ):
            if device.name and "batter" in device.name.lower():
                return device.id
    # Fallback: return first huawei_solar device
    for device in registry.devices.values():
        if any(
            domain == "huawei_solar"
            for domain, _ in device.identifiers
        ):
            return device.id
    return None


class EegEnergyOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EEG Energy Optimizer.

    Step 1 (user): Select inverter type with prerequisite validation.
    Step 2 (sensors): Map SOC, capacity, and PV sensors.
    The Huawei battery device is auto-detected from the device registry.
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
                # Auto-detect device ID
                if inverter_type == INVERTER_TYPE_HUAWEI:
                    device_id = _find_huawei_battery_device(self.hass)
                    if device_id:
                        self._data[CONF_HUAWEI_DEVICE_ID] = device_id
                        _LOGGER.info("Auto-detected Huawei battery device: %s", device_id)
                    else:
                        _LOGGER.warning("Huawei Solar loaded but no battery device found")

                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    def _get_sensor_defaults(self) -> dict[str, str]:
        """Get default sensor entity IDs if they exist for the selected inverter."""
        defaults: dict[str, str] = {}
        inverter_type = self._data.get(CONF_INVERTER_TYPE)

        if inverter_type == INVERTER_TYPE_HUAWEI:
            for conf_key, entity_id in HUAWEI_DEFAULTS.items():
                state = self.hass.states.get(entity_id)
                if state is not None:
                    defaults[conf_key] = entity_id

        return defaults

    def _build_sensors_schema(self) -> vol.Schema:
        """Build sensor step schema with defaults from known entities."""
        defaults = self._get_sensor_defaults()
        has_capacity_sensor = CONF_BATTERY_CAPACITY_SENSOR in defaults

        schema_dict: dict = {
            vol.Required(
                CONF_BATTERY_SOC_SENSOR,
                default=defaults.get(CONF_BATTERY_SOC_SENSOR),
            ): EntitySelector(
                EntitySelectorConfig(domain="sensor")
            ),
        }

        # Capacity: offer sensor if auto-detected, otherwise manual input.
        # Both fields shown — user fills one or the other.
        if has_capacity_sensor:
            schema_dict[vol.Optional(
                CONF_BATTERY_CAPACITY_SENSOR,
                default=defaults[CONF_BATTERY_CAPACITY_SENSOR],
            )] = EntitySelector(
                EntitySelectorConfig(domain="sensor")
            )
            schema_dict[vol.Optional(CONF_BATTERY_CAPACITY_KWH)] = NumberSelector(
                NumberSelectorConfig(
                    min=1, max=100, step=0.1, unit_of_measurement="kWh",
                    mode=NumberSelectorMode.BOX,
                )
            )
        else:
            # No capacity sensor found — manual input as default, sensor as optional
            schema_dict[vol.Optional(CONF_BATTERY_CAPACITY_SENSOR)] = EntitySelector(
                EntitySelectorConfig(domain="sensor")
            )
            schema_dict[vol.Required(CONF_BATTERY_CAPACITY_KWH)] = NumberSelector(
                NumberSelectorConfig(
                    min=1, max=100, step=0.1, unit_of_measurement="kWh",
                    mode=NumberSelectorMode.BOX,
                )
            )

        schema_dict[vol.Required(
            CONF_PV_POWER_SENSOR,
            default=defaults.get(CONF_PV_POWER_SENSOR),
        )] = EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="power")
        )

        return vol.Schema(schema_dict)

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the sensor mapping step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            has_sensor = user_input.get(CONF_BATTERY_CAPACITY_SENSOR)
            has_manual = user_input.get(CONF_BATTERY_CAPACITY_KWH)

            if not has_sensor and not has_manual:
                errors[CONF_BATTERY_CAPACITY_KWH] = "capacity_required"
            else:
                self._data.update(user_input)
                return self.async_create_entry(
                    title="EEG Energy Optimizer",
                    data=self._data,
                )

        return self.async_show_form(
            step_id="sensors",
            data_schema=self._build_sensors_schema(),
            errors=errors,
        )
