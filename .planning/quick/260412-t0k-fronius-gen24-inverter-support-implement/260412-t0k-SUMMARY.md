---
phase: 260412-t0k
plan: 01
subsystem: inverter
tags: [fronius, gen24, modbus, sunspec, pymodbus]
dependency_graph:
  requires: [inverter-base-abc]
  provides: [fronius-gen24-inverter-support]
  affects: [factory, constants, config-flow, websocket-api, panel-wizard]
tech_stack:
  added: [pymodbus>=3.6.0]
  patterns: [sunspec-model-discovery, modbus-tcp-direct, percentage-based-control]
key_files:
  created:
    - custom_components/eeg_energy_optimizer/inverter/fronius.py
  modified:
    - custom_components/eeg_energy_optimizer/inverter/__init__.py
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/manifest.json
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/websocket_api.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
    - custom_components/eeg_energy_optimizer/config_flow.py
decisions:
  - "Direct Modbus TCP via pymodbus for battery control (native Fronius Integration is read-only)"
  - "SunSpec Model Discovery at runtime (register addresses vary by firmware/config)"
  - "WChaMax cached daily (max battery power rarely changes)"
  - "StorCtl_Mod=3 for discharge with TODO for real-device validation (KONZEPT 8.1)"
  - "Config entry VERSION bumped to 11 (migration is no-op, Fronius fields only set in wizard)"
metrics:
  duration: 9m 17s
  completed: "2026-04-12T19:20:00Z"
  tasks: 3/3
  files_created: 1
  files_modified: 7
---

# Quick Task 260412-t0k: Fronius Gen24 Inverter Support Summary

Fronius Gen24 inverter driver using pymodbus for direct SunSpec Model 124 Modbus TCP control, with full panel UI wizard and sensor auto-detection via native Fronius integration.

## Task Results

### Task 1: FroniusInverter driver + factory + constants + manifest
**Commit:** 919e287

- Created `inverter/fronius.py` (300+ lines) implementing `InverterBase` with:
  - SunSpec Model Discovery scanning from register 40000 to find Model 124
  - WChaMax read once per day and cached for percentage calculations
  - `async_set_charge_limit`: StorCtl_Mod=1, InWRte=0 (block) or percentage
  - `async_set_discharge`: StorCtl_Mod=3, OutWRte=percent, InWRte=0, optional MinRsvPct
  - `async_stop_forcible`: StorCtl_Mod=0, InWRte=10000, OutWRte=10000
  - Connection retry logic (3 attempts, 200ms delay)
  - 200ms pause between register writes
  - Lazy pymodbus import, graceful error handling with auto-reconnect
- Factory maps `fronius_gen24` to `FroniusInverter`
- Constants: `INVERTER_TYPE_FRONIUS`, sign conventions (battery_sign=1, grid_sign=1), `CONF_FRONIUS_MODBUS_HOST/PORT`
- Manifest: added `pymodbus>=3.6.0` requirement, `fronius` after_dependency

### Task 2: Config migration + WebSocket API for Fronius
**Commit:** 4bdca3f

- Config migration v10->v11 block (no-op, Fronius fields only set in wizard)
- `FRONIUS_SENSOR_SUFFIXES` mapping EEG config keys to Fronius native entity suffixes
- `ws_check_prerequisites` now includes `fronius` domain
- `ws_detect_sensors` handles Fronius via suffix scanning with entity name heuristics (fronius, solarnet, power_flow, byd)

### Task 3: Panel UI -- Fronius wizard card, Modbus config, instruction dialog
**Commit:** de3d3b4

- `DIALOG_CONTENT.fronius` with full setup guide:
  - Fronius Integration setup (auto-discovery + Solar API)
  - Modbus TCP activation (int+SF, Allow Control, port 502)
  - No-auto-revert warning (inverter retains Modbus settings after optimizer crash)
  - Firmware requirements (min 1.34.6-1, recommended 1.40.0)
  - Troubleshooting table
- Wizard Step 1: Fronius Gen24 card with HA brand logo, detection badge
- Modbus IP/Port input fields when Fronius selected
- Validation: requires Fronius integration + Modbus IP address
- Auto-selection when Fronius integration detected
- Updated: grid layout (auto-fit for 4 cards), help texts, summary row, tested setups list
- `config_flow.py` VERSION = 11

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

**1. TODO: KONZEPT open question 8.1** (`inverter/fronius.py`, line 293)
- StorCtl_Mod=3 may force grid discharge even when house consumption could absorb battery output
- Intentional per plan -- needs validation on real Fronius Gen24 hardware
- Does NOT prevent the plan's goal from being achieved

## Self-Check: PASSED

All 8 files verified present. All 3 commit hashes verified in git log.
