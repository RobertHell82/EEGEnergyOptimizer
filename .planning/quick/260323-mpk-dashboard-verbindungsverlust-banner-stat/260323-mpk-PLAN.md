---
phase: quick
plan: 260323-mpk
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: []
must_haves:
  truths:
    - "When HA WebSocket connection is lost, dashboard shows a visible 'Verbindung verloren' banner instead of a white screen"
    - "When connection restores, dashboard automatically returns to normal rendering"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "Connection-lost banner in _renderDashboard()"
      contains: "Verbindung verloren"
  key_links:
    - from: "_renderDashboard()"
      to: "_readState() returning null"
      via: "decision sensor availability check"
      pattern: "decisionState.*Verbindung"
---

<objective>
Show a "Verbindung verloren" banner on the dashboard when the HA WebSocket connection is lost, replacing the current white-screen behavior.

Purpose: Users see a clear status message instead of a confusing blank dashboard when connection drops.
Output: Modified panel JS with connection-lost banner.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add connection-lost banner to dashboard</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
In `_renderDashboard()` (starts at line 1740), add an early-return check AFTER the existing `if (!h)` guard (line 1742) and AFTER reading decisionState (line 1749). The check should:

1. Read the decision sensor entity (already done at line 1749 as `decisionState`). Also check if `this._hass.states` is empty or has very few entries (indicating connection loss vs just one sensor being unavailable).

2. If `decisionState` is null (entity unavailable/unknown) AND either:
   - `Object.keys(this._hass.states).length < 3` (connection likely lost), OR
   - The mode select entity is ALSO unavailable (`modeState` is null, already read at line 1745)

   Then return a connection-lost banner HTML instead of the normal dashboard.

3. The banner HTML structure:
```html
<div class="connection-lost">
  <div class="connection-lost-icon">&#9888;</div>
  <h2>Verbindung verloren</h2>
  <p>Warte auf Verbindung zum Home Assistant Server...</p>
  <div class="connection-lost-spinner"></div>
</div>
```

4. Add CSS in the style section (around line 2098) for `.connection-lost`:
   - Centered in viewport: `display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:60vh; text-align:center`
   - Warning icon: `font-size:48px; color:var(--warning-color, #ffa726)` with margin-bottom
   - h2: `color:var(--primary-text-color); font-weight:500; margin:8px 0`
   - p: `color:var(--secondary-text-color, #666); font-size:14px; margin:4px 0 24px`
   - Spinner: A simple CSS spinning animation (border-based spinner), `width:32px; height:32px; border:3px solid var(--divider-color, #e0e0e0); border-top-color:var(--warning-color, #ffa726); border-radius:50%; animation:conn-spin 1s linear infinite`
   - Add `@keyframes conn-spin { to { transform:rotate(360deg) } }`

5. The check placement should be right after line 1749 (after decisionState is read), before any chart rendering. Insert:
```js
// Connection lost banner
if (!decisionState && !modeState) {
  return `<div class="connection-lost">
    <div class="connection-lost-icon">&#9888;</div>
    <h2>Verbindung verloren</h2>
    <p>Warte auf Verbindung zum Home Assistant Server...</p>
    <div class="connection-lost-spinner"></div>
  </div>`;
}
```

No reconnect logic needed — `set hass()` triggers re-render automatically when connection restores.
  </action>
  <verify>
    <automated>grep -n "Verbindung verloren" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js && grep -n "connection-lost" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js | head -10</automated>
  </verify>
  <done>When both the decision sensor and mode select are unavailable, _renderDashboard() returns a centered warning banner with "Verbindung verloren" heading, subtitle, and spinning indicator. Normal dashboard resumes automatically when entities become available again.</done>
</task>

</tasks>

<verification>
- `grep "Verbindung verloren" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` finds the banner text
- `grep "connection-lost" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` finds both HTML classes and CSS rules
- `grep "conn-spin" custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` finds the spinner animation
</verification>

<success_criteria>
Dashboard shows a prominent "Verbindung verloren" banner with warning icon and spinner when HA connection is lost, instead of a white screen with "---" values. Normal dashboard rendering resumes when connection restores.
</success_criteria>

<output>
After completion, create `.planning/quick/260323-mpk-dashboard-verbindungsverlust-banner-stat/260323-mpk-SUMMARY.md`
</output>
