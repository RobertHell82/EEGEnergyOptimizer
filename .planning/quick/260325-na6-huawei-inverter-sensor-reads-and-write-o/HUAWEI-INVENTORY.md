# Huawei SUN2000 Inverter Dependency Inventory

**Date:** 2026-03-25
**Purpose:** Porting reference for adding new inverter types (SolaX, Fronius, etc.)
**Codebase version:** v0.3.16
**Root path:** `custom_components/eeg_energy_optimizer/`

This document catalogs every Huawei-specific touchpoint in the EEG Energy Optimizer codebase. Use it as the sole reference when implementing a new inverter type -- it maps all sensor reads, write operations, config parameters, and hardcoded references so you don't need to grep the codebase yourself.

---

## A. Sensor Reads (HA Entity State Reads)

These are external HA entities whose `.state` or `.attributes` are read via `hass.states.get()`. A new inverter implementation must provide equivalent entities (or the user must map them in config).

### A1. Battery Sensors (directly inverter-dependent)

| # | Config Key | Huawei Default Entity | Data Type | Unit | Source File:Line | Purpose |
|---|------------|----------------------|-----------|------|------------------|---------|
| 1 | `battery_soc_sensor` | `sensor.batteries_batterieladung` | float (0-100) | % | `optimizer.py` L190-193 | Battery state of charge -- core input for discharge and morning delay decisions |
| 2 | `battery_capacity_sensor` | `sensor.batterien_akkukapazitat` | float | kWh or Wh | `optimizer.py` L331-345, `sensor.py` L392-406 | Battery total capacity -- used for missing energy calc, dynamic min-SOC calc. Auto-detects Wh vs kWh (>1000 threshold or unit_of_measurement attribute) |
| 3 | `battery_power_sensor` | `sensor.batteries_lade_entladeleistung` | float | kW | `sensor.py` L494 | Battery charge/discharge power (positive=charging, negative=discharging). Used in Hausverbrauch calculation |

### A2. PV and Grid Sensors (inverter-dependent)

| # | Config Key | Huawei Default Entity | Data Type | Unit | Source File:Line | Purpose |
|---|------------|----------------------|-----------|------|------------------|---------|
| 4 | `pv_power_sensor` | `sensor.inverter_eingangsleistung` | float | kW | `sensor.py` L493, `__init__.py` L93 | PV input power -- used for Hausverbrauch calculation and backfill |
| 5 | `grid_power_sensor` | `sensor.power_meter_wirkleistung` | float | kW | `sensor.py` L495, `__init__.py` L95 | Grid active power (positive=export, negative=import). Used in Hausverbrauch calculation and backfill |

### A3. Huawei-Only Reads (not config-mapped)

| # | Entity | Data Type | Unit | Source File:Line | Purpose |
|---|--------|-----------|------|------------------|---------|
| 6 | `number.batteries_maximale_ladeleistung` (`.attributes.max`) | float | W | `inverter/huawei.py` L32-37 | Reads max charge power attribute to restore after blocking. Hardcoded in `MAX_CHARGE_POWER_ENTITY` constant. Falls back to `5000.0` W if entity unavailable |

### A4. Non-Inverter Reads (no porting needed)

These reads are inverter-independent. Listed for completeness.

| # | Entity | Source File:Line | Purpose | Porting? |
|---|--------|------------------|---------|----------|
| 7 | `sun.sun` (attributes: `next_rising`, `next_setting`) | `optimizer.py` L351-373, `sensor.py` L307-313 | Sunrise/sunset times for morning/evening windows | No porting needed |
| 8 | Forecast entities (Solcast or Forecast.Solar, user-configured) | `forecast_provider.py` | PV production forecasts (remaining today + tomorrow) | No porting needed |

### A5. Indirect Reads (derived sensor, no porting needed)

| # | Entity | Source File | Purpose | Porting? |
|---|--------|-------------|---------|----------|
| 9 | `sensor.eeg_energy_optimizer_hausverbrauch` | `coordinator.py` via recorder statistics | Own calculated sensor used as consumption data source. Derived from sensors #3, #4, #5 above | No porting needed (reads from recorder) |

---

## B. Inverter Writes (Service Calls)

These are the commands the optimizer sends to control the inverter. Defined abstractly in `InverterBase`, implemented concretely in `HuaweiInverter`.

### B1. Abstract Interface (`inverter/base.py`)

```python
class InverterBase(ABC):
    def __init__(self, hass: Any, config: dict) -> None:
        self._hass = hass
        self._config = config

    @abstractmethod
    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit in kW. 0 = block charging."""

    @abstractmethod
    async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
        """Start forced battery discharge at given power. Optional SOC floor."""

    @abstractmethod
    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the inverter connection/service is available."""
```

All 3 write methods return `bool` (True=success, False=failure). The `is_available` property gates all inverter interactions.

### B2. Huawei Implementation (`inverter/huawei.py`)

| # | Abstract Method | HA Service | Service Data | Behavior |
|---|----------------|------------|--------------|----------|
| 1 | `async_set_charge_limit(power_kw)` | `number.set_value` | `entity_id: "number.batteries_maximale_ladeleistung"`, `value: {power_kw * 1000}` (int watts) | Sets max charge power. Called with `0` to block charging during morning feed-in |
| 2 | `async_set_discharge(power_kw, target_soc)` | `huawei_solar.forcible_discharge_soc` | `device_id: {huawei_device_id}`, `power: {str(int(power_kw * 1000))}` (string watts), `target_soc: max(int(target_soc), 12)` | Starts forced discharge. Target SOC floored at 12% (Huawei hardware minimum) |
| 3 | `async_stop_forcible()` | Two calls: (1) `number.set_value` then (2) `huawei_solar.stop_forcible_charge` | (1) `entity_id: "number.batteries_maximale_ladeleistung"`, `value: {max_power}` (restored from entity attribute); (2) `device_id: {huawei_device_id}` | Restores max charge power to hardware maximum, then stops any forcible mode |
| 4 | `is_available` (property) | Checks `hass.config_entries.async_entries("huawei_solar")` | n/a | Returns `True` if any huawei_solar config entry has `state.value == "loaded"` |

**Implementation notes:**
- `async_set_charge_limit` converts kW to integer watts
- `async_set_discharge` converts kW to string watts (Huawei service requirement), floors target SOC at 12
- `async_stop_forcible` reads `MAX_CHARGE_POWER_ENTITY` attribute `max` (default 5000 W) before restoring
- All methods use `blocking=True` for synchronous execution
- All methods catch `Exception` broadly and return `False` on failure

### B3. Call Sites (where inverter methods are invoked)

| # | Call Site | Method Called | Trigger |
|---|-----------|-------------|---------|
| 1 | `optimizer.py:_execute()` L794-795 | `async_set_charge_limit(0)` | 30s optimizer cycle, state=Morgen-Einspeisung, mode=Ein |
| 2 | `optimizer.py:_execute()` L797-799 | `async_set_discharge(power_kw, target_soc)` | 30s optimizer cycle, state=Abend-Entladung, mode=Ein |
| 3 | `optimizer.py:_execute()` L802 | `async_stop_forcible()` | 30s optimizer cycle, state=Normal, mode=Ein |
| 4 | `websocket_api.py:ws_test_inverter()` L255 | `async_stop_forcible()` | Panel: test inverter button |
| 5 | `websocket_api.py:ws_manual_stop()` L291 | `async_stop_forcible()` | Panel: manual stop button |
| 6 | `websocket_api.py:ws_manual_discharge()` L332 | `async_set_discharge(power_kw, target_soc)` | Panel: manual discharge button |
| 7 | `websocket_api.py:ws_manual_block_charge()` L368 | `async_set_charge_limit(0)` | Panel: manual block charge button |

All call sites access the inverter through the abstract `InverterBase` interface -- they are already generic and require no changes for porting.

---

## C. Config Parameters

| Config Key | Constant in `const.py` | Generic? | Porting Note |
|------------|----------------------|----------|--------------|
| `inverter_type` | `CONF_INVERTER_TYPE` (L5) | Yes | Factory pattern in `inverter/__init__.py` selects implementation. Value: `"huawei_sun2000"` |
| `huawei_device_id` | `CONF_HUAWEI_DEVICE_ID` (L12) | **No** | Huawei-specific: device registry ID for service calls. Other inverters may need different identifiers (e.g., Modbus host/port for SolaX) |
| `battery_soc_sensor` | `CONF_BATTERY_SOC_SENSOR` (L6) | Yes | User selects entity. Huawei default: `sensor.batteries_batterieladung` |
| `battery_capacity_sensor` | `CONF_BATTERY_CAPACITY_SENSOR` (L7) | Yes | User selects entity. Huawei default: `sensor.batterien_akkukapazitat` |
| `battery_capacity_kwh` | `CONF_BATTERY_CAPACITY_KWH` (L8) | Yes | Manual fallback when capacity sensor unavailable |
| `pv_power_sensor` | `CONF_PV_POWER_SENSOR` (L9) | Yes | User selects entity. Huawei default: `sensor.inverter_eingangsleistung` |
| `grid_power_sensor` | `CONF_GRID_POWER_SENSOR` (L10) | Yes | User selects entity. Huawei default: `sensor.power_meter_wirkleistung` |
| `battery_power_sensor` | `CONF_BATTERY_POWER_SENSOR` (L11) | Yes | User selects entity. Huawei default: `sensor.batteries_lade_entladeleistung` |

**Note:** All sensor config keys are generic (user maps entities in the wizard). The only Huawei-specific config key is `huawei_device_id`. New inverter types will likely need their own connection parameter (e.g., `solax_modbus_host`).

---

## D. Hardcoded Huawei References

These are the specific locations in the codebase that contain Huawei-specific values. Each must be addressed when porting to a new inverter type.

| # | File:Line | Hardcoded Value | What It Does | Porting Action |
|---|-----------|----------------|--------------|----------------|
| 1 | `inverter/huawei.py` L16 | `"number.batteries_maximale_ladeleistung"` | Entity ID for max charge power (used for blocking and restoring) | New inverter needs its own charge-blocking mechanism. May not use a number entity at all |
| 2 | `inverter/huawei.py` L36 | `5000.0` (fallback W) | Default max charge power if entity attribute unavailable | Inverter-specific default. SolaX Gen4 max may differ |
| 3 | `inverter/huawei.py` L65 | `12` (minimum target SOC) | Hardware minimum SOC floor for forcible discharge | May differ per inverter model. Some inverters have configurable minimums |
| 4 | `websocket_api.py` L32-38 | `HUAWEI_DEFAULTS` dict | Maps config keys to default Huawei entity IDs for auto-detection in wizard | Each inverter type needs its own defaults dict (e.g., `SOLAX_DEFAULTS`) |
| 5 | `websocket_api.py` L41-58 | `_find_huawei_battery_device()` | Searches device registry for `huawei_solar` domain devices | Each inverter needs its own device detection function |
| 6 | `websocket_api.py` L183 | `["huawei_solar", "solcast_solar", "forecast_solar"]` | check_domains list for prerequisite check | Must add new inverter integration domain (e.g., `"solax_modbus"`) |
| 7 | `websocket_api.py` L207 | `hass.config_entries.async_entries("huawei_solar")` | Checks if Huawei integration is loaded before detection | `ws_detect_sensors()` currently only handles Huawei. Must be generalized |
| 8 | `__init__.py` L93 | `"sensor.inverter_eingangsleistung"` | Fallback PV sensor ID for backfill when config is empty | Huawei-specific entity name as fallback. Should use inverter-type-aware defaults |
| 9 | `const.py` L33 | `"sensor.power_meter_wirkleistung"` | `DEFAULT_GRID_POWER_SENSOR` constant | Huawei-specific entity name used as default in sensor.py and __init__.py |
| 10 | `const.py` L34 | `"sensor.batteries_lade_entladeleistung"` | `DEFAULT_BATTERY_POWER_SENSOR` constant | Huawei-specific entity name used as default in sensor.py and __init__.py |
| 11 | `const.py` L14 | `"huawei_sun2000"` | `INVERTER_TYPE_HUAWEI` constant | Inverter type identifier. Already used correctly via factory pattern |
| 12 | `const.py` L16-18 | `INVERTER_PREREQUISITES` dict | Maps inverter type to required HA integration domain | Must add new entry for each inverter type |
| 13 | `inverter/__init__.py` L13-15 | `INVERTER_TYPES` dict with `"huawei_sun2000": HuaweiInverter` | Factory registry for inverter creation | Must register new inverter class here |

---

## E. Data Flow Diagram

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
  (Solcast/Forecast.Solar)           |                       [number.set_value -> max +
                                     v                        huawei_solar.stop_forcible_charge]
                              EntscheidungsSensor
                              (decision + 26 attributes)


MANUAL CONTROLS (via WebSocket API)
====================================
ws_manual_block_charge  ---> async_set_charge_limit(0)
ws_manual_discharge     ---> async_set_discharge(power_kw, target_soc)
ws_manual_stop          ---> async_stop_forcible()
ws_test_inverter        ---> async_stop_forcible()
```

**Read flow:** Config-mapped entity IDs are resolved at runtime via `hass.states.get()`. The optimizer never references Huawei entity names directly -- it uses config keys. The only exception is the `MAX_CHARGE_POWER_ENTITY` in `inverter/huawei.py`, which is internal to the Huawei implementation.

**Write flow:** All writes go through the `InverterBase` abstract interface. The optimizer and WebSocket handlers call abstract methods; only `HuaweiInverter` knows about Huawei-specific service calls.

---

## F. Porting Checklist for New Inverter Type

### Must Implement (8 steps)

| # | Step | File(s) | What to Do |
|---|------|---------|------------|
| 1 | Create inverter module | `inverter/{name}.py` | Subclass `InverterBase`, implement `async_set_charge_limit()`, `async_set_discharge()`, `async_stop_forcible()`, and `is_available` property |
| 2 | Register in factory | `inverter/__init__.py` L13-15 | Add entry to `INVERTER_TYPES` dict: `"{type_id}": NewInverter` |
| 3 | Add config key constant | `const.py` | Add `CONF_{NAME}_DEVICE_ID` (or equivalent connection parameter) and `INVERTER_TYPE_{NAME}` constant |
| 4 | Add prerequisite mapping | `const.py` L16-18 | Add entry to `INVERTER_PREREQUISITES` dict |
| 5 | Add default entity mappings | `websocket_api.py` | Create `{NAME}_DEFAULTS` dict (like `HUAWEI_DEFAULTS` at L32-38) with default sensor entity IDs |
| 6 | Add device detection function | `websocket_api.py` | Create `_find_{name}_device()` (like `_find_huawei_battery_device()` at L41-58) |
| 7 | Update `ws_detect_sensors()` | `websocket_api.py` L200-232 | Handle detection for the new inverter type (currently hardcoded to Huawei only) |
| 8 | Update `ws_check_prerequisites()` | `websocket_api.py` L183 | Add new integration domain to `check_domains` list |

### Should Review (3 items)

| # | File:Line | Issue | Recommendation |
|---|-----------|-------|----------------|
| 1 | `__init__.py` L93 | Hardcoded fallback `"sensor.inverter_eingangsleistung"` | Make inverter-type-aware or remove fallback entirely (config should always have the value after wizard) |
| 2 | `const.py` L33-34 | `DEFAULT_GRID_POWER_SENSOR` and `DEFAULT_BATTERY_POWER_SENSOR` are Huawei entity names | Either make defaults inverter-type-aware or remove defaults (rely on config from wizard) |
| 3 | `inverter/huawei.py` L65 | SOC floor of `12` is hardware-specific | Document that new implementations should set their own minimum SOC floor |

### Already Generic (NO changes needed)

These files/modules use config-mapped entity IDs or abstract interfaces and require zero modifications for a new inverter type:

| File | Why It's Generic |
|------|-----------------|
| `optimizer.py` | Reads sensors via config keys (`CONF_BATTERY_SOC_SENSOR`, etc.), calls inverter through `InverterBase` ABC |
| `sensor.py` | All entity IDs come from config dict. `HausverbrauchSensor` uses config-mapped `pv_power_sensor`, `battery_power_sensor`, `grid_power_sensor` |
| `coordinator.py` | Reads from own `sensor.eeg_energy_optimizer_hausverbrauch` via recorder -- completely inverter-independent |
| `forecast_provider.py` | Independent of inverter type -- reads Solcast or Forecast.Solar entities |
| `config_flow.py` | Single-click setup with `setup_complete=False` -- no inverter-specific logic |
| `select.py` | Optimizer mode entity (Ein/Test) -- inverter-independent |
| `inverter/base.py` | Abstract base class -- defines the interface, doesn't implement anything |
| WebSocket manual controls (`ws_manual_*`) | Call abstract `InverterBase` methods -- no Huawei-specific code |
| Frontend panel (`eeg-optimizer-panel.js`) | Communicates via WebSocket API -- never touches inverter directly |
