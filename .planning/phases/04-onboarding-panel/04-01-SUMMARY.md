---
phase: 04-onboarding-panel
plan: 01
subsystem: ui, api
tags: [websocket, ha-panel, config-flow, migration, custom-element, shadow-dom]

# Dependency graph
requires:
  - phase: 03-optimizer
    provides: optimizer modes, config entry v3, sensor/select platforms
provides:
  - WebSocket API with 4 commands (get_config, save_config, check_prerequisites, detect_sensors)
  - Sidebar panel registration with mdi:solar-power icon
  - Panel shell custom element with dashboard/wizard view toggle
  - 1-click config flow (VERSION 4)
  - v3 to v4 migration with setup_complete flag
affects: [04-02, 04-03]

# Tech tracking
tech-stack:
  added: [ha-websocket-api, ha-frontend-panel, shadow-dom]
  patterns: [websocket-command-handlers, panel-custom-element, event-delegation]

key-files:
  created:
    - custom_components/eeg_energy_optimizer/websocket_api.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
  modified:
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/manifest.json
    - custom_components/eeg_energy_optimizer/strings.json
    - custom_components/eeg_energy_optimizer/translations/de.json

key-decisions:
  - "HUAWEI_DEFAULTS and _find_huawei_battery_device moved from config_flow to websocket_api (needed for detect_sensors command)"
  - "Panel uses plain HTMLElement with Shadow DOM instead of LitElement (no external imports)"
  - "Config flow reduced to single empty form submission creating entry with setup_complete=false"

patterns-established:
  - "WebSocket command pattern: @websocket_command decorator + @async_response for all panel communication"
  - "Panel event delegation: single click listener on shadow root checking data-action attributes"
  - "Selective re-render: hass setter only triggers render when WATCHED entity states change"

requirements-completed: [INF-04]

# Metrics
duration: 3min
completed: 2026-03-22
---

# Phase 04 Plan 01: Panel Infrastructure Summary

**WebSocket API with 4 commands, HA sidebar panel with Shadow DOM shell, 1-click config flow replacing 5-step flow, v3-to-v4 migration**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-22T07:08:27Z
- **Completed:** 2026-03-22T07:11:04Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Created websocket_api.py with get_config, save_config, check_prerequisites, detect_sensors commands
- Registered sidebar panel with mdi:solar-power icon loading eeg-optimizer-panel.js custom element
- Replaced 5-step config flow with single-click entry creation (VERSION 4)
- Added v3-to-v4 migration adding setup_complete=false to existing entries
- Created panel shell with dashboard/wizard view toggle, setup card, and German UI text

## Task Commits

Each task was committed atomically:

1. **Task 1: WebSocket API + panel registration + config flow reduction + migration** - `fb923e9` (feat)
2. **Task 2: Panel shell JS file (dashboard/wizard view toggle)** - `25864a8` (feat)

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/websocket_api.py` - 4 WebSocket command handlers + HUAWEI_DEFAULTS + device detection
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` - Panel shell custom element (249 lines)
- `custom_components/eeg_energy_optimizer/__init__.py` - Panel registration, WS command setup, v4 migration
- `custom_components/eeg_energy_optimizer/config_flow.py` - Minimal 1-click flow (VERSION 4)
- `custom_components/eeg_energy_optimizer/const.py` - Added CONF_SETUP_COMPLETE
- `custom_components/eeg_energy_optimizer/manifest.json` - Added http, frontend, websocket_api dependencies
- `custom_components/eeg_energy_optimizer/strings.json` - Simplified to 1-click flow text
- `custom_components/eeg_energy_optimizer/translations/de.json` - Mirrored strings.json changes

## Decisions Made
- Moved HUAWEI_DEFAULTS and _find_huawei_battery_device from config_flow.py to websocket_api.py since config_flow no longer needs them
- Used plain HTMLElement + Shadow DOM for panel (no LitElement/Lit dependency, no CDN imports)
- Config entry created with only setup_complete=false; all other config populated via panel wizard

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- WebSocket commands ready for wizard (Plan 02) and dashboard (Plan 03) to use
- Panel shell ready with wizard-root and dashboard-root placeholder divs
- Panel loads config on first hass set and shows appropriate view based on setup_complete

---
*Phase: 04-onboarding-panel*
*Completed: 2026-03-22*

## Self-Check: PASSED
- All 8 files found on disk
- Both task commits verified (fb923e9, 25864a8)
