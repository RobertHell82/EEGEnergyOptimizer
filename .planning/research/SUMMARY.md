# Project Research Summary

**Project:** EEG Energy Optimizer
**Domain:** Home Assistant custom integration for EEG/energy community battery optimization
**Researched:** 2026-03-20
**Confidence:** HIGH

## Executive Summary

The EEG Energy Optimizer is a Home Assistant custom integration that optimizes residential battery storage for Austrian Energiegemeinschaften (energy communities). Unlike every existing HA battery optimizer (EMHASS, Predbat, PowerSync, PV Opt), which focus on electricity price arbitrage, this integration optimizes for EEG time-window patterns -- maximizing feed-in during community demand peaks (mornings and evenings) rather than minimizing cost. This is an uncontested niche in the DACH region where energy communities are rapidly growing under Austrian EAG law and German Solarspitzengesetz 2025.

The recommended approach is a Python backend (HA integration) with an abstract inverter interface, a LitElement sidebar panel for onboarding and runtime monitoring, and rule-based strategy selection (surplus factor + guard system). Huawei SUN2000 is the first supported inverter via the existing `huawei_solar` HA integration's service calls. Fronius Gen24 comes second. PV forecasts use Solcast (paid) or Forecast.Solar (free) -- both already have HA integrations. The decision engine uses deterministic, explainable strategies (UEBERSCHUSS/BALANCIERT/ENGPASS/NACHT) based on PV forecast vs. demand ratios, with a two-tier safety guard system proven in the existing reference integration.

The key risks are: (1) designing an inverter abstraction that leaks hardware semantics from the first implementation, making the second inverter a rewrite; (2) service call timing delays causing optimizer oscillation; and (3) HA startup race conditions where unavailable sensors read as zero and trigger false safety overrides. All three are well-understood and preventable with specific patterns identified during research -- intent-based interface design, command cooldowns, and a "warming up" state that suppresses execution until sensors report valid data.

## Key Findings

### Recommended Stack

The stack is entirely standard HA ecosystem tooling with high confidence. Python 3.12+ with asyncio for the backend, Lit 3.3 (native to HA frontend) with TypeScript for the panel, Rollup for bundling. Testing uses pytest with `pytest-homeassistant-custom-component` (v0.13.x). Distribution via HACS with GitHub Releases.

**Core technologies:**
- **Python 3.12+ / asyncio**: HA 2026.x runtime requirement, all sensor reads and service calls are async
- **Lit 3.3 / TypeScript 5.9**: HA frontend-native web component framework; avoids iframe isolation that React/Vue would require
- **Rollup 4.x**: Bundles panel source into single distributable JS module; matches HA frontend toolchain
- **huawei_solar integration**: Provides `forcible_charge`, `forcible_discharge_soc`, `stop_forcible_charge` services via HA for Huawei SUN2000 battery control
- **Solcast Solar + Forecast.Solar**: Dual PV forecast sources (paid accurate + free fallback), both already HA integrations
- **pytest-homeassistant-custom-component 0.13.x**: HA test fixtures; the existing integration has zero tests, this one must not repeat that

### Expected Features

**Must have (table stakes):**
- PV forecast-driven charge/discharge scheduling
- Morning feed-in priority with configurable guard delay (EEG core value)
- Evening battery discharge to grid during demand peaks
- Dynamic min-SOC calculation (overnight consumption reserve)
- Next-day surplus check before discharging
- Configurable EEG time windows (morning + evening)
- Two-tier safety guards (KRITISCH always active, HOCH deferrable during EEG windows)
- Decision sensor with human-readable German reasoning
- Dry-run mode (calculate but don't execute)
- HACS-compatible distribution

**Should have (differentiators):**
- Onboarding sidebar panel with guided setup wizard and prerequisite checks
- Abstract inverter interface (Huawei first, Fronius second, community contributions later)
- Zero-config consumption forecasting from HA recorder (rolling 4-zone weekday splits)
- Surplus factor strategy selection (automatic UEBERSCHUSS/BALANCIERT/ENGPASS/NACHT)
- Inverter throttle detection (speculative +2kW when feed-in is at limit)
- Nightly discharge preview during daytime
- Dual forecast source support (Solcast or Forecast.Solar, user choice)

**Defer indefinitely:**
- Spot price / tariff optimization (EMHASS/Predbat territory)
- EV charging control (separate domain, use evcc)
- Heizstab / hot water control (site-specific, out of scope for v1)
- LP/ML solvers (rule-based is sufficient, explainable, and debuggable)
- Multi-location support (users run separate instances)

### Architecture Approach

Three-subsystem architecture: Python backend (optimizer + inverter layer + sensor platform), JavaScript frontend (LitElement sidebar panel), and WebSocket API bridging them. The optimizer runs a 60-second cycle: gather inputs from sensors, evaluate strategy based on EEG time windows and guards, execute via abstract inverter interface. The panel registers programmatically from `__init__.py` (no YAML editing required). Configuration lives in `config_entry.options` (mutable), not files. A minimal config flow creates the entry; the onboarding panel handles all meaningful configuration via WebSocket commands.

**Major components:**
1. **Optimizer engine** (`optimizer.py`) -- strategy selection, EEG window logic, guard system, 60s decision cycle
2. **Abstract inverter layer** (`inverter/base.py` + implementations) -- ABC with intent-based methods (`execute_action`, `stop_forcible`), factory pattern for type selection
3. **WebSocket API** (`websocket.py`) -- custom commands for panel communication (get_status, update_config, check_prerequisites)
4. **Sidebar panel** (`frontend/`) -- LitElement onboarding wizard + runtime dashboard, bundled via Rollup
5. **Sensor platform** (`sensor.py`) -- decision sensor with strategy + reasoning attributes, forecast sensors, demand sensors

### Critical Pitfalls

1. **Inverter abstraction leaking hardware semantics** -- Design the interface around optimizer intents ("discharge at X kW until SOC Y%"), not hardware operations. Stub both Huawei and Fronius before committing to the interface contract.
2. **Service call timing and oscillation** -- Track pending commands with cooldown timers (2x polling interval). Never re-send identical commands within cooldown window.
3. **HA startup race conditions** -- Distinguish "sensor reports 0" from "sensor unavailable." Add a "warming up" state that suppresses execution until all critical sensors report valid data.
4. **Panel JS caching after HACS updates** -- Append version query parameter to `module_url` during panel registration for automatic cache busting.
5. **HACS repo structure** -- Create HACS-compliant structure from day one (single `custom_components/eeg_optimizer/` directory, proper `manifest.json`, `hacs.json`, brand assets). Run `hacs/action` in CI.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Foundation and Inverter Layer
**Rationale:** Everything depends on the integration skeleton and inverter ABC contract. The inverter interface is the highest-risk design decision -- getting it wrong means a rewrite when adding Fronius. Must be designed before any optimizer logic.
**Delivers:** Working HA integration that can read battery status and send charge/discharge commands to a Huawei SUN2000 inverter.
**Addresses:** Abstract inverter interface, HACS-compliant scaffolding, manifest.json, translations structure, CI setup (hassfest + hacs/action)
**Avoids:** Pitfall #1 (leaky abstraction -- stub both Huawei and Fronius), Pitfall #5 (repo structure), Pitfall #8 (HA breaking changes via CI), Pitfall #11 (German-only), Pitfall #12 (missing manifest fields)

### Phase 2: Optimizer Core
**Rationale:** The decision engine is the product's core value and can be validated with HA entities before any panel exists. Depends on inverter layer from Phase 1.
**Delivers:** Working optimizer that reads PV forecasts, calculates strategy, executes charge/discharge decisions, and exposes state via sensors.
**Addresses:** PV forecast integration (Solcast), EEG time windows, surplus factor strategy selection, two-tier safety guards with guard delay, dynamic min-SOC, evening discharge, decision sensor with reasoning, dry-run mode
**Avoids:** Pitfall #2 (service call timing -- command cooldowns from the start), Pitfall #3 (startup race -- warming-up state), Pitfall #9 (forecast abstraction -- design for daily aggregates)

### Phase 3: Consumption Forecasting and Polish
**Rationale:** Consumption forecasting enhances strategy accuracy but is not required for core operation (the optimizer works with just PV forecasts and current sensor readings). This phase adds the "zero-config" differentiator.
**Delivers:** Auto-detected consumption patterns from HA recorder, Forecast.Solar as alternative forecast source, inverter throttle detection, nightly discharge preview.
**Addresses:** Zero-config consumption forecasting, dual forecast source support, inverter throttle detection, nightly discharge preview, next-day surplus check refinement

### Phase 4: Onboarding Panel
**Rationale:** The panel is the biggest UX differentiator but has the highest complexity and depends on working WebSocket endpoints and a functional optimizer. Building it last ensures the backend API is stable.
**Delivers:** LitElement sidebar panel with guided onboarding wizard (prerequisite checks, inverter selection, sensor mapping, EEG window configuration) and runtime status dashboard.
**Addresses:** Onboarding wizard, prerequisite validation, sensor mapping UI, runtime dashboard
**Avoids:** Pitfall #4 (JS caching -- version query params), Pitfall #6 (hardcoded entities -- validation during selection), Pitfall #7 (WS versioning), Pitfall #10 (prerequisite detection -- use config entries not entity existence), Pitfall #13 (component name mismatch)

### Phase 5: HACS Publication
**Rationale:** Distribution concerns should not drive architecture. This phase is about polish, documentation, and meeting HACS default repository inclusion requirements.
**Delivers:** Published HACS integration with documentation, brand assets, CI/CD pipeline, GitHub Releases.
**Addresses:** HACS distribution, automated testing, brand assets, release automation

### Phase Ordering Rationale

- **Inverter layer before optimizer** because the optimizer cannot be tested without a way to read battery state and issue commands. The abstract interface is also the highest-risk design decision.
- **Optimizer before panel** because the panel displays optimizer state -- building UI before the data model is stable causes rework. The optimizer can be fully validated with standard HA dashboard cards.
- **Consumption forecasting between optimizer and panel** because it enriches strategy accuracy but the core optimizer works without it. This gives time to collect recorder data during testing.
- **Panel last among functional phases** because it is the most complex frontend work and benefits from a stable backend API. Users can use the integration via standard HA entities and config flow while the panel is being built.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Inverter Layer):** The abstract interface design is critical. Needs research into both Huawei service call semantics and Fronius HTTP API to validate the abstraction before committing. The existing `fronius_api.py` provides reference but the intent-based mapping needs careful design.
- **Phase 4 (Onboarding Panel):** Custom panel development in HA is less documented than backend integration. The panel registration pattern, WebSocket API, and LitElement integration with HA's `hass` object need hands-on validation. Multi-step wizard state management in Lit may need a spike.

Phases with standard patterns (skip research-phase):
- **Phase 2 (Optimizer Core):** Well-documented patterns from the existing reference integration. Strategy selection, guard system, and sensor platform are proven code that needs restructuring, not new research.
- **Phase 3 (Consumption Forecasting):** The existing `coordinator.py` already implements the recorder-based consumption averaging. Port and improve.
- **Phase 5 (HACS Publication):** HACS requirements are thoroughly documented with CI validation tools.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technologies are HA-native or ecosystem standard. Versions verified against HA 2026.3 frontend and core. |
| Features | HIGH | Competitive landscape thoroughly mapped. EEG niche confirmed uncontested. Feature priorities validated against 7 competing integrations. |
| Architecture | HIGH | Panel registration pattern verified from HACS source code and community guides. Inverter interface pattern is standard Python ABC. WebSocket API is official HA developer pattern. |
| Pitfalls | HIGH | Critical pitfalls (#1-#3) backed by concrete evidence from existing codebase and Huawei Solar wiki. Panel pitfalls (#4, #13) confirmed by community reports. |

**Overall confidence:** HIGH

### Gaps to Address

- **Huawei service call parameters:** The wiki documents service names but detailed parameter schemas (exact field names, types, validation) need verification against the `huawei_solar` integration source code during Phase 1.
- **Panel build pipeline in HACS context:** How HACS handles the `frontend/` subdirectory during installation needs validation. The Rollup source should be excluded from the distributed release ZIP.
- **Fronius inverter interface validation:** The existing `fronius_api.py` uses HTTP Digest Auth with a hybrid HA1=MD5/HA2=SHA256 scheme. This needs to be validated as still working with current Fronius firmware before the abstraction is finalized.
- **Config entry options size limits:** Storing full sensor mappings, EEG time windows, and inverter config in `config_entry.options` -- need to confirm there is no practical size limit for options dictionaries in HA.
- **Lit state management for multi-step wizard:** The onboarding panel has 5+ steps with shared state. Need to decide on approach during Phase 4 planning (plain properties vs. @lit/context vs. external store).
- **Panel testing strategy:** No established pattern for testing LitElement panels in the HA ecosystem. May need browser-based testing or accept manual testing for the frontend.

## Sources

### Primary (HIGH confidence)
- [HA Developer Docs: Custom Panels](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/)
- [HA Developer Docs: WebSocket API](https://developers.home-assistant.io/docs/frontend/extending/websocket-api/)
- [HA Developer Docs: Integration File Structure](https://developers.home-assistant.io/docs/creating_integration_file_structure/)
- [HACS Integration Publishing](https://hacs.xyz/docs/publish/integration/)
- [Huawei Solar Integration](https://github.com/wlcrs/huawei_solar) -- v1.6.0, battery control services
- [Huawei Solar Force Charge/Discharge Wiki](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery)
- [HA Frontend package.json](https://github.com/home-assistant/frontend/blob/dev/package.json) -- Lit 3.3.2, TS 5.9.3
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) -- v0.13.318
- [Forecast.Solar HA integration docs](https://www.home-assistant.io/integrations/forecast_solar/)
- [Solcast Solar HA integration](https://github.com/BJReplay/ha-solcast-solar)

### Secondary (MEDIUM confidence)
- [Community Guide: Adding Sidebar Panel](https://community.home-assistant.io/t/how-to-add-a-sidebar-panel-to-a-home-assistant-integration/981585)
- [HSEM: Huawei Solar Energy Management](https://github.com/woopstar/hsem) -- reference architecture
- [HACS __init__.py panel registration pattern](https://github.com/hacs/integration/blob/main/custom_components/hacs/__init__.py)
- [StaticPathConfig API](https://github.com/hacs/integration/issues/3828)
- [Energiesparhaus.at Forum](https://www.energiesparhaus.at/forum-optimiertes-batteriemanagement-herstelleruebergreifend/82851)

### Tertiary (LOW confidence)
- Competitive integrations (EMHASS, Predbat, PowerSync, PV Opt, HAEO, Solar Optimizer) -- feature comparison based on documentation review, not hands-on testing

---
*Research completed: 2026-03-20*
*Ready for roadmap: yes*
