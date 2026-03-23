---
phase: quick-260323-fzl
plan: 01
subsystem: consumption-profile
tags: [backfill, recorder, statistics, hausverbrauch]
dependency_graph:
  requires: [hausverbrauch-sensor, grid-power-sensor]
  provides: [historical-consumption-data]
  affects: [consumption-coordinator, forecast-sensors]
tech_stack:
  added: []
  patterns: [recorder-statistics-import, lazy-imports]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/__init__.py
decisions:
  - "async_import_statistics called directly (not via executor) per HA API"
  - "Backfill threshold at 168 entries (1 week hourly) to determine skip"
  - "Float timestamp normalization for cross-sensor alignment"
metrics:
  duration: "3min"
  completed: "2026-03-23"
---

# Quick Task 260323-fzl: One-time Backfill Hausverbrauch Statistics

One-time startup backfill that calculates historical Hausverbrauch = max(PV - Battery - Grid, 0) per hour from 3 source sensors and imports into HA recorder via async_import_statistics, enabling immediate consumption profile generation.

## Changes Made

### Task 1: Add async_backfill_hausverbrauch_stats function and wire into setup

**Commit:** d827f6f

Added `async_backfill_hausverbrauch_stats(hass, config)` function to `__init__.py` with:

1. **Idempotency check**: Queries existing statistics for `sensor.eeg_energy_optimizer_hausverbrauch` over 2 weeks. If >168 entries exist, skips with info log.

2. **Source sensor loading**: Reads PV, Battery, and Grid sensor IDs from config (with defaults from const.py). Loads `mean` statistics for all 3 sensors over the configured lookback period.

3. **Hausverbrauch calculation**: Indexes entries by float timestamp, finds common timestamps across all 3 sensors, and calculates `max(pv_mean - battery_mean - grid_mean, 0.0)` for each overlapping hour. Values rounded to 3 decimal places.

4. **Statistics import**: Uses `async_import_statistics` with `StatisticMetaData(source="recorder", has_mean=True, unit_of_measurement="kW")` and `StatisticData(start=hour_dt, mean=value, state=value)`.

5. **Error safety**: Entire function body wrapped in `try/except Exception` with `_LOGGER.exception()` — backfill failures never block integration startup.

**Wiring**: Called in `async_setup_entry` after coordinator/provider check, before optimizer creation (line 325).

### Task 2: Copy to deployment directory and verify

**Commit:** bce7ec0 (deployment repo)

Copied modified `__init__.py` to `/tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/` and pushed to GitHub. All verification checks passed:
- Function defined and called in setup
- async_import_statistics used
- Skip threshold (168) present
- CONSUMPTION_SENSOR imported from const

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all functionality is fully wired.

## Verification Results

- Python syntax check: PASSED
- `async_backfill_hausverbrauch_stats` defined: YES (2 occurrences: definition + call)
- `async_import_statistics` used: YES (2 occurrences: import + call)
- `CONSUMPTION_SENSOR` imported and used: YES (4 occurrences)
- Deployment copy verified: YES

## Self-Check: PASSED
