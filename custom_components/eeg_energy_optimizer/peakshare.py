"""PeakShare community grid import forecast provider.

Fetches hourly community demand forecasts from the PeakShare API and provides
a sliding-window algorithm to find the optimal contiguous evening discharge
window where community demand is highest.
"""

from __future__ import annotations

import logging
import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from homeassistant.helpers.storage import Store
    from homeassistant.util import dt as dt_util

    _utcnow = dt_util.utcnow
    _as_local = dt_util.as_local
except ImportError:
    _utcnow = lambda: datetime.now(tz=timezone.utc)  # noqa: E731
    _as_local = lambda dt: dt  # noqa: E731
    async_get_clientsession = None  # type: ignore[assignment]
    Store = None  # type: ignore[assignment,misc]


PEAKSHARE_API_URL = (
    "https://peakshare.app/api/public/community-grid-import-forecast"
)
PEAKSHARE_USER_AGENT = "HomeAssistant/EEGEnergyOptimizer"

# Cache freshness thresholds
CACHE_FRESH_SECONDS = 6 * 3600   # re-fetch after 6 hours
CACHE_MAX_SECONDS = 24 * 3600    # discard cache after 24 hours


def find_discharge_window(
    hours: list[dict],
    available_kwh: float,
    discharge_power_kw: float,
    window_start: datetime,
    window_end: datetime,
    jitter_minutes: int,
) -> tuple[datetime, datetime] | None:
    """Find the optimal contiguous discharge window using a sliding window.

    Scans the PeakShare hourly forecast data for the contiguous block of
    ``required_hours`` with the highest sum of ``deficitKwh``, constrained
    to the discharge window (sunset to 04:00).

    Args:
        hours: PeakShare hourly data (list of dicts with "timestamp" and
            "deficitKwh").
        available_kwh: Battery energy available for discharge.
        discharge_power_kw: Configured discharge power (kW).
        window_start: Earliest allowed discharge start (e.g. sunset).
        window_end: Latest allowed discharge end (hard cutoff, e.g. 04:00).
        jitter_minutes: Pre-rolled jitter offset in minutes for today.

    Returns:
        ``(start_time, end_time)`` tuple of timezone-aware datetimes, or
        ``None`` if no valid window can be formed.
    """
    if available_kwh <= 0 or discharge_power_kw <= 0:
        return None

    required_hours = max(1, math.ceil(available_kwh / discharge_power_kw))

    # Filter hours to eligible window — keep ALL hours (including deficit=0)
    # to preserve contiguity information for the sliding window.
    eligible: list[dict] = []
    for h in hours:
        ts_str = h.get("timestamp", "")
        deficit = h.get("deficitKwh", 0)
        if not ts_str or deficit is None:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            ts_local = _as_local(ts)
        except (ValueError, TypeError):
            continue
        if window_start <= ts_local < window_end:
            eligible.append({"ts": ts_local, "deficit": max(0.0, float(deficit))})

    if len(eligible) < required_hours:
        return None

    # Sort by timestamp to ensure chronological order
    eligible.sort(key=lambda e: e["ts"])

    # Sliding window: find contiguous block with maximum deficit sum.
    # Hours must be truly consecutive (1h apart) — skip windows with gaps.
    def _is_contiguous(start_idx: int, length: int) -> bool:
        """Check that all hours in the block are exactly 1h apart."""
        for j in range(start_idx, start_idx + length - 1):
            gap = (eligible[j + 1]["ts"] - eligible[j]["ts"]).total_seconds()
            if gap != 3600:
                return False
        return True

    best_sum = -1.0
    best_start = -1

    for i in range(len(eligible) - required_hours + 1):
        if not _is_contiguous(i, required_hours):
            continue
        window_sum = sum(eligible[i + k]["deficit"] for k in range(required_hours))
        if window_sum > best_sum:
            best_sum = window_sum
            best_start = i

    if best_start < 0:
        return None

    # Apply jitter to start time, clamped to window_start
    start_time = eligible[best_start]["ts"] + timedelta(minutes=jitter_minutes)
    if start_time < window_start:
        start_time = window_start
    end_time = start_time + timedelta(hours=required_hours)
    # Clamp end_time to window_end (04:00 hard cutoff)
    if end_time > window_end:
        end_time = window_end

    return (start_time, end_time)


def _validate_api_response(data: Any) -> bool:
    """Validate the structure of a PeakShare API response (T-kqk-02)."""
    if not isinstance(data, dict):
        return False
    communities = data.get("communities")
    if not isinstance(communities, list):
        return False
    for community in communities:
        if not isinstance(community, dict):
            return False
        if "name" not in community:
            return False
        comm_hours = community.get("hours")
        if not isinstance(comm_hours, list):
            return False
        for hour in comm_hours:
            if not isinstance(hour, dict):
                return False
            if "timestamp" not in hour or "deficitKwh" not in hour:
                return False
    return True


class PeakShareProvider:
    """Fetches and caches PeakShare community grid import forecasts."""

    def __init__(self, hass: Any, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        if Store is not None:
            self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}_peakshare")
        else:
            self._store = None  # type: ignore[assignment]
        self._cache: dict | None = None
        self._cache_time: datetime | None = None
        self._jitter_today: int | None = None
        self._jitter_date: str | None = None
        self._discharge_plan: tuple[datetime, datetime] | None = None
        self._discharge_plan_date: str | None = None

    async def async_load(self) -> None:
        """Load persisted cache from Store on startup."""
        if self._store is None:
            return
        try:
            stored = await self._store.async_load()
            if stored and isinstance(stored, dict):
                self._cache = stored.get("data")
                fetched_at = stored.get("fetched_at")
                if fetched_at:
                    self._cache_time = datetime.fromisoformat(fetched_at)
                # Restore persisted jitter so HA restarts don't re-roll
                self._jitter_today = stored.get("jitter_value")
                self._jitter_date = stored.get("jitter_date")
                _LOGGER.debug(
                    "PeakShare: loaded cache (fetched_at=%s, jitter=%s for %s)",
                    fetched_at,
                    self._jitter_today,
                    self._jitter_date,
                )
        except Exception:
            _LOGGER.debug("PeakShare: no persisted cache found")

    async def async_fetch(self) -> dict | None:
        """Fetch fresh data if cache is stale (>6h).

        Falls back to cached data if API fails (cache < 24h), or None if
        cache is expired. A 30-second timeout prevents blocking the
        optimizer cycle (T-kqk-03).
        """
        now = _utcnow()

        # Return cached data if still fresh
        if (
            self._cache_time
            and (now - self._cache_time).total_seconds() < CACHE_FRESH_SECONDS
        ):
            return self._cache

        # Attempt API fetch
        if async_get_clientsession is not None:
            try:
                import aiohttp

                session = async_get_clientsession(self._hass)
                async with session.get(
                    PEAKSHARE_API_URL,
                    headers={"User-Agent": PEAKSHARE_USER_AGENT},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # Validate response structure (T-kqk-02)
                        if not _validate_api_response(data):
                            _LOGGER.warning(
                                "PeakShare API: ungueltige Antwortstruktur, verwende Cache"
                            )
                        else:
                            self._cache = data
                            self._cache_time = now
                            # Invalidate discharge plan so it recalculates
                            # with fresh data on next cycle
                            self._discharge_plan = None
                            self._discharge_plan_date = None
                            if self._store is not None:
                                await self._store.async_save(
                                    {
                                        "data": data,
                                        "fetched_at": now.isoformat(),
                                        "jitter_value": self._jitter_today,
                                        "jitter_date": self._jitter_date,
                                    }
                                )
                            return data
                    else:
                        _LOGGER.warning(
                            "PeakShare API: HTTP %s, verwende Cache", resp.status
                        )
            except Exception:
                _LOGGER.warning("PeakShare API Abfrage fehlgeschlagen, verwende Cache")

        # Fallback: cached data if < 24h old
        if (
            self._cache_time
            and (now - self._cache_time).total_seconds() < CACHE_MAX_SECONDS
        ):
            return self._cache
        return None

    def get_communities(self) -> list[str]:
        """Return list of community names from cached data."""
        if not self._cache or not isinstance(self._cache, dict):
            return []
        communities = self._cache.get("communities", [])
        return [c["name"] for c in communities if isinstance(c, dict) and "name" in c]

    def get_jitter_today(self) -> int:
        """Get today's jitter offset in minutes (rolled once per day).

        The jitter is persisted in the Store alongside cache data so that
        HA restarts within the same day don't re-roll.
        """
        today = _as_local(_utcnow()).date().isoformat()
        if self._jitter_date != today:
            self._jitter_today = random.randint(-60, 60)
            self._jitter_date = today
            # Persist jitter asynchronously if possible
            if self._store is not None and self._cache_time is not None:
                # Fire-and-forget save to persist jitter
                self._hass.async_create_task(
                    self._store.async_save(
                        {
                            "data": self._cache,
                            "fetched_at": self._cache_time.isoformat(),
                            "jitter_value": self._jitter_today,
                            "jitter_date": self._jitter_date,
                        }
                    )
                )
        return self._jitter_today  # type: ignore[return-value]

    def get_discharge_plan(
        self,
        community: str,
        available_kwh: float,
        discharge_power_kw: float,
        sunset_time: datetime | None,
        now: datetime,
        discharge_start_lower_bound: datetime | None = None,
        next_sunrise: datetime | None = None,
    ) -> tuple[datetime, datetime] | None:
        """Compute discharge window, recalculating when fresh API data arrives.

        The plan is date-locked: once computed for today, it is cached until
        new API data invalidates it (see ``async_fetch``). Returns
        ``(start_time, end_time)`` or None.

        Args:
            discharge_start_lower_bound: Earliest allowed start (today's
                ``discharge_start_time`` resolved to a datetime). PeakShare
                may pick any later start, but never earlier. None = no extra
                bound, fall back to sunset.
            next_sunrise: Next sunrise as known by the snapshot — drives the
                dynamic hard cutoff (``min(04:00, sunrise − 1h)``). None =
                fixed 04:00 cutoff (legacy behaviour).
        """
        today_str = now.strftime("%Y-%m-%d")

        # Already computed today (and not invalidated by fresh fetch):
        # return cached plan
        if self._discharge_plan_date == today_str:
            return self._discharge_plan

        if sunset_time is None:
            return None

        # Find community data
        if not self._cache or not isinstance(self._cache, dict):
            return None
        communities = self._cache.get("communities", [])
        community_data = None
        for c in communities:
            if isinstance(c, dict) and c.get("name") == community:
                community_data = c
                break
        if community_data is None:
            _LOGGER.warning(
                "PeakShare: Community '%s' nicht in API-Daten gefunden", community
            )
            return None

        api_hours = community_data.get("hours", [])
        if not api_hours:
            return None

        # Window: max(sunset, discharge_start_time) bis dynamischer Hard-Cutoff.
        # Untergrenze sorgt dafür, dass PeakShare nicht vor der konfigurierten
        # Mindeststart-Uhrzeit startet — auch wenn das beste Bedarfsfenster
        # früher liegen würde. Späterer Start = präzisere Verbrauchsprognose.
        window_start = sunset_time
        if discharge_start_lower_bound is not None:
            window_start = max(window_start, discharge_start_lower_bound)

        # Dynamischer Hard-Cutoff: min(04:00 am Sunrise-Tag, sunrise − 1h).
        # Im Winter (Sonnenaufgang ~07:30) gewinnt das bis zu 2.5 h zusätzlichen
        # Korridor; im Sommer bleibt es bei ~03:30 (sunrise − 1h).
        from .optimizer import compute_hard_cutoff
        next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=1
        )
        # Anker für den 04:00-Fixwert ist der Folgetag; für die sunrise-1h-
        # Variante zählt der mitgegebene next_sunrise des Snapshots.
        window_end = compute_hard_cutoff(next_day, next_sunrise)

        # Edge-Case: Wenn die Untergrenze bereits nach Cutoff liegt (z.B. User
        # setzt discharge_start_time auf 05:00) → kein Fenster konstruierbar.
        if window_start >= window_end:
            _LOGGER.info(
                "PeakShare: Untergrenze %s liegt nach Hard-Cutoff %s — kein Fenster",
                window_start.strftime("%H:%M"),
                window_end.strftime("%H:%M"),
            )
            self._discharge_plan = None
            self._discharge_plan_date = today_str
            return None

        jitter = self.get_jitter_today()

        plan = find_discharge_window(
            api_hours,
            available_kwh,
            discharge_power_kw,
            window_start,
            window_end,
            jitter,
        )

        # Lock computation for today
        self._discharge_plan = plan
        self._discharge_plan_date = today_str

        if plan:
            _LOGGER.info(
                "PeakShare: Entladefenster berechnet %s - %s (Jitter: %+d Min, Community: %s)",
                plan[0].strftime("%H:%M"),
                plan[1].strftime("%H:%M"),
                jitter,
                community,
            )
        else:
            _LOGGER.info(
                "PeakShare: Kein geeignetes Entladefenster gefunden (Community: %s)",
                community,
            )

        return plan
