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
    DEFAULT_DISCHARGE_POWER_KW,
    DEFAULT_DISCHARGE_START_TIME,
    DEFAULT_MIN_SOC,
    DEFAULT_MORNING_END_TIME,
    DEFAULT_SAFETY_BUFFER_PCT,
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
        consumption_to_sunset_kwh=8.0,
        consumption_tomorrow_kwh=12.0,
        consumption_overnight_kwh=3.0,
        consumption_today_daylight_kwh=7.0,
        consumption_tomorrow_daylight_kwh=9.0,
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
            consumption_overnight_kwh=3.0,
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
            consumption_overnight_kwh=3.0,
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
            consumption_overnight_kwh=3.0,
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
            consumption_overnight_kwh=3.0,
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
            consumption_overnight_kwh=3.0,
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


# ---------------------------------------------------------------------------
# Daylight consumption (SA -> SU)
# ---------------------------------------------------------------------------

class TestDaylightConsumption:
    """Tests for daylight-only (sunrise-to-sunset) consumption fields."""

    def test_snapshot_has_daylight_fields(self):
        """Snapshot dataclass has consumption_today_daylight_kwh and consumption_tomorrow_daylight_kwh."""
        snap = _make_snapshot()
        assert hasattr(snap, "consumption_today_daylight_kwh")
        assert hasattr(snap, "consumption_tomorrow_daylight_kwh")

    def test_daylight_fields_default_to_zero(self):
        """Daylight consumption fields default to 0.0."""
        snap = Snapshot(now=datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc))
        assert snap.consumption_today_daylight_kwh == 0.0
        assert snap.consumption_tomorrow_daylight_kwh == 0.0

    def test_gather_snapshot_computes_daylight_consumption(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """_gather_snapshot() computes daylight consumption using coordinator.calculate_period(sunrise, sunset)."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)

        # Setup sun.sun entity: morning call, next_rising is today, next_setting is today
        sun_state = MagicMock()
        sun_state.attributes = {
            "next_rising": "2026-06-15T05:30:00+00:00",
            "next_setting": "2026-06-15T20:30:00+00:00",
        }
        soc_state = MagicMock()
        soc_state.state = "50"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sun.sun": sun_state,
            "sensor.battery_soc": soc_state,
        }.get(eid))

        # Return different values for different periods
        def calc_period(start, end):
            hours = (end - start).total_seconds() / 3600
            return {"verbrauch_kwh": hours * 0.5, "stunden": hours, "stundenprofil": []}

        mock_coordinator.calculate_period = MagicMock(side_effect=calc_period)

        with patch("custom_components.eeg_energy_optimizer.optimizer._now",
                    return_value=datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)):
            snap = opt._gather_snapshot()

        assert snap.consumption_today_daylight_kwh > 0.0
        assert snap.consumption_tomorrow_daylight_kwh > 0.0

    def test_sun_time_derivation_afternoon(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """When next_rising is tomorrow (afternoon call), today's sunrise is derived by subtracting 1 day."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)

        # Afternoon: next_rising is tomorrow, next_setting is today
        sun_state = MagicMock()
        sun_state.attributes = {
            "next_rising": "2026-06-16T05:30:00+00:00",  # tomorrow
            "next_setting": "2026-06-15T20:30:00+00:00",  # today
        }
        soc_state = MagicMock()
        soc_state.state = "50"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sun.sun": sun_state,
            "sensor.battery_soc": soc_state,
        }.get(eid))

        calls = []
        def calc_period(start, end):
            calls.append((start, end))
            return {"verbrauch_kwh": 5.0, "stunden": 8.0, "stundenprofil": []}
        mock_coordinator.calculate_period = MagicMock(side_effect=calc_period)

        with patch("custom_components.eeg_energy_optimizer.optimizer._now",
                    return_value=datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)):
            snap = opt._gather_snapshot()

        # Today's daylight should use today's sunrise (derived) to today's sunset
        # Find the daylight call: it should use a start time on June 15 (not 16)
        daylight_calls = [c for c in calls if c[0].date().day == 15 and c[1].hour == 20 and c[1].minute == 30]
        assert len(daylight_calls) >= 1, f"Expected daylight call for today, got: {calls}"

    def test_sun_time_derivation_after_sunset(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """After sunset, next_setting is tomorrow; today's sunset derived by subtracting 1 day."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)

        # After sunset: both next_rising and next_setting are tomorrow
        sun_state = MagicMock()
        sun_state.attributes = {
            "next_rising": "2026-06-16T05:30:00+00:00",
            "next_setting": "2026-06-16T20:30:00+00:00",
        }
        soc_state = MagicMock()
        soc_state.state = "50"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sun.sun": sun_state,
            "sensor.battery_soc": soc_state,
        }.get(eid))

        calls = []
        def calc_period(start, end):
            calls.append((start, end))
            return {"verbrauch_kwh": 5.0, "stunden": 8.0, "stundenprofil": []}
        mock_coordinator.calculate_period = MagicMock(side_effect=calc_period)

        with patch("custom_components.eeg_energy_optimizer.optimizer._now",
                    return_value=datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc)):
            snap = opt._gather_snapshot()

        # Tomorrow daylight should be computed with June 16 sunrise/sunset
        tomorrow_calls = [c for c in calls if c[0].date().day == 16 and c[1].date().day == 16]
        assert len(tomorrow_calls) >= 1, f"Expected tomorrow daylight call, got: {calls}"

    def test_tomorrow_sunrise_sunset_shifted_by_one_day(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Tomorrow's sunrise/sunset approximated by shifting today's values by +1 day."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)

        sun_state = MagicMock()
        sun_state.attributes = {
            "next_rising": "2026-06-15T05:30:00+00:00",
            "next_setting": "2026-06-15T20:30:00+00:00",
        }
        soc_state = MagicMock()
        soc_state.state = "50"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sun.sun": sun_state,
            "sensor.battery_soc": soc_state,
        }.get(eid))

        calls = []
        def calc_period(start, end):
            calls.append((start, end))
            return {"verbrauch_kwh": 5.0, "stunden": 8.0, "stundenprofil": []}
        mock_coordinator.calculate_period = MagicMock(side_effect=calc_period)

        with patch("custom_components.eeg_energy_optimizer.optimizer._now",
                    return_value=datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)):
            snap = opt._gather_snapshot()

        # Find tomorrow daylight call: should use June 16 05:30 -> June 16 20:30
        tomorrow_daylight = [c for c in calls
                             if c[0].date().day == 16
                             and c[0].hour == 5 and c[0].minute == 30
                             and c[1].hour == 20 and c[1].minute == 30]
        assert len(tomorrow_daylight) == 1, f"Expected tomorrow daylight call, got: {calls}"

    def test_energiebedarf_uses_daylight_consumption(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """_calc_energiebedarf() uses consumption_today_daylight_kwh instead of consumption_to_sunset_kwh."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            consumption_today_daylight_kwh=6.0,
            consumption_to_sunset_kwh=8.0,  # should NOT be used
            battery_soc=50.0,
            battery_capacity_kwh=10.0,
        )
        bedarf = opt._calc_energiebedarf(snap)
        # Expected: 6.0 (daylight) + 5.0 (missing battery: 50% of 10kWh) = 11.0
        assert bedarf == pytest.approx(11.0)

    def test_morning_delay_outside_window_uses_daylight_tomorrow(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """_morning_delay_status() outside-window uses consumption_tomorrow_daylight_kwh."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),  # after morning window
            consumption_tomorrow_kwh=20.0,  # full-day (should NOT be used)
            consumption_tomorrow_daylight_kwh=12.0,  # daylight only (SHOULD be used)
            battery_capacity_kwh=10.0,
            pv_tomorrow_kwh=50.0,
        )
        bedarf = opt._calc_energiebedarf(snap)
        result = opt._morning_delay_status(snap, bedarf)
        # Tomorrow demand should be based on daylight consumption (12.0), not full-day (20.0)
        # missing_battery = (100 - 10) / 100 * 10 = 9.0 (min_soc=10 default)
        # tomorrow_threshold = (12.0 + 9.0) * 1.25 = 26.25
        assert result["threshold_kwh"] == pytest.approx((12.0 + 9.0) * 1.25)

    def test_discharge_still_uses_full_day_consumption(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """_should_discharge() still uses snap.consumption_tomorrow_kwh (not daylight)."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            consumption_tomorrow_kwh=12.0,
            consumption_tomorrow_daylight_kwh=8.0,
            pv_tomorrow_kwh=40.0,
            consumption_overnight_kwh=3.0,
        )
        should, min_soc, reasons = opt._should_discharge(snap)
        assert should is True  # uses full-day 12.0 not daylight 8.0

    def test_discharge_detail_still_uses_full_day(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """_discharge_detail_status() uses consumption_tomorrow_kwh (unchanged)."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            consumption_tomorrow_kwh=12.0,
            consumption_tomorrow_daylight_kwh=8.0,
            pv_tomorrow_kwh=40.0,
        )
        result = opt._discharge_detail_status(snap, True, 48.0, [])
        # demand uses full-day: 12.0 + (90% * 10) = 12.0 + 9.0 = 21.0
        assert result["demand_tomorrow_kwh"] == pytest.approx(21.0)

    def test_daylight_fields_zero_when_sunrise_sunset_none(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """When sunrise/sunset is None, daylight consumption fields remain 0.0."""
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)

        sun_state = None  # no sun entity
        soc_state = MagicMock()
        soc_state.state = "50"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sensor.battery_soc": soc_state,
        }.get(eid))

        mock_coordinator.calculate_period = MagicMock(
            return_value={"verbrauch_kwh": 5.0, "stunden": 8.0, "stundenprofil": []}
        )

        with patch("custom_components.eeg_energy_optimizer.optimizer._now",
                    return_value=datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)):
            snap = opt._gather_snapshot()

        assert snap.consumption_today_daylight_kwh == 0.0
        assert snap.consumption_tomorrow_daylight_kwh == 0.0
