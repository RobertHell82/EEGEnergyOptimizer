"""Tests for ConsumptionCoordinator."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.coordinator import ConsumptionCoordinator


def _make_stat_entry(dt_local, mean_watts):
    """Create a statistics entry with a UTC timestamp."""
    return {
        "start": dt_local.astimezone(timezone.utc).timestamp(),
        "mean": mean_watts,
    }


def _generate_week_stats(base_monday, patterns):
    """Generate a week of hourly stats.

    patterns: dict mapping weekday index (0=Mon) to a function hour -> watts.
    """
    entries = []
    for day_offset in range(7):
        day = base_monday + timedelta(days=day_offset)
        weekday_idx = day.weekday()
        pattern_fn = patterns.get(weekday_idx, lambda h: 300.0)
        for hour in range(24):
            dt_local = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            entries.append(_make_stat_entry(dt_local, pattern_fn(hour)))
    return entries


# CET timezone (UTC+1) for Austrian tests
CET = timezone(timedelta(hours=1))


@pytest.fixture
def mock_hass():
    """Create mock hass for coordinator tests."""
    hass = MagicMock()
    hass.data = {}
    return hass


@pytest.fixture
def two_weeks_stats():
    """Generate 2 weeks of statistics with distinct per-weekday patterns."""
    # Week 1: Mon 2026-03-16 (a Monday in CET)
    base_w1 = datetime(2026, 3, 16, tzinfo=CET)
    # Week 2: Mon 2026-03-09
    base_w2 = datetime(2026, 3, 9, tzinfo=CET)

    patterns = {
        0: lambda h: 400.0 + h * 10,    # Monday: 400-630W
        1: lambda h: 410.0 + h * 10,    # Tuesday
        2: lambda h: 420.0 + h * 10,    # Wednesday
        3: lambda h: 430.0 + h * 10,    # Thursday
        4: lambda h: 350.0 + h * 5,     # Friday: 350-465W
        5: lambda h: 500.0 + h * 15,    # Saturday: 500-845W
        6: lambda h: 450.0 + h * 12,    # Sunday: 450-726W
    }

    entries = _generate_week_stats(base_w1, patterns) + _generate_week_stats(base_w2, patterns)
    return {"sensor.consumption": entries}


def _patch_recorder(stats_data):
    """Context manager to patch recorder statistics_during_period."""
    mock_stats = AsyncMock(return_value=stats_data)
    mock_get_instance = MagicMock()
    mock_recorder = MagicMock()
    mock_recorder.async_add_executor_job = mock_stats
    mock_get_instance.return_value = mock_recorder

    return (
        patch(
            "custom_components.eeg_energy_optimizer.coordinator.statistics_during_period",
            new=MagicMock(),
        ),
        patch(
            "custom_components.eeg_energy_optimizer.coordinator.get_instance",
            new=mock_get_instance,
        ),
        mock_stats,
        mock_recorder,
    )


class TestWeekdayGrouping:
    """Test that statistics are correctly grouped by 7 individual weekdays."""

    @pytest.mark.asyncio
    async def test_weekday_grouping(self, mock_hass, two_weeks_stats):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(two_weeks_stats)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Should have all 7 weekday keys
        assert set(coordinator.hourly_avg.keys()) == {"mo", "di", "mi", "do", "fr", "sa", "so"}

        # Monday hour 0 should be ~400W (from pattern: 400 + 0*10)
        assert abs(coordinator.hourly_avg["mo"][0] - 400.0) < 1.0

        # Saturday hour 12 should be ~680W (500 + 12*15)
        assert abs(coordinator.hourly_avg["sa"][12] - 680.0) < 1.0

        # Sunday hour 10 should be ~570W (450 + 10*12)
        assert abs(coordinator.hourly_avg["so"][10] - 570.0) < 1.0

        # Friday hour 20 should be ~450W (350 + 20*5)
        assert abs(coordinator.hourly_avg["fr"][20] - 450.0) < 1.0

        assert coordinator.stats_count > 0

    @pytest.mark.asyncio
    async def test_each_weekday_has_24_hours(self, mock_hass, two_weeks_stats):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(two_weeks_stats)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        for day in ["mo", "di", "mi", "do", "fr", "sa", "so"]:
            assert len(coordinator.hourly_avg[day]) == 24, f"{day} missing hours"


class TestCalculatePeriod:
    """Test consumption period calculations."""

    @pytest.mark.asyncio
    async def test_calculate_period_full_hours(self, mock_hass, two_weeks_stats):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(two_weeks_stats)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Monday 08:00-10:00 -> 2 full hours: mo[8] + mo[9]
        start = datetime(2026, 3, 16, 8, 0, tzinfo=CET)  # Monday
        end = datetime(2026, 3, 16, 10, 0, tzinfo=CET)

        result = coordinator.calculate_period(start, end)
        mo_8 = coordinator.hourly_avg["mo"][8]  # 400 + 80 = 480W
        mo_9 = coordinator.hourly_avg["mo"][9]  # 400 + 90 = 490W
        expected_kwh = (mo_8 + mo_9) / 1000.0

        assert abs(result["verbrauch_kwh"] - expected_kwh) < 0.01
        assert result["stunden"] == 2.0

    @pytest.mark.asyncio
    async def test_calculate_period_partial_hours(self, mock_hass, two_weeks_stats):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(two_weeks_stats)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Monday 08:30-10:00 -> 0.5h of hour 8 + 1.0h of hour 9
        start = datetime(2026, 3, 16, 8, 30, tzinfo=CET)
        end = datetime(2026, 3, 16, 10, 0, tzinfo=CET)

        result = coordinator.calculate_period(start, end)
        mo_8 = coordinator.hourly_avg["mo"][8]
        mo_9 = coordinator.hourly_avg["mo"][9]
        expected_kwh = (0.5 * mo_8 + 1.0 * mo_9) / 1000.0

        assert abs(result["verbrauch_kwh"] - expected_kwh) < 0.01
        assert result["stunden"] == 1.5

    @pytest.mark.asyncio
    async def test_calculate_period_cross_midnight(self, mock_hass, two_weeks_stats):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(two_weeks_stats)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Sunday 23:00 to Monday 01:00 -> so[23] + mo[0]
        start = datetime(2026, 3, 15, 23, 0, tzinfo=CET)  # Sunday
        end = datetime(2026, 3, 16, 1, 0, tzinfo=CET)  # Monday

        result = coordinator.calculate_period(start, end)
        so_23 = coordinator.hourly_avg["so"][23]
        mo_0 = coordinator.hourly_avg["mo"][0]
        expected_kwh = (so_23 + mo_0) / 1000.0

        assert abs(result["verbrauch_kwh"] - expected_kwh) < 0.01
        assert result["stunden"] == 2.0

    def test_calculate_period_empty_returns_zero(self, mock_hass):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)
        # No data loaded, hourly_avg is empty

        start = datetime(2026, 3, 16, 8, 0, tzinfo=CET)
        end = datetime(2026, 3, 16, 10, 0, tzinfo=CET)

        result = coordinator.calculate_period(start, end)
        assert result["verbrauch_kwh"] == 0.0

    def test_calculate_period_end_before_start(self, mock_hass):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        start = datetime(2026, 3, 16, 10, 0, tzinfo=CET)
        end = datetime(2026, 3, 16, 8, 0, tzinfo=CET)

        result = coordinator.calculate_period(start, end)
        assert result["verbrauch_kwh"] == 0.0
        assert result["stunden"] == 0.0


class TestFallbackChain:
    """Test fallback when a weekday has no data."""

    @pytest.mark.asyncio
    async def test_fallback_chain(self, mock_hass):
        """Remove all Saturday data, verify it falls back to Sunday."""
        # Only generate Sunday + weekday data (no Saturday)
        patterns = {
            0: lambda h: 400.0,  # Monday
            1: lambda h: 400.0,  # Tuesday
            2: lambda h: 400.0,  # Wednesday
            3: lambda h: 400.0,  # Thursday
            4: lambda h: 350.0,  # Friday
            # 5: Saturday - NO DATA
            6: lambda h: 500.0,  # Sunday
        }

        base = datetime(2026, 3, 16, tzinfo=CET)
        entries = []
        for day_offset in range(7):
            day = base + timedelta(days=day_offset)
            weekday_idx = day.weekday()
            if weekday_idx == 5:  # Skip Saturday
                continue
            pattern_fn = patterns.get(weekday_idx, lambda h: 300.0)
            for hour in range(24):
                dt_local = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                entries.append(_make_stat_entry(dt_local, pattern_fn(hour)))

        stats_data = {"sensor.consumption": entries}
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(stats_data)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Saturday should fall back to Sunday (first in sa fallback chain)
        # Sunday pattern is 500W constant
        assert abs(coordinator.hourly_avg["sa"][12] - 500.0) < 1.0

    @pytest.mark.asyncio
    async def test_fallback_weekend_to_friday(self, mock_hass):
        """When both sa and so have no data, fall back to fr."""
        patterns = {
            0: lambda h: 400.0,
            1: lambda h: 400.0,
            2: lambda h: 400.0,
            3: lambda h: 400.0,
            4: lambda h: 350.0,  # Friday
            # 5: Saturday - NO DATA
            # 6: Sunday - NO DATA
        }

        base = datetime(2026, 3, 16, tzinfo=CET)
        entries = []
        for day_offset in range(5):  # Mon-Fri only
            day = base + timedelta(days=day_offset)
            weekday_idx = day.weekday()
            pattern_fn = patterns.get(weekday_idx, lambda h: 300.0)
            for hour in range(24):
                dt_local = day.replace(hour=hour, minute=0, second=0, microsecond=0)
                entries.append(_make_stat_entry(dt_local, pattern_fn(hour)))

        stats_data = {"sensor.consumption": entries}
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(stats_data)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        # Saturday falls back: so (no data) -> fr (350W)
        assert abs(coordinator.hourly_avg["sa"][12] - 350.0) < 1.0
        # Sunday falls back: sa (no data) -> fr (350W)
        assert abs(coordinator.hourly_avg["so"][12] - 350.0) < 1.0


class TestEmptyStatistics:
    """Test behavior with no statistics data."""

    @pytest.mark.asyncio
    async def test_empty_statistics(self, mock_hass):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        stats_data = {"sensor.consumption": []}
        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(stats_data)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        assert coordinator.stats_count == 0
        # All hours should be 0.0
        for day in ["mo", "di", "mi", "do", "fr", "sa", "so"]:
            for hour in range(24):
                assert coordinator.hourly_avg[day][hour] == 0.0

    @pytest.mark.asyncio
    async def test_missing_sensor_in_stats(self, mock_hass):
        coordinator = ConsumptionCoordinator(mock_hass, "sensor.consumption", 8)

        stats_data = {}  # No data at all
        patch_sdp, patch_gi, mock_stats, mock_recorder = _patch_recorder(stats_data)
        with patch_sdp, patch_gi:
            await coordinator.async_update()

        assert coordinator.stats_count == 0
