---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
stopped_at: Completed 04-03-PLAN.md
last_updated: "2026-03-22T20:02:33.580Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 11
  completed_plans: 10
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-20)

**Core value:** Feed solar energy into the grid when the community actually needs it, not when everyone else is feeding in too.
**Current focus:** Phase 04 — onboarding-panel

## Current Position

Phase: 04 (onboarding-panel) — EXECUTING
Plan: 2 of 3

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 4min | 2 tasks | 14 files |
| Phase 01 P02 | 90 | 3 tasks | 9 files |
| Phase 02 P01 | 5min | 2 tasks | 5 files |
| Phase 02 P03 | 3min | 2 tasks | 5 files |
| Phase 02 P02 | 3min | 2 tasks | 4 files |
| Phase 03 P01 | 4min | 2 tasks | 6 files |
| Phase 03 P03 | 2min | 2 tasks | 2 files |
| Phase 03 P02 | 4min | 2 tasks | 5 files |
| Phase 04 P01 | 3min | 2 tasks | 8 files |
| Phase 04 P03 | 2min | 2 tasks | 1 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 4 phases derived from 17 requirements. Phase 3 (Optimizer) is the heaviest (10 reqs) because OPT/SAF/SENS are tightly coupled -- splitting would create artificial boundaries.
- [Roadmap]: Research suggested 5 phases but Phase 5 (HACS Publication) had no mapped requirement. HACS scaffolding is covered by INF-03 in Phase 1. Publication tasks will be handled as part of Phase 4 completion.
- [Phase 01]: TYPE_CHECKING guards for HA imports: dev environment cannot install homeassistant package, using type-hint-only imports
- [Phase 01]: Huawei SOC sensor has no device_class='battery' — EntitySelector filter removed
- [Phase 01]: Auto-detect Huawei device from device registry instead of DeviceSelector
- [Phase 01]: Manual battery capacity (kWh) input added as fallback when capacity sensor unavailable
- [Phase 02]: Module-level _as_local/_now pattern for timezone handling in coordinator
- [Phase 02]: Lazy recorder imports via _ensure_recorder_imports() to avoid ImportError in test env
- [Phase 02]: Forecast entity selectors on same form as source selection for simpler UX
- [Phase 02]: Config flow VERSION bumped to 2 due to schema change (new forecast/consumption keys)
- [Phase 02]: Forecast sensors omit state_class to prevent HA recorder pollution
- [Phase 02]: Battery sensor falls back to manual capacity config when sensor unavailable
- [Phase 03]: Dynamic min-SOC as discharge calculation only (D-14/D-16), not as guard
- [Phase 03]: Three optimizer modes: Ein/Test/Aus with inverter deduplication via _prev_zustand
- [Phase 03]: Duck typing for update_from_decision avoids circular imports between sensor.py and optimizer.py
- [Phase 03]: Optimizer created after platform setup (coordinator/provider injected by sensor.py)
- [Phase 03]: Config flow VERSION bumped to 3 with async_migrate_entry defaults for Phase 3 keys
- [Phase 04]: HUAWEI_DEFAULTS moved from config_flow to websocket_api for detect_sensors command
- [Phase 04]: Panel uses plain HTMLElement + Shadow DOM, no LitElement/CDN imports
- [Phase 04]: Config flow reduced to 1-click with setup_complete=false; full config via panel wizard
- [Phase 04]: Used Energiebedarf (kWh) instead of Ueberschuss-Faktor for dashboard display, matching updated Decision dataclass
- [Phase 04]: Inline SVG charts with HA CSS variables for light/dark theme compatibility

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 research flag: Abstract inverter interface design is critical. Must stub both Huawei and Fronius before committing to the interface contract (from research SUMMARY.md).
- Phase 4 research flag: Custom panel development in HA is less documented. Panel registration, WebSocket API, and LitElement wizard state management may need a spike.

## Session Continuity

Last session: 2026-03-22T20:02:33.570Z
Stopped at: Completed 04-03-PLAN.md
Resume file: None
