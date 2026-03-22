# Requirements: EEG Energy Optimizer

**Defined:** 2026-03-20
**Core Value:** Feed solar energy into the grid when the community actually needs it, not when everyone else is feeding in too.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Optimierung

- [x] **OPT-01**: Morgen-Einspeisevorrang — Batterie-Laden verzögern, PV morgens ins Netz einspeisen (konfigurierbarer Zeitraum, z.B. bis 10:00-11:00)
- [x] **OPT-02**: Abend-Entladung — Batterie abends ins Netz entladen unter konfigurierbaren Bedingungen (SOC-Schwelle, PV-Prognose morgen, Nachtverbrauchsreserve)
- [x] **OPT-03**: Optimale Entlade-Strategie — vollständige Logik aus bestehender Integration (dynamischer Min-SOC basierend auf Nachtverbrauch + Sicherheitspuffer, Überschuss-Check inkl. Batterie + Puffer + Hausverbrauch)

### Sicherheit

- [x] **SAF-01**: SOC-Guards — zweistufig: KRITISCH (<10%: sofort laden, immer aktiv) und HOCH (<25%: Ladelimit erhöhen, unterdrückbar während EEG-Fenster via Guard-Delay)
- [x] **SAF-02**: Dynamischer Min-SOC — Formel: Basis-Min-SOC + (prognostizierter Nachtverbrauch × Sicherheitspuffer-%) als SOC-Prozent
- [x] **SAF-03**: Nächster-Tag-Check — Entladung nur wenn PV-Prognose morgen >= Gesamtbedarf morgen (Hausverbrauch + Batterie von Min-SOC auf 100% + Puffer-Aufheizung)
- [x] **SAF-04**: Dry-Run Modus — Optimizer berechnet und zeigt Entscheidungen, führt aber keine Aktionen aus

### Prognose

- [x] **FCST-01**: Solcast PV-Produktionsprognose — verbleibende Produktion heute + Prognose morgen aus Solcast Solar HA-Integration lesen
- [x] **FCST-02**: Forecast.Solar als Alternative — kostenlose PV-Produktionsprognose als zweite Quelle, wählbar im Setup
- [x] **FCST-03**: Verbrauchsprofil — automatische Verbrauchsprognose aus HA Recorder Langzeit-Statistiken (rollende Durchschnitte, 7 Einzeltage: Mo/Di/Mi/Do/Fr/Sa/So)

### Infrastruktur

- [x] **INF-01**: Abstraktes Wechselrichter-Interface — Python ABC mit Methoden für Lade-/Entlade-Steuerung (set_charge_limit, set_discharge, stop_forcible) und is_available Property, unabhängig vom WR-Typ. SOC/Kapazität werden über HA-Sensor-Entities gelesen (im Config Flow gemappt), nicht über das Interface.
- [x] **INF-02**: Huawei SUN2000 Implementierung — konkrete Implementierung des WR-Interface via HA Huawei Solar Integration Services (forcible_charge, forcible_discharge_soc, stop_forcible_charge)
- [x] **INF-03**: HACS-kompatible Repo-Struktur — manifest.json, hacs.json, korrekte Verzeichnisstruktur, Brand-Assets von Anfang an
- [x] **INF-04**: Onboarding Panel — HA Sidebar Panel (LitElement/JS) mit Step-by-Step Setup-Wizard, Voraussetzungsprüfung (Solcast/Forecast.Solar installiert? WR-Integration aktiv?), Sensor-Mapping mit Kontext-Hilfe, Anleitungen für Abhängigkeiten

### Sensoren & Dashboard

- [x] **SENS-01**: Entscheidungs-Sensor — aktuelle Strategie als State, vollständige Decision (Begründung, Inputs, Guards, Zeitstempel) als Attribute
- [x] **SENS-02**: Entladungs-Vorschau — tagsüber anzeigen ob heute Nacht Entladung geplant ist (Min-SOC, PV-Prognose vs. Bedarf)
- [x] **SENS-03**: EEG Zeitfenster — konfigurierbare Morgen- und Abend-Fenster (z.B. 6:00-9:00, 17:00-22:00) die definieren wann EEG-Einspeisung priorisiert wird

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Wechselrichter

- **INV-01**: Fronius Gen24 Implementierung — Batterie-Steuerung via Modbus/HTTP Digest API
- **INV-02**: SMA Sunny Boy / Tripower Implementierung
- **INV-03**: Weitere WR-Typen als Community-Beiträge

### Erweiterte Optimierung

- **ADV-01**: Strategie-Auswahl — automatische Strategiewahl (Überschuss/Balanciert/Engpass/Nacht) basierend auf Überschuss-Faktor
- **ADV-02**: Inverter-Drosselungs-Erkennung — spekulativ +2kW wenn WR am Einspeise-Limit drosselt
- **ADV-03**: Mehrere Entlade-Strategien — einfach (nur SOC-Schwelle) bis optimal (volle Logik), wählbar

## Out of Scope

| Feature | Reason |
|---------|--------|
| Spot-Preis / Tarif-Optimierung | EMHASS und Predbat lösen das bereits gut. EEG nutzt keine Spot-Preise. |
| EV-Ladeoptimierung | Eigene Domain mit eigenen Integrationen (evcc, go-eCharger). Zu viel Kopplung. |
| Heizstab / Warmwasser-Steuerung | Anlagen-spezifisch, nicht jeder hat einen OhmPilot. Hält den Fokus auf Batterie + Netz. |
| LP-Solver / mathematische Optimierung | Regelbasiert ist erklärbar und debugbar. LP-Solver sind Blackboxen für Endbenutzer. |
| Multi-Location Support | Massive Komplexität für Nischen-Usecase. Separate Instanzen nutzen. |
| Echtzeit-EEG-API | Keine standardisierte API existent. Zeitfenster sind pragmatischer Proxy. |
| Machine Learning | Dependency-Overhead, Training-Daten nötig, Blackbox-Entscheidungen. Rolling Averages reichen. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INF-01 | Phase 1 | Complete |
| INF-02 | Phase 1 | Complete |
| INF-03 | Phase 1 | Complete |
| FCST-01 | Phase 2 | Complete |
| FCST-02 | Phase 2 | Complete |
| FCST-03 | Phase 2 | Complete |
| OPT-01 | Phase 3 | Complete |
| OPT-02 | Phase 3 | Complete |
| OPT-03 | Phase 3 | Complete |
| SAF-01 | Phase 3 | Complete |
| SAF-02 | Phase 3 | Complete |
| SAF-03 | Phase 3 | Complete |
| SAF-04 | Phase 3 | Complete |
| SENS-01 | Phase 3 | Complete |
| SENS-02 | Phase 3 | Complete |
| SENS-03 | Phase 3 | Complete |
| INF-04 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-03-20*
*Last updated: 2026-03-20 after roadmap creation*
