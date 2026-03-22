---
phase: 02
slug: forecasting-consumption-profile
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-21
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-homeassistant-custom-component |
| **Config file** | `pyproject.toml` (from Phase 1) |
| **Quick run command** | `pytest tests/ -x --timeout=10` |
| **Full suite command** | `pytest tests/ --timeout=30` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x --timeout=10`
- **After every plan wave:** Run `pytest tests/ --timeout=30`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

*To be filled by planner after plan creation — maps each task to its automated verify command.*

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | FCST-01 | unit (mock) | `pytest tests/test_pv_forecast.py -x` | No — Wave 0 | ⬜ pending |
| TBD | TBD | TBD | FCST-02 | unit (mock) | `pytest tests/test_pv_forecast.py -x` | No — Wave 0 | ⬜ pending |
| TBD | TBD | TBD | FCST-03 | unit (mock) | `pytest tests/test_consumption_profile.py -x` | No — Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pv_forecast.py` — stubs for FCST-01, FCST-02 (Solcast + Forecast.Solar provider tests)
- [ ] `tests/test_consumption_profile.py` — stubs for FCST-03 (recorder statistics, 7-day grouping)
- [ ] `tests/test_sensors.py` — stubs for sensor entity creation, update intervals

*Phase 1 test infrastructure (conftest.py, pyproject.toml) is reused.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Solcast entity reads on live HA | FCST-01 | Requires live Solcast installation | Check sensor.solcast_pv_forecast_today reads correct value |
| Forecast.Solar entity reads on live HA | FCST-02 | Requires live Forecast.Solar installation | Check sensor.energy_production_today reads correct value |
| Recorder statistics over real 8-week window | FCST-03 | Requires real historical data | Verify consumption profile averages match HA history |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
