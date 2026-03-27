# SolaX Modbus Write/Control Commands - Deep Research

**Researched:** 2026-03-27
**Domain:** SolaX inverter battery control via homeassistant-solax-modbus
**Confidence:** HIGH (Mode 1), MEDIUM (Mode 8), HIGH (register addresses)

## Summary

The `solax_modbus` integration (by wills106) exposes battery control exclusively through standard HA entity services (`number.set_value`, `select.select_option`, `button.press`). It does NOT expose custom HA services for inverter control -- the only custom services are administrative (`stop_all`, `stop_hub`).

Control operates in two tiers: (1) **Data-Local entities** that store parameters in the integration's memory (not written to Modbus directly), and (2) a **trigger button** that collects all Data-Local values and writes them as a single `write_multiple_registers` Modbus command to the inverter. This two-phase approach means you MUST set all parameters BEFORE pressing the trigger button.

**Primary recommendation:** Use Mode 1 Remote Control with "Enabled Battery Control" for discharge (negative power) and "Enabled No Discharge" for charge blocking. This is the pattern used by Predbat (the leading HA battery optimization tool) and does NOT write to EEPROM.

---

## 1. Control Architecture Overview

### How solax_modbus Writes Work

```
Step 1: Set Data-Local entities (stored in integration memory only)
  - select.solax_remotecontrol_power_control  = "Enabled Battery Control"
  - number.solax_remotecontrol_active_power   = -3000  (Watts, negative = discharge)
  - number.solax_remotecontrol_duration       = 60     (seconds)
  - number.solax_remotecontrol_autorepeat_duration = 120 (seconds)

Step 2: Press trigger button (writes ALL parameters to Modbus in one operation)
  - button.solax_remotecontrol_trigger  -->  write_multiple_registers(0x7C, payload)

The trigger button's value_function (autorepeat_function_remotecontrol_recompute)
collects all Data-Local values and constructs a single Modbus payload written to
register 0x7C and subsequent registers via WRITE_MULTI_MODBUS.
```

### Write Methods in the Integration

| Write Method | Constant | What It Does |
|-------------|----------|-------------|
| `WRITE_SINGLE_MODBUS` | 1 | Single register write (function code 6) |
| `WRITE_MULTISINGLE_MODBUS` | 2 | Multiple-register command for one register |
| `WRITE_MULTI_MODBUS` | 4 | write_multiple_registers (function code 16) |
| `WRITE_DATA_LOCAL` | 3 | Stores in integration memory only -- NOT sent to inverter until trigger |

**Critical insight:** All `remotecontrol_*` number/select entities use `WRITE_DATA_LOCAL`. They are NOT written to the inverter when you call `number.set_value`. The actual Modbus write only happens when `button.solax_remotecontrol_trigger` is pressed.

---

## 2. Modbus Register Map (Battery Control)

### 2.1 Remote Control Mode 1 Registers (Written by Trigger at 0x7C)

The trigger button writes a contiguous block starting at holding register 0x7C:

| Offset | Abs. Address | Name | Data Type | Range | Unit | Description |
|--------|-------------|------|-----------|-------|------|-------------|
| +0 | 0x7C | Remote Control Command Block Start | - | - | - | Write target for trigger |
| +2 | 0x7E | Active Power | S32 | -30000..30000 | W | Battery: + charge, - discharge |
| +4 | 0x80 | Reactive Power | S32 | -4000..4000 | VAR | Usually 0 |
| +6 | 0x82 | Duration | U16 | 0..28800 | s | Command slot duration (step: 60s) |
| +7 | 0x83 | Target SOC (Mode 3) | U16 | 0..100 | % | Only used in Mode 3 |
| +8 | 0x84 | Target Energy (Mode 2) | S32 | 0..30000 | Wh | Only used in Mode 2 |
| +10 | 0x86 | Charge/Discharge Power (Mode 2/3) | S32 | -30000..30000 | W | Modes 2 and 3 |
| +12 | 0x88 | Timeout | U16 | 0..28800 | s | Command expiry (step: 60s) |
| +13 | 0x89 | Push Mode Power (Mode 4) | S32 | -30000..30000 | W | Mode 4 only |

**Note:** The trigger function (`autorepeat_function_remotecontrol_recompute`) constructs the complete payload from Data-Local values and writes it as one `write_multiple_registers` call. The individual "direct" entities (e.g., `remotecontrol_active_power_direct` at 0x7E) exist for advanced users who want to write registers individually.

### 2.2 Remote Control Mode 8 Registers (Written by Trigger at 0xA0)

| Offset | Abs. Address | Name | Data Type | Range | Unit | Description |
|--------|-------------|------|-----------|-------|------|-------------|
| +0 | 0xA0 | Mode 8/9 Command Block Start | - | - | - | Write target for mode 8 trigger |
| +2 | 0xA2 | PV Power Limit | U32 | 0..30000 | W | Cap PV output |
| +4 | 0xA4 | Push Mode Power 8/9 | S32 | -30000..30000 | W | + export, - import (grid perspective) |
| +6 | 0xA6 | Duration (Mode 8) / Target SOC (Mode 9) | U16 | 0..28800 / 0..100 | s / % | Dual purpose |
| +7 | 0xA7 | Timeout 8/9 | U16 | 0..28800 | s | Command expiry |

### 2.3 Battery Configuration Registers (Direct Modbus Writes)

These are regular holding registers written directly via `WRITE_SINGLE_MODBUS` or `WRITE_MULTISINGLE_MODBUS`:

| Address | Name | Data Type | Scale | Min | Max | Unit | Gen Support | Description |
|---------|------|-----------|-------|-----|-----|------|-------------|-------------|
| 0x20 | battery_minimum_capacity | U16 | 1 | 10 | 99 | % | Gen2, Gen3 | Min SOC (legacy) |
| 0x24 | battery_charge_max_current | Float | 0.1 (Gen3+) / 0.01 (Gen2) | 0 | 20 | A | All | Max charge current |
| 0x25 | battery_discharge_max_current | Float | 0.1 (Gen3+) / 0.01 (Gen2) | 0 | 20 | A | All | Max discharge current |
| 0x42 | export_control_user_limit | U16 | 1 (X1) / 10 (X3) | 0 | 6000 | W | Gen4+ | Grid export limit |
| 0x61 | selfuse_discharge_min_soc | U16 | 1 | 10 | 100 | % | Gen4+ | Min SOC for Self Use mode |
| 0x63 | selfuse_nightcharge_upper_soc | U16 | 1 | 10 | 100 | % | Gen4+ | Night charge target |
| 0x64 | feedin_nightcharge_upper_soc | U16 | 1 | 10 | 100 | % | Gen4+ | Feedin night charge target |
| 0x65 | feedin_discharge_min_soc | U16 | 1 | 10 | 100 | % | Gen4+ | Min SOC for Feedin mode |
| 0xC5 | selfuse_backup_soc | U16 | 1 | 10 | 100 | % | Gen4, Gen5 | Backup SOC (disabled by default) |
| 0xE0 | battery_charge_upper_soc | U16 | 1 | 10 | 100 | % | Gen4+ | Max charge SOC |

### 2.4 Work Mode Registers

| Address | Name | Data Type | Options | Gen Support | EEPROM? |
|---------|------|-----------|---------|-------------|---------|
| 0x1F | charger_use_mode | U16 | 0: Self Use, 1: Force Time Use, 2: Back Up, 3: Feedin Priority, 4: Manual Mode | Gen2-Gen4+ | **YES** |
| 0x00 | lock_state | U16 | Write password 2014 to unlock | All | - |

**WARNING:** Writing to `charger_use_mode` (0x1F) writes to EEPROM. Do NOT toggle this register frequently. Use Mode 1 Remote Control instead.

---

## 3. HA Entity Mapping

### 3.1 Control Entities for Mode 1

| HA Entity | Platform | Register / Method | R/W | Purpose |
|-----------|----------|-------------------|-----|---------|
| `select.solax_remotecontrol_power_control` | select | DATA_LOCAL | W | Control mode selection |
| `number.solax_remotecontrol_active_power` | number | DATA_LOCAL | W | Target power (W) |
| `number.solax_remotecontrol_duration` | number | DATA_LOCAL | W | Command slot duration (s) |
| `number.solax_remotecontrol_autorepeat_duration` | number | DATA_LOCAL | W | Auto-repeat interval (s) |
| `number.solax_remotecontrol_timeout` | number | DATA_LOCAL | W | Command timeout (s) |
| `number.solax_remotecontrol_import_limit` | number | DATA_LOCAL | W | Grid import limit (W) |
| `select.solax_remotecontrol_set_type` | select | DATA_LOCAL | W | Set(1) or Update(2) |
| `button.solax_remotecontrol_trigger` | button | 0x7C (MULTI) | W | **Executes the command** |

### 3.2 Control Entities for Mode 8

| HA Entity | Platform | Register / Method | R/W | Purpose |
|-----------|----------|-------------------|-----|---------|
| `select.solax_remotecontrol_power_control_mode` | select | DATA_LOCAL | W | Mode 8/9 submode |
| `number.solax_remotecontrol_pv_power_limit` | number | DATA_LOCAL | W | PV power cap (W) |
| `number.solax_remotecontrol_push_mode_power_8_9` | number | DATA_LOCAL | W | Grid power target (W) |
| `number.solax_remotecontrol_target_soc_8_9` | number | DATA_LOCAL | W | Target SOC for Mode 9 |
| `button.solax_powercontrolmode8_trigger` | button | 0xA0 (MULTI) | W | **Executes mode 8 command** |

### 3.3 Battery SOC/Current Entities (Direct Write)

| HA Entity | Platform | Register | R/W | Purpose |
|-----------|----------|----------|-----|---------|
| `number.solax_battery_charge_max_current` | number | 0x24 | RW | Max charge current (A) |
| `number.solax_battery_discharge_max_current` | number | 0x25 | RW | Max discharge current (A) |
| `number.solax_selfuse_discharge_min_soc` | number | 0x61 | RW | Min SOC in Self Use (%) |
| `number.solax_feedin_discharge_min_soc` | number | 0x65 | RW | Min SOC in Feedin (%) |
| `number.solax_battery_charge_upper_soc` | number | 0xE0 | RW | Max charge SOC (%) |
| `select.solax_charger_use_mode` | select | 0x1F | RW | Work mode (**EEPROM!**) |
| `select.solax_lock_state` | select | 0x00 | W | Unlock with password 2014 |

### 3.4 Entity Name Prefix Variation

The `solax_` prefix in entity names varies by installation:
- `solax_` (default)
- `solax_inverter_` (common alternate)
- `solaxmodbus_` (older installations)
- User-customized prefix

**Our implementation MUST use configurable entity IDs**, not hardcoded names.

---

## 4. remotecontrol_power_control Options (Mode 1)

| Value | Option String | Behavior |
|-------|--------------|----------|
| 0 | `Disabled` | Return to normal automatic operation |
| 1 | `Enabled Power Control` | Direct power output control |
| 11 | `Enabled Grid Control` | Control grid interface (+ charge from grid, - export) |
| 12 | `Enabled Battery Control` | Control battery (+ charge, - discharge) |
| 110 | `Enabled Self Use` | Force self-use mode via remote control |
| 120 | `Enabled Feedin Priority` | Force feedin priority via remote control |
| 130 | `Enabled No Discharge` | Prevent battery discharge (PV charges battery, no grid discharge) |

### Power Sign Convention (Mode 1 Battery Control)

```
Positive active_power  = CHARGE battery (grid/PV -> battery)
Negative active_power  = DISCHARGE battery (battery -> grid/house)

Example: active_power = -3000  --> discharge at 3000W
Example: active_power =  2000  --> charge at 2000W
Example: active_power =     0  --> neither charge nor discharge
```

### Power Sign Convention (Mode 8 Push Mode)

```
Positive push_mode_power = EXPORT to grid (battery discharges)
Negative push_mode_power = IMPORT from grid (battery charges)

Mode 8 perspective is GRID, Mode 1 Battery Control perspective is BATTERY.
```

---

## 5. Predbat Mode Mapping (Verified Reference)

Predbat (the leading HA battery optimization tool) uses this exact mapping for SolaX:

```yaml
mode_mapping:
  Disabled:         "Disabled"            # Return to auto
  Force Charge:     "Enabled Battery Control"   # + power = charge
  Force Discharge:  "Enabled Battery Control"   # - power = discharge
  Freeze Charge:    "Enabled No Discharge"      # Block discharge
  Freeze Discharge: "Enabled Feedin Priority"   # Block charge, allow discharge
```

**Our EEG Optimizer needs:**

| Our Operation | Predbat Equivalent | Mode 1 Setting |
|--------------|-------------------|----------------|
| Block charging (morning) | Freeze Discharge | `Enabled Feedin Priority` with active_power=0 **OR** `Enabled No Discharge` (see section 6) |
| Force discharge (evening) | Force Discharge | `Enabled Battery Control` with active_power=-(watts) |
| Return to auto | Disabled | `Disabled` |

---

## 6. Concrete Implementation for InverterBase Methods

### 6.1 `async_set_charge_limit(power_kw)` -- Block/Limit Charging

**Goal:** When called with `power_kw=0`, prevent the battery from charging so PV surplus goes to the grid (EEG morning feed-in).

**Approach A -- "Enabled Feedin Priority" (RECOMMENDED):**
This mode prioritizes grid feed-in over battery charging. The inverter will export PV to grid first and only charge battery with excess. With active_power=0, battery neither charges nor discharges.

```python
async def async_set_charge_limit(self, power_kw: float) -> bool:
    if power_kw == 0:
        # Block charging: feedin priority means PV goes to grid, not battery
        await self._set_select("remotecontrol_power_control", "Enabled Feedin Priority")
        await self._set_number("remotecontrol_active_power", 0)
    else:
        # Partial charge limit: use battery control with positive power
        power_w = int(power_kw * 1000)
        await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
        await self._set_number("remotecontrol_active_power", power_w)
    await self._set_number("remotecontrol_duration", 60)
    await self._set_number("remotecontrol_autorepeat_duration", 120)
    await self._press_trigger()
    return True
```

**Approach B -- "Enabled No Discharge" (Alternative):**
Prevents discharge but does NOT prevent charging. This is the OPPOSITE of what we want for morning charge blocking. "No Discharge" means "battery can charge but not discharge" -- WRONG for our use case.

**IMPORTANT CLARIFICATION on "Enabled No Discharge":**
- "Enabled No Discharge" = battery CAN charge, CANNOT discharge
- "Enabled Feedin Priority" = PV goes to grid first, battery gets leftovers
- For our morning charge blocking, we want PV to go to the grid, NOT to the battery
- Therefore "Enabled Feedin Priority" is the correct choice, NOT "Enabled No Discharge"

**Approach C -- Set charge current to 0 (Simplest, but writes to EEPROM-adjacent register):**
```python
# NOT RECOMMENDED for frequent toggling -- register 0x24 may have write limits
await self._set_number("battery_charge_max_current", 0)
```

### 6.2 `async_set_discharge(power_kw, target_soc)` -- Force Discharge

**Goal:** Discharge battery at given power for evening EEG feed-in.

```python
async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
    # Set min SOC floor if target_soc provided
    if target_soc is not None:
        min_soc = max(int(target_soc), 10)  # SolaX minimum is 10%
        await self._set_number("selfuse_discharge_min_soc", min_soc)

    # Set battery control mode with NEGATIVE power for discharge
    power_w = -abs(int(power_kw * 1000))  # Ensure negative
    await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
    await self._set_number("remotecontrol_active_power", power_w)
    await self._set_number("remotecontrol_duration", 60)
    await self._set_number("remotecontrol_autorepeat_duration", 120)
    await self._press_trigger()
    return True
```

**Target SOC caveat:** The `selfuse_discharge_min_soc` register (0x61) sets the minimum SOC for Self Use mode. During Remote Control "Enabled Battery Control", this limit may NOT be enforced by the inverter firmware. The optimizer MUST monitor SOC in its 30s cycle and call `async_stop_forcible()` when SOC reaches the target. This is a software-side safety check.

### 6.3 `async_stop_forcible()` -- Return to Auto

**Goal:** Cancel any remote control command and return to normal operation.

```python
async def async_stop_forcible(self) -> bool:
    await self._set_select("remotecontrol_power_control", "Disabled")
    await self._set_number("remotecontrol_active_power", 0)
    await self._set_number("remotecontrol_autorepeat_duration", 0)  # Stop repeating
    await self._press_trigger()
    return True
```

### 6.4 `is_available` -- Integration Check

```python
@property
def is_available(self) -> bool:
    entries = self._hass.config_entries.async_entries("solax_modbus")
    return any(entry.state.value == "loaded" for entry in entries)
```

### 6.5 Helper Methods

```python
SOLAX_DOMAIN = "solax_modbus"

# Entity key -> default entity ID mapping
SOLAX_ENTITY_DEFAULTS = {
    "remotecontrol_power_control": "select.solax_remotecontrol_power_control",
    "remotecontrol_active_power": "number.solax_remotecontrol_active_power",
    "remotecontrol_duration": "number.solax_remotecontrol_duration",
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

---

## 7. Duration and Autorepeat Strategy

### The Problem

Remote control commands have a limited lifetime. When `duration` expires, the inverter returns to its previous operating mode. Our optimizer cycle is 30 seconds.

### The Solution: Autorepeat

The `solax_modbus` integration has a built-in autorepeat mechanism:

| Parameter | Recommended Value | Why |
|-----------|-------------------|-----|
| `remotecontrol_duration` | 60 seconds | Single command slot length |
| `remotecontrol_autorepeat_duration` | 120 seconds | Total repeat window (> optimizer cycle) |
| `remotecontrol_timeout` | 0 | No timeout (let autorepeat handle it) |

**How autorepeat works:**
1. When trigger is pressed with `autorepeat_duration > 0`, the integration schedules a timer
2. The timer re-sends the same Modbus command every polling cycle until `autorepeat_duration` expires
3. Our optimizer re-triggers every 30s, so autorepeat_duration=120s gives 4x safety margin

**When stopping:** Set `autorepeat_duration=0` before pressing trigger with "Disabled" to ensure the autorepeat timer is cancelled.

---

## 8. Gen4 vs Gen5 vs Gen6 Differences

| Feature | Gen4 | Gen5 | Gen6 |
|---------|------|------|------|
| Mode 1 Remote Control | YES | YES | YES (confirmed in code) |
| Mode 8 Remote Control | YES (newer firmware) | YES | YES |
| Trigger button (0x7C) | YES | YES | YES |
| Mode 8 trigger (0xA0) | YES | YES | YES |
| selfuse_discharge_min_soc (0x61) | YES | YES | YES |
| feedin_discharge_min_soc (0x65) | YES | YES | YES |
| battery_charge_upper_soc (0xE0) | YES | YES | YES |
| battery_charge_max_current (0x24) | Scale 0.1 | Scale 0.1 | Scale 0.1 |
| selfuse_backup_soc (0xC5) | YES | YES | NO |
| charger_use_mode (0x1F) | YES (EEPROM) | YES (EEPROM) | YES (EEPROM) |
| MAX_CURRENTS | Model-dependent (30-60A) | Model-dependent | Model-dependent |
| MAX_EXPORT | Model-dependent (5-30kW) | Model-dependent | Model-dependent |

**Key finding:** Gen4, Gen5, and Gen6 all support Mode 1 with identical register layout. The differences are in maximum values (model-dependent, not generation-dependent) and Mode 8 availability.

**Gen2/Gen3 are fundamentally different:** No remote control entities. Control only via `charger_use_mode` (EEPROM writes). NOT recommended for our optimizer.

---

## 9. Caveats and Risks

### Caveat 1: Lock State Must Be Unlocked

The inverter has a `select.solax_lock_state` entity. If locked, all write operations silently fail or throw errors. The default unlock password is **2014** (written to register 0x00).

**Recommendation:** Check lock state in the setup wizard prerequisite step. Warn user if locked.

### Caveat 2: Target SOC Not Enforced During Remote Control

During "Enabled Battery Control" with negative power, the inverter may discharge below `selfuse_discharge_min_soc`. The min SOC register applies to the Self Use operating mode, not necessarily to remote control commands.

**Recommendation:** The optimizer MUST monitor SOC every 30s and call `async_stop_forcible()` when SOC reaches target. This is already our pattern.

### Caveat 3: Power Value Clamping

The inverter clamps power to its rated capacity. A 3kW inverter will ignore a 6kW command silently. No error is returned.

**Recommendation:** Read the inverter's rated power from sensor attributes if available, or let the user configure max power in the wizard.

### Caveat 4: SolaX Delivers Values in Watts

All SolaX power sensors and control registers use Watts, not kW. Our InverterBase ABC uses kW. The SolaX implementation MUST convert: `power_w = int(power_kw * 1000)`.

### Caveat 5: Sleep Mode

The inverter may enter sleep mode at night (no PV, no load). During sleep, Modbus communication may fail or return stale values. Entity states become `unavailable`.

**Recommendation:** Check entity availability before issuing commands. If unavailable, skip the cycle.

### Caveat 6: SolaX X1 Fit (Retrofit/AC-coupled) Limited Support

The X1 Fit Gen4 is an AC-coupled retrofit inverter. It may NOT expose all remote control entities (specifically, `remotecontrol_trigger` may be missing). This is a known limitation.

**Recommendation:** During setup, verify that `button.solax_remotecontrol_trigger` exists. If not, warn the user that their model may not be fully supported.

### Caveat 7: Entity Prefix Varies

Entity names are NOT standardized. The prefix depends on the integration configuration name. Users may have `solax_`, `solax_inverter_`, `solaxmodbus_`, or custom prefixes.

**Recommendation:** Use auto-detection in the setup wizard: search for entities matching `*_remotecontrol_power_control` pattern to discover the actual prefix.

---

## 10. HA Services Summary

The `solax_modbus` integration exposes only two custom services, both administrative:

| Service | Description | Useful for Us? |
|---------|-------------|---------------|
| `solax_modbus.stop_all` | Force-stop all SolaX hubs | No |
| `solax_modbus.stop_hub` | Force-stop a named hub | No |

**All inverter control uses standard HA services:**

| Service | Entity Platform | What We Use It For |
|---------|----------------|-------------------|
| `number.set_value` | number | Set power, duration, SOC values |
| `select.select_option` | select | Set control mode |
| `button.press` | button | Trigger the Modbus write |

---

## 11. Complete Entity List for SolaX Inverter Implementation

### Required Entities (must be auto-detected or configured)

| Config Key | Default Entity ID | Platform | Purpose | Required? |
|-----------|-------------------|----------|---------|-----------|
| `solax_remotecontrol_power_control` | `select.solax_remotecontrol_power_control` | select | Mode selection | YES |
| `solax_remotecontrol_active_power` | `number.solax_remotecontrol_active_power` | number | Power target (W) | YES |
| `solax_remotecontrol_duration` | `number.solax_remotecontrol_duration` | number | Slot duration (s) | YES |
| `solax_remotecontrol_autorepeat_duration` | `number.solax_remotecontrol_autorepeat_duration` | number | Repeat interval (s) | YES |
| `solax_remotecontrol_trigger` | `button.solax_remotecontrol_trigger` | button | Execute command | YES |
| `solax_selfuse_discharge_min_soc` | `number.solax_selfuse_discharge_min_soc` | number | Min SOC floor (%) | YES |

### Optional Entities

| Config Key | Default Entity ID | Platform | Purpose |
|-----------|-------------------|----------|---------|
| `solax_battery_charge_max_current` | `number.solax_battery_charge_max_current` | number | Charge current limit (A) |
| `solax_feedin_discharge_min_soc` | `number.solax_feedin_discharge_min_soc` | number | Min SOC for feedin mode |
| `solax_battery_charge_upper_soc` | `number.solax_battery_charge_upper_soc` | number | Max charge SOC |

### Read-Only Sensors (already defined in STORY_SOLAX_INVERTER.md)

| Config Key | Default Entity ID | Unit |
|-----------|-------------------|------|
| `battery_soc_sensor` | `sensor.solax_inverter_battery_capacity` | % |
| `battery_power_sensor` | `sensor.solax_energy_dashboard_solax_battery_power` | W |
| `pv_power_sensor` | `sensor.solax_energy_dashboard_solax_solar_power` | W |
| `grid_power_sensor` | `sensor.solax_energy_dashboard_solax_grid_power` | W |
| `pv_power_sensor_2` | `sensor.solax_inverter_meter_2_measured_power` | W (optional) |

---

## 12. Charge Blocking: Which Mode is Correct?

This is the most important design decision for our EEG morning feed-in feature. Analysis:

| Mode | What Happens to PV | Battery Charges? | Battery Discharges? | EEG Feed-in? |
|------|-------------------|-----------------|--------------------|--------------|
| `Enabled Feedin Priority` | Exported to grid first | Only from surplus | Yes (if needed) | **YES** |
| `Enabled No Discharge` | Goes to battery + house | **Yes** | No | No (PV charges battery) |
| `Enabled Battery Control` (power=0) | Goes to house, surplus to grid | No (power=0) | No (power=0) | **YES** (surplus) |
| `Disabled` | Normal auto operation | Yes (auto) | Yes (auto) | Depends on mode |

**Conclusion for `async_set_charge_limit(0)` (morning charge blocking):**

**"Enabled Battery Control" with active_power=0 is the safest choice.**

Reasoning:
- `Enabled Feedin Priority` changes the overall operating logic and may have side effects
- `Enabled Battery Control` with power=0 explicitly tells the battery to do nothing (neither charge nor discharge)
- PV surplus goes to the house first, then to the grid -- exactly what we want for EEG morning feed-in
- This matches the Predbat "Freeze Discharge" equivalent behavior
- It is the most predictable: battery sits idle, PV feeds grid

**Alternative: "Enabled Feedin Priority" is also correct** and may be slightly better for maximizing grid export (it actively prioritizes export over battery charging). Both should be tested on real hardware.

---

## Sources

### Primary (HIGH confidence)
- [homeassistant-solax-modbus GitHub repo](https://github.com/wills106/homeassistant-solax-modbus) -- plugin_solax.py register definitions, button.py/number.py/select.py entity implementations, services.yaml
- [Predbat SolaX Mode 1 script](https://springfall2008.github.io/batpred/inverter-setup/) -- verified control pattern with mode mapping
- [GitHub Discussion #1071 - Remote Control](https://github.com/wills106/homeassistant-solax-modbus/discussions/1071) -- automation examples with exact entity names

### Secondary (MEDIUM confidence)
- [GitHub Discussion #39 - Charger Use Mode / Lock State](https://github.com/wills106/homeassistant-solax-modbus/discussions/39) -- unlock mechanism, password 2014
- [GitHub Discussion #1124 - X1 Fit Gen4](https://github.com/wills106/homeassistant-solax-modbus/discussions/1124) -- AC-coupled limitations
- [Predbat solax_sx4.yaml template](https://raw.githubusercontent.com/springfall2008/batpred/refs/heads/main/templates/solax_sx4.yaml) -- entity regex patterns

### Tertiary (LOW confidence)
- ReadTheDocs documentation (403 blocked during research, content inferred from search result snippets)
- Community forum posts on entity naming variations

---

## Metadata

**Confidence breakdown:**
- Register addresses: HIGH -- extracted directly from plugin_solax.py source code
- Mode 1 control flow: HIGH -- verified via Predbat implementation + GitHub discussions
- Power sign convention: HIGH -- confirmed in source code (S32 range -30000..30000) and Predbat mapping
- Target SOC enforcement: MEDIUM -- unclear if honored during remote control; software monitoring recommended
- Gen4/5/6 parity: HIGH -- confirmed in source code allowed_types flags
- Entity naming: MEDIUM -- prefix varies, defaults confirmed but user may differ
- charger_use_mode options: MEDIUM -- register 0x1F confirmed, exact options inferred from discussions

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (stable integration, slow release cadence)
