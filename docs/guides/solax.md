# SolaX Modbus einrichten

## 1. Unterstützte Wechselrichter

Nur **Gen4, Gen5 und Gen6** Wechselrichter werden unterstützt. Ältere Generationen (Gen2/Gen3) haben keine Remote Control Funktion.

## 2. Wechselrichter-Einstellungen

Diese Einstellungen müssen am Wechselrichter oder in der SolaX-App korrekt gesetzt sein:

| Einstellung | Wert |
|---|---|
| **Work Mode** | **Self Use** (charger_use_mode = 0) |
| **Night Charge** | **Aus** — sonst lädt die Batterie nachts aus dem Netz |
| **Smart Schedule / Zeitplan** | **Aus** — kollidiert mit der Optimizer-Steuerung |

> [!WARNING]
> **Wichtig:** Der Work Mode darf **NICHT** auf „Feedin Priority" oder „Force Time Use" stehen! Der EEG Energy Optimizer steuert die Batterie über Remote Control (Mode 1) und setzt voraus, dass der Wechselrichter im Self Use Modus läuft.

## 3. HACS Integration installieren

_**Voraussetzung:** [HACS](https://hacs.xyz/) muss installiert sein._

1. Gehe zu **HACS → Integrationen → Suche „SolaX Inverter Modbus"**<br>
   _Repository: `wills106/homeassistant-solax-modbus`_
2. Installiere die Integration und **starte Home Assistant neu**

## 4. Integration konfigurieren

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„SolaX Inverter Modbus"**
3. Gib die **IP-Adresse** des Wechselrichters / WiFi-Dongles ein
4. Port: **502** (Standard für Modbus TCP)
5. Prüfe, dass **„Gen4+ Inverter"** als Typ ausgewählt ist

## 5. Batterie-Kapazität

SolaX stellt **keinen Sensor für die Batteriekapazität** bereit. Die Kapazität gibst du später im Wizard manuell ein (z.B. 5.8 kWh für eine T-BAT 5.8).

## 6. Prüfen

1. Unter **Einstellungen → Integrationen**: SolaX Inverter Modbus zeigt **„geladen"**
2. **Entwicklerwerkzeuge → Zustände**: `sensor.solax_*battery_capacity` zeigt SOC (0–100%)
3. `button.solax_*remotecontrol_trigger` existiert (= Remote Control verfügbar)
4. Kehre hierher zurück — der Wechselrichter wird automatisch erkannt

_**Hinweis:** Der Entity-Prefix variiert je Installation (z.B. `solax_inverter_` statt `solax_`). Der EEG Energy Optimizer erkennt den Prefix automatisch._

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Connection refused** | WiFi-Dongle nicht erreichbar → IP und Netzwerk prüfen |
| **Kein remotecontrol_trigger** | Gen2/Gen3 oder X1 Fit (AC-coupled) → nicht unterstützt |
| **Kommandos ohne Wirkung** | Work Mode auf „Self Use" prüfen, Night Charge und Smart Schedule aus |
| **Batterie lädt trotz Blockierung** | Lock State prüfen — Passwort `2014` zum Entsperren |
| **Sensoren „unavailable" nachts** | Normal — Wechselrichter im Sleep Mode (kein PV, keine Last) |
