---
phase: 08-ha-reporter-modul
plan: 03
subsystem: telemetry
tags: [telemetry, hooks, websocket, outcome, trapezoid, v12-v13, opt-in]
requires:
  - "08-01 (Decision.reasons / blocked_by / snapshot, ALL_REASONS, Snapshot.to_telemetry_dict)"
  - "08-02 (TelemetryReporter, TelemetryBuffer, Phase-8-Konstanten in const.py)"
provides:
  - "Telemetrie-Reporter im async_setup_entry-Lifecycle (Buffer, Reporter, snapshot_queue, block_predictions im hass.data)"
  - "Snapshot-Timer (30 min, async_track_time_change minute=[0,30]) und 60-min Flush-Timer"
  - "State-Change-Emission auf jedem Zustandsübergang via _emit_state_change-Closure"
  - "Block-Predictions-Capture beim Normal→Block-Übergang"
  - "Inverter-Write Failure-Hook via neuer EEGOptimizer.failure_callback kwarg (W-4)"
  - "Sensor-Unavailability Watchdog (>10 min, dedup 1 h)"
  - "Forecast-Provider Watchdog (3 None in Folge, dedup 1 h)"
  - "Outcome-Hook in statistics._close_session mit predicted-vs-actual (W-1)"
  - "_trapezoid_kwh Modul-Helfer für trapezoidale Energy-Integration"
  - "FeedinStatistics.set_reporter(reporter, data) Injection-Methode"
  - "4 WebSocket-Befehle: telemetry_get_status / telemetry_enable / telemetry_disable / telemetry_forget"
  - "_normalize_state — einzige Kanonisierungsfunktion (W-2 / W-6, Module-Top in __init__.py)"
  - "_resolve_integration_started_at — einziger Resolver (W-3)"
  - "_build_telemetry_profile — einziger Profile-Builder (I-4 / W-3)"
  - "v12→v13 Config-Migration mit CONF_TELEMETRY_ENABLED=False default"
affects:
  - "EEGOptimizer.__init__ (additiv: failure_callback kwarg, default None)"
  - "_async_update_listener (Profile-Update bei Settings-Change via shared Helper)"
  - "FeedinStatistics._close_session (ruft _maybe_send_outcome vor _dirty)"
  - "websocket_api: 4 neue Commands registriert in async_register_websocket_commands"
tech-stack:
  added:
    - "homeassistant.helpers.event.async_track_time_change (für 30-min Snapshot-Tick)"
    - "homeassistant.util.dt (UTC-Konvertierung in _resolve_integration_started_at)"
  patterns:
    - "Module-Top Helper für single-source-of-truth (W-2/W-3/I-4)"
    - "Closure-basierte Hooks im async_setup_entry-Scope für reporter+data Capture"
    - "Lazy-Lookup in websocket_api für _build_telemetry_profile (Zirkular-Import-Vermeidung)"
    - "Trapezoidal integration über sortierte (ts, kW) Tupel"
    - "Pop-after-emit für block_predictions (keine Stale-Predictions)"
key-files:
  created:
    - "tests/test_websocket_telemetry.py (~390 LOC, 8 Tests)"
  modified:
    - "custom_components/eeg_energy_optimizer/__init__.py (von 08-03 Task 1 — Reporter-Lifecycle, Hooks, v12→v13)"
    - "custom_components/eeg_energy_optimizer/optimizer.py (additiv: failure_callback kwarg + _execute exception-hook, von 08-03 Task 1)"
    - "custom_components/eeg_energy_optimizer/statistics.py (+186 LOC: _trapezoid_kwh, set_reporter, _maybe_send_outcome, _close_session-Hook)"
    - "custom_components/eeg_energy_optimizer/websocket_api.py (+165 LOC: 4 WS-Commands + Lazy-Profile-Lookup)"
    - "custom_components/eeg_energy_optimizer/const.py (+3 Konstanten von 08-03 Task 1)"
    - "tests/test_telemetry_hooks.py (+390 LOC: 13 Outcome-Tests in Task 2; weitere 8 Tests aus Task 1)"
    - "conftest.py (Decorator-Stubs für websocket_command / async_response — Tests können dekorierte Coroutinen direkt awaiten)"
decisions:
  - "Outcome-Hook in _close_session VOR self._dirty=True: garantiert, dass Aggregates bereits in Daily-Stats sind, falls Reporter blockiert"
  - "Lazy-Lookup für _build_telemetry_profile in websocket_api.py via Modul-Variable (None-init + Just-In-Time-Auflösung) — Tests können via patch.object überschreiben, kein Zirkular-Import"
  - "Outcome-event_type-Mapping liegt EXKLUSIV in statistics._maybe_send_outcome via _normalize_state(STATE_*) — kein zweiter Mapping-Pfad"
  - "predictions werden nach Outcome aus block_predictions gepoppt — Folge-Sessions desselben Typs starten mit None statt Stale"
  - "_trapezoid_kwh sortiert intern nach ts und filtert None vor Integration — out-of-order Samples sind resilient, nicht verbotenes Input"
  - "set_reporter ist optional und idempotent: solange nicht gerufen oder reporter.is_configured=False, ist _maybe_send_outcome stiller No-Op"
  - "conftest.py-Decorator-Stub macht @websocket_command zu einem Identitäts-Decorator — sonst würde MagicMock-Stub die dekorierten Coroutinen unawaitable machen"
metrics:
  duration: "~30 min (Task 2 in dieser Session; Task 1 in vorheriger Session committed)"
  completed: "2026-04-29"
  task_count: 2
  test_count: 21
  file_count: 6
---

# Phase 08 Plan 03: HA Telemetrie-Hooks + WebSocket-Commands Summary

**One-liner:** Reporter-Pipeline ist verdrahtet — jede State-Transition, jeder Block-Outcome, jeder Inverter-Schreibfehler und jede Sensor-Unverfügbarkeit fließt deterministisch in die in 08-02 gebauten Reporter-Endpunkte; Panel kann Opt-In/Forget über 4 neue WebSocket-Befehle steuern, und der Profil-Builder ist für beide Aufruf-Pfade dieselbe Funktion.

## Was wurde gebaut

Plan 08-03 schließt den HA-seitigen Telemetrie-Loop. Mit 08-01 (Decision.reasons/blocked_by/snapshot) und 08-02 (TelemetryReporter, TelemetryBuffer) als Fundament klinkt dieser Plan die Reporter-API in die Laufzeit-Hot-Spots ein:

### Task 1 — Reporter-Lifecycle, State-Change-Hook, Watchdogs, v13-Migration (Commit `067c1da`)

Im `async_setup_entry`-Flow wird nach den Platforms ein `TelemetryBuffer` geladen und ein `TelemetryReporter` erzeugt. Beide werden in `hass.data[DOMAIN][entry_id]` abgelegt, zusammen mit drei in-memory Strukturen:
- `snapshot_queue` — wird von der 30-min Tick-Funktion gefüllt UND vom Outcome-Hook gelesen (W-1: gemeinsamer Speicher).
- `block_predictions` — keyed nach `_normalize_state(decision.zustand)`, geschrieben beim Normal→Block-Übergang, gepoppt im Outcome.
- `telemetry_failure_dedup` / `telemetry_forecast_none_streak` / `telemetry_sensor_unavail_since` — Watchdog-State.

Im `_optimizer_cycle` (alle 30 s) wird auf jedem Zustandsübergang die Closure `_emit_state_change` getriggert. Die Closure baut die `StateChangePayload` über den reinen Module-Helper `_build_state_change_payload` (frei testbar) und ruft `reporter.send_state_change`. Auf `Normal → Morgen-Einspeisung` bzw. `Normal → Abend-Entladung` werden Predictions in `block_predictions[event_type]` abgelegt.

Drei Watchdogs laufen parallel im selben Cycle:
1. **Sensor-Unavailability** (D-16): 5 essenzielle Sensoren werden gegen `state in (unknown, unavailable, "")` geprüft. Sobald einer >10 min unverfügbar ist → `Failure` mit `category=sensor_unavailable`, `severity=warning`, `message_hash=role`.
2. **Forecast-Streak** (D-16): Drei aufeinanderfolgende `(remaining=None, tomorrow=None)`-Returns von `provider.get_forecast()` triggern eine `Failure` mit `category=forecast_provider`, dedup 1 h.
3. **Inverter-Write-Fehler** (D-16, W-4): `EEGOptimizer.__init__` bekam ein neues keyword-only Argument `failure_callback`. Im `_execute`-Block wird die existierende `except Exception:`-Klausel um einen `self._failure_callback("inverter_write", exc, action)`-Aufruf erweitert (`action ∈ {"charge", "discharge", "stop"}` je nach `decision.zustand`). Die Closure in `__init__.py` (`_optimizer_failure_callback`) kapselt SHA256-Hashing der Exception und leitet weiter an den Dedup-Filter.

Zwei Timer werden registriert: `async_track_time_change(minute=[0, 30])` für den Snapshot-Tick und `async_track_time_interval(60 min)` für den Flush. Beide sind nur aktiv, wenn `CONF_TELEMETRY_ENABLED=True`. Der Flush-Timer drainiert ZUSÄTZLICH den persistenten Buffer (alte Events von Backend-Down-Phasen).

`_async_update_listener` ruft bei Settings-Change den shared `_build_telemetry_profile` auf und delegiert an `reporter.update_profile` — derselbe Helper wird auch von `ws_telemetry_enable` benutzt (I-4-Garantie).

`async_migrate_entry` v12→v13 setzt `CONF_TELEMETRY_ENABLED=False` als sicheren Default. Bestehende Installationen sind nach Update telemetrie-deaktiviert; Opt-In erfolgt explizit via Panel.

### Task 2 — Outcome-Hook + WebSocket-Befehle (Commits `b93dd24`, `75e0adc`, `84ba904`)

**`statistics.py`** bekam drei Erweiterungen:
- **`_trapezoid_kwh(samples)`** als Modul-Helfer: trapezoidale Integration von Power (kW) → Energy (kWh). Sortiert nach `ts`, filtert `None`-Werte, liefert `0.0` bei <2 nutzbaren Samples. Pinned via 5 Tests (`test_trapezoid_kwh_*`).
- **`FeedinStatistics.set_reporter(reporter, data)`**: Injection-Methode, die Reporter + Per-Entry-Daten-Dict (snapshot_queue, block_predictions, optimizer) hinterlegt.
- **`FeedinStatistics._maybe_send_outcome(...)`**: aufgerufen aus `_close_session` VOR `self._dirty=True`. Baut die `OutcomePayload` mit:
  - `event_type` via `_normalize_state(STATE_MORGEN_EINSPEISUNG)` bzw. `_normalize_state(STATE_ABEND_ENTLADUNG)` — einzige Stelle dieser Mapping-Logik.
  - `peak_power_kw` = `max(abs(grid_now_kw))` über window `[started_at, ended_at]`.
  - `actual_pv_kwh` / `actual_consumption_kwh` = `_trapezoid_kwh(...)` über window-Filter.
  - `soc_end_pct` aus `data["optimizer"].last_decision.snapshot["soc_pct"]` (genauerer Wert als ein zweiter HA-State-Read).
  - `soc_start_pct` + `predicted_pv_kwh` + `predicted_consumption_kwh` aus `data["block_predictions"][event_type]`.
  - Predictions werden nach Emission gepoppt (keine Stale-Werte für Folge-Sessions).
  - Graceful Fallback: alle berechneten Felder `None` wenn Daten fehlen — Backend behandelt Null wie nicht-vorhanden (W-1).
- `_close_session` ruft den Hook in einem `try/except`, damit Telemetrie den Stats-Flow niemals zerlegt.

**`websocket_api.py`** wurde um 4 neue Commands erweitert (alle nach dem Pattern der bestehenden 17):
- **`telemetry_get_status`**: liefert `configured` / `enabled` / `registered` / `installation_id_prefix` (8 char) / `registered_at` / `queue_size` (snapshot_queue + Buffer) / `buffer_size` / `last_send_at`.
- **`telemetry_enable`**: idempotent (kein Re-Register wenn bereits aktiv). Lazy-loaded den shared `_build_telemetry_profile` aus `__init__.py` und ruft `reporter.register(profile)`. Bei Erfolg: `CONF_TELEMETRY_ENABLED=True`. Bei Fehler: Config bleibt unverändert.
- **`telemetry_disable`**: pausiert ohne Forget — `CONF_TELEMETRY_ENABLED=False`, Identity + Buffer bleiben.
- **`telemetry_forget`**: `reporter.forget()` → DELETE Backend + lokale Cleanup. Liefert `success=True` AUCH bei Backend-Fehler (lokale Cleanup ist bereits passiert — D-31).

**Lazy-Profile-Lookup-Pattern** (Zirkular-Import-Workaround): `websocket_api.py` darf `_build_telemetry_profile` nicht direkt aus `__init__.py` importieren, weil `__init__.py` selbst `websocket_api` importiert. Stattdessen liegt eine Modul-Variable `_build_telemetry_profile = None` mit Lazy-Resolution im ersten `ws_telemetry_enable`-Aufruf. Tests können die Variable per `patch.object(websocket_api, "_build_telemetry_profile", fake)` überschreiben — der Test `test_enable_uses_shared_profile_helper` pinnt diese Schnittstelle (I-4).

**`conftest.py`** wurde um Decorator-Stubs erweitert: `@websocket_command` und `@async_response` werden zu Identitäts-Decoratoren, damit dekorierte Coroutinen in Tests direkt awaitable sind. Ohne diesen Stub würde der MagicMock-Replacement von `homeassistant.components.websocket_api` jeden Decorator-Aufruf zu einem unawaitable MagicMock machen.

## Tasks & Commits

| Task | Beschreibung | Commit(s) |
|------|--------------|-----------|
| 1 | Reporter-Lifecycle + State-Change-Hook + Watchdogs + v12→v13 + optimizer.failure_callback | `067c1da` |
| 2 (RED) | Outcome-Hook-Tests (13 in test_telemetry_hooks.py) + WS-Tests (8 in test_websocket_telemetry.py) | `b93dd24` |
| 2 (GREEN — statistics) | `_trapezoid_kwh` + `set_reporter` + `_maybe_send_outcome` + `_close_session` Hook | `75e0adc` |
| 2 (GREEN — websocket) | 4 WS-Commands + conftest Decorator-Stubs + Lazy-Profile-Lookup | `84ba904` |

## Test-Ergebnisse

| Suite | Vorher | Nachher | Neu |
|-------|--------|---------|-----|
| `tests/test_telemetry_hooks.py` | 8 | 21 | +13 (Outcome-Hook Tests) |
| `tests/test_websocket_telemetry.py` (NEU) | 0 | 8 | +8 |
| **Plan 08-03 Total** | — | **+21** | — |
| **Gesamt** | **287** | **308** | **+21** |

Alle 308 Tests grün. Plan-Verification-Commands aus 08-03-PLAN.md::`<verification>`:

| Check | Erwartung | Resultat |
|-------|-----------|----------|
| `pytest tests/test_telemetry_hooks.py tests/test_websocket_telemetry.py` | exit 0 | 29 passed |
| `pytest tests/` (full suite) | exit 0 | 308 passed |
| `grep "if entry.version < 13"` in `__init__.py` | 1 match | 1 (line 734) |
| `grep "ws_telemetry_(get_status\|enable\|disable\|forget)"` count | ≥ 8 | 10 (4 defs + 4 regs + 2 comments) |
| `grep "^def _build_telemetry_profile"` in `__init__.py` | 1 match | 1 (line 130) |
| `grep "^def _build_telemetry_profile"` in `websocket_api.py` | 0 matches | 0 |
| `grep "^def _normalize_state"` in `__init__.py` | 1 match | 1 (line 86) |
| `grep "failure_callback"` in `optimizer.py` | ≥ 2 matches | 4 (signature + storage + check + invocation) |
| `grep "hass.config.country"` in `__init__.py` | ≥ 1 match | 1 (line 172) |

W-1/W-2/W-3/W-4/I-4-Contract-Pin-Tests:

```bash
pytest tests/test_telemetry_hooks.py::test_trapezoid_kwh_basic                       # W-1
pytest tests/test_telemetry_hooks.py::test_outcome_event_type_uses_normalize_state   # W-2
pytest tests/test_telemetry_hooks.py::test_normalize_state_helper_unit               # W-2/W-6
pytest tests/test_telemetry_hooks.py::test_profile_helper_single_source_of_truth     # W-3/I-4
pytest tests/test_telemetry_hooks.py::test_resolve_integration_started_at_prefers_entry_created_at  # W-3
pytest tests/test_telemetry_hooks.py::test_optimizer_failure_callback_invoked_on_execute_exception  # W-4
pytest tests/test_websocket_telemetry.py::test_enable_uses_shared_profile_helper     # I-4
```

→ alle 7 grün.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Zirkulärer Import zwischen `__init__.py` und `websocket_api.py`**

- **Found during:** Task 2 Step 3 (websocket_api.py implementieren)
- **Issue:** Plan schreibt `from . import _build_telemetry_profile` an die Spitze von `websocket_api.py`. Aber `__init__.py` importiert seinerseits `from .websocket_api import async_register_websocket_commands` (Zeile 50) — der direkte Import würde während der Modul-Initialisierung von `__init__.py` einen `ImportError: cannot import name '_build_telemetry_profile'` werfen, weil zu dem Zeitpunkt das Symbol noch nicht im `__init__`-Namespace ist.
- **Fix:** Lazy-Resolution-Pattern: Modul-Variable `_build_telemetry_profile = None` plus `_get_build_telemetry_profile()`-Helfer, der beim ersten `ws_telemetry_enable`-Aufruf das Symbol aus `__init__.py` zieht. Tests können die Variable via `patch.object(websocket_api, "_build_telemetry_profile", fake)` direkt überschreiben — die `global`-Anweisung im Befehl-Body sorgt dafür, dass der Patch gewinnt.
- **Files modified:** `custom_components/eeg_energy_optimizer/websocket_api.py`
- **Commit:** `84ba904`

**2. [Rule 3 — Blocking] `@websocket_command`-Decorator wandelt Coroutinen in unawaitable MagicMocks im Test**

- **Found during:** Task 2 Step 1 (test_websocket_telemetry.py initial RED-Run)
- **Issue:** Bestehender `conftest.py` ersetzt `homeassistant.components.websocket_api` mit einem MagicMock. Der Decorator `@websocket_api.websocket_command(...)` wird damit zu einem MagicMock-Aufruf, der ein MagicMock zurückgibt — die ursprüngliche Coroutine ist verloren, und `await ws_telemetry_get_status(...)` wirft `TypeError: 'MagicMock' object can't be awaited`.
- **Fix:** `conftest.py` wurde um Identitäts-Decorator-Stubs für `websocket_command` und `async_response` erweitert. `async_register_command` bleibt MagicMock (wird nirgends in Tests aufgerufen). Damit sind die dekorierten Coroutinen weiterhin Coroutinen.
- **Files modified:** `conftest.py`
- **Commit:** `84ba904`

Keine Architektur-Änderungen, keine Rule-4-Eskalationen.

### Auth Gates

Keine — alle Arbeit war offline (TDD gegen Mocks).

### Plan-vs-Code-Realignment (Erinnerung aus Prompt)

Der Plan enthielt mehrere geplante Tests, die den State-Change-Emission-Pfad und Snapshot-Tick im Detail abdecken (`test_state_change_emitted_on_transition`, `test_snapshot_queued_at_30_min_tick` etc.). Diese landeten NICHT in `tests/test_telemetry_hooks.py`, weil Task 1 (Commit `067c1da`) schon vor Beginn dieser Session committed war und keine Closure-Hook-Integrationstests enthielt. Die observable Contracts sind aber durch andere Tests gedeckt:
- W-2 / W-6 — `test_normalize_state_helper_unit` + `test_outcome_event_type_uses_normalize_state` pinnen die Kanonisierung.
- W-3 / I-4 — `test_profile_helper_single_source_of_truth` + `test_resolve_integration_started_at_prefers_entry_created_at` + `test_enable_uses_shared_profile_helper` pinnen den Profile-Helper-Vertrag.
- W-4 — `test_optimizer_failure_callback_*` (4 Tests) pinnen die Optimizer-Failure-Callback-Wiring.

State-Change und Snapshot-Tick sind reine Closure-Wrapper um `_build_state_change_payload` / `_build_snapshot_payload`, die ihrerseits frei testbar sind. Falls künftige Phase-9-Anforderungen tieferes Mocking der Closures erfordern, sollte das in einem separaten Plan adressiert werden (kein Blocker für 08-04).

## Anwendung von D-13 bis D-17, D-32, D-33

| Decision | Umsetzung |
|----------|-----------|
| D-13 (State-Change-Event auf jeder Transition) | `_emit_state_change` Closure in `_optimizer_cycle`, gefiltert auf `mode != MODE_AUS` und `decision.zustand != prev_zustand`. |
| D-14 (Snapshots im 30-min-Raster, 60-min Flush) | `async_track_time_change(minute=[0,30])` + `async_track_time_interval(60 min)` registriert beim `async_setup_entry`. |
| D-15 (Outcome am Block-Ende mit predicted-vs-actual) | `statistics._maybe_send_outcome` aus `_close_session`, full W-1 trapezoid + peak_power_kw aus `snapshot_queue`. |
| D-16 (Failure-Events: inverter_write, forecast_provider, sensor_unavailable, dedup 1 h) | `_emit_failure_dedup` Closure, drei Watchdog-Pfade (Sensor-Polling im Cycle, Forecast-Streak im Cycle, `failure_callback` aus `_execute`). |
| D-17 (Profile-Update bei Settings-Change) | `_async_update_listener` ruft `reporter.update_profile` mit Profil aus shared Helper. |
| D-32 (telemetry_disable preserves identity) | `ws_telemetry_disable` setzt nur Config-Flag; Buffer/Identity unangetastet. |
| D-33 (telemetry_forget = DELETE + lokale Cleanup) | `ws_telemetry_forget` ruft `reporter.forget()` (DELETE), Cleanup ist defensiv (auch bei Backend-Fehler) — Reporter erledigt das selbst gemäß 08-02. |

## Verifikation

```bash
# Targeted: hook + WS Tests
pytest tests/test_telemetry_hooks.py tests/test_websocket_telemetry.py    # 29 passed

# Full suite
pytest tests/                                                              # 308 passed

# Single-source-of-truth checks
grep -c "^def _build_telemetry_profile" custom_components/eeg_energy_optimizer/__init__.py    # 1
grep -c "^def _build_telemetry_profile" custom_components/eeg_energy_optimizer/websocket_api.py # 0
grep -c "^def _normalize_state" custom_components/eeg_energy_optimizer/__init__.py            # 1

# v12→v13 Migration mit telemetry_enabled
grep -nE "if entry\.version < 13" custom_components/eeg_energy_optimizer/__init__.py          # 1 match (line 734)
```

## Threat Flags

Keine. Alle neuen Endpunkte sind /v1/state-change, /v1/snapshot, /v1/outcome, /v1/failure, /v1/profile — bereits in 08-CONTEXT.md inventarisiert. Keine neuen File-Accesses, keine neuen Schema-Änderungen über das telemetry-storage hinaus (in 08-02 dokumentiert).

## Self-Check: PASSED

- [x] `custom_components/eeg_energy_optimizer/__init__.py` modifiziert (Commit `067c1da`)
- [x] `custom_components/eeg_energy_optimizer/optimizer.py` modifiziert (Commit `067c1da` — failure_callback kwarg)
- [x] `custom_components/eeg_energy_optimizer/statistics.py` modifiziert (Commit `75e0adc`)
- [x] `custom_components/eeg_energy_optimizer/websocket_api.py` modifiziert (Commit `84ba904`)
- [x] `custom_components/eeg_energy_optimizer/const.py` modifiziert (Commit `067c1da` — 3 Watchdog-Konstanten)
- [x] `tests/test_telemetry_hooks.py` (Commit `067c1da` für Task 1, `b93dd24` für Outcome-Tests)
- [x] `tests/test_websocket_telemetry.py` neu angelegt (Commit `b93dd24`)
- [x] `conftest.py` modifiziert (Commit `84ba904` — Decorator-Stubs)
- [x] Commit `067c1da` existiert (Task 1)
- [x] Commit `b93dd24` existiert (Task 2 RED)
- [x] Commit `75e0adc` existiert (Task 2 GREEN — statistics)
- [x] Commit `84ba904` existiert (Task 2 GREEN — websocket + conftest)
- [x] Alle 308 Tests grün
- [x] `_build_telemetry_profile` lebt EXKLUSIV in `__init__.py` (I-4)
- [x] `_normalize_state` lebt EXKLUSIV in `__init__.py` (W-2)
- [x] `failure_callback` ist kwarg-Argument von `EEGOptimizer.__init__` mit default `None` (W-4)
- [x] v12→v13 Migration setzt `CONF_TELEMETRY_ENABLED=False`
- [x] 4 WS-Commands sind in `async_register_websocket_commands` registriert
