# Quick Task 260406-nv9: Summary

## Changes

**File:** `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js`

### Huawei Anleitung erweitert (von 5 auf 30+ Schritte)
1. **Wechselrichter vorbereiten** — FusionSolar App, Installer-Login (00000a), Modbus TCP aktivieren
2. **Einzelverbindungs-Warnung** — FusionSolar App muss komplett geschlossen sein
3. **HACS Installation** — Hinweis auf HACS-Voraussetzung, Repository wlcrs/huawei_solar
4. **Config Flow** — IP, Port 6607/502, Slave ID, Elevated Permissions (Pflicht!), Installer-Passwort
5. **Verifikation** — 4-Punkte Checkliste (Integration geladen, SOC lesbar, Ladeleistung steuerbar)
6. **Troubleshooting-Tabelle** — 5 häufige Probleme mit Lösungen

### Solcast Azimuth korrigiert
- Vorher: 0°=Nord, 90°=Ost, 180°=Süd, -90°=West (falsch)
- Jetzt: 0°=Nord, -90°=Ost, ±180°=Süd, 90°=West (korrekt)
