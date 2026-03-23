# Quick Task 260323-q66: Tagesverbrauch SA->SU Sensor - Research

**Researched:** 2026-03-23
**Domain:** Optimizer consumption calculation, sensor platform
**Confidence:** HIGH

## Summary

The task adds a daylight-only consumption forecast (sunrise-to-sunset) that replaces the full-day consumption in the morning delay decision. The coordinator already has `calculate_period(start, end)` which sums hourly averages for arbitrary time ranges -- we just need to call it with sunrise/sunset boundaries instead of midnight-to-midnight.

**Primary recommendation:** Add a helper method on `EEGOptimizer` (or inline in `_gather_snapshot`) that calculates SA->SU consumption using the coordinator, and store it in new Snapshot fields. The morning delay logic swaps this value in where it currently uses full-day consumption. Optionally expose as a HA sensor for transparency.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Sensor is **only for Morgen-Verzoegerungs-Entscheidung** (morning delay), evening discharge unchanged
- Replaces consumption input in threshold formula: `threshold = (tagesverbrauch_SA_SU + fehlende_batterie) * (1 + puffer%)`
- Buffer and missing battery energy stay as-is
- Before `morning_end_time`: use **today's** SA->SU consumption
- From `morning_end_time` onward: use **tomorrow's** SA->SU consumption
- No additional dashboard lines -- existing "Bedarf + Puffer" line shows the new (lower) value automatically

### Claude's Discretion
- Sensor name and entity ID
- Whether exposed as a real HA sensor or computed internally in the optimizer only
</user_constraints>

## Architecture Analysis

### Current Flow (Morning Delay)

```
_gather_snapshot():
  consumption_today_kwh = coordinator.calculate_period(now, end_of_day)     # full remaining day
  consumption_tomorrow_kwh = coordinator.calculate_period(tomorrow_start, tomorrow_end)  # full 24h
  consumption_to_sunset_kwh = coordinator.calculate_period(now, sunset)      # now -> sunset

_calc_energiebedarf(snap):
  return snap.consumption_to_sunset_kwh + missing_battery_kwh

_should_block_charging(snap):
  bedarf = _calc_energiebedarf(snap)
  schwelle = bedarf * (1 + safety_buffer_pct / 100)
  return pv_today > schwelle

_morning_delay_status(snap, bedarf):
  # When OUTSIDE window (preview for tomorrow):
  tomorrow_demand = snap.consumption_tomorrow_kwh + missing_battery_est     # <-- uses FULL day
  tomorrow_threshold = tomorrow_demand * (1 + safety_buffer_pct / 100)
```

### Problem

1. **`_calc_energiebedarf()`** uses `consumption_to_sunset_kwh` (now -> sunset) which is already somewhat daylight-scoped but includes the current partial hour. This is used for the **in-window** decision. This is close to correct but includes early morning hours before sunrise if called before sunrise.

2. **`_morning_delay_status()`** for the **tomorrow preview** (outside window) uses `consumption_tomorrow_kwh` which is a full 24h value. This is the main target -- it should use SA->SU only.

### What Needs to Change

#### 1. New Snapshot Fields

Add to `Snapshot` dataclass:
```python
consumption_today_daylight_kwh: float = 0.0    # today SA -> SU
consumption_tomorrow_daylight_kwh: float = 0.0  # tomorrow SA -> SU
```

#### 2. Computing Sunrise/Sunset for Tomorrow

**Critical insight:** `sun.sun` entity only provides `next_rising` and `next_setting`. These are always the *next* occurrence:
- Before sunrise: `next_rising` = today's sunrise, `next_setting` = today's sunset
- After sunrise, before sunset: `next_rising` = tomorrow's sunrise, `next_setting` = today's sunset
- After sunset: `next_rising` = tomorrow's sunrise, `next_setting` = tomorrow's sunset

For **today's SA->SU**: We need today's sunrise and today's sunset. If we're already past sunrise, `next_rising` is tomorrow's -- so we need to handle this carefully.

**Recommended approach:** Use approximate sunrise/sunset hours from the coordinator's hourly resolution. Since the coordinator works with integer hours anyway, we can:
- Use `sun.sun` attributes `next_rising`/`next_setting` to get today's times
- For tomorrow: estimate sunrise/sunset from today's values +/- 1 minute (negligible difference day-to-day)
- Or: hardcode a reasonable approach -- use `next_rising` hour and `next_setting` hour as boundaries

**Simpler approach (recommended):** Since `calculate_period()` works with `datetime` objects, and we need sunrise/sunset of specific days:
- **Today:** sunrise = if `next_rising` is today, use it; else approximate from yesterday's sunrise (today_date + sunrise_hour). For sunset: if `next_setting` is today, use it.
- **Tomorrow:** sunrise_tomorrow ~ sunrise_today + timedelta(days=1), sunset_tomorrow ~ sunset_today + timedelta(days=1)

**Even simpler:** The optimizer already has `snap.sunrise` and `snap.sunset` from `_get_sun_times()`. For the hourly-resolution coordinator, rounding to the nearest hour is perfectly acceptable. So:
- Today's daylight consumption: `calculate_period(today_sunrise, today_sunset)`
- Tomorrow's daylight consumption: `calculate_period(tomorrow_sunrise, tomorrow_sunset)`

Where sunrise/sunset can be derived:
- `snap.sunrise` is `next_rising` -- could be today or tomorrow
- `snap.sunset` is `next_setting` -- could be today or tomorrow

**Best approach for `_gather_snapshot()`:**

```python
# Derive today and tomorrow sun times
today_date = now.date()
tomorrow_date = today_date + timedelta(days=1)

# sun.sun gives next_rising/next_setting
# Derive today/tomorrow sunrise/sunset by checking dates
if sunrise is not None and sunset is not None:
    # For today: use known times or shift by -1/+1 day
    if sunrise.date() == today_date:
        today_sunrise = sunrise
    else:
        # next_rising is tomorrow -> today's sunrise was ~24h earlier
        today_sunrise = sunrise - timedelta(days=1)

    if sunset.date() == today_date:
        today_sunset = sunset
    else:
        today_sunset = sunset - timedelta(days=1)

    # Tomorrow: shift today's times by +1 day (accurate enough for hourly resolution)
    tomorrow_sunrise = today_sunrise + timedelta(days=1)
    tomorrow_sunset = today_sunset + timedelta(days=1)

    consumption_today_daylight = coordinator.calculate_period(
        max(today_sunrise, now),  # don't count past hours
        today_sunset
    ).get("verbrauch_kwh", 0.0)

    consumption_tomorrow_daylight = coordinator.calculate_period(
        tomorrow_sunrise, tomorrow_sunset
    ).get("verbrauch_kwh", 0.0)
```

#### 3. Integration Points in Optimizer

**A. `_calc_energiebedarf()` (line 414-431)**

Currently uses `snap.consumption_to_sunset_kwh`. This is called by `_should_block_charging()` during the in-window check.

The CONTEXT says: replace consumption input in threshold formula. Currently `_calc_energiebedarf()` already uses now->sunset. The new sensor should use full SA->SU for consistency with the "what does today's total daylight consumption look like" question.

**However**, for the in-window case (morning, before morning_end_time), the relevant question is "can today's PV cover today's daylight consumption + battery?" -- using `consumption_today_daylight_kwh` is correct here.

Change `_calc_energiebedarf()` to accept a consumption parameter, or add a new method. The switch logic:
- Before `morning_end_time`: use `snap.consumption_today_daylight_kwh`
- After `morning_end_time`: use `snap.consumption_tomorrow_daylight_kwh`

**B. `_morning_delay_status()` (line 296-367)**

- **In-window path (line 338-344):** Uses `bedarf` which comes from `_calc_energiebedarf()`. If we change energiebedarf to use daylight consumption, this is automatically updated.
- **Outside-window path (line 346-365):** Computes `tomorrow_demand = snap.consumption_tomorrow_kwh + missing_battery_est`. This must change to `snap.consumption_tomorrow_daylight_kwh`.

**C. `_should_block_charging()` (line 433-466)**

Calls `_calc_energiebedarf(snap)` -- automatically picks up changes.

#### 4. Sensor Exposure (Optional)

The DailyForecastSensor pattern (sensors 2-8) shows how to add forecast sensors. A daylight consumption sensor would follow the same pattern but filter hours.

**Recommendation:** Expose as a real sensor for debugging/transparency. Name: "Tagesverbrauch Tageslicht" or "Verbrauch SA-SU heute" / "morgen". But per discretion, could also be internal-only.

### Coordinator Usage

`calculate_period(start, end)` is the key method. It:
- Walks hour by hour from `start` to `end`
- Looks up `hourly_avg[weekday_key][hour]` (watts)
- Handles partial hours at boundaries
- Returns `{"verbrauch_kwh": float, "stunden": float, "stundenprofil": list}`

Data is stored as `{weekday: {hour: avg_watts}}` -- 7 weekdays x 24 hours. Already weekday-aware, so tomorrow's calculation uses the correct weekday profile.

## Common Pitfalls

### Pitfall 1: Sun Time Date Ambiguity
**What goes wrong:** `sun.sun` `next_rising`/`next_setting` change meaning depending on time of day. After sunrise, `next_rising` jumps to tomorrow.
**How to avoid:** Always check `.date()` of the returned datetime against today/tomorrow before using it. Derive both today and tomorrow times explicitly.

### Pitfall 2: Negative Time Ranges
**What goes wrong:** If called after sunset, `today_sunset - now` is negative, `calculate_period()` returns 0.
**How to avoid:** `calculate_period()` already handles `end <= start` by returning empty result. But for "today daylight remaining", use `max(today_sunrise, now)` as start.

### Pitfall 3: Morning End Time Switch
**What goes wrong:** The switch from "today" to "tomorrow" daylight consumption must happen at `morning_end_time`, not at sunset.
**How to avoid:** Implement the switch in `_gather_snapshot()` or in the caller. The CONTEXT specifies: before morning_end_time use today, after use tomorrow.

### Pitfall 4: Energiebedarf Used in Multiple Places
**What goes wrong:** `_calc_energiebedarf()` is called by both `_should_block_charging()` (which should use daylight consumption) and `_evaluate()` (for the Decision.energiebedarf_kwh field used in markdown/dashboard).
**How to avoid:** Make sure the energiebedarf value in the Decision reflects the daylight-scoped consumption. Since energiebedarf is only used for morning delay display and blocking decision, this is consistent.

## Code Examples

### Adding Daylight Consumption to Snapshot

```python
# In _gather_snapshot(), after getting sunrise/sunset:

# Daylight consumption (SA -> SU) for morning delay decision
consumption_today_daylight = 0.0
consumption_tomorrow_daylight = 0.0

if sunrise is not None and sunset is not None:
    today_date = now.date()

    # Determine today's sunrise
    if sunrise.date() == today_date:
        today_sunrise = sunrise
    else:
        today_sunrise = sunrise - timedelta(days=1)

    # Determine today's sunset
    if sunset.date() == today_date:
        today_sunset = sunset
    else:
        today_sunset = sunset + timedelta(days=1)

    # Today: from max(sunrise, now) to sunset
    if today_sunset > now:
        daylight_start = max(today_sunrise, now)
        consumption_today_daylight = self._coordinator.calculate_period(
            daylight_start, today_sunset
        ).get("verbrauch_kwh", 0.0)

    # Tomorrow: full sunrise to sunset (shift by +1 day)
    tomorrow_sunrise = today_sunrise + timedelta(days=1)
    tomorrow_sunset = today_sunset + timedelta(days=1)
    consumption_tomorrow_daylight = self._coordinator.calculate_period(
        tomorrow_sunrise, tomorrow_sunset
    ).get("verbrauch_kwh", 0.0)
```

### Modified _calc_energiebedarf

```python
def _calc_energiebedarf(self, snap: Snapshot) -> float:
    """Calculate energy demand using daylight-only consumption."""
    # Use daylight consumption (SA->SU) instead of now->sunset
    consumption = snap.consumption_today_daylight_kwh

    missing_battery = 0.0
    if snap.battery_capacity_kwh > 0:
        missing_battery = (100 - snap.battery_soc) / 100 * snap.battery_capacity_kwh

    return consumption + missing_battery
```

### Modified Tomorrow Preview in _morning_delay_status

```python
# In _morning_delay_status(), outside-window path:
tomorrow_demand = snap.consumption_tomorrow_daylight_kwh + missing_battery_est
```

## Implementation Summary

| Change | File | What |
|--------|------|------|
| Add Snapshot fields | optimizer.py | `consumption_today_daylight_kwh`, `consumption_tomorrow_daylight_kwh` |
| Compute daylight consumption | optimizer.py `_gather_snapshot()` | Derive today/tomorrow sunrise/sunset, call `calculate_period()` |
| Update energiebedarf | optimizer.py `_calc_energiebedarf()` | Use daylight consumption instead of `consumption_to_sunset_kwh` |
| Update tomorrow preview | optimizer.py `_morning_delay_status()` | Use `consumption_tomorrow_daylight_kwh` instead of `consumption_tomorrow_kwh` |
| (Optional) New sensor | sensor.py | Expose daylight consumption as HA sensor |

## Sources

### Primary (HIGH confidence)
- `custom_components/eeg_energy_optimizer/coordinator.py` -- `calculate_period()` API, hourly_avg structure
- `custom_components/eeg_energy_optimizer/optimizer.py` -- Snapshot, Decision, all decision methods
- `custom_components/eeg_energy_optimizer/sensor.py` -- sensor patterns, DailyForecastSensor template
- Home Assistant sun.sun entity documentation -- `next_rising`/`next_setting` behavior

## Metadata

**Confidence breakdown:**
- Architecture: HIGH -- all relevant code read and understood
- Integration points: HIGH -- exact lines identified
- Sun time handling: MEDIUM -- `next_rising`/`next_setting` semantics well-known but edge cases around midnight need care

**Research date:** 2026-03-23
**Valid until:** 2026-04-23
