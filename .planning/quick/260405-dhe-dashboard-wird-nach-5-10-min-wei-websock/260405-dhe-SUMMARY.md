---
phase: quick
plan: 260405-dhe
subsystem: frontend
tags: [bugfix, websocket, dashboard, resilience]
dependency_graph:
  requires: []
  provides: [websocket-resilience, dashboard-stability]
  affects: [eeg-optimizer-panel.js]
tech_stack:
  added: []
  patterns: [watchdog-interval, connectedCallback-reattach, subscription-recovery]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - "60s watchdog interval with 120s staleness threshold balances responsiveness vs overhead"
  - "connectedCallback re-registers visibilitychange listener removed by disconnectedCallback"
metrics:
  duration: "2min"
  completed: "2026-04-05"
---

# Quick Task 260405-dhe: Dashboard WebSocket Resilience Summary

**One-liner:** Three-layer WebSocket resilience (connectedCallback, 60s watchdog, subscription recovery) prevents dashboard white screen after 5-10 minutes.

## What Was Done

### Task 1: Add connectedCallback, watchdog interval, and subscription recovery

**Commit:** 9f4db44

Added three resilience mechanisms to `EegOptimizerPanel` class:

1. **connectedCallback()** -- Re-registers the visibilitychange listener and re-initializes panel data when HA router reattaches the element (e.g., after navigating away and back).

2. **Watchdog interval** -- Runs every 60 seconds. If tab is visible and no hass update received for >120 seconds, forces a config reload. Also re-renders if shadow DOM is empty (white screen recovery).

3. **Subscription recovery in _setHassInner()** -- On every hass update, checks if the activity event subscription is null while setup is complete and panel is initialized. If so, re-subscribes automatically.

4. **Cleanup** -- disconnectedCallback() now stops the watchdog interval before cleanup of other resources.

**Files modified:**
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` (+50 lines)

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- Syntax check: `node -c` passes
- All resilience patterns present (connectedCallback, _startWatchdog, _stopWatchdog, _watchdogInterval, clearInterval)
- Watchdog cleanup verified in disconnectedCallback
- Subscription recovery verified in _setHassInner

## Known Stubs

None.

## Self-Check: PASSED

- [x] `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` exists
- [x] Commit 9f4db44 exists in git log
