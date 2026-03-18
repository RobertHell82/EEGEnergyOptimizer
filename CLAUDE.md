# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Energieoptimierung** (v3.0.0) — a Home Assistant custom integration for predictive energy management at a dual-location smart home in Austria (Grünbach and Traun). It optimizes Heizstab (heating rod), battery charge/discharge, and grid feed-in based on PV forecasts, consumption history, and real-time sensor data.

**Language**: Python (async, Home Assistant framework)
**HA Instance**: `http://192.168.100.211:8123`
**Fronius Inverter**: `192.168.100.57` (HTTP Digest Auth)

## Architecture

All code lives in `custom_components/energieoptimierung/`. The integration runs as a Home Assistant config-flow hub.

### Core Processing Loop (60-second cycle)

```
__init__.py: async_setup_entry()
  → EnergyOptimizer instantiated
  → Platforms forwarded: sensor, switch, number
  → 60s timer: async_run_cycle(execute=switch_on)

optimizer.py: async_run_cycle()
  → _gather_inputs() → Snapshot (all sensor states as dataclass)
  → _evaluate() → Decision (strategy + actions)
     1. _check_guards() — emergency overrides (WW kritisch, Batterie kritisch, etc.)
     2. Strategy selection based on PV forecast vs demand:
        - ÜBERSCHUSS: PV surplus day → charge battery, heat water, feed-in
        - BALANCIERT: moderate PV → balanced loading
        - ENGPASS: low PV → conserve
        - NACHT: nighttime → minimal consumption
     3. _check_entladung() — evening battery discharge logic
  → _execute() — writes to HA entities + Fronius API
```

### Key Files

| File | Role |
|------|------|
| `optimizer.py` | Decision engine — strategies, guards, Snapshot/Decision dataclasses |
| `sensor.py` | 15 sensors: forecasts (sunrise, 7-day), demand, consumption profile |
| `coordinator.py` | Loads hourly consumption averages from recorder (8-week rolling, weekday/weekend split) |
| `config_flow.py` | 7-step UI configuration flow |
| `fronius_api.py` | HTTP Digest Auth client for Fronius inverter battery control |
| `fronius_sync.py` | Shared sync function between switches and Fronius |
| `const.py` | All constants, defaults, strategy/mode enums, entity IDs |
| `switch.py` | Optimizer enable/disable + Einspeisung (feed-in) toggle |
| `number.py` | Battery discharge power control (0–12 kW) |

### Output Entities (written by optimizer)

- `input_select.heizstab` — Aus / 1-Phasig / 3-Phasig
- `input_number.batterie_ladelimit_kw` — charge limit in kW
- `switch.energieoptimierung_einspeisung` — feed-in enable
- `number.energieoptimierung_einspeiseleistung` — feed-in power (0–12 kW)
- Fronius API: `HYB_EM_MODE` (0=auto, 1=manual), `HYB_EM_POWER` (negative W for discharge)

### Dependencies

- **recorder** — long-term hourly statistics for consumption history
- **sun** — sunrise/sunset calculations
- **solcast_solar** (after_dependency) — PV production forecasts

## Dashboards

- `dashboard_energieoptimierung.yaml` — optimizer status, strategy, decisions, controls
- `dashboard_energie.yaml` — consumption profiles, 7-day forecasts

## Key Domain Concepts

- **Strategies**: ÜBERSCHUSS / BALANCIERT / ENGPASS / NACHT / INAKTIV — selected based on Solcast PV forecast vs. calculated energy demand
- **Guards**: Emergency conditions checked before strategy (WW kritisch, Battery kritisch, WW hoch, Battery hoch, Holzvergaser active)
- **Consumption profile**: Hourly averages from recorder, split by weekday (Mo–Fr) vs. weekend (Sa–So), 8-week rolling window
- **Heizstab**: OhmPilot heating rod — Aus (0 kW), 1-Phasig (2 kW), 3-Phasig (6 kW)
- **Entladung**: Evening battery discharge after configurable start time (default 20:00) when SOC above minimum

## Development Notes

- No build system, tests, or CI — component is deployed by copying files to HA's `custom_components/` directory
- All UI strings are in German (`strings.json`, `translations/de.json`)
- The optimizer always calculates but only executes actions when `switch.energieoptimierung_optimizer` is on
- Config changes trigger full integration reload via `_async_update_listener`
- `HOME_ASSISTANT_OVERVIEW.md` contains a complete inventory of all HA entities (3,400+) across both locations
