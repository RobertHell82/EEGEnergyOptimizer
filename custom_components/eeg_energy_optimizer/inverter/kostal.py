"""Kostal Plenticore inverter control via direct Modbus TCP.

Uses pymodbus AsyncModbusTcpClient for direct register writes against the
proprietary Kostal battery-control registers (NOT SunSpec Model 124 — Kostal
does not implement the storage-control model; evcc confirms this by writing
the same proprietary registers). Sensors are read via the native HA
`kostal_plenticore` integration (REST).

KOSTAL Modbus spec Rev. 2.9, chapter 3.4 (identical for G1/G2/G3):
  Port 1502, Unit-ID 71, Float32 with word swap (factory default
  "little-endian" byte order = CDAB word order), FC 0x03 / 0x10.

  1034  Battery charge power (DC) setpoint  Float RW
        positive = DISCHARGE, negative = charge — actively into/from grid
  1038  Battery max. charge power limit     Float RW (0 = charging blocked,
        discharge for house consumption stays available)
  1040  Battery max. discharge power limit  Float RW (not written by us)
  210   Act. state of charge (%)            Float R
  1068  Battery work capacity (Wh)          Float R
  1080  Battery management mode             U16   R
        0 = internal, 1 = external digital I/O, 2 = external Modbus TCP

Central architectural difference to Fronius: Kostal expects the setpoint to
be REWRITTEN CYCLICALLY (watchdog, timeout configurable in the service menu,
recommendation 60 s). On timeout the inverter falls back to its internal
automatic battery management — a built-in failsafe if HA dies mid-discharge.
The driver therefore runs its own keepalive task that rewrites the active
setpoint every KEEPALIVE_INTERVAL seconds, decoupled from the optimizer's
"only write on state change" deduplication.

The control registers are volatile (RAM, spec ch. 3.3) — cyclic writing is
harmless (no NVRAM wear, unlike SolarEdge). There is no hardware target-SOC
register: the optimizer supervises the SOC every 30 s and stops the
discharge itself; the watchdog covers the HA-crash case.

VERIFY AT DEVICE (before first production release):
  1. Does a positive 1034 setpoint really feed into the grid beyond house
     consumption? (multiple community confirmations, one dissent)
  2. AT grid-connection ramp (~10 min, TOR Erzeuger): are writes to 1034
     rejected with an exception or silently ignored? (spec footnote 7)
  3. Watchdog/fallback behavior of the concrete firmware; whether identical
     rewrites are accepted (some firmwares need a ±1 W jitter — implemented
     unconditionally below, harmless either way)
  4. Float vs U32 encoding of 1038/1040 (evcc writes float; an older
     community register list documents U32 — for the 0-W blocking value
     both encodings are identical, so only Einspeisebegrenzung would care)
"""

from __future__ import annotations

import asyncio
import logging
import struct
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _slave_kw(client: Any, slave_id: int) -> dict:
    """Return the slave/device-id kwarg matching the active pymodbus API.

    pymodbus 3.9+ renamed the ``slave`` parameter on
    ``ModbusClientMixin.read_holding_registers`` (and friends) to
    ``device_id``. Older releases still expect ``slave``. Same probing
    approach as the Fronius driver so the code runs on both.
    """
    import inspect
    try:
        sig = inspect.signature(client.read_holding_registers)
        if "device_id" in sig.parameters:
            return {"device_id": slave_id}
    except (TypeError, ValueError):
        pass
    return {"slave": slave_id}


# Kostal Modbus endpoint (spec ch. 3.1)
KOSTAL_UNIT_ID = 71

# Control registers (spec ch. 3.4)
REG_BATTERY_SETPOINT = 1034   # Float W — positive = discharge
REG_MAX_CHARGE_POWER = 1038   # Float W — 0 = block charging
REG_MAX_DISCHARGE_POWER = 1040  # Float W — read-only for us

# Read registers used by driver/probe
REG_SOC = 210                 # Float %
REG_BATTERY_CAPACITY = 1068   # Float Wh
REG_BATTERY_MGMT_MODE = 1080  # U16: 0=internal, 1=ext. digital I/O, 2=ext. Modbus
REG_PRODUCTNAME = 768         # String, 32 registers
REG_POWER_CLASS = 800         # String, 32 registers

BATTERY_MGMT_EXTERNAL_MODBUS = 2

# Keepalive rewrite interval. evcc rewrites at watchdog-timeout/2 with the
# recommended 60 s timeout → 30 s. We use 25 s for extra margin: a single
# lost/slow write must not let the watchdog lapse mid-state.
KEEPALIVE_INTERVAL = 25.0

# Some firmwares reportedly ignore identical rewrites for watchdog purposes.
# Alternate the written value by ±1 W between keepalive cycles — electrically
# irrelevant, but guarantees every write is a register change.
_JITTER_W = 1.0


def float_to_registers(value: float) -> list[int]:
    """Encode Float32 in Kostal's factory-default word order (CDAB).

    Bytes within each 16-bit register travel big-endian on the Modbus wire;
    Kostal's "little-endian" setting swaps the WORD order: the low word is
    transmitted first. IEEE754 bytes A B C D therefore map to
    registers [C<<8|D, A<<8|B].
    """
    a, b, c, d = struct.pack(">f", value)
    return [(c << 8) | d, (a << 8) | b]


def registers_to_float(regs: list[int]) -> float:
    """Decode Float32 from Kostal word-swapped register order (CDAB)."""
    low, high = regs[0], regs[1]
    raw = bytes([(high >> 8) & 0xFF, high & 0xFF, (low >> 8) & 0xFF, low & 0xFF])
    return struct.unpack(">f", raw)[0]


def registers_to_string(regs: list[int]) -> str:
    """Decode a Kostal string register block (2 ASCII chars per register)."""
    chars: list[str] = []
    for reg in regs:
        chars.append(chr((reg >> 8) & 0xFF))
        chars.append(chr(reg & 0xFF))
    return "".join(chars).split("\x00", 1)[0].strip()


class KostalInverter(InverterBase):
    """Kostal Plenticore battery control via direct Modbus TCP.

    Active commands are held in ``self._active`` and rewritten by the
    keepalive task until async_stop_forcible() clears them.
    """

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        self._host: str = config.get("kostal_modbus_host", "")
        self._port: int = int(config.get("kostal_modbus_port", 1502))
        self._client: Any = None  # AsyncModbusTcpClient (lazy)
        self._slave_id: int = KOSTAL_UNIT_ID
        # Active command the keepalive rewrites:
        #   ("discharge", watts) | ("charge_limit", watts) | None
        self._active: tuple[str, float] | None = None
        self._keepalive_task: asyncio.Task | None = None
        self._jitter_toggle: bool = False
        # Snapshot of the max-charge-power register before we first wrote it,
        # restored on stop. RAM-only on purpose: the register is volatile —
        # after an HA restart the watchdog has already returned the inverter
        # to internal management, which ignores the stale value; the next
        # mode entry rewrites all relevant registers anyway.
        self._max_charge_pre_block: float | None = None
        # Serializes Modbus operations between the 30-second optimizer
        # cycle, manual WebSocket commands, and the keepalive task. Same
        # rationale as the Fronius driver: the direct Modbus TCP path has
        # no HA service-call serialization.
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection handling (mirrors the Fronius driver)
    # ------------------------------------------------------------------

    def _close_client(self) -> None:
        """Close and discard the Modbus TCP client (releases the socket)."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                _LOGGER.debug("Kostal: error closing Modbus client")
            self._client = None

    async def _ensure_connected(self) -> bool:
        """Ensure Modbus TCP connection is established (3 attempts)."""
        if self._client is not None and self._client.connected:
            return True

        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError:
            _LOGGER.error("Kostal: pymodbus not installed")
            return False

        for attempt in range(3):
            try:
                if self._client is None or not self._client.connected:
                    self._close_client()
                    self._client = AsyncModbusTcpClient(
                        self._host, port=self._port
                    )
                    await self._client.connect()
                if self._client.connected:
                    _LOGGER.debug(
                        "Kostal: Modbus TCP connected to %s:%s (attempt %d)",
                        self._host, self._port, attempt + 1,
                    )
                    return True
            except Exception:
                _LOGGER.debug(
                    "Kostal: connection attempt %d failed", attempt + 1
                )
                self._close_client()
            if attempt < 2:
                await asyncio.sleep(0.2)

        _LOGGER.error(
            "Kostal: failed to connect to %s:%s after 3 attempts",
            self._host, self._port,
        )
        return False

    # ------------------------------------------------------------------
    # Register primitives
    # ------------------------------------------------------------------

    async def _write_float(self, address: int, value: float) -> bool:
        """Write a Float32 (word-swapped) via FC16, count writes, 200ms pause."""
        try:
            result = await self._client.write_registers(
                address=address, values=float_to_registers(value),
                **_slave_kw(self._client, self._slave_id),
            )
            if result.isError():
                _LOGGER.error(
                    "Kostal: write error at register %d (value=%.1f)",
                    address, value,
                )
                return False
            self.register_writes += 1
            await asyncio.sleep(0.2)
            _LOGGER.debug("Kostal: wrote register %d = %.1f", address, value)
            return True
        except Exception:
            _LOGGER.exception(
                "Kostal: exception writing register %d (value=%.1f)",
                address, value,
            )
            self._close_client()
            return False

    async def _read_float(self, address: int) -> float | None:
        """Read a Float32 (word-swapped) holding register pair."""
        try:
            result = await self._client.read_holding_registers(
                address=address, count=2,
                **_slave_kw(self._client, self._slave_id),
            )
            if result.isError():
                _LOGGER.error("Kostal: read error at register %d", address)
                return None
            return registers_to_float(result.registers)
        except Exception:
            _LOGGER.exception("Kostal: exception reading register %d", address)
            self._close_client()
            return None

    # ------------------------------------------------------------------
    # Keepalive (watchdog feeding)
    # ------------------------------------------------------------------

    def _start_keepalive(self) -> None:
        if self._keepalive_task is None or self._keepalive_task.done():
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    def _cancel_keepalive(self) -> None:
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    async def _keepalive_loop(self) -> None:
        """Rewrite the active setpoint until cancelled.

        Failures are logged but tolerated: the AT grid-connection ramp (spec
        footnote 7) can reject writes to 1034 for ~10 minutes after grid
        reconnection — cyclic writing heals this by itself, and a watchdog
        lapse in the meantime only means temporary internal automatic mode.
        """
        try:
            while True:
                await asyncio.sleep(KEEPALIVE_INTERVAL)
                async with self._lock:
                    active = self._active
                    if active is None:
                        return
                    if not await self._ensure_connected():
                        _LOGGER.warning(
                            "Kostal: keepalive write skipped — not connected"
                        )
                        continue
                    kind, watts = active
                    self._jitter_toggle = not self._jitter_toggle
                    jittered = watts + (_JITTER_W if self._jitter_toggle else 0.0)
                    if kind == "discharge":
                        ok = await self._write_float(
                            REG_BATTERY_SETPOINT, jittered
                        )
                    else:  # charge_limit
                        ok = await self._write_float(
                            REG_MAX_CHARGE_POWER, jittered
                        )
                    if not ok:
                        _LOGGER.warning(
                            "Kostal: keepalive rewrite failed (%s, %.0f W) — "
                            "will retry next interval; watchdog may fall back "
                            "to internal mode until then",
                            kind, watts,
                        )
        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("Kostal: keepalive loop crashed")

    # ------------------------------------------------------------------
    # InverterBase implementation
    # ------------------------------------------------------------------

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery max charge power / block charging.

        power_kw=0: block charging (Morgen-Einspeisung) — register 1038 = 0.
        Discharge for house consumption stays available (Kostal semantics).
        power_kw>0: partial charge limit (Einspeisebegrenzung).
        The keepalive rewrites the value until stop.
        """
        async with self._lock:
            return await self._set_charge_limit_locked(power_kw)

    async def _set_charge_limit_locked(self, power_kw: float) -> bool:
        try:
            if not await self._ensure_connected():
                return False

            # Stuck-register guard: when switching from a discharge, reset
            # the setpoint explicitly instead of trusting the watchdog
            # timeout (community-reported bug: old setpoints survive a mode
            # change on some firmwares).
            if self._active is not None and self._active[0] == "discharge":
                if not await self._write_float(REG_BATTERY_SETPOINT, 0.0):
                    return False

            # Snapshot the pre-block max charge power once, so stop can
            # restore it. Read failure is non-critical: without a snapshot
            # the watchdog fallback restores internal management anyway.
            if self._max_charge_pre_block is None:
                current = await self._read_float(REG_MAX_CHARGE_POWER)
                if current is not None and current > 0:
                    self._max_charge_pre_block = current
                    _LOGGER.debug(
                        "Kostal: cached pre-block max charge power %.0f W",
                        current,
                    )

            watts = max(power_kw, 0.0) * 1000.0
            if not await self._write_float(REG_MAX_CHARGE_POWER, watts):
                return False

            self._active = ("charge_limit", watts)
            self._start_keepalive()
            _LOGGER.info(
                "Kostal: charge limit set (%.2f kW) — keepalive active",
                power_kw,
            )
            return True

        except Exception:
            _LOGGER.exception("Kostal: failed to set charge limit")
            self._close_client()
            return False

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force battery discharge at the given power (register 1034, positive).

        Kostal has no hardware target-SOC register: `target_soc` is accepted
        for interface compatibility but enforcement happens in the optimizer,
        which re-evaluates the SOC every 30 s and calls async_stop_forcible().
        The watchdog fallback to internal automatic covers the HA-crash case.
        """
        async with self._lock:
            return await self._set_discharge_locked(power_kw)

    async def _set_discharge_locked(self, power_kw: float) -> bool:
        try:
            if not await self._ensure_connected():
                return False

            # Stuck-register guard: leaving a charge block behind while
            # discharging is functionally harmless (charging is not wanted
            # during discharge), but restore it anyway so a later stop or
            # watchdog lapse never resumes with a stale 0-W charge limit.
            if (
                self._active is not None
                and self._active[0] == "charge_limit"
                and self._max_charge_pre_block is not None
            ):
                if await self._write_float(
                    REG_MAX_CHARGE_POWER, self._max_charge_pre_block
                ):
                    self._max_charge_pre_block = None

            watts = max(power_kw, 0.0) * 1000.0
            if not await self._write_float(REG_BATTERY_SETPOINT, watts):
                return False

            self._active = ("discharge", watts)
            self._start_keepalive()
            _LOGGER.info(
                "Kostal: discharge set (%.2f kW) — keepalive active", power_kw
            )
            return True

        except Exception:
            _LOGGER.exception("Kostal: failed to set discharge")
            self._close_client()
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Explicitly zeroes the discharge setpoint and restores the max charge
        power (stuck-register guard), then stops feeding the watchdog — the
        inverter falls back to internal automatic management on timeout.
        """
        async with self._lock:
            return await self._stop_forcible_locked()

    async def _stop_forcible_locked(self) -> bool:
        # Clear the active command FIRST so a failed write below cannot
        # race with a concurrent keepalive rewrite of the old setpoint.
        self._active = None
        self._cancel_keepalive()
        try:
            if not await self._ensure_connected():
                return False

            if not await self._write_float(REG_BATTERY_SETPOINT, 0.0):
                return False

            if self._max_charge_pre_block is not None:
                if await self._write_float(
                    REG_MAX_CHARGE_POWER, self._max_charge_pre_block
                ):
                    _LOGGER.info(
                        "Kostal: restored max charge power to %.0f W",
                        self._max_charge_pre_block,
                    )
                    self._max_charge_pre_block = None
                else:
                    # False → optimizer retries stop next cycle. The register
                    # is volatile, so even a persistent failure resolves once
                    # the watchdog lapses back to internal management.
                    _LOGGER.warning(
                        "Kostal: failed to restore max charge power — retrying"
                    )
                    return False

            _LOGGER.info(
                "Kostal: stopped forcible mode — watchdog will hand back "
                "to internal automatic management"
            )
            return True

        except Exception:
            _LOGGER.exception("Kostal: failed to stop forcible mode")
            self._close_client()
            return False

    @property
    def is_available(self) -> bool:
        """Whether the inverter is reachable.

        Connection is opened lazily (same rationale as Fronius): as long as
        a host is configured, report available — the real TCP probe happens
        inside _ensure_connected when an operation runs.
        """
        return bool(self._host)

    async def async_disconnect(self) -> None:
        """Stop keepalive and disconnect (called on entry unload)."""
        self._cancel_keepalive()
        self._active = None
        self._close_client()
