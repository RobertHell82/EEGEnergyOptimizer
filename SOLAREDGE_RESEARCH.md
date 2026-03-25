# SolarEdge Inverter Integration Research for EEG Energy Optimizer

**Researched:** 2026-03-25
**Domain:** SolarEdge inverter control via Home Assistant integrations
**Confidence:** MEDIUM
**Goal:** Determine feasibility of a `SolarEdgeInverter` implementation for the existing `InverterBase` ABC

## 1. Summary

SolarEdge offers PV inverters with optional battery storage through their StorEdge system (using LG Chem RESU, BYD, or SolarEdge Energy Bank batteries). There are three main Home Assistant integrations: the **official cloud-based `solaredge` integration** (read-only monitoring via SolarEdge Monitoring API), the **`solaredge_modbus` integration** by binsentsu (local Modbus TCP, primarily read-only sensors), and the **`solaredge-modbus-multi` HACS integration** by WillCodeForCats (local Modbus TCP with StorEdge battery read/write support). Only `solaredge-modbus-multi` provides the battery control capabilities needed for the EEG Energy Optimizer. A `SolarEdgeInverter` implementation is **feasible** using `solaredge-modbus-multi`, but with notable limitations: SolarEdge's storage control model uses predefined command modes (Maximize Self Consumption, Maximize Export, Charge from PV, Charge from Grid, Discharge to Maximize Export) rather than direct power setpoints, making granular power control less precise than Huawei's service-based approach. Charge blocking and forced discharge are achievable; fine-grained power control is limited.

## 2. Available Integrations

### 2.1 Official HA SolarEdge Integration (`solaredge`)

| Property | Value |
|----------|-------|
| Type | Core HA integration |
| Connection | Cloud API (SolarEdge Monitoring API) |
| Control capability | **NONE -- read-only** |
| HACS required | No |
| URL | https://www.home-assistant.io/integrations/solaredge/ |

**What it provides:**
- Site energy overview (production, consumption, self-consumption)
- Power flow data (PV, grid, load, storage) via the Monitoring API
- Lifetime/annual/monthly/daily energy totals
- Inverter status

**Sensors provided:**
- `sensor.solaredge_current_power` -- current PV production (W)
- `sensor.solaredge_energy_today` -- daily PV production (Wh)
- `sensor.solaredge_energy_this_month` -- monthly PV production (Wh)
- `sensor.solaredge_energy_this_year` -- yearly PV production (Wh)
- `sensor.solaredge_lifetime_energy` -- lifetime production (Wh)
- Power flow sensors (when available): grid, load, PV, storage power

**Limitations:**
- Cloud-based (requires internet, has API rate limits: 300 requests/day)
- Update interval minimum ~15 minutes (API quota constraint)
- No write/control capability whatsoever
- No battery SOC or detailed battery data on all accounts

**Verdict:** Insufficient for our needs. Cannot control anything. Only useful as a supplementary data source for PV production totals. The 15-minute update interval makes it unsuitable even for reliable sensor data for our 30-second optimizer cycle.

### 2.2 SolarEdge Modbus Integration (`solaredge_modbus`)

| Property | Value |
|----------|-------|
| Type | Core HA integration (originally custom, merged into core) |
| Connection | Modbus TCP (local network) |
| Control capability | **Limited -- mostly read-only, some StorEdge write support** |
| HACS required | No |
| URL | https://www.home-assistant.io/integrations/solaredge_modbus/ |

**Prerequisites:**
- SolarEdge inverter with Modbus TCP enabled (configured via SetApp or LCD)
- Network connection to inverter (Ethernet or WiFi with Modbus TCP port 1502 or 502)

**Sensors provided:**
- `sensor.solaredge_i1_ac_current` -- AC current
- `sensor.solaredge_ac_power` -- AC output power (W)
- `sensor.solaredge_dc_power` -- DC input power (W)
- `sensor.solaredge_ac_frequency` -- grid frequency
- `sensor.solaredge_ac_voltab` -- AC voltage
- `sensor.solaredge_ac_energy_kwh` -- total energy produced (kWh)
- `sensor.solaredge_status` -- inverter status
- `sensor.solaredge_temperature` -- inverter temperature

**StorEdge battery sensors (if battery present):**
- `sensor.solaredge_b1_state_of_energy` -- battery SOC (%)
- `sensor.solaredge_b1_dc_power` -- battery charge/discharge power (W)
- `sensor.solaredge_b1_status` -- battery status
- `sensor.solaredge_b1_state_of_health` -- battery health (%)
- `sensor.solaredge_b1_rated_energy` -- battery rated capacity (Wh)

**Control entities (limited):**
- The core `solaredge_modbus` integration has limited write support for StorEdge registers
- Storage control mode and charge/discharge limits may not be exposed as entities in all versions
- Write support varies by HA version and integration version

**Verdict:** Provides good read-only sensor data via local Modbus TCP. Battery sensor support exists for StorEdge systems. However, write/control capabilities are limited and inconsistent across versions. Not the recommended path for full battery control.

### 2.3 SolarEdge Modbus Multi (`solaredge-modbus-multi`) -- RECOMMENDED

| Property | Value |
|----------|-------|
| Type | HACS custom component |
| Connection | Modbus TCP (local network) |
| Control capability | **Full read/write for StorEdge battery** |
| Repository | https://github.com/WillCodeForCats/ha-solaredge-modbus-multi |
| HACS required | Yes |
| Domain name | `solaredge_modbus_multi` |

**Supported SolarEdge models:**
- Single phase inverters: SE2200H, SE3000H, SE3500H, SE3680H, SE4000H, SE5000H, SE6000H
- Three phase inverters: SE3K, SE4K, SE5K, SE7K, SE8K, SE9K, SE10K, SE12.5K, SE15K, SE16K, SE17K, SE25K, SE27.6K, SE33.3K
- StorEdge battery systems (LG Chem RESU, BYD, SolarEdge Energy Bank)
- Multiple inverter support (hence "multi")
- Meter support (revenue-grade meters, WattNode meters)

**Key features:**
- Local Modbus TCP communication (no cloud dependency)
- Full StorEdge battery read/write control
- Storage command mode switching
- Battery charge/discharge power limits
- Backup reserve SOC setting
- Support for multiple inverters and batteries
- Power control settings (export limiting, site limit)
- Configurable update interval (polling-based)

**StorEdge control entities:**
- `select.solaredge_storage_command_mode` -- storage operation mode
- `number.solaredge_storage_charge_limit` -- max charge power (W)
- `number.solaredge_storage_discharge_limit` -- max discharge power (W)
- `number.solaredge_storage_backup_reserve` -- backup reserve SOC (%)
- `number.solaredge_site_limit` -- site export limit (W)

**Verdict:** This is the integration to target. It provides full StorEdge battery control via Modbus TCP with proper HA entity interfaces. Active development and community support through HACS.

### 2.4 Other Integrations

| Integration | Notes |
|-------------|-------|
| `solaredge_optimizers` (HACS) | Reads optimizer-level data (per-panel). No battery control. |
| SolarEdge SetApp | Mobile app for installer configuration. Not an HA integration. Used to enable Modbus TCP on the inverter. |
| SolarEdge Cloud API v2 | REST API for monitoring. Same data as official integration. No control. |

## 3. Sensor Entities (solaredge-modbus-multi)

### Read-Only Sensors

| Entity ID pattern | Type | Description | Needed by us? |
|-------------------|------|-------------|---------------|
| `sensor.solaredge_ac_power` | sensor | Current AC output power (W) | Yes -- PV power |
| `sensor.solaredge_b1_state_of_energy` | sensor | Battery SOC (%) | Yes -- battery SOC |
| `sensor.solaredge_b1_dc_power` | sensor | Battery power (W, positive=charge, negative=discharge) | Yes -- battery power |
| `sensor.solaredge_m1_ac_power` | sensor | Meter power (W, grid import/export) | Yes -- grid power |
| `sensor.solaredge_b1_rated_energy` | sensor | Battery rated capacity (Wh) | Yes -- battery capacity |
| `sensor.solaredge_b1_state_of_health` | sensor | Battery health (%) | Optional |
| `sensor.solaredge_b1_temperature` | sensor | Battery temperature (C) | Optional |
| `sensor.solaredge_b1_status` | sensor | Battery status (Off, Idle, Charging, Discharging) | Optional |
| `sensor.solaredge_ac_energy_kwh` | sensor | Total energy produced (kWh) | Optional |
| `sensor.solaredge_status` | sensor | Inverter status | Optional |
| `sensor.solaredge_dc_power` | sensor | DC power from PV strings (W) | Optional (alternative PV) |

**Note on entity naming:** The `solaredge_` prefix is the default but can be customized during integration setup. Multi-inverter setups use `solaredge_i1_`, `solaredge_i2_` prefixes. Battery entities use `b1_`, `b2_` for multiple batteries. Meter entities use `m1_`, `m2_`.

### Control Entities (Select / Number)

| Entity ID pattern | Type | Description |
|-------------------|------|-------------|
| `select.solaredge_storage_command_mode` | select | Storage operation mode (see Section 4) |
| `number.solaredge_storage_charge_limit` | number | Max charge power (W) |
| `number.solaredge_storage_discharge_limit` | number | Max discharge power (W) |
| `number.solaredge_storage_backup_reserve` | number | Backup reserve SOC (%) |
| `number.solaredge_site_limit` | number | Site export limit (W) |
| `select.solaredge_storage_default_mode` | select | Default storage mode (for when command mode returns to default) |

## 4. Control Capabilities

### Storage Command Modes

SolarEdge StorEdge systems use a **command mode** paradigm for battery control. The `select.solaredge_storage_command_mode` entity accepts these options:

| Mode | Description | Effect |
|------|-------------|--------|
| `Maximize Self Consumption` | Default/normal mode | Battery charges from PV surplus, discharges for self-consumption |
| `Maximize Export` | Maximize grid export | Battery discharges to grid at max rate |
| `Charge from PV` | Charge battery from PV only | Battery charges from PV, does NOT discharge |
| `Charge from PV and Grid` | Charge from both sources | Battery charges from PV and grid |
| `Discharge to Maximize Export` | Force discharge to grid | Battery discharges at max power to grid |
| `Remote Control Command` | Advanced control | Uses separate charge/discharge limit registers |

### Charge Blocking

**Can the battery charging be blocked/limited?** YES

- **Full block:** Set `storage_command_mode` to `Maximize Export` or `Discharge to Maximize Export` -- battery will not charge
- **Partial limit:** Set `storage_charge_limit` to desired power (W) while in a mode that allows charging
- **Zero charge:** Set `storage_charge_limit` to 0 W

### Forced Discharge

**Can forced discharge be triggered with a target power?** PARTIAL

- **Discharge to grid:** Set `storage_command_mode` to `Maximize Export` or `Discharge to Maximize Export`
- **Discharge power limit:** Set `storage_discharge_limit` to desired power (W)
- **Limitation:** The command mode approach does not allow setting an exact discharge power -- it sets a maximum. The inverter manages the actual discharge rate based on conditions.

### Target SOC

**Can a target SOC be set for discharge?** YES (via backup reserve)

- Set `storage_backup_reserve` to the desired minimum SOC (%)
- The battery will stop discharging when SOC reaches the backup reserve level
- This works across all modes -- it is a hard floor for discharge

### Return to Auto Mode

**Can the inverter be returned to auto mode?** YES

- Set `storage_command_mode` back to `Maximize Self Consumption`
- Reset `storage_charge_limit` and `storage_discharge_limit` to their maximum values
- The inverter returns to normal self-consumption operation

### HA Services Used

All control is through standard HA entity services:
- `select.select_option` -- for `storage_command_mode`
- `number.set_value` -- for `storage_charge_limit`, `storage_discharge_limit`, `storage_backup_reserve`

No custom services are exposed by `solaredge-modbus-multi`.

### StorEdge-Specific Considerations

1. **StorEdge is required:** Only SolarEdge systems with a StorEdge interface and connected battery support these controls. A standard SolarEdge PV-only inverter has no battery to control.
2. **SetApp configuration required:** Modbus TCP must be enabled on the inverter via the SolarEdge SetApp (installer app). Default port is 1502 (non-standard Modbus port).
3. **Modbus TCP connection:** Only one Modbus TCP client can connect at a time on most SolarEdge inverters. If the monitoring portal uses the connection (SolarEdge's own cloud polling), local Modbus may conflict.
4. **Register-based control:** The control works by writing to SunSpec Modbus registers. Changes take effect on the next inverter control cycle (typically 1-5 seconds).
5. **Persistent settings:** Storage command mode changes persist across inverter reboots -- they are stored in non-volatile memory. This differs from SolaX Mode 1 (duration-based/temporary).

## 5. Mapping to InverterBase ABC

| ABC Method | SolarEdge Implementation | Confidence |
|------------|-------------------------|------------|
| `async_set_charge_limit(power_kw)` | If `power_kw == 0`: Set `storage_command_mode` = "Maximize Export" (prevents any charging). If `power_kw > 0`: Set `storage_charge_limit` = `power_kw * 1000` (W) while keeping current mode. | HIGH for block (0), MEDIUM for partial limit |
| `async_set_discharge(power_kw, target_soc)` | Set `storage_command_mode` = "Discharge to Maximize Export". Set `storage_discharge_limit` = `power_kw * 1000` (W). If `target_soc` provided: set `storage_backup_reserve` = `target_soc` (%). | MEDIUM -- power is a max limit, not exact setpoint |
| `async_stop_forcible()` | Set `storage_command_mode` = "Maximize Self Consumption". Restore `storage_charge_limit` and `storage_discharge_limit` to hardware max. Restore `storage_backup_reserve` to original value. | HIGH |
| `is_available` | Check `self._hass.config_entries.async_entries("solaredge_modbus_multi")` for loaded entries. | HIGH |

### Implementation Sketch

```python
class SolarEdgeInverter(InverterBase):
    """SolarEdge StorEdge battery control via solaredge-modbus-multi."""

    DOMAIN = "solaredge_modbus_multi"

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Block or limit battery charging."""
        try:
            if power_kw == 0:
                # Full charge block: switch to export mode
                await self._set_select(
                    "storage_command_mode", "Maximize Export"
                )
            else:
                # Partial charge limit
                await self._set_number(
                    "storage_charge_limit", int(power_kw * 1000)
                )
            return True
        except Exception:
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force battery discharge to grid."""
        try:
            if target_soc is not None:
                await self._set_number(
                    "storage_backup_reserve", max(int(target_soc), 0)
                )
            await self._set_number(
                "storage_discharge_limit", int(power_kw * 1000)
            )
            await self._set_select(
                "storage_command_mode", "Discharge to Maximize Export"
            )
            return True
        except Exception:
            return False

    async def async_stop_forcible(self) -> bool:
        """Return to normal self-consumption mode."""
        try:
            await self._set_select(
                "storage_command_mode", "Maximize Self Consumption"
            )
            # Restore defaults
            await self._set_number(
                "storage_charge_limit", self._max_charge_power
            )
            await self._set_number(
                "storage_discharge_limit", self._max_discharge_power
            )
            await self._set_number(
                "storage_backup_reserve", self._original_backup_reserve
            )
            return True
        except Exception:
            return False

    @property
    def is_available(self) -> bool:
        entries = self._hass.config_entries.async_entries(self.DOMAIN)
        return any(e.state.value == "loaded" for e in entries)
```

### Key Design Notes

1. **Store original values:** On initialization, read and store `storage_charge_limit`, `storage_discharge_limit`, and `storage_backup_reserve` so `async_stop_forcible()` can restore them.
2. **No trigger button needed:** Unlike SolaX, SolarEdge Modbus writes take effect immediately -- no trigger/confirm step required.
3. **Persistent state concern:** Since storage command mode persists in non-volatile memory, it is critical that `async_stop_forcible()` reliably restores normal operation. Consider a watchdog mechanism.

## 6. Comparison with Huawei Implementation

| Aspect | Huawei (`huawei_solar`) | SolarEdge (`solaredge-modbus-multi`) |
|--------|------------------------|--------------------------------------|
| Integration type | HACS custom component | HACS custom component |
| Connection | Local (Modbus TCP) | Local (Modbus TCP, port 1502) |
| Control mechanism | Dedicated HA services (`forcible_discharge_soc`, `stop_forcible_charge`) | Standard HA entity services (`select.select_option`, `number.set_value`) |
| Charge blocking | Set `number.batteries_maximale_ladeleistung` = 0 W | Set `storage_command_mode` = "Maximize Export" or set `storage_charge_limit` = 0 |
| Force discharge | Service `forcible_discharge_soc` with power + target_soc | Set `storage_command_mode` = "Discharge to Maximize Export" + set `storage_discharge_limit` |
| Stop forcible | Service `stop_forcible_charge` + restore max charge power | Set `storage_command_mode` = "Maximize Self Consumption" + restore limits |
| Target SOC for discharge | Native in service call parameter | Via `storage_backup_reserve` entity (acts as discharge floor) |
| Power precision | Direct power setpoint in W | Maximum power limit (inverter manages actual rate) |
| Command persistence | Non-persistent (auto-reverts) | Persistent (survives reboots -- must explicitly restore) |
| Device identification | Uses `device_id` in service calls | Uses entity IDs (prefixed, configurable per install) |
| Multi-step commands | Single service call per operation | 1-3 entity writes per operation (no trigger needed) |
| Concurrent connections | Multiple clients supported | Typically single Modbus TCP client |

### Key Implementation Differences

1. **Command persistence:** Huawei forcible commands are temporary (auto-revert after a timeout). SolarEdge storage command mode changes persist in non-volatile memory. This means if our integration crashes without calling `async_stop_forcible()`, the inverter stays in the last commanded mode. A watchdog/recovery mechanism is more important for SolarEdge.

2. **Power control granularity:** Huawei allows setting exact charge power limits (0 to max). SolarEdge uses maximum limits combined with command modes -- the actual power output is managed by the inverter's internal logic. This means "discharge at 2 kW" on SolarEdge sets a 2 kW ceiling, but actual discharge may vary.

3. **No dedicated services:** Like SolaX, SolarEdge Modbus Multi does not expose custom HA services. All control uses standard entity services (`number.set_value`, `select.select_option`).

4. **Target SOC:** Huawei has target SOC as a native parameter in the discharge service. SolarEdge uses `storage_backup_reserve` which acts as a hard SOC floor -- functionally equivalent for our discharge use case.

5. **Single client limitation:** Most SolarEdge inverters allow only one Modbus TCP connection. If another tool (e.g., SolarEdge cloud monitoring or another integration) is using the connection, control may fail.

## 7. Common Pitfalls

### Pitfall 1: Persistent Command Mode After Crash
**What goes wrong:** Battery stays in "Maximize Export" or "Discharge to Maximize Export" mode indefinitely after HA restart or integration crash.
**Why it happens:** SolarEdge stores the storage command mode in non-volatile memory. Unlike Huawei (auto-reverts) or SolaX Mode 1 (duration-based), SolarEdge commands persist.
**How to avoid:** Implement startup recovery in the inverter class -- on initialization, check current mode and restore to "Maximize Self Consumption" if the optimizer is not actively commanding something else. Store last-commanded state in HA storage.
**Warning signs:** Battery unexpectedly exporting at full power after HA restart.

### Pitfall 2: Single Modbus TCP Connection Limit
**What goes wrong:** Integration fails to connect or reads stale data.
**Why it happens:** Most SolarEdge inverters support only one concurrent Modbus TCP client. If SolarEdge's cloud monitoring or another tool holds the connection, `solaredge-modbus-multi` cannot connect.
**How to avoid:** Disable SolarEdge's built-in cloud connection to Modbus (use WiFi for cloud monitoring instead of Modbus TCP). Ensure no other Modbus clients are active.
**Warning signs:** Frequent connection timeouts, `is_available` returning False intermittently.

### Pitfall 3: Non-Standard Modbus Port
**What goes wrong:** Cannot connect to inverter.
**Why it happens:** SolarEdge uses port 1502 by default (not standard Modbus port 502). Users may configure 502 or other ports via SetApp.
**How to avoid:** Document that users need to verify their Modbus TCP port in SetApp. Default to 1502 in our auto-detect flow.
**Warning signs:** Connection refused on port 502.

### Pitfall 4: Entity Prefix Variation with Multiple Inverters
**What goes wrong:** Hardcoded entity IDs fail.
**Why it happens:** Multi-inverter setups use `solaredge_i1_`, `solaredge_i2_` prefixes. Battery entities use `b1_`, `b2_`. Custom names may also be used.
**How to avoid:** Make all entity IDs configurable in the wizard. Provide auto-detect by searching for entities with matching suffixes (e.g., `_storage_command_mode`).
**Warning signs:** Entity not found errors in logs.

### Pitfall 5: SetApp Configuration Not Done
**What goes wrong:** No Modbus TCP access at all.
**Why it happens:** SolarEdge inverters ship with Modbus TCP disabled. It must be enabled by the installer via the SolarEdge SetApp mobile application.
**How to avoid:** Document clearly in the setup wizard that Modbus TCP must be enabled. Check prerequisites by verifying the `solaredge_modbus_multi` integration is loaded.
**Warning signs:** Integration cannot be set up; no entities appear.

### Pitfall 6: Charge Limit vs. Command Mode Interaction
**What goes wrong:** Setting `storage_charge_limit` to 0 does not block charging.
**Why it happens:** The charge limit only applies within certain command modes. In "Maximize Self Consumption" mode, setting charge limit to 0 may still allow some trickle charging depending on firmware.
**How to avoid:** For reliable charge blocking, use the `storage_command_mode` = "Maximize Export" approach rather than just setting charge limit to 0.
**Warning signs:** Battery still charging slowly despite charge limit being 0.

### Pitfall 7: Backup Reserve Floor During Discharge
**What goes wrong:** Battery does not discharge to the expected SOC level.
**Why it happens:** `storage_backup_reserve` acts as a hard floor. If set higher than the desired discharge target, the battery stops discharging early.
**How to avoid:** When setting up discharge, always set `storage_backup_reserve` BEFORE changing the command mode. Restore the original backup reserve value when stopping.
**Warning signs:** Battery stops discharging at a higher SOC than expected.

## 8. Feasibility Assessment

| Requirement | Feasible? | Approach | Confidence |
|-------------|-----------|----------|------------|
| Block charging (`set_charge_limit(0)`) | YES | Set `storage_command_mode` = "Maximize Export" | HIGH |
| Set partial charge limit | YES | Set `storage_charge_limit` to desired W value | MEDIUM |
| Force discharge at power | PARTIAL | Set `storage_command_mode` = "Discharge to Maximize Export" + `storage_discharge_limit`; power is max ceiling, not exact setpoint | MEDIUM |
| Set target SOC for discharge | YES | Set `storage_backup_reserve` to desired SOC% | HIGH |
| Return to auto mode | YES | Set `storage_command_mode` = "Maximize Self Consumption" + restore limits | HIGH |
| Battery SOC sensor | YES | `sensor.solaredge_b1_state_of_energy` | HIGH |
| PV power sensor | YES | `sensor.solaredge_ac_power` or `sensor.solaredge_dc_power` | HIGH |
| Grid power sensor | YES | `sensor.solaredge_m1_ac_power` (meter) | HIGH |
| Battery capacity info | YES | `sensor.solaredge_b1_rated_energy` (Wh) | HIGH |
| is_available check | YES | Check config entries for `solaredge_modbus_multi` domain | HIGH |

### Overall Verdict: FEASIBLE

A SolarEdgeInverter implementation is feasible with the following caveats:

1. **Requires `solaredge-modbus-multi` HACS integration** (not the official `solaredge` or core `solaredge_modbus` integration)
2. **Requires StorEdge system** -- a standard SolarEdge PV-only inverter has no battery to control
3. **Modbus TCP must be enabled** on the inverter via SolarEdge SetApp (installer tool)
4. **Power control is ceiling-based**, not exact setpoint -- acceptable for our morning charge blocking and evening discharge use cases
5. **Command persistence is a risk** -- startup recovery logic is critical to avoid leaving the battery in an unintended mode
6. **Single Modbus TCP connection** may conflict with other tools -- must be documented
7. **Entity IDs must be configurable** due to multi-inverter naming patterns

## 9. Scope Recommendation

### Phase 1 (Recommended initial scope)
- Support StorEdge battery systems via `solaredge-modbus-multi`
- Configurable entity IDs with sensible defaults (`solaredge_` prefix)
- Auto-detect `solaredge_modbus_multi` integration presence
- Implement charge blocking via command mode switching ("Maximize Export")
- Implement discharge via "Discharge to Maximize Export" + discharge limit + backup reserve
- Implement stop via "Maximize Self Consumption" + restore original limits
- Store original settings on init for reliable restoration
- Startup recovery: check and restore command mode on integration load
- Add `solaredge` to `INVERTER_TYPES` dict in factory

### Phase 2 (Future)
- Power optimization: use "Remote Control Command" mode for finer-grained power control
- Multi-battery support (b1, b2 prefixes)
- Multi-inverter support (i1, i2 prefixes)
- Auto-detection of entity prefixes by scanning for suffix patterns
- Battery capacity auto-read from `b1_rated_energy` sensor
- Watchdog mechanism for command mode persistence safety

## 10. Sources

### Primary (HIGH confidence)
- [SolarEdge Modbus Multi GitHub](https://github.com/WillCodeForCats/ha-solaredge-modbus-multi) -- repository, supported models, entity documentation
- [SolarEdge Modbus Multi Documentation](https://github.com/WillCodeForCats/ha-solaredge-modbus-multi/wiki) -- wiki with entity descriptions and StorEdge control
- [Official HA SolarEdge integration](https://www.home-assistant.io/integrations/solaredge/) -- confirmed cloud-only, read-only
- [SolarEdge SunSpec Modbus Register Map](https://www.solaredge.com/sites/default/files/sunspec-implementation-technical-note.pdf) -- official Modbus register documentation

### Secondary (MEDIUM confidence)
- [HA Community Forum - SolarEdge Modbus Multi](https://community.home-assistant.io/t/solaredge-modbus-multi-device-and-inverter-support/) -- community usage, configuration examples
- [SolarEdge StorEdge Application Note](https://www.solaredge.com/sites/default/files/storedge_application_note.pdf) -- StorEdge battery modes and capabilities
- [HA Community Forum - SolarEdge battery control](https://community.home-assistant.io/t/solaredge-storedge-battery-control/) -- user experiences with battery control

### Tertiary (LOW confidence)
- Community forum posts on Modbus TCP configuration -- port settings, connection issues
- GitHub issues on `solaredge-modbus-multi` -- edge cases with specific firmware versions

## Metadata

**Confidence breakdown:**
- Integration capabilities: HIGH -- verified via GitHub repository and wiki documentation
- Entity names/types: MEDIUM-HIGH -- confirmed in documentation, but multi-inverter naming varies
- StorEdge control pattern: MEDIUM -- command mode approach is well-documented, but exact behavior varies by firmware
- Power control precision: MEDIUM -- ceiling-based rather than exact setpoint, acceptable for our use cases
- Persistence/recovery: MEDIUM -- persistence behavior documented but recovery patterns are our responsibility
- Single client limitation: HIGH -- well-documented hardware constraint

**Research date:** 2026-03-25
**Valid until:** 2026-09-25 (active integration development, may add new features)
