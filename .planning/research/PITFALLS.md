# Domain Pitfalls

**Domain:** Home Assistant custom integration with custom panel, abstract inverter battery control, HACS distribution
**Researched:** 2026-03-20

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or bricked battery systems.

### Pitfall 1: Inverter Abstraction That Leaks Hardware Semantics

**What goes wrong:** The abstract inverter interface maps poorly onto actual hardware capabilities. Huawei uses TOU period scheduling and working mode switches (Maximize Self Consumption vs Time-of-Use). Fronius uses direct Modbus register writes (HYB_EM_MODE, HYB_EM_POWER with negative watts for discharge). These are fundamentally different control paradigms -- one is declarative (set schedule), the other is imperative (set power now).

**Why it happens:** Designing the abstraction from the first inverter (Huawei) bakes in that inverter's mental model. When Fronius arrives, the interface either cannot express Fronius's capabilities or requires awkward adapters that defeat the abstraction's purpose.

**Consequences:** Either a rewrite of the interface when the second inverter is added, or a leaky abstraction where "set discharge power" means different things per backend (Huawei ignores the power parameter because it uses TOU schedules; Fronius needs an exact watt value).

**Prevention:**
- Study both Huawei and Fronius control APIs before designing the interface. The existing integration's `fronius_api.py` already demonstrates the Fronius imperative model.
- Design the abstraction around optimizer *intents* (e.g., "discharge at X kW until SOC Y%", "stop discharge", "allow grid charge") rather than hardware operations.
- Include a `capabilities` property per inverter backend so the optimizer can query what the inverter actually supports (e.g., `supports_power_target`, `supports_tou_schedule`, `supports_grid_charge`).
- Validate the interface design by writing both Huawei and Fronius backends as stubs before committing to the interface.

**Detection:** If the interface has methods like `set_tou_period()` or parameters that only one inverter uses, the abstraction is already leaking.

**Phase:** Must be addressed in the architecture/design phase before any inverter code is written. Retrofitting an abstraction is a rewrite.

**Confidence:** HIGH -- this pattern is well-documented in the existing codebase (Fronius-specific `fronius_api.py`) and the HSEM project's Huawei-specific TOU approach.

---

### Pitfall 2: Service Call Timing and State Propagation Delays

**What goes wrong:** The optimizer sends a service call to change battery mode (e.g., `huawei_solar.forcible_discharge_soc`), then reads the SOC sensor in the next 60-second cycle assuming the command took effect. But inverter state changes propagate with 30-120 second delays through the Modbus polling chain: optimizer calls service -> Huawei Solar integration writes register -> inverter processes command -> next Modbus poll reads new state -> HA entity updates.

**Why it happens:** The optimizer treats service calls as synchronous operations when they are actually fire-and-forget. The Huawei Solar integration polls Modbus registers on its own interval (typically 30s), so there is an inherent delay between "command sent" and "state reflects command."

**Consequences:** The optimizer oscillates -- it sends "discharge," reads stale state showing "not discharging," sends "discharge" again. In the worst case, rapid contradictory commands confuse the inverter firmware or trigger safety lockouts. The existing Fronius integration already shows this problem: the optimizer writes einspeisewert *before* the einspeisung switch specifically to avoid a race condition (lines 1133-1150 of optimizer.py).

**Prevention:**
- Track "pending commands" with expected state and a cooldown timer. After sending a discharge command, wait at least 2 polling intervals before re-evaluating.
- Use the inverter backend's `capabilities` to expose its polling interval, and size the cooldown accordingly.
- Never re-send a command if the previous identical command is still within its cooldown window.
- Log a warning if the state has not converged after 3x the expected delay (indicates a real failure vs. propagation delay).

**Detection:** Watch for log spam where the same service call repeats every cycle. Watch for inverter state toggling rapidly between two modes.

**Phase:** Core optimizer loop design (Phase 1-2). The 60-second cycle timer must account for command latency from the start.

**Confidence:** HIGH -- the existing integration explicitly handles ordering (einspeisewert before switch), confirming this is a known issue.

---

### Pitfall 3: HA Startup Race -- Sensors Unavailable When Optimizer Runs

**What goes wrong:** The optimizer runs its first cycle 10 seconds after setup (line 49 of `__init__.py`), but dependent integrations (Solcast, Huawei Solar, sun.sun) may not have loaded their entities yet. All `_get_float()` calls return 0.0 for unavailable sensors, which the optimizer treats as valid data. This means: battery SOC "0%" triggers critical guards, PV forecast "0 kWh" selects ENGPASS strategy, and the optimizer executes safety overrides on perfectly healthy hardware.

**Why it happens:** Home Assistant loads integrations in dependency order, but `after_dependencies` (like Solcast) are not guaranteed to be fully initialized when the depending integration starts. The 10-second delay in the existing code is a heuristic, not a guarantee.

**Consequences:** On every HA restart, the optimizer briefly takes incorrect actions (stops feed-in, forces battery charging) until real sensor data arrives. For a battery optimization integration, this means unnecessary grid draw or missed EEG feed-in windows after every restart.

**Prevention:**
- Distinguish between "sensor reports 0" and "sensor unavailable/unknown." The `_get_float()` helper already checks for "unknown"/"unavailable" but returns 0.0 -- it should return `None` and the optimizer should treat `None` as "data not ready."
- Add a "warming up" state: suppress all execution (not just calculation) until all critical sensors have reported at least one valid value.
- Use HA's `async_track_state_change_event` to detect when critical sensors first become available, rather than relying on a fixed delay.
- Display a clear "Warming up -- waiting for sensors" message in the decision sensor.

**Detection:** Check the decision sensor immediately after HA restart. If it shows "Sicherheit" or "Engpass" for the first 30-60 seconds before switching to a normal strategy, this pitfall is active.

**Phase:** Core optimizer loop (Phase 1). Must be in the initial implementation -- retrofitting "warming up" logic into an already-executing optimizer is error-prone.

**Confidence:** HIGH -- the existing integration already uses a 10-second delay hack (line 49), indicating this is a known problem.

---

### Pitfall 4: Custom Panel JavaScript Not Updating After HACS Upgrades

**What goes wrong:** Users install an update via HACS, but the onboarding panel still shows the old version. Browsers aggressively cache JavaScript modules. Since HA serves custom panel files from `/local/` or a registered static path, there is no cache-busting mechanism unless explicitly implemented.

**Why it happens:** HA's built-in frontend uses hashed filenames for cache busting. Custom panels served via `module_url` do not get this treatment. The URL stays the same across versions, so the browser serves the cached copy.

**Consequences:** Users report bugs that were already fixed. Worse, if the Python backend changes its WebSocket API but the cached frontend still sends old-format messages, the panel silently breaks.

**Prevention:**
- Append a version query parameter to `module_url` during panel registration: `/local/eeg_optimizer/panel.js?v=1.2.0`. Read the version from `manifest.json` at registration time.
- Document "hard refresh" (Ctrl+Shift+R) in troubleshooting.
- Consider using a hash of the JS file content as the query parameter for automatic cache busting.

**Detection:** After an update, open browser dev tools Network tab and check if the panel JS returns 304 (cached) or 200 (fresh).

**Phase:** Panel implementation phase. Must be designed in from the start -- adding cache busting later means existing users are stuck on old caches.

**Confidence:** MEDIUM -- based on general web development patterns and HA community reports of stale frontend resources.

---

### Pitfall 5: HACS Repository Structure When Extracting from Monorepo

**What goes wrong:** The project starts development in the existing HomeAssistant repo alongside the private Energieoptimierung integration (PROJECT.md: "Will be developed in this repo initially, then moved to its own repo before HACS publication"). During extraction, files end up in the wrong structure, or git history references are lost, or the existing integration's files accidentally get included.

**Why it happens:** HACS requires exactly one subdirectory under `custom_components/`. The source repo has `custom_components/energieoptimierung/` (existing) and will have `custom_components/eeg_optimizer/` (new). When extracting to a standalone repo, it is easy to accidentally include both, or to forget required files like `hacs.json`, `brand/icon.png`, or proper `manifest.json` fields.

**Consequences:** HACS shows "Repository structure not compliant" error. Users cannot install. If the existing integration's `__pycache__` or config files leak into the published repo, it looks unprofessional and may expose private configuration.

**Prevention:**
- Create the HACS-compliant structure from day one, even in the monorepo. Have `custom_components/eeg_optimizer/` with its own `manifest.json` containing all required fields (`domain`, `documentation`, `issue_tracker`, `codeowners`, `name`, `version`).
- Create `hacs.json` and `brand/icon.png` early. HACS now requires brand assets.
- Use a `.gitignore` that excludes `__pycache__/`, `.env`, and any credentials files.
- Before extraction, run the HACS validation action (`hacs/action@main`) against the planned repo structure.
- Script the extraction: `git filter-repo` or `git subtree split` to cleanly extract only `custom_components/eeg_optimizer/` and root-level files.

**Detection:** Run `hacs/action` in CI before publishing. Check that `custom_components/` contains exactly one subdirectory.

**Phase:** Should be set up in the project scaffolding phase (Phase 1). Do not defer to "later."

**Confidence:** HIGH -- HACS documentation explicitly states the single-integration requirement, and the PROJECT.md already calls out the extraction plan.

## Moderate Pitfalls

### Pitfall 6: Hardcoded Entity IDs Instead of User-Selected Sensors

**What goes wrong:** The existing integration hardcodes entity IDs like `sensor.solarnet_leistung_verbrauch` as defaults, which only work for the developer's specific setup. The new integration must let users select their sensors during onboarding, but if sensor selection is incomplete or allows invalid entity types, the optimizer silently reads wrong data.

**Prevention:**
- Validate entity domains during sensor selection (e.g., ensure battery SOC is a `sensor.*` entity, not an `input_number.*`).
- Show the entity's current value and unit during selection so users can verify they picked the right one.
- Store sensor selections in config entry data, not hardcoded constants.
- Provide a "test reading" step in onboarding that reads all selected sensors and displays their values.

**Detection:** If any sensor returns `None` or implausible values (SOC > 100%, negative power) consistently, the mapping is wrong.

**Phase:** Onboarding panel (Phase 2-3). The sensor mapping UX is the most important part of the panel.

**Confidence:** HIGH -- the existing integration's `const.py` is entirely hardcoded defaults.

---

### Pitfall 7: Custom Panel WebSocket API Versioning

**What goes wrong:** The onboarding panel communicates with the Python backend via WebSocket. As the integration evolves, the WebSocket message format changes. Old panel versions (cached or not updated) send messages the new backend does not understand, or vice versa.

**Prevention:**
- Version the WebSocket API from day one: include a `version` field in every message.
- Backend should reject messages from incompatible panel versions with a clear error message telling the user to refresh.
- Keep WebSocket API changes backward-compatible within a major version where possible.

**Detection:** Backend logs show "unknown message type" or panel shows "connection error" after an update.

**Phase:** Panel + backend communication design (Phase 2-3).

**Confidence:** MEDIUM -- standard API versioning concern, not specific to HA.

---

### Pitfall 8: HA Core Breaking Changes Breaking Custom Integration on Update

**What goes wrong:** Home Assistant deprecates APIs on a regular cadence. Recent examples: `async_forward_entry_setup` removed in 2025.6 (must use `async_forward_entry_setups`), `ConfigEntry` option flow changes in 2025.12, `DEVICE_CLASS_*` constants renamed. Each HA update risks breaking the integration.

**Prevention:**
- Follow the HA developer blog for deprecation announcements.
- Use the latest HA APIs from the start (`async_forward_entry_setups`, not the singular version -- the existing integration already does this correctly).
- Set a `homeassistant` minimum version in `manifest.json` to prevent installation on unsupported versions.
- Set up the `hassfest` and `hacs/action` GitHub Actions for CI to catch deprecation warnings early.
- Avoid using internal/private HA APIs (anything with `_` prefix).

**Detection:** Integration fails to load after HA update. Check HA logs for deprecation warnings.

**Phase:** CI/CD setup (Phase 1). Run `hassfest` from the first commit.

**Confidence:** HIGH -- documented deprecation cycles with concrete examples.

---

### Pitfall 9: Forecast Source Abstraction Mismatch (Solcast vs Forecast.Solar)

**What goes wrong:** Solcast and Forecast.Solar expose different data shapes. Solcast provides remaining today + tomorrow as separate sensors with kWh values. Forecast.Solar provides hourly forecasts as an attribute list. If the forecast abstraction assumes Solcast's model, Forecast.Solar support requires awkward transformations or loses hourly granularity.

**Prevention:**
- Define the forecast interface as "remaining kWh today" and "expected kWh tomorrow" -- both sources can provide these.
- Do not expose hourly forecast data through the abstraction initially; stick to daily aggregates that both sources support.
- Allow configuration of which forecast entity maps to "remaining today" and "tomorrow" so users can point to any sensor.

**Detection:** Forecast.Solar users report consistently wrong strategy selection (always ENGPASS or always UEBERSCHUSS).

**Phase:** Forecast integration (Phase 2). Design the abstraction before implementing the first forecast source.

**Confidence:** MEDIUM -- based on examining Solcast sensor naming and known Forecast.Solar entity structure.

---

### Pitfall 10: Onboarding Panel Assumes Prerequisite Integrations Are Installed

**What goes wrong:** The onboarding panel checks for prerequisites (Solcast, Huawei Solar) but cannot distinguish between "not installed," "installed but not configured," and "installed, configured, but entities not yet loaded." Users see false negatives ("Solcast not found") when Solcast is actually installed but still initializing.

**Prevention:**
- Check for integration presence via `hass.config_entries.async_entries("solcast_solar")` (config entries exist) rather than entity existence (which depends on initialization order).
- Show three states: "Not installed," "Installed but not configured," and "Ready" with specific guidance for each.
- Allow users to proceed past prerequisite checks with a warning, since the user may install prerequisites after initial setup.

**Detection:** Users report the onboarding panel says prerequisites are missing when they are not.

**Phase:** Onboarding panel (Phase 2-3).

**Confidence:** MEDIUM -- based on HA startup race condition patterns.

## Minor Pitfalls

### Pitfall 11: German-Only UI Strings Limiting HACS Adoption

**What goes wrong:** The existing integration uses German everywhere (strategy names, sensor names, decision reasoning). For HACS distribution to the broader DACH community this is fine initially, but HACS default repository inclusion expects English as fallback, and non-German speakers cannot use the integration.

**Prevention:**
- Use HA's `strings.json` / `translations/` system from the start. German in `translations/de.json`, English in `strings.json`.
- Keep strategy names and sensor keys in English internally; use translations only for display.

**Detection:** HACS default repository review rejects the integration for missing English translations.

**Phase:** Initial scaffolding. Translation structure is hard to retrofit.

**Confidence:** HIGH -- HACS inclusion requirements documented.

---

### Pitfall 12: manifest.json Missing Required Fields for HACS

**What goes wrong:** The manifest.json is missing `version`, `issue_tracker`, or `codeowners`, causing HACS validation to fail.

**Prevention:**
- Start with all required fields: `domain`, `name`, `version` (semver), `documentation`, `issue_tracker`, `codeowners`, `dependencies`, `requirements`.
- Use CalVer or SemVer for version -- HACS validates this via AwesomeVersion.
- Include `"frontend"` and `"panel_custom"` in `dependencies` if registering a custom panel.

**Detection:** `hacs/action` CI validation catches this immediately.

**Phase:** Project scaffolding (Phase 1).

**Confidence:** HIGH -- HACS documentation is explicit about requirements.

---

### Pitfall 13: Panel webcomponent_name Mismatch

**What goes wrong:** The `webcomponent_name` passed to `async_register_panel()` does not match the `customElements.define()` call in the JavaScript file. The panel registers successfully but renders a blank page.

**Prevention:**
- Use a single constant for the component name in both Python and JS.
- Test panel loading in the browser console: `document.createElement('eeg-optimizer-panel')` should return your element, not an HTMLUnknownElement.

**Detection:** Panel URL loads but shows blank white page. Browser console shows no errors (the element just never renders).

**Phase:** Panel implementation (Phase 2-3).

**Confidence:** HIGH -- explicitly documented in community guides.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Abstract inverter interface design | #1: Leaking hardware semantics | Design from intents, not hardware. Stub both Huawei and Fronius before committing. |
| Core optimizer loop | #2: Service call timing, #3: Startup race | Command cooldowns, warming-up state, None vs 0 distinction |
| Onboarding panel | #4: JS caching, #7: WS versioning, #10: Prerequisite detection, #13: Name mismatch | Version query params, API versioning, config entry checks |
| Sensor mapping | #6: Hardcoded entity IDs | Validation during selection, test reading step |
| HACS publication | #5: Repo structure, #8: HA breaking changes, #11: German-only, #12: Missing manifest fields | HACS-compliant structure from day one, CI validation, translations |
| Forecast integration | #9: Solcast vs Forecast.Solar mismatch | Abstract to daily aggregates, user-configurable entity mapping |

## Sources

- [Home Assistant Custom Panels Documentation](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/)
- [HACS Integration Publishing Requirements](https://hacs.xyz/docs/publish/integration/)
- [Community Guide: Adding Sidebar Panel to Integration](https://community.home-assistant.io/t/how-to-add-a-sidebar-panel-to-a-home-assistant-integration/981585)
- [Huawei Solar Force Charge/Discharge Wiki](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery)
- [HSEM: Huawei Solar Energy Management](https://github.com/woopstar/hsem)
- [HA Developer Blog - Breaking Changes](https://developers.home-assistant.io/blog/)
- [Home Assistant Config Flow Documentation](https://developers.home-assistant.io/docs/config_entries_config_flow_handler/)
- [HA Integration Manifest Documentation](https://developers.home-assistant.io/docs/creating_integration_manifest/)
- Existing `custom_components/energieoptimierung/` codebase (optimizer.py, __init__.py, const.py)
