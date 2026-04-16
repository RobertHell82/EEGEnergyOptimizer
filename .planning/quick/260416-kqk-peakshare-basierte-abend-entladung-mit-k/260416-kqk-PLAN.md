---
phase: 260416-kqk
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/peakshare.py
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/optimizer.py
  - custom_components/eeg_energy_optimizer/websocket_api.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
  - CLAUDE.md
autonomous: true
requirements: []

must_haves:
  truths:
    - "PeakShare API wird alle 6h abgefragt und liefert Community-Bedarfsdaten"
    - "Optimizer berechnet einmalig um Sonnenuntergang ein optimales Entladefenster aus PeakShare-Daten"
    - "Jitter von +/-60 Minuten wird einmal pro Tag gewuerfelt und bleibt stabil"
    - "Bei PeakShare-Ausfall greift Fallback-Kette: Cache (24h) > fixe Startzeit"
    - "Settings zeigen PeakShare-Checkbox mit Community-Dropdown wenn aktiv"
    - "Alle Nachteinspeisung-Referenzen sind durch Abend-Entladung ersetzt"
    - "Upgrade von bestehenden Instanzen setzt enable_peakshare=True automatisch, ohne Konfigurationsverlust"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/peakshare.py"
      provides: "PeakShareProvider class + find_discharge_window() algorithm"
      min_lines: 100
    - path: "custom_components/eeg_energy_optimizer/const.py"
      provides: "CONF_ENABLE_PEAKSHARE, CONF_PEAKSHARE_COMMUNITY, updated DEFAULT_DISCHARGE_POWER_KW"
      contains: "CONF_ENABLE_PEAKSHARE"
    - path: "custom_components/eeg_energy_optimizer/optimizer.py"
      provides: "PeakShare-integrated _should_discharge() + Abend-Entladung terminology"
      contains: "Abend-Entladung deaktiviert"
    - path: "custom_components/eeg_energy_optimizer/__init__.py"
      provides: "PeakShareProvider creation, migration v12, hot-reload support"
      contains: "peakshare"
    - path: "custom_components/eeg_energy_optimizer/websocket_api.py"
      provides: "eeg_optimizer/get_peakshare_communities WS command"
      contains: "get_peakshare_communities"
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "PeakShare checkbox, community dropdown, terminology Abend-Entladung"
      contains: "enable_peakshare"
  key_links:
    - from: "peakshare.py"
      to: "PeakShare API"
      via: "aiohttp GET with User-Agent header"
      pattern: "peakshare\\.app/api/public"
    - from: "optimizer.py"
      to: "peakshare.py"
      via: "PeakShareProvider.async_fetch() + find_discharge_window()"
      pattern: "peakshare"
    - from: "__init__.py"
      to: "peakshare.py"
      via: "PeakShareProvider creation + data dict storage"
      pattern: "PeakShareProvider"
    - from: "frontend/eeg-optimizer-panel.js"
      to: "websocket_api.py"
      via: "eeg_optimizer/get_peakshare_communities WebSocket call"
      pattern: "get_peakshare_communities"
---

<objective>
Implement PeakShare-based evening discharge with consistent "Abend-Entladung" terminology.

Purpose: Replace fixed discharge start times with demand-driven window calculation based on PeakShare community grid import forecasts. The optimizer finds the optimal contiguous discharge window where community demand is highest, enabling smarter grid-friendly battery discharge. Simultaneously rename all "Nachteinspeisung" references to "Abend-Entladung" for consistency.

Output: New `peakshare.py` module, updated optimizer with PeakShare integration, config migration v12, WebSocket API for community list, updated panel UI with PeakShare checkbox and community dropdown, consistent terminology throughout.
</objective>

<execution_context>
@C:\Users\RobertHell\.claude\get-shit-done\workflows\execute-plan.md
@C:\Users\RobertHell\.claude\get-shit-done\templates\summary.md
</execution_context>

<context>
@.planning/quick/260416-kqk-peakshare-basierte-abend-entladung-mit-k/260416-kqk-CONTEXT.md
@.planning/quick/260416-kqk-peakshare-basierte-abend-entladung-mit-k/260416-kqk-RESEARCH.md
@custom_components/eeg_energy_optimizer/const.py
@custom_components/eeg_energy_optimizer/optimizer.py
@custom_components/eeg_energy_optimizer/__init__.py
@custom_components/eeg_energy_optimizer/websocket_api.py
@custom_components/eeg_energy_optimizer/config_flow.py
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js

<interfaces>
<!-- Key types and contracts from existing codebase -->

From const.py:
```python
CONF_ENABLE_NIGHT_DISCHARGE = "enable_night_discharge"  # internal key, stays
CONF_DISCHARGE_START_TIME = "discharge_start_time"
CONF_DISCHARGE_POWER_KW = "discharge_power_kw"
DEFAULT_DISCHARGE_POWER_KW = 3.0  # will change to 5.0
STATE_ABEND_ENTLADUNG = "Abend-Entladung"  # already correct
```

From optimizer.py:
```python
class EEGOptimizer:
    def __init__(self, hass, entry_id, config, inverter, coordinator, provider): ...
    async def async_run_cycle(self, mode: str) -> Decision: ...
    def _should_discharge(self, snap: Snapshot) -> tuple[bool, float, list[str]]: ...
    # Key: _should_discharge is sync, async_run_cycle is async
    # PeakShare fetch MUST happen in async_run_cycle before _evaluate
```

From __init__.py:
```python
# Config flow version: currently VERSION = 10 in config_flow.py
# Migration chain: v3 -> v4 -> v5 -> v6 -> v7 -> v8 -> v9 -> v10 (last migration: < 10)
# Hot-reload in _async_update_listener: re-creates EEGOptimizer with new config
# data dict pattern: hass.data[DOMAIN][entry.entry_id]["peakshare"] = provider
```

From websocket_api.py:
```python
# Registration pattern: websocket_api.async_register_command(hass, ws_function)
# Helper: _get_entry_data(hass, connection, msg) -> (entry, data)
# Decorator: @websocket_api.websocket_command({...}) + @websocket_api.async_response
```

From frontend/eeg-optimizer-panel.js:
```javascript
// Config defaults at line ~80-101: enable_night_discharge: true, discharge_start_time: "20:00", discharge_power_kw: 3.0
// Wizard Step 4 (_renderStep4): feature cards + discharge fields
// Settings (_renderSettings): mirrors wizard structure
// Summary (_renderStep6): reads wizardData
// Dashboard: discharge status card reads ma.discharge_* attributes
// Info modal: "Abend-Entladung (Nachteinspeisung)" title
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: PeakShare backend — provider, algorithm, optimizer integration, config migration</name>
  <files>
    custom_components/eeg_energy_optimizer/peakshare.py,
    custom_components/eeg_energy_optimizer/const.py,
    custom_components/eeg_energy_optimizer/config_flow.py,
    custom_components/eeg_energy_optimizer/__init__.py,
    custom_components/eeg_energy_optimizer/optimizer.py,
    custom_components/eeg_energy_optimizer/websocket_api.py
  </files>
  <action>
**1. Create `peakshare.py`** (NEW FILE):

Implement `PeakShareProvider` class:
- Constructor: `__init__(self, hass, entry_id)` — creates `Store(hass, 1, f"{DOMAIN}_{entry_id}_peakshare")`, init `_cache`, `_cache_time`, `_jitter_today`, `_jitter_date`, `_discharge_plan`, `_discharge_plan_date`
- `async_load()` — load persisted cache from Store on startup (data + fetched_at + jitter)
- `async_fetch()` — fetch from `https://peakshare.app/api/public/community-grid-import-forecast` with `User-Agent: HomeAssistant/EEGEnergyOptimizer` header, 30s timeout. Return cached data if still fresh (<6h). On API failure, return cached data if <24h old, else None. Persist to Store on successful fetch. Use `async_get_clientsession(hass)` from `homeassistant.helpers.aiohttp_client`.
- `get_communities()` — return list of community names from cached data (for dropdown)
- `get_jitter_today()` — return today's jitter offset in minutes, rolled once per day with `random.randint(-60, 60)`. Persist jitter in Store alongside cache data so HA restarts don't re-roll.
- `get_discharge_plan(community, available_kwh, discharge_power_kw, sunset_time, now)` — wrapper that computes discharge window once per day (locked by date string). Calls `find_discharge_window()` only after sunset - 30min. Returns `(start_time, end_time)` or None.

Implement `find_discharge_window()` standalone function:
- Parameters: `hours` (list of dicts with "timestamp" and "deficitKwh"), `available_kwh`, `discharge_power_kw`, `window_start` (datetime), `window_end` (datetime, 04:00 hard cutoff), `jitter_minutes` (int)
- Calculate `required_hours = math.ceil(available_kwh / discharge_power_kw)`, minimum 1
- Filter hours to eligible window (between window_start and window_end, with deficitKwh > 0)
- Parse API timestamps as UTC via `datetime.fromisoformat()`, convert to local via `dt_util.as_local()`
- Sliding window O(n): find contiguous block of `required_hours` with maximum sum of deficitKwh
- If not enough eligible hours, return None
- Apply jitter to start_time, clamp to not go before window_start
- Return `(start_time, end_time)` tuple

**2. Update `const.py`**:

Add new config keys:
```python
CONF_ENABLE_PEAKSHARE = "enable_peakshare"
CONF_PEAKSHARE_COMMUNITY = "peakshare_community"

DEFAULT_ENABLE_PEAKSHARE = True
DEFAULT_PEAKSHARE_COMMUNITY = "BEG"
```

Change `DEFAULT_DISCHARGE_POWER_KW = 5.0` (from 3.0). Existing installs keep their configured value via migration.

**3. Update `config_flow.py`**:

Current config_flow.py has `VERSION = 10`. Set to `VERSION = 12`. The migration chain in __init__.py ends at `< 10`. Add migration for `< 12`.

**4. Update `__init__.py`**:

Add migration for version < 12:
```python
if entry.version < 12:
    new_data = {**entry.data}
    new_data.setdefault("enable_peakshare", True)
    new_data.setdefault("peakshare_community", "BEG")
    # Don't change existing discharge_power_kw — only default for new installs is 5.0
    hass.config_entries.async_update_entry(entry, data=new_data, version=12)
```

In `async_setup_entry()`, after creating the optimizer and before the 30s timer:
- Create `PeakShareProvider(hass, entry.entry_id)`
- Call `await provider.async_load()` to restore cache
- Store in `data["peakshare"] = peakshare_provider`
- Pass to optimizer: add `peakshare` parameter to `EEGOptimizer.__init__`

In `_async_update_listener()` hot-reload:
- Preserve PeakShareProvider across hot-reloads (don't recreate, it has cache)
- Pass existing peakshare_provider to new optimizer instance

**5. Update `optimizer.py`**:

Add `peakshare` parameter to `EEGOptimizer.__init__()`:
- Store as `self._peakshare = peakshare` (can be None if PeakShare not available)
- Add `self._enable_peakshare = config.get(CONF_ENABLE_PEAKSHARE, True)`
- Add `self._peakshare_community = config.get(CONF_PEAKSHARE_COMMUNITY, "BEG")`

In `async_run_cycle()`, BEFORE calling `_evaluate()`:
- If PeakShare enabled and peakshare provider exists, call `await self._peakshare.async_fetch()` to ensure fresh data

Modify `_should_discharge()`:
- When PeakShare is enabled AND provider has data:
  - Calculate `available_kwh = (snap.battery_soc - min_soc) / 100 * snap.battery_capacity_kwh`
  - Get discharge plan from provider: `self._peakshare.get_discharge_plan(community, available_kwh, self._discharge_power_kw, snap.sunset_today, snap.now)`
  - If plan returned: check if `snap.now` is within `(plan_start, plan_end)` instead of checking fixed `discharge_start`
  - If no plan (API down + cache expired): fall back to fixed `discharge_start` check (existing logic)
- When PeakShare disabled: use existing fixed start time logic (unchanged)
- All other checks (SOC, PV tomorrow) remain unchanged

Terminology fix in `_should_discharge()`:
- Line 669: `"Nachteinspeisung deaktiviert"` -> `"Abend-Entladung deaktiviert"`

Add discharge plan info to Decision dataclass:
- Add field `discharge_peakshare_active: bool = False` — whether PeakShare determined the window
- Add field `discharge_window_start: str = ""` — computed window start time (for dashboard display)
- Add field `discharge_window_end: str = ""` — computed window end time
- Populate these fields in `_evaluate()` when PeakShare is active

**6. Update `websocket_api.py`**:

Add new WebSocket command `eeg_optimizer/get_peakshare_communities`:
```python
@websocket_api.websocket_command(
    {vol.Required("type"): "eeg_optimizer/get_peakshare_communities"}
)
@websocket_api.async_response
async def ws_get_peakshare_communities(hass, connection, msg):
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    peakshare = data.get("peakshare")
    if not peakshare:
        # Fetch directly if no provider yet (during setup)
        from .peakshare import PeakShareProvider
        temp = PeakShareProvider(hass, "temp")
        api_data = await temp.async_fetch()
        communities = [c["name"] for c in (api_data or {}).get("communities", [])]
    else:
        communities = peakshare.get_communities()
        if not communities:
            await peakshare.async_fetch()
            communities = peakshare.get_communities()
    connection.send_result(msg["id"], {"communities": communities})
```

Register in `async_register_websocket_commands()`: add `websocket_api.async_register_command(hass, ws_get_peakshare_communities)`.
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && python -c "
from custom_components.eeg_energy_optimizer.peakshare import PeakShareProvider, find_discharge_window
from custom_components.eeg_energy_optimizer.const import CONF_ENABLE_PEAKSHARE, CONF_PEAKSHARE_COMMUNITY, DEFAULT_DISCHARGE_POWER_KW
from custom_components.eeg_energy_optimizer.optimizer import EEGOptimizer, Decision
assert CONF_ENABLE_PEAKSHARE == 'enable_peakshare'
assert CONF_PEAKSHARE_COMMUNITY == 'peakshare_community'
assert DEFAULT_DISCHARGE_POWER_KW == 5.0
assert hasattr(Decision, 'discharge_peakshare_active')
assert hasattr(Decision, 'discharge_window_start')
# Test find_discharge_window with mock data
from datetime import datetime, timezone, timedelta
hours = [
    {'timestamp': '2026-04-16T16:00:00.000Z', 'deficitKwh': 300},
    {'timestamp': '2026-04-16T17:00:00.000Z', 'deficitKwh': 600},
    {'timestamp': '2026-04-16T18:00:00.000Z', 'deficitKwh': 700},
    {'timestamp': '2026-04-16T19:00:00.000Z', 'deficitKwh': 500},
    {'timestamp': '2026-04-16T20:00:00.000Z', 'deficitKwh': 400},
]
ws = datetime(2026, 4, 16, 16, 0, tzinfo=timezone.utc)
we = datetime(2026, 4, 17, 4, 0, tzinfo=timezone.utc)
result = find_discharge_window(hours, 10.0, 5.0, ws, we, 0)
assert result is not None, 'Expected a discharge window'
# Test date-lock: get_discharge_plan returns cached result on same day
p = PeakShareProvider.__new__(PeakShareProvider)
p._cache = {'communities': [{'name': 'BEG', 'hours': hours}]}
p._cache_time = datetime.now(timezone.utc)
p._jitter_today = 0
p._jitter_date = '2026-04-16'
p._discharge_plan = None
p._discharge_plan_date = None
sunset = datetime(2026, 4, 16, 18, 30, tzinfo=timezone.utc)
now1 = datetime(2026, 4, 16, 18, 1, tzinfo=timezone.utc)
r1 = p.get_discharge_plan('BEG', 10.0, 5.0, sunset, now1)
r2 = p.get_discharge_plan('BEG', 10.0, 5.0, sunset, now1)
assert r1 == r2, 'Date-lock failed: same-day calls should return cached result'
print('All backend checks passed')
"
    </automated>
  </verify>
  <done>
    - peakshare.py exists with PeakShareProvider and find_discharge_window()
    - const.py has CONF_ENABLE_PEAKSHARE, CONF_PEAKSHARE_COMMUNITY, DEFAULT_DISCHARGE_POWER_KW=5.0
    - config_flow.py VERSION=12
    - __init__.py has migration v12 and PeakShareProvider creation
    - optimizer.py integrates PeakShare into _should_discharge(), "Nachteinspeisung deaktiviert" replaced
    - websocket_api.py has get_peakshare_communities command
    - find_discharge_window() correctly finds optimal contiguous window
  </done>
</task>

<task type="auto">
  <name>Task 2: Frontend PeakShare UI + terminology rename to Abend-Entladung</name>
  <files>
    custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js,
    CLAUDE.md
  </files>
  <action>
**1. Update `eeg-optimizer-panel.js`**:

**Terminology renames** (all occurrences):
- Line 2380: `"Nachteinspeisung"` -> `"Abend-Entladung"` (Wizard Step 4 feature title)
- Line 2495: `"Nachteinspeisung"` -> `"Abend-Entladung"` (Summary Step 6 heading)
- Line 2601: `"Nachteinspeisung"` -> `"Abend-Entladung"` (Settings feature title)
- Line 2682: `"Abend-Entladung (Nachteinspeisung)"` -> `"Abend-Entladung"` (Info modal title)
- Line 2873: `if (r.includes("Nachtverbrauch")) reasonParts.push("Nachtverbrauch zu hoch")` -> `reasonParts.push("Nachtverbrauch zu hoch")` (keep "Nachtverbrauch" — it describes consumption, not the feature)

**Config defaults** (line ~80-101):
Add to the DEFAULT_CONFIG object:
```javascript
enable_peakshare: true,
peakshare_community: "BEG",
```
Change `discharge_power_kw: 5.0` (from 3.0).

**Wizard Step 4 (`_renderStep4`)** — Abend-Entladung section:
When `nDischarge` is true, add PeakShare checkbox above discharge fields:
```javascript
const peakshare = this._wizardData.enable_peakshare !== false;  // default true

// PeakShare checkbox
`<div class="feature-params">
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:12px">
    <input type="checkbox" data-field="enable_peakshare" ${peakshare ? "checked" : ""}>
    <div>
      <div style="font-weight:500">PeakShare-Bedarfssteuerung</div>
      <div class="help-text" style="margin-top:2px">Entladezeitpunkt wird automatisch nach dem Bedarf der Energiegemeinschaft optimiert.</div>
    </div>
  </label>
  ${peakshare ? communityDropdownHtml : dischargeStartTimeField + dischargePowerField}
  // min_soc field always shown (both modes need it)
  ${minSocField}
</div>`
```

**Community dropdown** (when PeakShare active):
- On wizard load / when checkbox toggled to active, fetch communities via WebSocket: `this._hass.callWS({type: "eeg_optimizer/get_peakshare_communities"})`
- Store result in `this._peakshareCommunitiesCache`
- Render `<select data-field="peakshare_community">` with options from API, pre-select `this._wizardData.peakshare_community || "BEG"`
- Show fallback text if communities empty: "Communities werden geladen..."

**Conditional field visibility** (per CONTEXT.md locked decision):
- PeakShare ACTIVE: HIDE "Startzeit der Entladung" and "Entladeleistung (kW)" fields, SHOW community dropdown
- PeakShare INACTIVE: SHOW "Startzeit der Entladung" and "Entladeleistung (kW)" fields, HIDE community dropdown
- "Minimaler Ladezustand (%)" always visible in both modes

**Settings screen (`_renderSettings`)** — mirror the same logic:
- Add PeakShare checkbox inside the Abend-Entladung feature-card section
- Same conditional visibility: peakshare active = dropdown, peakshare inactive = start time + power fields
- Fetch communities when settings screen renders if PeakShare enabled
- Handle `data-field="settings_enable_peakshare"` and `data-field="settings_peakshare_community"` with same prefix pattern as other settings fields

**Summary (`_renderStep6`)**:
- If PeakShare active: show "Modus: PeakShare-Bedarfssteuerung" and "Community: [name]"
- If PeakShare inactive: show existing start time + power fields

**Dashboard discharge status card**:
- If `ma.discharge_peakshare_active` is true, show the computed window times instead of fixed start time:
  - Replace "Geplant ab {start_time}" with "Geplant {window_start} - {window_end} (PeakShare)"
  - Replace "AKTIV" line to include window info
- If PeakShare not active or no data, show existing fixed start time display

**Info modal** for Abend-Entladung:
- Update content to mention PeakShare: "Im PeakShare-Modus wird der Entladezeitpunkt automatisch nach dem Bedarf der Energiegemeinschaft optimiert. Ohne PeakShare wird ab der konfigurierten festen Startzeit entladen."

**Event handler updates**:
- Handle `data-field="enable_peakshare"` checkbox toggle in both wizard and settings
- On toggle: re-render the discharge section to show/hide fields
- Handle `data-field="peakshare_community"` select change

**2. Update `CLAUDE.md`**:

- Replace any remaining "Nachteinspeisung" or "Nacht-Entladung" mentions with "Abend-Entladung"
- Add PeakShare to the Architecture section:
  - New file: `peakshare.py` | PeakShareProvider — fetches + caches PeakShare API data, sliding window algorithm
  - Update optimizer description to mention PeakShare integration
- Add CONF_ENABLE_PEAKSHARE and CONF_PEAKSHARE_COMMUNITY to config keys
- Add `eeg_optimizer/get_peakshare_communities` to WebSocket API table
- Update "Evening Discharge" domain concept to mention PeakShare-based window optimization
- Mention config entry version is now 12
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && python -c "
import re
# Check panel has PeakShare references
panel = open('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js', 'r', encoding='utf-8').read()
assert 'enable_peakshare' in panel, 'Missing enable_peakshare in panel'
assert 'peakshare_community' in panel, 'Missing peakshare_community in panel'
assert 'get_peakshare_communities' in panel, 'Missing WS call in panel'
# Check no Nachteinspeisung remains as feature title (but Nachtverbrauch is ok)
nacht_hits = [m.start() for m in re.finditer(r'Nachteinspeisung', panel)]
assert len(nacht_hits) == 0, f'Nachteinspeisung still present at positions: {nacht_hits}'
# Check CLAUDE.md updated
claude = open('CLAUDE.md', 'r', encoding='utf-8').read()
assert 'peakshare' in claude.lower(), 'Missing PeakShare in CLAUDE.md'
assert 'Nachteinspeisung' not in claude, 'Nachteinspeisung still in CLAUDE.md'
print('All frontend + terminology checks passed')
"
    </automated>
  </verify>
  <done>
    - All "Nachteinspeisung" replaced with "Abend-Entladung" in panel (feature titles, info modals, summary)
    - PeakShare checkbox ("PeakShare-Bedarfssteuerung") added to Wizard Step 4 and Settings, default=checked
    - When PeakShare active: Startzeit and Entladeleistung hidden, Community dropdown shown
    - When PeakShare inactive: Startzeit and Entladeleistung shown, Community dropdown hidden
    - Community dropdown fetches from get_peakshare_communities WS command, pre-selects "BEG"
    - Dashboard discharge card shows PeakShare window times when active
    - CLAUDE.md fully updated with PeakShare info and consistent terminology
    - No "Nachteinspeisung" string remains in panel or CLAUDE.md
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HA -> PeakShare API | External HTTP API, untrusted response data |
| Panel -> WebSocket | User input for config fields (community name, checkbox state) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-kqk-01 | S (Spoofing) | PeakShare API | accept | Public endpoint, no auth; data is community-level forecast, not sensitive |
| T-kqk-02 | T (Tampering) | PeakShare API response | mitigate | Validate response structure: check "communities" array exists, each entry has "hours" array with "timestamp" and "deficitKwh" fields; discard malformed data and fall back to cache/fixed time |
| T-kqk-03 | D (Denial of Service) | PeakShare API unavailable | mitigate | 3-tier fallback: fresh data > 24h cache > fixed start time; 30s timeout prevents blocking optimizer cycle |
| T-kqk-04 | I (Info Disclosure) | User-Agent header | accept | Only sends integration name, no user-identifying data |
| T-kqk-05 | T (Tampering) | WebSocket config save | accept | HA WebSocket auth already gates access; community name is free-text from known list |
</threat_model>

<verification>
1. `python -c "from custom_components.eeg_energy_optimizer.peakshare import PeakShareProvider, find_discharge_window; print('Import OK')"` succeeds
2. `find_discharge_window()` returns correct window for test data
3. No "Nachteinspeisung" string in panel JS
4. `CONF_ENABLE_PEAKSHARE` and `CONF_PEAKSHARE_COMMUNITY` importable from const
5. `DEFAULT_DISCHARGE_POWER_KW == 5.0`
6. Config flow VERSION == 12
7. `eeg_optimizer/get_peakshare_communities` registered in websocket_api
</verification>

<success_criteria>
- PeakShareProvider fetches API data, caches with Store, serves community list
- find_discharge_window() computes optimal contiguous discharge window using sliding window
- Optimizer uses PeakShare window when enabled, falls back to fixed time otherwise
- Jitter persisted across restarts, rolled once per day
- Config migration v12 adds enable_peakshare=True, peakshare_community="BEG"
- Panel shows PeakShare checkbox in Wizard Step 4 + Settings with conditional field visibility
- Community dropdown populated from WebSocket API, pre-selects "BEG"
- All "Nachteinspeisung" replaced with "Abend-Entladung" in user-facing strings
- CLAUDE.md documents PeakShare feature
</success_criteria>

<output>
After completion, create `.planning/quick/260416-kqk-peakshare-basierte-abend-entladung-mit-k/260416-kqk-SUMMARY.md`
</output>
