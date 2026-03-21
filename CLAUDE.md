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
  → Platforms forwarded: sensor, switch, number, select
  → Initial read-only cycle, then 60s timer: async_run_cycle(execute=switch_on)

optimizer.py: async_run_cycle()
  → _gather_inputs() → Snapshot (all sensor states as dataclass)
  → _evaluate() → Decision (strategy + actions)
     1. _check_guards() — safety overrides with morning delay:
        - KRITISCH (always active): WW < 40°C, Battery < 10%
        - HOCH (delayed by guard_delay_h after sunrise): WW < 55°C, Battery < 25%
        - MITTEL: Holzvergaser active + PV < 6kW
     2. Critical guards → immediate return with "Sicherheit" strategy
     3. Strategy selection based on PV forecast vs demand:
        - ÜBERSCHUSS: PV surplus → feed-in priority, then battery, then Heizstab
        - BALANCIERT: moderate PV → battery priority, then Heizstab
        - ENGPASS: low PV → maximize self-consumption
        - NACHT: after sunset → defaults + evening discharge check
     4. HOCH guards applied as overrides after strategy
     5. Guard-Delay info appended to reasoning
     6. Nachtentladung preview (daytime only)
  → _execute() — writes to HA entities + Fronius API
```

### Key Files

| File | Role |
|------|------|
| `__init__.py` | Entry setup, 60s optimizer timer, platform forwarding |
| `optimizer.py` | Decision engine — strategies, guards, guard-delay, Snapshot/Decision dataclasses |
| `sensor.py` | 16 sensors: forecasts, demand components, consumption profile, optimizer decision |
| `coordinator.py` | Loads hourly consumption averages from recorder (rolling, 4-zone weekday split) |
| `config_flow.py` | 6-step UI configuration flow + options flow |
| `fronius_api.py` | HTTP Digest Auth client for Fronius inverter battery control |
| `fronius_sync.py` | Shared sync function between switches/number and Fronius API |
| `const.py` | All constants, defaults, strategy/mode enums, entity IDs |
| `select.py` | Optimizer mode select entity (Ein/EV-Modi/Aus), restores state across restarts |
| `switch.py` | Einspeisung (feed-in) toggle, triggers Fronius sync |
| `number.py` | Feed-in power control (0–12 kW), triggers Fronius sync |

### Sensors (16 total)

| # | Sensor | Update | Description |
|---|--------|--------|-------------|
| 1 | Prognose bis Sonnenaufgang | slow (15min) | Consumption forecast now → sunrise+offset |
| 2 | Prognose bis Sonnenuntergang | slow | Consumption forecast now → sunset |
| 3 | Batterie fehlende Energie | fast (2min) | kWh needed to fully charge battery |
| 4 | Tesla fehlende Ladeenergie | fast | kWh needed to charge Tesla (0 if not home) |
| 5 | Puffer Aufheizenergie | fast | kWh needed to heat buffer to target temp |
| 6 | Energiebedarf heute | fast | Sum of sensors 2+3+4+5 |
| 7 | Verbrauchsprofil | slow | Hourly averages per zone for dashboard charts |
| 8–15 | Prognose heute/morgen/Tag 2–7 | slow | Daily consumption forecasts (8 sensors) |
| 16 | Entscheidung | 60s | Current optimizer strategy + full decision as attributes |

### Switches & Number

| Entity | Type | Description |
|--------|------|-------------|
| `select.energieoptimierung_optimizer` | Select | Optimizer mode: Ein / EV Heizstab / EV Batterie / EV Balanciert / Aus |
| `switch.energieoptimierung_einspeisung` | Switch | Feed-in toggle, triggers Fronius sync |
| `number.energieoptimierung_einspeiseleistung` | Number | Feed-in power 0–12 kW, triggers Fronius sync |

### Output Entities (written by optimizer)

- `input_select.heizstab` — Aus / 1-Phasig / 3-Phasig
- `input_number.batterie_ladelimit_kw` — charge limit in kW
- `switch.energieoptimierung_einspeisung` — feed-in enable
- `number.energieoptimierung_einspeiseleistung` — feed-in power (0–12 kW)
- Fronius API: `HYB_EM_MODE` (0=auto, 1=manual), `HYB_EM_POWER` (negative W for discharge)

### Dependencies

- **recorder** — long-term hourly statistics for consumption history
- **sun** — sunrise/sunset calculations, guard-delay timing
- **solcast_solar** (after_dependency) — PV production forecasts

## Dashboards

- `dashboard_energieoptimierung.yaml` — optimizer status, strategy, decisions, controls
- `dashboard_energie.yaml` — consumption profiles, 7-day forecasts
- `dashboard_gruenbach.yaml` — location-specific overview

## Key Domain Concepts

- **Strategies**: ÜBERSCHUSS / BALANCIERT / ENGPASS / NACHT / INAKTIV — selected based on Solcast PV forecast vs. calculated energy demand (Überschuss-Faktor)
- **Guards**: Safety conditions checked every cycle. Two levels:
  - **KRITISCH** (always active): WW < 40°C → sofort aufheizen, Battery < 10% → sofort laden
  - **HOCH** (delayed mornings): WW < 55°C → Heizstab Priorität, Battery < 25% → Ladelimit erhöhen
  - **MITTEL**: Holzvergaser aktiv + PV < 6kW → Heizstab aus
- **Guard-Delay** (`guard_delay_h`, default 3h): HOCH-Guards werden in den ersten Stunden nach Sonnenaufgang unterdrückt, damit morgens die EEG-Einspeisung Vorrang hat. KRITISCH-Guards sind immer aktiv.
- **Consumption profile**: Hourly averages from recorder, split by 4 zones (Mo–Do / Fr / Sa / So), rolling window (default 8 weeks)
- **Heizstab**: OhmPilot heating rod — Aus (0 kW), 1-Phasig (2 kW), 3-Phasig (6 kW)
- **Entladung**: Evening battery discharge after configurable start time (default 20:00) when SOC above dynamic min-SOC and tomorrow is a surplus day (PV forecast >= total energy demand)
- **Inverter-Drosselung**: When feed-in is at the limit, PV is speculatively increased by 2 kW to break the deadlock and allow battery/Heizstab activation
- **Nachtentladung Vorschau**: Daytime preview of tonight's discharge plan (shown in decision reasoning)

## Config Flow (6 Steps)

1. **Energiemessung** — Consumption sensor, Heizstab sensor, Wallbox sensor, lookback weeks, update interval, sunrise offset
2. **Hausbatterie** — SOC sensor, capacity sensor
3. **Warmwasserpuffer** — Temperature sensor, volume, target temperature
4. **Tesla-Fahrzeug** — Tracker, SOC, limit, capacity, efficiency, home zone
5. **Optimizer** — PV sensor, feed-in sensor, Solcast sensors, Holzvergaser, Einspeiselimit, Überschuss-Faktor, Guard-Delay
6. **Abend-Entladung & Fronius** — Discharge power/time, min SOC, safety buffer, min WW temp, Fronius credentials

## Development Notes

- No build system, tests, or CI — component is deployed by copying files to HA's `custom_components/` directory
- All UI strings are in German (`strings.json`, `translations/de.json`)
- The optimizer always calculates but only executes actions when `select.energieoptimierung_optimizer` is not "Aus"
- Optimizer modes: Ein (full optimization), Eigenverbrauch Heizstab/Batterie/Balanciert (self-consumption variants), Aus (dry-run)
- Config changes trigger full integration reload via `_async_update_listener`
- `HOME_ASSISTANT_OVERVIEW.md` contains a complete inventory of all HA entities (3,400+) across both locations
- Fronius Gen24 uses hybrid digest auth: HA1=MD5, HA2+response=SHA256, URI without query string
- `INSTALL.md` contains detailed documentation of all strategies, guards, Fronius integration, and sensor details in German
