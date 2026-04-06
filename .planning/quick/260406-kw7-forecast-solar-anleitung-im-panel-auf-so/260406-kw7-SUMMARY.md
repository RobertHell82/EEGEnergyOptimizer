# Quick Task 260406-kw7: Summary

## Changes

**File:** `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js`

Replaced 3-line Forecast.Solar stub with full setup guide matching Solcast detail level:

1. **Step-by-step Integration setup** — Einstellungen → Geräte & Dienste → Forecast.Solar
2. **Config-Feld Tabelle** — Name, API Key, Lat/Long, Dachneigung, Azimuth, Leistung (kWp in Watt!)
3. **Azimuth-Warnung** — HA nutzt 0°=Nord (Kompass), Forecast.Solar Website nutzt 0°=Süd
4. **Multi-Ausrichtung** — Ost/West → Integration 2x hinzufügen, Sensoren mit `_2` Suffix
5. **Verifikationsschritte** — Entwicklerwerkzeuge → Zustände → energy_production prüfen
6. **Kostenlos-Info** — 12 Abrufe/h, heute+morgen, ausreichend für Optimizer
