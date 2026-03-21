"""Config flow for EEG Energy Optimizer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_CONSUMPTION_SENSOR,
    CONF_DISCHARGE_POWER_KW,
    CONF_DISCHARGE_START_TIME,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_SOURCE,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_HUAWEI_DEVICE_ID,
    CONF_INVERTER_TYPE,
    CONF_LOOKBACK_WEEKS,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_PV_POWER_SENSOR,
    CONF_SAFETY_BUFFER_PCT,
    CONF_UEBERSCHUSS_SCHWELLE,
    CONF_UPDATE_INTERVAL_FAST,
    CONF_UPDATE_INTERVAL_SLOW,
    DEFAULT_CONSUMPTION_SENSOR,
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_SAFETY_BUFFER_PCT,
    DEFAULT_UEBERSCHUSS_SCHWELLE,
    DEFAULT_UPDATE_INTERVAL_FAST,
    DEFAULT_UPDATE_INTERVAL_SLOW,
    DOMAIN,
    FORECAST_SOURCE_FORECAST_SOLAR,
    FORECAST_SOURCE_SOLCAST,
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
    TimeSelector,
    TimeSelectorConfig,
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
    Step 3 (forecast): Select PV forecast source and entity IDs.
    Step 4 (consumption): Configure consumption sensor and intervals.
    The Huawei battery device is auto-detected from the device registry.
    """

    VERSION = 3

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
                return await self.async_step_forecast()

        return self.async_show_form(
            step_id="sensors",
            data_schema=self._build_sensors_schema(),
            errors=errors,
        )

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the forecast source selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            forecast_source = user_input[CONF_FORECAST_SOURCE]

            # Validate that the selected forecast integration is installed and loaded
            entries = self.hass.config_entries.async_entries(forecast_source)
            loaded = [e for e in entries if e.state.value == "loaded"]
            if not loaded:
                errors["base"] = "forecast_not_installed"
            else:
                self._data.update(user_input)
                return await self.async_step_consumption()

        return self.async_show_form(
            step_id="forecast",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FORECAST_SOURCE): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                {"value": FORECAST_SOURCE_SOLCAST, "label": "Solcast Solar"},
                                {"value": FORECAST_SOURCE_FORECAST_SOLAR, "label": "Forecast.Solar"},
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(CONF_FORECAST_REMAINING_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(CONF_FORECAST_TOMORROW_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_consumption(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the consumption sensor configuration step."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_optimizer()

        return self.async_show_form(
            step_id="consumption",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONSUMPTION_SENSOR,
                        default=DEFAULT_CONSUMPTION_SENSOR,
                    ): EntitySelector(
                        EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Required(
                        CONF_LOOKBACK_WEEKS,
                        default=DEFAULT_LOOKBACK_WEEKS,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=52, step=1,
                            unit_of_measurement="Wochen",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL_FAST,
                        default=DEFAULT_UPDATE_INTERVAL_FAST,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=60, step=1,
                            unit_of_measurement="Minuten",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_UPDATE_INTERVAL_SLOW,
                        default=DEFAULT_UPDATE_INTERVAL_SLOW,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=120, step=5,
                            unit_of_measurement="Minuten",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )

    async def async_step_optimizer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the optimizer settings step."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="EEG Energy Optimizer",
                data=self._data,
            )

        return self.async_show_form(
            step_id="optimizer",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UEBERSCHUSS_SCHWELLE,
                        default=DEFAULT_UEBERSCHUSS_SCHWELLE,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0.5, max=3.0, step=0.05,
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MORNING_END_TIME,
                        default=DEFAULT_MORNING_END_TIME,
                    ): TimeSelector(
                        TimeSelectorConfig()
                    ),
                    vol.Required(
                        CONF_DISCHARGE_START_TIME,
                        default=DEFAULT_DISCHARGE_START_TIME,
                    ): TimeSelector(
                        TimeSelectorConfig()
                    ),
                    vol.Required(
                        CONF_DISCHARGE_POWER_KW,
                        default=DEFAULT_DISCHARGE_POWER_KW,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0.5, max=10.0, step=0.5,
                            unit_of_measurement="kW",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_MIN_SOC,
                        default=DEFAULT_MIN_SOC,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=50, step=1,
                            unit_of_measurement="%",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_SAFETY_BUFFER_PCT,
                        default=DEFAULT_SAFETY_BUFFER_PCT,
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=100, step=5,
                            unit_of_measurement="%",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
