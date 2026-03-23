---
phase: quick-260323-cs1
plan: 01
subsystem: consumption-sensor-default
tags: [config, migration, sensor, default]
dependency_graph:
  requires: [260322-v34, 260322-v8z]
  provides: [accurate-consumption-forecasts]
  affects: [coordinator, forecast-sensors, optimizer]
tech_stack:
  patterns: [config-migration-v8, conditional-migration]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
    - tests/test_config_flow.py
    - CLAUDE.md
decisions:
  - "Migration v8 only updates consumption_sensor if it matches the old default (sensor.power_meter_verbrauch), preserving custom user configurations"
metrics:
  duration: 2min
  completed: "2026-03-23T08:16:16Z"
---

# Quick Task 260323-cs1: Verbrauchsprognose auf eigenen Hausverbrauch-Sensor umstellen

**One-liner:** Default consumption sensor switched from grid-import-only Huawei sensor to calculated Hausverbrauch sensor (PV - Battery - Grid) for accurate consumption forecasts.

## What Changed

The default consumption sensor (`DEFAULT_CONSUMPTION_SENSOR`) was changed from `sensor.power_meter_verbrauch` (Huawei power meter, grid import only) to `sensor.eeg_energy_optimizer_hausverbrauch` (integration's own calculated sensor). The old sensor missed self-consumption from PV and battery, making consumption forecasts undercount actual household usage.

## Tasks Completed

### Task 1: Update default constant, config migration, and panel default
**Commit:** `450c302`

- **const.py**: `DEFAULT_CONSUMPTION_SENSOR` changed to `sensor.eeg_energy_optimizer_hausverbrauch`
- **__init__.py**: Added migration v8 that conditionally updates `consumption_sensor` only if it was set to the old default
- **config_flow.py**: `VERSION` bumped from 7 to 8
- **frontend/eeg-optimizer-panel.js**: Panel wizard default updated

### Task 2: Update tests to use new default sensor
**Commit:** `ab21899`

- **tests/test_config_flow.py**: All 3 references to `sensor.power_meter_verbrauch` in consumption_sensor fields updated to new default
- Tests cannot run in dev environment (no HA package), but changes are syntactically correct and match the pattern

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Updated CLAUDE.md version reference**
- **Found during:** Post-task verification
- **Issue:** CLAUDE.md still referenced "Config entry version: 7"
- **Fix:** Updated to "Config entry version: 8"
- **Files modified:** CLAUDE.md (both repos)

## Verification

- `grep -rn "power_meter_verbrauch"` in source: only migration v8 check (correct -- detects old value to migrate)
- `grep -rn "eeg_energy_optimizer_hausverbrauch"` in const.py, __init__.py, panel JS: all confirmed
- `VERSION = 8` confirmed in config_flow.py
- Files copied to /tmp/EEGEnergyOptimizer/ for new repo

## Known Stubs

None -- all changes are complete and wired.
