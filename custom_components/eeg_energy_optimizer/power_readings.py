"""Zentrale Helfer für das Lesen + Normalisieren von Power-Sensoren (kW).

Eine Quelle der Wahrheit für drei Aufrufer:
  - sensor.PVLeistungSensor / HausverbrauchSensor / etc. (HA-Dashboard)
  - optimizer.EEGOptimizer._current_power_readings (Telemetrie + Decision)
  - statistics.FeedinStatistics._read_grid_export (Feed-in-Aggregation)

Damit zeigen das Integration-Dashboard und das Telemetry-Backend
denselben Wert — kein Drift mehr durch divergente Lokalkopien.
"""
from __future__ import annotations

from typing import Any

from .const import (
    CONF_BATTERY_POWER_SENSOR,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    CONF_PV_POWER_SENSOR_2,
    EMMA_SENSOR_PREFIX,
    INVERTER_SIGN_CONVENTIONS,
    INVERTER_TYPE_HUAWEI,
)


def resolve_sign(inv_type: str, entity_id: str | None, kind: str) -> int:
    """Effektives Vorzeichen (+1/-1) für einen grid-/battery-Leistungssensor.

    Einzige Anwendungsstelle der Vorzeichen-Konvention — alle Aufrufer
    (Sensoren, Optimizer-Snapshot, Feed-in-Statistik) leiten ihr Vorzeichen
    hierüber ab.

    Basis ist ``INVERTER_SIGN_CONVENTIONS[inv_type][kind]`` (pro Inverter-Typ).
    Sonderfall Huawei-EMMA: Sensoren des EMMA-Energiemanagements (entity_id-
    Präfix ``sensor.emma…``) liefern die Leistung mit umgekehrtem Vorzeichen
    gegenüber der SUN2000-Konvention — für einen solchen Sensor wird das
    Basis-Vorzeichen invertiert.

    Args:
        inv_type: Konfigurierter Inverter-Typ (CONF_INVERTER_TYPE).
        entity_id: entity_id des konkreten Sensors (kann None/leer sein).
        kind: ``"grid_sign"`` oder ``"battery_sign"``.
    """
    base = INVERTER_SIGN_CONVENTIONS.get(inv_type, {}).get(kind, 1)
    if (
        inv_type == INVERTER_TYPE_HUAWEI
        and entity_id
        and entity_id.lower().startswith(EMMA_SENSOR_PREFIX)
    ):
        return -base
    return base


# Bekannte Einheiten-Aliase, alle in der KEY in lowercase. Deckt die in HA-
# Sensoren beobachteten Schreibweisen ab — bewusst defensiv, weil HA-Custom-
# Integrationen selten den `homeassistant.const.UnitOfPower`-Constraint nutzen.
_UNIT_FACTORS_TO_KW: dict[str, float] = {
    # → kW
    "kw": 1.0,
    "kilowatt": 1.0,
    "kilowatts": 1.0,
    # → W
    "w": 0.001,
    "watt": 0.001,
    "watts": 0.001,
    # → MW (selten in PV/Hausanlagen, aber gerne in Industriesensoren)
    "mw": 1000.0,
    "megawatt": 1000.0,
    "megawatts": 1000.0,
}


def read_power_kw(hass: Any, entity_id: str) -> float | None:
    """Liest einen Power-Sensor und normalisiert auf kW.

    Returns None für nicht konfigurierte / nicht verfügbare Sensoren —
    NICHT 0.0, weil das Backend zwischen "0 W" und "konnte nicht gelesen
    werden" unterscheidet.

    Einheiten-Erkennung ist case-insensitive und akzeptiert die gängigen
    Aliase (W/Watt/Watts, kW/kilowatt, MW/Megawatt). Eine fehlende oder
    unbekannte Einheit wird konservativ als kW interpretiert (Default-
    Verhalten der HA-Integration vor diesem Refactoring).
    """
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None:
        return None
    raw_state = state.state
    if raw_state in (None, "unknown", "unavailable", ""):
        return None
    try:
        val = float(raw_state)
    except (ValueError, TypeError):
        return None

    attrs = getattr(state, "attributes", None) or {}
    unit_raw = attrs.get("unit_of_measurement") if hasattr(attrs, "get") else None
    unit = (unit_raw or "").strip().lower()

    factor = _UNIT_FACTORS_TO_KW.get(unit)
    if factor is None:
        # Unbekannt oder leer → Sensor wird so behandelt, als sei er bereits
        # in kW. Das ist die historische Default-Annahme der Integration.
        return val
    return val * factor


def compute_pv_now_kw(hass: Any, config: dict) -> float | None:
    """Live-PV-Leistung in kW — identisch zu sensor.PVLeistungSensor.

    Wendet dieselben drei Korrekturen an, die das HA-Integration-Dashboard
    verwendet:
      1. Optionalen zweiten PV-Sensor summieren (Multi-Inverter-Setups,
         z.B. SolaX-Generator über Meter 2 oder zweiter SolarEdge-Inverter).
      2. ``pv_includes_battery``-Korrektur: bei SolarEdge enthält
         ``ac_power`` bereits die Batterie-Entladung. Echte PV =
         ac_power + battery_raw  (Entladung ist negativ → wird subtrahiert,
         Ladung ist positiv → wird zur PV addiert, da der Inverter die
         Batterie aus PV speist).
      3. Clipping auf ``>= 0`` — kleine negative Werte aus
         Wandlungsverlusten / Inverter-Eigenverbrauch werden zu 0, statt
         als Phantom-Negativ-Erzeugung ans Backend zu gehen.

    Liefert ``None`` nur dann, wenn weder primärer noch sekundärer
    PV-Sensor lesbar ist — andernfalls wird die jeweilige fehlende Quelle
    als 0 behandelt (Konsistenz mit ``PVLeistungSensor.async_update``).
    """
    inv_type = config.get(CONF_INVERTER_TYPE, "")
    signs = INVERTER_SIGN_CONVENTIONS.get(inv_type, {})
    pv_includes_battery = signs.get("pv_includes_battery", False)

    pv_id = config.get(CONF_PV_POWER_SENSOR, "")
    pv_2_id = config.get(CONF_PV_POWER_SENSOR_2, "")

    pv_raw = read_power_kw(hass, pv_id) if pv_id else None
    pv_2_raw = read_power_kw(hass, pv_2_id) if pv_2_id else None

    # Beide Quellen unverfügbar → kein Wert (Backend bekommt None, nicht 0)
    if pv_raw is None and pv_2_raw is None:
        return None

    pv_combined = (pv_raw or 0.0) + (pv_2_raw or 0.0)

    if pv_includes_battery:
        bat_id = config.get(CONF_BATTERY_POWER_SENSOR, "")
        if bat_id:
            bat_raw = read_power_kw(hass, bat_id)
            if bat_raw is not None:
                pv_combined += bat_raw
        # Multi-Inverter SolarEdge: zweiter PV-Sensor implizierte zweite Batterie
        # (gleiche Heuristik wie PVLeistungSensor.__init__: ac_power → b1_dc_power).
        if pv_2_id and "ac_power" in pv_2_id:
            bat_2_id = pv_2_id.replace("ac_power", "b1_dc_power")
            bat_2_raw = read_power_kw(hass, bat_2_id)
            if bat_2_raw is not None:
                pv_combined += bat_2_raw

    return max(pv_combined, 0.0)
