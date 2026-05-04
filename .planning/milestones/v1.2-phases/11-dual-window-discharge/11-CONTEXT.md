# Phase 11: Dual-Window-Entladung — Context

**Gathered:** 2026-05-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Implementierung der in `11-SPEC.md` gesperrten Dual-Window-Entladelogik im EEG Energy Optimizer. Refactor von `optimizer.py:_should_discharge` für zwei unabhängige Slots, Konfigurations- und Migrations-Layer, Onboarding-Panel-Erweiterung, Telemetrie-Reasons additiv, SolarEdge-XOR-Sonderfall.

Diese Phase liefert keine neuen Optimierungs-Konzepte (Slot M, demand-weighted Aufteilung, slot-spezifische PeakShare-Communities) — die sind explizit in v1.3+ verschoben.

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**9 requirements are locked.** See `11-SPEC.md` für vollständige Requirements, Boundaries und Acceptance Criteria.

Downstream-Agents (Researcher, Planner) MÜSSEN `11-SPEC.md` vor Planung/Umsetzung lesen. Requirements werden hier nicht dupliziert.

**In scope (aus SPEC.md):**
- Dual-Window-Optimizer-Decision-Engine (`optimizer.py:_should_discharge` Refactor)
- Pro-Slot-Hysterese
- Konfigurations-Schema-Erweiterung + Config-Entry-Migration
- Adaptives B-Ende mit `compute_b_window_end`
- Mutual-Exclusion-Garantie zur Morgen-Einspeisung
- SolarEdge-XOR-Sperre (Lauflzeit + Panel)
- PeakShare-Integration für Dual-Mode
- Telemetry-Reasons additiv für Slot-Phasen
- Panel-Erweiterung
- Unit-Tests

**Out of scope (aus SPEC.md):**
- Slot M / Mid-Night-Polling — Backlog v1.3+
- Slot-individuelle PeakShare-Communities
- Demand-weighted Energie-Aufteilung
- Quantitative Wirkungsanalyse via Telemetrie
- Backwards-Migration alter `discharge_start_time` zu Dual-Konfiguration

</spec_lock>

<decisions>
## Implementation Decisions

### Refactor-Strategie
- **D-01:** `_should_discharge` wird in 3 Methoden aufgespalten: `_evaluate_slot_a`, `_evaluate_slot_b`, `_evaluate_legacy_window` (Single-Window). Eine private `_check_common_guards` kapselt die slot-übergreifenden Checks (Tomorrow-PV-Surplus, SOC-Sensor-Verfügbarkeit, Discharge-Aborted-Watchdog für SolarEdge). Die orchestrierende `_should_discharge`-Methode wählt anhand `enable_dual_discharge` + `inverter_type` den richtigen Pfad und ruft Common-Guards einmal vorab auf.
- **D-02:** Slot-State bleibt als Felder im `EEGOptimizer`-Objekt (`_slot_a_activated_date`, `_slot_b_activated_date`) — konsistent mit `_morning_activated_date`, `_discharge_activated_date`. Reset-Logik im `_evaluate`-Pfad zentral; pro Slot eigener Reset-Trigger (Slot A nach Sunrise, Slot B nach Sunrise des Folgetags).

### Migration & Backwards-Compat
- **D-03:** Config-Entry-Version-Bump von 12 auf 13. `_async_migrate_entry` in `__init__.py` ergänzt für jeden Bestands-Entry die neuen Keys mit Defaults: `enable_dual_discharge=True, enable_slot_a=True, enable_slot_b=True, discharge_a_start_time="20:00", discharge_b_start_time="03:00", discharge_b_end_cap="07:00", discharge_a_reserve_pct=15`. SolarEdge-Sonderfall: `enable_dual_discharge=False, enable_slot_a=True, enable_slot_b=False`.
- **D-04:** **Default-Wechsel ist intendiert.** Bestands-Anlagen erhalten Dual-Window automatisch beim Update — KEINE byte-identische Verhaltensgarantie mehr. Mitigation: Pro-Slot-Hysterese und PV-Tomorrow-Garantie verhindern aggressive Erstaktivierung. CHANGELOG und Release-Notes müssen den Default-Wechsel prominent erklären (eigener Abschnitt "Verhaltensänderung beim Update").
- **D-05:** Single-Window-Pfad (Legacy) bleibt vollständig erhalten und funktional für Setups mit explizit gesetztem `enable_dual_discharge=False`. Code wird nicht entfernt; eigene Tests decken den Legacy-Pfad ab. Spätere Phase könnte Single-Window als spezialisierten Slot-A-only-Modus reimplementieren — nicht in Phase 11.

### Panel-Layout
- **D-06:** Inline-Erweiterung der bestehenden Discharge-Sektion im Onboarding-Panel (`frontend/eeg-optimizer-panel.js`). Master-Toggle `enable_dual_discharge` oben in der Sektion. Bei aktiviert: zwei Sub-Bereiche "Slot A — Abend" und "Slot B — Morgen" mit jeweils eigenen Toggles + Zeit-/Reserve-Feldern werden eingeblendet. Bei deaktiviert: Legacy-Felder (`discharge_start_time`) bleiben sichtbar.
- **D-07:** SolarEdge-Sonderfall: Master-Toggle `enable_dual_discharge` ist deaktiviert/versteckt. Stattdessen Radio-Button "Welcher Slot soll laufen?" mit Optionen "Slot A — Abend (Default)" und "Slot B — Morgen". Wechsel zwischen den Optionen schaltet `enable_slot_a`/`enable_slot_b` exklusiv um. Tooltip am Radio-Container: "SolarEdge nutzt NVRAM für Entlade-Kommandos — nur ein Slot pro Tag möglich, um den Schreibzyklen-Verschleiß zu begrenzen".
- **D-08:** Status-Anzeige (Decision-Card) im Live-Dashboard zeigt `discharge_active_slot: A | B | None` als visuelle Markierung am aktiven Fenster, plus separate Anzeige der Slot-A-/Slot-B-Status (deaktiviert / wartend / aktiv / abgeschlossen).

### Telemetry & Reasons
- **D-09:** Neue Reasons additiv. Bestehende Keys (`before_discharge_start`, `hard_cutoff_after_4am`, `peakshare_before_window` etc.) bleiben in `ALL_REASONS` und werden vom Single-Window-Pfad weiter genutzt. Neue Keys für Dual-Pfad: `before_slot_a`, `slot_a_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_active`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`. Backend-Schema (eeg-telemetry-backend D1) muss erweitert werden — bestehende State-Change-Events bleiben gültig, neue Events kommen dazu. Keine Breaking-Change in v1.1-Telemetrie-Verträgen.
- **D-10:** `Decision`-Dataclass erhält neues Feld `discharge_active_slot: Literal["A", "B"] | None` (default None für Legacy + Pause-Phasen). Sensor "Entscheidung" (#18) reicht den Wert in den Markdown-Status durch; WebSocket-API liefert ihn unverändert.

### Claude's Discretion
Folgende Punkte wurden bewusst nicht im Detail festgelegt — der Planner trifft sie basierend auf bestehenden Code-Conventions:
- **Inverter-Race-Validation** (b_start vs erwartetes Slot-A-Ende): Entweder Save-Validierung lehnt ab, oder Auto-Korrektur (b_start += 5min). Entscheidung in PLAN.md auf Basis bestehender Validation-Patterns im Config-Flow.
- **Test-Layout**: Erweiterung von `tests/test_optimizer.py` vs. neue Datei `tests/test_dual_window.py`. Planner orientiert sich an Größe und Komplexität der neuen Tests.
- **PeakShare-Cache-Schema**: Migration `_discharge_plan: tuple` → `dict[Literal["a","b"], tuple]`. Planner trifft Schema-Entscheidung; Cache-Invalidation bei Datums-Wechsel bleibt gleich.
- **Translations-Strings**: Deutsche/englische Strings für neue Reasons und Panel-Labels — Planner generiert konsistent zu bestehenden `strings.json`/`translations/de.json`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream-Agents MÜSSEN diese vor Planung/Umsetzung lesen.**

### Phase 11 Spezifikation
- `.planning/milestones/v1.2-phases/11-dual-window-discharge/11-SPEC.md` — **Locked Requirements** (9 Stück), Boundaries, Acceptance Criteria. MUSS gelesen werden vor jedem Implementierungs-Schritt.

### v1.0 / v1.1 — relevanter Kontext
- `.planning/milestones/v1.0-phases/03-optimizer-safety-system/03-CONTEXT.md` — Ursprungs-Entscheidungen zur Single-Window-Logik (Hysterese-Pattern, min_soc-Berechnung, Mutex-Reihenfolge in `_evaluate`).
- `.planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md` — Telemetrie-Schema mit `reasons`/`blocked_by` snake_case-Keys (D-09 dort). Neue Slot-Reasons müssen konsistent mit diesem Schema sein.
- `.planning/milestones/v1.1-telemetry-ROADMAP.md` — Backend-Endpoints (`/v1/state-change`), an die neue Reasons gesendet werden.

### Code-Anker
- `custom_components/eeg_energy_optimizer/optimizer.py:175` — `compute_hard_cutoff` (zu erweitern um `compute_b_window_end`)
- `custom_components/eeg_energy_optimizer/optimizer.py:905` — `_should_discharge` (Refactor-Ziel)
- `custom_components/eeg_energy_optimizer/optimizer.py:370` — Hysterese-Felder (zu duplizieren pro Slot)
- `custom_components/eeg_energy_optimizer/peakshare.py:295` — `get_discharge_plan` (Cache-Schema-Migration)
- `custom_components/eeg_energy_optimizer/__init__.py` — `_async_migrate_entry` (Version 12→13 ergänzen)
- `custom_components/eeg_energy_optimizer/inverter/solaredge.py` — Inverter-Type-Detection für XOR-Sperre
- `custom_components/eeg_energy_optimizer/sensor.py` (#17 Register-Writes, #18 Entscheidung) — Telemetrie-Konsumenten
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` — Discharge-Sektion erweitern
- `custom_components/eeg_energy_optimizer/strings.json`, `translations/de.json`, `translations/en.json` — neue UI-Strings

### Konventionen
- `CLAUDE.md` (Projekt-Root) — Architektur-Übersicht, 30-Sekunden-Cycle, Config-Entry-Version aktuell 12.
- Memory-File `feedback_umlaute.md` — UI-Strings nutzen echte Umlaute (ä/ö/ü), keine ASCII-Substitution.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `compute_hard_cutoff` (`optimizer.py:175`): Anchor-an-Sunrise-Day-Logik kann als Vorlage für `compute_b_window_end` dienen — gleiches Anchoring, neue Cap-Quelle.
- `_async_migrate_entry`-Pattern in `__init__.py`: Bestehende Migrations 11→12 (oder ältere) zeigen das Schema; Version 13 wird analog ergänzt.
- `Decision`-Dataclass (`optimizer.py:248`) ist bereits modular aufgebaut mit `discharge_*`-Feldern — neue Slot-Felder fügen sich ein.
- `peakshare.find_discharge_window` ist parametrisierbar mit `window_start`/`window_end` — kann pro Slot mit unterschiedlichen Grenzen aufgerufen werden, ohne Algorithmus-Änderung.

### Established Patterns
- **Hysterese als Datums-Feld**: `_morning_activated_date`, `_discharge_activated_date` mit Reset zentral in `_evaluate`. Slot-Hysterese-Felder folgen dem gleichen Muster.
- **SolarEdge-Sonderfall via `is_solaredge`-Flag**: bereits in `optimizer.py:384` etabliert (5-kW-Mindest-Power, Grid-Import-Watchdog). XOR-Logik nutzt das gleiche Flag.
- **Reasons als snake_case-Keys in `ALL_REASONS`**: Phase 8 hat das Pattern gesetzt; Erweiterung ist additiv.
- **Config-Reads via `config.get(KEY, DEFAULT)`**: Alle Defaults auch ohne Migrate-Step lesbar — Migrate-Step persistiert sie nur ins Storage.

### Integration Points
- **Optimizer-Cycle (30s)** in `__init__.py:async_setup_entry`: Decision-Engine wird unverändert aufgerufen — Schnittstelle bleibt `Decision`-Objekt.
- **WebSocket-API** in `websocket_api.py`: 17 bestehende Commands, keine neue benötigt — Konfig-Felder fließen über bestehenden `save_config`/`get_config`.
- **Sensor "Entscheidung" (#18)**: konsumiert `Decision.markdown` — neue Slot-Felder im Markdown rendern.
- **Telemetry-Reporter** (eeg-telemetry-backend, separates Repo): Schema-Update D1 erforderlich — Hinweis im PR-Body, dass Backend-Migration parallel vorbereitet werden muss.

</code_context>

<specifics>
## Specific Ideas

- **Default `discharge_b_end_cap = "07:00"`** wurde aus EEG-Bedarfs-Beobachtung des Users abgeleitet ("EEG hat bis 07:00 sicher Bedarf, sogar bis 08:30") — Default deckt Wintermaximum ab; SA-Adaption schneidet im Sommer automatisch.
- **Default `discharge_a_start = "20:00"`** orientiert sich am EEG-Abendpeak 18:00–23:00; früherer Start wäre wertvoller, würde aber `discharge_a_reserve_pct` realistisch hoch treiben.
- **`discharge_a_reserve_pct = 15`** ist eine Schätzung für 10-kWh-Batterien mit 5-kW-Discharge; Empirie könnte den Default in v1.3+ adjustieren.
- **7-Tage-User-UAT** als finale Akzeptanz: User beobachtet selbst an seinen Test-HA-Instanzen (Huawei 192.168.1.211, Fronius 192.168.100.211) und entscheidet "gute Idee" oder nicht. Kein quantitativer Schwellwert.

</specifics>

<deferred>
## Deferred Ideas

- **"Slot M" — Mid-Night-Polling** zwischen A-Ende und B-Start für nicht-prognostizierten Restbedarf. Erhöht Phase-11-Komplexität deutlich. Backlog v1.3+.
- **Demand-weighted Energie-Aufteilung** zwischen Slot A und B basierend auf integrierter EEG-Bedarfskurve (PeakShare). Intelligenter als statische Reserve, aber erfordert PeakShare-Daten für beide Slot-Zeiträume in stabiler Form. Backlog v1.3+.
- **Slot-individuelle PeakShare-Communities** — heute teilen A und B sich eine Community. Sinnvoll wenn Abend- und Morgen-EEG-Bedarf in unterschiedlichen Communities relevanter sind. Backlog v1.3+.
- **Slot-spezifische Inverter-Rate-Limits** über die SolarEdge-Sperre hinaus. Z.B. SolaX-Mindestdauer pro Slot. Aktuell keine Empirie verfügbar — Backlog.
- **Auto-Berechnung von `discharge_a_reserve_pct`** aus historischen Verbrauchswerten (statt fixem Default). Erst nach Real-World-Daten aus 7-Tage-UAT entscheidbar. Backlog.
- **Spätere Phase: Single-Window als spezialisierten Slot-A-only-Modus reimplementieren** und Legacy-Pfad entfernen. Erst sinnvoll wenn Dual-Window 6+ Monate stabil läuft.

</deferred>

---

*Phase: 11-dual-window-discharge*
*Context gathered: 2026-05-04*
*Next step: /gsd-plan-phase 11 — Plan-Erstellung mit Forschungs-Schritt für Inverter-Race-Pattern und Test-Strategien*
