"""Inverter factory module for EEG Energy Optimizer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import InverterBase
from .huawei import HuaweiInverter

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

INVERTER_TYPES: dict[str, type[InverterBase]] = {
    "huawei_sun2000": HuaweiInverter,
}


def create_inverter(
    inverter_type: str, hass: Any, config: dict
) -> InverterBase:
    """Create an inverter instance based on the configured type.

    Args:
        inverter_type: The inverter type identifier string.
        hass: Home Assistant instance.
        config: Integration configuration dictionary.

    Returns:
        An InverterBase subclass instance.

    Raises:
        ValueError: If the inverter type is not registered.
    """
    cls = INVERTER_TYPES.get(inverter_type)
    if cls is None:
        raise ValueError(f"Unknown inverter type: {inverter_type}")
    return cls(hass, config)
