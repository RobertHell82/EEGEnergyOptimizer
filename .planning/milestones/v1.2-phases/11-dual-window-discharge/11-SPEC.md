# Phase 11: Dual-Window-Entladung — Specification

**Created:** 2026-05-04
**Ambiguity score:** 0.12
**Requirements:** 9 locked

## Goal

Der Optimizer unterstützt zwei unabhängig aktivierbare Entladefenster (Slot A abends, Slot B morgens) mit getrennter Pro-Slot-Hysterese und Energie-Budgetierung, sodass EEG-Bedarf in Abend- (~20:00–24:00) und Morgenstunden (~03:00 bis vor Sonnenaufgang) gezielt adressiert wird, ohne den Genauigkeitsgewinn des heutigen späten Single-Window-Starts zu verlieren.

## Background

`optimizer.py:_should_discharge` (Zeile 905+) berechnet heute genau **ein** Entladefenster aus `discharge_start_time` (Default 01:00 nach v1.1.x-Anpassung) bis `compute_hard_cutoff` (`min(04:00 next-sunrise-day, sunrise − 1h)`). Mit PeakShare läuft `peakshare.find_discharge_window` (Zeile 44+) als Sliding-Window-Suche über genau diese Spanne und liefert ein einziges `tuple[datetime, datetime]`. Hysterese ist ein einzelnes Datumsfeld `_discharge_activated_date` (`optimizer.py:370`).

Der späte Start ab 01:00 wurde gewählt, weil zu diesem Zeitpunkt der reale Nachtverbrauch der Hausinstallation bereits weitgehend bekannt ist — die Entscheidung "wieviel Batterie kann ich entladen" wird damit verlässlicher. Der Preis ist der Verzicht auf Einspeisung in die Stunden 20:00–01:00 (EEG-Abendpeak) und auf Einspeisung in die kalten Morgenstunden vor Sonnenaufgang im Winter, wo der EEG-Bedarf laut PeakShare-Daten ebenfalls hoch ist.

SolarEdge StorEdge (`inverter/solaredge.py`) schreibt Entlade-Kommandos in NVRAM. Dies wird über den Register-Writes-Sensor (`sensor.py` #17) und einen Grid-Import-Watchdog überwacht; doppelte Start/Stop-Zyklen pro Tag sind hier explizit zu vermeiden.

## Requirements

1. **Konfigurations-Schema für Dual-Window**: Zwei unabhängig aktivierbare Slots mit eigenen Zeit-Konfigurationen.
   - Current: `CONF_DISCHARGE_START_TIME` und `CONF_DISCHARGE_POWER_KW` (`const.py:89-90`) konfigurieren genau ein Fenster.
   - Target: Neue Config-Keys `CONF_ENABLE_DUAL_DISCHARGE` (default False), `CONF_ENABLE_SLOT_A`, `CONF_ENABLE_SLOT_B`, `CONF_DISCHARGE_A_START` (default "20:00"), `CONF_DISCHARGE_B_START` (default "03:00"), `CONF_DISCHARGE_B_END_CAP` (default "07:00"), `CONF_DISCHARGE_A_RESERVE_PCT` (default 15). Die alten Keys bleiben für `enable_dual_discharge=False` erhalten.
   - Acceptance: Mit `enable_dual_discharge=False` (Default) bleibt die heutige Single-Window-Logik byte-genau erhalten — bestehende Tests in `tests/` laufen unverändert grün; Config-Migration setzt `enable_dual_discharge=False` für alle Bestands-Entries (config_entry version bump in `__init__.py`).

2. **Slot A — Abend-Entladung mit Energie-Reserve**: Entlädt ab `discharge_a_start_time` ohne harte Uhrzeit-Obergrenze, bis SOC die für Slot B reservierte Untergrenze erreicht.
   - Current: Es existiert kein Slot-A-Konzept; Entladung beginnt einmalig bei `discharge_start_time`.
   - Target: Wenn Slot A aktiv ist, gilt eine **erhöhte SOC-Untergrenze** = `min_soc_dyn + discharge_a_reserve_pct`. A endet automatisch wenn SOC ≤ diese erhöhte Schwelle, oder spätestens 5 Minuten vor `discharge_b_start_time` (falls Slot B ebenfalls aktiv).
   - Acceptance: Bei `discharge_a_reserve_pct=15`, `min_soc_dyn=20` und Batterie-SOC fällt auf 35% → Slot A geht aus, übergeht in Pause-Phase. Wenn nur Slot A aktiv (B aus), endet A bei `min_soc_dyn` ohne Reserve-Aufschlag.

3. **Slot B — Morgen-Entladung mit adaptivem Ende vor Sonnenaufgang**: Entlädt ab `discharge_b_start_time` bis `min(discharge_b_end_cap, sunrise − 5min)`.
   - Current: `compute_hard_cutoff` (`optimizer.py:175`) liefert `min(04:00 next-sunrise-day, sunrise − 1h)` als einzigen Cutoff für das gesamte Fenster.
   - Target: Neue Funktion `compute_b_window_end(now, sunrise, b_end_cap, morning_offset_h)` liefert `min(b_end_cap_anchored_at_sunrise_day, sunrise − morning_offset_h, sunrise − 5min)`. Slot B endet **strikt vor** Beginn der Morgen-Einspeisung — Slot B und Morgen-Einspeisung laufen niemals parallel.
   - Acceptance: Test-Cases für Sommer (SA 04:52 → b_end ≈ 04:47), Winter (SA 07:30, b_end_cap=07:00 → b_end = 07:00, weil SA−5min = 07:25 später ist), Übergang (SA 06:00 → b_end = 05:55), tiefer Winter (SA 08:30, cap=07:00 → b_end = 07:00). Wenn `b_start ≥ b_end_effective`, wird Slot B in dieser Sitzung nicht aktiviert (z.B. Sommer mit `b_start=05:00`).

4. **Pro-Slot-Hysterese**: Reaktivierungs-Schwellen werden pro Slot getrennt verfolgt.
   - Current: Ein einzelnes `_discharge_activated_date` für die gesamte Entlade-Sitzung; Reaktivierung benötigt `SOC > min_soc + 5%`.
   - Target: `_slot_a_activated_date` und `_slot_b_activated_date` als separate Felder. Reaktivierungs-Aufschlag (+5% SOC) gilt pro Slot unabhängig — wenn A heute aktiv war und endete, gilt für A bei erneuter Aktivierung der Aufschlag, B startet ohne Aufschlag (sofern B selbst noch nicht aktiv war heute).
   - Acceptance: Test simuliert: A aktiviert 20:00–22:00, deaktiviert (SOC fällt unter Reserve), 22:30 SOC steigt wieder über Reserve+5% → A reaktiviert (Hysterese-Aufschlag wirkt nur auf A). B startet 03:00 mit normaler `min_soc_dyn`-Schwelle ohne Aufschlag.

5. **Mutual Exclusion zur Morgen-Einspeisung**: Slot B endet stets vor Beginn der Morgen-Einspeisung; beide laufen niemals gleichzeitig.
   - Current: Es gibt keine explizite Slot-B-Phase; `compute_hard_cutoff` mit `sunrise − 1h` schließt heute mit dem Morgen-Einspeisungs-Start (bei `morning_offset = 0` wäre der Konflikt-Bereich neu).
   - Target: `compute_b_window_end` zieht stets eine 5-Minuten-Pause vor `sunrise − morning_offset_h` ab. Im `_evaluate`-Pfad gilt weiter die heutige Reihenfolge: `block_charging` (Morgen-Einspeisung) wird vor `should_discharge` ausgewertet — bei Konflikt gewinnt Morgen-Einspeisung.
   - Acceptance: Test mit `morning_offset=0`, SA 07:30, `b_end_cap=07:00` → Slot B endet 07:00, Morgen-Einspeisung beginnt 07:30 — Pause-Lücke ≥ 25min. Test mit `morning_offset=1`, SA 07:30 → Morgen-Einspeisung würde 06:30 starten, Slot B endet damit 06:25 (SA−1h−5min).

6. **SolarEdge-Sperre für Dual-Mode**: Auf SolarEdge-Wechselrichtern bleibt Dual-Window deaktiviert.
   - Current: SolarEdge erzwingt bereits `discharge_power_kw ≥ 5.0` (`optimizer.py:349-354`); kein Limit auf Anzahl Slots, weil heute nur einer existiert.
   - Target: Wenn `inverter_type == "solaredge_storedge"`, wird `enable_dual_discharge` zur Laufzeit auf `False` erzwungen (mit Warnung im Log) und im Onboarding-Panel mit erläuterndem Hinweistext deaktiviert.
   - Acceptance: Bei SolarEdge-Setup zeigt das Panel "Dual-Window auf SolarEdge nicht verfügbar (NVRAM-Verschleiß)"; beim Speichern eines Configs mit `inverter_type=solaredge_storedge` und `enable_dual_discharge=true` setzt der Code den Wert auf `false` zurück und loggt eine Warnung.

7. **Telemetry-Reasons pro Slot**: Activity Log und Telemetrie-Events unterscheiden Slot-A- und Slot-B-Phasen.
   - Current: `REASON_BEFORE_DISCHARGE_START`, `REASON_HARD_CUTOFF_AFTER_4AM` etc. (`optimizer.py:73+`) sind slot-agnostisch.
   - Target: Neue snake_case-Reasons in `ALL_REASONS`: `before_slot_a`, `slot_a_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_active`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`. `Decision`-Felder erweitert um `discharge_active_slot: "A"|"B"|None`.
   - Acceptance: Activity-Log-Einträge bei Slot-A-Start enthalten Reason `slot_a_active`; bei Übergang von A zur Pause `slot_a_reserve_reached` oder `between_slots`. WebSocket-API `eeg_optimizer/get_activity_log` liefert die neuen Reasons unverändert durch.

8. **Independent Slot-Aktivierung**: A-only und B-only Konfigurationen funktionieren ohne Verlust der Reserve-/Hysterese-Logik.
   - Current: Es gibt keine Slot-Trennung.
   - Target: `enable_slot_a=true, enable_slot_b=false` → A-only (kein Reserve-Aufschlag, A endet bei `min_soc_dyn`). `enable_slot_a=false, enable_slot_b=true` → B-only (klassische Morgen-Entladung). `enable_slot_a=true, enable_slot_b=true` → Dual mit Reserve.
   - Acceptance: Drei Test-Szenarien mit jeweils nur einem Slot aktiv plus dem Dual-Szenario produzieren erwartete Decision-Sequenzen über einen 24h-Simulationslauf.

9. **Inverter-Race-Schutz**: Zwischen Slot-Ende und nächstem Inverter-Kommando liegen mindestens 5 Minuten.
   - Current: `_execute` (`optimizer.py`) deduppliziert Kommandos via `_prev_zustand`/`_last_decision`; keine zeitliche Mindestlücke zwischen Stop und Start.
   - Target: Slot-A-Ende und Slot-B-Start müssen mindestens 5 Minuten auseinanderliegen (`b_start ≥ a_end_effective + 5min` als Konsistenz-Constraint). Der `compute_b_window_end`-Output beachtet die 5-Minuten-Lücke zur Morgen-Einspeisung.
   - Acceptance: Wenn ein User `a_start=20:00` und `b_start=02:55` setzt während das System eine Slot-A-Sitzung bis ~02:50 erwartet (Energie reicht so weit), wird die Konfiguration mit Validierungsfehler abgewiesen oder b_start auf 02:56 angehoben (Verhalten in discuss-phase finalisiert).

## Boundaries

**In scope:**
- Dual-Window-Optimizer-Decision-Engine (`optimizer.py:_should_discharge` Refactor mit Slot-A/B-Pfaden)
- Pro-Slot-Hysterese mit unabhängigen Aktivierungs-Datumsfeldern
- Konfigurations-Schema-Erweiterung (`const.py`) plus Config-Entry-Migration
- Adaptives B-Ende mit neuer Funktion `compute_b_window_end`
- Mutual-Exclusion-Garantie zur Morgen-Einspeisung
- SolarEdge-Sperre (Lauflzeit-Erzwingung + UI-Hinweis)
- PeakShare-Integration für Dual-Mode (zwei separate Sliding-Window-Suchen, eine pro Slot, mit slot-spezifischem `available_kwh`)
- Telemetry-Reasons für Slot-Phasen
- Onboarding-Panel-Erweiterung (`frontend/eeg-optimizer-panel.js`) für Dual-Konfiguration und Status-Anzeige
- Unit-Tests für Window-Resolution, SA-Adaption, Reserve-Logik, Pro-Slot-Hysterese, SolarEdge-Sperre

**Out of scope:**
- "Slot M" / Mid-Night-Polling zwischen A-Ende und B-Start — Backlog v1.3+, hält Phase 11 fokussiert
- Slot-individuelle PeakShare-Communities — eine Community gilt für beide Slots
- Slot-spezifische Inverter-Rate-Limits über die SolarEdge-Sperre hinaus
- Quantitative Wirkungsanalyse via Telemetrie-Vergleich (Single- vs. Dual-Window-kWh) — nutzbar in v1.1-Dashboard, kein Verifikationskriterium hier
- Dynamische Auto-Berechnung von `discharge_a_reserve_pct` aus historischen Verbrauchswerten — fix konfigurierbar, Default 15
- Demand-weighted Energie-Aufteilung zwischen Slot A und B (Vorschlag aus Konzept-Diskussion) — bleibt in `static_reserve`-Modus, demand-weighting evtl. v1.3
- Backwards-Migration alter `discharge_start_time` zu Dual-Konfiguration — alte Logik bleibt bei `enable_dual_discharge=false` 1:1 erhalten

## Constraints

- **Inverter-Kompatibilität:** Dual-Mode erfordert Wechselrichter, die mehrfache Entlade-Start/Stop-Zyklen pro Tag ohne Verschleiß tolerieren. Huawei, Fronius, SolaX bestätigt; SolarEdge gesperrt.
- **Mindestpause:** ≥5 Minuten zwischen Slot-Ende und nächstem Inverter-Kommando (Slot-A-Ende vor Slot-B-Start, Slot-B-Ende vor Morgen-Einspeisung).
- **Backwards-Compatibility:** Mit `enable_dual_discharge=False` (Default für Bestands-Entries) bleibt das Verhalten der heutigen Single-Window-Logik byte-genau erhalten — keine Verhaltensänderung ohne explizites Opt-in.
- **Config-Entry-Migration:** Version-Bump in `__init__.py` mit `_async_migrate_entry`-Eintrag, der für Bestands-Entries `enable_dual_discharge=False` setzt.
- **PeakShare-Daten-Reichweite:** Die `community_data["hours"]`-Liste muss die Slot-A- und Slot-B-Zeiträume abdecken; falls nicht, fällt der betroffene Slot auf `static_reserve`-Modus zurück (kein Slot-Ausfall).

## Acceptance Criteria

- [ ] `enable_dual_discharge=False` (Default) — bestehende Tests in `tests/` laufen byte-identisch grün
- [ ] `enable_slot_a=true, enable_slot_b=true` — Slot A und Slot B liefern in einem 24h-Simulationstest jeweils ≥1 separate Entladephase mit korrekter Slot-Markierung in Decision
- [ ] `enable_slot_a=true, enable_slot_b=false` — Verhalten entspricht klassischer Abend-Entladung mit `a_start` als `discharge_start_time`, ohne Reserve-Aufschlag
- [ ] `enable_slot_a=false, enable_slot_b=true` — System startet Entladung erst um `b_start`, nutzt klassische `min_soc_dyn`-Schwelle
- [ ] `compute_b_window_end` liefert für 4 Test-Cases (Sommer-SA, Winter-SA, Übergang, tiefer Winter) die in Requirement 3 spezifizierten Werte
- [ ] Slot B endet stets ≥5min vor Beginn der Morgen-Einspeisung, validiert über parametrisierten Test über `morning_offset ∈ {0, 1}` × Sunrise-Range
- [ ] Pro-Slot-Hysterese: Test simuliert A-Aktivierung → A-Ende durch Reserve → A-Reaktivierung benötigt SOC > Reserve+5%, gleichzeitig B startet später am Tag mit `min_soc_dyn`-Schwelle ohne Aufschlag
- [ ] SolarEdge-Erzwingung: Config mit `inverter_type=solaredge_storedge, enable_dual_discharge=true` führt zu Logged-Warning und `enable_dual_discharge=false` zur Laufzeit
- [ ] Onboarding-Panel zeigt Dual-Window-Settings nur wenn `inverter_type ≠ solaredge_storedge`; bei SolarEdge ist die Toggle deaktiviert mit erläuterndem Tooltip
- [ ] Activity-Log enthält die in Requirement 7 gelisteten neuen Reasons mit korrekter Slot-Zuordnung
- [ ] Inverter-Race-Schutz: Konfigurations-Validation lehnt `b_start < a_min_required_end + 5min` ab oder korrigiert automatisch (Verhalten in PLAN.md festzulegen)
- [ ] Manuelle 7-Tage-Beobachtung an mind. einer der Test-HA-Instanzen (Huawei und/oder Fronius) durch User; Bewertung "gute Idee oder nicht" als finale UAT-Entscheidung

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                              |
|--------------------|-------|------|--------|----------------------------------------------------|
| Goal Clarity       | 0.92  | 0.75 | ✓      | Zwei Slots, EEG-Mehrwert, Genauigkeitserhalt klar  |
| Boundary Clarity   | 0.88  | 0.70 | ✓      | Slot M, demand-weighted, SolarEdge-Migration out  |
| Constraint Clarity | 0.85  | 0.65 | ✓      | Defaults gesetzt, Mindestpause spezifiziert        |
| Acceptance Criteria| 0.85  | 0.70 | ✓      | 12 Pass/Fail-Kriterien plus 7-Tage-User-UAT        |
| **Ambiguity**      | 0.12  | ≤0.20| ✓      |                                                    |

## Interview Log

| Round | Perspective    | Question summary                              | Decision locked                                            |
|-------|----------------|-----------------------------------------------|-----------------------------------------------------------|
| 1     | Researcher     | Sommer-Bedarf, Sonnenaufgangs-Tabelle, morning_offset | Bedarf bis 08:30, morning_offset default 0, b_cap 07:00 |
| 1     | Boundary       | Slot M Mid-Night?                             | Out of scope, Backlog v1.3+                              |
| 1     | Failure        | Erfolgsmetrik?                                | Manuelle 7-Tage-Beobachtung durch User + Funktionale Tests |
| 1     | Simplifier     | Slot-A-Ende per Uhrzeit oder Energie?         | Energie-Reserve, keine harte Uhrzeit-Obergrenze           |
| 2     | Failure        | Slot B vs Morgen-Einspeisung im Sommer?       | Strikt sequentiell, B endet vor SA−5min, niemals parallel |
| 2     | Boundary       | Akzeptanztest formal?                         | Funktionale Tests + 7-Tage-Beobachtung                    |

---

*Phase: 11-dual-window-discharge*
*Spec created: 2026-05-04*
*Next step: /gsd-discuss-phase 11 — Implementierungs-Entscheidungen (Refactor-Strategie für `_should_discharge`, Migration-Pattern, Panel-Integration, Test-Layout)*
