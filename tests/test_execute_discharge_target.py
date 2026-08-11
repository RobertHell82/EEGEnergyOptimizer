"""Tests für _execute: Ziel-SOC-Nachführung + Retry bei fehlgeschlagenem Write.

Regression für den Fronius-Nacht-Deadlock (11.08.2026): Der dynamische
Ziel-SOC sinkt im Lauf der Nacht, wurde aber wegen der Zustands-Deduplizierung
nie an den Inverter nachgeschrieben — der beim Entladestart gesetzte
MinRsvPct-Floor blieb stehen und fror die Batterie ein. Außerdem wurden
fehlgeschlagene Inverter-Writes (return False) als erledigt markiert, sodass
z. B. ein gescheitertes stop_forcible nie wiederholt wurde.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom_components.eeg_energy_optimizer.const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_SOC_SENSOR,
    CONF_INVERTER_TYPE,
    INVERTER_TYPE_HUAWEI,
    STATE_ABEND_ENTLADUNG,
    STATE_NORMAL,
)
from custom_components.eeg_energy_optimizer.optimizer import (
    Decision,
    EEGOptimizer,
    Snapshot,
)

_UTC = timezone.utc
_NOW = datetime(2026, 8, 10, 22, 0, tzinfo=_UTC)


def _config(**overrides):
    base = {
        CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
        CONF_BATTERY_CAPACITY_KWH: 10.0,
        CONF_INVERTER_TYPE: INVERTER_TYPE_HUAWEI,
    }
    base.update(overrides)
    return base


def _snap():
    return Snapshot(
        now=_NOW,
        battery_soc=77.0,
        battery_capacity_kwh=10.0,
    )


def _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider, **cfg):
    opt = EEGOptimizer(
        mock_hass, "test_entry", _config(**cfg),
        mock_inverter, mock_coordinator, mock_provider,
    )
    # Startup-Grace-Period überspringen
    opt._startup_time = _NOW - timedelta(seconds=200)
    return opt


def _discharge_decision(target_soc: float) -> Decision:
    return Decision(
        zustand=STATE_ABEND_ENTLADUNG,
        entladeleistung_kw=2.5,
        min_soc_berechnet=target_soc,
        ausführung=True,
    )


@pytest.mark.asyncio
async def test_target_soc_drift_resends_discharge(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """Sinkender Ziel-SOC bei gleichbleibendem Zustand → neuer Discharge-Write."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    snap = _snap()

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=_NOW
    ):
        # Entladestart: Ziel-SOC 77
        await opt._execute(_discharge_decision(77.0), snap)
        mock_inverter.async_set_discharge.assert_awaited_once_with(
            2.5, target_soc=77.0
        )
        assert opt._prev_target_soc == 77.0

        # Nächster Zyklus, Ziel-SOC auf 70 gesunken → Re-Send trotz gleichem Zustand
        await opt._execute(_discharge_decision(70.0), snap)
        assert mock_inverter.async_set_discharge.await_count == 2
        mock_inverter.async_set_discharge.assert_awaited_with(2.5, target_soc=70.0)
        assert opt._prev_target_soc == 70.0


@pytest.mark.asyncio
async def test_target_soc_small_drift_deduplicated(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """Änderung unter 1 % → kein Re-Send (Dedupe greift weiter)."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    snap = _snap()

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=_NOW
    ):
        await opt._execute(_discharge_decision(77.0), snap)
        await opt._execute(_discharge_decision(76.5), snap)
        assert mock_inverter.async_set_discharge.await_count == 1


@pytest.mark.asyncio
async def test_target_soc_drift_not_resent_for_solaredge(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """SolarEdge: NVRAM-Verschleiß — Re-Send nur bei Zustandswechsel."""
    opt = _opt(
        mock_hass, mock_inverter, mock_coordinator, mock_provider,
        **{CONF_INVERTER_TYPE: "solaredge_storedge"},
    )
    snap = _snap()

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=_NOW
    ):
        await opt._execute(_discharge_decision(77.0), snap)
        await opt._execute(_discharge_decision(60.0), snap)
        assert mock_inverter.async_set_discharge.await_count == 1


@pytest.mark.asyncio
async def test_failed_stop_forcible_is_retried(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """stop_forcible → False: _prev_zustand bleibt stehen, nächster Zyklus wiederholt.

    Vorher wurde der Fehlschlag verschluckt — der Inverter blieb dauerhaft im
    erzwungenen Entlademodus (z. B. nach einem Modbus-Verbindungsabriss genau
    im Zyklus des Zustandswechsels).
    """
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._prev_zustand = STATE_ABEND_ENTLADUNG
    snap = _snap()
    normal = Decision(zustand=STATE_NORMAL, ausführung=True)

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=_NOW
    ):
        mock_inverter.async_stop_forcible.return_value = False
        await opt._execute(normal, snap)
        assert opt._prev_zustand == STATE_ABEND_ENTLADUNG  # nicht als erledigt markiert

        # Verbindung wieder da → Retry im nächsten Zyklus erfolgreich
        mock_inverter.async_stop_forcible.return_value = True
        await opt._execute(normal, snap)
        assert mock_inverter.async_stop_forcible.await_count == 2
        assert opt._prev_zustand == STATE_NORMAL


@pytest.mark.asyncio
async def test_failed_discharge_entry_is_retried(
    mock_hass, mock_inverter, mock_coordinator, mock_provider
):
    """Fehlgeschlagener Entladestart wird im nächsten Zyklus wiederholt."""
    opt = _opt(mock_hass, mock_inverter, mock_coordinator, mock_provider)
    opt._prev_zustand = STATE_NORMAL
    snap = _snap()

    with patch(
        "custom_components.eeg_energy_optimizer.optimizer._now", return_value=_NOW
    ):
        mock_inverter.async_set_discharge.return_value = False
        await opt._execute(_discharge_decision(77.0), snap)
        assert opt._prev_zustand == STATE_NORMAL
        assert opt._prev_target_soc == -1.0  # kein erfolgreicher Write

        mock_inverter.async_set_discharge.return_value = True
        await opt._execute(_discharge_decision(77.0), snap)
        assert mock_inverter.async_set_discharge.await_count == 2
        assert opt._prev_zustand == STATE_ABEND_ENTLADUNG
        assert opt._prev_target_soc == 77.0
