# SolarEdge Modbus Multi einrichten

## 1. Wechselrichter vorbereiten

Modbus TCP muss am Wechselrichter aktiviert sein. Je nach Modell gibt es zwei Varianten:

### SetApp-Wechselrichter (ohne LCD-Display)

1. Roten **DIP-Schalter** am Wechselrichter kurz (< 5 Sek.) auf **„P"** stellen<br>
   _Aktiviert den WiFi-Direct-Hotspot des Wechselrichters._
2. Handy-WLAN mit dem Wechselrichter-Hotspot verbinden (Netzwerkname steht auf dem Gerät)
3. Im Browser `http://172.16.0.1` öffnen
4. **Site Communication** öffnen
5. **Modbus/TCP** aktivieren

> [!WARNING]
> **Zeitfenster:** Die Integration muss sich **innerhalb von 2 Minuten** nach dem Aktivieren verbinden! Danach bleibt der Port offen. Falls zu spät: Modbus TCP aus- und wieder einschalten.

### LCD-Wechselrichter (ältere Modelle)

1. **„OK"** für 5 Sekunden drücken (Installer-Modus)
2. Passwort: `12312312`
3. **Communications → LAN setup** navigieren
4. Modbus/TCP Port konfigurieren

> [!WARNING]
> **Wichtig:** SolarEdge erlaubt nur **EINE Modbus-Verbindung** gleichzeitig! Andere Modbus-Integrationen müssen deaktiviert werden.

## 2. HACS Integration installieren

_**Voraussetzung:** [HACS](https://hacs.xyz/) muss installiert sein._

1. Gehe zu **HACS → Integrationen → Suche „SolarEdge Modbus Multi"**<br>
   _Repository: `WillCodeForCats/solaredge-modbus-multi`_
2. Installiere die Integration und **starte Home Assistant neu**

## 3. Integration konfigurieren

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„SolarEdge Modbus Multi"**
3. Gib die **IP-Adresse** des Wechselrichters ein
4. Port: **1502** (Standard für SolarEdge Modbus TCP)
5. Device ID: **1**

## 4. Speichersteuerung aktivieren

> [!CAUTION]
> **Pflichtschritt!** Ohne diesen Schritt fehlen die Steuerungs-Entities und der EEG Energy Optimizer kann die Batterie nicht steuern.

1. Gehe zu **Einstellungen → Integrationen → SolarEdge Modbus Multi**
2. Klicke auf das **Drei-Punkte-Menü** → **„Konfigurieren"**
3. Aktiviere **„Allow StorEdge Control"** (Speichersteuerung)
4. Speichern und **Integration neu laden**

_Nach dem Neuladen sollten diese Entities erscheinen: `select.*storage_command_mode`, `number.*storage_charge_limit`, `number.*storage_discharge_limit`_

_**Hinweis:** Der EEG Energy Optimizer setzt `storage_control_mode` bei Bedarf automatisch auf „Remote Control" und stellt den Originalzustand danach wieder her._

> [!NOTE]
> **NVRAM-Schreibvorgänge:** SolarEdge speichert Modbus-Registeränderungen im Flash-Speicher (NVRAM). Der EEG Energy Optimizer minimiert Schreibvorgänge: max. ~12 Writes/Tag (Worst Case), an bewölkten Tagen oder im Winter 0 Writes. Realistisch ~7 Writes/Tag im Jahresdurchschnitt → ~39 Jahre bei 100.000 Flash-Zyklen.

## 5. Prüfen

1. Unter **Einstellungen → Integrationen**: SolarEdge Modbus Multi zeigt **„geladen"**
2. **Entwicklerwerkzeuge → Zustände**: `sensor.solaredge_*_b1_state_of_energy` zeigt SOC (0–100%)
3. `select.solaredge_*_storage_command_mode` existiert (= Speichersteuerung aktiv)
4. Kehre hierher zurück — der Wechselrichter wird automatisch erkannt

_**Hinweis:** Der Entity-Prefix variiert je Installation (z.B. `solaredge_i1_` statt `solaredge_`). Der EEG Energy Optimizer erkennt den Prefix automatisch._

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Connection refused** | Modbus TCP nicht aktiviert → Schritt 1 wiederholen |
| **Connection timeout** | Port 1502 prüfen. Bei SetApp: 2-Minuten-Fenster beachten |
| **Keine Batterie-Entities** | Options → „Detect Batteries" aktivieren |
| **Keine Storage-Entities** | „Allow StorEdge Control" in Options nicht aktiviert → Schritt 4 |
| **Verbindung bricht ab** | Nur EINE Modbus-Verbindung möglich — andere Integrationen deaktivieren |
