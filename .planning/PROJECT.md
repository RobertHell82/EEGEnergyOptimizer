# EEG Energy Optimizer

## What This Is

A Home Assistant custom integration for grid-friendly battery management, optimized for energy communities (Energiegemeinschaften / EEG). It controls when a PV battery charges and discharges to maximize feed-in during times the EEG actually needs energy — mornings and evenings rather than midday when PV surplus is abundant everywhere. Designed for PV owners with battery storage, with or without EEG membership.

## Core Value

Feed solar energy into the grid when the community actually needs it, not when everyone else is feeding in too.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Morning feed-in priority — delay battery charging to feed PV production into the grid during early hours (configurable start time, e.g. until 10:00-11:00)
- [ ] Night feed-in — discharge battery into the grid during evening/night hours under configurable conditions (SOC threshold, next-day PV forecast, overnight consumption reserve)
- [ ] Night feed-in optimal strategy — full logic from existing integration (dynamic min-SOC based on overnight consumption + safety buffer, next-day surplus check including battery + buffer + household demand)
- [ ] Configurable EEG time windows — define when the community needs energy (e.g. 6:00-9:00, 17:00-22:00)
- [ ] Huawei SUN2000 inverter support — battery charge/discharge control via HA Huawei Solar integration services
- [ ] Abstract inverter interface — clean separation so additional inverter types can be added without touching optimization logic
- [ ] Solcast PV forecast integration — read remaining/tomorrow forecasts from Solcast Solar HA integration
- [ ] Forecast.Solar integration — alternative free PV forecast source
- [ ] Onboarding Panel — dedicated HA sidebar panel with step-by-step setup wizard, prerequisite checks (is Solcast installed? is inverter integration set up?), and guidance for installing dependencies
- [ ] Sensor entity mapping — user selects relevant sensors (SOC, PV power, consumption, grid feed-in) during setup with contextual help
- [ ] HACS compatibility — proper repository structure, manifest, hacs.json for distribution via HACS

### Out of Scope

- Heizstab (heating rod) control — not part of this integration, keep it simple
- Tesla/EV charging optimization — separate concern
- Warmwasserpuffer (hot water buffer) management — separate concern
- Multiple locations — single installation focus
- Real-time EEG API integration — no API exists, time-based approach
- Fronius Gen24 support in v1 — comes as second inverter type after Huawei is validated

## Context

- Developed alongside an existing private Energieoptimierung integration in this repo (`custom_components/energieoptimierung/`) which serves as reference for core algorithms (night discharge logic, surplus factor calculation, guard delays)
- The existing integration is Fronius-specific and feature-heavy — the new one is deliberately simpler and more universal
- Will be developed in this repo initially, then moved to its own repo before HACS publication
- Austrian/German energy community context: EEG members share surplus PV production, but midday feed-in is worth less because everyone produces at the same time
- Huawei SUN2000 is the initial target because control via HA services is simpler than Fronius Modbus; this allows faster validation of the core optimization logic
- Forecast sources: Solcast (paid, accurate) and Forecast.Solar (free, simpler) — user chooses during setup

## Constraints

- **Platform**: Home Assistant custom integration (Python, async)
- **Frontend**: LitElement/JS for Onboarding Panel (HA custom panel)
- **Distribution**: HACS-compatible repository structure
- **Dependencies**: Relies on existing HA integrations (Huawei Solar, Solcast/Forecast.Solar) — cannot bundle them
- **Inverter control**: Via HA services (Huawei) — no direct hardware access in v1
- **Language**: UI strings in German (primary audience is DACH region), English as fallback

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Huawei first, Fronius later | Huawei control via HA services is simpler, faster to validate core logic | — Pending |
| Onboarding Panel over Config Flow | Better UX for prerequisite guidance and sensor mapping, worth the frontend effort | — Pending |
| Time-based EEG demand (no API) | No real-time EEG demand API exists, configurable time windows are pragmatic | — Pending |
| Abstract inverter interface from day one | Avoid Huawei-specific coupling, make adding Fronius/SMA/others clean | — Pending |
| Develop in existing repo, extract later | Need reference access to existing integration's algorithms during development | — Pending |

---
*Last updated: 2026-03-20 after initialization*
