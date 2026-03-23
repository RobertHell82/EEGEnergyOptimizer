---
phase: quick-260323-ddr
plan: 01
subsystem: frontend
tags: [dashboard, charts, pv-forecast, weekday-profile]
key-files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - Grouped bars use half-width with 2px gap; PV color #FF9800 (amber) for theme compatibility
  - Multi-weekday chart height increased from 250 to 280 to fit legend below x-axis
  - Background weekday lines at 20% opacity to avoid visual clutter
metrics:
  duration: 3min
  completed: "2026-03-23T08:46:00Z"
  tasks: 3
  files: 1
---

# Quick Task 260323-ddr: Dashboard PV Erzeugungsprognose + Wochentag-Profil Summary

Grouped bar chart showing consumption vs PV forecast (amber) side-by-side for 7 days, plus multi-weekday line chart with today highlighted at full opacity and other 6 weekdays as background lines.

## What Changed

### Task 1: Grouped Bar Chart (Energieprognose 7 Tage)

- `_renderBarChart(data, pvData = null)` now accepts optional PV data array
- When pvData provided: two bars per day slot (consumption left, PV right) with #FF9800 amber color
- PV bars only render for days with actual values (today + tomorrow from existing sensors)
- Legend at top-right: blue square "Verbrauch", amber square "PV Erzeugung"
- `_renderDashboard()` builds pvForecastData from pvHeute/pvMorgen sensor values
- Chart title changed: "Verbrauchsprognose (7 Tage)" to "Energieprognose (7 Tage)"
- Backward compatible: pvData=null renders original single-bar layout

### Task 2: Multi-Weekday Line Chart (Verbrauchsprofil Wochentage)

- `_renderLineChart(datasets, highlightIndex)` replaces old single-dataset signature
- Reads all 7 weekday_watts arrays from profilState attributes (mo_watts through so_watts)
- Today's weekday: stroke-width 2.5px, full primary-color, polygon area fill at 0.1 opacity
- Other 6 weekdays: stroke-width 1px, primary-color at 0.2 opacity, no area fill
- Compact legend below chart with line indicators and weekday labels (today bold)
- SVG height increased from 250 to 280 for legend space
- Chart title changed: "Verbrauchsprofil (Stundenmittel)" to "Verbrauchsprofil (Wochentage)"
- Empty datasets show "Keine Daten verfuegbar" message

### Task 3: Deployment

- Copied to /tmp/EEGEnergyOptimizer/ and pushed to GitHub (06e3577)

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1+2 | 54a57bf | feat(quick-260323-ddr): grouped bar chart + multi-weekday line chart |
| 3 | 06e3577 | Deployed to GitHub repo |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
