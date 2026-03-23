# Quick Task 260323-m0o: Dashboard Status-Header - Research

**Researched:** 2026-03-23
**Domain:** Panel JS (frontend) + Optimizer Decision dataclass (backend)
**Confidence:** HIGH

## Summary

The task replaces the single "Optimizer Status" card at the top of the dashboard with two side-by-side status cards: "Verzogerte Ladung" (morning charge delay) and "Abend-Entladung" (evening discharge). Each card shows a status line with reasoning, a divider, and 2-3 condition rows with values and check/cross indicators.

The data flow is: `optimizer.py _evaluate()` produces a `Decision` dataclass, which is passed to `sensor.py EntscheidungsSensor.update_from_decision()`, which exposes it as HA entity attributes. The panel JS reads these attributes via `this._readState(entityId).attributes`. The 60-second optimizer cycle drives updates.

**Primary recommendation:** Extend the `Decision` dataclass with new fields for both features' detailed status, propagate them through `update_from_decision()` as new sensor attributes, and rewrite the status card HTML in `_renderDashboard()`.

## User Constraints (from CONTEXT.md)

### Layout-Struktur
- Two equal status cards side-by-side: left "Verzogerte Ladung", right "Abend-Entladung"
- Each card: Title, status line with reasoning, divider, 2-3 condition rows with values and check/cross

### Status-Texte (locked -- use these exact patterns)
- "Nicht geplant -- SOC zu niedrig"
- "Nicht geplant -- PV morgen nicht ausreichend"
- "Nicht aktiv -- PV reicht nicht fur Bedarf + Puffer"
- "Geplant ab 20:00 bis 35% SOC"
- "AKTIV -- 3.0 kW Entladung bis 35% SOC" / "AKTIV -- Ladung blockiert bis 10:00"

### Abend-Entladung -- 6 states (locked)
1. Geplant (before start time, conditions met)
2. Nicht geplant -- SOC zu niedrig
3. Nicht geplant -- PV morgen nicht ausreichend
4. Nicht geplant -- mehrere Grunde
5. Aktiv (running now)
6. Deaktiviert

### Verzogerte Ladung -- 5 states (locked)
1. Aktiv (in window, PV sufficient)
2. Im Zeitfenster, nicht aktiv (PV insufficient)
3. Ausserhalb Zeitfenster, morgen erwartet
4. Ausserhalb Zeitfenster, morgen nicht erwartet
5. Deaktiviert

### Color coding (locked)
- Green dot = aktiv, Blue circle = geplant, Red cross = nicht moglich, Gray dash = deaktiviert

### Claude's Discretion
- Backend data: Extend Decision attributes (new fields in Decision dataclass + sensor attributes). Use existing 60s update mechanism, no new WebSocket command needed.

## Architecture: Current Data Flow

### Optimizer -> Decision -> Sensor -> Panel

```
optimizer.py: _evaluate(snap, mode)
  -> Decision dataclass (12 fields)
  -> stored as self._last_decision

__init__.py: _optimizer_cycle()
  -> calls optimizer.async_run_cycle()
  -> calls decision_sensor.update_from_decision(decision)

sensor.py: EntscheidungsSensor.update_from_decision()
  -> Maps Decision fields to entity attributes dict
  -> Calls async_write_ha_state()

panel JS: _renderDashboard()
  -> decisionState = this._readState("sensor...entscheidung")
  -> Reads decisionState.attributes.zustand, .energiebedarf_kwh, etc.
```

### Current Decision Dataclass Fields (optimizer.py:87-101)

| Field | Type | Description |
|-------|------|-------------|
| timestamp | str | ISO timestamp |
| zustand | str | "Normal" / "Morgen-Einspeisung" / "Abend-Entladung" |
| energiebedarf_kwh | float | Consumption to sunset + missing battery |
| ladung_blockiert | bool | Morning charge blocking active |
| entladung_aktiv | bool | Evening discharge active |
| entladeleistung_kw | float | Discharge power (0 if not discharging) |
| min_soc_berechnet | float | Dynamic min SOC |
| naechste_aktion | str | Next action text |
| markdown | str | Markdown dashboard text |
| ausfuehrung | bool | True if mode=Ein |
| block_reasons | list[str] | Reasons discharge is NOT active |

### Current Sensor Attributes (sensor.py:547-557)

```python
{
    "markdown": decision.markdown,
    "zustand": decision.zustand,
    "energiebedarf_kwh": round(decision.energiebedarf_kwh, 2),
    "entladung_aktiv": decision.entladung_aktiv,
    "ladung_blockiert": decision.ladung_blockiert,
    "min_soc": decision.min_soc_berechnet,
    "entladeleistung_kw": decision.entladeleistung_kw,
    "ausfuehrung": decision.ausfuehrung,
    "letzte_aktualisierung": decision.timestamp,
}
```

### Panel Entity Access Pattern

```javascript
const decisionState = this._readState(
    this._entityIds?.entscheidung || "sensor.eeg_energy_optimizer_entscheidung"
);
const zustand = decisionState?.attributes?.zustand;
```

The panel also reads `this._config` which contains ALL integration config keys (loaded via WebSocket `eeg_energy_optimizer/get_config`). This means the panel already has access to:
- `enable_morning_delay` (bool)
- `enable_night_discharge` (bool)
- `morning_end_time` (str, e.g. "10:00")
- `discharge_start_time` (str, e.g. "20:00")
- `discharge_power_kw` (float)
- `min_soc` (int, base value)
- `safety_buffer_pct` (int)
- `battery_soc_sensor` (entity ID -- panel can read SOC directly)

## New Decision Fields Needed

### For Abend-Entladung Card

The existing `block_reasons` list already contains the discharge rejection reasons. However, the card needs structured data, not just strings. New fields:

| Field | Type | Purpose |
|-------|------|---------|
| `discharge_status` | str | One of: "aktiv", "geplant", "nicht_geplant", "deaktiviert" |
| `discharge_reasons` | list[str] | Why not active/planned (already exists as `block_reasons`) |
| `battery_soc` | float | Current SOC for condition display |
| `pv_tomorrow_kwh` | float | PV forecast tomorrow |
| `tomorrow_demand_kwh` | float | Tomorrow's consumption + battery charge need |
| `discharge_target_soc` | float | = min_soc_berechnet (already exists) |

**Key insight -- "geplant" state:** This is new logic. Currently `_should_discharge()` returns False if time < discharge_start. The card needs to distinguish "not yet time but would discharge" from "conditions not met." This requires evaluating SOC and PV-tomorrow checks even when time hasn't been reached.

### For Verzogerte Ladung Card

| Field | Type | Purpose |
|-------|------|---------|
| `morning_status` | str | One of: "aktiv", "nicht_aktiv", "morgen_erwartet", "morgen_nicht_erwartet", "deaktiviert" |
| `morning_reason` | str | Why not active |
| `morning_end_time` | str | End of morning window (already in config) |
| `pv_today_kwh` | float | PV remaining today |
| `morning_threshold_kwh` | float | energiebedarf * (1 + buffer) |
| `in_morning_window` | bool | Whether currently in sunrise-1h to morning_end |

**Key insight -- "morgen erwartet" state:** This requires forward-looking logic for when we're OUTSIDE the morning window. The optimizer currently only checks `_should_block_charging()` which returns False outside the window without indicating why. New logic needed:
- Check if PV forecast for tomorrow would satisfy tomorrow's demand + buffer
- Estimate tomorrow's sunrise for the "ab ~06:15" text
- Use `snap.sunrise` (which is next_rising, so it IS tomorrow's sunrise when checked in the evening)

## Architecture Pattern: How to Structure the Changes

### 1. Optimizer Changes (optimizer.py)

Refactor `_evaluate()` to compute detailed status for both features BEFORE determining the overall `zustand`. Add a helper `_morning_delay_status()` and modify `_should_discharge()` to return a richer result.

```python
@dataclass
class MorningDelayInfo:
    status: str  # "aktiv", "nicht_aktiv", "morgen_erwartet", "morgen_nicht_erwartet", "deaktiviert"
    reason: str
    in_window: bool
    pv_today_kwh: float | None
    threshold_kwh: float
    sunrise_tomorrow: str  # HH:MM for display

@dataclass
class DischargeInfo:
    status: str  # "aktiv", "geplant", "nicht_geplant", "deaktiviert"
    reasons: list[str]
    battery_soc: float
    min_soc: float
    pv_tomorrow_kwh: float
    tomorrow_demand_kwh: float
    discharge_power_kw: float
    start_time: str  # HH:MM
```

Add these as fields to the Decision dataclass (or as dicts for simpler serialization -- dicts are easier since sensor attributes must be JSON-serializable).

**Recommendation:** Use flat fields with a prefix rather than nested dataclasses, since HA sensor attributes are a flat dict. Example: `morning_status`, `morning_reason`, `discharge_status`, `discharge_soc`, etc.

### 2. Sensor Changes (sensor.py)

Add new fields to `update_from_decision()` attribute dict. No new sensors needed.

### 3. Panel Changes (frontend/eeg-optimizer-panel.js)

Replace the current status card (lines 1764-1786) with two side-by-side cards. Keep the metrics row and charts below unchanged.

Current layout:
```
[Optimizer Status card (full width)]
[SOC] [PV Heute] [PV Morgen]  <- metrics row
[Charts...]
```

New layout:
```
[Verzogerte Ladung card] [Abend-Entladung card]  <- side by side
[SOC] [PV Heute] [PV Morgen]  <- metrics row (unchanged)
[Charts...]
```

### CSS Pattern

Use flexbox for the two cards (similar to existing `metrics-row`):
```css
.status-cards-row { display: flex; gap: 16px; }
.status-cards-row .card { flex: 1; min-width: 280px; }
```

For narrow screens, stack vertically (already have `.dashboard-grid.narrow` pattern).

## Key Gotchas

### 1. block_reasons Field Naming Confusion

`block_reasons` on the Decision dataclass actually contains DISCHARGE rejection reasons, not morning-block reasons. The field name is misleading. Line 432:
```python
block_reasons=discharge_reasons if zustand != STATE_ABEND_ENTLADUNG else [],
```
It's populated from `_should_discharge()` return value. When discharge IS active, it's empty. When discharge is NOT active, it has the reasons. This is correct for the Abend-Entladung card.

### 2. _should_discharge() Time Check Ordering

Currently `_should_discharge()` adds "Startzeit nicht erreicht" to reasons when time < discharge_start. For the "geplant" state, we need to know if time is the ONLY reason. Solution: evaluate all conditions, then check if the only failing condition is time.

### 3. Morning "morgen erwartet" Requires New Logic

The current `_should_block_charging()` is a simple boolean. For the "tomorrow expected" state, we need:
- We're outside the morning window (easy: `snap.now > morning_end` or `snap.now < window_start`)
- Check if tomorrow's PV would exceed tomorrow's demand + buffer
- Use `snap.sunrise` for display (next_rising = tomorrow's sunrise when checked in afternoon/evening)
- **Edge case:** Between midnight and sunrise, `snap.sunrise` is TODAY's sunrise. Need to handle this.

### 4. Sunrise Display for "Morgen ab ~06:15"

`snap.sunrise` comes from `sun.sun` entity `next_rising`. In the evening, this IS tomorrow's sunrise. But the "~" prefix suggests approximation. Just format it as HH:MM with the tilde.

### 5. HA Attribute Serialization

All sensor extra_state_attributes must be JSON-serializable. Lists and dicts of primitives are fine. Avoid datetime objects -- use strings.

## Current Panel Status Card HTML (lines 1764-1786)

The existing card to replace:
```html
<div class="card">
  <h3>Optimizer Status</h3>
  <div class="status-row">
    <div class="status-item">Modus: <badge>{mode}</badge></div>
    <div class="status-item">Zustand: <badge>{zustand}</badge></div>
  </div>
  <div class="status-row">Energiebedarf: {value}</div>
  <div class="next-action">Nachste Aktion: {text}</div>
</div>
```

The Modus badge and Energiebedarf info should move into the new cards or be removed (the mode is visible in the HA select entity).

## Implementation Order

1. **optimizer.py**: Add `_morning_delay_status()` method and refactor `_should_discharge()` to separate time-check from condition-checks. Add new flat fields to Decision dataclass.
2. **sensor.py**: Extend `update_from_decision()` to expose new fields as attributes.
3. **panel JS**: Rewrite the status card section in `_renderDashboard()`. Add CSS for new card layout.
4. **Test**: Verify all 6 discharge states + 5 morning states render correctly.

## Project Constraints (from CLAUDE.md)

- Plain HTMLElement + Shadow DOM, no LitElement/CDN
- All UI strings in German
- HA imports guarded with try/except for test environment
- Duck typing for update_from_decision (no circular imports)
- Optimizer calculates every cycle but only executes when mode="Ein"
- Config changes trigger full integration reload

## Sources

### Primary (HIGH confidence)
- `custom_components/eeg_energy_optimizer/optimizer.py` -- Decision dataclass, _evaluate(), _should_block_charging(), _should_discharge()
- `custom_components/eeg_energy_optimizer/sensor.py` -- EntscheidungsSensor.update_from_decision(), attribute mapping
- `custom_components/eeg_energy_optimizer/const.py` -- State names, config keys, defaults
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` -- _renderDashboard(), CSS, entity access patterns

## Metadata

**Confidence breakdown:**
- Data flow understanding: HIGH -- read all source files
- New fields needed: HIGH -- clear from CONTEXT.md states vs existing Decision fields
- Panel rendering: HIGH -- read current HTML/CSS patterns
- Morning "morgen erwartet" logic: MEDIUM -- requires new forward-looking evaluation, edge cases around midnight/sunrise

**Research date:** 2026-03-23
**Valid until:** 2026-04-06 (stable codebase, no external dependencies)
