"""Tests for Phase 8 Plan 03 — Telemetry-Hooks und Outcome-Verwertung.

Wired into __init__.py / optimizer.py / statistics.py:
  - State-Change Emission auf Zustandsübergang
  - Block-Predictions Capture (Normal → Block)
  - 30-min Snapshot-Tick / 60-min Flush-Drain
  - Sensor-Unavailability Watchdog (10 min)
  - Forecast-Provider Watchdog (3 None in Folge)
  - Inverter-Write Failure-Callback (W-4)
  - Trapezoid-Helper (W-1)
  - _normalize_state Helper (W-2 / W-6)
  - _build_telemetry_profile / _resolve_integration_started_at (W-3 / I-4)
  - v12 → v13 Migration
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_SOC_SENSOR,
    CONF_FORECAST_SOURCE,
    CONF_INVERTER_TYPE,
    CONF_TELEMETRY_ENABLED,
    DOMAIN,
    FAILURE_DEDUP_WINDOW_S,
    FORECAST_NONE_STREAK_THRESHOLD,
    MODE_AUS,
    MODE_EIN,
    MODE_TEST,
    SENSOR_UNAVAIL_THRESHOLD_S,
    STATE_ABEND_ENTLADUNG,
    STATE_MORGEN_EINSPEISUNG,
    STATE_NORMAL,
    TELEMETRY_SETTINGS_KEYS,
)


# ---------------------------------------------------------------------------
# b2) _normalize_state direct unit test
# ---------------------------------------------------------------------------
def test_normalize_state_helper_unit():
    from custom_components.eeg_energy_optimizer import _normalize_state

    assert _normalize_state("Normal") == "normal"
    assert _normalize_state("Morgen-Einspeisung") == "morgen_einspeisung"
    assert _normalize_state("Abend-Entladung") == "abend_entladung"
    assert _normalize_state(None) is None


# ---------------------------------------------------------------------------
# m3) _resolve_integration_started_at preferences (W-3)
# ---------------------------------------------------------------------------
def test_resolve_integration_started_at_prefers_entry_created_at():
    from custom_components.eeg_energy_optimizer import _resolve_integration_started_at

    created = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    entry = SimpleNamespace(created_at=created)
    result = _resolve_integration_started_at(entry, "2026-01-01T00:00:00+00:00")
    # Prefer entry.created_at -> ISO form (UTC)
    assert isinstance(result, str)
    assert result.startswith("2026-01-15T10:00:00")

    # Fallback when entry has no created_at
    entry2 = SimpleNamespace()
    result2 = _resolve_integration_started_at(entry2, "2026-01-01T00:00:00+00:00")
    assert result2 == "2026-01-01T00:00:00+00:00"

    # Neither -> None
    entry3 = SimpleNamespace()
    assert _resolve_integration_started_at(entry3, None) is None


# ---------------------------------------------------------------------------
# m2) _build_telemetry_profile single source of truth (I-4 / W-3)
# ---------------------------------------------------------------------------
def test_profile_helper_single_source_of_truth():
    from custom_components.eeg_energy_optimizer import _build_telemetry_profile

    hass = MagicMock()
    hass.config = SimpleNamespace(country="AT")
    entry = SimpleNamespace(
        data={
            CONF_INVERTER_TYPE: "huawei_sun2000",
            CONF_BATTERY_CAPACITY_KWH: 10,
            CONF_FORECAST_SOURCE: "solcast_solar",
            "min_soc": 15,
            "battery_soc_sensor": "sensor.foo",  # not whitelisted
        },
        options={},
        created_at=None,
    )
    p1 = _build_telemetry_profile(hass, entry, identity_registered_at="2026-01-01T00:00:00+00:00")
    p2 = _build_telemetry_profile(hass, entry, identity_registered_at="2026-01-01T00:00:00+00:00")
    assert p1 == p2
    assert p1["country_iso"] == "AT"
    assert p1["inverter_type"] == "huawei_sun2000"
    assert p1["battery_capacity_kwh"] == 10
    assert p1["forecast_provider"] == "solcast_solar"
    # settings filtered to whitelist
    assert p1["settings"].get("min_soc") == 15
    assert "battery_soc_sensor" not in p1["settings"]


# ---------------------------------------------------------------------------
# n) _trapezoid_kwh basic + edge cases (W-1)
# ---------------------------------------------------------------------------
def test_trapezoid_kwh_basic():
    from custom_components.eeg_energy_optimizer.statistics import _trapezoid_kwh

    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    samples = [(t0, 2.0), (t1, 4.0), (t2, 2.0)]
    result = _trapezoid_kwh(samples)
    assert result == pytest.approx(6.0, rel=1e-9)


def test_trapezoid_kwh_empty():
    from custom_components.eeg_energy_optimizer.statistics import _trapezoid_kwh

    assert _trapezoid_kwh([]) == 0.0


def test_trapezoid_kwh_single_sample():
    from custom_components.eeg_energy_optimizer.statistics import _trapezoid_kwh

    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert _trapezoid_kwh([(t0, 5.0)]) == 0.0


def test_trapezoid_kwh_sorts_unsorted_samples():
    from custom_components.eeg_energy_optimizer.statistics import _trapezoid_kwh

    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    # Out-of-order input
    samples = [(t1, 4.0), (t0, 2.0)]
    # Trapezoid: (2+4)/2 * 1 = 3
    assert _trapezoid_kwh(samples) == pytest.approx(3.0, rel=1e-9)


def test_trapezoid_kwh_filters_none_powers():
    from custom_components.eeg_energy_optimizer.statistics import _trapezoid_kwh

    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    # Middle sample has power None — should be dropped, then 1-segment integration
    samples = [(t0, 2.0), (t1, None), (t2, 4.0)]
    # After filter: [(t0,2.0), (t2,4.0)] over 2h → (2+4)/2 * 2 = 6.0
    assert _trapezoid_kwh(samples) == pytest.approx(6.0, rel=1e-9)


# ---------------------------------------------------------------------------
# h2) optimizer failure_callback wiring (W-4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_optimizer_failure_callback_invoked_on_execute_exception(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """W-4 — pin the optimizer.py contract: failure_callback fires on _execute exception."""
    from custom_components.eeg_energy_optimizer.optimizer import (
        Decision,
        EEGOptimizer,
        Snapshot,
    )

    # Inverter raises on async_set_charge_limit (Morgen-Einspeisung path)
    mock_inverter.async_set_charge_limit = AsyncMock(
        side_effect=OSError("Modbus timeout")
    )
    callback = MagicMock()
    config = {
        CONF_BATTERY_CAPACITY_KWH: 10.0,
        CONF_INVERTER_TYPE: "huawei_sun2000",
    }
    now = datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)
    startup = now - timedelta(seconds=300)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=startup):
        opt = EEGOptimizer(
            mock_hass, "test_entry_id", config, mock_inverter,
            mock_coordinator, mock_provider, failure_callback=callback,
        )
    decision = Decision(timestamp=now.isoformat(), zustand=STATE_MORGEN_EINSPEISUNG)
    snap = Snapshot(now=now)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=now):
        await opt._execute(decision, snap)
    assert callback.call_count == 1
    args = callback.call_args[0]
    assert args[0] == "inverter_write"
    assert isinstance(args[1], OSError)
    assert args[2] == "charge"


@pytest.mark.asyncio
async def test_optimizer_failure_callback_action_discharge(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    from custom_components.eeg_energy_optimizer.optimizer import (
        Decision,
        EEGOptimizer,
        Snapshot,
    )

    mock_inverter.async_set_discharge = AsyncMock(side_effect=RuntimeError("boom"))
    callback = MagicMock()
    now = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)
    startup = now - timedelta(seconds=300)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=startup):
        opt = EEGOptimizer(
            mock_hass, "e", {CONF_BATTERY_CAPACITY_KWH: 10.0}, mock_inverter,
            mock_coordinator, mock_provider, failure_callback=callback,
        )
    decision = Decision(
        timestamp=now.isoformat(),
        zustand=STATE_ABEND_ENTLADUNG,
        entladeleistung_kw=3.0,
        min_soc_berechnet=20.0,
    )
    snap = Snapshot(now=now)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=now):
        await opt._execute(decision, snap)
    assert callback.call_count == 1
    assert callback.call_args[0][2] == "discharge"


@pytest.mark.asyncio
async def test_optimizer_failure_callback_action_stop(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    from custom_components.eeg_energy_optimizer.optimizer import (
        Decision,
        EEGOptimizer,
        Snapshot,
    )

    mock_inverter.async_stop_forcible = AsyncMock(side_effect=RuntimeError("nope"))
    callback = MagicMock()
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    startup = now - timedelta(seconds=300)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=startup):
        opt = EEGOptimizer(
            mock_hass, "e", {CONF_BATTERY_CAPACITY_KWH: 10.0}, mock_inverter,
            mock_coordinator, mock_provider, failure_callback=callback,
        )
    decision = Decision(timestamp=now.isoformat(), zustand=STATE_NORMAL)
    snap = Snapshot(now=now)
    with patch("custom_components.eeg_energy_optimizer.optimizer._now", return_value=now):
        await opt._execute(decision, snap)
    assert callback.call_count == 1
    assert callback.call_args[0][2] == "stop"


def test_optimizer_failure_callback_default_none(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """failure_callback defaults to None — additive, all old call sites unchanged."""
    from custom_components.eeg_energy_optimizer.optimizer import EEGOptimizer

    opt = EEGOptimizer(
        mock_hass, "e", {CONF_BATTERY_CAPACITY_KWH: 10.0}, mock_inverter,
        mock_coordinator, mock_provider,
    )
    assert opt._failure_callback is None


# ---------------------------------------------------------------------------
# l) v12 → v13 migration adds telemetry_enabled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_v12_to_v13_migration_adds_telemetry_enabled():
    from custom_components.eeg_energy_optimizer import async_migrate_entry

    hass = MagicMock()

    # Capture what async_update_entry was called with
    captured: dict = {}

    def _update(entry, *, data=None, version=None):
        captured["data"] = data
        captured["version"] = version
        # Mutate entry so subsequent migration steps see the new state
        entry.data = data
        entry.version = version

    hass.config_entries.async_update_entry = MagicMock(side_effect=_update)

    entry = SimpleNamespace(version=12, data={"some": "value"})
    ok = await async_migrate_entry(hass, entry)
    assert ok is True
    # Final state after all migration steps should be v13 with telemetry_enabled=False
    assert entry.version == 13
    assert entry.data.get(CONF_TELEMETRY_ENABLED) is False


# ---------------------------------------------------------------------------
# Outcome-Hook Tests (W-1, W-2) — statistics._maybe_send_outcome
# ---------------------------------------------------------------------------
#
# Diese Tests pinnen das Outcome-Verhalten in statistics.py:
#   - event_type via _normalize_state (W-2)
#   - peak_power_kw = max(abs(grid_now_kw)) über window
#   - actual_pv_kwh / actual_consumption_kwh = trapezoidal
#   - block_predictions wird nach Outcome gepoppt
#   - graceful Fallbacks wenn Daten fehlen
#
# Testidiom: wir konstruieren FeedinStatistics, hängen einen vollständigen
# Reporter-Mock + ein data-Dict ein, öffnen die Session manuell und schließen
# sie via _close_session(now_local) → das löst _maybe_send_outcome aus.


def _make_outcome_hass(grid_kw=0.0):
    """Return a hass mock whose grid sensor reads the given kW value."""
    hass = MagicMock()
    state = MagicMock()
    state.state = str(grid_kw)
    state.attributes = {"unit_of_measurement": "kW"}
    hass.states.get = MagicMock(return_value=state)
    # async_create_task should run the coroutine inline so AsyncMocks see the call
    def _create_task(coro):
        # Awaiting/closing the coroutine prevents asyncio warnings
        try:
            coro.close()
        except Exception:
            pass
        return MagicMock()
    hass.async_create_task = MagicMock(side_effect=_create_task)
    return hass


def _make_outcome_stats(hass=None, identity_known=True, configured=True):
    """Create a FeedinStatistics with reporter + data dict wired in."""
    from custom_components.eeg_energy_optimizer.statistics import FeedinStatistics

    if hass is None:
        hass = _make_outcome_hass()
    config = {"grid_power_sensor": "sensor.grid", "inverter_type": "huawei_sun2000"}
    stats = FeedinStatistics(hass, "entry-id", config)

    reporter = MagicMock()
    reporter.is_configured = configured
    reporter.send_outcome = AsyncMock()
    reporter._buffer = MagicMock()
    reporter._buffer.identity_known = MagicMock(return_value=identity_known)

    data: dict = {
        "snapshot_queue": [],
        "block_predictions": {},
        "optimizer": None,
    }
    stats.set_reporter(reporter, data)
    return stats, reporter, data


def _open_morning_session(stats, kwh=0.5, start_iso="2026-04-15T05:30:00+00:00"):
    """Manually open a morning session in the stats with a known accumulated kwh."""
    stats._current_session = {
        "state": "morning",
        "start_utc": start_iso,
        "start_local": "07:30",
        "date": "2026-04-15",
        "accumulated_kwh": kwh,
    }
    stats._dirty = True


def _open_evening_session(stats, kwh=1.5, start_iso="2026-04-15T18:00:00+00:00"):
    stats._current_session = {
        "state": "evening",
        "start_utc": start_iso,
        "start_local": "20:00",
        "date": "2026-04-15",
        "accumulated_kwh": kwh,
    }
    stats._dirty = True


# ---------------------------------------------------------------------------
# a) Outcome with full predictions + trapezoid actuals
# ---------------------------------------------------------------------------
def test_outcome_emitted_on_block_end_with_predictions():
    stats, reporter, data = _make_outcome_stats()

    started = datetime(2026, 4, 15, 5, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
    data["block_predictions"]["morgen_einspeisung"] = {
        "started_at": started.isoformat(),
        "soc_start_pct": 90,
        "predicted_pv_kwh": 8.0,
        "predicted_consumption_kwh": 1.5,
    }

    # 4 snapshots inside [started, ended] — 30 min apart
    snaps = []
    times = [
        datetime(2026, 4, 15, 5, 30, tzinfo=timezone.utc),
        datetime(2026, 4, 15, 6, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 15, 6, 30, tzinfo=timezone.utc),
        datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc),
    ]
    grids = [0.5, 1.5, 2.0, 1.0]      # peak abs = 2.0
    pvs = [1.0, 3.0, 4.0, 2.0]        # trapezoid kwh
    cons = [0.5, 0.4, 0.3, 0.2]
    for ts, g, pv, c in zip(times, grids, pvs, cons):
        snaps.append({
            "ts": ts.isoformat(), "state": "morgen_einspeisung", "mode": "ein",
            "grid_now_kw": g, "pv_now_kw": pv, "consumption_now_kw": c,
        })
    data["snapshot_queue"] = list(snaps)

    # last_decision provides soc_end_pct
    last_decision = SimpleNamespace(
        snapshot={"soc_pct": 30}
    )
    data["optimizer"] = SimpleNamespace(last_decision=last_decision)

    _open_morning_session(stats, kwh=4.5, start_iso=started.isoformat())
    stats._close_session(ended)

    assert reporter.send_outcome.await_count == 1 or reporter.send_outcome.call_count == 1
    payload = (reporter.send_outcome.call_args or reporter.send_outcome.await_args).args[0]
    assert payload["event_type"] == "morgen_einspeisung"
    assert payload["soc_start_pct"] == 90
    assert payload["soc_end_pct"] == 30
    assert payload["predicted_pv_kwh"] == 8.0
    assert payload["predicted_consumption_kwh"] == 1.5
    # peak: max abs(grid_now_kw) = 2.0
    assert payload["peak_power_kw"] == pytest.approx(2.0)
    # PV trapezoid: (1+3)/2*0.5 + (3+4)/2*0.5 + (4+2)/2*0.5 = 1 + 1.75 + 1.5 = 4.25
    assert payload["actual_pv_kwh"] == pytest.approx(4.25, rel=1e-9)
    # Cons trapezoid: (0.5+0.4)/2*0.5 + (0.4+0.3)/2*0.5 + (0.3+0.2)/2*0.5 = 0.225 + 0.175 + 0.125 = 0.525
    assert payload["actual_consumption_kwh"] == pytest.approx(0.525, rel=1e-9)
    assert payload["grid_export_kwh"] == pytest.approx(4.5)
    # block_predictions popped
    assert "morgen_einspeisung" not in data["block_predictions"]


# ---------------------------------------------------------------------------
# a2) Outcome event_type uses _normalize_state for both states (W-2)
# ---------------------------------------------------------------------------
def test_outcome_event_type_uses_normalize_state():
    from custom_components.eeg_energy_optimizer import _normalize_state

    # Morning session
    stats, reporter, data = _make_outcome_stats()
    _open_morning_session(stats)
    stats._close_session(datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc))
    assert reporter.send_outcome.call_count == 1
    p1 = reporter.send_outcome.call_args.args[0]
    assert p1["event_type"] == _normalize_state(STATE_MORGEN_EINSPEISUNG)

    # Evening session — fresh stats, fresh reporter mock
    stats2, reporter2, data2 = _make_outcome_stats()
    _open_evening_session(stats2)
    stats2._close_session(datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc))
    assert reporter2.send_outcome.call_count == 1
    p2 = reporter2.send_outcome.call_args.args[0]
    assert p2["event_type"] == _normalize_state(STATE_ABEND_ENTLADUNG)


# ---------------------------------------------------------------------------
# a3) Peak falls back to None when no grid samples
# ---------------------------------------------------------------------------
def test_outcome_peak_power_falls_back_to_none_when_no_grid_samples():
    stats, reporter, data = _make_outcome_stats()
    started = datetime(2026, 4, 15, 5, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
    data["block_predictions"]["morgen_einspeisung"] = {
        "started_at": started.isoformat(),
        "soc_start_pct": 80,
        "predicted_pv_kwh": 5.0,
        "predicted_consumption_kwh": 1.0,
    }
    # All grid samples None
    data["snapshot_queue"] = [
        {"ts": (started + timedelta(minutes=30)).isoformat(),
         "grid_now_kw": None, "pv_now_kw": 2.0, "consumption_now_kw": 0.4},
        {"ts": (started + timedelta(minutes=60)).isoformat(),
         "grid_now_kw": None, "pv_now_kw": 3.0, "consumption_now_kw": 0.3},
    ]
    _open_morning_session(stats, start_iso=started.isoformat())
    stats._close_session(ended)
    payload = reporter.send_outcome.call_args.args[0]
    assert payload["peak_power_kw"] is None


# ---------------------------------------------------------------------------
# a4) Actuals fall back to None when <2 samples
# ---------------------------------------------------------------------------
def test_outcome_actuals_fall_back_to_none_with_lt_2_samples():
    stats, reporter, data = _make_outcome_stats()
    started = datetime(2026, 4, 15, 5, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
    data["block_predictions"]["morgen_einspeisung"] = {
        "started_at": started.isoformat(),
        "soc_start_pct": 80,
        "predicted_pv_kwh": 5.0,
        "predicted_consumption_kwh": 1.0,
    }
    # Only 1 snapshot inside the window
    data["snapshot_queue"] = [{
        "ts": (started + timedelta(minutes=30)).isoformat(),
        "grid_now_kw": 1.0, "pv_now_kw": 2.0, "consumption_now_kw": 0.5,
    }]
    _open_morning_session(stats, start_iso=started.isoformat())
    stats._close_session(ended)
    payload = reporter.send_outcome.call_args.args[0]
    assert payload["actual_pv_kwh"] is None
    assert payload["actual_consumption_kwh"] is None
    # peak still works with single sample
    assert payload["peak_power_kw"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# a5) Window filters snapshots outside [started_at, ended_at]
# ---------------------------------------------------------------------------
def test_outcome_window_filters_snapshots_by_block_range():
    stats, reporter, data = _make_outcome_stats()
    started = datetime(2026, 4, 15, 5, 30, tzinfo=timezone.utc)
    ended = datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc)
    data["block_predictions"]["morgen_einspeisung"] = {
        "started_at": started.isoformat(),
        "soc_start_pct": 80,
        "predicted_pv_kwh": 5.0,
        "predicted_consumption_kwh": 1.0,
    }
    # 2 BEFORE started, 3 inside, 1 AFTER ended
    before = [
        {"ts": "2026-04-15T04:30:00+00:00", "grid_now_kw": 99.0, "pv_now_kw": 99.0, "consumption_now_kw": 99.0},
        {"ts": "2026-04-15T05:00:00+00:00", "grid_now_kw": 99.0, "pv_now_kw": 99.0, "consumption_now_kw": 99.0},
    ]
    inside = [
        {"ts": "2026-04-15T06:00:00+00:00", "grid_now_kw": 1.0, "pv_now_kw": 2.0, "consumption_now_kw": 0.4},
        {"ts": "2026-04-15T06:30:00+00:00", "grid_now_kw": 2.0, "pv_now_kw": 3.0, "consumption_now_kw": 0.3},
        {"ts": "2026-04-15T07:00:00+00:00", "grid_now_kw": 1.5, "pv_now_kw": 2.5, "consumption_now_kw": 0.2},
    ]
    after = [
        {"ts": "2026-04-15T08:00:00+00:00", "grid_now_kw": 99.0, "pv_now_kw": 99.0, "consumption_now_kw": 99.0},
    ]
    data["snapshot_queue"] = before + inside + after
    _open_morning_session(stats, start_iso=started.isoformat())
    stats._close_session(ended)
    payload = reporter.send_outcome.call_args.args[0]
    # Peak should be 2.0 (inside) — 99 (outside) must NOT contribute
    assert payload["peak_power_kw"] == pytest.approx(2.0)
    # PV trapezoid: (2+3)/2*0.5 + (3+2.5)/2*0.5 = 1.25 + 1.375 = 2.625
    assert payload["actual_pv_kwh"] == pytest.approx(2.625, rel=1e-9)


# ---------------------------------------------------------------------------
# b) Silent emission when block_predictions empty (still emits with None values)
# ---------------------------------------------------------------------------
def test_outcome_silent_when_no_predictions():
    stats, reporter, data = _make_outcome_stats()
    # No block_predictions entry — ended_at missing started_at fallback
    _open_morning_session(stats, start_iso="2026-04-15T05:30:00+00:00")
    stats._close_session(datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc))
    assert reporter.send_outcome.call_count == 1
    payload = reporter.send_outcome.call_args.args[0]
    assert payload["event_type"] == "morgen_einspeisung"
    assert payload["predicted_pv_kwh"] is None
    assert payload["predicted_consumption_kwh"] is None
    assert payload["actual_pv_kwh"] is None
    assert payload["actual_consumption_kwh"] is None
    assert payload["peak_power_kw"] is None


# ---------------------------------------------------------------------------
# c) Silent when reporter not configured
# ---------------------------------------------------------------------------
def test_outcome_silent_when_reporter_not_configured():
    stats, reporter, data = _make_outcome_stats(configured=False)
    _open_morning_session(stats)
    stats._close_session(datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc))
    assert reporter.send_outcome.call_count == 0


# ---------------------------------------------------------------------------
# d) Silent when no identity
# ---------------------------------------------------------------------------
def test_outcome_silent_when_no_identity():
    stats, reporter, data = _make_outcome_stats(identity_known=False)
    _open_morning_session(stats)
    stats._close_session(datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc))
    assert reporter.send_outcome.call_count == 0

