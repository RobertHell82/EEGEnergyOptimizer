"""Tests for EEG Energy Optimizer decision engine."""

import math
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_DISCHARGE_POWER_KW,
    CONF_DISCHARGE_START_TIME,
    CONF_MIN_SOC,
    CONF_MORNING_END_TIME,
    CONF_SAFETY_BUFFER_PCT,
    CONF_UEBERSCHUSS_SCHWELLE,
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_SAFETY_BUFFER_PCT,
    DEFAULT_UEBERSCHUSS_SCHWELLE,
    MODE_AUS,
    MODE_EIN,
    MODE_TEST,
    STATE_ABEND_ENTLADUNG,
    STATE_MORGEN_EINSPEISUNG,
    STATE_NORMAL,
)
from custom_components.eeg_energy_optimizer.optimizer import (
    Decision,
    EEGOptimizer,
    Snapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides):
    """Create a minimal optimizer config dict."""
    base = {
        CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
        CONF_BATTERY_CAPACITY_SENSOR: "",
        CONF_BATTERY_CAPACITY_KWH: 10.0,
    }
    base.update(overrides)
    return base


def _make_snapshot(**overrides):
    """Create a Snapshot with sensible defaults for testing."""
    now = overrides.pop("now", datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc))
    defaults = dict(
        now=now,
        battery_soc=50.0,
        battery_capacity_kwh=10.0,
        pv_remaining_today_kwh=20.0,
        pv_tomorrow_kwh=25.0,
        consumption_today_kwh=10.0,
        consumption_tomorrow_kwh=12.0,
        consumption_to_sunrise_kwh=3.0,
        sunrise=now.replace(hour=5, minute=30),
        sunset=now.replace(hour=20, minute=30),
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider, config=None):
    """Create an EEGOptimizer instance with mocks."""
    cfg = config or _make_config()
    return EEGOptimizer(mock_hass, cfg, mock_inverter, mock_coordinator, mock_provider)


# ---------------------------------------------------------------------------
# _calc_ueberschuss_faktor
# ---------------------------------------------------------------------------

class TestUeberschussFaktor:
    def test_normal_calculation(self, mock_hass, mock_inverter, mock_coordinator, mock_provider):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(pv_remaining_today_kwh=25.0, consumption_today_kwh=10.0)
        assert opt._calc_ueberschuss_faktor(snap) == pytest.approx(2.5)

    def test_returns_zero_when_pv_none(self, mock_hass, mock_inverter, mock_coordinator, mock_provider):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(pv_remaining_today_kwh=None, consumption_today_kwh=10.0)
        assert opt._calc_ueberschuss_faktor(snap) == 0.0

    def test_returns_zero_when_pv_zero(self, mock_hass, mock_inverter, mock_coordinator, mock_provider):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(pv_remaining_today_kwh=0.0, consumption_today_kwh=10.0)
        assert opt._calc_ueberschuss_faktor(snap) == 0.0

    def test_returns_99_when_consumption_zero(self, mock_hass, mock_inverter, mock_coordinator, mock_provider):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(pv_remaining_today_kwh=20.0, consumption_today_kwh=0.0)
        assert opt._calc_ueberschuss_faktor(snap) == 99.0


# ---------------------------------------------------------------------------
# _should_block_charging
# ---------------------------------------------------------------------------

class TestShouldBlockCharging:
    def test_morning_block_active_during_window_on_surplus_day(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        # 5:00 is 30 min before sunrise but within sunrise-1h window
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 5, 0, tzinfo=timezone.utc),
            sunrise=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,  # factor = 2.0 >= 1.25
        )
        assert opt._should_block_charging(snap) is True

    def test_morning_block_false_when_factor_below_threshold(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """D-03: Non-surplus day should not block."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc),
            sunrise=sunrise,
            pv_remaining_today_kwh=5.0,
            consumption_today_kwh=10.0,  # factor = 0.5 < 1.25
        )
        assert opt._should_block_charging(snap) is False

    def test_morning_block_false_after_end_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """D-04: After morning_end_time, no blocking."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc),  # after 10:00
            sunrise=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,  # factor = 2.0
        )
        assert opt._should_block_charging(snap) is False

    def test_morning_block_false_before_window(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Before sunrise - 1h, should not block."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 3, 0, tzinfo=timezone.utc),  # before 4:30
            sunrise=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,
        )
        assert opt._should_block_charging(snap) is False

    def test_morning_block_false_when_sunrise_none(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(sunrise=None)
        assert opt._should_block_charging(snap) is False


# ---------------------------------------------------------------------------
# _calc_min_soc
# ---------------------------------------------------------------------------

class TestCalcMinSoc:
    def test_min_soc_calculation(self, mock_hass, mock_inverter, mock_coordinator, mock_provider):
        """base=10, overnight=3.0, buffer=25%, capacity=10 -> 10 + ceil(3.75/10*100) = 10+38 = 48."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            consumption_to_sunrise_kwh=3.0,
            battery_capacity_kwh=10.0,
        )
        result = opt._calc_min_soc(snap)
        expected = 10 + math.ceil((3.0 * 1.25) / 10.0 * 100)
        assert result == expected  # 48

    def test_min_soc_returns_base_when_capacity_zero(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(battery_capacity_kwh=0.0)
        assert opt._calc_min_soc(snap) == DEFAULT_MIN_SOC


# ---------------------------------------------------------------------------
# _should_discharge
# ---------------------------------------------------------------------------

class TestShouldDischarge:
    def test_discharge_active_when_conditions_met(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        # Evening time, high SOC, tomorrow is surplus
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            pv_tomorrow_kwh=40.0,
            consumption_tomorrow_kwh=12.0,
            consumption_to_sunrise_kwh=3.0,
        )
        should, min_soc, reasons = opt._should_discharge(snap)
        assert should is True
        assert len(reasons) == 0

    def test_discharge_false_when_soc_below_min(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=5.0,  # very low SOC
            battery_capacity_kwh=10.0,
            pv_tomorrow_kwh=40.0,
            consumption_tomorrow_kwh=12.0,
            consumption_to_sunrise_kwh=3.0,
        )
        should, min_soc, reasons = opt._should_discharge(snap)
        assert should is False
        assert any("SOC" in r for r in reasons)

    def test_discharge_false_when_tomorrow_not_surplus(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """SAF-03: Next-day check prevents discharge when pv_tomorrow < demand."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            pv_tomorrow_kwh=5.0,  # Low PV tomorrow
            consumption_tomorrow_kwh=12.0,
            consumption_to_sunrise_kwh=3.0,
        )
        should, min_soc, reasons = opt._should_discharge(snap)
        assert should is False
        assert any("morgen" in r.lower() or "prognose" in r.lower() for r in reasons)

    def test_discharge_false_before_start_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),  # before 20:00
            battery_soc=80.0,
            pv_tomorrow_kwh=40.0,
            consumption_tomorrow_kwh=12.0,
        )
        should, min_soc, reasons = opt._should_discharge(snap)
        assert should is False
        assert any("zeit" in r.lower() or "uhrzeit" in r.lower() or "start" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# async_run_cycle integration tests
# ---------------------------------------------------------------------------

class TestAsyncRunCycle:
    @pytest.mark.asyncio
    async def test_ein_mode_morning_block_calls_charge_limit(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Mode Ein during morning block: should call async_set_charge_limit(0)."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc),
            sunrise=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,
        )
        with patch.object(opt, "_gather_snapshot", return_value=snap):
            decision = await opt.async_run_cycle(MODE_EIN)
        assert decision.ladung_blockiert is True
        assert decision.zustand == STATE_MORGEN_EINSPEISUNG
        mock_inverter.async_set_charge_limit.assert_called_once_with(0)

    @pytest.mark.asyncio
    async def test_ein_mode_evening_discharge_calls_set_discharge(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Mode Ein during evening discharge: should call async_set_discharge."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            pv_tomorrow_kwh=40.0,
            consumption_tomorrow_kwh=12.0,
            consumption_to_sunrise_kwh=3.0,
            sunrise=datetime(2026, 6, 16, 5, 30, tzinfo=timezone.utc),
            sunset=datetime(2026, 6, 15, 20, 30, tzinfo=timezone.utc),
        )
        with patch.object(opt, "_gather_snapshot", return_value=snap):
            decision = await opt.async_run_cycle(MODE_EIN)
        assert decision.entladung_aktiv is True
        assert decision.zustand == STATE_ABEND_ENTLADUNG
        mock_inverter.async_set_discharge.assert_called_once()

    @pytest.mark.asyncio
    async def test_ein_mode_normal_calls_stop_forcible(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Mode Ein during Normal state: should call async_stop_forcible."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),  # midday
            sunrise=datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc),
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,  # surplus but after morning window
        )
        with patch.object(opt, "_gather_snapshot", return_value=snap):
            decision = await opt.async_run_cycle(MODE_EIN)
        assert decision.zustand == STATE_NORMAL
        mock_inverter.async_stop_forcible.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_mode_no_inverter_calls(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """SAF-04: Test mode must NOT call any inverter methods."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc),
            sunrise=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,
        )
        with patch.object(opt, "_gather_snapshot", return_value=snap):
            decision = await opt.async_run_cycle(MODE_TEST)
        assert decision.ausfuehrung is False
        mock_inverter.async_set_charge_limit.assert_not_called()
        mock_inverter.async_set_discharge.assert_not_called()
        mock_inverter.async_stop_forcible.assert_not_called()

    @pytest.mark.asyncio
    async def test_inverter_deduplication(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Same state twice should not call inverter a second time."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
            sunrise=datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc),
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,
        )
        with patch.object(opt, "_gather_snapshot", return_value=snap):
            await opt.async_run_cycle(MODE_EIN)
            await opt.async_run_cycle(MODE_EIN)
        # stop_forcible should only be called once (deduplication)
        assert mock_inverter.async_stop_forcible.call_count == 1
