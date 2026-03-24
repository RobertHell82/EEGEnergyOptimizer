# Phase ip7: Optimizer Aktivitaetsprotokoll - Research

**Researched:** 2026-03-24
**Domain:** Home Assistant logbook integration, in-memory ring buffer, WebSocket push, plain JS timeline
**Confidence:** HIGH (core HA patterns verified via official docs and HA core source)

---

## Summary

The activity log requires three independent mechanisms that compose cleanly with the existing codebase:

1. **HA Logbook**: A `logbook.py` platform file in the integration registers an `async_describe_events` callback. The optimizer fires `hass.bus.async_fire("eeg_optimizer_event", {...})` on state changes. HA's logbook automatically picks this up and renders it in the built-in Activity view. No `logbook_entry` sentinel event is needed — that pattern is obsolete/unreliable.

2. **In-memory ring buffer**: A `collections.deque(maxlen=200)` stored in `hass.data[DOMAIN][entry_id]["activity_log"]`. Appended after every optimizer cycle that changes state, and on 15-min heartbeat. Zero persistence — clears on HA restart (acceptable for a live panel).

3. **Panel timeline**: A new WebSocket command `eeg_optimizer/get_activity_log` returns the deque as a list. The panel fetches on load and subscribes to `eeg_optimizer_event` via `subscribe_events` for live push — no custom push infrastructure needed.

**Primary recommendation:** Use `logbook.py` platform + `hass.bus.async_fire` for the HA logbook side. Use the event bus subscription (`subscribe_events`) in the panel for real-time updates — this is zero new server infrastructure.

---

## Standard Stack

### Core
| Component | Version | Purpose |
|-----------|---------|---------|
| `collections.deque` | stdlib | Ring buffer, O(1) append/pop, `maxlen` caps memory |
| `homeassistant.components.logbook` | HA built-in | Renders custom events in Activity view |
| `hass.bus.async_fire` | HA core | Posts event to event bus (logbook + WS subscribers) |
| `websocket_api.async_register_command` | HA built-in | Already used — add `ws_get_activity_log` |

### No additional pip dependencies needed.

---

## Architecture Patterns

### Pattern 1: HA Logbook Platform File

Create `custom_components/eeg_energy_optimizer/logbook.py`:

```python
# Source: HA core homeassistant/components/zha/logbook.py pattern
from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_DOMAIN,
    LOGBOOK_ENTRY_ENTITY_ID,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback
from .const import DOMAIN

EVENT_EEG_OPTIMIZER = "eeg_optimizer_event"

@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event,
) -> None:
    """Describe eeg_optimizer_event for the HA logbook."""

    @callback
    def _describe(event: Event) -> dict:
        data = event.data
        return {
            LOGBOOK_ENTRY_NAME: "EEG Optimizer",
            LOGBOOK_ENTRY_MESSAGE: data.get("message", data.get("zustand", "Zustand geaendert")),
            LOGBOOK_ENTRY_DOMAIN: DOMAIN,
            LOGBOOK_ENTRY_ENTITY_ID: data.get("entity_id"),
        }

    async_describe_event(DOMAIN, EVENT_EEG_OPTIMIZER, _describe)
```

HA auto-discovers `logbook.py` when forwarding platforms — no explicit registration needed.

### Pattern 2: Firing Events + Appending to Ring Buffer

In `optimizer.py` or `__init__.py`, after `decision_sensor.update_from_decision(decision)`:

```python
# In _optimizer_cycle() in __init__.py
RING_BUFFER_SIZE = 200

def _append_activity(data: dict, entry_data: dict, hass, entry_id: str) -> None:
    """Append entry to ring buffer and fire logbook event."""
    log = entry_data.setdefault("activity_log", deque(maxlen=RING_BUFFER_SIZE))
    log.appendleft(data)  # newest first
    hass.bus.async_fire("eeg_optimizer_event", data)

# Fire on state change only (deduplicate by zustand):
if decision.zustand != data.get("last_logged_zustand"):
    _append_activity({
        "ts": decision.timestamp,
        "zustand": decision.zustand,
        "message": f"Zustand: {decision.zustand}",
        "entity_id": "sensor.eeg_energy_optimizer_entscheidung",
        "ausfuehrung": decision.ausfuehrung,
    }, data, hass, entry.entry_id)
    data["last_logged_zustand"] = decision.zustand

# Fire every 15min regardless (heartbeat):
now_ts = datetime.now(timezone.utc)
last_hb = data.get("last_activity_heartbeat")
if last_hb is None or (now_ts - last_hb).total_seconds() >= 900:
    _append_activity({
        "ts": decision.timestamp,
        "zustand": decision.zustand,
        "message": f"Heartbeat: {decision.zustand} (SOC {decision.discharge_soc:.0f}%)",
        "entity_id": "sensor.eeg_energy_optimizer_entscheidung",
        "heartbeat": True,
    }, data, hass, entry.entry_id)
    data["last_activity_heartbeat"] = now_ts
```

Import at top of `__init__.py`: `from collections import deque`

### Pattern 3: WebSocket Command for Bulk Fetch

Add to `websocket_api.py`:

```python
@websocket_api.websocket_command({"vol.Required("type")": "eeg_optimizer/get_activity_log"})
@websocket_api.async_response
async def ws_get_activity_log(hass, connection, msg):
    entry, data = _get_entry_data(hass, connection, msg)
    if entry is None:
        return
    log = data.get("activity_log", [])
    connection.send_result(msg["id"], {"entries": list(log)})
```

Register in `async_register_websocket_commands`.

### Pattern 4: Panel — Fetch + Live Subscribe

In the panel JS (`eeg-optimizer-panel.js`), within the dashboard section:

```javascript
// One-time fetch of history
async _loadActivityLog() {
  const result = await this._hass.callWS({ type: "eeg_optimizer/get_activity_log" });
  this._activityLog = result.entries || [];
  this._render();
}

// Live subscription via HA event bus (no custom server push needed)
_subscribeActivityLog() {
  if (this._activityUnsub) return;
  this._activityUnsub = this._hass.connection.subscribeEvents((event) => {
    const entry = event.data;
    this._activityLog = [entry, ...this._activityLog].slice(0, 200);
    this._renderActivityTimeline();
  }, "eeg_optimizer_event");
}

// Unsubscribe on disconnect / view change
_unsubscribeActivityLog() {
  if (this._activityUnsub) {
    this._activityUnsub();
    this._activityUnsub = null;
  }
}
```

`this._hass.connection.subscribeEvents(callback, eventType)` is the standard HA frontend connection API — available in all HA panels via the `hass` property. Returns an unsubscribe function.

### Pattern 5: Timeline HTML (Shadow DOM, no LitElement)

```javascript
_renderActivityTimeline() {
  const container = this._shadow.querySelector("#activity-timeline");
  if (!container) return;
  const items = (this._activityLog || []).slice(0, 50);
  container.innerHTML = items.map(e => {
    const ts = new Date(e.ts).toLocaleTimeString("de-DE", {hour:"2-digit", minute:"2-digit"});
    const icon = e.heartbeat ? "⏱" : (
      e.zustand === "Morgen-Einspeisung" ? "☀" :
      e.zustand === "Abend-Entladung"   ? "🔋" : "⚡"
    );
    const cls = e.heartbeat ? "log-heartbeat" : "log-state";
    return `<div class="log-entry ${cls}">
      <span class="log-time">${ts}</span>
      <span class="log-icon">${icon}</span>
      <span class="log-msg">${e.message}</span>
    </div>`;
  }).join("");
}
```

CSS in Shadow DOM template: `overflow-y: auto; max-height: 300px;` on the container `<div id="activity-timeline">`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Custom push channel | WebSocket server subscription registry | `hass.bus.async_fire` + client `subscribeEvents` |
| Persistent log across restarts | DB writes / file I/O | HA logbook (recorder-backed), ring buffer is ephemeral |
| Custom event format | Ad-hoc schema | `LOGBOOK_ENTRY_NAME/MESSAGE/DOMAIN/ENTITY_ID` constants |

---

## Common Pitfalls

### Pitfall 1: Using `logbook_entry` event directly
**What goes wrong:** Firing `hass.bus.async_fire("logbook_entry", {...})` appears to work but has been documented as unreliable since HA 2023.x. The `logbook_entry` event type is an internal sentinel, not a public API.
**How to avoid:** Use a domain-specific event (`eeg_optimizer_event`) + `logbook.py` platform. This is the pattern all first-party integrations use (ZHA, Alexa, etc.).

### Pitfall 2: Firing on every 60s cycle
**What goes wrong:** 1440 logbook entries per day floods the Activity view and recorder.
**How to avoid:** Fire only on `zustand` state change + 15-min heartbeat. Track `last_logged_zustand` and `last_activity_heartbeat` in `hass.data`.

### Pitfall 3: `subscribeEvents` called before `_hass` is set
**What goes wrong:** Panel initializes before HA connection is ready — subscription fails silently.
**How to avoid:** Call `_subscribeActivityLog()` inside the `set hass(value)` setter, guarded by `if (!this._activityUnsub && this._view === "dashboard")`.

### Pitfall 4: Memory leak from unsubscribed event listener
**What goes wrong:** Every panel load adds a new subscription, and old ones are never cleaned up.
**How to avoid:** Call `_unsubscribeActivityLog()` in `disconnectedCallback()` and when switching away from dashboard view.

### Pitfall 5: Ring buffer not initialized before first access
**What goes wrong:** `data["activity_log"]` doesn't exist if optimizer hasn't run yet; `ws_get_activity_log` returns error.
**How to avoid:** Use `data.get("activity_log", [])` in the WS handler. In `_append_activity`, use `setdefault`.

---

## Data Structure

```python
# One log entry (dict stored in deque, sent over WS, fired as event data)
{
    "ts": "2026-03-24T07:15:00+01:00",   # ISO 8601 from decision.timestamp
    "zustand": "Morgen-Einspeisung",       # one of 3 known states
    "message": "Zustand: Morgen-Einspeisung",  # human-readable for logbook
    "entity_id": "sensor.eeg_energy_optimizer_entscheidung",
    "ausfuehrung": True,                   # was inverter command actually sent?
    "heartbeat": False,                    # True = periodic, False = state change
}
```

---

## File Changes Required

| File | Change |
|------|--------|
| `logbook.py` | New file — `async_describe_events` |
| `const.py` | Add `EVENT_EEG_OPTIMIZER = "eeg_optimizer_event"` |
| `__init__.py` | Import `deque`, add `_append_activity()`, call in `_optimizer_cycle()` |
| `websocket_api.py` | Add `ws_get_activity_log`, register it |
| `frontend/eeg-optimizer-panel.js` | Add `_loadActivityLog`, `_subscribeActivityLog`, `_renderActivityTimeline`, timeline HTML/CSS |

No new pip dependencies. No config entry migration needed.

---

## Sources

### Primary (HIGH confidence)
- HA core `homeassistant/components/zha/logbook.py` — `async_describe_events` pattern (fetched via WebFetch)
- HA core `homeassistant/components/logbook/__init__.py` — `LOGBOOK_ENTRY_*` constants, callback type (fetched via WebFetch)
- [Firing events — HA Developer Docs](https://developers.home-assistant.io/docs/api/websocket/) — `hass.bus.async_fire` pattern
- [WebSocket API — HA Developer Docs](https://developers.home-assistant.io/docs/api/websocket/) — `subscribe_events` client API

### Secondary (MEDIUM confidence)
- `hass.connection.subscribeEvents(cb, eventType)` JS API — standard HA frontend pattern, confirmed used in official HA dashboards; exact method signature inferred from community examples (not official dev docs)

**Research date:** 2026-03-24
**Valid until:** 2026-04-24 (stable HA APIs, low churn risk)
