# Quick Task 260406-ufh: Einstellungen-Screen statt Wizard nach Setup - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Task Boundary

Nach abgeschlossenem Wizard soll der "Einstellungen"-Button (Zahnrad oben) nicht mehr den Wizard öffnen, sondern einen neuen Settings-Screen mit allen relevanten Einstellungen auf einem Bildschirm. Dazu neue Config-Toggles für Simulation und Manuelle Steuerung, die am Dashboard die Sichtbarkeit der entsprechenden Sections steuern.

</domain>

<decisions>
## Implementation Decisions

### Settings-Layout
- **Sections mit Cards**: Drei separate Karten untereinander:
  1. Expertenmodus-Toggle (eigene kleine Card oben)
  2. Ladung & Einspeisung (alle Felder: Morgen-Verzögerung, Ende-Uhrzeit, Abend-Entladung, Start-Uhrzeit, Leistung, Min-SOC, Sicherheitspuffer)
  3. Erweiterte Einstellungen (Lookback, Update-Intervalle + im Expertenmodus: Simulation-Toggle, Manuelle Steuerung-Toggle)
- Ganz oben: Button "Wizard nochmal starten"

### Wizard-Restart
- **Komplett von Schritt 1**: Der Button startet den Wizard bei "Willkommen" (Schritt 0), damit auch Wechselrichter/Sensoren geändert werden können
- Wizard-Progress aus localStorage wird dabei gelöscht

### Toggle-Sichtbarkeit am Dashboard
- **Komplett ausblenden**: Wenn Simulation bzw. Manuelle Steuerung in den Settings deaktiviert sind (default: false), verschwinden die entsprechenden Dashboard-Cards vollständig
- Cleanes Dashboard für Normal-User, Experten können die Features bei Bedarf einschalten

### Neue Config-Keys
- `enable_simulation` (bool, default: false) — Simulation-Card am Dashboard sichtbar
- `enable_manual_control` (bool, default: false) — Manuelle Steuerung-Card am Dashboard sichtbar
- Beide werden im Config-Entry gespeichert und über WebSocket save_config persistiert

</decisions>

<specifics>
## Specific Ideas

- Der Settings-Screen ist ein neuer View-Modus (neben "dashboard" und "wizard"), z.B. `_view = "settings"`
- Einstellungen-Button im Dashboard-Header öffnet Settings statt Wizard
- Settings-Screen hat eigenen "Zurück"-Button zum Dashboard
- Wizard-Restart-Button im Settings-Screen setzt `_view = "wizard"` mit `_wizardStep = 0`
- Die beiden neuen Toggles werden auch im Wizard Schritt "Erweiterte Einstellungen" angezeigt
- Config-Migration (Version 10) für die neuen Keys mit Default-Werten

</specifics>
