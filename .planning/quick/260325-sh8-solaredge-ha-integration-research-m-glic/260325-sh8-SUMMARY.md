---
phase: quick
plan: 260325-sh8
subsystem: inverter
tags: [research, solaredge, storedge, modbus, inverter-abstraction]
dependency_graph:
  requires: []
  provides: [solaredge-integration-research, solaredge-inverter-feasibility]
  affects: [inverter/base.py, inverter/__init__.py]
tech_stack:
  added: []
  patterns: [command-mode-battery-control, modbus-tcp-entity-control]
key_files:
  created: [SOLAREDGE_RESEARCH.md]
  modified: []
decisions:
  - "solaredge-modbus-multi (WillCodeForCats HACS) is the only viable integration for StorEdge battery control"
  - "SolarEdge uses command mode paradigm (not direct power setpoint) -- charge blocking and forced discharge are feasible but power is ceiling-based"
  - "Command persistence in non-volatile memory requires startup recovery logic (unlike Huawei auto-revert)"
  - "StorEdge backup_reserve entity maps well to target_soc for discharge floor"
metrics:
  duration: 3min
  completed: 2026-03-25
  tasks: 1
  files: 1
---

# Quick Task 260325-sh8: SolarEdge HA Integration Research Summary

**One-liner:** SolarEdge StorEdge battery control feasible via solaredge-modbus-multi using command mode switching and power limit entities

## What Was Done

Researched all SolarEdge Home Assistant integrations and assessed their suitability for implementing a `SolarEdgeInverter` class against the existing `InverterBase` ABC. Produced a comprehensive research document (SOLAREDGE_RESEARCH.md, 457 lines) covering:

1. Three integrations evaluated: official `solaredge` (cloud, read-only), core `solaredge_modbus` (local, limited write), and `solaredge-modbus-multi` (HACS, full StorEdge control)
2. Complete sensor entity inventory for the recommended integration
3. StorEdge command mode paradigm mapped to all four ABC methods
4. Side-by-side comparison with existing Huawei implementation
5. Seven common pitfalls documented (persistent command mode, single Modbus client, etc.)
6. Full feasibility assessment table with confidence ratings

## Key Findings

- **Feasibility: YES** -- all four InverterBase methods can be implemented
- **Recommended integration:** `solaredge-modbus-multi` (HACS, by WillCodeForCats)
- **Control paradigm:** Command mode switching (Maximize Export, Discharge to Maximize Export, Maximize Self Consumption) + power limit entities
- **Key difference from Huawei:** SolarEdge uses ceiling-based power limits (not exact setpoints), and commands persist in non-volatile memory (Huawei auto-reverts)
- **Target SOC:** Uses `storage_backup_reserve` entity as discharge floor -- functionally equivalent to Huawei's target_soc parameter
- **Critical risk:** Command persistence requires startup recovery logic to avoid leaving battery in unintended export mode after crash

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | bc3443e | SolarEdge research document (457 lines, 10 sections) |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- SOLAREDGE_RESEARCH.md: FOUND (457 lines, 11 sections)
- Commit bc3443e: FOUND
- SUMMARY.md: FOUND
