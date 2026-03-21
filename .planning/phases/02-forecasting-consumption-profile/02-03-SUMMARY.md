---
phase: 02-forecasting-consumption-profile
plan: 03
subsystem: ui
tags: [config-flow, selectors, translations, solcast, forecast-solar]

requires:
  - phase: 02-01
    provides: "Phase 2 const keys (CONF_FORECAST_SOURCE, CONF_CONSUMPTION_SENSOR, etc.)"
provides:
  - "4-step config flow: user -> sensors -> forecast -> consumption"
  - "Forecast source prerequisite validation (Solcast/Forecast.Solar must be loaded)"
  - "Entity selectors for PV forecast entities (no hardcoded IDs)"
  - "Consumption sensor, lookback weeks, update intervals configuration"
  - "German and English translation strings for all 4 steps"
affects: [03-optimizer-battery-control, 04-onboarding-hacs]

tech-stack:
  added: []
  patterns:
    - "Multi-step config flow with prerequisite validation per step"
    - "EntitySelector for user-picked sensors (no hardcoded entity IDs)"

key-files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/strings.json
    - custom_components/eeg_energy_optimizer/translations/de.json
    - custom_components/eeg_energy_optimizer/translations/en.json
    - tests/test_config_flow.py

key-decisions:
  - "Forecast entity selectors shown on same form as source selection (single step, not split)"
  - "VERSION bumped to 2 due to config data schema change"

patterns-established:
  - "Integration prerequisite check pattern: async_entries(domain) -> filter loaded state"

requirements-completed: [FCST-01, FCST-02]

duration: 3min
completed: 2026-03-21
---

# Phase 02 Plan 03: Config Flow Extensions Summary

**4-step config flow with Solcast/Forecast.Solar prerequisite validation, EntitySelector-based PV forecast entity mapping, and consumption sensor configuration**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-21T20:11:59Z
- **Completed:** 2026-03-21T20:15:05Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Extended config flow from 2 steps to 4 steps (user, sensors, forecast, consumption)
- Forecast source validation ensures Solcast Solar or Forecast.Solar integration is installed and loaded before proceeding
- PV forecast entity IDs selected via EntitySelector (no hardcoded values)
- Consumption sensor defaults to sensor.power_meter_verbrauch with configurable lookback weeks and update intervals
- All UI strings in German (primary) with English translations; strings.json and de.json are identical

## Task Commits

Each task was committed atomically:

1. **Task 1: Config flow steps for forecast source + consumption sensor** - `9981a44` (feat)
2. **Task 2: Translation files for all config flow steps** - `ffdd58d` (feat)

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/config_flow.py` - Extended with async_step_forecast and async_step_consumption, VERSION bumped to 2
- `custom_components/eeg_energy_optimizer/strings.json` - Added forecast and consumption step strings (German)
- `custom_components/eeg_energy_optimizer/translations/de.json` - Identical to strings.json
- `custom_components/eeg_energy_optimizer/translations/en.json` - English translations for all 4 steps
- `tests/test_config_flow.py` - Added 8 new tests: forecast validation, consumption entry creation, full 4-step flow

## Decisions Made
- Forecast entity selectors (remaining today + tomorrow) shown on same form as source selection for simpler UX
- VERSION bumped from 1 to 2 because config data schema changed (new keys added)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Config flow complete for Phase 2 needs (forecast + consumption configuration)
- All 80 tests pass across the full test suite
- Ready for Phase 3 optimizer work which will consume these config values

---
*Phase: 02-forecasting-consumption-profile*
*Completed: 2026-03-21*
