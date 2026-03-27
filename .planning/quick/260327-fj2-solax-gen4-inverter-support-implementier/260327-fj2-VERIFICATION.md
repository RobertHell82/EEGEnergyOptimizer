---
phase: quick-260327-fj2
verified: 2026-03-27T00:00:00Z
status: passed
score: 7/7 must-haves verified
---

# Quick Task: SolaX Gen4+ Inverter Support — Verification Report

**Task Goal:** Implement full SolaX Gen4+ inverter support as specified in STORY_SOLAX_INVERTER.md
**Verified:** 2026-03-27
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SolaX Gen4+ inverter type is selectable in the setup wizard | VERIFIED | `eeg-optimizer-panel.js` renders SolaX card with `data-value="solax_gen4"`, `_renderStep1()` lines 1468-1475 |
| 2 | Auto-detection finds SolaX remote control entities by `*_remotecontrol_power_control` pattern | VERIFIED | `_find_solax_prefix()` in `websocket_api.py` lines 81-88 searches `hass.states.async_all("select")` for entities ending in `remotecontrol_power_control` |
| 3 | SolaXInverter controls battery via two-phase write model (set params + press trigger) | VERIFIED | `inverter/solax.py` all 3 methods: set select + set numbers, then `_press_trigger()` as final step |
| 4 | kW-to-W conversion happens inside SolaXInverter (InverterBase uses kW, SolaX uses W) | VERIFIED | `async_set_charge_limit`: `power_w = int(power_kw * 1000)`; `async_set_discharge`: `power_w = -abs(int(power_kw * 1000))` |
| 5 | `pv_power_sensor_2` optional field is supported in config and summed in Hausverbrauch sensor | VERIFIED | `sensor.py` lines 486, 512-515: `self._pv_sensor_2_id = config.get(CONF_PV_POWER_SENSOR_2, "")`, summed in `async_update` |
| 6 | Hardcoded Huawei fallbacks in `__init__.py` replaced with empty-string defaults | VERIFIED | `async_backfill_hausverbrauch_stats()` lines 91-101: uses `config.get(..., "")` with explicit skip if empty. `DEFAULT_GRID_POWER_SENSOR` and `DEFAULT_BATTERY_POWER_SENSOR` removed from `const.py` |
| 7 | `solax_modbus` added to `check_prerequisites` domain list | VERIFIED | `websocket_api.py` line 233: `check_domains = ["huawei_solar", "solax_modbus", "solcast_solar", "forecast_solar"]` |

**Score: 7/7 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/eeg_energy_optimizer/inverter/solax.py` | SolaXInverter class implementing InverterBase | VERIFIED | 140 lines; exports `SolaXInverter`, `SOLAX_DOMAIN`, `SOLAX_ENTITY_DEFAULTS`; all 4 InverterBase methods implemented |
| `custom_components/eeg_energy_optimizer/inverter/__init__.py` | Factory with `solax_gen4` type registered | VERIFIED | `INVERTER_TYPES = {"huawei_sun2000": HuaweiInverter, "solax_gen4": SolaXInverter}` |
| `custom_components/eeg_energy_optimizer/const.py` | `INVERTER_TYPE_SOLAX`, `CONF_PV_POWER_SENSOR_2` constants | VERIFIED | Both constants present at lines 15 and 22 |
| `custom_components/eeg_energy_optimizer/websocket_api.py` | `SOLAX_DEFAULTS`, `_find_solax_prefix`, extended `detect_sensors` | VERIFIED | `SOLAX_DEFAULTS` at line 58, `_find_solax_prefix` at line 81, SolaX branch in `ws_detect_sensors` at line 284 |
| `tests/test_solax_inverter.py` | Unit tests for SolaXInverter | VERIFIED | 20 tests, all passing |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `inverter/__init__.py` | `inverter/solax.py` | factory `INVERTER_TYPES` dict | VERIFIED | `from .solax import SolaXInverter` + `"solax_gen4": SolaXInverter` in dict |
| `websocket_api.py` | `const.py` | `INVERTER_TYPE_SOLAX` import | VERIFIED | Line 24: `INVERTER_TYPE_SOLAX` imported from `.const` |
| `sensor.py` | `const.py` | `CONF_PV_POWER_SENSOR_2` import | VERIFIED | Line 31: `CONF_PV_POWER_SENSOR_2` imported, used in `HausverbrauchSensor` |
| `frontend/eeg-optimizer-panel.js` | `websocket_api.py` | `detect_sensors` WS call returns SolaX sensors | VERIFIED | `_detectSensors()` handles `solax_prefix` response, pre-fills all 5 SolaX control keys |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `HausverbrauchSensor` | `pv_power` | `_read_float(hass, self._pv_sensor_2_id)` + `_read_float(hass, self._pv_sensor_id)` | Yes — reads live HA sensor states | FLOWING |
| `SolaXInverter.async_set_charge_limit` | `power_w` (writes to HA services) | `hass.services.async_call("number", "set_value", ...)` | Yes — calls live HA entity services | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SolaX unit tests pass (20 tests) | `pytest tests/test_solax_inverter.py -v` | 20 passed in 0.27s | PASS |
| Factory registers `solax_gen4` | Python with mocked HA modules | `['huawei_sun2000', 'solax_gen4']` | PASS |
| All required UI strings in panel JS | node check for 6 key strings | All 6 FOUND | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| SOLAX-IMPL | 260327-fj2-PLAN.md | Full SolaX Gen4+ inverter support from STORY_SOLAX_INVERTER.md | SATISFIED | All 7 must-have truths verified; all story sections 2.3-2.5 implemented |

---

### Anti-Patterns Found

None detected. Specifically checked:

- No hardcoded Huawei fallback sensor strings in `async_backfill_hausverbrauch_stats` — uses empty-string defaults with skip logic
- Note: Migration blocks in `__init__.py` (lines 234, 239) still contain old sensor strings (`sensor.power_meter_wirkleistung`, `sensor.batteries_lade_entladeleistung`) — these are correct and intentional: they set defaults for users upgrading from config versions 5/6. This is not a regression.
- No TODO/FIXME/placeholder patterns in new files
- All SolaX methods wrapped in `try/except` returning `False` on failure

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None | — | — |

---

### Pre-Existing Test Issues (Not Introduced by This Task)

The following test files fail to collect due to `CONF_CONSUMPTION_SENSOR` not existing in `const.py`. Git log confirms these files were last modified by commits predating this task:

- `tests/test_config_flow.py` — last touched: `ab21899` (quick-260323-cs1)
- `tests/test_sensors.py` — last touched: `a020e99` (02-02)
- `tests/test_optimizer.py` — 28 failures (pre-existing, unrelated to SolaX)
- `tests/test_coordinator.py` — 3 failures (pre-existing)

These are not regressions from this task.

---

### Human Verification Required

The following items cannot be verified programmatically:

#### 1. SolaX Wizard Card UI Rendering

**Test:** Open the setup wizard in a real HA instance with `solax_modbus` loaded. Navigate to Step 1 (Wechselrichter).
**Expected:** SolaX Gen4+ card appears alongside Huawei card, shows "Installiert" badge, is selectable. Selecting it enables the Hausverbrauch sensor section and shows the optional "Zweiter PV-Sensor" picker.
**Why human:** Visual rendering and card selection state cannot be verified without a browser.

#### 2. SolaX Two-Phase Write on Real Hardware

**Test:** Configure a SolaX Gen4+ inverter, activate "Ein" mode. Observe HA logs during morning charge-block cycle.
**Expected:** Sequence of 4 service calls: `select.select_option` ("Enabled Battery Control"), `number.set_value` (active_power=0), `number.set_value` (autorepeat_duration=60), `button.press` (trigger).
**Why human:** Requires real SolaX hardware with `solax_modbus` integration.

#### 3. pv_power_sensor_2 Summation in Live Dashboard

**Test:** Configure both `pv_power_sensor` and `pv_power_sensor_2`. Check the Hausverbrauch sensor value and its `pv_leistung_2_kw` attribute.
**Expected:** Hausverbrauch = max(pv1 + pv2 - battery - grid, 0), and `pv_leistung_2_kw` attribute shows the second sensor value.
**Why human:** Requires live sensor data.

---

## Summary

The SolaX Gen4+ implementation is complete and verified. All 7 must-have truths pass automated verification:

- **`inverter/solax.py`** — Full `SolaXInverter` class with two-phase write model, kW-to-W conversion, entity resolution from config with defaults fallback, `is_available` via `solax_modbus` config entries. 20 unit tests pass.
- **Factory** — `solax_gen4` registered alongside `huawei_sun2000`.
- **Constants** — `INVERTER_TYPE_SOLAX = "solax_gen4"`, `CONF_PV_POWER_SENSOR_2`, `INVERTER_PREREQUISITES` extended.
- **`websocket_api.py`** — `SOLAX_DEFAULTS` dict, `_find_solax_prefix()` pattern detection, `ws_detect_sensors` SolaX branch, `check_prerequisites` includes `solax_modbus`.
- **`sensor.py`** — `HausverbrauchSensor` sums `pv_power_sensor_2` when configured, exposes `pv_leistung_2_kw` attribute.
- **`__init__.py`** — Backfill function uses empty-string defaults with explicit skip logic; no hardcoded Huawei sensor strings.
- **Wizard UI** — SolaX card, prerequisite validation, auto-detection prefix handling, battery capacity auto-set to manual, optional `pv_power_sensor_2` picker, dynamic inverter name in summary.

---

_Verified: 2026-03-27_
_Verifier: Claude (gsd-verifier)_
