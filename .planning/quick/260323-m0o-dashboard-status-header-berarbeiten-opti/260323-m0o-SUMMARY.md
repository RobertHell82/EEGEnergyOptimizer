---
phase: quick-260323-m0o
plan: 01
subsystem: dashboard-status-cards
tags: [frontend, optimizer, sensor, dashboard]
dependency_graph:
  requires: []
  provides: [detailed-status-cards, morning-delay-status, discharge-status]
  affects: [optimizer.py, sensor.py, eeg-optimizer-panel.js]
tech_stack:
  added: []
  patterns: [status-card-rendering, condition-indicators]
key_files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/optimizer.py
    - custom_components/eeg_energy_optimizer/sensor.py
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - Flat fields on Decision dataclass (not nested dataclasses) for simple HA attribute serialization
  - Status card rendering extracted to _renderStatusCards() method for clean separation
  - Mode badge placed at bottom of Abend-Entladung card (subtle, not prominent)
metrics:
  duration: 3min
  completed: "2026-03-23"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Quick Task 260323-m0o: Dashboard Status-Header ueberarbeiten Summary

Two side-by-side status cards (Verzogerte Ladung + Abend-Entladung) with detailed state, reasoning text, and condition indicators replacing the single Optimizer Status card.

## What Was Done

### Task 1: Extended Decision dataclass with detailed status fields (7551c4c)

Added 15 new fields to the Decision dataclass split into two groups:
- **Morning delay**: morning_status, morning_reason, morning_in_window, morning_pv_today_kwh, morning_threshold_kwh, morning_end_time, morning_sunrise_tomorrow
- **Discharge**: discharge_status, discharge_reasons, discharge_soc, discharge_min_soc, discharge_pv_tomorrow_kwh, discharge_demand_tomorrow_kwh, discharge_power_kw, discharge_start_time

Added two new methods:
- `_morning_delay_status()`: Computes 5 morning states (aktiv, nicht_aktiv, morgen_erwartet, morgen_nicht_erwartet, deaktiviert)
- `_discharge_detail_status()`: Computes 4 discharge states (aktiv, geplant, nicht_geplant, deaktiviert) by separating time-reasons from condition-reasons

### Task 2: Sensor attributes and dashboard status cards (7885d0d)

- Extended `update_from_decision()` to expose all 15 new fields as HA entity attributes
- Replaced the single "Optimizer Status" card with `_renderStatusCards()` method producing two side-by-side cards
- Left card: Verzogerte Ladung with sun icon, status text, and PV/threshold condition rows
- Right card: Abend-Entladung with moon icon, status text, SOC/PV condition rows with check/cross markers
- Added CSS: `.status-cards-row`, `.status-indicator`, `.condition-row`, `.status-divider`, responsive narrow breakpoint
- Mode badge moved to subtle line at bottom of right card

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None - all data flows are wired end-to-end from optimizer through sensor attributes to panel rendering.

## Self-Check: PASSED
