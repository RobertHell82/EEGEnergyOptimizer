---
phase: quick
plan: 260323-muk
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [quick-260323-muk]
must_haves:
  truths:
    - "Dashboard no longer shows the Wechselrichter-Verbindung testen card"
    - "Manual control card still works"
    - "Wizard inverter test still works"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Dashboard without redundant inverter test card"
  key_links: []
---

<objective>
Remove the redundant "Wechselrichter-Verbindung testen" card from the dashboard view.

Purpose: The inverter connection test is already available in the wizard setup flow. Having it on the dashboard is redundant clutter.
Output: Cleaner dashboard without the test card.
</objective>

<execution_context>
@.claude/get-shit-done/workflows/execute-plan.md
@.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove inverter test card from dashboard</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Remove the following from `eeg-optimizer-panel.js`:

1. **Dashboard inverter test card** (lines ~2030-2048): Remove the entire `<!-- Inverter Test Card -->` block starting with `<div class="card">` containing "Wechselrichter-Verbindung" heading, through its closing `</div>`.

2. **Dashboard test status variables** (lines ~1896-1912): Remove the `// --- Inverter test (keep existing) ---` block that builds `testStatusHtml` from `this._inverterTestResult` and `this._inverterTesting`. Also remove the `testStatusHtml` variable usage.

3. **State variable initialization** (lines 156-157): Remove `this._inverterTestResult = null;` and `this._inverterTesting = false;` from the constructor.

4. **The `_testInverter()` method** (lines ~594-611): Remove the entire async method.

5. **Click handler case** (line ~258-260): Remove the `case "test-inverter": this._testInverter(); break;` from the click event handler switch statement.

DO NOT remove:
- The `.inverter-test-result` CSS styles (lines ~2258-2268) -- these are still used by the Manual Control card's status display (lines ~1886, 1890).
- The `eeg_optimizer/test_inverter` WebSocket command registration in `websocket_api.py` -- the wizard still uses it.
- Any manual control (`_manualCommand`, `_manualResult`) code.
  </action>
  <verify>
    <automated>grep -c "Wechselrichter-Verbindung" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep "^0$" && grep -c "_testInverter" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep "^0$" && grep -c "_inverterTestResult" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep "^0$" && grep -c "inverter-test-result" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep -v "^0$" && echo "PASS"</automated>
  </verify>
  <done>Dashboard no longer contains the inverter test card. The _testInverter method, _inverterTestResult/_inverterTesting state, and related click handler are gone. The .inverter-test-result CSS class remains (used by manual control). Manual control card is untouched.</done>
</task>

</tasks>

<verification>
- No references to `_testInverter`, `_inverterTestResult`, `_inverterTesting` remain
- No "Wechselrichter-Verbindung" text remains in dashboard
- `.inverter-test-result` CSS class still exists (needed by manual control)
- `_manualCommand` and manual control code untouched
- Panel JS has no syntax errors (valid JS structure)
</verification>

<success_criteria>
The dashboard loads without the inverter test card. Manual control card still renders correctly.
</success_criteria>

<output>
After completion, create `.planning/quick/260323-muk-dashboard-wechselrichter-verbindungstest/260323-muk-SUMMARY.md`
</output>
