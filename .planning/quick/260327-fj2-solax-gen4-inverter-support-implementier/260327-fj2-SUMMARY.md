---
phase: quick-260327-fj2
plan: 01
subsystem: inverter
tags: [solax, inverter, gen4, modbus, wizard]
dependency_graph:
  requires: [STORY_SOLAX_INVERTER.md]
  provides: [SolaXInverter, solax_gen4-factory-type, SOLAX_DEFAULTS]
  affects: [inverter-factory, websocket-api, wizard-ui, sensor-hausverbrauch]
tech_stack:
  added: [solax_modbus-integration-support]
  patterns: [two-phase-write-model, entity-prefix-autodetect]
key_files:
  created:
    - custom_components/eeg_energy_optimizer/inverter/solax.py
    - tests/test_solax_inverter.py
  modified:
    - custom_components/eeg_energy_optimizer/inverter/__init__.py
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/websocket_api.py
    - custom_components/eeg_energy_optimizer/sensor.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - "Two-phase write model: set params via number/select, then press trigger button"
  - "Entity prefix auto-detected via *_remotecontrol_power_control pattern"
  - "Removed DEFAULT_GRID_POWER_SENSOR and DEFAULT_BATTERY_POWER_SENSOR from const.py (Huawei-specific)"
  - "SolaX battery capacity always manual (no capacity sensor available)"
metrics:
  duration: 8min
  completed: 2026-03-27
  tasks: 3
  files: 8
---

# Quick Task 260327-fj2: SolaX Gen4+ Inverter Support Summary

SolaXInverter class controlling Gen4/5/6 batteries via solax_modbus Mode 1 Remote Control with two-phase write model, kW-to-W conversion, entity prefix auto-detection, and full wizard UI integration.

## Task Results

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | SolaX inverter class + constants + factory + tests | 467dcdf (RED), 03805e7 (GREEN) | Done |
| 2 | WebSocket API extension | 8690df5 | Done |
| 3 | Wizard UI SolaX card + auto-detection + pv_power_sensor_2 | 8cfa618 | Done |

## What Was Built

### SolaXInverter (inverter/solax.py)
- Implements all InverterBase methods: `async_set_charge_limit`, `async_set_discharge`, `async_stop_forcible`, `is_available`
- Two-phase write model: Phase 1 sets params via `number.set_value`/`select.select_option` (DATA_LOCAL), Phase 2 presses trigger button for Modbus write
- kW-to-W conversion: InverterBase uses kW, SolaX registers use Watts
- Entity resolution from config overrides (e.g. `solax_remotecontrol_power_control`) with SOLAX_ENTITY_DEFAULTS fallback
- Error handling: all methods wrapped in try/except, return False on failure

### WebSocket API (websocket_api.py)
- `SOLAX_DEFAULTS` dict for read sensor auto-detection (5 sensor types with fallback candidates)
- `_find_solax_prefix()` detects entity prefix by scanning `select.*_remotecontrol_power_control`
- `detect_sensors` extended: returns SolaX sensors + pre-filled control entity IDs when solax_modbus loaded
- `check_prerequisites` includes `solax_modbus` domain

### Wizard UI (eeg-optimizer-panel.js)
- SolaX Gen4+ card replaces placeholder in inverter selection step
- Prerequisite check for solax_modbus installation status
- Hausverbrauch sensor pickers shown for both Huawei and SolaX with type-specific help text
- Optional `pv_power_sensor_2` field for generator inverter (Meter 2)
- Auto-detection pre-fills SolaX control entities via detected prefix
- Battery capacity defaults to manual mode for SolaX
- Summary step shows dynamic inverter type name + pv_power_sensor_2 if configured

### Constants & Factory
- `INVERTER_TYPE_SOLAX = "solax_gen4"` and `CONF_PV_POWER_SENSOR_2 = "pv_power_sensor_2"` added
- `INVERTER_PREREQUISITES` extended with `"solax_gen4": "solax_modbus"`
- Factory registers `"solax_gen4": SolaXInverter`
- `DEFAULT_GRID_POWER_SENSOR` and `DEFAULT_BATTERY_POWER_SENSOR` removed (were Huawei-specific hardcodes)

### Hausverbrauch Sensor (sensor.py)
- Sums `pv_power_sensor` + `pv_power_sensor_2` when both configured
- Shows `pv_leistung_2_kw` in extra state attributes
- Removed hardcoded Huawei fallback defaults for battery/grid sensors

### Backfill Fix (__init__.py)
- Removed hardcoded Huawei sensor fallbacks in `async_backfill_hausverbrauch_stats`
- Now skips backfill with warning if sensor IDs not configured (instead of using wrong Huawei defaults)

## Tests

20 unit tests in `tests/test_solax_inverter.py`:
- Inheritance from InverterBase
- async_set_charge_limit: block (power=0) and partial charge with kW-to-W conversion
- async_set_discharge: with/without target_soc, min_soc clamped to 10, negative power
- async_stop_forcible: Disabled mode, autorepeat=0
- is_available: loaded/not loaded/no entries
- Entity resolution: config overrides vs SOLAX_ENTITY_DEFAULTS
- kW-to-W conversion: fractional values, small values

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully wired. Hardware-dependent features (lock state, gen4 detection) are documented as open questions in STORY_SOLAX_INVERTER.md for testing on real hardware.
