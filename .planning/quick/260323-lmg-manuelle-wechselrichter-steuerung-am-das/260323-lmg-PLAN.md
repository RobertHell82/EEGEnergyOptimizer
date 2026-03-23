---
phase: quick-260323-lmg
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/websocket_api.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [MANUAL-INVERTER-CONTROL]

must_haves:
  truths:
    - "User can click Normalbetrieb and inverter returns to automatic mode"
    - "User can enter kW/SOC and click Entladung starten to discharge battery"
    - "User can click Ladung blockieren to block battery charging"
    - "Manual controls are disabled when setup_complete is false"
    - "Each button shows loading state and success/error feedback"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/websocket_api.py"
      provides: "3 new WS commands: manual_discharge, manual_block_charge, manual_stop"
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Manuelle Steuerung card with 3 action buttons + inputs"
  key_links:
    - from: "eeg-optimizer-panel.js"
      to: "websocket_api.py"
      via: "hass.callWS eeg_optimizer/manual_*"
    - from: "websocket_api.py"
      to: "inverter/base.py"
      via: "inverter.async_set_discharge / async_set_charge_limit / async_stop_forcible"
---

<objective>
Add manual inverter control buttons to the dashboard panel so the user can test 3 optimizer modes manually: Normal (stop forcible), Discharge (configurable kW + target SOC), and Block Charging.

Purpose: Allow direct inverter control from the dashboard for testing and manual override.
Output: 3 new WebSocket commands + dashboard UI card with action buttons.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@custom_components/eeg_energy_optimizer/websocket_api.py
@custom_components/eeg_energy_optimizer/inverter/base.py
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
</context>

<interfaces>
<!-- Inverter API (inverter/base.py) - the 3 methods to call: -->
```python
async def async_set_charge_limit(self, power_kw: float) -> bool
async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool
async def async_stop_forcible(self) -> bool
@property
def is_available(self) -> bool
```

<!-- Existing WS pattern (websocket_api.py) - inverter access: -->
```python
entry = entries[0]
data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
inverter = data.get("inverter")
# Check: inverter is None, inverter.is_available
```

<!-- Panel event pattern (eeg-optimizer-panel.js): -->
```javascript
// State vars: this._inverterTestResult, this._inverterTesting
// Click handler: _handleAction(action, dataset) with switch/case
// WS call: await this._hass.callWS({ type: "eeg_optimizer/..." })
// Config access: this._config?.setup_complete, this._config?.discharge_power_kw
```
</interfaces>

<tasks>

<task type="auto">
  <name>Task 1: Add 3 manual inverter WebSocket commands</name>
  <files>custom_components/eeg_energy_optimizer/websocket_api.py</files>
  <action>
Add 3 new WebSocket command handlers to websocket_api.py, following the exact pattern of ws_test_inverter:

1. **ws_manual_stop** — command type `eeg_optimizer/manual_stop`, no extra params.
   - Get inverter from hass.data (same pattern as ws_test_inverter).
   - Check inverter is not None and is_available (same error messages).
   - Call `await inverter.async_stop_forcible()`.
   - Return `{success: true, message: "Normalbetrieb aktiviert."}` or `{success: false, error: "..."}`.

2. **ws_manual_discharge** — command type `eeg_optimizer/manual_discharge`.
   - Schema: `vol.Required("power_kw"): vol.Coerce(float)`, `vol.Optional("target_soc", default=10): vol.Coerce(float)`.
   - Get inverter, check availability (same pattern).
   - Call `await inverter.async_set_discharge(msg["power_kw"], msg["target_soc"])`.
   - Return `{success: true, message: "Entladung gestartet: X kW, Ziel-SOC: Y%."}` or error.

3. **ws_manual_block_charge** — command type `eeg_optimizer/manual_block_charge`, no extra params.
   - Get inverter, check availability (same pattern).
   - Call `await inverter.async_set_charge_limit(0)`.
   - Return `{success: true, message: "Batterieladung blockiert."}` or error.

All 3 handlers: wrap the inverter call in try/except Exception like ws_test_inverter does. Log with _LOGGER.exception on failure.

Register all 3 in `async_register_websocket_commands` alongside existing commands.

Extract a helper function `_get_inverter(hass, connection, msg)` that returns the inverter or sends the error and returns None, to avoid duplicating the 15-line inverter-lookup/availability-check block 4 times (refactor ws_test_inverter to use it too).
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('custom_components/eeg_energy_optimizer/websocket_api.py').read()); print('OK')"</automated>
  </verify>
  <done>3 new WS commands registered, all follow existing pattern, helper function eliminates duplication</done>
</task>

<task type="auto">
  <name>Task 2: Add Manuelle Steuerung card to dashboard panel</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Add a "Manuelle Steuerung" card to the dashboard in eeg-optimizer-panel.js. Place it between the chart cards and the existing "Wechselrichter-Verbindung" card (before line ~1771 in _renderDashboard).

**New state variables** (add in constructor alongside _inverterTestResult):
- `this._manualAction = null` — currently executing action name or null
- `this._manualResult = null` — {success, message/error} or null
- `this._manualDischargeKw = null` — will default from config on render
- `this._manualDischargeSoc = 10`

**New _handleAction cases** (add in switch block):
- `case "manual-stop":` — call `this._executeManualAction("manual-stop", { type: "eeg_optimizer/manual_stop" })`
- `case "manual-discharge":` — call with `{ type: "eeg_optimizer/manual_discharge", power_kw: this._manualDischargeKw || this._config?.discharge_power_kw || 3.0, target_soc: this._manualDischargeSoc }`
- `case "manual-block-charge":` — call `this._executeManualAction("manual-block-charge", { type: "eeg_optimizer/manual_block_charge" })`

**New helper method** `async _executeManualAction(actionName, wsPayload)`:
- Set `this._manualAction = actionName; this._manualResult = null; this._render()`
- try: `const result = await this._hass.callWS(wsPayload); this._manualResult = result;`
- catch: `this._manualResult = { success: false, error: "Kommunikationsfehler: " + (err.message || err) };`
- finally: `this._manualAction = null; this._render();`

**New input event handling**: Add in the existing `input` event listener (around line 184) a check: if `data-field` is `manual_discharge_kw`, set `this._manualDischargeKw = parseFloat(target.value) || 3.0`. If `manual_discharge_soc`, set `this._manualDischargeSoc = parseFloat(target.value) || 10`.

**Dashboard HTML** — new card inserted before the Wechselrichter-Verbindung card:
```
<div class="card">
  <h3 style="margin-top:0">Manuelle Steuerung</h3>
  <p style="color:var(--secondary-text-color);font-size:14px">
    Wechselrichter direkt steuern. Achtung: Der Optimizer überschreibt manuelle Befehle im nächsten Zyklus.
  </p>
  ${!this._config?.setup_complete ? disabled-hint : `
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px">
      <!-- 3 action buttons as styled divs/buttons -->
      <button class="btn-manual btn-manual-normal" data-action="manual-stop"
        ${this._manualAction ? "disabled" : ""}>
        <ha-icon icon="mdi:flash-auto"></ha-icon>
        <span>Normalbetrieb</span>
      </button>
      <button class="btn-manual btn-manual-discharge" data-action="manual-discharge"
        ${this._manualAction ? "disabled" : ""}>
        <ha-icon icon="mdi:battery-arrow-down"></ha-icon>
        <span>Entladung starten</span>
      </button>
      <button class="btn-manual btn-manual-block" data-action="manual-block-charge"
        ${this._manualAction ? "disabled" : ""}>
        <ha-icon icon="mdi:battery-off"></ha-icon>
        <span>Ladung blockieren</span>
      </button>
    </div>
    <!-- Discharge parameters row -->
    <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:12px">
      <label style="font-size:14px">
        Leistung:
        <input type="number" data-field="manual_discharge_kw" min="0.5" max="12" step="0.5"
          value="${this._manualDischargeKw || this._config?.discharge_power_kw || 3.0}"
          style="width:70px;...input-styles"> kW
      </label>
      <label style="font-size:14px">
        Ziel-SOC:
        <input type="number" data-field="manual_discharge_soc" min="5" max="100" step="5"
          value="${this._manualDischargeSoc}"
          style="width:70px;...input-styles"> %
      </label>
    </div>
    <!-- Status line -->
    ${manualStatusHtml}
  `}
</div>
```

**Status HTML** (same pattern as inverter test):
- If `this._manualAction`: show "Befehl wird ausgeführt..." with the action name
- If `this._manualResult?.success`: green success div with check icon + message
- If `this._manualResult` and not success: red error div with alert icon + error

**CSS** — add styles inside the existing `<style>` block:
```css
.btn-manual {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 16px 20px; border-radius: 12px; border: 1px solid var(--divider-color);
  background: var(--card-background-color); cursor: pointer;
  font-size: 14px; font-weight: 500; color: var(--primary-text-color);
  min-width: 120px; transition: all 0.2s;
}
.btn-manual:hover:not([disabled]) { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.btn-manual[disabled] { opacity: 0.5; cursor: not-allowed; }
.btn-manual ha-icon { --mdc-icon-size: 28px; }
.btn-manual-normal { border-color: #4caf50; }
.btn-manual-normal:hover:not([disabled]) { background: rgba(76,175,80,0.1); }
.btn-manual-discharge { border-color: #ff9800; }
.btn-manual-discharge:hover:not([disabled]) { background: rgba(255,152,0,0.1); }
.btn-manual-block { border-color: #2196f3; }
.btn-manual-block:hover:not([disabled]) { background: rgba(33,150,243,0.1); }
```

**Input styling** for the kW/SOC fields: match existing wizard input styles (border-radius:8px, border:1px solid var(--divider-color), padding:8px, background:var(--card-background-color), color:var(--primary-text-color)).

**When setup not complete**: Show the same disabled hint pattern as the inverter test card: disabled button text + info message about completing wizard first.
  </action>
  <verify>
    <automated>node -e "const fs=require('fs'); const src=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); const checks=['manual-stop','manual-discharge','manual-block-charge','_manualAction','_executeManualAction','btn-manual']; const missing=checks.filter(c=>!src.includes(c)); if(missing.length){console.error('Missing:',missing);process.exit(1)}else{console.log('All patterns found')}"</automated>
  </verify>
  <done>Dashboard shows Manuelle Steuerung card with 3 styled action buttons, kW/SOC inputs for discharge, loading/success/error feedback, disabled state when setup incomplete</done>
</task>

</tasks>

<verification>
1. Python syntax valid: `python -c "import ast; ast.parse(open('custom_components/eeg_energy_optimizer/websocket_api.py').read())"`
2. JS contains all required patterns (manual-stop, manual-discharge, manual-block-charge, _executeManualAction, btn-manual)
3. WS registration: grep for all 3 new `ws_manual_` in async_register_websocket_commands
4. Copy files to /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
</verification>

<success_criteria>
- websocket_api.py has 3 new WS commands (manual_stop, manual_discharge, manual_block_charge) with proper inverter checks
- Dashboard panel shows "Manuelle Steuerung" card with 3 action buttons
- Discharge button uses configurable kW (defaulting from config) and SOC inputs
- All buttons disabled when setup_complete is false or action in progress
- Success/error feedback displayed after each action
- Files copied to /tmp/EEGEnergyOptimizer/
</success_criteria>

<output>
After completion, create `.planning/quick/260323-lmg-manuelle-wechselrichter-steuerung-am-das/260323-lmg-SUMMARY.md`
</output>
