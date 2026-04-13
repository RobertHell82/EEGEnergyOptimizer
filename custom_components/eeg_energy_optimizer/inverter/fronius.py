"""Fronius Gen24 inverter control via direct Modbus TCP (SunSpec Model 124).

Uses pymodbus AsyncModbusTcpClient for direct register writes.
Sensors are read via the native HA Fronius Integration (Solar API).
Only 2-3 registers written per operation: StorCtl_Mod, InWRte, OutWRte.

SunSpec Model 124 register offsets (relative to discovered base address):
  +0  WChaMax      uint16  R   Max battery power in W
  +3  StorCtl_Mod  bitfield16 RW  Control mode (Bit 0=Charge, Bit 1=Discharge)
  +5  MinRsvPct    uint16(SF-2) RW  Min reserve %
  +12 OutWRte      int16(SF-2)  RW  Discharge rate % of WChaMax
  +13 InWRte       int16(SF-2)  RW  Charge rate % of WChaMax
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# SunSpec Model 124 register offsets (relative to model base address)
_OFFSET_WCHAMAX = 0
_OFFSET_STORCTL_MOD = 3
_OFFSET_MINRSVPCT = 5
_OFFSET_OUTWRTE = 12
_OFFSET_INWRTE = 13

# SunSpec identification
_SUNSPEC_ID_WORD0 = 0x5375  # "Su"
_SUNSPEC_ID_WORD1 = 0x6E53  # "nS"
_SUNSPEC_START = 40000
_SUNSPEC_MODEL_124 = 124
_SUNSPEC_END_MARKER = 0xFFFF
_SUNSPEC_MAX_ITERATIONS = 128

# Scale factor for InWRte/OutWRte: SF = -2, so 10000 = 100%
_RATE_100_PERCENT = 10000

# Sanity bound for WChaMax (max battery power in W). No residential Fronius
# Gen24 + battery setup exceeds this; a larger value almost certainly comes
# from a corrupted Modbus response and would compress every charge/discharge
# percentage calculation toward zero, making the battery appear inert.
_WCHAMAX_SANITY_LIMIT = 25000


class FroniusInverter(InverterBase):
    """Fronius Gen24 battery control via direct Modbus TCP (SunSpec Model 124)."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        self._host: str = config.get("fronius_modbus_host", "")
        self._port: int = int(config.get("fronius_modbus_port", 502))
        self._client: Any = None  # AsyncModbusTcpClient (lazy)
        self._model124_base: int | None = None
        self._wchamax: int | None = None
        self._wchamax_date: str | None = None  # date string for daily cache
        self._slave_id: int = 1  # Fronius default Modbus unit ID
        # Cached MinRsvPct value (raw register, SF -2) read before
        # async_set_discharge() overwrites it. Restored by
        # async_stop_forcible() so we do not leave the inverter with
        # an elevated reserve in automatic mode.
        self._minrsvpct_pre_discharge: int | None = None
        # Serializes Modbus operations. The 30-second optimizer cycle and
        # manual WebSocket commands (manual_discharge, manual_stop,
        # manual_block_charge) can otherwise interleave their multi-register
        # write sequences and leave the inverter in a half-set state.
        # Other inverter drivers rely on HA service-call serialization;
        # the direct Modbus TCP path here has no such guarantee.
        self._lock = asyncio.Lock()

    def _close_client(self) -> None:
        """Close and discard the Modbus TCP client.

        Use this instead of `self._client = None` so the underlying socket
        is released immediately rather than waiting for the GC. pymodbus
        AsyncModbusTcpClient.close() is synchronous (it just tears the
        transport down).
        """
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                _LOGGER.debug("Fronius: error closing Modbus client")
            self._client = None

    async def _ensure_connected(self) -> bool:
        """Ensure Modbus TCP connection is established.

        Creates a new AsyncModbusTcpClient if needed and attempts connection
        with up to 3 retries (200ms delay between attempts).
        Returns True if connected, False on failure.
        """
        if self._client is not None and self._client.connected:
            return True

        try:
            from pymodbus.client import AsyncModbusTcpClient
        except ImportError:
            _LOGGER.error("Fronius: pymodbus not installed")
            return False

        for attempt in range(3):
            try:
                if self._client is None or not self._client.connected:
                    # Close any stale client before replacing it
                    self._close_client()
                    self._client = AsyncModbusTcpClient(
                        self._host, port=self._port
                    )
                    await self._client.connect()
                if self._client.connected:
                    _LOGGER.debug(
                        "Fronius: Modbus TCP connected to %s:%s (attempt %d)",
                        self._host, self._port, attempt + 1,
                    )
                    return True
            except Exception:
                _LOGGER.debug(
                    "Fronius: connection attempt %d failed", attempt + 1
                )
                self._close_client()
            if attempt < 2:
                await asyncio.sleep(0.2)

        _LOGGER.error(
            "Fronius: failed to connect to %s:%s after 3 attempts",
            self._host, self._port,
        )
        return False

    async def _discover_model124(self) -> bool:
        """SunSpec Model Discovery: scan from register 40000 to find Model 124.

        Reads the SunSpec identification header, then iterates through the
        model table until Model 124 is found or the end marker is reached.
        """
        if self._client is None or not self._client.connected:
            return False

        try:
            # Verify SunSpec ID at registers 40000-40001
            result = await self._client.read_holding_registers(
                _SUNSPEC_START, 2, slave=self._slave_id
            )
            if result.isError():
                _LOGGER.error("Fronius: failed to read SunSpec ID at %d", _SUNSPEC_START)
                return False

            word0, word1 = result.registers[0], result.registers[1]
            if word0 != _SUNSPEC_ID_WORD0 or word1 != _SUNSPEC_ID_WORD1:
                _LOGGER.error(
                    "Fronius: invalid SunSpec ID at %d: 0x%04X 0x%04X (expected 0x%04X 0x%04X)",
                    _SUNSPEC_START, word0, word1, _SUNSPEC_ID_WORD0, _SUNSPEC_ID_WORD1,
                )
                return False

            _LOGGER.debug("Fronius: SunSpec ID verified at %d", _SUNSPEC_START)

            # Iterate through model table starting at 40002
            address = _SUNSPEC_START + 2
            for i in range(_SUNSPEC_MAX_ITERATIONS):
                result = await self._client.read_holding_registers(
                    address, 2, slave=self._slave_id
                )
                if result.isError():
                    _LOGGER.error(
                        "Fronius: failed to read model header at %d", address
                    )
                    return False

                model_id = result.registers[0]
                length = result.registers[1]

                _LOGGER.debug(
                    "Fronius: model %d (length %d) at address %d",
                    model_id, length, address,
                )

                if model_id == _SUNSPEC_END_MARKER:
                    _LOGGER.warning(
                        "Fronius: SunSpec end marker reached at %d, Model 124 not found",
                        address,
                    )
                    return False

                if model_id == _SUNSPEC_MODEL_124:
                    # Model 124 data starts after the 2-register header
                    self._model124_base = address + 2
                    _LOGGER.info(
                        "Fronius: SunSpec Model 124 found, data base address = %d",
                        self._model124_base,
                    )
                    return True

                # Advance past header (2 regs) + model data (length regs)
                address += length + 2

        except Exception:
            _LOGGER.exception("Fronius: error during SunSpec Model Discovery")
            self._close_client()
            return False

        return False

    async def _ensure_model124(self) -> bool:
        """Ensure Modbus connection is alive and Model 124 base address is known.

        Connection check must happen before the cache check — otherwise the
        cached base address keeps the driver from reconnecting after a
        Modbus TCP drop, and every subsequent read/write fails silently.
        """
        if not await self._ensure_connected():
            return False
        if self._model124_base is not None:
            return True
        return await self._discover_model124()

    async def _read_wchamax(self) -> int | None:
        """Read WChaMax (max battery power in W) from Model 124 offset +0.

        Cached for the current day — only re-read once per day.
        """
        today = date.today().isoformat()
        if self._wchamax is not None and self._wchamax_date == today:
            return self._wchamax

        if not await self._ensure_model124():
            return None

        try:
            result = await self._client.read_holding_registers(
                self._model124_base + _OFFSET_WCHAMAX, 1, slave=self._slave_id
            )
            if result.isError():
                _LOGGER.error("Fronius: failed to read WChaMax")
                return None

            raw = result.registers[0]
            if raw == 0 or raw > _WCHAMAX_SANITY_LIMIT:
                # Implausible value — likely a corrupted Modbus response or
                # wrong SunSpec model layout. Don't cache, force a re-read on
                # the next cycle. Zero is also handled by callers as "unknown".
                _LOGGER.warning(
                    "Fronius: WChaMax=%d W outside plausible range (1..%d) — ignoring",
                    raw, _WCHAMAX_SANITY_LIMIT,
                )
                return None

            self._wchamax = raw
            self._wchamax_date = today
            _LOGGER.info("Fronius: WChaMax = %d W", self._wchamax)
            return self._wchamax

        except Exception:
            _LOGGER.exception("Fronius: error reading WChaMax")
            self._close_client()
            return None

    async def _write_register(self, offset: int, value: int) -> bool:
        """Write a single register at Model 124 base + offset.

        Increments register_writes counter and adds 200ms pause after write.
        """
        if self._model124_base is None:
            _LOGGER.error("Fronius: Model 124 base address not discovered")
            return False

        address = self._model124_base + offset
        try:
            result = await self._client.write_register(
                address, value, slave=self._slave_id
            )
            if result.isError():
                _LOGGER.error(
                    "Fronius: write error at register %d (value=%d)", address, value
                )
                return False
            self.register_writes += 1
            await asyncio.sleep(0.2)
            _LOGGER.debug(
                "Fronius: wrote register %d = %d", address, value
            )
            return True
        except Exception:
            _LOGGER.exception(
                "Fronius: exception writing register %d (value=%d)", address, value
            )
            self._close_client()
            return False

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit / block charging.

        power_kw=0: Block charging (Morgen-Einspeisung)
          - StorCtl_Mod = 1 (Bit 0: Charge Limit active)
          - InWRte = 0 (0% charge = no charging)

        power_kw>0: Partial charge limit
          - StorCtl_Mod = 1
          - InWRte = percent of WChaMax (SF -2)
        """
        async with self._lock:
            return await self._set_charge_limit_locked(power_kw)

    async def _set_charge_limit_locked(self, power_kw: float) -> bool:
        try:
            if not await self._ensure_model124():
                return False

            wchamax = await self._read_wchamax()
            if wchamax is None or wchamax == 0:
                _LOGGER.error("Fronius: cannot set charge limit — WChaMax unknown or zero")
                return False

            # Write the rate register BEFORE activating the limit mode.
            # If StorCtl_Mod=1 succeeded first and InWRte then failed, the
            # inverter would enter Charge-Limit mode with the previously
            # cached InWRte (possibly 10000 = 100%) and silently fail to
            # block charging. Setting the rate first guarantees that when
            # the mode bit flips, the desired rate is already in place.
            if power_kw == 0:
                # Block charging completely
                inwrte_value = 0
            else:
                # Partial charge limit
                inwrte_value = int(
                    min(power_kw * 1000 / wchamax, 1.0) * _RATE_100_PERCENT
                )
            if not await self._write_register(_OFFSET_INWRTE, inwrte_value):
                return False

            # StorCtl_Mod = 1 (Charge Limit active) — activates InWRte set above
            if not await self._write_register(_OFFSET_STORCTL_MOD, 1):
                return False

            _LOGGER.info(
                "Fronius: charge limit set (power_kw=%.2f, WChaMax=%d W)",
                power_kw, wchamax,
            )
            return True

        except Exception:
            _LOGGER.exception("Fronius: failed to set charge limit")
            self._close_client()
            return False

    # TODO: KONZEPT open question 8.1 — StorCtl_Mod=3 may force grid discharge
    # even when house consumption could absorb battery output. Needs validation
    # on real Fronius Gen24 hardware. If confirmed, consider using StorCtl_Mod=2
    # (discharge-only) combined with separate charge blocking via a follow-up
    # StorCtl_Mod=1 write, or test if the inverter self-consumption logic still
    # applies under StorCtl_Mod=3.
    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Force battery discharge at given power.

        Sets StorCtl_Mod=3 (Charge + Discharge Limit active),
        OutWRte to discharge percent, InWRte=0 to block charging.
        Optionally sets MinRsvPct for SOC floor.
        """
        async with self._lock:
            return await self._set_discharge_locked(power_kw, target_soc)

    async def _set_discharge_locked(
        self, power_kw: float, target_soc: float | None
    ) -> bool:
        try:
            if not await self._ensure_model124():
                return False

            wchamax = await self._read_wchamax()
            if wchamax is None or wchamax == 0:
                _LOGGER.error("Fronius: cannot set discharge — WChaMax unknown or zero")
                return False

            percent = int(min(power_kw * 1000 / wchamax, 1.0) * _RATE_100_PERCENT)

            # Write the rate registers BEFORE activating the limit mode so
            # that a partial failure can never leave the inverter with the
            # discharge mode active but stale rate values from a previous
            # operation. See ME-03 in REVIEW.md / set_charge_limit comment.

            # InWRte = 0 (block charging during discharge)
            if not await self._write_register(_OFFSET_INWRTE, 0):
                return False

            # OutWRte = discharge percent
            if not await self._write_register(_OFFSET_OUTWRTE, percent):
                return False

            # Optional: set MinRsvPct for SOC floor (SF -2, e.g. 1500 = 15%)
            if target_soc is not None:
                # Snapshot the current MinRsvPct so async_stop_forcible() can
                # restore the user's configured reserve. Fronius has no
                # auto-revert, so without this snapshot the elevated reserve
                # would persist into automatic mode.
                if self._minrsvpct_pre_discharge is None:
                    try:
                        result = await self._client.read_holding_registers(
                            self._model124_base + _OFFSET_MINRSVPCT,
                            1,
                            slave=self._slave_id,
                        )
                        if not result.isError():
                            self._minrsvpct_pre_discharge = result.registers[0]
                            _LOGGER.debug(
                                "Fronius: cached pre-discharge MinRsvPct=%d",
                                self._minrsvpct_pre_discharge,
                            )
                    except Exception:
                        _LOGGER.debug(
                            "Fronius: could not snapshot MinRsvPct — will skip restore"
                        )

                min_rsv = int(target_soc * 100)
                if not await self._write_register(_OFFSET_MINRSVPCT, min_rsv):
                    _LOGGER.warning("Fronius: failed to set MinRsvPct (non-critical)")

            # StorCtl_Mod = 3 (Bits 0+1: Charge + Discharge Limit active) —
            # written LAST so that all rate/reserve registers are already in
            # place when the mode bits flip on. Prevents partial-failure
            # states like "discharge mode active with stale rate values".
            if not await self._write_register(_OFFSET_STORCTL_MOD, 3):
                return False

            _LOGGER.info(
                "Fronius: discharge set (power_kw=%.2f, percent=%d, WChaMax=%d W)",
                power_kw, percent, wchamax,
            )
            return True

        except Exception:
            _LOGGER.exception("Fronius: failed to set discharge")
            self._close_client()
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Restores: StorCtl_Mod=0, InWRte=10000 (100%), OutWRte=10000 (100%).
        """
        async with self._lock:
            return await self._stop_forcible_locked()

    async def _stop_forcible_locked(self) -> bool:
        try:
            if not await self._ensure_model124():
                return False

            # StorCtl_Mod = 0 (no limits active)
            if not await self._write_register(_OFFSET_STORCTL_MOD, 0):
                return False

            # InWRte = 10000 (100% charge allowed)
            if not await self._write_register(_OFFSET_INWRTE, _RATE_100_PERCENT):
                return False

            # OutWRte = 10000 (100% discharge allowed)
            if not await self._write_register(_OFFSET_OUTWRTE, _RATE_100_PERCENT):
                return False

            # Restore MinRsvPct if async_set_discharge() raised it earlier.
            # Fronius has no auto-revert: leaving the reserve elevated
            # would prevent the inverter from using the battery down to
            # the user's configured level in automatic mode.
            if self._minrsvpct_pre_discharge is not None:
                restored = self._minrsvpct_pre_discharge
                if await self._write_register(_OFFSET_MINRSVPCT, restored):
                    _LOGGER.info(
                        "Fronius: restored MinRsvPct to %d (pre-discharge value)",
                        restored,
                    )
                    self._minrsvpct_pre_discharge = None
                else:
                    _LOGGER.warning(
                        "Fronius: failed to restore MinRsvPct=%d — keeping cached value for retry",
                        restored,
                    )

            _LOGGER.info("Fronius: stopped forcible mode — automatic operation restored")
            return True

        except Exception:
            _LOGGER.exception("Fronius: failed to stop forcible mode")
            self._close_client()
            return False

    @property
    def is_available(self) -> bool:
        """Whether the Modbus TCP connection is established."""
        return self._client is not None and self._client.connected

    async def async_disconnect(self) -> None:
        """Disconnect Modbus TCP client for cleanup (called on entry unload)."""
        self._close_client()
