---
phase: 4
slug: onboarding-panel
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Manual browser testing + pytest for WebSocket commands |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/test_panel_ws.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds (backend) + manual (frontend) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_panel_ws.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green + manual panel check
- **Max feedback latency:** 5 seconds (backend)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | INF-04 | unit | `pytest tests/test_panel_ws.py -k ws_commands` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | INF-04 | manual | Browser: panel loads in sidebar | N/A | ⬜ pending |
| 04-02-01 | 02 | 2 | INF-04 | manual | Browser: wizard steps navigate | N/A | ⬜ pending |
| 04-02-02 | 02 | 2 | INF-04 | manual | Browser: prerequisite checks block | N/A | ⬜ pending |
| 04-03-01 | 03 | 3 | INF-04 | manual | Browser: dashboard shows live data | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_panel_ws.py` — stubs for WebSocket command tests
- [ ] `tests/conftest.py` — update with panel-related fixtures
- [ ] `pytest` — already installed from prior phases

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Panel appears in HA sidebar | INF-04 | Requires running HA instance | 1. Install integration, 2. Check sidebar for "EEG Optimizer" |
| Wizard steps navigate correctly | INF-04 | UI interaction testing | 1. Open panel, 2. Click through all wizard steps |
| Prerequisite check blocks when missing | INF-04 | Requires HA with/without integrations | 1. Remove Huawei Solar, 2. Verify wizard blocks with guidance |
| Entity picker shows correct sensors | INF-04 | Requires HA entity registry | 1. With Huawei Solar installed, 2. Verify auto-detection works |
| Dashboard shows live sensor data | INF-04 | Requires running sensors | 1. Complete wizard, 2. Verify dashboard updates via WebSocket |
| Charts render consumption data | INF-04 | Visual verification | 1. Open dashboard, 2. Verify bar chart and line chart render |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
