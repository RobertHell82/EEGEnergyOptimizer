---
phase: 1
slug: foundation-inverter-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-homeassistant-custom-component |
| **Config file** | `pyproject.toml` (to be created in Wave 0) |
| **Quick run command** | `pytest tests/ -x --timeout=10` |
| **Full suite command** | `pytest tests/ --timeout=30` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x --timeout=10`
- **After every plan wave:** Run `pytest tests/ --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | INF-01 | unit | `pytest tests/test_inverter_base.py -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 0 | INF-01 | unit | `pytest tests/test_inverter_factory.py -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | INF-02 | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | INF-02 | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | ❌ W0 | ⬜ pending |
| 01-02-03 | 02 | 1 | INF-02 | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 1 | INF-03 | unit | `pytest tests/test_manifest.py -x` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 1 | INF-03 | unit | `pytest tests/test_manifest.py -x` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | INF-03 | unit (mock) | `pytest tests/test_config_flow.py -x` | ❌ W0 | ⬜ pending |
| 01-04-02 | 04 | 2 | INF-03 | unit (mock) | `pytest tests/test_config_flow.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures, mock hass instance
- [ ] `tests/test_inverter_base.py` — ABC contract tests (INF-01)
- [ ] `tests/test_inverter_factory.py` — factory pattern tests (INF-01)
- [ ] `tests/test_huawei_inverter.py` — Huawei service call mocks (INF-02)
- [ ] `tests/test_config_flow.py` — config flow step tests (INF-03)
- [ ] `tests/test_manifest.py` — manifest validation (INF-03)
- [ ] `pyproject.toml` — test configuration
- [ ] Framework install: `pip install pytest pytest-homeassistant-custom-component pytest-asyncio`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HACS installation from GitHub | INF-03 | Requires live HACS instance | Add repo URL in HACS, verify integration appears |
| Config flow entity picker UX | INF-03 | UI interaction | Open HA → Settings → Integrations → Add → verify dropdowns work |
| Live Huawei charge/discharge | INF-02 | Requires physical inverter | Issue charge command, verify inverter responds |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
