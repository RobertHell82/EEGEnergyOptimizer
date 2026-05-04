# Plan 11-04 — Markdown + Activity-Log + CHANGELOG — Summary

**Phase:** 11 — Dual-Window-Entladung
**Wave:** 3 (parallel zu 11-03, files-disjunkt durch Test-Datei-Split)
**Status:** Complete
**Tasks:** 2/2
**Date:** 2026-05-04

## Was geliefert wurde

### Task 1 — Markdown + Activity-Log + Frontend + Integration-Tests

**Files modified:**
- `custom_components/eeg_energy_optimizer/optimizer.py` (`_build_markdown`)
- `custom_components/eeg_energy_optimizer/__init__.py` (`_log_activity` Closure innerhalb `async_setup_entry`)
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` (Aktivitäts-Timeline-Render)
- `tests/test_dual_window_integration.py` (NEU, getrennt von `tests/test_dual_window.py`, vermeidet Wave-3-Kollision mit Plan 11-03)

**Concrete changes:**

1. **`_build_markdown`** im Decision-Sensor:
   - **Dynamischer Header**: `### Morgen-Entladung` bei `discharge_active_slot == "B"`, sonst `### Abend-Entladung`.
   - **Slot-Marker**: `- Aktiver Slot: A` oder `- Aktiver Slot: B` als zusätzliche Zeile bei aktiver Entladung. Bei `None` (Legacy) wird die Zeile übersprungen → rückwärtskompatibel.
   - **Slot-Konfigurations-Übersicht**: neue Sektion `### Slot-Konfiguration` zeigt aktive/deaktivierte Slots mit Start-Zeiten und Reserve/Cap-Werten. Nur sichtbar wenn `enable_dual_discharge=True` und `inverter_type != solaredge_storedge`.

2. **`_log_activity`** in `__init__.py:1290+`:
   - `entry_data`-Dict-Builder erhält das Feld `"discharge_active_slot": decision.discharge_active_slot` (D-09 — VERPFLICHTEND, kein Skip-Test).
   - Wert wird über `hass.bus.async_fire("eeg_optimizer_activity", entry_data)` an Frontend-Listener und potenzielle Telemetrie-Sinks weitergegeben.
   - Persistierte Activity-Log-Einträge ohne das Feld bleiben rückwärtskompatibel (additive Erweiterung).

3. **Frontend Aktivitäts-Timeline** (`eeg-optimizer-panel.js:4196+`):
   - Neuer `slotMarker` und `zustandLabel` vor dem `reason`-Render.
   - Bei `e.zustand === "Abend-Entladung"` UND `e.discharge_active_slot === "A" || === "B"` wird der Status-Text um " (Slot A)" oder " (Slot B)" erweitert.
   - Strikt-Check `=== "A" || === "B"` macht Render-Verhalten bei `null/undefined` Legacy-kompatibel.

4. **Tests** (in `tests/test_dual_window_integration.py`):

   **TestMarkdownRendering** (5 Tests):
   - `test_markdown_shows_slot_a_marker` — Slot-A-Marker + `### Abend-Entladung`-Header
   - `test_markdown_shows_slot_b_marker` — Slot-B-Marker + dynamischer `### Morgen-Entladung`-Header
   - `test_markdown_no_slot_marker_for_legacy` — Legacy-Pfad ohne Slot-Marker
   - `test_markdown_shows_slot_config_when_dual_enabled` — Slot-Konfigurations-Sektion sichtbar mit allen Werten
   - `test_markdown_no_slot_config_when_legacy` — Sektion nicht sichtbar bei `enable_dual_discharge=False`

   **TestEvaluate24hSlotMarkerPersistence** (3 Tests, mit `real_now`-Fixture):
   - `test_slot_a_activated_date_set_on_first_activation` — `_evaluate` setzt `_slot_a_activated_date`, `Decision.discharge_active_slot=="A"`
   - `test_slot_b_activated_date_set_independently_from_a` — Slot-B-only-Konfig, `_slot_b_activated_date` gesetzt, `_slot_a_activated_date` bleibt None
   - `test_slot_a_date_reset_after_sunrise` — Reset-Logik nullt veraltetes Datum aus dem Vortag

   **TestActivityLogSlotContext** (2 Tests, KEIN pytest.mark.skip):
   - `test_log_entry_carries_slot_marker` — Source-Pattern-Check der `__init__.py` auf das exakte Pattern `"discharge_active_slot": decision.discharge_active_slot`
   - `test_log_entry_dict_shape_includes_slot_field` — Reproduktion der Dict-Builder-Logik mit allen drei Slot-Werten (A / B / None)

   **`real_now`-Fixture:** Patcht `optimizer._now` auf eine echte datetime-Funktion. Der Conftest stubt `homeassistant.util.dt` als `MagicMock`, sodass der `try`-Branch in `optimizer.py` einen MagicMock-`_now` bindet — Vergleiche mit `STARTUP_GRACE_SECONDS` schlagen sonst fehl. Plus `opt._startup_time = datetime(2020, 1, 1, ...)` umgeht die Grace-Period.

**Acceptance-Criteria-Greps (alle erfüllt):**
- `Aktiver Slot:` in optimizer.py → 2 Treffer ✓ (≥1 gefordert)
- `Morgen-Entladung` in optimizer.py → 1 Treffer ✓
- `Slot-Konfiguration` in optimizer.py → 1 Treffer ✓
- `decision.discharge_active_slot` in optimizer.py → ≥4 Treffer ✓ (Plan 11-02 + 11-04)
- `"discharge_active_slot": decision.discharge_active_slot` in __init__.py → 1 ✓
- `discharge_active_slot` in panel.js → 3 Treffer ✓ (≥2 gefordert)
- Slot-Suffix `Slot ${e.discharge_active_slot}` → 1 ✓

**Commit:** `3606e04` feat(11-04): expose discharge_active_slot in markdown + activity-log + frontend

### Task 2 — CHANGELOG.md

**Files modified:**
- `CHANGELOG.md` (NEU — erste CHANGELOG.md im Projekt)

**Concrete changes:**

Neuer v1.2.0-dev-Eintrag im Keep-a-Changelog-Format mit Sektionen:

1. **Verhaltensänderung beim Update** (prominent platziert nach Header):
   - Erklärt Default-Flip auf Dual-Window
   - Listet Slot A (Abend) und Slot B (Morgen) mit Default-Zeiten
   - Beschreibt Pro-Slot-Hysterese und Energie-Reserve
   - Mitigation-Sektion: Hysterese, PV-Tomorrow-Garantie, Opt-Out-Pfad
   - SolarEdge-Sonderfall mit NVRAM-Verschleiß-Erklärung

2. **Added** — alle neuen Konfigurations-Keys, `compute_b_window_end`, 8 neue Telemetrie-Reasons, `Decision.discharge_active_slot`, Activity-Log-Feld, SolarEdge-XOR-Radio, Markdown-Sektion, Frontend-Slot-Suffix.

3. **Changed** — Default-Flip, `_should_discharge`-Dispatcher-Refactor, PeakShare-Cache-Schema-Migration, WebSocket-Save-Path-Validation, Onboarding-Panel-Erweiterung.

4. **Migration** — Config-Entry-Version 14 → 15, additive `setdefault`-Migration, getrennte Defaults für SolarEdge.

5. **Tests** — Liste der neuen Test-Dateien (`tests/test_dual_window.py` + `tests/test_dual_window_integration.py`) mit Test-Klassen-Übersicht.

6. **Manual UAT** — Verweis auf 7-Tage-Beobachtung an Test-HA-Instanz.

Plus zwei retrospektive Stub-Einträge für v1.1.3 und v1.1.2 (Verweis auf Git-Tags).

**Acceptance-Criteria (alle erfüllt):**
| Check | Forderung | Ergebnis |
|-------|-----------|----------|
| `1.2.0-dev` | ≥1 | 1 ✓ |
| `Verhaltensänderung` (echte Umlaute) | ≥1 | 2 ✓ |
| `Schreibzyklen\|Sonnenaufgang\|verfügbar\|unabhängig` | ≥3 | 6 ✓ |
| `Verhaltensaenderung\|Schreibzyklenverschleiss\|verfuegbar\|unabhaengig` (negativ) | =0 | 0 ✓ |
| `## .*Verhaltensänderung beim Update` | ≥1 | 1 ✓ |
| `Dual-Window` | ≥3 | 5 ✓ |
| `Slot A` | ≥3 | 7 ✓ |
| `Slot B` | ≥3 | 7 ✓ |
| `NVRAM-Verschleiß` | ≥1 | 1 ✓ |
| `v14 → v15` | ≥1 | 2 ✓ |
| `Pro-Slot-Hysterese` | ≥1 | 3 ✓ |
| `discharge_active_slot` | ≥1 | 2 ✓ |

**Commit:** `25fd526` docs(11-04): add CHANGELOG.md with v1.2.0-dev dual-window entry

## Test-Status

| Suite | Pass | Fail | Notes |
|-------|------|------|-------|
| `tests/test_dual_window_integration.py::TestMarkdownRendering` | 5 | 0 | neu |
| `tests/test_dual_window_integration.py::TestEvaluate24hSlotMarkerPersistence` | 3 | 0 | neu, mit `real_now`-Fixture |
| `tests/test_dual_window_integration.py::TestActivityLogSlotContext` | 2 | 0 | neu, KEIN Skip |
| `tests/test_dual_window_integration.py` (gesamt) | 10 | 0 | neue Datei |
| `tests/` (Gesamt) | 412 | 1 | OOS-Failure `test_creates_entry_on_confirmation` unverändert |

## Wave-3-Kollisions-Vermeidung

`tests/test_dual_window.py` (Plan 11-03 Tests) und `tests/test_dual_window_integration.py` (Plan 11-04 Tests) sind disjunkt. Beide Plans editieren `frontend/eeg-optimizer-panel.js`, aber an unterschiedlichen Stellen (11-03: Wizard/Settings-Discharge-Sektion + Save-Path Radio-Handler; 11-04: Aktivitäts-Timeline-Render). Da beide Plans inline-sequenziell ausgeführt wurden (nicht parallel im Worktree), ist die Vermeidung eher dokumentarisch — bei zukünftiger Worktree-Parallelisierung würde die Trennung greifen.

## Decisions adressiert

| Decision | Erfüllt durch |
|----------|---------------|
| D-04 (Default-Wechsel + CHANGELOG-Pflicht) | Task 2 — CHANGELOG-Sektion "Verhaltensänderung beim Update" prominent |
| D-08 (Status-Anzeige Slot-Marker) | Task 1 — `_build_markdown` Slot-Marker + Konfigurations-Sektion |
| D-09 (Slot-Kontext im Activity-Log) | Task 1 — `_log_activity` `entry_data["discharge_active_slot"]` + Frontend-Render |
| D-10 (Decision.discharge_active_slot durchgereicht) | Task 1 — Markdown rendert das Feld; Activity-Log serialisiert es |
| SPEC §7 (Telemetry-Reasons im Activity-Log) | Task 1 — Activity-Log-Reason-Reihe konsistent, neuer Slot-Kontext additiv |
| SPEC §8 (Independent Slot-Aktivierung) | Task 1 — `TestEvaluate24hSlotMarkerPersistence`-Tests prüfen unabhängige Aktivierung |

## Phase-11-Abschluss-Status

Mit Plan 11-04 sind alle 4 Plans abgeschlossen:
- 11-01 (Wave 1, foundational): Datenstruktur + Migration v14→v15 ✓
- 11-02 (Wave 2): Optimizer-Refactor + PeakShare-Cache-Migration ✓
- 11-03 (Wave 3a): Panel-UI + websocket_api Save-Path ✓
- 11-04 (Wave 3b): Markdown + Activity-Log + Frontend-Slot-Suffix + CHANGELOG ✓

Bereit für Phase-11-Verification (`gsd-verifier`).

## Deviations

Keine. Alle D-04, D-08, D-09, D-10-Decisions umgesetzt. SPEC §7 + §8 erfüllt. Activity-Log-Slot-Kontext ist verpflichtend implementiert (kein Skip-Test).

Anpassung: `real_now`-Fixture für `_evaluate`-Tests dokumentiert die Konflikt-Quelle (HA-`dt_util`-Stub) und löst sie ohne Änderung an `optimizer.py`-Quellcode.
