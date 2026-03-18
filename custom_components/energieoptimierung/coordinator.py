"""
Data coordinator for Energieoptimierung.

Loads hourly consumption averages from recorder long-term statistics once,
shared by all sensors. Also provides Solcast PV forecast lookup.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


class VerbrauchsCoordinator:
    """Shared data coordinator that loads statistics and provides forecasts."""

    def __init__(
        self,
        hass: HomeAssistant,
        consumption_sensor: str,
        heizstab_sensor: str,
        wallbox_sensor: str,
        lookback_weeks: int,
    ) -> None:
        """Initialize."""
        self.hass = hass
        self._consumption_id = consumption_sensor
        self._heizstab_id = heizstab_sensor
        self._wallbox_id = wallbox_sensor
        self._lookback_weeks = lookback_weeks

        # Hourly averages: {day_type: {hour: avg_watts_without_heizstab_and_wallbox}}
        self.hourly_avg: dict[str, dict[int, float]] = {}
        self.stats_count: int = 0

    async def async_update(self) -> None:
        """Reload hourly averages from recorder statistics."""
        now = dt_util.now()
        start = now - timedelta(weeks=self._lookback_weeks)

        _LOGGER.warning(
            "Loading statistics from %s to %s for %s, %s, %s",
            start.isoformat(), now.isoformat(),
            self._consumption_id, self._heizstab_id, self._wallbox_id,
        )

        stats = await self._async_get_statistics(start, now)

        if stats is None:
            _LOGGER.warning("Failed to load statistics - no data returned")
            return

        consumption_stats = stats.get(self._consumption_id, [])
        heizstab_stats = stats.get(self._heizstab_id, [])
        wallbox_stats = stats.get(self._wallbox_id, [])

        _LOGGER.warning(
            "Got %d consumption, %d heizstab, %d wallbox entries",
            len(consumption_stats), len(heizstab_stats), len(wallbox_stats),
        )

        if not consumption_stats:
            _LOGGER.warning(
                "No consumption statistics found for '%s'. "
                "Available keys: %s",
                self._consumption_id,
                list(stats.keys()),
            )
            return

        # Index Heizstab and Wallbox by timestamp
        heizstab_by_ts: dict[float, float] = {}
        for entry in heizstab_stats:
            ts = entry.get("start") or entry.get("start_ts")
            mean = entry.get("mean")
            if ts is not None and mean is not None:
                heizstab_by_ts[ts] = mean

        wallbox_by_ts: dict[float, float] = {}
        for entry in wallbox_stats:
            ts = entry.get("start") or entry.get("start_ts")
            mean = entry.get("mean")
            if ts is not None and mean is not None:
                wallbox_by_ts[ts] = mean

        # Day type zones:
        #   "mo-do"  = Monday-Thursday (0-3)
        #   "fr"     = Friday (4)
        #   "sa"     = Saturday (5)
        #   "so"     = Sunday (6)
        DAY_ZONES = {0: "mo-do", 1: "mo-do", 2: "mo-do", 3: "mo-do",
                     4: "fr", 5: "sa", 6: "so"}

        accum: dict[str, dict[int, list[float]]] = {
            zone: {h: [] for h in range(24)}
            for zone in ("mo-do", "fr", "sa", "so")
        }

        for entry in consumption_stats:
            ts = entry.get("start") or entry.get("start_ts")
            mean = entry.get("mean")
            if ts is None or mean is None:
                continue

            if isinstance(ts, (int, float)):
                local_dt = dt_util.as_local(
                    datetime.fromtimestamp(ts, tz=timezone.utc)
                )
            elif isinstance(ts, str):
                local_dt = dt_util.as_local(
                    datetime.fromisoformat(ts)
                )
            else:
                continue

            hour = local_dt.hour
            zone = DAY_ZONES[local_dt.weekday()]

            heizstab_mean = heizstab_by_ts.get(ts, 0.0)
            wallbox_mean = wallbox_by_ts.get(ts, 0.0)
            net_mean = max(mean - heizstab_mean - wallbox_mean, 0.0)
            accum[zone][hour].append(net_mean)

        # Calculate averages with fallback chain
        # fr → mo-do, sa → so, so → sa, mo-do → fr
        FALLBACKS = {
            "mo-do": ["fr", "sa", "so"],
            "fr": ["mo-do", "sa", "so"],
            "sa": ["so", "fr", "mo-do"],
            "so": ["sa", "fr", "mo-do"],
        }

        result: dict[str, dict[int, float]] = {}
        for zone in ("mo-do", "fr", "sa", "so"):
            result[zone] = {}
            for hour in range(24):
                values = accum[zone][hour]
                if values:
                    result[zone][hour] = sum(values) / len(values)
                else:
                    # Try fallbacks
                    found = False
                    for fb in FALLBACKS[zone]:
                        fb_values = accum[fb][hour]
                        if fb_values:
                            result[zone][hour] = sum(fb_values) / len(fb_values)
                            found = True
                            break
                    if not found:
                        result[zone][hour] = 0.0

        self.hourly_avg = result
        self.stats_count = len(consumption_stats)

        _LOGGER.info(
            "Loaded %d consumption, %d heizstab, %d wallbox stats. "
            "Sample weekday 00:00=%.0fW, weekend 12:00=%.0fW",
            len(consumption_stats), len(heizstab_stats), len(wallbox_stats),
            result.get("weekday", {}).get(0, 0),
            result.get("weekend", {}).get(12, 0),
        )

    async def _async_get_statistics(
        self, start: datetime, end: datetime
    ) -> dict[str, list[dict]] | None:
        """Get statistics using multiple fallback approaches."""

        # Approach 1: Use the websocket command handler (most reliable)
        try:
            stats = await self._async_get_stats_via_ws(start, end)
            if stats:
                _LOGGER.warning("Statistics loaded via WS approach")
                return stats
        except Exception:
            _LOGGER.warning("WS approach failed, trying direct import", exc_info=True)

        # Approach 2: Direct import with async_add_executor_job
        try:
            stats = await self._async_get_stats_via_recorder(start, end)
            if stats:
                _LOGGER.warning("Statistics loaded via recorder approach")
                return stats
        except Exception:
            _LOGGER.warning("Recorder approach failed", exc_info=True)

        _LOGGER.error("All approaches to load statistics failed")
        return None

    async def _async_get_stats_via_ws(
        self, start: datetime, end: datetime
    ) -> dict[str, list[dict]] | None:
        """Get statistics via the internal websocket command handler."""
        from homeassistant.components.recorder.websocket_api import (
            ws_handle_get_statistics_during_period,
        )
        # This won't work directly, use the component's API instead
        raise NotImplementedError("Trying next approach")

    async def _async_get_stats_via_recorder(
        self, start: datetime, end: datetime
    ) -> dict[str, list[dict]] | None:
        """Get statistics via recorder component."""
        from homeassistant.components.recorder import get_instance

        # Try importing the function - name may vary by HA version
        try:
            from homeassistant.components.recorder.statistics import (
                statistics_during_period,
            )
        except ImportError:
            _LOGGER.error("Cannot import statistics_during_period")
            return None

        statistic_ids = {self._consumption_id, self._heizstab_id, self._wallbox_id}

        # Try calling - it might be sync (needs executor) or async
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(statistics_during_period):
            _LOGGER.warning("statistics_during_period is async")
            stats = await statistics_during_period(
                self.hass,
                start,
                end,
                statistic_ids,
                "hour",
                None,
                {"mean"},
            )
        else:
            _LOGGER.warning("statistics_during_period is sync, using executor")
            recorder_instance = get_instance(self.hass)
            stats = await recorder_instance.async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                end,
                statistic_ids,
                "hour",
                None,
                {"mean"},
            )

        _LOGGER.warning(
            "statistics_during_period returned type=%s, keys=%s, "
            "consumption entries=%d",
            type(stats).__name__,
            list(stats.keys()) if isinstance(stats, dict) else "N/A",
            len(stats.get(self._consumption_id, [])) if isinstance(stats, dict) else 0,
        )

        return stats if isinstance(stats, dict) else None

    # ── Hourly Calculation ───────────────────────────────────────────────

    def calculate_period(
        self, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Calculate consumption forecast for an arbitrary time period."""
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

            day_zone = {0:"mo-do",1:"mo-do",2:"mo-do",3:"mo-do",
                        4:"fr",5:"sa",6:"so"}[current.weekday()]
            avg_watts = self.hourly_avg.get(day_zone, {}).get(hour, 0.0)

            kwh = (avg_watts * fraction) / 1000.0
            total_kwh += kwh

            hourly_details.append({
                "stunde": f"{hour:02d}:00",
                "zone": day_zone,
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
        return {
            "verbrauch_kwh": 0.0,
            "stunden": 0.0,
            "stundenprofil": [],
        }
