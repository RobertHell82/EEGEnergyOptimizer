---
phase: quick
plan: 260323-mpk
subsystem: frontend/panel
tags: [dashboard, ux, connection-handling]
dependency_graph:
  requires: []
  provides: [connection-lost-banner]
  affects: [eeg-optimizer-panel.js]
tech_stack:
  added: []
  patterns: [css-spinner-animation, entity-availability-guard]
key_files:
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions: []
metrics:
  duration: 2min
  completed: "2026-03-23"
---

# Quick Task 260323-mpk: Dashboard Verbindungsverlust Banner Summary

Connection-lost banner with warning icon and spinner replaces white-screen when HA WebSocket drops, auto-recovers on reconnect.

## What Was Done

### Task 1: Add connection-lost banner to dashboard
**Commit:** 40d741a

Added a guard in `_renderDashboard()` that checks if both the decision sensor entity and the mode select entity are unavailable. When both are null (indicating HA connection loss), the dashboard renders a centered banner instead of trying to render the normal dashboard with "---" values everywhere.

**Banner includes:**
- Warning icon (unicode triangle warning)
- "Verbindung verloren" heading
- "Warte auf Verbindung zum Home Assistant Server..." subtitle
- CSS spinning indicator using HA theme variables

**CSS styles added:**
- `.connection-lost` flex container (centered, 60vh min-height)
- `.connection-lost-icon` (48px warning color)
- `.connection-lost-spinner` (32px border spinner with `conn-spin` keyframes)
- All colors use HA CSS custom properties for light/dark theme compatibility

**Recovery:** No reconnect logic needed. HA's `set hass()` setter automatically triggers `_render()` when the connection restores, which re-evaluates the entity availability check and renders the normal dashboard.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 40d741a | feat(quick-260323-mpk): add connection-lost banner to dashboard |
