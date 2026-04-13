---
phase: 260412-t0k
verified: 2026-04-13T18:35:34Z
status: human_needed
score: 13/13
overrides_applied: 0
human_verification:
  - test: "Validate StorCtl_Mod=3 + OutWRte discharge behavior on real Fronius Gen24 hardware"
    expected: "Battery discharges at requested percentage, house consumption absorbs battery output before grid export"
    why_human: "KONZEPT 8.1 -- StorCtl_Mod=3 may force grid discharge bypassing self-consumption. Requires real hardware to confirm behavior. Cannot verify via code inspection alone."
  - test: "Complete Fronius wizard flow in HA panel (select Fronius, enter Modbus IP, detect sensors, test connection)"
    expected: "Panel shows Fronius Gen24 card, accepts Modbus IP/port, detects native Fronius integration sensors, completes setup"
    why_human: "End-to-end UI flow requires running HA instance with Fronius integration loaded"
  - test: "Verify SunSpec Model Discovery on Fronius Gen24 with different firmware versions"
    expected: "Model 124 found at correct register offset regardless of firmware version (1.34.6+)"
    why_human: "Register layout varies by firmware/config, cannot verify without real Modbus connection"
---

# Quick Task 260412-t0k: Fronius Gen24 Inverter Support Verification Report

**Task Goal:** Implement complete Fronius Gen24 inverter support -- backend driver, factory, constants, config migration, WebSocket API, and panel UI
**Verified:** 2026-04-13T18:35:34Z
**Status:** human_needed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | FroniusInverter class implements InverterBase with SunSpec Model 124 Modbus TCP control | VERIFIED | `inverter/fronius.py` line 48: `class FroniusInverter(InverterBase)`, 392 lines, full SunSpec Model 124 register offsets defined |
| 2 | Factory creates FroniusInverter when inverter_type is fronius_gen24 | VERIFIED | `inverter/__init__.py` line 20: `"fronius_gen24": FroniusInverter` in INVERTER_TYPES dict |
| 3 | SunSpec Model Discovery scans from register 40000 to find Model 124 base address | VERIFIED | `fronius.py` line 39: `_SUNSPEC_START = 40000`, lines 104-176: `_discover_model124()` reads SunSpec ID at 40000, iterates model table until Model 124 found |
| 4 | WChaMax is read once and cached for percentage calculations | VERIFIED | `fronius.py` lines 186-208: `_read_wchamax()` caches by `date.today().isoformat()`, returns cached value when `_wchamax_date == today` |
| 5 | Charge blocking sets StorCtl_Mod=1, InWRte=0 | VERIFIED | `fronius.py` line 269: `_write_register(_OFFSET_STORCTL_MOD, 1)`, line 274: `_write_register(_OFFSET_INWRTE, 0)` |
| 6 | Discharge sets StorCtl_Mod=3, OutWRte=percent, InWRte=0 | VERIFIED | `fronius.py` line 320: `_write_register(_OFFSET_STORCTL_MOD, 3)`, line 325: `_write_register(_OFFSET_INWRTE, 0)`, line 329: `_write_register(_OFFSET_OUTWRTE, percent)` |
| 7 | Stop forcible restores StorCtl_Mod=0, InWRte=10000, OutWRte=10000 | VERIFIED | `fronius.py` line 361: `_write_register(_OFFSET_STORCTL_MOD, 0)`, line 365: `_write_register(_OFFSET_INWRTE, _RATE_100_PERCENT)`, line 369: `_write_register(_OFFSET_OUTWRTE, _RATE_100_PERCENT)` where `_RATE_100_PERCENT = 10000` |
| 8 | Config migration bumps version to 11 with Fronius defaults | VERIFIED | `__init__.py` line 367: `if entry.version < 11:` block, `config_flow.py` line 25: `VERSION = 11` |
| 9 | WebSocket prerequisite check includes fronius domain | VERIFIED | `websocket_api.py` line 331: `check_domains` list includes `"fronius"` |
| 10 | WebSocket detect_sensors handles Fronius native integration entities | VERIFIED | `websocket_api.py` lines 108-114: `FRONIUS_SENSOR_SUFFIXES` mapping, lines 472-498: Fronius detection block with suffix scanning and entity name heuristics |
| 11 | Panel wizard shows Fronius Gen24 card with Modbus IP/Port config | VERIFIED | `eeg-optimizer-panel.js` line 2124: Fronius Gen24 card definition with HA brand logo, lines 2191-2199: Modbus IP input field + port input field |
| 12 | Panel has Fronius instruction dialog for Modbus TCP setup | VERIFIED | `eeg-optimizer-panel.js` lines 489-548: Full Fronius dialog content with Fronius Integration setup, Modbus TCP activation, firmware requirements, troubleshooting table |
| 13 | Fronius instruction dialog warns that inverter retains Modbus settings after optimizer crash (no auto-revert) | VERIFIED | `eeg-optimizer-panel.js` line 518: Warning box stating "Der Wechselrichter behaelt Modbus-Einstellungen (z.B. Lade-/Entladesperre) auch nach einem Absturz oder Neustart des Optimizers bei" |

**Score:** 13/13 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `inverter/fronius.py` | FroniusInverter class with pymodbus SunSpec Model 124 control | VERIFIED | 392 lines, complete implementation with connection retry, Model Discovery, WChaMax cache, all 3 control methods, disconnect cleanup |
| `inverter/__init__.py` | Factory with fronius_gen24 type | VERIFIED | Contains `"fronius_gen24": FroniusInverter` at line 20, import at line 11 |
| `const.py` | INVERTER_TYPE_FRONIUS, FRONIUS constants, sign conventions | VERIFIED | `INVERTER_TYPE_FRONIUS = "fronius_gen24"` (line 17), `INVERTER_PREREQUISITES` with `fronius_gen24: None` (line 23), `INVERTER_SIGN_CONVENTIONS` with fronius entry (line 35), `CONF_FRONIUS_MODBUS_HOST/PORT` (lines 38-40) |
| `manifest.json` | pymodbus requirement | VERIFIED | `"requirements": ["pymodbus>=3.6.0"]` (line 8), `"fronius"` in after_dependencies (line 9) |
| `__init__.py` | Config migration v11 for Fronius | VERIFIED | `if entry.version < 11:` block at line 367, no-op migration for Fronius fields |
| `websocket_api.py` | Fronius prerequisites + sensor auto-detect | VERIFIED | `INVERTER_TYPE_FRONIUS` imported (line 26), `FRONIUS_SENSOR_SUFFIXES` defined (lines 108-114), prerequisite check includes `"fronius"` (line 331), detect_sensors handles Fronius (lines 472-498) |
| `eeg-optimizer-panel.js` | Fronius wizard card, Modbus config, instruction dialog | VERIFIED | Fronius card at line 2124, Modbus IP/port inputs at lines 2191-2199, full instruction dialog at lines 489-548, validation at lines 1185-1190 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `inverter/fronius.py` | `inverter/base.py` | `class FroniusInverter(InverterBase)` | WIRED | Line 48: `class FroniusInverter(InverterBase)`, line 22: `from .base import InverterBase` |
| `inverter/__init__.py` | `inverter/fronius.py` | INVERTER_TYPES dict import | WIRED | Line 11: `from .fronius import FroniusInverter`, line 20: `"fronius_gen24": FroniusInverter` |
| `websocket_api.py` | `const.py` | INVERTER_TYPE_FRONIUS import | WIRED | Line 26: `INVERTER_TYPE_FRONIUS` imported, line 493: used in detect_sensors result |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `inverter/fronius.py` | 293 | TODO: KONZEPT 8.1 -- StorCtl_Mod=3 grid discharge behavior | Info | Known open question, documented in plan. Does not block implementation; needs hardware validation. |

### Human Verification Required

### 1. StorCtl_Mod=3 Discharge Behavior (KONZEPT 8.1)

**Test:** On a real Fronius Gen24 with BYD battery, trigger discharge via the optimizer and observe whether battery output is consumed by the house first or forced to grid.
**Expected:** Battery discharges at the requested percentage rate; house consumption absorbs battery output before any grid export occurs.
**Why human:** This is a hardware behavior question -- StorCtl_Mod=3 (Charge+Discharge Limit active) might bypass self-consumption logic. The code correctly writes the registers as designed, but real-world behavior depends on inverter firmware interpretation.

### 2. End-to-End Panel Wizard Flow

**Test:** In a running HA instance with the Fronius native integration loaded, open the EEG Optimizer panel, go through the wizard: select Fronius Gen24, enter Modbus IP/port, verify sensor auto-detection, run inverter connection test.
**Expected:** Fronius Gen24 card appears with brand logo and detection badge. Modbus IP/port fields appear. Sensors are auto-detected from Fronius integration entities. Connection test succeeds.
**Why human:** Requires a running HA instance with the Fronius integration and actual inverter hardware on the network.

### 3. SunSpec Model Discovery Across Firmware Versions

**Test:** Run the optimizer against Fronius Gen24 inverters with different firmware versions (minimum 1.34.6-1, recommended 1.40.0+).
**Expected:** SunSpec Model 124 is discovered at the correct register address regardless of firmware version.
**Why human:** SunSpec model table layout varies by firmware and configuration. Code handles this generically via scanning, but edge cases can only be caught on real hardware.

### Gaps Summary

No code-level gaps found. All 13 must-have truths are verified in the codebase. All 7 artifacts exist, are substantive, and are properly wired. All 3 key links are connected.

The only items requiring attention are hardware-dependent behaviors that cannot be verified through code inspection:
- KONZEPT 8.1 discharge behavior (StorCtl_Mod=3)
- End-to-end panel wizard flow on real HA
- SunSpec Model Discovery compatibility across firmware versions

---

_Verified: 2026-04-13T18:35:34Z_
_Verifier: Claude (gsd-verifier)_
