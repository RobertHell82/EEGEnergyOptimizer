"""Tests for EEG Energy Optimizer sensor platform."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_CONSUMPTION_SENSOR,
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
        """Day_offset=0: calculate_period called with now..end_of_today."""
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
        # Verify calculate_period was called
        coord.calculate_period.assert_called_once()
        call_args = coord.calculate_period.call_args[0]
        # Start should be now (14:00), end should be end of day (00:00 next day)
        assert call_args[0] == fixed_now
        assert call_args[1].hour == 0
        assert call_args[1].day == 22

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
        hourly_avg = {
            day: {h: 400.0 + h * 10.0 for h in range(24)}
            for day in WEEKDAY_KEYS
        }
        coord = _make_coordinator(hourly_avg=hourly_avg, stats_count=200)

        sensor = self._make_sensor(mock_hass, entry, coord)
        await sensor.async_update()

        attrs = sensor.extra_state_attributes
        # Should have weekday keys
        for day in WEEKDAY_KEYS:
            assert f"{day}_watts" in attrs, f"Missing {day}_watts"
            assert f"{day}_kwh" in attrs, f"Missing {day}_kwh"
            assert len(attrs[f"{day}_watts"]) == 24

        assert "stunden" in attrs
        assert len(attrs["stunden"]) == 24
        assert attrs["stunden"][0] == "00:00"
        assert "stats_count" in attrs
        assert "grundlage" in attrs


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
        with patch("custom_components.eeg_energy_optimizer.sensor._now", return_value=fixed_now):
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
