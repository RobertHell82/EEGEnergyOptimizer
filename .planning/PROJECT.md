# EEG Energy Optimizer

## What This Is

A Home Assistant custom integration for grid-friendly battery management, optimized for energy communities (Energiegemeinschaften / EEG). It controls when a PV battery charges and discharges to maximize feed-in during times the EEG actually needs energy — mornings and evenings rather than midday when PV surplus is abundant everywhere. Designed for PV owners with battery storage, with or without EEG membership.

## Core Value

Feed solar energy into the grid when the community actually needs it, not when everyone else is feeding in too.

## Requirements

### Validated

- ✓ Morning feed-in priority — v1.0 (morning charge blocking with configurable EEG window)
- ✓ Night feed-in — v1.0 (evening discharge with SOC threshold, next-day PV forecast, overnight reserve)
- ✓ Night feed-in optimal strategy — v1.0 (dynamic min-SOC, surplus-day detection, safety buffer)
- ✓ Configurable EEG time windows — v1.0 (morning + evening windows in config flow)
- ✓ Huawei SUN2000 inverter support — v1.0 (forcible charge/discharge/stop via HA services)
- ✓ Abstract inverter interface — v1.0 (InverterBase ABC with factory pattern)
- ✓ Solcast PV forecast integration — v1.0 (remaining today + tomorrow forecasts)
- ✓ Forecast.Solar integration — v1.0 (alternative free source, selectable in setup)
- ✓ Onboarding Panel — v1.0 (sidebar panel with 8-step wizard, prerequisite checks, live dashboard)
- ✓ Sensor entity mapping — v1.0 (entity pickers with auto-detection and contextual help)
- ✓ HACS compatibility — v1.0 (manifest, hacs.json, proper repo structure)

### Active

(None — next milestone requirements TBD via /gsd:new-milestone)

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
| Huawei first, Fronius later | Huawei control via HA services is simpler, faster to validate core logic | ✓ Good — Huawei working, abstract interface ready for Fronius |
| Onboarding Panel over Config Flow | Better UX for prerequisite guidance and sensor mapping, worth the frontend effort | ✓ Good — 8-step wizard with auto-detection, live dashboard |
| Time-based EEG demand (no API) | No real-time EEG demand API exists, configurable time windows are pragmatic | ✓ Good — pragmatic approach, configurable windows |
| Abstract inverter interface from day one | Avoid Huawei-specific coupling, make adding Fronius/SMA/others clean | ✓ Good — ABC with factory, clean separation |
| Develop in existing repo, extract later | Need reference access to existing integration's algorithms during development | ✓ Good — algorithms adapted successfully |
| Plain HTMLElement over LitElement | No CDN dependency, Shadow DOM isolation, simpler deployment | ✓ Good — 1892 LOC JS, no build step needed |
| 1-click config flow + panel wizard | Config flow minimal, full setup in panel for better UX | ✓ Good — setup_complete flag gates features |

## Current State

Shipped v1.0 with 4,194 LOC (2,302 Python + 1,892 JS) across 6 phases and 14 plans.
Tech stack: Python async (HA framework), plain JS/Shadow DOM (panel), WebSocket API.
All 17 v1 requirements validated. 8 tech debt items addressed in Phase 5+6.
Ready for HACS publication or next milestone (Fronius support, advanced strategies).

---
*Last updated: 2026-03-22 after v1.0 milestone*
