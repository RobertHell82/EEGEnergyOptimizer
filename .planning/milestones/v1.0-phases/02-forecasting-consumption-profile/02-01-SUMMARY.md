---
phase: 02-forecasting-consumption-profile
plan: 01
subsystem: forecasting
tags: [solcast, forecast-solar, recorder, consumption-profile, pv-forecast]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Integration scaffolding, const.py, inverter abstraction, test infrastructure"
provides:
  - "PV forecast provider abstraction (SolcastProvider, ForecastSolarProvider)"
  - "ConsumptionCoordinator with 7-day weekday grouping from recorder statistics"
  - "Phase 2 config constants (forecast source, consumption sensor, intervals)"
  - "PVForecast dataclass for forecast data exchange"
  - "calculate_period() for arbitrary time range consumption forecasts"
affects: [02-02, 02-03, 03-optimizer-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ForecastProvider base class with _read_float helper for entity state reads"
    - "Recorder statistics query via get_instance().async_add_executor_job()"
    - "7-day weekday grouping with FALLBACKS dict for missing data"
    - "Module-level _as_local/_now for easy test patching of HA datetime utilities"

key-files:
  created:
    - custom_components/eeg_energy_optimizer/forecast_provider.py
    - custom_components/eeg_energy_optimizer/coordinator.py
    - tests/test_forecast_provider.py
    - tests/test_coordinator.py
  modified:
    - custom_components/eeg_energy_optimizer/const.py

key-decisions:
  - "Module-level _as_local/_now pattern for timezone handling: enables test patching without importing homeassistant.util.dt"
  - "Lazy recorder imports via _ensure_recorder_imports(): avoids ImportError in test environment"
  - "_read_float as module-level function (not method): simpler import for tests, shared across providers"

patterns-established:
  - "ForecastProvider hierarchy: base class with _read_float, concrete providers store entity IDs"
  - "ConsumptionCoordinator: recorder stats grouped by WEEKDAY_KEYS with FALLBACKS chain"
  - "TDD workflow: RED commit (failing tests) then GREEN commit (implementation)"

requirements-completed: [FCST-01, FCST-02, FCST-03]

# Metrics
duration: 5min
completed: 2026-03-21
---

# Phase 2 Plan 01: Data Layer Summary

**PV forecast abstraction (Solcast + Forecast.Solar) and consumption coordinator with 7-day weekday grouping from HA recorder statistics, plus Phase 2 config constants**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-21T20:04:00Z
- **Completed:** 2026-03-21T20:09:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- PV forecast providers (SolcastProvider, ForecastSolarProvider) reading entity states via _read_float helper
- ConsumptionCoordinator with 7-day weekday grouping, fallback chain, and calculate_period for arbitrary time ranges
- All Phase 2 config constants defined (forecast source, consumption sensor, intervals, weekday keys)
- Full TDD coverage: 25 new tests (14 forecast + 11 coordinator), 61 total tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Constants + forecast provider + tests**
   - `6cba814` (test: RED - failing forecast provider tests)
   - `09e27cf` (feat: GREEN - forecast providers + Phase 2 constants)
2. **Task 2: Consumption profile coordinator + tests**
   - `9101747` (test: RED - failing coordinator tests)
   - `3277eb5` (feat: GREEN - ConsumptionCoordinator implementation)

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/const.py` - Added Phase 2 config keys, defaults, WEEKDAY_KEYS
- `custom_components/eeg_energy_optimizer/forecast_provider.py` - PVForecast dataclass, ForecastProvider base, SolcastProvider, ForecastSolarProvider
- `custom_components/eeg_energy_optimizer/coordinator.py` - ConsumptionCoordinator with recorder stats, 7-day grouping, FALLBACKS, calculate_period
- `tests/test_forecast_provider.py` - 14 tests covering both providers and _read_float edge cases
- `tests/test_coordinator.py` - 11 tests covering weekday grouping, calculate_period (full/partial/cross-midnight), fallbacks, empty stats

## Decisions Made
- Used module-level `_as_local`/`_now` pattern for timezone handling instead of inline imports, enabling clean test patching
- Lazy recorder imports via `_ensure_recorder_imports()` to avoid ImportError in test environment without HA
- `_read_float` as module-level function rather than static method for simpler test imports

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed timezone handling in coordinator tests**
- **Found during:** Task 2 (coordinator implementation)
- **Issue:** Test statistics timestamps were created in CET but coordinator's `as_local` fallback was a no-op (identity function), causing weekday misalignment (UTC vs CET offset shifted entries by 1 hour, putting midnight entries on wrong weekday)
- **Fix:** Added module-level `_as_local`/`_now` imports with fallbacks, patched `_as_local` in tests with CET conversion function
- **Files modified:** coordinator.py, test_coordinator.py
- **Verification:** All 11 coordinator tests pass with correct weekday grouping
- **Committed in:** 3277eb5 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix for test correctness. No scope creep.

## Issues Encountered
None beyond the timezone deviation above.

## Known Stubs
None - all data providers are fully implemented with real logic.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- forecast_provider.py and coordinator.py ready for sensor.py (Plan 02) to consume
- Config constants ready for config_flow.py extension (Plan 03)
- All 61 tests passing, no regressions

## Self-Check: PASSED

- All 5 key files exist on disk
- All 4 commits verified in git log (6cba814, 09e27cf, 9101747, 3277eb5)
- 61/61 tests passing

---
*Phase: 02-forecasting-consumption-profile*
*Completed: 2026-03-21*
