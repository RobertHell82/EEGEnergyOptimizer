"""
Energy optimizer – the decision engine.

Runs every 60 seconds (when enabled via switch) and determines:
- Tagesstrategie: ÜBERSCHUSS / BALANCIERT / ENGPASS / NACHT
- Heizstab mode: Aus / 1-Phasig / 3-Phasig
- Batterie Ladelimit (kW)
- Einspeisung aktiv + Wert
- Abend-Entladung

Every decision includes a human-readable justification ("Begründung").
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_EINSPEISELIMIT_KW,
    CONF_ENTLADE_STARTZEIT,
    CONF_ENTLADELEISTUNG_KW,
    CONF_FEED_IN_SENSOR,
    CONF_FRONIUS_IP,
    CONF_FRONIUS_PASSWORD,
    CONF_FRONIUS_USER,
    CONF_GUARD_DELAY_H,
    CONF_HOLZVERGASER_SENSOR,
    CONF_MIN_SOC_ENTLADUNG,
    CONF_MIN_WW_ENTLADUNG,
    CONF_PUFFER_TARGET_TEMP,
    CONF_PUFFER_TEMP_SENSOR,
    CONF_PUFFER_VOLUME_L,
    CONF_PV_POWER_SENSOR,
    CONF_SICHERHEITSPUFFER_PROZENT,
    CONF_SOLCAST_MORGEN_SENSOR,
    CONF_SOLCAST_REMAINING_SENSOR,
    CONF_UEBERSCHUSS_FAKTOR,
    DEFAULT_BATTERY_CAPACITY_SENSOR,
    DEFAULT_BATTERY_SOC_SENSOR,
    DEFAULT_EINSPEISELIMIT_KW,
    DEFAULT_ENTLADE_STARTZEIT,
    DEFAULT_ENTLADELEISTUNG_KW,
    DEFAULT_FEED_IN_SENSOR,
    DEFAULT_FRONIUS_IP,
    DEFAULT_FRONIUS_PASSWORD,
    DEFAULT_FRONIUS_USER,
    DEFAULT_GUARD_DELAY_H,
    DEFAULT_HOLZVERGASER_SENSOR,
    DEFAULT_MIN_SOC_ENTLADUNG,
    DEFAULT_MIN_WW_ENTLADUNG,
    DEFAULT_PUFFER_TARGET_TEMP,
    DEFAULT_PUFFER_TEMP_SENSOR,
    DEFAULT_PUFFER_VOLUME_L,
    DEFAULT_PV_POWER_SENSOR,
    DEFAULT_SICHERHEITSPUFFER_PROZENT,
    DEFAULT_SOLCAST_MORGEN_SENSOR,
    DEFAULT_SOLCAST_REMAINING_SENSOR,
    DEFAULT_UEBERSCHUSS_FAKTOR,
    ENTITY_EINSPEISUNG_AKTIV,
    ENTITY_EINSPEISEWERT,
    ENTITY_ENERGIEBEDARF,
    ENTITY_HEIZSTAB,
    ENTITY_LADELIMIT,
    ENTITY_PROGNOSE_MORGEN,
    ENTITY_PROGNOSE_SUNRISE,
    HEIZSTAB_1P,
    HEIZSTAB_3P,
    HEIZSTAB_AUS,
    HEIZSTAB_POWER_KW,
    STRATEGY_BALANCIERT,
    STRATEGY_ENGPASS,
    STRATEGY_INAKTIV,
    STRATEGY_NACHT,
    STRATEGY_UEBERSCHUSS,
)
from .fronius_api import FroniusAPI

_LOGGER = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
#  Data classes
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class Snapshot:
    """All sensor values at a point in time."""

    now: datetime = field(default_factory=dt_util.now)
    current_hour: int = 0

    # PV & Grid
    pv_power_w: float = 0.0
    einspeisung_w: float = 0.0

    # Battery
    battery_soc: float = 0.0
    battery_capacity_kwh: float = 0.0

    # Hot water
    ww_temp: float = 0.0
    ww_target: float = 85.0

    # Forecasts
    solcast_remaining_kwh: float = 0.0
    solcast_morgen_kwh: float = 0.0
    energy_demand_kwh: float = 0.0
    prognose_sunrise_kwh: float = 0.0

    # Tomorrow
    verbrauch_morgen_kwh: float = 0.0

    # External
    holzvergaser_active: bool = False
    sun_above_horizon: bool = True

    # Hausverbrauch
    hausverbrauch_w: float = 0.0
    heizstab_leistung_w: float = 0.0


@dataclass
class Decision:
    """Optimizer output."""

    timestamp: str = ""
    strategie: str = STRATEGY_INAKTIV
    ueberschuss_faktor: float = 0.0
    heizstab_modus: str = HEIZSTAB_3P
    ladelimit_kw: float = 4.0
    einspeisung_aktiv: bool = False
    einspeisewert_kw: float = 0.0
    entladung_aktiv: bool = False
    entladeleistung_kw: float = 0.0
    min_soc_berechnet: float = 0.0
    begruendung: str = ""
    guards_aktiv: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)

    ausfuehrung: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "ausfuehrung": self.ausfuehrung,
            "strategie": self.strategie,
            "ueberschuss_faktor": self.ueberschuss_faktor,
            "heizstab_modus": self.heizstab_modus,
            "ladelimit_kw": self.ladelimit_kw,
            "einspeisung_aktiv": self.einspeisung_aktiv,
            "einspeisewert_kw": self.einspeisewert_kw,
            "entladung_aktiv": self.entladung_aktiv,
            "entladeleistung_kw": self.entladeleistung_kw,
            "min_soc_berechnet": self.min_soc_berechnet,
            "begruendung": self.begruendung,
            "guards_aktiv": self.guards_aktiv,
            "inputs": self.inputs,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  Optimizer
# ═════════════════════════════════════════════════════════════════════════════


class EnergyOptimizer:
    """Predictive energy optimization engine."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass = hass
        self._config = config
        self.last_decision: Decision | None = None

        # Config values (read once, updated on reload)
        self._einspeiselimit = config.get(CONF_EINSPEISELIMIT_KW, DEFAULT_EINSPEISELIMIT_KW)
        self._ueberschuss_faktor = config.get(CONF_UEBERSCHUSS_FAKTOR, DEFAULT_UEBERSCHUSS_FAKTOR)
        self._min_soc = config.get(CONF_MIN_SOC_ENTLADUNG, DEFAULT_MIN_SOC_ENTLADUNG)
        self._entladeleistung = config.get(CONF_ENTLADELEISTUNG_KW, DEFAULT_ENTLADELEISTUNG_KW)
        self._sicherheitspuffer = config.get(CONF_SICHERHEITSPUFFER_PROZENT, DEFAULT_SICHERHEITSPUFFER_PROZENT)
        self._min_ww_entladung = config.get(CONF_MIN_WW_ENTLADUNG, DEFAULT_MIN_WW_ENTLADUNG)
        self._guard_delay_h = config.get(CONF_GUARD_DELAY_H, DEFAULT_GUARD_DELAY_H)
        self._ww_target = config.get(CONF_PUFFER_TARGET_TEMP, DEFAULT_PUFFER_TARGET_TEMP)
        self._puffer_volume_l = config.get(CONF_PUFFER_VOLUME_L, DEFAULT_PUFFER_VOLUME_L)

        # Parse discharge start time
        startzeit = config.get(CONF_ENTLADE_STARTZEIT, DEFAULT_ENTLADE_STARTZEIT)
        try:
            parts = startzeit.split(":")
            self._entlade_start_h = int(parts[0])
            self._entlade_start_m = int(parts[1]) if len(parts) > 1 else 0
        except (ValueError, AttributeError):
            self._entlade_start_h = 20
            self._entlade_start_m = 0

        # Fronius API (optional)
        fronius_ip = config.get(CONF_FRONIUS_IP, DEFAULT_FRONIUS_IP)
        fronius_pw = config.get(CONF_FRONIUS_PASSWORD, DEFAULT_FRONIUS_PASSWORD)
        if fronius_ip and fronius_pw:
            fronius_user = config.get(CONF_FRONIUS_USER, DEFAULT_FRONIUS_USER)
            self._fronius = FroniusAPI(fronius_ip, fronius_user, fronius_pw)
        else:
            self._fronius = None

        # Track previous values to avoid unnecessary writes
        self._prev_heizstab: str | None = None
        self._prev_ladelimit: float | None = None
        self._prev_einspeisung: bool | None = None
        self._prev_einspeisewert: float | None = None
        self._prev_entladung: bool | None = None

    # ── Main cycle ───────────────────────────────────────────────────────

    async def async_run_cycle(self, execute: bool = False) -> None:
        """One optimization cycle.

        Always calculates the decision (visible in sensor).
        Only writes to actuators when execute=True (switch is ON).
        """
        try:
            snap = self._gather_inputs()
            decision = self._evaluate(snap)
            decision.ausfuehrung = execute

            if execute:
                await self._execute(decision)
            else:
                decision.begruendung += "\n[Nur Berechnung – Optimizer-Switch ist aus]"

            self.last_decision = decision
        except Exception:
            _LOGGER.exception("Optimizer cycle failed")

    # ── Input gathering ──────────────────────────────────────────────────

    def _gather_inputs(self) -> Snapshot:
        """Read all relevant sensor states into a snapshot."""
        c = self._config
        now = dt_util.now()

        snap = Snapshot(
            now=now,
            current_hour=now.hour,
            pv_power_w=self._get_float(c.get(CONF_PV_POWER_SENSOR, DEFAULT_PV_POWER_SENSOR)),
            einspeisung_w=self._get_float(c.get(CONF_FEED_IN_SENSOR, DEFAULT_FEED_IN_SENSOR)),
            battery_soc=self._get_float(c.get(CONF_BATTERY_SOC_SENSOR, DEFAULT_BATTERY_SOC_SENSOR)),
            battery_capacity_kwh=self._get_battery_capacity_kwh(c),
            ww_temp=self._get_float(c.get(CONF_PUFFER_TEMP_SENSOR, DEFAULT_PUFFER_TEMP_SENSOR)),
            ww_target=self._ww_target,
            solcast_remaining_kwh=self._get_float(c.get(CONF_SOLCAST_REMAINING_SENSOR, DEFAULT_SOLCAST_REMAINING_SENSOR)),
            solcast_morgen_kwh=self._get_float(c.get(CONF_SOLCAST_MORGEN_SENSOR, DEFAULT_SOLCAST_MORGEN_SENSOR)),
            energy_demand_kwh=self._get_float(ENTITY_ENERGIEBEDARF),
            prognose_sunrise_kwh=self._get_float(ENTITY_PROGNOSE_SUNRISE),
            verbrauch_morgen_kwh=self._get_float(ENTITY_PROGNOSE_MORGEN),
            holzvergaser_active=self._get_bool(c.get(CONF_HOLZVERGASER_SENSOR, DEFAULT_HOLZVERGASER_SENSOR)),
            sun_above_horizon=self._get_sun_state(),
            hausverbrauch_w=self._get_float(c.get("consumption_sensor", "sensor.solarnet_leistung_verbrauch")),
            heizstab_leistung_w=self._get_float(c.get("heizstab_sensor", "sensor.ohmpilot_leistung")),
        )
        return snap

    def _get_battery_capacity_kwh(self, config: dict) -> float:
        """Read battery capacity, auto-detect Wh vs kWh."""
        sensor_id = config.get(CONF_BATTERY_CAPACITY_SENSOR, DEFAULT_BATTERY_CAPACITY_SENSOR)
        raw = self._get_float(sensor_id)
        if raw is None:
            return 0.0
        state = self.hass.states.get(sensor_id)
        unit = state.attributes.get("unit_of_measurement", "") if state else ""
        if unit.lower() in ("wh", "w·h") or (not unit and raw > 1000):
            return raw / 1000.0
        return raw

    def _get_float(self, entity_id: str) -> float:
        """Safely read a numeric sensor value."""
        if not entity_id:
            return 0.0
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "None"):
            return 0.0
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return 0.0

    def _get_bool(self, entity_id: str) -> bool:
        """Read a switch/binary_sensor state as bool."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return False
        return state.state.lower() in ("on", "true", "1")

    def _get_sun_state(self) -> bool:
        """Check if sun is above horizon."""
        sun = self.hass.states.get("sun.sun")
        if sun is None:
            return True
        return sun.state != "below_horizon"

    # ── Evaluation (pure logic, no side effects) ─────────────────────────

    def _evaluate(self, snap: Snapshot) -> Decision:
        """Evaluate all inputs and produce a decision."""
        decision = Decision(
            timestamp=snap.now.isoformat(),
            inputs={
                "pv_leistung_w": snap.pv_power_w,
                "einspeisung_w": snap.einspeisung_w,
                "batterie_soc": snap.battery_soc,
                "batterie_kapazitaet_kwh": snap.battery_capacity_kwh,
                "warmwasser_temp": snap.ww_temp,
                "solcast_rest_kwh": snap.solcast_remaining_kwh,
                "solcast_morgen_kwh": snap.solcast_morgen_kwh,
                "verbrauch_morgen_kwh": snap.verbrauch_morgen_kwh,
                "energiebedarf_kwh": snap.energy_demand_kwh,
                "prognose_sunrise_kwh": snap.prognose_sunrise_kwh,
                "holzvergaser": snap.holzvergaser_active,
                "sonne": "oben" if snap.sun_above_horizon else "unten",
                "stunde": snap.current_hour,
            },
        )

        # Min-SOC immer berechnen (auch tagsüber als Vorschau)
        decision.min_soc_berechnet = self._calc_min_soc_entladung(snap)

        # ── Step 1: Safety guards ────────────────────────────────────────
        guards = self._check_guards(snap)
        decision.guards_aktiv = [g for g, _ in guards]

        kritisch = [(g, fn) for g, fn in guards if "KRITISCH" in g]
        if kritisch:
            # Apply all critical overrides, then return
            for _, apply_fn in kritisch:
                apply_fn(snap, decision)
            decision.strategie = "Sicherheit"
            return decision

        # ── Step 2: Determine strategy ───────────────────────────────────
        if not snap.sun_above_horizon:
            decision.strategie = STRATEGY_NACHT
            self._apply_nacht(snap, decision)
        else:
            factor = self._calc_ueberschuss_faktor(snap)
            decision.ueberschuss_faktor = round(factor, 2)

            if factor >= self._ueberschuss_faktor:
                decision.strategie = STRATEGY_UEBERSCHUSS
                self._apply_ueberschuss(snap, decision)
            elif factor >= 0.8:
                decision.strategie = STRATEGY_BALANCIERT
                self._apply_balanciert(snap, decision)
            else:
                decision.strategie = STRATEGY_ENGPASS
                self._apply_engpass(snap, decision)

        # ── Step 3: Apply non-critical guards as overrides ───────────────
        hoch = [(g, fn) for g, fn in guards if "HOCH" in g]
        for _, apply_fn in hoch:
            apply_fn(snap, decision)

        # Guard-Delay Info in Begründung
        hours = self._hours_since_sunrise(snap.now)
        if hours is not None and hours < self._guard_delay_h:
            decision.begruendung += (
                f"\n☀ Guard-Delay: {hours:.1f}h seit Sonnenaufgang"
                f" < {self._guard_delay_h:.0f}h → HOCH-Guards unterdrückt (EEG-Vorrang)"
            )

        # ── Step 4: Nachtentladungs-Vorschau (nur tagsüber) ──────────────
        if snap.sun_above_horizon:
            decision.begruendung += self._nachtentladung_vorschau(
                snap, decision.min_soc_berechnet
            )

        return decision

    # ── Safety guards ────────────────────────────────────────────────────

    def _hours_since_sunrise(self, now: datetime) -> float | None:
        """Calculate hours since today's sunrise. Returns None if unknown."""
        sun = self.hass.states.get("sun.sun")
        if sun is None:
            return None
        if sun.state == "below_horizon":
            return None  # Nachts – Guard-Delay irrelevant
        nr = sun.attributes.get("next_rising")
        if not nr:
            return None
        try:
            next_rising = datetime.fromisoformat(str(nr))
        except (ValueError, TypeError):
            return None
        # Sonne ist oben → next_rising ist morgen → heute ≈ next_rising - 24h
        today_sunrise = next_rising - timedelta(days=1)
        delta = (now - today_sunrise).total_seconds() / 3600.0
        return max(delta, 0.0)

    def _check_guards(self, snap: Snapshot) -> list[tuple[str, Any]]:
        """Check all safety conditions. Returns list of (description, apply_fn).

        HOCH-Guards (WW < 55°C, Batterie < 25%) werden in den ersten
        Stunden nach Sonnenaufgang unterdrückt (guard_delay_h), damit
        morgens die EEG-Einspeisung Vorrang hat.
        KRITISCH-Guards sind immer aktiv.
        """
        guards: list[tuple[str, Any]] = []

        # KRITISCH – immer aktiv
        if snap.ww_temp < 40 and snap.ww_temp > 0:
            guards.append((
                "KRITISCH: Warmwasser unter 40°C – sofort aufheizen",
                self._guard_ww_kritisch,
            ))

        if 0 < snap.battery_soc < 10:
            guards.append((
                "KRITISCH: Batterie unter 10% – sofort laden",
                self._guard_battery_kritisch,
            ))

        # HOCH – erst nach Guard-Delay aktiv
        hours = self._hours_since_sunrise(snap.now)
        guard_delayed = (
            hours is not None
            and hours < self._guard_delay_h
        )

        if guard_delayed:
            _LOGGER.debug(
                "Guard-Delay aktiv: %.1fh seit Sonnenaufgang < %.1fh Delay "
                "→ HOCH-Guards unterdrückt (WW %.0f°C, SOC %.0f%%)",
                hours, self._guard_delay_h, snap.ww_temp, snap.battery_soc,
            )

        if not guard_delayed:
            if 0 < snap.ww_temp < 55:
                guards.append((
                    "HOCH: Warmwasser unter 55°C – Heizstab Priorität",
                    self._guard_ww_hoch,
                ))

            if 0 < snap.battery_soc < 25:
                guards.append((
                    "HOCH: Batterie unter 25% – Ladelimit erhöhen",
                    self._guard_battery_hoch,
                ))

        if snap.holzvergaser_active and snap.pv_power_w < 6000:
            guards.append((
                "MITTEL: Holzvergaser aktiv, PV < 6kW – Heizstab aus",
                self._guard_holzvergaser,
            ))

        return guards

    def _guard_ww_kritisch(self, snap: Snapshot, dec: Decision) -> None:
        pv_kw = snap.pv_power_w / 1000.0
        hausverbrauch_kw = snap.hausverbrauch_w / 1000.0
        heizstab_kw_aktuell = snap.heizstab_leistung_w / 1000.0
        haus_netto_kw = hausverbrauch_kw - heizstab_kw_aktuell

        # Bei SOC < 50%: 1 kW für Batterie reservieren, Rest für Heizstab
        bat_reserve = 1.0 if snap.battery_soc < 50 else 0.0
        verfuegbar_kw = pv_kw + heizstab_kw_aktuell - hausverbrauch_kw
        heizstab_kw_soll = HEIZSTAB_POWER_KW[HEIZSTAB_3P]  # 6 kW

        if verfuegbar_kw >= heizstab_kw_soll + bat_reserve:
            # Genug PV für Heizstab 3P + Batterie
            ladelimit = round(verfuegbar_kw - heizstab_kw_soll)
            dec.heizstab_modus = HEIZSTAB_3P
        elif bat_reserve > 0 and verfuegbar_kw >= bat_reserve:
            # SOC niedrig: Batterie bekommt 1 kW, Heizstab den Rest
            ladelimit = round(bat_reserve)
            rest_fuer_heizstab = verfuegbar_kw - bat_reserve
            if rest_fuer_heizstab >= 1.0:
                dec.heizstab_modus = HEIZSTAB_1P
            else:
                dec.heizstab_modus = HEIZSTAB_3P  # OhmPilot regelt selbst
        else:
            ladelimit = 0
            dec.heizstab_modus = HEIZSTAB_3P

        dec.ladelimit_kw = ladelimit
        dec.einspeisung_aktiv = False
        dec.einspeisewert_kw = 0

        bat_info = f"Batterie: {ladelimit} kW"
        if bat_reserve > 0:
            bat_info += f" (SOC {snap.battery_soc:.0f}% < 50%)"

        dec.begruendung = (
            f"Strategie: Sicherheit\n"
            f"⚠ Warmwasser nur {snap.ww_temp:.0f}°C (< 40°C)\n"
            f"PV: {pv_kw:.1f} kW – Heizstab: {dec.heizstab_modus} – Haus: {haus_netto_kw:.1f} kW\n"
            f"→ Heizstab: {dec.heizstab_modus} | {bat_info} | Einspeisung: gestoppt"
        )

    def _guard_battery_kritisch(self, snap: Snapshot, dec: Decision) -> None:
        dec.heizstab_modus = HEIZSTAB_AUS
        dec.ladelimit_kw = max(round(snap.pv_power_w / 1000), 2)
        dec.einspeisung_aktiv = False
        dec.einspeisewert_kw = 0
        dec.entladung_aktiv = False
        dec.begruendung = (
            f"Strategie: Sicherheit\n"
            f"⚠ Batterie nur {snap.battery_soc:.0f}% (< 10%)\n"
            f"→ Batterie: {dec.ladelimit_kw} kW (alle PV) | Heizstab: Aus | Einspeisung: Aus"
        )

    def _guard_ww_hoch(self, snap: Snapshot, dec: Decision) -> None:
        if dec.heizstab_modus == HEIZSTAB_AUS:
            dec.heizstab_modus = HEIZSTAB_1P
            dec.begruendung += (
                f"\n⚠ Guard: WW {snap.ww_temp:.0f}°C < 55°C → Heizstab auf 1-Phasig"
            )

    def _guard_battery_hoch(self, snap: Snapshot, dec: Decision) -> None:
        if dec.ladelimit_kw < 2:
            dec.ladelimit_kw = 2
            dec.begruendung += (
                f"\n⚠ Guard: SOC {snap.battery_soc:.0f}% < 25% → Ladelimit auf 2 kW"
            )

    def _guard_holzvergaser(self, snap: Snapshot, dec: Decision) -> None:
        if dec.heizstab_modus != HEIZSTAB_AUS:
            dec.heizstab_modus = HEIZSTAB_AUS
            dec.begruendung += (
                f"\n⚠ Guard: Holzvergaser aktiv, PV < 6kW → Heizstab Aus"
            )

    # ── Überschuss-Faktor ────────────────────────────────────────────────

    def _calc_ueberschuss_faktor(self, snap: Snapshot) -> float:
        """PV remaining / energy demand. Higher = more surplus."""
        if snap.energy_demand_kwh <= 0:
            return 99.0 if snap.solcast_remaining_kwh > 0 else 1.0
        return snap.solcast_remaining_kwh / snap.energy_demand_kwh

    # ── Strategy: ÜBERSCHUSS ─────────────────────────────────────────────

    def _apply_ueberschuss(self, snap: Snapshot, dec: Decision) -> None:
        """Good PV day: feed in early, charge at midday, discharge evening."""
        pv_kw = snap.pv_power_w / 1000.0
        limit_kw = self._einspeiselimit
        hausverbrauch_kw = snap.hausverbrauch_w / 1000.0
        heizstab_kw_aktuell = snap.heizstab_leistung_w / 1000.0

        # Inverter-Drosselung erkennen: Wenn Einspeisung am Limit ist,
        # wird der Inverter gedrosselt und pv_kw zeigt NICHT die wahre
        # Kapazität. In diesem Fall spekulativ mehr PV annehmen, damit
        # Batterie/Heizstab aktiviert werden und der Inverter aufmacht.
        einspeisung_am_limit = snap.einspeisung_w >= (limit_kw * 1000 - 100)
        inverter_gedrosselt = einspeisung_am_limit
        if inverter_gedrosselt:
            # PV könnte deutlich mehr liefern – mindestens 2kW extra annehmen
            # damit der Deadlock durchbrochen wird
            pv_kw_korrigiert = pv_kw + 2.0
            _LOGGER.debug(
                "Inverter-Drosselung erkannt: Einspeisung %.0fW ≈ Limit %.0fkW, "
                "pv_kw %.1f → korrigiert %.1f kW",
                snap.einspeisung_w, limit_kw, pv_kw, pv_kw_korrigiert,
            )
            pv_kw = pv_kw_korrigiert

        # Verfügbare Leistung nach Einspeiselimit und Hausverbrauch
        # (Was können wir für Batterie + Heizstab verwenden?)
        # heizstab_kw_aktuell wird addiert, da diese Leistung umverteilt werden kann
        verfuegbar_kw = pv_kw + heizstab_kw_aktuell - limit_kw - hausverbrauch_kw

        if snap.ww_temp >= snap.ww_target:
            # Puffer voll → alles für Batterie
            dec.heizstab_modus = HEIZSTAB_AUS
            dec.ladelimit_kw = max(round(verfuegbar_kw), 0)
            dec.begruendung = (
                f"Strategie: Überschuss (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW\n→ Einspeisung: {limit_kw:.0f} kW (verfügbar: {verfuegbar_kw:.1f} kW)\n"
                f"→ Batterie: {dec.ladelimit_kw} kW (SOC {snap.battery_soc:.0f}%)\n"
                f"→ Heizstab: Aus (WW {snap.ww_temp:.0f}°C erreicht)"
            )
        elif snap.battery_soc > 99:
            # Batterie voll → alles für Heizstab
            dec.heizstab_modus = HEIZSTAB_3P if verfuegbar_kw > 4 else HEIZSTAB_1P if verfuegbar_kw > 0.5 else HEIZSTAB_AUS
            dec.ladelimit_kw = 0
            dec.begruendung = (
                f"Strategie: Überschuss (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW\n→ Einspeisung: {limit_kw:.0f} kW (verfügbar: {verfuegbar_kw:.1f} kW)\n"
                f"→ Batterie: 0 kW (SOC {snap.battery_soc:.0f}% – voll)\n"
                f"→ Heizstab: {dec.heizstab_modus} (WW {snap.ww_temp:.0f}°C → {snap.ww_target:.0f}°C)"
            )
        elif verfuegbar_kw < 0:
            # Morgens bei niedrigem PV: Einspeisung hat Priorität
            # (nach Drosselungs-Korrektur immer noch negativ = wirklich zu wenig PV)
            dec.heizstab_modus = HEIZSTAB_AUS
            dec.ladelimit_kw = 0
            drosselung = "\n⚡ Inverter-Drosselung erkannt, +2kW angenommen" if inverter_gedrosselt else ""
            dec.begruendung = (
                f"Strategie: Überschuss (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW\n→ Einspeisung: {limit_kw:.0f} kW | Haus: {hausverbrauch_kw:.1f} kW (PV reicht noch nicht)\n"
                f"→ Batterie: wartet (SOC {snap.battery_soc:.0f}%)\n"
                f"→ Heizstab: wartet (WW {snap.ww_temp:.0f}°C)"
                f"{drosselung}"
            )
        else:
            # Genug PV für Einspeisung + Laden
            heizstab, heizstab_kw = self._choose_heizstab(verfuegbar_kw, snap)
            rest_fuer_batterie = max(verfuegbar_kw - heizstab_kw, 0)

            dec.heizstab_modus = heizstab
            dec.ladelimit_kw = round(rest_fuer_batterie)

            dec.begruendung = (
                f"Strategie: Überschuss (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW\n→ Einspeisung: {limit_kw:.0f} kW (verfügbar: {verfuegbar_kw:.1f} kW)\n"
                f"→ Heizstab: {heizstab} ({heizstab_kw:.0f} kW, WW {snap.ww_temp:.0f}°C)\n"
                f"→ Batterie: {dec.ladelimit_kw} kW (SOC {snap.battery_soc:.0f}%)"
            )

        # Feed-in is always desired in ÜBERSCHUSS (happens automatically via inverter)
        dec.einspeisung_aktiv = False
        dec.einspeisewert_kw = 0

    # ── Strategy: BALANCIERT ─────────────────────────────────────────────

    def _apply_balanciert(self, snap: Snapshot, dec: Decision) -> None:
        """Moderate PV day: balance between charging and feed-in."""
        pv_kw = snap.pv_power_w / 1000.0
        hausverbrauch_kw = snap.hausverbrauch_w / 1000.0
        heizstab_kw_aktuell = snap.heizstab_leistung_w / 1000.0

        # Inverter-Drosselung erkennen (gleiche Logik wie ÜBERSCHUSS)
        limit_kw = self._einspeiselimit
        einspeisung_am_limit = snap.einspeisung_w >= (limit_kw * 1000 - 100)
        if einspeisung_am_limit:
            pv_kw += 2.0

        # Verfügbare Leistung für Batterie + Heizstab (ohne Einspeiselimit-Reserve)
        verfuegbar_kw = pv_kw + heizstab_kw_aktuell - hausverbrauch_kw

        if verfuegbar_kw <= 0:
            dec.heizstab_modus = HEIZSTAB_AUS
            dec.ladelimit_kw = 0
            dec.begruendung = (
                f"Strategie: Balanciert (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW | Haus: {hausverbrauch_kw:.1f} kW (kein Überschuss)"
            )
        else:
            # Batterie hat Vorrang, WW danach
            if snap.battery_soc < 80:
                batterie_kw = min(verfuegbar_kw, max(round(verfuegbar_kw * 0.6), 1))
                rest = verfuegbar_kw - batterie_kw
                heizstab, heizstab_kw = self._choose_heizstab(rest, snap)
            else:
                heizstab, heizstab_kw = self._choose_heizstab(verfuegbar_kw, snap)
                batterie_kw = max(verfuegbar_kw - heizstab_kw, 0)

            dec.heizstab_modus = heizstab
            dec.ladelimit_kw = round(batterie_kw)
            dec.begruendung = (
                f"Strategie: Balanciert (Faktor {dec.ueberschuss_faktor:.1f}x)\n"
                f"PV: {pv_kw:.1f} kW (verfügbar: {verfuegbar_kw:.1f} kW)\n"
                f"→ Batterie: {dec.ladelimit_kw} kW (SOC {snap.battery_soc:.0f}%)\n"
                f"→ Heizstab: {heizstab} (WW {snap.ww_temp:.0f}°C)\n"
                f"→ Überschuss → Netz"
            )

        dec.einspeisung_aktiv = False
        dec.einspeisewert_kw = 0

    # ── Strategy: ENGPASS ────────────────────────────────────────────────

    def _apply_engpass(self, snap: Snapshot, dec: Decision) -> None:
        """Bad PV day: maximize self-consumption."""
        pv_kw = snap.pv_power_w / 1000.0
        hausverbrauch_kw = snap.hausverbrauch_w / 1000.0
        heizstab_kw_aktuell = snap.heizstab_leistung_w / 1000.0

        # Inverter-Drosselung erkennen
        limit_kw = self._einspeiselimit
        einspeisung_am_limit = snap.einspeisung_w >= (limit_kw * 1000 - 100)
        if einspeisung_am_limit:
            pv_kw += 2.0

        verfuegbar_kw = pv_kw + heizstab_kw_aktuell - hausverbrauch_kw

        if verfuegbar_kw <= 0:
            dec.heizstab_modus = HEIZSTAB_AUS
            dec.ladelimit_kw = 0
        else:
            batterie_voll = snap.battery_soc >= 98
            if batterie_voll:
                # Batterie voll → Heizstab bekommt alles verfügbare
                heizstab, heizstab_kw = self._choose_heizstab(verfuegbar_kw, snap)
                dec.heizstab_modus = heizstab
                dec.ladelimit_kw = max(round(verfuegbar_kw - heizstab_kw), 0)
            elif snap.ww_temp < 55:
                # Batterie nicht voll, aber WW kritisch → aufteilen
                heizstab, heizstab_kw = self._choose_heizstab(verfuegbar_kw, snap)
                dec.heizstab_modus = heizstab
                dec.ladelimit_kw = max(round(verfuegbar_kw - heizstab_kw), 0)
            else:
                # Batterie nicht voll, WW ok → alles für Batterie
                dec.heizstab_modus = HEIZSTAB_AUS
                dec.ladelimit_kw = round(verfuegbar_kw)

        dec.einspeisung_aktiv = False
        dec.einspeisewert_kw = 0
        dec.begruendung = (
            f"Strategie: Engpass (Faktor {dec.ueberschuss_faktor:.1f}x, PV {snap.solcast_remaining_kwh:.0f} kWh < Bedarf {snap.energy_demand_kwh:.0f} kWh)\n"
            f"PV: {pv_kw:.1f} kW (verfügbar: {verfuegbar_kw:.1f} kW)\n"
            f"→ Batterie: {dec.ladelimit_kw} kW (SOC {snap.battery_soc:.0f}%)\n"
            f"→ Heizstab: {dec.heizstab_modus} (WW {snap.ww_temp:.0f}°C)\n"
            f"→ Einspeisung: aus – Eigenverbrauch Priorität"
        )

    # ── Strategy: NACHT ──────────────────────────────────────────────────

    def _apply_nacht(self, snap: Snapshot, dec: Decision) -> None:
        """After sunset: default generous, potentially discharge for EEG.

        Heizstab and battery charge are set to generous defaults because
        the inverter only charges from PV (not grid) and the Ohmpilot
        only heats with PV surplus. Setting high limits at night costs nothing.
        """
        dec.heizstab_modus = HEIZSTAB_3P
        dec.ladelimit_kw = 4

        # Check if evening discharge should be active
        entlade_ok = self._check_entladung(snap, dec)

        if entlade_ok:
            dec.entladung_aktiv = True
            dec.einspeisung_aktiv = True
            dec.einspeisewert_kw = self._entladeleistung
            dec.entladeleistung_kw = self._entladeleistung
        else:
            dec.entladung_aktiv = False
            dec.einspeisung_aktiv = False
            dec.einspeisewert_kw = 0

    def _calc_energiebedarf_morgen(self, snap: Snapshot) -> dict:
        """Calculate total energy demand for tomorrow.

        Includes household consumption + battery charge from min_soc + puffer from 40°C.
        """
        verbrauch = snap.verbrauch_morgen_kwh

        # Battery: from configured min SOC floor to 100%
        min_soc = float(self._min_soc)
        batterie_kwh = 0.0
        if snap.battery_capacity_kwh > 0:
            batterie_kwh = (100.0 - min_soc) / 100.0 * snap.battery_capacity_kwh

        # Puffer: from min_ww_entladung (40°C) to target temp
        puffer_delta = max(self._ww_target - self._min_ww_entladung, 0.0)
        puffer_kwh = self._puffer_volume_l * 4.186 * puffer_delta / 3600.0

        gesamt = verbrauch + batterie_kwh + puffer_kwh

        return {
            "verbrauch_kwh": verbrauch,
            "batterie_kwh": round(batterie_kwh, 1),
            "puffer_kwh": round(puffer_kwh, 1),
            "gesamt_kwh": round(gesamt, 1),
            "min_soc": min_soc,
        }

    def _check_entladung(self, snap: Snapshot, dec: Decision) -> bool:
        """Determine if evening battery discharge should be active.

        Nachtentladung wird freigegeben wenn ALLE Bedingungen erfüllt sind:
        1. Startzeit erreicht (default 20:00)
        2. SOC > dynamischer Min-SOC (Nachtverbrauch + Sicherheitspuffer)
        3. WW-Temp >= Mindest-WW-Temperatur (default 40°C)
        4. Morgen ist ein Überschusstag: PV-Prognose >= Gesamtbedarf
           Gesamtbedarf = Hausverbrauch + Batterie (min_soc→100%) + Puffer (40°C→Ziel)
        """
        startzeit = f"{self._entlade_start_h:02d}:{self._entlade_start_m:02d}"

        # Calculate tomorrow's total energy demand and factor
        bedarf = self._calc_energiebedarf_morgen(snap)
        faktor_morgen = (
            snap.solcast_morgen_kwh / bedarf["gesamt_kwh"]
            if bedarf["gesamt_kwh"] > 0 else 0.0
        )
        faktor_info = (
            f"Faktor morgen: {faktor_morgen:.2f} "
            f"(PV {snap.solcast_morgen_kwh:.0f} kWh / Bedarf {bedarf['gesamt_kwh']:.1f} kWh)\n"
            f"  Bedarf: Verbrauch {bedarf['verbrauch_kwh']:.1f} + "
            f"Batterie {bedarf['batterie_kwh']:.1f} (ab {bedarf['min_soc']:.0f}%) + "
            f"Puffer {bedarf['puffer_kwh']:.1f} (ab {self._min_ww_entladung:.0f}°C)"
        )

        # Not time yet?
        if snap.current_hour < self._entlade_start_h or (
            snap.current_hour == self._entlade_start_h and snap.now.minute < self._entlade_start_m
        ):
            dec.begruendung = (
                f"Strategie: Nacht (warte auf Entladung ab {startzeit})\n"
                f"SOC: {snap.battery_soc:.0f}% | WW: {snap.ww_temp:.0f}°C\n"
                f"{faktor_info}\n"
                f"→ Heizstab: 3-Phasig | Ladelimit: 4 kW (Defaults)"
            )
            return False

        # Calculate min SOC for discharge
        min_soc = self._calc_min_soc_entladung(snap)
        dec.min_soc_berechnet = min_soc

        # Check conditions
        blockiert: list[str] = []

        if snap.battery_soc <= min_soc:
            blockiert.append(f"SOC {snap.battery_soc:.0f}% <= Min {min_soc:.0f}%")
        if faktor_morgen < 1.0:
            blockiert.append(f"Morgen kein Überschusstag (PV deckt nur {faktor_morgen * 100:.0f}% vom Bedarf)")

        nacht_info = (
            f"Min-SOC: {min_soc:.0f}% "
            f"(Nachtverbrauch {snap.prognose_sunrise_kwh:.1f} kWh + {self._sicherheitspuffer}% Puffer)"
        )

        if blockiert:
            dec.begruendung = (
                f"Strategie: Nacht (Entladung blockiert)\n"
                + "".join(f"✖ {b}\n" for b in blockiert)
                + f"{nacht_info}\n"
                + f"{faktor_info}"
            )
            return False

        dec.begruendung = (
            f"Strategie: Nacht – Entladung aktiv\n"
            f"→ Entladung: {self._entladeleistung:.0f} kW für EEG\n"
            f"SOC: {snap.battery_soc:.0f}% > Min {min_soc:.0f}% | WW: {snap.ww_temp:.0f}°C\n"
            f"{nacht_info}\n"
            f"{faktor_info}"
        )
        return True

    def _calc_min_soc_entladung(self, snap: Snapshot) -> float:
        """Calculate minimum SOC for evening discharge.

        Formula: absolute min SOC + (overnight consumption × safety buffer) as SOC%.
        """
        if snap.battery_capacity_kwh <= 0:
            return float(self._min_soc)

        nacht_kwh = snap.prognose_sunrise_kwh
        puffer_factor = 1.0 + (self._sicherheitspuffer / 100.0)
        benoetigte_kwh = nacht_kwh * puffer_factor

        nacht_soc = (benoetigte_kwh / snap.battery_capacity_kwh) * 100.0
        return math.ceil(self._min_soc + nacht_soc)

    # ── Nachtentladung Vorschau ──────────────────────────────────────────

    def _nachtentladung_vorschau(self, snap: Snapshot, min_soc: float) -> str:
        """Build a preview line for tonight's discharge plan."""
        bedarf = self._calc_energiebedarf_morgen(snap)
        faktor_morgen = (
            snap.solcast_morgen_kwh / bedarf["gesamt_kwh"]
            if bedarf["gesamt_kwh"] > 0 else 0.0
        )

        blockiert: list[str] = []

        if snap.battery_soc <= min_soc:
            blockiert.append(f"SOC {snap.battery_soc:.0f}% <= Min {min_soc:.0f}%")
        if faktor_morgen < 1.0:
            blockiert.append(
                f"Morgen kein Überschusstag (PV {snap.solcast_morgen_kwh:.0f} kWh"
                f" < Bedarf {bedarf['gesamt_kwh']:.1f} kWh)"
            )

        if blockiert:
            return (
                f"\nNachtentladung: nicht geplant ({', '.join(blockiert)})"
            )

        return (
            f"\nNachtentladung: geplant"
            f" (Min-SOC {min_soc:.0f}%,"
            f" PV morgen {snap.solcast_morgen_kwh:.0f} kWh >= Bedarf {bedarf['gesamt_kwh']:.1f} kWh)"
        )

    # ── Heizstab selection ───────────────────────────────────────────────

    def _choose_heizstab(
        self, available_kw: float, snap: Snapshot
    ) -> tuple[str, float]:
        """Choose heizstab mode based on available power and WW temperature.

        Returns (mode_string, power_kw).
        """
        if snap.ww_temp >= snap.ww_target:
            return HEIZSTAB_AUS, 0.0

        # 3-Phasig (6kW) wenn genug Leistung und WW braucht es
        if available_kw >= 6.0 and snap.ww_temp < snap.ww_target - 5:
            return HEIZSTAB_3P, HEIZSTAB_POWER_KW[HEIZSTAB_3P]

        # 1-Phasig wenn Leistung verfügbar
        if available_kw > 0 and snap.ww_temp < snap.ww_target:
            return HEIZSTAB_1P, HEIZSTAB_POWER_KW[HEIZSTAB_1P]

        return HEIZSTAB_AUS, 0.0

    # ── Execution (side effects) ─────────────────────────────────────────

    async def _execute(self, dec: Decision) -> None:
        """Write decision to HA entities.

        Heizstab + Ladelimit: via input_* helpers (external).
        Einspeisung: via own switch + number entities → fronius_sync handles API.
        """

        # Heizstab
        if dec.heizstab_modus != self._prev_heizstab:
            await self.hass.services.async_call(
                "input_select", "select_option",
                {"entity_id": ENTITY_HEIZSTAB, "option": dec.heizstab_modus},
            )
            _LOGGER.info("Optimizer: Heizstab → %s", dec.heizstab_modus)
            self._prev_heizstab = dec.heizstab_modus

        # Ladelimit
        if dec.ladelimit_kw != self._prev_ladelimit:
            await self.hass.services.async_call(
                "input_number", "set_value",
                {"entity_id": ENTITY_LADELIMIT, "value": dec.ladelimit_kw},
            )
            _LOGGER.info("Optimizer: Ladelimit → %s kW", dec.ladelimit_kw)
            self._prev_ladelimit = dec.ladelimit_kw

        # Einspeiseleistung ZUERST setzen (bevor Switch fronius_sync triggert)
        if dec.einspeisewert_kw != self._prev_einspeisewert:
            await self.hass.services.async_call(
                "number", "set_value",
                {"entity_id": ENTITY_EINSPEISEWERT, "value": dec.einspeisewert_kw},
            )
            _LOGGER.info("Optimizer: Einspeiseleistung → %s kW", dec.einspeisewert_kw)
            self._prev_einspeisewert = dec.einspeisewert_kw

        # Einspeisung Switch DANACH (triggers fronius_sync mit korrektem Wert)
        if dec.einspeisung_aktiv != self._prev_einspeisung:
            service = "turn_on" if dec.einspeisung_aktiv else "turn_off"
            await self.hass.services.async_call(
                "switch", service,
                {"entity_id": ENTITY_EINSPEISUNG_AKTIV},
            )
            _LOGGER.info("Optimizer: Einspeisung → %s", service)
            self._prev_einspeisung = dec.einspeisung_aktiv
