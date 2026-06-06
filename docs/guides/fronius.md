# Fronius Gen24 einrichten

## 1. Fronius Integration in Home Assistant

Die native Fronius Integration wird für das Lesen der Sensoren (PV, Batterie, SOC, Netz) benötigt:

1. Wird normalerweise **automatisch via Auto-Discovery** erkannt<br>
   _Falls nicht: Einstellungen → Geräte & Dienste → Integration hinzufügen → „Fronius"_
2. IP-Adresse des Wechselrichters angeben
3. Die **Solar API** muss im Fronius Web-Interface aktiviert sein (Standard ab FW 1.14.1)

## 2. Modbus TCP am Wechselrichter aktivieren

Der EEG Energy Optimizer steuert die Batterie über Modbus TCP (SunSpec Model 124). Dafür muss Modbus am Wechselrichter aktiviert werden:

1. Fronius Web-Interface öffnen: `http://<IP des Wechselrichters>`
2. **Communication → Modbus → Aktivieren**
3. Mode: **TCP Server**
4. SunSpec Model Type: **int + SF**<br>
   _Wichtig: Nicht „float" wählen — die Register-Adressen unterscheiden sich!_
5. Port: **502** (Standard)
6. **Allow Control via Modbus: EIN**<br>
   _Ohne diese Einstellung werden alle Schreibzugriffe abgelehnt!_

> [!WARNING]
> **Wichtig:** Alle Scheduled (Dis)Charging Zeitpläne im Web-Interface deaktivieren! Modbus und Web-Interface konkurrieren — der höhere Wert gewinnt.

> [!NOTE]
> **Hinweis:** Der Wechselrichter behält Modbus-Einstellungen (z.B. Lade-/Entladesperre) auch nach einem Absturz oder Neustart des Optimizers bei, bis ein neuer Schreibbefehl kommt oder der Wechselrichter selbst neu gestartet wird. Im Normalbetrieb stellt der Optimizer den Ausgangszustand automatisch wieder her.

## 3. Firmware

- **Minimum:** >= 1.34.6-1
- **Empfohlen:** >= 1.40.0

## 4. Prüfen

1. Unter **Einstellungen → Integrationen**: Fronius zeigt **„geladen"**
2. **Entwicklerwerkzeuge → Zustände**: Suche nach `power_photovoltaics` / `pv_leistung` und `state_of_charge` / `ladezustand`
3. Kehre hierher zurück — die Sensoren werden automatisch erkannt

## Häufige Probleme

| Problem | Lösung |
|---|---|
| **Modbus Connection refused** | Modbus TCP nicht aktiviert oder „Allow Control" nicht EIN → Schritt 2 wiederholen |
| **Alle Werte 0 oder unsinnig** | Falscher SunSpec-Modus → „int + SF" statt „float" einstellen |
| **Keine Fronius-Sensoren in HA** | Fronius Integration prüfen: Solar API im Web-Interface aktiviert? |
| **Steuerung funktioniert manchmal nicht** | Scheduled Charging/Discharging im Web-Interface deaktivieren (konkurriert mit Modbus) |
