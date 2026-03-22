# Phase 4: Onboarding Panel - Research

**Researched:** 2026-03-21
**Domain:** Home Assistant Custom Panel (LitElement/JS), WebSocket API, Frontend Integration
**Confidence:** MEDIUM

## Summary

This phase implements a permanent HA sidebar panel with two areas: a Dashboard showing optimizer status/forecasts/charts in real-time, and a Setup Wizard replacing the current 5-step config flow. The panel is built as a JavaScript custom element (vanilla LitElement or plain HTMLElement with Shadow DOM), registered from the integration's Python backend, and communicating via custom WebSocket commands for config read/write.

The primary technical challenge is that HA's built-in web components (`ha-entity-picker`, `ha-form`, `ha-selector`) use lazy loading and are not guaranteed to be available when a custom panel loads. The proven solution is a dynamic component loader (`@kipk/load-ha-components` or a custom loader that triggers HA's panel resolver). Charts use HA's internal ECharts-based `ha-chart-base` component, though a lightweight standalone chart library (Chart.js or uPlot) may be more reliable for a custom panel context.

**Primary recommendation:** Build the panel as a single-file JavaScript custom element using Shadow DOM + HA CSS custom properties for theming. Use `async_register_built_in_panel` with `component_name="custom"` (the HACS pattern). Register custom WebSocket commands for all config operations. Use a dynamic loader for `ha-entity-picker` and fall back to a standard text input if loading fails.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Permanentes Sidebar-Panel, bleibt nach Erstsetup dauerhaft sichtbar
- **D-02:** Sidebar-Icon: `mdi:solar-power`, Name: "EEG Optimizer"
- **D-03:** Zwei Hauptbereiche: **Dashboard** (Startseite) und **Einstellungs-Wizard** (ueber Zahnrad-Button erreichbar)
- **D-04:** Vor erstem Wizard-Durchlauf: Dashboard zeigt grossen Setup-Button + Hinweis "Setup noch nicht abgeschlossen"
- **D-05:** Nach erstem Wizard-Durchlauf: Dashboard normal, Wizard ueber Zahnrad-Icon oben rechts erreichbar
- **D-06:** Sprache: nur Deutsch fuer v1
- **D-07 to D-14:** 8-step linear wizard (Willkommen, Wechselrichter-Typ, Prerequisites, Batterie & PV Sensoren, Prognose-Sensoren, Verbrauchssensor, Optimizer-Parameter, Zusammenfassung)
- **D-15:** Linear wizard with forward/back navigation
- **D-16:** Zwischenstand wird gespeichert -- Abbruch und Wiederaufnahme moeglich
- **D-17:** Wizard jederzeit erneut startbar fuer Re-Konfiguration
- **D-18 to D-22:** Prerequisite checks block wizard, with inline guidance and popup instructions
- **D-23 to D-27:** Sensor auto-detection (Huawei), explicit confirmation, context help, editable entity pickers
- **D-28 to D-36:** Dashboard: optimizer status, Ueberschuss-Faktor, naechste Aktion, SOC, PV-Prognose, 7-day chart, hourly profile chart, live WebSocket updates, HA Material Design
- **D-37 to D-39:** Config flow reduced to 1-click, VERSION bump 3->4 with migration

### Claude's Discretion
- LitElement component structure and state management
- WebSocket subscription implementation (HA API pattern)
- Panel registration approach (`async_register_built_in_panel` vs. custom)
- Chart library for consumption charts (HA internal ApexCharts or similar)
- Popup/Dialog implementation for instructions
- CSS/Styling in HA Material Design system
- Wizard state persistence (localStorage vs. HA Config Entry)
- Responsive layout for mobile/desktop

### Deferred Ideas (OUT OF SCOPE)
- Englische Uebersetzung des Panels -- v2
- Fronius Gen24 als zweiter WR-Typ im Wizard -- kommt mit INV-01
- SMA/weitere WR-Typen -- Community-Beitraege
- Erweiterte Dashboard-Widgets (historische Charts, Einspeisung-Statistiken)
- Dark Mode spezifisches Styling (HA Dark Mode auto via CSS Custom Properties)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INF-04 | Onboarding Panel -- HA Sidebar Panel (LitElement/JS) with step-by-step setup wizard, prerequisite checks, sensor mapping with context help, dependency guidance | Panel registration pattern (HACS-proven), WebSocket API for config read/write, ha-entity-picker loading strategy, ECharts/chart integration for dashboard |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LitElement (via HA global) | HA-bundled | Web component framework | HA frontend is built on Lit; panels can access it from HA's global scope |
| home-assistant-js-websocket | HA-bundled | WebSocket client for entity subscriptions | Already loaded in every HA frontend session via `hass.connection` |
| ECharts (via ha-chart-base) | HA-bundled | Chart rendering | HA's internal chart component; no extra dependency |

### Supporting
| Library | Purpose | When to Use |
|---------|---------|-------------|
| @kipk/load-ha-components | Dynamic loader for HA web components | Loading ha-entity-picker, ha-form, ha-selector in panel context |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ha-chart-base (ECharts) | Chart.js standalone | More reliable loading (no HA lazy-load dependency) but adds ~60KB, different look |
| LitElement class | Plain HTMLElement + Shadow DOM | Simpler (no Lit dependency), but more boilerplate; HACS uses plain HTMLElement |
| @kipk/load-ha-components | Custom loader function | Fewer dependencies but must maintain loading logic yourself |

**Recommendation for charts:** Use a lightweight standalone approach. Since `ha-chart-base` requires HA's internal ECharts module (lazy-loaded, not easily importable), use a self-contained SVG-based approach or inline Canvas rendering for the two simple charts needed (7-day bar chart, 24h line chart). This avoids the lazy-loading problem entirely. If complexity grows, bundle Chart.js (~60KB).

**Recommendation for component loading:** Implement a simple custom loader function (5-10 lines) that calls `customElements.whenDefined()` with a timeout, rather than adding an npm dependency. The panel only needs `ha-entity-picker` -- other form inputs can use standard HTML elements styled with HA CSS variables.

## Architecture Patterns

### Recommended Project Structure
```
custom_components/eeg_energy_optimizer/
  __init__.py          # + panel registration + WebSocket command registration
  config_flow.py       # reduced to 1-click (VERSION 4)
  websocket_api.py     # NEW: WebSocket command handlers (get/save config, check prerequisites)
  frontend/
    eeg-optimizer-panel.js   # Main panel entry point (custom element)
```

### Pattern 1: Panel Registration (HACS-proven)
**What:** Register a sidebar panel from a custom integration using `async_register_built_in_panel` with `component_name="custom"`.
**When to use:** Always for custom integration panels.
**Example:**
```python
# Source: HACS integration frontend.py (verified)
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig

PANEL_URL = "/eeg_optimizer_panel"
PANEL_PATH = str(Path(__file__).parent / "frontend")

async def async_register_panel(hass):
    """Register the EEG Optimizer panel."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, PANEL_PATH, cache_headers=False)]
    )

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="EEG Optimizer",
        sidebar_icon="mdi:solar-power",
        frontend_url_path="eeg-optimizer",
        config={
            "_panel_custom": {
                "name": "eeg-optimizer-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{PANEL_URL}/eeg-optimizer-panel.js",
            }
        },
        require_admin=False,
    )
```

### Pattern 2: WebSocket Command Registration
**What:** Register custom WS commands for config read/write from the panel.
**When to use:** Any backend communication from the panel.
**Example:**
```python
# Source: HA Developer Docs (verified)
import voluptuous as vol
from homeassistant.components import websocket_api

@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/get_config",
})
@websocket_api.async_response
async def ws_get_config(hass, connection, msg):
    """Return current integration config."""
    entries = hass.config_entries.async_entries("eeg_energy_optimizer")
    if entries:
        entry = entries[0]
        connection.send_result(msg["id"], {**entry.data, **entry.options})
    else:
        connection.send_error(msg["id"], "not_configured", "Integration not set up")

@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/save_config",
    vol.Required("config"): dict,
})
@websocket_api.async_response
async def ws_save_config(hass, connection, msg):
    """Save config to the config entry."""
    entries = hass.config_entries.async_entries("eeg_energy_optimizer")
    if entries:
        entry = entries[0]
        hass.config_entries.async_update_entry(entry, data=msg["config"])
        connection.send_result(msg["id"], {"success": True})

# Registration in async_setup_entry:
websocket_api.async_register_command(hass, ws_get_config)
websocket_api.async_register_command(hass, ws_save_config)
```

### Pattern 3: Frontend Panel Custom Element
**What:** JavaScript custom element that receives `hass`, `panel`, `narrow`, `route` properties.
**When to use:** The panel JS file.
**Example:**
```javascript
// Source: HA Developer Docs + HACS pattern (verified)
class EegOptimizerPanel extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._view = "dashboard"; // "dashboard" | "wizard"
    this._wizardStep = 0;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set panel(panel) {
    this._config = panel.config;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._render();
  }

  // Call backend via WebSocket
  async _loadConfig() {
    return await this._hass.callWS({ type: "eeg_optimizer/get_config" });
  }

  async _saveConfig(config) {
    return await this._hass.callWS({
      type: "eeg_optimizer/save_config",
      config: config,
    });
  }

  // Check prerequisites
  async _checkPrerequisites() {
    return await this._hass.callWS({
      type: "eeg_optimizer/check_prerequisites",
    });
  }

  _render() {
    if (!this._hass) return;
    // Render dashboard or wizard based on this._view
  }
}

customElements.define("eeg-optimizer-panel", EegOptimizerPanel);
```

### Pattern 4: Entity Subscriptions for Live Dashboard
**What:** Use `hass` property updates for real-time entity data. The `hass` setter is called by HA whenever any entity state changes.
**When to use:** Dashboard live updates.
**Example:**
```javascript
set hass(hass) {
  const oldHass = this._hass;
  this._hass = hass;

  // Only re-render if relevant entities changed
  const watchedEntities = [
    "select.eeg_energy_optimizer_optimizer",
    "sensor.eeg_energy_optimizer_entscheidung",
    "sensor.eeg_energy_optimizer_pv_prognose_heute",
  ];

  if (oldHass) {
    const changed = watchedEntities.some(
      (e) => hass.states[e] !== oldHass.states[e]
    );
    if (!changed) return;
  }
  this._render();
}
```

### Pattern 5: Using ha-entity-picker
**What:** Load HA's built-in entity picker in the panel context.
**When to use:** Sensor mapping wizard steps.
**Example:**
```javascript
async _ensureEntityPicker() {
  if (customElements.get("ha-entity-picker")) return;
  // Trigger HA to load the component by briefly creating a partial-panel-resolver
  const helpers = await window.loadCardHelpers?.();
  if (helpers) {
    // Creating a dummy entity card forces HA to load entity picker
    await helpers.createCardElement({ type: "entity", entity: "sun.sun" });
  }
  // Wait for it to be defined
  await customElements.whenDefined("ha-entity-picker");
}
```

### Anti-Patterns to Avoid
- **Importing Lit from CDN:** Do NOT import LitElement from unpkg.com. Use plain HTMLElement with Shadow DOM or access Lit from HA's global scope. CDN imports add load time and version conflicts.
- **Polling for state changes:** Do NOT use setInterval to poll entity states. The `hass` setter is called automatically by HA on every state change.
- **Storing config in localStorage only:** Wizard progress can use localStorage for crash recovery, but final config MUST be saved to the config entry via WebSocket commands.
- **Large bundled JS frameworks:** Do NOT bundle React, Vue, or Angular. The panel JS should be a single file, ideally under 100KB.
- **Synchronous rendering:** Do NOT block the main thread with heavy rendering. Use requestAnimationFrame or microtask scheduling for complex UI updates.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Entity picker with autocomplete | Custom dropdown with entity search | `ha-entity-picker` (dynamically loaded) | Handles 3000+ entities, fuzzy search, domain filtering, device grouping |
| WebSocket connection management | Custom WebSocket client | `this._hass.callWS()` / `this._hass.connection` | Already authenticated, handles reconnection, message queuing |
| Theming / dark mode | Custom CSS color variables | HA CSS custom properties (`--primary-color`, `--card-background-color`, etc.) | Automatically matches user's HA theme including dark mode |
| Panel routing | Custom URL router | `location.hash` or simple view state variable | Panel is single-page; hash-based routing is sufficient for dashboard/wizard toggle |
| Integration prerequisite check | Frontend-only entity scanning | Backend WebSocket command checking `hass.config_entries.async_entries()` | More reliable, handles edge cases (loaded vs. not_loaded states) |

**Key insight:** The HA frontend already provides authenticated WebSocket connections, entity state subscriptions, and themed UI components. The panel should leverage these rather than building parallel infrastructure.

## Common Pitfalls

### Pitfall 1: ha-entity-picker Not Loaded
**What goes wrong:** Panel renders `<ha-entity-picker>` but it shows as empty/undefined because the component hasn't been lazy-loaded yet.
**Why it happens:** HA lazy-loads most `ha-*` components. They are only defined when the corresponding built-in panel is visited.
**How to avoid:** Use `window.loadCardHelpers()` to trigger component loading, then `customElements.whenDefined("ha-entity-picker")` before rendering.
**Warning signs:** Empty/invisible form fields, "undefined is not a constructor" console errors.

### Pitfall 2: Config Entry Race Condition
**What goes wrong:** Panel tries to read config before the integration is fully set up, or saves config while a reload is in progress.
**Why it happens:** `async_setup_entry` and config entry updates trigger integration reloads.
**How to avoid:** WebSocket commands should check entry state, and the panel should handle "not_configured" responses gracefully. After saving config that triggers a reload, show a loading indicator and re-fetch config after a short delay.
**Warning signs:** "Integration not found" errors, stale config displayed after save.

### Pitfall 3: Panel Not Removed on Unload
**What goes wrong:** After uninstalling the integration, the sidebar panel remains as a dead link.
**Why it happens:** `async_register_built_in_panel` registers globally; `async_unload_entry` must explicitly remove it.
**How to avoid:** In `async_unload_entry`, call `async_remove_panel(hass, "eeg-optimizer")`.
**Warning signs:** Orphaned sidebar entry after integration removal.

### Pitfall 4: Static Path Caching
**What goes wrong:** After updating the JS file, the browser serves the old cached version.
**Why it happens:** Browser and HA cache static paths aggressively.
**How to avoid:** Use `cache_headers=False` in `StaticPathConfig` during development. For production, append a version query parameter to the JS URL (e.g., `?v=0.2.0`).
**Warning signs:** Code changes not reflected after restart.

### Pitfall 5: Shadow DOM CSS Isolation
**What goes wrong:** HA CSS variables don't apply inside Shadow DOM, or panel styles leak into the HA shell.
**Why it happens:** Shadow DOM creates CSS isolation by default.
**How to avoid:** Explicitly use `:host` and HA CSS custom properties in the shadow stylesheet. CSS custom properties DO penetrate shadow boundaries (by design), so `var(--primary-color)` works.
**Warning signs:** Panel appears unstyled or uses wrong colors.

### Pitfall 6: Config Flow VERSION Migration
**What goes wrong:** Existing installations break after config flow changes because old config data doesn't match new expectations.
**Why it happens:** VERSION bump from 3 to 4 requires migration of existing config entries.
**How to avoid:** Implement `async_migrate_entry` for version 4 that preserves all existing Phase 1-3 config keys and sets defaults for any new Phase 4 keys.
**Warning signs:** "Migration failed" errors on HA restart, integration fails to load.

## Code Examples

### Complete Panel Registration in __init__.py
```python
# Source: HACS pattern + HA core frontend API (verified)
from pathlib import Path
from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig

PANEL_FRONTEND_URL = "/eeg_optimizer_panel"
PANEL_ICON = "mdi:solar-power"
PANEL_TITLE = "EEG Optimizer"
PANEL_URL_PATH = "eeg-optimizer"

async def _async_register_panel(hass) -> None:
    frontend_path = str(Path(__file__).parent / "frontend")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_FRONTEND_URL, frontend_path, cache_headers=False)]
    )
    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            config={
                "_panel_custom": {
                    "name": "eeg-optimizer-panel",
                    "embed_iframe": False,
                    "trust_external": False,
                    "js_url": f"{PANEL_FRONTEND_URL}/eeg-optimizer-panel.js",
                }
            },
            require_admin=False,
        )
```

### WebSocket Prerequisite Check Command
```python
# Source: HA Developer Docs websocket_api pattern (verified)
import voluptuous as vol
from homeassistant.components import websocket_api

@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/check_prerequisites",
})
@websocket_api.async_response
async def ws_check_prerequisites(hass, connection, msg):
    """Check if required integrations are installed and loaded."""
    result = {
        "huawei_solar": False,
        "solcast_solar": False,
        "forecast_solar": False,
    }
    for domain in result:
        entries = hass.config_entries.async_entries(domain)
        loaded = [e for e in entries if e.state.value == "loaded"]
        result[domain] = len(loaded) > 0

    connection.send_result(msg["id"], result)
```

### Wizard State Persistence Strategy
```javascript
// Source: Community best practice (MEDIUM confidence)
// Use localStorage for wizard crash recovery, config entry for final save
const WIZARD_STATE_KEY = "eeg_optimizer_wizard_state";

function saveWizardProgress(step, data) {
  localStorage.setItem(WIZARD_STATE_KEY, JSON.stringify({ step, data, ts: Date.now() }));
}

function loadWizardProgress() {
  const raw = localStorage.getItem(WIZARD_STATE_KEY);
  if (!raw) return null;
  const state = JSON.parse(raw);
  // Expire after 24 hours
  if (Date.now() - state.ts > 86400000) {
    localStorage.removeItem(WIZARD_STATE_KEY);
    return null;
  }
  return state;
}

function clearWizardProgress() {
  localStorage.removeItem(WIZARD_STATE_KEY);
}
```

### HA CSS Custom Properties for Theming
```css
/* Source: HA frontend source + community panels (verified) */
:host {
  display: block;
  padding: 16px;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--paper-font-common-base_-_font-family, Roboto, sans-serif);
}

.card {
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  box-shadow: var(--ha-card-box-shadow, 0 2px 2px rgba(0,0,0,.14));
  padding: 16px;
  margin-bottom: 16px;
}

.btn-primary {
  background: var(--primary-color);
  color: var(--text-primary-color);
  border: none;
  border-radius: 4px;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
}

.btn-primary:hover {
  opacity: 0.9;
}

.status-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.active { background: var(--success-color, #4caf50); color: white; }
.status-badge.warning { background: var(--warning-color, #ff9800); color: white; }
.status-badge.inactive { background: var(--disabled-color, #bdbdbd); color: white; }
```

### manifest.json Dependencies Update
```json
{
  "dependencies": ["recorder", "sun", "http", "frontend", "websocket_api"],
  "after_dependencies": ["huawei_solar", "solcast_solar", "forecast_solar"]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `panel_custom` in configuration.yaml | `async_register_built_in_panel` from integration code | HA 0.115+ | Integrations register panels programmatically, no YAML needed |
| Polymer-based panels | Lit/LitElement-based panels | HA 2023+ | Polymer deprecated, Lit is the standard |
| `hass.components.frontend.async_register_built_in_panel` | Direct import from `homeassistant.components.frontend` | HA 2024.9 | Accessing via `hass.components` deprecated |
| Chart.js / ApexCharts external | ha-chart-base (ECharts wrapper) | HA 2024+ | HA's internal chart component standardized on ECharts |

**Deprecated/outdated:**
- `panel_custom` YAML configuration: Still works but not recommended for integrations that register panels programmatically
- `hass.components.frontend.*` access pattern: Deprecated since HA 2024.9, use direct imports instead
- Polymer web components: Fully replaced by Lit

## Open Questions

1. **ha-entity-picker Reliability in Panels**
   - What we know: `loadCardHelpers()` + `createCardElement()` trick works for Lovelace cards to trigger lazy loading of `ha-entity-picker`
   - What's unclear: Whether this trick works reliably in sidebar panel context (not Lovelace context)
   - Recommendation: Implement the loader with a fallback to a plain text input field. Test on the target HA instance early. If unreliable, use a simpler entity selector approach (fetch entity list via WS, render as searchable dropdown).

2. **ha-chart-base Availability in Custom Panels**
   - What we know: HA uses ECharts internally via `ha-chart-base`, but it's lazy-loaded like other components
   - What's unclear: Whether custom panels can reliably trigger ECharts loading
   - Recommendation: For the two simple charts needed (7-day bar, 24h line), use inline SVG generation or a minimal Canvas-based renderer. Avoids the lazy-loading problem entirely. If charts need to be more sophisticated later, evaluate bundling a lightweight library.

3. **Config Entry Update After Panel Save**
   - What we know: `hass.config_entries.async_update_entry()` updates the entry and triggers `_async_update_listener` which reloads the integration
   - What's unclear: Whether reloading the integration (which unloads/re-loads platforms + panel) causes the panel to disconnect or flash
   - Recommendation: After saving config, the WebSocket command should update the entry but potentially skip the full reload for non-critical changes (e.g., optimizer parameters). For sensor remapping or inverter type changes, a full reload is necessary -- show a "Wird neu geladen..." overlay.

4. **HACS Distribution of Panel JS Files**
   - What we know: HACS copies `custom_components/eeg_energy_optimizer/` to the target; static paths registered via `async_register_static_paths` serve from that directory
   - What's unclear: Whether the `frontend/` subdirectory is properly distributed
   - Recommendation: Include `frontend/` as a subdirectory of the integration. HACS copies the entire `custom_components/eeg_energy_optimizer/` tree. Verify with a test HACS install.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Manual testing against live HA instance |
| Config file | none -- no automated test framework in project |
| Quick run command | Manual: load panel in browser, verify sidebar appears |
| Full suite command | Manual: complete wizard flow, verify dashboard data |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INF-04a | Sidebar panel appears after installation | smoke | Manual: HA restart, check sidebar | N/A |
| INF-04b | Wizard checks prerequisites | integration | Manual: remove Huawei Solar, verify wizard blocks | N/A |
| INF-04c | Sensor mapping with entity picker | integration | Manual: complete wizard step 4-5, verify entity selection | N/A |
| INF-04d | Config saved via wizard matches config entry | integration | Manual: complete wizard, check entry.data in HA dev tools | N/A |
| INF-04e | Dashboard shows live optimizer data | smoke | Manual: verify sensor values update in panel | N/A |
| INF-04f | Config flow reduced to 1-click | smoke | Manual: add integration, verify single-step flow | N/A |

### Sampling Rate
- **Per task commit:** Manual panel reload in browser + check console for errors
- **Per wave merge:** Complete wizard walkthrough + dashboard verification
- **Phase gate:** Full wizard flow + dashboard with live data + config flow 1-click

### Wave 0 Gaps
- [ ] `custom_components/eeg_energy_optimizer/frontend/` directory -- create with panel JS file
- [ ] `custom_components/eeg_energy_optimizer/websocket_api.py` -- WebSocket command handlers
- [ ] Panel registration code in `__init__.py`

## Sources

### Primary (HIGH confidence)
- [HA Developer Docs: Creating Custom Panels](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/) -- panel structure, properties, registration
- [HA Developer Docs: WebSocket API](https://developers.home-assistant.io/docs/frontend/extending/websocket-api/) -- command registration, decorators, async_response
- [HA Core source: frontend/__init__.py](https://github.com/home-assistant/core/blob/dev/homeassistant/components/frontend/__init__.py) -- async_register_built_in_panel signature and Panel class
- [HACS integration: frontend.py](https://github.com/hacs/integration/blob/main/custom_components/hacs/frontend.py) -- proven panel registration pattern
- [home-assistant-js-websocket](https://github.com/home-assistant/home-assistant-js-websocket) -- subscribeEntities, callWS, connection API

### Secondary (MEDIUM confidence)
- [Community Guide: Adding Sidebar Panel to Integration](https://community.home-assistant.io/t/how-to-add-a-sidebar-panel-to-a-home-assistant-integration/981585) -- complete end-to-end example with Python + JS
- [DeepWiki: HA Frontend Data Visualization](https://deepwiki.com/home-assistant/frontend/5-data-visualization) -- ha-chart-base, ECharts usage
- [KipK/load-ha-components](https://github.com/KipK/load-ha-components) -- dynamic HA component loading utility
- [HA Community: Use of HA Web Components in Custom UI](https://community.home-assistant.io/t/use-of-ha-web-components-in-custom-ui/379296) -- lazy loading challenges and solutions

### Tertiary (LOW confidence)
- Chart approach recommendation (inline SVG/Canvas vs. ha-chart-base) -- based on analysis of lazy-loading challenges, not directly verified in a custom panel context
- `loadCardHelpers()` trick for entity picker in panels -- verified for Lovelace cards but not explicitly tested in sidebar panel context

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM -- Panel registration pattern is well-proven (HACS uses it), but ha-entity-picker loading and charts in panel context are less documented
- Architecture: HIGH -- WebSocket command pattern, config entry management, and panel JS structure are well-documented in HA developer docs
- Pitfalls: HIGH -- Lazy loading issues, config entry race conditions, and panel cleanup are well-known in the community

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (30 days -- HA frontend API is relatively stable)
