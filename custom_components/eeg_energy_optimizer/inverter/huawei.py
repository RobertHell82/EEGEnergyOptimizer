"""Huawei SUN2000 inverter control via HA Huawei Solar services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HUAWEI_DOMAIN = "huawei_solar"
MAX_CHARGE_POWER_ENTITY = "number.batteries_maximale_ladeleistung"


class HuaweiInverter(InverterBase):
    """Huawei SUN2000 inverter control via HA Huawei Solar services."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        device_id = config.get("huawei_device_id")
        if not device_id:
            raise ValueError(
                "HuaweiInverter requires 'huawei_device_id' in config — "
                "device was not auto-detected. Re-run setup wizard to detect the Huawei device."
            )
        self._device_id: str = device_id

    async def _get_max_charge_power(self) -> float:
        """Read the max value of the charge power number entity."""
        state = self._hass.states.get(MAX_CHARGE_POWER_ENTITY)
        if state is None:
            return 5000.0
        return float(state.attributes.get("max", 5000))

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery max charge power via number entity.

        power_kw=0 blocks charging, any other value sets the limit.
        """
        power_w = int(power_kw * 1000)
        try:
            await self._hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": MAX_CHARGE_POWER_ENTITY,
                    "value": power_w,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set charge limit via %s", MAX_CHARGE_POWER_ENTITY)
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Start forced battery discharge at given power and target SOC."""
        power_w = str(int(power_kw * 1000))
        soc = max(int(target_soc) if target_soc is not None else 12, 12)
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "forcible_discharge_soc",
                {
                    "device_id": self._device_id,
                    "power": power_w,
                    "target_soc": soc,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Resets max charge power to hardware maximum and stops any
        forcible charge/discharge mode.
        """
        try:
            # Restore max charge power
            max_power = await self._get_max_charge_power()
            await self._hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": MAX_CHARGE_POWER_ENTITY,
                    "value": max_power,
                },
                blocking=True,
            )
            # Stop forcible discharge if active
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "stop_forcible_charge",
                {"device_id": self._device_id},
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        """Whether the Huawei Solar integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(HUAWEI_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
