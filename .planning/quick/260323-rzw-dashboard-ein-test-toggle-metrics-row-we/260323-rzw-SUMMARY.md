---
phase: quick
plan: 260323-rzw
subsystem: frontend, select
tags: [dashboard, ui, toggle, cleanup]
dependency_graph:
  requires: []
  provides: [ein-test-toggle, simplified-dashboard]
  affects: [eeg-optimizer-panel.js, const.py, select.py]
tech_stack:
  added: []
  patterns: [css-toggle-switch, callService-select]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/select.py
    - tests/test_select.py
decisions:
  - MODE_AUS constant kept in const.py for backwards compatibility (used in __init__.py fallback)
  - Select entity defaults to Test instead of Aus for safety-first approach
metrics:
  duration: 2min
  completed: 2026-03-23
---

# Quick Task 260323-rzw: Dashboard Ein/Test Toggle, Metrics Row Removal

Ein/Test pill toggle switch replacing mode badge, metrics row removed, dashboard simplified

## Commits

| # | Hash | Message | Files |
|---|------|---------|-------|
| 1 | b8e37de | feat(quick-260323-rzw): remove Aus from optimizer select entity | const.py, select.py, test_select.py |
| 2 | 32bb793 | feat(quick-260323-rzw): add Ein/Test toggle, remove metrics row and mode badge | eeg-optimizer-panel.js |

## What Changed

### Task 1: Remove Aus from backend select entity
- `OPTIMIZER_MODES` reduced from `[Ein, Test, Aus]` to `[Ein, Test]`
- `MODE_AUS` constant kept for backwards compatibility (still referenced in `__init__.py`)
- Select entity default changed from `MODE_AUS` to `MODE_TEST`
- Restore logic naturally rejects old "Aus" saved states (falls back to Test)
- Tests updated: 10 tests pass, including new `test_restore_aus_state_rejected`

### Task 2: Dashboard UI changes
- **Added**: Pill-shaped toggle switch (green=Ein, orange=Test) at top-right of dashboard
- **Added**: Click handler calling `hass.callService("select", "select_option", ...)` to toggle mode
- **Removed**: Metrics row (Batterie SOC, PV Heute, PV Morgen) -- 3 metric cards
- **Removed**: Mode badge from Abend-Entladung status card (`.mode-line` div)
- **Removed**: Related CSS rules (`.metrics-row`, `.metric-card`, `.mode-line`, narrow overrides)
- **Added**: CSS for `.mode-toggle-row`, `.mode-toggle`, `.toggle-knob` with Ein/Test states

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
