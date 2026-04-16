# Quick Task: PeakShare-basierte Abend-Entladung - Research

**Researched:** 2026-04-16
**Domain:** REST API integration, sliding window algorithm, HA caching
**Confidence:** HIGH

## Summary

The PeakShare API is a public, unauthenticated REST endpoint returning hourly community grid import deficit forecasts for 24 hours ahead. The response is well-structured, stable, and directly usable for discharge window optimization. The integration requires: (1) an `aiohttp`-based fetcher with `Store`-backed caching, (2) a sliding window algorithm to find the optimal contiguous discharge window, (3) new config keys + migration for PeakShare mode, and (4) terminology cleanup from "Nachteinspeisung" to "Abend-Entladung".

**Primary recommendation:** Implement a `PeakShareProvider` class that fetches + caches API data, and a `find_discharge_window()` function that computes the optimal start time. Hook into `_should_discharge()` by replacing the fixed `discharge_start_h/m` with the computed window start.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- "Abend-Entladung" als einheitlicher Begriff (ersetzt "Nachteinspeisung" etc.)
- PeakShare-Checkbox: "PeakShare-Bedarfssteuerung" default=aktiviert
- Wenn PeakShare aktiv: Startzeit und Entladeleistung-Felder ausgeblendet, Community-Dropdown stattdessen
- Wenn PeakShare deaktiviert: klassischer Modus mit fixer Startzeit
- API Endpoint: GET https://peakshare.app/api/public/community-grid-import-forecast
- Alle 6h abfragen, 24h max Cache, Fallback auf fixe Startzeit (Default 20:00)
- Fensterberechnung: Energie / Leistung = Stunden, zusammenhangendes Fenster mit hochstem Bedarf
- Einmalige Entscheidung rund um Sonnenuntergang, kein standiges An/Aus
- Jitter: +/-60 Min zufalliger Offset, einmal pro Tag
- Entladeleistung: konfigurierbar, Default 5 kW
- Fallback: PeakShare-Daten > Cache (24h) > fixe Startzeit (20:00)
- Bestandteile die bleiben: STATE_ABEND_ENTLADUNG (const.py), "evening" (interner Code-Key)

### Claude's Discretion
(not explicitly separated in CONTEXT.md -- implementation details)

### Deferred Ideas (OUT OF SCOPE)
(none specified)
</user_constraints>

## PeakShare API Analysis

**Source:** Live API fetch on 2026-04-16 [VERIFIED: direct HTTP request]

### Response Structure

```json
{
  "communities": [
    {
      "name": "BEG",
      "hours": [
        {"timestamp": "2026-04-16T14:00:00.000Z", "deficitKwh": 0},
        {"timestamp": "2026-04-16T15:00:00.000Z", "deficitKwh": 95.6477052},
        ...
      ],
      "xTenant": "CC100283",
      "warnings": [],
      "sourceDays": ["2026-03-26", "2026-03-27", ...]
    },
    ...
  ],
  "generatedAt": "2026-04-16T12:59:41.818Z",
  "windowStart": "2026-04-16T14:00:00.000Z",
  "windowEndExclusive": "2026-04-17T14:00:00.000Z"
}
```

### Key Properties

| Property | Value | Notes |
|----------|-------|-------|
| Time resolution | **Hourly** (1h buckets) | 24 entries per community |
| Forecast window | **24 hours** from `windowStart` to `windowEndExclusive` | Rolling, regenerated periodically |
| `deficitKwh` unit | **kWh** per hour | Community-level grid import deficit, NOT per-household |
| `deficitKwh` range | 0 to ~1300 (BEG) | 0 during daytime (PV covers demand), peaks in evening/morning |
| Timestamps | ISO 8601 UTC with milliseconds | `2026-04-16T14:00:00.000Z` |
| Communities (current) | 11 | BEG, Bad_Hall, EEG Steyr Sud, FHW, GEA ATSV Stein, GEA Nettingsdorferstr, GEA Wild-Strome, Horsching, Marchtrenk, Pucking, Wegscheid |
| Authentication | **None** (public endpoint) | Returns 403 via WebFetch but 200 with User-Agent header |
| `warnings` | Array (observed empty) | May contain API-level warnings |
| `sourceDays` | Array of date strings | Days used to compute the forecast |

### Demand Pattern (BEG example, 2026-04-16)

```
14:00 UTC (16:00 CEST):    0 kWh      -- PV still active
15:00 UTC (17:00 CEST):   95.6 kWh    -- PV declining
16:00 UTC (18:00 CEST):  363.6 kWh    -- evening ramp
17:00 UTC (19:00 CEST):  656.9 kWh    -- 
18:00 UTC (20:00 CEST):  713.4 kWh    -- PEAK
19:00 UTC (21:00 CEST):  627.5 kWh    --
20:00 UTC (22:00 CEST):  519.3 kWh    -- declining
...
03:00 UTC (05:00 CEST):  819.2 kWh    -- morning ramp
04:00 UTC (06:00 CEST): 1187.5 kWh    --
05:00 UTC (07:00 CEST): 1329.8 kWh    -- MORNING PEAK
06:00 UTC (08:00 CEST):  745.9 kWh    -- PV starting
07:00 UTC (09:00 CEST):    0 kWh      -- PV covers demand
```

**Important insight:** The evening peak (18:00-19:00 UTC = 20:00-21:00 CEST) is significant but the morning peak (05:00-06:00 UTC) is even larger. The sliding window algorithm will naturally find the best contiguous block. For batteries with limited capacity, the evening peak is the right target since the user wants "Abend-Entladung" (and morning is already handled by Morgen-Einspeisung). The algorithm should be constrained to the discharge window (sunset to sunrise/04:00).

### API Reliability Considerations

- The `User-Agent` header is **required** -- bare requests return 403 [VERIFIED: WebFetch failed, curl with UA succeeded]
- Response is ~15KB for 11 communities (lightweight)
- `generatedAt` field allows staleness detection

## Sliding Window Algorithm

### Algorithm Design

Given:
- `available_kwh`: battery energy available for discharge (SOC - min_SOC) * capacity
- `discharge_power_kw`: configured discharge rate (default 5 kW)
- `hours[]`: array of `{timestamp, deficitKwh}` for the selected community
- Window constraints: only consider hours between sunset and 04:00 (hard cutoff)

```python
def find_discharge_window(
    hours: list[dict],           # PeakShare hourly data
    available_kwh: float,        # available energy for discharge
    discharge_power_kw: float,   # configured discharge power
    window_start: datetime,      # sunset (or current time if past sunset)
    window_end: datetime,        # 04:00 next day (hard cutoff)
    jitter_minutes: int,         # pre-rolled jitter for today
) -> tuple[datetime, datetime] | None:
    """Find optimal contiguous discharge window.
    
    Returns (start_time, end_time) or None if no valid window.
    """
    # 1. Calculate required hours
    required_hours = math.ceil(available_kwh / discharge_power_kw)
    
    # 2. Filter hours to discharge window (sunset to 04:00)
    eligible = [h for h in hours 
                if window_start <= parse(h["timestamp"]) < window_end
                and h["deficitKwh"] > 0]
    
    # 3. Sliding window: find contiguous block of required_hours
    #    with maximum sum of deficitKwh
    if len(eligible) < required_hours:
        return None  # not enough hours with demand
    
    # Since hours are already hourly and contiguous in the API,
    # use a simple sliding window on the full eligible range
    best_start = 0
    best_sum = 0
    current_sum = sum(eligible[i]["deficitKwh"] for i in range(required_hours))
    best_sum = current_sum
    
    for i in range(1, len(eligible) - required_hours + 1):
        current_sum -= eligible[i - 1]["deficitKwh"]
        current_sum += eligible[i + required_hours - 1]["deficitKwh"]
        if current_sum > best_sum:
            best_sum = current_sum
            best_start = i
    
    # 4. Apply jitter
    start_time = parse(eligible[best_start]["timestamp"])
    start_time += timedelta(minutes=jitter_minutes)
    end_time = start_time + timedelta(hours=required_hours)
    
    return (start_time, end_time)
```

### Edge Cases

| Case | Handling |
|------|----------|
| `required_hours` > eligible hours | Return None, fall back to fixed start time |
| `required_hours` < 1 | Minimum 1 hour window |
| Fractional hours (e.g., 3.4h from 17kWh/5kW) | `math.ceil()` -- round up to guarantee full discharge |
| All `deficitKwh` = 0 in window | Return None (no community demand) |
| API returns 0 communities | Return None, fall back |
| Jitter pushes start before sunset | Clamp to sunset |
| Jitter pushes end past 04:00 | Allow it -- the optimizer's 04:00 hard cutoff will stop discharge anyway |

### Complexity

O(n) where n = number of eligible hours (max 24). Trivial computation.

## Caching Strategy

### Implementation Pattern

Use `homeassistant.helpers.storage.Store` (already used by activity log and feed-in stats in this project) combined with an in-memory cache with TTL tracking.

```python
class PeakShareProvider:
    """Fetches and caches PeakShare community grid import forecasts."""
    
    def __init__(self, hass, entry_id):
        self._hass = hass
        self._store = Store(hass, 1, f"{DOMAIN}_{entry_id}_peakshare")
        self._cache: dict | None = None        # in-memory cache
        self._cache_time: datetime | None = None  # when fetched
        self._jitter_today: int | None = None   # today's jitter (minutes)
        self._jitter_date: str | None = None    # date for which jitter was rolled
    
    async def async_load(self):
        """Load persisted cache on startup."""
        stored = await self._store.async_load()
        if stored:
            self._cache = stored.get("data")
            self._cache_time = datetime.fromisoformat(stored["fetched_at"])
    
    async def async_fetch(self) -> dict | None:
        """Fetch fresh data if cache is stale (>6h)."""
        now = utcnow()
        if self._cache_time and (now - self._cache_time).total_seconds() < 6 * 3600:
            return self._cache  # still fresh
        
        try:
            session = async_get_clientsession(self._hass)
            async with session.get(
                "https://peakshare.app/api/public/community-grid-import-forecast",
                headers={"User-Agent": "HomeAssistant/EEGEnergyOptimizer"},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._cache = data
                    self._cache_time = now
                    await self._store.async_save({
                        "data": data,
                        "fetched_at": now.isoformat(),
                    })
                    return data
        except Exception:
            _LOGGER.warning("PeakShare API fetch failed, using cache")
        
        # Fallback: cached data if < 24h old
        if self._cache_time and (now - self._cache_time).total_seconds() < 24 * 3600:
            return self._cache
        return None  # cache expired, API down -> trigger fixed-time fallback
    
    def get_jitter_today(self) -> int:
        """Get today's jitter offset in minutes (rolled once per day)."""
        today = date.today().isoformat()
        if self._jitter_date != today:
            self._jitter_today = random.randint(-60, 60)
            self._jitter_date = today
        return self._jitter_today
```

### HTTP Client in HA [VERIFIED: HA documentation pattern]

```python
from homeassistant.helpers.aiohttp_client import async_get_clientsession
```

This returns the shared `aiohttp.ClientSession` managed by HA. No need to create/close our own session.

### Cache Lifecycle

| Event | Action |
|-------|--------|
| Integration startup | Load from Store |
| Every 6h (or first cycle after 6h) | Re-fetch from API |
| API failure | Use cached data (if < 24h) |
| Cache > 24h AND API down | Return None -> fallback to fixed start time |
| Config change (reload) | Provider survives hot-reload via `data` dict |

### When to Fetch

The fetch should happen lazily: when `_should_discharge()` needs PeakShare data and the cache is stale (>6h), trigger a fetch. This avoids periodic timers and keeps the implementation simple. Since the optimizer runs every 30 seconds, the first cycle needing PeakShare data will trigger the fetch.

**Important:** The fetch is async (HTTP call), but `_should_discharge()` is currently synchronous. The PeakShare provider should be pre-fetched in `async_run_cycle()` (which is already async) before calling `_evaluate()`.

## Integration with Existing Optimizer

### Decision Flow Changes

Current flow in `_should_discharge()`:
1. Check `enable_night_discharge`
2. Check time >= `discharge_start`
3. Check SOC > min_soc
4. Check PV tomorrow >= demand

New flow with PeakShare:
1. Check `enable_night_discharge`
2. **If PeakShare enabled:**
   a. Get PeakShare discharge plan (computed once around sunset)
   b. Check if current time is within computed window
   c. If no plan available -> fallback to fixed start time check
3. **If PeakShare disabled:** Check time >= `discharge_start` (unchanged)
4. Check SOC > min_soc (unchanged)
5. Check PV tomorrow >= demand (unchanged)

### Decision Timing ("Einmalige Entscheidung")

The discharge window should be computed once per day, around sunset. Implementation approach:

```python
# In optimizer __init__:
self._peakshare_plan: tuple[datetime, datetime] | None = None
self._peakshare_plan_date: str | None = None

# In _should_discharge() or a helper:
def _get_discharge_window(self, snap: Snapshot) -> tuple[int, int] | None:
    """Get discharge start hour/minute for today.
    
    PeakShare: compute window once per day (after sunset data available).
    Returns (hour, minute) or None for fallback.
    """
    today_str = snap.now.strftime("%Y-%m-%d")
    if self._peakshare_plan_date == today_str:
        return self._peakshare_plan  # already computed today
    
    # Not yet computed: check if we're near/past sunset
    if snap.sunset_today and snap.now >= snap.sunset_today - timedelta(minutes=30):
        # Compute window
        plan = find_discharge_window(...)
        self._peakshare_plan = plan
        self._peakshare_plan_date = today_str
        return plan
    
    return None  # too early, no plan yet
```

### Config Keys (New)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enable_peakshare` | bool | `true` | PeakShare-Bedarfssteuerung aktiv |
| `peakshare_community` | str | `"BEG"` | Selected community name |
| `discharge_power_kw` | float | `5.0` | (existing key, change default from 3.0 to 5.0) |

**Config migration:** Version 12 -- add `enable_peakshare=True`, `peakshare_community="BEG"`, update `discharge_power_kw` default to 5.0 for new installs.

Note: `discharge_start_time` and `discharge_power_kw` remain as they are used for fallback mode and the discharge execution.

### Entladeleistung Visibility Logic

Per CONTEXT.md decision:
- PeakShare active: hide `discharge_start_time` and `discharge_power_kw` fields in Settings UI
- PeakShare inactive: show both fields (classic mode)

However, `discharge_power_kw` is still needed for window calculation even in PeakShare mode. The UI hides the field but the value (default 5 kW) is still used internally.

**Correction:** Re-reading CONTEXT.md -- "Wenn aktiv: Felder Startzeit der Entladung und Entladeleistung NICHT eingeblendet". This means in PeakShare mode the user does not configure these, they use defaults (5 kW discharge, computed start time). The `discharge_power_kw` config should still exist for PeakShare mode window calculation but use the default 5 kW.

## Terminology Rename Scope

### Files to Change

| File | Occurrences | What to Change |
|------|-------------|----------------|
| `optimizer.py:669` | 1 | `"Nachteinspeisung deaktiviert"` -> `"Abend-Entladung deaktiviert"` |
| `optimizer.py:676` | 1 | `"Nachtverbrauch zu hoch"` -> keep or update (this refers to overnight consumption, not the feature name) |
| `frontend/eeg-optimizer-panel.js` | ~8 | `"Nachteinspeisung"` -> `"Abend-Entladung"` in Wizard, Settings, Dashboard, Help |
| `frontend/evening-discharge.svg:96` | 1 | `"Nachtverbrauch"` -> acceptable (describes overnight consumption, not feature) |
| `CLAUDE.md` | Various | Update terminology references |

### What Stays Unchanged

- `CONF_ENABLE_NIGHT_DISCHARGE = "enable_night_discharge"` -- internal config key, kept for backward compatibility
- `STATE_ABEND_ENTLADUNG` -- already correct
- `"evening"` -- internal stats key, stays
- `Nachtverbrauch` -- describes overnight household consumption, not the feature. Could keep as-is or rename to "Uebernachtverbrauch" for clarity. [ASSUMED: "Nachtverbrauch" is acceptable since it describes consumption, not the feature]

## Common Pitfalls

### Pitfall 1: Synchronous HTTP in Optimizer Cycle
**What goes wrong:** `_should_discharge()` is synchronous but PeakShare fetch needs async HTTP.
**How to avoid:** Pre-fetch PeakShare data in `async_run_cycle()` (already async) and pass it into the evaluation. The provider's `async_fetch()` should be called before `_evaluate()`.

### Pitfall 2: API Returns 403 Without User-Agent
**What goes wrong:** Default `aiohttp` requests may not include a User-Agent.
**How to avoid:** Always set `User-Agent: HomeAssistant/EEGEnergyOptimizer` header.

### Pitfall 3: Timezone Confusion
**What goes wrong:** API returns UTC timestamps, optimizer works in local time (CEST/CET).
**How to avoid:** Parse API timestamps as UTC, convert to local time for window comparison. Use `dt_util.as_local()`.

### Pitfall 4: Jitter Re-rolling on Every Restart
**What goes wrong:** If HA restarts, jitter is re-rolled. If discharge already started with old jitter, new jitter could shift the window.
**How to avoid:** Persist jitter in the Store alongside cache data. Only re-roll at date boundary.

### Pitfall 5: Race Between Sunset Decision and Optimizer Cycle
**What goes wrong:** The "compute once around sunset" logic runs in the 30-second cycle. If sunset changes slightly between cycles, multiple computations could occur.
**How to avoid:** Lock computation to date (`_peakshare_plan_date`). Once computed for today, don't recompute.

## New File Structure

```
custom_components/eeg_energy_optimizer/
  peakshare.py          # NEW: PeakShareProvider + find_discharge_window()
  optimizer.py          # MODIFIED: integrate PeakShare into _should_discharge()
  const.py              # MODIFIED: new config keys
  __init__.py           # MODIFIED: create PeakShareProvider, migration v12
  websocket_api.py      # MODIFIED: expose community list for panel dropdown
  frontend/eeg-optimizer-panel.js  # MODIFIED: PeakShare checkbox, community dropdown, terminology
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | "Nachtverbrauch" is acceptable terminology since it describes consumption, not the feature | Terminology | Low -- only UI label clarity |
| A2 | API will continue to be available without authentication | API Analysis | Medium -- if auth is added, needs adaptation |
| A3 | `discharge_power_kw` default change from 3.0 to 5.0 only affects new installs | Config Keys | Low -- existing installs keep their configured value via migration |

## Sources

### Primary (HIGH confidence)
- PeakShare API live response -- fetched 2026-04-16T12:59:41Z [VERIFIED: direct HTTP request]
- Existing codebase: optimizer.py, const.py, __init__.py, statistics.py [VERIFIED: file reads]

### Secondary (MEDIUM confidence)
- `homeassistant.helpers.aiohttp_client.async_get_clientsession` -- standard HA pattern [ASSUMED: based on HA documentation patterns from training data]
- `homeassistant.helpers.storage.Store` -- verified via existing usage in project [VERIFIED: statistics.py, __init__.py]

## Metadata

**Confidence breakdown:**
- PeakShare API structure: HIGH -- verified via live request
- Sliding window algorithm: HIGH -- well-understood CS problem
- Caching strategy: HIGH -- follows existing project patterns
- Integration approach: HIGH -- based on reading actual optimizer code
- Terminology scope: HIGH -- grep verified all occurrences

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (API structure could change; re-verify if implementation delayed)
