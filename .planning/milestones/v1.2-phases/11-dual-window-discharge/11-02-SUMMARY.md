---
phase: 11
plan: 02
subsystem: optimizer-decision-engine
tags: [dual-window, optimizer-refactor, peakshare-cache, hysteresis, slot-marker]
requires:
  - "Plan 11-01: compute_b_window_end + 8 REASON_*-Keys + Decision.discharge_active_slot + Migration v14→v15 + Test-Helpers"
provides:
  - "_should_discharge als Dispatcher (~33 LOC), routet anhand enable_dual_discharge + _is_solaredge"
  - "_check_common_guards (slot-übergreifende Guards für Dual-Mode)"
  - "_evaluate_slot_a (SPEC §2 — Reserve-aware Abend-Entladung)"
  - "_evaluate_slot_b (SPEC §3 — adaptives Ende via compute_b_window_end)"
  - "_evaluate_legacy_window (D-05 byte-identische Single-Window-Logik)"
  - "Pro-Slot-Hysterese-Felder _slot_a_activated_date / _slot_b_activated_date / _last_active_slot mit Sunrise-keyed Reset"
  - "SolarEdge-Runtime-Force in __init__ (Defense-in-depth, T-11-02-02)"
  - "Decision.discharge_active_slot wird in _evaluate aus REASON_SLOT_A/B_ACTIVE abgeleitet"
  - "PeakShareProvider._discharge_plan: dict[a/b] mit gemeinsamem Tageslock + slot-Parameter in get_discharge_plan"
  - "Schema-Migration: alte tuple-Form wird in async_load verworfen (T-11-02-03)"
affects:
  - custom_components/eeg_energy_optimizer/optimizer.py
  - custom_components/eeg_energy_optimizer/peakshare.py
  - custom_components/eeg_energy_optimizer/websocket_api.py
  - tests/test_dual_window.py
tech-stack:
  added: []
  patterns:
    - "Dispatcher-Pattern: _should_discharge wählt einen von drei Pfaden"
    - "Setdefault statt Hard-Set für Cache-Schema-Migration (alte tuple-Form verworfen, neue dict-Form gefüllt)"
    - "Defense-in-depth Runtime-Force (zwei unabhängige Layer: Migration + __init__)"
    - "Slot-Marker via Reasons-Liste-Lookup (REASON_SLOT_A/B_ACTIVE → active_slot)"
    - "Past-Midnight-Phase-Detection (now < 12 AND start_h >= 12) für Slot A"
key-files:
  created: []
  modified:
    - custom_components/eeg_energy_optimizer/optimizer.py
    - custom_components/eeg_energy_optimizer/peakshare.py
    - custom_components/eeg_energy_optimizer/websocket_api.py
    - tests/test_dual_window.py
decisions:
  - "Default für _enable_dual_discharge ist False (im __init__) — Bestands-Tests ohne explizit gesetzten Key routen auf Legacy-Pfad. Echte Setups bekommen den Wert via v14→v15-Migration."
  - "_evaluate_legacy_window enthält den Body 1:1 (D-05). KEINE Guard-Entfernung trotz _check_common_guards — Common-Guards werden NUR im Dual-Mode-Pfad aufgerufen."
  - "Slot A erkennt Past-Midnight-Phase: now < 12 AND a_start_h >= 12 → A läuft vom Vorabend weiter. Andernfalls würde A nicht über Mitternacht laufen können (inkonsistent zur 'endet 5min vor B-Start'-Regel)."
  - "PeakShare-Decision-Felder im Optimizer wählen Slot-Plan abhängig vom active_slot: Dual-B → Slot-B-Plan, sonst → Slot-A-Plan."
  - "websocket_api zeigt nur Slot-A-Plan im Panel (Hauptfenster) — Slot-B-Visualisierung kommt in 11-03/11-04."
metrics:
  duration: "ca. 35 Minuten (3 Edits + 3 Test-Runs + 4 Commits)"
  completed: "2026-05-04"
  tasks_completed: 2
  files_changed: 4
  lines_added_approx: 1138
---

# Phase 11 Plan 02: Optimizer-Refactor + PeakShare-Cache-Schema — Summary

Refactor der Decision-Engine zu einem Dispatcher mit drei Pfaden (Legacy / Slot-A / Slot-B), Pro-Slot-Hysterese-Felder, PeakShare-Cache-Schema-Migration auf `dict[a/b]`, und 24h-Simulationstests für die SPEC §8-Anforderungen.

## Refactor-Struktur

### `_should_discharge` als Dispatcher

```python
def _should_discharge(self, snap):
    use_legacy = (not self._enable_dual_discharge) or self._is_solaredge
    if use_legacy:
        return self._evaluate_legacy_window(snap)
    common_blocked, min_soc = self._check_common_guards(snap)
    if common_blocked:
        return (False, min_soc, [], common_blocked, False)
    # Slot A bevorzugt, Slot B als Fallback
    if self._enable_slot_a:
        passed_a, ... = self._evaluate_slot_a(snap, min_soc)
        if passed_a:
            return (True, min_soc, ..., hyst_a)
    if self._enable_slot_b:
        passed_b, ... = self._evaluate_slot_b(snap, min_soc)
        if passed_b:
            return (True, min_soc, ..., hyst_b)
    # Beide blockiert → kombinierte blocked_by-Liste
    ...
```

**Body-Größen:**
| Methode | LOC | Zweck |
| ------- | --- | ----- |
| `_should_discharge` | ~33 | Dispatcher (Legacy vs Common-Guards + Slot-A/B) |
| `_check_common_guards` | ~40 | night_disabled, demand_too_high, soc_unavailable (in `_evaluate`), discharge_aborted, tomorrow_pv |
| `_evaluate_slot_a` | ~67 | Past-Midnight-Phase-Detection, 5min-Pause vor B, Reserve-aware SOC-Schwelle, Hysterese-Aufschlag |
| `_evaluate_slot_b` | ~70 | b_start (mit Tag-Verschiebung), `compute_b_window_end`, Hysterese-Aufschlag |
| `_evaluate_legacy_window` | ~152 | Heutige Body 1:1 — D-05 byte-identische Garantie |

### Pro-Slot-Hysterese-Felder + Reset-Trigger

In `__init__` (nach Legacy-Hysterese-Feldern):
```python
self._slot_a_activated_date: str | None = None
self._slot_b_activated_date: str | None = None
self._last_active_slot: str | None = None  # "A" | "B" | None
```

Reset-Trigger in `_evaluate` (analog `_discharge_activated_date`):
```python
if (
    self._slot_a_activated_date is not None
    and self._slot_a_activated_date < today_str
    and snap.sunrise_today is not None
    and snap.now >= snap.sunrise_today
):
    self._slot_a_activated_date = None
# (gleiche Logik für slot_b)
```

**Reset NUR nach today's Sunrise** — nicht zu Mitternacht. Verhindert das Aushebeln der Hysterese durch Datums-Wechsel (T-11-02-01).

Aktivierungsdatum-Tracking in `_evaluate`:
```python
if zustand == STATE_ABEND_ENTLADUNG:
    if self._discharge_activated_date is None:
        self._discharge_activated_date = today_str
    if active_slot == "A":
        if self._slot_a_activated_date is None:
            self._slot_a_activated_date = today_str
        self._last_active_slot = "A"
    elif active_slot == "B":
        if self._slot_b_activated_date is None:
            self._slot_b_activated_date = today_str
        self._last_active_slot = "B"
```

### SolarEdge-Runtime-Force-Stelle

In `EEGOptimizer.__init__` (nach Phase-11-Config-Reads):
```python
if self._is_solaredge and self._enable_dual_discharge:
    _LOGGER.warning(
        "SolarEdge: enable_dual_discharge=True nicht erlaubt — "
        "auf False gesetzt (NVRAM-Verschleiß-Schutz)"
    )
    self._enable_dual_discharge = False
```

Defense-in-depth — auch wenn die Migration v14→v15 (Plan 11-01) bereits `enable_dual_discharge=False` für SolarEdge schreibt, schützt diese Runtime-Prüfung vor manuellem Tampering der Config (T-11-02-02).

### Decision.discharge_active_slot

Wird in `_evaluate` aus den Reasons abgeleitet:
```python
active_slot: str | None = None
if zustand == STATE_ABEND_ENTLADUNG:
    if REASON_SLOT_A_ACTIVE in dis_reasons_keys:
        active_slot = "A"
    elif REASON_SLOT_B_ACTIVE in dis_reasons_keys:
        active_slot = "B"
# ...
decision = Decision(
    ...,
    discharge_active_slot=active_slot,
)
```

Im Legacy-Pfad bleibt `active_slot=None` (keine Slot-Reasons in `dis_reasons_keys`) — D-10 explizit so verlangt.

## PeakShare-Cache-Schema-Migration

### Init (peakshare.py:160-178)
```python
self._discharge_plan: dict[str, tuple[datetime, datetime] | None] = {
    "a": None, "b": None,
}
self._discharge_plan_date: str | None = None  # gemeinsames Tageslock
```

### async_load (peakshare.py:180-208)
Liest `data`/`fetched_at`/`jitter_value`/`jitter_date` aus dem Persistat, verwirft aber das alte tuple-Form-Persistat des `_discharge_plan` explizit:
```python
# Phase 11: Cache-Schema-Migration — alte tuple-Form wird verworfen,
# nächster Cycle berechnet neu.
self._discharge_plan = {"a": None, "b": None}
self._discharge_plan_date = None
```

### async_fetch (peakshare.py:243-251)
Cache-Invalidate setzt das gesamte dict zurück:
```python
self._discharge_plan = {"a": None, "b": None}
self._discharge_plan_date = None
```

### get_discharge_plan (peakshare.py:308-432)
Neue keyword-only-Parameter:
```python
def get_discharge_plan(
    self,
    community: str,
    available_kwh: float,
    discharge_power_kw: float,
    sunset_time: datetime | None,
    now: datetime,
    discharge_start_lower_bound: datetime | None = None,
    next_sunrise: datetime | None = None,
    *,
    slot: str = "a",
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> tuple[datetime, datetime] | None:
```

**Cache-Lookup nutzt slot:**
```python
if self._discharge_plan_date == today_str:
    return self._discharge_plan.get(slot)
```

**Plan-Lock pro Slot:**
```python
self._discharge_plan[slot] = plan
self._discharge_plan_date = today_str
```

**Edge-Case (window_start ≥ window_end):**
```python
self._discharge_plan[slot] = None
self._discharge_plan_date = today_str
return None
```

### Optimizer-Code-Pfade angepasst
- `_discharge_detail_status` (`optimizer.py:871-882`): `plan_dict.get("a")` (Legacy nutzt Slot "a").
- `_evaluate` PeakShare-Decision-Felder (`optimizer.py:1620-1635`): `slot_key = "b" if active_slot == "B" else "a"`.
- `_evaluate` next-aktion-Anzeige (`optimizer.py:1554-1558`): `get_discharge_plan(...)` ohne explicit slot → Default "a".

### websocket_api.py
`get_peakshare_data` (`websocket_api.py:1242-1259`): zeigt nur Slot-A-Plan im Panel; Slot-B-Visualisierung kommt erst in 11-03/11-04.

## 24h-Simulationstest-Ergebnisse

`TestDualWindow24hSimulation` simuliert einen Wintertag (21./22.12.2026, Sunrise 07:30):

| Szenario | Slot A erwartet | Slot B erwartet | Slot-Sequenz (Stunden 18-29) |
| -------- | --------------- | --------------- | ---------------------------- |
| Dual (A+B) | ✓ | ✓ | 20-26: A; 27-29: B (ab 03:00) |
| A-only | ✓ | ✗ | 20-26: A; danach Reserve |
| B-only | ✗ | ✓ | 27-29: B (ab 03:00) |

Alle drei Tests grün — SPEC §8 (Independent Slot-Aktivierung) bestätigt.

**Sunrise-Konvention im snap_factory** ist HA-style: "next upcoming sunrise". Vor today's Sunrise → today's; danach → tomorrow's. Diese Korrektheit war essenziell — eine vorherige Iteration setzte `sunrise=sunrise_today` für `hour < 8` auch im Folgetag, was `compute_b_window_end` einen vergangenen Sunrise gab und Slot B fälschlich blockierte.

## Test-Status

| Suite | Vorher (Plan 11-01) | Nachher (Plan 11-02) | Δ |
| ----- | ------------------- | -------------------- | - |
| `tests/test_dual_window.py` | 14 passed | 42 passed | +28 |
| `tests/test_optimizer.py` | 86 passed | 86 passed | ±0 (D-05) |
| `tests/test_config_flow.py` | 6 passed, 1 fail | 6 passed, 1 fail | ±0 (OOS) |
| `pytest tests/ -q` (gesamt) | 366 passed, 1 fail | 394 passed, 1 fail | +28 |

**Pre-existing Failure** (out-of-scope, nicht Plan-11-relevant):
`tests/test_config_flow.py::TestStepUser::test_creates_entry_on_confirmation` — telemetry_enabled=True wird beim Step-User in CONF_*-Daten gesetzt, aber Test erwartet nur `setup_complete=False`. Existierte schon vor Plan 11-01.

### Neue Test-Klassen (Plan 11-02)

| Klasse | Tests | Coverage |
| ------ | ----- | -------- |
| `TestSlotAReserveLogic` | 4 | A-only/Dual SOC-Schwelle, 5min-Pause vor B, vor a_start |
| `TestSlotBLogic` | 4 | b_only SOC, expired, sommer-edge-case, vor b_start |
| `TestProSlotHysteresis` | 2 | A-Reaktivierung +5%, B startet ohne Aufschlag |
| `TestSlotBPreSunriseCutoff` | 7 (param.) | Mutex ≥5min für sunrise×offset-Matrix |
| `TestMutualExclusion` | 1 | Slot B endet vor Morgen-Einspeisungs-Start |
| `TestSolarEdgeRuntimeForce` | 1 | __init__ forced dual_discharge auf False |
| `TestEnableDualDischargeFalseLegacyPath` | 2 | dual=False + SolarEdge → Legacy |
| `TestPeakShareCacheSchema` | 4 | dict[a/b]-Init, slot-Lookups, Invalidate |
| `TestDualWindow24hSimulation` | 3 | A-only / B-only / Dual SPEC §8 |
| **Summe** | **28** | |

## Pattern-Checks

```text
def _check_common_guards: 1 ✓
def _evaluate_slot_a: 1 ✓
def _evaluate_slot_b: 1 ✓
def _evaluate_legacy_window: 1 ✓
def _should_discharge: 1 ✓ (jetzt Dispatcher)
self._slot_a_activated_date: 7 (>= 4) ✓
self._slot_b_activated_date: 7 (>= 4) ✓
self._last_active_slot: 5 (>= 3) ✓
compute_b_window_end(: 2 ✓
self._is_solaredge and self._enable_dual_discharge: 1 ✓ (Runtime-Force)
self._discharge_plan: dict: 1 ✓
"a": None, "b": None: 2 (>= 2) ✓
slot: str = "a": 1 ✓
self._discharge_plan[slot]: 2 ✓
self._discharge_plan.get(slot): 1 ✓
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Slot A lief nicht über Mitternacht**
- **Found during:** Task 1 — `test_a_ends_5min_before_b_start` (now=02:56) failed mit `REASON_BEFORE_SLOT_A` statt `REASON_SLOT_A_RESERVE_REACHED`.
- **Issue:** Reines `if snap.now < a_start_today` blockt Slot A in der Past-Midnight-Phase fälschlich. SPEC §2 ("endet automatisch wenn SOC ≤ Reserve, oder spätestens 5 Minuten vor `discharge_b_start_time`") impliziert aber, dass Slot A über Mitternacht weiterläuft.
- **Fix:** Past-Midnight-Phase-Detection: `is_past_midnight_phase = snap.now.hour < 12 and self._discharge_a_start_h >= 12`. Wenn diese Phase aktiv → der Vor-a_start-Block wird übersprungen.
- **Files modified:** `custom_components/eeg_energy_optimizer/optimizer.py:1095-1110`
- **Commit:** 9651e08 (zusammen mit den Tests).

**2. [Rule 1 — Bug] 24h-Simulations-Snap_factory hatte falsche Sunrise**
- **Found during:** Task 2 — `test_dual_a_and_b_both_activate` failed weil Slot B in den Stunden 27-29 (= 03:00-05:00 Folgetag) nicht aktivierte.
- **Issue:** Im snap_factory wurde `sunrise=sunrise_today` für `hour_norm < 8` verwendet — auch wenn `day=22`. Dann zeigte sunrise auf 21.12. 07:30 (Vergangenheit), was `compute_b_window_end` einen vergangenen Sunrise gab → b_end < b_start → REASON_SLOT_B_PRE_SUNRISE_CUTOFF.
- **Fix:** Sunrise-Resolution auf "next upcoming" angepasst: `if day == 22 or (day == 21 and hour_norm >= 8): snap_sunrise = sunrise_tomorrow`. Damit zeigt sunrise korrekt auf 22.12. 07:30 für Stunden 22.12. 03:00-05:00.
- **Files modified:** `tests/test_dual_window.py:711-735` (snap_factory in TestDualWindow24hSimulation)
- **Commit:** 36c7523

### Pre-existing Failures Not Touched

**1. `tests/test_config_flow.py::TestStepUser::test_creates_entry_on_confirmation`**
- Test war schon vor Plan-Start failed. Out of scope (Scope-Boundary-Regel). Logged hier zur Vollständigkeit, NICHT gefixt in 11-02.

## Threat Model Compliance

| Threat ID    | Disposition | Mitigation Status |
| ------------ | ----------- | ----------------- |
| T-11-02-01   | mitigate    | ✅ Slot-Hysterese-Reset NUR nach today's Sunrise; Test `test_a_reactivation_requires_min_soc_plus_5` grün |
| T-11-02-02   | mitigate    | ✅ Defense-in-depth: __init__-Force `if self._is_solaredge: self._enable_dual_discharge = False` + Logger-Warning. Test `test_solaredge_init_forces_dual_to_false` grün |
| T-11-02-03   | mitigate    | ✅ async_load setzt `_discharge_plan = {"a": None, "b": None}` explizit. Test `test_init_creates_dict_schema` grün |
| T-11-02-04   | mitigate    | ✅ `_evaluate_slot_a` setzt `a_end_cap = b_start - timedelta(minutes=5)` wenn B aktiv; `compute_b_window_end` zieht 5min für Slot B ab. Test `test_a_ends_5min_before_b_start` grün |
| T-11-02-05   | mitigate    | ✅ `active_slot`-Lookup aus `dis_reasons_keys`-Liste; Test `test_dual_a_and_b_both_activate` validiert Slot-Marker |
| T-11-02-06   | accept      | (Information Disclosure — reasons-Keys sind designed für Telemetrie) |

## Hinweis für Phase 11-03 / 11-04

Plan 11-03 (Panel + Save-Path) baut **direkt** auf der Decision-Engine auf:
- `Decision.discharge_active_slot` ist verfügbar — Panel-Renderer kann den aktiven Slot visualisieren.
- `_should_discharge` ist Dispatcher; Save-Path muss SolarEdge XOR-Validation haben (analog der Runtime-Force in `__init__`).
- PeakShare-Plan ist via `_discharge_plan["a"]` / `_discharge_plan["b"]` zugreifbar — Panel kann beide separat anzeigen.

Plan 11-04 (Markdown-Renderer + Activity-Log) ergänzt:
- `_build_markdown` muss den Slot-Marker (A/B) in der Status-Karte rendern.
- Activity-Log nutzt die neuen Reasons (`slot_a_active`, `slot_b_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`, `before_slot_a`).

## Acceptance Criteria — Status

- [x] `_should_discharge` ist Dispatcher (~33 LOC), routet anhand `enable_dual_discharge` + `_is_solaredge`
- [x] `_evaluate_slot_a` implementiert SPEC §2 (Reserve-Schwelle, 5min-Pause vor B, Past-Midnight-Phase)
- [x] `_evaluate_slot_b` implementiert SPEC §3/§5 (compute_b_window_end, Mutex zur Morgen-Einspeisung)
- [x] `_evaluate_legacy_window` enthält den heutigen Body 1:1 (D-05)
- [x] `_check_common_guards` extrahiert: feature-disabled, demand-too-high, discharge-aborted, tomorrow-pv
- [x] Pro-Slot-Hysterese-Felder existieren mit korrektem Reset (Slot A & B beide nach today's Sunrise)
- [x] `Decision.discharge_active_slot` wird in `_evaluate` gesetzt: "A"/"B" wenn Slot aktiv, sonst None
- [x] PeakShare `_discharge_plans: dict[a/b]`-Schema funktioniert; alter Cache-Inhalt wird invalidiert
- [x] `peakshare.find_discharge_window` ist via `slot=`-Parameter zweimal aufrufbar (für 11-04 vorbereitet — heute nutzt Optimizer im Dual-Mode noch keine PeakShare-Aufrufe pro Slot)
- [x] Alle 24h-Simulationstests grün: A-only, B-only, dual
- [x] `pytest tests/ -q` exit 0 (oder nur das pre-existing OOS-Failure) — 394 passed, 1 OOS-fail
- [x] SUMMARY.md geschrieben

## Self-Check: PASSED

Alle in Frontmatter und Text aufgeführten Artefakte existieren und sind committet:

- ✅ FOUND: `custom_components/eeg_energy_optimizer/optimizer.py` (modified, commits f2509f2 + 9651e08 + b534f59)
- ✅ FOUND: `custom_components/eeg_energy_optimizer/peakshare.py` (modified, commit b534f59)
- ✅ FOUND: `custom_components/eeg_energy_optimizer/websocket_api.py` (modified, commit b534f59)
- ✅ FOUND: `tests/test_dual_window.py` (modified, commits 9651e08 + 36c7523)
- ✅ FOUND: commit `f2509f2` (refactor: dispatcher) in git log
- ✅ FOUND: commit `9651e08` (test: Slot-A/B + hysteresis) in git log
- ✅ FOUND: commit `b534f59` (refactor: peakshare dict[a/b]) in git log
- ✅ FOUND: commit `36c7523` (test: PeakShare + 24h simulation) in git log
- ✅ Pattern checks all green (siehe oben).
- ✅ Verification command erfolgreich: alle vier neuen Methoden und PeakShareProvider importierbar (via pytest-Test).
