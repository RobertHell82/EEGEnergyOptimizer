# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**EEG Energy Optimizer** (v0.3.13) — a Home Assistant custom integration for grid-friendly battery management, optimized for energy communities (Energiegemeinschaften / EEG) in the DACH region. It controls when a PV battery charges and discharges to maximize feed-in during EEG-relevant time windows (mornings and evenings).

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
     2. _should_block_charging() — morning charge blocking check:
        - Feature enabled + sunrise known
        - Within window (sunrise - 1h to morning_end_time)
        - PV forecast > demand * (1 + safety_buffer%)
     3. _should_discharge() — evening discharge check:
        - Feature enabled
        - Time >= discharge_start
        - SOC > dynamic min_soc
        - PV tomorrow >= tomorrow_demand
     4. State: Morgen-Einspeisung / Abend-Entladung / Normal
  → _execute() — inverter commands (only in mode "Ein")
```

### Key Files

| File | Role |
|------|------|
| `__init__.py` | Entry setup, 30s optimizer timer, activity log, panel registration, config migration |
| `optimizer.py` | Decision engine — Snapshot/Decision dataclasses, charge blocking, discharge logic |
| `sensor.py` | 14 sensors: consumption profile, forecasts, battery, PV, Hausverbrauch, decision |
| `coordinator.py` | Loads hourly consumption averages from recorder (rolling, weekday split) |
| `forecast_provider.py` | Abstract PV forecast provider — Solcast and Forecast.Solar implementations |
| `config_flow.py` | Single-click config flow (full setup happens in panel) |
| `websocket_api.py` | 12 WebSocket commands for panel (config, sensors, inverter control, activity log) |
| `inverter/base.py` | Abstract inverter interface (InverterBase ABC) |
| `inverter/huawei.py` | Huawei SUN2000 implementation via HA services |
| `inverter/__init__.py` | Factory function `create_inverter()` |
| `select.py` | Optimizer mode select entity (Ein/Test), restores state across restarts |
| `const.py` | All constants, defaults, mode enums, state names |
| `frontend/eeg-optimizer-panel.js` | Dashboard + onboarding panel (plain HTMLElement, Shadow DOM) |

### Sensors (14 total)

| # | Sensor | Update | Description |
|---|--------|--------|-------------|
| 1 | Verbrauchsprofil | slow | Hourly averages per weekday for dashboard charts |
| 2–8 | Tagesverbrauchsprognose heute..Tag 6 | fast | Daily consumption forecasts (7 sensors) |
| 9 | Prognose bis Sonnenaufgang | fast | Consumption now → next sunrise |
| 10 | Batterie fehlende Energie | fast | kWh needed to fully charge battery |
| 11 | PV Prognose heute | fast | Remaining PV today from forecast provider |
| 12 | PV Prognose morgen | fast | PV forecast tomorrow |
| 13 | Hausverbrauch | fast | Calculated: PV - Battery - Grid (kW, MEASUREMENT) |
| 14 | Entscheidung | 30s | Current optimizer state + Markdown dashboard |

### Select Entity

| Entity | Options | Description |
|--------|---------|-------------|
| `select.eeg_energy_optimizer_optimizer` | Ein / Test | Optimizer mode — Ein executes inverter commands, Test is dry-run (Aus is internal state only) |

### Optimizer States

- **Morgen-Einspeisung**: Battery charging blocked to maximize morning EEG feed-in
- **Abend-Entladung**: Battery discharging for evening EEG feed-in
- **Normal**: Standard operation (inverter in auto mode)

### Activity Log

- **Ring buffer**: 5000 entries (`collections.deque`), persisted via `homeassistant.helpers.storage.Store`
- **Logging**: At fixed quarter-hours (:00, :15, :30, :45) as heartbeat + on every state change
- **API**: Paginated WebSocket endpoint (`get_activity_log` with `offset`/`limit`)
- **Frontend**: Loads 100 entries initially, "Mehr laden" fetches 100 more per click, live events via subscription

### WebSocket API (12 commands)

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

### Inverter Abstraction

```
InverterBase (ABC)
  ├── async_set_charge_limit(power_kw) → bool
  ├── async_set_discharge(power_kw, target_soc) → bool
  ├── async_stop_forcible() → bool
  └── is_available → bool

Implementations:
  └── HuaweiInverter — via HA huawei_solar services
```

### Dependencies

- **recorder** — long-term hourly statistics for consumption history
- **sun** — sunrise/sunset calculations
- **http**, **frontend**, **websocket_api** — onboarding panel
- **huawei_solar** (after_dependency) — Huawei inverter control
- **solcast_solar**, **forecast_solar** (after_dependency) — PV forecasts

## Key Domain Concepts

- **Morning Charge Blocking**: Prevents battery from charging during morning hours so PV surplus feeds into the grid when the EEG community needs it most. Active when PV forecast exceeds demand + safety buffer.
- **Evening Discharge**: Discharges battery into grid during evening hours when community demand is high. Requires: sufficient SOC above dynamic min-SOC, and tomorrow's PV forecast covers tomorrow's demand.
- **Dynamic Min-SOC**: base_min_soc + ceil((overnight_consumption * (1 + buffer%) / capacity) * 100) — ensures enough energy for overnight household consumption.
- **Safety Buffer** (`safety_buffer_pct`, default 25%): Applied to both morning blocking threshold and overnight consumption reserve.
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

Config entry version: 9 (migrations in `__init__.py`)

## Development Notes

- Tests in `tests/` directory, run with `pytest` (asyncio_mode=auto)
- `pyproject.toml` configures pytest
- All UI strings in German (`strings.json`, `translations/de.json`), English fallback (`translations/en.json`)
- HA imports are guarded with try/except for test environment compatibility (stubs provided)
- The optimizer calculates every cycle but only executes inverter commands when mode is "Ein"
- Config changes trigger full integration reload via `_async_update_listener`
- `__pycache__/` directories should be added to `.gitignore`
