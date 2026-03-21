"""Consumption profile coordinator for EEG Energy Optimizer.

Loads hourly consumption averages from HA recorder long-term statistics,
grouped by 7 individual weekdays (mo/di/mi/do/fr/sa/so). Provides
calculate_period() to forecast consumption for arbitrary time ranges.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .const import WEEKDAY_KEYS

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Timezone conversion - imported at module level for easy test patching
try:
    from homeassistant.util import dt as dt_util

    _as_local = dt_util.as_local
    _now = dt_util.now
except ImportError:
    _as_local = lambda dt: dt  # noqa: E731
    _now = lambda: datetime.now(tz=timezone.utc)  # noqa: E731

# Lazy imports for recorder (only available at runtime in HA)
statistics_during_period = None
get_instance = None

# Fallback chain when a weekday has no data for a given hour
FALLBACKS: dict[str, list[str]] = {
    "mo": ["di", "mi", "do", "fr"],
    "di": ["mo", "mi", "do", "fr"],
    "mi": ["di", "do", "mo", "fr"],
    "do": ["mi", "di", "mo", "fr"],
    "fr": ["do", "sa", "mo"],
    "sa": ["so", "fr"],
    "so": ["sa", "fr"],
}


def _ensure_recorder_imports() -> None:
    """Lazy-import recorder functions (not available during tests without HA)."""
    global statistics_during_period, get_instance  # noqa: PLW0603
    if statistics_during_period is not None:
        return
    try:
        from homeassistant.components.recorder import get_instance as _gi
        from homeassistant.components.recorder.statistics import (
            statistics_during_period as _sdp,
        )

        statistics_during_period = _sdp
        get_instance = _gi
    except ImportError:
        _LOGGER.warning("Recorder not available - statistics will not be loaded")


class ConsumptionCoordinator:
    """Loads hourly averages from recorder, grouped by 7 individual weekdays."""

    def __init__(
        self,
        hass: HomeAssistant,
        consumption_sensor: str,
        lookback_weeks: int,
    ) -> None:
        self.hass = hass
        self._consumption_id = consumption_sensor
        self._lookback_weeks = lookback_weeks

        # {weekday: {hour: avg_watts}} e.g. {"mo": {0: 350.0, ...}, ...}
        self.hourly_avg: dict[str, dict[int, float]] = {}
        self.stats_count: int = 0

    async def async_update(self) -> None:
        """Reload hourly averages from recorder statistics."""
        _ensure_recorder_imports()

        if get_instance is None or statistics_during_period is None:
            _LOGGER.error("Recorder imports not available, cannot load statistics")
            self._init_empty()
            return

        now = _now()
        start = now - timedelta(weeks=self._lookback_weeks)

        stats = await self._async_load_statistics(start, now)
        entries = stats.get(self._consumption_id, [])

        if not entries:
            _LOGGER.warning(
                "No consumption statistics for '%s'. Available: %s",
                self._consumption_id,
                list(stats.keys()) if stats else "none",
            )
            self._init_empty()
            self.stats_count = 0
            return

        self._process_entries(entries)

    async def _async_load_statistics(
        self, start: datetime, end: datetime
    ) -> dict[str, list[dict]]:
        """Load statistics from recorder."""
        recorder_instance = get_instance(self.hass)

        result = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            self.hass,
            start,
            end,
            {self._consumption_id},
            "hour",
            None,
            {"mean"},
        )

        return result if isinstance(result, dict) else {}

    def _process_entries(self, entries: list[dict]) -> None:
        """Process statistics entries into hourly averages by weekday."""
        # Accumulate values: {weekday: {hour: [watts, ...]}}
        accum: dict[str, dict[int, list[float]]] = {
            day: {h: [] for h in range(24)} for day in WEEKDAY_KEYS
        }

        for entry in entries:
            ts = entry.get("start") or entry.get("start_ts")
            mean = entry.get("mean")
            if ts is None or mean is None:
                continue

            if isinstance(ts, (int, float)):
                local_dt = _as_local(
                    datetime.fromtimestamp(ts, tz=timezone.utc)
                )
            elif isinstance(ts, str):
                local_dt = _as_local(datetime.fromisoformat(ts))
            else:
                continue

            weekday_key = WEEKDAY_KEYS[local_dt.weekday()]
            accum[weekday_key][local_dt.hour].append(mean)

        # Calculate averages with fallback chain
        result: dict[str, dict[int, float]] = {}
        for day in WEEKDAY_KEYS:
            result[day] = {}
            for hour in range(24):
                values = accum[day][hour]
                if values:
                    result[day][hour] = sum(values) / len(values)
                else:
                    # Try fallback chain
                    found = False
                    for fb_day in FALLBACKS[day]:
                        fb_values = accum[fb_day][hour]
                        if fb_values:
                            result[day][hour] = sum(fb_values) / len(fb_values)
                            found = True
                            break
                    if not found:
                        result[day][hour] = 0.0

        self.hourly_avg = result
        self.stats_count = len(entries)

        _LOGGER.info(
            "Loaded %d consumption statistics. Sample mo[0]=%.0fW, sa[12]=%.0fW",
            len(entries),
            result.get("mo", {}).get(0, 0),
            result.get("sa", {}).get(12, 0),
        )

    def _init_empty(self) -> None:
        """Initialize hourly_avg with zeros for all weekdays/hours."""
        self.hourly_avg = {
            day: {h: 0.0 for h in range(24)} for day in WEEKDAY_KEYS
        }

    def calculate_period(
        self, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Calculate consumption forecast for an arbitrary time period.

        Walks hour-by-hour from start to end, looking up the average
        watts for each weekday+hour combination. Handles partial hours.

        Returns dict with verbrauch_kwh, stunden, stundenprofil.
        """
        if end <= start:
            return self._empty_result()

        hours_total = (end - start).total_seconds() / 3600.0
        hourly_details: list[dict[str, Any]] = []
        total_kwh = 0.0

        current = start.replace(minute=0, second=0, microsecond=0)

        while current < end:
            hour = current.hour
            next_hour = current + timedelta(hours=1)

            slot_start = max(current, start)
            slot_end = min(next_hour, end)
            fraction = (slot_end - slot_start).total_seconds() / 3600.0

            if fraction <= 0:
                current = next_hour
                continue

            weekday_key = WEEKDAY_KEYS[current.weekday()]
            avg_watts = self.hourly_avg.get(weekday_key, {}).get(hour, 0.0)

            kwh = (avg_watts * fraction) / 1000.0
            total_kwh += kwh

            hourly_details.append({
                "stunde": f"{hour:02d}:00",
                "wochentag": weekday_key,
                "anteil": round(fraction, 2),
                "verbrauch_w": round(avg_watts),
                "kwh": round(kwh, 3),
            })

            current = next_hour

        return {
            "verbrauch_kwh": round(total_kwh, 2),
            "stunden": round(hours_total, 1),
            "stundenprofil": hourly_details,
        }

    @staticmethod
    def _empty_result() -> dict[str, Any]:
        """Return empty calculation result."""
        return {
            "verbrauch_kwh": 0.0,
            "stunden": 0.0,
            "stundenprofil": [],
        }
