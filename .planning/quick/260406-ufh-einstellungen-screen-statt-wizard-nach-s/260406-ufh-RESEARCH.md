# Quick Task 260406-ufh: Einstellungen-Screen statt Wizard - Research

**Researched:** 2026-04-06
**Domain:** Panel JS view switching, config entry migration, dashboard conditional rendering
**Confidence:** HIGH

## Summary

This task adds a third view mode ("settings") to the panel alongside "dashboard" and "wizard". The existing codebase has clean separation points for this: `_view` state variable controls rendering, `_handleAction()` dispatches view transitions, and `_renderDashboard()` already conditionally shows cards based on `expert_mode`. The new `enable_simulation` and `enable_manual_control` config keys replace the single `expert_mode` gate on the two dashboard cards.

**Primary recommendation:** Add `_view = "settings"` as a third render branch in `_renderInner()`, build `_renderSettings()` reusing field markup from `_renderStep4()`/`_renderStep5()`, and change the gear button action from `open-wizard` to `open-settings`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Settings-Layout**: Three Cards stacked vertically: (1) Expertenmodus-Toggle, (2) Ladung & Einspeisung, (3) Erweiterte Einstellungen (Lookback, intervals + in expert mode: Simulation-Toggle, Manuelle Steuerung-Toggle)
- **Wizard-Restart**: Button at top of settings, restarts wizard at step 0 (Willkommen), clears localStorage progress
- **Toggle-Sichtbarkeit am Dashboard**: Sections completely hidden when `enable_simulation`/`enable_manual_control` are false (default: false)
- **Neue Config-Keys**: `enable_simulation` (bool, default false), `enable_manual_control` (bool, default false), stored in config entry via WebSocket save_config

### Specific Ideas (guidance, not locked)
- Settings-Screen as new view mode `_view = "settings"`
- Gear button opens settings instead of wizard
- Settings has own "Zurueck" button to dashboard
- Wizard-Restart button sets `_view = "wizard"` with `_wizardStep = 0`
- New toggles also shown in Wizard step "Erweiterte Einstellungen"
- Config migration version 9 -> 10 for new keys with defaults
</user_constraints>

## Current Architecture (findings)

### View Switching Mechanism

**State variable:** `this._view` (line 530) - currently `"dashboard"` or `"wizard"`

**Render dispatch** in `_renderInner()` (lines 3314-3350):
```javascript
if (this._setupComplete && this._view === "dashboard") {
  headerRight = `<button data-action="open-wizard" title="Einstellungen">...`;
} else if (this._view === "wizard") {
  headerRight = `<button data-action="back-to-dashboard" title="Zurueck">...`;
}

// Content dispatch:
if (this._view === "wizard") { ... }
else if (!this._setupComplete) { ... setup card ... }
else { ... dashboard ... }
```

**Action handler** `_handleAction()` (line 704):
- `"open-wizard"` / `"start-wizard"` -> `_startWizard()`
- `"back-to-dashboard"` -> `_view = "dashboard"; _render()`

**Adding "settings" view requires:**
1. New action `"open-settings"` in `_handleAction()`
2. New `headerRight` case for `_view === "settings"` with back button
3. New content branch `else if (this._view === "settings")` calling `_renderSettings()`
4. Change gear button `data-action` from `"open-wizard"` to `"open-settings"`

### Wizard Step 4: Ladung & Einspeisung (line 2117-2201)

`_renderStep4()` renders:
- Morning delay toggle card (feature-card with click toggle)
- If expert + morning enabled: morning_end_time input
- Night discharge toggle card
- If enabled: min_soc input; if expert: discharge_start_time, discharge_power_kw inputs
- If expert: safety_buffer_pct input

**For settings reuse:** Same fields, but without feature-card toggle styling (already configured). Settings screen should show all fields directly, with expert-only fields gated by expert_mode from config.

### Wizard Step 5: Erweiterte Einstellungen (line 2204-2233)

`_renderStep5()` renders:
- lookback_weeks input
- update_interval_fast_min input  
- update_interval_slow_min input

**For settings reuse:** Same fields. New toggles `enable_simulation` and `enable_manual_control` should be added here (in both wizard step 5 AND settings screen).

### Dashboard Card Gating (lines 3137-3269)

Currently both Manual Control and Simulation cards are wrapped in a SINGLE `expert_mode` check:
```javascript
${this._config?.expert_mode ? `
  <!-- Manual Control Card --> ...
  <!-- Simulation Card --> ...
` : "<!-- Expert mode disabled -->"}
```

**Change needed:** Replace single `expert_mode` gate with two separate checks:
```javascript
${this._config?.enable_manual_control ? `<!-- Manual Control Card -->...` : ""}
${this._config?.enable_simulation ? `<!-- Simulation Card -->...` : ""}
```

### Config Save/Load Flow

**Save:** `ws_save_config` (websocket_api.py line 252-266) merges `msg["config"]` into `entry.data` via `async_update_entry`. No schema validation on keys -- any dict is accepted.

**Load:** `ws_get_config` (line 227-242) returns `{**entry.data, **entry.options}`. Panel loads config in `_loadConfig()` and stores in `this._config`.

**Settings save approach:** Call `save_config` WebSocket with changed fields only (same as wizard finish). Integration reloads automatically via `_async_update_listener`.

### Config Migration Pattern (lines 302-350)

Current version: 9. Each migration is an `if entry.version < N:` block with `setdefault()` for new keys and `async_update_entry()` bumping version.

**Version 10 migration:**
```python
if entry.version < 10:
    new_data = {**entry.data}
    new_data.setdefault("enable_simulation", False)
    new_data.setdefault("enable_manual_control", False)
    hass.config_entries.async_update_entry(entry, data=new_data, version=10)
```

### Config Flow Version

The config flow VERSION constant needs to be bumped to 10. Located in `config_flow.py`.

### WIZARD_DEFAULTS (line 66-106)

New keys need to be added to WIZARD_DEFAULTS:
```javascript
enable_simulation: false,
enable_manual_control: false,
```

### Constants (const.py)

New constants needed:
```python
CONF_ENABLE_SIMULATION = "enable_simulation"
CONF_ENABLE_MANUAL_CONTROL = "enable_manual_control"
```

## Architecture Pattern for Settings Screen

### Render Method Structure

```javascript
_renderSettings() {
  const cfg = this._config || {};
  const isExpert = cfg.expert_mode;
  return `
    <div style="max-width:600px;margin:0 auto">
      <!-- Wizard Restart Button -->
      <button class="btn-secondary" data-action="restart-wizard">
        <ha-icon icon="mdi:refresh"></ha-icon> Wizard nochmal starten
      </button>
      
      <!-- Card 1: Expertenmodus -->
      <div class="card">
        <label>Expertenmodus <input type="checkbox" data-field="settings_expert_mode" ${isExpert ? "checked" : ""}></label>
      </div>
      
      <!-- Card 2: Ladung & Einspeisung -->
      <div class="card">
        <h3>Ladung & Einspeisung</h3>
        <!-- fields from _renderStep4() adapted for settings context -->
      </div>
      
      <!-- Card 3: Erweiterte Einstellungen -->
      <div class="card">
        <h3>Erweiterte Einstellungen</h3>
        <!-- fields from _renderStep5() + new toggles -->
        ${isExpert ? `
          <label>Simulation am Dashboard <input type="checkbox" data-field="settings_enable_simulation" ...></label>
          <label>Manuelle Steuerung am Dashboard <input type="checkbox" data-field="settings_enable_manual_control" ...></label>
        ` : ""}
      </div>
      
      <!-- Save Button -->
      <button class="btn-primary" data-action="save-settings">Speichern</button>
    </div>`;
}
```

### Data Flow for Settings

1. Open settings: populate `this._settingsData` from `this._config` (like wizard does with `_wizardData`)
2. Field changes: update `_settingsData` via existing `change` event listener pattern
3. Save: call `save_config` WebSocket with changed fields, reload integration
4. Back to dashboard: `_view = "dashboard"; _render()`

**Important:** Settings save should NOT set `setup_complete = true` again (it already is). Only send changed config keys.

## Common Pitfalls

### Pitfall 1: Integration Reload After Settings Save
**What goes wrong:** `save_config` triggers `_async_update_listener` which reloads the entire integration. Dashboard state (subscriptions, timers) is lost.
**How to avoid:** After save, call `_waitForOptimizer()` (same as wizard finish, line 1063) to poll until optimizer is ready again. Show loading state during reload.

### Pitfall 2: Settings Data Not Synced With Config
**What goes wrong:** Using `_wizardData` for settings would conflict with wizard state.
**How to avoid:** Use separate `_settingsData` object, populated from `this._config` on settings open.

### Pitfall 3: Expert Mode Toggle in Settings vs Wizard
**What goes wrong:** `expert_mode` exists in both wizard (as `_wizardData.expert_mode`) and settings. Changing in settings should update config entry, not wizard state.
**How to avoid:** Settings uses `_settingsData` backed by config entry. Wizard uses `_wizardData` backed by localStorage.

### Pitfall 4: Backward Compatibility of Dashboard Gating
**What goes wrong:** Existing users have `expert_mode: true` but no `enable_simulation`/`enable_manual_control` keys. After migration they lose access to both cards.
**How to avoid:** Migration v10 should set both new keys to `true` when `expert_mode` is already `true` in existing config. This preserves current behavior for existing experts.

## Key Implementation Details

### Files to Modify

| File | Changes |
|------|---------|
| `frontend/eeg-optimizer-panel.js` | New "settings" view, `_renderSettings()`, action handlers, dashboard card gating change, WIZARD_DEFAULTS update |
| `__init__.py` | Migration v10 block |
| `config_flow.py` | VERSION = 10 |
| `const.py` | CONF_ENABLE_SIMULATION, CONF_ENABLE_MANUAL_CONTROL constants |

### Config Migration v10 - Smart Defaults

```python
if entry.version < 10:
    new_data = {**entry.data}
    # Preserve existing expert behavior: if expert_mode was on,
    # enable both new features to maintain current dashboard
    is_expert = new_data.get("expert_mode", False)
    new_data.setdefault("enable_simulation", is_expert)
    new_data.setdefault("enable_manual_control", is_expert)
    hass.config_entries.async_update_entry(entry, data=new_data, version=10)
```

### localStorage Cleanup for Wizard Restart

Wizard progress key: `WIZARD_KEY` (referenced in `_saveWizardProgress` / `_clearWizardProgress`). The restart button should call `_clearWizardProgress()` then `_startWizard()` which will naturally start at step 0 since there's no saved progress and no `setup_complete` override (wizard restart should force step 0 regardless).

Actually, looking at `_startWizard()` (line 887-907): if `setup_complete` is true and no localStorage, it jumps to step 4. The restart button needs to either:
- Clear localStorage AND temporarily set a flag to skip the step-4 jump, OR
- Set `_wizardStep = 0` explicitly AFTER `_startWizard()`

Simplest: add a `_restartWizard()` method that clears progress, sets `_view = "wizard"`, `_wizardStep = 0`, resets `_wizardData`.

## Sources

### Primary (HIGH confidence)
- Direct code analysis of `eeg-optimizer-panel.js` (3792 lines)
- Direct code analysis of `__init__.py` (migration pattern, lines 302-350)
- Direct code analysis of `websocket_api.py` (save_config, lines 252-266)
- Direct code analysis of `const.py` (all constants)

## Metadata

**Confidence breakdown:**
- View switching mechanism: HIGH - direct code reading
- Config migration: HIGH - clear pattern from 9 prior migrations
- Dashboard card gating: HIGH - direct code reading
- Settings data flow: HIGH - follows established wizard pattern

**Research date:** 2026-04-06
**Valid until:** 2026-05-06
