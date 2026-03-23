---
phase: quick-260323-dyi
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [QUICK-DYI]
must_haves:
  truths:
    - "Wizard Step 1 shows 3 entity pickers for PV, Battery, and Grid sensors when Huawei is selected"
    - "Entity pickers are pre-filled from auto-detection results"
    - "User can manually override any of the 3 sensors"
    - "Zusammenfassung (Step 6) displays all 3 Hausverbrauch sensors"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Wizard UI for Hausverbrauch sensor configuration"
  key_links:
    - from: "_renderStep1()"
      to: "_detectedSensors.sensors"
      via: "entity picker pre-fill"
      pattern: "_entityPickerHtml.*pv_power_sensor"
---

<objective>
Add 3 configurable entity pickers (PV power, battery power, grid power) to the wizard Step 1 (Wechselrichter), shown conditionally when Huawei is selected. Pre-fill from auto-detection, allow manual override. Update summary step to show all 3 sensors.

Purpose: Users currently cannot see or override the Hausverbrauch input sensors. They are silently auto-detected with no visibility or control.
Output: Updated eeg-optimizer-panel.js with sensor fields in Step 1 and Step 6.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add Hausverbrauch sensor pickers to Step 1 and update WIZARD_DEFAULTS + validation + summary</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Three changes in eeg-optimizer-panel.js:

**A) WIZARD_DEFAULTS (line ~52):** Add the two missing keys:
- `grid_power_sensor: ""`
- `battery_power_sensor: ""`
(pv_power_sensor already exists)

**B) _renderStep1() (line ~956):** After the closing `</div>` of the prereq-cards grid (line ~987) and before the "Erneut pruefen" button (line ~988), insert a conditional section that only renders when `huaweiSelected` is true:

```javascript
const sensorSection = huaweiSelected ? `
  <div class="card" style="padding:16px;margin-bottom:16px">
    <h3 style="margin:0 0 4px">Hausverbrauch-Sensoren</h3>
    <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 12px">
      Diese Sensoren werden f&uuml;r die Berechnung des Hausverbrauchs verwendet (PV &minus; Batterie &minus; Netz).
    </p>
    ${this._entityPickerHtml(
      "pv_power_sensor",
      this._wizardData.pv_power_sensor,
      "PV-Eingangsleistung *",
      "Aktuelle PV-Produktion in W oder kW.",
      "sensor"
    )}
    ${this._entityPickerHtml(
      "battery_power_sensor",
      this._wizardData.battery_power_sensor,
      "Batterie Lade-/Entladeleistung *",
      "Lade- und Entladeleistung der Batterie in W oder kW.",
      "sensor"
    )}
    ${this._entityPickerHtml(
      "grid_power_sensor",
      this._wizardData.grid_power_sensor,
      "Netzbezug/-einspeisung *",
      "Wirkleistung am Netzanschluss in W oder kW.",
      "sensor"
    )}
  </div>
` : "";
```

Insert `${sensorSection}` in the return template between the prereq-cards div and the "Erneut pruefen" button.

**C) _renderStep6() (line ~1248):** In the "Batterie & PV" summary section (around line 1266), add two more rows after the existing PV-Sensor row (line 1275):
```javascript
${row("Batterie-Leistung", d.battery_power_sensor || "—")}
${row("Netz-Leistung", d.grid_power_sensor || "—")}
```

**D) _isNextDisabled() (line ~913):** Update the Step 1 validation (currently only checks huawei_solar prerequisite). Add after the existing check for step === 1: also block "Weiter" if Huawei is selected but any of the 3 sensor fields are empty:
```javascript
if (step === 1) {
  if (this._prerequisites && !this._prerequisites.huawei_solar) return true;
  const d = this._wizardData;
  if (d.inverter_type === "huawei_sun2000" &&
      (!d.pv_power_sensor || !d.battery_power_sensor || !d.grid_power_sensor)) {
    return true;
  }
}
```
This replaces the existing simple `step === 1` check.

After editing, copy the file:
```bash
cp custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
```
  </action>
  <verify>
    <automated>grep -c "battery_power_sensor\|grid_power_sensor\|pv_power_sensor" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep -v "^0$"</automated>
    Verify: WIZARD_DEFAULTS has all 3 keys, _renderStep1 has entity pickers, _renderStep6 shows all 3 sensors, _isNextDisabled validates all 3 fields.
  </verify>
  <done>
    - WIZARD_DEFAULTS includes grid_power_sensor and battery_power_sensor (empty string defaults)
    - Step 1 shows 3 entity pickers in a "Hausverbrauch-Sensoren" card when Huawei is selected
    - Entity pickers pre-fill from auto-detection (already handled by _detectSensors loop)
    - Step 1 "Weiter" button is disabled until all 3 sensors are filled (when Huawei selected)
    - Step 6 summary shows all 3 Hausverbrauch sensors
    - File copied to /tmp/EEGEnergyOptimizer/
  </done>
</task>

</tasks>

<verification>
1. Open wizard, select Huawei -- 3 sensor pickers appear below inverter cards
2. If auto-detection ran, sensors are pre-filled
3. Clear one sensor field -- "Weiter" button becomes disabled
4. Fill all 3 -- can proceed to Step 2
5. Reach Zusammenfassung -- all 3 sensors shown in "Batterie & PV" section
</verification>

<success_criteria>
- All 3 Hausverbrauch sensors visible and editable in wizard Step 1
- Auto-detection pre-fill still works (no regression)
- Validation prevents proceeding without all 3 sensors
- Summary step shows all 3 sensors
</success_criteria>

<output>
After completion, create `.planning/quick/260323-dyi-hausverbrauch-sensoren-pv-batterie-netz-/260323-dyi-SUMMARY.md`
</output>
