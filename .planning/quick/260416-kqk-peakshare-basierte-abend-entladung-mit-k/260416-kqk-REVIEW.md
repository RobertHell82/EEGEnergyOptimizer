---
phase: 260416-kqk
reviewed: 2026-04-16T12:00:00Z
depth: quick
files_reviewed: 8
files_reviewed_list:
  - CLAUDE.md
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
  - custom_components/eeg_energy_optimizer/optimizer.py
  - custom_components/eeg_energy_optimizer/peakshare.py
  - custom_components/eeg_energy_optimizer/websocket_api.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 260416-kqk: Code Review Report

**Reviewed:** 2026-04-16T12:00:00Z
**Depth:** quick
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Quick pattern-matching review of the PeakShare integration feature. The new `peakshare.py` module is well-structured with proper API validation, caching, and graceful fallback. One critical bug was found in the sliding window algorithm where non-contiguous hours are treated as contiguous, which can produce incorrect discharge windows. Three warnings relate to an unclamped end_time that can exceed the hard 04:00 cutoff, potential XSS via innerHTML with entity data, and a timezone inconsistency in the jitter date check. Two info items cover broad exception handling and console.error statements in the frontend.

## Critical Issues

### CR-01: Sliding window treats non-contiguous hours as contiguous

**File:** `custom_components/eeg_energy_optimizer/peakshare.py:76-107`
**Issue:** The `find_discharge_window` function filters eligible hours to only those with `deficit > 0`, removing hours with zero or negative deficit. After filtering, the sliding window assumes adjacent list elements are consecutive hours. However, if hour 19 has deficit > 0, hour 20 has deficit = 0, and hour 21 has deficit > 0, then hours 19 and 21 appear adjacent in the `eligible` list. The algorithm would select them as a "contiguous 2-hour block" even though there is a gap at hour 20. The resulting discharge window would span 19:00-21:00 (2 hours from start), but the community demand at 20:00 is actually zero — the window is not truly optimal.
**Fix:** Either (a) include all hours in the window (even zero-deficit ones) and only optimize the sum, or (b) add a contiguity check that verifies consecutive elements are exactly 1 hour apart:
```python
# Option (b): verify contiguity in the sliding window
for i in range(1, len(eligible) - required_hours + 1):
    current_sum -= eligible[i - 1]["deficit"]
    current_sum += eligible[i + required_hours - 1]["deficit"]
    # Check all hours in window are consecutive
    is_contiguous = all(
        (eligible[i + j + 1]["ts"] - eligible[i + j]["ts"]).total_seconds() == 3600
        for j in range(required_hours - 1)
    )
    if is_contiguous and current_sum > best_sum:
        best_sum = current_sum
        best_start = i
```

## Warnings

### WR-01: Discharge end_time not clamped to window_end (04:00 hard cutoff)

**File:** `custom_components/eeg_energy_optimizer/peakshare.py:110-115`
**Issue:** After applying jitter, `end_time = start_time + timedelta(hours=required_hours)` can exceed `window_end` (04:00). While the optimizer has its own 04:00 cutoff check, the PeakShare plan itself returns an end_time past 04:00, which is displayed to the user on the dashboard and could cause confusion. If the optimizer trusts the PeakShare window end for any future logic, discharge could run past the hard cutoff.
**Fix:**
```python
end_time = start_time + timedelta(hours=required_hours)
if end_time > window_end:
    end_time = window_end
return (start_time, end_time)
```

### WR-02: innerHTML with unsanitized entity names (potential XSS)

**File:** `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js:1920-1924`
**Issue:** Entity names (`e.name`) and friendly names (`friendly`) from Home Assistant state objects are interpolated directly into HTML via innerHTML without escaping. While HA entity names are typically safe, a malicious or corrupted integration could inject HTML/JS through a crafted friendly_name attribute. This also applies to lines 1949 and 1953 where `sv` (sensor state value) and `friendly` are interpolated into innerHTML.
**Fix:** Create a simple escape helper and use it before inserting into innerHTML:
```javascript
const esc = (s) => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
// Then use: esc(e.name), esc(friendly), esc(sv), etc.
```

### WR-03: Timezone inconsistency in jitter date check

**File:** `custom_components/eeg_energy_optimizer/peakshare.py:256`
**Issue:** `get_jitter_today()` uses `date.today().isoformat()` which returns the date in the server's local timezone. However, `get_discharge_plan()` at line 288 uses `now.strftime("%Y-%m-%d")` where `now` is the HA-aware local time (via `_now()` / `dt_util.now()`). If the server timezone and HA configured timezone differ, these could produce different date strings, causing jitter to be re-rolled when the discharge plan date and jitter date use different timezone bases.
**Fix:**
```python
def get_jitter_today(self) -> int:
    today = _as_local(_utcnow()).date().isoformat()
    # ... rest unchanged
```

## Info

### IN-01: Broad exception handling in peakshare.py

**File:** `custom_components/eeg_energy_optimizer/peakshare.py:178,232`
**Issue:** Two `except Exception:` blocks silently swallow all errors during cache load (line 178) and API fetch (line 232). While this is intentional for resilience (non-critical feature), it makes debugging API issues harder since no traceback is logged.
**Fix:** Consider using `_LOGGER.debug("...", exc_info=True)` instead of plain `_LOGGER.debug(...)` / `_LOGGER.warning(...)` to capture the traceback at debug level.

### IN-02: console.error statements in frontend JS

**File:** `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js:1436`
**Issue:** `console.error("Failed to load PeakShare communities:", e)` and several other console.error/warn calls are present. These are appropriate for a production panel (error reporting, not debug logging), so this is informational only.
**Fix:** No action needed. These are appropriate error-level logs for a custom panel.

---

_Reviewed: 2026-04-16T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: quick_
