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

### Primär: Native HA Fronius (Sensoren) + Direkte Modbus TCP Steuerung (pymodbus)

**Lesen:** Native HA Fronius Integration für alle Sensoren (PV, Batterie, Grid, SOC).

**Steuern:** Direkte Modbus TCP Schreibzugriffe über pymodbus auf SunSpec Model 124 Register.

**Begründung:**

1. **Keine Drittanbieter-Abhängigkeit:** Kein fronius_modbus HACS-Addon nötig — der Benutzer braucht nur die native HA Fronius Integration (für Sensoren) und Modbus TCP aktiviert am Wechselrichter
2. **Minimaler Scope:** Für den EEG Optimizer werden nur 3 Register geschrieben (`StorCtl_Mod`, `InWRte`, `OutWRte`) — dafür eine komplette HACS-Integration zu verlangen wäre Overkill
3. **Volle Kontrolle:** Keine Überraschungen durch Breaking Changes einer Drittintegration. Wir wissen exakt welche Register gesetzt werden
4. **SunSpec-Standard:** Das Protokoll ist standardisiert und firmware-stabil. Register-Semantik ändert sich nicht
5. **Einfachere Benutzer-Einrichtung:** Eine Dependency weniger, kein HACS-Repository hinzufügen, keine Entity-IDs konfigurieren
6. **pymodbus:** Etablierte Python-Bibliothek, asynchron (asyncio), gut getestet

**Einzige Hürde:** SunSpec Model Discovery — die Register-Adressen von Model 124 sind nicht fest, sondern müssen beim Start einmalig durch einen Scan ab Register 40000 ermittelt werden. Das ist ein einmaliger Scan (~20 Register lesen), kein Hexenwerk.

### Alternativ: fronius_modbus HACS (callifo Fork)

Falls der direkte Modbus-Weg Probleme bereitet:

- `fronius_modbus` HACS Custom Component (callifo Fork, v0.2.9) bietet HA-native select/number Entities
- Identisches Muster wie SolaX/SolarEdge (Entities über HA Services ansteuern)
- Nachteil: Zusätzliche Dependency, "Work in Progress", Entity-IDs können sich zwischen Versionen ändern

### Nicht empfohlen: Undokumentierte Web API

Zu fragil, Firmware-Abhängigkeit, komplexe Authentifizierung. Selbst etablierte Projekte wie batcontrol und evcc hatten wiederholte Probleme nach Firmware-Updates.

---

## 6. Mapping auf InverterBase

### 6.1 Empfohlener Weg: Direkte Modbus TCP Steuerung (pymodbus)

Die Implementierung nutzt pymodbus für direkte Register-Schreibzugriffe auf SunSpec Model 124. Beim Start wird einmalig SunSpec Model Discovery durchgeführt, um die Basisadresse von Model 124 zu ermitteln. Danach werden nur 2-3 Register pro Operation geschrieben.

#### Initialisierung (einmalig beim Start)

1. Modbus TCP Verbindung zu Fronius IP:502 aufbauen (async, pymodbus `AsyncModbusTcpClient`)
2. SunSpec Model Discovery: Ab Register 40000 scannen, Model-Header lesen (Model-ID + Länge), bis Model 124 (Storage) gefunden
3. Basisadresse von Model 124 merken → alle Offsets relativ dazu
4. `WChaMax` lesen (Offset +2) — maximale Batterieleistung in W, wird für Prozentwert-Berechnung gebraucht

#### async_set_charge_limit(power_kw)

**Morgen-Einspeisung (power_kw = 0) — Ladung komplett blockieren:**

1. `write_register(StorCtl_Mod, 1)` — Bit 0: Charge Limit aktiv
2. `write_register(InWRte, 0)` — 0% Ladeleistung = keine Ladung erlaubt
3. **Ergebnis:** PV-Überschuss geht ins Netz statt in die Batterie

**Teilweise Ladung (power_kw > 0):**

1. Prozentwert berechnen: `percent = int(min(power_kw * 1000 / WChaMax, 1.0) * 10000)`
2. `write_register(StorCtl_Mod, 1)` — Charge Limit aktiv
3. `write_register(InWRte, percent)` — Ladung begrenzt auf X% von WChaMax

**Beispiel:** WChaMax = 5000W, power_kw = 2.0 → percent = int(2000/5000 * 10000) = 4000 → 40% Ladeleistung erlaubt

#### async_set_discharge(power_kw, target_soc)

**Abend-Entladung:**

1. Prozentwert berechnen: `percent = int(min(power_kw * 1000 / WChaMax, 1.0) * 10000)`
2. `write_register(StorCtl_Mod, 3)` — Bits 0+1: Charge Limit + Discharge Limit aktiv
3. `write_register(InWRte, 0)` — Ladung blockiert (während Entladung nicht laden)
4. `write_register(OutWRte, percent)` — Entlade-Satz in % von WChaMax
5. Optional: `write_register(MinRsvPct, int(target_soc * 100))` — Mindest-SOC (SF -2, d.h. 1500 = 15%)

**Beispiel:** WChaMax = 5000W, power_kw = 5.0 → percent = 10000 (100%) → volle Entladeleistung

**Was bedeutet `StorCtl_Mod = 3` + `OutWRte`?**
- `StorCtl_Mod = 3` aktiviert die Steuerung für Laden UND Entladen (Bit 0 + Bit 1)
- `OutWRte = 10000` (100%) sagt dem Wechselrichter: "Entlade mit bis zu 100% der maximalen Leistung"
- `InWRte = 0` blockiert gleichzeitig das Laden
- **Ob der Gen24 das als aktive Entladung ins Netz interpretiert** (gewünschtes Verhalten) **oder nur als Obergrenze**, muss am Testgerät verifiziert werden. Community-Berichte deuten auf aktive Entladung hin, aber das ist ein kritischer Verifizierungspunkt (siehe Kapitel 8).

**target_soc-Handling:** Der EEG Optimizer steuert den Mindest-SOC selbst über seine Dynamic Min-SOC Berechnung. `MinRsvPct` kann als zusätzliche Hardware-Sicherheit gesetzt werden, damit der Wechselrichter selbst nicht unter diesen SOC entlädt.

#### async_stop_forcible()

**Normalbetrieb wiederherstellen:**

1. `write_register(StorCtl_Mod, 0)` — Keine Limits aktiv
2. `write_register(InWRte, 10000)` — 100% Ladung erlaubt
3. `write_register(OutWRte, 10000)` — 100% Entladung erlaubt
4. **Ergebnis:** Wechselrichter arbeitet wieder im Automatik-Modus

#### is_available

```
Modbus TCP Verbindung prüfen:
  return self._client.connected  (pymodbus AsyncModbusTcpClient)
```

Kein Domain-Check über config_entries nötig — die Modbus-Verbindung wird direkt vom FroniusInverter-Treiber verwaltet.

### 6.2 Alternativer Weg: Via fronius_modbus HACS Entities

Falls der direkte Modbus-Weg Probleme bereitet, kann die fronius_modbus HACS-Integration als Fallback verwendet werden. Die Steuerung erfolgt dann über HA select/number Entities (analog zu SolaX/SolarEdge):

- **Ladung blockieren:** `select.select_option("Block charging")`
- **Entladung:** `select.select_option("Discharge to Grid")` + `number.set_value(power_w)`
- **Stop:** `select.select_option("Auto")`
- **is_available:** `hass.config_entries.async_entries("fronius_modbus")` Domain-Check

### 6.3 Vergleich mit bestehenden Implementierungen

| Aspekt | Huawei | SolaX | SolarEdge | **Fronius (empfohlen)** |
|---|---|---|---|---|
| **Steuerungsweg** | HA Services (huawei_solar) | HA Entities (solax_modbus) | HA Entities (solaredge_modbus_multi) | **pymodbus direkt (SunSpec Model 124)** |
| **Ladung blockieren** | number.set_value(0) auf Max-Charge | select("Battery Control") + active_power(0) | select("Discharge Minimize Import") | StorCtl_Mod=1, InWRte=0 |
| **Entladung** | Service forcible_discharge_soc | select("Battery Control") + neg. active_power | select("Discharge Maximize Export") + discharge_limit | StorCtl_Mod=3, OutWRte=% von WChaMax |
| **Stop** | stop_forcible_charge + restore max | select("Disabled") + trigger | Restore original modes | StorCtl_Mod=0, InWRte/OutWRte=10000 |
| **Persistenz** | Nein (Timeout) | Nein (Autorepeat-Timer) | Ja (NVRAM!) | Nein (zu verifizieren) |
| **Leistungsangabe** | Watt (direkt) | Watt (direkt) | Watt (direkt) | Prozent von WChaMax (Umrechnung nötig) |
| **HA-Dependency** | huawei_solar | solax_modbus | solaredge_modbus_multi | **Keine** (nur pymodbus) |
| **Entity-Prefix variabel** | Nein (bekannte IDs) | Ja (konfigurierbar) | Ja (konfigurierbar) | — (keine Entities, direkte Register) |
| **Stop-Zuverlässigkeit** | Mittel (Timeout hilft) | Mittel (Autorepeat hilft) | Kritisch (NVRAM!) | Wichtig (kein Auto-Revert) |
| **Installationsaufwand Benutzer** | huawei_solar nötig | solax_modbus nötig | solaredge_modbus_multi nötig | **Nur Modbus TCP am WR aktivieren** |

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

### 7.2 Firmware-Empfehlung

- **Minimum:** >= 1.34.6-1 (ältere Versionen haben Bugs bei Ladeleistungs-Begrenzung)
- **Empfohlen:** >= 1.40.0 (callifo Fork Empfehlung, beste Kompatibilität)
- **Vorsicht bei:** FW 1.38 (Auth-Änderung MD5 → SHA-256, betrifft nur Web API, nicht Modbus)

### 7.3 HA Native Fronius Integration (für Sensoren)

- **Core-Integration** — in Home Assistant eingebaut, kein HACS, kein manuelles Installieren nötig
- Wird automatisch via **Auto-Discovery** erkannt — jeder Fronius-Benutzer hat diese Integration ohnehin
- Liefert alle lesenden Sensoren (PV, Batterie, Grid, SOC) die der Benutzer auch für sein HA Energy Dashboard braucht
- Koexistiert problemlos mit direktem Modbus TCP (verschiedene Protokolle: Solar API über HTTP vs. Modbus TCP Port 502)
- **Vergleichbar mit huawei_solar bei Huawei** — eine Standard-HA-Komponente, keine Drittanbieter-Dependency
- Sensoren zusätzlich über Modbus selbst zu lesen wäre redundant: Die native Integration pollt bereits alle 10s (Power Flow) bzw. 60s (Storage/SOC), was für den 30s-Optimizer-Zyklus ausreicht

### 7.4 Panel-Anleitung für Fronius Integration

Bei der Implementierung muss eine Panel-Anleitung erstellt werden (analog zu den bestehenden Anleitungen für Huawei Solar, SolaX und SolarEdge). Die Anleitung führt den Benutzer durch:

1. **Fronius Integration einrichten:**
   - Wird normalerweise automatisch via Auto-Discovery erkannt
   - Falls nicht: Einstellungen → Geräte & Dienste → Integration hinzufügen → "Fronius"
   - IP-Adresse des Wechselrichters angeben
   - Solar API muss im Fronius Web-Interface aktiviert sein

2. **Modbus TCP am Wechselrichter aktivieren:**
   - Fronius Web-Interface öffnen (http://{IP})
   - Communication → Modbus → Aktivieren
   - Mode: TCP Server
   - SunSpec Model Type: **int + SF**
   - Port: 502
   - **Allow Control via Modbus: EIN**

3. **Scheduled (Dis)Charging deaktivieren:**
   - Batterie/Energie-Management → Zeitpläne deaktivieren
   - Wichtig: Aktivierte Zeitpläne überschreiben die Modbus-Steuerung

4. **Sensoren prüfen:**
   - Nach Einrichtung der Fronius Integration sollten folgende Sensoren verfügbar sein:
   - PV-Leistung (`power_photovoltaics`)
   - Batterie-Leistung (`power_battery`)
   - Batterie-SOC (`state_of_charge`)
   - Netz-Leistung (`power_grid`)
   - Batterie-Kapazität (`capacity_maximum`)

---

## 8. Offene Fragen (Testgerät-Verifizierung)

Die folgenden Punkte müssen am Testgerät (Fronius Gen24 unter **192.168.100.211**) verifiziert werden:

### 8.1 Erzwingt StorCtl_Mod=3 + OutWRte=10000 eine aktive Entladung ins Netz? (KRITISCH)

- **Was bekannt ist:** Community-Berichte deuten auf aktive Entladung hin. Die fronius_modbus Integration bietet einen expliziten "Discharge to Grid" Modus, der auf diesen Registern basiert.
- **Was unklar ist:** Ob der Gen24 bei gesetztem Discharge Limit aktiv ins Netz entlädt, oder ob OutWRte nur eine Obergrenze ist und die Entladung nur bei Hausverbrauch stattfindet.
- **Test:** StorCtl_Mod=3, InWRte=0, OutWRte=10000 setzen → Netz-Einspeisung beobachten. Steigt die Einspeisung über den PV-Überschuss hinaus? Dann wird aktiv aus der Batterie ins Netz eingespeist.
- **Falls NICHT aktiv entladen wird:** Alternative prüfen — möglicherweise braucht es einen zusätzlichen Register-Wert oder die undokumentierte Web API als Ergänzung nur für diesen einen Zweck.

### 8.2 SunSpec Model Discovery — Basisadresse von Model 124

- **Was bekannt ist:** Register-Adressen sind dynamisch und hängen von Firmware und aktivierten Modellen ab. Standard-Basisadresse für Model 124 ist typischerweise 40343 (int+SF).
- **Was unklar ist:** Exakte Basisadresse am Testgerät. Funktioniert der Scan ab Register 40000 zuverlässig?
- **Test:** pymodbus-Skript schreiben das ab 40000 scannt: Model-ID (uint16) + Länge (uint16) lesen, bis Model-ID 124 gefunden wird. Basisadresse notieren.

### 8.3 WChaMax-Wert und Prozentwert-Umrechnung

- **Was bekannt ist:** WChaMax enthält die maximale Batterieleistung in W, wird für die Umrechnung kW → Prozentwert benötigt
- **Was unklar ist:** Ist WChaMax ein fester Wert (z.B. 5000W für Gen24 Plus 5.0) oder ändert er sich je nach Batterie-Zustand (Temperatur, SOC)?
- **Test:** WChaMax-Register mehrfach zu verschiedenen Zeiten lesen. Wenn konstant → kann beim Setup einmal gelesen und gecacht werden. Wenn variabel → muss vor jedem Schreibvorgang gelesen werden.

### ~~8.4 Persistenz nach WR-Neustart~~ — GESTRICHEN

Nicht relevant — der EEG Optimizer schreibt die Register ohnehin täglich neu (Morgen-Einspeisung morgens, Abend-Entladung abends, Normalbetrieb dazwischen).

### ~~8.5 Koexistenz native HA Fronius + Modbus~~ — GESTRICHEN

Bereits bestätigt: Native Fronius Integration (Solar API/HTTP) verträgt sich mit direkten Modbus TCP Schreibzugriffen (vom Benutzer selbst getestet).

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

### 9.7 pymodbus als Dependency

Der direkte Modbus-Weg erfordert pymodbus als Python-Dependency. Da Home Assistant selbst pymodbus bereits als Dependency hat (für die HA Modbus Integration), ist es wahrscheinlich bereits verfügbar. Falls nicht, muss es in `manifest.json` als Requirement aufgenommen werden.

**Konsequenz für die Implementierung:**
- `pymodbus` in `manifest.json` `requirements` aufnehmen
- `AsyncModbusTcpClient` für asynchrone Verbindung verwenden (kompatibel mit HA Event Loop)
- Verbindungs-Management: Reconnect-Logik bei Verbindungsverlust
- SunSpec Model Discovery einmalig beim Setup, Basisadresse cachen

---

## Fazit

Der Fronius Gen24 lässt sich gut in den EEG Energy Optimizer integrieren. Der empfohlene Weg kombiniert die **native HA Fronius Integration** (für zuverlässiges Sensor-Lesen) mit **direkten Modbus TCP Schreibzugriffen** über pymodbus auf SunSpec Model 124 Register.

Die Implementierung des `FroniusInverter`-Treibers ist schlanker als bei den anderen Wechselrichtern: Keine Drittanbieter-HA-Integration nötig, nur 2-3 Register-Schreibzugriffe pro Operation (`StorCtl_Mod`, `InWRte`, `OutWRte`). Der Benutzer muss lediglich Modbus TCP mit "Allow Control" am Wechselrichter aktivieren — kein HACS-Addon, keine zusätzlichen Entities konfigurieren.

Die größte Besonderheit gegenüber den anderen Wechselrichtern:
1. **Prozentwerte statt Watt** — Umrechnung über WChaMax nötig
2. **Kein Auto-Revert** — `async_stop_forcible()` muss zuverlässig aufgerufen werden
3. **SunSpec Model Discovery** — Register-Adressen werden einmalig beim Start ermittelt

Vor der Implementierung sollten die offenen Fragen am Testgerät (192.168.100.211) geklärt werden, insbesondere ob `StorCtl_Mod=3` + `OutWRte=10000` tatsächlich eine aktive Entladung ins Netz bewirkt und wie sich Modbus-Werte nach einem WR-Neustart verhalten.
