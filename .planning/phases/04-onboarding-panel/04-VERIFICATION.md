---
phase: 04-onboarding-panel
verified: 2026-03-22T22:00:00Z
status: gaps_found
score: 18/21 must-haves verified
re_verification: false
gaps:
  - truth: "Panel appears as 'EEG Optimizer' with mdi:solar-power icon in HA sidebar after integration setup"
    status: failed
    reason: "Panel icon changed from mdi:solar-power (per plan) to mdi:battery-charging-high in __init__.py line 26"
    artifacts:
      - path: "custom_components/eeg_energy_optimizer/__init__.py"
        issue: "PANEL_ICON = 'mdi:battery-charging-high' instead of 'mdi:solar-power'"
    missing:
      - "Change PANEL_ICON back to 'mdi:solar-power' or update plan to accept new icon"

  - truth: "Existing VERSION 3 entries migrate to VERSION 4 with setup_complete=false"
    status: partial
    reason: "Migration v3->v4 exists and is correct. However config_flow.py VERSION is now 5 (not 4), and migration also includes a v4->v5 block. The v3->v4 migration path works but this truth is partially superseded — new entries are created at VERSION 5. The v3->v4->v5 chain is intact."
    artifacts:
      - path: "custom_components/eeg_energy_optimizer/config_flow.py"
        issue: "VERSION = 5 (plan 01 acceptance criteria required VERSION = 4; plan 02 bumped it to 5 as a deviation)"
    missing:
      - "No code fix needed — v5 migration is intentional from plan 02. Accept VERSION=5 and update must_have truth."

  - truth: "Wizard step 2 checks if Huawei Solar integration is installed and blocks with guidance when missing"
    status: partial
    reason: "Plan 02 specified wizard step 2 as Wechselrichter (Huawei Solar check). Actual implementation reordered: step 1=Wechselrichter, step 2=Prognose-Integration. Huawei Solar prerequisite check exists in step 1, not step 2 as stated in the truth. Functionality is correct but step numbering differs."
    artifacts:
      - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
        issue: "Step numbering changed: Wechselrichter is step 1 (index), Prognose is step 2. Plan 02 truth referenced step 2 for Huawei check."
    missing:
      - "No code fix needed — wizard is functionally correct. Update truth to reflect actual step order."
human_verification:
  - test: "Verify panel icon in HA sidebar"
    expected: "EEG Optimizer appears in sidebar with the correct icon"
    why_human: "Cannot verify visual rendering of sidebar icons programmatically"
  - test: "Complete full wizard flow (all 8 steps) and verify config saves"
    expected: "After clicking Fertig on step 8 (Zusammenfassung), config is persisted and dashboard appears"
    why_human: "WebSocket save_config call requires live HA instance to confirm round-trip"
  - test: "Verify dashboard live updates when optimizer mode changes"
    expected: "Changing select.eeg_energy_optimizer_optimizer in HA dev tools updates badge in dashboard without page refresh"
    why_human: "Reactive rendering requires live browser and HA"
  - test: "Verify SVG charts render with data"
    expected: "7-day bar chart and hourly line chart display actual data with correct labels and axes"
    why_human: "Chart rendering requires live sensor data"
---

# Phase 4: Onboarding Panel Verification Report

**Phase Goal:** Permanent HA sidebar panel with dashboard (live optimizer status, forecasts, charts) and setup wizard (8-step guided configuration replacing the config flow), plus 1-click config flow and WebSocket API
**Verified:** 2026-03-22T22:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

#### From Plan 04-01 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Panel appears as 'EEG Optimizer' with mdi:solar-power icon in HA sidebar | FAILED | PANEL_ICON = "mdi:battery-charging-high" in `__init__.py` line 26 |
| 2 | WebSocket command eeg_optimizer/get_config returns current config entry data | VERIFIED | `websocket_api.py` lines 66-85: handler exists, reads entry.data + entry.options |
| 3 | WebSocket command eeg_optimizer/save_config updates config entry | VERIFIED | `websocket_api.py` lines 88-109: merges msg["config"] into entry.data |
| 4 | WebSocket command eeg_optimizer/check_prerequisites returns installed status | VERIFIED | `websocket_api.py` lines 112-132: checks huawei_solar, solcast_solar, forecast_solar |
| 5 | WebSocket command eeg_optimizer/detect_sensors returns auto-detected Huawei sensor entity IDs | VERIFIED | `websocket_api.py` lines 135-173: uses HUAWEI_DEFAULTS + state check |
| 6 | Config flow is a single-click step that creates the entry with defaults | VERIFIED | `config_flow.py`: single async_step_user creating entry with {"setup_complete": False} |
| 7 | Existing VERSION 3 entries migrate to VERSION 4 with setup_complete=false | PARTIAL | Migration chain v3->v4->v5 exists in __init__.py. v4 block adds setup_complete=False correctly. VERSION now 5 (intentional plan 02 deviation). |

#### From Plan 04-02 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 8 | User can navigate through all 8 wizard steps with forward/back buttons | VERIFIED | `_renderWizard()` at line 801, WIZARD_STEPS array with 8 entries, Weiter/Zurück/Fertig buttons |
| 9 | Wizard step 2 checks if Huawei Solar integration is installed and blocks with guidance when missing | PARTIAL | Check exists in step 1 (_renderStep1), not step 2. Steps were renumbered (plan deviation). Functionality present. |
| 10 | Wizard step 3 checks if Solcast or Forecast.Solar is installed and blocks with guidance when missing | VERIFIED | `_renderStep2()` at line 945 checks prerequisites, shows blocking message, "Erneut prüfen" button |
| 11 | Wizard step 4 auto-detects Huawei sensors and pre-fills entity pickers with confirmation prompt | VERIFIED | `_renderStep3()` calls detect_sensors, shows green card when detected, pre-fills pickers |
| 12 | Wizard step 5 pre-selects forecast entities based on chosen source | VERIFIED | `_renderStep2()` (step index 2) handles forecast source + auto-suggests entities |
| 13 | Wizard step 8 shows summary of all settings and saves config via WebSocket on completion | VERIFIED | `_renderStep7()` at line 1211, `_finishWizard()` at line 447 calls eeg_optimizer/save_config |
| 14 | Wizard progress is saved to localStorage and restorable after page reload | VERIFIED | `_saveWizardProgress()` / `_loadWizardProgress()` at lines 479-508 with 24h expiry |
| 15 | After wizard completion, setup_complete is set to true and dashboard view activates | VERIFIED | `_finishWizard()` line 452: `this._wizardData.setup_complete = true`, switches view to "dashboard" |

#### From Plan 04-03 Must-Haves

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 16 | Dashboard shows current optimizer status (Morgen-Einspeisung/Normal/Abend-Entladung/Test/Aus) | VERIFIED | `_renderDashboard()` line 1393 reads entscheidung sensor, colored badges for each state |
| 17 | Dashboard shows Energiebedarf (replaces Überschuss-Faktor per deviation) and whether today is a surplus day | VERIFIED | Line 1410: reads energiebedarf_kwh attribute, displayed as "X.X kWh" |
| 18 | Dashboard shows next planned action from decision sensor | VERIFIED | Line 1409: reads naechste_aktion attribute, displayed in status card |
| 19 | Dashboard shows current battery SOC | VERIFIED | Lines 1414-1416: reads from config.battery_soc_sensor, color-coded |
| 20 | Dashboard shows PV forecast for today and tomorrow | VERIFIED | Lines 1419-1423: reads pv_prognose_heute and pv_prognose_morgen |
| 21 | Dashboard shows 7-day consumption forecast as bar chart | VERIFIED | `_renderBarChart()` at line 1323, reads tagesverbrauchsprognose_heute through _tag_6 |
| 22 | Dashboard shows hourly consumption profile as line chart | VERIFIED | `_renderLineChart()` at line 1353, reads verbrauchsprofil sensor {day}_watts attributes |
| 23 | Dashboard updates live via hass property without manual refresh | VERIFIED | `set hass(hass)` at line 618: selective re-render when WATCHED entities change |

**Score:** 18/21 truths verified (2 partial = counted as failed for scoring, 1 minor icon discrepancy)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `custom_components/eeg_energy_optimizer/websocket_api.py` | WebSocket command handlers | VERIFIED | 232 lines, 5 commands registered (includes bonus test_inverter) |
| `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` | Panel shell + wizard + dashboard | VERIFIED | 1827 lines, fully implemented |
| `custom_components/eeg_energy_optimizer/__init__.py` | Panel registration + WS setup | VERIFIED | Panel registered, WS commands wired, migration chain complete |
| `custom_components/eeg_energy_optimizer/config_flow.py` | Minimal 1-click config flow | VERIFIED | VERSION=5, single async_step_user only |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `__init__.py` | `websocket_api.py` | `async_register_websocket_commands(hass)` | WIRED | Line 73: called before platform forwarding |
| `__init__.py` | `frontend/eeg-optimizer-panel.js` | `async_register_built_in_panel` with js_url | WIRED | Lines 81-96: panel registered with correct js_url path |
| `eeg-optimizer-panel.js` | `websocket_api.py ws_get_config` | `hass.callWS({type: 'eeg_optimizer/get_config'})` | WIRED | Line 665: called in `_loadConfig()` on first hass set |
| `eeg-optimizer-panel.js` | `websocket_api.py ws_save_config` | `hass.callWS({type: 'eeg_optimizer/save_config'})` | WIRED | Line 454: called in `_finishWizard()` |
| `eeg-optimizer-panel.js` | `websocket_api.py ws_check_prerequisites` | `hass.callWS({type: 'eeg_optimizer/check_prerequisites'})` | WIRED | Line 518: called in `_checkPrerequisites()` |
| `eeg-optimizer-panel.js` | `websocket_api.py ws_detect_sensors` | `hass.callWS({type: 'eeg_optimizer/detect_sensors'})` | WIRED | Line 576: called in `_detectSensors()` |
| `eeg-optimizer-panel.js dashboard` | `sensor.eeg_energy_optimizer_entscheidung` | `hass.states[]` access in `_renderDashboard` | WIRED | Line 1402: `_readState("sensor.eeg_energy_optimizer_entscheidung")` |
| `eeg-optimizer-panel.js dashboard` | `select.eeg_energy_optimizer_optimizer` | `hass.states[]` access for optimizer mode | WIRED | Line 1398: `_readState("select.eeg_energy_optimizer_optimizer")` |
| `eeg-optimizer-panel.js charts` | `sensor.eeg_energy_optimizer_verbrauchsprofil` | `hass.states[]` attributes for hourly data | WIRED | Line 1450: reads verbrauchsprofil attributes |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| INF-04 | 04-01, 04-02, 04-03 | Onboarding Panel — HA Sidebar Panel with Step-by-Step Setup-Wizard, prerequisite checking, sensor mapping | SATISFIED | Panel registered, 8-step wizard with prerequisite checks and sensor mapping fully implemented |

No orphaned requirements — INF-04 is the only requirement mapped to Phase 4, and all three plans claim it.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `__init__.py` | 26 | `PANEL_ICON = "mdi:battery-charging-high"` instead of `mdi:solar-power` | Warning | Sidebar icon differs from plan spec; cosmetic only |
| `config_flow.py` | 24 | `VERSION = 5` — plan 01 acceptance criteria required VERSION = 4 | Info | Intentional: plan 02 bumped to v5 to add feature flags |
| `eeg-optimizer-panel.js` | 1587 | "Die Einrichtung wurde noch nicht abgeschlossen" — plan 01 specified "Setup noch nicht abgeschlossen" | Info | Text change; German phrasing improved but slightly different from spec |

No stub patterns found. No TODO/FIXME/placeholder comments in critical paths. No empty implementations.

### Human Verification Required

#### 1. Panel Icon in Sidebar

**Test:** After installing the integration, look at the HA sidebar entry for "EEG Optimizer"
**Expected:** Icon should match design intent (plan specified mdi:solar-power; code has mdi:battery-charging-high)
**Why human:** Visual rendering cannot be verified programmatically

#### 2. Complete Wizard Flow End-to-End

**Test:** Open panel, click "Einrichtung starten", navigate all 8 steps, fill in real sensors, click "Fertig"
**Expected:** Config saves successfully, panel switches to dashboard view, gear icon appears
**Why human:** Requires live HA instance with WebSocket connection

#### 3. Dashboard Live Updates

**Test:** Change `select.eeg_energy_optimizer_optimizer` in HA developer tools
**Expected:** Dashboard status badge updates immediately without page reload
**Why human:** Reactive rendering requires live browser session

#### 4. SVG Charts with Real Data

**Test:** Complete wizard, view dashboard, verify chart sections show bars and lines
**Expected:** 7-day bar chart shows daily forecast values; hourly line chart shows current weekday profile
**Why human:** Chart correctness requires live sensor data from optimizer

### Gaps Summary

There are 3 issues:

1. **Icon mismatch (Warning):** `PANEL_ICON` in `__init__.py` is `mdi:battery-charging-high` instead of `mdi:solar-power` as required by plan 01 acceptance criteria and the INF-04 must_have truth. This is cosmetic but fails a documented plan acceptance criterion.

2. **VERSION divergence (Info):** Plan 01 set `VERSION = 4` and the acceptance criteria verified `VERSION = 4`. Plan 02 bumped it to 5 as a documented deviation (adding feature flags `enable_morning_delay`, `enable_night_discharge`). This is intentional and the migration chain is complete. The v3->v4->v5 path in `async_migrate_entry` is correctly implemented.

3. **Wizard step number mismatch (Partial):** Plan 02 truths referenced step 2 for Huawei Solar check and step 3 for forecast check. Actual implementation reorganized the steps (Wechselrichter is now step index 1, Prognose is step index 2). Both checks exist and are fully functional — the truth was about functionality, not step numbers. This is a documentation/truth-vs-reality gap, not a functional gap.

**Root cause of icon gap:** The plan specified `mdi:solar-power` but the implementation chose `mdi:battery-charging-high`. This is either a deliberate UX choice (battery charging better represents the optimizer's core action) or an oversight. A one-line fix resolves it if the original icon is required.

---

_Verified: 2026-03-22T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
