# Story: SolaX Gen4+ Inverter Support

## Voraussetzung

- HA-Integration: [SolaX Inverter Modbus](https://github.com/wills106/homeassistant-solax-modbus)
- **Nur Gen4+ Wechselrichter werden unterstuetzt** — bei der Wechselrichter-Auswahl im Wizard muss geprueft werden, ob es sich um einen Gen4 (oder neuer) handelt. Aeltere Generationen haben eingeschraenkte Modbus-Register und unterstuetzen RemoteControl nicht zuverlaessig.

---

## 1. Lesende Sensoren (erledigt)

Mapping ist definiert. Der User waehlt die Entities im Setup-Wizard. `pv_power_sensor_2` ist optional und nur relevant fuer SolaX-Anlagen mit einem sekundaeren PV-Eingang (Generator-Wechselrichter), der ueber Meter 2 angebunden ist.

| # | Config Key | SolaX Entity | Einheit | Status |
|---|-----------|-------------|---------|--------|
| 1 | `battery_soc_sensor` | `sensor.solax_inverter_battery_capacity` | % | fertig |
| 2 | `battery_capacity_sensor` | **manuell** (`battery_capacity_kwh`) | kWh | fertig — kein SolaX-Sensor vorhanden |
| 3 | `battery_power_sensor` | `sensor.solax_energy_dashboard_solax_battery_power` | W | fertig |
| 4 | `pv_power_sensor` | `sensor.solax_energy_dashboard_solax_solar_power` | W | fertig |
| 5 | `grid_power_sensor` | `sensor.solax_energy_dashboard_solax_grid_power` | W | fertig |
| 6 | `pv_power_sensor_2` | `sensor.solax_inverter_meter_2_measured_power` | W | fertig — optional |

**Achtung Einheiten:** SolaX liefert W, Huawei liefert kW. Der Optimizer rechnet intern mit kW — die Umrechnung muss in der SolaX-Implementierung oder generisch im Sensor-Layer passieren.

### Optionaler zweiter PV-Sensor (Generator-WR)

SolaX-Anlagen koennen einen separaten Generator-Wechselrichter haben, dessen Leistung ueber Meter 2 erfasst wird. Dafuer gibt es den optionalen Config Key `pv_power_sensor_2`.

- **Config Key:** `pv_power_sensor_2`
- **Default Entity:** `sensor.solax_inverter_meter_2_measured_power`
- **Auto-Fill:** Wenn der Default-Sensor in HA existiert, wird das Feld automatisch vorbelegt. Wenn nicht, bleibt es leer (kein zweiter PV-Eingang).
- **Logik:** Der Optimizer summiert `pv_power_sensor` + `pv_power_sensor_2` fuer den Gesamt-PV-Wert. Wenn `pv_power_sensor_2` nicht konfiguriert ist, wird nur `pv_power_sensor` verwendet (bisheriges Verhalten).

---

## 2. Schreibende Zugriffe

### 2.1 Steuerungsarchitektur (Zwei-Phasen-Schreibmodell)

Die SolaX Modbus Integration (`solax_modbus` von wills106) steuert den Wechselrichter NICHT ueber Custom-HA-Services. Stattdessen werden ausschliesslich Standard-HA-Entity-Services verwendet (`number.set_value`, `select.select_option`, `button.press`).

**Zwei-Phasen-Schreibarchitektur:**

```
Phase 1: Parameter setzen (DATA_LOCAL — nur im Integrations-Speicher, NICHT auf Modbus)
  select.solax_remotecontrol_power_control  = "Enabled Battery Control"
  number.solax_remotecontrol_active_power   = -3000  (Watts, negativ = Entladen)
  number.solax_remotecontrol_autorepeat_duration = 60  (Sekunden)

Phase 2: Trigger druecken (schreibt ALLE Parameter als ein write_multiple_registers auf 0x7C)
  button.solax_remotecontrol_trigger  -->  write_multiple_registers(0x7C, payload)
```

**Wichtig:** Alle `remotecontrol_*` Number/Select-Entities verwenden `WRITE_DATA_LOCAL`. Sie werden beim `number.set_value`-Aufruf NICHT an den Wechselrichter gesendet. Der tatsaechliche Modbus-Write passiert erst beim `button.press` auf den Trigger.

**Schreibmethoden der Integration:**

| Methode | Konstante | Beschreibung |
|---------|-----------|-------------|
| `WRITE_SINGLE_MODBUS` | 1 | Einzelregister-Write (Function Code 6) |
| `WRITE_MULTISINGLE_MODBUS` | 2 | Multi-Register-Kommando fuer ein Register |
| `WRITE_MULTI_MODBUS` | 4 | write_multiple_registers (Function Code 16) |
| `WRITE_DATA_LOCAL` | 3 | Speichert nur im Integrations-Speicher — NICHT an Inverter bis Trigger |

### 2.2 Register-Tabelle (Mode 1 Remote Control)

**Remote Control Registers (geschrieben durch Trigger ab 0x7C):**

| Offset | Abs. Addr | Name | Datentyp | Bereich | Einheit | Beschreibung |
|--------|-----------|------|----------|---------|---------|-------------|
| +0 | 0x7C | Remote Control Command Block Start | - | - | - | Write-Ziel fuer Trigger |
| +2 | 0x7E | Active Power | S32 | -30000..30000 | W | Batterie: + Laden, - Entladen |
| +4 | 0x80 | Reactive Power | S32 | -4000..4000 | VAR | Normal 0 |
| +6 | 0x82 | Duration | U16 | 0..28800 | s | Kommando-Slot-Dauer (Step: 60s) |
| +7 | 0x83 | Target SOC (Mode 3) | U16 | 0..100 | % | Nur fuer Mode 3 |
| +8 | 0x84 | Target Energy (Mode 2) | S32 | 0..30000 | Wh | Nur fuer Mode 2 |
| +10 | 0x86 | Charge/Discharge Power (Mode 2/3) | S32 | -30000..30000 | W | Modes 2 und 3 |
| +12 | 0x88 | Timeout | U16 | 0..28800 | s | Kommando-Ablauf (Step: 60s) |

**Batterie-Konfigurationsregister (direkte Modbus-Writes):**

| Adresse | Name | Datentyp | Min | Max | Einheit | Beschreibung |
|---------|------|----------|-----|-----|---------|-------------|
| 0x24 | battery_charge_max_current | Float | 0 | 20 | A | Max Ladestrom (Scale: 0.1 Gen4+) |
| 0x25 | battery_discharge_max_current | Float | 0 | 20 | A | Max Entladestrom |
| 0x61 | selfuse_discharge_min_soc | U16 | 10 | 100 | % | Min SOC fuer Self Use Modus |
| 0x65 | feedin_discharge_min_soc | U16 | 10 | 100 | % | Min SOC fuer Feedin Modus |
| 0xE0 | battery_charge_upper_soc | U16 | 10 | 100 | % | Max Lade-SOC |

**Work Mode Register (ACHTUNG: EEPROM!):**

| Adresse | Name | Optionen | EEPROM? |
|---------|------|----------|---------|
| 0x1F | charger_use_mode | 0: Self Use, 1: Force Time Use, 2: Back Up, 3: Feedin Priority | **JA** |
| 0x00 | lock_state | Passwort 2014 zum Entsperren | - |

**WARNUNG:** Schreiben auf `charger_use_mode` (0x1F) schreibt ins EEPROM. Dieses Register NICHT haeufig umschalten! Stattdessen Mode 1 Remote Control verwenden.

### 2.3 HA Entity-Mapping (Schreibende Entities)

**Steuerungs-Entities fuer Mode 1 (erforderlich):**

| Config Key | Default Entity ID | Platform | Zweck | Pflicht? |
|-----------|-------------------|----------|-------|----------|
| `solax_remotecontrol_power_control` | `select.solax_remotecontrol_power_control` | select | Modus-Auswahl | JA |
| `solax_remotecontrol_active_power` | `number.solax_remotecontrol_active_power` | number | Ziel-Leistung (W) | JA |
| `solax_remotecontrol_autorepeat_duration` | `number.solax_remotecontrol_autorepeat_duration` | number | Wiederholungs-Intervall (s) | JA |
| `solax_remotecontrol_trigger` | `button.solax_remotecontrol_trigger` | button | Kommando ausfuehren | JA |
| `solax_selfuse_discharge_min_soc` | `number.solax_selfuse_discharge_min_soc` | number | Min SOC Floor (%) | JA |

**Batterie SOC/Strom Entities (optional, direkte Writes):**

| Config Key | Default Entity ID | Platform | Zweck |
|-----------|-------------------|----------|-------|
| `solax_battery_charge_max_current` | `number.solax_battery_charge_max_current` | number | Ladestrom-Limit (A) |
| `solax_feedin_discharge_min_soc` | `number.solax_feedin_discharge_min_soc` | number | Min SOC fuer Feedin |
| `solax_battery_charge_upper_soc` | `number.solax_battery_charge_upper_soc` | number | Max Lade-SOC |

**Entity-Prefix variiert:** Die `solax_`-Praefix haengt von der Installations-Konfiguration ab. Moegliche Varianten: `solax_`, `solax_inverter_`, `solaxmodbus_`, oder benutzerdefiniert. Die Auto-Detection im Wizard sucht nach Entities die `*_remotecontrol_power_control` matchen.

### 2.4 remotecontrol_power_control Optionen

| Wert | Option String | Verhalten |
|------|--------------|----------|
| 0 | `Disabled` | Zurueck zum normalen Automatik-Betrieb |
| 1 | `Enabled Power Control` | Direkte Leistungssteuerung |
| 11 | `Enabled Grid Control` | Netz-Interface steuern (+ Laden aus Netz, - Export) |
| 12 | `Enabled Battery Control` | Batterie steuern (+ Laden, - Entladen) |
| 110 | `Enabled Self Use` | Self-Use Modus erzwingen via Remote Control |
| 120 | `Enabled Feedin Priority` | Feedin Priority erzwingen via Remote Control |
| 130 | `Enabled No Discharge` | Entladung verhindern (PV laedt Batterie, kein Grid-Discharge) |

**Leistungs-Vorzeichen-Konvention (Mode 1 Battery Control):**

```
Positiv active_power  = LADEN (Netz/PV -> Batterie)
Negativ active_power  = ENTLADEN (Batterie -> Netz/Haus)

Beispiel: active_power = -3000  --> Entladen mit 3000W
Beispiel: active_power =  2000  --> Laden mit 2000W
Beispiel: active_power =     0  --> Weder Laden noch Entladen (Batterie idle)
```

### 2.5 InverterBase-Methoden Implementierung

#### `async_set_charge_limit(power_kw)` — Laden begrenzen/blockieren

**Zweck:** Mit `power_kw=0` aufgerufen: Batterie-Laden blockieren, damit PV-Ueberschuss ins Netz geht (EEG Morgen-Einspeisung).

**Ansatz: "Enabled Battery Control" mit active_power=0 (empfohlen)**

Battery Control mit Leistung 0 sagt der Batterie explizit: nichts tun (weder Laden noch Entladen). PV-Ueberschuss geht ans Haus und dann ins Netz — genau was wir fuer EEG Morning Feed-in brauchen.

```python
async def async_set_charge_limit(self, power_kw: float) -> bool:
    if power_kw == 0:
        # Laden blockieren: Battery Control mit 0 = Batterie idle
        await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
        await self._set_number("remotecontrol_active_power", 0)
    else:
        # Teilweise Ladebegrenzung: Battery Control mit positiver Leistung
        power_w = int(power_kw * 1000)
        await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
        await self._set_number("remotecontrol_active_power", power_w)
    await self._set_number("remotecontrol_autorepeat_duration", 60)
    await self._press_trigger()
    return True
```

**Warum NICHT "Enabled No Discharge"?** Der Name ist irrefuehrend: "No Discharge" bedeutet die Batterie KANN laden, KANN NICHT entladen — also das Gegenteil von dem was wir wollen.

**Warum NICHT "Enabled Feedin Priority"?** Laut offizieller Doku (readthedocs) ist Feedin Priority eine **Emulation** des eingebauten Feedin-Priority-Modus, die den Target-Wert **ignoriert** und *"may not be as accurate/responsive as the builtin feedin_priority mode"*. "Enabled Battery Control" mit active_power=0 ist der offizielle, getestete Weg — bestaetigt durch die Beispiel-Automationen in der Integration-Doku.

#### `async_set_discharge(power_kw, target_soc)` — Erzwungene Entladung

**Zweck:** Batterie mit gegebener Leistung entladen fuer EEG Abend-Einspeisung.

```python
async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
    # Min SOC Floor setzen falls target_soc angegeben
    if target_soc is not None:
        min_soc = max(int(target_soc), 10)  # SolaX Minimum ist 10%
        await self._set_number("selfuse_discharge_min_soc", min_soc)

    # Battery Control Modus mit NEGATIVER Leistung fuer Entladung
    power_w = -abs(int(power_kw * 1000))  # Sicherstellen dass negativ
    await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
    await self._set_number("remotecontrol_active_power", power_w)
    await self._set_number("remotecontrol_autorepeat_duration", 60)
    await self._press_trigger()
    return True
```

**Target SOC Caveat:** Das `selfuse_discharge_min_soc` Register (0x61) setzt den minimalen SOC fuer den Self Use Modus. Waehrend Remote Control "Enabled Battery Control" wird dieses Limit moeglicherweise NICHT von der Firmware durchgesetzt. Der Optimizer prueft im regulaeren Zyklus den SOC und ruft `async_stop_forcible()` auf wenn das Ziel erreicht ist — kein extra Mechanismus noetig, dieselbe Logik wie beim Morgen-Check.

#### `async_stop_forcible()` — Zurueck auf Automatik

**Zweck:** Remote Control Kommando abbrechen und normalen Betrieb wiederherstellen.

```python
async def async_stop_forcible(self) -> bool:
    await self._set_select("remotecontrol_power_control", "Disabled")
    await self._set_number("remotecontrol_active_power", 0)
    await self._set_number("remotecontrol_autorepeat_duration", 0)  # Wiederholung stoppen
    await self._press_trigger()
    return True
```

**Wichtig:** `autorepeat_duration=0` VOR dem Trigger setzen, damit der Autorepeat-Timer der Integration geloescht wird.

#### `is_available` — Integration pruefen

**Zweck:** Pruefen ob die SolaX Modbus Integration geladen und verfuegbar ist.

```python
@property
def is_available(self) -> bool:
    entries = self._hass.config_entries.async_entries("solax_modbus")
    return any(entry.state.value == "loaded" for entry in entries)
```

#### Helper-Methoden

```python
SOLAX_DOMAIN = "solax_modbus"

# Entity Key -> Default Entity ID Mapping
SOLAX_ENTITY_DEFAULTS = {
    "remotecontrol_power_control": "select.solax_remotecontrol_power_control",
    "remotecontrol_active_power": "number.solax_remotecontrol_active_power",
    "remotecontrol_autorepeat_duration": "number.solax_remotecontrol_autorepeat_duration",
    "remotecontrol_trigger": "button.solax_remotecontrol_trigger",
    "selfuse_discharge_min_soc": "number.solax_selfuse_discharge_min_soc",
    "battery_charge_max_current": "number.solax_battery_charge_max_current",
}

async def _set_number(self, config_key: str, value: float) -> None:
    entity_id = self._config.get(
        f"solax_{config_key}", SOLAX_ENTITY_DEFAULTS[config_key]
    )
    await self._hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity_id, "value": value},
        blocking=True,
    )

async def _set_select(self, config_key: str, option: str) -> None:
    entity_id = self._config.get(
        f"solax_{config_key}", SOLAX_ENTITY_DEFAULTS[config_key]
    )
    await self._hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity_id, "option": option},
        blocking=True,
    )

async def _press_trigger(self) -> None:
    entity_id = self._config.get(
        "solax_remotecontrol_trigger", SOLAX_ENTITY_DEFAULTS["remotecontrol_trigger"]
    )
    await self._hass.services.async_call(
        "button", "press",
        {"entity_id": entity_id},
        blocking=True,
    )
```

### 2.6 Duration und Autorepeat-Strategie

Remote Control Kommandos haben eine begrenzte Lebensdauer. Wenn `duration` ablaeuft, kehrt der Wechselrichter zum vorherigen Betriebsmodus zurueck.

**Empfohlene Werte:**

| Parameter | Wert | Begruendung |
|-----------|------|-------------|
| `remotecontrol_autorepeat_duration` | 60 Sekunden | Wiederholungsfenster (>= Optimizer-Zyklus von 30s) |

**Wie Autorepeat funktioniert:**
1. Beim Trigger-Press mit `autorepeat_duration > 0` plant die Integration einen Timer
2. Der Timer sendet dasselbe Modbus-Kommando bei jedem Polling-Zyklus bis `autorepeat_duration` ablaeuft
3. Unser Optimizer triggert alle 30s neu, daher gibt `autorepeat_duration=60s` einen 2-fachen Sicherheitspuffer
4. `remotecontrol_duration` muss nicht explizit gesetzt werden — Autorepeat uebernimmt die Wiederholung

**Beim Stoppen:** `autorepeat_duration=0` setzen BEVOR der Trigger mit "Disabled" gedrueckt wird, damit der Autorepeat-Timer sicher geloescht wird.

### 2.7 Gen4 vs Gen5 vs Gen6 Kompatibilitaet

| Feature | Gen4 | Gen5 | Gen6 |
|---------|------|------|------|
| Mode 1 Remote Control | JA | JA | JA |
| Trigger Button (0x7C) | JA | JA | JA |
| selfuse_discharge_min_soc (0x61) | JA | JA | JA |
| battery_charge_upper_soc (0xE0) | JA | JA | JA |
| battery_charge_max_current (0x24) | Scale 0.1 | Scale 0.1 | Scale 0.1 |
| charger_use_mode (0x1F) | JA (EEPROM) | JA (EEPROM) | JA (EEPROM) |

**Fazit:** Gen4, Gen5 und Gen6 unterstuetzen alle Mode 1 mit identischem Register-Layout. Unterschiede liegen nur bei Maximalwerten (modellabhaengig, nicht generationsabhaengig).

**Gen2/Gen3 sind grundlegend anders:** Keine Remote Control Entities. Steuerung nur ueber `charger_use_mode` (EEPROM-Writes). NICHT unterstuetzt.

### 2.8 Caveats und Risiken

1. **Lock State muss entsperrt sein:** Der Wechselrichter hat ein `select.solax_lock_state` Entity. Bei gesperrtem Zustand scheitern alle Schreib-Operationen lautlos oder mit Fehler. Entsperren mit Passwort **2014** (Register 0x00). Im Setup-Wizard als Prerequisite pruefen.

2. **Target SOC nicht firmware-seitig enforced:** Waehrend "Enabled Battery Control" mit negativer Leistung kann der Wechselrichter unter `selfuse_discharge_min_soc` entladen. Das Min-SOC-Register gilt fuer den Self Use Betriebsmodus, nicht zwingend fuer Remote Control Kommandos. **Der Optimizer prueft den SOC im regulaeren Zyklus und wechselt auf Normalmodus wenn das Ziel erreicht ist.**

3. **Power Value Clamping:** Der Wechselrichter begrenzt die Leistung auf seine Nennleistung. Ein 3kW-Wechselrichter ignoriert ein 6kW-Kommando lautlos. Kein Fehler wird zurueckgegeben.

4. **Einheiten: SolaX = Watts, InverterBase = kW:** Alle SolaX Leistungs-Sensoren und Steuerungs-Register verwenden Watt. Unsere InverterBase ABC verwendet kW. Die SolaX-Implementierung MUSS umrechnen: `power_w = int(power_kw * 1000)`.

5. **Sleep Mode:** Der Wechselrichter kann nachts in den Sleep Mode gehen (kein PV, keine Last). Waehrend Sleep kann Modbus-Kommunikation fehlschlagen oder veraltete Werte liefern. Entity-States werden `unavailable`. Vor Kommando-Ausfuehrung Entity-Verfuegbarkeit pruefen.

6. **X1 Fit (AC-coupled) eingeschraenkt:** Der SolaX X1 Fit Gen4 ist ein AC-gekoppelter Retrofit-Wechselrichter. Er stellt moeglicherweise NICHT alle Remote Control Entities bereit (insbesondere `remotecontrol_trigger` kann fehlen). Im Setup pruefen ob `button.solax_remotecontrol_trigger` existiert.

7. **Entity-Prefix variiert:** Entity-Namen sind NICHT standardisiert. Der Prefix haengt von der Integrations-Konfiguration ab (`solax_`, `solax_inverter_`, `solaxmodbus_`, oder benutzerdefiniert). Auto-Detection via `*_remotecontrol_power_control` Pattern im Setup-Wizard erforderlich.

---

## 3. Code-Aenderungen (Uebersicht)

| # | Datei | Was |
|---|-------|-----|
| 1 | `inverter/solax.py` | **Neu:** SolaXInverter Klasse, erbt von InverterBase |
| 2 | `inverter/__init__.py` | Factory erweitern: `"solax_gen4": SolaXInverter` |
| 3 | `const.py` | Neue Konstanten: `INVERTER_TYPE_SOLAX`, `CONF_SOLAX_DEVICE_ID`, `INVERTER_PREREQUISITES` erweitern |
| 4 | `websocket_api.py` | `SOLAX_DEFAULTS` Dict, `_find_solax_device()`, `ws_detect_sensors()` erweitern, `check_domains` erweitern |
| 5 | `__init__.py` | Hardcoded Huawei-Fallbacks bereinigen (L93) |
| 6 | `const.py` | `DEFAULT_GRID_POWER_SENSOR` / `DEFAULT_BATTERY_POWER_SENSOR` inverter-type-aware machen oder entfernen |

---

## 4. Wizard-Erweiterung

- [ ] Wechselrichter-Auswahl: SolaX Gen4+ als Option hinzufuegen
- [ ] **Gen4-Pruefung:** Bei Auswahl von SolaX pruefen ob ein Gen4+ Inverter erkannt wird (aeltere Generationen ablehnen mit Hinweis)
- [ ] Auto-Detection: `SOLAX_DEFAULTS` fuer die 5 lesenden Sensoren vorbelegen
- [ ] Battery Capacity: Bei SolaX automatisch das manuelle Eingabefeld anzeigen (kein Sensor verfuegbar)
- [ ] Optionaler zweiter PV-Sensor: Bei SolaX Auto-Detection pruefen ob `sensor.solax_inverter_meter_2_measured_power` existiert. Wenn ja, `pv_power_sensor_2` automatisch vorbelegen. Im Wizard als optionales Feld anzeigen (Experten-Modus oder immer sichtbar wenn vorbelegt).

---

## 5. Offene Fragen

### Erledigt (durch Recherche beantwortet)

- [x] **Einheiten-Handling:** Umrechnung W <-> kW im SolaX-Inverter-Code (`power_w = int(power_kw * 1000)`). Siehe Caveat 4 in Abschnitt 2.8.
- [x] **RemoteControl Autorepeat:** `autorepeat_duration=60s` genuegt bei 30s Optimizer-Zyklus. Siehe Abschnitt 2.6.
- [x] **Enabled Feedin Priority vs Enabled Battery Control (power=0):** Geklaert — "Enabled Feedin Priority" ist laut offizieller Doku eine Emulation die den Target-Wert ignoriert und weniger praezise ist. "Enabled Battery Control" mit active_power=0 ist der offizielle, getestete Weg. Kein Hardware-Test noetig.

### Offen (Hardware-Test erforderlich)

- [ ] **Lock State Handling:** Muss vor jedem Schreibzyklus explizit entsperrt werden (Passwort 2014)? Oder reicht einmaliges Entsperren beim Setup? Hardware-Test noetig.
- [ ] **X1 Fit Kompatibilitaet:** Der SolaX X1 Fit (AC-coupled) hat moeglicherweise keinen `remotecontrol_trigger` Button. Auf echter Hardware pruefen ob das Entity existiert.
- [ ] **Gen4-Erkennung:** Wie erkennt man programmatisch ob es ein Gen4+ ist? (Firmware-Version? Modell-Sensor? `sensor.solax_inverter_power_type`?) Muss im Wizard getestet werden.
- [ ] **Multi-Inverter:** SolaX Energy Dashboard aggregiert bereits. Reicht das oder braucht es spezielle Behandlung fuer Anlagen mit mehreren Wechselrichtern?
- [ ] **Target SOC Enforcement:** Wird `selfuse_discharge_min_soc` waehrend Remote Control "Enabled Battery Control" von der Firmware beachtet? Wenn nicht, muss der Optimizer den SOC aktiv ueberwachen (bereits geplant im 30s-Zyklus).
