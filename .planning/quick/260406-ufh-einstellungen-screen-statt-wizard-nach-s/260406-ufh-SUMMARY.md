---
phase: quick-260406-ufh
plan: 01
subsystem: panel, config
tags: [settings, dashboard-gating, config-migration]
dependency_graph:
  requires: []
  provides: [settings-screen, enable_simulation-toggle, enable_manual_control-toggle]
  affects: [frontend/eeg-optimizer-panel.js, __init__.py, config_flow.py, const.py]
tech_stack:
  added: []
  patterns: [settings-view-mode, per-feature-dashboard-gating]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - Settings as third view mode alongside dashboard and wizard
  - Separate _settingsData object to avoid conflicts with _wizardData
  - Smart migration v10 defaults based on existing expert_mode state
  - Inner setup_complete guard on Simulation card removed as redundant
metrics:
  duration: 4min
  completed: 2026-04-06
---

# Quick Task 260406-ufh: Einstellungen-Screen statt Wizard nach Setup Summary

Settings screen with 3 cards (Expertenmodus, Ladung & Einspeisung, Erweiterte Einstellungen) replaces Wizard as gear-button target; two new config toggles gate dashboard card visibility independently.

## What Was Done

### Task 1: Backend -- Config migration v10 + constants
- Added `CONF_ENABLE_SIMULATION` and `CONF_ENABLE_MANUAL_CONTROL` to const.py
- Bumped config_flow VERSION from 9 to 10
- Added migration v10 block with smart defaults: existing expert_mode=true users get both toggles set to true (preserves current dashboard experience)

**Commit:** `f8327f4`

### Task 2: Frontend -- Settings screen + dashboard gating + wizard restart
- Added `_view = "settings"` as third render branch in `_renderInner()`
- Built `_renderSettings()` with 3 cards reusing field patterns from step 4/5
- Changed gear button `data-action` from `open-wizard` to `open-settings`
- Added `_saveSettings()` method that diffs changed fields and calls save_config WebSocket
- Wizard restart button clears localStorage and starts at step 0
- Dashboard Manual Control card gated by `enable_manual_control` (was `expert_mode`)
- Dashboard Simulation card gated by `enable_simulation` (was `expert_mode` + `setup_complete`)
- Removed inner `setup_complete` guard on Simulation card (redundant when `enable_simulation` controls visibility)
- Added `enable_simulation`/`enable_manual_control` checkboxes to Wizard step 5 in expert mode
- Updated WIZARD_DEFAULTS with both new keys (default: false)

**Commit:** `1de9b07`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] Wizard checkbox change handlers for new toggles**
- **Found during:** Task 2
- **Issue:** The `enable_simulation` and `enable_manual_control` checkboxes in Wizard step 5 used plain `data-field` but the change event listener only handled `expert_mode` explicitly for checkbox inputs.
- **Fix:** Added explicit change handler for `enable_simulation` and `enable_manual_control` fields in the change event listener, mirroring the expert_mode pattern.
- **Files modified:** frontend/eeg-optimizer-panel.js
- **Commit:** 1de9b07

## Known Stubs

None -- all features are fully wired to config entry persistence.

## Verification

- All required markers found in panel JS (automated check passed)
- JavaScript syntax validation passed
- Dashboard gating uses `enable_manual_control` / `enable_simulation` (no more `expert_mode` gate)
- Config migration v10 preserves existing expert user experience

## Self-Check: PASSED
