# Plan 11-03 — Panel-UI + websocket_api Save-Path-Validation — Summary

**Phase:** 11 — Dual-Window-Entladung
**Wave:** 3 (parallel zu 11-04, files-disjunkt)
**Status:** Complete
**Tasks:** 2/2
**Date:** 2026-05-04

## Was geliefert wurde

### Task 1 — Backend (websocket_api.py + Tests)

Defense-in-depth Layer 2 für die SolarEdge-XOR-Regel und Inverter-Race-Schutz im Save-Path.

**Files modified:**
- `custom_components/eeg_energy_optimizer/websocket_api.py`
- `tests/test_dual_window.py` (Tests)

**Concrete changes:**

1. **`_parse_hhmm(s: str) -> int`** als Modul-Helper (nach `_LOGGER`-Definition). Akzeptiert "HH:MM" und liefert Minuten seit Mitternacht. Wirft `ValueError` bei malformed Input.

2. **SolarEdge-XOR im `ws_save_config`-SolarEdge-Block** (nach 5kW-Clamp, gleicher `if`-Block):
   - `enable_dual_discharge=True` → False mit `_LOGGER.warning("SolarEdge: enable_dual_discharge=True nicht erlaubt — auf False gesetzt")`
   - Beide Slots an → Slot B aus (`_LOGGER.warning("SolarEdge: nur ein Slot erlaubt — Slot A bevorzugt")`)
   - Beide Slots aus → Slot A an (Fallback)

3. **Inverter-Race-Auto-Korrektur** als separater Block VOR `async_update_entry` (nur bei `enable_dual_discharge AND slot_a AND slot_b`):
   - Berechne `a_min_end = a_start + 30min`, `a_on_tomorrow` mit Tagesachsen-Mapping
   - Wenn `b_on_tomorrow < a_on_tomorrow + 5`: `b_start := a_min_end + 5min` mit Logger-Warning
   - Default-Konfig (a=20:00, b=03:00) bleibt unverändert
   - Konsistent mit existierendem SolarEdge-5kW-Clamp-Pattern (Auto-Korrektur, nicht Hard-Reject)

**Tests** (in `tests/test_dual_window.py`, neue Klassen `TestSolarEdgeXOR` + `TestInverterRaceValidation`):
- `test_save_config_solaredge_disables_dual` — SolarEdge + dual=True → False
- `test_save_config_solaredge_two_slots_falls_back_a` — beide Slots an → Slot B aus
- `test_save_config_solaredge_no_slot_falls_back_to_a` — beide Slots aus → Slot A an
- `test_b_start_too_close_auto_bumped` — a=20:00 + b=20:25 → b=20:35
- `test_default_dual_config_no_correction` — a=20:00 + b=03:00 → unverändert
- `test_only_one_slot_active_skips_race_check` — nur Slot A aktiv, b=20:25 bleibt
- `test_parse_hhmm_basic` — 4 Beispiele
- `test_parse_hhmm_raises_on_malformed` — "invalid" wirft ValueError

**Test-Pattern:** `_call_ws(handler, hass, conn, msg)` extrahiert die innere Coroutine via `getattr(handler, "_func", handler)` (HA-WS-Decorator-Bypass). `_ws_hass(entry_data)` baut MagicMock + SimpleNamespace-Entry. Schema nutzt `msg["config"]` (nicht `msg["data"]`).

**Commit:** `15630ba` feat(11-03): add SolarEdge-XOR enforcement + inverter-race auto-correction in ws_save_config

### Task 2 — Panel-UI (Wizard + Settings + Radio-Save-Pfad)

**Files modified:**
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js`

**Concrete changes:**

1. **`WIZARD_DEFAULTS`** (Z. 102+) erhält 7 neue Keys mit den Defaults aus `const.py`:
   - `enable_dual_discharge: true`, `enable_slot_a: true`, `enable_slot_b: true`
   - `discharge_a_start_time: "20:00"`, `discharge_b_start_time: "03:00"`, `discharge_b_end_cap: "07:00"`
   - `discharge_a_reserve_pct: 15`

2. **Wizard Step 4 (`_renderStep4`):** vier neue Template-Variablen vor `dischargeFields`:
   - `dualMasterToggle` — Master-Toggle (versteckt bei SolarEdge)
   - `solarEdgeXorRadio` — Radio-Button-Block mit Tooltip "NVRAM-Verschleiß: nur ein Slot pro Tag möglich" und 2 Optionen "Slot A — Abend (Default)" / "Slot B — Morgen"
   - `slotAFields` — Sub-Karte mit `--primary-color`-Border, Toggle + a_start_time + a_reserve_pct
   - `slotBFields` — Sub-Karte mit `--accent-color`-Border, Toggle + b_start_time + b_end_cap
   - Beide Sub-Karten sichtbar bei `dualOn && !isSolarEdge`
   - Eingebettet im bestehenden `dischargeFields` vor dem PeakShare-Toggle

3. **Settings-Tab `evening` (`_renderSettings` evening-section):** spiegelt Wizard 1:1 mit `settings_*`-Präfix für alle `data-field`-Attribute. Eigene Variablen `settingsDualMasterToggle`, `settingsSolarEdgeXorRadio`, `settingsSlotAFields`, `settingsSlotBFields`. Liest aus `d` (= `this._settingsData`).

4. **Save-Path JS — Radio-Handler im `change`-Listener** (Z. 841+, vor dem allgemeinen `data-field`-Handler):
   - Sucht `[data-field-radio]` im Event-Target
   - Map auf `enable_slot_a/_b` Bool-Paar; `enable_dual_discharge=false` mitgesetzt
   - Funktioniert für Wizard (`_wizardData`) und Settings (`_settingsData`-Präfix `settings_`)

5. **UI-Strings:** alle neuen Labels/Tooltips/Help-Texte mit echten Umlauten (ä/ö/ü/ß). Verifiziert via grep:
   - `Verschleiss\|verfuegbar\|unabhaengig` → 0 Treffer (negative)
   - `Sonnenaufgang` → 14 Treffer (positive, viele aus Bestandscode plus neue Slot-B-Hilfetexte)
   - `NVRAM-Verschleiß` → 1 Treffer (Tooltip-Text)

**Acceptance-Criteria-Greps (alle erfüllt):**
- `data-field="enable_dual_discharge"` → 1 (Wizard) ✓
- `data-field="settings_enable_dual_discharge"` → 1 (Settings) ✓
- `data-field="discharge_a_start_time"` → 1 ✓
- `data-field="discharge_b_start_time"` → 1 ✓
- `data-field="discharge_b_end_cap"` → 1 ✓
- `data-field="discharge_a_reserve_pct"` → 1 ✓
- `name="solaredge_slot"` → 4 (Wizard 2 Radios + Settings 2 Radios) ✓ (≥2 gefordert)
- `Slot A — Abend` → 2 (Wizard + Settings) ✓
- `Slot B — Morgen` → 2 ✓

**Commit:** `5b16e63` feat(11-03): add dual-window panel UI in wizard + settings + SolarEdge XOR radio

## Test-Status

| Suite | Pass | Fail | Notes |
|-------|------|------|-------|
| `tests/test_dual_window.py::TestSolarEdgeXOR` | 3 | 0 | neu |
| `tests/test_dual_window.py::TestInverterRaceValidation` | 5 | 0 | neu (3 async + 2 sync) |
| `tests/` (Gesamt) | 402 | 1 | OOS-Failure `test_creates_entry_on_confirmation` unverändert |

## Manual UAT (7-Tage, siehe 11-VALIDATION.md)

Visuelle Verifikation gehört in die Manual-Only-Sektion:
1. SolarEdge-Setup im Wizard: Master-Toggle versteckt, XOR-Radio mit Default Slot A sichtbar, Tooltip "NVRAM-Verschleiß"
2. Huawei/Fronius/SolaX-Setup: Master-Toggle sichtbar; bei aktiviert Slot-A- und Slot-B-Sub-Karten mit korrekter Border-Farbe
3. Settings-Tab `evening`: Spiegelt Wizard-Layout 1:1; Save schreibt `settings_*`-Werte korrekt zurück
4. Radio-Klick auf SolarEdge: enable_slot_a/_b werden korrekt exklusiv gesetzt; Backend setzt dual_discharge=false zusätzlich

## Defense-in-depth-Übersicht (SolarEdge-XOR)

| Layer | Stelle | Was passiert |
|-------|--------|--------------|
| 1 — Migration | `__init__.py:async_migrate_entry v14→v15` (Plan 11-01) | Bestands-SolarEdge-Entry: dual=False, slot_a=True, slot_b=False |
| 2 — Save-Path | `websocket_api.ws_save_config` (DIESER PLAN) | dual=True → False; XOR-Konflikt-Auflösung; leere Konfig → A-Fallback |
| 3 — Runtime-Force | `EEGOptimizer.__init__` (Plan 11-02) | Erzwingt zur Laufzeit XOR auch wenn Save-Path umgangen wurde |

## Bereit für 11-04

11-04 (parallel-möglich) ergänzt:
- Markdown-Renderer für Slot-A/B-Status
- Activity-Log-Slot-Kontext
- 24h-Decision-Sequenz-Test
- CHANGELOG-Eintrag mit "Verhaltensänderung beim Update"-Sektion

Wave-3-Files sind disjunkt (`tests/test_dual_window.py` für 11-03 vs `tests/test_dual_window_integration.py` für 11-04; beide editieren `frontend/eeg-optimizer-panel.js` an unterschiedlichen Stellen).

## Deviations

Keine. Alle D-06/D-07 Decisions umgesetzt. Auto-Korrektur (statt Hard-Reject) folgt der RESEARCH.md-Empfehlung und ist konsistent mit dem bestehenden SolarEdge-5kW-Clamp-Pattern.
