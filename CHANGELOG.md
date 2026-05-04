# Changelog

Alle nennenswerten Änderungen am EEG Energy Optimizer.

Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [SemVer](https://semver.org/lang/de/).

> Hinweis: DEV-Repo nutzt Patch-Versionen (1.x.y); Release-Versionen werden im Release-Repo getaggt.

## [1.2.0-dev] - 2026-05-04

> User selbst macht Releases — dieser Eintrag ist DEV-Repo-only und wird beim Release-Sync übernommen.

### Verhaltensänderung beim Update

Mit Phase 11 wird die **Dual-Window-Entladung** zum Standard für alle Wechselrichter außer SolarEdge. Bestands-Anlagen werden beim Update automatisch auf das neue Modell migriert (Config-Entry-Version-Bump v14 → v15).

**Was sich ändert:**
- Die Abend-Entladung läuft nun in **zwei unabhängigen Slots** statt einem einzigen Fenster:
  - **Slot A — Abend** (Default 20:00 bis 5min vor Slot-B-Start): Adressiert den EEG-Abendpeak (18:00–23:00).
  - **Slot B — Morgen** (Default 03:00 bis spätestens 07:00 oder Sonnenaufgang−5min): Adressiert den EEG-Morgenpeak und die Wintermorgen, wenn der Bedarf der Energiegemeinschaft hoch ist und PV noch nicht trägt.
- **Pro-Slot-Hysterese:** Slot A und Slot B haben jeweils unabhängige Reaktivierungs-Schwellen (+5% SOC bei Reaktivierung), damit oszillierendes Ein/Aus vermieden wird.
- **Energie-Reserve:** Slot A endet bei `min_soc + 15%` (Default), damit Slot B genug Energie übrig hat. Bei Slot-A-only oder Slot-B-only entfällt der Aufschlag, das jeweilige Fenster nutzt die volle Restkapazität.

**Mitigation gegen unerwünschtes Entladen:**
- Pro-Slot-Hysterese verhindert oszillierende Aktivierung.
- PV-Tomorrow-Garantie: Beide Slots prüfen weiterhin, dass die PV-Prognose für morgen den Bedarf inklusive Sicherheitspuffer deckt; sonst wird nicht entladen.
- Konfiguration jederzeit umstellbar: Im Onboarding-Panel → Einstellungen → Abend-Entladung kann jeder User die `Dual-Window-Entladung` deaktivieren und auf das alte Single-Window-Verhalten zurückkehren — der Legacy-Code-Pfad bleibt 1:1 erhalten und ist durch eigene Tests abgedeckt.

**SolarEdge-Sonderfall:**
SolarEdge-Wechselrichter schreiben Entlade-Kommandos in NVRAM-Speicher mit begrenzten Schreibzyklen. Daher ist Dual-Window auf SolarEdge **nicht verfügbar**. Stattdessen gibt es ein Radio-Auswahl-Feld "Slot A — Abend (Default) | Slot B — Morgen" im Panel; pro Tag läuft genau einer der beiden Slots. Dies ist dreifach abgesichert (Defense-in-depth): Migration setzt den Default, der Save-Path normalisiert die Konfiguration, und der Optimizer erzwingt das Verhalten zur Laufzeit.

### Added
- **Dual-Window-Entladung** mit Slot A (Abend) und Slot B (Morgen) — neue Konfigurationskeys `enable_dual_discharge`, `enable_slot_a`, `enable_slot_b`, `discharge_a_start_time`, `discharge_b_start_time`, `discharge_b_end_cap`, `discharge_a_reserve_pct`.
- Funktion `compute_b_window_end()` für adaptives Slot-B-Ende vor Sonnenaufgang. Schneidet automatisch auf `min(b_end_cap, sunrise − 5min)`, sodass Slot B niemals in die Morgen-Einspeisungs-Phase überlappt.
- Acht neue Telemetrie-Reasons für Slot-Phasen: `before_slot_a`, `slot_a_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_active`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`. Additiv zur Phase-8-Reasons-Liste, kein Schemabruch.
- `Decision.discharge_active_slot`-Feld (Werte "A", "B" oder None) für slotunabhängige Statusanzeige.
- Activity-Log-Feld `discharge_active_slot` für Slot-Kontext im Aktivitätsverlauf (D-09). Sichtbar im HA-Dashboard und im `eeg_optimizer_activity`-Bus-Event.
- SolarEdge-XOR-Radio im Onboarding-Panel mit Tooltip-Erklärung "NVRAM-Verschleiß: nur ein Slot pro Tag möglich".
- Markdown-Sektion "Slot-Konfiguration" im Decision-Sensor zeigt aktuelle Slot-A/Slot-B-Werte.
- Frontend-Aktivitäts-Timeline zeigt Slot-Suffix "(Slot A)" / "(Slot B)" bei Abend-Entladung-Einträgen.

### Changed
- **Default-Verhalten:** Bestands-Anlagen erhalten beim Update Dual-Window automatisch (Config v14 → v15). SolarEdge-Bestände bekommen Slot-A-only (XOR-Konfiguration). Siehe "Verhaltensänderung beim Update" oben.
- `_should_discharge` ist nun ein Dispatcher mit drei Pfaden (`_evaluate_legacy_window` / `_evaluate_slot_a` / `_evaluate_slot_b`); gemeinsame Guards in `_check_common_guards`. Legacy-Pfad bleibt byte-identisch erhalten für Setups mit `enable_dual_discharge=False`.
- PeakShare-Cache `_discharge_plan` ist nun ein slot-indiziertes Dict (`{"a": ..., "b": ...}`) statt single tuple. Alte Cache-Form wird beim Update verworfen und neu berechnet — keine Migration nötig, da Cache-Inhalte ohnehin täglich neu berechnet werden.
- WebSocket-Save-Path validiert SolarEdge-XOR und Inverter-Race (`b_start ≥ a_start + 30min + 5min`) mit Auto-Korrektur statt Hard-Reject. Konsistent mit dem bestehenden SolarEdge-5kW-Clamp-Pattern.
- Onboarding-Panel: Discharge-Sektion (Wizard Schritt 4 + Settings-Tab "Abend-Entladung") um Master-Toggle und Slot-A/Slot-B-Sub-Karten erweitert.

### Migration
- Config-Entry-Version: 14 → 15.
- Migration ist additiv: bestehende User-Werte bleiben erhalten (`setdefault`).
- Nicht-SolarEdge-Bestände: `enable_dual_discharge=True`, `enable_slot_a=True`, `enable_slot_b=True`, Defaults für die neuen Zeit-/Reserve-Keys.
- SolarEdge-Bestände: `enable_dual_discharge=False`, `enable_slot_a=True`, `enable_slot_b=False` (XOR-Default Slot A).

### Tests
- Neue Test-Datei `tests/test_dual_window.py` (Plan 11-01 + 11-02 + 11-03) mit ~50 Tests in 12 Klassen, deckt `compute_b_window_end`, Reasons-Catalog, Migration v14→v15, Slot-A/B-Logik, Pro-Slot-Hysterese, Mutual Exclusion, SolarEdge-Runtime-Force, PeakShare-Cache-Schema, 24h-Simulation, SolarEdge-XOR-Save-Path und Inverter-Race-Validation ab.
- Neue Test-Datei `tests/test_dual_window_integration.py` (Plan 11-04) mit 10 Tests in 3 Klassen für Markdown-Rendering, _evaluate-Slot-Marker-Persistenz und Activity-Log-Slot-Kontext.

### Manual UAT
Final-UAT ist eine 7-Tage-Beobachtung an mindestens einer Test-HA-Instanz (Huawei und/oder Fronius). User entscheidet "gute Idee oder nicht" auf Basis realer EEG-Bedarfsdaten und Inverter-Reaktion. Siehe `.planning/milestones/v1.2-phases/11-dual-window-discharge/11-VALIDATION.md`.

## [1.1.3] - 2026-04-16

Vorletzter Release vor Phase-11. Details siehe Git-Tag `v1.1.3` und Quick-Tasks im DEV-Repo.

## [1.1.2] - 2026-04-15

Details siehe Git-Tag `v1.1.2`.
