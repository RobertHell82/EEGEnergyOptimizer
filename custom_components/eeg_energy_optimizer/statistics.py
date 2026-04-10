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
    STATE_TO_STATS_KEY,
    STATS_COMPACT_AFTER_DAYS,
)

_LOGGER = logging.getLogger(__name__)

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
    """Read a power sensor value and normalize to kW."""
    state = hass.states.get(entity_id)
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", ""):
        return None
    try:
        val = float(state.state)
    except (ValueError, TypeError):
        return None
    unit = (state.attributes.get("unit_of_measurement") or "").strip()
    if unit == "W":
        return val / 1000.0
    return val


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

        # Handle midnight boundary: close current session if date changed
        if self._current_session and self._current_session.get("date") != today_str:
            self._split_session_at_midnight(now_local)

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

        self._dirty = True

    def _split_session_at_midnight(self, now_local: datetime) -> None:
        """Split the current session at midnight boundary."""
        if self._current_session is None:
            return

        # Close the session at midnight of the new day
        midnight_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        self._close_session(midnight_local)

        # Re-open session for the new day if state is still active
        # (the caller will handle this in the state transition logic,
        #  but we need to set up for it)

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
