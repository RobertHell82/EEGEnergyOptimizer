# Phase 11: Dual-Window-Entladung — Research

**Researched:** 2026-05-04
**Domain:** Home Assistant Custom-Integration · Optimizer-Decision-Engine · Config-Migration · Frontend-Panel
**Confidence:** HIGH (alle relevanten Code-Anker, Versions- und Konventions-Aussagen am realen Code in diesem Repo verifiziert; Auto-Mode aktiv)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Refactor-Strategie**
- **D-01:** `_should_discharge` wird in 3 Methoden aufgespalten: `_evaluate_slot_a`, `_evaluate_slot_b`, `_evaluate_legacy_window` (Single-Window). Eine private `_check_common_guards` kapselt die slot-übergreifenden Checks (Tomorrow-PV-Surplus, SOC-Sensor-Verfügbarkeit, Discharge-Aborted-Watchdog für SolarEdge). Die orchestrierende `_should_discharge`-Methode wählt anhand `enable_dual_discharge` + `inverter_type` den richtigen Pfad und ruft Common-Guards einmal vorab auf.
- **D-02:** Slot-State bleibt als Felder im `EEGOptimizer`-Objekt (`_slot_a_activated_date`, `_slot_b_activated_date`) — konsistent mit `_morning_activated_date`, `_discharge_activated_date`. Reset-Logik im `_evaluate`-Pfad zentral; pro Slot eigener Reset-Trigger (Slot A nach Sunrise, Slot B nach Sunrise des Folgetags).

**Migration & Backwards-Compat**
- **D-03:** Config-Entry-Version-Bump von 12 auf 13. `_async_migrate_entry` ergänzt für jeden Bestands-Entry die neuen Keys mit Defaults: `enable_dual_discharge=True, enable_slot_a=True, enable_slot_b=True, discharge_a_start_time="20:00", discharge_b_start_time="03:00", discharge_b_end_cap="07:00", discharge_a_reserve_pct=15`. SolarEdge-Sonderfall: `enable_dual_discharge=False, enable_slot_a=True, enable_slot_b=False`.
  - **Korrektur (siehe Migration & Versioning unten):** Tatsächliche Ist-Version ist 14, daher Bump 14→15.
- **D-04:** Default-Wechsel ist intendiert. Bestands-Anlagen erhalten Dual-Window automatisch beim Update. CHANGELOG/Release-Notes müssen den Default-Wechsel prominent erklären.
- **D-05:** Single-Window-Pfad (Legacy) bleibt vollständig erhalten und funktional für Setups mit explizit gesetztem `enable_dual_discharge=False`. Code wird nicht entfernt; eigene Tests decken den Legacy-Pfad ab.

**Panel-Layout**
- **D-06:** Inline-Erweiterung der bestehenden Discharge-Sektion (`frontend/eeg-optimizer-panel.js`). Master-Toggle `enable_dual_discharge` oben. Bei aktiviert: zwei Sub-Bereiche "Slot A — Abend" und "Slot B — Morgen" mit eigenen Toggles + Zeit-/Reserve-Feldern. Bei deaktiviert: Legacy-Felder bleiben sichtbar.
- **D-07:** SolarEdge-Sonderfall: Master-Toggle deaktiviert/versteckt. Stattdessen Radio-Button "Slot A — Abend (Default) | Slot B — Morgen". Tooltip: "SolarEdge nutzt NVRAM für Entlade-Kommandos — nur ein Slot pro Tag möglich, um den Schreibzyklen-Verschleiß zu begrenzen".
- **D-08:** Status-Anzeige zeigt `discharge_active_slot: A | B | None` als visuelle Markierung am aktiven Fenster, plus separate Slot-A-/Slot-B-Status (deaktiviert / wartend / aktiv / abgeschlossen).

**Telemetry & Reasons**
- **D-09:** Neue Reasons additiv. Bestehende Keys bleiben in `ALL_REASONS`. Neue Keys für Dual-Pfad: `before_slot_a`, `slot_a_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_active`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`. Backend-Schema (D1) wird erweitert. Keine Breaking-Change in v1.1-Telemetrie-Verträgen.
- **D-10:** `Decision`-Dataclass erhält Feld `discharge_active_slot: Literal["A", "B"] | None` (default None). Sensor "Entscheidung" reicht den Wert in den Markdown-Status durch.

### Claude's Discretion
- Inverter-Race-Validation (b_start vs erwartetes Slot-A-Ende): Save-Validierung vs. Auto-Korrektur — Empfehlung in dieser RESEARCH.md
- Test-Layout: Erweiterung `tests/test_optimizer.py` vs. neue Datei `tests/test_dual_window.py` — Empfehlung unten
- PeakShare-Cache-Schema-Migration `_discharge_plan: tuple` → `dict[Literal["a","b"], tuple]` — Empfehlung unten
- Translations-Strings für Dual-Window-UI (de/en) — Plan-Detail

### Deferred Ideas (OUT OF SCOPE)
- "Slot M" — Mid-Night-Polling zwischen A-Ende und B-Start. Backlog v1.3+.
- Demand-weighted Energie-Aufteilung zwischen Slot A und B. Backlog v1.3+.
- Slot-individuelle PeakShare-Communities. Backlog v1.3+.
- Slot-spezifische Inverter-Rate-Limits über die SolarEdge-Sperre hinaus. Backlog.
- Auto-Berechnung von `discharge_a_reserve_pct` aus historischen Werten. Backlog.
- Spätere Phase: Single-Window als spezialisierten Slot-A-only-Modus reimplementieren und Legacy-Pfad entfernen. Erst nach 6+ Monaten Dual-Stabilität.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| Req 1 | Konfigurations-Schema für Dual-Window | Migration & Versioning + const.py-Erweiterung (siehe unten) |
| Req 2 | Slot A — Abend-Entladung mit Energie-Reserve | Refactor-Strategie + Slot-A-Logik (Pro-Slot-Hysterese) |
| Req 3 | Slot B — Morgen-Entladung mit adaptivem Ende vor Sonnenaufgang | Slot-Window-Mathematik (`compute_b_window_end`) — 4 Test-Cases |
| Req 4 | Pro-Slot-Hysterese | Pro-Slot-Hysterese-Sektion (Reset-Trigger, Reaktivierungsschwelle) |
| Req 5 | Mutual Exclusion zur Morgen-Einspeisung | Slot-Window-Mathematik (5-Minuten-Pause-Garantie) |
| Req 6 | SolarEdge-Sperre für Dual-Mode | SolarEdge-XOR-Sektion (Runtime + Save-Path + Panel) |
| Req 7 | Telemetry-Reasons pro Slot | Telemetry-Reasons-Sektion (8 neue Keys + REASON_LABELS_DE) |
| Req 8 | Independent Slot-Aktivierung (A-only / B-only / dual) | Refactor-Strategie + Test-Strategie (3 Szenario-Tests) |
| Req 9 | Inverter-Race-Schutz (≥5min) | Inverter-Race-Validation-Sektion (Empfehlung: Auto-Korrektur b_start) |
</phase_requirements>

## Summary

Phase 11 ist eine **Refactor-und-Erweiterungs-Phase** — sie touchiert eine kleine, sauber abgegrenzte Menge an Modulen (`optimizer.py`, `__init__.py`, `peakshare.py`, `const.py`, `frontend/eeg-optimizer-panel.js`, `translations/*.json`, `tests/`) und führt das bewährte Slot-A-Konzept des bestehenden Single-Window-Pfads (heute `_should_discharge`) als zwei unabhängig konfigurierbare Slots mit Pro-Slot-Hysterese fort. Die größten Risiken liegen NICHT im Algorithmus selbst (der ist klar in SPEC und CONTEXT), sondern in (a) korrekter Migrations-Versionierung (siehe kritische Korrektur unten), (b) lückenloser 5-Minuten-Pause zwischen Slot B und Morgen-Einspeisung in allen Sunrise-Bereichen, und (c) Schema-Migration des PeakShare-Cache von `tuple` auf slot-indiziertes Dict.

Der Code ist schon erfreulich modular für diesen Refactor: `Decision` ist eine erweiterbare Dataclass mit existierendem `discharge_*`-Feld-Block, `ALL_REASONS` ist genau für additive Erweiterungen gebaut, `find_discharge_window` in `peakshare.py` nimmt bereits `window_start`/`window_end` als Parameter (kann pro Slot mit unterschiedlichen Grenzen aufgerufen werden), `_should_discharge` liefert bereits `(bool, float, list[str], list[str], bool)` (Phase-8-Refactor) — das ist die fertige Schnittstelle für die drei neuen Methoden `_evaluate_slot_a` / `_evaluate_slot_b` / `_evaluate_legacy_window`. Reasons-Catalog folgt dem snake_case-Closed-Set-Pattern aus Phase 8.

**Primary recommendation:** Plan in 4 Plans aufteilen:
1. **11-01** — `const.py` + `_async_migrate_entry` v14→v15 + Helper `compute_b_window_end` + Reasons-Catalog-Erweiterung + Decision-Feld `discharge_active_slot`. **Reine Datenstruktur-Erweiterung, keine Verhaltensänderung.** Tests parallel.
2. **11-02** — `_should_discharge`-Refactor mit den 3 neuen Methoden + `_check_common_guards` + Pro-Slot-Hysterese-Felder + Slot-State-Reset im `_evaluate`. PeakShare-Cache-Schema-Migration. **Verhaltensänderung Default Dual=ON.** Tests umfassend.
3. **11-03** — Panel-Erweiterung (Wizard + Settings-Tab "Abend-Entladung"), SolarEdge-XOR-Radio, Save-Path-Validierung mit b_start-Auto-Bump. Translations (de/en).
4. **11-04** — Inverter-Race-Validation Hardening + WebSocket-Save-Path-Tests + Markdown-Renderer-Update + Activity-Log-Heartbeat-Texte. **Auch Backend-Schema-Erweiterung als PR-Hinweis** (Backend-Repo separat).

11-01 und 11-04 können parallel zu 11-02 und 11-03 gestartet werden, sobald 11-01 gemerged ist (Reasons-Keys + Migration sind Grundlage). 11-02 → 11-03 sequenziell (UI braucht funktionierenden Decision-Pfad). 11-04 ist der UAT-Gate-Plan — nach Merge wird die 7-Tage-User-Beobachtung ausgelöst.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dual-Window Decision-Engine (Slot A/B Auswahl, Reserve-Logik, Hysterese) | Backend (`optimizer.py`) | — | Reine Server-Side-Logik, läuft im 30s-Cycle ohne Browser |
| Adaptives B-Ende vor Sunrise (`compute_b_window_end`) | Backend (`optimizer.py`) | — | Berechnung gehört zur Decision-Engine — neben `compute_hard_cutoff` (bestehender Code-Anker `optimizer.py:175`) |
| Config-Entry-Migration v14→v15 | Backend (`__init__.py:async_migrate_entry`) | — | Persistente Storage-Mutation, läuft beim HA-Boot |
| Pro-Slot-Hysterese-State (`_slot_a_activated_date`, `_slot_b_activated_date`) | Backend (in-memory `EEGOptimizer`) | — | Genau wie bestehendes `_morning_activated_date` — flüchtiger Tagesstate, kein Storage |
| PeakShare-Cache-Schema-Migration | Backend (`peakshare.py`) | — | Cache lebt in `homeassistant.helpers.storage.Store` — Backend-only |
| Telemetry-Reasons-Erweiterung (Katalog + Labels) | Backend (`optimizer.py:ALL_REASONS`) | Frontend (Status-Card-Übersetzung via `REASON_LABELS_DE`) | Snake_case-Keys ans Telemetrie-Backend; deutsche Labels ans Panel |
| Master-Toggle + Slot-A/B-Sub-Bereiche (UI) | Frontend (`frontend/eeg-optimizer-panel.js`) | Backend (Save via `eeg_optimizer/save_config`) | Plain HTMLElement + Shadow DOM, render-only — Persistierung im WS-Save-Handler |
| SolarEdge-XOR-Radio | Frontend (Panel) | Backend (Runtime-Erzwingung in `__init__.py` UND Save-Path in `websocket_api.py:ws_save_config`) | Defense-in-depth: UI verhindert Falsch-Klick, Backend lehnt fehlerhaftes WS-Payload ab und korrigiert beim Boot |
| Inverter-Race-Validation (b_start ≥ a_end + 5min) | Backend (`websocket_api.py:ws_save_config`) | Frontend (Inline-Hint vor Klick) | Server-side ist autoritativ — Frontend kann optional warnen, aber niemals validieren-only |
| `discharge_active_slot`-Decision-Feld → Markdown | Backend (`optimizer.py:_build_markdown`) | Frontend (Sensor "Entscheidung" rendert Markdown 1:1) | Markdown-Renderer ist im Backend; Sensor-Attribut wird in HA-Card direkt gerendert |
| Activity-Log-Einträge mit Slot-Kontext | Backend (`__init__.py` Activity-Log-Pfad) | — | Bestehender Pattern: Heartbeat-Strings deutsch, Reasons separat (D-38 aus Phase 8) |

## Standard Stack

### Core (alle bereits im Projekt verfügbar — KEINE neuen Abhängigkeiten)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `homeassistant` (Framework) | bestehend (manifest min. ≥ 2025.x) | ConfigEntry, Store, async_track_time_interval, dt_util | Projekt ist HA-Integration — kein anderer Weg |
| `voluptuous` | bestehend | Schema-Validierung im WS-Save-Path | Bereits etabliert in `websocket_api.py:ws_save_config` und `config_flow.py` |
| `dataclasses` (stdlib) | py3.11+ | `Decision` und `Snapshot` erweitern | Bestehendes Pattern in `optimizer.py:211, 247` |
| `pytest` + `pytest-asyncio` | bestehend (`pyproject.toml`) | Tests | `asyncio_mode=auto` schon konfiguriert |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `homeassistant.helpers.storage.Store` | bestehend | PeakShare-Cache + Telemetry | Bereits in `peakshare.py:163` und `__init__.py` aktiv — gleiches Pattern für Schema-Migration |
| `homeassistant.util.dt` | bestehend | `_now()`, `_as_local()` für Sunrise-Math | `optimizer.py:147-153` — KEIN naive datetime, alles tz-aware |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline-Erweiterung Discharge-Sektion (D-06) | Eigener Wizard-Step "Slot-Konfiguration" | Würde Wizard auf 7 Steps verlängern → User-friction; Inline-Lösung passt zu bestehendem Toggle-Pattern in Steps 4 + Settings-Tab |
| `dict[Literal["a","b"], tuple]` für PeakShare-Cache | Zwei separate Felder `_discharge_plan_a`, `_discharge_plan_b` | Dict ist sauberer (skaliert auf Slot M später), separate Felder duplizieren `_discharge_plan_date`-Logik |
| Hartes Save-Reject bei b_start-Konflikt | Auto-Korrektur (b_start = computed_a_end_min + 5min) | Auto-Korrektur ist konsistent mit existierendem Pattern (SolarEdge clamp 5kW; PeakShare-Window-Clamp); Hard-Reject würde User mit unklarer Fehlermeldung im Panel hängen lassen — siehe Inverter-Race-Sektion |

**Installation:** keine neuen Pakete — Phase 11 nutzt ausschließlich bestehende Imports.

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│ HA-Boot                                                          │
│  ├── async_setup_entry → async_migrate_entry (v14 → v15)         │
│  │     └── default keys: enable_dual_discharge, enable_slot_a/b, │
│  │         discharge_a_start, discharge_b_start, b_end_cap,      │
│  │         discharge_a_reserve_pct                               │
│  │         (SolarEdge: dual=False, slot_a=True, slot_b=False)    │
│  └── EEGOptimizer(_init_) liest neue Keys via config.get(..)     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 30-Sekunden-Cycle: async_run_cycle(mode)                         │
│                                                                  │
│  _gather_snapshot()  ──►  Snapshot                               │
│                                                                  │
│  _evaluate(snap, mode):                                          │
│    1. SOC-None-Guard (bestehend)                                 │
│    2. Hysterese-Reset für slot_a/slot_b/morning (zentral)        │
│    3. _should_block_charging(snap)         ─► (bool, reasons)    │
│    4. _should_discharge(snap)              ─► dispatcher:        │
│         ├── enable_dual_discharge=False → _evaluate_legacy_window│
│         ├── inverter=solaredge_storedge → _evaluate_legacy       │
│         │   (effektiv slot_a-only oder slot_b-only via XOR)      │
│         └── default → _check_common_guards()                     │
│             + _evaluate_slot_a(snap)  und/oder                   │
│               _evaluate_slot_b(snap)  → erstes Pass gewinnt      │
│    5. State-Resolution: block > discharge > Normal               │
│       Bei discharge: discharge_active_slot = "A"|"B"             │
│    6. Activity-Log + Telemetry (reasons, blocked_by, snapshot)   │
│    7. _execute(decision) (nur Mode=Ein)                          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ Frontend Panel (eeg-optimizer-panel.js)                          │
│   Wizard Step "Abend-Entladung":                                 │
│     ├── enable_dual_discharge (Master, hidden bei SolarEdge)     │
│     ├── Slot A Sub-Bereich (Toggle + a_start + reserve_pct)      │
│     ├── Slot B Sub-Bereich (Toggle + b_start + b_end_cap)        │
│     └── SolarEdge: Radio-Button "Slot A | Slot B" (XOR)          │
│   Settings-Tab "Abend-Entladung": parallele Inline-UI            │
│   Decision-Card: Marker für discharge_active_slot                │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼ ws_save_config
┌──────────────────────────────────────────────────────────────────┐
│ websocket_api.ws_save_config — Server-Side-Validation           │
│   1. SolarEdge-XOR: enable_dual_discharge → False (Auto-Korrektur)│
│   2. b_start ≥ a_min_required_end + 5min (Auto-Korrektur, log)   │
│   3. Bestehende Validations (Fronius-Modbus, SolarEdge 5kW) bleiben│
└──────────────────────────────────────────────────────────────────┘
```

### Recommended Code Structure (Datei-Footprint)

```
custom_components/eeg_energy_optimizer/
├── const.py                       # +7 CONF_* + 5 DEFAULT_* Konstanten
├── __init__.py                    # async_migrate_entry: +1 Block v14→v15
├── optimizer.py                   # Refactor _should_discharge in 3 Methoden
│                                  # +compute_b_window_end()
│                                  # +8 REASON_* Konstanten in ALL_REASONS
│                                  # +REASON_LABELS_DE-Einträge (deutsch)
│                                  # +Decision.discharge_active_slot
│                                  # +EEGOptimizer._slot_a_activated_date
│                                  # +EEGOptimizer._slot_b_activated_date
├── peakshare.py                   # _discharge_plan: dict[Literal["a","b"], tuple]
│                                  # get_discharge_plan(slot=...) Signatur-Erw.
│                                  # async_load: tuple→dict-Format-Migration
├── frontend/eeg-optimizer-panel.js # Wizard Step 4 + Settings-Tab "evening"
│                                  # Master-Toggle + Slot-A/B Sub-Bereiche
│                                  # SolarEdge-XOR-Radio
│                                  # Decision-Card: Slot-Marker
├── translations/de.json           # Optional: nur falls neue strings.json-Keys
├── translations/en.json           # Optional: dito
├── websocket_api.py               # ws_save_config: +Inverter-Race-Validation
└── tests/
    ├── test_optimizer.py          # Erweitert (Slot-A-/Slot-B-Sektionen)
    └── test_dual_window.py        # NEU — siehe Test-Strategie unten
```

### Pattern 1: Slot-Decision-Funktionen mit gemeinsamen Guards

**What:** `_check_common_guards(snap)` liefert `(common_blocked_by: list[str], min_soc: float)` als Vorab-Check für Tomorrow-PV-Surplus, SOC-Sensor, SolarEdge-Discharge-Aborted. Slot-A/B-Methoden gehen erst weiter, wenn `common_blocked_by == []`.

**When to use:** Im neuen `_should_discharge`-Dispatcher, vor dem Aufruf der Slot-Methoden.

**Example (Skelett, nicht endgültig):**
```python
# optimizer.py — neue Methoden, ergänzen das bestehende Modul
def _check_common_guards(self, snap: Snapshot) -> tuple[list[str], float]:
    if not self._enable_night_discharge:
        return ([REASON_NIGHT_DISCHARGE_DISABLED], float(self._min_soc))
    min_soc = self._calc_min_soc(snap)
    if min_soc >= 100.0:
        return ([REASON_OVERNIGHT_DEMAND_TOO_HIGH], min_soc)
    today_str = snap.now.strftime("%Y-%m-%d")
    if self._is_solaredge and self._discharge_aborted_date == today_str:
        return ([REASON_DISCHARGE_ABORTED_TODAY], min_soc)
    # Tomorrow-PV-Surplus: gleiche Berechnung wie heute in _should_discharge:1031-1044
    cb = self._safety_buffer_pct
    cwb = snap.consumption_tomorrow_daylight_kwh * (1 + cb / 100)
    bcn = (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
    if (snap.pv_tomorrow_kwh or 0.0) < (cwb + bcn):
        return ([REASON_TOMORROW_PV_INSUFFICIENT], min_soc)
    return ([], min_soc)

def _evaluate_slot_a(self, snap, min_soc) -> tuple[bool, list[str], list[str], bool]:
    # Slot-A-spezifische SOC-Schwelle: min_soc + reserve_pct (nur wenn Slot B aktiv)
    reserve_active = self._enable_slot_b
    a_min_soc = min_soc + (self._discharge_a_reserve_pct if reserve_active else 0)
    # Hysterese mit _slot_a_activated_date (analog zu _discharge_activated_date)
    is_reactivation = (
        self._slot_a_activated_date is not None
        and self._last_active_slot != "A"
    )
    effective_min_soc = a_min_soc + (5 if is_reactivation else 0)
    # Window-Check, SOC-Check, return passing/blocked Keys
    ...
```

### Pattern 2: Adaptives Slot-B-Ende — `compute_b_window_end`

**What:** Neue Funktion neben `compute_hard_cutoff` (siehe `optimizer.py:175-208`). Liefert das effektive B-Fenster-Ende als striktes Minimum aus drei Quellen.

**When to use:** Im `_evaluate_slot_b`, vor SOC- und Window-Check.

**Example (target):**
```python
def compute_b_window_end(
    now: datetime,
    sunrise: datetime | None,
    b_end_cap: str,                     # "07:00"
    morning_offset_h: float,            # CONF_MORNING_START_OFFSET (Default 0)
) -> datetime | None:
    """Berechne das effektive Slot-B-Ende.

    end = min(
        b_end_cap_anchored_at_sunrise_day,
        sunrise - morning_offset_h,
        sunrise - 5min,
    )

    Garantiert ≥5min Pause vor Beginn der Morgen-Einspeisung
    (sunrise − morning_offset_h) und ≥5min vor Sunrise selbst.

    Wenn sunrise unbekannt: None (Slot B kann ohne Sunrise nicht laufen).
    """
    if sunrise is None:
        return None
    cap_h, cap_m = (int(p) for p in b_end_cap.split(":"))
    cap_at_sunrise_day = sunrise.replace(
        hour=cap_h, minute=cap_m, second=0, microsecond=0
    )
    pre_morning_einspeisung = sunrise - timedelta(
        hours=morning_offset_h, minutes=5
    )
    pre_sunrise = sunrise - timedelta(minutes=5)
    return min(cap_at_sunrise_day, pre_morning_einspeisung, pre_sunrise)
```

### Pattern 3: PeakShare-Cache als slot-indiziertes Dict

**What:** `_discharge_plan` wird von `tuple[datetime, datetime] | None` zu `dict[Literal["a","b"], tuple[datetime, datetime] | None]`. `_discharge_plan_date` bleibt einzeln (lock pro Tag, gemeinsam für beide Slots).

**When to use:** In `peakshare.py` — `get_discharge_plan` bekommt `slot: Literal["a","b"]`-Parameter; `find_discharge_window` wird pro Slot mit `window_start`/`window_end` aus der jeweiligen Slot-Konfiguration aufgerufen.

**Migration in `async_load`:** Wenn beim Laden `_discharge_plan` als `tuple` (Legacy-Format) erkannt wird → in Dict mit Key `"a"` einsortieren oder verwerfen (Cache-Invalidation ist günstig — er wird beim nächsten 30s-Cycle neu berechnet).

### Anti-Patterns to Avoid

- **Slot-Felder in Snapshot ablegen:** Snapshot ist immutable Input-Struktur. Slot-Konfiguration und Slot-State gehören in den `EEGOptimizer`-Self.
- **Hard-Reject bei Inverter-Race in WS-Save:** Würde Panel mit `invalid_config`-Error stehen lassen ohne klare User-Aktion. Statt Reject: Auto-Korrektur mit Log + sichtbarem Toast im Panel (siehe Inverter-Race-Sektion).
- **Doppelte Migration für SolarEdge:** Migrate-Step setzt SolarEdge-Defaults ein, aber Save-Path UND `EEGOptimizer.__init__` müssen die Erzwingung wiederholen — Defense-in-depth wegen Inverter-Type-Wechsel im laufenden Setup.
- **Block-Pfad und Discharge-Pfad gleichzeitig aktivieren:** Bestehender `_evaluate` hat `if block: ... elif should_discharge: ...` (Zeile 1102-1107). Reihenfolge bleibt (D-09 aus Phase 3): Morgen-Einspeisung gewinnt bei Konflikt. Slot B endet vor Beginn — siehe `compute_b_window_end`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sliding-Window-Suche pro Slot | Eigene Schleife | Existierendes `peakshare.find_discharge_window()` zweimal aufrufen mit Slot-A/B-Window-Grenzen | Algorithmus inkl. Contiguity-Check, Jitter-Anwendung, Edge-Cases bereits validiert |
| Tz-aware Sunrise-Mathematik | Naive datetime + manuelle `replace(hour=...)` | `homeassistant.util.dt.now()` + `as_local()` und Anchor-Pattern aus `compute_hard_cutoff` | DST-Übergänge fressen Naive-Code |
| Config-Migration | Custom-Storage-Update | `_async_migrate_entry`-Pattern aus `__init__.py:748-846` | Bestehender 11-Schritt-Migrations-Pfad, Convention etabliert |
| Snake_case-Reasons-Closed-Set | String-Literals an einzelnen Code-Stellen | `ALL_REASONS`-Frozenset in `optimizer.py:95-117` erweitern | Phase 8 hat das Pattern für Telemetrie deterministisch fixiert |
| Test-Mock für Snapshot/Optimizer | Eigene Fixtures | `_make_snapshot()` / `_make_optimizer()` in `tests/test_optimizer.py:81-106` | Bestehende Helpers decken alle Felder ab |
| Frontend-Toggle-Card | Eigenes HTML | Wiederverwendung des `feature-toggle`/`feature-card`-Patterns aus `eeg-optimizer-panel.js:3034+` | Konsistente CSS-Klassen, vorhandenes State-Handling |

**Key insight:** Phase 11 ist primär Refactoring + Erweiterung. Jeder Punkt, an dem Hand-Rolling reizt, hat schon einen etablierten Pattern im Repo — die Phase-8-Vorarbeit hat den Weg geebnet.

## Migration & Versioning

### Kritische Korrektur (vom Orchestrator gemeldet, in Code verifiziert)

> **SPEC.md (Z. 24, 94, 100) und CONTEXT.md (D-03, Z. 51, 91) referenzieren `Version 12 → 13`. Das ist OUTDATED.**

**Verifizierter Ist-Zustand (gegrep am 2026-05-04):**
- `custom_components/eeg_energy_optimizer/config_flow.py:24` deklariert `VERSION = 14` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/__init__.py:820` migriert Bestands-Entries auf `version=13` (Telemetrie CONF_TELEMETRY_ENABLED) `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/__init__.py:831` migriert Bestands-Entries auf `version=14` (`discharge_start_time = "01:00"` Hard-Migration) `[VERIFIED: file read]`

**Aktion für Phase 11:** Migration ist **v14 → v15**, NICHT v12 → v13. Migrationsblock im Plan sieht so aus:

```python
# __init__.py – ergänzen NACH dem bestehenden v14-Block (Z. 831-844)
if entry.version < 15:
    new_data = {**entry.data}
    inverter_type = new_data.get(CONF_INVERTER_TYPE, "")
    is_solaredge = inverter_type == INVERTER_TYPE_SOLAREDGE

    if is_solaredge:
        # XOR-Konfiguration: nur ein Slot pro Tag (NVRAM-Verschleiß)
        new_data.setdefault("enable_dual_discharge", False)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", False)
    else:
        # Default-Wechsel: Bestands-Anlagen erhalten Dual-Window automatisch
        new_data.setdefault("enable_dual_discharge", True)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", True)

    new_data.setdefault("discharge_a_start_time", "20:00")
    new_data.setdefault("discharge_b_start_time", "03:00")
    new_data.setdefault("discharge_b_end_cap", "07:00")
    new_data.setdefault("discharge_a_reserve_pct", 15)
    hass.config_entries.async_update_entry(entry, data=new_data, version=15)
```

**Außerdem MUSS `config_flow.py:24` von `VERSION = 14` auf `VERSION = 15` gehoben werden** — bestehender HA-Convention nach.

### Neue Konstanten in `const.py` (additiv)

```python
# Phase 11: Dual-Window-Entladung
CONF_ENABLE_DUAL_DISCHARGE = "enable_dual_discharge"
CONF_ENABLE_SLOT_A = "enable_slot_a"
CONF_ENABLE_SLOT_B = "enable_slot_b"
CONF_DISCHARGE_A_START_TIME = "discharge_a_start_time"
CONF_DISCHARGE_B_START_TIME = "discharge_b_start_time"
CONF_DISCHARGE_B_END_CAP = "discharge_b_end_cap"
CONF_DISCHARGE_A_RESERVE_PCT = "discharge_a_reserve_pct"

DEFAULT_ENABLE_DUAL_DISCHARGE_NON_SOLAREDGE = True
DEFAULT_ENABLE_DUAL_DISCHARGE_SOLAREDGE = False
DEFAULT_DISCHARGE_A_START_TIME = "20:00"
DEFAULT_DISCHARGE_B_START_TIME = "03:00"
DEFAULT_DISCHARGE_B_END_CAP = "07:00"
DEFAULT_DISCHARGE_A_RESERVE_PCT = 15
```

`CONF_DISCHARGE_START_TIME` und `DEFAULT_DISCHARGE_START_TIME = "01:00"` (in `const.py:89, 102`) bleiben erhalten — sie sind die Legacy-Konfiguration und wirken weiter, wenn `enable_dual_discharge=False`.

**`TELEMETRY_SETTINGS_KEYS` in `const.py:166-178`:** Erweitern um die neuen Slot-Keys, damit das Backend Settings-Drift erkennt:
```python
TELEMETRY_SETTINGS_KEYS = (
    ... bestehende Keys ...,
    "enable_dual_discharge",
    "enable_slot_a", "enable_slot_b",
    "discharge_a_start_time", "discharge_b_start_time",
    "discharge_b_end_cap", "discharge_a_reserve_pct",
)
```

## Refactor-Strategie

### Schnittstelle bleibt: `_should_discharge` → `(should, min_soc, reasons, blocked_by, hysteresis_active)`

Bestehende Signatur in `optimizer.py:905-907` ist genau das, was der refactorete Dispatcher zurückgeben soll — `_evaluate` (Z. 1097) ruft die Methode bereits in dieser Form auf. **Die Schnittstelle muss NICHT geändert werden, nur die Inneneinrichtung.**

Zusätzlich neu: `Decision.discharge_active_slot: Literal["A", "B"] | None` (default None) — wird nur in `_evaluate` gesetzt, nachdem feststeht welcher Slot aktiv ist.

### Dispatcher-Skelett

```python
# optimizer.py — neue Implementierung _should_discharge
def _should_discharge(self, snap: Snapshot) -> tuple[bool, float, list[str], list[str], bool]:
    # Common Guards (gemeinsam für Legacy + Slot-A + Slot-B)
    common_blocked, min_soc = self._check_common_guards(snap)
    if common_blocked:
        return (False, min_soc, [], common_blocked, False)

    # Pfadwahl
    use_legacy = (
        not self._enable_dual_discharge
        or self._is_solaredge  # SolarEdge bleibt immer Single-Slot
    )
    if use_legacy:
        # Legacy-Pfad ist 1:1 der heutige _should_discharge-Body
        # (PeakShare- ODER Fixed-Time-Logik mit _discharge_activated_date)
        return self._evaluate_legacy_window(snap, min_soc)

    # Dual-Mode: Slot A bevorzugt (zeitlich früher), Fallback Slot B
    # Der tatsächlich aktive Slot wird in _evaluate gesetzt.
    if self._enable_slot_a:
        passed, reasons, blocked, hyst = self._evaluate_slot_a(snap, min_soc)
        if passed:
            return (True, min_soc, reasons + [REASON_SLOT_A_ACTIVE], [], hyst)
    if self._enable_slot_b:
        passed, reasons, blocked, hyst = self._evaluate_slot_b(snap, min_soc)
        if passed:
            return (True, min_soc, reasons + [REASON_SLOT_B_ACTIVE], [], hyst)

    # Beide Slots haben blockiert oder sind disabled — kombinierte Liste:
    combined_blocked = []
    if self._enable_slot_a:
        combined_blocked.extend(blocked_a)
    if self._enable_slot_b:
        combined_blocked.extend(blocked_b)
    return (False, min_soc, [], combined_blocked, False)
```

`_evaluate` (Z. 1057) braucht eine kleine Erweiterung: nach `should_discharge=True` muss er anhand der `reasons`-Liste entscheiden, welcher Slot aktiv ist (`"slot_a_active"` vs. `"slot_b_active"`), und das Datumsfeld setzen + `decision.discharge_active_slot` füllen.

### Legacy-Pfad bleibt funktional

Der heutige Body von `_should_discharge` (Z. 905-1055) wird zu `_evaluate_legacy_window` umbenannt — keine inhaltliche Änderung. Das ist die `enable_dual_discharge=False`-Garantie aus D-05.

## Slot-Window-Mathematik

### `compute_b_window_end`-Test-Cases (aus SPEC Req 3 + Req 5)

Sunrise-Werte aus realistischen Energy-Community-Standorten Österreich/Deutschland (verifiziert über typischen Sunrise-Range; HA `sun.sun`-Werte sind tz-aware lokale Zeit).

| Case | sunrise | b_end_cap | morning_offset_h | Erwartetes b_end | Begründung |
|------|---------|-----------|------------------|------------------|-----------|
| **Sommer SA 04:52** | `2026-06-21 04:52` | `"07:00"` | `0` | `04:47` | sunrise−5min ist striktester Schnitt; cap 07:00 weit später |
| **Winter SA 07:30** | `2026-12-21 07:30` | `"07:00"` | `0` | `07:00` | cap 07:00 ist striktester Schnitt; sunrise−5min wäre 07:25 |
| **Übergang SA 06:00** | `2026-04-15 06:00` | `"07:00"` | `0` | `05:55` | sunrise−5min ist striktester Schnitt |
| **Tiefer Winter SA 08:30** | `2026-01-15 08:30` | `"07:00"` | `0` | `07:00` | cap 07:00 ist striktester Schnitt; sunrise−5min wäre 08:25 |

**Mit `morning_offset_h=1` (Test für Req 5):**

| Case | sunrise | b_end_cap | morning_offset_h | Erwartetes b_end |
|------|---------|-----------|------------------|------------------|
| Winter SA 07:30, Morgen-Einspeisung 06:30 startet | `2026-12-21 07:30` | `"07:00"` | `1` | `06:25` |

→ Pause-Lücke zur Morgen-Einspeisung (würde 06:30 starten) = 5min ✓

### 5-Minuten-Pause-Garantie

`compute_b_window_end` zieht IMMER `timedelta(minutes=5)` ab — sowohl von `(sunrise − morning_offset_h)` als auch von `sunrise` direkt. Das schließt zwei Konflikt-Fälle aus:

1. **Slot B vs Morgen-Einspeisung:** Morgen-Einspeisung-Start ist `sunrise − morning_offset_h` (siehe `_should_block_charging` `optimizer.py:849`). Slot B endet `5min` davor → keine parallele Aktivität.
2. **Slot B vs Inverter-Reset bei Sunrise:** Bei `morning_offset_h = 0` ist Morgen-Einspeisungs-Start = sunrise, und Slot B endet `5min` vor sunrise. Selbst wenn Morgen-Einspeisung dann nicht aktiviert wird (weil PV-Forecast schlecht), gibt es einen sauberen Stop des Inverters vor SA.

### Edge-Cases (in Tests aufnehmen)

- `sunrise` is None: `compute_b_window_end` liefert None — Slot B inaktiv für diese Sitzung.
- `b_end_cap = "23:59"`: Cap effektiv weit weg → sunrise-getriebenes Ende greift.
- `morning_offset_h = 2.5` (User-Konfiguration aus dem Wizard, max=3): pre_morning = sunrise − 2h35min → cap ≤ pre_morning bei Winter-SA-Sonne; sunrise−5min weit später → cap gewinnt.
- `b_start ≥ b_end_effective`: Slot B nicht aktiviert (z.B. Sommer-SA 04:52 + b_start=05:00 → b_end=04:47, b_start nach b_end → kein Fenster). Im `_evaluate_slot_b` als `REASON_SLOT_B_WINDOW_EXPIRED` (oder neuer Key `slot_b_pre_sunrise_cutoff`) markieren.

## Pro-Slot-Hysterese

### Felder

```python
# EEGOptimizer.__init__ — analog zu Z. 366-371
self._slot_a_activated_date: str | None = None  # ISO-Datum "YYYY-MM-DD"
self._slot_b_activated_date: str | None = None
# _last_eval_zustand: str = STATE_NORMAL — bleibt
# Zusätzlich: tracking welcher Slot zuletzt aktiv war für is_reactivation-Check
self._last_active_slot: str | None = None  # "A" | "B" | None
```

### Reset-Trigger (im `_evaluate`, vor den Slot-Methoden)

Reihenfolge analog zu `optimizer.py:1081-1093`:

```python
today_str = snap.now.strftime("%Y-%m-%d")

# Morning bleibt unverändert (kein Mitternachtsübergang)
if self._morning_activated_date is not None and self._morning_activated_date < today_str:
    self._morning_activated_date = None

# Slot A: Reset nach today's Sunrise (Slot A endet vor Slot B oder vor Sunrise; nicht über zwei Sunrises)
if (self._slot_a_activated_date is not None
        and self._slot_a_activated_date < today_str
        and snap.sunrise_today is not None
        and snap.now >= snap.sunrise_today):
    self._slot_a_activated_date = None

# Slot B: Slot B läuft 03:00 → vor Sunrise. Aktivierungsdatum ist heute oder gestern.
# Reset nach today's Sunrise — analog zu Slot A.
if (self._slot_b_activated_date is not None
        and self._slot_b_activated_date < today_str
        and snap.sunrise_today is not None
        and snap.now >= snap.sunrise_today):
    self._slot_b_activated_date = None

# Bestehender _discharge_activated_date für Legacy-Pfad bleibt unverändert
```

### Reaktivierungs-Schwellen

Beim Pro-Slot-Reaktivierungs-Check gilt Phase-3-Pattern (siehe `optimizer.py:1017-1024`):

- **Slot A:** `effective_min_soc = a_min_soc + 5` wenn `_slot_a_activated_date is not None and _last_active_slot != "A"`. Reason `slot_a_active` + `hysteresis_strict` wird mit gesendet.
- **Slot B:** `effective_min_soc = min_soc + 5` wenn `_slot_b_activated_date is not None and _last_active_slot != "B"`. Reason `slot_b_active` + `hysteresis_strict` wird gesendet.

**Wichtig: Slot-Hysterese-Schwellen sind unabhängig.** Wenn Slot A heute aktiviert wurde und endete (Reserve erreicht), wirkt der +5%-Aufschlag NUR auf Slot A. Slot B startet später am Tag mit normalem `min_soc_dyn`-Threshold (ohne Aufschlag), sofern Slot B selbst noch nicht aktiv war.

### Coexistenz mit `_morning_activated_date`

`_morning_activated_date` ist unabhängig — Morgen-Einspeisung ist ein separater Zustand, nicht Slot des Discharge-Pfads. Bestehender Code in `optimizer.py:1113-1118` setzt das Datum bei Zustands-Wechsel auf `STATE_MORGEN_EINSPEISUNG` und bleibt unangetastet. Slot-A-/Slot-B-Aktivierungsdaten werden in einem analogen neuen Block gesetzt:

```python
# Im _evaluate — nach decision-State-Resolution:
if zustand == STATE_ABEND_ENTLADUNG:
    if decision.discharge_active_slot == "A" and self._slot_a_activated_date is None:
        self._slot_a_activated_date = today_str
        self._last_active_slot = "A"
    elif decision.discharge_active_slot == "B" and self._slot_b_activated_date is None:
        self._slot_b_activated_date = today_str
        self._last_active_slot = "B"
```

## PeakShare-Cache-Schema-Migration

### Schema-Änderung

```python
# peakshare.py — Vor:
self._discharge_plan: tuple[datetime, datetime] | None = None
self._discharge_plan_date: str | None = None

# Nach:
self._discharge_plan: dict[str, tuple[datetime, datetime] | None] = {"a": None, "b": None}
self._discharge_plan_date: str | None = None  # Lock pro Tag, gemeinsam für a/b
```

### Migration in `async_load`

```python
# peakshare.py — async_load (heute Z. 174-195)
async def async_load(self) -> None:
    if self._store is None:
        return
    try:
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict):
            self._cache = stored.get("data")
            fetched_at = stored.get("fetched_at")
            if fetched_at:
                self._cache_time = datetime.fromisoformat(fetched_at)
            self._jitter_today = stored.get("jitter_value")
            self._jitter_date = stored.get("jitter_date")
            # Phase 11: Cache-Schema-Migration
            # Alte tuple-Form wird verworfen — der nächste Cycle berechnet neu
            self._discharge_plan = {"a": None, "b": None}
            self._discharge_plan_date = None  # Force-Recompute
    except Exception:
        _LOGGER.debug("PeakShare: no persisted cache found")
```

**Begründung:** Der `_discharge_plan` wird beim Boot ohnehin im 30s-Cycle neu berechnet, sobald frische Daten vorliegen. Eine "saubere" Migration alter Tuple-Werte würde mehr Code für weniger Nutzen bedeuten.

### Slot-spezifischer Aufruf von `find_discharge_window`

`get_discharge_plan` bekommt zwei zusätzliche Parameter:

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
    slot: str = "a",          # Phase 11: "a" oder "b"
    window_start: datetime | None = None,  # Optional Override (statt sunset_time)
    window_end: datetime | None = None,    # Optional Override (statt hard_cutoff)
) -> tuple[datetime, datetime] | None:
    today_str = now.strftime("%Y-%m-%d")
    # Cache-Lookup pro Slot
    if self._discharge_plan_date == today_str:
        return self._discharge_plan.get(slot)
    ...
    # Window-Resolution
    if window_start is None:
        window_start = sunset_time
        if discharge_start_lower_bound is not None:
            window_start = max(window_start, discharge_start_lower_bound)
    if window_end is None:
        window_end = compute_hard_cutoff(next_day, next_sunrise)
    ...
    plan = find_discharge_window(...)
    self._discharge_plan[slot] = plan
    self._discharge_plan_date = today_str
    return plan
```

### Slot-spezifisches `available_kwh`

Im Optimizer wird das Energie-Budget pro Slot getrennt gerechnet:

- **Slot A `available_kwh`:** `(snap.battery_soc − a_min_soc) / 100 * battery_capacity_kwh` mit `a_min_soc = min_soc + reserve_pct` (sofern Slot B aktiv)
- **Slot B `available_kwh`:** `(slot_a_end_soc_estimate − min_soc) / 100 * battery_capacity_kwh` ODER (einfacher und wahrscheinlich ausreichend) `(reserve_pct + 0) / 100 * battery_capacity_kwh` als statische Schätzung dessen, was Slot A reserviert hat

**Empfehlung:** **Statische Slot-B-Schätzung** für Phase 11 (`available_kwh_b ≈ reserve_pct / 100 * capacity`). Demand-weighted Aufteilung ist explizit Backlog v1.3+ (CONTEXT.md `<deferred>`). Falls die statische Schätzung zu wenig ergibt → `find_discharge_window` liefert `None` → Slot B wird in dieser Sitzung übersprungen, kein Schaden.

### Fallback wenn PeakShare-Daten unvollständig

SPEC.md Constraint Z. 95: *"Die `community_data["hours"]`-Liste muss die Slot-A- und Slot-B-Zeiträume abdecken; falls nicht, fällt der betroffene Slot auf `static_reserve`-Modus zurück (kein Slot-Ausfall)."*

`find_discharge_window` liefert bereits heute `None` wenn `eligible < required_hours` (Z. 92-93). Der Slot fällt dann auf den **Fixed-Time-Pfad** zurück — analog zum heutigen Single-Window-Verhalten. Das ist bereits in der heutigen Logik abgebildet (`peakshare_plan is not None` → PeakShare-Pfad, sonst Fixed-Time-Pfad in `optimizer.py:992`). Slot-A/B-Methoden replizieren dieses Pattern.

## SolarEdge-XOR

### Drei Layer Defense-in-depth

**1. Migration (im `_async_migrate_entry`):** Bei v14→v15 für SolarEdge-Bestands-Entries `enable_dual_discharge=False, enable_slot_a=True, enable_slot_b=False` setzen. Code oben in **Migration & Versioning** dokumentiert.

**2. Save-Path (`websocket_api.py:ws_save_config`):** Erweiterung des bestehenden SolarEdge-Blocks (Z. 410-414):

```python
# websocket_api.py:ws_save_config — erweitern nach Z. 414
if new_data.get("inverter_type") == INVERTER_TYPE_SOLAREDGE:
    discharge_kw = new_data.get("discharge_power_kw")
    if discharge_kw is not None and float(discharge_kw) < 5.0:
        new_data["discharge_power_kw"] = 5.0
    # Phase 11: SolarEdge bleibt Single-Slot
    if new_data.get("enable_dual_discharge"):
        _LOGGER.warning(
            "SolarEdge: enable_dual_discharge=True nicht erlaubt — auf False gesetzt"
        )
        new_data["enable_dual_discharge"] = False
    # XOR: genau ein Slot. Default Slot A. Zwei Slots gleichzeitig → fallback Slot A.
    if new_data.get("enable_slot_a") and new_data.get("enable_slot_b"):
        _LOGGER.warning(
            "SolarEdge: nur ein Slot erlaubt — Slot A bevorzugt"
        )
        new_data["enable_slot_b"] = False
    if not new_data.get("enable_slot_a") and not new_data.get("enable_slot_b"):
        # Fallback: A aktivieren wenn beide aus
        new_data["enable_slot_a"] = True
```

**3. Runtime-Erzwingung (`EEGOptimizer.__init__`):** Bei `_is_solaredge`-Flag auch `_enable_dual_discharge=False` setzen, unabhängig von `config.get(...)`. Dispatcher-Pfadwahl im `_should_discharge` springt damit auf Legacy-Pfad. Begründung: User könnte den Inverter-Type im Setup wechseln, ohne dass der Save-Path getriggert wird → Defensive Code-Pfad-Konvergenz.

### Panel-Erkennungs-Text

```text
"Auf SolarEdge-Wechselrichtern können nicht beide Slots gleichzeitig laufen.
Grund: SolarEdge schreibt Entlade-Kommandos in NVRAM-Speicher, der nur eine
begrenzte Zahl Schreibzyklen zulässt. Wähle daher genau einen Slot:"

[Radio: ◉ Slot A — Abend (Default)]
[Radio: ○ Slot B — Morgen]
```

Tooltip am Radio-Container: *"NVRAM-Verschleiß: nur ein Slot pro Tag möglich"* (D-07 wörtlich).

## Telemetry-Reasons

### Neue Keys (8 Stück, additiv zu `ALL_REASONS`)

```python
# optimizer.py — nach Z. 91 ergänzen
# Phase 11: Dual-Window
REASON_BEFORE_SLOT_A = "before_slot_a"
REASON_SLOT_A_ACTIVE = "slot_a_active"
REASON_SLOT_A_RESERVE_REACHED = "slot_a_reserve_reached"
REASON_BETWEEN_SLOTS = "between_slots"
REASON_BEFORE_SLOT_B = "before_slot_b"
REASON_SLOT_B_ACTIVE = "slot_b_active"
REASON_SLOT_B_WINDOW_EXPIRED = "slot_b_window_expired"
REASON_SLOT_B_PRE_SUNRISE_CUTOFF = "slot_b_pre_sunrise_cutoff"
```

In `ALL_REASONS` (Z. 95-117) einfügen (frozenset bleibt closed-set für Backend-Diagnose).

### `REASON_LABELS_DE`-Erweiterung (Z. 120-142)

```python
REASON_LABELS_DE: dict[str, str] = {
    ... bestehende Einträge ...,
    REASON_BEFORE_SLOT_A: "Vor Slot-A-Start (Abend)",
    REASON_SLOT_A_ACTIVE: "Slot A aktiv (Abend-Entladung)",
    REASON_SLOT_A_RESERVE_REACHED: "Slot-A-Reserve erreicht",
    REASON_BETWEEN_SLOTS: "Pause zwischen Slot A und Slot B",
    REASON_BEFORE_SLOT_B: "Vor Slot-B-Start (Morgen)",
    REASON_SLOT_B_ACTIVE: "Slot B aktiv (Morgen-Entladung)",
    REASON_SLOT_B_WINDOW_EXPIRED: "Slot-B-Fenster abgelaufen",
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF: "Slot B beendet vor Sonnenaufgang",
}
```

### Wirkung auf bestehende Tests

`tests/test_optimizer.py` importiert eine Untermenge der Reasons (siehe Z. 30-56). Es ist nicht nötig, alle neuen Keys einzeln zu importieren — der `ALL_REASONS`-Subset-Check in den Tests (z.B. Z. 225 `assert set(reasons).issubset(ALL_REASONS)`) deckt sie automatisch ab.

### Backend-Schema-Auswirkung

`EEGEnergyOptimzierBackend/src/types.ts` (separate Repo, deployed): das `reasons`-Feld in `state_changes` und `snapshots` ist heute `string[]`. Neue Keys sind also additiv ohne Breaking-Change. Plan 11-04 sollte einen PR-Hinweis im Body führen, dass das Backend-Reasons-Auswertungs-Dashboard (in v1.1.x noch in Bau) die neuen Keys später einlernen kann. **Kein Hard-Coupling — Phase 11 kann ohne Backend-Update deployen.**

`TELEMETRY_SETTINGS_KEYS` muss erweitert werden (siehe Migration-Sektion oben), damit `/v1/profile`-Update die neuen Slot-Settings ans Backend schickt.

## Inverter-Race-Validation

### Empfehlung: **Auto-Korrektur mit Toast** (NICHT Hard-Reject)

**Begründung anhand bestehender Validation-Patterns:**

| Pattern im Repo | Verhalten | Anwendbar auf Phase 11? |
|----------------|-----------|------------------------|
| SolarEdge < 5 kW Discharge-Power (`websocket_api.py:411-414` + `optimizer.py:349-354`) | **Auto-clamp auf 5.0**, Warning ins Log | Ja — gleiche Defense-in-depth (Save + Runtime) |
| PeakShare `window_start ≥ window_end` (`peakshare.py:370-378`) | **Plan auf None setzen**, Info-Log, weiter mit Fixed-Time | Ja — Slot wird inaktiv statt Fehler |
| Fronius Modbus host empty (`websocket_api.py:421-426`) | **Hard-Reject** mit `invalid_config` | Nein — Inverter-Konfig ist setup-kritisch, Race-Konfig ist nur Optimierung |

Der **b_start vs a_min_required_end + 5min**-Konflikt ist eine **Optimierungs-Korrektheit**, kein Setup-Fehler. Auto-Korrektur ist konsistent mit dem dominanten Pattern (SolarEdge-Clamp, PeakShare-Window-Clamp), und die Hard-Reject-Variante zwingt den User zu Mathematik im Wizard, die der Server selbst machen kann.

### Implementierung im `ws_save_config`

```python
# websocket_api.py:ws_save_config — neuer Block vor async_update_entry
if new_data.get("enable_dual_discharge") and new_data.get("enable_slot_a") and new_data.get("enable_slot_b"):
    a_start = _parse_hhmm(new_data.get("discharge_a_start_time", "20:00"))
    b_start = _parse_hhmm(new_data.get("discharge_b_start_time", "03:00"))
    # Slot-A-min-Ende: Slot A muss mindestens 30 Minuten laufen können (Inverter-Sense),
    # also a_start + 30min als "frühestmögliches A-Ende". Dann +5min Pause.
    a_min_end_total_min = (a_start + 30) % (24 * 60)
    b_start_total_min = b_start
    # Auf "Tagesachse mit a abends, b nach Mitternacht" abbilden
    if b_start_total_min < 12 * 60:
        b_on_tomorrow = b_start_total_min + 24 * 60
    else:
        b_on_tomorrow = b_start_total_min
    if a_min_end_total_min < 12 * 60:
        a_on_tomorrow = a_min_end_total_min + 24 * 60
    else:
        a_on_tomorrow = a_min_end_total_min
    if b_on_tomorrow < a_on_tomorrow + 5:
        new_b_start = (a_on_tomorrow + 5) % (24 * 60)
        new_b_start_str = f"{new_b_start // 60:02d}:{new_b_start % 60:02d}"
        _LOGGER.warning(
            "Dual-Window: b_start %s zu nah an a_start+30min — auf %s angehoben",
            new_data.get("discharge_b_start_time"), new_b_start_str
        )
        new_data["discharge_b_start_time"] = new_b_start_str
```

**Hinweis:** Die "30-Minuten-Mindest-Slot-A-Dauer" ist eine pragmatische Annahme für die Validation — in der Praxis endet Slot A meist deutlich später (durch Reserve-SOC). Die Validation prüft hier den **Worst-Case**: User setzt `a_start=02:55` und `b_start=03:00` → `a_min_end = 03:25` → `b_start` würde auf `03:30` gehoben. Bei sinnvollen Defaults (`a_start=20:00, b_start=03:00`) greift die Validation nie.

**Frontend-Komplement:** Im Panel kann ein dezenter Inline-Hint angezeigt werden ("Slot B startet nach Slot A — Mindestabstand 5 Min."), aber **die autoritative Korrektur erfolgt server-side**.

## Test-Strategie

### Empfehlung: **Neue Datei `tests/test_dual_window.py`** (NICHT Erweiterung)

**Begründung:**
- `tests/test_optimizer.py` ist bereits **1891 Zeilen** (verifiziert via `wc -l`). Eine Erweiterung um ~600+ Zeilen für 4 neue Test-Klassen (Slot A, Slot B, Pro-Slot-Hysterese, `compute_b_window_end`) macht die Datei unübersichtlich.
- Phase-8-Pattern (siehe `tests/test_telemetry_*.py`): Neue Feature-Bereiche bekommen eigene Test-Dateien, gemeinsame Helpers leben in `conftest.py`.
- Bestehende Helpers `_make_config()`, `_make_snapshot()`, `_make_optimizer()` (Z. 63-106) sollten nach `tests/conftest.py` extrahiert oder als Modul-Level-Funktionen aus `test_optimizer.py` importiert werden, damit `test_dual_window.py` sie weiternutzen kann.

### Test-Layout `test_dual_window.py`

```
class TestComputeBWindowEnd:
    def test_summer_sunrise_5min_dominant()     # Case 1
    def test_winter_sunrise_cap_dominant()      # Case 2
    def test_transition_sunrise_5min_dominant() # Case 3
    def test_deep_winter_cap_dominant()         # Case 4
    def test_morning_offset_one_hour_pause()    # Req 5 — pause-lücke
    def test_sunrise_none_returns_none()        # Edge-Case
    def test_b_start_after_b_end_returns_none() # Edge-Case Sommer mit b_start=05:00

@pytest.mark.parametrize("sunrise_hour,morning_offset", [
    (5, 0), (5, 1), (6, 0), (7, 0), (7, 1), (8, 0), (8, 1),
])
class TestSlotBPreSunriseCutoff:
    def test_slot_b_ends_min_5min_before_morning_einspeisung()

class TestSlotAReserveLogic:
    def test_a_only_uses_min_soc_no_reserve()                # Req 8 (a-only)
    def test_dual_a_uses_min_soc_plus_reserve()              # Req 2
    def test_a_ends_when_soc_below_min_plus_reserve()        # Req 2
    def test_a_ends_5min_before_b_start_when_b_active()      # Req 9 + Req 2

class TestSlotBLogic:
    def test_b_only_uses_min_soc_threshold()                 # Req 8 (b-only)
    def test_b_window_expired_marks_correct_reason()         # Req 7
    def test_b_pre_sunrise_cutoff_marks_correct_reason()     # Req 7

class TestProSlotHysteresis:
    def test_a_reactivation_requires_min_soc_plus_5()        # Req 4
    def test_b_starts_without_a_reactivation_aufschlag()     # Req 4 — independence
    def test_slot_dates_reset_after_sunrise()                # Reset-Logic

class TestSolarEdgeXOR:
    def test_solaredge_dual_forced_to_legacy()               # Req 6 (runtime)
    def test_save_config_solaredge_disables_dual()           # Req 6 (save-path)
    def test_save_config_solaredge_two_slots_falls_back_a()  # Req 6 (xor)

class TestMutualExclusion:
    def test_slot_b_does_not_run_when_morning_einspeisung_starts()  # Req 5

class TestDualWindow24hSimulation:
    """24h-Simulationslauf: Decision-Sequenz über einen vollen Tag."""
    def test_dual_a_and_b_both_activate_with_correct_slot_marker()  # Req 8 + D-10
    def test_a_only_pure_evening_discharge()
    def test_b_only_pure_morning_discharge()
```

### Sampling-Rate (für Validation Architecture)

Das Test-Layout ist **70% pure-function-tests** (compute_b_window_end, single-Slot-Decision-Methoden) und **30% integration** (24h-Simulation). Die Pure-Tests laufen in unter 100ms. Die 24h-Simulation läuft mit gemockten 30s-Cycles über parametrisierten Stunden — geschätzt unter 5 Sekunden gesamt.

**Aufwandsschätzung:** ~600-800 Zeilen Test-Code in der neuen Datei. Plus ~50 Zeilen Anpassung in `test_optimizer.py` (Legacy-Pfad-Tests bleiben gültig — siehe Acceptance Criteria SPEC.md erstes Item: "byte-identisch zu v1.1").

### Erweiterung `test_optimizer.py`

Minimal — nur ein neuer Test-Block:

```python
class TestEnableDualDischargeFalseLegacyPath:
    """Ensures byte-identical legacy behavior with enable_dual_discharge=False."""
    def test_legacy_path_called_when_dual_disabled()
    def test_legacy_path_called_when_solaredge()
    def test_legacy_uses_existing_discharge_start_time_default_01_00()
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (`asyncio_mode=auto`) — bestehend in `pyproject.toml` |
| Config file | `pyproject.toml` (kein separates pytest.ini) |
| Quick run command | `pytest tests/test_dual_window.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| Req 1 | Migration v14→v15 setzt korrekte Defaults | unit | `pytest tests/test_dual_window.py::TestMigrationV14ToV15 -x` | ❌ Wave 0 (`tests/test_dual_window.py` neu) |
| Req 2 | Slot A endet bei min_soc + reserve_pct | unit | `pytest tests/test_dual_window.py::TestSlotAReserveLogic -x` | ❌ Wave 0 |
| Req 3 | `compute_b_window_end` 4 Test-Cases | unit | `pytest tests/test_dual_window.py::TestComputeBWindowEnd -x` | ❌ Wave 0 |
| Req 4 | Pro-Slot-Hysterese unabhängig | unit | `pytest tests/test_dual_window.py::TestProSlotHysteresis -x` | ❌ Wave 0 |
| Req 5 | Slot B endet ≥5min vor Morgen-Einspeisung | unit (parametrized) | `pytest tests/test_dual_window.py::TestSlotBPreSunriseCutoff -x` | ❌ Wave 0 |
| Req 6 | SolarEdge auf Single-Window beschränkt | unit | `pytest tests/test_dual_window.py::TestSolarEdgeXOR -x` | ❌ Wave 0 |
| Req 7 | Slot-spezifische Reasons in `Decision.reasons` | unit | `pytest tests/test_dual_window.py -k reason -x` | ❌ Wave 0 |
| Req 8 | A-only / B-only / Dual liefern erwartete Decision-Sequenz | integration (24h-Sim) | `pytest tests/test_dual_window.py::TestDualWindow24hSimulation -x` | ❌ Wave 0 |
| Req 9 | b_start ≥ a_min_required_end + 5min | unit | `pytest tests/test_dual_window.py::TestInverterRaceValidation -x` und `pytest tests/test_websocket_api.py -k race -x` | ❌ Wave 0 |
| SPEC ACC #1 | `enable_dual_discharge=False` → byte-identische Legacy-Pfad | unit | `pytest tests/test_optimizer.py::TestEnableDualDischargeFalseLegacyPath -x` | ❌ Wave 0 (erweitern) |
| SPEC ACC #11 | UAT 7-Tage-Beobachtung | manual-only | manuelles Monitoring an Huawei (192.168.1.211) und/oder Fronius (192.168.100.211) | — |

### Sampling Rate

- **Per task commit:** `pytest tests/test_dual_window.py -x -q` (~5 sec)
- **Per wave merge:** `pytest tests/ -q` (full suite, ~30-60 sec)
- **Phase gate:** Full suite green vor `/gsd-verify-work`; UAT-Phase startet nach Merge

### Wave 0 Gaps

- [ ] `tests/test_dual_window.py` — neue Datei mit allen Test-Klassen oben
- [ ] `tests/conftest.py` — Helper-Extraktion (`_make_config`, `_make_snapshot`, `_make_optimizer`) für Wiederverwendung in `test_dual_window.py`
- [ ] `tests/test_optimizer.py` — `TestEnableDualDischargeFalseLegacyPath`-Klasse hinzufügen
- [ ] Framework-Install: keiner — pytest + pytest-asyncio bereits etabliert

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | nein | Phase 11 fügt keine neuen Auth-Pfade hinzu — WS-Save nutzt bestehende HA-Auth |
| V3 Session Management | nein | dito |
| V4 Access Control | nein | dito |
| V5 Input Validation | **ja** | Voluptuous-Schema im `ws_save_config`-Handler erweitern um Range-Checks für Reserve-PCT (0..50), Time-Strings (`pattern="[0-2][0-9]:[0-5][0-9]"`), Bool-Checks für die drei `enable_*`-Keys |
| V6 Cryptography | nein | Keine neuen Krypto-Operationen |

### Known Threat Patterns für HA-Custom-Integration

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed Time-String im WS-Save | Tampering | Voluptuous-Pattern-Validation oder explizites `_parse_hhmm` mit Default-Fallback |
| Negativer/Zu-hoher reserve_pct | Tampering / DoS | `vol.Range(min=0, max=50)` |
| Inverter-Race-Konflikt vom UI bypass | Tampering | Server-side-Validation im Save-Path (siehe Inverter-Race-Sektion) |
| Migration läuft mehrfach (idempotenz) | Tampering | `if entry.version < N` ist HA-Standard und idempotent — keine zusätzliche Logik nötig |

**Privacy:** Die neuen Slot-Settings (`enable_slot_a` etc.) müssen in `TELEMETRY_SETTINGS_KEYS` ergänzt werden, **enthalten aber keine personenbezogenen Daten oder Entity-IDs** — passt in die existierende Whitelist (siehe `const.py:166`).

## Common Pitfalls

### Pitfall 1: Sunrise-Anchoring bei `compute_b_window_end`
**What goes wrong:** Wenn Slot B um 03:00 startet (vor Mitternacht-Übergang in lokaler Zeit), zeigt `snap.sunrise` (= `next_rising`) auf den heutigen Sonnenaufgang. `replace(hour=cap_h, minute=cap_m, ...)` ankert dann am richtigen Tag. Wenn aber jemand Slot B um 22:00 starten würde (würde nicht zur Spec passen, aber Code muss robust sein), wäre `next_rising` morgen.
**Why it happens:** `_get_sun_times` (`optimizer.py:600-626`) nutzt `next_rising` ohne Tagestrennung — das ist immer der NÄCHSTE Sonnenaufgang.
**How to avoid:** `compute_b_window_end` ankert immer am `sunrise.replace(hour=cap_h, ...)` — der Tag ist automatisch der `next_rising`-Tag. Bei `b_start < 12:00` (Morgen-Slot) und `now >= 12:00` muss Slot B aufs morgen-Datum projiziert werden, analog zu `discharge_start_resolved` in `optimizer.py:953-962`.
**Warning signs:** Test mit `now = 23:00` (Vorabend) und b_start = 03:00 zeigt `b_window_end > b_start_today + 24h` oder ähnlichen Off-by-Day-Fehler.

### Pitfall 2: Pro-Slot-Hysterese-Reset zu früh
**What goes wrong:** Ohne den `now >= snap.sunrise_today`-Guard im Reset würde `_slot_a_activated_date` direkt um 00:00 lokale Zeit zurückgesetzt — dann verliert Slot A die Hysterese-Information für seine eigene Sitzung über Mitternacht.
**Why it happens:** Bestehender Code für `_discharge_activated_date` (`optimizer.py:1087-1093`) nutzt das gleiche Pattern aus genau diesem Grund.
**How to avoid:** Strikt an das bestehende `_discharge_activated_date`-Pattern halten: Reset erst nach `today's sunrise`.
**Warning signs:** Test simuliert A-Aktivierung 23:00 → A-Ende 02:00 → A-Reaktivierung um 02:30 ohne `min_soc + 5`-Aufschlag.

### Pitfall 3: PeakShare available_kwh-Doppelvergabe
**What goes wrong:** Slot A und Slot B teilen sich die gleiche Batterie. Wenn beide Slots `available_kwh = (battery_soc − min_soc) / 100 * capacity` rechnen, planen sie beide die gesamte verfügbare Energie — was die Reserve-Logik aushebelt.
**Why it happens:** Naiver Refactor übernimmt die Available-kWh-Formel aus `_should_discharge:966` 1:1 für beide Slots.
**How to avoid:** Slot A nutzt `(battery_soc − a_min_soc)` mit `a_min_soc = min_soc + reserve_pct` (wenn Slot B aktiv); Slot B nutzt `reserve_pct / 100 * capacity` als statische Schätzung. Statisch heißt hier: einfach das Reserve-Budget. Das schließt aus, dass Slot A "zu viel" plant.
**Warning signs:** 24h-Simulation zeigt Slot A entlädt komplett auf min_soc → Slot B kann nicht starten weil SOC < min_soc.

### Pitfall 4: Decision.discharge_active_slot bleibt None bei Slot-Ausführung
**What goes wrong:** `_evaluate` setzt `discharge_active_slot` nur, wenn `should_discharge=True` UND der Refactor das Feld korrekt füllt. Wenn der Refactor das vergisst, ist der Sensor "Entscheidung" und das Backend-State-Change-Event uneindeutig.
**Why it happens:** Das Feld ist neu — Tests müssen es explizit prüfen.
**How to avoid:** Test in `TestDualWindow24hSimulation` prüft explizit `decision.discharge_active_slot in {"A", "B"}` während aktiver Discharge-Phasen.
**Warning signs:** Telemetrie-Backend-Logs zeigen `discharge_active_slot = None` während `zustand = "Abend-Entladung"`.

### Pitfall 5: Frontend-Save sendet `enable_slot_b=true` für SolarEdge
**What goes wrong:** Frontend-Code-Pfade übersehen die XOR-Sperre und schicken den UI-State direkt an `ws_save_config`. Ohne Save-Path-Defense würde `enable_slot_b=True` für SolarEdge persistiert und bei nächstem Cycle ignoriert (Runtime erzwingt) — aber Config-State und Runtime-Verhalten driften.
**Why it happens:** UI-State-Management in plain JavaScript Shadow-DOM (siehe `eeg-optimizer-panel.js:_renderSettings`) ist deklarativ; Logik-Branches werden manchmal vergessen.
**How to avoid:** Save-Path im `ws_save_config` ist autoritativ (siehe SolarEdge-XOR-Sektion). Frontend-Bug ist dann nur kosmetisch (User sieht im Panel was er nicht hat) — Test im WS-Save-Pfad fängt es.
**Warning signs:** Test `test_save_config_solaredge_two_slots_falls_back_a` schlägt fehl wenn Save-Path-Defense fehlt.

### Pitfall 6: 5-Minuten-Lücke zur Morgen-Einspeisung wird durch Optimizer-Cycle-Latenz verletzt
**What goes wrong:** Optimizer läuft alle 30 Sekunden. Slot B endet rechnerisch um 06:25, Morgen-Einspeisung beginnt rechnerisch um 06:30. Aber der nächste Cycle-Tick könnte erst um 06:25:28 sein — das ist immer noch innerhalb der 5-Minuten-Pause, also kein Konflikt. Risiko: User setzt `morning_offset = 0` UND der Cycle-Tick fällt zwischen `06:30:00` und `06:30:29` → für 30 Sekunden ist Slot B technisch bis 06:25 noch aktiv (vorheriger State) und Morgen-Einspeisung ab 06:30 (neuer State) — kein paralleler Befehl an den Inverter, weil Decision Mutex ist.
**Why it happens:** Decision-Engine ist Mutex (state ist eine String-Variable), nicht parallel.
**How to avoid:** Bestehende Mutex-Logik (`_evaluate` Z. 1102-1107) hält fest: `block ODER discharge ODER normal`. Einer gewinnt. Nur ein Inverter-Kommando pro Cycle.
**Warning signs:** Wenn die Acceptance-Tests ein paralleles "Slot B aktiv UND Morgen-Einspeisung aktiv" zeigen, ist die State-Resolution kaputt.

## Code Examples

### Slot-A-Logik (Skelett)

```python
# optimizer.py — neue Methode
def _evaluate_slot_a(
    self, snap: Snapshot, min_soc: float
) -> tuple[bool, list[str], list[str], bool]:
    """Slot A — Abend-Entladung.

    Returns (passed, reasons, blocked_by, hysteresis_active) — analog zu
    _should_discharge-Body, aber slot-A-spezifisch.

    SOC-Schwelle: min_soc + reserve_pct (wenn Slot B aktiv), sonst min_soc.
    Hysterese-Aufschlag +5% bei Reaktivierung innerhalb derselben Sitzung.
    """
    blocked_by: list[str] = []
    passing: list[str] = []

    # Slot-A-Window: a_start bis a_end_effective (Energie- oder Zeit-getrieben)
    a_start = snap.now.replace(
        hour=self._discharge_a_start_h, minute=self._discharge_a_start_m,
        second=0, microsecond=0,
    )
    if snap.now < a_start:
        return (False, [], [REASON_BEFORE_SLOT_A], False)

    # 5min-Pause vor Slot B (wenn aktiv)
    if self._enable_slot_b:
        b_start = snap.now.replace(
            hour=self._discharge_b_start_h, minute=self._discharge_b_start_m,
            second=0, microsecond=0,
        )
        if self._discharge_b_start_h < 12:
            b_start += timedelta(days=1)
        a_end_cap = b_start - timedelta(minutes=5)
        if snap.now >= a_end_cap:
            return (False, [], [REASON_SLOT_A_RESERVE_REACHED], False)

    # SOC-Schwelle
    a_reserve = self._discharge_a_reserve_pct if self._enable_slot_b else 0
    a_min_soc = min_soc + a_reserve

    is_reactivation = (
        self._slot_a_activated_date is not None
        and self._last_active_slot != "A"
    )
    effective_min_soc = a_min_soc + (5 if is_reactivation else 0)

    if snap.battery_soc <= effective_min_soc:
        if is_reactivation:
            blocked_by.append(REASON_HYSTERESIS_STRICT)
        blocked_by.append(REASON_SLOT_A_RESERVE_REACHED)
        return (False, [], blocked_by, is_reactivation)

    if is_reactivation:
        passing.append(REASON_HYSTERESIS_STRICT)
    passing.append(REASON_SOC_ABOVE_MIN)
    return (True, passing, [], is_reactivation)
```

### Slot-B-Logik (Skelett)

```python
def _evaluate_slot_b(
    self, snap: Snapshot, min_soc: float
) -> tuple[bool, list[str], list[str], bool]:
    """Slot B — Morgen-Entladung mit adaptivem Ende vor Sonnenaufgang."""
    if snap.sunrise is None:
        return (False, [], [REASON_SUNRISE_UNKNOWN], False)

    b_start = snap.now.replace(
        hour=self._discharge_b_start_h, minute=self._discharge_b_start_m,
        second=0, microsecond=0,
    )
    b_end = compute_b_window_end(
        snap.now, snap.sunrise,
        self._discharge_b_end_cap, self._morning_start_offset_h,
    )
    if b_end is None or b_start >= b_end:
        return (False, [], [REASON_SLOT_B_PRE_SUNRISE_CUTOFF], False)
    if snap.now < b_start:
        return (False, [], [REASON_BEFORE_SLOT_B], False)
    if snap.now >= b_end:
        return (False, [], [REASON_SLOT_B_WINDOW_EXPIRED], False)

    is_reactivation = (
        self._slot_b_activated_date is not None
        and self._last_active_slot != "B"
    )
    effective_min_soc = min_soc + (5 if is_reactivation else 0)

    if snap.battery_soc <= effective_min_soc:
        blocked_by = [REASON_SOC_BELOW_MIN]
        if is_reactivation:
            blocked_by.insert(0, REASON_HYSTERESIS_STRICT)
        return (False, [], blocked_by, is_reactivation)

    passing = [REASON_SOC_ABOVE_MIN]
    if is_reactivation:
        passing.insert(0, REASON_HYSTERESIS_STRICT)
    return (True, passing, [], is_reactivation)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-Window-Discharge mit 04:00 Hard-Cutoff | Single-Window mit `compute_hard_cutoff = min(04:00, sunrise−1h)` | v1.1.x (Phase 8 Vorarbeit) | Korridor in Wintermonaten ~2.5h länger — Phase 11 baut auf diesem Pattern für Slot B auf |
| Hysterese als boolean `is_in_session` | Hysterese als ISO-Date-Feld `_*_activated_date` | v1.0 Phase 3 | Robust gegen Mitternachts-Übergänge — Phase 11 dupliziert das Pattern pro Slot |
| String-Reasons als Freitext | snake_case-Closed-Set in `ALL_REASONS` | v1.1 Phase 8 | Backend-deterministisch, lokalisierbar via `REASON_LABELS_DE` — Phase 11 erweitert additiv |
| `_discharge_plan: tuple` (single) | `_discharge_plan: dict[Literal["a","b"], tuple]` | Phase 11 (NEU) | Cache-Schema-Migration nötig (siehe PeakShare-Sektion) |

**Deprecated/outdated:**
- SPEC.md/CONTEXT.md-Referenzen auf "Version 12 → 13" sind out-of-date (Ist: 14 → 15)
- Veraltete Annahme "Single-Window genügt": Telemetrie der UAT-Phase wird zeigen ob Dual-Window in Praxis Mehrwert bringt; aktuell wertfrei

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Statische Slot-B-Schätzung `available_kwh_b ≈ reserve_pct/100 * capacity` ist ausreichend | PeakShare-Cache-Schema | Bei zu kleinem Wert: Slot B startet selten/gar nicht. Bei zu großem Wert: Slot A bricht zu früh ab. UAT-Beobachtung zeigt es, Backlog v1.3+ ist demand-weighted. |
| A2 | "30-Minuten-Mindest-Slot-A-Dauer" für Inverter-Race-Validation ist pragmatisch | Inverter-Race-Validation | Bei zu großer Annahme würde gut konfigurierter b_start unnötig angehoben. 30min ist konservativ; alternativ 0min — lässt User-Konfig roh durch (aber kein Schutz). |
| A3 | UAT-7-Tage-Beobachtung ist die finale Akzeptanzmetrik (kein quantitativer Schwellwert) | Test-Strategie | Wenn User "nicht gut" entscheidet, muss zurückgerollt werden — daher Default-Wechsel sauber kommunizieren in Release-Notes. |
| A4 | PeakShare-API liefert für Slot B (03:00–07:00) im Winter Daten | PeakShare-Cache | Wenn Daten fehlen, Slot B fällt auf Fixed-Time-Pfad. Acceptable per SPEC-Constraint. |
| A5 | Frontend Plain-HTML/Shadow-DOM-Pattern skaliert auf zwei Sub-Bereiche | Architektur | Falls UI-Code zu unübersichtlich wird, Wizard-Step könnte langfristig auf Web-Components migrieren. Nicht in Phase 11. |
| A6 | Backend-D1-Schema akzeptiert neue Reasons-Keys ohne Migrate (string[] ist additiv) | Telemetry-Reasons | Falls Backend strikt validiert, würde ein 400-Response beim State-Change kommen. Reporter loggt + buffert das — keine Daten gehen verloren. PR-Body 11-04 sollte Backend-PR-Hinweis enthalten. |

## Open Questions

1. **Wie lange soll `_evaluate_legacy_window` neben den Slot-Methoden bestehen bleiben?**
   - What we know: D-05 fixiert "Code wird nicht entfernt", spätere Phase könnte konsolidieren.
   - What's unclear: Wann ist "spätere Phase"? Nach 6 Monaten Dual-Stabilität (siehe Deferred)?
   - Recommendation: Auf Backlog setzen mit Trigger "Dual-Window 6 Monate stabil + Telemetrie-Daten zeigen >95% Dual-Pfad-Nutzung". Phase 11 selbst keine Änderung.

2. **Sollen Slot A und Slot B unabhängige Discharge-Power-Settings haben?**
   - What we know: SPEC fixiert `CONF_DISCHARGE_POWER_KW` als single Value.
   - What's unclear: SolarEdge-Mindest-5-kW-Constraint gilt heute global. Wenn Slot A z.B. 3 kW sanft entlädt und Slot B 5 kW kurz feuert, würde sich der Algorithmus ändern.
   - Recommendation: **Nein für Phase 11.** Globale `discharge_power_kw` bleibt für beide Slots. Backlog v1.3+ falls Empirie es nahelegt.

3. **Activity-Log-Heartbeat-Texte: deutsch oder snake_case?**
   - What we know: D-38 aus Phase 8 hält Activity-Log-Strings deutsch (User-Texte), Reasons-Keys separat.
   - What's unclear: "Slot A aktiv (Abend-Entladung)" oder "Abend-Entladung" für die User-Anzeige?
   - Recommendation: User-Anzeige nutzt `REASON_LABELS_DE` für die deutschen Texte. Heartbeat-String beim Slot-Start-Log: `"Abend-Entladung Slot A gestartet (SOC 80% → 25%)"` — analog zum bestehenden Slot-agnostischen Log-Pattern.

## Environment Availability

Phase 11 ist eine reine Code/Config-/UI-Erweiterung — keine externen Tools, Services oder Runtimes außerhalb des bestehenden HA-Stacks. Alle Dependencies (Python stdlib, voluptuous, pytest, pytest-asyncio, homeassistant-Framework) sind bereits Teil der Test- und Laufzeit-Umgebung.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest + pytest-asyncio | Tests | ✓ | bestehend in `pyproject.toml` | — |
| voluptuous | WS-Save-Validation | ✓ | bestehend (HA-Core-Dep) | — |
| homeassistant.helpers.storage | PeakShare-Cache-Migration | ✓ | bestehend (HA-Core) | — |

**Missing dependencies with no fallback:** keine.
**Missing dependencies with fallback:** keine.

## Sources

### Primary (HIGH confidence) — verifiziert in dieser Session

- `custom_components/eeg_energy_optimizer/config_flow.py:24` — `VERSION = 14` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/__init__.py:748-846` — vollständige `_async_migrate_entry` mit Migrations-Blöcken bis v14 `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/optimizer.py:175-208` — `compute_hard_cutoff` als Vorlage für `compute_b_window_end` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/optimizer.py:905-1055` — kompletter Body von `_should_discharge` (Refactor-Ziel) `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/optimizer.py:63-142` — `ALL_REASONS` + `REASON_LABELS_DE` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/optimizer.py:247-298` — `Decision`-Dataclass `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/optimizer.py:1057-1230` — `_evaluate`-Pfad mit Hysterese-Reset und State-Resolution `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/peakshare.py:44-131, 295-409` — `find_discharge_window` und `get_discharge_plan` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/peakshare.py:163-195` — Cache-Persistence-Pattern mit `Store` `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/websocket_api.py:389-457` — `ws_save_config` mit SolarEdge-Clamp und Fronius-Reject `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/const.py:84-130, 137-178` — Phase-3-Konstanten und Telemetrie-Whitelist `[VERIFIED: file read]`
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js:3000-3400` — Wizard-Step + Settings-Tab Discharge-Sektionen `[VERIFIED: file read]`
- `tests/test_optimizer.py:1-120, 207-274` — bestehende Test-Helpers und Discharge-Tests `[VERIFIED: file read]`
- `.planning/milestones/v1.2-phases/11-dual-window-discharge/11-SPEC.md` — 9 Requirements `[CITED]`
- `.planning/milestones/v1.2-phases/11-dual-window-discharge/11-CONTEXT.md` — D-01 bis D-10 `[CITED]`
- `.planning/milestones/v1.0-phases/03-optimizer-safety-system/03-CONTEXT.md` — Hysterese-Pattern `[CITED]`
- `.planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md` — Reasons-Closed-Set-Pattern (D-09, D-12) `[CITED]`

### Secondary (MEDIUM confidence)

- HA-Convention für `async_migrate_entry` (idempotent, version-bumping pattern) — Standard-Practice in HA-Core und allen analysierten Migrations-Blöcken im Repo `[VERIFIED: cross-referenced with multiple migration blocks]`

### Tertiary (LOW confidence) — nicht relevant für Phase 11

— keine, da Phase 11 vollständig auf Repo-internem Wissen basiert

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — alle Libraries bereits in Repo, alle Versionen aus `pyproject.toml` / `manifest.json` ablesbar
- Architecture: HIGH — vollständig auf bestehenden Code-Anker-Patterns aufgebaut, keine spekulativen Komponenten
- Pitfalls: HIGH — abgeleitet aus existierenden Code-Bugs/Comments im Repo (z.B. `optimizer.py:1059-1071` SOC-None-Guard)
- Inverter-Race-Empfehlung: MEDIUM — basiert auf 3 verifizierten Validation-Patterns, A2-Annahme könnte präziser sein

**Research date:** 2026-05-04
**Valid until:** 2026-06-04 (30 days, stable phase scope)

---

## RESEARCH COMPLETE
