"""Shared Fronius sync – called whenever Einspeisung switch or Einspeiseleistung changes."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import DATA_OPTIMIZER, DOMAIN

_LOGGER = logging.getLogger(__name__)

ENTITY_EINSPEISUNG = "switch.energieoptimierung_einspeisung"
ENTITY_LEISTUNG = "number.energieoptimierung_einspeiseleistung"


async def async_sync_to_fronius(hass: HomeAssistant) -> None:
    """Read current switch + number state and write to Fronius API.

    - Switch ON + Leistung > 0:  HYB_EM_MODE=1, HYB_EM_POWER=-(leistung*1000)
    - Switch OFF or Leistung 0:  HYB_EM_MODE=0 (auto)
    """
    optimizer = hass.data.get(DOMAIN, {}).get(DATA_OPTIMIZER)
    if optimizer is None or optimizer._fronius is None:
        _LOGGER.warning("Fronius API nicht konfiguriert – sync übersprungen")
        return

    switch_state = hass.states.get(ENTITY_EINSPEISUNG)
    number_state = hass.states.get(ENTITY_LEISTUNG)

    einspeisung_aktiv = switch_state is not None and switch_state.state == "on"

    try:
        leistung_kw = float(number_state.state) if number_state else 0.0
    except (ValueError, TypeError):
        leistung_kw = 0.0

    if einspeisung_aktiv and leistung_kw > 0:
        _LOGGER.info(
            "Fronius sync: Einspeisung AN, %s kW → HYB_EM_MODE=1, HYB_EM_POWER=%s",
            leistung_kw, int(leistung_kw * -1000),
        )
        await optimizer._fronius.async_set_discharge(leistung_kw)
    else:
        _LOGGER.info("Fronius sync: Einspeisung AUS → HYB_EM_MODE=0 (auto)")
        await optimizer._fronius.async_set_auto_mode()
