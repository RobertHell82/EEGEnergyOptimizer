---
phase: 11-dual-window-discharge
verified: 2026-05-04T00:00:00Z
status: human_needed
score: 9/9 SPEC requirements verified, 10/10 CONTEXT decisions verified
overrides_applied: 0
test_results:
  total: 413
  passed: 412
  failed: 1
  failure_kind: pre-existing OOS (telemetry_enabled in step_user, vor Phase 11)
human_verification:
  - test: "7-Tage-UAT-Beobachtung an Test-HA-Instanz (Huawei 192.168.1.211 und/oder Fronius 192.168.100.211)"
    expected: "Slot-A-Aktivierungen 20:00–23:00, Slot-B-Aktivierungen 03:00–07:00, keine NVRAM-Probleme, finale 'gute Idee oder nicht'-Bewertung durch User"
    why_human: "Reale EEG-Bedarfsdaten, reale PV-Schwankung und reale Inverter-Reaktion sind nicht simulierbar. SPEC Acceptance §12."
  - test: "Onboarding-Panel-Visuelle-Verifikation (SolarEdge XOR-Radio + Master-Toggle versteckt + Tooltip 'NVRAM-Verschleiß')"
    expected: "Bei SolarEdge: Master-Toggle versteckt, XOR-Radio mit Default Slot A sichtbar, Tooltip-Text wörtlich. Bei Huawei/Fronius/SolaX: Master-Toggle sichtbar, Slot-A/B-Sub-Karten bei dual=ON."
    why_human: "Visuelle Korrektheit (Tooltip-Position, Radio-Default, Border-Farben) ist Pixel-spezifisch."
  - test: "Settings-Tab `evening` Round-Trip mit `settings_*`-Präfix"
    expected: "Save schreibt settings_*-Werte korrekt zurück; Backend setzt dual_discharge=False auf SolarEdge zusätzlich."
    why_human: "Live-DOM-Interaktion mit WS-Backend ist nur in laufender HA-Instanz beobachtbar."
gaps: []
---

# Phase 11: Dual-Window-Entladung — Verification Report

**Phase Goal:** Der Optimizer unterstützt zwei unabhängig aktivierbare Entladefenster (Slot A abends, Slot B morgens) mit getrennter Pro-Slot-Hysterese und Energie-Budgetierung, sodass EEG-Bedarf in Abend- (~20:00–24:00) und Morgenstunden (~03:00 bis vor Sonnenaufgang) gezielt adressiert wird, ohne den Genauigkeitsgewinn des heutigen späten Single-Window-Starts zu verlieren.
**Verified:** 2026-05-04
**Status:** human_needed (alle automatisierbaren Checks PASS, 7-Tage-UAT + Visual-UI ausstehend)
**Re-verification:** No — initial verification

## Goal Achievement Summary

Phase 11 liefert ein vollständig funktionsfähiges Dual-Window-Entlade-System mit Slot A (Abend) und Slot B (Morgen). Decision-Engine ist refaktoriert (Dispatcher + 4 Slot-Methoden), Pro-Slot-Hysterese ist implementiert, Migration v14→v15 läuft additive `setdefault`-Defaults für Bestands-Entries, und ein 3-Layer Defense-in-depth schließt SolarEdge vom Dual-Mode aus. Test-Suite zeigt 412/413 PASS (das eine Failure ist ein Pre-existing-OOS-Issue im Step-User-Flow ohne Phase-11-Bezug). Manuelle 7-Tage-UAT bleibt als finale Akzeptanz-Hürde offen — wie in SPEC §12 explizit so vorgesehen.

## Per-Requirement Table (SPEC §1..§9)

| # | SPEC-Requirement | Status | Evidence |
|---|------------------|--------|----------|
| 1 | Konfigurations-Schema für Dual-Window (CONF_*-Keys, Defaults, Migration) | PASS | `const.py:115-121` (7 CONF_*-Keys) + `const.py:DEFAULT_DISCHARGE_*` Defaults + `__init__.py:846-874` Migration v14→v15 mit setdefault-Branch für SolarEdge vs. non-SolarEdge. |
| 2 | Slot A — Abend-Entladung mit Energie-Reserve (`_evaluate_slot_a` mit `min_soc + reserve_pct`) | PASS | `optimizer.py:1081 _evaluate_slot_a` definiert + Zeile 1132-1134: `a_reserve = self._discharge_a_reserve_pct if self._enable_slot_b else 0; a_min_soc = min_soc + a_reserve`. A-only-Pfad (B disabled) setzt Reserve=0, A endet exakt bei `min_soc_dyn`. |
| 3 | Slot B — Morgen-Entladung mit adaptivem Ende (`compute_b_window_end` mit min(cap, sunrise−5min)) | PASS | `optimizer.py:compute_b_window_end` als Module-Level-Funktion (3 Treffer); `_evaluate_slot_b:1157` ruft sie auf; 4 SPEC-Test-Cases (Sommer/Winter/Übergang/tiefer Winter) plus morning_offset-Test grün in `tests/test_dual_window.py::TestComputeBWindowEnd` (7 Tests). |
| 4 | Pro-Slot-Hysterese (`_slot_a_activated_date`, `_slot_b_activated_date`) | PASS | `optimizer.py:457-458` Felder definiert, 14 Treffer in optimizer.py (>=4 gefordert); Reset-Logik Zeile 1480-1494 (NUR nach today's Sunrise — T-11-02-01); Aktivierungs-Tracking Zeile 1533-1538. Tests: `TestProSlotHysteresis` (2 Tests) grün. |
| 5 | Mutual Exclusion zur Morgen-Einspeisung (5min-Pause durch `compute_b_window_end`) | PASS | `compute_b_window_end` zieht `sunrise − morning_offset_h − 5min` UND `sunrise − 5min` über `min()` ab. `TestSlotBPreSunriseCutoff` (7 parametrisierte Tests über sunrise×offset) grün; `TestMutualExclusion` (1 Test) bestätigt strikten Übergang. |
| 6 | SolarEdge-Sperre für Dual-Mode (3-Layer Defense-in-depth) | PASS | Layer 1 (Migration): `__init__.py:862-865` SolarEdge-Branch `enable_dual_discharge=False, enable_slot_a=True, enable_slot_b=False`. Layer 2 (Save-Path): `websocket_api.py:432` Logger-Warning + Force auf False, Z. 437 XOR-Konfliktauflösung. Layer 3 (Runtime-Force): `optimizer.py:512-515` `if self._is_solaredge and self._enable_dual_discharge: ... self._enable_dual_discharge = False`. Tests: `TestSolarEdgeXOR` (3) + `TestSolarEdgeRuntimeForce` (1) grün. |
| 7 | Telemetry-Reasons pro Slot (8 neue Keys in ALL_REASONS + REASON_LABELS_DE) | PASS | `optimizer.py:106-113` 8 REASON_*-Konstanten definiert (snake_case = Variablen-Suffix); Z. 139-146 in ALL_REASONS; Z. 173-180 in REASON_LABELS_DE mit echten Umlauten. 35 Treffer im File (>=8 erwartet). Tests: `TestReasonsCatalog` (3 Tests) grün. |
| 8 | Independent Slot-Aktivierung (A-only / B-only / dual) | PASS | Dispatcher `_should_discharge:1228` routet anhand `enable_slot_a`/`enable_slot_b`-Kombination; A-only (B aus) → keine Reserve; B-only → klassische Morgen-Entladung; A+B → Reserve-aware. Tests: `TestDualWindow24hSimulation` (3 Szenarien grün): A-only, B-only, dual. |
| 9 | Inverter-Race-Schutz ≥5min (Save-Path Auto-Korrektur) | PASS | `websocket_api.py:_parse_hhmm:66` + Inverter-Race-Block Z. 507-521: berechnet `a_min_end = a_start + 30min` mit Tagesachsen-Mapping; wenn `b_on_tomorrow < a_on_tomorrow + 5`: `b_start := a_min_end + 5min` mit Logger-Warning ("Dual-Window: b_start %s zu nah an a_start+30min — auf %s angehoben"). Tests: `TestInverterRaceValidation` (5 Tests) grün. |

## Per-Decision Table (D-01..D-10)

| Decision | Status | Evidence |
|----------|--------|----------|
| D-01: 3 Methoden + `_check_common_guards` | PASS | `optimizer.py` definiert: `_check_common_guards:1040`, `_evaluate_slot_a:1081`, `_evaluate_slot_b:1157`, `_evaluate_legacy_window:1286`, `_should_discharge:1228` als Dispatcher (~33 LOC, ruft Common-Guards einmal vorab). |
| D-02: Slot-State als Felder im EEGOptimizer | PASS | `optimizer.py:457-458` `_slot_a_activated_date: str \| None` + `_slot_b_activated_date: str \| None`; konsistent mit bestehendem `_morning_activated_date`/`_discharge_activated_date`. Reset zentral in `_evaluate` Z. 1480-1494. |
| D-03: Migration v14→v15 (KORRIGIERT von SPEC's outdated v12→v13) | PASS | `__init__.py:846 if entry.version < 15:` — Migrations-Block setzt 7 Keys via `setdefault` mit SolarEdge-Branch. `config_flow.py:VERSION = 15` (1 Treffer). Tests: `TestMigrationV14ToV15` (4 Tests) grün, inkl. Idempotenz und User-Value-Preservation. |
| D-04: Default-Wechsel + CHANGELOG mit "Verhaltensänderung beim Update" | PASS | `CHANGELOG.md` enthält Sektion "Verhaltensänderung beim Update" (1 Treffer im Header-Kontext, 6 Treffer auf "Verhaltensänderung" gesamt) plus 13 Treffer auf v1.2.0-dev/Slot A/Slot B/Dual-Window. Negativcheck: 0 Treffer auf ASCII-Substitution (Verhaltensaenderung/verfuegbar/unabhaengig). |
| D-05: Legacy-Pfad bleibt 1:1 erhalten | PASS | `_evaluate_legacy_window:1286` enthält den heutigen Body; Dispatcher routet `(not enable_dual_discharge) OR is_solaredge` → Legacy. Tests: `tests/test_optimizer.py` 86 passed (keine Regression); `TestEnableDualDischargeFalseLegacyPath` (2 Tests) grün. |
| D-06: Inline-Panel-Erweiterung mit Master-Toggle | PASS | `frontend/eeg-optimizer-panel.js`: 40 Treffer auf Phase-11-Config-Keys; 7 data-field-Bindings (enable_dual_discharge, enable_slot_a, enable_slot_b, discharge_a_start_time, discharge_b_start_time, discharge_b_end_cap, discharge_a_reserve_pct) je in Wizard und Settings (Z. 3032+). Slot-A/B-Sub-Karten mit Border-Farben (`--primary-color`/`--accent-color`). |
| D-07: SolarEdge-XOR-Radio | PASS | `frontend/eeg-optimizer-panel.js`: 5 Treffer auf `solaredge_slot`/`NVRAM-Verschleiß` (2 Wizard-Radios + 2 Settings-Radios + 1 Tooltip). Master-Toggle versteckt bei SolarEdge; Default Slot A. Save-Path Radio-Handler vor allgemeinem `data-field`-Handler. |
| D-08: Decision-Card mit Slot-Marker | PASS | `optimizer.py:_build_markdown` Z. 1696-1722: dynamischer Header `### Morgen-Entladung` für Slot B, sonst `### Abend-Entladung`; Slot-Marker `- Aktiver Slot: A`/`B`; Slot-Konfigurations-Sektion sichtbar bei Dual-Mode. Frontend Aktivitäts-Timeline (Z. 4196+) ergänzt " (Slot A)" / " (Slot B)" am Status-Text. Tests: `TestMarkdownRendering` (5 Tests) grün. |
| D-09: Reasons additiv (8 neue Keys) | PASS | `optimizer.py:ALL_REASONS` Z. 139-146 enthält 8 neue Keys additiv neben den bestehenden 22; bestehende Keys (`before_discharge_start`, `hard_cutoff_after_4am` etc.) unverändert. `tests/test_optimizer.py::test_reasons_catalog_is_closed_set` als Closed-Set-Pin-Test grün (mit 30 Keys). |
| D-10: `Decision.discharge_active_slot` durchgereicht | PASS | `optimizer.py` 5 Treffer (Decision-Field, _evaluate setzt ihn aus Reasons-Lookup, Markdown-Renderer); `__init__.py:1303` `"discharge_active_slot": decision.discharge_active_slot` in `_log_activity`-entry_data; `panel.js` 3 Treffer (Aktivitäts-Timeline-Suffix). Legacy-Pfad: `active_slot=None` (D-10 explizit). |

## Test Status

| Suite | Pass | Fail | Δ vs Plan 11-04 |
|-------|------|------|----------------|
| `tests/test_dual_window.py` (Plans 11-01/02/03) | 50 | 0 | unverändert |
| `tests/test_dual_window_integration.py` (Plan 11-04) | 10 | 0 | unverändert |
| `tests/test_optimizer.py` | 86 | 0 | ±0 (D-05 Legacy-Garantie) |
| `tests/test_config_flow.py` | 6 | 1 | OOS-Failure (Pre-existing) |
| `tests/test_telemetry_hooks.py` | grün | 0 | v15-Asserts angepasst |
| **`pytest tests/ -q` Total** | **412** | **1** | finalisiert in 11-04 |

**Pre-existing Failure** (NICHT Phase-11-Bezug):
`tests/test_config_flow.py::TestStepUser::test_creates_entry_on_confirmation` erwartet `data == {"setup_complete": False}`, aber `config_flow.py:async_step_user` setzt zusätzlich `CONF_TELEMETRY_ENABLED: True` (aus Phase 8 Telemetrie). Dieser Test war schon vor Phase 11 rot und ist explizit out-of-scope. Dokumentiert in allen 4 Plan-SUMMARYs.

## Pattern-Check Ergebnisse

| Check | Erwartet | Gemessen | Status |
|-------|----------|----------|--------|
| `compute_b_window_end` in optimizer.py | ≥3 | 3 | PASS |
| `_evaluate_slot_a/b/_legacy_window/_check_common_guards` definiert | ≥4 | 4 distinct (+ 1 Dispatcher) | PASS |
| `_slot_a_activated_date \| _slot_b_activated_date` | ≥4 | 14 | PASS |
| 8 REASON_*-Slot-Keys | 8 | 35 (>=8 unique) | PASS |
| `discharge_active_slot` in optimizer.py | ≥4 | 5 | PASS |
| `discharge_active_slot` in __init__.py (D-09) | ≥1 | 1 (Z. 1303) | PASS |
| `discharge_active_slot` in panel.js | ≥2 | 3 | PASS |
| `if entry.version < 15:` in __init__.py | =1 | 1 (Z. 846) | PASS |
| `VERSION = 15` in config_flow.py | =1 | 1 | PASS |
| `enable_dual_discharge` in const.py | ≥1 | 3 | PASS |
| Save-Path Enforcement (`_parse_hhmm` + 3 Warning-Strings) | ≥4 | 4 (Z. 66, 432, 437, 521) | PASS |
| `Verhaltensänderung beim Update` in CHANGELOG.md | ≥1 | 1 | PASS |
| ASCII-Substitution-Negativcheck (Verhaltensaenderung etc.) | =0 | 0 | PASS |

## Defense-in-depth Verification (D-07, SPEC §6)

| Layer | Stelle | Verifiziert |
|-------|--------|-------------|
| 1 — Migration | `__init__.py:862-865` SolarEdge-Branch in `if entry.version < 15:` | Bestands-SolarEdge-Entry erhält dual=False, slot_a=True, slot_b=False via `setdefault`. Test `test_solaredge_xor_defaults` grün. |
| 2 — Save-Path | `websocket_api.py:432` (`enable_dual_discharge=True nicht erlaubt`), Z. 437 (`nur ein Slot erlaubt`), XOR-Konflikt-Auflösung + 5kW-Clamp im selben SolarEdge-Block | Tests `TestSolarEdgeXOR` (3) grün. |
| 3 — Runtime-Force | `optimizer.py:512-515` re-asserts `enable_dual_discharge=False` falls SolarEdge mit Logger-Warning | Test `test_solaredge_init_forces_dual_to_false` grün. |

## SPEC Acceptance Criteria — Status

- [x] `enable_dual_discharge=False` (explizit gesetzt) — Single-Window-Logik byte-identisch zu v1.1 (D-05, durch tests/test_optimizer.py 86 passed bestätigt)
- [x] Bestands-Entry mit version=14 wird via `_async_migrate_entry` auf version=15 mit korrekten Defaults migriert; SolarEdge-Bestands-Entry erhält XOR-Konfiguration (nur Slot A) — `TestMigrationV14ToV15` (4 Tests) grün
- [x] `enable_slot_a=true, enable_slot_b=true` — Slot A und Slot B liefern in einem 24h-Simulationstest jeweils ≥1 separate Entladephase mit korrekter Slot-Markierung — `TestDualWindow24hSimulation::test_dual_a_and_b_both_activate` grün
- [x] `enable_slot_a=true, enable_slot_b=false` — Verhalten entspricht klassischer Abend-Entladung mit `a_start` als `discharge_start_time`, ohne Reserve-Aufschlag — `TestDualWindow24hSimulation::test_a_only_no_reserve` grün
- [x] `enable_slot_a=false, enable_slot_b=true` — System startet Entladung erst um `b_start`, nutzt klassische `min_soc_dyn`-Schwelle — `TestDualWindow24hSimulation::test_b_only_classic_threshold` grün
- [x] `compute_b_window_end` liefert für 4 Test-Cases (Sommer-SA, Winter-SA, Übergang, tiefer Winter) die in Requirement 3 spezifizierten Werte — `TestComputeBWindowEnd` (7 Tests) grün
- [x] Slot B endet stets ≥5min vor Beginn der Morgen-Einspeisung, validiert über parametrisierten Test über `morning_offset ∈ {0, 1}` × Sunrise-Range — `TestSlotBPreSunriseCutoff` (7 parametrisierte Tests) grün
- [x] Pro-Slot-Hysterese: A-Aktivierung → A-Ende durch Reserve → A-Reaktivierung benötigt SOC > Reserve+5%, B startet später am Tag mit `min_soc_dyn`-Schwelle ohne Aufschlag — `TestProSlotHysteresis` (2 Tests) grün
- [x] SolarEdge-Erzwingung: Config mit `inverter_type=solaredge_storedge, enable_dual_discharge=true` führt zu Logged-Warning und `enable_dual_discharge=false` zur Laufzeit — Save-Path + Runtime-Force-Tests grün
- [ ] **MANUAL** — Onboarding-Panel zeigt Master-Toggle nur wenn `inverter_type ≠ solaredge_storedge`; bei SolarEdge XOR-Radio mit Default Slot A und Tooltip "NVRAM-Verschleiß" — Code vorhanden, Visual-Verifikation ausstehend
- [x] Activity-Log enthält die in Requirement 7 gelisteten neuen Reasons mit korrekter Slot-Zuordnung — `TestActivityLogSlotContext` (2 Tests) grün
- [x] Inverter-Race-Schutz: Konfigurations-Validation lehnt `b_start < a_min_required_end + 5min` ab oder korrigiert automatisch — Auto-Korrektur via `b_start := a_min_end + 5min`; `TestInverterRaceValidation` (5 Tests) grün
- [ ] **MANUAL** — 7-Tage-Beobachtung an mind. einer Test-HA-Instanz (Huawei und/oder Fronius); finale UAT-Entscheidung "gute Idee oder nicht" — PENDING (manual)

## Gaps & Concerns

**Keine Gaps gefunden.** Alle 9 SPEC-Requirements und alle 10 CONTEXT-Decisions sind im Code verifizierbar mit Test-Coverage. Pre-existing OOS-Failure (`test_creates_entry_on_confirmation`) ist explizit dokumentiert und out-of-scope.

**Beobachtungen ohne Auswirkung auf Status:**
1. SPEC §1 spricht von Migration "Version 12→13" (outdated zum Zeitpunkt der Implementation), tatsächlich umgesetzt als v14→v15 wegen zwischenzeitlicher v13/v14-Migrationen. CONTEXT D-03 KORRIGIERT dies explizit, alle SUMMARYs dokumentieren die Anpassung. Keine fachliche Abweichung.
2. Save-Path verwendet Auto-Korrektur statt Hard-Reject (CONTEXT "Claude's Discretion": Inverter-Race-Validation entweder Save-Validierung lehnt ab, oder Auto-Korrektur). Konsistent mit bestehendem SolarEdge-5kW-Clamp-Pattern. SPEC §9 erlaubt beide Verhalten.

## Manual UAT Pending

Zwei manuelle Verifikationsschritte sind per Design Teil der Phase-11-Akzeptanz und können nicht automatisiert werden:

1. **7-Tage-UAT-Beobachtung** an mind. einer Test-HA-Instanz (Huawei 192.168.1.211 oder Fronius 192.168.100.211). Reale EEG-Bedarfsdaten, reale PV-Schwankung und reale Inverter-Reaktion sind nicht simulierbar. Finale "gute Idee oder nicht"-Bewertung durch User.
2. **Visuelle UI-Verifikation** des Onboarding-Panels (SolarEdge XOR-Radio + Tooltip + Master-Toggle-Sichtbarkeit + Slot-A/B-Sub-Karten-Border-Farben + Settings-Tab-Round-Trip).

Beide Punkte sind in `11-VALIDATION.md` Sektion "Manual-Only Verifications" dokumentiert und vorgesehen.

## Next Steps

- **Optional:** `gsd-add-tests` falls weitere Tests nach UAT-Beobachtung gewünscht (z.B. Real-World-Edge-Cases). Aktuell nicht erforderlich.
- **Required (manual):** 7-Tage-UAT durchlaufen lassen, danach UAT-Ergebnis (akzeptiert/verworfen) in CHANGELOG.md final notieren.
- **Required (manual):** Panel-Visualcheck wie in 11-VALIDATION.md beschrieben.
- **Bei UAT-PASS:** `gsd-milestone-audit` für v1.2-Milestone durchführen.
- **Bei UAT-Findings:** `gsd-plan-phase --gaps` für Follow-up-Plans im Rahmen Phase 11 oder neue Phase 11.x.

---

*Verified: 2026-05-04*
*Verifier: Claude (gsd-verifier)*

## VERIFICATION COMPLETE
