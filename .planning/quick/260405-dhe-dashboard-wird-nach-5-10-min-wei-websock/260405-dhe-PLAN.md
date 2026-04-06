---
phase: quick
plan: 260405-dhe
type: execute
wave: 1
depends_on: []
files_modified:
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
autonomous: true
requirements: [BUG-dashboard-white-screen]

must_haves:
  truths:
    - "Dashboard survives WebSocket reconnect without going white"
    - "Activity subscription auto-recovers after connection drop while tab is visible"
    - "Panel re-initializes when HA router reattaches the element"
  artifacts:
    - path: "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js"
      provides: "connectedCallback, watchdog interval, subscription recovery"
      contains: "connectedCallback"
  key_links:
    - from: "connectedCallback()"
      to: "_loadConfigWithRetry()"
      via: "re-init on reattach"
      pattern: "connectedCallback.*_loadConfigWithRetry"
    - from: "watchdog interval"
      to: "_loadConfigWithRetry()"
      via: "stale hass detection"
      pattern: "_watchdogInterval"
    - from: "_setHassInner()"
      to: "_subscribeActivityEvents()"
      via: "null subscription recovery"
      pattern: "_activityUnsub.*_subscribeActivityEvents"
---

<objective>
Fix dashboard going white after 5-10 minutes by adding WebSocket resilience: connectedCallback for router reattach, a keepalive watchdog for active-tab connection drops, and proactive activity subscription recovery in the hass setter.

Purpose: The panel has no recovery path when WebSocket drops while the user is actively viewing (not switching tabs). The visibilitychange handler only fires on tab switch.
Output: Updated eeg-optimizer-panel.js with three resilience mechanisms.
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
  <name>Task 1: Add connectedCallback, watchdog interval, and subscription recovery</name>
  <files>custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js</files>
  <action>
All changes are in the EegOptimizerPanel class in eeg-optimizer-panel.js.

**1. Add connectedCallback() — insert after disconnectedCallback() (after line 3313, before the closing brace of the class):**

```js
connectedCallback() {
  // Re-register visibilitychange listener (disconnectedCallback removes it)
  if (this._onVisibilityChange) {
    document.addEventListener("visibilitychange", this._onVisibilityChange);
  }
  // If already initialized before detach, re-init data + subscription
  if (this._hass && this._initialized) {
    console.info("EEG Optimizer: panel reattached, refreshing");
    this._loadConfigPending = false;
    this._loadConfigWithRetry();
  }
  // Start watchdog
  this._startWatchdog();
}
```

**2. Add _startWatchdog() and _stopWatchdog() methods (next to connectedCallback):**

```js
_startWatchdog() {
  this._stopWatchdog();
  this._watchdogInterval = setInterval(() => {
    if (document.visibilityState !== "visible" || !this._initialized) return;
    const elapsed = Date.now() - this._lastHassUpdate;
    if (elapsed > 120000) {
      console.warn("EEG Optimizer: no hass update for " + Math.round(elapsed / 1000) + "s, forcing reload");
      this._loadConfigPending = false;
      this._loadConfigWithRetry();
      // Also force re-render if shadow DOM is empty
      if (this._shadow && this._shadow.childNodes.length === 0) {
        this._render();
      }
    }
  }, 60000);
}

_stopWatchdog() {
  if (this._watchdogInterval) {
    clearInterval(this._watchdogInterval);
    this._watchdogInterval = null;
  }
}
```

**3. Update constructor — after line 258 (after the visibilitychange listener registration), add:**

```js
// Start watchdog for active-tab connection drops
this._watchdogInterval = null;
this._startWatchdog();
```

**4. Update disconnectedCallback() — add watchdog cleanup. The method should become:**

```js
disconnectedCallback() {
  this._stopWatchdog();
  if (this._activityUnsub) {
    try { this._activityUnsub(); } catch (_) { /* connection already gone */ }
    this._activityUnsub = null;
  }
  if (this._onVisibilityChange) {
    document.removeEventListener("visibilitychange", this._onVisibilityChange);
  }
}
```

**5. Add subscription recovery in _setHassInner() — after the connection-change block (after line 1048), before the entity picker update, add:**

```js
// Recover silently-dead activity subscription
if (this._setupComplete && !this._activityUnsub && this._initialized) {
  console.info("EEG Optimizer: activity subscription missing, re-subscribing");
  this._subscribeActivityEvents();
}
```

This goes after line 1048 (after the `return;` of the connection-change block) and before line 1050 (the entity picker update comment).

**Do NOT change:**
- The existing error suppression (lines 184-202)
- The existing visibilitychange handler logic
- The existing _subscribeActivityEvents() method
- The existing _loadConfigWithRetry() / _loadConfig() methods
  </action>
  <verify>
    <automated>cd C:/Data/source/HA_EEG_Energy_Optimizier && node -e "const fs=require('fs'); const s=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); const checks=['connectedCallback','_startWatchdog','_stopWatchdog','_watchdogInterval','clearInterval(this._watchdogInterval']; const missing=checks.filter(c=>!s.includes(c)); if(missing.length){console.error('MISSING:',missing);process.exit(1)} console.log('All resilience patterns present'); const m1=s.match(/disconnectedCallback[^}]*_stopWatchdog/s); if(!m1){console.error('watchdog not cleaned in disconnectedCallback');process.exit(1)} console.log('Watchdog cleanup verified'); const m2=s.match(/_setupComplete\s*&&\s*!this\._activityUnsub/); if(!m2){console.error('subscription recovery not in hass setter');process.exit(1)} console.log('Subscription recovery verified')"</automated>
  </verify>
  <done>
    - connectedCallback() restores visibilitychange listener and re-inits when panel is reattached
    - 60s watchdog detects stale hass (>120s) while tab is visible and forces reload
    - disconnectedCallback() cleans up watchdog interval
    - _setHassInner() proactively re-subscribes activity events when subscription is null
    - Existing error suppression and retry logic untouched
  </done>
</task>

</tasks>

<verification>
1. Syntax check: `node -c custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` passes
2. All three resilience mechanisms present (connectedCallback, watchdog, subscription recovery)
3. Watchdog cleaned up in disconnectedCallback
4. No changes to existing _loadConfig, _loadConfigWithRetry, _subscribeActivityEvents internals
</verification>

<success_criteria>
- Panel JS file parses without syntax errors
- connectedCallback re-initializes panel on reattach
- Watchdog runs every 60s checking for >120s stale hass updates
- Activity subscription auto-recovers in hass setter when null
- Manual test: dashboard stays alive after extended open time (user verification on next HA session)
</success_criteria>

<output>
After completion, create `.planning/quick/260405-dhe-dashboard-wird-nach-5-10-min-wei-websock/260405-dhe-SUMMARY.md`
</output>
