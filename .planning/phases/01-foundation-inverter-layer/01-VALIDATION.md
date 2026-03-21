---
phase: 1
slug: foundation-inverter-layer
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-21
updated: 2026-03-21
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (standard mocks, no HA test component) |
| **Config file** | `pyproject.toml` (created in Plan 01 Task 2) |
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

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 01-01-T2 | 01 | 1 | INF-01, INF-03 | collect | `pytest tests/ --collect-only --timeout=10` | pending |
| 01-01-T1 | 01 | 1 | INF-01, INF-03 | unit | `pytest tests/test_inverter_base.py tests/test_inverter_factory.py tests/test_manifest.py -x --timeout=10` | pending |
| 01-02-T1 | 02 | 2 | INF-02 | unit (mock) | `pytest tests/test_huawei_inverter.py -x --timeout=10` | pending |
| 01-02-T2 | 02 | 2 | INF-02, INF-03 | unit (mock) | `pytest tests/test_config_flow.py tests/test_huawei_inverter.py -x --timeout=10` | pending |
| 01-02-T3 | 02 | 2 | INF-02, INF-03 | manual | Human verify: integration loads in HA, config flow works | pending |

*Status: pending / green / red / flaky*

**Note:** Plan 01 Task 2 (test infrastructure) executes before Task 1 (TDD). Task IDs reflect execution order within each plan.

---

## Wave 0 Requirements

Test files are created in Plan 01 Task 2 (first task executed due to TDD ordering):

- [ ] `pyproject.toml` — test configuration
- [ ] `tests/__init__.py` — package marker
- [ ] `tests/conftest.py` — shared fixtures, mock hass instance
- [ ] `tests/test_inverter_base.py` — ABC contract tests (INF-01)
- [ ] `tests/test_inverter_factory.py` — factory pattern tests (INF-01)
- [ ] `tests/test_manifest.py` — manifest + hacs.json + README validation (INF-03)
- [ ] Framework install: `pip install pytest pytest-asyncio pytest-timeout`

Additional test files created in Plan 02 Task 1-2:

- [ ] `tests/test_huawei_inverter.py` — Huawei service call mocks (INF-02)
- [ ] `tests/test_config_flow.py` — config flow step tests (INF-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| HACS installation from GitHub | INF-03 | Requires live HACS instance | Add repo URL in HACS, verify integration appears |
| Config flow entity picker UX | INF-03 | UI interaction | Open HA > Settings > Integrations > Add > verify dropdowns work |
| Live Huawei charge/discharge | INF-02 | Requires physical inverter | Issue charge command, verify inverter responds |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all test file creation
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
