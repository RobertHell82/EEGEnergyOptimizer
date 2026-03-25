# Huawei Inverter Sensor Reads & Write Operations - Research

**Researched:** 2026-03-25
**Domain:** Inverter abstraction layer - complete inventory for porting
**Confidence:** HIGH (direct code analysis, no external sources needed)

## Summary

Complete inventory of all inverter/battery-dependent sensor reads and write operations currently implemented for Huawei SUN2000. Categorized into (A) HA entity state reads consumed by the optimizer/sensors, (B) HA service calls that write to the inverter, and (C) Huawei-specific config parameters. This serves as the porting checklist for adding SolaX, Fronius, or other inverter types.

---

## A. Sensor READS (HA Entity State Reads)

These are external HA entities whose `.state` or `.attributes` are read via `hass.states.get()`. A new inverter implementation must provide equivalent entities (or the user must map them in config).

### A1. Battery Sensors (directly inverter-dependent)

| # | Config Key | Huawei Default Entity | Data Type | Unit | Where Read | Purpose |
|---|------------|----------------------|-----------|------|------------|---------|
| 1 | `battery_soc_sensor` | `sensor.batteries_batterieladung` | float (0-100) | % | `optimizer.py:_gather_snapshot()` L190-193 | Battery state of charge - core input for discharge decisions |
| 2 | `battery_capacity_sensor` | `sensor.batterien_akkukapazitat` | float | kWh or Wh | `optimizer.py:_resolve_capacity()` L331-345, `sensor.py:BatteryMissingEnergySensor._resolve_capacity()` L392-406 | Battery total capacity - used for missing energy calc, min-SOC calc |
| 3 | `battery_power_sensor` | `sensor.batteries_lade_entladeleistung` | float | kW | `sensor.py:HausverbrauchSensor.async_update()` L494 | Battery charge/discharge power (positive=charging, negative=discharging) |

### A2. PV & Grid Sensors (inverter-dependent)

| # | Config Key | Huawei Default Entity | Data Type | Unit | Where Read | Purpose |
|---|------------|----------------------|-----------|------|------------|---------|
| 4 | `pv_power_sensor` | `sensor.inverter_eingangsleistung` | float | kW | `sensor.py:HausverbrauchSensor.async_update()` L493, `__init__.py:async_backfill_hausverbrauch_stats()` L93 | PV input power - used for Hausverbrauch calculation |
| 5 | `grid_power_sensor` | `sensor.power_meter_wirkleistung` | float | kW | `sensor.py:HausverbrauchSensor.async_update()` L495, `__init__.py:async_backfill_hausverbrauch_stats()` L95 | Grid active power (positive=export, negative=import) |

### A3. Non-inverter Reads (inverter-independent, no porting needed)

| # | Entity | Where Read | Purpose |
|---|--------|------------|---------|
| 6 | `sun.sun` (attributes: `next_rising`, `next_setting`) | `optimizer.py:_get_sun_times()` L351-373, `sensor.py:SunriseForecastSensor` L307-313 | Sunrise/sunset times for morning/evening windows |
| 7 | Forecast entities (Solcast or Forecast.Solar, user-configured) | `forecast_provider.py:SolcastProvider/ForecastSolarProvider.get_forecast()` | PV production forecasts (remaining today + tomorrow) |
| 8 | `number.batteries_maximale_ladeleistung` (attributes: `max`) | `inverter/huawei.py:_get_max_charge_power()` L32-37 | **Huawei-specific**: reads max charge power attribute to restore after blocking |

### A4. Indirect Reads (via own calculated sensor)

| # | Entity | Where Read | Purpose |
|---|--------|------------|---------|
| 9 | `sensor.eeg_energy_optimizer_hausverbrauch` | `coordinator.py` via recorder statistics | Own calculated sensor used as consumption data source. Derived from sensors #3, #4, #5 |

---

## B. Inverter WRITES (HA Service Calls)

These are the commands the optimizer sends to control the inverter. Defined in `InverterBase` ABC, implemented in `HuaweiInverter`.

### B1. Abstract Interface (`inverter/base.py`)

```python
class InverterBase(ABC):
    async def async_set_charge_limit(self, power_kw: float) -> bool
    async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool
    async def async_stop_forcible(self) -> bool
    @property
    def is_available(self) -> bool
```

### B2. Huawei Implementation Details (`inverter/huawei.py`)

| # | Method | HA Service Call | Service Data | When Called |
|---|--------|----------------|--------------|------------|
| 1 | `async_set_charge_limit(0)` | `number.set_value` | `entity_id: number.batteries_maximale_ladeleistung`, `value: 0` | Morning charge blocking (STATE_MORGEN_EINSPEISUNG) |
| 2 | `async_set_discharge(power_kw, target_soc)` | `huawei_solar.forcible_discharge_soc` | `device_id: {huawei_device_id}`, `power: {watts_str}`, `target_soc: {soc}` | Evening discharge (STATE_ABEND_ENTLADUNG) |
| 3 | `async_stop_forcible()` | `number.set_value` + `huawei_solar.stop_forcible_charge` | (1) Restore max charge power, (2) Stop forcible mode with device_id | Return to normal (STATE_NORMAL), also used for test_inverter and manual_stop |
| 4 | `is_available` (property) | Checks `hass.config_entries.async_entries("huawei_solar")` | Returns True if any entry has `state.value == "loaded"` | Before every inverter command via `_get_inverter()` in websocket_api.py |

### B3. Call Sites (where inverter methods are invoked)

| Call Site | Method | Trigger |
|-----------|--------|---------|
| `optimizer.py:_execute()` L794-795 | `async_set_charge_limit(0)` | 30s optimizer cycle, state=Morgen-Einspeisung, mode=Ein |
| `optimizer.py:_execute()` L797-799 | `async_set_discharge(power, soc)` | 30s optimizer cycle, state=Abend-Entladung, mode=Ein |
| `optimizer.py:_execute()` L802 | `async_stop_forcible()` | 30s optimizer cycle, state=Normal, mode=Ein |
| `websocket_api.py:ws_test_inverter()` L255 | `async_stop_forcible()` | Panel: test inverter button |
| `websocket_api.py:ws_manual_stop()` L291 | `async_stop_forcible()` | Panel: manual stop button |
| `websocket_api.py:ws_manual_discharge()` L332 | `async_set_discharge(power, soc)` | Panel: manual discharge button |
| `websocket_api.py:ws_manual_block_charge()` L368 | `async_set_charge_limit(0)` | Panel: manual block charge button |

---

## C. Huawei-Specific Config Parameters

| Config Key | Constant | Where Used | Porting Note |
|------------|----------|------------|--------------|
| `inverter_type` | `CONF_INVERTER_TYPE` | `__init__.py:create_inverter()`, `websocket_api.py:ws_detect_sensors()` | Already generic - factory pattern selects implementation |
| `huawei_device_id` | `CONF_HUAWEI_DEVICE_ID` | `inverter/huawei.py:__init__()` L24, `websocket_api.py:ws_detect_sensors()` L230 | **Huawei-specific**: device_id for service calls. Other inverters may need different identifiers (e.g., Modbus host/port for SolaX) |
| `battery_soc_sensor` | `CONF_BATTERY_SOC_SENSOR` | optimizer.py, sensor.py | Generic - user selects entity. Huawei default: `sensor.batteries_batterieladung` |
| `battery_capacity_sensor` | `CONF_BATTERY_CAPACITY_SENSOR` | optimizer.py, sensor.py | Generic - user selects entity. Huawei default: `sensor.batterien_akkukapazitat` |
| `battery_capacity_kwh` | `CONF_BATTERY_CAPACITY_KWH` | optimizer.py, sensor.py | Generic fallback when sensor unavailable |
| `pv_power_sensor` | `CONF_PV_POWER_SENSOR` | sensor.py, __init__.py | Generic - user selects entity. Huawei default: `sensor.inverter_eingangsleistung` |
| `grid_power_sensor` | `CONF_GRID_POWER_SENSOR` | sensor.py, __init__.py | Generic - user selects entity. Huawei default: `sensor.power_meter_wirkleistung` |
| `battery_power_sensor` | `CONF_BATTERY_POWER_SENSOR` | sensor.py, __init__.py | Generic - user selects entity. Huawei default: `sensor.batteries_lade_entladeleistung` |

---

## D. Hardcoded Huawei References (must be abstracted for porting)

| Location | Hardcoded Value | What It Does | Porting Impact |
|----------|----------------|--------------|----------------|
| `inverter/huawei.py` L16 | `number.batteries_maximale_ladeleistung` | Charge limit entity for blocking | New inverters need their own charge-blocking mechanism |
| `inverter/huawei.py` L36 | `5000.0` (fallback max charge power) | Default max W if entity unavailable | Inverter-specific default |
| `inverter/huawei.py` L65 | `12` (minimum target SOC floor) | Huawei minimum SOC for forcible discharge | May differ per inverter |
| `websocket_api.py` L32-38 | `HUAWEI_DEFAULTS` dict | Default entity IDs for auto-detection | Each inverter type needs its own defaults dict |
| `websocket_api.py` L41-58 | `_find_huawei_battery_device()` | Device registry lookup for `huawei_solar` domain | Each inverter needs its own device detection logic |
| `websocket_api.py` L183 | `check_domains = ["huawei_solar", ...]` | Prerequisite check | Must add new inverter integration domains |
| `websocket_api.py` L207 | `hass.config_entries.async_entries("huawei_solar")` | Detect if Huawei is loaded | Detect function currently only handles Huawei |
| `__init__.py` L93 | `"sensor.inverter_eingangsleistung"` | Backfill fallback PV sensor | Huawei-specific fallback |
| `const.py` L33-34 | `DEFAULT_GRID_POWER_SENSOR`, `DEFAULT_BATTERY_POWER_SENSOR` | Huawei entity IDs as defaults | These defaults are Huawei-specific entity names |

---

## E. Data Flow Summary

```
EXTERNAL HA ENTITIES (inverter-dependent)          WRITES TO INVERTER
================================                   ==================
battery_soc_sensor --------\
battery_capacity_sensor ----+---> optimizer.py     optimizer._execute()
pv_power_sensor ------\     |     _gather_snapshot()   |
battery_power_sensor --+--> |        |                  +--> async_set_charge_limit(0)
grid_power_sensor ----/     |        v                  |    [number.set_value -> 0W]
  (Hausverbrauch calc)      |     Snapshot              |
                            |        |                  +--> async_set_discharge(kW, soc)
sun.sun -------------------/      _evaluate()           |    [huawei_solar.forcible_discharge_soc]
                                     |                  |
forecast entities                 Decision              +--> async_stop_forcible()
  (Solcast/Forecast.Solar)           |                       [number.set_value -> max + stop_forcible]
                                     v
                              EntscheidungsSensor
                              (14 attributes)
```

---

## F. Porting Checklist for New Inverter Type

To add a new inverter (e.g., SolaX, Fronius), implement:

1. **`inverter/{name}.py`** - Subclass `InverterBase`, implement 3 write methods + `is_available`
2. **Register in `inverter/__init__.py`** - Add to `INVERTER_TYPES` dict
3. **Add default entity mappings** - Like `HUAWEI_DEFAULTS` in websocket_api.py for auto-detection
4. **Add device detection function** - Like `_find_huawei_battery_device()` for the new integration's domain
5. **Add prerequisite domain** - In `INVERTER_PREREQUISITES` (const.py) and `ws_check_prerequisites` check_domains list
6. **Add config key constant** - Like `CONF_HUAWEI_DEVICE_ID` if new inverter needs specific connection params
7. **Update `ws_detect_sensors()`** - Handle detection for the new inverter type (currently hardcoded to Huawei only)
8. **Update `DEFAULT_*` constants** - Currently Huawei entity names; make inverter-type-aware or remove defaults

### What Does NOT Need Porting (already generic)

- Optimizer logic (`optimizer.py`) - reads config keys, not Huawei entities directly
- Sensor platform (`sensor.py`) - uses config-mapped entity IDs
- Consumption coordinator (`coordinator.py`) - reads from own Hausverbrauch sensor
- Forecast provider (`forecast_provider.py`) - independent of inverter type
- Config flow (`config_flow.py`) - 1-click, no inverter specifics
- Panel WebSocket commands for manual control (`ws_manual_*`) - call abstract inverter methods

## Sources

### Primary (HIGH confidence)
- Direct code analysis of all files in `custom_components/eeg_energy_optimizer/`
