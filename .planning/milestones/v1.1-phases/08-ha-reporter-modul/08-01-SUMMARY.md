---
phase: 08-ha-reporter-modul
plan: 01
subsystem: optimizer
tags: [decision-refactor, telemetry, reasons-katalog, tdd]
requires: []
provides:
  - "Decision dataclass mit reasons/blocked_by/snapshot Feldern"
  - "ALL_REASONS frozenset (20 snake_case-Keys, Closed Set)"
  - "REASON_LABELS_DE für deutsche UI-Renderer"
  - "Snapshot.to_telemetry_dict() — lean Snapshot für State-Change-Payload"
  - "EEGOptimizer._current_power_readings() — Live-Power-Werte mit Sign-Konventionen"
  - "_should_block_charging Signatur (bool, list, list)"
  - "_should_discharge Signatur (bool, float, list, list, bool)"
affects:
  - "EntscheidungsSensor: reasons/blocked_by/snapshot als HA-State-Attribute"
  - "Activity-Log in __init__.py: Detektion über Katalog-Key statt String-Match"
  - "Markdown-Renderer zeigt Diagnose-Sektionen aus REASON_LABELS_DE"
tech-stack:
  added: []
  patterns:
    - "Closed-Set Reasons-Katalog (frozenset-Guard für Tests + Backend)"
    - "Mutual-Exclusion-Invariante: bei block=True ist blocked_by leer und umgekehrt"
    - "Defensive Kopien (list/dict) in EntscheidungsSensor gegen Mutations-Leaks"
key-files:
  created: []
  modified:
    - "custom_components/eeg_energy_optimizer/optimizer.py"
    - "custom_components/eeg_energy_optimizer/sensor.py"
    - "custom_components/eeg_energy_optimizer/__init__.py"
    - "tests/test_optimizer.py"
    - "tests/test_decision_sensor.py"
decisions:
  - "REASON_HYSTERESIS_STRICT als Modifier-Marker an SOC-Resultat gekoppelt — landet in passing[] bei Pass und in blocked_by[] bei Block, nie eigenständig"
  - "Watchdog-Pfad spiegelt REASON_DISCHARGE_ABORTED_TODAY in decision.blocked_by, damit Activity-Log-Detektion auch im Abbruch-Zyklus selbst greift"
  - "Snapshot.to_telemetry_dict() liefert nur soc_pct (deterministische Snapshot-Daten); Live-Werte werden in _evaluate über _current_power_readings ergänzt"
metrics:
  duration: "~45 min"
  completed: "2026-04-29"
  commits: 2
  tests-added: 32
  tests-total-passing: 279
---

# Phase 8 Plan 01: Decision-Refactor Summary

**One-liner:** Decision-Engine spricht jetzt die strukturierte Telemetrie-Sprache des Backends — geschlossener snake_case-Reasons-Katalog, lean Snapshot-Payload, alle Konsumenten in einem Atomar-Refactor migriert.

## Was wurde gebaut

Plan 08-01 etabliert das Fundament für die Plans 08-02/08-03 (Reporter + Hooks), indem der `Decision`-Dataclass auf das Schema von `EEGEnergyOptimzierBackend/src/types.ts::StateChangePayload` ausgerichtet wird. Vorher hatte `Decision` ein redundantes `block_reasons`-Feld (das in `_evaluate` versehentlich `discharge_reasons` aliast hat) und freitext-Strings als Reason-Quelle. Jetzt:

1. **Reasons-Katalog (D-12)** — 20 snake_case-Konstanten in `optimizer.py`, in `ALL_REASONS: frozenset` zusammengefasst. Schließt die Welt der möglichen Begründungen — Tests prüfen Closed-Set-Invariante. Jeder Eintrag in `decision.reasons`/`decision.blocked_by` ist ein Member; keine Hand-getippten Strings mehr.

2. **REASON_LABELS_DE (D-38)** — deutsche Texte für UI-Renderer. Der Markdown-Renderer übersetzt Katalog-Keys via diesem Dict. Der Telemetrie-Pfad sendet ausschließlich Keys (deterministisch).

3. **`Decision.reasons` / `Decision.blocked_by` / `Decision.snapshot`** — drei neue kanonische Felder (D-09). `block_reasons` ist weg (D-10). `discharge_reasons` (deutsche Freitext-Liste) bleibt für die Status-Card im Panel — saubere Trennung UI vs. Telemetrie.

4. **`_should_block_charging` → `(bool, list, list)`** — 8 dokumentierte Branches (Feature off, Sunrise unknown, Outside window, In-Window-Varianten mit/ohne Hysterese), jede emittiert dokumentierte Katalog-Keys. Mutual-Exclusion-Invariante: wenn `block=True`, ist `blocked_by` leer; wenn `block=False`, ist `reasons` leer.

5. **`_should_discharge` → `(bool, float, list, list, bool)`** — 12 Branches mit Pass-Reasons (`SOC_ABOVE_MIN`, `TOMORROW_PV_SUFFICIENT`, `PEAKSHARE_WINDOW_ACTIVE`) und Block-Reasons (`SOC_BELOW_MIN`, `BEFORE_DISCHARGE_START`, `HARD_CUTOFF_AFTER_4AM`, `DISCHARGE_ABORTED_TODAY`, …). Hysterese als Modifier markiert.

6. **`Snapshot.to_telemetry_dict()`** — liefert die Snapshot-deterministischen Felder (`soc_pct`); Live-Werte (pv/grid/battery/consumption_now_kw) werden in `_evaluate` über `_current_power_readings()` ergänzt. Ergebnis matcht 1:1 `SnapshotPayload` aus `types.ts`.

7. **`EEGOptimizer._current_power_readings()`** — liest live-Power-Sensoren mit Sign-Konventionen (Huawei: pass-through; SolaX: grid/battery flip). Bei fehlenden Sensoren `None` (NICHT 0.0 — Backend-Analytics unterscheiden „0 W exportiert" von „konnten nicht lesen").

8. **Konsumenten-Migration im selben Plan (D-10)**:
   - `EntscheidungsSensor.update_from_decision`: exponiert `reasons`/`blocked_by`/`snapshot` als HA-State-Attribute (defensive `list()`/`dict()` gegen Mutations-Leak).
   - `__init__.py::_optimizer_cycle`: Activity-Log-Detektion „Netzbezug-Abbruch" via `REASON_DISCHARGE_ABORTED_TODAY in decision.blocked_by` statt String-Suche `"Netzbezug" in r`.
   - Watchdog-Pfad in `_check_grid_import_watchdog` spiegelt den Katalog-Key in `decision.blocked_by`, damit die Detektion auch in dem Zyklus greift, in dem der Watchdog feuert.
   - Markdown-Renderer zeigt zwei neue Diagnose-Sektionen aus den Katalog-Keys.

## Tasks & Commits

| Task | Beschreibung | Commit |
|------|--------------|--------|
| 1 | Reasons-Katalog + Decision/Snapshot-Felder + neue `_should_*`-Signaturen (TDD: Tests-First) | `f36dd11` |
| 2 | `_current_power_readings` + `Decision.snapshot`-Anreicherung + EntscheidungsSensor + Activity-Log-Migration | `a5e266b` |

## Test-Ergebnisse

| Suite | Vorher | Nachher | Neu |
|-------|--------|---------|-----|
| `test_optimizer.py` | 39 | 71 | +32 |
| `test_decision_sensor.py` | 8 | 11 | +3 |
| **Gesamt** | **247** | **279** | **+32** |

Alle 279 Tests grün. Closed-Set-Invariante getestet: jeder REASON_*-Konstante ist in `ALL_REASONS`, jeder Key in `REASON_LABELS_DE` ist in `ALL_REASONS`, jeder Wert ist snake_case (Regex `^[a-z][a-z_0-9]*$`). Branch-Coverage für `_should_block_charging` (8 Branches) und `_should_discharge` (12 Branches) — jeder asserted invariant `set(reasons|blocked_by) ⊆ ALL_REASONS` und Mutual-Exclusion.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `REASON_HYSTERESIS_STRICT` als eigenständiger Block-Eintrag verursachte Regression**

- **Found during:** Task 1 GREEN-Phase (`test_discharge_reactivation_succeeds_with_enough_margin` schlug fehl)
- **Issue:** Erste Implementierung append'te `REASON_HYSTERESIS_STRICT` immer wenn `is_reactivation=True` an `blocked_by`, auch wenn SOC die strengere Schwelle übertraf. Dadurch war `blocked_by` nie leer und `should_discharge` wurde fälschlich `False`.
- **Fix:** Hysterese-Marker an SOC-Resultat gekoppelt — landet in `passing[]` bei Pass, in `blocked_by[]` bei Block, nie eigenständig. Spiegelt das Pattern aus dem Morgen-Pfad (`REASON_HYSTERESIS_STRICT` als Modifier von PV-Forecast-Resultat).
- **Files modified:** `custom_components/eeg_energy_optimizer/optimizer.py`
- **Commit:** `f36dd11` (Fix war Teil derselben Task-1-Implementierung)

**2. [Rule 2 - Missing critical functionality] Watchdog-Pfad reflektierte Abbruch-Zustand nicht in `decision.blocked_by`**

- **Found during:** Task 2 — beim Migrieren der Activity-Log-Detektion in `__init__.py`
- **Issue:** Der ursprüngliche Plan migrierte den Activity-Log-Check auf `REASON_DISCHARGE_ABORTED_TODAY in decision.blocked_by`. Aber `_check_grid_import_watchdog` setzt `decision.zustand = STATE_NORMAL` und appendet nur an `decision.discharge_reasons` (deutsche Freitext-Liste). Im selben Zyklus wäre `blocked_by` aus `_should_discharge` ohne den neuen Eintrag, und die Detektion in `__init__.py` würde stillschweigend nicht greifen.
- **Fix:** Watchdog appendet `REASON_DISCHARGE_ABORTED_TODAY` zusätzlich an `decision.blocked_by` und setzt `decision.reasons = []` (Zustand wechselte auf Normal).
- **Files modified:** `custom_components/eeg_energy_optimizer/optimizer.py`
- **Commit:** `f36dd11`

**3. [Rule 3 - Blocking] Test-Setup für `_evaluate` benötigt `_now`-Patch beim Optimizer-Konstruktor**

- **Found during:** Task 2 RED-Phase
- **Issue:** Neue `TestDecisionSnapshotFullShape`-Tests konstruierten den Optimizer außerhalb des `_now`-Patch-Kontexts. `self._startup_time` wurde aus dem ungemockten `_now()` gelesen, bei der späteren Subtraktion unter Patch ergab sich `MagicMock - real_datetime` und `< STARTUP_GRACE_SECONDS` warf TypeError.
- **Fix:** Optimizer-Konstruktion in den Patch-Kontext gezogen (Pattern aus `test_evaluate_tracks_activation_dates` übernommen).
- **Files modified:** `tests/test_optimizer.py`
- **Commit:** `a5e266b`

Keine Architektur-Änderungen, keine `Rule 4`-Eskalationen.

## Anwendung von D-09 bis D-12

| Decision | Umsetzung |
|----------|-----------|
| D-09 (kanonische Felder) | `Decision.reasons`, `Decision.blocked_by`, `Decision.snapshot` populated bei jedem `_evaluate` |
| D-10 (vollständige Migration) | `block_reasons` weg, `discharge_reasons` bewusst behalten (UI-Freitext), Konsumenten alle migriert (Sensor, Activity-Log, Markdown) |
| D-11 (neue Signaturen) | `_should_block_charging` → 3-Tupel, `_should_discharge` → 5-Tupel |
| D-12 (geschlossener Katalog) | `ALL_REASONS` frozenset, Tests prüfen Closed-Set + snake_case |

## Verifikation

```bash
# Alle Tests grün
pytest tests/                                                            # 279 passed

# Closed-Set-Garantien
pytest tests/test_optimizer.py::TestReasonsCatalog                        # 5 passed
pytest tests/test_optimizer.py::TestSnapshotToTelemetryDict               # 3 passed
pytest tests/test_optimizer.py::TestShouldBlockChargingBranches           # 9 passed
pytest tests/test_optimizer.py::TestShouldDischargeBranches               # 12 passed
pytest tests/test_optimizer.py::TestCurrentPowerReadings                  # 5 passed
pytest tests/test_optimizer.py::TestDecisionSnapshotFullShape             # 2 passed
```

`block_reasons` ist nirgends mehr im Production-Code. In Tests nur noch im Negativ-Assertion-Test (`test_update_does_not_expose_legacy_block_reasons`).

## Self-Check: PASSED

- [x] `custom_components/eeg_energy_optimizer/optimizer.py` modifiziert (commit `f36dd11`, `a5e266b`)
- [x] `custom_components/eeg_energy_optimizer/sensor.py` modifiziert (commit `a5e266b`)
- [x] `custom_components/eeg_energy_optimizer/__init__.py` modifiziert (commit `a5e266b`)
- [x] `tests/test_optimizer.py` modifiziert (commits `f36dd11`, `a5e266b`)
- [x] `tests/test_decision_sensor.py` modifiziert (commits `f36dd11`, `a5e266b`)
- [x] Commit `f36dd11` existiert (Task 1)
- [x] Commit `a5e266b` existiert (Task 2)
- [x] Alle 279 Tests grün
- [x] Reasons-Katalog ist Closed-Set; REASON_LABELS_DE deckt alle Keys
- [x] `block_reasons` nicht mehr in Production-Code
- [x] Activity-Log nutzt Katalog-Key
