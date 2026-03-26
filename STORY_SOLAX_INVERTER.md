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

## 2. Schreibende Zugriffe (TODO)

Die SolaX Modbus Integration steuert den Wechselrichter ueber RemoteControl-Modi. Die konkreten HA-Services und Parameter muessen noch ermittelt und getestet werden.

### TODO: `async_set_charge_limit(power_kw)`

**Zweck:** Ladeleistung begrenzen. Mit `0` aufgerufen = Laden komplett blockieren.

**Huawei-Referenz:** `number.set_value` auf `number.batteries_maximale_ladeleistung`

**SolaX-Ansatz (zu recherchieren):**
- [ ] Welcher RemoteControl-Mode blockiert das Laden? (Mode 2/3? Oder `battery_charge_max_current` auf 0 setzen?)
- [ ] Kann `number.solax_inverter_battery_charge_max_current` (aktuell 30.0 A) auf 0 gesetzt werden?
- [ ] Oder muss der `charger_use_mode` umgestellt werden?
- [ ] Rueckgabewert / Fehlerbehandlung klaeren

### TODO: `async_set_discharge(power_kw, target_soc)`

**Zweck:** Erzwungene Entladung mit Ziel-SOC.

**Huawei-Referenz:** `huawei_solar.forcible_discharge_soc` mit device_id

**SolaX-Ansatz (zu recherchieren):**
- [ ] RemoteControl Mode 1 mit negativer Active Power? Oder dedizierter Discharge-Mode?
- [ ] `number.solax_inverter_remotecontrol_active_power` (Mode 1) — kann damit entladen werden?
- [ ] Target SOC: `number.solax_inverter_remotecontrol_target_soc_mode_3_direct` oder `feedin_discharge_min_soc`?
- [ ] Minimaler SOC-Floor bei SolaX Gen4? (Huawei: 12%)
- [ ] `button.solax_inverter_remotecontrol_trigger` zum Ausloesen noetig?
- [ ] Duration/Timeout: `number.solax_inverter_remotecontrol_duration` (aktuell 20s) — reicht das oder muss Autorepeat konfiguriert werden?

### TODO: `async_stop_forcible()`

**Zweck:** Zurueck auf Automatik-Betrieb.

**Huawei-Referenz:** (1) Max Charge Power restore + (2) `huawei_solar.stop_forcible_charge`

**SolaX-Ansatz (zu recherchieren):**
- [ ] RemoteControl beenden: `select.solax_inverter_remotecontrol_set_type` auf bestimmten Wert setzen?
- [ ] Oder Timeout ablaufen lassen? (aktuell 0s = unbegrenzt?)
- [ ] Charge Max Current wiederherstellen falls veraendert?
- [ ] Charger Use Mode zuruecksetzen falls veraendert?

### TODO: `is_available`

**Zweck:** Pruefen ob die SolaX-Integration geladen ist.

**Huawei-Referenz:** `config_entries.async_entries("huawei_solar")` → state == loaded

**SolaX-Ansatz:**
- [ ] `config_entries.async_entries("solax_modbus")` → state == loaded
- [ ] Zusaetzlich pruefen ob der Inverter online ist? (`sensor.solax_inverter_run_mode` != unavailable?)

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

- [ ] **Einheiten-Handling:** Wo wird W → kW konvertiert? Im SolaX-Inverter-Code oder generisch im Sensor-Layer?
- [ ] **Gen4-Erkennung:** Wie erkennt man programmatisch ob es ein Gen4 ist? (Firmware-Version? Modell-Sensor? `sensor.solax_inverter_power_type`?)
- [ ] **Multi-Inverter:** SolaX Energy Dashboard aggregiert bereits. Reicht das oder braucht es spezielle Behandlung?
- [ ] **RemoteControl Autorepeat:** Optimizer-Zyklus ist 30s. RemoteControl Duration muss >= 30s sein oder Autorepeat aktiv.
