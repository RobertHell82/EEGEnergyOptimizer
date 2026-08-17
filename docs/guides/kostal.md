# Kostal Plenticore einrichten

## 1. Kostal Plenticore Integration in Home Assistant

Die native Kostal-Integration wird für das Lesen der Sensoren (PV, Batterie, SOC, Netz, Hausverbrauch) benötigt:

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Kostal Plenticore Solar Inverter"**
2. IP-Adresse des Wechselrichters angeben
3. Passwort: das **Anlagenbetreiber-Passwort** des Kostal-Webservers (dasselbe wie beim Login auf `http://<IP des Wechselrichters>`)
4. Service Code: **leer lassen**<br>
   _Das Feld ist optional und nur für den Installer-Modus der Integration gedacht. Der EEG Energy Optimizer benötigt die Integration nur lesend — Anlagenbetreiber-Passwort genügt._

_Bei mehreren Wechselrichtern (z.B. zweiter Plenticore ohne Batterie): die Integration für jedes Gerät separat hinzufügen — ein Config-Eintrag pro Wechselrichter._

## 2. Modbus TCP am Wechselrichter aktivieren

Der EEG Energy Optimizer steuert die Batterie über Modbus TCP. Modbus kann der Anlagenbetreiber selbst aktivieren:

1. Kostal-Webserver öffnen: `http://<IP des Wechselrichters>`, als **Anlagenbetreiber** anmelden
2. **Einstellungen → Modbus / SunSpec (TCP)** → **Modbus aktivieren**
3. Port: **1502** (Standard)
4. Byte-Reihenfolge: **Little-endian (CDAB)** — Werksdefault, nicht ändern!

## 3. Batteriesteuerung auf „Extern über Protokoll" umstellen

Damit der Optimizer die Batterie steuern darf, muss die Batteriesteuerung im Wechselrichter umgestellt werden:

1. **Servicemenü → Batterieeinstellungen**
2. Batteriesteuerung: **„Extern über Protokoll (Modbus TCP)"**
3. Watchdog-Timeout: **60 Sekunden** (falls einstellbar)

> [!CAUTION]
> **Installateur-Zugang erforderlich:** Das Servicemenü ist nur mit Installateur-Login zugänglich (Master Key vom Typenschild + PARAKO-Servicecode, nur für Fachbetriebe). Bitte den Installateur / Solarteur kontaktieren — die Umstellung ist oft per Fernwartung möglich und dauert nur wenige Minuten.

> [!NOTE]
> **Eingebauter Failsafe:** Kostal erwartet zyklische Steuerbefehle (Watchdog). Fällt der Optimizer oder Home Assistant aus, kehrt der Wechselrichter nach dem Timeout automatisch zur internen Batterie-Automatik zurück — die Anlage läuft also nie unkontrolliert weiter.

> [!WARNING]
> **Nur ein steuerndes System:** Es darf immer nur ein System die Batterie über Modbus steuern. Parallelbetrieb mit evcc-Batteriesteuerung oder anderen Modbus-Steuerungen ist nicht möglich. Lesende Zugriffe (z.B. die Kostal-Integration aus Schritt 1) sind unproblematisch.

## 4. Firmware

- **Plenticore G1:** mindestens UI 01.16.05025 / MC 01.44
- **Plenticore G2 / G3:** aktuelle Firmware empfohlen

_Die Firmware-Version ist im Kostal-Webserver unter „Info" sichtbar. Updates macht der Wechselrichter über das Webinterface._

## 5. Prüfen

1. Unter **Einstellungen → Geräte & Dienste**: Kostal Plenticore zeigt **„geladen"** und listet Sensoren
2. **Entwicklerwerkzeuge → Zustände**: Suche nach `battery_soc` / `ladezustand` und `home_power` — die Werte müssen plausibel sein
3. Kehre hierher zurück — die Sensoren werden automatisch erkannt

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Modbus Connection refused** | Modbus TCP nicht aktiviert oder falscher Port → Schritt 2 wiederholen (Port 1502, nicht 502) |
| **Steuerbefehle ohne Wirkung** | Batteriesteuerung steht noch auf „Intern" → Schritt 3 (Installateur) durchführen |
| **Keine Kostal-Sensoren in HA** | Falsches Passwort — es wird das Anlagenbetreiber-Passwort des Webservers benötigt, nicht der Master Key |
| **Alle Werte 0 oder unsinnig** | Byte-Reihenfolge im Webserver verstellt → auf Little-endian (Werksdefault) zurücksetzen |
| **Steuerung reagiert kurz nach Netzstörung nicht** | Nach Netz-Zuschaltung fährt der Wechselrichter ~10 Minuten eine Leistungsrampe (länderabhängig, z.B. Österreich) — in dieser Zeit sind Steuerbefehle gesperrt, der Optimizer wiederholt sie automatisch |
