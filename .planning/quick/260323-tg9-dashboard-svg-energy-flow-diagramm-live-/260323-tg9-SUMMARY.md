---
phase: quick
plan: 260323-tg9
subsystem: frontend
tags: [dashboard, svg, energy-flow, live-values]
dependency_graph:
  requires: []
  provides: [energy-flow-diagram, live-values-card]
  affects: [eeg-optimizer-panel]
tech_stack:
  added: []
  patterns: [inline-svg, css-animation, stroke-dashoffset]
key_files:
  modified:
    - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
decisions:
  - Used unicode symbols for node icons (sun, battery, house, lightning) instead of mdi icons for SVG compatibility
  - Diamond/cross layout with PV top, Battery left, House right, Grid bottom
  - 50W threshold for flow line visibility to avoid visual noise from measurement jitter
metrics:
  duration: 3min
  completed: "2026-03-23T20:19:00Z"
  tasks: 1
  files: 1
---

# Quick Plan 260323-tg9: Dashboard SVG Energy Flow Diagram + Live Values Summary

Animated SVG energy flow diagram with 4 nodes (PV, Battery, House, Grid) and directional flow lines plus live values card showing real-time power/SOC readings with color coding.

## Task Results

### Task 1: Add SVG Energy Flow Diagram and Live Values Card

**Commit:** 96ee638

Added two new render methods to the dashboard panel:

**`_renderEnergyFlow()`** - Inline SVG (300x270 viewBox) with:
- 4 nodes in diamond layout: PV (top, circle), Battery (left, rounded rect), House (right, rounded rect), Grid (bottom, circle)
- Flow lines between nodes with CSS stroke-dashoffset animation for direction indication
- Line thickness scales with power magnitude (1.5-6px for 0-3000W)
- Color coding: green (#4CAF50) for PV/export, orange (#FF9800) for battery, red (#f44336) for grid import
- 50W threshold - lines only visible when power exceeds threshold
- Node values displayed in kW with appropriate colors
- Battery node also shows SOC% with traffic-light coloring

**`_renderLiveValues()`** - CSS grid card with:
- PV Leistung (green), Batterie with charge/discharge label (orange), SOC% (color by level), Netz with import/export label (red/green), Hausverbrauch (blue)
- All values in kW (1 decimal), SOC in % (0 decimals)
- Max charge power shown as subtitle on SOC row

Both cards inserted between timestamps row and charts section, using existing `status-cards-row` flex layout for side-by-side on desktop, stacking on narrow/mobile.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED
