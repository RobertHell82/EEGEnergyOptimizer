---
phase: 01-foundation-inverter-layer
plan: 02
subsystem: inverter
tags: [home-assistant, config-flow, huawei-solar, inverter, testing]

# Dependency graph
requires:
  - phase: 01-01
    provides: HACS skeleton, abstract InverterBase interface, INVERTER_TYPES factory
provides:
  - HuaweiInverter implementation calling huawei_solar HA services
  - 2-step config flow with inverter type selection and sensor mapping
  - Prerequisite validation (blocks setup if huawei_solar not loaded)
  - German and English translations per UI-SPEC copywriting contract
  - 22 tests across inverter and config flow test files
affects: [02-optimizer-core, 03-sensors-dashboard]

# Tech tracking
tech-stack:
  added:
    - homeassistant.helpers.selector (SelectSelector, EntitySelector, DeviceSelector)
    - homeassistant.config_entries (ConfigFlow, ConfigEntryState)
  patterns:
    - TDD Red-Green for HA service call verification
    - Prerequisite guard in config flow step_user before advancing
    - Power-as-string conversion: str(int(power_kw * 1000)) per Huawei Solar services.yaml
    - Auto-detect Huawei device from device registry (no manual device picker)

key-files:
  created:
    - custom_components/eeg_energy_optimizer/inverter/huawei.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - custom_components/eeg_energy_optimizer/strings.json
    - custom_components/eeg_energy_optimizer/translations/de.json
    - custom_components/eeg_energy_optimizer/translations/en.json
    - tests/test_huawei_inverter.py
    - tests/test_config_flow.py
  modified:
    - custom_components/eeg_energy_optimizer/inverter/__init__.py
    - custom_components/eeg_energy_optimizer/const.py

key-decisions:
  - "Huawei Solar SOC sensor has no device_class='battery' — EntitySelector filter removed to allow selection"
  - "Huawei battery device auto-detected from device registry (first huawei_solar device) rather than requiring user to pick from DeviceSelector"
  - "Manual battery capacity (kWh) input added as alternative to sensor, since Huawei capacity sensor may not exist on all installations"
  - "German umlauts (ä/ö/ü) used in all UI strings after live testing showed placeholder text was wrong"

patterns-established:
  - "Pattern: InverterBase subclass sends commands via hass.services.async_call, power always as string watts"
  - "Pattern: Config flow prerequisite check via hass.config_entries.async_entries(domain) for ConfigEntryState.LOADED"
  - "Pattern: Defaults injected in async_step_sensors so users see pre-filled Huawei sensor suggestions"

requirements-completed: [INF-02, INF-03]

# Metrics
duration: ~90min
completed: 2026-03-21
---

# Phase 01 Plan 02: Huawei Inverter & Config Flow Summary

**HuaweiInverter sending forcible charge/discharge/stop to huawei_solar HA services, with a 2-step config flow that blocks setup when the prerequisite integration is absent — verified by live HA testing.**

## Performance

- **Duration:** ~90 min (including live HA testing and bugfix round)
- **Started:** 2026-03-21T06:45:00Z (estimated)
- **Completed:** 2026-03-21T10:40:00Z (estimated)
- **Tasks:** 3 of 3 (Task 3 = human-verify checkpoint, approved)
- **Files modified:** 9 files (282 + 397 + 202 = ~880 lines added)

## Accomplishments

- HuaweiInverter fully implements InverterBase: charge, discharge, stop, availability — all sending correct huawei_solar service calls with power as string watts
- 2-step config flow (inverter type + sensor mapping) with prerequisite validation, SelectSelector, EntitySelector, and Huawei defaults pre-filled
- German and English translations complete per UI-SPEC copywriting contract with proper umlauts
- Integration loaded successfully in live HA instance (192.168.100.211) with no errors
- 22 tests pass (15 inverter + 7 config flow)

## Task Commits

1. **Task 1: Implement HuaweiInverter and register in factory** — `7bbe131` (feat)
2. **Task 2: Config flow with prerequisite validation and translations** — `208f078` (feat)
3. **Task 3: Verify integration loads in Home Assistant** — checkpoint approved (no commit needed)
4. **Post-checkpoint auto-fix: config flow improvements from live testing** — `39fb07d` (fix)

## Files Created/Modified

- `custom_components/eeg_energy_optimizer/inverter/huawei.py` — HuaweiInverter class, 3 service methods + is_available
- `custom_components/eeg_energy_optimizer/inverter/__init__.py` — registered HuaweiInverter in INVERTER_TYPES factory
- `custom_components/eeg_energy_optimizer/config_flow.py` — 2-step EegEnergyOptimizerConfigFlow with prerequisite guard and Huawei defaults
- `custom_components/eeg_energy_optimizer/const.py` — added CONF_BATTERY_CAPACITY_KWH constant
- `custom_components/eeg_energy_optimizer/strings.json` — German UI strings with umlauts, data_description help texts
- `custom_components/eeg_energy_optimizer/translations/de.json` — German translations (primary language)
- `custom_components/eeg_energy_optimizer/translations/en.json` — English fallback translations
- `tests/test_huawei_inverter.py` — 15 tests: service call params, power-as-string, error returns, availability
- `tests/test_config_flow.py` — 7 tests: form display, prerequisite guard, entry creation, unique_id abort

## Decisions Made

**Remove device_class filter on SOC sensor:** The Huawei Solar integration's SOC sensor (`batteries_batterieladung`) does not have `device_class="battery"` set. Keeping the EntitySelector filter would prevent the sensor from appearing. Filter removed; users see all sensors and must pick the right one.

**Auto-detect Huawei device:** Instead of DeviceSelector (which confused users), the config flow auto-detects the first loaded huawei_solar device from the device registry. No manual picker needed.

**Manual capacity fallback:** Added `CONF_BATTERY_CAPACITY_KWH` (NumberSelector) as alternative to the capacity sensor, since not all Huawei installations expose a capacity sensor entity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SOC EntitySelector blocked Huawei sensor from appearing**
- **Found during:** Task 3 (live HA testing)
- **Issue:** `EntitySelectorConfig(device_class="battery")` excluded `batteries_batterieladung` which has no device_class
- **Fix:** Removed device_class filter from SOC sensor selector
- **Files modified:** `config_flow.py`, `strings.json`, `translations/de.json`, `translations/en.json`
- **Committed in:** `39fb07d`

**2. [Rule 2 - Missing critical functionality] DeviceSelector confused users; auto-detect added**
- **Found during:** Task 3 (live HA testing)
- **Issue:** Presenting DeviceSelector made users unsure which device to pick; auto-detection is more reliable
- **Fix:** Replaced DeviceSelector with auto-detection of first loaded huawei_solar device from device registry
- **Files modified:** `config_flow.py`
- **Committed in:** `39fb07d`

**3. [Rule 1 - Bug] German placeholder text used ae/oe/ue instead of proper umlauts**
- **Found during:** Task 3 (live HA testing — UI text review)
- **Issue:** All German strings used ASCII approximations (ae→ä, oe→ö, ue→ü) which displayed incorrectly
- **Fix:** Replaced all instances with proper Unicode umlauts in strings.json, de.json, en.json
- **Files modified:** `strings.json`, `translations/de.json`, `translations/en.json`
- **Committed in:** `39fb07d`

---

**Total deviations:** 3 auto-fixed (Rule 1 x2, Rule 2 x1)
**Impact on plan:** All fixes required for correct operation. No scope creep — changes stayed within the config flow and translations files already in scope.

## Issues Encountered

Live HA testing revealed three issues (documented above as deviations). All three were fixed in a single commit (`39fb07d`) after the human-verify checkpoint returned "approved" — the user approved the basic flow loading while noting issues during the test session.

## Known Stubs

None — all config flow data flows into the config entry. No placeholder values reach the UI.

## Self-Check: PASSED

- `custom_components/eeg_energy_optimizer/inverter/huawei.py` — EXISTS
- `custom_components/eeg_energy_optimizer/config_flow.py` — EXISTS
- `custom_components/eeg_energy_optimizer/strings.json` — EXISTS
- `custom_components/eeg_energy_optimizer/translations/de.json` — EXISTS
- `custom_components/eeg_energy_optimizer/translations/en.json` — EXISTS
- `tests/test_huawei_inverter.py` — EXISTS
- `tests/test_config_flow.py` — EXISTS
- Commits `7bbe131`, `208f078`, `39fb07d` — VERIFIED in git log
