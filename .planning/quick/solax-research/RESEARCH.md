# Solax Inverter Integration Research for EEG Energy Optimizer

**Researched:** 2026-03-25
**Domain:** SolaX inverter control via Home Assistant integrations
**Confidence:** MEDIUM-HIGH
**Goal:** Determine feasibility of a `SolaxInverter` implementation for the existing `InverterBase` ABC

## Summary

There are two main Home Assistant integrations for SolaX inverters. The **official HA SolaX integration** (`solax`) is read-only -- it provides basic sensor data via the inverter's REST API but offers zero battery control. The **SolaX Modbus custom component** (`solax_modbus` by wills106) is the community standard for full inverter control via Modbus TCP/RS485, available through HACS, and provides extensive read/write entities including battery charge/discharge control.

A `SolaxInverter` implementation is **feasible** using the SolaX Modbus integration. The integration exposes select, number, and button entities that map well to our `InverterBase` ABC. The approach differs from Huawei (which uses dedicated services like `forcible_discharge_soc`) -- Solax control works through setting entity values and pressing a trigger button. Two control modes exist: Mode 1 (Gen4+, all models) and Mode 8 (Gen4+, newer firmware). Both can achieve the three operations our ABC requires.

**Primary recommendation:** Implement `SolaxInverter` using Mode 1 remote control entities from `solax_modbus`. Mode 1 has the broadest device support and is the pattern used by Predbat (the most established HA battery optimization tool).

## 1. Available Integrations

### 1.1 Official HA SolaX Integration (`solax`)

| Property | Value |
|----------|-------|
| Type | Core HA integration |
| Connection | REST API (local WiFi) |
| Control capability | **NONE -- read-only** |
| HACS required | No |
| URL | https://www.home-assistant.io/integrations/solax/ |

**Sensors provided:**
- `sensor.pv1_power`, `sensor.pv2_power` -- PV string power
- `sensor.power_now` -- current output power
- `sensor.exported_power` -- grid export
- Battery level and power (basic)
- Consumption sensors (kWh)

**Verdict:** Insufficient for our needs. Cannot control charge/discharge. Only useful as a secondary data source.

### 1.2 SolaX Modbus Integration (`solax_modbus`)

| Property | Value |
|----------|-------|
| Type | HACS custom component |
| Connection | Modbus TCP or RS485 |
| Control capability | **Full read/write** |
| Repository | https://github.com/wills106/homeassistant-solax-modbus |
| Documentation | https://homeassistant-solax-modbus.readthedocs.io/ |
| HACS required | Yes |
| Domain name | `solax_modbus` |

**Supported SolaX models:**
- Gen2 Hybrid (X1/X3)
- Gen3 Hybrid (X1/X3)
- Gen4 Hybrid (X1/X3) -- best support
- Gen5 Hybrid
- Gen6 Hybrid (added 2025-2026)
- A1 / J1 series
- Also supports: Growatt, Sofar, Solis, Solinteg, SRNE, Swatten (not relevant here)

**Verdict:** This is the integration to target. It provides full control via Modbus entities.

### 1.3 Other Integrations

No other significant Solax-specific integrations were found. The `solax_modbus` integration is the de facto standard, also used by Predbat (the leading HA battery optimization tool).

## 2. SolaX Modbus Entities (Key Sensors)

### Read-Only Sensors

| Entity ID pattern | Type | Description | Needed by us? |
|-------------------|------|-------------|---------------|
| `sensor.solax_battery_capacity` | sensor | Battery SOC (%) | Yes -- maps to battery SOC |
| `sensor.solax_battery_power_charge` | sensor | Battery charge/discharge power (W, negative = discharge) | Yes -- battery power |
| `sensor.solax_pv_power` (or pv1+pv2) | sensor | Total PV generation (W) | Yes -- PV power |
| `sensor.solax_measured_power` | sensor | Grid power at meter (W, positive = export, negative = import) | Yes -- grid power |
| `sensor.solax_house_load` | sensor | House consumption (W) | Optional |
| `sensor.solax_battery_state_of_health` | sensor | Battery health % | Optional |
| `sensor.solax_battery_temperature` | sensor | Battery temp | Optional |
| `sensor.solax_grid_import` / `grid_export` | sensor | Grid import/export (W) | Optional |
| `sensor.solax_today_s_import_energy` | sensor | Daily grid import (kWh) | Optional |
| `sensor.solax_today_s_export_energy` | sensor | Daily grid export (kWh) | Optional |
| `sensor.solax_battery_input_energy_today` | sensor | Energy stored to battery today (kWh) | Optional |

**Note on entity naming:** The `solax_` prefix varies by installation. It can be `solaxmodbus_`, `solax_inverter_`, or user-customized. The implementation must allow configurable entity prefixes or full entity ID mapping.

### Control Entities (Number / Select / Button)

| Entity ID pattern | Type | Description |
|-------------------|------|-------------|
| `select.solax_charger_use_mode` | select | Main operation mode (Self Use, Feedin Priority, Manual, Back Up) |
| `select.solax_manual_mode_select` | select | Manual sub-mode (Stop, Force Charge, Force Discharge) |
| `number.solax_battery_charge_max_current` | number | Max charge current limit |
| `number.solax_battery_discharge_max_current` | number | Max discharge current limit |
| `number.solax_battery_charge_upper_soc` | number | Upper SOC limit for charging |
| `number.solax_selfuse_discharge_min_soc` | number | Minimum SOC for self-use discharge |
| `number.solax_export_control_user_limit` | number | Max grid export power |
| `button.solax_remotecontrol_trigger` | button | Trigger remote control command |
| `select.solax_remotecontrol_power_control` | select | Remote control mode |
| `number.solax_remotecontrol_active_power` | number | Target power for remote control (W) |
| `number.solax_remotecontrol_duration` | number | Remote control timeslot duration (s) |
| `number.solax_remotecontrol_autorepeat_duration` | number | Auto-repeat interval (s) |

## 3. Control Approaches

### 3.1 Mode 1 Remote Control (RECOMMENDED)

**Supported on:** Gen4+ inverters (all firmware versions)
**How it works:** Set parameters via number/select entities, then press trigger button. Commands are temporary (duration-based) and do NOT write to EEPROM.

**Entities used:**
```
select.solax_remotecontrol_power_control   -- control mode
number.solax_remotecontrol_active_power    -- target power (W)
number.solax_remotecontrol_duration        -- command duration (seconds)
number.solax_remotecontrol_autorepeat_duration -- auto-repeat (seconds)
button.solax_remotecontrol_trigger         -- activate command
```

**Control modes available in `remotecontrol_power_control`:**
- `Disabled` -- return to normal operation
- `Enabled Power Control` -- direct power control
- `Enabled Grid Control` -- control grid interface (positive = charge from grid)
- `Enabled Battery Control` -- control battery (positive = charge, negative = discharge)
- `Enabled Self Use` -- self-use mode
- `Enabled Feedin Priority` -- feed-in priority
- `Enabled No Discharge` -- prevent battery discharge

**Mapping to our InverterBase ABC:**

| ABC Method | Mode 1 Implementation |
|------------|----------------------|
| `async_set_charge_limit(0)` (block charging) | Set `remotecontrol_power_control` = "Enabled No Discharge" + `active_power` = 0, trigger. OR: Set `remotecontrol_power_control` = "Enabled Battery Control" + `active_power` = 0, trigger. |
| `async_set_discharge(power_kw, target_soc)` | Set `remotecontrol_power_control` = "Enabled Battery Control" + `active_power` = -(power_w), trigger. For target_soc: set `selfuse_discharge_min_soc` = target_soc. |
| `async_stop_forcible()` | Set `remotecontrol_power_control` = "Disabled", trigger. |

### 3.2 Mode 8 Remote Control (Alternative)

**Supported on:** Gen4+ with newer firmware, Gen5, Gen6
**How it works:** Similar to Mode 1 but uses different trigger entity and has direct grid-interface power semantics.

**Entities used:**
```
select.solax_remotecontrol_power_control_mode  -- submode selection
number.solax_remotecontrol_push_mode_power_8_9 -- target power (positive = export, negative = import)
number.solax_remotecontrol_pv_power_limit      -- PV power cap
number.solax_remotecontrol_import_limit        -- grid import cap
number.solax_remotecontrol_duration            -- command duration
number.solax_remotecontrol_autorepeat_duration -- auto-repeat
button.solax_powercontrolmode8_trigger         -- activate mode 8
```

**Key difference:** Mode 8 power values reference the grid interface (positive = export to grid, negative = import from grid), while Mode 1 Battery Control references the battery interface.

### 3.3 Gen2/Gen3 Charger Use Mode (Legacy)

**Supported on:** Gen2, Gen3
**How it works:** Uses `select.solax_charger_use_mode` to switch between Self Use, Feedin Priority, Manual Mode, Back Up, etc. Then `select.solax_manual_mode_select` for Force Charge / Force Discharge.

**Key difference from Gen4+:**
- No remote control entities
- Mode switches write to EEPROM (limited write cycles, should not be toggled frequently)
- Less granular power control
- For force discharge: uses `button.solax_grid_export` + `number.solax_grid_export_limit`

**Mapping to our ABC (Gen2/Gen3):**

| ABC Method | Gen2/Gen3 Implementation |
|------------|--------------------------|
| `async_set_charge_limit(0)` | Set `charger_use_mode` = "Manual Mode", `manual_mode_select` = "Stop Charge and Discharge" |
| `async_set_discharge(power_kw, target_soc)` | Set `charger_use_mode` = "Manual Mode", `manual_mode_select` = "Force Discharge", set `grid_export_limit` = power_w, set `battery_minimum_capacity_grid_tied` = target_soc |
| `async_stop_forcible()` | Set `charger_use_mode` = "Self Use" |

**Warning:** Gen2/Gen3 EEPROM writes -- toggling modes every 60 seconds is NOT recommended. Our optimizer runs every 60s. This is a significant concern for Gen2/Gen3 support.

## 4. Comparison with Huawei Implementation

| Aspect | Huawei (`huawei_solar`) | SolaX (`solax_modbus`) |
|--------|------------------------|------------------------|
| Integration type | HACS custom component | HACS custom component |
| Control mechanism | Dedicated HA services (`forcible_discharge_soc`, `stop_forcible_charge`) | Entity-based (set number/select values + press trigger button) |
| Charge blocking | Set `number.batteries_maximale_ladeleistung` = 0 | Remote control: "Enabled No Discharge" or "Enabled Battery Control" with power=0 |
| Force discharge | Service `forcible_discharge_soc` with power + target_soc | Remote control: "Enabled Battery Control" with negative power |
| Stop forcible | Service `stop_forcible_charge` + restore max charge power | Remote control: "Disabled" + trigger |
| Target SOC for discharge | Native in service call | Separate entity: `selfuse_discharge_min_soc` or rely on battery running down |
| EEPROM concern | No (services are non-persistent) | Mode 1/8: No (not stored in EEPROM). Gen2/3: YES (EEPROM writes) |
| Device identification | Uses `device_id` in service calls | Uses entity IDs (prefixed, configurable) |

### Key Implementation Differences

1. **No dedicated services:** SolaX Modbus does not expose custom HA services. All control is through standard HA entity services (`number.set_value`, `select.select_option`, `button.press`).

2. **Multi-step commands:** Each control operation requires 2-4 entity updates + a trigger button press (vs. single service call for Huawei).

3. **Duration-based commands:** Remote control commands expire after `remotecontrol_duration` seconds. Our 60-second optimizer cycle must re-issue commands periodically. Set `autorepeat_duration` to handle this.

4. **Target SOC handling:** Huawei has native target SOC in the discharge service. SolaX requires setting `selfuse_discharge_min_soc` as a separate entity write, which may not immediately take effect during remote control mode.

## 5. Recommended Implementation Plan

### Entity Configuration

The SolaxInverter class needs configurable entity IDs since the prefix varies. Suggested config:

```python
SOLAX_DEFAULTS = {
    "remotecontrol_power_control": "select.solax_remotecontrol_power_control",
    "remotecontrol_active_power": "number.solax_remotecontrol_active_power",
    "remotecontrol_duration": "number.solax_remotecontrol_duration",
    "remotecontrol_autorepeat_duration": "number.solax_remotecontrol_autorepeat_duration",
    "remotecontrol_trigger": "button.solax_remotecontrol_trigger",
    "discharge_min_soc": "number.solax_selfuse_discharge_min_soc",
    "battery_soc": "sensor.solax_battery_capacity",
}
```

### Implementation Pattern (Mode 1)

```python
class SolaxInverter(InverterBase):
    """SolaX inverter control via solax_modbus Mode 1 remote control."""

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Block charging by setting remote control to no-discharge with 0 power."""
        if power_kw == 0:
            # Block charging: use "Enabled No Discharge" mode
            await self._set_select("remotecontrol_power_control", "Enabled No Discharge")
            await self._set_number("remotecontrol_active_power", 0)
        else:
            # Partial charge limit: not directly supported in Mode 1
            # Could use "Enabled Battery Control" with positive power value
            await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
            await self._set_number("remotecontrol_active_power", int(power_kw * 1000))
        await self._set_number("remotecontrol_autorepeat_duration", 120)  # > 60s cycle
        await self._press_trigger()
        return True

    async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
        """Force battery discharge at given power."""
        if target_soc is not None:
            await self._set_number("discharge_min_soc", target_soc)
        await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
        # Negative value = discharge in Battery Control mode
        await self._set_number("remotecontrol_active_power", -int(power_kw * 1000))
        await self._set_number("remotecontrol_autorepeat_duration", 120)
        await self._press_trigger()
        return True

    async def async_stop_forcible(self) -> bool:
        """Return to normal auto mode."""
        await self._set_select("remotecontrol_power_control", "Disabled")
        await self._set_number("remotecontrol_autorepeat_duration", 0)
        await self._press_trigger()
        return True
```

### Helper Methods

```python
async def _set_number(self, config_key: str, value: float) -> None:
    entity_id = self._config.get(config_key, SOLAX_DEFAULTS[config_key])
    await self._hass.services.async_call(
        "number", "set_value",
        {"entity_id": entity_id, "value": value},
        blocking=True,
    )

async def _set_select(self, config_key: str, option: str) -> None:
    entity_id = self._config.get(config_key, SOLAX_DEFAULTS[config_key])
    await self._hass.services.async_call(
        "select", "select_option",
        {"entity_id": entity_id, "option": option},
        blocking=True,
    )

async def _press_trigger(self) -> None:
    entity_id = self._config.get(
        "remotecontrol_trigger", SOLAX_DEFAULTS["remotecontrol_trigger"]
    )
    await self._hass.services.async_call(
        "button", "press",
        {"entity_id": entity_id},
        blocking=True,
    )
```

## 6. Common Pitfalls

### Pitfall 1: EEPROM Wear on Gen2/Gen3
**What goes wrong:** Switching `charger_use_mode` every 60 seconds wears out EEPROM.
**Why it happens:** Gen2/Gen3 store mode changes in EEPROM (limited write cycles ~100K).
**How to avoid:** Only support Gen4+ with Mode 1/Mode 8 remote control initially. These do NOT write to EEPROM. If Gen2/3 support is needed, implement debouncing to only write on state transitions.
**Warning signs:** Documentation explicitly warns about EEPROM writes.

### Pitfall 2: Entity Name Prefix Variation
**What goes wrong:** Hardcoded entity IDs like `select.solax_remotecontrol_power_control` fail.
**Why it happens:** Prefix depends on integration config: `solax_`, `solaxmodbus_`, `solax_inverter_`, or custom.
**How to avoid:** Make entity IDs configurable. Auto-detect entities by looking for `_remotecontrol_power_control` suffix across all select entities.
**Warning signs:** Entity not found errors in logs.

### Pitfall 3: Remote Control Duration Expiry
**What goes wrong:** Inverter returns to normal mode unexpectedly.
**Why it happens:** Remote control commands expire after `remotecontrol_duration` seconds.
**How to avoid:** Set `remotecontrol_autorepeat_duration` to a value larger than the optimizer cycle (> 60s). The integration auto-repeats the command each polling cycle.
**Warning signs:** Intermittent behavior where battery briefly charges before being re-blocked.

### Pitfall 4: Power Value Sign Convention
**What goes wrong:** Charging instead of discharging (or vice versa).
**Why it happens:** Mode 1 Battery Control: positive = charge, negative = discharge. Mode 8: positive = grid export, negative = grid import. Signs are opposite perspectives.
**How to avoid:** Document and verify sign convention clearly. Test with small values first.

### Pitfall 5: Target SOC Not Enforced During Remote Control
**What goes wrong:** Battery discharges below intended minimum SOC.
**Why it happens:** `selfuse_discharge_min_soc` may only apply during Self Use mode, not during active remote control battery discharge. The remote control actively pushes power regardless.
**How to avoid:** Monitor battery SOC in the optimizer cycle and issue `stop_forcible` when SOC drops to target. This is a software-side check our optimizer should do anyway.

### Pitfall 6: Lock State Must Be Unlocked
**What goes wrong:** Entity writes silently fail or throw errors.
**Why it happens:** The integration has a `select.solax_lock_state` entity that must be set to "Unlocked" before writing to number/select entities.
**How to avoid:** Check and document this prerequisite. Optionally auto-unlock in the inverter setup flow.

## 7. Feasibility Assessment

| Requirement | Feasible? | Approach | Confidence |
|-------------|-----------|----------|------------|
| Block charging (`set_charge_limit(0)`) | YES | Remote control "Enabled No Discharge" or "Enabled Battery Control" power=0 | HIGH |
| Set partial charge limit | PARTIAL | "Enabled Battery Control" with positive power value; less precise than Huawei's direct max charge power | MEDIUM |
| Force discharge at power | YES | "Enabled Battery Control" with negative power value | HIGH |
| Set target SOC for discharge | PARTIAL | Set `selfuse_discharge_min_soc`; may not be enforced during remote control. Software-side SOC monitoring recommended. | MEDIUM |
| Return to auto mode | YES | "Disabled" + trigger | HIGH |
| Battery SOC sensor | YES | `sensor.solax_battery_capacity` | HIGH |
| PV power sensor | YES | `sensor.solax_pv_power` (or pv1+pv2) | HIGH |
| Grid power sensor | YES | `sensor.solax_measured_power` | HIGH |
| Battery capacity info | PARTIAL | Available as `battery_capacity` but this is SOC%, not kWh. Capacity in kWh may need manual config. | MEDIUM |

### Overall Verdict: FEASIBLE

A SolaxInverter implementation is feasible with the following caveats:
1. **Requires `solax_modbus` HACS integration** (not the official `solax` integration)
2. **Best with Gen4+ inverters** using Mode 1 remote control
3. **Gen2/Gen3 support is risky** due to EEPROM wear -- should be deferred or heavily debounced
4. **Target SOC enforcement** needs software-side monitoring in our optimizer cycle
5. **Entity IDs must be configurable** due to prefix variation
6. **Multi-step command pattern** differs from Huawei's single service call approach

## 8. Scope Recommendation for Implementation

### Phase 1 (Recommended initial scope)
- Support Gen4+ via Mode 1 remote control only
- Configurable entity IDs with sensible defaults (`solax_` prefix)
- Auto-detect `solax_modbus` integration presence
- Software-side SOC monitoring for discharge target
- Add `solax_gen4` to `INVERTER_TYPES` dict in factory

### Phase 2 (Future)
- Mode 8 support for newer firmware
- Gen2/Gen3 support with debounced mode switching
- Auto-detection of entity prefixes
- Battery capacity (kWh) auto-detection from integration attributes

## Sources

### Primary (HIGH confidence)
- [SolaX Modbus official docs - Mode 1](https://homeassistant-solax-modbus.readthedocs.io/en/latest/solax-mode1-modbus-power-control/) -- entity names, control modes
- [SolaX Modbus official docs - Mode 8](https://homeassistant-solax-modbus.readthedocs.io/en/latest/solax-mode8-modbus-power-control/) -- Mode 8 specifics
- [SolaX Modbus official docs - Entity description](https://homeassistant-solax-modbus.readthedocs.io/en/latest/solax-entity-description/) -- sensor entities
- [SolaX Modbus official docs - Gen4 modes](https://homeassistant-solax-modbus.readthedocs.io/en/latest/solax-G4-operation-modes/) -- charger use modes
- [SolaX Modbus official docs - Gen2/3 modes](https://homeassistant-solax-modbus.readthedocs.io/en/latest/solax-G23-operation-modes/) -- legacy support
- [SolaX Modbus GitHub](https://github.com/wills106/homeassistant-solax-modbus) -- supported models, architecture
- [Official HA SolaX integration](https://www.home-assistant.io/integrations/solax/) -- confirmed read-only

### Secondary (MEDIUM confidence)
- [Predbat inverter setup docs](https://springfall2008.github.io/batpred/inverter-setup/) -- confirmed Solax Mode 1 as control pattern
- [GitHub Discussion #1071](https://github.com/wills106/homeassistant-solax-modbus/discussions/1071) -- automation examples with exact entity names

### Tertiary (LOW confidence)
- Community forum posts on entity naming variations -- prefix differences reported but not systematically documented

## Metadata

**Confidence breakdown:**
- Integration capabilities: HIGH -- verified via official docs
- Entity names/types: MEDIUM-HIGH -- confirmed in docs and community examples, but prefix varies
- Mode 1 control pattern: HIGH -- documented, used by Predbat
- Target SOC enforcement: MEDIUM -- unclear if min_soc is respected during remote control
- Gen2/Gen3 feasibility: MEDIUM -- works but EEPROM concern is real

**Research date:** 2026-03-25
**Valid until:** 2026-06-25 (stable integration, slow-moving)
