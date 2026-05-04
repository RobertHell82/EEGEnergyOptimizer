---
phase: 11
plan: 01
subsystem: optimizer-foundation
tags: [dual-window, migration, reasons-catalog, config-schema, foundation]
requires: []
provides:
  - "compute_b_window_end (module-level pure function)"
  - "8 slot-aware REASON_* keys in ALL_REASONS + REASON_LABELS_DE"
  - "Decision.discharge_active_slot field (str | None)"
  - "Migration v14 -> v15 with SolarEdge XOR and non-SolarEdge dual-defaults"
  - "Module-level test helpers _make_config / _make_snapshot / _make_optimizer in tests/conftest.py"
  - "tests/test_dual_window.py (TestComputeBWindowEnd, TestReasonsCatalog, TestMigrationV14ToV15)"
affects:
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/optimizer.py
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - tests/conftest.py
  - tests/test_dual_window.py
  - tests/test_config_flow.py
  - tests/test_telemetry_hooks.py
  - tests/test_optimizer.py
tech-stack:
  added: []
  patterns:
    - "Anchor-an-Sunrise-Tag (replace(hour=, minute=))"
    - "Striktester min() über alle Schnittquellen"
    - "Snake_case-Reasons-Closed-Set (Phase-8-Pattern)"
    - "Setdefault statt Hard-Set für additive Migrationen"
    - "Modul-Level-Helper statt pytest-Fixture (parametrisierbar)"
key-files:
  created:
    - tests/test_dual_window.py
  modified:
    - custom_components/eeg_energy_optimizer/const.py
    - custom_components/eeg_energy_optimizer/optimizer.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - tests/conftest.py
    - tests/test_config_flow.py
    - tests/test_telemetry_hooks.py
    - tests/test_optimizer.py
decisions:
  - "compute_b_window_end belässt 5min Pause vor sunrise UND vor morning_offset-Start (Mutex)"
  - "Migration v14->v15 ist setdefault-basiert (additiv) — kein Hard-Override"
  - "SolarEdge-Sonderfall in Migration: Slot A only, dual_discharge=False"
  - "REASON_*-Keys snake_case-Werte exakt = Variablen-Suffix"
  - "Decision.discharge_active_slot Annotation: str | None (nicht Literal) — konsistent mit bestehenden Decision-Feldern"
metrics:
  duration: "ca. 10 Minuten"
  completed: "2026-05-04"
  tasks_completed: 2
  files_changed: 9
  lines_added_approx: 429
---

# Phase 11 Plan 01: Foundation für Dual-Window-Entladung — Summary

JWT-äquivalente Foundation für Phase 11: Datenstruktur + Migration v14→v15 + slot-aware Reasons-Catalog + adaptive B-Window-Funktion + Test-Infrastruktur. Phase 11-02 baut darauf direkt auf.

## Was gebaut wurde

### const.py — 7 Konfigurations-Keys + 6 Defaults

Phase-11-Konstanten-Block direkt nach Phase-3-Block (additiv, keine bestehenden Keys verändert):

| Konstante                                  | Wert / Default                |
| ------------------------------------------ | ----------------------------- |
| `CONF_ENABLE_DUAL_DISCHARGE`               | `"enable_dual_discharge"`     |
| `CONF_ENABLE_SLOT_A`                       | `"enable_slot_a"`             |
| `CONF_ENABLE_SLOT_B`                       | `"enable_slot_b"`             |
| `CONF_DISCHARGE_A_START_TIME`              | `"discharge_a_start_time"`    |
| `CONF_DISCHARGE_B_START_TIME`              | `"discharge_b_start_time"`    |
| `CONF_DISCHARGE_B_END_CAP`                 | `"discharge_b_end_cap"`       |
| `CONF_DISCHARGE_A_RESERVE_PCT`             | `"discharge_a_reserve_pct"`   |
| `DEFAULT_ENABLE_DUAL_DISCHARGE_NON_SOLAREDGE` | `True`                     |
| `DEFAULT_ENABLE_DUAL_DISCHARGE_SOLAREDGE`  | `False`                       |
| `DEFAULT_DISCHARGE_A_START_TIME`           | `"20:00"`                     |
| `DEFAULT_DISCHARGE_B_START_TIME`           | `"03:00"`                     |
| `DEFAULT_DISCHARGE_B_END_CAP`              | `"07:00"`                     |
| `DEFAULT_DISCHARGE_A_RESERVE_PCT`          | `15`                          |

`TELEMETRY_SETTINGS_KEYS` um die 7 neuen Keys erweitert (am Ende des Tupels, positionsstabil).

### optimizer.py — `compute_b_window_end` + 8 Reasons + Decision-Field

**Signatur:**
```python
def compute_b_window_end(
    now: datetime,
    sunrise: datetime | None,
    b_end_cap: str,
    morning_offset_h: float,
) -> datetime | None
```

Liefert striktestes `min()` aus drei Schnittquellen:
- `b_end_cap` an Sunrise-Tag verankert (z.B. "07:00")
- `sunrise − morning_offset_h − 5min` (Pause vor Morgen-Einspeisung — SPEC §5)
- `sunrise − 5min` (Pause vor Sunrise selbst)

`sunrise=None` → `None` (Slot B kann ohne Sunrise nicht laufen).

**SPEC-Test-Coverage (alle grün):**
| Saison        | Sunrise | b_end_cap | offset | Erwartet | Dominator         |
| ------------- | ------- | --------- | ------ | -------- | ----------------- |
| Sommer        | 04:52   | 07:00     | 0      | 04:47    | sunrise − 5min    |
| Winter        | 07:30   | 07:00     | 0      | 07:00    | cap               |
| Übergang      | 06:00   | 07:00     | 0      | 05:55    | sunrise − 5min    |
| Tiefer Winter | 08:30   | 07:00     | 0      | 07:00    | cap               |
| Winter+offset | 07:30   | 07:00     | 1      | 06:25    | pre-morning-pause |

**8 neue REASON_*-Konstanten** (snake_case, alle in `ALL_REASONS`, alle mit deutschem Label in `REASON_LABELS_DE`):

| Konstante                          | snake_case-Wert                   | DE-Label                              |
| ---------------------------------- | --------------------------------- | ------------------------------------- |
| `REASON_BEFORE_SLOT_A`             | `before_slot_a`                   | Vor Slot-A-Start (Abend)              |
| `REASON_SLOT_A_ACTIVE`             | `slot_a_active`                   | Slot A aktiv (Abend-Entladung)        |
| `REASON_SLOT_A_RESERVE_REACHED`    | `slot_a_reserve_reached`          | Slot-A-Reserve erreicht               |
| `REASON_BETWEEN_SLOTS`             | `between_slots`                   | Pause zwischen Slot A und Slot B      |
| `REASON_BEFORE_SLOT_B`             | `before_slot_b`                   | Vor Slot-B-Start (Morgen)             |
| `REASON_SLOT_B_ACTIVE`             | `slot_b_active`                   | Slot B aktiv (Morgen-Entladung)       |
| `REASON_SLOT_B_WINDOW_EXPIRED`     | `slot_b_window_expired`           | Slot-B-Fenster abgelaufen             |
| `REASON_SLOT_B_PRE_SUNRISE_CUTOFF` | `slot_b_pre_sunrise_cutoff`       | Slot B beendet vor Sonnenaufgang      |

Alle Labels mit echten Umlauten (ä/ö/ü) — keine ASCII-Substitution.

**Decision-Dataclass-Erweiterung:**
```python
# Phase 11: aktiver Slot ("A" | "B" | None für Legacy/Pause)
discharge_active_slot: str | None = None
```

### __init__.py — Migration v14 → v15 (mit SolarEdge-Branch)

```python
if entry.version < 15:
    new_data = {**entry.data}
    inverter_type = new_data.get("inverter_type", "")
    is_solaredge = inverter_type == "solaredge_storedge"
    if is_solaredge:
        new_data.setdefault("enable_dual_discharge", False)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", False)
    else:
        new_data.setdefault("enable_dual_discharge", True)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", True)
    new_data.setdefault("discharge_a_start_time", "20:00")
    new_data.setdefault("discharge_b_start_time", "03:00")
    new_data.setdefault("discharge_b_end_cap", "07:00")
    new_data.setdefault("discharge_a_reserve_pct", 15)
    hass.config_entries.async_update_entry(entry, data=new_data, version=15)
```

**Sicherheits-Eigenschaften:**
- `setdefault` statt `=`: respektiert vorhandene User-Werte (T-11-01-01, getestet).
- Idempotent über `if entry.version < 15:` Guard (T-11-01-02, getestet).
- Inverter-Type via Stringliteral `"solaredge_storedge"` (konsistent mit `optimizer.py:349, :384`) — vermeidet zusätzlichen Import von `INVERTER_TYPE_SOLAREDGE` in `__init__.py`.

### config_flow.py — VERSION 14 → 15

Einzige Änderung: `VERSION = 14` → `VERSION = 15`. Sync mit `async_migrate_entry`.

### tests/conftest.py — Modul-Level-Helpers extrahiert

Drei Funktionen aus `tests/test_optimizer.py:63-106` nach `tests/conftest.py` als Modul-Level-Funktionen kopiert:
- `_make_config(**overrides)` — Default `discharge_start_time="20:00"` für Bestands-Tests.
- `_make_snapshot(**overrides)` — Snapshot mit Sensible-Defaults.
- `_make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider, config=None)`.

Die Original-Funktionen in `test_optimizer.py` blieben unverändert (Duplikat akzeptabel — beide Test-Dateien laufen grün; keine Cross-Imports notwendig). Phase-11-Tests können sie via `from tests.conftest import _make_config` importieren, sobald sie sie brauchen.

### tests/test_dual_window.py (NEU) — 14 Tests, alle grün

| Klasse                  | Tests | Coverage                                                          |
| ----------------------- | ----- | ----------------------------------------------------------------- |
| `TestComputeBWindowEnd` | 7     | 4 SPEC-Cases + morning_offset + sunrise_none + cap_clamping       |
| `TestReasonsCatalog`    | 3     | 8 keys in ALL_REASONS / 8 keys in REASON_LABELS_DE / Decision-Default |
| `TestMigrationV14ToV15` | 4     | Non-SolarEdge defaults / SolarEdge XOR / preserve user values / idempotency |

### tests/test_config_flow.py — VERSION-Assertion + Smoke

`test_version_in_sync_with_migration` von `== 14` auf `== 15` aktualisiert.
Neuer `test_config_flow_version_is_15` als zusätzlicher Phase-11-Smoke.

### tests/test_telemetry_hooks.py — v13→v14-Tests an v15-Migrations-Kette angepasst

Beide `test_v13_to_v14_migration_*`-Tests prüften vorher `entry.version == 14`. Da Phase 11 die Migration durchgehend von v13 über v14 nach v15 hochzieht, läuft `async_migrate_entry` jetzt komplett durch. Die Tests prüfen jetzt:
- `entry.version == 15` (finale Version nach Phase 11).
- `entry.data["discharge_start_time"] == "01:00"` (v14-Effekt bleibt unverändert wirksam).

Damit bleibt der inhaltliche Test-Zweck (v14 setzt discharge_start_time hart auf "01:00") erhalten.

## Test-Status

| Suite                                           | Vorher          | Nachher           |
| ----------------------------------------------- | --------------- | ----------------- |
| `tests/test_dual_window.py` (NEU)               | —               | 14 passed         |
| `tests/test_optimizer.py`                       | 86 passed       | 86 passed         |
| `tests/test_config_flow.py -k version`          | 1 passed        | 2 passed          |
| `tests/test_config_flow.py` (gesamt)            | 5 passed, 1 fail (pre-existing) | 6 passed, 1 fail (pre-existing) |
| `tests/test_telemetry_hooks.py`                 | grün            | grün (2 Asserts angepasst) |
| `pytest tests/ -q` (gesamt)                     | 351 passed, 1 fail | 366 passed, 1 fail |

**Pre-existing Failure** (nicht Phase-11-relevant): `tests/test_config_flow.py::TestStepUser::test_creates_entry_on_confirmation` erwartet `data == {"setup_complete": False}`, aber der aktuelle `config_flow.py:async_step_user` setzt zusätzlich `CONF_TELEMETRY_ENABLED: True`. Diese Disparität existiert seit vor Plan 11-01 und ist out-of-scope für Phase 11.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] `test_optimizer.py::test_reasons_catalog_is_closed_set` failed**
- **Found during:** Task 1 (nach Reasons-Erweiterung in optimizer.py)
- **Issue:** Bestehender Closed-Set-Pin-Test in test_optimizer.py erwartet exakt die alten 22 REASON_*-Keys. Phase 11 erweitert um 8 neue (D-09 additiv).
- **Fix:** `_EXPECTED_REASON_KEYS`-frozenset in `tests/test_optimizer.py:1035-1083` um die 8 neuen Phase-11-Keys ergänzt — gleiche Liste wie in `optimizer.py:ALL_REASONS`.
- **Files modified:** `tests/test_optimizer.py`
- **Commit:** b41341d

**2. [Rule 3 - Blocker] `test_telemetry_hooks.py::test_v13_to_v14_migration_*` (2 Tests) failed**
- **Found during:** Task 2 (nach Aktivierung der v15-Migration)
- **Issue:** Diese beiden Tests starten mit `entry.version=13` und prüften, dass das Entry am Ende `version == 14` ist. Da die v15-Migration jetzt nahtlos im selben Aufruf durchläuft, erreicht das Entry direkt `version=15`. Der inhaltliche v14-Effekt (discharge_start_time="01:00") bleibt aber unverändert.
- **Fix:** Assertion auf `entry.version == 15` angepasst, Kommentar ergänzt: "Phase 11: nach v14 läuft v15 direkt durch — finale Version ist 15."
- **Files modified:** `tests/test_telemetry_hooks.py`
- **Commit:** b2d23b8

### Pre-existing Failures Not Touched

**1. `tests/test_config_flow.py::TestStepUser::test_creates_entry_on_confirmation`**
- Test war schon vor Plan-Start failed. Out of scope (Scope-Boundary-Regel).
- Logged hier zur Vollständigkeit, NICHT gefixt in 11-01.

## Threat Model Compliance

| Threat ID    | Disposition | Mitigation Status |
| ------------ | ----------- | ----------------- |
| T-11-01-01   | mitigate    | ✅ `setdefault` durchgehend in v15-Block; Test `test_existing_user_values_preserved` grün |
| T-11-01-02   | mitigate    | ✅ `if entry.version < 15:`-Guard; Test `test_migration_idempotent_when_already_v15` grün |
| T-11-01-03   | accept      | ✅ Plan 11-01 vertraut Save-Path-Validierung in 11-03; manuelles Tampering = Crash via `int(...)` (akzeptabel) |
| T-11-01-04   | mitigate    | ✅ Whitelist-Pattern in `TELEMETRY_SETTINGS_KEYS` beibehalten; nur Bool/Int/Time-String-Keys hinzugefügt |

## Hinweis für Phase 11-02

Plan 11-02 (Optimizer-Refactor + PeakShare-Cache-Schema) baut **direkt** auf den hier erstellten Artefakten auf:

- `compute_b_window_end` ist als Module-Level-Funktion in `optimizer.py` importierbar:
  ```python
  from .optimizer import compute_b_window_end
  ```
- 8 neue `REASON_*`-Konstanten + `Decision.discharge_active_slot` sind verfügbar.
- Migration ist abgeschlossen — neue Config-Keys können in `_should_discharge`-Refactor direkt via `config.get("enable_dual_discharge", False)` gelesen werden.
- Test-Helpers in `tests/conftest.py` sind als Modul-Level-Funktionen importierbar via `from tests.conftest import _make_config, _make_snapshot, _make_optimizer`.

## Acceptance Criteria — Status

- [x] const.py exportiert 7 CONF_* + 6 DEFAULT_* + erweiterte TELEMETRY_SETTINGS_KEYS
- [x] optimizer.py exportiert `compute_b_window_end` + 8 neue REASON_* in ALL_REASONS + REASON_LABELS_DE-Erweiterung + `Decision.discharge_active_slot`
- [x] config_flow.py: `VERSION = 15`
- [x] __init__.py enthält Migrations-Block v14→v15 mit SolarEdge-Sonderfall
- [x] tests/conftest.py exportiert die drei Helper-Funktionen als Modul-Level
- [x] tests/test_dual_window.py existiert mit TestComputeBWindowEnd (7 Tests), TestReasonsCatalog (3 Tests), TestMigrationV14ToV15 (4 Tests)
- [x] Volle Test-Suite `pytest tests/ -q` zeigt 366 passed (1 pre-existing fail aus altem test_config_flow.py-Test, nicht Phase 11)
- [x] Keine Regression in tests/test_optimizer.py (86 passed)

## Self-Check: PASSED

Alle in Frontmatter und Text aufgeführten Artefakte existieren und sind committet:

- ✅ FOUND: `custom_components/eeg_energy_optimizer/const.py` (modified, commit b41341d)
- ✅ FOUND: `custom_components/eeg_energy_optimizer/optimizer.py` (modified, commit b41341d)
- ✅ FOUND: `custom_components/eeg_energy_optimizer/__init__.py` (modified, commit b2d23b8)
- ✅ FOUND: `custom_components/eeg_energy_optimizer/config_flow.py` (modified, commit b2d23b8)
- ✅ FOUND: `tests/conftest.py` (modified, commit b2d23b8)
- ✅ FOUND: `tests/test_dual_window.py` (NEW, commit b2d23b8)
- ✅ FOUND: `tests/test_config_flow.py` (modified, commit b2d23b8)
- ✅ FOUND: `tests/test_telemetry_hooks.py` (modified, commit b2d23b8)
- ✅ FOUND: `tests/test_optimizer.py` (modified, commit b41341d)
- ✅ FOUND: commit `b41341d` in git log
- ✅ FOUND: commit `b2d23b8` in git log
- ✅ Pattern checks all green:
  - `grep -c "VERSION = " config_flow.py` = 1
  - `grep -c "if entry.version <" __init__.py` = 13 (>= 5)
  - `grep "CONF_ENABLE_DUAL_DISCHARGE" const.py` = 1 occurrence
  - `grep "def compute_b_window_end" optimizer.py` = 1 occurrence
  - `grep "discharge_active_slot: str | None = None" optimizer.py` = 1 occurrence
