# Quick Task 260405-vho: Fix dashboard white-screen nach View Transition Error

## Problem
Dashboard wird nach 10-20 Minuten weiß. Konsole zeigt: "Uncaught (in promise) AbortError: Transition was skipped"

## Root Cause
1. Error-Filter fängt "Transition was aborted" aber nicht "Transition was skipped"
2. Shadow DOM wird durch HA View Transition geleert, aber `set hass()` erkennt das nicht
3. Watchdog prüft leere Shadow DOM nur wenn keine hass-Updates kommen (120s Timeout)

## Tasks

### Task 1: Fix error filter + shadow DOM recovery
- **Files:** `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js`
- **Action:**
  1. Add "Transition was skipped" to unhandledrejection filter
  2. Add empty-shadow-DOM check in `_setHassInner()` to force re-render
  3. Improve watchdog: check for empty DOM independently of hass-update timing, reduce interval to 30s
