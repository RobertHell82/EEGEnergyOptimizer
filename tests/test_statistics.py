"""Tests for FeedinStatistics — feed-in energy tracking during optimizer states."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from custom_components.eeg_energy_optimizer.statistics import (
    FeedinStatistics,
    _MICRO_SESSION_SECONDS,
    _MAX_ELAPSED_SECONDS,
)
from custom_components.eeg_energy_optimizer.const import (
    STATE_MORGEN_EINSPEISUNG,
    STATE_ABEND_ENTLADUNG,
    STATE_NORMAL,
)


def _make_decision(zustand=STATE_NORMAL, ausfuehrung=True):
    """Create a minimal decision-like object."""
    return SimpleNamespace(zustand=zustand, ausführung=ausfuehrung)


def _make_hass(grid_kw=2.0, unit="kW"):
    """Create a mock hass with a grid power sensor."""
    hass = MagicMock()
    state = MagicMock()
    state.state = str(grid_kw)
    state.attributes = {"unit_of_measurement": unit}
    hass.states.get = MagicMock(return_value=state)
    return hass


def _make_config():
    return {
        "grid_power_sensor": "sensor.grid_power",
        "inverter_type": "huawei_sun2000",
    }


def _make_stats(hass=None, config=None):
    """Create a FeedinStatistics instance without Store (test mode)."""
    if hass is None:
        hass = _make_hass()
    if config is None:
        config = _make_config()
    stats = FeedinStatistics(hass, "test_entry", config)
    return stats


def _utc(hour, minute=0, second=0, day=10, month=4, year=2026):
    """Create a UTC datetime for testing. Supports second overflow (e.g. 90s → 1m30s)."""
    base = datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)
    return base + timedelta(seconds=second)


class TestSessionLifecycle:
    """Test session start, accumulate, close."""

    @pytest.mark.asyncio
    async def test_first_cycle_no_accumulation(self):
        """First cycle should only set timestamp, not accumulate."""
        stats = _make_stats()
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        await stats.async_update(decision, _utc(7, 0))
        # No session yet — first cycle just sets the timestamp
        assert stats.get_today_kwh("morning") == 0.0

    @pytest.mark.asyncio
    async def test_session_opens_and_accumulates(self):
        """Session should open on active state and accumulate energy."""
        hass = _make_hass(grid_kw=3.0)  # 3 kW export
        stats = _make_stats(hass=hass)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        # First cycle: timestamp only
        await stats.async_update(decision, _utc(7, 0, 0))
        # Second cycle: 30s later → 3.0 kW * 30s / 3600 = 0.025 kWh
        await stats.async_update(decision, _utc(7, 0, 30))

        assert stats._current_session is not None
        assert stats._current_session["state"] == "morning"
        assert abs(stats._current_session["accumulated_kwh"] - 0.025) < 0.001

    @pytest.mark.asyncio
    async def test_session_closes_on_normal(self):
        """Session should close when state returns to Normal."""
        hass = _make_hass(grid_kw=6.0)  # 6 kW export
        stats = _make_stats(hass=hass)

        # Run morning state for 5 minutes (10 cycles of 30s)
        t = _utc(7, 0, 0)
        decision_morning = _make_decision(STATE_MORGEN_EINSPEISUNG)
        await stats.async_update(decision_morning, t)
        for i in range(1, 11):
            t = _utc(7, 0, 30 * i)
            await stats.async_update(decision_morning, t)

        # Switch to Normal
        decision_normal = _make_decision(STATE_NORMAL)
        await stats.async_update(decision_normal, _utc(7, 5, 30))

        assert stats._current_session is None
        today_str = _utc(7, 0).strftime("%Y-%m-%d")
        day_data = stats._daily.get(today_str, {})
        morning = day_data.get("morning", {})
        assert morning["count"] == 1
        assert morning["total_kwh"] > 0

    @pytest.mark.asyncio
    async def test_get_today_kwh_includes_active_session(self):
        """get_today_kwh should include energy from the active session.

        get_today_kwh internally calls statistics._now() to determine "today".
        We patch it to the test clock so the date matches the session date —
        otherwise the wall clock won't match the synthetic _utc(...) timestamps.
        """
        hass = _make_hass(grid_kw=2.0)
        stats = _make_stats(hass=hass)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        await stats.async_update(decision, _utc(7, 0, 0))
        await stats.async_update(decision, _utc(7, 0, 30))

        with patch(
            "custom_components.eeg_energy_optimizer.statistics._now",
            return_value=_utc(7, 0, 30),
        ):
            kwh = stats.get_today_kwh("morning")
        # 2 kW * 30s / 3600 ≈ 0.0167 kWh
        assert kwh > 0


class TestOnlyPositiveExport:
    """Only positive grid export should be counted."""

    @pytest.mark.asyncio
    async def test_negative_grid_ignored(self):
        """Grid import (negative after sign convention) should not accumulate."""
        hass = _make_hass(grid_kw=-1.5)  # import
        stats = _make_stats(hass=hass)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        await stats.async_update(decision, _utc(7, 0, 0))
        await stats.async_update(decision, _utc(7, 0, 30))

        assert stats._current_session["accumulated_kwh"] == 0.0

    @pytest.mark.asyncio
    async def test_solax_sign_convention(self):
        """SolaX has grid_sign=-1, so positive raw = import (should be ignored)."""
        hass = _make_hass(grid_kw=2.0)  # raw positive, but SolaX = import
        config = {
            "grid_power_sensor": "sensor.grid_power",
            "inverter_type": "solax_gen4",
        }
        stats = _make_stats(hass=hass, config=config)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        await stats.async_update(decision, _utc(7, 0, 0))
        await stats.async_update(decision, _utc(7, 0, 30))

        # SolaX grid_sign=-1 → 2.0 * -1 = -2.0 → max(-2.0, 0) = 0
        assert stats._current_session["accumulated_kwh"] == 0.0


class TestTestModeIgnored:
    """Test mode (ausführung=False) should not accumulate."""

    @pytest.mark.asyncio
    async def test_no_accumulation_in_test_mode(self):
        """When ausführung is False, stats_key should be None (no tracking)."""
        hass = _make_hass(grid_kw=5.0)
        stats = _make_stats(hass=hass)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG, ausfuehrung=False)

        await stats.async_update(decision, _utc(7, 0, 0))
        await stats.async_update(decision, _utc(7, 0, 30))

        assert stats._current_session is None
        assert stats.get_today_kwh("morning") == 0.0


class TestStateTransition:
    """Test transitions between different active states."""

    @pytest.mark.asyncio
    async def test_morning_to_evening(self):
        """Switching from morning to evening should close morning, open evening."""
        hass = _make_hass(grid_kw=4.0)
        stats = _make_stats(hass=hass)

        # Morning phase: 3 minutes
        morning = _make_decision(STATE_MORGEN_EINSPEISUNG)
        await stats.async_update(morning, _utc(7, 0, 0))
        for i in range(1, 7):  # 6 cycles = 3 min
            await stats.async_update(morning, _utc(7, 0, 30 * i))

        # Switch to evening
        evening = _make_decision(STATE_ABEND_ENTLADUNG)
        await stats.async_update(evening, _utc(20, 0, 0))
        await stats.async_update(evening, _utc(20, 0, 30))

        assert stats._current_session is not None
        assert stats._current_session["state"] == "evening"

        today_str = _utc(7, 0).strftime("%Y-%m-%d")
        assert stats._daily[today_str]["morning"]["count"] == 1


class TestStaleDataGuard:
    """Skip accumulation if elapsed > _MAX_ELAPSED_SECONDS."""

    @pytest.mark.asyncio
    async def test_large_gap_no_accumulation(self):
        """If more than 120s between cycles, energy should not be accumulated."""
        hass = _make_hass(grid_kw=10.0)
        stats = _make_stats(hass=hass)
        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)

        await stats.async_update(decision, _utc(7, 0, 0))
        # Normal cycles: accumulate energy
        await stats.async_update(decision, _utc(7, 0, 30))
        await stats.async_update(decision, _utc(7, 1, 0))
        kwh_after_normal = stats._current_session["accumulated_kwh"]
        assert kwh_after_normal > 0

        # Gap of 5 minutes (300s > 120s) — should skip accumulation
        await stats.async_update(decision, _utc(7, 6, 0))
        kwh_after_gap = stats._current_session["accumulated_kwh"]
        assert kwh_after_gap == kwh_after_normal  # unchanged


class TestMidnightRollover:
    """Sessions running across midnight stay attached to the start day."""

    @pytest.mark.asyncio
    async def test_session_stays_on_start_day_across_midnight(self):
        """Cross-midnight sessions accumulate on the start day; no daily entry
        is written until the session closes (e.g. via state change to Normal).
        """
        hass = _make_hass(grid_kw=3.0)
        stats = _make_stats(hass=hass)
        decision_evening = _make_decision(STATE_ABEND_ENTLADUNG)

        # Start evening session at 23:58 on day 10
        await stats.async_update(decision_evening, _utc(23, 58, 0, day=10))
        await stats.async_update(decision_evening, _utc(23, 58, 30, day=10))
        await stats.async_update(decision_evening, _utc(23, 59, 0, day=10))

        # Cross midnight — day=11
        await stats.async_update(decision_evening, _utc(0, 0, 30, day=11))
        await stats.async_update(decision_evening, _utc(0, 1, 0, day=11))

        # No closed session yet — both days should be empty in _daily
        assert "2026-04-10" not in stats._daily
        assert "2026-04-11" not in stats._daily

        # Session is still active and tagged with the start day
        assert stats._current_session is not None
        assert stats._current_session["date"] == "2026-04-10"

        # Close session via state change (back to Normal)
        decision_normal = _make_decision("Normal")
        await stats.async_update(decision_normal, _utc(0, 2, 0, day=11))

        # Session must be closed and bucketed on the START day (10), not 11
        assert "2026-04-10" in stats._daily
        evening_10 = stats._daily["2026-04-10"].get("evening", {})
        assert evening_10.get("count", 0) == 1
        # Day 11 must NOT have a session
        assert "2026-04-11" not in stats._daily or \
            stats._daily.get("2026-04-11", {}).get("evening", {}).get("count", 0) == 0


class TestCompaction:
    """Old entries should have sessions compacted to aggregates."""

    @pytest.mark.asyncio
    async def test_compact_removes_sessions(self):
        """Entries older than STATS_COMPACT_AFTER_DAYS should lose session details."""
        stats = _make_stats()

        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

        stats._daily = {
            old_date: {
                "morning": {
                    "sessions": [{"start": "07:30", "end": "10:00", "kwh": 3.0, "duration_min": 150}],
                    "total_kwh": 3.0,
                    "total_duration_min": 150,
                    "count": 1,
                },
                "evening": _empty_state_stats_with_sessions(),
            },
            recent_date: {
                "morning": {
                    "sessions": [{"start": "08:00", "end": "10:30", "kwh": 2.5, "duration_min": 150}],
                    "total_kwh": 2.5,
                    "total_duration_min": 150,
                    "count": 1,
                },
                "evening": _empty_state_stats_with_sessions(),
            },
        }

        stats._compact_old_entries()

        # Old entry: sessions removed, aggregates preserved
        assert "sessions" not in stats._daily[old_date]["morning"]
        assert stats._daily[old_date]["morning"]["total_kwh"] == 3.0
        assert stats._daily[old_date]["morning"]["count"] == 1

        # Recent entry: sessions still there
        assert "sessions" in stats._daily[recent_date]["morning"]

    @pytest.mark.asyncio
    async def test_compacted_entries_in_summary(self):
        """Compacted entries (no sessions) should still be included in summaries."""
        stats = _make_stats()

        old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
        stats._daily = {
            old_date: {
                "morning": {
                    "total_kwh": 5.0,
                    "total_duration_min": 200,
                    "count": 2,
                },
                "evening": {
                    "total_kwh": 3.0,
                    "total_duration_min": 120,
                    "count": 1,
                },
            },
        }

        summary = stats.get_summary(days=None)  # All time
        assert summary["morning"]["kwh"] == 5.0
        assert summary["morning"]["count"] == 2
        assert summary["evening"]["kwh"] == 3.0


class TestSummaryPeriods:
    """Test summary aggregation for different periods."""

    @pytest.mark.asyncio
    async def test_summary_filters_by_days(self):
        """get_summary(days=7) should only include last 7 days."""
        stats = _make_stats()
        today = datetime.now().strftime("%Y-%m-%d")
        old = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")

        stats._daily = {
            today: {
                "morning": {"total_kwh": 2.0, "total_duration_min": 60, "count": 1},
                "evening": {"total_kwh": 1.0, "total_duration_min": 30, "count": 1},
            },
            old: {
                "morning": {"total_kwh": 10.0, "total_duration_min": 300, "count": 3},
                "evening": {"total_kwh": 8.0, "total_duration_min": 240, "count": 2},
            },
        }

        week = stats.get_summary(days=7)
        assert week["morning"]["kwh"] == 2.0  # only today
        assert week["morning"]["count"] == 1

        total = stats.get_summary(days=None)
        assert total["morning"]["kwh"] == 12.0  # both days


class TestDailyStatsFiltering:
    """Test get_daily_stats date range filtering."""

    def test_date_range_filtering(self):
        stats = _make_stats()
        stats._daily = {
            "2026-04-01": {"morning": {"total_kwh": 1.0}, "evening": {"total_kwh": 0.5}},
            "2026-04-05": {"morning": {"total_kwh": 2.0}, "evening": {"total_kwh": 1.0}},
            "2026-04-10": {"morning": {"total_kwh": 3.0}, "evening": {"total_kwh": 1.5}},
        }

        result = stats.get_daily_stats("2026-04-03", "2026-04-08")
        assert list(result.keys()) == ["2026-04-05"]

        result_all = stats.get_daily_stats()
        assert len(result_all) == 3


class TestHaRestartRecovery:
    """Test session recovery after HA restart."""

    @pytest.mark.asyncio
    async def test_persisted_session_restored(self):
        """A current_session from Store should be restored on load."""
        stats = _make_stats()

        # Simulate Store load — use the same date as the test's synthetic clock
        test_date = _utc(7, 0).strftime("%Y-%m-%d")
        stats._current_session = {
            "state": "morning",
            "start_utc": _utc(7, 0).isoformat(),
            "start_local": "07:00",
            "date": test_date,
            "accumulated_kwh": 1.5,
        }

        # Continue accumulating
        hass = _make_hass(grid_kw=2.0)
        stats._hass = hass
        stats._first_cycle = False
        stats._last_update_utc = _utc(7, 30, 0)

        decision = _make_decision(STATE_MORGEN_EINSPEISUNG)
        await stats.async_update(decision, _utc(7, 30, 30))

        # Should have accumulated on top of 1.5 (≈ 1.5 + 0.0167)
        assert stats._current_session["accumulated_kwh"] > 1.5


def _empty_state_stats_with_sessions():
    return {
        "sessions": [],
        "total_kwh": 0.0,
        "total_duration_min": 0,
        "count": 0,
    }
