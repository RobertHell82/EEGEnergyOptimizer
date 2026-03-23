---
phase: quick-260323-czf
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/sensor.py
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
  - custom_components/eeg_energy_optimizer/translations/en.json
autonomous: true
requirements: []
must_haves:
  truths:
    - "consumption_sensor is no longer configurable anywhere in the integration"
    - "The integration hardcodes sensor.eeg_energy_optimizer_hausverbrauch as the consumption sensor"
    - "The wizard has 7 steps instead of 8 (Verbrauch step removed)"
    - "Existing config entries with consumption_sensor key are cleaned up by migration v9"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/const.py"
      provides: "CONSUMPTION_SENSOR hardcoded constant (not CONF_ prefixed)"
      contains: "CONSUMPTION_SENSOR = "
    - path: "custom_components/eeg_energy_optimizer/__init__.py"
      provides: "Migration v9 that strips consumption_sensor from config data"
      contains: "entry.version < 9"
    - path: "custom_components/eeg_energy_optimizer/config_flow.py"
      provides: "VERSION = 9"
      contains: "VERSION = 9"
  key_links:
    - from: "custom_components/eeg_energy_optimizer/sensor.py"
      to: "custom_components/eeg_energy_optimizer/const.py"
      via: "imports CONSUMPTION_SENSOR constant"
      pattern: "from \\.const import.*CONSUMPTION_SENSOR"
---

<objective>
Remove the configurable consumption_sensor from the integration and hardcode it to our own calculated Hausverbrauch sensor (sensor.eeg_energy_optimizer_hausverbrauch).

Purpose: The consumption sensor config is redundant since PV, Battery, and Grid sensors (the inputs to the Hausverbrauch calculation) are already configurable. Simplifies the wizard and eliminates a potential misconfiguration source.

Output: All references to CONF_CONSUMPTION_SENSOR and DEFAULT_CONSUMPTION_SENSOR removed, replaced by a single hardcoded CONSUMPTION_SENSOR constant. Wizard reduced from 8 to 7 steps. Migration v9 cleans up stored config.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@custom_components/eeg_energy_optimizer/const.py
@custom_components/eeg_energy_optimizer/sensor.py
@custom_components/eeg_energy_optimizer/__init__.py
@custom_components/eeg_energy_optimizer/config_flow.py
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
@custom_components/eeg_energy_optimizer/translations/en.json
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove consumption_sensor config from Python backend + migration v9</name>
  <files>
    custom_components/eeg_energy_optimizer/const.py,
    custom_components/eeg_energy_optimizer/sensor.py,
    custom_components/eeg_energy_optimizer/__init__.py,
    custom_components/eeg_energy_optimizer/config_flow.py,
    custom_components/eeg_energy_optimizer/translations/en.json
  </files>
  <action>
    **const.py:**
    - Remove `CONF_CONSUMPTION_SENSOR = "consumption_sensor"` (line 24)
    - Remove `DEFAULT_CONSUMPTION_SENSOR = "sensor.eeg_energy_optimizer_hausverbrauch"` (line 32)
    - Add a new hardcoded constant (NOT a CONF_ key): `CONSUMPTION_SENSOR = "sensor.eeg_energy_optimizer_hausverbrauch"`
    - Place it in the Phase 2 section, after the CONF_ keys

    **sensor.py:**
    - Remove imports of `CONF_CONSUMPTION_SENSOR` and `DEFAULT_CONSUMPTION_SENSOR` from const
    - Add import of `CONSUMPTION_SENSOR` from const
    - In `async_setup_entry()` (around line 576): replace `consumption_sensor = config.get(CONF_CONSUMPTION_SENSOR, DEFAULT_CONSUMPTION_SENSOR)` with just using the `CONSUMPTION_SENSOR` constant directly:
      ```python
      coordinator = ConsumptionCoordinator(hass, CONSUMPTION_SENSOR, lookback_weeks)
      ```
    - Remove the `consumption_sensor` local variable entirely

    **__init__.py:**
    - Add migration v9 block after the v8 block:
      ```python
      if entry.version < 9:
          new_data = {**entry.data}
          new_data.pop("consumption_sensor", None)
          hass.config_entries.async_update_entry(entry, data=new_data, version=9)
      ```

    **config_flow.py:**
    - Change `VERSION = 8` to `VERSION = 9`

    **translations/en.json:**
    - Remove `"consumption_sensor"` entries from data and data_description in the consumption step
    - Update the consumption step description to remove mention of configuring a consumption sensor (it now just covers lookback/intervals)
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && grep -c "CONF_CONSUMPTION_SENSOR" custom_components/eeg_energy_optimizer/const.py custom_components/eeg_energy_optimizer/sensor.py && echo "FAIL: CONF_CONSUMPTION_SENSOR still present" || echo "PASS: CONF removed" && grep -c "CONSUMPTION_SENSOR = " custom_components/eeg_energy_optimizer/const.py | grep -q "1" && echo "PASS: hardcoded constant exists" && grep -q "VERSION = 9" custom_components/eeg_energy_optimizer/config_flow.py && echo "PASS: VERSION=9" && grep -q "entry.version < 9" custom_components/eeg_energy_optimizer/__init__.py && echo "PASS: migration v9 exists"</automated>
  </verify>
  <done>
    - CONF_CONSUMPTION_SENSOR and DEFAULT_CONSUMPTION_SENSOR no longer exist in const.py
    - CONSUMPTION_SENSOR hardcoded constant exists in const.py
    - sensor.py uses CONSUMPTION_SENSOR directly (no config.get)
    - Migration v9 strips consumption_sensor from stored config
    - config_flow VERSION is 9
  </done>
</task>

<task type="auto">
  <name>Task 2: Remove Verbrauch wizard step from frontend panel</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
    **WIZARD_STEPS array (line 42-51):**
    - Remove `"Verbrauch"` entry (line 47). New array:
      ```js
      const WIZARD_STEPS = [
        "Willkommen",        // 0
        "Wechselrichter",    // 1
        "Prognose",          // 2
        "Batterie",          // 3
        "Ladung & Einspeisung",  // 4 (was 5)
        "Erweiterte Einstellungen", // 5 (was 6)
        "Zusammenfassung",   // 6 (was 7)
      ];
      ```

    **WIZARD_DEFAULTS (line 53+):**
    - Remove `consumption_sensor: "sensor.eeg_energy_optimizer_hausverbrauch"` (line 63)

    **_validateCurrentStep() (around line 443):**
    - Remove `case 4: // Verbrauch` block entirely (lines 443-448)
    - No renumbering needed — the switch cases now naturally align with the new step indices

    **_goToStep() (around line 363):**
    - Change `if (step === 3 || step === 4)` to just `if (step === 3)` since step 4 no longer needs entity picker (it's now Ladung & Einspeisung)

    **Render switch statement (around line 864-889):**
    - Remove `case 4: stepContent = this._renderStep4(); break;`
    - Renumber: case 4 -> _renderStep5(), case 5 -> _renderStep6(), case 6 -> _renderStep7()
    - The switch should now go 0-6 (7 steps total)

    **Delete _renderStep4() method entirely** (lines 1146-1154)

    **Renumber render methods:**
    - `_renderStep5()` -> `_renderStep4()` (Ladung & Einspeisung)
    - `_renderStep6()` -> `_renderStep5()` (Erweiterte Einstellungen)
    - `_renderStep7()` -> `_renderStep6()` (Zusammenfassung)

    **Summary section (around line 1307-1310):**
    - Remove the "Verbrauch" summary section that shows `d.consumption_sensor`

    **_saveConfig or finish-wizard handler:**
    - If consumption_sensor is included in the data sent to the backend, remove it. Search for where `consumption_sensor` is included in the save payload and remove that line.

    IMPORTANT: After renumbering, verify all internal references to step numbers are consistent. The _renderStepN methods and the switch statement must match.
  </action>
  <verify>
    <automated>cd /c/Data/source/HA_EEG_Energy_Optimizier && grep -c "consumption_sensor" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep -q "^0$" && echo "PASS: no consumption_sensor refs in panel" || echo "FAIL: consumption_sensor still in panel" && grep -c "Verbrauch\"," custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep -q "^0$" && echo "PASS: Verbrauch step removed from WIZARD_STEPS" || echo "FAIL: Verbrauch step still in WIZARD_STEPS" && grep -c "_renderStep7" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | grep -q "^0$" && echo "PASS: no _renderStep7 (7 steps = 0-6)" || echo "FAIL: _renderStep7 still exists"</automated>
  </verify>
  <done>
    - WIZARD_STEPS has 7 entries (Verbrauch removed)
    - No references to consumption_sensor in the panel JS
    - Render methods numbered _renderStep0 through _renderStep6
    - Switch statement cases 0-6 match render methods
    - Summary section no longer shows consumption sensor
  </done>
</task>

<task type="auto">
  <name>Task 3: Copy changed files to /tmp/EEGEnergyOptimizer</name>
  <files>/tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/</files>
  <action>
    Copy all modified files to the deployment directory:
    ```bash
    cp custom_components/eeg_energy_optimizer/const.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
    cp custom_components/eeg_energy_optimizer/sensor.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
    cp custom_components/eeg_energy_optimizer/__init__.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
    cp custom_components/eeg_energy_optimizer/config_flow.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
    cp custom_components/eeg_energy_optimizer/translations/en.json /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/translations/
    cp custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/frontend/
    ```
  </action>
  <verify>
    <automated>ls -la /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/const.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/__init__.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/sensor.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/config_flow.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/translations/en.json</automated>
  </verify>
  <done>All 6 modified files copied to /tmp/EEGEnergyOptimizer deployment directory</done>
</task>

</tasks>

<verification>
1. `grep -r "CONF_CONSUMPTION_SENSOR\|DEFAULT_CONSUMPTION_SENSOR" custom_components/eeg_energy_optimizer/` returns no matches
2. `grep "CONSUMPTION_SENSOR = " custom_components/eeg_energy_optimizer/const.py` shows hardcoded constant
3. `grep "VERSION = 9" custom_components/eeg_energy_optimizer/config_flow.py` confirms version bump
4. `grep "consumption_sensor" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` returns no matches
5. `grep -c "WIZARD_STEPS" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` and verify 7 entries
</verification>

<success_criteria>
- consumption_sensor is completely removed as a configurable option
- The hardcoded CONSUMPTION_SENSOR constant points to sensor.eeg_energy_optimizer_hausverbrauch
- Wizard has 7 steps (was 8), no Verbrauch step
- Migration v9 cleans up existing config entries
- All files deployed to /tmp/EEGEnergyOptimizer
</success_criteria>

<output>
After completion, create `.planning/quick/260323-czf-consumption-sensor-config-entfernen-fest/260323-czf-SUMMARY.md`
</output>
