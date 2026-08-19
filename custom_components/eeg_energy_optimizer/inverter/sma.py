"""SMA Smart Energy / Sunny Boy Storage inverter control via direct Modbus TCP.

Uses pymodbus AsyncModbusTcpClient against SMA's external battery management
("6-Parameter-Methode", CmpBMS registers) — the same productive control path
evcc's sma-hybrid/sma-sbs templates use. Sensors are read via the native HA
`sma` (WebConnect) integration; because it only exposes directional pairs
(charge/discharge, supplied/absorbed), the setup creates synthetic combined
sensors — identical to the Fronius pair infrastructure.

SMA Modbus profile (SMA_Modbus-TB, evcc templates, PV-Forum 251643):
  Port 502, Unit-ID 3, writes via FC16 (writemultiple), U32 big-endian
  (high word first), GridWSpt is S32.

  40236  CmpBMS.OpMod       U32 enum — 2424=Default, 2289=Laden,
         2290=Entladen, 303=Aus, 1438=Automatik.
         ⚠️ some firmwares use 41259 instead — beta checklist item 2.
  40793  CmpBMS.BatChaMinW  U32 W — min charge power
  40795  CmpBMS.BatChaMaxW  U32 W — max charge power (0 = charging blocked)
  40797  CmpBMS.BatDschMinW U32 W — min discharge power
  40799  CmpBMS.BatDschMaxW U32 W — max discharge power
  40801  CmpBMS.GridWSpt    S32 W — grid-exchange setpoint at the grid
         connection point: POSITIVE = feed-in (export), NEGATIVE = draw
         from grid. ⚠️ sign is beta checklist item 1.

Protocol rules (SMA doc):
  - All 6 registers must be (re)written as a block within 10 s, otherwise
    the values are ignored. We write 40236 first, then 40793–40802 in a
    single contiguous FC16 multi-write — well inside the window.
  - The block must be refreshed at least every 300 s; on timeout the
    inverter falls back to its internal automatic battery management —
    a built-in failsafe if HA dies mid-discharge (identical semantics to
    the Kostal watchdog). The driver keepalive rewrites every 60 s
    (evcc uses the same interval).

Flash wear: the CmpBMS registers are volatile setpoints (not persisted) —
cyclic writing is required and harmless. Static parameters (SelfCsmp.*,
WMax, …) ARE flash-persisted; this driver never touches any register
outside {40236, 40793, 40795, 40797, 40799, 40801} in the write path.
Any other write address is a review-blocking bug.

Central conceptual difference to Fronius/Kostal: a forced discharge is
expressed as a GRID setpoint, not a battery setpoint. The inverter itself
regulates the grid connection point to +P W export and compensates house
consumption on top — the exported power is directly the EEG-effective
power. There is no hardware target-SOC: the optimizer supervises SOC every
30 s; the watchdog covers the HA-crash case.

VERIFY AT DEVICE (beta checklist, .planning/research/SMA-KONZEPT.md §8):
  1. GridWSpt sign + does it really force export beyond house consumption
  2. OpMod address 40236 vs 41259 on the target firmware (probe reads it)
  3. Coexistence with Sunny Home Manager 2 (prognosebasiertes Laden OFF)
  5. Fallback behavior after watchdog timeout
  6. Block-write timing (contiguous multi-write used here)
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def _slave_kw(client: Any, slave_id: int) -> dict:
    """Return the slave/device-id kwarg matching the active pymodbus API.

    pymodbus 3.9+ renamed ``slave`` to ``device_id`` — same probing approach
    as the Fronius/Kostal drivers so the code runs on both.
    """
    import inspect
    try:
        sig = inspect.signature(client.read_holding_registers)
        if "device_id" in sig.parameters:
            return {"device_id": slave_id}
    except (TypeError, ValueError):
        pass
    return {"slave": slave_id}


# SMA Modbus endpoint
SMA_UNIT_ID = 3

# CmpBMS control registers (write path — closed set, see module docstring)
REG_CMPBMS_OPMOD = 40236      # U32 enum
REG_BAT_CHA_MIN_W = 40793     # U32 W — start of the contiguous 5-value block
REG_BAT_CHA_MAX_W = 40795     # U32 W
REG_BAT_DSCH_MIN_W = 40797    # U32 W
REG_BAT_DSCH_MAX_W = 40799    # U32 W
REG_GRID_W_SPT = 40801        # S32 W — positive = export (verify at device!)

# Read registers (probe / diagnostics only)
REG_DEVICE_TYPE = 30053       # U32 — SMA device type id
REG_SERIAL = 30057            # U32 — serial number
REG_BATTERY_SOC = 30845       # U32 %
REG_BATTERY_CHARGE_W = 31393  # U32 W — current charge power
REG_BATTERY_DISCHARGE_W = 31395  # U32 W — current discharge power

# CmpBMS.OpMod enum values (SMA taglist)
OPMOD_DEFAULT = 2424   # "Voreinstellung" — limits + GridWSpt apply
OPMOD_CHARGE = 2289    # force charge (unused by us)
OPMOD_DISCHARGE = 2290  # force discharge — only discharges on grid DRAW,
#                         goes standby on export → useless for EEG feed-in;
#                         forced export works via GridWSpt under 2424.
OPMOD_OFF = 303
OPMOD_AUTO = 1438

# SMA NaN markers
U32_NAN = 0xFFFFFFFF
S32_NAN = 0x80000000

# Keepalive rewrite interval. SMA requires a refresh at least every 300 s;
# evcc uses 60 s — we match it (5× margin before the watchdog lapses).
KEEPALIVE_INTERVAL = 60.0

# Neutral upper power limit written to BatChaMaxW/BatDschMaxW when the mode
# does not restrict that direction. 10 kW covers the largest v1 target
# (STP10.0-SE battery path); devices clamp to their own hardware limit.
# Beta checklist: verify a value above the device limit is accepted.
DEFAULT_POWER_LIMIT_W = 10000


def u32_to_registers(value: int) -> list[int]:
    """Encode U32 big-endian (SMA standard: high word first)."""
    value = int(value) & 0xFFFFFFFF
    return [(value >> 16) & 0xFFFF, value & 0xFFFF]


def s32_to_registers(value: int) -> list[int]:
    """Encode S32 (two's complement) big-endian."""
    return u32_to_registers(int(value) & 0xFFFFFFFF)


def registers_to_u32(regs: list[int]) -> int:
    """Decode U32 from big-endian register pair."""
    return ((regs[0] & 0xFFFF) << 16) | (regs[1] & 0xFFFF)


def registers_to_s32(regs: list[int]) -> int:
    """Decode S32 (two's complement) from big-endian register pair."""
    raw = registers_to_u32(regs)
    return raw - 0x100000000 if raw >= 0x80000000 else raw


@dataclass(frozen=True)
class CmpBmsBlock:
    """One complete 6-parameter CmpBMS setpoint block."""

    op_mod: int
    cha_min_w: int
    cha_max_w: int
    dsch_min_w: int
    dsch_max_w: int
    grid_w_spt: int

    def power_registers(self) -> list[int]:
        """The contiguous register block 40793–40802 (5 × U32/S32)."""
        return (
            u32_to_registers(self.cha_min_w)
            + u32_to_registers(self.cha_max_w)
            + u32_to_registers(self.dsch_min_w)
            + u32_to_registers(self.dsch_max_w)
            + s32_to_registers(self.grid_w_spt)
        )


def _block_normal() -> CmpBmsBlock:
    """evcc 'normal': default mode, full limits, no grid setpoint."""
    return CmpBmsBlock(
        OPMOD_DEFAULT, 0, DEFAULT_POWER_LIMIT_W, 0, DEFAULT_POWER_LIMIT_W, 0
    )


def _block_charge_limit(watts: int) -> CmpBmsBlock:
    """Charging limited to `watts` (0 = blocked); discharge for the house
    stays available (evcc 'HoldCharge' semantics — same as Kostal 1038=0)."""
    return CmpBmsBlock(
        OPMOD_DEFAULT, 0, watts, 0, DEFAULT_POWER_LIMIT_W, 0
    )


def _block_discharge(export_watts: int) -> CmpBmsBlock:
    """Forced feed-in: grid setpoint +`export_watts`, charging blocked.

    GridWSpt regulates the grid connection point — the inverter adds house
    consumption on top of the export setpoint by itself, limited by
    BatDschMaxW. Positive = export (beta checklist item 1).
    """
    return CmpBmsBlock(
        OPMOD_DEFAULT, 0, 0, 0, DEFAULT_POWER_LIMIT_W, export_watts
    )


class SMAInverter(InverterBase):
    """SMA battery control via the CmpBMS 6-parameter Modbus method.

    The active block is held in ``self._active`` and rewritten by the
    keepalive task every KEEPALIVE_INTERVAL seconds until
    async_stop_forcible() clears it.
    """

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        self._host: str = config.get("sma_modbus_host", "")
        self._port: int = int(config.get("sma_modbus_port", 502))
        self._client: Any = None  # AsyncModbusTcpClient (lazy)
        self._slave_id: int = SMA_UNIT_ID
        # Active CmpBMS block the keepalive rewrites (None = inactive)
        self._active: CmpBmsBlock | None = None
        self._keepalive_task: asyncio.Task | None = None
        # Serializes Modbus operations between the 30-second optimizer
        # cycle, manual WebSocket commands, and the keepalive task (the
        # direct Modbus TCP path has no HA service-call serialization).
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection handling (mirrors the Fronius/Kostal drivers)
    # ------------------------------------------------------------------

    def _close_client(self) -> None:
        """Close and discard the Modbus TCP client (releases the socket)."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                _LOGGER.debug("SMA: error closing Modbus client")
            self._client = None

    async def _ensure_connected(self) -> bool:
        """Ensure Modbus TCP connection is established (3 attempts)."""
        if self._client is not None and self._client.connected:
            return True

        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError:
            _LOGGER.error("SMA: pymodbus not installed")
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
                        "SMA: Modbus TCP connected to %s:%s (attempt %d)",
                        self._host, self._port, attempt + 1,
                    )
                    return True
            except Exception:
                _LOGGER.debug(
                    "SMA: connection attempt %d failed", attempt + 1
                )
                self._close_client()
            if attempt < 2:
                await asyncio.sleep(0.2)

        _LOGGER.error(
            "SMA: failed to connect to %s:%s after 3 attempts",
            self._host, self._port,
        )
        return False

    # ------------------------------------------------------------------
    # Register primitives
    # ------------------------------------------------------------------

    async def _write_block(self, block: CmpBmsBlock) -> bool:
        """Write a complete CmpBMS block: OpMod, then 40793–40802 in one FC16.

        The SMA spec requires all 6 parameters within 10 s; the contiguous
        multi-write keeps the power block atomic (beta checklist item 6).
        """
        try:
            result = await self._client.write_registers(
                address=REG_CMPBMS_OPMOD,
                values=u32_to_registers(block.op_mod),
                **_slave_kw(self._client, self._slave_id),
            )
            if result.isError():
                _LOGGER.error(
                    "SMA: write error at OpMod register %d (value=%d)",
                    REG_CMPBMS_OPMOD, block.op_mod,
                )
                return False
            self.register_writes += 1
            await asyncio.sleep(0.2)

            result = await self._client.write_registers(
                address=REG_BAT_CHA_MIN_W,
                values=block.power_registers(),
                **_slave_kw(self._client, self._slave_id),
            )
            if result.isError():
                _LOGGER.error(
                    "SMA: write error at power block %d–%d (%s)",
                    REG_BAT_CHA_MIN_W, REG_GRID_W_SPT + 1, block,
                )
                return False
            self.register_writes += 1
            await asyncio.sleep(0.2)
            _LOGGER.debug("SMA: wrote CmpBMS block %s", block)
            return True
        except Exception:
            _LOGGER.exception("SMA: exception writing CmpBMS block %s", block)
            self._close_client()
            return False

    async def _read_u32(self, address: int) -> int | None:
        """Read a U32 holding register pair (None on error or SMA-NaN)."""
        try:
            result = await self._client.read_holding_registers(
                address=address, count=2,
                **_slave_kw(self._client, self._slave_id),
            )
            if result.isError():
                _LOGGER.error("SMA: read error at register %d", address)
                return None
            value = registers_to_u32(result.registers)
            return None if value == U32_NAN else value
        except Exception:
            _LOGGER.exception("SMA: exception reading register %d", address)
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
        """Rewrite the active CmpBMS block until cancelled.

        Failures are logged but tolerated: a lapse only means temporary
        fallback to the inverter's internal automatic management; the next
        successful rewrite re-arms external control.
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
                            "SMA: keepalive write skipped — not connected"
                        )
                        continue
                    if not await self._write_block(active):
                        _LOGGER.warning(
                            "SMA: keepalive rewrite failed (%s) — will retry "
                            "next interval; watchdog may fall back to "
                            "internal mode until then",
                            active,
                        )
        except asyncio.CancelledError:
            pass
        except Exception:
            _LOGGER.exception("SMA: keepalive loop crashed")

    # ------------------------------------------------------------------
    # InverterBase implementation
    # ------------------------------------------------------------------

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery max charge power / block charging.

        power_kw=0: block charging (Morgen-Einspeisung) — BatChaMaxW = 0,
        discharge for house consumption stays available (evcc 'HoldCharge').
        power_kw>0: partial charge limit (Einspeisebegrenzung).
        The keepalive rewrites the block until stop. No stuck-register
        guards needed: every write is a complete 6-parameter block.
        """
        async with self._lock:
            watts = int(max(power_kw, 0.0) * 1000.0)
            block = _block_charge_limit(watts)
            if not await self._ensure_connected():
                return False
            if not await self._write_block(block):
                return False
            self._active = block
            self._start_keepalive()
            _LOGGER.info(
                "SMA: charge limit set (%.2f kW) — keepalive active", power_kw
            )
            return True

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force feed-in at the given power via the grid setpoint.

        GridWSpt = +power_kw regulates the GRID CONNECTION POINT: the
        exported power is directly the EEG-effective power, house
        consumption is compensated on top by the inverter (up to
        BatDschMaxW). SMA has no hardware target-SOC: `target_soc` is
        accepted for interface compatibility; enforcement happens in the
        optimizer (30 s cycle), the watchdog covers the HA-crash case.
        """
        async with self._lock:
            watts = int(max(power_kw, 0.0) * 1000.0)
            block = _block_discharge(watts)
            if not await self._ensure_connected():
                return False
            if not await self._write_block(block):
                return False
            self._active = block
            self._start_keepalive()
            _LOGGER.info(
                "SMA: grid feed-in setpoint set (%.2f kW) — keepalive active",
                power_kw,
            )
            return True

    async def async_stop_forcible(self) -> bool:
        """Stop forced control, return to automatic mode.

        Writes one neutral block (default mode, full limits, setpoint 0),
        then stops feeding the watchdog — the inverter falls back to its
        internal automatic management within 300 s.
        """
        async with self._lock:
            # Clear the active block FIRST so a failed write below cannot
            # race with a concurrent keepalive rewrite of the old block.
            self._active = None
            self._cancel_keepalive()
            if not await self._ensure_connected():
                return False
            if not await self._write_block(_block_normal()):
                # False → optimizer retries stop next cycle. Even a
                # persistent failure resolves once the watchdog lapses.
                return False
            _LOGGER.info(
                "SMA: stopped forcible mode — watchdog will hand back "
                "to internal automatic management"
            )
            return True

    @property
    def is_available(self) -> bool:
        """Whether the inverter is reachable.

        Connection is opened lazily (same rationale as Fronius/Kostal):
        as long as a host is configured, report available — the real TCP
        probe happens inside _ensure_connected when an operation runs.
        """
        return bool(self._host)

    async def async_disconnect(self) -> None:
        """Stop keepalive and disconnect (called on entry unload)."""
        self._cancel_keepalive()
        self._active = None
        self._close_client()
