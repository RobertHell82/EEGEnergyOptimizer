# Fronius Gen24 — Umsetzungskonzept für den EEG Energy Optimizer

**Stand:** 2026-04-12
**Autor:** Automatisch erstellt auf Basis der Research-Ergebnisse
**Zweck:** Implementierungsgrundlage für den Fronius-Inverter-Treiber (`FroniusInverter`)
**Referenz-Setup:** Fronius GEN24 Plus + BYD HVS/HVM Batteriespeicher

---

## 1. Ziel und Scope

### Ziel

Integration des Fronius Gen24 Wechselrichters (mit BYD HVS/HVM Batterie) in den EEG Energy Optimizer. Der Fronius Gen24 soll als vierter Wechselrichter-Typ neben Huawei SUN2000, SolaX Gen4+ und SolarEdge StorEdge unterstützt werden.

### Referenz-Setup

- **Wechselrichter:** Fronius GEN24 Plus (5.0 / 6.0 / 8.0 / 10.0 / 12.0 kW)
- **Batteriespeicher:** BYD Battery-Box Premium HVS/HVM (die gängigste Kombination mit dem Gen24)
- **Firmware:** >= 1.34.6-1, idealerweise >= 1.40.0
- **Testgerät:** Fronius Gen24 unter `192.168.100.211`

### Abgrenzung

Dieses Dokument ist ein **Umsetzungskonzept**, keine Implementierung. Es beschreibt:
- Welche Sensoren für den EEG Optimizer gelesen werden können
- Wie der Wechselrichter angesteuert wird (Laden blockieren, Entladen erzwingen, Normalbetrieb)
- Welcher Integrationsweg empfohlen wird und warum
- Wie die bestehende `InverterBase`-Abstraktion auf den Fronius abgebildet wird

Die Batterie-Steuerung erfolgt ausschließlich über den Wechselrichter, nicht direkt zur BYD-Batterie.

---

## 2. Lesende Sensoren

### 2.1 Native HA Fronius Integration (Solar API) — Empfohlener Leseweg

Die native Home Assistant Fronius Integration nutzt die Fronius Solar API v1 (HTTP/JSON, lokale Requests) und ist **rein lesend** — keine Steuerungsfunktionen. Die Solar API muss im Fronius Web-Interface aktiviert sein (Firmware >= 1.14.1).

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
| `relative_autonomy` | Autarkiequote | % | 0–100 |
| `relative_self_consumption` | Eigenverbrauchsquote | % | 0–100 |
| `energy_day` | Tagesenergie | Wh | kumulativ |
| `energy_total` | Gesamtenergie | Wh | kumulativ |

#### Storage/Batterie Sensoren (Update jede Minute)

| HA Entity Key | Beschreibung | Einheit |
|---|---|---|
| `state_of_charge` | Batterie-Ladestand (SOC) | % |
| `capacity_maximum` | Maximale Kapazität | Wh |
| `capacity_designed` | Design-Kapazität | Wh |
| `current_dc` | Batterie-Strom | A |
| `voltage_dc` | Batterie-Spannung | V |
| `temperature_cell` | Zell-Temperatur | °C |

#### Entity-Namensschema

Die tatsächlichen Entity-IDs folgen dem Muster:

```
sensor.{device_name}_{key}
```

Typische Beispiele (installations-/IP-abhängig):
- `sensor.solarnet_power_battery` oder `sensor.power_battery_fronius_power_flow_0_{IP}`
- `sensor.solarnet_power_photovoltaics`
- `sensor.solarnet_power_grid`
- `sensor.byd_battery_box_premium_hv_state_of_charge`

**Wichtig:** Der genaue Präfix hängt von der HA-Installation und dem Geräte-Discovery ab. Die Entity-IDs müssen im Wizard/Panel vom Benutzer zugeordnet werden (Entity-Picker).

### 2.2 Mapping auf EEG Optimizer Config Keys

| EEG Optimizer Config Key | Fronius Native Entity | Einheit | Umrechnung | Vorzeichen-Konvention |
|---|---|---|---|---|
| `pv_power_sensor` | `sensor.{prefix}_power_photovoltaics` | W | W → kW (÷ 1000) im Inverter-Treiber | immer positiv |
| `battery_power_sensor` | `sensor.{prefix}_power_battery` | W | W → kW (÷ 1000) im Inverter-Treiber | + Entladung / - Ladung (gleiche Konvention wie Huawei) |
| `battery_soc_sensor` | `sensor.{prefix}_state_of_charge` | % | Keine Umrechnung nötig | 0–100 |
| `grid_power_sensor` | `sensor.{prefix}_power_grid` | W | W → kW (÷ 1000) im Inverter-Treiber | + Einspeisung / - Bezug |
| `battery_capacity` | `sensor.{prefix}_capacity_maximum` | Wh | Wh → kWh (÷ 1000) — oder manuelle Eingabe in kWh | — |

**Vorzeichen-Konventionen:**
- **Batterie:** `power_battery` liefert + bei Entladung und - bei Ladung — das entspricht der gleichen Konvention wie beim Huawei SUN2000 und ist kompatibel mit dem EEG Optimizer.
- **Netz:** `power_grid` liefert + bei Einspeisung und - bei Bezug — ebenfalls kompatibel mit der bestehenden Logik.
- **Einheiten:** Fronius liefert alle Leistungswerte in **Watt (W)**, der EEG Optimizer arbeitet intern teilweise mit **kW**. Die Umrechnung erfolgt im Inverter-Treiber oder in der Sensor-Auswertung.

### 2.3 Fronius Solar API v1 (direkt)

Die Solar API v1 liefert JSON-Daten über HTTP GET ohne Authentifizierung:

- **Power Flow:** `http://{IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi`
- **Storage:** `http://{IP}/solar_api/v1/GetStorageRealtimeData.cgi?Scope=System` (ab FW 1.13)

Die direkte Nutzung der Solar API ist **nicht nötig**, da die native HA Fronius Integration alle Werte vollständig und zuverlässig liefert. Kein Grund, die API direkt anzusprechen.

### 2.4 Modbus TCP Lesen

Alternativ können Sensoren auch über Modbus TCP (SunSpec) gelesen werden:

| Register (int+SF) | Beschreibung | SunSpec Model |
|---|---|---|
| 40345 | WChaMax (Max Lade-/Entladeleistung) | 124 |
| 40349 | ChaState (SOC in %) | 124 |
| 40351 | ChaSt (Betriebsstatus) | 124 |
| 30845 | Battery SOC | System |
| 30775 | Battery Power | System |

**Fazit:** Modbus-Lesen ist für den EEG Optimizer nicht erforderlich, da die native HA Integration alle Werte liefert. Modbus TCP wird nur für die **Steuerung** benötigt.

---

## 3. Wechselrichter-Ansteuerung (Kernthema)

### 3.1 Methode A: HA Native Fronius Integration — KEINE Steuerung möglich

Die offizielle HA Fronius Integration nutzt die Solar API, die **explizit read-only** ist:

> "The Solar API used by this integration is read-only. It does not provide any means to control the Fronius devices."

- Keine HA Services für Batterie-Steuerung
- Keine number/select Entities zum Schreiben
- Keine Pläne seitens Home Assistant, Steuerung hinzuzufügen (Solar API Limitation)

**Bewertung: Nicht geeignet für Batterie-Steuerung.**

### 3.2 Methode B: Modbus TCP direkt (pymodbus + SunSpec Model 124)

#### Voraussetzungen

1. **Modbus TCP aktivieren** im Fronius Web-Interface:
   - Communication → Modbus → Aktivieren
   - Mode: TCP Server
   - SunSpec Model Type: **int + SF** (wichtig! Nicht float)
   - Port: 502 (Standard) oder 1502
   - **Allow Control: ON** (ohne dies scheitern alle Schreibzugriffe mit Exception)
   - Scheduled (dis)charging im Web-UI deaktivieren (Konfliktvermeidung)
2. **Firmware >= 1.34.6-1** empfohlen (ältere Versionen haben bekannte Bugs bei Ladeleistungs-Begrenzung)
3. **Battery Management** im Fronius Web-Interface aktiviert

#### SunSpec Model 124 — Storage Control Register

**Startadresse Model 124:** 40343 (int+SF) bzw. 40353 (float)

**WICHTIG: Register-Adressen sind dynamisch.** Die unten genannten Adressen gelten für die typische Konfiguration mit int+SF. Die tatsächlichen Adressen hängen von der Zusammensetzung der SunSpec Register-Liste ab und müssen beim ersten Zugriff über SunSpec Model Discovery ermittelt werden.

| Register | Offset | Name | Typ | R/W | Beschreibung |
|---|---|---|---|---|---|
| 40345 | +2 | WChaMax | uint16 | R | Max. Lade-/Entladeleistung in W |
| 40348 | +5 | StorCtl_Mod | bitfield16 | **RW** | Steuermodus: Bit 0 = Charge Limit, Bit 1 = Discharge Limit |
| 40349 | +6 | ChaState | uint16 | R | SOC in % (mit Scale Factor) |
| 40350 | +7 | MinRsvPct | uint16 | **RW** | Mindest-Reserve in % (mit SF, z.B. 500 = 5%) |
| 40351 | +8 | ChaSt | enum16 | R | Status: OFF / EMPTY / DISCHARGING / CHARGING / FULL / HOLDING |
| 40355 | +12 | OutWRte | int16 | **RW** | Entlade-Limit in % von WChaMax (SF -2, d.h. 10000 = 100%) |
| 40356 | +13 | InWRte | int16 | **RW** | Lade-Limit in % von WChaMax (SF -2, d.h. 10000 = 100%) |
| 40357 | +14 | ChaGriSet | enum16 | **RW** | Netzladung erlauben/verbieten |
| 40364 | +21 | InOutWRte_SF | sunssf | R | Scale Factor für InWRte/OutWRte = -2 |

**Hinweis zu Register-Adressen:** Die obigen Adressen stammen aus verschiedenen Quellen und können je nach Firmware-Version und aktivierten SunSpec-Modellen leicht variieren. Einige Quellen berichten StorCtl_Mod auf 40319 oder 40359 — das liegt an unterschiedlichen Konfigurationen. Die `fronius_modbus` HACS-Integration löst dieses Problem automatisch durch SunSpec Model Discovery.

#### Steuerungssequenzen

**Ladung blockieren (Morgen-Einspeisung):**

1. `StorCtl_Mod` = 1 (Bit 0: Charge Limit aktiv)
2. `InWRte` = 0 (0% Ladeleistung = keine Ladung)
3. **Ergebnis:** PV-Überschuss geht ins Netz statt in die Batterie

**Entladung erzwingen (Abend-Entladung):**

1. `StorCtl_Mod` = 3 (Bits 0+1: Charge + Discharge Limit aktiv)
2. `OutWRte` = 10000 (100% Entladeleistung = volle Entladung)
3. `InWRte` = 0 (Ladung weiterhin blockiert während Entladung)
4. Optional: `MinRsvPct` setzen für Mindest-SOC (z.B. 1500 = 15%)
5. **Ergebnis:** Batterie entlädt mit maximaler Leistung ins Netz

**Normalbetrieb wiederherstellen:**

1. `StorCtl_Mod` = 0 (Keine Limits aktiv)
2. `InWRte` = 10000 (100% = unbegrenzt)
3. `OutWRte` = 10000 (100% = unbegrenzt)
4. `MinRsvPct` auf Standardwert (z.B. 500 = 5%)
5. **Ergebnis:** Wechselrichter arbeitet im Automatik-Modus

#### Besonderheit: Prozentwerte statt Absolutwerte

Anders als bei Huawei (Watt direkt) oder SolaX (Watt direkt) arbeitet der Fronius Gen24 mit **Prozentwerten relativ zu WChaMax**:

- InWRte / OutWRte sind Prozentwerte (0–10000 mit SF -2, also 0–100%)
- Die tatsächliche Leistung wird berechnet: `power_w = WChaMax * (InWRte / 10000)`
- Für den EEG Optimizer: Wenn `async_set_discharge(power_kw)` aufgerufen wird, muss der Prozentwert berechnet werden:
  `percent = min(power_kw * 1000 / WChaMax * 10000, 10000)`

#### Wettbewerb mit Web-Interface-Einstellungen

> "The value set via Modbus competes with the settings in the Fronius web interface: the higher value wins."

Das bedeutet: Wenn im Web-Interface ein Lade-Limit von 50% konfiguriert ist und per Modbus 0% gesetzt wird, gewinnt der Web-Interface-Wert (50%). Daher muss der Benutzer in der Anleitung darauf hingewiesen werden, **scheduled (dis)charging im Web-UI zu deaktivieren**.

### 3.3 Methode B2: fronius_modbus HACS-Integration (empfohlen)

Statt direkt mit pymodbus auf die Register zuzugreifen, kann die HACS Custom Component `fronius_modbus` verwendet werden, die HA-native Entities bereitstellt.

#### Variante 1: redpomodoro/fronius_modbus (Original)

- **GitHub:** https://github.com/redpomodoro/fronius_modbus
- **Version:** v0.1.9 (September 2025), 99 Stars
- **Status:** "Early development, breaking changes possible"

#### Variante 2: callifo/fronius_modbus (Fork — empfohlen)

- **GitHub:** https://github.com/callifo/fronius_modbus
- **Version:** v0.2.9 (März 2026), 251 Commits, 27 Releases
- **Status:** Aktiv entwickelt, nutzt sowohl Modbus als auch authentifizierte Web API
- **Firmware-Empfehlung:** >= 1.40.0
- **Vorteile gegenüber Original:** Mehr Entities, mehr Features, aktivere Entwicklung, bessere Stabilität

**Empfehlung: callifo Fork** — aktiver entwickelt, besser gewartet, mehr Features.

#### Relevante Entities für Batterie-Steuerung

| Entity-Typ | Entity-Key | Beschreibung | Steuerungsrelevanz |
|---|---|---|---|
| select | Storage Control Mode | Auto / PV Charge Limit / Discharge Limit / PV Charge and Discharge Limit / Charge from Grid / Discharge to Grid / Block discharging / Block charging | **Zentral** — Hauptsteuerelement |
| number | PV Charge Limit | Max. PV-Ladeleistung in W | Teilladung begrenzen |
| number | Discharge Limit | Max. Entladeleistung in W | Entladeleistung begrenzen |
| number | Grid Discharge Power | Netz-Entladeleistung in W | Entladung ins Netz |
| number | Grid Charge Power | Netz-Ladeleistung in W | Netzladung (nicht benötigt für EEG) |
| number | Minimum Reserve | Mindest-Reserve in % | SOC-Untergrenze |
| sensor | State of Charge | SOC in % | Status-Überwachung |
| sensor | Charge Status | Holding / Charging / Discharging | Status-Überwachung |

#### Steuerungssequenzen über HA-Entities

**Ladung blockieren (Morgen-Einspeisung):**

```
select.select_option: "Block charging"  → Storage Control Mode Entity
```

Ergebnis: InWRte = 0, PV-Überschuss geht ins Netz.

**Entladung erzwingen (Abend-Entladung):**

```
select.select_option: "Discharge to Grid"  → Storage Control Mode Entity
number.set_value: {power_w}  → Grid Discharge Power Entity
number.set_value: {min_soc}  → Minimum Reserve Entity (optional)
```

Ergebnis: Batterie entlädt mit der angegebenen Leistung ins Netz.

**Normalbetrieb wiederherstellen:**

```
select.select_option: "Auto"  → Storage Control Mode Entity
```

Ergebnis: Wechselrichter kehrt zum automatischen Betrieb zurück.

### 3.4 Methode C: Fronius Solar API v1 — Read-only, keine Steuerung

Die offizielle Solar API v1 ist **rein lesend**. Es existieren keine POST-Endpunkte für Batterie-Steuerung. Keine Steuerungsfunktionen verfügbar.

**Bewertung: Nicht geeignet für Batterie-Steuerung.**

### 3.5 Methode D: Undokumentierte Web API — NICHT EMPFOHLEN

Es existiert eine undokumentierte Web API für Batterie-Steuerung, die im Web-Interface des Gen24 verwendet wird:

- **Endpoint:** `http://{IP}/config/batteries` oder `/config/timeofuse`
- **Methode:** POST
- **Authentifizierung:** Digest-Auth (MD5 bis FW 1.37, SHA-256 ab FW 1.38) + CSRF-Token + Session
- **ScheduleType-Werte:** `DISCHARGE_MAX`, `CHARGE_MAX`, `DISCHARGE_MIN`, `CHARGE_MIN`

**Projekte die diese API nutzen:**
- **batcontrol** (muexxl/batcontrol) — Python, läuft standalone
- **OpenHAB Fronius Binding** — Java, bietet Aktionen wie `holdBatteryCharge()`, `forceBatteryDischarging(power)`, `resetBatteryControl()`
- **sbam** (HA Add-on) — Fronius-spezifisch

**Schwerwiegende Probleme:**

1. **Nicht dokumentiert:** Fronius kann die API jederzeit ändern oder entfernen
2. **Firmware-Breaking-Changes:** FW 1.38 hat Auth von MD5 auf SHA-256 umgestellt, FW 1.39 hat bei vielen Nutzern die Battery-Control-API gebrochen ("alg not implemented" Fehler)
3. **Nicht-standardkonforme Header:** Fronius sendet `X-WWW-Authenticate` statt `WWW-Authenticate`
4. **CSRF-Token erforderlich:** Ab FW 1.38 muss ein CSRF-Token + Session-Cookie mitgesendet werden
5. **Benutzer-Credentials erforderlich:** Login-Daten des Fronius Web-Interface nötig

**Bewertung: Nicht empfohlen als primärer Steuerungsweg.** Zu fragil, Firmware-Updates können die Integration jederzeit brechen. Kein standardisiertes Protokoll.

---

## 4. Vergleichstabelle

| Kriterium | HA Native (Solar API) | Modbus direkt (pymodbus) | fronius_modbus (HACS) | Undok. Web API |
|---|---|---|---|---|
| **Sensoren lesen** | Ja (vollständig) | Ja (aufwendig) | Ja (vollständig) | Nur über Solar API |
| **Ladung blockieren** | NEIN | Ja (StorCtl_Mod + InWRte) | Ja ("Block charging") | Ja (DISCHARGE_MAX) |
| **Entladung erzwingen** | NEIN | Ja (StorCtl_Mod + OutWRte) | Ja ("Discharge to Grid") | Ja (CHARGE_MAX = 0) |
| **Normalbetrieb** | — | Ja (StorCtl_Mod = 0) | Ja ("Auto") | Ja (resetBatteryControl) |
| **HA-nativ** | Ja (Core) | Nein (eigene Modbus-Lib) | Ja (Entities) | Nein (HTTP-Calls) |
| **Zuverlässigkeit** | Hoch | Hoch | Mittel (WIP) | Niedrig |
| **Firmware-Stabilität** | Hoch (offizielle API) | Hoch (SunSpec Standard) | Hoch (SunSpec-basiert) | Niedrig (Breaking Changes) |
| **Auth nötig** | Nein | Nein | Nein | Ja (Digest + CSRF) |
| **Community-Support** | Sehr hoch (Core) | Mittel | Mittel-Hoch (99–251 Stars) | Gering |
| **Installationsaufwand** | Gering (Auto-Discovery) | Hoch (pymodbus als Dep.) | Mittel (HACS) | Hoch (Credentials, CSRF) |
| **Koexistenz mit Native** | — | Ja (versch. Protokolle) | Ja (Modbus != Solar API) | Ja |

---

## 5. Empfehlung

### Primär: Native HA Fronius + fronius_modbus HACS (callifo Fork)

**Lesen:** Native HA Fronius Integration für alle Sensoren (PV, Batterie, Grid, SOC).

**Steuern:** `fronius_modbus` HACS Custom Component (callifo Fork) für Batterie-Steuerung.

**Begründung:**

1. **HA-native Entities:** Select- und Number-Entities für Steuerung — analog zur bestehenden SolaX- und SolarEdge-Implementierung
2. **SunSpec-basiert:** Standardisiertes Protokoll, firmware-stabil (keine Breaking Changes bei FW-Updates)
3. **Aktive Entwicklung:** v0.2.9 (März 2026), 251 Commits, 27 Releases
4. **Koexistenz:** Native HA Fronius (Solar API/HTTP) und fronius_modbus (Modbus/TCP Port 502) nutzen unterschiedliche Protokolle und können parallel laufen
5. **Implementierungsmuster:** Steuerung über select/number Entities — identisches Muster wie SolaX und SolarEdge

### Alternativ: Direkte Modbus TCP Steuerung (pymodbus)

Falls die HACS-Integration Probleme bereitet oder nicht gewünscht ist:

- Direkte Modbus-Register-Zugriffe über pymodbus
- Volle Kontrolle, keine Abhängigkeit von Drittanbieter-Integration
- Höhere Komplexität: SunSpec Model Discovery, Register-Berechnung, pymodbus als Dependency
- Sinnvoll als Fallback-Option oder wenn maximale Kontrolle gewünscht ist

### Nicht empfohlen: Undokumentierte Web API

Zu fragil, Firmware-Abhängigkeit, komplexe Authentifizierung. Selbst etablierte Projekte wie batcontrol und evcc hatten wiederholte Probleme nach Firmware-Updates.

---

## 6. Mapping auf InverterBase

### 6.1 Empfohlener Weg: Via fronius_modbus Entities

Die Implementierung wäre analog zur bestehenden SolaX- und SolarEdge-Implementierung, die ebenfalls HA-Entities (select/number) ansteuern.

#### async_set_charge_limit(power_kw)

**Morgen-Einspeisung (power_kw = 0):**

1. `select.select_option("Block charging")` auf Storage Control Mode Entity
2. **Ergebnis:** StorCtl_Mod Bit 0 wird gesetzt, InWRte = 0 → PV-Überschuss geht ins Netz

**Teilweise Ladung (power_kw > 0):**

1. `select.select_option("PV Charge Limit")` auf Storage Control Mode Entity
2. `number.set_value(power_kw * 1000)` auf PV Charge Limit Entity (Watt)
3. **Ergebnis:** Batterie lädt nur bis zum angegebenen Limit

**Analogie:** Vergleichbar mit SolaX `async_set_charge_limit` (select + number + trigger), aber ohne Trigger-Button.

#### async_set_discharge(power_kw, target_soc)

**Abend-Entladung:**

1. `select.select_option("Discharge to Grid")` auf Storage Control Mode Entity
2. `number.set_value(power_kw * 1000)` auf Grid Discharge Power Entity (Watt)
3. Optional: `number.set_value(target_soc)` auf Minimum Reserve Entity (%)
4. **Ergebnis:** Batterie entlädt mit der angegebenen Leistung ins Netz

**target_soc-Handling:** Der EEG Optimizer steuert den Mindest-SOC selbst über seine Dynamic Min-SOC Berechnung. Die Minimum Reserve Entity kann als zusätzliche Sicherheit gesetzt werden, ähnlich wie bei SolarEdge (wo `backup_reserve` als Safety Net dient).

**Analogie:** Vergleichbar mit SolarEdge `async_set_discharge` (command_mode + discharge_limit).

#### async_stop_forcible()

**Normalbetrieb wiederherstellen:**

1. `select.select_option("Auto")` auf Storage Control Mode Entity
2. **Ergebnis:** StorCtl_Mod = 0, InWRte/OutWRte = 10000 → Wechselrichter im Automatik-Modus

**Analogie:** Vergleichbar mit SolaX `async_stop_forcible` ("Disabled" + trigger) oder SolarEdge (Restore "Maximize Self Consumption").

#### is_available

```
Prüfen ob fronius_modbus Integration geladen ist:
  entries = hass.config_entries.async_entries("fronius_modbus")
  return any(entry.state.value == "loaded" for entry in entries)
```

**Analogie:** Identisches Muster wie bei allen bestehenden Implementierungen (Domain-Check über config_entries).

### 6.2 Alternativer Weg: Via direkte Modbus TCP

Falls pymodbus direkt verwendet wird (ohne fronius_modbus HACS):

#### async_set_charge_limit(power_kw)

1. Verbindung zu Fronius IP:502 (Modbus TCP)
2. SunSpec Model 124 Startadresse ermitteln (Model Discovery)
3. `write_register(StorCtl_Mod_addr, 1)` — Bit 0: Charge Limit aktiv
4. `write_register(InWRte_addr, 0)` — 0% Ladung = blockiert

Bei power_kw > 0 (Teilladung):
1. WChaMax aus Register lesen
2. `percent = min(power_kw * 1000 / WChaMax * 10000, 10000)`
3. `write_register(StorCtl_Mod_addr, 1)` — Charge Limit aktiv
4. `write_register(InWRte_addr, int(percent))` — Ladung in %

#### async_set_discharge(power_kw, target_soc)

1. WChaMax aus Register lesen
2. `percent = min(power_kw * 1000 / WChaMax * 10000, 10000)`
3. `write_register(StorCtl_Mod_addr, 3)` — Bits 0+1: Charge + Discharge aktiv
4. `write_register(InWRte_addr, 0)` — Ladung blockiert
5. `write_register(OutWRte_addr, int(percent))` — Entladung in %
6. Optional: `write_register(MinRsvPct_addr, int(target_soc * 100))` — Mindest-SOC

#### async_stop_forcible()

1. `write_register(StorCtl_Mod_addr, 0)` — Keine Limits
2. `write_register(InWRte_addr, 10000)` — 100% Ladung erlaubt
3. `write_register(OutWRte_addr, 10000)` — 100% Entladung erlaubt

### 6.3 Vergleich mit bestehenden Implementierungen

| Aspekt | Huawei | SolaX | SolarEdge | Fronius (HACS) | Fronius (direkt) |
|---|---|---|---|---|---|
| **Steuerungsweg** | HA Services (huawei_solar) | HA Entities (solax_modbus) | HA Entities (solaredge_modbus_multi) | HA Entities (fronius_modbus) | pymodbus direkt |
| **Ladung blockieren** | number.set_value(0) auf Max-Charge | select("Battery Control") + active_power(0) | select("Discharge Minimize Import") | select("Block charging") | StorCtl_Mod=1, InWRte=0 |
| **Entladung** | Service forcible_discharge_soc | select("Battery Control") + neg. active_power | select("Discharge Maximize Export") + discharge_limit | select("Discharge to Grid") + power | StorCtl_Mod=3, OutWRte=% |
| **Stop** | stop_forcible_charge + restore max | select("Disabled") + trigger | Restore original modes | select("Auto") | StorCtl_Mod=0, InWRte/OutWRte=10000 |
| **Persistenz** | Nein (Timeout) | Nein (Autorepeat-Timer) | Ja (NVRAM!) | Nein (Modbus nicht persistent) | Nein |
| **Leistungsangabe** | Watt (direkt) | Watt (direkt) | Watt (direkt) | Watt (Entity) | Prozent von WChaMax |
| **HA-Dependency** | huawei_solar | solax_modbus | solaredge_modbus_multi | fronius_modbus | Keine (pymodbus) |
| **Entity-Prefix variabel** | Nein (bekannte IDs) | Ja (konfigurierbar) | Ja (konfigurierbar) | Ja (konfigurierbar) | — |
| **Stop-Zuverlässigkeit** | Mittel (Timeout hilft) | Mittel (Autorepeat hilft) | Kritisch (NVRAM!) | Wichtig (kein Auto-Revert) | Wichtig (kein Auto-Revert) |

---

## 7. Voraussetzungen für den Benutzer

### 7.1 Fronius Web-Interface Konfiguration

Der Benutzer muss vor der Nutzung folgende Einstellungen im Fronius Web-Interface vornehmen:

1. **Modbus TCP aktivieren:**
   - Communication → Modbus → Aktivieren
   - Mode: TCP Server
   - SunSpec Model Type: **int + SF** (nicht float!)
   - Port: 502 (Standard)
   - **Allow Control via Modbus: EIN** (ohne dies werden Schreibzugriffe mit Exception abgelehnt)

2. **Scheduled (Dis)Charging deaktivieren:**
   - Im Web-Interface unter Batterie/Energie-Management
   - Grund: "The value set via Modbus competes with the settings in the Fronius web interface: the higher value wins" — aktivierte Zeitpläne können die Modbus-Steuerung überschreiben

3. **Battery Management aktiviert:** BYD-Batterie muss erkannt und aktiv sein

### 7.2 fronius_modbus HACS-Integration installieren

1. **HACS installieren** (falls noch nicht vorhanden)
2. **callifo Fork hinzufügen:**
   - HACS → Custom repositories → `https://github.com/callifo/fronius_modbus`
   - Alternativ: Original `https://github.com/redpomodoro/fronius_modbus`
3. **Integration einrichten** in HA → Einstellungen → Geräte & Dienste
4. **Entities prüfen:** Storage Control Mode (select), Grid Discharge Power (number), etc.

### 7.3 Firmware-Empfehlung

- **Minimum:** >= 1.34.6-1 (ältere Versionen haben Bugs bei Ladeleistungs-Begrenzung)
- **Empfohlen:** >= 1.40.0 (callifo Fork Empfehlung, beste Kompatibilität)
- **Vorsicht bei:** FW 1.38 (Auth-Änderung MD5 → SHA-256, betrifft nur Web API, nicht Modbus)

### 7.4 HA Native Fronius Integration

- Muss zusätzlich installiert sein (für lesende Sensoren)
- Wird automatisch via Auto-Discovery erkannt
- Koexistiert problemlos mit fronius_modbus (verschiedene Protokolle: HTTP vs. Modbus TCP)

---

## 8. Offene Fragen (Testgerät-Verifizierung)

Die folgenden Punkte müssen am Testgerät (Fronius Gen24 unter **192.168.100.211**) verifiziert werden:

### 8.1 Exakte Entity-IDs der fronius_modbus Integration

- **Was bekannt ist:** Entity-Typen (select, number) und ungefähre Bezeichnungen
- **Was unklar ist:** Exaktes Entity-ID-Muster — z.B. `select.fronius_storage_control_mode` oder `select.{device_name}_storage_control_mode`?
- **Empfehlung:** Am Testgerät nach Installation von fronius_modbus prüfen → Entity-Keys im Inverter-Treiber konfigurierbar machen (wie bei SolaX/SolarEdge)

### 8.2 Persistenz der Modbus-Werte nach WR-Neustart

- **Was bekannt ist:** Modbus-Werte gelten während der Laufzeit
- **Was unklar ist:** Bleiben StorCtl_Mod / InWRte / OutWRte nach einem WR-Neustart erhalten (NVRAM) oder werden sie auf Standardwerte zurückgesetzt?
- **Relevanz:** Falls persistent (wie SolarEdge NVRAM), muss `async_stop_forcible()` besonders zuverlässig aufgerufen werden. Falls nicht persistent, revertiert der WR nach Neustart automatisch — weniger kritisch.
- **Empfehlung:** Am Testgerät verifizieren: Modbus-Wert setzen → WR neu starten → Wert prüfen

### 8.3 callifo vs. redpomodoro Fork

- **Was bekannt ist:** callifo ist aktiver (mehr Commits, neuere Version), nutzt auch Web API
- **Was unklar ist:** Ist der callifo Fork stabiler für reine Modbus-Steuerung? Gibt es Konflikte durch die Web API Nutzung?
- **Empfehlung:** callifo verwenden (aktiver, besser gewartet), bei Problemen auf redpomodoro zurückfallen

### 8.4 WChaMax-Zugriff bei fronius_modbus

- **Was bekannt ist:** WChaMax wird für Prozentwert-Berechnung bei direktem Modbus benötigt
- **Was unklar ist:** Abstrahiert fronius_modbus die Prozentwert-Umrechnung? (Entities scheinen in Watt zu arbeiten)
- **Relevanz:** Bei fronius_modbus-Weg möglicherweise kein Problem, da Entities in Watt arbeiten und die Umrechnung intern erfolgt
- **Empfehlung:** Am Testgerät prüfen: Grid Discharge Power auf z.B. 2000 W setzen → tatsächliche Entladeleistung messen

### 8.5 Koexistenz native HA Fronius + fronius_modbus

- **Was bekannt ist:** Verschiedene Protokolle (HTTP vs. Modbus TCP), sollte funktionieren
- **Was unklar ist:** Gibt es in der Praxis Störungen? Locking-Konflikte auf dem Fronius?
- **Empfehlung:** Am Testgerät verifizieren: Beide Integrationen gleichzeitig aktiv → Sensoren und Steuerung parallel testen

---

## 9. Besonderheiten und Pitfalls

### 9.1 Prozentwerte statt Watt (InWRte/OutWRte)

Der Fronius Gen24 arbeitet bei direktem Modbus-Zugriff mit **Prozentwerten relativ zu WChaMax**, nicht mit absoluten Watt-Angaben. Die fronius_modbus Integration abstrahiert das teilweise (Entities scheinen in Watt zu arbeiten), aber bei direktem Modbus-Zugriff muss umgerechnet werden:

- `percent = min(power_kw * 1000 / WChaMax * 10000, 10000)`
- Scale Factor = -2, d.h. 10000 entspricht 100%

### 9.2 Keine Auto-Revert (Kein Timeout, kein Autorepeat)

Anders als Huawei (Timeout nach x Minuten) und SolaX (Autorepeat-Timer mit Duration) revertiert der Fronius Gen24 Modbus-Einstellungen **nicht automatisch**. Dies ist vergleichbar mit SolarEdge (NVRAM-Persistenz).

**Konsequenz:** `async_stop_forcible()` muss zuverlässig aufgerufen werden. Bei einem Absturz der Integration bleiben die Modbus-Werte bestehen bis zum nächsten Schreibzugriff oder WR-Neustart.

**Mitigations-Optionen:**
- Watchdog-Timer in der Integration, der bei Nicht-Antwort des Optimizers automatisch `async_stop_forcible()` aufruft
- HA Automation als Safety Net: "Wenn EEG Optimizer unavailable wird → Fronius auf Auto setzen"
- Am Testgerät prüfen, ob WR-Neustart die Werte zurücksetzt (wäre ein natürlicher Fallback)

### 9.3 Konkurrierende Einstellungen (Web-Interface vs. Modbus)

Fronius Web-Interface und Modbus konkurrieren — **der höhere Wert gewinnt**. Das bedeutet:
- Wenn im Web-Interface scheduled charging auf 50% steht und per Modbus 0% gesetzt wird, gewinnt 50%
- **Benutzer muss** alle Time-of-Use / Scheduled (Dis)Charging Einstellungen im Web-UI deaktivieren
- **Warnsignal:** Inkonsistentes Verhalten, Steuerung "funktioniert manchmal"

### 9.4 Dynamische SunSpec Register-Adressen

SunSpec Register-Adressen sind **nicht fest codiert**, sondern hängen von der Firmware-Version und den aktivierten SunSpec-Modellen ab. Hardcoded Register-Adressen funktionieren auf einem Gerät, nicht auf einem anderen.

**Lösung:**
- **fronius_modbus Weg (empfohlen):** Problem wird automatisch gelöst (SunSpec Model Discovery eingebaut)
- **Direkter Modbus Weg:** SunSpec Model Discovery selbst implementieren — Scan ab Register 40000, Model-Header lesen, Länge überspringen bis Model 124 gefunden

### 9.5 Float vs. int+SF Konfiguration

Der Gen24 unterstützt zwei SunSpec-Modi: **int+SF** und **float**. Die Register-Adressen unterscheiden sich um +10 zwischen den Modi.

- **int+SF (empfohlen):** Register wie oben dokumentiert, Scale Factors als separate Register
- **float:** Register um +10 verschoben, Werte direkt als IEEE 754 float

**Warnsignal:** Alle Werte sind 0 oder unsinnig → falscher SunSpec-Modus konfiguriert.

**Lösung:** Immer **"int + SF"** im Fronius Web-Interface einstellen (Standard für fronius_modbus).

### 9.6 "Allow Control" muss explizit aktiviert sein

Im Fronius Web-Interface muss "Allow Control" / "Inverter control via Modbus" explizit aktiviert sein. Ohne diese Einstellung werden alle Modbus-Schreibzugriffe mit einer Exception abgelehnt.

**Warnsignal:** Exception bei jedem Schreibzugriff, Lesen funktioniert aber.

### 9.7 fronius_modbus ist "Work in Progress"

Beide Forks (redpomodoro und callifo) sind in aktiver Entwicklung und können Entity-Namen, Modi oder Verhalten zwischen Versionen ändern.

**Konsequenz für die Implementierung:**
- Entity-Keys **konfigurierbar** machen, nicht hardcoden (wie bei SolaX/SolarEdge: Config-Key mit Default-Fallback)
- Default-Entity-IDs als `FRONIUS_ENTITY_DEFAULTS` Dictionary pflegen
- Version-Pinning in der Benutzeranleitung empfehlen
- Bei fronius_modbus-Update: Entities prüfen, ggf. Defaults aktualisieren

---

## Fazit

Der Fronius Gen24 lässt sich gut in den EEG Energy Optimizer integrieren. Der empfohlene Weg kombiniert die **native HA Fronius Integration** (für zuverlässiges Sensor-Lesen) mit der **fronius_modbus HACS-Integration** (callifo Fork, für SunSpec-basierte Batterie-Steuerung).

Die Implementierung des `FroniusInverter`-Treibers folgt dem gleichen Muster wie SolaX und SolarEdge: HA-Entities (select/number) über Services ansteuern, Entity-Keys konfigurierbar halten, Domain-Check für `is_available`.

Die größte Besonderheit gegenüber den anderen Wechselrichtern ist das fehlende Auto-Revert — `async_stop_forcible()` muss zuverlässig aufgerufen werden. Die direkte Modbus-Variante mit pymodbus bietet einen soliden Fallback, erfordert aber mehr Implementierungsaufwand (SunSpec Discovery, Prozentwert-Umrechnung).

Vor der Implementierung sollten die offenen Fragen am Testgerät (192.168.100.211) geklärt werden, insbesondere die exakten Entity-IDs und das Persistenz-Verhalten nach WR-Neustart.
