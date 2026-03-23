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
    CONF_ENABLE_MORNING_DELAY,
    CONF_ENABLE_NIGHT_DISCHARGE,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_SAFETY_BUFFER_PCT,
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_SAFETY_BUFFER_PCT,
    MODE_EIN,
    MODE_TEST,
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
    consumption_to_sunset_kwh: float = 0.0
    consumption_tomorrow_kwh: float = 0.0
    consumption_overnight_kwh: float = 0.0
    consumption_today_daylight_kwh: float = 0.0    # SA -> SU today
    consumption_tomorrow_daylight_kwh: float = 0.0  # SA -> SU tomorrow
    sunrise: datetime | None = None
    sunset: datetime | None = None


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
    naechste_aktion: str = ""
    markdown: str = ""
    ausfuehrung: bool = False
    block_reasons: list[str] = field(default_factory=list)

    # Morning delay status card fields
    morning_status: str = "deaktiviert"
    morning_reason: str = ""
    morning_in_window: bool = False
    morning_pv_today_kwh: float = 0.0
    morning_threshold_kwh: float = 0.0
    morning_end_time: str = ""
    morning_sunrise_tomorrow: str = ""

    # Discharge status card fields
    discharge_status: str = "deaktiviert"
    discharge_reasons: list[str] = field(default_factory=list)
    discharge_soc: float = 0.0
    discharge_min_soc: float = 0.0
    discharge_pv_tomorrow_kwh: float = 0.0
    discharge_demand_tomorrow_kwh: float = 0.0
    discharge_power_kw: float = 0.0
    discharge_start_time: str = ""


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
        self._enable_morning_delay = config.get(CONF_ENABLE_MORNING_DELAY, True)
        self._enable_night_discharge = config.get(CONF_ENABLE_NIGHT_DISCHARGE, True)

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

        # Consumption until sunset (for morning delay decision)
        consumption_to_sunset = 0.0
        if sunset is not None and sunset > now:
            consumption_to_sunset = self._coordinator.calculate_period(
                now, sunset
            ).get("verbrauch_kwh", 0.0)

        # Overnight consumption for discharge min-SOC calculation
        # Before discharge start: from discharge_start to sunrise + 1h
        # After discharge start: from now to sunrise + 1h
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

        return Snapshot(
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
            "end_time": end_time_str,
            "sunrise_tomorrow": "",
        }

        if not self._enable_morning_delay:
            return result

        threshold = bedarf * (1 + self._safety_buffer_pct / 100)
        pv_today = snap.pv_remaining_today_kwh if snap.pv_remaining_today_kwh is not None else 0.0
        result["pv_today_kwh"] = pv_today
        result["threshold_kwh"] = threshold

        # Check if in morning window
        in_window = False
        if snap.sunrise is not None:
            window_start = snap.sunrise - timedelta(hours=1)
            morning_end = snap.now.replace(
                hour=self._morning_end_hour,
                minute=self._morning_end_min,
                second=0,
                microsecond=0,
            )
            in_window = window_start <= snap.now <= morning_end
        result["in_window"] = in_window

        # Sunrise display for tomorrow
        if snap.sunrise is not None:
            result["sunrise_tomorrow"] = f"~{snap.sunrise.strftime('%H:%M')}"

        if in_window:
            if pv_today > threshold:
                result["status"] = "aktiv"
                result["reason"] = f"Ladung blockiert bis {end_time_str}"
            else:
                result["status"] = "nicht_aktiv"
                result["reason"] = "PV reicht nicht fuer Bedarf + Puffer"
        else:
            # Outside window: check if tomorrow's conditions would trigger
            pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0
            # Estimate tomorrow's demand: consumption + missing battery energy
            missing_battery_est = 0.0
            if snap.battery_capacity_kwh > 0:
                missing_battery_est = (100 - self._min_soc) / 100 * snap.battery_capacity_kwh
            tomorrow_demand = snap.consumption_tomorrow_daylight_kwh + missing_battery_est
            tomorrow_threshold = tomorrow_demand * (1 + self._safety_buffer_pct / 100)

            # Show tomorrow's values in the card (not today's remaining)
            result["pv_today_kwh"] = pv_tomorrow
            result["threshold_kwh"] = tomorrow_threshold

            if pv_tomorrow > tomorrow_threshold:
                sunrise_str = result["sunrise_tomorrow"] or "Sonnenaufgang"
                result["status"] = "morgen_erwartet"
                result["reason"] = f"Morgen ab {sunrise_str}"
            else:
                result["status"] = "morgen_nicht_erwartet"
                result["reason"] = "PV Prognose zu gering"

        return result

    def _discharge_detail_status(
        self, snap: Snapshot, should_discharge: bool, min_soc: float, discharge_reasons: list[str]
    ) -> dict:
        """Compute detailed discharge status for the status card.

        Returns a dict with: status, reasons, soc, min_soc, pv_tomorrow_kwh,
        demand_tomorrow_kwh, power_kw, start_time.
        """
        start_time_str = f"{self._discharge_start_h:02d}:{self._discharge_start_m:02d}"
        pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0
        battery_charge_needed = (100 - self._min_soc) / 100 * snap.battery_capacity_kwh
        tomorrow_demand = snap.consumption_tomorrow_kwh + battery_charge_needed

        result: dict = {
            "status": "deaktiviert",
            "reasons": [],
            "soc": snap.battery_soc,
            "min_soc": min_soc,
            "pv_tomorrow_kwh": pv_tomorrow,
            "demand_tomorrow_kwh": tomorrow_demand,
            "power_kw": self._discharge_power_kw,
            "start_time": start_time_str,
        }

        if not self._enable_night_discharge:
            return result

        if should_discharge:
            result["status"] = "aktiv"
            return result

        # Not discharging: separate time-reason from condition-reasons
        time_reasons = [r for r in discharge_reasons if "Startzeit" in r]
        condition_reasons = [r for r in discharge_reasons if "Startzeit" not in r]

        if not condition_reasons and time_reasons:
            # Only time is blocking -> planned
            result["status"] = "geplant"
        else:
            # Condition failures -> not planned
            result["status"] = "nicht_geplant"
            result["reasons"] = condition_reasons

        return result

    def _calc_energiebedarf(self, snap: Snapshot) -> float:
        """Calculate total energy demand: daylight consumption (SA->SU) + missing battery energy.

        This represents everything that must be covered by today's PV:
        - Household consumption during daylight hours (sunrise to sunset)
        - Energy needed to fully charge the battery
        """
        # Daylight consumption (SA -> SU) for morning delay decision
        consumption = snap.consumption_today_daylight_kwh

        # Missing battery energy (kWh to reach 100%)
        missing_battery = 0.0
        if snap.battery_capacity_kwh > 0:
            missing_battery = (
                (100 - snap.battery_soc) / 100 * snap.battery_capacity_kwh
            )

        return consumption + missing_battery

    def _should_block_charging(self, snap: Snapshot) -> bool:
        """Determine if morning charge blocking should be active.

        Conditions (all must be true):
        - Feature enabled in config
        - Sunrise known
        - Current time within window (sunrise - 1h to morning_end_time)
        - PV forecast today > energy demand * (1 + safety_buffer)

        Energy demand = consumption to sunset + missing battery energy.
        """
        if not self._enable_morning_delay:
            return False
        if snap.sunrise is None:
            return False

        window_start = snap.sunrise - timedelta(hours=1)
        morning_end = snap.now.replace(
            hour=self._morning_end_hour,
            minute=self._morning_end_min,
            second=0,
            microsecond=0,
        )
        if not (window_start <= snap.now <= morning_end):
            return False

        pv_today = snap.pv_remaining_today_kwh
        if pv_today is None or pv_today <= 0:
            return False

        bedarf = self._calc_energiebedarf(snap)
        schwelle = bedarf * (1 + self._safety_buffer_pct / 100)

        return pv_today > schwelle

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
        return float(self._min_soc + math.ceil(soc_pct))

    def _should_discharge(
        self, snap: Snapshot
    ) -> tuple[bool, float, list[str]]:
        """Determine if evening discharge should be active.

        Per D-05 to D-09:
        - Feature must be enabled in config
        - Time >= discharge_start
        - SOC > calculated min_soc
        - PV tomorrow >= tomorrow_demand (including battery charge needs)
        """
        if not self._enable_night_discharge:
            return (False, float(self._min_soc), ["Nachteinspeisung deaktiviert"])
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
        bedarf = self._calc_energiebedarf(snap)
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

        # Compute detailed status for both features
        morning_info = self._morning_delay_status(snap, bedarf)
        discharge_info = self._discharge_detail_status(
            snap, should_discharge, min_soc, discharge_reasons
        )

        decision = Decision(
            timestamp=snap.now.isoformat(),
            zustand=zustand,
            energiebedarf_kwh=round(bedarf, 2),
            ladung_blockiert=block,
            entladung_aktiv=(zustand == STATE_ABEND_ENTLADUNG),
            entladeleistung_kw=self._discharge_power_kw if zustand == STATE_ABEND_ENTLADUNG else 0.0,
            min_soc_berechnet=round(min_soc, 1),
            naechste_aktion=naechste_aktion,
            # Explicit: ausfuehrung=True only for MODE_EIN, False for MODE_TEST/MODE_AUS
            ausfuehrung=(mode == MODE_EIN),
            block_reasons=discharge_reasons if zustand != STATE_ABEND_ENTLADUNG else [],
            # Morning delay status card fields
            morning_status=morning_info["status"],
            morning_reason=morning_info["reason"],
            morning_in_window=morning_info["in_window"],
            morning_pv_today_kwh=round(morning_info["pv_today_kwh"], 1),
            morning_threshold_kwh=round(morning_info["threshold_kwh"], 1),
            morning_end_time=morning_info["end_time"],
            morning_sunrise_tomorrow=morning_info["sunrise_tomorrow"],
            # Discharge status card fields
            discharge_status=discharge_info["status"],
            discharge_reasons=discharge_info["reasons"],
            discharge_soc=round(snap.battery_soc, 0),
            discharge_min_soc=round(min_soc, 1),
            discharge_pv_tomorrow_kwh=round(discharge_info["pv_tomorrow_kwh"], 1),
            discharge_demand_tomorrow_kwh=round(discharge_info["demand_tomorrow_kwh"], 1),
            discharge_power_kw=self._discharge_power_kw,
            discharge_start_time=discharge_info["start_time"],
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
            schwelle = decision.energiebedarf_kwh * (1 + self._safety_buffer_pct / 100)
            lines.append("### Ladung blockiert")
            lines.append(
                f"- Blockiert bis: {self._morning_end_hour:02d}:{self._morning_end_min:02d}"
            )
            if snap.pv_remaining_today_kwh is not None:
                lines.append(
                    f"- PV Prognose heute: {snap.pv_remaining_today_kwh:.1f} kWh"
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
                    f"- PV Prognose morgen: {snap.pv_tomorrow_kwh:.1f} kWh"
                )
            lines.append(
                f"- Verbrauchsprognose morgen: {snap.consumption_tomorrow_kwh:.1f} kWh"
            )
            lines.append("")

        if not decision.ladung_blockiert and not decision.entladung_aktiv:
            lines.append("### Normalbetrieb")
            lines.append(f"- Energiebedarf: {decision.energiebedarf_kwh:.1f} kWh")
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
            elif mode == MODE_TEST:
                _LOGGER.debug("Dry-run: %s (keine Ausfuehrung)", decision.zustand)

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
