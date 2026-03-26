# Necessary Sensors for a New Inverter

## Lesende Sensoren (5 Pflicht + 1 Optional)

| # | Config Key | Beschreibung | Typ | Einheit | Vorzeichen |
|---|-----------|-------------|-----|---------|------------|
| 1 | `battery_soc_sensor` | Batterie-Ladestand | float 0–100 | % | — |
| 2 | `battery_capacity_sensor` | Gesamtkapazitaet der Batterie | float | kWh (oder Wh) | — |
| 3 | `battery_power_sensor` | Aktuelle Lade-/Entladeleistung | float | kW | + = Laden, − = Entladen |
| 4 | `pv_power_sensor` | PV-Eingangsleistung | float | kW | immer positiv |
| 5 | `grid_power_sensor` | Netz-Wirkleistung | float | kW | + = Export, − = Import |
| 6 | `pv_power_sensor_2` | Zweiter PV-Eingang (optional, Generator-WR) | float | kW | immer positiv |

Der User mappt diese 5 Pflicht-Sensoren im Setup-Wizard auf die Entities seiner Integration. Der Optimizer liest sie nur ueber Config Keys — nie ueber hardcodierte Entity-IDs.

`pv_power_sensor_2` ist optional und nur relevant wenn ein zweiter PV-Eingang (z.B. Generator-Wechselrichter) vorhanden ist. Der Optimizer summiert beide PV-Sensoren fuer den Gesamtwert.

## Schreibende Zugriffe (3 Methoden + 1 Property)

| # | Methode | Parameter | Rueckgabe | Was sie tut |
|---|---------|-----------|----------|-------------|
| 1 | `async_set_charge_limit(power_kw)` | float (kW), 0 = blockieren | bool | Ladeleistung begrenzen / Laden blockieren |
| 2 | `async_set_discharge(power_kw, target_soc)` | float (kW), float (%) optional | bool | Erzwungene Entladung starten |
| 3 | `async_stop_forcible()` | — | bool | Alles zuruecksetzen auf Automatik |
| 4 | `is_available` (Property) | — | bool | Ist die Inverter-Integration geladen? |

## Sensor-Mapping: Huawei vs. SolaX

Die folgende Tabelle zeigt das Mapping fuer alle 5 Pflicht-Sensoren sowie den optionalen 6. Sensor (`pv_power_sensor_2`).

| # | Config Key | Huawei Entity | SolaX Entity (solax_modbus) | Hinweis |
|---|-----------|--------------|----------------------------|---------|
| 1 | `battery_soc_sensor` | `sensor.batteries_batterieladung` | `sensor.solax_inverter_battery_capacity` | Gleiche Einheit (%), SolaX-Name irrefuehrend — ist der SOC, nicht die Kapazitaet |
| 2 | `battery_capacity_sensor` | `sensor.batterien_akkukapazitat` | **kein Sensor vorhanden** → `battery_capacity_kwh` manuell eingeben | Huawei liefert kWh, SolaX hat kein Modbus-Register dafuer |
| 3 | `battery_power_sensor` | `sensor.batteries_lade_entladeleistung` | `sensor.solax_energy_dashboard_solax_battery_power` | Huawei: kW, SolaX: W. Vorzeichen gleich: + Laden, − Entladen |
| 4 | `pv_power_sensor` | `sensor.inverter_eingangsleistung` | `sensor.solax_energy_dashboard_solax_solar_power` | Huawei: kW, SolaX: W |
| 5 | `grid_power_sensor` | `sensor.power_meter_wirkleistung` | `sensor.solax_energy_dashboard_solax_grid_power` | Huawei: kW, SolaX: W. Vorzeichen gleich: + Export, − Import |
| 6 | `pv_power_sensor_2` | **nicht vorhanden** (Huawei hat keinen Meter 2) | `sensor.solax_inverter_meter_2_measured_power` | Optional: nur bei SolaX mit Generator-WR. Huawei: nicht relevant |

**Wichtig:** Huawei liefert Werte in kW, SolaX in W — die Umrechnung muss im Code beruecksichtigt werden.

## Schreibende Zugriffe: Huawei-Referenz

| Methode | Huawei HA Service |
|---------|------------------|
| `async_set_charge_limit` | `number.set_value` auf `number.batteries_maximale_ladeleistung` (kW → int Watt) |
| `async_set_discharge` | `huawei_solar.forcible_discharge_soc` mit device_id (kW → String Watt, SOC min 12%) |
| `async_stop_forcible` | (1) `number.set_value` max restore + (2) `huawei_solar.stop_forcible_charge` |
| `is_available` | `config_entries.async_entries("huawei_solar")` → state == loaded |
