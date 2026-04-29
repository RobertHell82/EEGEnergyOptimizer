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
