# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — EEG Energy Optimizer

**Shipped:** 2026-03-22
**Phases:** 6 | **Plans:** 14 | **Tasks:** 27

### What Was Built
- Abstract inverter interface (ABC + factory) with Huawei SUN2000 implementation
- PV forecast abstraction (Solcast + Forecast.Solar) and recorder-based consumption profiling
- EEG optimizer with morning charge blocking, evening discharge, dynamic min-SOC, safety guards
- Onboarding panel with 8-step wizard, live dashboard (SVG charts), WebSocket API
- Robustness hardening: safe dict access, error surfacing, persistent notifications
- Tech debt cleanup: explicit dry-run, ABC enforcement, dynamic entity IDs

### What Worked
- Gap closure phases (5+6) after milestone audit caught real issues before shipping
- Plain HTMLElement + Shadow DOM for panel — no build step, no CDN dependencies, 1892 LOC
- 1-click config flow + panel wizard pattern — clean separation of concerns
- Factory pattern for inverters — adding Fronius later requires only a new file
- Parallel plan execution in Wave 1 — both 06-01 and 06-02 ran concurrently

### What Was Inefficient
- Phase 3+4 roadmap checkboxes not updated during execution (manual fix needed)
- Milestone audit found 8 tech debt items that could have been caught earlier with per-phase verification
- No test framework set up — all verification is code-level (grep, AST parse), no runtime tests

### Patterns Established
- Snapshot/Decision dataclass pattern for optimizer state
- Duck typing for cross-module updates (update_from_decision) to avoid circular imports
- SENSOR_SUFFIXES map for dynamic entity ID resolution with fallback defaults
- setup_complete flag for gating features in wizard vs. post-setup

### Key Lessons
1. Per-phase verification catches tech debt early — don't defer all verification to milestone audit
2. Config flow VERSION migration is critical — bump version and add async_migrate_entry for every schema change
3. Shadow DOM panels need HA CSS variable passthrough for theme compatibility
4. Guard-delay pattern (suppress non-critical guards during EEG windows) is powerful for balancing safety vs. optimization

### Cost Observations
- Model mix: ~70% opus (planning + execution), ~30% sonnet (verification + checking)
- Timeline: 5 days (2026-03-18 to 2026-03-22)
- Notable: Gap closure phases (5+6) were lightweight — 3 plans total vs. 11 for core phases

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 6 | 14 | Initial milestone — established GSD workflow patterns |

### Cumulative Quality

| Milestone | Verification | Gap Closure | Tech Debt Items |
|-----------|-------------|-------------|-----------------|
| v1.0 | 6/6 phases verified | 2 phases (5+6) | 8 items resolved |

### Top Lessons (Verified Across Milestones)

1. Milestone audit + gap closure phases are an effective safety net before shipping
2. Abstract interfaces from day one pay off — clean extension points for future inverter types
