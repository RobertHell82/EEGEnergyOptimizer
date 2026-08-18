"""Tests for the SMA inverter implementation (CmpBMS 6-parameter Modbus).

Focus areas mirror the driver's architecture decisions:
  - U32/S32 big-endian encoding (SMA standard word order)
  - Complete-block semantics: every command writes OpMod + the contiguous
    power block 40793–40802 in exactly two FC16 calls
  - Register semantics: BatChaMaxW=0 blocks charging, GridWSpt positive =
    forced export, neutral block on stop
  - Watchdog keepalive: active block survives and is rewritten
  - Flash-wear guard: no write address outside the CmpBMS set
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.sma import (
    DEFAULT_POWER_LIMIT_W,
    KEEPALIVE_INTERVAL,
    OPMOD_DEFAULT,
    REG_BAT_CHA_MIN_W,
    REG_CMPBMS_OPMOD,
    SMA_UNIT_ID,
    SMAInverter,
    CmpBmsBlock,
    registers_to_s32,
    registers_to_u32,
    s32_to_registers,
    u32_to_registers,
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
def sma_config():
    return {
        "sma_modbus_host": "192.168.1.60",
        "sma_modbus_port": 502,
    }


@pytest.fixture
def mock_modbus_client():
    """Mocked AsyncModbusTcpClient with success responses by default."""
    client = MagicMock()
    client.connected = True
    client.write_registers = AsyncMock(return_value=_ok_response())
    client.read_holding_registers = AsyncMock(
        return_value=_ok_response(u32_to_registers(0))
    )
    client.connect = AsyncMock(return_value=True)
    client.close = MagicMock()
    return client


@pytest.fixture
def inverter(mock_hass, sma_config, mock_modbus_client):
    inv = SMAInverter(mock_hass, sma_config)
    inv._client = mock_modbus_client
    return inv


def _writes(client):
    """Return list of (address, values) tuples for all register writes."""
    return [
        (c.kwargs.get("address"), c.kwargs.get("values"))
        for c in client.write_registers.await_args_list
    ]


def _last_block(client):
    """Decode the last complete CmpBMS block written to the client."""
    opmod = None
    power = None
    for address, values in _writes(client):
        if address == REG_CMPBMS_OPMOD:
            opmod = registers_to_u32(values)
        elif address == REG_BAT_CHA_MIN_W:
            power = values
    assert opmod is not None and power is not None
    assert len(power) == 10
    return CmpBmsBlock(
        op_mod=opmod,
        cha_min_w=registers_to_u32(power[0:2]),
        cha_max_w=registers_to_u32(power[2:4]),
        dsch_min_w=registers_to_u32(power[4:6]),
        dsch_max_w=registers_to_u32(power[6:8]),
        grid_w_spt=registers_to_s32(power[8:10]),
    )


class TestSMAInverterBase:
    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(SMAInverter, InverterBase)


class TestConfigParsing:
    def test_host_from_config(self, mock_hass):
        inv = SMAInverter(mock_hass, {"sma_modbus_host": "10.0.0.9"})
        assert inv._host == "10.0.0.9"

    def test_default_port_is_502(self, mock_hass):
        inv = SMAInverter(mock_hass, {})
        assert inv._port == 502

    def test_custom_port(self, mock_hass):
        inv = SMAInverter(mock_hass, {"sma_modbus_port": 1502})
        assert inv._port == 1502

    def test_unit_id_is_3(self, mock_hass):
        inv = SMAInverter(mock_hass, {})
        assert inv._slave_id == SMA_UNIT_ID == 3

    def test_available_iff_host_configured(self, mock_hass):
        assert SMAInverter(mock_hass, {"sma_modbus_host": "x"}).is_available
        assert not SMAInverter(mock_hass, {}).is_available


class TestEncoding:
    """SMA standard: big-endian word order (high word first)."""

    def test_u32_encoding(self):
        # 2424 = 0x00000978 → high word 0x0000, low word 0x0978
        assert u32_to_registers(2424) == [0x0000, 0x0978]

    def test_u32_high_word(self):
        assert u32_to_registers(0x00010000) == [0x0001, 0x0000]

    def test_u32_roundtrip(self):
        for value in (0, 1, 2424, 10000, 0xFFFFFFFF):
            assert registers_to_u32(u32_to_registers(value)) == value

    def test_s32_positive_roundtrip(self):
        assert registers_to_s32(s32_to_registers(5000)) == 5000

    def test_s32_negative_roundtrip(self):
        assert registers_to_s32(s32_to_registers(-5000)) == -5000

    def test_s32_negative_two_complement(self):
        # -1 = 0xFFFFFFFF
        assert s32_to_registers(-1) == [0xFFFF, 0xFFFF]


class TestBlockComposition:
    """Every command must write the COMPLETE 6-parameter block: OpMod via
    one FC16, then 40793–40802 as ONE contiguous 10-register FC16 write
    (SMA requires all 6 within 10 s)."""

    async def test_two_writes_per_command(self, inverter, mock_modbus_client):
        await inverter.async_set_charge_limit(0)
        writes = _writes(mock_modbus_client)
        assert len(writes) == 2
        assert writes[0][0] == REG_CMPBMS_OPMOD
        assert writes[1][0] == REG_BAT_CHA_MIN_W
        assert len(writes[1][1]) == 10

    async def test_no_write_outside_cmpbms_set(
        self, inverter, mock_modbus_client
    ):
        """Flash-wear guard: only 40236 and the 40793-block are written."""
        await inverter.async_set_charge_limit(0)
        await inverter.async_set_discharge(3.0)
        await inverter.async_stop_forcible()
        for address, _values in _writes(mock_modbus_client):
            assert address in (REG_CMPBMS_OPMOD, REG_BAT_CHA_MIN_W)

    async def test_uses_unit_id_3(self, inverter, mock_modbus_client):
        await inverter.async_set_charge_limit(0)
        for c in mock_modbus_client.write_registers.await_args_list:
            slave = c.kwargs.get("slave", c.kwargs.get("device_id"))
            assert slave == SMA_UNIT_ID


class TestChargeLimit:
    async def test_block_charging(self, inverter, mock_modbus_client):
        """power_kw=0 → BatChaMaxW=0, discharge stays available, no export."""
        ok = await inverter.async_set_charge_limit(0)
        assert ok is True
        block = _last_block(mock_modbus_client)
        assert block.op_mod == OPMOD_DEFAULT
        assert block.cha_max_w == 0
        assert block.dsch_max_w == DEFAULT_POWER_LIMIT_W
        assert block.grid_w_spt == 0

    async def test_partial_charge_limit(self, inverter, mock_modbus_client):
        """power_kw=2.5 → BatChaMaxW=2500 (Einspeisebegrenzung)."""
        ok = await inverter.async_set_charge_limit(2.5)
        assert ok is True
        block = _last_block(mock_modbus_client)
        assert block.cha_max_w == 2500
        assert block.grid_w_spt == 0

    async def test_sets_active_and_keepalive(self, inverter):
        await inverter.async_set_charge_limit(0)
        assert inverter._active is not None
        assert inverter._keepalive_task is not None
        inverter._cancel_keepalive()

    async def test_write_error_returns_false(
        self, inverter, mock_modbus_client
    ):
        mock_modbus_client.write_registers = AsyncMock(
            return_value=_err_response()
        )
        ok = await inverter.async_set_charge_limit(0)
        assert ok is False
        assert inverter._active is None


class TestDischarge:
    async def test_grid_setpoint_positive_export(
        self, inverter, mock_modbus_client
    ):
        """Discharge 3 kW → GridWSpt=+3000 (positive = export), charging
        blocked, discharge limit open."""
        ok = await inverter.async_set_discharge(3.0)
        assert ok is True
        block = _last_block(mock_modbus_client)
        assert block.op_mod == OPMOD_DEFAULT
        assert block.grid_w_spt == 3000
        assert block.cha_max_w == 0
        assert block.dsch_max_w == DEFAULT_POWER_LIMIT_W

    async def test_target_soc_accepted_but_ignored(
        self, inverter, mock_modbus_client
    ):
        """SMA has no hardware target-SOC — the optimizer supervises."""
        ok = await inverter.async_set_discharge(2.0, target_soc=30)
        assert ok is True
        block = _last_block(mock_modbus_client)
        assert block.grid_w_spt == 2000

    async def test_negative_power_clamped_to_zero(
        self, inverter, mock_modbus_client
    ):
        await inverter.async_set_discharge(-5.0)
        block = _last_block(mock_modbus_client)
        assert block.grid_w_spt == 0

    async def test_sets_active_and_keepalive(self, inverter):
        await inverter.async_set_discharge(3.0)
        assert inverter._active is not None
        inverter._cancel_keepalive()


class TestStopForcible:
    async def test_writes_neutral_block(self, inverter, mock_modbus_client):
        """Stop → default mode, full limits both directions, setpoint 0."""
        await inverter.async_set_discharge(3.0)
        ok = await inverter.async_stop_forcible()
        assert ok is True
        block = _last_block(mock_modbus_client)
        assert block.op_mod == OPMOD_DEFAULT
        assert block.cha_max_w == DEFAULT_POWER_LIMIT_W
        assert block.dsch_max_w == DEFAULT_POWER_LIMIT_W
        assert block.grid_w_spt == 0

    async def test_clears_active_and_keepalive(self, inverter):
        await inverter.async_set_discharge(3.0)
        await inverter.async_stop_forcible()
        assert inverter._active is None
        assert inverter._keepalive_task is None

    async def test_active_cleared_even_on_write_failure(
        self, inverter, mock_modbus_client
    ):
        """The active block is cleared BEFORE the write so a failed stop
        can never race a keepalive rewrite of the stale block."""
        await inverter.async_set_discharge(3.0)
        mock_modbus_client.write_registers = AsyncMock(
            return_value=_err_response()
        )
        ok = await inverter.async_stop_forcible()
        assert ok is False
        assert inverter._active is None


class TestKeepalive:
    async def test_keepalive_rewrites_active_block(
        self, inverter, mock_modbus_client, monkeypatch
    ):
        """The keepalive loop rewrites the active block after the interval."""
        monkeypatch.setattr(
            "custom_components.eeg_energy_optimizer.inverter.sma."
            "KEEPALIVE_INTERVAL",
            0.01,
        )
        await inverter.async_set_discharge(3.0)
        writes_before = len(_writes(mock_modbus_client))
        await asyncio.sleep(0.1)
        inverter._cancel_keepalive()
        writes_after = len(_writes(mock_modbus_client))
        assert writes_after > writes_before
        # Rewrites are the identical discharge block
        block = _last_block(mock_modbus_client)
        assert block.grid_w_spt == 3000

    async def test_keepalive_stops_when_inactive(
        self, inverter, monkeypatch
    ):
        monkeypatch.setattr(
            "custom_components.eeg_energy_optimizer.inverter.sma."
            "KEEPALIVE_INTERVAL",
            0.01,
        )
        await inverter.async_set_discharge(3.0)
        inverter._active = None
        await asyncio.sleep(0.05)
        assert (
            inverter._keepalive_task is None
            or inverter._keepalive_task.done()
        )

    def test_keepalive_interval_within_watchdog(self):
        """SMA requires a refresh at least every 300 s."""
        assert KEEPALIVE_INTERVAL < 300


class TestDisconnect:
    async def test_disconnect_cleans_up(self, inverter, mock_modbus_client):
        await inverter.async_set_discharge(3.0)
        await inverter.async_disconnect()
        assert inverter._active is None
        assert inverter._client is None
        mock_modbus_client.close.assert_called()


class TestRegisterWriteCounter:
    async def test_counts_two_writes_per_block(self, inverter):
        assert inverter.register_writes == 0
        await inverter.async_set_charge_limit(0)
        assert inverter.register_writes == 2
        inverter._cancel_keepalive()
