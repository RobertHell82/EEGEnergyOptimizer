---
phase: 04-onboarding-panel
plan: 02
status: complete
started: "2026-03-22T18:00:00Z"
completed: "2026-03-22T21:30:00Z"
duration_minutes: 210
---

# Plan 04-02 Summary: Setup Wizard

## What Was Built

Complete 8-step setup wizard inside the onboarding panel with guided configuration flow.

## Key Files

### Created
(none — all changes in existing file)

### Modified
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` — Full wizard implementation
- `custom_components/eeg_energy_optimizer/optimizer.py` — New energy demand formula, feature flags, overnight consumption logic
- `custom_components/eeg_energy_optimizer/const.py` — Added CONF_ENABLE_MORNING_DELAY, CONF_ENABLE_NIGHT_DISCHARGE
- `custom_components/eeg_energy_optimizer/websocket_api.py` — Added test_inverter WebSocket command
- `custom_components/eeg_energy_optimizer/__init__.py` — Migration v5, platforms_loaded tracking, unload fix
- `custom_components/eeg_energy_optimizer/config_flow.py` — VERSION bump to 5
- `custom_components/eeg_energy_optimizer/sensor.py` — energiebedarf_kwh attribute (replacing ueberschuss_faktor)

## Wizard Steps (8 total)

1. **Willkommen** — Welcome screen with setup start
2. **Wechselrichter** — Inverter type selection (card-based, Huawei + placeholder)
3. **Prognose** — Forecast source selection (Solcast/Forecast.Solar cards) + sensor entity pickers inline
4. **Batterie** — SOC sensor, capacity mode (manual/sensor tiles), auto-detection from Huawei
5. **Verbrauch** — Consumption sensor picker
6. **Ladung & Einspeisung** — Feature toggles for morning delay + night discharge with parameters
7. **Erweiterte Einstellungen** — Lookback weeks, update intervals
8. **Zusammenfassung** — Review all settings before save

## Key Features Implemented

- **Custom autocomplete entity pickers** with dropdown, chevron arrow, and live sensor value preview
- **Card-based selection** for capacity mode (manual/sensor) with HA icons
- **Feature toggle cards** for verzögerte Batterieladung and Nachteinspeisung (individually activatable)
- **Inverter test button** on dashboard (WebSocket → stop_forcible as safe no-op)
- **New optimizer logic**: Energiebedarf = Verbrauch bis SU + fehlende Batterieenergie; replaces Überschuss-Faktor
- **Overnight consumption**: calculated from discharge start (or now) to sunrise + 1h
- **Safety buffer** applies to both features (shared "Allgemeine Einstellungen")
- **Config migration v5**: adds enable_morning_delay, enable_night_discharge; removes ueberschuss_schwelle
- **Unload fix**: tracks platforms_loaded to prevent ValueError on reload after wizard completion

## Deviations from Plan

1. **Wizard reduced from planned steps**: Optimizer-Parameter and Prognose-Sensoren steps were merged into other steps for better UX flow
2. **Überschuss-Schwelle removed**: Replaced by energy demand formula (consumption to sunset + missing battery) × (1 + safety buffer)
3. **Feature flags added**: enable_morning_delay and enable_night_discharge allow individual activation
4. **Inverter test button**: Added beyond plan scope for post-setup validation

## Self-Check: PASSED

All wizard steps render correctly, config saves via WebSocket, validation works per step.
