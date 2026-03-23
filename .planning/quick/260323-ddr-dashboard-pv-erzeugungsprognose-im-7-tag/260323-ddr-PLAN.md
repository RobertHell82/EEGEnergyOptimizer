---
phase: quick-260323-ddr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [DASHBOARD-CHART-GROUPED-BAR, DASHBOARD-CHART-MULTILINE-WEEKDAY]
must_haves:
  truths:
    - "7-Tage chart shows consumption AND PV forecast bars side by side per day"
    - "PV bars appear only for Heute and Morgen (days 0 and 1) since no 7-day PV sensor data exists"
    - "Chart has a legend distinguishing Verbrauch and PV Erzeugung"
    - "Verbrauchsprofil chart shows all 7 weekdays as lines"
    - "Today's weekday line is thick (2-3px), full color, with area fill"
    - "Other 6 weekday lines are thin (1px), muted/low opacity, no area fill"
    - "Weekday legend identifies which line is which"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Updated _renderBarChart and _renderLineChart methods plus dashboard wiring"
  key_links:
    - from: "_renderDashboard()"
      to: "_renderBarChart()"
      via: "passes pvData array alongside forecastData"
    - from: "_renderDashboard()"
      to: "_renderLineChart()"
      via: "passes all 7 weekday datasets from verbrauchsprofil attributes"
---

<objective>
Enhance two dashboard charts in eeg-optimizer-panel.js:
1. Convert the 7-Tage forecast bar chart from single bars to grouped bars showing consumption + PV forecast side by side
2. Convert the Verbrauchsprofil line chart from single-weekday to all-7-weekdays with today highlighted

Purpose: Give the user a richer view of energy production vs consumption forecasts and weekly consumption patterns.
Output: Updated eeg-optimizer-panel.js with both chart improvements.
</objective>

<execution_context>
@~/.claude/get-shit-done/workflows/execute-plan.md
@~/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Grouped bar chart for 7-Tage Verbrauch + PV Erzeugung</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Modify `_renderBarChart(data)` to accept a second parameter `pvData` (array of same length, each element `{label, value}` or null):

**New signature:** `_renderBarChart(data, pvData = null)`

**When pvData is provided:**
- Each day gets TWO bars side by side within the same slot
- Left bar = consumption (existing `var(--primary-color)`)
- Right bar = PV production (use `#FF9800` amber/orange — good contrast in both light and dark themes)
- Each bar is half the original `barW` width with a small 2px gap between them
- Value labels above each bar (existing for consumption, same style for PV)
- If a pvData entry has value 0 or null, skip that PV bar (days 2-6 have no PV data)

**Add legend** above the chart (inside the SVG, top-right area):
- Small colored square + text: "Verbrauch" (primary-color), "PV Erzeugung" (amber)
- Font size 11, positioned at top-right of SVG

**When pvData is null:** Behave exactly as before (backward compatible).

**maxVal calculation:** Must consider both datasets: `Math.max(...data.map(d => d.value), ...(pvData || []).map(d => d.value || 0), 1) * 1.1`

**Update `_renderDashboard()`** to build pvData and pass it:

```javascript
// Build PV forecast data for chart (only today + tomorrow available)
const pvForecastData = forecastData.map((d, i) => {
  if (i === 0) return { label: d.label, value: pvHeute || 0 };
  if (i === 1) return { label: d.label, value: pvMorgen || 0 };
  return { label: d.label, value: 0 };
});
```

Pass to render call: `this._renderBarChart(forecastData, pvForecastData)`

Also update the chart card heading from "Verbrauchsprognose (7 Tage)" to "Energieprognose (7 Tage)" since it now shows both consumption and production.
  </action>
  <verify>
    <automated>node -e "const fs=require('fs'); const c=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); const checks=['pvData','PV Erzeugung','#FF9800','Energieprognose','pvForecastData']; const missing=checks.filter(k=>!c.includes(k)); if(missing.length){console.error('Missing:',missing);process.exit(1)} console.log('All grouped bar chart elements present')"</automated>
  </verify>
  <done>7-Tage chart renders grouped bars with consumption (blue) and PV (amber) side by side. PV bars only for today+tomorrow. Legend present. Backward compatible when pvData is null.</done>
</task>

<task type="auto">
  <name>Task 2: Multi-weekday line chart for Verbrauchsprofil</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Replace `_renderLineChart(hourlyData, label)` with a new signature that supports multiple datasets:

**New signature:** `_renderLineChart(datasets, highlightIndex = 0)`

Where `datasets` is an array of `{ data: number[24], label: string, key: string }`.

**Rendering logic:**
1. Compute `maxVal` across ALL datasets: flatten all values, take max * 1.1
2. Draw y-axis grid lines (same as current)
3. Draw x-axis labels (same as current, every 3h)
4. For each dataset that is NOT the highlighted one (draw background lines FIRST):
   - Polyline: stroke width 1px, color `var(--primary-color)` at opacity 0.2, no area fill
5. For the highlighted dataset (draw ON TOP):
   - Area polygon: `var(--primary-color)` at opacity 0.1 (same as current)
   - Polyline: stroke width 2.5px, `var(--primary-color)` full opacity
6. Add a legend below the x-axis labels (or top-right):
   - Show all 7 weekday short names (Mo, Di, Mi, Do, Fr, Sa, So)
   - Today's weekday in bold with a thicker line indicator
   - Other weekdays in lighter text
   - Use a compact horizontal layout, font-size 10

**Weekday keys and order:** `["mo", "di", "mi", "do", "fr", "sa", "so"]`
**Weekday display labels:** `["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]`

**Update `_renderDashboard()`** to build all 7 weekday datasets:

```javascript
const weekdayKeys = ["mo", "di", "mi", "do", "fr", "sa", "so"];
const weekdayLabels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
const todayKeyIdx = ["so", "mo", "di", "mi", "do", "fr", "sa"].indexOf(dayKey);
// Map to mo-based index: so=0->6, mo=1->0, di=2->1, mi=3->2, do=4->3, fr=5->4, sa=6->5
const todayMoIdx = todayKeyIdx === 0 ? 6 : todayKeyIdx - 1;

const weekdayDatasets = [];
weekdayKeys.forEach((key, idx) => {
  const watts = profilState?.attributes?.[`${key}_watts`];
  if (watts && Array.isArray(watts) && watts.length === 24) {
    weekdayDatasets.push({
      data: watts.map(w => w / 1000),
      label: weekdayLabels[idx],
      key: key
    });
  }
});

const highlightIdx = weekdayDatasets.findIndex(ds => ds.key === dayKey);
```

Pass: `this._renderLineChart(weekdayDatasets, highlightIdx >= 0 ? highlightIdx : 0)`

Handle edge case: if `weekdayDatasets` is empty, show "Keine Daten verfuegbar". If only 1 dataset, render it highlighted (same visual as before).

Increase SVG height from 250 to 280 to accommodate the legend below the chart.

Update chart card heading from "Verbrauchsprofil (Stundenmittel)" to "Verbrauchsprofil (Wochentage)" to reflect all-weekdays view.
  </action>
  <verify>
    <automated>node -e "const fs=require('fs'); const c=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); const checks=['weekdayKeys','weekdayLabels','weekdayDatasets','highlightIndex','opacity=\"0.2\"','stroke-width=\"2.5\"','Wochentage']; const missing=checks.filter(k=>!c.includes(k)); if(missing.length){console.error('Missing:',missing);process.exit(1)} console.log('All multi-line chart elements present')"</automated>
  </verify>
  <done>Verbrauchsprofil chart shows all 7 weekday lines. Today's line is thick (2.5px) with area fill. Other 6 lines are thin (1px) at 20% opacity. Compact legend identifies weekdays. Empty state handled gracefully.</done>
</task>

<task type="auto">
  <name>Task 3: Copy updated file to deployment directory</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
Copy the modified eeg-optimizer-panel.js to the deployment path:
```bash
cp custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
```

Verify the copy succeeded by checking file sizes match.
  </action>
  <verify>
    <automated>diff custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js /tmp/EEGEnergyOptimizer/custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</automated>
  </verify>
  <done>Deployment copy matches source file exactly.</done>
</task>

</tasks>

<verification>
1. File contains updated _renderBarChart with pvData parameter and grouped bar logic
2. File contains updated _renderLineChart with multi-dataset support
3. _renderDashboard passes PV data to bar chart and all weekday datasets to line chart
4. Both charts have legends
5. Chart headings updated (Energieprognose, Wochentage)
6. Deployment copy is identical to source
</verification>

<success_criteria>
- eeg-optimizer-panel.js loads without JS errors
- 7-Tage chart shows grouped consumption + PV bars (PV only for today/tomorrow)
- Verbrauchsprofil chart shows 7 weekday lines with today highlighted
- Both charts have readable legends
- File deployed to /tmp/EEGEnergyOptimizer/
</success_criteria>

<output>
After completion, create `.planning/quick/260323-ddr-dashboard-pv-erzeugungsprognose-im-7-tag/260323-ddr-SUMMARY.md`
</output>
