"""Tests for Kostal Plenticore inverter implementation (proprietary Modbus TCP).

Focus areas mirror the driver's architecture decisions:
  - Float32 word-swap encoding (CDAB, Kostal factory default)
  - Register semantics: 1034 setpoint (positive = discharge), 1038 charge limit
  - Watchdog keepalive: active command survives, rewrites with ±1 W jitter
  - Stuck-register guards on mode switches and stop
  - Snapshot/restore of the pre-block max charge power
"""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.inverter.base import InverterBase
from custom_components.eeg_energy_optimizer.inverter.kostal import (
    KEEPALIVE_INTERVAL,
    KOSTAL_UNIT_ID,
    KostalInverter,
    REG_BATTERY_SETPOINT,
    REG_MAX_CHARGE_POWER,
    float_to_registers,
    registers_to_float,
    registers_to_string,
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
def kostal_config():
    return {
        "kostal_modbus_host": "192.168.1.50",
        "kostal_modbus_port": 1502,
    }


@pytest.fixture
def mock_modbus_client():
    """Mocked AsyncModbusTcpClient with success responses by default."""
    client = MagicMock()
    client.connected = True
    client.write_registers = AsyncMock(return_value=_ok_response())
    # Default read: 0.0 as word-swapped float (harmless for snapshot logic)
    client.read_holding_registers = AsyncMock(
        return_value=_ok_response(float_to_registers(0.0))
    )
    client.connect = AsyncMock(return_value=True)
    client.close = MagicMock()
    return client


@pytest.fixture
def inverter(mock_hass, kostal_config, mock_modbus_client):
    inv = KostalInverter(mock_hass, kostal_config)
    inv._client = mock_modbus_client
    return inv


def _written(client, address):
    """Return the list of register-value lists written to `address`."""
    calls = []
    for call in client.write_registers.await_args_list:
        kwargs = call.kwargs
        if kwargs.get("address") == address:
            calls.append(kwargs.get("values"))
    return calls


class TestKostalInverterBase:
    def test_is_instance_of_inverter_base(self, inverter):
        assert isinstance(inverter, InverterBase)

    def test_is_subclass_of_inverter_base(self):
        assert issubclass(KostalInverter, InverterBase)


class TestConfigParsing:
    def test_host_from_config(self, mock_hass):
        inv = KostalInverter(mock_hass, {"kostal_modbus_host": "10.0.0.7"})
        assert inv._host == "10.0.0.7"

    def test_default_port_is_1502(self, mock_hass):
        inv = KostalInverter(mock_hass, {})
        assert inv._port == 1502

    def test_custom_port(self, mock_hass):
        inv = KostalInverter(mock_hass, {"kostal_modbus_port": 502})
        assert inv._port == 502

    def test_unit_id_is_71(self, mock_hass):
        inv = KostalInverter(mock_hass, {})
        assert inv._slave_id == KOSTAL_UNIT_ID == 71

    def test_available_iff_host_configured(self, mock_hass):
        assert KostalInverter(mock_hass, {"kostal_modbus_host": "x"}).is_available
        assert not KostalInverter(mock_hass, {}).is_available


class TestFloatEncoding:
    """Kostal factory default: Float32 with word swap (CDAB).

    IEEE754 1.0 = 0x3F800000 (words AB=0x3F80, CD=0x0000) → low word first.
    """

    def test_one_point_zero(self):
        assert float_to_registers(1.0) == [0x0000, 0x3F80]

    def test_zero(self):
        assert float_to_registers(0.0) == [0x0000, 0x0000]

    def test_roundtrip(self):
        for value in (0.0, 1.0, -1.0, 3000.0, 16600.0, 0.5, -2750.25):
            regs = float_to_registers(value)
            assert registers_to_float(regs) == pytest.approx(value, rel=1e-6)

    def test_matches_struct_reference(self):
        # Reference encoding: pack big-endian, swap 16-bit words
        value = 5500.0
        raw = struct.pack(">f", value)
        expected = [
            (raw[2] << 8) | raw[3],
            (raw[0] << 8) | raw[1],
        ]
        assert float_to_registers(value) == expected

    def test_string_decoding(self):
        # "PLENTICORE" as 2 chars per register, null-terminated
        text = "PLENTICORE plus 5.5"
        padded = text + "\x00" * (32 - len(text))
        regs = [
            (ord(padded[i]) << 8) | ord(padded[i + 1])
            for i in range(0, 32, 2)
        ]
        assert registers_to_string(regs) == text


class TestChargeLimit:
    async def test_block_charging_writes_zero_to_1038(self, inverter, mock_modbus_client):
        ok = await inverter.async_set_charge_limit(0)
        assert ok is True
        writes = _written(mock_modbus_client, REG_MAX_CHARGE_POWER)
        assert writes == [float_to_registers(0.0)]
        assert inverter._active == ("charge_limit", 0.0)
        await inverter.async_disconnect()

    async def test_partial_limit_writes_watts(self, inverter, mock_modbus_client):
        ok = await inverter.async_set_charge_limit(2.5)
        assert ok is True
        writes = _written(mock_modbus_client, REG_MAX_CHARGE_POWER)
        assert writes == [float_to_registers(2500.0)]
        await inverter.async_disconnect()

    async def test_snapshots_previous_max_charge_power(self, inverter, mock_modbus_client):
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response(float_to_registers(5600.0))
        )
        await inverter.async_set_charge_limit(0)
        assert inverter._max_charge_pre_block == pytest.approx(5600.0)
        await inverter.async_disconnect()

    async def test_write_failure_returns_false(self, inverter, mock_modbus_client):
        mock_modbus_client.write_registers = AsyncMock(return_value=_err_response())
        ok = await inverter.async_set_charge_limit(0)
        assert ok is False
        assert inverter._active is None
        await inverter.async_disconnect()

    async def test_starts_keepalive_task(self, inverter):
        await inverter.async_set_charge_limit(0)
        assert inverter._keepalive_task is not None
        assert not inverter._keepalive_task.done()
        await inverter.async_disconnect()


class TestDischarge:
    async def test_discharge_writes_positive_setpoint(self, inverter, mock_modbus_client):
        ok = await inverter.async_set_discharge(3.0, target_soc=25.0)
        assert ok is True
        writes = _written(mock_modbus_client, REG_BATTERY_SETPOINT)
        # Positive value = discharge (Kostal convention)
        assert writes == [float_to_registers(3000.0)]
        assert inverter._active == ("discharge", 3000.0)
        await inverter.async_disconnect()

    async def test_target_soc_accepted_but_not_written(self, inverter, mock_modbus_client):
        """Kostal has no hardware target-SOC register — optimizer supervises."""
        await inverter.async_set_discharge(2.0, target_soc=30.0)
        for call in mock_modbus_client.write_registers.await_args_list:
            assert call.kwargs.get("address") in (
                REG_BATTERY_SETPOINT, REG_MAX_CHARGE_POWER,
            )
        await inverter.async_disconnect()

    async def test_write_failure_returns_false(self, inverter, mock_modbus_client):
        mock_modbus_client.write_registers = AsyncMock(return_value=_err_response())
        ok = await inverter.async_set_discharge(3.0)
        assert ok is False
        assert inverter._active is None
        await inverter.async_disconnect()


class TestModeSwitch:
    async def test_discharge_to_charge_limit_zeroes_setpoint(self, inverter, mock_modbus_client):
        """Stuck-register guard: old discharge setpoint is explicitly reset."""
        await inverter.async_set_discharge(3.0)
        mock_modbus_client.write_registers.reset_mock()

        await inverter.async_set_charge_limit(0)
        setpoint_writes = _written(mock_modbus_client, REG_BATTERY_SETPOINT)
        assert setpoint_writes == [float_to_registers(0.0)]
        assert inverter._active == ("charge_limit", 0.0)
        await inverter.async_disconnect()

    async def test_charge_limit_to_discharge_restores_snapshot(self, inverter, mock_modbus_client):
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response(float_to_registers(4000.0))
        )
        await inverter.async_set_charge_limit(0)
        mock_modbus_client.write_registers.reset_mock()

        await inverter.async_set_discharge(2.0)
        restore_writes = _written(mock_modbus_client, REG_MAX_CHARGE_POWER)
        assert restore_writes == [float_to_registers(4000.0)]
        assert inverter._max_charge_pre_block is None
        await inverter.async_disconnect()


class TestStopForcible:
    async def test_stop_zeroes_setpoint_and_cancels_keepalive(self, inverter, mock_modbus_client):
        await inverter.async_set_discharge(3.0)
        task = inverter._keepalive_task
        mock_modbus_client.write_registers.reset_mock()

        ok = await inverter.async_stop_forcible()
        assert ok is True
        assert inverter._active is None
        assert inverter._keepalive_task is None
        # give the cancelled task a tick to unwind
        await asyncio.sleep(0)
        assert task.cancelled() or task.done()
        setpoint_writes = _written(mock_modbus_client, REG_BATTERY_SETPOINT)
        assert setpoint_writes == [float_to_registers(0.0)]

    async def test_stop_restores_max_charge_power(self, inverter, mock_modbus_client):
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response(float_to_registers(6300.0))
        )
        await inverter.async_set_charge_limit(0)
        mock_modbus_client.write_registers.reset_mock()

        ok = await inverter.async_stop_forcible()
        assert ok is True
        restore_writes = _written(mock_modbus_client, REG_MAX_CHARGE_POWER)
        assert restore_writes == [float_to_registers(6300.0)]
        assert inverter._max_charge_pre_block is None

    async def test_stop_returns_false_when_restore_fails(self, inverter, mock_modbus_client):
        mock_modbus_client.read_holding_registers = AsyncMock(
            return_value=_ok_response(float_to_registers(6300.0))
        )
        await inverter.async_set_charge_limit(0)

        # Setpoint write succeeds, restore write fails → False so the
        # optimizer retries next cycle.
        async def _write(address, values, **kwargs):
            if address == REG_MAX_CHARGE_POWER:
                return _err_response()
            return _ok_response()

        mock_modbus_client.write_registers = AsyncMock(side_effect=_write)
        ok = await inverter.async_stop_forcible()
        assert ok is False
        assert inverter._max_charge_pre_block == pytest.approx(6300.0)

    async def test_stop_without_active_command_is_safe(self, inverter):
        ok = await inverter.async_stop_forcible()
        assert ok is True


class TestKeepalive:
    async def test_keepalive_rewrites_with_jitter(self, inverter, mock_modbus_client, monkeypatch):
        """The keepalive rewrites the active setpoint, alternating ±1 W."""
        monkeypatch.setattr(
            "custom_components.eeg_energy_optimizer.inverter.kostal.KEEPALIVE_INTERVAL",
            0.01,
        )
        await inverter.async_set_discharge(3.0)
        mock_modbus_client.write_registers.reset_mock()

        # allow several keepalive cycles (each write itself sleeps 200 ms)
        await asyncio.sleep(0.9)
        await inverter.async_disconnect()

        writes = _written(mock_modbus_client, REG_BATTERY_SETPOINT)
        assert len(writes) >= 2
        values = {round(registers_to_float(w)) for w in writes}
        # Alternates between 3000 and 3001 (±1 W jitter)
        assert values <= {3000, 3001}
        assert len(values) == 2

    async def test_keepalive_stops_after_stop_forcible(self, inverter, mock_modbus_client, monkeypatch):
        monkeypatch.setattr(
            "custom_components.eeg_energy_optimizer.inverter.kostal.KEEPALIVE_INTERVAL",
            0.01,
        )
        await inverter.async_set_discharge(3.0)
        await inverter.async_stop_forcible()
        mock_modbus_client.write_registers.reset_mock()

        await asyncio.sleep(0.1)
        assert mock_modbus_client.write_registers.await_count == 0

    def test_default_interval_feeds_60s_watchdog(self):
        # Recommended watchdog timeout is 60 s; evcc rewrites at timeout/2.
        # Our interval must stay safely below that even if one write is lost.
        assert KEEPALIVE_INTERVAL <= 30.0
