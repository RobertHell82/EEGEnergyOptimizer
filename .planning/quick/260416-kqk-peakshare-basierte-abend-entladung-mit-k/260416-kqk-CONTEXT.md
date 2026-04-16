# Quick Task 260416-kqk: PeakShare-basierte Abend-Entladung mit konsistenter Begrifflichkeit - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Task Boundary

Konsistente Begrifflichkeit "Abend-Entladung" im gesamten Projekt durchsetzen und PeakShare-API-Integration für bedarfsgesteuerte Entladung implementieren. Checkbox in Settings für PeakShare vs. fixe Startzeit. Community-Auswahl aus API-Daten. Intelligente Fensterberechnung basierend auf verfügbarer Energie und Entladeleistung.

</domain>

<decisions>
## Implementation Decisions

### Begrifflichkeit
- **"Abend-Entladung"** wird als einheitlicher Begriff verwendet
- "Nachteinspeisung", "Nacht-Entladung" und alle Varianten werden ersetzt
- Betrifft: Panel (Wizard, Settings, Dashboard), Optimizer-Logmeldungen, CLAUDE.md
- Bestandteile die bleiben: STATE_ABEND_ENTLADUNG (const.py), "evening" (interner Code-Key)

### PeakShare-Modus (Checkbox)
- Neue Checkbox: "PeakShare-Bedarfssteuerung" — Default: aktiviert (ja)
- Wenn aktiv: Felder "Startzeit der Entladung" und "Entladeleistung" NICHT eingeblendet
- Stattdessen: Community-Dropdown (aus PeakShare API) — "BEG" vorausgewählt
- Wenn deaktiviert: Klassischer Modus mit fixer Startzeit und fixer Leistung (wie bisher)

### PeakShare API
- Endpoint: GET https://peakshare.app/api/public/community-grid-import-forecast
- Alle 6 Stunden abfragen (nicht bei jedem Zyklus)
- Antwort cachen für Fallback bei API-Ausfall (max 24h)
- Wenn Cache abgelaufen UND API nicht erreichbar → Fallback auf fixe Startzeit (Default 20:00)

### Fensterberechnung (Kernlogik)
- Verfügbare Energie (kWh) ÷ Entladeleistung (kW) = benötigte Stunden
- Zusammenhängendes Fenster mit hohem Community-Bedarf finden
- Fenster muss lang genug sein, um die gesamte Energie einzuspeisen
- Wenn kein perfektes Fenster → erstes passendes Fenster nehmen
- **Einmalige Entscheidung**: Rund um Sonnenuntergang wird der Plan festgelegt
- **Kein ständiges An/Aus**: Ein Fenster, durchgehend einspeisen

### Zufallsmechanismus (Jitter)
- ±60 Minuten zufälliger Offset auf den berechneten Startzeitpunkt
- Wird einmalig pro Tag gewürfelt (nicht bei jedem Zyklus)
- Verhindert, dass alle HA-Instanzen gleichzeitig einspeisen

### Entladeleistung
- Konfigurierbar in den Settings, Default: 5 kW
- Beeinflusst die Fensterberechnung (Dauer = Energie ÷ Leistung)

### Fallback-Strategie
- Priorität 1: Aktuelle PeakShare-Daten
- Priorität 2: Gecachte PeakShare-Daten (max 24h alt)
- Priorität 3: Fixe Startzeit aus Konfiguration (Default 20:00)
- User sieht immer ein Startzeit-Feld als Backup (aber nur wenn PeakShare deaktiviert oder als Fallback-Info)

</decisions>

<specifics>
## Specific Ideas

- PeakShare API liefert Communities → Dropdown mit Vorauswahl "BEG"
- 5 kW Standardeinspeisung als konfigurierbarer Default
- Entscheidungszeitpunkt: Sonnenuntergang (oder kurz davor)
- Fensterlogik: z.B. 20 kWh bei 5 kW → 4h Fenster nötig → suche 4h-Block mit höchstem Bedarf

</specifics>

<canonical_refs>
## Canonical References

- PeakShare API: GET https://peakshare.app/api/public/community-grid-import-forecast
- Bestehende Abend-Entladung Logik: custom_components/eeg_energy_optimizer/optimizer.py (_should_discharge)
- Panel Settings: custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
- Konstanten: custom_components/eeg_energy_optimizer/const.py

</canonical_refs>
