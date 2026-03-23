---
phase: quick-260323-u1p
plan: 01
subsystem: optimizer, frontend
tags: [simulation, websocket, dashboard, testing]

provides:
  - "Runtime test overrides for consumption factor and SOC in optimizer"
  - "Three new WS commands: set/get/clear test_overrides"
  - "Dashboard simulation card with factor input, SOC override, warning banner"
affects: [optimizer, dashboard]

tech-stack:
  added: []
  patterns: ["hass.data runtime overrides for simulation without config persistence"]

key-files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/optimizer.py
    - custom_components/eeg_energy_optimizer/websocket_api.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js

key-decisions:
  - "Runtime-only overrides stored in hass.data (no config persistence, no restart survival)"
  - "entry_id added to EEGOptimizer constructor for scoped override lookup"
  - "_get_entry_data helper reusable for future WS commands needing entry+data"

requirements-completed: [SIM-01]

duration: 3min
completed: 2026-03-23
---

# Quick Task 260323-u1p: Simulation Overrides Summary

**Dashboard simulation section with consumption factor (0.1-3.0x) and SOC override for testing optimizer decisions without waiting for real conditions**

## What Was Built

### Task 1: Backend (optimizer.py, websocket_api.py, __init__.py)
- Added `entry_id` parameter to `EEGOptimizer.__init__()` for scoped hass.data lookup
- Override logic at end of `_gather_snapshot()`: multiplies all 6 consumption fields by factor, optionally replaces battery_soc
- Three new WebSocket commands:
  - `eeg_optimizer/set_test_overrides` — sets consumption_factor (0.1-3.0) and optional soc_override (0-100)
  - `eeg_optimizer/get_test_overrides` — returns current overrides or null
  - `eeg_optimizer/clear_test_overrides` — removes overrides
- `_get_entry_data()` helper for entry+data lookup pattern

### Task 2: Frontend (eeg-optimizer-panel.js)
- Simulation card below Manual Control with:
  - Consumption factor number input (0.1-3.0, step 0.1, default 1.0)
  - SOC override with enable checkbox (0-100, default 50, disabled until checked)
  - "Anwenden" button calls set_test_overrides WS
  - "Zuruecksetzen" button calls clear_test_overrides WS
- Orange warning banner at top of dashboard when overrides active, with inline reset button
- Override state loaded on dashboard init via get_test_overrides
- Only shown when setup_complete is true

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 441dbc4 | Backend: entry_id, WS commands, snapshot override |
| 2 | 0a2b305 | Frontend: simulation card, banner, event handlers |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
