---
phase: quick-260406-ufh
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [SETTINGS-SCREEN, CONFIG-TOGGLES, DASHBOARD-GATING]

must_haves:
  truths:
    - "Gear button on dashboard opens Settings screen (not Wizard)"
    - "Settings screen shows 3 cards: Expertenmodus, Ladung & Einspeisung, Erweiterte Einstellungen"
    - "Wizard Restart button in Settings starts Wizard at step 0"
    - "Saving settings persists to config entry and reloads integration"
    - "Dashboard hides Manual Control card when enable_manual_control is false"
    - "Dashboard hides Simulation card when enable_simulation is false"
    - "Existing expert_mode users get both new toggles set to true after migration"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/const.py"
      provides: "CONF_ENABLE_SIMULATION, CONF_ENABLE_MANUAL_CONTROL constants"
      contains: "CONF_ENABLE_SIMULATION"
    - path: "custom_components/eeg_energy_optimizer/__init__.py"
      provides: "Config migration v10"
      contains: "version < 10"
    - path: "custom_components/eeg_energy_optimizer/config_flow.py"
      provides: "VERSION = 10"
      contains: "VERSION = 10"
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Settings view, dashboard gating, wizard restart"
      contains: "_renderSettings"
  key_links:
    - from: "frontend/eeg-optimizer-panel.js _renderSettings()"
      to: "websocket_api save_config"
      via: "save-settings action calls _saveSettings() which sends WebSocket save_config"
      pattern: "save-settings.*save_config"
    - from: "frontend/eeg-optimizer-panel.js _renderDashboard()"
      to: "this._config.enable_manual_control / enable_simulation"
      via: "conditional rendering of Manual Control and Simulation cards"
      pattern: "enable_manual_control|enable_simulation"
    - from: "__init__.py migration v10"
      to: "config entry data"
      via: "setdefault with smart expert_mode-based defaults"
      pattern: "enable_simulation.*is_expert"
---

<objective>
Add a Settings screen as a third view mode in the panel. After setup is complete, the gear button opens this Settings screen (not the Wizard). The Settings screen has 3 cards (Expertenmodus, Ladung & Einspeisung, Erweiterte Einstellungen) plus a Wizard Restart button. Two new config toggles (enable_simulation, enable_manual_control) control dashboard card visibility.

Purpose: Clean dashboard for normal users, expert features opt-in via Settings.
Output: Updated panel JS with settings view, config migration v10, dashboard card gating.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/260406-ufh-einstellungen-screen-statt-wizard-nach-s/260406-ufh-CONTEXT.md
@.planning/quick/260406-ufh-einstellungen-screen-statt-wizard-nach-s/260406-ufh-RESEARCH.md
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
@custom_components/eeg_energy_optimizer/__init__.py
@custom_components/eeg_energy_optimizer/config_flow.py
@custom_components/eeg_energy_optimizer/const.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Backend — Config migration v10 + constants</name>
  <files>custom_components/eeg_energy_optimizer/const.py, custom_components/eeg_energy_optimizer/config_flow.py, custom_components/eeg_energy_optimizer/__init__.py</files>
  <action>
1. **const.py** — Add two new constants after the existing CONF_ block (around line 61):
   ```python
   CONF_ENABLE_SIMULATION = "enable_simulation"
   CONF_ENABLE_MANUAL_CONTROL = "enable_manual_control"
   ```

2. **config_flow.py** — Bump VERSION from 9 to 10 (line 24).

3. **__init__.py** — Add migration v10 block after the `if entry.version < 9:` block (after line 349, before `return True`):
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
   IMPORTANT: Smart defaults — existing expert_mode=true users get both toggles set to true (per Research pitfall 4). New users get false.
  </action>
  <verify>
    <automated>cd custom_components/eeg_energy_optimizer && python -c "from const import CONF_ENABLE_SIMULATION, CONF_ENABLE_MANUAL_CONTROL; print('OK')" && python -c "from config_flow import EegEnergyOptimizerConfigFlow; assert EegEnergyOptimizerConfigFlow.VERSION == 10; print('OK')"</automated>
  </verify>
  <done>const.py has both new CONF_ constants, config_flow VERSION=10, __init__.py has migration v10 with smart expert_mode defaults</done>
</task>

<task type="auto">
  <name>Task 2: Frontend — Settings screen + dashboard gating + wizard restart</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
This is a large panel file (3792 lines). All changes are in eeg-optimizer-panel.js.

**A. WIZARD_DEFAULTS (line 66-106)** — Add two new keys:
```javascript
enable_simulation: false,
enable_manual_control: false,
```

**B. Change listener for settings fields (around line 663-669)** — Before the generic `_wizardData[field]` assignment, add handling for `settings_` prefixed fields:
```javascript
if (field.startsWith("settings_")) {
  const realField = field.replace("settings_", "");
  if (type === "checkbox") {
    this._settingsData[realField] = target.checked;
  } else if (type === "number") {
    this._settingsData[realField] = parseFloat(target.value) || 0;
  } else if (type === "time") {
    this._settingsData[realField] = target.value;
  } else {
    this._settingsData[realField] = target.value;
  }
  this._render();
  return;
}
```
Also add in the `change` event listener (around line 672-701) a handler for `settings_` checkbox fields:
```javascript
if (field.startsWith("settings_")) {
  const realField = field.replace("settings_", "");
  this._settingsData[realField] = target.checked;
  this._render();
  return;
}
```

**C. _handleAction (line 704-882)** — Add new action cases:
- `"open-settings"`: `this._settingsData = {...this._config}; this._view = "settings"; this._render();`
- `"restart-wizard"`: call `this._clearWizardProgress(); this._wizardStep = 0; this._wizardData = {...WIZARD_DEFAULTS}; this._view = "wizard"; this._render();` (explicit step 0 to bypass the setup_complete jump-to-step-4 in _startWizard)
- `"save-settings"`: call `this._saveSettings()` (new async method)
- `"back-to-dashboard"` already exists (line 710-712), keep as-is — it works for settings too

**D. New method `_saveSettings()`** — Add after `_finishWizard()` (around line 1070):
```javascript
async _saveSettings() {
  try {
    const changed = {};
    const cfg = this._config || {};
    for (const [k, v] of Object.entries(this._settingsData)) {
      if (JSON.stringify(v) !== JSON.stringify(cfg[k])) changed[k] = v;
    }
    if (Object.keys(changed).length === 0) {
      this._view = "dashboard"; this._render(); return;
    }
    await this._hass.callWS({ type: "eeg_optimizer/save_config", config: changed });
    this._view = "dashboard";
    await this._waitForOptimizer();
  } catch (err) {
    console.error("Settings save error:", err);
    alert("Fehler beim Speichern: " + err.message);
  }
}
```
Uses `_waitForOptimizer()` for integration reload recovery (per Research pitfall 1).

**E. New method `_renderSettings()`** — Add after `_renderStep6()`. Renders 3 cards:

Card layout (max-width 600px, centered):

1. **Wizard Restart Button** at top — secondary style button with mdi:refresh icon, text "Wizard nochmal starten", data-action="restart-wizard"

2. **Card 1: Expertenmodus** — Single toggle:
   - Checkbox `data-field="settings_expert_mode"` checked from `this._settingsData.expert_mode`
   - Label: "Expertenmodus" with help text "Zeigt erweiterte Einstellungen und zusaetzliche Optionen"

3. **Card 2: Ladung & Einspeisung** — All fields from _renderStep4 adapted for settings context:
   - Toggle: Verzoegerte Batterieladung (enable_morning_delay) — use feature-card style with click toggle via data-action="toggle-settings-feature" data-feature="enable_morning_delay"
   - If expert + morning enabled: morning_end_time input
   - Toggle: Nachteinspeisung (enable_night_discharge) — same feature-card style
   - If discharge enabled: min_soc input
   - If expert + discharge enabled: discharge_start_time, discharge_power_kw inputs
   - If expert: safety_buffer_pct input
   - All fields use `data-field="settings_FIELDNAME"` prefix and read from `this._settingsData`

4. **Card 3: Erweiterte Einstellungen** — Fields from _renderStep5 + new toggles:
   - lookback_weeks input
   - update_interval_fast_min input
   - update_interval_slow_min input
   - If expert mode: enable_simulation checkbox toggle, enable_manual_control checkbox toggle
   - All with `settings_` prefix

5. **Save Button** at bottom — primary style, data-action="save-settings", text "Speichern"

Add action handler for `"toggle-settings-feature"` in _handleAction:
```javascript
case "toggle-settings-feature": {
  const feat = dataset?.feature;
  if (feat) { this._settingsData[feat] = !this._settingsData[feat]; this._render(); }
  break;
}
```

**F. _renderInner header (line 3314-3325)** — Change gear button action and add settings case:
- Line 3317: Change `data-action="open-wizard"` to `data-action="open-settings"`
- Add new else-if for settings view between dashboard and wizard cases:
  ```javascript
  } else if (this._view === "settings") {
    headerRight = `<button data-action="back-to-dashboard" title="Zurueck"><ha-icon icon="mdi:arrow-left"></ha-icon></button>`;
  ```

**G. _renderInner content (line 3327-3352)** — Add settings branch:
- After `if (this._view === "wizard")` block, add:
  ```javascript
  else if (this._view === "settings") {
    content = `<div class="content">${this._renderSettings()}</div>`;
  }
  ```

**H. Dashboard card gating (line 3137-3269)** — Replace the single `expert_mode` gate:
- Replace `${this._config?.expert_mode ? \`` (line 3137) with two separate gates:
  - `${this._config?.enable_manual_control ? \`` wrapping ONLY the Manual Control card (lines 3138-3205)
  - `${this._config?.enable_simulation ? \`` wrapping ONLY the Simulation card (lines 3207-3268)
- Each gets its own closing `\` : ""}` instead of the combined one at line 3269
- Remove the single `<!-- Expert mode disabled -->` comment at line 3269

**I. Wizard Step 5 (_renderStep5, line 2206-2233)** — Add the new toggles at the end (before closing backtick), visible only in expert mode:
```javascript
${this._wizardData.expert_mode ? `
<div style="margin-top:24px">
  <h3 style="margin:0 0 12px;font-size:16px">Dashboard-Bereiche</h3>
  <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer">
    <input type="checkbox" data-field="enable_simulation" ${this._wizardData.enable_simulation ? "checked" : ""}>
    Simulation am Dashboard anzeigen
  </label>
  <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
    <input type="checkbox" data-field="enable_manual_control" ${this._wizardData.enable_manual_control ? "checked" : ""}>
    Manuelle Steuerung am Dashboard anzeigen
  </label>
</div>` : ""}
```
  </action>
  <verify>
    <automated>node -e "const fs=require('fs'); const c=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); const checks=['_renderSettings','open-settings','restart-wizard','save-settings','_saveSettings','enable_simulation','enable_manual_control','settings_expert_mode','toggle-settings-feature']; const missing=checks.filter(s=>!c.includes(s)); if(missing.length){console.error('MISSING:',missing);process.exit(1)}; console.log('All markers found');"</automated>
  </verify>
  <done>
    - Gear button opens Settings screen (not Wizard)
    - Settings screen renders 3 cards with all configurable fields
    - Wizard restart button starts at step 0 (clears localStorage)
    - Save persists via WebSocket and waits for optimizer reload
    - Dashboard Manual Control card gated by enable_manual_control
    - Dashboard Simulation card gated by enable_simulation
    - Wizard step 5 shows new toggles in expert mode
    - Both new keys in WIZARD_DEFAULTS with default false
  </done>
</task>

</tasks>

<verification>
1. Open panel at /eeg-optimizer on a configured instance
2. Gear button opens Settings screen with 3 cards
3. "Wizard nochmal starten" button starts wizard at step 0 (Willkommen)
4. Toggle expert mode in settings, verify expanded fields appear
5. Enable/disable simulation and manual control toggles, save
6. Dashboard shows/hides corresponding cards based on toggle state
7. Existing expert_mode users: after migration both dashboard sections still visible
</verification>

<success_criteria>
- Settings screen accessible via gear button after setup
- All optimizer settings editable in one screen (no wizard steps)
- Wizard restart works from step 0
- Dashboard cards visibility controlled by individual toggles
- Config migration v10 preserves existing expert user experience
</success_criteria>

<output>
After completion, create `.planning/quick/260406-ufh-einstellungen-screen-statt-wizard-nach-s/260406-ufh-SUMMARY.md`
</output>
