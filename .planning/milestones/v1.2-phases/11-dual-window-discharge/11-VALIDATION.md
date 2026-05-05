---
phase: 11
slug: dual-window-discharge
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-04
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (asyncio_mode=auto) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/test_dual_window.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~30 seconds (full suite), ~5 seconds (dual-window only) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_dual_window.py -x -q` plus the targeted test module the task touches (e.g. `tests/test_optimizer.py`, `tests/test_config_flow.py`).
- **After every plan wave:** Run `pytest tests/ -q`.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 30 seconds.

---

## Per-Task Verification Map

> Filled by the planner during plan generation. Each plan's `<verify>` block must list the test commands that validate its acceptance criteria. Manual 7-day UAT (SPEC Acceptance §12) is tracked separately in the Manual-Only section.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | — | — | REQ-1..9 (SPEC) | — | N/A | unit / integration | `pytest tests/test_dual_window.py::<test>` | ⬜ planner | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_dual_window.py` — neue Datei für Dual-Window-spezifische Tests (Slot-A/B-Window-Resolution, SA-Adaption, Reserve-Logik, Pro-Slot-Hysterese, SolarEdge-XOR, 24h-Decision-Sequenzen)
- [ ] `tests/conftest.py` — Helper-Fixtures (`make_optimizer_dual`, `make_snapshot_at`, `freeze_sunrise`) — extrahiert aus bestehenden `test_optimizer.py`-Mustern
- [ ] Bestehende `pytest`-Infrastruktur (asyncio_mode=auto, conftest in tests/) deckt alle anderen Anforderungen ab — kein Framework-Install nötig

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 7-Tage-UAT-Beobachtung an Test-HA-Instanz (Huawei 192.168.1.211 oder Fronius 192.168.100.211) | SPEC Acceptance §12 | Reale EEG-Bedarfsdaten, reale PV-Schwankung und reale Inverter-Reaktion lassen sich nicht simulieren; finale "gute Idee oder nicht"-Bewertung durch User | 1. Update auf v1.2.0-dev installieren. 2. Default-Migration prüfen (Dual=ON). 3. Activity-Log auf Slot-A-Aktivierungen 20:00–23:00 und Slot-B-Aktivierungen 03:00–07:00 monitoren. 4. Telemetrie-Backend prüfen, ob neue Reasons ankommen. 5. Mind. 7 zusammenhängende Tage. 6. User-Bewertung "akzeptiert/verworfen" notieren. |
| Onboarding-Panel-Hinweis bei SolarEdge ("NVRAM-Verschleiß: nur ein Slot pro Tag möglich") | SPEC Req 6 | Visuelle Korrektheit (Tooltip-Position, Radio-Default = Slot A) ist Pixel-spezifisch | 1. SolarEdge-Setup im Wizard auswählen. 2. Discharge-Sektion öffnen. 3. Master-Toggle muss DEAKTIVIERT sichtbar sein. 4. Stattdessen Radio "Slot A (Abend) / Slot B (Morgen)" mit Default Slot A. 5. Tooltip-Text wörtlich prüfen. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
