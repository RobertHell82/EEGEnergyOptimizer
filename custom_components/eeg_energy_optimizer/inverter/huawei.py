"""Huawei SUN2000 inverter control via HA Huawei Solar services."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HUAWEI_DOMAIN = "huawei_solar"


class HuaweiInverter(InverterBase):
    """Huawei SUN2000 inverter control via HA Huawei Solar services.

    Translates kW power commands to HA service calls to the huawei_solar
    integration. Power is always passed as a string per Huawei Solar's
    services.yaml text selector requirement.
    """

    def __init__(self, hass: Any, config: dict) -> None:
        """Initialize HuaweiInverter.

        Args:
            hass: Home Assistant instance.
            config: Integration config containing 'huawei_device_id'.
        """
        super().__init__(hass, config)
        device_id = config.get("huawei_device_id")
        if not device_id:
            raise ValueError(
                "HuaweiInverter requires 'huawei_device_id' in config — "
                "device was not auto-detected. Re-run setup wizard to detect the Huawei device."
            )
        self._device_id: str = device_id

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit in kW.

        Calls huawei_solar.forcible_charge_soc to charge at the given power
        up to 100% SOC. Power is converted to watts and passed as string.
        """
        power_w = str(int(power_kw * 1000))
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "forcible_charge_soc",
                {
                    "device_id": self._device_id,
                    "power": power_w,
                    "target_soc": 100,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set charge limit")
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Set battery discharge at given power in kW.

        Calls huawei_solar.forcible_discharge_soc. If target_soc is not
        provided, defaults to 10% as the discharge floor.
        """
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

        Calls huawei_solar.stop_forcible_charge.
        """
        try:
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
