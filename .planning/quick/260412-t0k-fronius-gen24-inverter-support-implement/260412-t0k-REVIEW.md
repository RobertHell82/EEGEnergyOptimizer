---
phase: 260412-t0k
reviewed: 2026-04-13T14:30:00Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - custom_components/eeg_energy_optimizer/inverter/fronius.py
  - custom_components/eeg_energy_optimizer/inverter/__init__.py
  - custom_components/eeg_energy_optimizer/const.py
  - custom_components/eeg_energy_optimizer/manifest.json
  - custom_components/eeg_energy_optimizer/__init__.py
  - custom_components/eeg_energy_optimizer/websocket_api.py
  - custom_components/eeg_energy_optimizer/config_flow.py
  - custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
findings:
  critical: 2
  high: 2
  medium: 4
  low: 2
  nit: 2
  total: 12
status: issues_found
---

# Phase 260412-t0k: Fronius Gen24 Code Review

**Reviewed:** 2026-04-13
**Depth:** deep (cross-file analysis, call-chain tracing, concurrency review)
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The Fronius Gen24 inverter implementation is well-structured, follows the existing InverterBase pattern, and the SunSpec Model 124 discovery algorithm is correctly implemented. The pymodbus 3.6+ API is used correctly. However, two critical issues were found: (1) the battery sign convention is likely wrong, which would corrupt energy calculations for all Fronius users, and (2) after a Modbus connection loss, the driver never reconnects through its normal operation path, causing permanent failure until HA restart. Additionally, the Modbus TCP connection is never cleaned up on integration unload (resource leak), and `MinRsvPct` is not restored in `async_stop_forcible()`.

---

## Critical Issues

### CR-01: Battery sign convention likely wrong -- will invert Hausverbrauch calculation

**File:** `custom_components/eeg_energy_optimizer/const.py:35`
**Issue:** Fronius `power_battery` sensor reports positive values for **discharging** and negative for **charging** (confirmed in Fronius Solar API documentation and the concept doc FRONIUS-GEN24-KONZEPT.md section 2.1 table: `power_battery | W | + Entladung / - Ladung`). However, the sign convention is set to `battery_sign: 1`, which is the Huawei convention (positive = charging). This is wrong -- Fronius uses the same convention as SolaX (positive = discharging), so it should be `battery_sign: -1`.

With `battery_sign: 1`, when the battery is discharging (raw positive value), the system treats it as charging. The Hausverbrauch formula `PV - battery - grid` would subtract a positive number (interpreted as charging) instead of adding it, producing wildly incorrect house consumption values. This cascades into incorrect consumption profiles, incorrect forecasts, and incorrect optimizer decisions (Morgen-Einspeisung and Abend-Entladung thresholds).

Note: The concept doc section 2.2 text claims "das entspricht der gleichen Konvention wie beim Huawei SUN2000" which is incorrect -- the table in section 2.1 directly contradicts this claim. The table is authoritative (it matches the Fronius API docs).

**Fix:**
```python
# const.py line 35
"fronius_gen24": {"battery_sign": -1, "grid_sign": 1},
```

### CR-02: Driver never reconnects after Modbus TCP connection loss

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:178-184`
**Issue:** After any Modbus error, the exception handlers set `self._client = None` (e.g., lines 173, 214, 245) but do NOT clear `self._model124_base`. On the next optimizer cycle, `_ensure_model124()` (line 180) sees `_model124_base is not None` and returns `True` immediately without calling `_ensure_connected()`. Subsequent `_write_register` / `_read_wchamax` calls then fail with an AttributeError (`NoneType has no attribute write_register`) because `self._client` is still `None`.

The error is caught by the except block in `_write_register` (line 241-245), which again sets `self._client = None` but still does not clear `_model124_base`. This creates an infinite cycle: every 30-second optimizer cycle logs an exception and fails, but reconnection is never attempted.

The only escape path is `async_stop_forcible()` which calls `_ensure_connected()` directly (line 354), or an HA restart.

**Fix:**
```python
async def _ensure_model124(self) -> bool:
    """Ensure Model 124 base address is known and connection is alive."""
    if not await self._ensure_connected():
        return False
    if self._model124_base is not None:
        return True
    return await self._discover_model124()
```

This ensures reconnection is always attempted before checking the cached base address. The reconnect check (`_ensure_connected`) is cheap -- it returns immediately if `self._client.connected` is True (line 68-69).

---

## High Issues

### HI-01: Modbus TCP connection never closed on integration unload -- resource leak

**File:** `custom_components/eeg_energy_optimizer/__init__.py:665-685`
**Issue:** `async_unload_entry()` does not call `inverter.async_disconnect()`. The `FroniusInverter.async_disconnect()` method exists (line 385-392 of fronius.py) and properly closes the Modbus TCP socket, but it is never invoked. When the integration is unloaded (e.g., config change, HA restart, user removes integration), the TCP connection to the Fronius inverter remains open as an orphaned socket until the Python garbage collector reclaims it.

For the other inverter types (Huawei, SolaX, SolarEdge), this is not an issue because they use HA service calls, not persistent connections. This is unique to the Fronius driver.

**Fix:**
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EEG Energy Optimizer config entry."""
    from homeassistant.components.frontend import async_remove_panel

    async_remove_panel(hass, PANEL_URL_PATH)

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    platforms_loaded = data.get("platforms_loaded", False)

    # Close Fronius Modbus TCP connection if applicable
    inverter = data.get("inverter")
    if inverter and hasattr(inverter, "async_disconnect"):
        await inverter.async_disconnect()

    if platforms_loaded:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    else:
        unload_ok = True

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
```

### HI-02: async_stop_forcible does not restore MinRsvPct

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:348-378`
**Issue:** `async_set_discharge()` optionally writes `MinRsvPct` (line 332-334), e.g., setting it to 15% (1500). However, `async_stop_forcible()` restores `StorCtl_Mod`, `InWRte`, and `OutWRte` but does NOT restore `MinRsvPct` to its default. Since the concept doc (section 9.2) confirms Fronius Modbus settings have no auto-revert, the elevated MinRsvPct persists. This means the inverter's automatic mode will keep the elevated minimum reserve, potentially preventing the battery from discharging below 15% even during normal operation -- reducing usable battery capacity.

The concept doc section 3.2 specifies that the stop sequence should set `MinRsvPct` auf Standardwert (z.B. 500 = 5%).

**Fix:**
```python
async def async_stop_forcible(self) -> bool:
    """Stop forced charge/discharge, return to automatic mode.

    Restores: StorCtl_Mod=0, InWRte=10000, OutWRte=10000, MinRsvPct=default.
    """
    try:
        if not await self._ensure_connected():
            return False

        if not await self._ensure_model124():
            return False

        if not await self._write_register(_OFFSET_STORCTL_MOD, 0):
            return False
        if not await self._write_register(_OFFSET_INWRTE, _RATE_100_PERCENT):
            return False
        if not await self._write_register(_OFFSET_OUTWRTE, _RATE_100_PERCENT):
            return False
        # Restore MinRsvPct to default (5% = 500 with SF -2)
        # Non-critical: log warning but don't fail the whole operation
        if not await self._write_register(_OFFSET_MINRSVPCT, 500):
            _LOGGER.warning("Fronius: failed to restore MinRsvPct (non-critical)")

        _LOGGER.info("Fronius: stopped forcible mode -- automatic operation restored")
        return True

    except Exception:
        _LOGGER.exception("Fronius: failed to stop forcible mode")
        self._client = None
        return False
```

Alternatively, snapshot the original MinRsvPct value on startup (like SolarEdge does with `_original_discharge_limit`) and restore that value.

---

## Medium Issues

### ME-01: No concurrency guard on Modbus operations

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py`
**Issue:** The Fronius driver manages its own TCP connection and performs multi-register write sequences (e.g., `async_set_discharge` writes 3-4 registers). There is no `asyncio.Lock` to prevent concurrent access. If the 30-second optimizer cycle and a manual WebSocket command (`manual_discharge`, `manual_stop`, `manual_block_charge`) execute simultaneously, their register writes can interleave, leaving the inverter in an inconsistent state (e.g., `StorCtl_Mod=3` from discharge + `InWRte=10000` from stop).

The other drivers (Huawei, SolaX, SolarEdge) also lack locks, but they use HA service calls with `blocking=True` which provides implicit serialization. The Fronius driver's direct Modbus TCP connection does not have this guarantee.

**Fix:**
Add an `asyncio.Lock` to serialize all Modbus operations:
```python
def __init__(self, hass: Any, config: dict) -> None:
    super().__init__(hass, config)
    self._host: str = config.get("fronius_modbus_host", "")
    self._port: int = int(config.get("fronius_modbus_port", 502))
    self._client: Any = None
    self._lock = asyncio.Lock()
    # ... rest of init

async def async_set_charge_limit(self, power_kw: float) -> bool:
    async with self._lock:
        # ... existing implementation

async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
    async with self._lock:
        # ... existing implementation

async def async_stop_forcible(self) -> bool:
    async with self._lock:
        # ... existing implementation
```

### ME-02: Stale Modbus client not closed before creating new one

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:77-96`
**Issue:** In `_ensure_connected`, when creating a new client (line 80), the old `self._client` (if it exists but is not connected) is abandoned without calling `close()`. The orphaned socket may linger in TIME_WAIT state, consuming OS resources. Similarly, all exception handlers throughout the code set `self._client = None` without closing the old client first (lines 94, 173, 214, 245, 290, 345, 377).

**Fix:**
```python
def _close_client(self) -> None:
    """Close and discard the Modbus client."""
    if self._client is not None:
        try:
            self._client.close()
        except Exception:
            pass
        self._client = None
```
Then use `self._close_client()` instead of `self._client = None` throughout the file.

### ME-03: Partial register write failure leaves inverter in inconsistent state

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:268-281` (and similarly 319-335)
**Issue:** In `async_set_charge_limit`, if `_write_register(StorCtl_Mod, 1)` succeeds but `_write_register(InWRte, 0)` fails, the inverter has charge limit mode active with the previous InWRte value (possibly 10000 = 100%), meaning the charge block is not actually working despite no error being logged for the StorCtl_Mod write. The method returns `False` to indicate failure, but the caller (optimizer) will retry on the next cycle -- meanwhile the inverter is in an unexpected state.

Same issue in `async_set_discharge`: if StorCtl_Mod=3 succeeds but InWRte=0 or OutWRte fails, partial state remains.

**Fix:**
Add a best-effort rollback on partial failure:
```python
# In async_set_charge_limit, after StorCtl_Mod=1 succeeds but InWRte fails:
if not await self._write_register(_OFFSET_INWRTE, 0):
    # Best effort: revert StorCtl_Mod
    await self._write_register(_OFFSET_STORCTL_MOD, 0)
    return False
```
Alternatively, write InWRte/OutWRte **before** StorCtl_Mod so the rate values are set before the mode activates them.

### ME-04: No validation of fronius_modbus_host/port on backend

**File:** `custom_components/eeg_energy_optimizer/websocket_api.py:300-316`
**Issue:** The `ws_save_config` handler accepts arbitrary dict values via WebSocket and merges them directly into the config entry (line 307). The `fronius_modbus_host` value undergoes no server-side validation -- it could be an empty string, a non-IP string, or contain unexpected characters. While this is not directly exploitable (pymodbus handles it gracefully by failing to connect), it represents missing defense-in-depth. The frontend validates non-empty host but does not validate IP format.

**Fix:**
Add basic validation in `ws_save_config`:
```python
# After merging new_data
if new_data.get("inverter_type") == INVERTER_TYPE_FRONIUS:
    host = new_data.get("fronius_modbus_host", "")
    port = new_data.get("fronius_modbus_port", 502)
    if not host or not isinstance(host, str) or len(host) > 255:
        connection.send_error(msg["id"], "invalid_config", "Invalid Modbus host")
        return
    try:
        port = int(port)
        if not (1 <= port <= 65535):
            raise ValueError
        new_data["fronius_modbus_port"] = port
    except (ValueError, TypeError):
        connection.send_error(msg["id"], "invalid_config", "Invalid Modbus port")
        return
```

---

## Low Issues

### LO-01: Fronius sensor auto-detect suffix matching may match non-Fronius entities

**File:** `custom_components/eeg_energy_optimizer/websocket_api.py:478-490`
**Issue:** The suffix `state_of_charge` is generic and could match sensors from other integrations. The filter check (line 485-486) includes `"byd" in eid.lower()` which could match a standalone BYD BMS integration that is not associated with Fronius. The detection is only used for pre-populating wizard suggestions (user can override), so impact is low.

**Fix:**
Consider tightening the filter to prefer entities associated with the Fronius integration via device registry, similar to how `_find_huawei_battery_device` uses the device registry for Huawei.

### LO-02: WChaMax value not validated for sanity bounds

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:206`
**Issue:** The WChaMax register value is read and cached without sanity checking. The code already handles `None` and `0` (line 264). However, a corrupt Modbus response could return an unreasonably large value (e.g., 65535 W = 65.5 kW) which would be accepted, cached for the entire day, and used in percentage calculations. This would cause the calculated charge/discharge percentages to be very small, making the battery appear to do nothing.

**Fix:**
```python
self._wchamax = result.registers[0]
if self._wchamax > 25000:  # No residential battery inverter exceeds 25 kW
    _LOGGER.warning("Fronius: WChaMax=%d W seems unrealistic, ignoring", self._wchamax)
    self._wchamax = None
    return None
```

---

## Nit

### NI-01: Config migration v10->v11 is a no-op

**File:** `custom_components/eeg_energy_optimizer/__init__.py:367-371`
**Issue:** The migration block for version 11 copies the data dict and writes it back without any actual changes. The comment explains this is intentional (Fronius fields are only set when the user selects Fronius). This is harmless but adds dead code to the migration chain. Every future HA startup for every user will execute this empty migration block.

**Fix:** No code change needed, but consider adding a brief inline comment: `# Bump version only -- Fronius config fields are set via wizard when needed`.

### NI-02: `async_disconnect` uses sync `close()` instead of async pattern

**File:** `custom_components/eeg_energy_optimizer/inverter/fronius.py:389`
**Issue:** `self._client.close()` is the synchronous close method. In pymodbus 3.6+, `AsyncModbusTcpClient.close()` is synchronous (it just closes the transport), so this works correctly. However, for consistency and future-proofing, the pymodbus documentation recommends using the client as a context manager or calling `close()` -- the current usage is correct but may want to check if pymodbus introduces an `async_close()` in future versions.

**Fix:** No change needed currently. This is informational.

---

_Reviewed: 2026-04-13_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
