# SolarEdge Anleitung im Panel — Summary

**Quick Task:** 260406-tg6
**Date:** 2026-04-06
**Status:** Complete

## Was wurde gemacht

### DIALOG_CONTENT.solaredge (90 Zeilen HTML)

5-Schritte-Anleitung analog zum Huawei-Guide:

1. **Wechselrichter vorbereiten** — Modbus TCP aktivieren
   - SetApp-Variante (WiFi Direct → 172.16.0.1 → Modbus TCP)
   - LCD-Variante (OK 5s → Passwort 12312312 → LAN setup)
   - Warnung: 2-Minuten-Fenster bei SetApp, nur 1 Modbus-Verbindung

2. **HACS Integration installieren** — SolarEdge Modbus Multi (WillCodeForCats)

3. **Integration konfigurieren** — IP, Port 1502, Device ID 1

4. **Speichersteuerung aktivieren** — Pflichtschritt!
   - Options → "Allow StorEdge Control" aktivieren
   - Rote Warnung-Box: Ohne diesen Schritt keine Batteriesteuerung
   - Hinweis: Optimizer setzt storage_control_mode automatisch

5. **Prüfen** — Integration geladen, SOC-Entity, storage_command_mode vorhanden

**Häufige Probleme** — 5 Einträge (Connection refused/timeout, keine Batterie/Storage-Entities, Verbindungsabbruch)

### Wizard-Button

Anleitung-Button bei SolarEdge-Karte eingefügt (`data-action="show-dialog" data-dialog="solaredge"`).

### Version Bump

0.6.1 → 0.7.0
