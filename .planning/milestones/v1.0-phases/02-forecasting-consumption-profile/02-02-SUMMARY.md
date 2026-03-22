---
phase: 02-forecasting-consumption-profile
plan: 02
subsystem: sensors
tags: [sensor-platform, pv-forecast, consumption-profile, battery, dual-timers]

# Dependency graph
requires:
  - phase: 02-forecasting-consumption-profile
    plan: 01
    provides: "ForecastProvider, ConsumptionCoordinator, Phase 2 constants"
provides:
  - "12 sensor entities: Verbrauchsprofil, 7 daily forecasts, sunrise forecast, battery missing, 2 PV forecasts"
  - "Dual update timer pattern: slow (15min) for profiles, fast (1min) for live data"
  - "async_setup_entry for sensor platform with coordinator/provider wiring"
affects: [02-03, 03-optimizer-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SensorEntity subclasses with _attr_has_entity_name = True and shared DeviceInfo"
    - "Dual async_track_time_interval timers for slow/fast sensor groups"
    - "No state_class on forecast sensors (avoids HA long-term statistics pollution)"
    - "Battery capacity Wh/kWh auto-detection with >1000 threshold"
    - "Module-level _now() for test patching of datetime"

key-files:
  created:
    - custom_components/eeg_energy_optimizer/sensor.py
    - tests/test_sensors.py
  modified:
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/manifest.json

key-decisions:
  - "Forecast sensors omit state_class to prevent HA recorder from accumulating forecast values as measurements"
  - "Battery sensor falls back to manual CONF_BATTERY_CAPACITY_KWH when capacity sensor unavailable"
  - "HA imports guarded with try/except and stubs for test environment compatibility"

patterns-established:
  - "Sensor platform pattern: async_setup_entry creates coordinator+provider, instantiates sensors, sets up dual timers"
  - "All sensor unique_ids prefixed with DOMAIN + entry_id for multi-instance support"

requirements-completed: [FCST-01, FCST-02, FCST-03]

# Metrics
duration: 3min
completed: 2026-03-21
---

# Phase 2 Plan 02: Sensor Platform Summary

**12 sensor entities (PV forecasts, consumption profile, daily forecasts, battery missing energy, sunrise forecast) with dual update timers and full HA integration wiring**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-21T20:11:53Z
- **Completed:** 2026-03-21T20:15:22Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- 6 sensor classes creating 12 entity instances with German names and proper DeviceInfo
- Dual update timers: slow (15min) updates Verbrauchsprofil via coordinator reload, fast (1min) updates daily forecasts, sunrise, battery, PV
- Battery sensor auto-detects Wh vs kWh capacity with >1000 threshold, falls back to manual config
- No state_class on forecast sensors (prevents HA long-term statistics pollution)
- PLATFORMS includes "sensor" for platform forwarding in __init__.py
- manifest.json declares recorder + sun as hard dependencies, solcast_solar + forecast_solar as after_dependencies
- 12 new tests, 80 total tests passing

## Task Commits

1. **Task 1: Sensor platform with 12 sensors and dual update timers (TDD)**
   - `a020e99` (test: RED - failing sensor tests)
   - `ffdd58d` (feat: GREEN - sensor platform implementation)
2. **Task 2: Integration wiring**
   - `d84b4a8` (chore: __init__.py PLATFORMS + manifest.json dependencies)

## Files Created/Modified
- `custom_components/eeg_energy_optimizer/sensor.py` - 6 sensor classes, async_setup_entry, dual timers
- `tests/test_sensors.py` - 12 tests covering battery, PV forecast, daily forecast, profile, sunrise
- `custom_components/eeg_energy_optimizer/__init__.py` - PLATFORMS = ["sensor"]
- `custom_components/eeg_energy_optimizer/manifest.json` - recorder/sun deps, solcast/forecast_solar after_deps

## Decisions Made
- Forecast sensors omit state_class to prevent HA recorder from treating forecasts as measurements
- Battery sensor uses capacity sensor with Wh auto-detect, falls back to manual kWh config
- HA imports guarded with try/except stubs for test environment without homeassistant package

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all sensors are fully implemented with real calculation logic.

## Next Phase Readiness
- 12 sensor entities ready for dashboard consumption and optimizer (Phase 3)
- Coordinator and provider stored in hass.data for access by other platforms
- All 80 tests passing, no regressions

## Self-Check: PASSED

- All 4 key files exist on disk
- All 3 commits verified in git log (a020e99, ffdd58d, d84b4a8)
- 80/80 tests passing

---
*Phase: 02-forecasting-consumption-profile*
*Completed: 2026-03-21*
