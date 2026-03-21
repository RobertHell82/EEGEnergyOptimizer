"""EEG Optimizer decision engine.

Core intelligence: decides when to block battery charging (morning EEG feed-in)
and when to discharge (evening EEG feed-in) based on PV forecasts, consumption
history, and battery state.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_DISCHARGE_POWER_KW,
    CONF_DISCHARGE_START_TIME,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_SAFETY_BUFFER_PCT,
    CONF_UEBERSCHUSS_SCHWELLE,
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_SAFETY_BUFFER_PCT,
    DEFAULT_UEBERSCHUSS_SCHWELLE,
    MODE_EIN,
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

# Timezone utilities
try:
    from homeassistant.util import dt as dt_util

    _now = dt_util.now
except ImportError:
    _now = lambda: datetime.now(tz=timezone.utc)  # noqa: E731


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


@dataclass
class Snapshot:
    """Immutable snapshot of all inputs for one optimizer cycle."""

    now: datetime
    battery_soc: float = 0.0
    battery_capacity_kwh: float = 0.0
    pv_remaining_today_kwh: float | None = None
    pv_tomorrow_kwh: float | None = None
    consumption_today_kwh: float = 0.0
    consumption_tomorrow_kwh: float = 0.0
    consumption_to_sunrise_kwh: float = 0.0
    sunrise: datetime | None = None
    sunset: datetime | None = None


@dataclass
class Decision:
    """Result of one optimizer evaluation cycle."""

    timestamp: str = ""
    zustand: str = "Normal"
    ueberschuss_faktor: float = 0.0
    ladung_blockiert: bool = False
    entladung_aktiv: bool = False
    entladeleistung_kw: float = 0.0
    min_soc_berechnet: float = 0.0
    naechste_aktion: str = ""
    markdown: str = ""
    ausfuehrung: bool = False
    block_reasons: list[str] = field(default_factory=list)


class EEGOptimizer:
    """EEG-optimized battery management decision engine."""

    def __init__(
        self,
        hass: Any,
        config: dict,
        inverter: Any,
        coordinator: Any,
        provider: Any,
    ) -> None:
        self._hass = hass
        self._config = config
        self._inverter = inverter
        self._coordinator = coordinator
        self._provider = provider

        # Config values
        self._ueberschuss_schwelle = config.get(
            CONF_UEBERSCHUSS_SCHWELLE, DEFAULT_UEBERSCHUSS_SCHWELLE
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
        self._min_soc = config.get(CONF_MIN_SOC, DEFAULT_MIN_SOC)
        self._safety_buffer_pct = config.get(
            CONF_SAFETY_BUFFER_PCT, DEFAULT_SAFETY_BUFFER_PCT
        )

        # Inverter deduplication
        self._prev_zustand: str | None = None
        self._last_decision: Decision | None = None

    # ------------------------------------------------------------------
    # Snapshot gathering
    # ------------------------------------------------------------------

    def _gather_snapshot(self) -> Snapshot:
        """Read all inputs and build an immutable Snapshot."""
        now = _now()

        # Battery SOC
        soc_id = self._config.get(CONF_BATTERY_SOC_SENSOR, "")
        battery_soc = _read_float(self._hass, soc_id) if soc_id else 0.0
        if battery_soc is None:
            battery_soc = 0.0

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

        # Overnight consumption (now to sunrise)
        consumption_to_sunrise = 0.0
        if sunrise is not None and sunrise > now:
            consumption_to_sunrise = self._coordinator.calculate_period(
                now, sunrise
            ).get("verbrauch_kwh", 0.0)

        return Snapshot(
            now=now,
            battery_soc=battery_soc,
            battery_capacity_kwh=capacity_kwh,
            pv_remaining_today_kwh=pv_remaining,
            pv_tomorrow_kwh=pv_tomorrow,
            consumption_today_kwh=consumption_today,
            consumption_tomorrow_kwh=consumption_tomorrow,
            consumption_to_sunrise_kwh=consumption_to_sunrise,
            sunrise=sunrise,
            sunset=sunset,
        )

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
                sunrise = datetime.fromisoformat(str(next_rising))
            except (ValueError, TypeError):
                pass

        if next_setting is not None:
            try:
                sunset = datetime.fromisoformat(str(next_setting))
            except (ValueError, TypeError):
                pass

        return sunrise, sunset

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    def _calc_ueberschuss_faktor(self, snap: Snapshot) -> float:
        """Calculate surplus factor: PV remaining / consumption today."""
        if snap.pv_remaining_today_kwh is None or snap.pv_remaining_today_kwh <= 0:
            return 0.0
        if snap.consumption_today_kwh <= 0:
            return 99.0
        return snap.pv_remaining_today_kwh / snap.consumption_today_kwh

    def _should_block_charging(self, snap: Snapshot) -> bool:
        """Determine if morning charge blocking should be active.

        Per D-01 to D-04:
        - Only on surplus days (factor >= threshold)
        - Time window: sunrise - 1h to morning_end_time
        """
        if snap.sunrise is None:
            return False

        faktor = self._calc_ueberschuss_faktor(snap)
        if faktor < self._ueberschuss_schwelle:
            return False

        window_start = snap.sunrise - timedelta(hours=1)
        morning_end = snap.now.replace(
            hour=self._morning_end_hour,
            minute=self._morning_end_min,
            second=0,
            microsecond=0,
        )

        return window_start <= snap.now <= morning_end

    def _calc_min_soc(self, snap: Snapshot) -> float:
        """Calculate dynamic minimum SOC for discharge.

        Formula: base_min_soc + ceil((overnight_kwh * (1 + buffer%) / capacity) * 100)
        """
        if snap.battery_capacity_kwh <= 0:
            return float(self._min_soc)

        needed_kwh = snap.consumption_to_sunrise_kwh * (
            1 + self._safety_buffer_pct / 100
        )
        soc_pct = needed_kwh / snap.battery_capacity_kwh * 100
        return float(self._min_soc + math.ceil(soc_pct))

    def _should_discharge(
        self, snap: Snapshot
    ) -> tuple[bool, float, list[str]]:
        """Determine if evening discharge should be active.

        Per D-05 to D-09:
        - Time >= discharge_start
        - SOC > calculated min_soc
        - PV tomorrow >= tomorrow_demand (including battery charge needs)
        """
        min_soc = self._calc_min_soc(snap)
        reasons: list[str] = []

        # Check time
        discharge_start = snap.now.replace(
            hour=self._discharge_start_h,
            minute=self._discharge_start_m,
            second=0,
            microsecond=0,
        )
        if snap.now < discharge_start:
            reasons.append(f"Startzeit {self._discharge_start_h:02d}:{self._discharge_start_m:02d} noch nicht erreicht")

        # Check SOC
        if snap.battery_soc <= min_soc:
            reasons.append(f"SOC {snap.battery_soc:.0f}% <= Min-SOC {min_soc:.0f}%")

        # Check tomorrow surplus (D-09)
        # Tomorrow demand = consumption + battery charge needed
        battery_charge_needed = (
            (100 - self._min_soc) / 100 * snap.battery_capacity_kwh
        )
        tomorrow_demand = snap.consumption_tomorrow_kwh + battery_charge_needed
        pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0

        if pv_tomorrow < tomorrow_demand:
            reasons.append(
                f"PV-Prognose morgen ({pv_tomorrow:.1f} kWh) < Bedarf ({tomorrow_demand:.1f} kWh)"
            )

        return (len(reasons) == 0, min_soc, reasons)

    def _evaluate(self, snap: Snapshot, mode: str) -> Decision:
        """Evaluate snapshot and produce a Decision."""
        faktor = self._calc_ueberschuss_faktor(snap)
        block = self._should_block_charging(snap)
        should_discharge, min_soc, discharge_reasons = self._should_discharge(snap)

        # Determine state
        if block:
            zustand = STATE_MORGEN_EINSPEISUNG
        elif should_discharge:
            zustand = STATE_ABEND_ENTLADUNG
        else:
            zustand = STATE_NORMAL

        # Determine next action text
        if zustand == STATE_MORGEN_EINSPEISUNG:
            naechste_aktion = (
                f"Morgen-Einspeisung bis "
                f"{self._morning_end_hour:02d}:{self._morning_end_min:02d}"
            )
        elif zustand == STATE_ABEND_ENTLADUNG:
            naechste_aktion = (
                f"Abend-Entladung {self._discharge_start_h:02d}:"
                f"{self._discharge_start_m:02d}"
            )
        else:
            naechste_aktion = "Normalbetrieb"

        decision = Decision(
            timestamp=snap.now.isoformat(),
            zustand=zustand,
            ueberschuss_faktor=round(faktor, 2),
            ladung_blockiert=block,
            entladung_aktiv=(zustand == STATE_ABEND_ENTLADUNG),
            entladeleistung_kw=self._discharge_power_kw if zustand == STATE_ABEND_ENTLADUNG else 0.0,
            min_soc_berechnet=round(min_soc, 1),
            naechste_aktion=naechste_aktion,
            ausfuehrung=(mode == MODE_EIN),
            block_reasons=discharge_reasons if zustand != STATE_ABEND_ENTLADUNG else [],
        )

        decision.markdown = self._build_markdown(snap, decision)
        return decision

    def _build_markdown(self, snap: Snapshot, decision: Decision) -> str:
        """Build Markdown status text for the decision sensor."""
        lines: list[str] = []

        lines.append(f"## Status")
        lines.append(f"{decision.zustand}")
        lines.append("")

        if decision.ladung_blockiert:
            lines.append("### Ladung blockiert")
            lines.append(
                f"- Blockiert bis: {self._morning_end_hour:02d}:{self._morning_end_min:02d}"
            )
            if snap.pv_remaining_today_kwh is not None:
                lines.append(
                    f"- PV Prognose heute: {snap.pv_remaining_today_kwh:.1f} kWh"
                )
            lines.append(
                f"- Verbrauchsprognose heute: {snap.consumption_today_kwh:.1f} kWh"
            )
            lines.append(
                f"- Ueberschuss-Faktor: {decision.ueberschuss_faktor:.2f}"
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
                    f"- PV Prognose morgen: {snap.pv_tomorrow_kwh:.1f} kWh"
                )
            lines.append(
                f"- Verbrauchsprognose morgen: {snap.consumption_tomorrow_kwh:.1f} kWh"
            )
            lines.append("")

        if not decision.ladung_blockiert and not decision.entladung_aktiv:
            lines.append("### Normalbetrieb")
            lines.append(f"- Ueberschuss-Faktor: {decision.ueberschuss_faktor:.2f}")
            lines.append(f"- Batterie SOC: {snap.battery_soc:.0f}%")
            lines.append("")

        lines.append(f"**Modus:** {'Ausfuehrung' if decision.ausfuehrung else 'Berechnung'}")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(self, decision: Decision, snap: Snapshot) -> None:
        """Execute inverter commands based on decision.

        Only called when decision.ausfuehrung is True.
        Deduplicates against previous state.
        """
        if decision.zustand == self._prev_zustand:
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
        except Exception:
            _LOGGER.exception("Inverter command failed for state %s", decision.zustand)

    async def async_run_cycle(self, mode: str) -> Decision:
        """Run one optimizer cycle.

        1. Gather snapshot
        2. Evaluate -> Decision
        3. Execute (if mode == Ein)
        4. Return Decision
        """
        try:
            snap = self._gather_snapshot()
            decision = self._evaluate(snap, mode)

            if mode == MODE_EIN:
                await self._execute(decision, snap)

            self._last_decision = decision
            return decision

        except Exception:
            _LOGGER.exception("Optimizer cycle failed")
            fallback = Decision(
                timestamp=_now().isoformat(),
                zustand=STATE_NORMAL,
                naechste_aktion="Fehler im Optimizer-Zyklus",
            )
            self._last_decision = fallback
            return fallback

    @property
    def last_decision(self) -> Decision | None:
        """Return the last computed decision."""
        return self._last_decision
