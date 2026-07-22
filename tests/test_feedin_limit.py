"""Tests for the "Einspeisebegrenzung optimieren" feature.

Deckt ab:
- _should_limit_feedin: Guards (Feature aus, falscher Inverter, Sensor fehlt,
  Batterie voll), Eintritt/kein-Überschuss.
- Asymmetrischer Regler: langsam hoch (feste Schritte), schnell runter
  (proportional), Netzbezug-Schutz, 60-s-Throttle.
- Konvergenz: grid pendelt sich am Limit ein.
- _execute: Delta-Dedup schreibt nur bei geänderter Ladeleistung.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_SOC_SENSOR,
    CONF_ENABLE_FEEDIN_LIMIT,
    CONF_FEEDIN_LIMIT_KW,
    CONF_INVERTER_TYPE,
    FEEDIN_STEP_UP_KW,
    INVERTER_TYPE_HUAWEI,
    STATE_EINSPEISEBEGRENZUNG,
)
from custom_components.eeg_energy_optimizer.optimizer import (
    EEGOptimizer,
    Decision,
    REASON_FEEDIN_LIMIT_ACTIVE,
    REASON_FEEDIN_LIMIT_BATTERY_FULL,
    REASON_FEEDIN_LIMIT_DISABLED,
    REASON_FEEDIN_LIMIT_NO_GRID_SENSOR,
    REASON_FEEDIN_LIMIT_NO_SURPLUS,
    REASON_FEEDIN_LIMIT_UNSUPPORTED_INVERTER,
    Snapshot,
)

_UTC = timezone.utc


def _feedin_config(**overrides):
    base = {
        CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
        CONF_BATTERY_CAPACITY_KWH: 10.0,
        CONF_INVERTER_TYPE: INVERTER_TYPE_HUAWEI,
        CONF_ENABLE_FEEDIN_LIMIT: True,
        CONF_FEEDIN_LIMIT_KW: 4.0,
    }
    base.update(overrides)
    return base


def _snap(**overrides):
    now = overrides.pop("now", datetime(2026, 6, 15, 12, 0, tzinfo=_UTC))
    defaults = dict(
        now=now,
        battery_soc=50.0,
        battery_capacity_kwh=10.0,
        grid_now_kw=5.0,
        pv_now_kw=8.0,
        consumption_now_kw=1.0,
        battery_now_kw=0.0,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider, **cfg):
    return EEGOptimizer(
        mock_hass, "test_entry", _feedin_config(**cfg),
        mock_inverter, mock_coordinator, mock_provider,
    )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_feature_disabled(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider,
               **{CONF_ENABLE_FEEDIN_LIMIT: False})
    active, charge, reasons, blocked = opt._should_limit_feedin(_snap())
    assert active is False
    assert charge == 0.0
    assert REASON_FEEDIN_LIMIT_DISABLED in blocked


def test_unsupported_inverter(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider,
               **{CONF_INVERTER_TYPE: "solax_gen4"})
    active, _charge, _reasons, blocked = opt._should_limit_feedin(_snap())
    assert active is False
    assert REASON_FEEDIN_LIMIT_UNSUPPORTED_INVERTER in blocked


def test_no_grid_sensor(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    active, _charge, _reasons, blocked = opt._should_limit_feedin(_snap(grid_now_kw=None))
    assert active is False
    assert REASON_FEEDIN_LIMIT_NO_GRID_SENSOR in blocked


def test_battery_full(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    active, _charge, _reasons, blocked = opt._should_limit_feedin(_snap(battery_soc=99.0))
    assert active is False
    assert REASON_FEEDIN_LIMIT_BATTERY_FULL in blocked


def test_no_surplus_no_entry(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Einspeisung deutlich unter Limit → kein Eintritt."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    # grid=1.0, limit=4.0 → weit unter Limit-Marge
    active, charge, _reasons, blocked = opt._should_limit_feedin(_snap(grid_now_kw=1.0))
    assert active is False
    assert charge == 0.0
    assert REASON_FEEDIN_LIMIT_NO_SURPLUS in blocked


# ---------------------------------------------------------------------------
# Eintritt + Regler
# ---------------------------------------------------------------------------

def test_entry_sets_feedforward_estimate(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Beim Eintritt konservative Feedforward-Schätzung (pv-cons-limit)*0.8."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = "Normal"
    active, charge, reasons, _blocked = opt._should_limit_feedin(
        _snap(grid_now_kw=5.0, pv_now_kw=8.0, consumption_now_kw=1.0)
    )
    assert active is True
    # estimate = max(0, 8-1-4)*0.8 = 2.4
    assert charge == pytest.approx(2.4, abs=0.01)
    assert REASON_FEEDIN_LIMIT_ACTIVE in reasons


def test_slow_up_when_at_limit(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Einspeisung am Limit → Ladeleistung um festen Schritt anheben."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = STATE_EINSPEISEBEGRENZUNG
    opt._feedin_charge_kw = 2.0
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    opt._feedin_last_adjust = now - timedelta(seconds=61)
    # grid == limit → error ~0 → hochtasten
    _active, charge, _r, _b = opt._should_limit_feedin(
        _snap(now=now, grid_now_kw=4.0, pv_now_kw=8.0, consumption_now_kw=1.0)
    )
    assert charge == pytest.approx(2.0 + FEEDIN_STEP_UP_KW, abs=0.01)


def test_fast_down_below_limit(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Einspeisung unter Limit → proportional (schnell) absenken."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = STATE_EINSPEISEBEGRENZUNG
    opt._feedin_charge_kw = 3.0
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    opt._feedin_last_adjust = now - timedelta(seconds=61)
    # grid=2.0, limit=4.0 → error=-2.0 → charge += -2.0 (pv-Überschuss deckelt nicht)
    _active, charge, _r, _b = opt._should_limit_feedin(
        _snap(now=now, grid_now_kw=2.0, pv_now_kw=10.0, consumption_now_kw=1.0)
    )
    assert charge == pytest.approx(1.0, abs=0.01)


def test_grid_import_protection(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """PV-Einbruch (Netzbezug) → Ladeleistung wird durch PV-Überschuss-Deckel auf 0 gezogen."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = STATE_EINSPEISEBEGRENZUNG
    opt._feedin_charge_kw = 4.0
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    opt._feedin_last_adjust = now - timedelta(seconds=61)
    # PV bricht ein: pv=1.5, cons=2.0 → Überschuss negativ → Deckel 0 → Austritt
    active, charge, _r, _b = opt._should_limit_feedin(
        _snap(now=now, grid_now_kw=-0.5, pv_now_kw=1.5, consumption_now_kw=2.0)
    )
    assert charge == 0.0
    assert active is False


def test_60s_throttle(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Kein aktiver Regelschritt vor Ablauf des 60-s-Intervalls."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = STATE_EINSPEISEBEGRENZUNG
    opt._feedin_charge_kw = 2.0
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    opt._feedin_last_adjust = now - timedelta(seconds=30)  # erst 30 s
    _active, charge, _r, _b = opt._should_limit_feedin(
        _snap(now=now, grid_now_kw=4.0, pv_now_kw=8.0, consumption_now_kw=1.0)
    )
    # kein Schritt → unverändert (Deckel greift, aber Überschuss 7 > 2.0)
    assert charge == pytest.approx(2.0, abs=0.01)


def test_convergence_holds_grid_near_limit(mock_hass, mock_inverter, mock_coordinator, mock_provider):
    """Simuliert grid = pv - cons - charge und prüft Einpendeln nahe Limit."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._last_eval_zustand = "Normal"
    pv, cons, limit = 8.0, 1.0, 4.0
    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    grid = pv - cons  # zu Beginn kein Laden → voller Überschuss
    last_grid = None
    for _ in range(20):
        active, charge, _r, _b = opt._should_limit_feedin(
            _snap(now=now, grid_now_kw=grid, pv_now_kw=pv, consumption_now_kw=cons)
        )
        assert active is True
        opt._last_eval_zustand = STATE_EINSPEISEBEGRENZUNG
        grid = pv - cons - charge  # physikalische Rückkopplung
        last_grid = grid
        now = now + timedelta(seconds=61)
    # eingependelt: grid bleibt am Limit (Sägezahn max. eine Schrittweite darunter)
    assert limit - FEEDIN_STEP_UP_KW - 0.05 <= last_grid <= limit + 0.05


# ---------------------------------------------------------------------------
# _execute Delta-Dedup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_writes_only_on_charge_change(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._prev_zustand = STATE_EINSPEISEBEGRENZUNG
    opt._prev_charge_kw = 3.0

    now = datetime(2026, 6, 15, 12, 0, tzinfo=_UTC)
    snap = _snap(now=now)

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=now
    ):
        # Startup-Grace-Period überspringen
        opt._startup_time = now - timedelta(seconds=200)

        # Gleiche Ladeleistung → kein Write (Delta unter Schwelle)
        dec_same = Decision(
            zustand=STATE_EINSPEISEBEGRENZUNG, ladeleistung_kw=3.0, ausführung=True
        )
        await opt._execute(dec_same, snap)
        assert mock_inverter.async_set_charge_limit.call_count == 0

        # Geänderte Ladeleistung → genau ein Write mit neuem Wert
        dec_changed = Decision(
            zustand=STATE_EINSPEISEBEGRENZUNG, ladeleistung_kw=3.5, ausführung=True
        )
        await opt._execute(dec_changed, snap)
        mock_inverter.async_set_charge_limit.assert_awaited_once_with(3.5)
        assert opt._prev_charge_kw == 3.5
