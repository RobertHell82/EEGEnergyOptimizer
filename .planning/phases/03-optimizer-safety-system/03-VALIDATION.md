---
phase: 3
slug: optimizer-safety-system
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | none — Wave 0 installs |
| **Quick run command** | `pytest tests/test_optimizer.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_optimizer.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | OPT-01 | unit | `pytest tests/test_optimizer.py -k morning` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | OPT-02, OPT-03 | unit | `pytest tests/test_optimizer.py -k discharge` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | SAF-03 | unit | `pytest tests/test_optimizer.py -k surplus` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | SAF-04 | unit | `pytest tests/test_optimizer.py -k test_mode` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | SENS-01 | unit | `pytest tests/test_sensors.py -k decision` | ❌ W0 | ⬜ pending |
| 03-02-02 | 02 | 2 | SENS-02 | unit | `pytest tests/test_sensors.py -k preview` | ❌ W0 | ⬜ pending |
| 03-02-03 | 02 | 2 | SENS-03 | unit | `pytest tests/test_sensors.py -k eeg_window` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_optimizer.py` — stubs for OPT-01, OPT-02, OPT-03, SAF-03, SAF-04
- [ ] `tests/test_sensors.py` — stubs for SENS-01, SENS-02, SENS-03
- [ ] `tests/conftest.py` — shared fixtures (mock hass, mock inverter, mock forecast provider)
- [ ] `pytest` — install if not present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Select entity persists across HA restart | SAF-04 | Requires HA restart cycle | 1. Set mode to Test, 2. Restart HA, 3. Verify mode is still Test |
| Inverter commands reach Huawei | OPT-01, OPT-02 | Requires live hardware | Verify via Huawei Solar integration logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
