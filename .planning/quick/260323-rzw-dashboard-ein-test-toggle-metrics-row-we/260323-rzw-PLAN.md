---
phase: quick
plan: 260323-rzw
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/select.py
  - tests/test_select.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "Dashboard shows an Ein/Test toggle switch instead of the old mode badge"
    - "Toggling the switch calls HA select service to change optimizer mode"
    - "Metrics row (Batterie SOC, PV Heute, PV Morgen) is no longer shown"
    - "Mode badge on Abend-Entladung card is removed"
    - "Select entity only offers Ein and Test as options (no Aus)"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Toggle switch UI, removed metrics row, removed mode badge"
    - path: "custom_components/eeg_energy_optimizer/const.py"
      provides: "OPTIMIZER_MODES without MODE_AUS"
    - path: "custom_components/eeg_energy_optimizer/select.py"
      provides: "Select entity defaulting to MODE_TEST, options=[Ein, Test]"
  key_links:
    - from: "eeg-optimizer-panel.js toggle click"
      to: "HA select.select_option service"
      via: "hass.callService in click handler"
      pattern: "callService.*select.*select_option"
---

<objective>
Dashboard UI cleanup: replace mode badge with Ein/Test toggle switch, remove metrics row, remove mode badge from discharge card, and restrict select entity to Ein/Test only.

Purpose: Simplify the dashboard by removing redundant information and providing a direct toggle for the most common mode switch.
Output: Updated panel JS, updated const.py and select.py
</objective>

<execution_context>
@C:\Users\RobertHell\.claude\get-shit-done\workflows\execute-plan.md
@C:\Users\RobertHell\.claude\get-shit-done\templates\summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
@custom_components/eeg_energy_optimizer/const.py
@custom_components/eeg_energy_optimizer/select.py
@tests/test_select.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove Aus from backend select entity</name>
  <files>custom_components/eeg_energy_optimizer/const.py, custom_components/eeg_energy_optimizer/select.py, tests/test_select.py</files>
  <action>
In const.py:
- Change OPTIMIZER_MODES to `[MODE_EIN, MODE_TEST]` (remove MODE_AUS from the list).
- Keep MODE_AUS constant defined for backwards compatibility (it is still used as a fallback in __init__.py line 328 when the select entity is not yet ready -- this is a safety default, not user-facing).

In select.py:
- Change `_attr_current_option = MODE_AUS` to `_attr_current_option = MODE_TEST` (default to Test instead of Aus).
- In `async_added_to_hass`, the restore logic already checks `if last_state.state in self._attr_options` which will naturally reject "Aus" from old saved states and fall through to the default MODE_TEST. No additional migration code needed.

In tests/test_select.py:
- Update test assertions: options should be [MODE_EIN, MODE_TEST], default should be MODE_TEST.
- Remove or update the assertion `assert MODE_AUS in select_entity._attr_options`.
- Update any test that checks default is MODE_AUS to check MODE_TEST instead.
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && python -m pytest tests/test_select.py -x -v 2>&1 | tail -20</automated>
  </verify>
  <done>OPTIMIZER_MODES is [Ein, Test]. Select entity defaults to Test. All select tests pass.</done>
</task>

<task type="auto">
  <name>Task 2: Add Ein/Test toggle, remove metrics row and mode badge from dashboard</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Three changes in eeg-optimizer-panel.js:

**A) Add Ein/Test toggle switch in the status cards area (above the two status cards).**

Add a toggle row at the top of _renderDashboard(), right before the status cards row (before line 1879). The toggle should be:
- A styled CSS toggle switch (pill-shaped track with sliding circle).
- Labels "Ein" on left, "Test" on right (or vice versa — "Ein" should be the active/green state).
- Toggle reflects current modeValue ("Ein" = toggle on/green, "Test" = toggle off/yellow).
- Wrap in a small row: `<div class="mode-toggle-row">` with the toggle and a label.
- Add a data-action="toggle-mode" attribute on the toggle element.

Add a click handler in the existing event delegation (wherever `data-action` clicks are handled). When `toggle-mode` is clicked:
```javascript
const newMode = modeValue === "Ein" ? "Test" : "Ein";
this._hass.callService("select", "select_option", {
  entity_id: this._entityIds?.select || "select.eeg_energy_optimizer_optimizer",
  option: newMode
});
```

Add CSS for the toggle in the `<style>` section:
```css
.mode-toggle-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-bottom: 12px;
}
.mode-toggle-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--primary-text-color);
}
.mode-toggle {
  position: relative;
  width: 56px;
  height: 28px;
  border-radius: 14px;
  cursor: pointer;
  transition: background 0.2s;
}
.mode-toggle.ein {
  background: var(--success-color, #4caf50);
}
.mode-toggle.test {
  background: var(--warning-color, #ff9800);
}
.mode-toggle .toggle-knob {
  position: absolute;
  top: 3px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: white;
  transition: left 0.2s;
  box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.mode-toggle.ein .toggle-knob { left: 31px; }
.mode-toggle.test .toggle-knob { left: 3px; }
```

The toggle HTML (inside _renderDashboard, before status cards):
```html
<div class="mode-toggle-row">
  <span class="mode-toggle-label">${modeValue === "Ein" ? "Ein" : "Test"}</span>
  <div class="mode-toggle ${modeValue === "Ein" ? "ein" : "test"}" data-action="toggle-mode">
    <div class="toggle-knob"></div>
  </div>
</div>
```

**B) Remove the metrics row.**

Delete the entire metrics row block from _renderDashboard() (lines 1882-1904, the `<div class="metrics-row">...</div>` containing Batterie SOC, PV Heute, PV Morgen cards).

Keep the variables (socVal, pvHeute, pvMorgen, pvWeek, etc.) that are computed above the metrics row because pvWeek and forecastData are still used by the charts below.

Also remove the `.metrics-row` CSS rules (line 2238 and line 2272 narrow override).

**C) Remove the mode badge from the Abend-Entladung card.**

In `_renderStatusCards()`, remove line 1561:
```
<div class="mode-line">Modus: <span class="badge ${modeBadgeClass}">${modeValue}</span></div>
```

Also remove the `.mode-line` CSS rule (line 2270).

The `_renderStatusCards` method signature can drop `modeValue` and `modeBadgeClass` params since they are no longer used there. Update the call site at line 1879 accordingly. The modeBadgeClass variable in _renderDashboard can also be removed (modeValue is still needed for the toggle).
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && grep -c "metrics-row" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js && grep -c "mode-line" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js && grep -c "mode-toggle" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</automated>
  </verify>
  <done>metrics-row grep returns 0, mode-line grep returns 0, mode-toggle grep returns >0. Toggle switch renders in dashboard, metrics row gone, mode badge on discharge card gone.</done>
</task>

</tasks>

<verification>
- `python -m pytest tests/test_select.py -x` passes
- In the JS file: no occurrences of "metrics-row" or "mode-line"
- In the JS file: "mode-toggle" and "toggle-mode" present
- In const.py: OPTIMIZER_MODES contains exactly 2 items (Ein, Test)
- MODE_AUS constant still exists in const.py (backwards compat)
</verification>

<success_criteria>
- Dashboard shows a toggle switch (green=Ein, orange=Test) in place of the old mode badge
- Clicking the toggle switches between Ein and Test via HA service call
- Metrics row (SOC, PV Heute, PV Morgen) no longer appears
- Mode badge removed from Abend-Entladung status card
- Select entity only offers Ein/Test; defaults to Test on fresh install
- Existing users with "Aus" saved state gracefully fall back to Test
</success_criteria>

<output>
After completion, create `.planning/quick/260323-rzw-dashboard-ein-test-toggle-metrics-row-we/260323-rzw-SUMMARY.md`
</output>
