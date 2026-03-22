---
phase: 03-optimizer-safety-system
plan: 01
subsystem: optimizer
tags: [battery-management, decision-engine, eeg, select-entity, restore-state, tdd]

# Dependency graph
requires:
  - phase: 02-sensor-forecast-system
    provides: "ConsumptionCoordinator, ForecastProvider, sensor helpers"
  - phase: 01-foundation-and-config
    provides: "InverterBase, config flow, const.py foundations"
provides:
  - "EEGOptimizer decision engine with morning charge blocking and evening discharge"
  - "Snapshot/Decision dataclasses for cycle state"
  - "OptimizerModeSelect entity with Ein/Test/Aus and RestoreEntity"
  - "Phase 3 config keys, mode constants, state constants in const.py"
affects: [03-02, 03-03, 04-onboarding]

# Tech tracking
tech-stack:
  added: [pytest-asyncio]
  patterns: [snapshot-decision-execute, inverter-deduplication, tdd-red-green]

key-files:
  created:
    - custom_components/eeg_energy_optimizer/optimizer.py
    - custom_components/eeg_energy_optimizer/select.py
    - tests/test_optimizer.py
    - tests/test_select.py
  modified:
    - custom_components/eeg_energy_optimizer/const.py
    - tests/conftest.py

key-decisions:
  - "Dynamic min-SOC lives as discharge calculation, not as guard (D-14/D-16)"
  - "Three optimizer modes: Ein (execute), Test (dry-run), Aus (inactive) per D-17"
  - "Inverter deduplication via _prev_zustand prevents redundant API calls"
  - "Morning block window: sunrise-1h to configurable end time, only on surplus days"

patterns-established:
  - "Snapshot/Decision pattern: gather inputs -> evaluate -> execute"
  - "Inverter deduplication: skip calls when state unchanged"
  - "HA import guards with test-compatible stubs for SelectEntity/RestoreEntity"

requirements-completed: [OPT-01, OPT-02, OPT-03, SAF-01, SAF-02, SAF-03, SAF-04]

# Metrics
duration: 4min
completed: 2026-03-21
---

# Phase 3 Plan 1: Optimizer Decision Engine Summary

**EEG optimizer with morning charge blocking, evening discharge with dynamic min-SOC, surplus-day detection, and Ein/Test/Aus mode select entity**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-21T21:16:06Z
- **Completed:** 2026-03-21T21:20:16Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- EEGOptimizer decision engine with Snapshot/Decision dataclasses implementing morning charge blocking (D-01 to D-04) and evening discharge (D-05 to D-09)
- OptimizerModeSelect entity with Ein/Test/Aus modes and RestoreEntity persistence across restarts
- 29 unit tests covering surplus factor, morning blocking, min-SOC calculation, discharge conditions, mode execution, and inverter deduplication

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend const.py and create optimizer.py** - `ba54d0f` (feat)
2. **Task 2: Create select.py with OptimizerModeSelect** - `f38b08c` (feat)

_TDD approach: RED (import error) -> GREEN (all tests pass) for both tasks_

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/const.py` - Extended with Phase 3 config keys, mode/state constants, defaults
- `custom_components/eeg_energy_optimizer/optimizer.py` - EEGOptimizer engine with Snapshot/Decision dataclasses
- `custom_components/eeg_energy_optimizer/select.py` - OptimizerModeSelect with Ein/Test/Aus and RestoreEntity
- `tests/conftest.py` - Added mock_inverter, mock_coordinator, mock_provider fixtures
- `tests/test_optimizer.py` - 20 tests for optimizer logic
- `tests/test_select.py` - 9 tests for select entity

## Decisions Made
- Dynamic min-SOC formula: base + ceil((overnight * (1+buffer%) / capacity) * 100) -- per D-08
- Morning block only activates on surplus days (factor >= 1.25 threshold) -- per D-03
- Evening discharge requires: time >= start, SOC > min_soc, PV tomorrow >= total demand -- per D-05/D-09
- SAF-01/SAF-02 guards dropped per D-14/D-16 -- min-SOC is discharge calculation only
- Inverter deduplication via _prev_zustand prevents redundant API calls on repeated cycles

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all data paths are wired to mock dependencies for testing and will connect to real HA entities at runtime.

## Next Phase Readiness
- Optimizer engine ready for integration with __init__.py (60s timer, platform forwarding)
- Select entity ready for platform registration
- Decision sensor (03-02) can consume EEGOptimizer.last_decision for dashboard display

---
*Phase: 03-optimizer-safety-system*
*Completed: 2026-03-21*
