# Phase 3: Optimizer & Safety System - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Automatisiertes, EEG-optimiertes Batteriemanagement: Morgens Batterieladung blockieren damit PV ins Netz geht, abends Batterie entladen wenn morgen ein Überschuss-Tag ist. Entscheidungs-Sensor mit Markdown-Dashboard für vollständige Transparenz. Optimizer-Modi (Ein/Test/Aus) als Select-Entity.

</domain>

<decisions>
## Implementation Decisions

### Morgen-Einspeisung (OPT-01)
- **D-01:** 1 Stunde vor Sonnenaufgang → Batterie-Ladelimit auf 0 kW setzen via Inverter-Interface
- **D-02:** Sperre gilt bis konfigurierbare Enduhrzeit (z.B. 10:00 oder 11:00)
- **D-03:** Sperre greift NUR an Überschuss-Tagen (Überschuss-Faktor ≥ Schwelle). An normalen Tagen: kein Eingriff morgens
- **D-04:** Mittags (nach Enduhrzeit): kein Eingriff, Batterie lädt normal vom Wechselrichter

### Abend-Entladung (OPT-02, OPT-03)
- **D-05:** Entladung startet ab konfigurierbarer Uhrzeit (Default: 20:00)
- **D-06:** Feste Entladeleistung in kW (konfigurierbar)
- **D-07:** Entladung läuft bis berechneter Min-SOC erreicht ist, keine End-Uhrzeit
- **D-08:** Min-SOC Berechnung: konfigurierter Basis-Min-SOC + (prognostizierter Verbrauch bis Sonnenaufgang × Sicherheitspuffer-%) umgerechnet in SOC-Prozent
- **D-09:** Entlade-Bedingung: Nur wenn PV-Prognose morgen ≥ Gesamtbedarf morgen (Überschuss-Tag)
- **D-10:** Batterie hat zusätzlich Hardware-seitigen Min-SOC vom Hersteller als absolute Untergrenze

### Überschuss-Faktor (zentrale Steuerung)
- **D-11:** Überschuss-Faktor = PV-Prognose / Energiebedarf — entscheidet ob ein Tag ein Überschuss-Tag ist
- **D-12:** Schwellwert konfigurierbar (z.B. 1.25 als Default aus bestehender Integration)
- **D-13:** Steuert BEIDES: Morgen-Einspeisung UND Abend-Entladung. Faktor unter Schwelle → weder Morgen-Sperre noch Abend-Entladung

### Keine Guards (Vereinfachung gegenüber Referenz)
- **D-14:** KEINE zweistufigen Safety-Guards (kein KRITISCH/HOCH/MITTEL System)
- **D-15:** Min-SOC bei Entladung + Hardware-Schutz des Wechselrichters reichen als Sicherheitsnetz
- **D-16:** SAF-01 (SOC-Guards) und SAF-02 (dynamischer Min-SOC als Guard) entfallen. Der dynamische Min-SOC lebt als Entlade-Berechnung weiter (D-08), nicht als Guard

### Optimizer-Modi (SAF-04)
- **D-17:** Drei Modi: **Ein** (volle Optimierung), **Test** (berechnet + zeigt, führt nicht aus), **Aus** (komplett inaktiv)
- **D-18:** Select-Entity, persistent über HA-Neustarts (restore_state)
- **D-19:** Kein Feed-In Switch, kein Power-Number — Optimizer steuert alles selbst

### Steuerungs-Entities
- **D-20:** Alle Entities (Select + Sensoren) unter einem gemeinsamen Device
- **D-21:** Kein separater Switch oder Number für Einspeisung — nur der Modus-Select

### Optimizer-Zustände
- **D-22:** Drei interne Zustände: **Morgen-Einspeisung**, **Normal**, **Abend-Entladung**
- **D-23:** Kein "Inaktiv"-Zustand separat — wenn Modus "Aus" dann läuft der Zyklus nicht

### Entscheidungs-Sensor (SENS-01, SENS-02, SENS-03)
- **D-24:** EIN Sensor für alles — kein separater Entlade-Vorschau-Sensor (SENS-02 wird Attribut)
- **D-25:** State: Nächste geplante Aktion (z.B. "Abend-Entladung 20:00")
- **D-26:** Hauptattribut: Markdown-formatierter Textblock als Mini-Dashboard
- **D-27:** Markdown-Inhalt je nach Tageszeit:
  - Aktueller Status (Zustandstext)
  - Nächste Aktion mit relevanten Daten
  - Übernächste Aktion mit relevanten Daten
- **D-28:** Abend-Entladungs-Block: Startzeit, PV-Prognose morgen, Verbrauchsprognose morgen, Überschuss-Faktor, berechneter Ziel-SOC (mit Berechnungsgrundlagen: konfigurierter Min-SOC + Verbrauch bis Sonnenaufgang)
- **D-29:** Morgen-Einspeisungs-Block: Ob Ladung blockiert wird (ja/nein), bis wann blockiert, PV-Prognose heute, Verbrauchsprognose heute, Überschuss-Faktor
- **D-30:** Update-Intervall: minütlich (Default), konfigurierbar in erweiterten Einstellungen

### Claude's Discretion
- Optimizer-Zyklus Architektur (async timer, Snapshot/Decision Pattern)
- Markdown-Formatierung und Layout des Entscheidungs-Sensors
- Config Flow Erweiterung für Phase-3-Parameter (Zeitfenster, Entladeleistung, Min-SOC etc.)
- Interne Berechnung des Überschuss-Faktors
- Fehlerbehandlung bei fehlenden Sensor-Werten
- 60-Sekunden-Zyklus vs. konfigurierbares Intervall

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bestehende Integration (Algorithmus-Referenz)
- `custom_components/energieoptimierung/optimizer.py` — Decision Engine: Snapshot/Decision Dataclasses, Strategie-Auswahl, Nachtentladung-Logik (dynamischer Min-SOC, Überschuss-Check, Entlade-Bedingungen). Kernalgorithmen übertragbar, aber vereinfacht (keine Guards, kein Heizstab, kein Warmwasser)
- `custom_components/energieoptimierung/select.py` — Optimizer Mode Select Entity mit restore_state Pattern
- `custom_components/energieoptimierung/const.py` — Strategy-Konstanten, Mode-Definitionen, Config-Keys für Entladung/Guards

### Neue Integration (Phase 1+2 Output)
- `custom_components/eeg_energy_optimizer/__init__.py` — Entry Setup, Platform-Forwarding, hass.data Pattern (muss um 60s-Timer und Select-Platform erweitert werden)
- `custom_components/eeg_energy_optimizer/const.py` — Bestehende Config-Keys, Defaults (muss um Optimizer-Konstanten erweitert werden)
- `custom_components/eeg_energy_optimizer/sensor.py` — 12 bestehende Sensoren, dual-timer Pattern (fast/slow), DeviceInfo
- `custom_components/eeg_energy_optimizer/coordinator.py` — ConsumptionCoordinator: calculate_period() für Verbrauchsprognosen
- `custom_components/eeg_energy_optimizer/forecast_provider.py` — ForecastProvider: get_forecast() für PV-Prognosen
- `custom_components/eeg_energy_optimizer/inverter/base.py` — InverterBase: async_set_charge_limit(), async_set_discharge(), async_stop_forcible()

### Projekt-Dokumentation
- `.planning/REQUIREMENTS.md` — OPT-01, OPT-02, OPT-03, SAF-03, SAF-04, SENS-01, SENS-03 (SAF-01, SAF-02 entfallen)
- `.planning/PROJECT.md` — Projektkontext, Constraints, Key Decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `optimizer.py` (Referenz): Snapshot/Decision Dataclass-Pattern, Nachtentladungs-Logik mit dynamischem Min-SOC, Überschuss-Faktor Berechnung — Kernalgorithmen übertragbar
- `select.py` (Referenz): RestoreEntity Mixin für persistenten Modus über Neustarts
- `sensor.py` (neue Integration): Dual-Timer Pattern (fast/slow), DeviceInfo-Sharing über alle Entities
- `coordinator.py` (neue Integration): `calculate_period(start, end)` liefert Verbrauchsprognose für beliebige Zeiträume
- `forecast_provider.py` (neue Integration): `get_forecast()` liefert PV remaining today + tomorrow

### Established Patterns
- `async_track_time_interval` für periodische Optimizer-Zyklen
- `hass.data[DOMAIN][entry_id]` für Shared State (Inverter, Provider, Coordinator)
- `RestoreEntity` für State-Persistenz über HA-Neustarts
- `SensorEntity` mit `extra_state_attributes` für Markdown-Attribute

### Integration Points
- Inverter-Interface: `async_set_charge_limit(0)` für Morgen-Sperre, `async_set_discharge(power, soc)` für Abend-Entladung, `async_stop_forcible()` für Normal-Zustand
- ConsumptionCoordinator: `calculate_period(now, sunrise)` für Nachtverbrauchs-Prognose
- ForecastProvider: `get_forecast()` für Überschuss-Faktor Berechnung
- Sun-Integration: `sun.sun` Entity für Sonnenaufgang/Sonnenuntergang Zeiten
- Config Entry: Neue Keys für Entlade-Parameter, EEG-Zeitfenster, Überschuss-Schwelle

</code_context>

<specifics>
## Specific Ideas

- Überschuss-Faktor Schwelle aus bestehender Integration übernehmen (Default 1.25)
- Morgen-Sperre startet 1h vor Sonnenaufgang — nicht an festes Zeitfenster gebunden, sondern an sun.sun
- Entladeleistung und Startzeit sollen "später vielleicht einmal noch intelligenter" werden — vorerst einfache fixe Werte
- Markdown im Entscheidungs-Sensor: "hübsch formatiert" als Mini-Dashboard für Lovelace Markdown-Card
- Bestehende energieoptimierung-Integration als lebende Algorithmus-Referenz, aber eigenständig neu implementiert

</specifics>

<deferred>
## Deferred Ideas

- Intelligentere Entlade-Startzeit (z.B. basierend auf Strompreis oder EEG-Bedarf) — "später vielleicht einmal"
- SAF-01/SAF-02 Guards könnten als optionales Feature zurückkommen wenn Nutzer es brauchen
- Feed-In Switch + Power Number als manuelle Override-Entities — vorerst nicht nötig
- Zusätzliche Optimizer-Modi (z.B. "Nur Einspeisung" ohne Entladung) — bei Bedarf erweiterbar

</deferred>

---

*Phase: 03-optimizer-safety-system*
*Context gathered: 2026-03-21*
