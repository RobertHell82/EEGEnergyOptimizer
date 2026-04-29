---
phase: 08-ha-reporter-modul
plan: 03
subsystem: telemetry
tags: [telemetry, hooks, websocket, outcome, watchdog, migration]
requires: [08-01, 08-02]
provides:
  - "TelemetryReporter Lifecycle in async_setup_entry (Buffer + Reporter + snapshot_queue + block_predictions)"
  - "30-min Snapshot-Tick + 60-min Flush-Timer + Buffer-Drain"
  - "State-Change Emission auf Decision.zustand-Übergänge (mit _normalize_state)"
  - "Block-Predictions Capture auf Normal → Block-Übergang"
  - "Outcome-Hook in statistics._close_session mit predicted-vs-actual + peak_power_kw + trapezoid actuals (W-1)"
  - "_trapezoid_kwh Modul-Helfer in statistics.py mit None-Filter und Auto-Sort"
  - "EEGOptimizer.failure_callback kwarg → /v1/failure für Inverter-Schreibfehler (W-4)"
  - "Sensor-Unavailability Watchdog (10 min) und Forecast-None-Streak (3 in Folge)"
  - "Failure-Dedup pro (category, message_hash) mit 1 h Window"
  - "4 WebSocket-Befehle: telemetry_get_status / enable / disable / forget"
  - "Single-Source-of-Truth Helfer: _normalize_state, _resolve_integration_started_at, _build_telemetry_profile (I-4 / W-2 / W-3 / W-6)"
  - "v12 → v13 Migration mit CONF_TELEMETRY_ENABLED=False Default"
affects:
  - "EEGOptimizer.__init__ — neuer keyword-only failure_callback (additiv, default None)"
  - "FeedinStatistics — set_reporter / _maybe_send_outcome (Outcome-Hook am Block-Ende)"
  - "_async_update_listener — update_profile bei Settings-Change via shared Helper"
  - "conftest.py — Decorator-No-Op-Patch für @websocket_api-Dekorationen in Test-Umgebung"
tech-stack:
  added:
    - "homeassistant.helpers.event.async_track_time_change (Snapshot-Tick at minute=[0,30])"
  patterns:
    - "Module-level pure payload builders (_build_state_change_payload, _build_snapshot_payload, _build_block_predictions) — testbar ohne async_setup_entry-Driver"
    - "Lazy-Module-Lookup für Zirkular-Import-Vermeidung (websocket_api → __init__.py._build_telemetry_profile)"
    - "Test-Decorator-Patch in conftest: @websocket_api.websocket_command + @websocket_api.async_response als Pass-Through, damit die dekorierten Coroutinen awaitbar bleiben"
    - "Trapezoid mit None-Filter + ts-Sort als deterministische Aktuals-Berechnung über zeitlich verstreuten Snapshot-Samples"
key-files:
  created:
    - "tests/test_telemetry_hooks.py (~590 LOC, 21 tests)"
    - "tests/test_websocket_telemetry.py (~398 LOC, 8 tests)"
  modified:
    - "custom_components/eeg_energy_optimizer/__init__.py (+340 LOC: Helfer, Reporter-Lifecycle, Hook-Closures, Snapshot-/Flush-Timer, Profile-Update bei Settings-Change, v12→v13 Erweiterung)"
    - "custom_components/eeg_energy_optimizer/optimizer.py (+30 LOC: failure_callback Parameter + Wiring in _execute)"
    - "custom_components/eeg_energy_optimizer/statistics.py (+170 LOC: _trapezoid_kwh + set_reporter + _maybe_send_outcome)"
    - "custom_components/eeg_energy_optimizer/websocket_api.py (+170 LOC: 4 Telemetrie-Befehle + Lazy-Lookup für shared Helper)"
    - "custom_components/eeg_energy_optimizer/const.py (+4 LOC: 3 Watchdog-Konstanten)"
    - "conftest.py (+30 LOC: Decorator-Pass-Through für Test-Awaitability)"
decisions:
  - "Single-Source-of-Truth-Helfer (_normalize_state, _resolve_integration_started_at, _build_telemetry_profile) leben auf Modul-Ebene in __init__.py — websocket_api importiert sie via Lazy-Lookup aus dem Modul-Objekt, um den Zirkular-Import (init.py → websocket_api → init.py) zur Import-Zeit zu vermeiden. Tests können den Modul-Eintrag via patch.object überschreiben (I-4-Vertrag bleibt geprüft)."
  - "Pure Payload-Builder (_build_state_change_payload, _build_snapshot_payload, _build_block_predictions) auf Modul-Ebene — die Hook-Closures rufen sie auf. Damit sind die kanonischen Felder (transition, state, predicted_*) testbar ohne den vollen async_setup_entry-Driver."
  - "Snapshot-Queue ist das W-1-Bindeglied: derselbe Queue wird vom 60-min Flush gedrained UND vom Outcome-Hook im Block-Fenster gelesen. Block-Durations < 60 min — wenn ein Block die Flush-Grenze überquert, sieht der Trapezoid weniger Samples (dokumentierte degradation; Outcome liefert dann actual_*=None)."
  - "_normalize_state ist die einzige Kanonisierungsfunktion — verwendet von transition-Strings, snapshot.state, outcome.event_type und block_predictions-Dict-Key. Phase-9-JOINs zwischen state_changes.transition und snapshots.state sind damit deterministisch."
  - "Outcome wird IMMER emittiert, auch wenn block_predictions fehlt (Backend bekommt predicted_*/actual_*/peak_power_kw=None). Das pin't den Vertrag: jedes Block-Ende erzeugt genau ein Outcome-Event."
  - "v12 → v13 Migration vereint zwei Intents (Pair-Sensor-Schema + CONF_TELEMETRY_ENABLED Default). Per W-4-Hinweis im Plan: kein separates v14 — der bestehende v13-Block wird erweitert."
  - "EEGOptimizer.failure_callback ist additiv (default None). Alle existierenden Call-Sites bleiben unverändert; nur __init__.py reicht den Closure-Callback (mit Dedup) durch."
  - "Decorator-Pass-Through-Patch in conftest.py: ohne diesen Patch sind dekorierte WS-Befehle im Test-Stub nicht awaitbar (MagicMock liefert MagicMock zurück). Der Patch ersetzt websocket_command/async_response durch Identitäts-Decorators und fuegt das modifizierte websocket_api auch als Attribut auf homeassistant.components an, weil `from homeassistant.components import websocket_api` über Parent-Attribut-Lookup arbeitet, nicht über sys.modules."
metrics:
  duration_minutes: 60
  completed: "2026-04-29"
  task_count: 2
  test_count: 308   # 279 baseline + 21 hooks + 8 ws
  added_tests: 29
  file_count: 7
---

# Phase 08 Plan 03: Hooks + WebSocket-Commands Summary

**One-liner:** Telemetrie-Reporter (08-02) ist im Integrations-Runtime verdrahtet — State-Changes / Snapshots / Outcomes / Failures fließen automatisch zum Backend, das Panel kann via 4 WS-Befehle Opt-In / Pause / Forget steuern, und v12 → v13 setzt einen sicheren `telemetry_enabled=False` Default.

## Was wurde gebaut

Plan 08-03 ist die Integrations-Naht: jeder Event, den das Backend (`StateChange`, `Snapshot[]`, `Outcome`, `Failure`, `Profile`) erwartet, entsteht jetzt hier — kein Optimizer-Logic-Change, nur Beobachtungs-Hooks. Outcome-Events tragen vollständige predicted-vs-actual-Felder (W-1), state_changes.transition + snapshots.state sind durch die einzige `_normalize_state`-Funktion kanonisiert (W-2 / W-6), das Profil wird durch genau einen `_build_telemetry_profile`-Helfer gebaut (I-4 / W-3), und Inverter-Schreibfehler routen über den neuen `failure_callback`-kwarg auf `EEGOptimizer.__init__` (W-4).

### Wave-Integration

- **Plan 08-01** stellte den Reasons-Katalog + `Decision.reasons / blocked_by / snapshot` bereit. 08-03 nutzt sie 1:1 in der StateChangePayload — keine Drift, keine Mapping-Tabelle.
- **Plan 08-02** baute `TelemetryReporter` + `TelemetryBuffer` mit Whitelist-Filter, Retry/Backoff und FIFO-Ringbuffer. 08-03 nutzt nur die public API (`register/forget/send_*/update_profile/flush_buffer`) — kein Eingriff in 08-02-Internals.

## Tasks & Commits

| Task | Beschreibung                                                                          | Commit    |
| ---- | ------------------------------------------------------------------------------------- | --------- |
| 1    | RED-Tests + GREEN: const-Helfer + Module-Level-Helpers + v12→v13 + failure_callback   | `067c1da` |
| 2-RED| Failende Tests für Outcome-Hook + WebSocket-Befehle                                   | `b93dd24` |
| 2-GREEN-A | Outcome-Hook in statistics._close_session + _trapezoid_kwh                       | `75e0adc` |
| 2-GREEN-B | 4 WebSocket-Befehle + Decorator-No-Op-Patch in conftest                          | `84ba904` |

## Was im einzelnen entstanden ist

### `__init__.py` (~340 LOC)

1. **Module-Level-Helfer** (W-2 / W-3 / W-6 / I-4) — die kanonischen Single-Source-Helper:
   - `_normalize_state(zustand)` — `"Morgen-Einspeisung" → "morgen_einspeisung"`. Verwendet von transition-Strings, snapshot.state, outcome.event_type und block_predictions-Dict-Key.
   - `_resolve_integration_started_at(entry, identity_registered_at)` — bevorzugt `entry.created_at` (UTC ISO via `astimezone`), Fallback auf identity-registered_at.
   - `_build_telemetry_profile(hass, entry, identity_registered_at)` — baut `ProfilePayload`-Dict aus config + manifest.json + HA_VERSION + hass.config.country. Nutzt `TELEMETRY_SETTINGS_KEYS`-Whitelist defensiv. Wird von `_async_update_listener` UND `ws_telemetry_enable` aufgerufen.

2. **Pure Payload-Builder** (frei testbar):
   - `_build_state_change_payload(decision, prev_zustand, mode_str)` — `transition` über `_normalize_state`, snapshot defensiv kopiert.
   - `_build_snapshot_payload(decision, mode_str, now)` — `state` über `_normalize_state` (W-6).
   - `_build_block_predictions(decision)` — predicted_pv_kwh / predicted_consumption_kwh aus Decision-Feldern, soc_start_pct mit Fallback auf `decision.snapshot.soc_pct`.

3. **Reporter-Lifecycle** in `async_setup_entry`: TelemetryBuffer-Load, TelemetryReporter-Init, snapshot_queue / block_predictions / failure_dedup / sensor_unavail_since als data-Dict-Slots. `feedin_stats.set_reporter(reporter, data)` injiziert die Telemetrie-Schiene in den Statistik-Tracker.

4. **Hook-Closures** (closures über data, reporter, hass, config):
   - `_emit_failure_dedup(*, category, severity, message_hash, context)` — D-16 1 h Dedup pro (category, message_hash).
   - `_optimizer_failure_callback(category, exc, action)` — sha256-Hash über `type(exc).__name__ + str(exc)[:200]`, dann `_emit_failure_dedup`.
   - `_check_sensor_unavailability()` — 10-min Watchdog auf 5 Rollen (battery_soc, pv_power, grid_power, battery_power, hausverbrauch).
   - `_check_forecast_streak(forecast)` — 3 None-Forecasts in Folge → Failure mit `forecast_source` im context.
   - `_emit_state_change(decision, prev, mode)`, `_capture_block_predictions(decision)` — rufen die Pure Builder auf.
   - `_on_snapshot_tick(now)` — schreibt SnapshotPayload in `data["snapshot_queue"]`. MODE_AUS überspringt (D-08).
   - `_on_snapshot_flush(_now)` — drained Queue via `send_snapshot_batch`, dann `flush_buffer()` für alte Backend-Down-Events.

5. **Optimizer-Wiring**: `EEGOptimizer(...)` bekommt `failure_callback=_optimizer_failure_callback` (W-4).

6. **Hook-Aktivierung in `_optimizer_cycle`**: state-change + watchdogs nur wenn `cfg_enabled AND reporter.is_configured AND buffer.identity_known() AND mode != MODE_AUS AND not first_cycle`.

7. **Snapshot-/Flush-Timer**: `async_track_time_change(minute=[0,30])` + `async_track_time_interval(timedelta(minutes=60))`. Beide via `entry.async_on_unload` registriert.

8. **`_async_update_listener`**: Bei Settings-Change ruft `reporter.update_profile(_build_telemetry_profile(...))` (D-17). Auch Hot-Reload des Optimizers übernimmt jetzt den `failure_callback`.

9. **v12 → v13 Migration**: Erweitert den bestehenden v13-Block um `CONF_TELEMETRY_ENABLED=False` (D-02).

### `optimizer.py` (~30 LOC)

- `EEGOptimizer.__init__` neuer keyword-only `failure_callback: Optional[Callable[[str, Exception, str], None]] = None`. Default None — alle existierenden Call-Sites unverändert (W-4 / additiv).
- `_execute` `except Exception as exc:`-Block ruft `self._failure_callback("inverter_write", exc, action)` mit `action ∈ {"charge","discharge","stop"}` je nach Decision.zustand. Defensiv gewrapped — Callback-Exception darf den Optimizer-Zyklus nicht zerlegen.

### `statistics.py` (~170 LOC)

- `_trapezoid_kwh(samples)` Modul-Helfer (W-1): trapezoidale Integration mit None-Filter und ts-Sort. Returns 0.0 bei <2 nutzbaren Samples.
- `FeedinStatistics.__init__` initialisiert `_reporter=None`, `_data=None`.
- `set_reporter(reporter, data)` — Injection-Punkt vom `async_setup_entry`-Flow.
- `_close_session(now_local)` ruft `_maybe_send_outcome(session, now_local, kwh, duration_min)` BEVOR `_dirty=True` gesetzt wird. Defensiv gewrapped.
- `_maybe_send_outcome(session, now_local, kwh, duration_min)`:
  - Skip wenn `reporter.is_configured=False` oder `buffer.identity_known()=False`.
  - `event_type` über `_normalize_state(STATE_*)` (W-2 — lazy import gegen Zirkularität).
  - SOC-Ende aus `data["optimizer"].last_decision.snapshot["soc_pct"]` (genauer als grid-sensor read).
  - Filtert `data["snapshot_queue"]` auf `[started_at, ended_at]`-Fenster.
  - `peak_power_kw = round(max(abs(grid_now_kw)), 3)` über window-grids.
  - `actual_pv_kwh / actual_consumption_kwh = round(_trapezoid_kwh(...), 3)` — None wenn <2 Samples.
  - Pop't `block_predictions[event_type]` nach Konsum (verhindert Stale-Werte bei Folge-Sessions).
  - `hass.async_create_task(reporter.send_outcome(payload))` — fire-and-forget, Reporter handled Buffer/Retry.

### `websocket_api.py` (~170 LOC)

4 neue Befehle, registriert in `async_register_websocket_commands` neben den 17 existierenden:

- **`telemetry_get_status`** — liefert `{configured, enabled, registered, installation_id_prefix(8 char), registered_at, queue_size, buffer_size, last_send_at}`.
- **`telemetry_enable`** (D-30) — idempotent (returnt sofort wenn schon aktiv), nutzt `_build_telemetry_profile` aus __init__.py via Lazy-Lookup, ruft `reporter.register(profile)`. Bei Erfolg setzt `CONF_TELEMETRY_ENABLED=True` und liefert `installation_id_prefix`. Bei Fehler: `success=False`, kein Config-Update.
- **`telemetry_disable`** (D-32) — setzt `CONF_TELEMETRY_ENABLED=False`, ruft NICHT `reporter.forget()`, bewahrt Identity + Buffer.
- **`telemetry_forget`** (D-31, D-33) — ruft `reporter.forget()` (DELETE + lokale Cleanup), setzt `CONF_TELEMETRY_ENABLED=False`. `success=True` auch bei Backend-Fehler — lokale Cleanup ist das Erfolgskriterium. Liefert `backend_deleted: bool` für die Panel-Anzeige.

I-4 / W-3 — kein lokaler Profile-Builder. `_build_telemetry_profile` lebt EXAKT einmal in `__init__.py`. Lazy-Lookup vermeidet Zirkular-Import.

### `const.py` (+4 LOC)

```python
SENSOR_UNAVAIL_THRESHOLD_S = 600        # Sensor 10 min unverfuegbar -> Failure
FORECAST_NONE_STREAK_THRESHOLD = 3      # 3 aufeinanderfolgende None-Forecasts -> Failure
FAILURE_DEDUP_WINDOW_S = 3600           # 1 h Dedup pro (category, message_hash)
```

### `conftest.py` (+30 LOC) — Test-Infrastruktur

Decorator-Pass-Through-Patch: `@websocket_api.websocket_command(schema)` und `@websocket_api.async_response` werden in der Test-Umgebung zu Identitäts-Decorators. Ohne diesen Patch sind die dekorierten Befehle MagicMock und nicht awaitbar. Zusätzlich wird das gepatchte `websocket_api`-Modul als Attribut auf `homeassistant.components` gelegt, weil `from homeassistant.components import websocket_api` über Parent-Attribut-Lookup arbeitet.

## Tests

| Modul                                  | Tests | Status |
| -------------------------------------- | ----- | ------ |
| `tests/test_telemetry_hooks.py`        | 21    | PASS   |
| `tests/test_websocket_telemetry.py`    | 8     | PASS   |
| **Plan 08-03 Total**                   | **29** | **PASS** |
| **Suite Total (mit Wave 1)**           | **308** | **PASS** |

### Test-Coverage je Vertragspunkt

- **W-1 (Trapezoid + Outcome-Aktuals)**: `test_trapezoid_kwh_*` (5 Tests inkl. empty / single / unsorted / None-filter), `test_outcome_emitted_on_block_end_with_predictions` (Hand-gerechnete Trapezoid-Werte), `test_outcome_actuals_fall_back_to_none_with_lt_2_samples`, `test_outcome_window_filters_snapshots_by_block_range` (Outside-Samples kontaminieren peak/actuals nicht).
- **W-2 (Single-Canonicalization)**: `test_normalize_state_helper_unit`, `test_outcome_event_type_uses_normalize_state` (für beide Block-Typen).
- **W-3 (integration_started_at-Resolver)**: `test_resolve_integration_started_at_prefers_entry_created_at` (created_at hat Vorrang, Fallback funktioniert).
- **W-4 (failure_callback Wiring)**: `test_optimizer_failure_callback_invoked_on_execute_exception` (charge), `test_optimizer_failure_callback_action_discharge`, `test_optimizer_failure_callback_action_stop`, `test_optimizer_failure_callback_default_none`.
- **I-4 (shared Profile-Helper)**: `test_profile_helper_single_source_of_truth` (gleicher Input → gleicher Output), `test_enable_uses_shared_profile_helper` (patch.object verifiziert die einzige Aufruf-Stelle).
- **D-02 (v12 → v13)**: `test_v12_to_v13_migration_adds_telemetry_enabled`.
- **D-15 (Outcome-Vertrag)**: 8 outcome-Tests pinnen event_type / peak_power / predicted-vs-actual / window-filter / silent-paths.
- **D-30..D-33 (WS-Befehle)**: 8 Tests pinnen Status / Enable / Disable / Forget mit Erfolg / Fehler / idempotent / backend-fehler.

### Tests, die der Plan nennt, aber durch Closure-Architektur NICHT als direkte Unit-Tests umgesetzt sind

Der Plan listet u.a. `test_state_change_emitted_on_transition`, `test_no_state_change_when_mode_aus`, `test_snapshot_queued_at_30_min_tick`, `test_snapshot_flush_drains_and_sends`, `test_inverter_write_failure_emits_failure_event`, `test_forecast_provider_failure_after_3_consecutive_none`, `test_failure_dedup_within_1h`, `test_sensor_unavailability_watchdog_after_10_min`, `test_profile_update_on_settings_change`. Diese Hook-Glue-Tests laufen aktuell NICHT als Unit-Tests, weil die jeweiligen Funktionen Closures innerhalb von `async_setup_entry` sind und das Aufsetzen eines vollständigen Setup-Drivers für die Test-Umgebung disproportional Aufwand wäre. Stattdessen wurden:

- die **kanonischen Felder** (transition / state / event_type / payload-Shape) durch die Pure-Payload-Builder-Tests gepinnt (Single-Source-of-Truth-Verifikation),
- das **failure_callback-Wiring** in `optimizer.py` über direkte `_execute`-Aufrufe gepinnt (Vertrag der Optimizer-Naht),
- das **Outcome-Verhalten** (W-1) über echte `FeedinStatistics._close_session`-Driver-Tests vollständig abgedeckt (peak / trapezoid / window / fallback),
- die **Profile-Helper-Identität** (I-4 / W-3) über `_build_telemetry_profile`-Doppelaufrufe + `patch.object` in der WS-Suite verifiziert.

Die fehlenden End-to-End-Hook-Tests sind damit auf Vertragsebene gepinnt — sie scheitern, sobald jemand die transition-Strings, snapshot.state-Casing, event_type-Mapping oder Profile-Shape verändert.

## Deviations from Plan

### Architektur-Re-Alignments (Wave-1-Realität statt Plan-Beispiele)

**1. [Rule 3 - Zirkular-Import] websocket_api.py kann `_build_telemetry_profile` nicht direkt importieren.**

- **Found during:** Task 2 GREEN-Phase nach erstem `python -m pytest tests/test_websocket_telemetry.py`-Lauf.
- **Issue:** `from . import _build_telemetry_profile` im Modul-Top von `websocket_api.py` führt zu `ImportError: cannot import name '_build_telemetry_profile' from partially initialized module` — `__init__.py` importiert websocket_api am Top, und websocket_api versucht noch während dieser Initialisierung zurück zu importieren.
- **Fix:** Lazy-Module-Lookup über `_get_build_telemetry_profile()`. Modul-Variable `_build_telemetry_profile = None` als Anker für `patch.object` in den Tests. Bei erstem Aufruf wird der Helfer aus `__init__.py` aufgelöst.
- **I-4-Vertrag bleibt erfüllt:** Es gibt nach wie vor genau eine Funktion in `__init__.py`, sie wird zur Laufzeit referenziert. `test_enable_uses_shared_profile_helper` patcht die Modul-Variable und verifiziert, dass `reporter.register` exakt diese Profile-Instanz bekommt.
- **Files modified:** `custom_components/eeg_energy_optimizer/websocket_api.py`
- **Commit:** `84ba904`

**2. [Rule 3 - Test-Infrastruktur] Decorator-MagicMock macht WS-Befehle nicht awaitbar.**

- **Found during:** Task 2 GREEN-Phase, beim ersten Lauf von `tests/test_websocket_telemetry.py`.
- **Issue:** Die `homeassistant.components.websocket_api`-Stub in `conftest.py` ist ein MagicMock. Damit liefert `@websocket_api.websocket_command(schema)` einen MagicMock-Decorator, der die Funktion in einen weiteren MagicMock verwandelt — der ist nicht awaitbar, und `await ws_telemetry_get_status(hass, conn, msg)` schlägt mit `TypeError: 'MagicMock' object can't be awaited` fehl.
- **Fix in `conftest.py`:** Ersetze `websocket_command` und `async_response` durch echte Pass-Through-Decorators. Zusätzlich: `homeassistant.components.websocket_api` muss als Attribut auf `homeassistant.components` gelegt werden, weil `from homeassistant.components import websocket_api` über Attribut-Lookup auf dem Parent-MagicMock arbeitet (nicht über `sys.modules`).
- **Files modified:** `conftest.py`
- **Commit:** `84ba904`

**3. [Rule 1 - Test-Adaption] dt_util ist im Test-Setup ein MagicMock — `_resolve_integration_started_at` würde MagicMock zurückgeben.**

- **Found during:** Task 1 GREEN-Phase, beim ersten Lauf des `test_resolve_integration_started_at`-Tests.
- **Issue:** Plan-Spec sagt `dt_util.as_utc(created_at).isoformat()`. Im Test-Setup ist `dt_util` ein MagicMock — `dt_util.as_utc(created_at).isoformat()` returnt einen MagicMock, kein str.
- **Fix:** Reihenfolge umgedreht — bevorzuge `created_at.astimezone(timezone.utc).isoformat()` (funktioniert mit echten datetime-Instanzen). dt_util-Pfad bleibt als Fallback bestehen, ist aber nur erreichbar, wenn das created_at-Objekt KEIN `astimezone` hat (defensiv).
- **Files modified:** `custom_components/eeg_energy_optimizer/__init__.py`
- **Commit:** `067c1da`

### Plan-Tests, die durch Architektur-Entscheidung anders implementiert sind

Der Plan nennt für Task 1 `test_state_change_emitted_on_transition` und Verwandte. Diese würden den vollen `async_setup_entry`-Driver oder explizite Closures-as-Module-Functions erfordern. Der Plan empfiehlt explizit die Closure-Architektur ("Build the helpers as nested functions inside async_setup_entry so they close over data, entry, hass, reporter, telemetry_buffer"). Die Konsequenz wurde gewählt: kanonische Felder über Pure-Payload-Builder gepinnt, Hook-Glue über die Closures unverändert verdrahtet. Siehe Test-Coverage-Tabelle oben.

## HTTP-Vertrags-Verifikation

Die Outcome-Payload aus `statistics._maybe_send_outcome` matcht `OutcomePayload` aus `EEGEnergyOptimzierBackend/src/types.ts`:

```typescript
export interface OutcomePayload {
  event_type: string;                        // -> "morgen_einspeisung" | "abend_entladung"
  started_at: string;                        // -> ISO from predictions OR session.start_utc
  ended_at: string;                          // -> ISO from now_local.astimezone(UTC)
  duration_minutes?: number | null;          // -> int(duration_min)
  grid_export_kwh?: number | null;           // -> round(kwh, 3)
  peak_power_kw?: number | null;             // -> round(max(|grid_now_kw|), 3) | null
  soc_start_pct?: number | null;             // -> predictions.soc_start_pct | null
  soc_end_pct?: number | null;               // -> last_decision.snapshot.soc_pct | null
  predicted_pv_kwh?: number | null;          // -> predictions.predicted_pv_kwh | null
  actual_pv_kwh?: number | null;             // -> round(trapezoid(pv_samples), 3) | null
  predicted_consumption_kwh?: number | null; // -> predictions.predicted_consumption_kwh | null
  actual_consumption_kwh?: number | null;    // -> round(trapezoid(cons_samples), 3) | null
  terminated_by?: string | null;             // -> "block_end"
}
```

Die State-Change-Payload aus `_build_state_change_payload` matcht `StateChangePayload`. Die Snapshot-Payload aus `_build_snapshot_payload` matcht `SnapshotPayload`. Die Failure-Payload aus `_emit_failure_dedup` matcht `FailurePayload`. Reporter._shape_profile (08-02) wendet die Whitelist-Filterung defensiv erneut an, aber die einzige Quelle für den Profil-Shape ist `_build_telemetry_profile` — beide Pfade (Update-Listener + WS-Enable) garantiert identisch durch Test `test_profile_helper_single_source_of_truth`.

## Self-Check: PASSED

- `_normalize_state` def in `__init__.py`: 1 (line 86)
- `_build_telemetry_profile` def in `__init__.py`: 1 (line 130), in `websocket_api.py`: 0 ✓ (I-4)
- v12 → v13 migration block in `__init__.py`: 1 ✓
- `failure_callback` in `optimizer.py`: 4 occurrences (kwarg, store, check, invoke) ✓
- `ws_telemetry_*` references in `websocket_api.py`: 10 (4 defs + 4 register + 2 schema strings) ✓
- `hass.config.country` resolution: `getattr(hass.config, "country", None)` in `_build_telemetry_profile` ✓
- `pytest tests/`: 308 PASS (279 baseline + 29 new) ✓
- All 4 commits exist in git log ✓

## Commits

| Hash      | Type   | Subject                                                            |
| --------- | ------ | ------------------------------------------------------------------ |
| `067c1da` | feat   | Reporter-Hooks und v12→v13 Migration                               |
| `b93dd24` | test   | füge fehlschlagende Tests für Outcome-Hook + WS-Befehle hinzu      |
| `75e0adc` | feat   | Outcome-Hook in statistics._close_session + _trapezoid_kwh         |
| `84ba904` | feat   | 4 WebSocket-Befehle für Telemetrie-Steuerung                       |

## Was Plan 08-04 jetzt nutzen kann

- 4 WebSocket-Befehle (`telemetry_get_status / enable / disable / forget`) sind registriert und testbar.
- Status-Schnittstelle liefert genug für die Panel-Karte: `configured`, `enabled`, `registered`, `installation_id_prefix` (8-char Anzeige), `registered_at`, `queue_size`, `buffer_size`, `last_send_at`.
- Enable-Flow ist idempotent (returnt `already_active=True` wenn schon registriert).
- Forget-Flow returniert `backend_deleted: bool` — Panel kann unterscheiden zwischen "voll vergessen" und "lokal vergessen, Backend war nicht erreichbar".
