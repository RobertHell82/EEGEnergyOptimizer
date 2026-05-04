# Phase 11: Dual-Window-Entladung — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `11-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-04
**Phase:** 11-dual-window-discharge
**Areas discussed:** Refactor-Strategie, Config-Migration & Backwards-Compat, Panel-Layout, Telemetry-Reasons & Backwards-Compat

---

## Refactor-Strategie für `_should_discharge`

| Option | Description | Selected |
|--------|-------------|----------|
| Aufspaltung in 3 Methoden | `_should_discharge` orchestriert; `_evaluate_slot_a`, `_evaluate_slot_b`, `_evaluate_legacy_window` enthalten die jeweilige Logik. Gemeinsame Checks in `_check_common_guards`. | ✓ |
| Eine Funktion, Slot-Pfade via if/else | Minimal-invasiv — bestehende Funktion erweitern um slot_id-Pfad. Funktion wächst auf ~250 LOC. | |
| Strategy-Pattern mit DischargeStrategy-Klassen | `SingleWindowStrategy`, `SlotAStrategy`, `SlotBStrategy` als separate Klassen. Sauberste Trennung, größter Footprint. | |

**User's choice:** Aufspaltung in 3 Methoden (Recommended)
**Notes:** Lesbar, einzeln testbar, klare Verantwortung. Common-Guards verhindern Code-Duplikation der Tomorrow-PV/Watchdog-Logik.

---

## Slot-State-Lokation

| Option | Description | Selected |
|--------|-------------|----------|
| Felder im EEGOptimizer (wie heute) | Konsistent mit `_discharge_activated_date`, `_morning_activated_date`. | ✓ |
| Eigene `SlotState`-Dataclass pro Slot | Sauberer gekapselt, neuer Datentyp für kleines Stück Zustand. | |

**User's choice:** Felder im EEGOptimizer (Recommended)
**Notes:** Konsistenz mit bestehendem Pattern wichtiger als Kapselung für so kleinen Zustand.

---

## Config-Migration & Backwards-Compat

| Option | Description | Selected |
|--------|-------------|----------|
| Config-Entry Version-Bump 12→13, `_async_migrate_entry` setzt alle neuen Keys | Konsistent mit bisherigem Pattern. Atomar beim ersten Restart. | ✓ |
| Defaults beim Lesen, kein Migrate-Step | Kein Boilerplate, aber inkonsistentes Schema. | |
| Migrate-Step nur für enable_dual_discharge=False, neue Keys lazy | Hybrid mit Lazy-Write. | |

**User's choice:** Config-Entry Version-Bump 12→13 (Recommended)
**Notes:** Atomar, idiomatisch, kein Branchcode in der Laufzeit.

---

## Legacy-Pfad-Erhalt

| Option | Description | Selected |
|--------|-------------|----------|
| Bleibt vollständig erhalten | `enable_dual_discharge=False` → Legacy-Window-Logik 1:1 erhalten. | ✓ |
| Bleibt erhalten, mit Deprecation-Warnung im Log | Sanfter Push für User, der bewusst Legacy nutzt. | |
| Phase 11: bleibt; Phase 12+: umbauen | Aufgeschoben. | |

**User's choice:** Bleibt vollständig erhalten (Recommended)
**Notes:** Old code wird nie entfernt; eigene Legacy-Tests decken den Pfad ab.

---

## Panel-Layout für Dual-Konfiguration

| Option | Description | Selected |
|--------|-------------|----------|
| Inline-Erweiterung mit Master-Toggle | Bestehende Sektion + Master-Toggle + Sub-Bereiche bei aktiviert. | ✓ |
| Zwei separate Karten 'Abend-Slot' + 'Morgen-Slot' | Visueller Reset, mehr Migrations-Aufwand in der UI. | |
| Eigener 'Erweitert'-Tab | Master-Toggle hinter extra Tab. | |

**User's choice:** Inline-Erweiterung mit Master-Toggle (Recommended) + WICHTIG: Default für Bestands-Anlagen ist `beide aktiviert` (außer SolarEdge → nur einer, Default Slot A, XOR).
**Notes:** Diese Antwort hat eine SPEC-Änderung getriggert — Default-Wechsel von `enable_dual_discharge=False` zu `True`. SPEC.md Requirement 1 + Constraints + Acceptance Criteria wurden entsprechend aktualisiert. Byte-identische Test-Garantie fällt damit weg, mitigiert durch Pro-Slot-Hysterese und Release-Notes.

---

## SolarEdge-UI-Sperre

| Option | Description | Selected |
|--------|-------------|----------|
| Toggle deaktiviert mit Tooltip 'NVRAM-Verschleiß' | Klar und ehrlich, kein versteckter Modus. | ✓ |
| Toggle versteckt bei SolarEdge | Sauberer Anblick, User wundert sich evtl. über Doku. | |
| Toggle aktiv, mit Warnung beim Speichern | Maximale Freiheit, hohes Risiko. | |

**User's choice:** Toggle deaktiviert mit Tooltip (Recommended) — präzisiert in Folge-Frage zu Radio-Button "Slot A XOR Slot B".

---

## Migration-Risiko-Bestätigung (SPEC-Änderung)

| Option | Description | Selected |
|--------|-------------|----------|
| Ja, Dual als Default ist die richtige Erfahrung | Update bringt direkt Mehrwert. Risiko durch Hysterese mitigiert. Release-Notes erklären. | ✓ |
| Nein, Opt-in mit Banner im Panel | Default Dual=False, Banner nach Update. | |
| Hybrid: opt-in für Bestands, opt-out für neu | Asymmetrisch, schwer zu kommunizieren. | |

**User's choice:** Ja, Dual als Default (Recommended)
**Notes:** Bewusste Inkaufnahme der Verhaltensänderung beim Update. SPEC + Release-Notes-Pflicht.

---

## SolarEdge-XOR-Logik

| Option | Description | Selected |
|--------|-------------|----------|
| Radio-Button: 'Abend' XOR 'Morgen', Default Abend | XOR-Auswahl, Default Slot A. `enable_dual_discharge` existiert auf SolarEdge nicht. | ✓ |
| Beide Toggles getrennt, mit Validierung | Standard-UI mit Save-Validierung. Mehr Fehlerquellen. | |
| Single-Window bleibt der einzige Modus | Auf altes Verhalten festnageln, kein Slot-A/B-UI. | |

**User's choice:** Radio-Button XOR (Recommended)
**Notes:** Default Slot A weil Abend-Bedarf typisch höher als Morgen-Bedarf in EEG-Communities; User kann auf Morgen umschalten wenn er das will.

---

## Telemetry-Reasons-Strategie

| Option | Description | Selected |
|--------|-------------|----------|
| Neue Reasons additiv, alte bleiben | `before_discharge_start` etc. bleiben für Single-Window-Pfad; neue Reasons kommen hinzu. | ✓ |
| Alte Reasons umbenennen auf Slot-Präfix | Schemabruch ab v1.2 in der DB. | |
| Doppelt: alte Reasons + Slot-Suffix neu | Maximale Backward-Compat, Code-Duplikation. | |

**User's choice:** Neue Reasons additiv (Recommended)
**Notes:** Backend-Schema-Erweiterung erforderlich, aber bestehende Events bleiben gültig.

---

## Claude's Discretion

Der User hat folgende Bereiche bewusst dem Planner überlassen:
- Inverter-Race-Validation (Save-Fehler vs. Auto-Korrektur)
- Test-Layout (eine Datei vs. mehrere)
- PeakShare-Cache-Schema-Migration
- Translation-Strings (analog zu bestehenden Mustern)

## Deferred Ideas

- Slot M (Mid-Night-Polling) — Backlog v1.3+
- Demand-weighted Energie-Aufteilung — Backlog v1.3+
- Slot-individuelle PeakShare-Communities — Backlog v1.3+
- Slot-spezifische Inverter-Rate-Limits — Backlog
- Auto-Berechnung `discharge_a_reserve_pct` aus Historie — Backlog
- Single-Window als Slot-A-only-Modus reimplementieren + Legacy entfernen — späte Phase nach 6+ Monaten Dual-Stabilität
