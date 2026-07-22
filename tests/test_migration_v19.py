"""Tests for v19 migration: SolarEdge → Driver-Combined-SOC/Capacity-Sensoren.

Bei SolarEdge zeigt die Migration battery_soc_sensor und battery_capacity_sensor
auf die neuen synthetischen Combined-Entities um, damit Frontend (Energy-Flow-
Diagramm liest direkt aus battery_soc_sensor) und Optimizer denselben Wert
sehen. Andere Inverter (Huawei, Fronius, SolaX) bleiben unverändert.
"""

from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_solaredge_v18_to_v19_sets_combined_sensors():
    """SolarEdge-Entry mit i1-Sensoren wird auf Combined-IDs umgestellt."""
    from custom_components.eeg_energy_optimizer import async_migrate_entry

    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    entry = MagicMock()
    entry.version = 18
    entry.data = {
        "inverter_type": "solaredge_storedge",
        "battery_soc_sensor": "sensor.solaredge_i1_b1_state_of_energy",
        "battery_capacity_sensor": "sensor.solaredge_i1_b1_maximum_energy",
        "battery_capacity_kwh": 24.25,
    }

    await async_migrate_entry(hass, entry)

    # v19-spezifischen Call gezielt suchen (seit v20 folgen weitere Calls).
    v19_call = next(
        c for c in hass.config_entries.async_update_entry.call_args_list
        if c.kwargs.get("version") == 19
    )
    args, kwargs = v19_call
    new_data = kwargs.get("data") or args[1]
    assert new_data["battery_soc_sensor"] == "sensor.eeg_energy_optimizer_combined_soc"
    assert new_data["battery_capacity_sensor"] == "sensor.eeg_energy_optimizer_combined_capacity"
    # Manueller Capacity-Fallback wird NICHT gelöscht (User-Nachvollziehbarkeit)
    assert new_data.get("battery_capacity_kwh") == 24.25
    assert kwargs.get("version") == 19


@pytest.mark.asyncio
async def test_non_solaredge_v18_to_v19_unchanged():
    """Huawei/Fronius/SolaX: Sensor-Felder bleiben unangetastet."""
    from custom_components.eeg_energy_optimizer import async_migrate_entry

    for inv_type in ("huawei_sun2000", "fronius_gen24", "solax_gen4"):
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 18
        entry.data = {
            "inverter_type": inv_type,
            "battery_soc_sensor": f"sensor.{inv_type}_battery_soc",
            "battery_capacity_sensor": f"sensor.{inv_type}_battery_capacity",
        }

        await async_migrate_entry(hass, entry)

        v19_call = next(
            c for c in hass.config_entries.async_update_entry.call_args_list
            if c.kwargs.get("version") == 19
        )
        _args, kwargs = v19_call
        new_data = kwargs.get("data") or _args[1]
        # Andere Driver: kein Touch
        assert new_data["battery_soc_sensor"] == f"sensor.{inv_type}_battery_soc"
        assert new_data["battery_capacity_sensor"] == f"sensor.{inv_type}_battery_capacity"
        assert kwargs.get("version") == 19


@pytest.mark.asyncio
async def test_solaredge_already_latest_no_migration():
    """Schon auf aktueller Schema-Version: keine erneute Migration."""
    from custom_components.eeg_energy_optimizer import async_migrate_entry

    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    entry = MagicMock()
    # Aktuelle Schema-Version (config_flow.VERSION). Bei Anhebung hier mitziehen.
    entry.version = 20
    entry.data = {
        "inverter_type": "solaredge_storedge",
        "battery_soc_sensor": "sensor.eeg_energy_optimizer_combined_soc",
    }

    await async_migrate_entry(hass, entry)

    # Keine Update-Calls — Entry ist bereits auf der aktuellen Version
    assert hass.config_entries.async_update_entry.call_count == 0
