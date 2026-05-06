"""Feed-in statistics tracking for EEG Energy Optimizer.

Tracks grid feed-in energy (kWh), session count, and duration during
optimizer active states (Morgen-Einspeisung and Abend-Entladung).

Data is persisted via Home Assistant's Store API and retained indefinitely.
Session details (start/end/kwh per session) are compacted to daily aggregates
after STATS_COMPACT_AFTER_DAYS to keep storage size minimal.
"""

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any

from .const import (
    CONF_GRID_POWER_SENSOR,
    CONF_INVERTER_TYPE,
    DOMAIN,
    INVERTER_SIGN_CONVENTIONS,
    MIN_BLOCK_OUTCOME_MINUTES,
    STATE_ABEND_ENTLADUNG,
    STATE_MORGEN_EINSPEISUNG,
    STATE_TO_STATS_KEY,
    STATS_COMPACT_AFTER_DAYS,
)

_LOGGER = logging.getLogger(__name__)


def _trapezoid_kwh(samples: list[tuple[datetime, float]]) -> float:
    """Trapezoidal integration of power (kW) over time → energy (kWh).

    Formel: sum(((p[i] + p[i+1]) / 2) * dt_hours)
    wobei dt_hours = (samples[i+1].ts - samples[i].ts).total_seconds() / 3600.

    Returns 0.0 bei <2 nutzbaren Samples. Filtert None-Werte vor der Integration.
    Sortiert nach ts, damit out-of-order Samples sauber integriert werden.

    W-1 — Outcome predicted-vs-actual: actual_pv_kwh / actual_consumption_kwh
    werden aus dem 30-min Snapshot-Queue über das Block-Fenster gerechnet.
    """
    valid = sorted(
        [(ts, p) for ts, p in samples if p is not None],
        key=lambda x: x[0],
    )
    if len(valid) < 2:
        return 0.0
    total = 0.0
    for i in range(len(valid) - 1):
        dt_hours = (valid[i + 1][0] - valid[i][0]).total_seconds() / 3600.0
        if dt_hours <= 0:
            continue
        total += ((valid[i][1] + valid[i + 1][1]) / 2.0) * dt_hours
    return total

# HA imports guarded for test environment
try:
    from homeassistant.helpers.storage import Store
    from homeassistant.util import dt as dt_util
    _now = dt_util.now
    _as_local = dt_util.as_local
except ImportError:
    Store = None  # type: ignore[assignment,misc]
    _now = lambda: datetime.now(tz=timezone.utc)  # noqa: E731
    _as_local = lambda dt: dt  # noqa: E731

# Guard against stale readings: skip energy accumulation if cycle gap > 120s
_MAX_ELAPSED_SECONDS = 120

# Merge sessions shorter than 2 minutes into the previous one
_MICRO_SESSION_SECONDS = 120


def _empty_state_stats() -> dict:
    """Return empty statistics for one state (morning or evening)."""
    return {
        "sessions": [],
        "total_kwh": 0.0,
        "total_duration_min": 0,
        "count": 0,
    }


def _empty_day() -> dict:
    """Return empty daily statistics."""
    return {
        "morning": _empty_state_stats(),
        "evening": _empty_state_stats(),
    }


def _read_power_kw(hass: Any, entity_id: str) -> float | None:
    """Read a power sensor value and normalize to kW (delegate)."""
    from .power_readings import read_power_kw
    return read_power_kw(hass, entity_id)


class FeedinStatistics:
    """Tracks grid feed-in energy during optimizer active states."""

    def __init__(self, hass: Any, entry_id: str, config: dict) -> None:
        self._hass = hass
        self._entry_id = entry_id

        # Grid sensor + sign convention (same pattern as NetzleistungSensor)
        self._grid_sensor_id = config.get(CONF_GRID_POWER_SENSOR, "")
        inv_type = config.get(CONF_INVERTER_TYPE, "")
        signs = INVERTER_SIGN_CONVENTIONS.get(inv_type, {})
        self._grid_sign = signs.get("grid_sign", 1)

        # Persistence
        store_key = f"{DOMAIN}_{entry_id}_feedin_stats"
        if Store is not None:
            self._store: Any = Store(hass, 1, store_key)
        else:
            self._store = None

        # Internal state
        self._daily: dict[str, dict] = {}
        self._current_session: dict | None = None
        self._last_update_utc: datetime | None = None
        self._dirty = False
        self._first_cycle = True

        # Phase 8 — Telemetry-Hooks. Werden via set_reporter() injiziert; bleiben
        # None für Test-Setups oder bevor der Reporter im async_setup_entry-Flow
        # erstellt ist. _maybe_send_outcome wird zum stillen No-Op solange einer
        # der beiden None ist.
        self._reporter: Any = None
        self._data: dict | None = None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted statistics and compact old entries."""
        if self._store is None:
            return
        try:
            stored = await self._store.async_load()
        except Exception:
            _LOGGER.debug("No persisted feed-in statistics found")
            return

        if not stored or not isinstance(stored, dict):
            return

        self._daily = stored.get("daily", {})
        self._current_session = stored.get("current_session")

        # Compact old session details
        self._compact_old_entries()

    def _compact_old_entries(self) -> None:
        """Remove session details from entries older than STATS_COMPACT_AFTER_DAYS."""
        cutoff = (date.today() - timedelta(days=STATS_COMPACT_AFTER_DAYS)).isoformat()
        for day_str, day_data in self._daily.items():
            if day_str >= cutoff:
                continue
            for key in ("morning", "evening"):
                state_data = day_data.get(key)
                if state_data and "sessions" in state_data:
                    del state_data["sessions"]
                    self._dirty = True

    async def async_flush(self) -> None:
        """Persist statistics to disk if dirty."""
        if not self._dirty or self._store is None:
            return
        self._dirty = False
        try:
            data = {
                "version": 1,
                "current_session": self._current_session,
                "daily": self._daily,
            }
            await self._store.async_save(data)
        except Exception as err:
            _LOGGER.warning("Failed to save feed-in statistics: %s", err)

    # ------------------------------------------------------------------
    # Core update (called every 30s optimizer cycle)
    # ------------------------------------------------------------------

    async def async_update(self, decision: Any, now_utc: datetime) -> None:
        """Update feed-in statistics based on current optimizer decision.

        Args:
            decision: Decision dataclass from optimizer cycle.
            now_utc: Current UTC datetime.
        """
        stats_key = STATE_TO_STATS_KEY.get(decision.zustand)

        # Only track when optimizer is actually executing inverter commands
        if not decision.ausführung:
            stats_key = None

        now_local = _as_local(now_utc)
        today_str = now_local.strftime("%Y-%m-%d")

        # Read grid export power
        grid_export_kw = self._read_grid_export()

        # First cycle: just record timestamp, don't accumulate
        if self._first_cycle:
            self._first_cycle = False
            self._last_update_utc = now_utc
            # If no active state, ensure no stale session
            if stats_key is None:
                self._close_session(now_local)
            return

        # Calculate elapsed time
        elapsed_seconds = 0.0
        if self._last_update_utc is not None:
            elapsed_seconds = (now_utc - self._last_update_utc).total_seconds()
        self._last_update_utc = now_utc

        # Sessions are bucketed by their start date. Sessions running across
        # midnight stay attached to their start day and continue accumulating —
        # the closing _close_session writes total kWh to session["date"].

        # State transition logic
        current_state = self._current_session.get("state") if self._current_session else None

        if stats_key is None:
            # Normal state: close any open session
            self._close_session(now_local)
        elif stats_key == current_state:
            # Same state: accumulate energy
            self._accumulate(grid_export_kw, elapsed_seconds)
        else:
            # Different active state: close old, open new
            self._close_session(now_local)
            self._open_session(stats_key, now_local, today_str)
            # Accumulate energy for this cycle immediately
            self._accumulate(grid_export_kw, elapsed_seconds)

    def _read_grid_export(self) -> float:
        """Read normalized grid export power in kW (positive = export)."""
        raw = _read_power_kw(self._hass, self._grid_sensor_id)
        if raw is None:
            return 0.0
        return max(raw * self._grid_sign, 0.0)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _open_session(self, stats_key: str, now_local: datetime, today_str: str) -> None:
        """Start a new tracking session."""
        self._current_session = {
            "state": stats_key,
            "start_utc": now_local.astimezone(timezone.utc).isoformat(),
            "start_local": now_local.strftime("%H:%M"),
            "date": today_str,
            "accumulated_kwh": 0.0,
        }
        self._dirty = True

    def _accumulate(self, grid_export_kw: float, elapsed_seconds: float) -> None:
        """Accumulate energy into the current session."""
        if self._current_session is None:
            return
        if elapsed_seconds <= 0 or elapsed_seconds > _MAX_ELAPSED_SECONDS:
            return
        energy_kwh = grid_export_kw * elapsed_seconds / 3600.0
        if energy_kwh > 0:
            self._current_session["accumulated_kwh"] += energy_kwh
            self._dirty = True

    def _close_session(self, now_local: datetime) -> None:
        """Close the current session and save it to daily stats."""
        if self._current_session is None:
            return

        session = self._current_session
        self._current_session = None

        state_key = session["state"]
        day_str = session["date"]

        # Calculate duration
        try:
            start_utc = datetime.fromisoformat(session["start_utc"])
            duration_seconds = (now_local.astimezone(timezone.utc) - start_utc).total_seconds()
        except (ValueError, KeyError):
            duration_seconds = 0

        duration_min = round(duration_seconds / 60.0)
        kwh = round(session["accumulated_kwh"], 3)

        # Skip micro-sessions (< 2 min) with negligible energy
        if duration_seconds < _MICRO_SESSION_SECONDS and kwh < 0.01:
            self._dirty = True
            return

        # Ensure daily entry exists
        if day_str not in self._daily:
            self._daily[day_str] = _empty_day()
        day_data = self._daily[day_str]
        if state_key not in day_data:
            day_data[state_key] = _empty_state_stats()
        state_data = day_data[state_key]

        # Add session record (only if sessions list exists — compacted entries don't have it)
        if "sessions" not in state_data:
            state_data["sessions"] = []

        session_record = {
            "start": session["start_local"],
            "end": now_local.strftime("%H:%M"),
            "kwh": kwh,
            "duration_min": duration_min,
        }

        # Merge micro-sessions with previous
        if (duration_seconds < _MICRO_SESSION_SECONDS
                and state_data["sessions"]
                and kwh >= 0.01):
            prev = state_data["sessions"][-1]
            prev["end"] = session_record["end"]
            prev["kwh"] = round(prev["kwh"] + kwh, 3)
            prev["duration_min"] += duration_min
        else:
            state_data["sessions"].append(session_record)

        # Update aggregates
        state_data["total_kwh"] = round(state_data.get("total_kwh", 0) + kwh, 3)
        state_data["total_duration_min"] = state_data.get("total_duration_min", 0) + duration_min
        state_data["count"] = state_data.get("count", 0) + 1

        # Phase 8 — Outcome-Telemetrie (D-15). Vor dem _dirty-Flush, damit die
        # Aggregates bereits in den Daily-Stats sind, falls der Reporter blockiert.
        try:
            self._maybe_send_outcome(session, now_local, kwh, duration_min)
        except Exception:  # pragma: no cover — defensiv, niemals den FeedinStats-Flow zerlegen
            _LOGGER.exception("Telemetry: outcome emission failed")

        self._dirty = True

    # ------------------------------------------------------------------
    # Phase 8 — Telemetry injection + Outcome emission (W-1, W-2)
    # ------------------------------------------------------------------

    def set_reporter(self, reporter: Any, data: dict) -> None:
        """Wire den TelemetryReporter + per-entry data dict ein.

        Wird im async_setup_entry-Flow aufgerufen, NACHDEM Reporter und
        snapshot_queue / block_predictions im data-Dict abgelegt wurden.
        Solange diese Methode nicht aufgerufen wurde, bleibt _maybe_send_outcome
        ein stilles No-Op.
        """
        self._reporter = reporter
        self._data = data

    def _maybe_send_outcome(
        self,
        session: dict,
        now_local: datetime,
        kwh: float,
        duration_min: int,
    ) -> None:
        """Sendet ein Outcome-Event ans Backend (D-15, W-1, W-2).

        Aufgerufen aus _close_session am Block-Ende. Liest:
          - data["block_predictions"][event_type] für predicted_* + soc_start
          - data["block_samples"][event_type] für peak_power_kw + actual_pv/cons
            (hochauflösender 30s-Sampler — entkoppelt vom 60-min Snapshot-Flush).
            Fallback: data["snapshot_queue"] (Legacy-Pfad / Tests).
          - data["optimizer"].last_decision.snapshot["soc_pct"] für soc_end

        NULL-Felder werden vor dem Versand entfernt — das Backend behandelt
        fehlende Werte korrekt; eine 0 würde die Forecast-MAE-Statistik
        verfälschen.
        """
        if self._reporter is None or not getattr(self._reporter, "is_configured", False):
            return
        buf = getattr(self._reporter, "_buffer", None)
        if buf is None or not buf.identity_known():
            return

        # W-2 — _normalize_state ist die einzige Kanonisierungsfunktion. Lazy-Import,
        # um Zirkularität zu vermeiden (statistics ← __init__).
        from . import _normalize_state

        stats_key = session.get("state")
        if stats_key == "morning":
            event_type = _normalize_state(STATE_MORGEN_EINSPEISUNG)
        elif stats_key == "evening":
            event_type = _normalize_state(STATE_ABEND_ENTLADUNG)
        else:
            return  # unbekannter Session-Typ — nichts zu senden

        data = self._data or {}

        # Mindestdauer-Cutoff: Schwellen-Toggle-Spikes (z.B. SOC oszilliert
        # an der Reserve, Block startet und endet binnen Sekunden) verzerren
        # Backend-Statistiken. Block-State wird trotzdem aufgeräumt, damit
        # der nächste echte Block sauber startet.
        if duration_min < MIN_BLOCK_OUTCOME_MINUTES:
            _LOGGER.debug(
                "Telemetry: outcome geskippt — Block zu kurz (%d min < %d, event_type=%s)",
                duration_min, MIN_BLOCK_OUTCOME_MINUTES, event_type,
            )
            for key in ("block_predictions", "block_samples", "block_actuals_state"):
                d = data.get(key)
                if isinstance(d, dict):
                    d.pop(event_type, None)
            return

        predictions = (data.get("block_predictions") or {}).get(event_type)

        # SOC-Ende: bevorzugt aus dem optimizer.last_decision.snapshot — das ist
        # der genaueste Wert (Zyklus, in dem Block beendet wurde).
        soc_end: int | None = None
        opt = data.get("optimizer")
        if opt is not None:
            last_dec = getattr(opt, "last_decision", None)
            if last_dec is not None:
                snap = getattr(last_dec, "snapshot", None) or {}
                raw_soc = snap.get("soc_pct")
                if raw_soc is not None:
                    try:
                        soc_end = int(round(float(raw_soc)))
                    except (TypeError, ValueError):
                        soc_end = None

        # ---- W-1: peak_power_kw + actual_pv_kwh + actual_consumption_kwh ----
        peak_power_kw: float | None = None
        actual_pv_kwh: float | None = None
        actual_consumption_kwh: float | None = None

        ended_at_dt = now_local.astimezone(timezone.utc)
        started_at_str: str | None = (predictions or {}).get("started_at")
        started_at_dt: datetime | None = None
        if started_at_str:
            try:
                started_at_dt = datetime.fromisoformat(
                    str(started_at_str).replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                started_at_dt = None

        # Quelle für Power-Samples: bevorzugt der dedizierte block_samples-Buffer
        # (30s-Auflösung, nur während aktiver Blöcke befüllt). Nur wenn der
        # explizit nicht existiert (Legacy-Tests), Fallback auf snapshot_queue.
        block_samples = data.get("block_samples")
        if isinstance(block_samples, dict) and event_type in block_samples:
            sample_source = block_samples.get(event_type) or []
        else:
            sample_source = data.get("snapshot_queue") or []

        if started_at_dt is not None and sample_source:
            window: list[tuple[datetime, dict]] = []
            for snap in sample_source:
                ts_raw = snap.get("ts") if isinstance(snap, dict) else None
                if not ts_raw:
                    continue
                try:
                    ts_dt = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
                if started_at_dt <= ts_dt <= ended_at_dt:
                    window.append((ts_dt, snap))

            grids = [
                abs(s["grid_now_kw"]) for _, s in window
                if s.get("grid_now_kw") is not None
            ]
            if grids:
                peak_power_kw = round(max(grids), 3)

            pv_samples = [
                (ts, s.get("pv_now_kw")) for ts, s in window
                if s.get("pv_now_kw") is not None
            ]
            cons_samples = [
                (ts, s.get("consumption_now_kw")) for ts, s in window
                if s.get("consumption_now_kw") is not None
            ]
            if len(pv_samples) >= 2:
                actual_pv_kwh = round(_trapezoid_kwh(pv_samples), 3)
            if len(cons_samples) >= 2:
                actual_consumption_kwh = round(_trapezoid_kwh(cons_samples), 3)

        # actuals_invalid: True wenn ein während des Blocks bereits gesehener
        # Power-Sensor mid-block None geliefert hat (siehe __init__._record_block_sample).
        actuals_state = (data.get("block_actuals_state") or {}).get(event_type) or {}
        actuals_invalid = bool(actuals_state.get("actuals_invalid"))

        payload: dict = {
            "event_type": event_type,
            "started_at": started_at_str if started_at_str else session.get("start_utc", ""),
            "ended_at": ended_at_dt.isoformat(),
            "duration_minutes": int(duration_min),
            "grid_export_kwh": float(round(kwh, 3)),
            "peak_power_kw": peak_power_kw,
            "soc_start_pct": (predictions or {}).get("soc_start_pct"),
            "soc_end_pct": soc_end,
            "predicted_pv_kwh": (predictions or {}).get("predicted_pv_kwh"),
            "actual_pv_kwh": actual_pv_kwh,
            "predicted_consumption_kwh": (predictions or {}).get("predicted_consumption_kwh"),
            "actual_consumption_kwh": actual_consumption_kwh,
            "terminated_by": "block_end",
        }

        # NULL-tolerant: Felder mit None-Wert komplett aus dem Payload entfernen.
        # event_type / started_at / ended_at / duration_minutes / grid_export_kwh
        # / terminated_by sind Pflicht und nie None — der Filter trifft nur
        # optionale Metriken.
        payload = {k: v for k, v in payload.items() if v is not None}

        # actuals_invalid wird nur gesetzt, wenn True — sonst bleibt das Feld
        # weg (Backend-Default = False / actuals trustworthy).
        if actuals_invalid:
            payload["actuals_invalid"] = True

        # Predictions + Block-Samples + Actuals-State poppen, damit eine
        # Folge-Session desselben Typs keine veralteten Werte bekommt.
        bp = data.get("block_predictions")
        if isinstance(bp, dict):
            bp.pop(event_type, None)
        bs = data.get("block_samples")
        if isinstance(bs, dict):
            bs.pop(event_type, None)
        bas = data.get("block_actuals_state")
        if isinstance(bas, dict):
            bas.pop(event_type, None)

        # Fire-and-forget — Reporter handled Buffer/Retry bei Fehler.
        try:
            self._hass.async_create_task(self._reporter.send_outcome(payload))
        except Exception:  # pragma: no cover — defensiv
            _LOGGER.exception("Telemetry: failed to schedule send_outcome")

    # ------------------------------------------------------------------
    # Query methods (for WebSocket API and sensors)
    # ------------------------------------------------------------------

    def get_today_kwh(self, stats_key: str) -> float:
        """Return today's total feed-in kWh for a state, including active session."""
        now_local = _now()
        today_str = now_local.strftime("%Y-%m-%d")
        total = 0.0

        day_data = self._daily.get(today_str, {})
        state_data = day_data.get(stats_key, {})
        total += state_data.get("total_kwh", 0.0)

        # Add active session if it matches
        if (self._current_session
                and self._current_session.get("state") == stats_key
                and self._current_session.get("date") == today_str):
            total += self._current_session.get("accumulated_kwh", 0.0)

        return round(total, 3)

    def get_daily_stats(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        """Return daily statistics filtered by date range.

        Args:
            start_date: Start date string (YYYY-MM-DD), inclusive. None = no lower bound.
            end_date: End date string (YYYY-MM-DD), inclusive. None = no upper bound.
        """
        result = {}
        for day_str, day_data in sorted(self._daily.items()):
            if start_date and day_str < start_date:
                continue
            if end_date and day_str > end_date:
                continue
            result[day_str] = day_data
        return result

    def get_summary(self, days: int | None = None) -> dict:
        """Return aggregated summary for a time period.

        Args:
            days: Number of days to include (from today backwards). None = all data.
        """
        now_local = _now()
        today_str = now_local.strftime("%Y-%m-%d")

        if days is not None:
            start_date = (now_local - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        else:
            start_date = None

        summary: dict[str, dict] = {
            "morning": {"kwh": 0.0, "count": 0, "duration_min": 0},
            "evening": {"kwh": 0.0, "count": 0, "duration_min": 0},
        }

        for day_str, day_data in self._daily.items():
            if start_date and day_str < start_date:
                continue
            for key in ("morning", "evening"):
                state_data = day_data.get(key, {})
                summary[key]["kwh"] += state_data.get("total_kwh", 0.0)
                summary[key]["count"] += state_data.get("count", 0)
                summary[key]["duration_min"] += state_data.get("total_duration_min", 0)

        # Include active session in today's summary
        if self._current_session:
            sess_key = self._current_session.get("state")
            sess_date = self._current_session.get("date")
            if sess_key in summary:
                in_range = start_date is None or (sess_date and sess_date >= start_date)
                if in_range:
                    summary[sess_key]["kwh"] += self._current_session.get("accumulated_kwh", 0.0)

        # Round results
        for key in ("morning", "evening"):
            summary[key]["kwh"] = round(summary[key]["kwh"], 2)

        return summary
