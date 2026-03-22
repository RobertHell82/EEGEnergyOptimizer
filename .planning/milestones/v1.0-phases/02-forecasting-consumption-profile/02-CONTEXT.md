# Phase 2: Forecasting & Consumption Profile - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

PV-Produktionsprognosen aus Solcast oder Forecast.Solar lesen und Verbrauchsprognosen aus HA Recorder-History berechnen. Alle Daten die der Optimizer (Phase 3) braucht als HA-Sensor-Entities bereitstellen.

</domain>

<decisions>
## Implementation Decisions

### PV-Prognose Quellen
- **D-01:** Prognose ist Pflicht — Integration funktioniert nicht ohne PV-Prognose-Quelle
- **D-02:** Zwei Quellen unterstützt: Solcast Solar und Forecast.Solar (beide als HA-Integration vorausgesetzt, nicht selbst eingebaut)
- **D-03:** Auswahl der Prognose-Quelle erfolgt im Onboarding Panel (Phase 4), NICHT im Config Flow
- **D-04:** Wenn gewählte Prognose-Integration nicht installiert ist: blockieren + Installationsanleitung anzeigen
- **D-05:** Für Phase 2 (ohne Onboarding): Prognose-Quelle im Config Flow als Zwischenlösung konfigurierbar, wird in Phase 4 ins Panel verschoben
- **D-06:** Forecast.Solar: HA Integration (`forecast_solar`) voraussetzen — funktioniert gut, kein Grund direkte API einzubauen

### Verbrauchsprofil
- **D-07:** Ein einzelner Verbrauchssensor reicht — kein Heizstab/Wallbox/Puffer-Abzug
- **D-08:** Huawei Default: `sensor.power_meter_verbrauch` (Stromzähler Verbrauch, kWh, total_increasing)
- **D-09:** Lookback-Fenster: 8 Wochen default, konfigurierbar in erweiterten Onboarding-Einstellungen
- **D-10:** Wochentag-Gruppierung: **7 Einzeltage** (Mo, Di, Mi, Do, Fr, Sa, So) — nicht 4 Zonen wie in der alten Integration
- **D-11:** Berechnung sofort starten, auch mit wenig History

### Sensor-Umfang
- **D-12:** Tagesverbrauchsprognosen: heute + 6 weitere Tage = 7 Sensoren (basierend auf Verbrauchsprofil)
- **D-13:** Verbrauchsprofil: Stundendurchschnitte pro Wochentag als Sensor-Attribut (7 Tagesprofile)
- **D-14:** Batterie fehlende Energie: kWh bis Batterie voll (berechnet aus SOC + Kapazität)
- **D-15:** PV-Prognose heute (verbleibende Produktion) + PV-Prognose morgen = 2 Sensoren
- **D-16:** Prognose bis Sonnenaufgang: prognostizierter Verbrauch von jetzt bis Sonnenaufgang (für Nachtentladung/Min-SOC Berechnung in Phase 3)
- **D-17:** Kein Tesla, kein Puffer, kein Heizstab, kein Energy Dashboard

### Update-Intervalle
- **D-18:** Verbrauchsprofil: 15 Minuten (slow) — ändert sich kaum
- **D-19:** Alle anderen Sensoren: 1 Minute (fast) — PV-Prognose, Batterie fehlend, Tagesprognosen
- **D-20:** Beide Intervalle konfigurierbar in erweiterten Onboarding-Einstellungen (Phase 4). Für Phase 2: in Config Flow als Zwischenlösung

### Config Flow Erweiterung (Zwischenlösung bis Onboarding Panel)
- **D-21:** Config Flow bekommt zusätzliche Schritte für Phase 2: Prognose-Quelle, Verbrauchssensor
- **D-22:** Wird in Phase 4 komplett ins Onboarding Panel verschoben — Config Flow wird dann minimal

### Claude's Discretion
- Technische Architektur der Forecast-Provider (ABC oder einfache Klassen)
- Interne Coordinator-Struktur für Recorder-Abfragen
- Sensor-Entity Implementierung (SensorEntity Subklassen)
- Solcast vs. Forecast.Solar Entity-ID Mapping (welche Entities liefern was)
- Fehlerbehandlung bei fehlender Recorder-History

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bestehende Integration (Algorithmus-Referenz)
- `custom_components/energieoptimierung/coordinator.py` — VerbrauchsCoordinator: Recorder-Abfrage, Stundendurchschnitte, Zonen-Gruppierung (Pattern übertragbar, aber 7 Tage statt 4 Zonen)
- `custom_components/energieoptimierung/sensor.py` — 15 Sensor-Entities: Tagesprognosen, Verbrauchsprofil, Einzelbedarfe, Update-Timer Pattern (fast/slow)
- `custom_components/energieoptimierung/const.py` — Config-Keys, Defaults, Sensor-Naming

### Neue Integration (Phase 1 Output)
- `custom_components/eeg_energy_optimizer/__init__.py` — async_setup_entry, PLATFORMS forwarding, hass.data Pattern
- `custom_components/eeg_energy_optimizer/const.py` — Domain, Config-Keys, Inverter-Konstanten
- `custom_components/eeg_energy_optimizer/config_flow.py` — Mehrstufiger Config Flow, Entity-Selektoren, Huawei Defaults

### Projekt-Dokumentation
- `.planning/REQUIREMENTS.md` — FCST-01 (Solcast), FCST-02 (Forecast.Solar), FCST-03 (Verbrauchsprofil)
- `.planning/PROJECT.md` — Projektkontext, Constraints, Key Decisions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `coordinator.py`: Recorder-Statistik-Abfrage Pattern (`get_instance(hass).async_add_executor_job` für Statistics API). Algorithmus für Stundendurchschnitte übertragbar, Gruppierung muss von 4 Zonen auf 7 Tage umgebaut werden.
- `sensor.py`: Sensor-Entity Pattern mit `async_track_time_interval` für fast/slow Updates. DeviceInfo für Geräte-Zuordnung.
- `__init__.py` (neue Integration): Platform-Forwarding (`PLATFORMS = ["sensor"]` hinzufügen), hass.data für shared state.

### Established Patterns
- HA `recorder.statistics` API für Long-Term Statistics (hourly)
- `SensorEntity` mit `device_class`, `state_class`, `native_unit_of_measurement`
- `async_track_time_interval` für periodische Updates
- Solcast Solar Entities: `sensor.solcast_pv_forecast_today`, `sensor.solcast_pv_forecast_tomorrow` (mit detaillierten Forecast-Daten als Attribut)
- Forecast.Solar Entities: `sensor.energy_production_today`, `sensor.energy_production_tomorrow`

### Integration Points
- HA Recorder: `from homeassistant.components.recorder import get_instance`
- HA Sun: `from homeassistant.components.sun import STATE_ABOVE_HORIZON` für Sonnenauf-/untergang
- Solcast Solar / Forecast.Solar: Entity-States lesen via `hass.states.get()`
- Phase 1 Config: SOC-Sensor und Kapazitäts-Sensor/kWh aus `entry.data`

### Huawei-Instanz Sensor-Mapping (192.168.1.211)
- Verbrauch: `sensor.power_meter_verbrauch` (22999.99 kWh, total_increasing)
- Aktueller Verbrauch: `sensor.aktueller_verbrauch` (0.275 kW)
- Export: `sensor.power_meter_exportierte_energie` (9551.11 kWh)
- SOC: `sensor.batteries_batterieladung` (7.0%)
- Kapazität: `sensor.batterien_akkukapazitat` (15000 Wh)
- PV: `sensor.inverter_eingangsleistung` (0.607 kW)

</code_context>

<specifics>
## Specific Ideas

- Tagesverbrauchsprognosen heißen "Tagesverbrauchsprognose" (nicht "Prognose Tag X")
- Bestehende coordinator.py als Lese-Referenz für Recorder-Queries, aber eigenständig neu implementieren
- Forecast.Solar wird auf Huawei-Instanz installiert — kann als Live-Test-Quelle dienen
- Solcast auf Fronius-Instanz (192.168.100.211) bereits vorhanden

</specifics>

<deferred>
## Deferred Ideas

- Heizstab/Wallbox/Puffer als abziehbare Verbraucher — könnte in Zukunft als Option kommen
- Erweiterte Statistiken (Median statt Durchschnitt, Ausreißer-Erkennung)
- Energy Dashboard Integration (`state_class` für HA Energy)

</deferred>

---

*Phase: 02-forecasting-consumption-profile*
*Context gathered: 2026-03-21*
