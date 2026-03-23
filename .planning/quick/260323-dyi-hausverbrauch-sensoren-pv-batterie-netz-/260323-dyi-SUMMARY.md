---
phase: quick-260323-dyi
plan: 01
subsystem: frontend-wizard
tags: [wizard, entity-picker, hausverbrauch, sensors]
dependency_graph:
  requires: [websocket_api detect_sensors, HUAWEI_DEFAULTS]
  provides: [wizard UI for PV/battery/grid sensor config]
  affects: [eeg-optimizer-panel.js]
tech_stack:
  patterns: [conditional wizard sections, entity picker pre-fill]
key_files:
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - "Entity pickers shown conditionally only when Huawei inverter selected"
  - "All 3 sensors required before Step 1 can proceed (validation gate)"
metrics:
  duration: "1min"
  completed: "2026-03-23T09:07:27Z"
---

# Quick Task 260323-dyi: Hausverbrauch-Sensoren im Wizard Summary

3 entity pickers (PV, Batterie, Netz) in Wizard Step 1 for Hausverbrauch sensor configuration with auto-detection pre-fill and Step 6 summary display.

## Changes Made

### Task 1: Add Hausverbrauch sensor pickers to Step 1 + validation + summary

**Commit:** `6493551`

Four changes in `eeg-optimizer-panel.js`:

1. **WIZARD_DEFAULTS** -- Added `battery_power_sensor: ""` and `grid_power_sensor: ""` (pv_power_sensor already existed)

2. **_renderStep1()** -- Added conditional "Hausverbrauch-Sensoren" card shown when Huawei is selected, containing 3 entity pickers:
   - PV-Eingangsleistung (pv_power_sensor)
   - Batterie Lade-/Entladeleistung (battery_power_sensor)
   - Netzbezug/-einspeisung (grid_power_sensor)

3. **_isNextDisabled()** -- Extended Step 1 validation to block "Weiter" when Huawei is selected but any of the 3 sensor fields are empty

4. **_renderStep6()** -- Added "Batterie-Leistung" and "Netz-Leistung" rows to the Batterie & PV summary section

### Auto-detection pre-fill

No backend changes needed. The existing `_detectSensors()` method already copies all keys from the WebSocket `detect_sensors` response to `_wizardData`, and `HUAWEI_DEFAULTS` in `websocket_api.py` already maps all 3 sensor keys.

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Verification

- [x] grep confirms 13 occurrences of sensor keys across WIZARD_DEFAULTS, Step 1, validation, and Step 6
- [x] File copied to /tmp/EEGEnergyOptimizer/ and pushed to GitHub

## Self-Check: PASSED
