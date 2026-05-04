"""EEG Energy Optimizer decision engine.

Core intelligence: decides when to block battery charging (morning EEG feed-in)
and when to discharge (evening EEG feed-in) based on PV forecasts, consumption
history, and battery state.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Callable, Optional

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_DISCHARGE_A_RESERVE_PCT,
    CONF_DISCHARGE_A_START_TIME,
    CONF_DISCHARGE_B_END_CAP,
    CONF_DISCHARGE_B_START_TIME,
    CONF_DISCHARGE_POWER_KW,
    CONF_DISCHARGE_START_TIME,
    CONF_ENABLE_DUAL_DISCHARGE,
    CONF_ENABLE_MORNING_DELAY,
    CONF_ENABLE_NIGHT_DISCHARGE,
    CONF_ENABLE_PEAKSHARE,
    CONF_ENABLE_SLOT_A,
    CONF_ENABLE_SLOT_B,
    CONF_GRID_POWER_SENSOR,
    CONF_INVERTER_TYPE,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_MORNING_START_OFFSET,
    CONF_PEAKSHARE_COMMUNITY,
    CONF_PV_POWER_SENSOR,
    CONF_SAFETY_BUFFER_PCT,
    CONSUMPTION_SENSOR,
    DEFAULT_DISCHARGE_A_RESERVE_PCT,
    DEFAULT_DISCHARGE_A_START_TIME,
    DEFAULT_DISCHARGE_B_END_CAP,
    DEFAULT_DISCHARGE_B_START_TIME,
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_ENABLE_PEAKSHARE,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_MORNING_START_OFFSET,
    DEFAULT_PEAKSHARE_COMMUNITY,
    DEFAULT_SAFETY_BUFFER_PCT,
    INVERTER_SIGN_CONVENTIONS,
    MODE_EIN,
    MODE_TEST,
    STARTUP_GRACE_SECONDS,
    STATE_ABEND_ENTLADUNG,
    STATE_MORGEN_EINSPEISUNG,
    STATE_NORMAL,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import ConsumptionCoordinator
    from .forecast_provider import ForecastProvider
    from .inverter.base import InverterBase

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reasons-Katalog (D-12): geschlossener snake_case-Schlüsselsatz für Diagnose
# ---------------------------------------------------------------------------
# Diese Konstanten sind die einzige Quelle der Wahrheit für `Decision.reasons`
# und `Decision.blocked_by`. Telemetrie-Backend (siehe types.ts) erwartet exakt
# diese snake_case-Keys. UI-Texte für Endnutzer kommen aus REASON_LABELS_DE.

# Morgen-Einspeisung
REASON_PV_FORECAST_EXCEEDS_DEMAND = "pv_forecast_exceeds_demand"
REASON_PV_FORECAST_BELOW_THRESHOLD = "pv_forecast_below_threshold"
REASON_PV_FORECAST_NONE = "pv_forecast_none"
REASON_IN_MORNING_WINDOW = "in_morning_window"
REASON_OUTSIDE_MORNING_WINDOW = "outside_morning_window"
REASON_MORNING_DELAY_DISABLED = "morning_delay_disabled"
REASON_SUNRISE_UNKNOWN = "sunrise_unknown"
REASON_HYSTERESIS_STRICT = "hysteresis_strict"

# Abend-Entladung
REASON_NIGHT_DISCHARGE_DISABLED = "night_discharge_disabled"
REASON_OVERNIGHT_DEMAND_TOO_HIGH = "overnight_demand_too_high"
REASON_BEFORE_DISCHARGE_START = "before_discharge_start"
REASON_PEAKSHARE_BEFORE_WINDOW = "peakshare_before_window"
REASON_PEAKSHARE_WINDOW_ACTIVE = "peakshare_window_active"
REASON_PEAKSHARE_WINDOW_EXPIRED = "peakshare_window_expired"
REASON_HARD_CUTOFF_AFTER_4AM = "hard_cutoff_after_4am"
REASON_SOC_ABOVE_MIN = "soc_above_min"
REASON_SOC_BELOW_MIN = "soc_below_min"
REASON_TOMORROW_PV_SUFFICIENT = "tomorrow_pv_sufficient"
REASON_TOMORROW_PV_INSUFFICIENT = "tomorrow_pv_insufficient"
REASON_DISCHARGE_ABORTED_TODAY = "discharge_aborted_today"
REASON_BATTERY_SOC_UNAVAILABLE = "battery_soc_unavailable"

# Phase 11: Dual-Window-Entladung — Slot-aware Reasons (D-09 additiv)
REASON_BEFORE_SLOT_A = "before_slot_a"
REASON_SLOT_A_ACTIVE = "slot_a_active"
REASON_SLOT_A_RESERVE_REACHED = "slot_a_reserve_reached"
REASON_BETWEEN_SLOTS = "between_slots"
REASON_BEFORE_SLOT_B = "before_slot_b"
REASON_SLOT_B_ACTIVE = "slot_b_active"
REASON_SLOT_B_WINDOW_EXPIRED = "slot_b_window_expired"
REASON_SLOT_B_PRE_SUNRISE_CUTOFF = "slot_b_pre_sunrise_cutoff"

# Closed-Set-Garantie für Tests + Backend-Diagnose
ALL_REASONS: frozenset[str] = frozenset({
    REASON_PV_FORECAST_EXCEEDS_DEMAND,
    REASON_PV_FORECAST_BELOW_THRESHOLD,
    REASON_PV_FORECAST_NONE,
    REASON_IN_MORNING_WINDOW,
    REASON_OUTSIDE_MORNING_WINDOW,
    REASON_MORNING_DELAY_DISABLED,
    REASON_SUNRISE_UNKNOWN,
    REASON_HYSTERESIS_STRICT,
    REASON_NIGHT_DISCHARGE_DISABLED,
    REASON_OVERNIGHT_DEMAND_TOO_HIGH,
    REASON_BEFORE_DISCHARGE_START,
    REASON_PEAKSHARE_BEFORE_WINDOW,
    REASON_PEAKSHARE_WINDOW_ACTIVE,
    REASON_PEAKSHARE_WINDOW_EXPIRED,
    REASON_HARD_CUTOFF_AFTER_4AM,
    REASON_SOC_ABOVE_MIN,
    REASON_SOC_BELOW_MIN,
    REASON_TOMORROW_PV_SUFFICIENT,
    REASON_TOMORROW_PV_INSUFFICIENT,
    REASON_DISCHARGE_ABORTED_TODAY,
    REASON_BATTERY_SOC_UNAVAILABLE,
    # Phase 11: Dual-Window
    REASON_BEFORE_SLOT_A,
    REASON_SLOT_A_ACTIVE,
    REASON_SLOT_A_RESERVE_REACHED,
    REASON_BETWEEN_SLOTS,
    REASON_BEFORE_SLOT_B,
    REASON_SLOT_B_ACTIVE,
    REASON_SLOT_B_WINDOW_EXPIRED,
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
})

# Deutsche Texte für UI-Renderer (D-38). Telemetrie sendet nur Keys.
REASON_LABELS_DE: dict[str, str] = {
    REASON_PV_FORECAST_EXCEEDS_DEMAND: "PV-Prognose deckt Bedarf inkl. Puffer",
    REASON_PV_FORECAST_BELOW_THRESHOLD: "PV-Prognose unter Bedarfsschwelle",
    REASON_PV_FORECAST_NONE: "Keine PV-Prognose verfügbar",
    REASON_IN_MORNING_WINDOW: "Im Morgen-Einspeisungs-Fenster",
    REASON_OUTSIDE_MORNING_WINDOW: "Außerhalb des Morgen-Fensters",
    REASON_MORNING_DELAY_DISABLED: "Morgen-Einspeisung deaktiviert",
    REASON_SUNRISE_UNKNOWN: "Sonnenaufgang unbekannt",
    REASON_HYSTERESIS_STRICT: "Hysterese aktiv (höhere Schwelle)",
    REASON_NIGHT_DISCHARGE_DISABLED: "Abend-Entladung deaktiviert",
    REASON_OVERNIGHT_DEMAND_TOO_HIGH: "Nachtverbrauch zu hoch (Min-SOC ≥ 100%)",
    REASON_BEFORE_DISCHARGE_START: "Vor Entladestart-Zeit",
    REASON_PEAKSHARE_BEFORE_WINDOW: "PeakShare-Fenster noch nicht erreicht",
    REASON_PEAKSHARE_WINDOW_ACTIVE: "PeakShare-Fenster aktiv",
    REASON_PEAKSHARE_WINDOW_EXPIRED: "PeakShare-Fenster abgelaufen",
    REASON_HARD_CUTOFF_AFTER_4AM: "Harte Abschaltung 04:00",
    REASON_SOC_ABOVE_MIN: "SOC über Min-SOC",
    REASON_SOC_BELOW_MIN: "SOC unter Min-SOC",
    REASON_TOMORROW_PV_SUFFICIENT: "PV-Prognose morgen ausreichend",
    REASON_TOMORROW_PV_INSUFFICIENT: "PV-Prognose morgen zu gering",
    REASON_DISCHARGE_ABORTED_TODAY: "Entladung heute wegen Netzbezug abgebrochen",
    REASON_BATTERY_SOC_UNAVAILABLE: "Batterie-SOC-Sensor nicht verfügbar",
    # Phase 11: Dual-Window
    REASON_BEFORE_SLOT_A: "Vor Slot-A-Start (Abend)",
    REASON_SLOT_A_ACTIVE: "Slot A aktiv (Abend-Entladung)",
    REASON_SLOT_A_RESERVE_REACHED: "Slot-A-Reserve erreicht",
    REASON_BETWEEN_SLOTS: "Pause zwischen Slot A und Slot B",
    REASON_BEFORE_SLOT_B: "Vor Slot-B-Start (Morgen)",
    REASON_SLOT_B_ACTIVE: "Slot B aktiv (Morgen-Entladung)",
    REASON_SLOT_B_WINDOW_EXPIRED: "Slot-B-Fenster abgelaufen",
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF: "Slot B beendet vor Sonnenaufgang",
}


# Timezone utilities
try:
    from homeassistant.util import dt as dt_util

    _now = dt_util.now
    _as_local = dt_util.as_local
except ImportError:
    _now = lambda: datetime.now(tz=timezone.utc)  # noqa: E731
    _as_local = lambda dt: dt  # noqa: E731


def _read_float(hass: Any, entity_id: str) -> float | None:
    """Read a float value from an entity state."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


def _read_power_kw(hass: Any, entity_id: str) -> float | None:
    """Read a power sensor and normalise to kW (delegate to power_readings)."""
    from .power_readings import read_power_kw
    return read_power_kw(hass, entity_id)


def compute_hard_cutoff(now: datetime, next_sunrise: datetime | None) -> datetime:
    """Berechne den dynamischen Hard-Cutoff für die Abend-Entladung.

    Die Entladung muss spätestens enden, bevor:
      a) das Morgen-Einspeisungs-Fenster startet (Sonnenaufgang minus 1 h), und
      b) die Batterie für die morgendliche PV-Aufnahme leer ist.

    Frühere Logik nutzte ein fixes 04:00 unabhängig von der Saison — im
    Sommer (Sonnenaufgang ~04:30) immer noch konservativ, im Winter
    (Sonnenaufgang ~07:30) unnötig restriktiv und schneidet 2-3 h
    Einspeise-Korridor weg.

    Cutoff wird am Datum des nächsten Sonnenaufgangs verankert — egal ob wir
    pre- oder post-midnight aufgerufen werden:

      cutoff = min(04:00 am next-sunrise-Tag, next_sunrise − 1 h)

    Beispiele:
      - Aufruf 22:00, sunrise morgen 06:30 → min(04:00 morgen, 05:30) = 04:00 morgen
      - Aufruf 02:00, sunrise heute 06:30 → min(04:00 heute, 05:30) = 04:00 heute
      - Aufruf 02:00, sunrise heute 07:30 (Winter) → min(04:00 heute, 06:30)
        = 06:30 heute → 2.5 h zusätzlicher Korridor

    Falls Sonnenaufgang unbekannt: konservativer 04:00-Fallback (heute, wenn
    now in den frühen Morgenstunden liegt; sonst morgen).
    """
    if next_sunrise is None:
        anchor = now if now.hour < 12 else now + timedelta(days=1)
        return anchor.replace(hour=4, minute=0, second=0, microsecond=0)
    fixed_at_sunrise_day = next_sunrise.replace(
        hour=4, minute=0, second=0, microsecond=0
    )
    pre_sunrise = next_sunrise - timedelta(hours=1)
    return min(fixed_at_sunrise_day, pre_sunrise)


def compute_b_window_end(
    now: datetime,
    sunrise: datetime | None,
    b_end_cap: str,
    morning_offset_h: float,
) -> datetime | None:
    """Berechne das effektive Slot-B-Ende (Phase 11).

    Slot B (Morgen-Entladung) endet zum striktesten Minimum aus:
      - ``b_end_cap`` an Sunrise-Tag verankert (z.B. "07:00")
      - ``sunrise − morning_offset_h − 5min`` (Pause vor Morgen-Einspeisung)
      - ``sunrise − 5min`` (Pause vor Sunrise selbst)

    Garantiert ≥5 Minuten Pause vor Beginn der Morgen-Einspeisung
    (``sunrise − morning_offset_h``) — Slot B und Morgen-Einspeisung
    laufen niemals parallel (SPEC §5).

    Wenn ``sunrise`` unbekannt: ``None`` — Slot B kann ohne Sonnenaufgangs-
    Information nicht laufen.

    Beispiele:
      - Sommer SA 04:52, cap 07:00, offset 0 → 04:47 (sunrise−5min dominiert)
      - Winter SA 07:30, cap 07:00, offset 0 → 07:00 (cap dominiert)
      - Übergang SA 06:00, cap 07:00, offset 0 → 05:55 (sunrise−5min dominiert)
      - Tiefer Winter SA 08:30, cap 07:00, offset 0 → 07:00 (cap dominiert)
      - Winter SA 07:30, cap 07:00, offset 1 → 06:25 (pre-morning dominiert)
    """
    if sunrise is None:
        return None
    cap_h, cap_m = (int(p) for p in b_end_cap.split(":"))
    cap_at_sunrise_day = sunrise.replace(
        hour=cap_h, minute=cap_m, second=0, microsecond=0
    )
    pre_morning_einspeisung = sunrise - timedelta(
        hours=morning_offset_h, minutes=5
    )
    pre_sunrise = sunrise - timedelta(minutes=5)
    return min(cap_at_sunrise_day, pre_morning_einspeisung, pre_sunrise)


@dataclass
class Snapshot:
    """Immutable snapshot of all inputs for one optimizer cycle."""

    now: datetime
    battery_soc: float | None = None
    battery_capacity_kwh: float = 0.0
    pv_remaining_today_kwh: float | None = None
    pv_tomorrow_kwh: float | None = None
    consumption_today_kwh: float = 0.0
    consumption_to_sunset_kwh: float = 0.0
    consumption_tomorrow_kwh: float = 0.0
    consumption_overnight_kwh: float = 0.0
    consumption_today_daylight_kwh: float = 0.0    # SA -> SU today
    consumption_tomorrow_daylight_kwh: float = 0.0  # SA -> SU tomorrow
    sunrise: datetime | None = None
    sunset: datetime | None = None
    sunrise_today: datetime | None = None
    sunset_today: datetime | None = None
    sim_factor: float = 1.0

    def to_telemetry_dict(self) -> dict:
        """Schlanke Snapshot-Kopie für State-Change-Payload (D-09).

        Liefert die deterministischen Felder, die das Backend in den Tabellen
        `snapshots` und `state_changes.snapshot_json` erwartet. Live-Werte
        (pv_now_kw, grid_now_kw etc.) werden vom Aufrufer (EEGOptimizer._evaluate)
        ergänzt — Snapshot kennt keinen hass.states-Zugriff.
        """
        return {
            "soc_pct": int(round(self.battery_soc))
            if self.battery_soc is not None
            else None,
        }


@dataclass
class Decision:
    """Result of one optimizer evaluation cycle."""

    timestamp: str = ""
    zustand: str = "Normal"
    energiebedarf_kwh: float = 0.0
    ladung_blockiert: bool = False
    entladung_aktiv: bool = False
    entladeleistung_kw: float = 0.0
    min_soc_berechnet: float = 0.0
    nächste_aktion: str = ""
    markdown: str = ""
    ausführung: bool = False

    # Strukturierte Diagnose-Felder (D-09): kanonische snake_case-Keys aus
    # ALL_REASONS. Wird vom Telemetrie-Reporter 1:1 an State-Change-Events
    # gehängt. UI-Renderer übersetzen via REASON_LABELS_DE für Endnutzer.
    reasons: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)

    # Morning delay status card fields
    morning_status: str = "deaktiviert"
    morning_reason: str = ""
    morning_in_window: bool = False
    morning_pv_today_kwh: float = 0.0
    morning_threshold_kwh: float = 0.0
    morning_consumption_kwh: float = 0.0
    morning_buffer_kwh: float = 0.0
    morning_battery_kwh: float = 0.0
    morning_end_time: str = ""
    morning_sunrise_tomorrow: str = ""

    # Discharge status card fields
    discharge_status: str = "deaktiviert"
    discharge_reasons: list[str] = field(default_factory=list)
    discharge_soc: float = 0.0
    discharge_min_soc: float = 0.0
    discharge_pv_tomorrow_kwh: float = 0.0
    discharge_demand_overnight_kwh: float = 0.0
    discharge_consumption_daylight_kwh: float = 0.0
    discharge_safety_buffer_kwh: float = 0.0
    discharge_battery_charge_needed_kwh: float = 0.0
    discharge_demand_total_kwh: float = 0.0
    discharge_power_kw: float = 0.0
    discharge_start_time: str = ""
    discharge_peakshare_active: bool = False
    discharge_window_start: str = ""
    discharge_window_end: str = ""
    discharge_hysteresis_active: bool = False

    # Phase 11: aktiver Slot ("A" | "B" | None für Legacy/Pause)
    discharge_active_slot: str | None = None


class EEGOptimizer:
    """EEG-optimized battery management decision engine."""

    def __init__(
        self,
        hass: Any,
        entry_id: str,
        config: dict,
        inverter: Any,
        coordinator: Any,
        provider: Any,
        peakshare: Any = None,
        *,
        failure_callback: Optional[Callable[[str, Exception, str], None]] = None,
    ) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._config = config
        self._inverter = inverter
        self._coordinator = coordinator
        self._provider = provider
        self._peakshare = peakshare
        # W-4 — Telemetrie-Failure-Hook. Wird von __init__.py auf reporter.send_failure
        # geroutet; bleibt None für Tests / Setups ohne Telemetrie.
        self._failure_callback = failure_callback
        self._enable_peakshare = config.get(CONF_ENABLE_PEAKSHARE, DEFAULT_ENABLE_PEAKSHARE)
        self._peakshare_community = config.get(CONF_PEAKSHARE_COMMUNITY, DEFAULT_PEAKSHARE_COMMUNITY)

        # Config values
        self._morning_start_offset_h = config.get(
            CONF_MORNING_START_OFFSET, DEFAULT_MORNING_START_OFFSET
        )
        morning_end = config.get(CONF_MORNING_END_TIME, DEFAULT_MORNING_END_TIME)
        parts = morning_end.split(":")
        self._morning_end_hour = int(parts[0])
        self._morning_end_min = int(parts[1]) if len(parts) > 1 else 0

        discharge_start = config.get(
            CONF_DISCHARGE_START_TIME, DEFAULT_DISCHARGE_START_TIME
        )
        parts = discharge_start.split(":")
        self._discharge_start_h = int(parts[0])
        self._discharge_start_m = int(parts[1]) if len(parts) > 1 else 0

        self._discharge_power_kw = config.get(
            CONF_DISCHARGE_POWER_KW, DEFAULT_DISCHARGE_POWER_KW
        )
        # SolarEdge: enforce minimum discharge power of 5 kW
        inv_type_cfg = config.get(CONF_INVERTER_TYPE, "")
        if inv_type_cfg == "solaredge_storedge" and self._discharge_power_kw < 5.0:
            _LOGGER.warning(
                "SolarEdge: Entladeleistung %.1f kW unter Minimum 5 kW — auf 5 kW angehoben",
                self._discharge_power_kw,
            )
            self._discharge_power_kw = 5.0
        self._min_soc = config.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._safety_buffer_pct = config.get(
            CONF_SAFETY_BUFFER_PCT, DEFAULT_SAFETY_BUFFER_PCT
        )
        self._enable_morning_delay = config.get(CONF_ENABLE_MORNING_DELAY, True)
        self._enable_night_discharge = config.get(CONF_ENABLE_NIGHT_DISCHARGE, True)

        # Inverter deduplication
        self._prev_zustand: str | None = None
        self._last_decision: Decision | None = None

        # Hysteresis: track dates when states were first activated today.
        # If a state was already active and then deactivated on the same day,
        # require a higher threshold to reactivate (prevents oscillation).
        self._morning_activated_date: str | None = None
        self._discharge_activated_date: str | None = None
        self._last_eval_zustand: str = STATE_NORMAL

        # Phase 11: Pro-Slot-Hysterese-Felder (analog _discharge_activated_date)
        # Reset zentral in _evaluate nach today's Sunrise (analog Legacy-Pattern).
        self._slot_a_activated_date: str | None = None  # ISO "YYYY-MM-DD"
        self._slot_b_activated_date: str | None = None
        self._last_active_slot: str | None = None  # "A" | "B" | None — Reaktivierungs-Check

        # Startup grace period: don't send inverter commands until sensors
        # have had time to settle after a HA restart.
        self._startup_time: datetime = _now()
        self._grace_period_logged: bool = False

        # Grid import watchdog during discharge (SolarEdge only)
        # SolarEdge "Discharge to Maximize Export" pushes to grid but doesn't
        # cover household demand — the house draws from grid simultaneously.
        # If grid import > 1 kW persists for > 5 minutes, abort discharge for the day.
        self._grid_import_since: datetime | None = None
        self._discharge_aborted_date: str | None = None  # ISO date "YYYY-MM-DD"
        self._is_solaredge = inv_type_cfg == "solaredge_storedge"

        # Grid sensor for watchdog
        self._grid_sensor_id = config.get(CONF_GRID_POWER_SENSOR, "")
        inv_type = config.get(CONF_INVERTER_TYPE, "")
        self._grid_sign = INVERTER_SIGN_CONVENTIONS.get(inv_type, {}).get("grid_sign", 1)

        # Phase 11: Dual-Window Config-Reads
        # Default für enable_dual_discharge ist False, damit Bestands-Tests
        # ohne explizit gesetzten Key auf den Legacy-Pfad routen (D-05).
        # Echte Setups bekommen den Wert via Migration v14→v15 in __init__.py
        # (DEFAULT_ENABLE_DUAL_DISCHARGE_NON_SOLAREDGE = True für nicht-SolarEdge).
        self._enable_dual_discharge: bool = bool(
            config.get(CONF_ENABLE_DUAL_DISCHARGE, False)
        )
        self._enable_slot_a: bool = bool(config.get(CONF_ENABLE_SLOT_A, True))
        self._enable_slot_b: bool = bool(config.get(CONF_ENABLE_SLOT_B, True))
        self._discharge_a_reserve_pct: int = int(
            config.get(CONF_DISCHARGE_A_RESERVE_PCT, DEFAULT_DISCHARGE_A_RESERVE_PCT)
        )
        a_start_str = str(
            config.get(CONF_DISCHARGE_A_START_TIME, DEFAULT_DISCHARGE_A_START_TIME)
        )
        b_start_str = str(
            config.get(CONF_DISCHARGE_B_START_TIME, DEFAULT_DISCHARGE_B_START_TIME)
        )
        b_end_cap_str = str(
            config.get(CONF_DISCHARGE_B_END_CAP, DEFAULT_DISCHARGE_B_END_CAP)
        )
        a_parts = a_start_str.split(":")
        self._discharge_a_start_h = int(a_parts[0])
        self._discharge_a_start_m = int(a_parts[1]) if len(a_parts) > 1 else 0
        b_parts = b_start_str.split(":")
        self._discharge_b_start_h = int(b_parts[0])
        self._discharge_b_start_m = int(b_parts[1]) if len(b_parts) > 1 else 0
        self._discharge_b_end_cap: str = b_end_cap_str

        # Defense-in-depth: SolarEdge erzwingt Legacy-Pfad zur Laufzeit.
        # Phase-11-Migration setzt enable_dual_discharge=False schon beim Schreiben;
        # diese Runtime-Prüfung schützt vor manuell editierten Configs.
        if self._is_solaredge and self._enable_dual_discharge:
            _LOGGER.warning(
                "SolarEdge: enable_dual_discharge=True nicht erlaubt — "
                "auf False gesetzt (NVRAM-Verschleiß-Schutz)"
            )
            self._enable_dual_discharge = False

    # ------------------------------------------------------------------
    # Snapshot gathering
    # ------------------------------------------------------------------

    def _gather_snapshot(self) -> Snapshot:
        """Read all inputs and build an immutable Snapshot."""
        now = _now()

        # Battery SOC — None propagiert durch, statt mit 0.0 die Telemetrie zu
        # fälschen und min_soc_dyn auf 100% zu treiben (FIX: ehemals 0.0-Fallback).
        soc_id = self._config.get(CONF_BATTERY_SOC_SENSOR, "")
        battery_soc = _read_float(self._hass, soc_id) if soc_id else None

        # Battery capacity (sensor or manual fallback)
        capacity_kwh = self._resolve_capacity()

        # PV forecasts
        forecast = self._provider.get_forecast()
        pv_remaining = forecast.remaining_today_kwh
        pv_tomorrow = forecast.tomorrow_kwh

        # Sun times
        sunrise, sunset = self._get_sun_times(now)

        # Consumption forecasts
        tomorrow_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        tomorrow_end = tomorrow_start + timedelta(days=1)

        today_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=1
        )

        consumption_today = self._coordinator.calculate_period(now, today_end).get(
            "verbrauch_kwh", 0.0
        )
        consumption_tomorrow = self._coordinator.calculate_period(
            tomorrow_start, tomorrow_end
        ).get("verbrauch_kwh", 0.0)

        # Consumption until sunset (for morning delay decision)
        consumption_to_sunset = 0.0
        if sunset is not None and sunset > now:
            consumption_to_sunset = self._coordinator.calculate_period(
                now, sunset
            ).get("verbrauch_kwh", 0.0)

        # Overnight consumption for discharge min-SOC calculation
        # Before discharge start: from discharge_start to sunrise + 1h
        # After discharge start (incl. past midnight): from now to sunrise + 1h
        consumption_overnight = 0.0
        if sunrise is not None:
            overnight_end = sunrise + timedelta(hours=1)
            discharge_start = now.replace(
                hour=self._discharge_start_h,
                minute=self._discharge_start_m,
                second=0,
                microsecond=0,
            )
            overnight_start = max(discharge_start, now)
            # Past midnight: discharge_start resolves to tonight (future),
            # but we're already in the overnight period from yesterday's start.
            # Use now as the start so we calculate remaining demand until sunrise.
            if overnight_start > overnight_end:
                overnight_start = now
            if overnight_end > overnight_start:
                consumption_overnight = self._coordinator.calculate_period(
                    overnight_start, overnight_end
                ).get("verbrauch_kwh", 0.0)

        # Daylight consumption (SA -> SU) for morning delay decision
        consumption_today_daylight = 0.0
        consumption_tomorrow_daylight = 0.0

        if sunrise is not None and sunset is not None:
            today_date = now.date()

            # Determine today's sunrise from sun.sun next_rising
            if sunrise.date() == today_date:
                today_sunrise = sunrise
            else:
                # next_rising is tomorrow -> today's sunrise was ~24h earlier
                today_sunrise = sunrise - timedelta(days=1)

            # Determine today's sunset from sun.sun next_setting
            if sunset.date() == today_date:
                today_sunset = sunset
            else:
                # next_setting is tomorrow (we're past sunset) -> today's was ~24h earlier
                today_sunset = sunset - timedelta(days=1)

            # Today: remaining daylight consumption (max(sunrise, now) -> sunset)
            if today_sunset > now:
                daylight_start = max(today_sunrise, now)
                consumption_today_daylight = self._coordinator.calculate_period(
                    daylight_start, today_sunset
                ).get("verbrauch_kwh", 0.0)

            # Tomorrow: full daylight (shift today's times by +1 day)
            tomorrow_sunrise = today_sunrise + timedelta(days=1)
            tomorrow_sunset = today_sunset + timedelta(days=1)
            consumption_tomorrow_daylight = self._coordinator.calculate_period(
                tomorrow_sunrise, tomorrow_sunset
            ).get("verbrauch_kwh", 0.0)

        # Resolve today's actual sunrise/sunset (next_rising/next_setting may be tomorrow)
        resolved_sunrise_today = None
        resolved_sunset_today = None
        if sunrise is not None and sunset is not None:
            resolved_sunrise_today = today_sunrise
            resolved_sunset_today = today_sunset

        snap = Snapshot(
            now=now,
            battery_soc=battery_soc,
            battery_capacity_kwh=capacity_kwh,
            pv_remaining_today_kwh=pv_remaining,
            pv_tomorrow_kwh=pv_tomorrow,
            consumption_today_kwh=consumption_today,
            consumption_to_sunset_kwh=consumption_to_sunset,
            consumption_tomorrow_kwh=consumption_tomorrow,
            consumption_overnight_kwh=consumption_overnight,
            consumption_today_daylight_kwh=consumption_today_daylight,
            consumption_tomorrow_daylight_kwh=consumption_tomorrow_daylight,
            sunrise=sunrise,
            sunset=sunset,
            sunrise_today=resolved_sunrise_today,
            sunset_today=resolved_sunset_today,
        )

        # Apply test overrides if active
        overrides = self._hass.data.get("eeg_energy_optimizer", {}).get(
            self._entry_id, {}
        ).get("test_overrides")
        if overrides:
            factor = overrides.get("consumption_factor", 1.0)
            soc_override = overrides.get("soc_override")
            snap.sim_factor = factor
            if factor != 1.0:
                snap.consumption_today_kwh *= factor
                snap.consumption_to_sunset_kwh *= factor
                snap.consumption_tomorrow_kwh *= factor
                snap.consumption_overnight_kwh *= factor
                snap.consumption_today_daylight_kwh *= factor
                snap.consumption_tomorrow_daylight_kwh *= factor
            if soc_override is not None:
                snap.battery_soc = soc_override
            _LOGGER.debug(
                "Test overrides active: factor=%.1f, soc=%s", factor, soc_override
            )

        return snap

    def _current_power_readings(self) -> dict:
        """Read live power values for the snapshot payload (D-09).

        Returns dict mit pv_now_kw / consumption_now_kw / grid_now_kw /
        battery_now_kw — float|None pro Eintrag (None bei nicht
        konfiguriertem oder nicht verfügbarem Sensor).

        Sign-Konventionen folgen INVERTER_SIGN_CONVENTIONS:
          positiv = Export (Grid) bzw. Laden (Battery).

        ``pv_now_kw`` wird über den gemeinsamen ``compute_pv_now_kw``-Helper
        berechnet — dadurch ist der ans Backend gemeldete Wert IDENTISCH
        zum Sensor ``sensor.eeg_energy_optimizer_pv_leistung`` (HA-Dashboard).
        Insbesondere bei SolarEdge greift hier die ``pv_includes_battery``-
        Korrektur (ac_power enthält Batterie-Entladung) und das ≥0-Clipping.

        Wichtig: Bei fehlenden Sensoren NICHT 0.0 zurückgeben — Backend-
        Analytics unterscheiden "0 W exportiert" von "konnten nicht lesen".
        """
        from .power_readings import compute_pv_now_kw

        cfg = self._config
        inv_type = cfg.get(CONF_INVERTER_TYPE, "")
        signs = INVERTER_SIGN_CONVENTIONS.get(inv_type, {})
        battery_sign = signs.get("battery_sign", 1)
        grid_sign = signs.get("grid_sign", 1)

        pv_now_kw = compute_pv_now_kw(self._hass, cfg)
        grid_raw = _read_power_kw(self._hass, cfg.get(CONF_GRID_POWER_SENSOR, ""))
        bat_raw = _read_power_kw(self._hass, cfg.get(CONF_BATTERY_POWER_SENSOR, ""))
        cons_raw = _read_power_kw(self._hass, CONSUMPTION_SENSOR)

        return {
            "pv_now_kw": pv_now_kw,
            "grid_now_kw": (grid_raw * grid_sign) if grid_raw is not None else None,
            "battery_now_kw": (bat_raw * battery_sign) if bat_raw is not None else None,
            "consumption_now_kw": cons_raw,
        }

    def _resolve_capacity(self) -> float:
        """Resolve battery capacity: sensor -> manual fallback."""
        cap_id = self._config.get(CONF_BATTERY_CAPACITY_SENSOR, "")
        if cap_id:
            raw = _read_float(self._hass, cap_id)
            if raw is not None:
                cap_state = self._hass.states.get(cap_id)
                unit = ""
                if cap_state and hasattr(cap_state, "attributes"):
                    unit = cap_state.attributes.get("unit_of_measurement", "")
                if unit.lower() in ("wh", "w·h") or (not unit and raw > 1000):
                    return raw / 1000.0
                return raw
        manual = self._config.get(CONF_BATTERY_CAPACITY_KWH)
        return float(manual) if manual is not None else 0.0

    def _get_sun_times(
        self, now: datetime
    ) -> tuple[datetime | None, datetime | None]:
        """Get sunrise/sunset from sun.sun entity."""
        sun_state = self._hass.states.get("sun.sun")
        if sun_state is None:
            return None, None

        sunrise = None
        sunset = None

        next_rising = sun_state.attributes.get("next_rising")
        next_setting = sun_state.attributes.get("next_setting")

        if next_rising is not None:
            try:
                sunrise = _as_local(datetime.fromisoformat(str(next_rising)))
            except (ValueError, TypeError):
                pass

        if next_setting is not None:
            try:
                sunset = _as_local(datetime.fromisoformat(str(next_setting)))
            except (ValueError, TypeError):
                pass

        return sunrise, sunset

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    def _morning_delay_status(self, snap: Snapshot, bedarf: float) -> dict:
        """Compute detailed morning delay status for the status card.

        Returns a dict with: status, reason, in_window, pv_today_kwh,
        threshold_kwh, end_time, sunrise_tomorrow.
        """
        end_time_str = f"{self._morning_end_hour:02d}:{self._morning_end_min:02d}"
        result: dict = {
            "status": "deaktiviert",
            "reason": "",
            "in_window": False,
            "pv_today_kwh": 0.0,
            "threshold_kwh": 0.0,
            "consumption_kwh": 0.0,
            "buffer_kwh": 0.0,
            "battery_kwh": 0.0,
            "end_time": end_time_str,
            "sunrise_tomorrow": "",
        }

        if not self._enable_morning_delay:
            return result

        # bedarf already includes buffer on consumption (not on battery)
        result["threshold_kwh"] = bedarf
        pv_today = snap.pv_remaining_today_kwh if snap.pv_remaining_today_kwh is not None else 0.0
        result["pv_today_kwh"] = pv_today

        # Breakdown for today (in-window)
        consumption_today = snap.consumption_today_daylight_kwh
        buffer_today = consumption_today * self._safety_buffer_pct / 100
        battery_today = 0.0
        if snap.battery_capacity_kwh > 0:
            battery_today = (100 - snap.battery_soc) / 100 * snap.battery_capacity_kwh
        result["consumption_kwh"] = consumption_today
        result["buffer_kwh"] = buffer_today
        result["battery_kwh"] = battery_today

        # Check if in morning window (use today's actual sunrise, not next_rising)
        in_window = False
        if snap.sunrise_today is not None:
            window_start = snap.sunrise_today - timedelta(hours=self._morning_start_offset_h)
            morning_end = snap.now.replace(
                hour=self._morning_end_hour,
                minute=self._morning_end_min,
                second=0,
                microsecond=0,
            )
            in_window = window_start <= snap.now <= morning_end
        result["in_window"] = in_window

        # Sunrise display for tomorrow (next_rising is always the next upcoming sunrise)
        if snap.sunrise is not None:
            # If next_rising is today (before sunrise), tomorrow = next_rising + 1 day
            # If next_rising is tomorrow (after sunrise), use it directly
            if snap.sunrise.date() == snap.now.date():
                tomorrow_sunrise = snap.sunrise + timedelta(days=1)
            else:
                tomorrow_sunrise = snap.sunrise
            result["sunrise_tomorrow"] = f"~{tomorrow_sunrise.strftime('%H:%M')}"

        if in_window:
            if pv_today > bedarf:
                result["status"] = "aktiv"
                result["reason"] = f"Ladung blockiert bis {end_time_str}"
            else:
                result["status"] = "nicht_aktiv"
                result["reason"] = "PV reicht nicht für Bedarf + Puffer"
        else:
            # Outside window: check if tomorrow's conditions would trigger
            pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0
            # Estimate tomorrow's demand: consumption + missing battery energy
            missing_battery_est = 0.0
            if snap.battery_capacity_kwh > 0:
                missing_battery_est = (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
            consumption_tomorrow = snap.consumption_tomorrow_daylight_kwh
            buffer_tomorrow = consumption_tomorrow * self._safety_buffer_pct / 100
            consumption_with_buffer = consumption_tomorrow + buffer_tomorrow
            tomorrow_threshold = consumption_with_buffer + missing_battery_est

            # Show tomorrow's values in the card (not today's remaining)
            result["pv_today_kwh"] = pv_tomorrow
            result["threshold_kwh"] = tomorrow_threshold
            result["consumption_kwh"] = consumption_tomorrow
            result["buffer_kwh"] = buffer_tomorrow
            result["battery_kwh"] = missing_battery_est

            if pv_tomorrow > tomorrow_threshold:
                sunrise_str = result["sunrise_tomorrow"] or "Sonnenaufgang"
                result["status"] = "morgen_erwartet"
                result["reason"] = f"Morgen ab {sunrise_str}"
            else:
                result["status"] = "morgen_nicht_erwartet"
                result["reason"] = "PV-Prognose zu gering"

        return result

    def _discharge_detail_status(
        self, snap: Snapshot, should_discharge: bool, min_soc: float,
        discharge_blocked_by: list[str]
    ) -> dict:
        """Compute detailed discharge status for the status card.

        Args:
            discharge_blocked_by: snake_case-Keys aus ALL_REASONS, die das
                Discharge blockieren. Werden für die Status-Karte via
                REASON_LABELS_DE in deutsche Texte übersetzt (D-38).

        Returns a dict with: status, reasons (deutsche Freitext-Liste für Panel),
        soc, min_soc, pv_tomorrow_kwh, demand_tomorrow_kwh, power_kw, start_time.
        """
        # Show PeakShare window times if a plan was computed today
        ps_plan = None
        if self._enable_peakshare and self._peakshare is not None:
            ps_plan_date = getattr(self._peakshare, "_discharge_plan_date", None)
            if ps_plan_date == snap.now.strftime("%Y-%m-%d"):
                ps_plan = getattr(self._peakshare, "_discharge_plan", None)
        if ps_plan is not None:
            start_time_str = f"{ps_plan[0].strftime('%H:%M')}-{ps_plan[1].strftime('%H:%M')} (PeakShare)"
        else:
            start_time_str = f"{self._discharge_start_h:02d}:{self._discharge_start_m:02d}"
        pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0
        overnight_kwh = snap.consumption_overnight_kwh

        # Compute demand breakdown (same logic as _should_discharge)
        consumption_daylight = snap.consumption_tomorrow_daylight_kwh
        safety_buffer_kwh = consumption_daylight * (self._safety_buffer_pct / 100)
        battery_charge_needed = (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
        demand_total = consumption_daylight + safety_buffer_kwh + battery_charge_needed

        result: dict = {
            "status": "deaktiviert",
            "reasons": [],
            "soc": snap.battery_soc,
            "min_soc": min_soc,
            "pv_tomorrow_kwh": pv_tomorrow,
            "demand_overnight_kwh": overnight_kwh,
            "consumption_daylight_kwh": round(consumption_daylight, 1),
            "safety_buffer_kwh": round(safety_buffer_kwh, 1),
            "battery_charge_needed_kwh": round(battery_charge_needed, 1),
            "demand_total_kwh": round(demand_total, 1),
            "power_kw": self._discharge_power_kw,
            "start_time": start_time_str,
        }

        if not self._enable_night_discharge:
            return result

        if should_discharge:
            result["status"] = "aktiv"
            return result

        # Not discharging: separate time-reason from condition-reasons via Katalog-Keys.
        # Both fixed-time (REASON_BEFORE_DISCHARGE_START) and PeakShare
        # (REASON_PEAKSHARE_BEFORE_WINDOW) sind Time-Reasons → Karte zeigt
        # "Geplant" (blau) statt "Nicht geplant" (rot).
        time_reason_keys = {
            REASON_BEFORE_DISCHARGE_START,
            REASON_PEAKSHARE_BEFORE_WINDOW,
        }
        time_keys = [k for k in discharge_blocked_by if k in time_reason_keys]
        condition_keys = [k for k in discharge_blocked_by if k not in time_reason_keys]

        if not condition_keys and time_keys:
            # Only time is blocking -> planned
            result["status"] = "geplant"
        else:
            # Condition failures -> not planned. Übersetze Keys in deutsche Texte
            # für die Status-Karte (discharge_reasons-Feld bleibt UI-Freitext).
            result["status"] = "nicht_geplant"
            result["reasons"] = [REASON_LABELS_DE.get(k, k) for k in condition_keys]

        return result

    def _calc_energiebedarf(self, snap: Snapshot) -> float:
        """Calculate total energy demand: daylight consumption with buffer + missing battery.

        Safety buffer applies only to consumption (variable/uncertain),
        not to missing battery energy (fixed physical quantity).
        """
        consumption = snap.consumption_today_daylight_kwh
        consumption_with_buffer = consumption * (1 + self._safety_buffer_pct / 100)

        missing_battery = 0.0
        if snap.battery_capacity_kwh > 0:
            missing_battery = (
                (100 - snap.battery_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
            )

        return consumption_with_buffer + missing_battery

    def _should_block_charging(
        self, snap: Snapshot
    ) -> tuple[bool, list[str], list[str]]:
        """Determine if morning charge blocking should be active.

        Returns:
            tuple ``(block, reasons, blocked_by)`` per D-11 mit
            snake_case-Keys aus ALL_REASONS:

            - ``block=True``  → reasons listet die Aktivierungsgründe,
              ``blocked_by`` ist leer (gegenseitiger Ausschluss).
            - ``block=False`` → reasons ist leer; ``blocked_by`` listet jeden
              Guard, der das Blockieren verhindert hat (Reihenfolge:
              `morning_delay_disabled` → `sunrise_unknown` →
              `outside_morning_window` → `in_morning_window` plus
              PV-/Hysterese-Detail).
        """
        # Guard 1: Feature off
        if not self._enable_morning_delay:
            return (False, [], [REASON_MORNING_DELAY_DISABLED])

        # Guard 2: Sonnenaufgang heute unbekannt
        if snap.sunrise_today is None:
            return (False, [], [REASON_SUNRISE_UNKNOWN])

        # Guard 3: Zeitfenster
        window_start = snap.sunrise_today - timedelta(hours=self._morning_start_offset_h)
        morning_end = snap.now.replace(
            hour=self._morning_end_hour,
            minute=self._morning_end_min,
            second=0,
            microsecond=0,
        )
        if not (window_start <= snap.now <= morning_end):
            return (False, [], [REASON_OUTSIDE_MORNING_WINDOW])

        # Ab hier: im Fenster
        in_window_blocked: list[str] = [REASON_IN_MORNING_WINDOW]

        pv_today = snap.pv_remaining_today_kwh
        if pv_today is None or pv_today <= 0:
            in_window_blocked.append(REASON_PV_FORECAST_NONE)
            return (False, [], in_window_blocked)

        bedarf = self._calc_energiebedarf(snap)

        # Hysteresis: if morning feed-in was already active today and then
        # deactivated, require PV to exceed demand by 10% to reactivate.
        # Veraltete Aktivierungsdaten werden in _evaluate zentral zurückgesetzt,
        # daher reicht hier die „Datum gesetzt"-Prüfung.
        is_reactivation = (
            self._morning_activated_date is not None
            and self._last_eval_zustand != STATE_MORGEN_EINSPEISUNG
        )

        if is_reactivation:
            in_window_active: list[str] = [REASON_IN_MORNING_WINDOW, REASON_HYSTERESIS_STRICT]
            if pv_today > bedarf * 1.1:
                return (True, in_window_active + [REASON_PV_FORECAST_EXCEEDS_DEMAND], [])
            return (False, [], in_window_active + [REASON_PV_FORECAST_BELOW_THRESHOLD])

        if pv_today > bedarf:
            return (True, [REASON_IN_MORNING_WINDOW, REASON_PV_FORECAST_EXCEEDS_DEMAND], [])
        return (False, [], [REASON_IN_MORNING_WINDOW, REASON_PV_FORECAST_BELOW_THRESHOLD])

    def _calc_min_soc(self, snap: Snapshot) -> float:
        """Calculate dynamic minimum SOC for discharge.

        Formula: base_min_soc + ceil((overnight_kwh * (1 + buffer%) / capacity) * 100)

        overnight_kwh covers the period from discharge start (or now, if
        already discharging) until sunrise + 1h the next morning.
        """
        if snap.battery_capacity_kwh <= 0:
            return float(self._min_soc)

        needed_kwh = snap.consumption_overnight_kwh * (
            1 + self._safety_buffer_pct / 100
        )
        soc_pct = needed_kwh / snap.battery_capacity_kwh * 100
        return min(float(self._min_soc + math.ceil(soc_pct)), 100.0)

    # ------------------------------------------------------------------
    # Phase 11: Dual-Window-Dispatcher + Slot-Pfade
    # ------------------------------------------------------------------

    def _check_common_guards(
        self, snap: Snapshot
    ) -> tuple[list[str], float]:
        """Slot-übergreifende Guards für den Dual-Mode-Pfad (Phase 11).

        Liefert ``(blocked_by, min_soc)``. Wenn ``blocked_by`` leer ist, dürfen
        Slot-A/B evaluiert werden. Reihenfolge der Guards entspricht dem
        heutigen ``_should_discharge``-Body-Anfang (D-01).

        Hinweis: Wird NUR vom Dual-Mode-Dispatcher genutzt — der Legacy-Pfad
        (``_evaluate_legacy_window``) hat seine eigenen Guards 1:1 erhalten
        (D-05 byte-identische Garantie).
        """
        if not self._enable_night_discharge:
            return ([REASON_NIGHT_DISCHARGE_DISABLED], float(self._min_soc))

        min_soc = self._calc_min_soc(snap)
        if min_soc >= 100.0:
            return ([REASON_OVERNIGHT_DEMAND_TOO_HIGH], min_soc)

        # SolarEdge-Discharge-Aborted-Watchdog (slot-übergreifend)
        today_str = snap.now.strftime("%Y-%m-%d")
        if self._is_solaredge and self._discharge_aborted_date == today_str:
            return ([REASON_DISCHARGE_ABORTED_TODAY], min_soc)

        # Tomorrow-PV-Surplus-Check (slot-übergreifend)
        consumption_with_buffer = snap.consumption_tomorrow_daylight_kwh * (
            1 + self._safety_buffer_pct / 100
        )
        battery_charge_needed = (
            (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
        )
        tomorrow_demand = consumption_with_buffer + battery_charge_needed
        pv_tomorrow = (
            snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0
        )
        if pv_tomorrow < tomorrow_demand:
            return ([REASON_TOMORROW_PV_INSUFFICIENT], min_soc)

        return ([], min_soc)

    def _evaluate_slot_a(
        self, snap: Snapshot, min_soc: float
    ) -> tuple[bool, list[str], list[str], bool]:
        """Slot A — Abend-Entladung mit Energie-Reserve (Phase 11, SPEC §2).

        Liefert ``(passed, reasons, blocked_by, hysteresis_active)``.

        SOC-Schwelle:
          - Wenn Slot B aktiv: ``min_soc + reserve_pct`` (Reserve für Slot B)
          - Sonst (A-only): ``min_soc`` (kein Reserve-Aufschlag)

        Hysterese-Aufschlag +5% bei Reaktivierung innerhalb derselben Sitzung
        (Slot A war heute schon aktiv, _last_active_slot ist nicht "A").

        Slot A endet 5 Minuten vor Slot-B-Start (wenn B aktiv) → Mindestpause
        zwischen Inverter-Kommandos (SPEC §9, Phase 11 Constraint).
        """
        # Slot-A-Window: ab a_start (typisch 20:00). Slot A läuft über
        # Mitternacht weiter bis kurz vor Slot-B-Start (wenn B aktiv) oder
        # bis SOC-Reserve erreicht wird.
        a_start_today = snap.now.replace(
            hour=self._discharge_a_start_h,
            minute=self._discharge_a_start_m,
            second=0,
            microsecond=0,
        )
        # Past-Midnight-Phase: now in den frühen Morgenstunden + a_start
        # liegt am Vorabend (a_start_h >= 12). In dieser Phase läuft A
        # noch von gestern weiter — wir sind innerhalb des Fensters.
        is_past_midnight_phase = (
            snap.now.hour < 12 and self._discharge_a_start_h >= 12
        )
        if not is_past_midnight_phase and snap.now < a_start_today:
            return (False, [], [REASON_BEFORE_SLOT_A], False)

        # 5min-Pause vor Slot B (wenn B aktiv): Slot A endet automatisch
        if self._enable_slot_b:
            b_start = snap.now.replace(
                hour=self._discharge_b_start_h,
                minute=self._discharge_b_start_m,
                second=0,
                microsecond=0,
            )
            # Wenn b_start in den frühen Morgenstunden liegt und now nachmittags
            # ist → b_start gehört zum Folgetag.
            if self._discharge_b_start_h < 12 and snap.now.hour >= 12:
                b_start = b_start + timedelta(days=1)
            a_end_cap = b_start - timedelta(minutes=5)
            if snap.now >= a_end_cap:
                return (False, [], [REASON_SLOT_A_RESERVE_REACHED], False)

        # SOC-Schwelle: nur wenn Slot B aktiv → reserve_pct als Aufschlag
        a_reserve = self._discharge_a_reserve_pct if self._enable_slot_b else 0
        a_min_soc = min_soc + a_reserve

        # Pro-Slot-Hysterese: Aufschlag bei Reaktivierung
        is_reactivation = (
            self._slot_a_activated_date is not None
            and self._last_active_slot != "A"
        )
        effective_min_soc = a_min_soc + (5 if is_reactivation else 0)

        if snap.battery_soc <= effective_min_soc:
            blocked_by: list[str] = []
            if is_reactivation:
                blocked_by.append(REASON_HYSTERESIS_STRICT)
            blocked_by.append(REASON_SLOT_A_RESERVE_REACHED)
            return (False, [], blocked_by, is_reactivation)

        passing: list[str] = []
        if is_reactivation:
            passing.append(REASON_HYSTERESIS_STRICT)
        passing.append(REASON_SOC_ABOVE_MIN)
        passing.append(REASON_SLOT_A_ACTIVE)
        return (True, passing, [], is_reactivation)

    def _evaluate_slot_b(
        self, snap: Snapshot, min_soc: float
    ) -> tuple[bool, list[str], list[str], bool]:
        """Slot B — Morgen-Entladung mit adaptivem Ende vor Sonnenaufgang
        (Phase 11, SPEC §3 + §5).

        Liefert ``(passed, reasons, blocked_by, hysteresis_active)``.

        Window:
          - Start: ``b_start`` (z.B. 03:00); auf morgen verschoben wenn
            now nachmittags ist und b_start vormittags.
          - Ende: ``compute_b_window_end`` — striktestes ``min()`` aus
            ``b_end_cap``, ``sunrise − morning_offset_h − 5min``,
            ``sunrise − 5min``. Garantiert Mutual Exclusion zur
            Morgen-Einspeisung (≥5min Pause).

        Sommer-Edge-Case: Wenn ``b_start ≥ b_end_effective``, kann Slot B
        in dieser Sitzung nicht aktiviert werden → REASON_SLOT_B_PRE_SUNRISE_CUTOFF.
        """
        if snap.sunrise is None:
            return (False, [], [REASON_SUNRISE_UNKNOWN], False)

        # b_start auf morgen verschieben wenn now nachmittags + b_start vormittags
        # (analog discharge_start_resolved-Pattern in _evaluate_legacy_window).
        b_start = snap.now.replace(
            hour=self._discharge_b_start_h,
            minute=self._discharge_b_start_m,
            second=0,
            microsecond=0,
        )
        if snap.now.hour >= 12 and self._discharge_b_start_h < 12:
            b_start = b_start + timedelta(days=1)

        b_end = compute_b_window_end(
            snap.now,
            snap.sunrise,
            self._discharge_b_end_cap,
            float(self._morning_start_offset_h),
        )
        if b_end is None:
            return (False, [], [REASON_SUNRISE_UNKNOWN], False)
        if b_start >= b_end:
            # Sommer-Fall: Fenster schon vorbei bevor es startet
            return (False, [], [REASON_SLOT_B_PRE_SUNRISE_CUTOFF], False)
        if snap.now < b_start:
            return (False, [], [REASON_BEFORE_SLOT_B], False)
        if snap.now >= b_end:
            return (False, [], [REASON_SLOT_B_WINDOW_EXPIRED], False)

        # Pro-Slot-Hysterese (Slot B): kein Reserve-Aufschlag, nur +5%
        # bei Reaktivierung.
        is_reactivation = (
            self._slot_b_activated_date is not None
            and self._last_active_slot != "B"
        )
        effective_min_soc = min_soc + (5 if is_reactivation else 0)

        if snap.battery_soc <= effective_min_soc:
            blocked_by: list[str] = []
            if is_reactivation:
                blocked_by.append(REASON_HYSTERESIS_STRICT)
            blocked_by.append(REASON_SOC_BELOW_MIN)
            return (False, [], blocked_by, is_reactivation)

        passing: list[str] = []
        if is_reactivation:
            passing.append(REASON_HYSTERESIS_STRICT)
        passing.append(REASON_SOC_ABOVE_MIN)
        passing.append(REASON_SLOT_B_ACTIVE)
        return (True, passing, [], is_reactivation)

    def _should_discharge(
        self, snap: Snapshot
    ) -> tuple[bool, float, list[str], list[str], bool]:
        """Phase 11 Dispatcher: wählt Legacy- oder Slot-Pfad (D-01).

        Schnittstelle bleibt erhalten (D-11):
        ``(should_discharge, min_soc, reasons, blocked_by, hysteresis_active)``.

        Routing:
          - SolarEdge oder ``enable_dual_discharge=False`` → Legacy-Pfad
            (``_evaluate_legacy_window``) — D-05 byte-identische Garantie.
          - Sonst → Common-Guards + Slot-A/B-Evaluierung (D-01).
        """
        # Pfadwahl: SolarEdge (Defense-in-depth, falls Runtime-Force in __init__
        # umgangen wurde) oder Legacy-Konfig → Single-Slot-Pfad.
        use_legacy = (not self._enable_dual_discharge) or self._is_solaredge
        if use_legacy:
            return self._evaluate_legacy_window(snap)

        # Dual-Mode: Common-Guards einmal vorab
        common_blocked, min_soc = self._check_common_guards(snap)
        if common_blocked:
            return (False, min_soc, [], common_blocked, False)

        # Slot A bevorzugt (zeitlich früher), dann Slot B als Fallback
        passed_a_flag = False
        passed_b_flag = False
        passing_a: list[str] = []
        blocked_a: list[str] = []
        hyst_a = False
        passing_b: list[str] = []
        blocked_b: list[str] = []
        hyst_b = False

        if self._enable_slot_a:
            passed_a_flag, passing_a, blocked_a, hyst_a = self._evaluate_slot_a(
                snap, min_soc
            )
            if passed_a_flag:
                return (True, min_soc, passing_a, [], hyst_a)
        if self._enable_slot_b:
            passed_b_flag, passing_b, blocked_b, hyst_b = self._evaluate_slot_b(
                snap, min_soc
            )
            if passed_b_flag:
                return (True, min_soc, passing_b, [], hyst_b)

        # Beide Slots blockiert/aus → kombinierte blocked_by-Liste
        combined_blocked: list[str] = []
        if self._enable_slot_a:
            combined_blocked.extend(blocked_a)
        if self._enable_slot_b:
            combined_blocked.extend(blocked_b)
        if not combined_blocked:
            # Beide Slots disabled — synthetischer Reason
            combined_blocked = [REASON_NIGHT_DISCHARGE_DISABLED]
        return (False, min_soc, [], combined_blocked, hyst_a or hyst_b)

    def _evaluate_legacy_window(
        self, snap: Snapshot
    ) -> tuple[bool, float, list[str], list[str], bool]:
        """Legacy single-window discharge evaluation (Phase 11, D-05).

        Aktiv wenn ``enable_dual_discharge=False`` oder bei SolarEdge.
        Body byte-identisch zum heutigen ``_should_discharge`` vor dem
        Phase-11-Refactor — keine Verhaltensänderung für Setups, die explizit
        auf Single-Window konfiguriert sind.

        Returns ``(should_discharge, min_soc, reasons, blocked_by, hysteresis_active)``
        per D-11. Alle Einträge in ``reasons``/``blocked_by`` sind snake_case-Keys
        aus ALL_REASONS (D-12).
        """
        # Guard 1: Feature aus
        if not self._enable_night_discharge:
            return (False, float(self._min_soc), [], [REASON_NIGHT_DISCHARGE_DISABLED], False)

        min_soc = self._calc_min_soc(snap)

        # Guard 2: Nachtverbrauch verschlingt komplette Batterie
        if min_soc >= 100.0:
            return (False, min_soc, [], [REASON_OVERNIGHT_DEMAND_TOO_HIGH], False)

        blocked_by: list[str] = []
        passing: list[str] = []

        today_str = snap.now.strftime("%Y-%m-%d")
        # Hysterese-Status früh bestimmen — wird auch in blocked_by-Liste reflektiert.
        # Eine Sitzung gilt so lange als „läuft noch", wie das Aktivierungsdatum
        # gesetzt ist (Reset erfolgt zentral in _evaluate nach dem Sonnenaufgang
        # des Folgetags). Damit bleibt Hysterese auch bei Oszillation über
        # Mitternacht innerhalb derselben Abend-Sitzung wirksam.
        is_reactivation = (
            self._discharge_activated_date is not None
            and self._last_eval_zustand != STATE_ABEND_ENTLADUNG
        )

        # Check time — PeakShare or fixed start time
        # Pre-init guards so neither branch can leave them unbound (past bug: UnboundLocalError)
        past_midnight_in_window = False
        past_midnight = False
        peakshare_plan = None
        # Konfigurierte Mindeststart-Uhrzeit als Datetime auflösen — gilt in
        # beiden Modi als Untergrenze für den Start.
        # Sonderfall: Wenn die Startzeit in den frühen Morgenstunden liegt
        # (< 12:00) und wir aktuell nachmittags sind, zeigt sie auf MORGEN —
        # die Sitzung beginnt also erst nach Mitternacht (z.B. discharge
        # ab 01:00 → bei now 18:00 ist gemeint: morgen 01:00).
        discharge_start_today = snap.now.replace(
            hour=self._discharge_start_h,
            minute=self._discharge_start_m,
            second=0,
            microsecond=0,
        )
        if self._discharge_start_h < 12 and snap.now.hour >= 12:
            discharge_start_resolved = discharge_start_today + timedelta(days=1)
        else:
            discharge_start_resolved = discharge_start_today

        if self._enable_peakshare and self._peakshare is not None:
            # PeakShare mode: compute discharge window based on community demand
            available_kwh = (snap.battery_soc - min_soc) / 100 * snap.battery_capacity_kwh
            if available_kwh > 0:
                peakshare_plan = self._peakshare.get_discharge_plan(
                    self._peakshare_community,
                    available_kwh,
                    self._discharge_power_kw,
                    snap.sunset_today,
                    snap.now,
                    discharge_start_lower_bound=discharge_start_resolved,
                    next_sunrise=snap.sunrise,
                )

        if peakshare_plan is not None:
            plan_start, plan_end = peakshare_plan
            if snap.now < plan_start:
                blocked_by.append(REASON_PEAKSHARE_BEFORE_WINDOW)
            elif snap.now >= plan_end:
                blocked_by.append(REASON_PEAKSHARE_WINDOW_EXPIRED)
            else:
                # Fenster aktiv → Pass-Grund
                passing.append(REASON_PEAKSHARE_WINDOW_ACTIVE)
            # Hard-Cutoff dynamisch: min(04:00, sunrise − 1h).
            cutoff = compute_hard_cutoff(snap.now, snap.sunrise)
            past_midnight = snap.now.hour < 12 and plan_start.hour >= 12
            if past_midnight and snap.now >= cutoff:
                blocked_by.append(REASON_HARD_CUTOFF_AFTER_4AM)
        else:
            # Fixed start time check (fallback oder PeakShare disabled)
            discharge_start = discharge_start_resolved
            # Past midnight: discharge_start points to a future moment, but we
            # are already in the discharge window that started the prior evening.
            # Beispiel: start=21:00, now=03:00 (gleicher Kalendertag) — `now <
            # start` und sunrise ist nah. Bei einem Morgen-Start (z.B. 01:00,
            # via discharge_start_resolved auf morgen verschoben) trifft `now
            # < start` aber AUCH um 18:00 abends zu — daher zusätzlich auf
            # echte Morgen-Stunden klemmen (now.hour < 12).
            past_midnight_in_window = (
                snap.now < discharge_start
                and snap.now.hour < 12
                and snap.sunrise is not None
                and snap.now < snap.sunrise
                and (snap.sunrise - snap.now).total_seconds() < 12 * 3600
            )
            if snap.now < discharge_start and not past_midnight_in_window:
                blocked_by.append(REASON_BEFORE_DISCHARGE_START)

            # Hard-Cutoff dynamisch — siehe compute_hard_cutoff.
            cutoff = compute_hard_cutoff(snap.now, snap.sunrise)
            if past_midnight_in_window and snap.now >= cutoff:
                blocked_by.append(REASON_HARD_CUTOFF_AFTER_4AM)

        # Hysteresis: SOC-Schwelle anheben falls schon einmal aktiv und deaktiviert.
        # REASON_HYSTERESIS_STRICT wird nur gemeinsam mit dem SOC-Resultat gesetzt
        # (begleitende Modifier-Markierung — nicht eigenständig blockierend).
        effective_min_soc = min_soc + 5 if is_reactivation else min_soc

        if snap.battery_soc <= effective_min_soc:
            if is_reactivation:
                blocked_by.append(REASON_HYSTERESIS_STRICT)
            blocked_by.append(REASON_SOC_BELOW_MIN)
        else:
            if is_reactivation:
                passing.append(REASON_HYSTERESIS_STRICT)
            passing.append(REASON_SOC_ABOVE_MIN)

        # Tomorrow surplus check (D-09)
        # Tomorrow demand = daylight consumption (mit Safety-Buffer) + battery charge needed
        # Nur Tageslicht-Verbrauch konkurriert mit PV; Abendverbrauch deckt die geladene Batterie.
        consumption_with_buffer = snap.consumption_tomorrow_daylight_kwh * (1 + self._safety_buffer_pct / 100)
        battery_charge_needed = (
            (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
        )
        tomorrow_demand = consumption_with_buffer + battery_charge_needed
        pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0

        if pv_tomorrow < tomorrow_demand:
            blocked_by.append(REASON_TOMORROW_PV_INSUFFICIENT)
        else:
            passing.append(REASON_TOMORROW_PV_SUFFICIENT)

        # Grid import watchdog (nur SolarEdge): falls Entladung heute abgebrochen wurde
        if self._is_solaredge:
            if self._discharge_aborted_date == today_str:
                blocked_by.append(REASON_DISCHARGE_ABORTED_TODAY)

        # Mutual-Exclusion-Invariante: bei Pass werden passing-Keys reasons,
        # bei Block bleibt reasons leer und blocked_by führt die Liste.
        if not blocked_by:
            return (True, min_soc, passing, [], is_reactivation)
        return (False, min_soc, [], blocked_by, is_reactivation)

    def _evaluate(self, snap: Snapshot, mode: str) -> Decision:
        """Evaluate snapshot and produce a Decision."""
        # SOC-Sensor nicht verfügbar → Normalbetrieb erzwingen, statt mit
        # Phantom-0%-Werten zu rechnen (würde min_soc_dyn auf 100% kippen
        # und falsche soc_pct=0-Snapshots ans Backend senden).
        if snap.battery_soc is None:
            self._last_eval_zustand = STATE_NORMAL
            return Decision(
                timestamp=snap.now.isoformat(),
                zustand=STATE_NORMAL,
                nächste_aktion="Normalbetrieb (SOC-Sensor nicht verfügbar)",
                ausführung=(mode == MODE_EIN),
                reasons=[REASON_BATTERY_SOC_UNAVAILABLE],
                blocked_by=[REASON_BATTERY_SOC_UNAVAILABLE],
                snapshot=snap.to_telemetry_dict(),
            )

        # Hysterese-Reset: veraltete Aktivierungsdaten verwerfen, bevor
        # _should_block_charging / _should_discharge sie auswerten.
        # - Morgen-Einspeisung läuft nur am Vormittag (kein Mitternachtsübergang),
        #   ein Datum aus einem Vortag ist daher immer veraltet.
        # - Abend-Entladung kann über Mitternacht laufen; das gespeicherte
        #   Startdatum bleibt deshalb gültig, bis der nächste Sonnenaufgang
        #   überschritten ist (= Ende der Sitzung).
        today_str = snap.now.strftime("%Y-%m-%d")
        if (
            self._morning_activated_date is not None
            and self._morning_activated_date < today_str
        ):
            self._morning_activated_date = None
        if (
            self._discharge_activated_date is not None
            and self._discharge_activated_date < today_str
            and snap.sunrise_today is not None
            and snap.now >= snap.sunrise_today
        ):
            self._discharge_activated_date = None

        # Phase 11: Pro-Slot-Hysterese-Reset (analog _discharge_activated_date).
        # Slot A (Abend-Entladung) und Slot B (Morgen-Entladung) bekommen
        # eigene Reset-Trigger. Reset NUR nach today's Sunrise — verhindert
        # Mitternachts-Reset, der Hysterese aushebeln würde (T-11-02-01).
        if (
            self._slot_a_activated_date is not None
            and self._slot_a_activated_date < today_str
            and snap.sunrise_today is not None
            and snap.now >= snap.sunrise_today
        ):
            self._slot_a_activated_date = None
        if (
            self._slot_b_activated_date is not None
            and self._slot_b_activated_date < today_str
            and snap.sunrise_today is not None
            and snap.now >= snap.sunrise_today
        ):
            self._slot_b_activated_date = None

        bedarf = self._calc_energiebedarf(snap)
        block, block_reasons_keys, block_blocked_by_keys = self._should_block_charging(snap)
        should_discharge, min_soc, dis_reasons_keys, dis_blocked_by_keys, hysteresis_active = (
            self._should_discharge(snap)
        )

        # Determine state
        if block:
            zustand = STATE_MORGEN_EINSPEISUNG
        elif should_discharge:
            zustand = STATE_ABEND_ENTLADUNG
        else:
            zustand = STATE_NORMAL

        # Phase 11: Slot-Marker aus den Discharge-Reasons ableiten (D-10).
        # Im Legacy-Pfad bleibt active_slot None (keine slot-Reasons in der Liste).
        active_slot: str | None = None
        if zustand == STATE_ABEND_ENTLADUNG:
            if REASON_SLOT_A_ACTIVE in dis_reasons_keys:
                active_slot = "A"
            elif REASON_SLOT_B_ACTIVE in dis_reasons_keys:
                active_slot = "B"

        # Aktivierungsdatum nur beim erstmaligen Aktivieren setzen — bei
        # durchgehender Sitzung (z.B. Abend-Entladung über Mitternacht)
        # bleibt das ursprüngliche Startdatum erhalten, damit der Reset
        # oben zum Sonnenaufgang sauber greift.
        if zustand == STATE_MORGEN_EINSPEISUNG:
            if self._morning_activated_date is None:
                self._morning_activated_date = today_str
        elif zustand == STATE_ABEND_ENTLADUNG:
            if self._discharge_activated_date is None:
                self._discharge_activated_date = today_str
            # Phase 11: Pro-Slot-Aktivierungsdatum + last_active_slot.
            # _last_active_slot trackt den zuletzt aktiven Slot — wird in
            # _evaluate_slot_a/b für die Reaktivierungs-Logik gelesen.
            if active_slot == "A":
                if self._slot_a_activated_date is None:
                    self._slot_a_activated_date = today_str
                self._last_active_slot = "A"
            elif active_slot == "B":
                if self._slot_b_activated_date is None:
                    self._slot_b_activated_date = today_str
                self._last_active_slot = "B"
        self._last_eval_zustand = zustand

        # Determine next action text
        in_grace_period = (
            (_now() - self._startup_time).total_seconds() < STARTUP_GRACE_SECONDS
        )
        if in_grace_period:
            remaining = int(STARTUP_GRACE_SECONDS - (_now() - self._startup_time).total_seconds())
            nächste_aktion = f"Neustart — warte auf Sensordaten ({remaining}s)"
        elif zustand == STATE_MORGEN_EINSPEISUNG:
            nächste_aktion = (
                f"Morgen-Einspeisung bis "
                f"{self._morning_end_hour:02d}:{self._morning_end_min:02d}"
            )
        elif zustand == STATE_ABEND_ENTLADUNG:
            # Show PeakShare window times if available
            ps_plan = self._peakshare.get_discharge_plan(
                self._peakshare_community, 0, 0, None, snap.now
            ) if self._enable_peakshare and self._peakshare and self._peakshare._discharge_plan_date == snap.now.strftime("%Y-%m-%d") else None
            if ps_plan:
                nächste_aktion = (
                    f"Abend-Entladung {ps_plan[0].strftime('%H:%M')}-"
                    f"{ps_plan[1].strftime('%H:%M')} (PeakShare)"
                )
            else:
                nächste_aktion = (
                    f"Abend-Entladung {self._discharge_start_h:02d}:"
                    f"{self._discharge_start_m:02d}"
                )
        else:
            nächste_aktion = "Normalbetrieb"

        # Compute detailed status for both features
        morning_info = self._morning_delay_status(snap, bedarf)
        discharge_info = self._discharge_detail_status(
            snap, should_discharge, min_soc, dis_blocked_by_keys
        )

        decision = Decision(
            timestamp=snap.now.isoformat(),
            zustand=zustand,
            energiebedarf_kwh=round(bedarf, 2),
            ladung_blockiert=block,
            entladung_aktiv=(zustand == STATE_ABEND_ENTLADUNG),
            entladeleistung_kw=self._discharge_power_kw if zustand == STATE_ABEND_ENTLADUNG else 0.0,
            min_soc_berechnet=round(min_soc, 1),
            nächste_aktion=nächste_aktion,
            # Explicit: ausführung=True only for MODE_EIN, False for MODE_TEST/MODE_AUS
            ausführung=(mode == MODE_EIN),
            # Morning delay status card fields
            morning_status=morning_info["status"],
            morning_reason=morning_info["reason"],
            morning_in_window=morning_info["in_window"],
            morning_pv_today_kwh=round(morning_info["pv_today_kwh"], 1),
            morning_threshold_kwh=round(morning_info["threshold_kwh"], 1),
            morning_consumption_kwh=round(morning_info["consumption_kwh"], 1),
            morning_buffer_kwh=round(morning_info["buffer_kwh"], 1),
            morning_battery_kwh=round(morning_info["battery_kwh"], 1),
            morning_end_time=morning_info["end_time"],
            morning_sunrise_tomorrow=morning_info["sunrise_tomorrow"],
            # Discharge status card fields
            discharge_status=discharge_info["status"],
            discharge_reasons=discharge_info["reasons"],
            discharge_soc=round(snap.battery_soc, 0),
            discharge_min_soc=round(min_soc, 1),
            discharge_pv_tomorrow_kwh=round(discharge_info["pv_tomorrow_kwh"], 1),
            discharge_demand_overnight_kwh=round(discharge_info["demand_overnight_kwh"], 1),
            discharge_consumption_daylight_kwh=discharge_info["consumption_daylight_kwh"],
            discharge_safety_buffer_kwh=discharge_info["safety_buffer_kwh"],
            discharge_battery_charge_needed_kwh=discharge_info["battery_charge_needed_kwh"],
            discharge_demand_total_kwh=discharge_info["demand_total_kwh"],
            discharge_power_kw=self._discharge_power_kw,
            discharge_start_time=discharge_info["start_time"],
            discharge_hysteresis_active=hysteresis_active,
            # Phase 11: aktiver Slot ("A" | "B" | None für Legacy/Pause).
            discharge_active_slot=active_slot,
        )

        # Populate PeakShare fields if a plan was computed today
        if self._enable_peakshare and self._peakshare is not None:
            ps_plan_date = getattr(self._peakshare, "_discharge_plan_date", None)
            ps_plan = getattr(self._peakshare, "_discharge_plan", None)
            if ps_plan_date == snap.now.strftime("%Y-%m-%d") and ps_plan is not None:
                decision.discharge_peakshare_active = True
                decision.discharge_window_start = ps_plan[0].strftime("%H:%M")
                decision.discharge_window_end = ps_plan[1].strftime("%H:%M")

        # Strukturierte Diagnose (D-09): kanonische Katalog-Keys für Telemetrie.
        # Mapping je nach gewähltem Zustand:
        #   Morgen-Einspeisung → reasons = block-Pass-Keys, blocked_by = discharge-Guards
        #   Abend-Entladung    → reasons = discharge-Pass-Keys, blocked_by = block-Guards
        #   Normal             → reasons = [], blocked_by = beide Guard-Listen kombiniert
        if zustand == STATE_MORGEN_EINSPEISUNG:
            decision.reasons = list(block_reasons_keys)
            decision.blocked_by = list(dis_blocked_by_keys)
        elif zustand == STATE_ABEND_ENTLADUNG:
            decision.reasons = list(dis_reasons_keys)
            decision.blocked_by = list(block_blocked_by_keys)
        else:
            decision.reasons = []
            decision.blocked_by = list(block_blocked_by_keys) + list(dis_blocked_by_keys)

        # Lean Snapshot für State-Change-Payload (D-09).
        # Field-Namen matchen 1:1 SnapshotPayload (EEGEnergyOptimzierBackend/src/types.ts).
        readings = self._current_power_readings()
        decision.snapshot = {
            **snap.to_telemetry_dict(),
            **readings,
            "min_soc_dyn": int(round(min_soc)),
            "hysteresis": bool(hysteresis_active),
        }

        decision.markdown = self._build_markdown(snap, decision)
        return decision

    def _build_markdown(self, snap: Snapshot, decision: Decision) -> str:
        """Build Markdown status text for the decision sensor."""
        lines: list[str] = []

        lines.append(f"## Status")
        lines.append(f"{decision.zustand}")
        lines.append("")

        if decision.ladung_blockiert:
            schwelle = decision.energiebedarf_kwh * (1 + self._safety_buffer_pct / 100)
            lines.append("### Ladung blockiert")
            lines.append(
                f"- Blockiert bis: {self._morning_end_hour:02d}:{self._morning_end_min:02d}"
            )
            if snap.pv_remaining_today_kwh is not None:
                lines.append(
                    f"- PV-Prognose heute: {snap.pv_remaining_today_kwh:.1f} kWh"
                )
            lines.append(
                f"- Energiebedarf: {decision.energiebedarf_kwh:.1f} kWh "
                f"(Verbrauch SA-SU: {snap.consumption_today_daylight_kwh:.1f} + "
                f"Batterie: {decision.energiebedarf_kwh - snap.consumption_today_daylight_kwh:.1f})"
            )
            lines.append(
                f"- Schwelle inkl. Puffer: {schwelle:.1f} kWh"
            )
            lines.append("")

        if decision.entladung_aktiv:
            lines.append("### Abend-Entladung")
            lines.append(
                f"- Startzeit: {self._discharge_start_h:02d}:{self._discharge_start_m:02d}"
            )
            lines.append(f"- Leistung: {decision.entladeleistung_kw:.1f} kW")
            lines.append(f"- Ziel-SOC: {decision.min_soc_berechnet:.0f}%")
            if snap.pv_tomorrow_kwh is not None:
                lines.append(
                    f"- PV-Prognose morgen: {snap.pv_tomorrow_kwh:.1f} kWh"
                )
            lines.append(
                f"- Verbrauchsprognose morgen: {snap.consumption_tomorrow_kwh:.1f} kWh"
            )
            lines.append("")

        if not decision.ladung_blockiert and not decision.entladung_aktiv:
            lines.append("### Normalbetrieb")
            lines.append(f"- Energiebedarf: {decision.energiebedarf_kwh:.1f} kWh")
            soc_str = f"{snap.battery_soc:.0f}%" if snap.battery_soc is not None else "—"
            lines.append(f"- Batterie SOC: {soc_str}")
            lines.append("")

        # Diagnose-Sektionen aus dem Reasons-Katalog (D-38): kanonische Keys
        # werden via REASON_LABELS_DE in deutsche Texte übersetzt.
        if decision.reasons:
            lines.append("### Diagnose (Gründe)")
            for key in decision.reasons:
                lines.append(f"- {REASON_LABELS_DE.get(key, key)}")
            lines.append("")
        if decision.blocked_by:
            lines.append("### Diagnose (blockiert durch)")
            for key in decision.blocked_by:
                lines.append(f"- {REASON_LABELS_DE.get(key, key)}")
            lines.append("")

        lines.append(f"**Modus:** {'Ausführung' if decision.ausführung else 'Berechnung'}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(self, decision: Decision, snap: Snapshot) -> None:
        """Execute inverter commands based on decision.

        Only called when decision.ausführung is True.
        Deduplicates: only sends commands on state change, except:
        - SolaX: resends every cycle (commands expire via autorepeat)
        - SolarEdge: sets command_timeout high to avoid flash wear
        """
        # Startup grace period: skip inverter commands while sensors settle
        elapsed = (_now() - self._startup_time).total_seconds()
        if elapsed < STARTUP_GRACE_SECONDS:
            remaining = int(STARTUP_GRACE_SECONDS - elapsed)
            if not self._grace_period_logged:
                _LOGGER.info(
                    "Startup Grace Period aktiv — keine Inverter-Befehle für %ds",
                    remaining,
                )
                self._grace_period_logged = True
            return

        is_active_state = decision.zustand in (STATE_MORGEN_EINSPEISUNG, STATE_ABEND_ENTLADUNG)
        inv_type = self._config.get("inverter_type", "")
        needs_repeat = inv_type == "solax_gen4" and is_active_state

        if decision.zustand == self._prev_zustand and not needs_repeat:
            return

        try:
            if decision.zustand == STATE_MORGEN_EINSPEISUNG:
                await self._inverter.async_set_charge_limit(0)
            elif decision.zustand == STATE_ABEND_ENTLADUNG:
                await self._inverter.async_set_discharge(
                    decision.entladeleistung_kw,
                    target_soc=decision.min_soc_berechnet,
                )
            else:
                await self._inverter.async_stop_forcible()

            self._prev_zustand = decision.zustand
        except Exception as exc:
            _LOGGER.exception("Inverter command failed for state %s", decision.zustand)
            # W-4 — Telemetrie-Hook für Inverter-Schreibfehler (D-16). Action je
            # nach Zielzustand: charge / discharge / stop. Callback ist defensiv
            # gewrappt — eine Exception darin darf den Optimizer-Zyklus nicht
            # zerlegen.
            if self._failure_callback is not None:
                if decision.zustand == STATE_MORGEN_EINSPEISUNG:
                    action = "charge"
                elif decision.zustand == STATE_ABEND_ENTLADUNG:
                    action = "discharge"
                else:
                    action = "stop"
                try:
                    self._failure_callback("inverter_write", exc, action)
                except Exception:  # pragma: no cover — defensive
                    _LOGGER.exception("Inverter failure callback raised")

    def _check_grid_import_watchdog(self, decision: Decision, snap: Snapshot) -> Decision:
        """Check for sustained grid import during discharge and abort if needed.

        SolarEdge only: "Discharge to Maximize Export" pushes power to grid
        but doesn't cover household demand — the house draws from grid
        simultaneously. If grid import exceeds 1 kW for more than 5
        consecutive minutes, the discharge is aborted for the rest of the day.

        Huawei/SolaX cover household demand first, so this issue doesn't apply.

        Returns the (possibly modified) decision.
        """
        now = snap.now

        # Only monitor SolarEdge during active discharge
        if not self._is_solaredge or decision.zustand != STATE_ABEND_ENTLADUNG:
            self._grid_import_since = None
            return decision

        # Read grid power (normalized: positive = export, negative = import)
        grid_raw = _read_float(self._hass, self._grid_sensor_id)
        if grid_raw is None:
            self._grid_import_since = None
            return decision
        grid_kw = grid_raw * self._grid_sign
        # _read_float returns raw value; normalize with _grid_sign
        # grid_kw > 0 = export, < 0 = import
        # Check unit — if sensor reports W, convert
        state = self._hass.states.get(self._grid_sensor_id)
        if state:
            unit = (state.attributes.get("unit_of_measurement") or "").strip()
            if unit == "W":
                grid_kw = grid_kw / 1000.0

        # grid_kw < -1.0 means importing > 1 kW from grid
        if grid_kw < -1.0:
            if self._grid_import_since is None:
                self._grid_import_since = now
                _LOGGER.warning(
                    "Netzbezug-Watchdog: Netzbezug %.1f kW während Entladung erkannt, Timer gestartet",
                    abs(grid_kw),
                )
            elif (now - self._grid_import_since).total_seconds() >= 300:
                # 5 minutes of sustained grid import — abort discharge for today
                self._discharge_aborted_date = now.strftime("%Y-%m-%d")
                self._grid_import_since = None
                _LOGGER.error(
                    "Netzbezug-Watchdog: Netzbezug > 1 kW seit > 5 Min — "
                    "Entladung für heute (%s) abgebrochen",
                    self._discharge_aborted_date,
                )
                # Override decision to Normal
                decision.zustand = STATE_NORMAL
                decision.entladung_aktiv = False
                decision.entladeleistung_kw = 0.0
                decision.nächste_aktion = "Entladung abgebrochen (Netzbezug)"
                decision.discharge_reasons.append(
                    "Entladung heute wegen Netzbezug > 1 kW für > 5 Min abgebrochen"
                )
                # Katalog-Key in blocked_by spiegeln, damit der Activity-Log-Check
                # in __init__.py (REASON_DISCHARGE_ABORTED_TODAY in decision.blocked_by)
                # auch auf dem Watchdog-Zyklus selbst greift (D-09).
                if REASON_DISCHARGE_ABORTED_TODAY not in decision.blocked_by:
                    decision.blocked_by.append(REASON_DISCHARGE_ABORTED_TODAY)
                # Da Zustand auf Normal gewechselt hat: passing-reasons löschen.
                decision.reasons = []
        else:
            # Grid import below threshold — reset timer
            if self._grid_import_since is not None:
                _LOGGER.info("Netzbezug-Watchdog: Netzbezug unter 1 kW, Timer zurückgesetzt")
            self._grid_import_since = None

        return decision

    async def async_run_cycle(self, mode: str) -> Decision:
        """Run one optimizer cycle.

        1. Gather snapshot
        2. Evaluate -> Decision
        3. Grid import watchdog (may override decision)
        4. Execute (if mode == Ein)
        5. Return Decision
        """
        try:
            # Pre-fetch PeakShare data (async) before sync evaluation
            if self._enable_peakshare and self._peakshare is not None:
                await self._peakshare.async_fetch()

            snap = self._gather_snapshot()
            decision = self._evaluate(snap, mode)

            # Grid import watchdog — may abort discharge
            if mode == MODE_EIN:
                decision = self._check_grid_import_watchdog(decision, snap)

            if mode == MODE_EIN:
                await self._execute(decision, snap)
            elif mode == MODE_TEST:
                _LOGGER.debug("Dry-run: %s (keine Ausführung)", decision.zustand)

            self._last_decision = decision
            return decision

        except Exception:
            _LOGGER.exception("Optimizer cycle failed")
            fallback = Decision(
                timestamp=_now().isoformat(),
                zustand=STATE_NORMAL,
                nächste_aktion="Fehler im Optimizer-Zyklus",
            )
            self._last_decision = fallback
            return fallback

    @property
    def last_decision(self) -> Decision | None:
        """Return the last computed decision."""
        return self._last_decision
