# Fronius Gen24 Umsetzungskonzept - Research

**Researched:** 2026-04-12
**Domain:** Fronius Gen24 inverter integration (sensors + battery control) for EEG Energy Optimizer
**Confidence:** HIGH (Modbus control), MEDIUM (Solar API control), HIGH (sensor reading)

## Summary

The Fronius Gen24 with BYD HVS/HVM battery can be integrated into the EEG Energy Optimizer through multiple paths. For **reading sensors**, the native Home Assistant Fronius integration (Solar API) provides all needed entities (PV power, battery power/SOC, grid power). For **writing/controlling the battery**, Modbus TCP via SunSpec Model 124 is the most reliable and well-proven method, with the HACS custom component `fronius_modbus` (redpomodoro or callifo fork) providing HA-native entity access to the control registers.

The Solar API (HTTP/JSON) is **read-only** and cannot control battery charging/discharging. There is an undocumented Web API endpoint (`/config/batteries` or `/config/timeofuse`) used by projects like batcontrol and OpenHAB, but it is not officially documented, has been broken by firmware updates (1.38+), and requires complex CSRF/session authentication -- making it unsuitable as a primary control path.

**Primary recommendation:** Use the native HA Fronius integration for reading sensors + the `fronius_modbus` HACS custom component (callifo fork) for battery control via Modbus TCP SunSpec Model 124 registers.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Implementation Decisions
- Alle Wege vergleichen: HA Fronius-Integration, Modbus TCP direkt, Fronius Solar API
- Pro/Contra-Vergleich mit Empfehlung
- Fokus auf Praxistauglichkeit fuer den EEG Energy Optimizer Use-Case
- BYD HVS/HVM als Referenz-Setup (gaengigste Kombination mit Gen24)
- Konzept soll Batterie-Steuerung ueber den Wechselrichter abbilden, nicht direkt zur Batterie
- Praxistauglich detailliert: Konkrete Entity-IDs, Modbus-Register oder API-Endpoints mit Parametern
- So dass man direkt damit implementieren koennte
- Keine Code-Snippets oder Timing-Diagramme noetig, aber konkrete technische Details

### Specific Ideas
- Mapping auf die bestehende InverterBase-Abstraktion
- Vergleich mit der bestehenden Huawei/SolaX/SolarEdge-Implementierung
- Besonderheiten des Fronius Gen24 bei der Batteriesteuerung beachten
</user_constraints>

---

## 1. Lesende Sensoren (Reading Sensors)

### 1.1 Native HA Fronius Integration (Solar API)

Die native Home Assistant Fronius Integration nutzt die Fronius Solar API v1 (HTTP/JSON) und kommuniziert ueber lokale HTTP-Requests. Sie ist **rein lesend** -- keine Steuerungsfunktionen. [VERIFIED: home-assistant.io/integrations/fronius]

**Voraussetzung:** Solar API muss im Fronius Web-Interface aktiviert sein (Firmware >= 1.14.1). [VERIFIED: HA Fronius docs]

#### Power Flow Sensoren (Update alle 10 Sekunden)

| HA Entity Key | Beschreibung | Einheit | Vorzeichen |
|---|---|---|---|
| `power_photovoltaics` | PV-Erzeugungsleistung | W | immer positiv |
| `power_battery` | Batterie-Leistung (kombiniert) | W | + Entladung / - Ladung |
| `power_battery_charge` | Batterie-Ladeleistung | W | positiv |
| `power_battery_discharge` | Batterie-Entladeleistung | W | positiv |
| `power_grid` | Netz-Leistung | W | + Einspeisung / - Bezug |
| `power_grid_import` | Netz-Bezug | W | positiv |
| `power_grid_export` | Netz-Einspeisung | W | positiv |
| `power_load` | Hausverbrauch (kombiniert) | W | + Verbrauch / - Erzeugung |
| `relative_autonomy` | Autarkiequote | % | 0-100 |
| `relative_self_consumption` | Eigenverbrauchsquote | % | 0-100 |
| `energy_day` | Tagesenergie | Wh | kumulativ |
| `energy_total` | Gesamtenergie | Wh | kumulativ |

[VERIFIED: HA core source code homeassistant/components/fronius/sensor.py]

#### Storage/Batterie Sensoren (Update jede Minute)

| HA Entity Key | Beschreibung | Einheit |
|---|---|---|
| `state_of_charge` | Batterie-Ladestand (SOC) | % |
| `capacity_maximum` | Maximale Kapazitaet | Wh |
| `capacity_designed` | Design-Kapazitaet | Wh |
| `current_dc` | Batterie-Strom | A |
| `voltage_dc` | Batterie-Spannung | V |
| `temperature_cell` | Zell-Temperatur | C |

[VERIFIED: HA core source code homeassistant/components/fronius/sensor.py]

#### Entity-Namensschema

Die tatsaechlichen Entity-IDs folgen dem Muster:
```
sensor.{device_name}_{key}
```

Typische Beispiele (IP-abhaengig):
- `sensor.solarnet_power_battery` oder `sensor.power_battery_fronius_power_flow_0_{IP}`
- `sensor.solarnet_power_photovoltaics`
- `sensor.solarnet_power_grid`
- `sensor.byd_battery_box_premium_hv_state_of_charge`

**Wichtig:** Der genaue Praefix haengt von der HA-Installation und dem Geraete-Discovery ab. [VERIFIED: HA community forums]

#### Mapping auf EEG Optimizer Sensor-Anforderungen

| EEG Optimizer Config Key | Fronius Native Entity | Anmerkung |
|---|---|---|
| `pv_power_sensor` | `sensor.{prefix}_power_photovoltaics` | W, muss in kW umgerechnet werden |
| `battery_power_sensor` | `sensor.{prefix}_power_battery` | W, + Entladung / - Ladung (gleiche Konvention wie Huawei) |
| `battery_soc_sensor` | `sensor.{prefix}_state_of_charge` | %, vom Storage-Device |
| `grid_power_sensor` | `sensor.{prefix}_power_grid` | W, + Einspeisung / - Bezug |
| `battery_capacity` | `sensor.{prefix}_capacity_maximum` | Wh, muss in kWh umgerechnet werden |

[ASSUMED: Mapping basiert auf bestehender Sensor-Konfigurationslogik im EEG Optimizer]

### 1.2 Fronius Solar API v1 (direkt)

Die Solar API v1 liefert JSON-Daten ueber HTTP GET:

**Hauptendpoint:** `http://{IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi`

Antwort-Struktur:
```json
{
  "Body": {
    "Data": {
      "Site": {
        "P_Akku": -1234.5,
        "P_Grid": 567.8,
        "P_Load": -890.1,
        "P_PV": 2345.6,
        "rel_Autonomy": 85.0,
        "rel_SelfConsumption": 60.0
      },
      "Inverters": {
        "1": {
          "Battery_Mode": "normal",
          "SOC": 75.0,
          "P": 2345.6,
          "E_Total": 12345678
        }
      }
    }
  }
}
```

**Storage-Endpoint:** `http://{IP}/solar_api/v1/GetStorageRealtimeData.cgi?Scope=System`
(Verfuegbar ab Firmware 1.13) [VERIFIED: community forum + Fronius docs]

**Authentifizierung:** Nicht erforderlich fuer lesende Zugriffe. [VERIFIED: Fronius Solar API docs]

**Fazit Sensoren:** Die native HA Fronius Integration reicht fuer alle lesenden Sensoren vollstaendig aus. Kein Grund, die Solar API direkt anzusprechen.

### 1.3 Modbus TCP (SunSpec)

Alternativ koennen Sensoren auch ueber Modbus TCP gelesen werden:

| Register (int+SF) | Beschreibung | SunSpec Model |
|---|---|---|
| 40345 | WChaMax (Max Lade-/Entladeleistung) | 124 |
| 40349 | ChaState (SOC in %) | 124 |
| 40351 | ChaSt (Betriebsstatus) | 124 |
| 30845 | Battery SOC | System |
| 30775 | Battery Power | System |

[VERIFIED: Fronius Modbus documentation + libe.net + iobroker forum]

**Fazit:** Modbus-Lesen ist fuer den EEG Optimizer nicht noetig, da die native HA Integration alle Werte liefert. Modbus wird nur fuer die Steuerung benoetigt.

---

## 2. Wechselrichter-Ansteuerung (Battery Control) -- KERNTHEMA

### 2.1 Methode A: Home Assistant Native Fronius Integration

**Ergebnis: KEINE Steuerungsfunktionen vorhanden.** [VERIFIED: HA Fronius docs]

Die offizielle HA Fronius Integration nutzt die Solar API, die **explizit read-only** ist:
> "The Solar API used by this integration is read-only. It does not provide any means to control the Fronius devices."

- Keine HA Services fuer Batterie-Steuerung
- Keine number/select Entities zum Schreiben
- Keine Plaene, Steuerung hinzuzufuegen (Solar API Limitation)

**Bewertung: Nicht geeignet fuer Batterie-Steuerung.**

### 2.2 Methode B: Modbus TCP (SunSpec Model 124) -- EMPFOHLEN

#### Voraussetzungen

1. **Modbus TCP aktivieren** im Fronius Web-Interface:
   - Communication > Modbus > Aktivieren
   - Mode: TCP Server
   - SunSpec Model Type: **int + SF** (wichtig!)
   - Port: 502 (Standard) oder 1502
   - **Allow Control: ON** (ohne dies scheitern Schreibzugriffe)
   - Scheduled (dis)charging im Web-UI deaktivieren (Konfliktvermeidung)
2. **Firmware >= 1.34.6-1** empfohlen (aeltere Versionen haben bekannte Bugs bei Ladeleistungs-Begrenzung)
3. **Battery Management** im Fronius Web-Interface aktiviert

[VERIFIED: Fronius Modbus documentation + redpomodoro/fronius_modbus + libe.net]

#### SunSpec Model 124 -- Storage Control Register

**Startadresse Model 124:** 40343 (int+SF) bzw. 40353 (float) [VERIFIED: Fronius Modbus manual]

**WICHTIG: Register-Adressen sind dynamisch.** Die unten genannten Adressen gelten fuer die typische Konfiguration. Die tatsaechlichen Adressen haengen von der Zusammensetzung der SunSpec Register-Liste ab und muessen beim ersten Zugriff ueber SunSpec Model Discovery ermittelt werden. [VERIFIED: Fronius Modbus manual]

| Register | Offset | Name | Typ | R/W | Beschreibung |
|---|---|---|---|---|---|
| 40345 | +2 | WChaMax | uint16 | R | Max. Lade-/Entladeleistung in W |
| 40348 | +5 | StorCtl_Mod | bitfield16 | **RW** | Steuermodus: Bit 0=Charge Limit, Bit 1=Discharge Limit |
| 40349 | +6 | ChaState | uint16 | R | SOC in % (mit SF) |
| 40350 | +7 | MinRsvPct | uint16 | **RW** | Mindest-Reserve in % (mit SF) |
| 40351 | +8 | ChaSt | enum16 | R | Status: OFF/EMPTY/DISCHARGING/CHARGING/FULL/HOLDING |
| 40355 | +12 | OutWRte | int16 | **RW** | Entlade-Limit in % von WChaMax (SF -2, d.h. 10000 = 100%) |
| 40356 | +13 | InWRte | int16 | **RW** | Lade-Limit in % von WChaMax (SF -2, d.h. 10000 = 100%) |
| 40357 | +14 | ChaGriSet | enum16 | **RW** | Netzladung erlauben/verbieten |
| 40364 | +21 | InOutWRte_SF | sunssf | R | Scale Factor fuer InWRte/OutWRte = -2 |

[VERIFIED: Fronius Modbus documentation + libe.net/en/byd-modbus + multiple community sources]

**Hinweis zu Register-Adressen:** Die obigen Adressen stammen aus verschiedenen Quellen und koennen je nach Firmware-Version und aktivierten SunSpec-Modellen leicht variieren. Einige Quellen berichten StorCtl_Mod auf 40319 oder 40359 -- das liegt an unterschiedlichen Firmware-Versionen und aktivierten Modellen. Die `fronius_modbus` HACS-Integration loest dieses Problem automatisch durch SunSpec Model Discovery. [MEDIUM confidence]

#### Steuerungssequenzen

**Ladung blockieren (Morgen-Einspeisung):**
1. `StorCtl_Mod` = 1 (Bit 0: Charge Limit aktiv)
2. `InWRte` = 0 (0% Ladeleistung = keine Ladung)
3. Ergebnis: PV-Ueberschuss geht ins Netz statt in die Batterie

**Entladung erzwingen (Abend-Entladung):**
1. `StorCtl_Mod` = 3 (Bits 0+1: Charge + Discharge Limit aktiv)
2. `OutWRte` = 10000 (100% Entladeleistung = volle Entladung)
3. `InWRte` = 0 (Ladung weiterhin blockiert)
4. Optional: `MinRsvPct` setzen fuer Mindest-SOC
5. Ergebnis: Batterie entlaedt mit maximaler Leistung ins Netz

**Normalbetrieb wiederherstellen:**
1. `StorCtl_Mod` = 0 (Keine Limits aktiv)
2. `InWRte` = 10000 (100% = unbegrenzt)
3. `OutWRte` = 10000 (100% = unbegrenzt)
4. `MinRsvPct` auf Standardwert (z.B. 500 = 5%)
5. Ergebnis: Wechselrichter arbeitet im Automatik-Modus

[VERIFIED: Fronius Modbus documentation + libe.net/en/byd-modbus + community implementations]

#### Besonderheit: Prozentwerte statt Absolutwerte

Anders als bei Huawei (Watt direkt) oder SolaX (Watt direkt) arbeitet der Fronius Gen24 mit **Prozentwerten relativ zu WChaMax**:
- InWRte/OutWRte sind Prozentwerte (0-10000 mit SF -2, also 0-100%)
- Die tatsaechliche Leistung wird berechnet: `power_w = WChaMax * (InWRte / 10000)`
- Fuer den EEG Optimizer bedeutet das: Wenn `async_set_discharge(power_kw)` aufgerufen wird, muss der Prozentwert berechnet werden: `percent = min(power_kw * 1000 / WChaMax * 10000, 10000)`

[VERIFIED: SunSpec specification + Fronius Modbus documentation]

#### Wettbewerb mit Web-Interface-Einstellungen

> "The value set via Modbus competes with the settings in the Fronius web interface: the higher value wins."

Das bedeutet: Wenn im Web-Interface ein Lade-Limit von 50% konfiguriert ist und per Modbus 0% gesetzt wird, gewinnt der Web-Interface-Wert (50%). Daher muss der Benutzer in der Anleitung darauf hingewiesen werden, scheduled (dis)charging im Web-UI zu deaktivieren. [VERIFIED: Fronius Modbus documentation]

### 2.3 Methode B2: Modbus via `fronius_modbus` HACS-Integration

Statt direkt mit pymodbus auf die Register zuzugreifen, kann die HACS Custom Component `fronius_modbus` verwendet werden, die HA-native Entities bereitstellt.

#### Variante 1: redpomodoro/fronius_modbus
- **GitHub:** https://github.com/redpomodoro/fronius_modbus
- **Version:** v0.1.9 (September 2025), 99 Stars
- **Status:** "Early development, breaking changes possible"
- **Entities fuer Batterie-Steuerung:**

| Entity-Typ | Entity-Key | Beschreibung |
|---|---|---|
| select | Storage Control Mode | Auto / PV Charge Limit / Discharge Limit / PV Charge and Discharge Limit / Charge from Grid / Discharge to Grid / Block discharging / Block charging |
| number | PV Charge Limit | Max. PV-Ladeleistung (W) |
| number | Discharge Limit | Max. Entladeleistung (W) |
| number | Grid Charge Power | Netz-Ladeleistung (W) |
| number | Grid Discharge Power | Netz-Entladeleistung (W) |
| number | Minimum Reserve | Mindest-Reserve (%) |
| sensor | State of Charge | SOC (%) |
| sensor | Charge Status | Holding/Charging/Discharging |

[VERIFIED: redpomodoro/fronius_modbus README]

#### Variante 2: callifo/fronius_modbus (Fork)
- **GitHub:** https://github.com/callifo/fronius_modbus
- **Version:** v0.2.9 (Maerz 2026), 251 Commits, 27 Releases
- **Status:** Aktiv entwickelt, "Modbus-first + authenticated Web API"
- **Besonderheit:** Nutzt sowohl Modbus als auch die authentifizierte Web API
- **Firmware-Empfehlung:** >= 1.40.0
- **Mehr Entities und Features als das Original**

[VERIFIED: callifo/fronius_modbus GitHub]

#### Steuerung ueber fronius_modbus Entities

Fuer den EEG Optimizer waere der Integrationsweg analog zu SolaX/SolarEdge:

**Ladung blockieren:**
```
select.select_option: "Block charging"  (Storage Control Mode)
```

**Entladung erzwingen:**
```
select.select_option: "Discharge to Grid"  (Storage Control Mode)
number.set_value: {power_w}  (Grid Discharge Power)
```

**Normalbetrieb:**
```
select.select_option: "Auto"  (Storage Control Mode)
```

[ASSUMED: Basierend auf fronius_modbus Entity-Beschreibungen, nicht selbst getestet]

### 2.4 Methode C: Fronius Solar API v1 (HTTP) -- Lesend

Die offizielle Solar API v1 ist **rein lesend**. Keine Steuerungsfunktionen. [VERIFIED: Fronius docs + HA docs]

### 2.5 Methode D: Undokumentierte Fronius Web API -- NICHT EMPFOHLEN

Es existiert eine undokumentierte Web API fuer Batterie-Steuerung, die im Web-Interface des Gen24 verwendet wird:

**Endpoint:** `http://{IP}/config/batteries` oder `/config/timeofuse`
**Methode:** POST
**Authentifizierung:** Digest-Auth (MD5 bis FW 1.37, SHA-256 ab FW 1.38) + CSRF-Token + Session

**ScheduleType-Werte:**
- `DISCHARGE_MAX` -- Maximale Entladung (Entladung erzwingen)
- `CHARGE_MAX` -- Maximale Ladung
- `DISCHARGE_MIN` -- Minimale Entladung
- `CHARGE_MIN` -- Minimale Ladung

**TimeOfUse Payload-Struktur:**
```json
[{
  "Active": true,
  "Power": 0,
  "ScheduleType": "DISCHARGE_MAX",
  "TimeTable": {"Start": "06:00", "End": "10:00"},
  "Weekdays": {"Mon": true, "Tue": true, ...}
}]
```

[VERIFIED: OpenHAB Fronius binding + batcontrol project + evcc discussions]

**Projekte die diese API nutzen:**
- **batcontrol** (muexxl/batcontrol) -- Python, laeuft standalone
- **OpenHAB Fronius Binding** -- Java, bietet Aktionen wie `holdBatteryCharge()`, `forceBatteryDischarging(power)`, `resetBatteryControl()`
- **sbam** (HA Add-on) -- Fronius-spezifisch

[VERIFIED: GitHub projects]

**SCHWERWIEGENDE PROBLEME:**
1. **Nicht dokumentiert:** Fronius kann die API jederzeit aendern/entfernen
2. **Firmware-Breaking-Changes:** FW 1.38 hat Auth von MD5 auf SHA-256 umgestellt, FW 1.39 hat bei vielen Nutzern die Battery-Control-API gebrochen ("alg not implemented" Fehler)
3. **Nicht-standardkonforme Header:** Fronius sendet `X-WWW-Authenticate` statt `WWW-Authenticate`
4. **CSRF-Token erforderlich:** Ab FW 1.38 muss ein CSRF-Token + Session-Cookie mitgesendet werden
5. **Benutzer-Credentials erforderlich:** Login-Daten des Fronius Web-Interface noetig

[VERIFIED: evcc issues + Photovoltaikforum + batcontrol issues]

**Bewertung: Nicht empfohlen als primaerer Steuerungsweg.** Zu fragil, Firmware-Updates koennen Integration jederzeit brechen.

---

## 3. Vergleich der Methoden

### 3.1 Uebersichtstabelle

| Kriterium | HA Native (Solar API) | Modbus direkt (pymodbus) | fronius_modbus (HACS) | Undok. Web API |
|---|---|---|---|---|
| **Sensoren lesen** | Ja (vollstaendig) | Ja (aufwendig) | Ja (vollstaendig) | Nur ueber Solar API |
| **Ladung blockieren** | NEIN | Ja (StorCtl_Mod + InWRte) | Ja ("Block charging") | Ja (DISCHARGE_MAX) |
| **Entladung erzwingen** | NEIN | Ja (StorCtl_Mod + OutWRte) | Ja ("Discharge to Grid") | Ja (CHARGE_MAX = 0) |
| **Normalbetrieb** | -- | Ja (StorCtl_Mod = 0) | Ja ("Auto") | Ja (resetBatteryControl) |
| **HA-nativ** | Ja | Nein (eigene Modbus-Lib) | Ja (Entities) | Nein (HTTP-Calls) |
| **Zuverlaessigkeit** | Hoch | Hoch | Mittel (WIP) | Niedrig |
| **Firmware-Stabilitaet** | Hoch (offizielle API) | Hoch (SunSpec Standard) | Hoch (SunSpec) | Niedrig (breaking changes) |
| **Auth noetig** | Nein | Nein | Nein | Ja (Digest + CSRF) |
| **Community-Support** | Sehr hoch (Core) | Mittel | Mittel-Hoch (99-251 Stars) | Gering |
| **Installationsaufwand** | Gering (Auto-Discovery) | Hoch (pymodbus als Dep.) | Mittel (HACS) | Hoch (Credentials, CSRF) |
| **Koexistenz mit Native** | -- | Ja (verschiedene Ports/Protokolle) | Ja (Modbus != Solar API) | Ja |

### 3.2 Empfehlung

**Primaerer Weg: fronius_modbus HACS-Integration (callifo Fork)**

Gruende:
1. Bietet HA-native Entities (select/number) fuer Batterie-Steuerung
2. Basiert auf standardisiertem SunSpec/Modbus (firmware-stabil)
3. Aktiv entwickelt (v0.2.9, Maerz 2026, 251 Commits)
4. Kann neben der nativen HA Fronius Integration koexistieren (Solar API HTTP vs. Modbus TCP)
5. Steuerung analog zu SolaX/SolarEdge-Implementierung (select + number Entities)

**Alternativer Weg: Direkte Modbus TCP Steuerung (pymodbus)**

Falls die HACS-Integration Probleme bereitet oder nicht gewuenscht ist:
1. Direkte Modbus-Register-Zugriffe ueber pymodbus
2. Volle Kontrolle, keine Abhaengigkeit von Drittanbieter-Integration
3. Hoehere Komplexitaet: SunSpec Model Discovery, Register-Berechnung, pymodbus-Dependency
4. Vergleichbar mit dem Ansatz von `fronius-modbus-controller` (jtbnz)

**Nicht empfohlen: Undokumentierte Web API** -- zu fragil, Firmware-Abhaengigkeit, komplexe Auth.

---

## 4. Mapping auf InverterBase

### 4.1 Weg A: Via fronius_modbus HACS Entities (empfohlen)

Die Implementierung waere analog zur bestehenden SolaX- und SolarEdge-Implementierung, die ebenfalls HA-Entities ansteuern.

#### async_set_charge_limit(power_kw)

**Morgen-Einspeisung (power_kw = 0):**
```
1. select.select_option("Block charging") auf Storage Control Mode Entity
   -> Setzt StorCtl_Mod Bit 0, InWRte = 0
```

**Teilweise Ladung (power_kw > 0):**
```
1. select.select_option("PV Charge Limit") auf Storage Control Mode Entity
2. number.set_value(power_kw * 1000) auf PV Charge Limit Entity
```

Analog zu: SolaX `async_set_charge_limit` (select + number + trigger)

#### async_set_discharge(power_kw, target_soc)

**Abend-Entladung:**
```
1. select.select_option("Discharge to Grid") auf Storage Control Mode Entity
2. number.set_value(power_kw * 1000) auf Grid Discharge Power Entity
3. Optional: number.set_value(target_soc) auf Minimum Reserve Entity
```

Analog zu: SolarEdge `async_set_discharge` (command_mode + discharge_limit)

#### async_stop_forcible()

**Normalbetrieb:**
```
1. select.select_option("Auto") auf Storage Control Mode Entity
   -> Setzt StorCtl_Mod = 0, InWRte/OutWRte = 10000
```

Analog zu: SolaX `async_stop_forcible` ("Disabled" + trigger) oder SolarEdge (Maximize Self Consumption)

#### is_available

```
Pruefen ob fronius_modbus Integration geladen ist:
  entries = hass.config_entries.async_entries("fronius_modbus")
  return any(entry.state.value == "loaded" for entry in entries)
```

Analog zu: Alle bestehenden Implementierungen (Domain-Check)

### 4.2 Weg B: Via direkte Modbus TCP Schreibzugriffe

Falls pymodbus direkt verwendet wird (ohne fronius_modbus HACS):

#### async_set_charge_limit(power_kw)

```
1. Verbindung zu Fronius IP:502 (Modbus TCP)
2. SunSpec Model 124 Startadresse ermitteln (Model Discovery)
3. write_register(StorCtl_Mod_addr, 1)  # Bit 0: Charge Limit aktiv
4. write_register(InWRte_addr, 0)  # 0% Ladung = blockiert
```

#### async_set_discharge(power_kw, target_soc)

```
1. WChaMax lesen von Register
2. percent = min(power_kw * 1000 / WChaMax * 10000, 10000)
3. write_register(StorCtl_Mod_addr, 3)  # Bits 0+1: Charge + Discharge aktiv
4. write_register(InWRte_addr, 0)  # Ladung blockiert
5. write_register(OutWRte_addr, int(percent))  # Entladung in %
6. Optional: write_register(MinRsvPct_addr, int(target_soc * 100))  # Mindest-SOC
```

#### async_stop_forcible()

```
1. write_register(StorCtl_Mod_addr, 0)  # Keine Limits
2. write_register(InWRte_addr, 10000)  # 100% Ladung erlaubt
3. write_register(OutWRte_addr, 10000)  # 100% Entladung erlaubt
```

### 4.3 Vergleich mit bestehenden Implementierungen

| Aspekt | Huawei | SolaX | SolarEdge | Fronius (HACS) | Fronius (direkt) |
|---|---|---|---|---|---|
| **Steuerungsweg** | HA Services (huawei_solar) | HA Entities (solax_modbus) | HA Entities (solaredge_modbus_multi) | HA Entities (fronius_modbus) | pymodbus direkt |
| **Ladung blockieren** | number.set_value(0) auf Max-Charge | select("Battery Control") + active_power(0) | select("Discharge Minimize Import") | select("Block charging") | StorCtl_Mod=1, InWRte=0 |
| **Entladung** | Service forcible_discharge_soc | select("Battery Control") + negative active_power | select("Discharge Maximize Export") + discharge_limit | select("Discharge to Grid") + power | StorCtl_Mod=3, OutWRte=% |
| **Stop** | stop_forcible_charge + restore max | select("Disabled") + trigger | Restore original modes | select("Auto") | StorCtl_Mod=0, InWRte/OutWRte=10000 |
| **Persistenz** | Nein (timeout) | Nein (autorepeat timer) | Ja (NVRAM!) | Nein (Modbus-Werte nicht persistent) | Nein |
| **Leistungsangabe** | Watt (direkt) | Watt (direkt) | Watt (direkt) | Watt (Entity) | Prozent von WChaMax |
| **HA-Dependency** | huawei_solar | solax_modbus | solaredge_modbus_multi | fronius_modbus | Keine (pymodbus) |
| **Entity-Prefix variabel** | Nein (bekannte IDs) | Ja (konfigurierbar) | Ja (konfigurierbar) | Ja (konfigurierbar) | -- |

### 4.4 Besonderheiten Fronius Gen24

1. **Prozentwerte statt Watt:** InWRte/OutWRte sind Prozentwerte, nicht absolute Watt-Angaben. Die fronius_modbus Integration abstrahiert das teilweise (Entities in Watt), aber die direkte Modbus-Variante muss umrechnen.

2. **Keine Auto-Revert:** Anders als Huawei (Timeout) und SolaX (Autorepeat-Timer) revertiert der Fronius Gen24 Modbus-Einstellungen **nicht** automatisch. Wie bei SolarEdge muss `async_stop_forcible()` zuverlaessig aufgerufen werden. Bei Absturz der Integration bleiben die Modbus-Werte bestehen bis zum naechsten Schreibzugriff oder WR-Neustart. [ASSUMED: basierend auf Modbus-Semantik, nicht explizit verifiziert fuer Fronius]

3. **Konkurrierende Einstellungen:** Fronius Web-Interface und Modbus konkurrieren -- der hoehere Wert gewinnt. Benutzer muss Time-of-Use im Web-Interface deaktivieren.

4. **Koexistenz native + modbus:** Die native HA Fronius Integration (Solar API/HTTP) und fronius_modbus (Modbus/TCP Port 502) nutzen unterschiedliche Protokolle und koennen parallel laufen.

5. **Dynamische Register-Adressen:** SunSpec Register-Adressen sind nicht fest, sondern werden bei der Initialisierung durch Model Discovery ermittelt. Die fronius_modbus HACS-Integration uebernimmt das automatisch.

6. **Firmware-Empfehlung:** Mindestens 1.34.6-1, idealerweise >= 1.40.0 (callifo Fork Empfehlung).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| SunSpec Model Discovery | Eigene Register-Suche | fronius_modbus HACS | Dynamische Adressen, verschiedene FW-Versionen |
| Modbus TCP Verbindung | Eigener pymodbus Client | fronius_modbus HACS | Connection Management, Retry, Error Handling |
| Undok. Web API Auth | Eigener Digest+CSRF Client | Modbus TCP (stattdessen) | Firmware-Breaking-Changes, CSRF-Handling |
| Sensor-Lesen | Eigene Solar API Abfrage | Native HA Fronius Integration | Bereits integriert, Auto-Discovery, bewahrt |

## Common Pitfalls

### Pitfall 1: Dynamische SunSpec Register-Adressen
**Was schief geht:** Hardcoded Register-Adressen funktionieren auf einem Geraet, nicht auf einem anderen.
**Warum:** SunSpec Register-Adressen haengen von aktivierten Modellen und Firmware-Version ab.
**Vermeidung:** SunSpec Model Discovery verwenden oder fronius_modbus HACS nutzen (macht Discovery automatisch).
**Warnsignal:** Modbus-Schreibfehler oder falsche Werte nach Firmware-Update.

### Pitfall 2: Float vs. int+SF Konfiguration
**Was schief geht:** Register-Adressen um 10 verschoben, falsche Werte.
**Warum:** Der Gen24 unterstuetzt zwei SunSpec-Modi: int+SF und float. Die Register-Adressen unterscheiden sich um +10.
**Vermeidung:** Immer "int + SF" im Fronius Web-Interface einstellen (Standard fuer fronius_modbus).
**Warnsignal:** Alle Werte sind 0 oder unsinnig.

### Pitfall 3: "Allow Control" nicht aktiviert
**Was schief geht:** Modbus-Schreibzugriffe werden mit Exception abgelehnt.
**Warum:** Im Fronius Web-Interface muss "Allow Control" / "Inverter control via Modbus" explizit aktiviert sein.
**Vermeidung:** Benutzeranleitung mit klarer Schritt-fuer-Schritt-Anweisung.
**Warnsignal:** Exception bei jedem Schreibzugriff.

### Pitfall 4: Web-Interface TimeOfUse konkurriert
**Was schief geht:** Modbus-Befehle werden ignoriert, Batterie laed trotz Block-Befehl.
**Warum:** "The value set via Modbus competes with the settings in the Fronius web interface: the higher value wins."
**Vermeidung:** Benutzer muss scheduled (dis)charging im Web-UI deaktivieren.
**Warnsignal:** Inkonsistentes Verhalten, Steuerung "funktioniert manchmal".

### Pitfall 5: fronius_modbus ist "Work in Progress"
**Was schief geht:** Breaking Changes in der HACS-Integration, Entities aendern sich.
**Warum:** Beide Forks (redpomodoro und callifo) sind in aktiver Entwicklung und koennen Entity-Namen oder Modi aendern.
**Vermeidung:** Entity-Keys konfigurierbar machen (wie bei SolaX/SolarEdge), nicht hardcoden. Version-Pinning in Anleitung.
**Warnsignal:** Entities werden nach Update nicht gefunden.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sensor-Mapping auf EEG Optimizer Config Keys ist kompatibel | 1.1 | Niedrig -- Entity-Picker-UI erlaubt manuelle Zuordnung |
| A2 | fronius_modbus "Block charging" setzt StorCtl_Mod Bit 0 + InWRte=0 | 4.1 | Mittel -- muss bei Implementierung verifiziert werden |
| A3 | fronius_modbus "Discharge to Grid" erlaubt Power-Einstellung | 4.1 | Mittel -- muss bei Implementierung verifiziert werden |
| A4 | Fronius Gen24 Modbus-Werte revertieren nicht automatisch | 4.4 | Hoch -- falls doch, aendert Stop-Logik-Anforderungen |
| A5 | Native HA Fronius + fronius_modbus koennen parallel laufen | 3.2 | Mittel -- verschiedene Protokolle, sollte funktionieren |

## Open Questions

1. **Exakte Entity-IDs der fronius_modbus Integration**
   - Was wir wissen: Entity-Typen (select, number) und ungefaehre Bezeichnungen
   - Was unklar ist: Exakte Entity-ID-Muster (z.B. `select.fronius_storage_control_mode` oder `select.{device_name}_storage_control_mode`?)
   - Empfehlung: Am Fronius-Testgeraet (192.168.100.211) verifizieren nach Installation von fronius_modbus

2. **Persistenz der Modbus-Werte nach WR-Neustart**
   - Was wir wissen: Modbus-Werte gelten waehrend der Laufzeit
   - Was unklar ist: Bleiben StorCtl_Mod/InWRte/OutWRte nach einem WR-Neustart erhalten (NVRAM) oder werden sie zurueckgesetzt?
   - Empfehlung: Am Testgeraet verifizieren

3. **callifo vs. redpomodoro Fork**
   - Was wir wissen: callifo ist aktiver (mehr Commits, neuere Version), nutzt auch Web API
   - Was unklar ist: Ist der callifo Fork stabiler fuer reine Modbus-Steuerung?
   - Empfehlung: callifo verwenden (aktiver, besser gewartet), aber bei Problemen auf redpomodoro zurueckfallen

4. **WChaMax-Zugriff bei fronius_modbus**
   - Was wir wissen: WChaMax wird fuer Prozentwert-Berechnung benoetigt (bei direktem Modbus)
   - Was unklar ist: Abstrahiert fronius_modbus die Prozentwert-Umrechnung? (Entities scheinen in Watt zu sein)
   - Empfehlung: Bei fronius_modbus-Weg moeglicherweise kein Problem, da Entities in Watt arbeiten

---

## Sources

### Primary (HIGH confidence)
- [Home Assistant Fronius Integration Docs](https://www.home-assistant.io/integrations/fronius/) -- Offizielle Doku, read-only bestaetigt
- [HA Core Source: fronius/sensor.py](https://github.com/home-assistant/core/blob/dev/homeassistant/components/fronius/sensor.py) -- Exakte Entity-Keys
- [Fronius GEN24 Modbus TCP Operating Instructions](https://manuals.fronius.com/html/4204102649/en-US.html) -- Offizielle Register-Doku
- [libe.net: Fronius and BYD battery control via Modbus](https://www.libe.net/en/byd-modbus) -- Detaillierte Register-Beschreibung mit Praxisbeispielen
- [redpomodoro/fronius_modbus](https://github.com/redpomodoro/fronius_modbus) -- HACS Custom Component README
- [callifo/fronius_modbus](https://github.com/callifo/fronius_modbus) -- Aktiver Fork mit Web API Support

### Secondary (MEDIUM confidence)
- [HA Community: Fronius Integration with battery](https://community.home-assistant.io/t/howto-fronius-integration-with-battery-into-energy-dashboard/376329) -- Entity-Naming Patterns
- [OpenHAB Fronius Binding](https://www.openhab.org/addons/bindings/fronius/) -- Battery Control Actions/Methods
- [evcc Discussion #11711](https://github.com/evcc-io/evcc/discussions/11711) -- Modbus Register Adressen
- [jtbnz/fronius-modbus-controller](https://github.com/jtbnz/fronius-modbus-controller) -- Python Modbus Controller
- [muexxl/batcontrol](https://github.com/muexxl/batcontrol) -- Solar API Battery Control

### Tertiary (LOW confidence)
- [evcc Issue #11706](https://github.com/evcc-io/evcc/issues/11706) -- Web API Probleme
- [Photovoltaikforum: GEN24 Firmware Threads](https://www.photovoltaikforum.com/thread/254329-gen24-firmware-1-39-5-1/) -- Firmware Breaking Changes

## Metadata

**Confidence breakdown:**
- Sensor-Lesen: HIGH -- Native HA Integration ist hervorragend dokumentiert
- Modbus-Steuerung: HIGH -- SunSpec Standard, mehrere funktionierende Implementierungen
- fronius_modbus HACS: MEDIUM -- Funktioniert, aber "Work in Progress", Entity-Details nicht vollstaendig verifiziert
- Web API: LOW -- Undokumentiert, Firmware-Breaking-Changes bestaetigt

**Research date:** 2026-04-12
**Valid until:** 2026-05-12 (30 Tage, Modbus-Register sind stabil; fronius_modbus HACS kann sich aendern)
