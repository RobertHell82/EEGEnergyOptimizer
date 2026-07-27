# Huawei Solar Integration einrichten

> [!NOTE]
> **EMMA-Energiemanagement:** Wird Home Assistant über das Huawei-EMMA angebunden, tragen die Sensoren den Präfix `sensor.emma_…`. Die EMMA-Einspeiseleistung liefert das Netz-Vorzeichen umgekehrt gegenüber der direkten SUN2000-Anbindung — der EEG Energy Optimizer erkennt solche Sensoren automatisch und dreht das Netz-Vorzeichen entsprechend um (die Batterieleistung folgt der normalen Konvention und bleibt unverändert). Trage die `sensor.emma_*`-Entitäten einfach in der Sensor-Zuordnung ein.

## 1. Wechselrichter vorbereiten

Modbus TCP muss am Wechselrichter aktiviert sein, damit Home Assistant zugreifen kann:

1. Handy-WLAN mit dem Wechselrichter-Hotspot verbinden (`SUN2000-<Seriennummer>`)<br>
   _Passwort steht auf dem Dongle-Aufkleber. Mobile Daten am Handy deaktivieren!_
2. **FusionSolar App** oder **SUN2000 App** öffnen → **Geräte-Inbetriebnahme**
3. Login als **Installer** mit Passwort `00000a`<br>
   _Standard-Passwort (6 Zeichen). Falls geändert: aktuelles Installer-Passwort verwenden._
4. **Einstellungen → Kommunikationskonfiguration → Dongle-Parameter**
5. Modbus-TCP auf **„Aktivieren (uneingeschränkt)"** setzen

## 2. HACS Integration installieren

_**Voraussetzung:** [HACS](https://hacs.xyz/) muss installiert sein._

1. Gehe zu **HACS → Integrationen → Suche „Huawei Solar"**<br>
   _Repository: `wlcrs/huawei_solar`_
2. Installiere die Integration und **starte Home Assistant neu**

## 3. Integration konfigurieren

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„Huawei Solar"**
3. Wähle **Netzwerk** als Verbindungstyp
4. Gib die **IP-Adresse** des Wechselrichters/Dongles ein
5. Port: **6607** (neuere Firmware) oder **502** (ältere Firmware)
6. Slave ID: **1** (Standard, bei Problemen 0 versuchen)
7. **Elevated Permissions: MUSS aktiviert werden!**<br>
   _Ohne Elevated Permissions keine Batteriesteuerung — der EEG Energy Optimizer kann dann nicht steuern._
8. Installer-Passwort: `00000a` eingeben

_**Elevated Permissions vergessen?** Unter Einstellungen → Integrationen → Huawei Solar → Drei-Punkte-Menü → „Neu konfigurieren" nachträglich aktivieren._

## 4. Prüfen

1. Unter **Einstellungen → Integrationen**: Huawei Solar zeigt **„geladen"**
2. **Entwicklerwerkzeuge → Zustände**: `sensor.battery_state_of_capacity` zeigt SOC (0–100%)
3. `number.batteries_maximale_ladeleistung` existiert (= Elevated Permissions aktiv)
4. Kehre hierher zurück — der Wechselrichter wird automatisch erkannt

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Connection refused** | Modbus TCP nicht aktiviert → Schritt 1 wiederholen |
| **Connection timeout** | Port 6607 statt 502 versuchen (oder umgekehrt) |
| **Keine Batterie-Entities** | Elevated Permissions fehlen → neu konfigurieren |
| **Permission denied** | Passwort `00000a` oder `0000000a` (8 Zeichen) versuchen |
| **Verbindung bricht ab** | FusionSolar App komplett schließen, nicht nur minimieren |
