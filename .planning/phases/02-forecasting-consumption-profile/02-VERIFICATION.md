---
phase: 02-forecasting-consumption-profile
verified: 2026-03-21T00:00:00Z
status: passed
score: 14/14 must-haves verified
re_verification: false
---

# Phase 2: Forecasting & Consumption Profile Verification Report

**Phase Goal:** The integration reads PV production forecasts from either Solcast or Forecast.Solar and calculates consumption forecasts from HA recorder history -- all data the optimizer needs to make decisions.
**Verified:** 2026-03-21
**Status:** passed
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

All truths are drawn directly from the three plan must_haves blocks (Plan 01, Plan 02, Plan 03).

#### Plan 01 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SolcastProvider reads remaining_today and tomorrow kWh from HA entity states | VERIFIED | `forecast_provider.py` lines 64-69: calls `_read_float(self._hass, self._remaining_id)` and `_read_float(self._hass, self._tomorrow_id)`, returning a `PVForecast` dataclass. Tests `test_solcast_provider_valid_states`, `test_solcast_provider_unavailable` all pass. |
| 2 | ForecastSolarProvider reads remaining_today and tomorrow kWh from HA entity states | VERIFIED | `forecast_provider.py` lines 82-87: identical implementation pattern to SolcastProvider. Tests `test_forecast_solar_provider_valid_states`, `test_forecast_solar_provider_unknown` all pass. |
| 3 | ConsumptionCoordinator loads hourly averages from recorder grouped by 7 individual weekdays | VERIFIED | `coordinator.py` lines 127-173: `_process_entries()` groups entries by `WEEKDAY_KEYS[local_dt.weekday()]`. `WEEKDAY_KEYS = ["mo","di","mi","do","fr","sa","so"]`. Test `test_weekday_grouping` passes. `statistics_during_period` called in `_async_load_statistics`. |
| 4 | ConsumptionCoordinator.calculate_period returns kWh for arbitrary time ranges | VERIFIED | `coordinator.py` lines 188-239: `calculate_period(start, end)` walks hour-by-hour, handles partial hours via fraction. Tests `test_calculate_period_full_hours`, `test_calculate_period_partial_hours`, `test_calculate_period_cross_midnight` all pass. |
| 5 | Missing weekday data falls back to nearest similar weekday | VERIFIED | `coordinator.py` lines 36-44: `FALLBACKS` dict defined. Lines 161-170: fallback chain applied per hour when primary weekday has no data. Tests `test_fallback_chain`, `test_fallback_weekend_to_friday` pass. |

#### Plan 02 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | 12 sensor entities are created and registered with Home Assistant | VERIFIED | `sensor.py` comment lines 3-9 documents all 12. `async_setup_entry` lines 476-494 instantiates: 1 VerbrauchsprofilSensor + 7 DailyForecastSensor + SunriseForecastSensor + BatteryMissingEnergySensor + PVForecastTodaySensor + PVForecastTomorrowSensor = 12. |
| 7 | PV forecast sensors read values from the forecast provider every 1 minute | VERIFIED | `sensor.py` lines 506-519: `async_track_time_interval` sets fast timer with `timedelta(minutes=fast_interval)` (default 1). PV sensors are in `fast_sensors` list. |
| 8 | Consumption profile sensor exposes 7 weekday hourly profiles as attributes | VERIFIED | `sensor.py` lines 165-190: `VerbrauchsprofilSensor.async_update()` builds `{day}_watts` (list of 24 floats) and `{day}_kwh` for all 7 WEEKDAY_KEYS. Test `test_verbrauchsprofil_attributes` passes. |
| 9 | 7 daily consumption forecast sensors show kWh for today through day+6 | VERIFIED | `sensor.py` lines 478-481: `[DailyForecastSensor(..., day_offset=d) for d in range(7)]` creates 7 instances (offsets 0-6). Each calls `calculate_period` for the correct day range. Tests `test_daily_forecast_today`, `test_daily_forecast_tomorrow` pass. |
| 10 | Sunrise forecast sensor calculates consumption from now to next sunrise | VERIFIED | `sensor.py` lines 286-315: `SunriseForecastSensor.async_update()` reads `sun.sun` entity `next_rising` attribute, then calls `coordinator.calculate_period(now, sunrise)`. Returns None gracefully if sun entity unavailable. Tests `test_sunrise_forecast_calculates`, `test_sunrise_forecast_no_sun_entity` pass. |
| 11 | Battery missing energy sensor calculates kWh needed to full charge | VERIFIED | `sensor.py` lines 347-371: reads SOC and capacity (Wh/kWh auto-detected with >1000 threshold), computes `max(100 - soc, 0) / 100 * capacity_kwh`. Tests `test_battery_missing_energy_soc_70`, `test_battery_missing_energy_capacity_wh` pass. |
| 12 | Slow sensors update every 15 minutes, fast sensors every 1 minute | VERIFIED | `sensor.py` lines 496-519: dual `async_track_time_interval` timers. Slow timer uses `CONF_UPDATE_INTERVAL_SLOW` (default 15 min) for coordinator + VerbrauchsprofilSensor. Fast timer uses `CONF_UPDATE_INTERVAL_FAST` (default 1 min) for remaining 11 sensors. |

#### Plan 03 Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 13 | User can select Solcast Solar or Forecast.Solar as PV forecast source in config flow | VERIFIED | `config_flow.py` lines 253-263: `SelectSelector` with `FORECAST_SOURCE_SOLCAST` and `FORECAST_SOURCE_FORECAST_SOLAR` options. Test `test_forecast_step_solcast_valid` passes. |
| 14 | Config flow validates that selected forecast integration is installed and loaded | VERIFIED | `config_flow.py` lines 242-246: checks `hass.config_entries.async_entries(forecast_source)` and filters for `state.value == "loaded"`, returns `errors["base"] = "forecast_not_installed"` if empty. Tests `test_forecast_step_not_installed`, `test_forecast_step_not_loaded` pass. |

**Score: 14/14 truths verified**

---

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `custom_components/eeg_energy_optimizer/const.py` | VERIFIED | Contains all Phase 2 keys: `CONF_FORECAST_SOURCE`, `CONF_FORECAST_REMAINING_ENTITY`, `CONF_FORECAST_TOMORROW_ENTITY`, `CONF_CONSUMPTION_SENSOR`, `CONF_LOOKBACK_WEEKS`, `CONF_UPDATE_INTERVAL_FAST`, `CONF_UPDATE_INTERVAL_SLOW`, `FORECAST_SOURCE_SOLCAST`, `FORECAST_SOURCE_FORECAST_SOLAR`, `DEFAULT_CONSUMPTION_SENSOR`, `DEFAULT_LOOKBACK_WEEKS`, `DEFAULT_UPDATE_INTERVAL_FAST`, `DEFAULT_UPDATE_INTERVAL_SLOW`, `WEEKDAY_KEYS`. |
| `custom_components/eeg_energy_optimizer/forecast_provider.py` | VERIFIED | Exports `PVForecast`, `ForecastProvider`, `SolcastProvider`, `ForecastSolarProvider`. Module-level `_read_float` helper. 88 lines, substantive. |
| `custom_components/eeg_energy_optimizer/coordinator.py` | VERIFIED | Exports `ConsumptionCoordinator`. Contains `FALLBACKS`, `async_update`, `calculate_period`, `dt_util.as_local` equivalent, `statistics_during_period`. 249 lines, substantive. No heizstab/wallbox references. |
| `custom_components/eeg_energy_optimizer/sensor.py` | VERIFIED | Contains 6 sensor classes (producing 12 instances), `async_setup_entry`, `async_track_time_interval`, `_attr_has_entity_name = True`. No `state_class` on forecast sensors. 520 lines, substantive. |
| `custom_components/eeg_energy_optimizer/__init__.py` | VERIFIED | `PLATFORMS: list[str] = ["sensor"]` on line 14. Forwards to sensor platform on setup. |
| `custom_components/eeg_energy_optimizer/manifest.json` | VERIFIED | `"dependencies": ["recorder", "sun"]`, `"after_dependencies": ["huawei_solar", "solcast_solar", "forecast_solar"]`. |
| `custom_components/eeg_energy_optimizer/config_flow.py` | VERIFIED | Contains `async_step_forecast`, `async_step_consumption`, `CONF_FORECAST_SOURCE`, `CONF_CONSUMPTION_SENSOR`, `forecast_not_installed` error, `VERSION = 2`. Step sensors does not call `async_create_entry`; step consumption does. |
| `custom_components/eeg_energy_optimizer/strings.json` | VERIFIED | Contains `"forecast"` step with title `"Prognose-Quelle"`, `"consumption"` step with title `"Verbrauchsmessung"`, `"forecast_not_installed"` error. |
| `custom_components/eeg_energy_optimizer/translations/de.json` | VERIFIED | Byte-identical to strings.json (confirmed via `s == d` Python check). |
| `custom_components/eeg_energy_optimizer/translations/en.json` | VERIFIED | Contains `"forecast"` step with title `"Forecast Source"`, `"consumption"` step with title `"Consumption Measurement"`. |
| `tests/test_forecast_provider.py` | VERIFIED | 14 tests covering `_read_float`, `SolcastProvider`, `ForecastSolarProvider`, base class NotImplementedError. |
| `tests/test_coordinator.py` | VERIFIED | 10 tests covering weekday grouping, calculate_period (full/partial/cross-midnight/empty), fallback chain, empty statistics. |
| `tests/test_sensors.py` | VERIFIED | 12 tests covering BatteryMissingEnergySensor (4 cases), PVForecastSensors (3), DailyForecastSensor (2), VerbrauchsprofilSensor (1), SunriseForecastSensor (2). |
| `tests/test_config_flow.py` | VERIFIED | 13 tests including `test_forecast_step_solcast_valid`, `test_forecast_step_not_installed`, `test_forecast_step_not_loaded`, `test_consumption_step_creates_entry`, `test_full_flow_4_steps`. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `forecast_provider.py` | `hass.states.get()` | `_read_float` helper | WIRED | Line 32: `state = hass.states.get(entity_id)` called in both providers. |
| `coordinator.py` | `recorder.statistics` | `statistics_during_period` | WIRED | Lines 54-58: lazy-imported; lines 114-123: called in `_async_load_statistics` via `async_add_executor_job`. |
| `sensor.py` | `coordinator.py` | `ConsumptionCoordinator` import and usage | WIRED | Line 37: `from .coordinator import ConsumptionCoordinator`. Used in `async_setup_entry` line 458 and passed to sensor constructors. |
| `sensor.py` | `forecast_provider.py` | `ForecastProvider` import and usage | WIRED | Lines 38-41: `from .forecast_provider import ForecastSolarProvider, SolcastProvider`. Used in `async_setup_entry` lines 466-469. |
| `__init__.py` | `sensor.py` | `PLATFORMS` list | WIRED | Line 14: `PLATFORMS: list[str] = ["sensor"]`. Used in `async_forward_entry_setups` line 28. |
| `config_flow.py` | `const.py` | `CONF_FORECAST_SOURCE` import | WIRED | Lines 14-33: full import block including `CONF_FORECAST_SOURCE`. Used line 240. |
| `config_flow.py` | `hass.config_entries` | prerequisite validation | WIRED | Lines 242-246: `self.hass.config_entries.async_entries(forecast_source)` with loaded-state filter. |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FCST-01 | 02-01, 02-02, 02-03 | Solcast PV-Produktionsprognose — verbleibende Produktion heute + Prognose morgen aus Solcast Solar HA-Integration lesen | SATISFIED | `SolcastProvider` reads `remaining_today_kwh` and `tomorrow_kwh` from user-configured entity IDs. Config flow validates Solcast is installed. Sensors expose values. Tests pass. |
| FCST-02 | 02-01, 02-02, 02-03 | Forecast.Solar als Alternative — kostenlose PV-Produktionsprognose als zweite Quelle, wählbar im Setup | SATISFIED | `ForecastSolarProvider` provides identical interface. Config flow step `forecast` allows selection between `solcast_solar` and `forecast_solar`. Both validated on load. Tests pass. |
| FCST-03 | 02-01, 02-02 | Verbrauchsprofil — automatische Verbrauchsprognose aus HA Recorder Langzeit-Statistiken (rollende Durchschnitte, 7 Einzeltage: Mo/Di/Mi/Do/Fr/Sa/So) | SATISFIED | `ConsumptionCoordinator` queries recorder `statistics_during_period`, groups by `WEEKDAY_KEYS` (7 individual days), applies FALLBACKS, exposes `calculate_period`. Configurable lookback weeks. Tests pass. |

No orphaned requirements: all three FCST IDs mapped to Phase 2 appear in the plan frontmatter and are verified.

---

### Anti-Patterns Found

No anti-patterns detected. Specific checks performed:

- No TODO/FIXME/PLACEHOLDER/HACK/XXX comments in any Phase 2 implementation file.
- No `state_class` attribute on forecast sensors (correct -- avoids HA long-term statistics pollution).
- No `return null` / stub-only implementations.
- No heizstab/wallbox/puffer/tesla references in `coordinator.py` (clean separation per D-07/D-17).
- `_read_float` returns None gracefully for all invalid states rather than raising.
- `coordinator.py` "Recorder not available" paths are legitimate test/environment guards, not stubs -- the coordinator initializes to empty zeros in those paths rather than silently failing.

---

### Human Verification Required

The following items cannot be verified programmatically:

#### 1. Solcast Entity Discovery at Runtime

**Test:** In a HA instance with Solcast Solar installed, open the forecast step of the config flow. Verify that the EntitySelector dropdowns populate with Solcast sensor entities.
**Expected:** Sensors like `sensor.solcast_pv_forecast_forecast_remaining_today` appear as options.
**Why human:** Entity registry contents are runtime-specific; the code only stores the ID the user selects.

#### 2. Forecast.Solar Entity Discovery at Runtime

**Test:** Select Forecast.Solar in the forecast step. Verify the entity dropdowns show Forecast.Solar sensors.
**Expected:** Sensors such as `sensor.forecast_solar_energy_today_remaining` appear.
**Why human:** Same as above -- requires a live HA instance with the integration loaded.

#### 3. Recorder Statistics Population

**Test:** After a week of data collection, trigger the slow timer or restart HA. Check `sensor.eeg_energy_optimizer_verbrauchsprofil` attributes in Developer Tools.
**Expected:** `mo_watts`, `di_watts` ... `so_watts` attributes each contain 24 non-zero float values. `stats_count` > 0.
**Why human:** Requires live recorder data; cannot be verified against mock statistics in tests.

#### 4. Dual Timer Lifecycle

**Test:** Confirm that the slow and fast update timers are properly cancelled when the integration is unloaded (Settings → Integrations → Remove).
**Expected:** No residual timer callbacks in HA logs after unload.
**Why human:** `entry.async_on_unload` wiring is correct in code (lines 518-519), but the unload execution path can only be confirmed at runtime.

---

### Summary

Phase 2 goal is fully achieved. All three requirement IDs (FCST-01, FCST-02, FCST-03) are satisfied.

**Data layer (Plan 01):** `SolcastProvider` and `ForecastSolarProvider` both read entity states correctly and return `PVForecast` dataclasses. `ConsumptionCoordinator` loads from recorder, groups by 7 individual weekdays with a defined fallback chain, and exposes `calculate_period()` for arbitrary time ranges including partial-hour handling and midnight crossings.

**Sensor platform (Plan 02):** 12 sensor entities are created across 6 classes. Dual timers (1-minute fast, 15-minute slow) are wired via `async_track_time_interval` and registered for cleanup on unload. No `state_class` on forecast sensors. Battery capacity auto-detects Wh vs kWh.

**Config flow (Plan 03):** Extended from 2 steps to 4. Forecast source prerequisite validation prevents misconfiguration. Entity selectors ensure no hardcoded entity IDs. All UI strings are in German with English translations. `strings.json` and `de.json` are identical. `VERSION` bumped to 2.

Full test suite: 80 tests, 0 failures.

---

_Verified: 2026-03-21_
_Verifier: Claude (gsd-verifier)_
