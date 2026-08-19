# SMA Smart Energy einrichten

> [!NOTE]
> Unterstützt werden **Sunny Tripower Smart Energy** (STP 5.0–10.0 SE), **Sunny Boy Storage** (SBS 3.7/5.0/6.0) und **Sunny Boy Smart Energy** — jeweils mit Batteriespeicher (z.B. BYD Battery-Box). Sunny Island wird nicht unterstützt.

## 1. SMA Solar Integration in Home Assistant

Die native SMA-Integration wird für das Lesen der Sensoren (PV, Batterie, SOC, Netz) benötigt:

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „SMA Solar"**
2. IP-Adresse des Wechselrichters angeben
3. Gruppe: **Benutzer** (user) genügt — der EEG Energy Optimizer benötigt die Integration nur lesend
4. Passwort: das Benutzer-Passwort des SMA-Webinterface (`https://<IP des Wechselrichters>`)

## 2. Modbus-TCP-Server am Wechselrichter aktivieren

Der EEG Energy Optimizer steuert die Batterie über Modbus TCP. Den Modbus-Server kann der Anlagenbetreiber selbst aktivieren — es ist **kein Grid-Guard-Code nötig**:

1. SMA-Webinterface öffnen: `https://<IP des Wechselrichters>`, als **Installateur** (oder Benutzer mit Parameterrechten) anmelden
2. **Gerätekonfiguration → Externe Kommunikation → Modbus → TCP-Server** → **aktivieren**
3. Port: **502** (Standard, nicht ändern)

Die Unit-ID 3 für die Steuerregister ist im Optimizer fest hinterlegt.

## 3. Sunny Home Manager 2.0 (falls vorhanden)

> [!CAUTION]
> **Prognosebasiertes Laden deaktivieren:** Wenn ein Sunny Home Manager 2.0 verbaut ist, muss dessen **„prognosebasiertes Batterieladen"** in Sunny Portal deaktiviert werden. Sonst steuern zwei Systeme gleichzeitig die Batterie und arbeiten gegeneinander. Ein SMA Energy Meter (ohne Home Manager) ist unproblematisch — er misst nur.

> [!NOTE]
> **Eingebauter Failsafe:** SMA erwartet zyklische Steuerbefehle (Refresh spätestens alle 300 Sekunden). Fällt der Optimizer oder Home Assistant aus, kehrt der Wechselrichter automatisch zur internen Batterie-Automatik zurück — die Anlage läuft also nie unkontrolliert weiter.

> [!WARNING]
> **Nur ein steuerndes System:** Es darf immer nur ein System die Batterie über Modbus steuern. Parallelbetrieb mit evcc-Batteriesteuerung oder anderen Modbus-Steuerungen ist nicht möglich. Lesende Zugriffe (z.B. die SMA-Integration aus Schritt 1) sind unproblematisch.

## 4. Prüfen

1. Unter **Einstellungen → Geräte & Dienste**: SMA Solar zeigt **„geladen"** und listet Sensoren
2. **Entwicklerwerkzeuge → Zustände**: Suche nach `battery_soc_total`, `metering_power_absorbed` und `pv_power` — die Werte müssen plausibel sein
3. Kehre hierher zurück — die Sensoren werden automatisch erkannt

_Hinweis: Der Sensor `sensor.*_grid_power` ist bei SMA die AC-Ausgangsleistung des Wechselrichters, **nicht** der Netzanschlusspunkt. Für die Netzleistung verwendet der Optimizer das Sensorpaar `metering_power_supplied` (Einspeisung) und `metering_power_absorbed` (Bezug)._

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Modbus Connection refused** | Modbus-TCP-Server nicht aktiviert → Schritt 2 wiederholen (Port 502) |
| **Verbindungstest meldet „Steuerregister 40236 nicht lesbar"** | Manche Firmwares nutzen eine abweichende Registeradresse — bitte beim Support melden, bevor die Steuerung aktiviert wird |
| **Keine SMA-Sensoren in HA** | Falsche Gruppe/Passwort bei der SMA-Integration — Benutzer-Zugang des Webinterface verwenden |
| **Batterie lädt trotz Blockierung** | Sunny Home Manager 2.0 steuert noch mit → Schritt 3: prognosebasiertes Laden deaktivieren |
| **Keine Batteriekapazität erkannt** | SMA liefert keinen Kapazitätssensor — die nutzbare Kapazität (z.B. vom BYD-Typenschild) im Wizard manuell eintragen |
