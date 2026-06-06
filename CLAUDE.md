# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**EEG Energy Optimizer** (v1.0.9-dev) — a Home Assistant custom integration for grid-friendly battery management, optimized for energy communities (Energiegemeinschaften / EEG) in the DACH region. It controls when a PV battery charges and discharges to maximize feed-in during EEG-relevant time windows (mornings and evenings).

**Language**: Python (async, Home Assistant framework) + plain JS (panel)
**Distribution**: HACS-compatible repository structure

## Architecture

All code lives in `custom_components/eeg_energy_optimizer/`. The integration runs as a Home Assistant config-flow hub with a sidebar onboarding panel.

### Core Processing Loop (30-second cycle)

```
__init__.py: async_setup_entry()
  → Inverter created via factory (inverter/__init__.py)
  → Platforms forwarded: sensor, select
  → WebSocket API registered for panel
  → Frontend panel registered
  → Activity log: persistent ring buffer (5000 entries, paginated API)
  → 30s timer: _optimizer_cycle()

optimizer.py: async_run_cycle(mode)
  → _gather_snapshot() → Snapshot (all sensor states as dataclass)
  → _evaluate() → Decision
     1. _calc_energiebedarf() — consumption to sunset + missing battery energy
     2. _should_block_charging() — Morgen-Einspeisung check:
        - Feature enabled + sunrise known
        - Within window (sunrise - 1h to morning_end_time)
        - PV forecast > demand * (1 + safety_buffer%)
     3. _should_discharge() — evening discharge check:
        - Feature enabled
        - PeakShare mode: time within computed optimal window (or fixed start time fallback)
        - SOC > dynamic min_soc (+ hysteresis on reactivation)
        - PV tomorrow >= tomorrow_demand
     4. State: Morgen-Einspeisung / Nacht-Entladung / Normal
  → _execute() — inverter commands (only in mode "Ein")
```

### Key Files

| File | Role |
|------|------|
| `__init__.py` | Entry setup, 30s optimizer timer, activity log, feed-in statistics, panel registration, config migration |
| `optimizer.py` | Decision engine — Snapshot/Decision dataclasses, Morgen-Einspeisung, discharge logic |
| `statistics.py` | Feed-in statistics tracker — tracks grid export kWh, session count & duration during active states |
| `sensor.py` | 20 sensors: consumption profile, forecasts, battery, PV, Hausverbrauch, power flows, register writes, decision, feed-in energy |
| `coordinator.py` | Loads hourly consumption averages from recorder (rolling, weekday split) |
| `forecast_provider.py` | Abstract PV forecast provider — Solcast and Forecast.Solar implementations |
| `config_flow.py` | Single-click config flow (full setup happens in panel) |
| `peakshare.py` | PeakShareProvider — fetches + caches PeakShare API data, sliding window algorithm for optimal discharge window |
| `websocket_api.py` | 17 WebSocket commands for panel (config, sensors, inverter control, activity log, feed-in statistics, PeakShare communities & data, consumption profile status & refresh) |
| `inverter/base.py` | Abstract inverter interface (InverterBase ABC) |
| `inverter/huawei.py` | Huawei SUN2000 implementation via HA services |
| `inverter/fronius.py` | Fronius Gen24 implementation via direct Modbus TCP (SunSpec Model 124) |
| `inverter/solax.py` | SolaX Gen4+ implementation via solax_modbus Mode 1 |
| `inverter/solaredge.py` | SolarEdge StorEdge implementation via solaredge-modbus-multi |
| `inverter/__init__.py` | Factory function `create_inverter()` |
| `select.py` | Optimizer mode select entity (Ein/Test), restores state across restarts |
| `const.py` | All constants, defaults, mode enums, state names |
| `frontend/eeg-optimizer-panel.js` | Dashboard + onboarding panel (plain HTMLElement, Shadow DOM) |

### Sensors (20 total)

| # | Sensor | Update | Description |
|---|--------|--------|-------------|
| 1 | Verbrauchsprofil | slow | Hourly averages per weekday for dashboard charts |
| 2–8 | Tagesverbrauchsprognose heute..Tag 6 | fast | Daily consumption forecasts (7 sensors) |
| 9 | Prognose bis Sonnenaufgang | fast | Consumption now → next sunrise |
| 10 | Batterie fehlende Energie | fast | kWh needed to fully charge battery |
| 11 | PV-Prognose heute | fast | Remaining PV today from forecast provider |
| 12 | PV-Prognose morgen | fast | PV forecast tomorrow |
| 13 | Hausverbrauch | fast | Calculated: PV - Battery - Grid (kW, MEASUREMENT) |
| 14 | PV-Leistung | fast | Current PV production (kW, MEASUREMENT) |
| 15 | Netzleistung | fast | Current grid power — positive = import, negative = export (kW, MEASUREMENT) |
| 16 | Batterieleistung | fast | Current battery power — positive = charge, negative = discharge (kW, MEASUREMENT) |
| 17 | Register-Writes | fast | Cumulative inverter Modbus write counter (used for SolarEdge NVRAM monitoring) |
| 18 | Entscheidung | 30s | Current optimizer state + Markdown dashboard |
| 19 | Morgen-Einspeisung Energie heute | fast | Grid feed-in kWh during Morgen-Einspeisung (TOTAL, resets daily) |
| 20 | Nacht-Entladung Energie heute | fast | Grid feed-in kWh during evening discharge (TOTAL, resets daily) |

### Select Entity

| Entity | Options | Description |
|--------|---------|-------------|
| `select.eeg_energy_optimizer_optimizer` | Ein / Test | Optimizer mode — Ein executes inverter commands, Test is dry-run (Aus is internal state only) |

### Optimizer States

- **Morgen-Einspeisung**: Battery charging blocked to maximize morning EEG feed-in
- **Nacht-Entladung**: Battery discharging for evening EEG feed-in
- **Normal**: Standard operation (inverter in auto mode)

### Activity Log

- **Ring buffer**: 5000 entries (`collections.deque`), persisted via `homeassistant.helpers.storage.Store`
- **Logging**: At full hours (:00) as heartbeat + on every state change
- **API**: Paginated WebSocket endpoint (`get_activity_log` with `offset`/`limit`)
- **Frontend**: Loads 100 entries initially, "Mehr laden" fetches 100 more per click, live events via subscription

### WebSocket API (17 commands)

| Command | Description |
|---------|-------------|
| `eeg_optimizer/get_config` | Read config entry data |
| `eeg_optimizer/save_config` | Update config entry |
| `eeg_optimizer/check_prerequisites` | Check required integrations |
| `eeg_optimizer/detect_sensors` | Auto-detect Huawei sensors |
| `eeg_optimizer/test_inverter` | Test inverter connection |
| `eeg_optimizer/manual_stop` | Stop forcible charge/discharge |
| `eeg_optimizer/manual_discharge` | Trigger manual discharge |
| `eeg_optimizer/manual_block_charge` | Block battery charging |
| `eeg_optimizer/set_test_overrides` | Set simulation overrides |
| `eeg_optimizer/get_test_overrides` | Read simulation overrides |
| `eeg_optimizer/clear_test_overrides` | Clear simulation overrides |
| `eeg_optimizer/get_activity_log` | Paginated activity log (offset, limit) |
| `eeg_optimizer/get_feedin_statistics` | Feed-in statistics (days=0 for all data, includes daily + period summaries) |
| `eeg_optimizer/get_peakshare_communities` | List of PeakShare community names for dropdown |
| `eeg_optimizer/get_peakshare_data` | PeakShare community demand forecast + optimal discharge window |
| `eeg_optimizer/get_consumption_profile_status` | Status of consumption profile (datapoints, lookback, last refresh) |
| `eeg_optimizer/refresh_consumption_profile` | Manually recompute the consumption profile from recorder statistics |

### Inverter Abstraction

```
InverterBase (ABC)
  ├── async_set_charge_limit(power_kw) → bool
  ├── async_set_discharge(power_kw, target_soc) → bool
  ├── async_stop_forcible() → bool
  └── is_available → bool

Implementations:
  ├── HuaweiInverter — via HA huawei_solar services
  ├── FroniusInverter — via direct Modbus TCP (SunSpec Model 124, pymodbus)
  ├── SolarEdgeInverter — via HA solaredge_modbus_multi StorEdge
  └── SolaXInverter — via HA solax_modbus Mode 1
```

### Dependencies

- **recorder** — long-term hourly statistics for consumption history
- **sun** — sunrise/sunset calculations
- **http**, **frontend**, **websocket_api** — onboarding panel
- **huawei_solar** (after_dependency) — Huawei inverter control
- **fronius** (after_dependency) — Fronius sensor data via Solar API
- **solax_modbus** (after_dependency) — SolaX inverter control
- **solaredge_modbus_multi** (after_dependency) — SolarEdge inverter control
- **solcast_solar**, **forecast_solar** (after_dependency) — PV forecasts

## Key Domain Concepts

- **Morgen-Einspeisung** (Morning Feed-in): Prevents battery from charging during morning hours so PV surplus feeds into the grid when the EEG community needs it most. Active when PV forecast exceeds demand + safety buffer.
- **Night Discharge (Nacht-Entladung)**: Discharges battery into grid during evening and night hours when community demand is high. With PeakShare enabled, the discharge window is automatically optimized based on community grid import forecasts (sliding window algorithm finds the contiguous block with highest demand) — frequently runs through the night up to the 04:00 hard cutoff, which is why the UI label is "Nacht-Entladung". Without PeakShare, a fixed start time is used. Requires: sufficient SOC above dynamic min-SOC, and tomorrow's PV forecast covers tomorrow's demand. Hard cutoff at 04:00 — discharge stops regardless of other conditions.
- **Dynamic Min-SOC**: base_min_soc + ceil((overnight_consumption * (1 + buffer%) / capacity) * 100) — ensures enough energy for overnight household consumption.
- **Safety Buffer** (`safety_buffer_pct`, default 25%): Applied to both morning blocking threshold and overnight consumption reserve.
- **Hysteresis** (anti-oscillation): Tracks whether a state (Morgen-Einspeisung or Nacht-Entladung) was already active on the current day. If a state was active and then deactivated, stricter thresholds apply for reactivation: evening discharge requires SOC > min_soc + 5% (instead of > min_soc), morning feed-in requires PV > demand × 1.1 (instead of > demand). While a state remains continuously active, normal thresholds apply.
- **Consumption Profile**: Hourly averages from recorder, split by 7 individual weekdays (mo–so), rolling window (default 4 weeks), with weekday fallback chain for missing data.
- **Dual Update Timers**: Slow sensors (profile) every 15min, fast sensors (forecasts, battery, Hausverbrauch) every 1min.

## Config Flow & Onboarding

The config flow is a single-click setup that creates a config entry with `setup_complete=False`. Full configuration happens through the sidebar panel (`/eeg-optimizer`), which provides:

1. Prerequisite checks (inverter integration installed?)
2. Inverter type selection + auto-detection of sensors
3. Battery & PV sensor mapping
4. Forecast source selection (Solcast / Forecast.Solar)
5. Optimizer settings (morning window, discharge time, min-SOC, etc.)
6. Inverter connection test
7. Live dashboard with energy flow, charts, manual controls, activity log

Config entry version: 12 (migrations in `__init__.py`)

## Development Notes

- Tests in `tests/` directory, run with `pytest` (asyncio_mode=auto)
- `pyproject.toml` configures pytest
- All UI strings in German (`strings.json`, `translations/de.json`), English fallback (`translations/en.json`)
- HA imports are guarded with try/except for test environment compatibility (stubs provided)
- The optimizer calculates every cycle but only executes inverter commands when mode is "Ein"
- Config changes trigger full integration reload via `_async_update_listener`
- `__pycache__/` directories should be added to `.gitignore`

## Documentation Sync (docs/ ↔ Panel)

- `docs/guides/*.md` + `docs/images/**` are the **single source of truth** for the in-app guides ("Anleitung" dialogs in the panel)
- `scripts/build_guides.py` converts them to HTML fragments in `custom_components/eeg_energy_optimizer/frontend/guide/` (requires `pip install markdown`); the panel fetches these at runtime
- **Never edit `frontend/guide/*.html` directly** — edit the Markdown source and regenerate
- After changing any file in `docs/guides/` or `docs/images/`: run `python scripts/build_guides.py` and commit both sides
- CI (`.github/workflows/docs-sync.yml`) runs `build_guides.py --check` and fails on divergence
- Markdown conventions (alerts, secondary text, image paths) are documented in `docs/README.md`
- Installation docs (`docs/installation/`) exist only in `docs/` — they have no panel counterpart
