---
phase: quick-260323-fzl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/__init__.py
autonomous: true
requirements: [backfill-hausverbrauch-stats]
must_haves:
  truths:
    - "After integration startup, sensor.eeg_energy_optimizer_hausverbrauch has historical mean statistics in the recorder"
    - "ConsumptionCoordinator async_update() finds the backfilled statistics and builds a non-zero consumption profile"
    - "Backfill is idempotent — re-running does not duplicate entries, and is skipped if sufficient data exists"
    - "Integration startup is not blocked or broken if backfill fails"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/__init__.py"
      provides: "async_backfill_hausverbrauch_stats function + call in async_setup_entry"
      contains: "async_backfill_hausverbrauch_stats"
  key_links:
    - from: "__init__.py async_setup_entry"
      to: "async_backfill_hausverbrauch_stats"
      via: "awaited after coordinator creation, before optimizer setup"
    - from: "async_backfill_hausverbrauch_stats"
      to: "recorder async_import_statistics"
      via: "HA recorder statistics API"
---

<objective>
Add a one-time backfill of Hausverbrauch statistics from 3 historical source sensors (PV, Battery, Grid) into the HA recorder for sensor.eeg_energy_optimizer_hausverbrauch.

Purpose: The Hausverbrauch sensor was recently created and has no historical data. The ConsumptionCoordinator reads recorder statistics to build consumption profiles and forecasts. Without historical data, all forecasts are zero. The 3 source sensors DO have historical data, so we can calculate and import Hausverbrauch retrospectively.

Output: Modified __init__.py with backfill function that runs at startup, populating recorder statistics so the consumption profile works immediately.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/__init__.py
@custom_components/eeg_energy_optimizer/const.py
@custom_components/eeg_energy_optimizer/coordinator.py
@custom_components/eeg_energy_optimizer/sensor.py (lines 453-510 for HausverbrauchSensor)
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add async_backfill_hausverbrauch_stats function and wire into setup</name>
  <files>custom_components/eeg_energy_optimizer/__init__.py</files>
  <action>
Add a new async function `async_backfill_hausverbrauch_stats(hass, config)` in __init__.py (above async_setup_entry). The function must:

1. **Check if backfill is needed:**
   - Use lazy recorder imports (same pattern as coordinator.py `_ensure_recorder_imports`):
     ```python
     from homeassistant.components.recorder import get_instance
     from homeassistant.components.recorder.statistics import (
         statistics_during_period,
         async_import_statistics,
     )
     from homeassistant.components.recorder.models import StatisticMetaData, StatisticData
     ```
   - Query existing statistics for `sensor.eeg_energy_optimizer_hausverbrauch` over the last 2 weeks using `statistics_during_period`
   - If more than 168 entries exist (1 week worth), log "Backfill skipped — sufficient data" and return

2. **Load source sensor statistics:**
   - Read sensor IDs from config:
     - `config.get(CONF_PV_POWER_SENSOR, "")` — PV power (must exist, skip backfill if empty)
     - `config.get(CONF_BATTERY_POWER_SENSOR, DEFAULT_BATTERY_POWER_SENSOR)` — Battery power
     - `config.get(CONF_GRID_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR)` — Grid power
   - Import these constants from .const
   - Load `mean` statistics for ALL 3 sensors for `lookback_weeks` (from config, default 8) using `statistics_during_period` with `types={"mean"}`, `period="hour"`
   - The `statistics_during_period` call signature (same as coordinator.py lines 131-143):
     ```python
     recorder_instance = get_instance(hass)
     result = await recorder_instance.async_add_executor_job(
         statistics_during_period,
         hass,
         start_time,
         end_time,
         {pv_id, battery_id, grid_id},
         "hour",
         None,
         {"mean"},
     )
     ```

3. **Calculate Hausverbrauch for each hour:**
   - Index each sensor's entries by their `start` timestamp (use the raw value from the entry, converting float timestamps to datetime for comparison)
   - For each hour where ALL 3 sensors have a `mean` value:
     - `hausverbrauch = max(pv_mean - battery_mean - grid_mean, 0.0)`
     - This matches the HausverbrauchSensor formula in sensor.py line 506
   - Round to 3 decimal places

4. **Import statistics:**
   - Build `StatisticMetaData`:
     ```python
     metadata = StatisticMetaData(
         has_mean=True,
         has_sum=False,
         name="EEG Energy Optimizer Hausverbrauch",
         source="recorder",
         statistic_id="sensor.eeg_energy_optimizer_hausverbrauch",
         unit_of_measurement="kW",
     )
     ```
   - Build list of `StatisticData` objects:
     ```python
     StatisticData(start=hour_datetime, mean=value, state=value)
     ```
     Where `hour_datetime` must be a timezone-aware datetime (UTC).
     Parse the `start` field from stats entries: if float/int, use `datetime.fromtimestamp(ts, tz=timezone.utc)`. If string, use `datetime.fromisoformat(ts)`.
   - Call `async_import_statistics(hass, metadata, statistics)` — this is NOT an async_add_executor_job call, it's called directly
   - Log: "Backfilled {N} hourly statistics for Hausverbrauch from {start_date} to {end_date}"

5. **Error handling:**
   - Wrap the ENTIRE function body in try/except Exception, logging errors but never raising
   - This ensures integration startup is never broken by backfill failures

**Wire into async_setup_entry:**
After line 156 (where `coordinator = data.get("coordinator")`), and inside the `if coordinator and provider:` block (around line 158), add:

```python
# One-time backfill of Hausverbrauch statistics from source sensors
await async_backfill_hausverbrauch_stats(hass, config)
```

Place this BEFORE the optimizer is created (line 159) so the coordinator's next async_update will find the data.

Also add necessary imports to the existing const imports at top of file (line 11):
```python
from .const import DOMAIN, MODE_AUS, CONF_PV_POWER_SENSOR, CONF_BATTERY_POWER_SENSOR, CONF_GRID_POWER_SENSOR, DEFAULT_BATTERY_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR, CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS, CONSUMPTION_SENSOR
```
Use `CONSUMPTION_SENSOR` from const.py (value: "sensor.eeg_energy_optimizer_hausverbrauch") instead of hardcoding the string.
  </action>
  <verify>
    <automated>python -c "import ast; ast.parse(open('custom_components/eeg_energy_optimizer/__init__.py').read()); print('Syntax OK')"</automated>
  </verify>
  <done>
    - async_backfill_hausverbrauch_stats function exists with complete implementation
    - Function is called in async_setup_entry after coordinator is available, before optimizer creation
    - Backfill checks for existing data (>168 entries = skip)
    - Calculates max(PV - Battery - Grid, 0) for each hour with all 3 sources
    - Uses async_import_statistics with correct StatisticMetaData (source="recorder", has_mean=True)
    - Entire function wrapped in try/except so failures never block startup
    - All const references use named constants, not hardcoded strings
  </done>
</task>

<task type="auto">
  <name>Task 2: Copy to deployment directory and verify</name>
  <files>custom_components/eeg_energy_optimizer/__init__.py</files>
  <action>
Copy the modified __init__.py to the deployment directory:
```bash
cp custom_components/eeg_energy_optimizer/__init__.py /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/__init__.py
```

Then verify the file by:
1. Check that `async_backfill_hausverbrauch_stats` is defined
2. Check that it's called in `async_setup_entry`
3. Check that `async_import_statistics` is used
4. Check that the skip threshold (168) is present
5. Check that `CONSUMPTION_SENSOR` is imported and used
  </action>
  <verify>
    <automated>grep -c "async_backfill_hausverbrauch_stats" /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/__init__.py && grep -c "async_import_statistics" /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/__init__.py</automated>
  </verify>
  <done>
    - __init__.py copied to /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/
    - File contains the backfill function and its call in setup
    - Deployment directory has the latest version ready for HA restart
  </done>
</task>

</tasks>

<verification>
1. `python -c "import ast; ast.parse(open('custom_components/eeg_energy_optimizer/__init__.py').read())"` passes
2. `grep "async_backfill_hausverbrauch_stats" custom_components/eeg_energy_optimizer/__init__.py` shows definition and call
3. `grep "async_import_statistics" custom_components/eeg_energy_optimizer/__init__.py` shows the recorder API usage
4. `grep "CONSUMPTION_SENSOR" custom_components/eeg_energy_optimizer/__init__.py` shows const usage
5. File copied to /tmp/EEGEnergyOptimizer deployment directory
</verification>

<success_criteria>
- __init__.py contains async_backfill_hausverbrauch_stats that loads 3 source sensor statistics, calculates Hausverbrauch per hour, and imports them via async_import_statistics
- Backfill runs once at startup, is skipped if data already exists, and never blocks integration load on failure
- After HA restart, the ConsumptionCoordinator will find the imported statistics and produce non-zero consumption profiles
</success_criteria>

<output>
After completion, create `.planning/quick/260323-fzl-einmaliger-backfill-hausverbrauch-statis/260323-fzl-SUMMARY.md`
</output>
