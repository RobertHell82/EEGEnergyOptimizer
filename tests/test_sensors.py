"""Tests for EEG Energy Optimizer sensor platform."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_SOURCE,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_LOOKBACK_WEEKS,
    CONF_UPDATE_INTERVAL_FAST,
    CONF_UPDATE_INTERVAL_SLOW,
    DOMAIN,
    FORECAST_SOURCE_SOLCAST,
    WEEKDAY_KEYS,
)
from custom_components.eeg_energy_optimizer.forecast_provider import PVForecast


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(value, attributes=None):
    """Create a mock entity state."""
    state = MagicMock()
    state.state = str(value) if value is not None else "unavailable"
    state.attributes = attributes or {}
    return state


def _make_coordinator(hourly_avg=None, stats_count=100):
    """Create a mock ConsumptionCoordinator."""
    coord = MagicMock()
    coord.hourly_avg = hourly_avg or {
        day: {h: 500.0 for h in range(24)} for day in WEEKDAY_KEYS
    }
    coord.stats_count = stats_count
    coord.async_update = AsyncMock()
    coord.calculate_period = MagicMock(return_value={
        "verbrauch_kwh": 6.0,
        "stunden": 12.0,
        "stundenprofil": [],
    })
    return coord


def _make_provider(remaining=12.5, tomorrow=25.0):
    """Create a mock ForecastProvider."""
    provider = MagicMock()
    provider.get_forecast.return_value = PVForecast(
        remaining_today_kwh=remaining,
        tomorrow_kwh=tomorrow,
    )
    return provider


# ---------------------------------------------------------------------------
# Battery Missing Energy Sensor
# ---------------------------------------------------------------------------

class TestBatteryMissingEnergySensor:
    """Tests for BatteryMissingEnergySensor."""

    def _make_sensor(self, hass, config):
        from custom_components.eeg_energy_optimizer.sensor import BatteryMissingEnergySensor
        entry = MagicMock()
        entry.entry_id = "test_entry"
        return BatteryMissingEnergySensor(hass, entry, config)

    @pytest.mark.asyncio
    async def test_battery_missing_energy_soc_70(self, mock_hass):
        """SOC=70%, capacity=15kWh -> 4.5 kWh missing."""
        config = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_BATTERY_CAPACITY_KWH: 15.0,
        }
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sensor.battery_soc": _make_state(70.0),
            "sensor.battery_capacity": _make_state(15.0, {"unit_of_measurement": "kWh"}),
        }.get(eid))

        sensor = self._make_sensor(mock_hass, config)
        await sensor.async_update()
        assert sensor.native_value == 4.5

    @pytest.mark.asyncio
    async def test_battery_missing_energy_soc_100(self, mock_hass):
        """SOC=100% -> 0.0 kWh missing."""
        config = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_BATTERY_CAPACITY_KWH: 15.0,
        }
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sensor.battery_soc": _make_state(100.0),
            "sensor.battery_capacity": _make_state(15.0, {"unit_of_measurement": "kWh"}),
        }.get(eid))

        sensor = self._make_sensor(mock_hass, config)
        await sensor.async_update()
        assert sensor.native_value == 0.0

    @pytest.mark.asyncio
    async def test_battery_missing_energy_capacity_wh(self, mock_hass):
        """Capacity sensor reports 15000 Wh -> auto-detect and convert to 15.0 kWh."""
        config = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_SENSOR: "sensor.battery_capacity",
            CONF_BATTERY_CAPACITY_KWH: 15.0,
        }
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sensor.battery_soc": _make_state(70.0),
            "sensor.battery_capacity": _make_state(15000, {"unit_of_measurement": "Wh"}),
        }.get(eid))

        sensor = self._make_sensor(mock_hass, config)
        await sensor.async_update()
        # (100 - 70) / 100 * 15.0 = 4.5
        assert sensor.native_value == 4.5

    @pytest.mark.asyncio
    async def test_battery_missing_energy_no_sensor_uses_manual(self, mock_hass):
        """When capacity sensor unavailable, fall back to manual kWh config."""
        config = {
            CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
            CONF_BATTERY_CAPACITY_KWH: 10.0,
        }
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sensor.battery_soc": _make_state(50.0),
        }.get(eid))

        sensor = self._make_sensor(mock_hass, config)
        await sensor.async_update()
        # (100 - 50) / 100 * 10.0 = 5.0
        assert sensor.native_value == 5.0


# ---------------------------------------------------------------------------
# PV Forecast Sensors
# ---------------------------------------------------------------------------

class TestPVForecastSensors:
    """Tests for PVForecastTodaySensor and PVForecastTomorrowSensor."""

    def _make_today_sensor(self, hass, entry, provider):
        from custom_components.eeg_energy_optimizer.sensor import PVForecastTodaySensor
        return PVForecastTodaySensor(hass, entry, provider)

    def _make_tomorrow_sensor(self, hass, entry, provider):
        from custom_components.eeg_energy_optimizer.sensor import PVForecastTomorrowSensor
        return PVForecastTomorrowSensor(hass, entry, provider)

    @pytest.mark.asyncio
    async def test_pv_forecast_today(self, mock_hass):
        """Provider returns 12.5 -> sensor value 12.5."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        provider = _make_provider(remaining=12.5, tomorrow=25.0)

        sensor = self._make_today_sensor(mock_hass, entry, provider)
        await sensor.async_update()
        assert sensor.native_value == 12.5

    @pytest.mark.asyncio
    async def test_pv_forecast_tomorrow(self, mock_hass):
        """Provider returns 25.0 for tomorrow -> sensor value 25.0."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        provider = _make_provider(remaining=12.5, tomorrow=25.0)

        sensor = self._make_tomorrow_sensor(mock_hass, entry, provider)
        await sensor.async_update()
        assert sensor.native_value == 25.0

    @pytest.mark.asyncio
    async def test_pv_forecast_unavailable(self, mock_hass):
        """Provider returns None -> sensor value None."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        provider = _make_provider(remaining=None, tomorrow=None)

        sensor = self._make_today_sensor(mock_hass, entry, provider)
        await sensor.async_update()
        assert sensor.native_value is None

        sensor2 = self._make_tomorrow_sensor(mock_hass, entry, provider)
        await sensor2.async_update()
        assert sensor2.native_value is None


# ---------------------------------------------------------------------------
# Daily Forecast Sensor
# ---------------------------------------------------------------------------

class TestDailyForecastSensor:
    """Tests for DailyForecastSensor."""

    def _make_sensor(self, hass, entry, coordinator, day_offset):
        from custom_components.eeg_energy_optimizer.sensor import DailyForecastSensor
        return DailyForecastSensor(hass, entry, coordinator, day_offset)

    @pytest.mark.asyncio
    async def test_daily_forecast_today(self, mock_hass):
        """Day_offset=0: calculate_period called for remaining-day AND full-day total."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        coord = _make_coordinator()
        coord.calculate_period.return_value = {
            "verbrauch_kwh": 8.5,
            "stunden": 10.0,
            "stundenprofil": [],
        }

        sensor = self._make_sensor(mock_hass, entry, coord, 0)

        fixed_now = datetime(2026, 3, 21, 14, 0, 0, tzinfo=timezone.utc)
        with patch("custom_components.eeg_energy_optimizer.sensor._now", return_value=fixed_now):
            await sensor.async_update()

        assert sensor.native_value == 8.5
        # Two calls: 1) now → midnight+1d (remaining), 2) midnight → midnight+1d (total)
        assert coord.calculate_period.call_count == 2

        first_call = coord.calculate_period.call_args_list[0][0]
        assert first_call[0] == fixed_now
        assert first_call[1].hour == 0
        assert first_call[1].day == 22

        second_call = coord.calculate_period.call_args_list[1][0]
        assert second_call[0].hour == 0
        assert second_call[0].day == 21
        assert second_call[1].hour == 0
        assert second_call[1].day == 22

        # tagesverbrauch_gesamt_kwh attribute exposed for the dashboard chart
        assert "tagesverbrauch_gesamt_kwh" in sensor.extra_state_attributes

    @pytest.mark.asyncio
    async def test_daily_forecast_tomorrow(self, mock_hass):
        """Day_offset=1: calculate_period called for full tomorrow."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        coord = _make_coordinator()
        coord.calculate_period.return_value = {
            "verbrauch_kwh": 12.0,
            "stunden": 24.0,
            "stundenprofil": [],
        }

        sensor = self._make_sensor(mock_hass, entry, coord, 1)

        fixed_now = datetime(2026, 3, 21, 14, 0, 0, tzinfo=timezone.utc)
        with patch("custom_components.eeg_energy_optimizer.sensor._now", return_value=fixed_now):
            await sensor.async_update()

        assert sensor.native_value == 12.0
        call_args = coord.calculate_period.call_args[0]
        # Start should be midnight tomorrow, end should be midnight day after
        assert call_args[0].day == 22
        assert call_args[0].hour == 0
        assert call_args[1].day == 23
        assert call_args[1].hour == 0


# ---------------------------------------------------------------------------
# Verbrauchsprofil Sensor
# ---------------------------------------------------------------------------

class TestVerbrauchsprofilSensor:
    """Tests for VerbrauchsprofilSensor."""

    def _make_sensor(self, hass, entry, coordinator):
        from custom_components.eeg_energy_optimizer.sensor import VerbrauchsprofilSensor
        return VerbrauchsprofilSensor(hass, entry, coordinator)

    @pytest.mark.asyncio
    async def test_verbrauchsprofil_attributes(self, mock_hass):
        """Verify sensor exposes mo_watts, di_watts, etc. as attributes."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {}  # real dict so .get() returns defaults, not MagicMock
        hourly_avg = {
            day: {h: 400.0 + h * 10.0 for h in range(24)}
            for day in WEEKDAY_KEYS
        }
        coord = _make_coordinator(hourly_avg=hourly_avg, stats_count=200)
        # No sun.sun → driver falls back to default day window (6..20)
        mock_hass.states.get = MagicMock(return_value=None)

        sensor = self._make_sensor(mock_hass, entry, coord)
        await sensor.async_update()

        attrs = sensor.extra_state_attributes
        # Hourly arrays + day totals per weekday
        for day in WEEKDAY_KEYS:
            assert f"{day}_watts" in attrs, f"Missing {day}_watts"
            assert f"{day}_kwh" in attrs, f"Missing {day}_kwh"
            assert f"{day}_tag_kwh" in attrs, f"Missing {day}_tag_kwh"
            assert f"{day}_nacht_kwh" in attrs, f"Missing {day}_nacht_kwh"
            assert len(attrs[f"{day}_watts"]) == 24
            # Tag + Nacht must add up to the day total (within rounding)
            total = attrs[f"{day}_kwh"]
            split_sum = attrs[f"{day}_tag_kwh"] + attrs[f"{day}_nacht_kwh"]
            assert abs(total - split_sum) <= 0.2

        assert "stunden" in attrs
        assert len(attrs["stunden"]) == 24
        assert attrs["stunden"][0] == "00:00"
        # Sunrise / sunset hours are exposed for the chart legend
        assert attrs["sunrise_hour"] == 6
        assert attrs["sunset_hour"] == 20
        assert "stats_count" in attrs
        assert "grundlage" in attrs

    @pytest.mark.asyncio
    async def test_verbrauchsprofil_uses_sun_state_for_day_window(self, mock_hass):
        """Day window adapts to actual sunrise/sunset times from sun.sun."""
        from datetime import datetime, timezone

        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {}  # real dict so .get() returns defaults
        # Constant 1000 W per hour → 1 kWh per hour, 24 kWh per day
        hourly_avg = {day: {h: 1000.0 for h in range(24)} for day in WEEKDAY_KEYS}
        coord = _make_coordinator(hourly_avg=hourly_avg, stats_count=200)

        sun_state = _make_state(
            "above_horizon",
            {
                "next_rising": "2026-04-27T05:00:00+00:00",
                "next_setting": "2026-04-27T19:00:00+00:00",
            },
        )
        mock_hass.states.get = MagicMock(
            side_effect=lambda eid: sun_state if eid == "sun.sun" else None
        )

        sensor = self._make_sensor(mock_hass, entry, coord)
        # _as_local is a MagicMock in the test environment — keep it identity
        with patch(
            "custom_components.eeg_energy_optimizer.sensor._as_local",
            side_effect=lambda dt: dt,
        ):
            await sensor.async_update()

        attrs = sensor.extra_state_attributes
        assert attrs["sunrise_hour"] == 5
        assert attrs["sunset_hour"] == 19
        # Night mirrors optimizer: discharge_start (default 20:00) → sunrise+1h next day.
        # With sunrise 05:00, night_end = 06:00.
        # Hours 20–23 today (4h × 1 kWh) + hours 0–5 next day (6h × 1 kWh) = 10 kWh
        # Day = 24 - 10 = 14 kWh
        assert attrs["mo_nacht_kwh"] == 10.0
        assert attrs["mo_tag_kwh"] == 14.0
        assert attrs["discharge_start_hour"] == 20
        assert attrs["night_end_decimal"] == 6.0


# ---------------------------------------------------------------------------
# Sunrise Forecast Sensor
# ---------------------------------------------------------------------------

class TestSunriseForecastSensor:
    """Tests for SunriseForecastSensor."""

    def _make_sensor(self, hass, entry, coordinator):
        from custom_components.eeg_energy_optimizer.sensor import SunriseForecastSensor
        return SunriseForecastSensor(hass, entry, coordinator)

    @pytest.mark.asyncio
    async def test_sunrise_forecast_calculates(self, mock_hass):
        """Calculates consumption from now to next sunrise."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        coord = _make_coordinator()
        coord.calculate_period.return_value = {
            "verbrauch_kwh": 3.5,
            "stunden": 8.0,
            "stundenprofil": [],
        }

        # Mock sun.sun entity with next_rising
        sunrise_time = "2026-03-22T06:30:00+01:00"
        mock_hass.states.get = MagicMock(side_effect=lambda eid: {
            "sun.sun": _make_state("below_horizon", {"next_rising": sunrise_time}),
        }.get(eid))

        sensor = self._make_sensor(mock_hass, entry, coord)

        fixed_now = datetime(2026, 3, 21, 22, 0, 0, tzinfo=timezone.utc)
        # Patch _as_local too: in the test environment dt_util is a MagicMock,
        # so the production fallback (`lambda dt: dt`) does not apply.
        with patch(
            "custom_components.eeg_energy_optimizer.sensor._now",
            return_value=fixed_now,
        ), patch(
            "custom_components.eeg_energy_optimizer.sensor._as_local",
            side_effect=lambda dt: dt,
        ):
            await sensor.async_update()

        assert sensor.native_value == 3.5
        coord.calculate_period.assert_called_once()

    @pytest.mark.asyncio
    async def test_sunrise_forecast_no_sun_entity(self, mock_hass):
        """If sun entity unavailable, sensor value is None."""
        entry = MagicMock()
        entry.entry_id = "test_entry"
        coord = _make_coordinator()

        mock_hass.states.get = MagicMock(return_value=None)

        sensor = self._make_sensor(mock_hass, entry, coord)

        fixed_now = datetime(2026, 3, 21, 22, 0, 0, tzinfo=timezone.utc)
        with patch("custom_components.eeg_energy_optimizer.sensor._now", return_value=fixed_now):
            await sensor.async_update()

        assert sensor.native_value is None
