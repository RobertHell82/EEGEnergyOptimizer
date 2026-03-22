---
phase: quick
plan: 260322-v8z
subsystem: sensor
tags: [hausverbrauch, battery-power, formula-fix, migration]

provides:
  - "3-term HausverbrauchSensor formula matching proven template sensor"
  - "battery_power_sensor config constant and migration v7"
  - "Auto-detection default for Huawei battery power sensor"
affects: [sensor, config-flow, migration]

key-files:
  modified:
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/sensor.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/websocket_api.py

key-decisions:
  - "battery_power_sensor default set to sensor.batteries_lade_entladeleistung (Huawei entity)"

requirements-completed: []

duration: 1min
completed: 2026-03-22
---

# Quick Task 260322-v8z: Fix Hausverbrauch Formel Summary

**Corrected HausverbrauchSensor to 3-term formula (PV - battery - grid) with migration v7 and auto-detection**

## Performance

- **Duration:** 1 min
- **Started:** 2026-03-22T21:11:49Z
- **Completed:** 2026-03-22T21:13:13Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Fixed HausverbrauchSensor formula from `pv - grid` to `max(pv - battery - grid, 0)` matching user's proven template sensor
- Added CONF_BATTERY_POWER_SENSOR and DEFAULT_BATTERY_POWER_SENSOR constants
- Migration v7 ensures existing installations get the battery_power_sensor default automatically
- HUAWEI_DEFAULTS updated for auto-detection of new Huawei setups

## Task Commits

Each task was committed atomically:

1. **Task 1: Add battery_power_sensor constant, migration, and auto-detection** - `c032999` (feat)
2. **Task 2: Fix HausverbrauchSensor formula to 3-term calculation** - `686e918` (fix)

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/const.py` - Added CONF_BATTERY_POWER_SENSOR + DEFAULT_BATTERY_POWER_SENSOR
- `custom_components/eeg_energy_optimizer/__init__.py` - Migration v7 adding battery_power_sensor default
- `custom_components/eeg_energy_optimizer/config_flow.py` - VERSION bumped to 7
- `custom_components/eeg_energy_optimizer/websocket_api.py` - HUAWEI_DEFAULTS includes battery_power_sensor
- `custom_components/eeg_energy_optimizer/sensor.py` - 3-term formula in HausverbrauchSensor

## Decisions Made
- battery_power_sensor default set to sensor.batteries_lade_entladeleistung (Huawei entity matching user's working HA template sensor)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## Known Stubs
None

---
*Quick task: 260322-v8z*
*Completed: 2026-03-22*
