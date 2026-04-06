# Huawei Solar Anleitung - Research

**Researched:** 2026-04-06
**Domain:** Huawei SUN2000 inverter setup (hardware + HA integration)
**Confidence:** HIGH

## Summary

Setting up a Huawei SUN2000 inverter for use with the EEG Energy Optimizer requires two distinct phases: (1) enabling Modbus TCP on the inverter itself via the FusionSolar/SUN2000 app, and (2) installing and configuring the `huawei_solar` HACS integration in Home Assistant with "elevated permissions" enabled. Battery control (charge blocking, forced discharge) requires the installer account credentials.

**Primary recommendation:** The panel guide should walk users through both phases sequentially, with clear warnings about the single-connection limitation and the installer password requirement.

## Phase 1: Inverter-Side Configuration (Wechselrichter vorbereiten)

### Voraussetzungen

| Item | Details | Confidence |
|------|---------|------------|
| FusionSolar App oder SUN2000 App | Lokale Verbindung zum Wechselrichter (Phone WiFi) | HIGH |
| Installer-Passwort | Standard: `00000a` (6 Zeichen) oder `0000000a` (8 Zeichen) | HIGH |
| SmartDongle Firmware | Mindestens V100R001C00SPC127 | HIGH |

### Modbus TCP aktivieren

Es gibt mehrere Wege je nach Hardware:

**Weg A: Direkt am Wechselrichter (SUN2000 App / FusionSolar App lokal)**
1. Handy-WLAN mit dem Wechselrichter-Hotspot verbinden (`SUN2000-<Seriennummer>`)
   - WLAN-Passwort steht auf dem Aufkleber am Dongle
   - Achtung: Mobile Daten am Handy deaktivieren, sonst wird der WR nicht gefunden
2. App oeffnen -> "Device Commissioning" / "Geraete-Inbetriebnahme"
3. Login als "Installer" mit Passwort `00000a`
4. Einstellungen -> Kommunikationskonfiguration -> Dongle-Parametereinstellungen
5. Modbus-TCP -> **Aktivieren (uneingeschraenkt)** / "Enable (unrestricted)"

**Weg B: Ueber FusionSolar Portal (remote, wenn SDongle mit Cloud verbunden)**
1. Login auf FusionSolar Portal mit Installer-Account
2. Anlagenmanagement -> Geraeteverwaltung
3. SmartDongle auswaehlen -> "Parameter setzen"
4. Tab "Modbus-TCP" -> Verbindung auf "Aktivieren (uneingeschraenkt)" setzen

**Weg C: Ueber EMMA (wenn EMMA vorhanden)**
1. In EMMA-Einstellungen Modbus TCP aktivieren
2. TLS-Verschluesselung AUS
3. Client-IP auf `0.0.0.0` oder die Home-Assistant-IP setzen

### Verbindungsarten (Hardware)

| Hardware | Verbindung | Port | Hinweise |
|----------|-----------|------|----------|
| Integriertes WLAN | WR im Heimnetz | 6607 | Neuere Firmware; "Local O&M" muss aktiviert sein |
| SDongle-WLAN-FE | Dongle im Heimnetz | 6607 | Blockiert RS485-Pins; nur Modbus-TCP moeglich |
| SDongle-A05 | Dongle im Heimnetz | 6607 | Gleich wie FE |
| EMMA | Ueber EMMA | 502 | TLS deaktivieren |
| WR-Hotspot direkt | 192.168.200.1 | 502 oder 6607 | Nur fuer Tests; HA muesste im WR-WLAN sein |

### Kritische Hinweise (Wechselrichter)

1. **Nur EINE Modbus-Verbindung gleichzeitig**: FusionSolar App und HA koennen NICHT gleichzeitig verbunden sein. FusionSolar App schliessen bevor HA-Integration gestartet wird.
2. **Installer-Passwort**: Standard ist `00000a`. Falls geaendert, muss das aktuelle Passwort verwendet werden. Passwort-Reset ist moeglich ohne Auswirkung auf Cloud-Anbindung.
3. **Dongle-Neustarts**: SDongle startet sich regelmaessig neu wenn er den Default-Gateway nicht pingen kann oder keine Cloud-Verbindung hat. Das unterbricht die HA-Verbindung kurzzeitig.
4. **Port 502 vs 6607**: Neuere Firmware (ab ca. Dezember 2021) verwendet Port 6607 statt 502.

## Phase 2: Home Assistant Integration einrichten

### Installation

1. HACS oeffnen -> Integrationen -> Suche "Huawei Solar" -> Installieren
   - Repository: `wlcrs/huawei_solar`
   - NICHT die alte `Emilv2/huawei_solar` verwenden
2. Home Assistant neu starten
3. Einstellungen -> Integrationen -> "+ Integration hinzufuegen" -> "Huawei Solar"

### Config Flow Schritte

| Schritt | Eingabe | Wert |
|---------|---------|------|
| 1. Verbindungstyp | Netzwerk (Network) | auswaehlen |
| 2. Host | IP-Adresse des Wechselrichters/Dongles | z.B. `192.168.1.100` |
| 3. Port | 502 oder 6607 | je nach Firmware/Hardware |
| 4. Slave ID | 1 (oder 0 bei Problemen) | Standard: 1 |
| 5. Elevated Permissions | **MUSS aktiviert werden** | Haken setzen |
| 6. Installer-Passwort | `00000a` | Standard-Passwort |

### Warum "Elevated Permissions" Pflicht ist

| Ohne Elevated Permissions | Mit Elevated Permissions |
|--------------------------|------------------------|
| Nur Lese-Sensoren (PV-Leistung, Netz, etc.) | Alle Lese-Sensoren + Schreib-Entities |
| Kein Batterie-Zugriff auf Steuerung | `number.batteries_maximale_ladeleistung` verfuegbar |
| Keine Services | `forcible_discharge_soc`, `forcible_charge_soc`, `stop_forcible_charge` |
| **EEG Optimizer kann NICHT steuern** | **EEG Optimizer voll funktionsfaehig** |

### Wichtige Entities nach Setup

**Sensoren (Lesen):**
- `sensor.battery_state_of_capacity` — Batterie-SOC (%)
- `sensor.battery_charge_discharge_power` — Lade/Entladeleistung (W)
- `sensor.inverter_input_power` — PV-Eingangsleistung (W)
- `sensor.power_meter_active_power` — Netzeinspeisung/Bezug (W)

**Steuerung (Schreiben, nur mit Elevated Permissions):**
- `number.batteries_maximale_ladeleistung` — Max. Ladeleistung (W), 0 = Laden blockiert
  - Alternativ: `number.batterien_maximale_ladeleistung` (je nach Sprache/Version)
- Services: `huawei_solar.forcible_discharge_soc`, `huawei_solar.forcible_charge_soc`, `huawei_solar.stop_forcible_charge`

### Nachtraegliches Aktivieren

Falls Elevated Permissions beim Erstsetup vergessen wurde:
1. Einstellungen -> Integrationen -> Huawei Solar -> Drei-Punkte-Menu -> "Neu konfigurieren"
2. "Elevated Permissions" aktivieren und Installer-Passwort eingeben

## Haeufige Probleme & Loesungen

| Problem | Ursache | Loesung |
|---------|---------|---------|
| "Connection refused" | Modbus TCP nicht aktiviert | Phase 1 wiederholen, Modbus-TCP auf "unrestricted" setzen |
| "Connection timeout" | Falscher Port oder IP | Port 6607 statt 502 versuchen; IP pruefen |
| Verbindung bricht nach ~30 Min ab | Dongle-Neustart | WR komplett aus/ein (DC dann AC); Gateway-Ping sicherstellen |
| Keine Batterie-Entities | Elevated Permissions fehlen | Neu konfigurieren mit Elevated Permissions |
| "Permission denied" | Falsches Installer-Passwort | `00000a` oder `0000000a` versuchen |
| Slave ID Fehler | Falsche COM-Adresse | Slave ID 0 oder 1 versuchen |
| FusionSolar App blockiert | Gleichzeitige Verbindung | App komplett schliessen (nicht nur minimieren) |

## Validierung nach Setup

### Checkliste fuer den Benutzer

1. **Integration geladen?** Einstellungen -> Integrationen -> Huawei Solar zeigt "geladen"
2. **Batterie-SOC lesbar?** `sensor.battery_state_of_capacity` hat einen Wert (0-100)
3. **Ladeleistung steuerbar?** `number.batteries_maximale_ladeleistung` existiert und hat min/max Attribute
4. **Services verfuegbar?** Entwicklerwerkzeuge -> Services -> `huawei_solar.forcible_discharge_soc` ist aufgelistet
5. **EEG Optimizer Verbindungstest?** Im EEG Optimizer Panel -> Wechselrichter-Test erfolgreich

## Entity-Mapping fuer EEG Optimizer

| EEG Optimizer Config Key | Huawei Solar Entity | Hinweis |
|--------------------------|---------------------|---------|
| `battery_soc_sensor` | `sensor.battery_state_of_capacity` | Auto-Detect |
| `pv_power_sensor` | `sensor.inverter_input_power` | Auto-Detect |
| `battery_power_sensor` | `sensor.battery_charge_discharge_power` | Auto-Detect |
| `grid_power_sensor` | `sensor.power_meter_active_power` | Auto-Detect |
| `huawei_device_id` | Device ID aus Device Registry | Auto-Detect |

## Sources

### Primary (HIGH confidence)
- [wlcrs/huawei_solar GitHub](https://github.com/wlcrs/huawei_solar) - README, setup flow, services
- [wlcrs/huawei_solar Wiki: Connecting](https://github.com/wlcrs/huawei_solar/wiki/Connecting-to-the-inverter) - Port, connection types, troubleshooting
- [wlcrs/huawei_solar Wiki: Force charge/discharge](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery) - Battery control services

### Secondary (MEDIUM confidence)
- [Huawei Modbus TCP Official Docs](https://support.huawei.com/enterprise/en/doc/EDOC1100518312/2ca63b29/modbus-tcp) - Official Modbus TCP setup
- [Huawei FusionSolar Commissioning Guide](https://support.huawei.com/enterprise/en/doc/EDOC1100273864) - Installer mode, app setup
- [evcc Discussion #2868](https://github.com/evcc-io/evcc/discussions/2868) - Modbus TCP troubleshooting, SDongle details

### Tertiary (LOW confidence)
- [elektroda.com Forum](https://www.elektroda.com/rtvforum/topic3721385-960.html) - Community firmware/dongle experiences

## Metadata

**Confidence breakdown:**
- Inverter-side setup: HIGH - verified with official Huawei docs + wlcrs wiki
- HA integration setup: HIGH - verified with GitHub README + wiki
- Entity names: MEDIUM - confirmed via code but entity IDs can vary by language/version
- Troubleshooting: MEDIUM - community-sourced, verified across multiple sources

**Research date:** 2026-04-06
**Valid until:** 2026-07-06 (stable domain, slow-moving)
