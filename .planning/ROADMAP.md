# Roadmap: EEG Energy Optimizer

## Overview

This roadmap delivers a Home Assistant custom integration that optimizes residential battery storage for energy communities (EEG). The path moves from integration skeleton and inverter control (Phase 1), through forecast data acquisition (Phase 2), to the core optimization engine with safety guards and sensors (Phase 3), and finally a guided onboarding experience (Phase 4). Each phase delivers a verifiable, standalone capability.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Inverter Layer** - HACS-compliant integration skeleton with abstract inverter interface and Huawei SUN2000 implementation (completed 2026-03-21)
- [x] **Phase 2: Forecasting & Consumption Profile** - PV forecast integration (Solcast + Forecast.Solar) and recorder-based consumption profiling (completed 2026-03-21)
- [ ] **Phase 3: Optimizer & Safety System** - Decision engine with EEG time windows, morning feed-in priority, evening discharge, and decision sensor with Markdown dashboard
- [ ] **Phase 4: Onboarding Panel** - LitElement sidebar panel with setup wizard, prerequisite checks, and sensor mapping

## Phase Details

### Phase 1: Foundation & Inverter Layer
**Goal**: A working HA integration that loads via HACS, defines an abstract inverter contract, and can read battery state and send charge/discharge commands to a Huawei SUN2000 inverter
**Depends on**: Nothing (first phase)
**Requirements**: INF-01, INF-02, INF-03
**Success Criteria** (what must be TRUE):
  1. Integration installs via HACS from a GitHub repository and loads without errors in Home Assistant
  2. User can add the integration via HA config flow and select Huawei SUN2000 as inverter type
  3. Integration can read current battery SOC from Huawei inverter and issue charge/discharge commands via HA services
  4. Adding a second inverter type requires only a new implementation file -- no changes to optimizer or config flow logic
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — HACS skeleton, abstract inverter interface, factory pattern, test infrastructure
- [x] 01-02-PLAN.md — Huawei SUN2000 implementation, config flow, translations

### Phase 2: Forecasting & Consumption Profile
**Goal**: The integration reads PV production forecasts from either Solcast or Forecast.Solar and calculates consumption forecasts from HA recorder history -- all data the optimizer needs to make decisions
**Depends on**: Phase 1
**Requirements**: FCST-01, FCST-02, FCST-03
**Success Criteria** (what must be TRUE):
  1. Integration reads today's remaining and tomorrow's PV production forecast from a user-selected Solcast Solar integration
  2. Integration reads PV forecasts from Forecast.Solar as an alternative to Solcast, selectable during setup
  3. Integration calculates hourly consumption averages from HA recorder statistics using rolling window with 7 weekday groups (Mo / Di / Mi / Do / Fr / Sa / So)
  4. Forecast data is exposed as HA sensor entities that update on a configurable interval
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Constants, forecast provider (Solcast + Forecast.Solar), consumption coordinator, tests
- [x] 02-02-PLAN.md — Sensor platform (12 sensors), integration wiring (__init__.py, manifest.json)
- [x] 02-03-PLAN.md — Config flow extension (forecast source + consumption steps), translations

### Phase 3: Optimizer & Safety System
**Goal**: Users get automated, EEG-optimized battery management -- morning feed-in priority, evening discharge, dynamic min-SOC for safe overnight reserve -- with full transparency via a decision sensor with Markdown dashboard
**Depends on**: Phase 2
**Requirements**: OPT-01, OPT-02, OPT-03, SAF-01, SAF-02, SAF-03, SAF-04, SENS-01, SENS-02, SENS-03
**Success Criteria** (what must be TRUE):
  1. During configured morning EEG window, the optimizer delays battery charging so PV production feeds into the grid for the energy community
  2. During configured evening EEG window, the optimizer discharges the battery into the grid when conditions are met (sufficient SOC, favorable next-day PV forecast, overnight consumption reserve maintained)
  3. Critical safety guards (SOC < 10%) trigger immediate protective action regardless of EEG windows; high-priority guards (SOC < 25%) are suppressible during EEG feed-in windows via configurable guard delay
  4. User can see the current optimizer strategy, reasoning, guard status, and all decision inputs as sensor attributes in Home Assistant
  5. User can enable dry-run mode where the optimizer calculates and displays decisions but does not execute any inverter commands
**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Optimizer engine (Snapshot/Decision, morning blocking, evening discharge, min-SOC) + Select entity (Ein/Test/Aus)
- [x] 03-02-PLAN.md — Integration wiring (60s timer, select platform), config flow step 5 (optimizer params), strings, migration
- [x] 03-03-PLAN.md — Decision sensor (Entscheidung) with Markdown dashboard attribute, discharge preview

### Phase 4: Onboarding Panel
**Goal**: New users get a guided, step-by-step setup experience with prerequisite validation and contextual help, instead of a raw config flow
**Depends on**: Phase 3
**Requirements**: INF-04
**Success Criteria** (what must be TRUE):
  1. A dedicated sidebar panel appears in Home Assistant after installation with a step-by-step setup wizard
  2. The wizard checks prerequisites (Solcast or Forecast.Solar installed, inverter integration active) and shows clear guidance when dependencies are missing
  3. User can map their specific sensor entities (SOC, PV power, consumption, grid feed-in) during setup with contextual help explaining what each sensor is for
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Inverter Layer | 2/2 | Complete   | 2026-03-21 |
| 2. Forecasting & Consumption Profile | 3/3 | Complete   | 2026-03-21 |
| 3. Optimizer & Safety System | 1/3 | In Progress|  |
| 4. Onboarding Panel | 0/0 | Not started | - |
