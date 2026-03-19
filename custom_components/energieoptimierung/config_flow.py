"""Config flow for Energieoptimierung."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigEntry, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_CONSUMPTION_SENSOR,
    CONF_EINSPEISELIMIT_KW,
    CONF_ENTLADE_STARTZEIT,
    CONF_GUARD_DELAY_H,
    CONF_ENTLADELEISTUNG_KW,
    CONF_FEED_IN_SENSOR,
    CONF_FRONIUS_IP,
    CONF_FRONIUS_PASSWORD,
    CONF_FRONIUS_USER,
    CONF_HEIZSTAB_SENSOR,
    CONF_HOLZVERGASER_SENSOR,
    CONF_LOOKBACK_WEEKS,
    CONF_MIN_SOC_ENTLADUNG,
    CONF_MIN_WW_ENTLADUNG,
    CONF_PUFFER_TARGET_TEMP,
    CONF_PUFFER_TEMP_SENSOR,
    CONF_PUFFER_VOLUME_L,
    CONF_PV_POWER_SENSOR,
    CONF_SICHERHEITSPUFFER_PROZENT,
    CONF_SOLCAST_MORGEN_SENSOR,
    CONF_SOLCAST_REMAINING_SENSOR,
    CONF_SUNRISE_OFFSET,
    CONF_TESLA_CAPACITY_KWH,
    CONF_TESLA_EFFICIENCY,
    CONF_TESLA_HOME_ZONE,
    CONF_TESLA_LIMIT_SENSOR,
    CONF_TESLA_SOC_SENSOR,
    CONF_TESLA_TRACKER,
    CONF_UEBERSCHUSS_FAKTOR,
    CONF_UPDATE_INTERVAL,
    CONF_WALLBOX_SENSOR,
    DEFAULT_BATTERY_CAPACITY_SENSOR,
    DEFAULT_BATTERY_SOC_SENSOR,
    DEFAULT_CONSUMPTION_SENSOR,
    DEFAULT_EINSPEISELIMIT_KW,
    DEFAULT_ENTLADE_STARTZEIT,
    DEFAULT_GUARD_DELAY_H,
    DEFAULT_ENTLADELEISTUNG_KW,
    DEFAULT_FEED_IN_SENSOR,
    DEFAULT_FRONIUS_IP,
    DEFAULT_FRONIUS_PASSWORD,
    DEFAULT_FRONIUS_USER,
    DEFAULT_HEIZSTAB_SENSOR,
    DEFAULT_HOLZVERGASER_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_MIN_SOC_ENTLADUNG,
    DEFAULT_MIN_WW_ENTLADUNG,
    DEFAULT_PUFFER_TARGET_TEMP,
    DEFAULT_PUFFER_TEMP_SENSOR,
    DEFAULT_PUFFER_VOLUME_L,
    DEFAULT_PV_POWER_SENSOR,
    DEFAULT_SICHERHEITSPUFFER_PROZENT,
    DEFAULT_SOLCAST_MORGEN_SENSOR,
    DEFAULT_SOLCAST_REMAINING_SENSOR,
    DEFAULT_SUNRISE_OFFSET_H,
    DEFAULT_TESLA_CAPACITY_KWH,
    DEFAULT_TESLA_EFFICIENCY,
    DEFAULT_TESLA_HOME_ZONE,
    DEFAULT_TESLA_LIMIT_SENSOR,
    DEFAULT_TESLA_SOC_SENSOR,
    DEFAULT_TESLA_TRACKER,
    DEFAULT_UEBERSCHUSS_FAKTOR,
    DEFAULT_UPDATE_INTERVAL_MIN,
    DEFAULT_WALLBOX_SENSOR,
    DOMAIN,
)


# ── Schema definitions ───────────────────────────────────────────────────

def _energy_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_CONSUMPTION_SENSOR,
            default=defaults.get(CONF_CONSUMPTION_SENSOR, DEFAULT_CONSUMPTION_SENSOR),
        ): str,
        vol.Required(
            CONF_HEIZSTAB_SENSOR,
            default=defaults.get(CONF_HEIZSTAB_SENSOR, DEFAULT_HEIZSTAB_SENSOR),
        ): str,
        vol.Required(
            CONF_WALLBOX_SENSOR,
            default=defaults.get(CONF_WALLBOX_SENSOR, DEFAULT_WALLBOX_SENSOR),
        ): str,
        vol.Required(
            CONF_LOOKBACK_WEEKS,
            default=defaults.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS),
        ): vol.All(int, vol.Range(min=1, max=52)),
        vol.Required(
            CONF_UPDATE_INTERVAL,
            default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN),
        ): vol.All(int, vol.Range(min=1, max=60)),
        vol.Required(
            CONF_SUNRISE_OFFSET,
            default=defaults.get(CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET_H),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=6.0)),
    })


def _battery_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_BATTERY_SOC_SENSOR,
            default=defaults.get(CONF_BATTERY_SOC_SENSOR, DEFAULT_BATTERY_SOC_SENSOR),
        ): str,
        vol.Required(
            CONF_BATTERY_CAPACITY_SENSOR,
            default=defaults.get(CONF_BATTERY_CAPACITY_SENSOR, DEFAULT_BATTERY_CAPACITY_SENSOR),
        ): str,
    })


def _puffer_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_PUFFER_TEMP_SENSOR,
            default=defaults.get(CONF_PUFFER_TEMP_SENSOR, DEFAULT_PUFFER_TEMP_SENSOR),
        ): str,
        vol.Required(
            CONF_PUFFER_VOLUME_L,
            default=defaults.get(CONF_PUFFER_VOLUME_L, DEFAULT_PUFFER_VOLUME_L),
        ): vol.All(int, vol.Range(min=50, max=10000)),
        vol.Required(
            CONF_PUFFER_TARGET_TEMP,
            default=defaults.get(CONF_PUFFER_TARGET_TEMP, DEFAULT_PUFFER_TARGET_TEMP),
        ): vol.All(vol.Coerce(float), vol.Range(min=30.0, max=95.0)),
    })


def _tesla_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_TESLA_TRACKER,
            default=defaults.get(CONF_TESLA_TRACKER, DEFAULT_TESLA_TRACKER),
        ): str,
        vol.Required(
            CONF_TESLA_SOC_SENSOR,
            default=defaults.get(CONF_TESLA_SOC_SENSOR, DEFAULT_TESLA_SOC_SENSOR),
        ): str,
        vol.Required(
            CONF_TESLA_LIMIT_SENSOR,
            default=defaults.get(CONF_TESLA_LIMIT_SENSOR, DEFAULT_TESLA_LIMIT_SENSOR),
        ): str,
        vol.Required(
            CONF_TESLA_CAPACITY_KWH,
            default=defaults.get(CONF_TESLA_CAPACITY_KWH, DEFAULT_TESLA_CAPACITY_KWH),
        ): vol.All(vol.Coerce(float), vol.Range(min=10.0, max=200.0)),
        vol.Required(
            CONF_TESLA_EFFICIENCY,
            default=defaults.get(CONF_TESLA_EFFICIENCY, DEFAULT_TESLA_EFFICIENCY),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=1.0)),
        vol.Required(
            CONF_TESLA_HOME_ZONE,
            default=defaults.get(CONF_TESLA_HOME_ZONE, DEFAULT_TESLA_HOME_ZONE),
        ): str,
    })


def _optimizer_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_PV_POWER_SENSOR,
            default=defaults.get(CONF_PV_POWER_SENSOR, DEFAULT_PV_POWER_SENSOR),
        ): str,
        vol.Required(
            CONF_FEED_IN_SENSOR,
            default=defaults.get(CONF_FEED_IN_SENSOR, DEFAULT_FEED_IN_SENSOR),
        ): str,
        vol.Required(
            CONF_SOLCAST_REMAINING_SENSOR,
            default=defaults.get(CONF_SOLCAST_REMAINING_SENSOR, DEFAULT_SOLCAST_REMAINING_SENSOR),
        ): str,
        vol.Required(
            CONF_SOLCAST_MORGEN_SENSOR,
            default=defaults.get(CONF_SOLCAST_MORGEN_SENSOR, DEFAULT_SOLCAST_MORGEN_SENSOR),
        ): str,
        vol.Required(
            CONF_HOLZVERGASER_SENSOR,
            default=defaults.get(CONF_HOLZVERGASER_SENSOR, DEFAULT_HOLZVERGASER_SENSOR),
        ): str,
        vol.Required(
            CONF_EINSPEISELIMIT_KW,
            default=defaults.get(CONF_EINSPEISELIMIT_KW, DEFAULT_EINSPEISELIMIT_KW),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=30.0)),
        vol.Required(
            CONF_UEBERSCHUSS_FAKTOR,
            default=defaults.get(CONF_UEBERSCHUSS_FAKTOR, DEFAULT_UEBERSCHUSS_FAKTOR),
        ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=5.0)),
        vol.Required(
            CONF_GUARD_DELAY_H,
            default=defaults.get(CONF_GUARD_DELAY_H, DEFAULT_GUARD_DELAY_H),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=6.0)),
    })


def _entladung_schema(defaults: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(
            CONF_ENTLADELEISTUNG_KW,
            default=defaults.get(CONF_ENTLADELEISTUNG_KW, DEFAULT_ENTLADELEISTUNG_KW),
        ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
        vol.Required(
            CONF_ENTLADE_STARTZEIT,
            default=defaults.get(CONF_ENTLADE_STARTZEIT, DEFAULT_ENTLADE_STARTZEIT),
        ): str,
        vol.Required(
            CONF_MIN_SOC_ENTLADUNG,
            default=defaults.get(CONF_MIN_SOC_ENTLADUNG, DEFAULT_MIN_SOC_ENTLADUNG),
        ): vol.All(int, vol.Range(min=5, max=50)),
        vol.Required(
            CONF_SICHERHEITSPUFFER_PROZENT,
            default=defaults.get(CONF_SICHERHEITSPUFFER_PROZENT, DEFAULT_SICHERHEITSPUFFER_PROZENT),
        ): vol.All(int, vol.Range(min=5, max=100)),
        vol.Required(
            CONF_MIN_WW_ENTLADUNG,
            default=defaults.get(CONF_MIN_WW_ENTLADUNG, DEFAULT_MIN_WW_ENTLADUNG),
        ): vol.All(vol.Coerce(float), vol.Range(min=30.0, max=85.0)),
        vol.Required(
            CONF_FRONIUS_IP,
            default=defaults.get(CONF_FRONIUS_IP, DEFAULT_FRONIUS_IP),
        ): str,
        vol.Required(
            CONF_FRONIUS_USER,
            default=defaults.get(CONF_FRONIUS_USER, DEFAULT_FRONIUS_USER),
        ): str,
        vol.Optional(
            CONF_FRONIUS_PASSWORD,
            default=defaults.get(CONF_FRONIUS_PASSWORD, DEFAULT_FRONIUS_PASSWORD),
        ): str,
    })


# ── Config Flow ──────────────────────────────────────────────────────────

class EnergieoptimierungConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Energieoptimierung."""

    VERSION = 2

    def __init__(self) -> None:
        self._data: dict = {}

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()

        return self.async_show_form(
            step_id="user",
            data_schema=_energy_schema({}),
        )

    async def async_step_battery(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_puffer()

        return self.async_show_form(
            step_id="battery",
            data_schema=_battery_schema({}),
        )

    async def async_step_puffer(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_tesla()

        return self.async_show_form(
            step_id="puffer",
            data_schema=_puffer_schema({}),
        )

    async def async_step_tesla(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_optimizer()

        return self.async_show_form(
            step_id="tesla",
            data_schema=_tesla_schema({}),
        )

    async def async_step_optimizer(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_entladung()

        return self.async_show_form(
            step_id="optimizer",
            data_schema=_optimizer_schema({}),
        )

    async def async_step_entladung(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Energieoptimierung",
                data=self._data,
            )

        return self.async_show_form(
            step_id="entladung",
            data_schema=_entladung_schema({}),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EnergieoptimierungOptionsFlow(config_entry)


# ── Options Flow ─────────────────────────────────────────────────────────

class EnergieoptimierungOptionsFlow(OptionsFlow):
    """Options flow to reconfigure after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._data: dict = {}

    def _defaults(self) -> dict:
        return {**self._config_entry.data, **self._config_entry.options, **self._data}

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_battery()

        return self.async_show_form(
            step_id="init",
            data_schema=_energy_schema(self._defaults()),
        )

    async def async_step_battery(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_puffer()

        return self.async_show_form(
            step_id="battery",
            data_schema=_battery_schema(self._defaults()),
        )

    async def async_step_puffer(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_tesla()

        return self.async_show_form(
            step_id="puffer",
            data_schema=_puffer_schema(self._defaults()),
        )

    async def async_step_tesla(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_optimizer()

        return self.async_show_form(
            step_id="tesla",
            data_schema=_tesla_schema(self._defaults()),
        )

    async def async_step_optimizer(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_entladung()

        return self.async_show_form(
            step_id="optimizer",
            data_schema=_optimizer_schema(self._defaults()),
        )

    async def async_step_entladung(
        self, user_input: dict | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(
                title="Energieoptimierung",
                data=self._data,
            )

        return self.async_show_form(
            step_id="entladung",
            data_schema=_entladung_schema(self._defaults()),
        )
