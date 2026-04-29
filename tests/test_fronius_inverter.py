"""Tests for Fronius Gen24 inverter implementation (SunSpec Model 124 Modbus TCP)."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.fronius import (
    FroniusInverter,
    _OFFSET_INWRTE,
    _OFFSET_MINRSVPCT,
    _OFFSET_OUTWRTE,
    _OFFSET_RVRTTMS,
    _OFFSET_STORCTL_MOD,
    _OFFSET_WCHAMAX,
    _OFFSET_WINTMS,
    _RATE_100_PERCENT,
    _SUNSPEC_END_MARKER,
    _SUNSPEC_ID_WORD0,
    _SUNSPEC_ID_WORD1,
    _SUNSPEC_MODEL_124,
    _WCHAMAX_SANITY_LIMIT,
)


def _ok_response(registers=None):
    res = MagicMock()
    res.isError = MagicMock(return_value=False)
    if registers is not None:
        res.registers = registers
    return res


def _err_response():
    res = MagicMock()
    res.isError = MagicMock(return_value=True)
    return res


@pytest.fixture
def fronius_config():
    return {
        "fronius_modbus_host": "192.168.1.100",
        "fronius_modbus_port": 502,
    }


@pytest.fixture
def mock_modbus_client():
    """Mocked AsyncModbusTcpClient with success responses by default."""
    client = MagicMock()
    client.connected = True
    client.write_register = AsyncMock(return_value=_ok_response())
    client.read_holding_registers = AsyncMock(return_value=_ok_response([0]))
    client.connect = AsyncMock(return_value=True)
    client.close = MagicMock()
    return client


@pytest.fixture
def inverter(mock_hass, fronius_config, mock_modbus_client):
    """FroniusInverter with mocked client and pre-discovered Model 124 base."""
    inv = FroniusInverter(mock_hass, fronius_config)
    inv._client = mock_modbus_client
    inv._model124_base = 40070
    inv._wchamax = 5000  # 5 kW residential battery
    inv._wchamax_date = date.today().isoformat()
    return inv


class TestFroniusInverterBase:
    """Verify FroniusInverter conforms to the InverterBase contract."""

    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(FroniusInverter, InverterBase)


class TestConfigParsing:
    """Host and port are read from config (panel-driven)."""

    def test_host_from_config(self, mock_hass):
        inv = FroniusInverter(mock_hass, {"fronius_modbus_host": "10.0.0.5"})
        assert inv._host == "10.0.0.5"

    def test_default_port(self, mock_hass):
        inv = FroniusInverter(mock_hass, {})
        assert inv._port == 502

    def test_custom_port(self, mock_hass):
        inv = FroniusInverter(mock_hass, {"fronius_modbus_port": 1502})
        assert inv._port == 1502

    def test_string_port_coerced(self, mock_hass):
        """Port may arrive as a string from JSON-loaded config — must coerce."""
        inv = FroniusInverter(mock_hass, {"fronius_modbus_port": "503"})
        assert inv._port == 503


class TestAsyncSetChargeLimit:
    """Block / partial charge limit via InWRte (offset 13) + StorCtl_Mod (offset 3)."""

    async def test_block_charging_writes_inwrte_then_mode(self, inverter, mock_modbus_client):
        """power_kw=0 → InWRte=0, WinTms=0, RvrtTms=0, then StorCtl_Mod=1.

        Order matters: if mode flips on with a stale 100% rate value, the
        inverter would silently keep charging. Watchdog timers must be
        cleared before activating the mode so the limit takes effect
        immediately and is not auto-reverted after a few seconds.
        """
        result = await inverter.async_set_charge_limit(0)
        assert result is True

        calls = mock_modbus_client.write_register.call_args_list
        assert len(calls) == 4
        base = inverter._model124_base
        # 1. InWRte = 0
        assert (calls[0].kwargs["address"], calls[0].kwargs["value"]) == (base + _OFFSET_INWRTE, 0)
        # 2. WinTms = 0 (immediate effect)
        assert (calls[1].kwargs["address"], calls[1].kwargs["value"]) == (base + _OFFSET_WINTMS, 0)
        # 3. RvrtTms = 0 (no auto-revert)
        assert (calls[2].kwargs["address"], calls[2].kwargs["value"]) == (base + _OFFSET_RVRTTMS, 0)
        # 4. StorCtl_Mod = 1 (Charge Limit active)
        assert (calls[3].kwargs["address"], calls[3].kwargs["value"]) == (base + _OFFSET_STORCTL_MOD, 1)

    async def test_partial_charge_uses_wchamax_percentage(
        self, inverter, mock_modbus_client
    ):
        """power_kw=2.5 with WChaMax=5000W → 50% → 5000 (SF -2 = 100×percent)."""
        result = await inverter.async_set_charge_limit(2.5)
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        assert calls[0].kwargs["value"] == 5000  # 50% in SF -2 encoding

    async def test_partial_charge_clamped_to_100pct(self, inverter, mock_modbus_client):
        """power exceeding WChaMax is clamped to 100% (10000)."""
        result = await inverter.async_set_charge_limit(10.0)  # WChaMax=5kW
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        assert calls[0].kwargs["value"] == _RATE_100_PERCENT

    async def test_returns_false_on_write_error(self, inverter, mock_modbus_client):
        mock_modbus_client.write_register = AsyncMock(return_value=_err_response())
        result = await inverter.async_set_charge_limit(0)
        assert result is False

    async def test_returns_false_on_exception(self, inverter, mock_modbus_client):
        mock_modbus_client.write_register = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_charge_limit(0)
        assert result is False
        # Client closed on error so next call reconnects
        assert inverter._client is None

    async def test_returns_false_when_wchamax_unknown(
        self, inverter, mock_modbus_client
    ):
        """Without a known WChaMax the percentage scaling cannot be computed."""
        inverter._wchamax = None
        inverter._wchamax_date = None
        # Re-read returns out-of-range value → still rejected
        bad = _ok_response([_WCHAMAX_SANITY_LIMIT + 1])
        mock_modbus_client.read_holding_registers = AsyncMock(return_value=bad)
        result = await inverter.async_set_charge_limit(0)
        assert result is False


class TestAsyncSetDischarge:
    """Force discharge via InWRte=0, OutWRte=%, optional MinRsvPct, then StorCtl_Mod=3."""

    async def test_discharge_with_target_soc_writes_full_sequence(
        self, inverter, mock_modbus_client
    ):
        """power_kw=2.5, target_soc=15 → InWRte=0, OutWRte=5000, MinRsvPct=1500,
        WinTms=0, RvrtTms=0, StorCtl_Mod=3."""
        # Pre-discharge MinRsvPct read returns 500 (5%)
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([500])
        )
        result = await inverter.async_set_discharge(2.5, target_soc=15)
        assert result is True

        calls = mock_modbus_client.write_register.call_args_list
        assert len(calls) == 6
        base = inverter._model124_base
        assert (calls[0].kwargs["address"], calls[0].kwargs["value"]) == (base + _OFFSET_INWRTE, 0)
        assert (calls[1].kwargs["address"], calls[1].kwargs["value"]) == (base + _OFFSET_OUTWRTE, 5000)
        assert (calls[2].kwargs["address"], calls[2].kwargs["value"]) == (base + _OFFSET_MINRSVPCT, 1500)
        assert (calls[3].kwargs["address"], calls[3].kwargs["value"]) == (base + _OFFSET_WINTMS, 0)
        assert (calls[4].kwargs["address"], calls[4].kwargs["value"]) == (base + _OFFSET_RVRTTMS, 0)
        assert (calls[5].kwargs["address"], calls[5].kwargs["value"]) == (base + _OFFSET_STORCTL_MOD, 3)
        # Pre-discharge MinRsvPct cached for later restore
        assert inverter._minrsvpct_pre_discharge == 500

    async def test_discharge_without_target_soc_skips_minrsvpct(
        self, inverter, mock_modbus_client
    ):
        result = await inverter.async_set_discharge(2.5)
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        assert len(calls) == 5
        base = inverter._model124_base
        offsets = [c.kwargs["address"] - base for c in calls]
        assert _OFFSET_MINRSVPCT not in offsets
        assert inverter._minrsvpct_pre_discharge is None

    async def test_discharge_clamps_to_100pct(self, inverter, mock_modbus_client):
        """Power exceeding WChaMax clamps to 100% (10000)."""
        result = await inverter.async_set_discharge(10.0)  # WChaMax=5kW
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        # OutWRte is the second write
        assert calls[1].kwargs["value"] == _RATE_100_PERCENT

    async def test_storctl_mod_written_last(self, inverter, mock_modbus_client):
        """Mode bit must flip on AFTER all rate registers are in place."""
        await inverter.async_set_discharge(2.5)
        calls = mock_modbus_client.write_register.call_args_list
        assert calls[-1].kwargs["address"] == inverter._model124_base + _OFFSET_STORCTL_MOD
        assert calls[-1].kwargs["value"] == 3

    async def test_returns_false_on_exception(self, inverter, mock_modbus_client):
        mock_modbus_client.write_register = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_set_discharge(2.5)
        assert result is False

    async def test_minrsvpct_snapshot_failure_is_non_critical(
        self, inverter, mock_modbus_client
    ):
        """Failure to snapshot MinRsvPct must not abort the discharge."""
        mock_modbus_client.read_holding_registers = AsyncMock(
            side_effect=Exception("read failed")
        )
        result = await inverter.async_set_discharge(2.5, target_soc=15)
        assert result is True
        # Snapshot stays None — restore on stop will be skipped
        assert inverter._minrsvpct_pre_discharge is None


class TestAsyncStopForcible:
    """Stop writes StorCtl_Mod=0, then InWRte/OutWRte=10000, plus optional MinRsvPct restore."""

    async def test_stop_forcible_basic_sequence(self, inverter, mock_modbus_client):
        """Without cached MinRsvPct: 3 writes — mode off, charge 100%, discharge 100%."""
        result = await inverter.async_stop_forcible()
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        assert len(calls) == 3
        base = inverter._model124_base
        assert (calls[0].kwargs["address"], calls[0].kwargs["value"]) == (base + _OFFSET_STORCTL_MOD, 0)
        assert (calls[1].kwargs["address"], calls[1].kwargs["value"]) == (base + _OFFSET_INWRTE, _RATE_100_PERCENT)
        assert (calls[2].kwargs["address"], calls[2].kwargs["value"]) == (base + _OFFSET_OUTWRTE, _RATE_100_PERCENT)

    async def test_stop_forcible_restores_minrsvpct(self, inverter, mock_modbus_client):
        """A cached pre-discharge reserve is restored on stop, then cleared."""
        inverter._minrsvpct_pre_discharge = 500  # 5%
        result = await inverter.async_stop_forcible()
        assert result is True
        calls = mock_modbus_client.write_register.call_args_list
        assert len(calls) == 4
        assert (calls[3].kwargs["address"], calls[3].kwargs["value"]) == (
            inverter._model124_base + _OFFSET_MINRSVPCT,
            500,
        )
        assert inverter._minrsvpct_pre_discharge is None

    async def test_stop_forcible_keeps_minrsvpct_on_failed_restore(
        self, inverter, mock_modbus_client
    ):
        """Failed restore keeps the cached value so the next stop can retry."""
        inverter._minrsvpct_pre_discharge = 500
        responses = [
            _ok_response(),    # StorCtl_Mod=0
            _ok_response(),    # InWRte=10000
            _ok_response(),    # OutWRte=10000
            _err_response(),   # MinRsvPct restore — fails
        ]
        mock_modbus_client.write_register = AsyncMock(side_effect=responses)
        await inverter.async_stop_forcible()
        # Cache retained for retry on the next stop_forcible
        assert inverter._minrsvpct_pre_discharge == 500

    async def test_returns_false_on_exception(self, inverter, mock_modbus_client):
        mock_modbus_client.write_register = AsyncMock(side_effect=Exception("boom"))
        result = await inverter.async_stop_forcible()
        assert result is False


class TestIsAvailable:
    """is_available reflects whether a host is configured.

    Fronius opens the Modbus TCP connection lazily, so checking the live
    socket state would falsely report unavailable before the first
    operation runs. As long as a host is configured, the inverter is
    considered available — the actual TCP probe happens in
    _ensure_connected when an operation runs.
    """

    def test_available_when_host_configured(self, inverter, mock_modbus_client):
        mock_modbus_client.connected = True
        assert inverter.is_available is True

    def test_available_even_when_socket_disconnected(self, inverter, mock_modbus_client):
        """Disconnected socket still reports available — reconnect happens lazily."""
        mock_modbus_client.connected = False
        assert inverter.is_available is True

    def test_available_without_client(self, mock_hass, fronius_config):
        """No client yet, but host configured → available (lazy connect)."""
        inv = FroniusInverter(mock_hass, fronius_config)
        assert inv.is_available is True

    def test_unavailable_when_no_host(self, mock_hass):
        """Without a configured host, the inverter cannot be reached."""
        inv = FroniusInverter(mock_hass, {})
        assert inv.is_available is False


class TestAsyncDisconnect:
    """async_disconnect is called from async_unload_entry to free the TCP socket."""

    async def test_disconnect_closes_client(self, inverter, mock_modbus_client):
        await inverter.async_disconnect()
        mock_modbus_client.close.assert_called_once()
        assert inverter._client is None

    async def test_disconnect_when_no_client(self, mock_hass, fronius_config):
        inv = FroniusInverter(mock_hass, fronius_config)
        # Must not raise even though no client was ever created
        await inv.async_disconnect()


class TestRegisterWriteCounter:
    """Each successful Modbus write increments register_writes."""

    async def test_counter_increments_per_write(self, inverter, mock_modbus_client):
        before = inverter.register_writes
        await inverter.async_set_charge_limit(0)
        # set_charge_limit writes 4 registers: InWRte, WinTms, RvrtTms, StorCtl_Mod
        assert inverter.register_writes == before + 4

    async def test_failed_write_does_not_increment(
        self, inverter, mock_modbus_client
    ):
        before = inverter.register_writes
        mock_modbus_client.write_register = AsyncMock(return_value=_err_response())
        await inverter.async_set_charge_limit(0)
        assert inverter.register_writes == before


class TestWChaMaxSanityCheck:
    """Implausible WChaMax values are rejected so percentage scaling stays correct."""

    async def test_zero_wchamax_rejected(self, inverter, mock_modbus_client):
        inverter._wchamax = None
        inverter._wchamax_date = None
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([0])
        )
        result = await inverter._read_wchamax()
        assert result is None
        assert inverter._wchamax is None  # not cached

    async def test_oversized_wchamax_rejected(self, inverter, mock_modbus_client):
        inverter._wchamax = None
        inverter._wchamax_date = None
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([_WCHAMAX_SANITY_LIMIT + 1])
        )
        result = await inverter._read_wchamax()
        assert result is None
        assert inverter._wchamax is None

    async def test_plausible_wchamax_cached(self, inverter, mock_modbus_client):
        inverter._wchamax = None
        inverter._wchamax_date = None
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([4500])
        )
        result = await inverter._read_wchamax()
        assert result == 4500
        assert inverter._wchamax == 4500
        assert inverter._wchamax_date == date.today().isoformat()

    async def test_wchamax_cache_returns_without_io(
        self, inverter, mock_modbus_client
    ):
        """Cached WChaMax is reused on the same day — no Modbus reads issued."""
        inverter._wchamax = 4500
        inverter._wchamax_date = date.today().isoformat()
        mock_modbus_client.read_holding_registers = AsyncMock()
        result = await inverter._read_wchamax()
        assert result == 4500
        mock_modbus_client.read_holding_registers.assert_not_called()


class TestSunSpecDiscovery:
    """SunSpec model table walk from register 40000 finds Model 124."""

    async def test_discovers_model124_first_in_table(
        self, mock_hass, fronius_config, mock_modbus_client
    ):
        """Model 124 sits directly after the SunSpec ID."""
        responses = [
            _ok_response([_SUNSPEC_ID_WORD0, _SUNSPEC_ID_WORD1]),  # 40000
            _ok_response([_SUNSPEC_MODEL_124, 24]),                # 40002 header
        ]
        mock_modbus_client.read_holding_registers = AsyncMock(side_effect=responses)
        inv = FroniusInverter(mock_hass, fronius_config)
        inv._client = mock_modbus_client
        result = await inv._discover_model124()
        assert result is True
        # Data starts after 2-register header at 40002
        assert inv._model124_base == 40004

    async def test_aborts_on_invalid_sunspec_id(
        self, mock_hass, fronius_config, mock_modbus_client
    ):
        """Wrong magic ID at 40000 aborts immediately."""
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([0x0000, 0x0000])
        )
        inv = FroniusInverter(mock_hass, fronius_config)
        inv._client = mock_modbus_client
        result = await inv._discover_model124()
        assert result is False
        assert inv._model124_base is None

    async def test_aborts_on_end_marker(
        self, mock_hass, fronius_config, mock_modbus_client
    ):
        """Hitting 0xFFFF before Model 124 returns False."""
        responses = [
            _ok_response([_SUNSPEC_ID_WORD0, _SUNSPEC_ID_WORD1]),
            _ok_response([1, 50]),                          # Model 1, length 50
            _ok_response([_SUNSPEC_END_MARKER, 0]),         # end of table
        ]
        mock_modbus_client.read_holding_registers = AsyncMock(side_effect=responses)
        inv = FroniusInverter(mock_hass, fronius_config)
        inv._client = mock_modbus_client
        result = await inv._discover_model124()
        assert result is False

    async def test_iterates_past_other_models(
        self, mock_hass, fronius_config, mock_modbus_client
    ):
        """Walks past Model 1 and Model 103 to find Model 124."""
        responses = [
            _ok_response([_SUNSPEC_ID_WORD0, _SUNSPEC_ID_WORD1]),
            _ok_response([1, 65]),                          # Model 1, length 65
            _ok_response([103, 50]),                        # Model 103, length 50
            _ok_response([_SUNSPEC_MODEL_124, 24]),
        ]
        mock_modbus_client.read_holding_registers = AsyncMock(side_effect=responses)
        inv = FroniusInverter(mock_hass, fronius_config)
        inv._client = mock_modbus_client
        result = await inv._discover_model124()
        assert result is True
        # 40000 (start) + 2 (ID) + (65 + 2) (model 1+header) + (50 + 2) (model 103+header) + 2 (model 124 header)
        expected_base = 40000 + 2 + (65 + 2) + (50 + 2) + 2
        assert inv._model124_base == expected_base


class TestEnsureModel124Reconnect:
    """_ensure_model124 must reconnect when the TCP socket dropped, even if base is cached."""

    async def test_reconnects_when_disconnected_with_cached_base(
        self, inverter, monkeypatch
    ):
        """Connection check happens BEFORE the cache check.

        Otherwise a stale base address would mask a dropped socket and every
        subsequent read/write would silently fail.
        """
        import sys

        # Stale client that reports as disconnected
        stale_client = MagicMock()
        stale_client.connected = False
        stale_client.close = MagicMock()
        inverter._client = stale_client

        # Fresh client that the patched constructor returns on reconnect
        fresh_client = MagicMock()
        fresh_client.connected = False
        fresh_client.read_holding_registers = AsyncMock(
            return_value=_ok_response([0])
        )

        async def fresh_connect():
            fresh_client.connected = True
            return True

        fresh_client.connect = AsyncMock(side_effect=fresh_connect)

        # The driver re-imports pymodbus.client lazily in _ensure_connected.
        # Inject a stub module so the import succeeds without the real package.
        constructor = MagicMock(return_value=fresh_client)
        pymodbus_client_mod = MagicMock()
        pymodbus_client_mod.AsyncModbusTcpClient = constructor
        pymodbus_mod = MagicMock()
        pymodbus_mod.client = pymodbus_client_mod
        monkeypatch.setitem(sys.modules, "pymodbus", pymodbus_mod)
        monkeypatch.setitem(sys.modules, "pymodbus.client", pymodbus_client_mod)

        result = await inverter._ensure_model124()
        assert result is True
        # Stale socket released, new client built
        stale_client.close.assert_called_once()
        constructor.assert_called_with(inverter._host, port=inverter._port)
        fresh_client.connect.assert_called()
        # Cached Model 124 base preserved across the reconnect
        assert inverter._model124_base == 40070


class TestLockSerialization:
    """asyncio.Lock prevents interleaved Modbus write sequences."""

    async def test_lock_serializes_concurrent_calls(
        self, inverter, mock_modbus_client
    ):
        """Two concurrent control operations produce non-interleaved write streams."""
        import asyncio

        write_order: list[int] = []
        original_write = mock_modbus_client.write_register

        async def tracked_write(*args, **kwargs):
            # pymodbus 3.9+: address and value are passed as kwargs
            write_order.append(kwargs["address"])
            await asyncio.sleep(0)  # force a scheduler yield
            return await original_write(*args, **kwargs)

        mock_modbus_client.write_register = AsyncMock(side_effect=tracked_write)

        await asyncio.gather(
            inverter.async_set_charge_limit(0),
            inverter.async_stop_forcible(),
        )

        base = inverter._model124_base
        cl_writes = [
            base + _OFFSET_INWRTE,
            base + _OFFSET_WINTMS,
            base + _OFFSET_RVRTTMS,
            base + _OFFSET_STORCTL_MOD,
        ]
        sf_writes = [
            base + _OFFSET_STORCTL_MOD,
            base + _OFFSET_INWRTE,
            base + _OFFSET_OUTWRTE,
        ]
        # The two operations must run back-to-back, never interleaved
        assert (
            write_order == cl_writes + sf_writes
            or write_order == sf_writes + cl_writes
        ), f"Lock did not serialize writes: {write_order}"
