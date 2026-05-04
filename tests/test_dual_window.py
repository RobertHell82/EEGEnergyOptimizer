"""Phase 11: Dual-Window-Entladung — Tests for compute_b_window_end,
Reasons-Catalog, Migration v14→v15."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer.optimizer import (
    ALL_REASONS,
    Decision,
    REASON_BEFORE_SLOT_A,
    REASON_BEFORE_SLOT_B,
    REASON_BETWEEN_SLOTS,
    REASON_LABELS_DE,
    REASON_SLOT_A_ACTIVE,
    REASON_SLOT_A_RESERVE_REACHED,
    REASON_SLOT_B_ACTIVE,
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
    REASON_SLOT_B_WINDOW_EXPIRED,
    compute_b_window_end,
)


# ---------------------------------------------------------------------------
# compute_b_window_end — SPEC §3 / SPEC §5
# ---------------------------------------------------------------------------

class TestComputeBWindowEnd:
    """SPEC-Test-Cases aus 11-RESEARCH.md für die adaptive B-Ende-Berechnung."""

    def test_summer_sunrise_5min_dominant(self):
        """Sommer: SA 04:52, cap 07:00, offset 0 → sunrise−5min = 04:47."""
        sunrise = datetime(2026, 6, 21, 4, 52, tzinfo=timezone.utc)
        now = datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "07:00", 0)
        assert result == datetime(2026, 6, 21, 4, 47, tzinfo=timezone.utc)

    def test_winter_sunrise_cap_dominant(self):
        """Winter: SA 07:30, cap 07:00, offset 0 → cap = 07:00."""
        sunrise = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        now = datetime(2026, 12, 21, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "07:00", 0)
        assert result == datetime(2026, 12, 21, 7, 0, tzinfo=timezone.utc)

    def test_transition_sunrise_5min_dominant(self):
        """Übergang: SA 06:00, cap 07:00, offset 0 → sunrise−5min = 05:55."""
        sunrise = datetime(2026, 4, 15, 6, 0, tzinfo=timezone.utc)
        now = datetime(2026, 4, 15, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "07:00", 0)
        assert result == datetime(2026, 4, 15, 5, 55, tzinfo=timezone.utc)

    def test_deep_winter_cap_dominant(self):
        """Tiefer Winter: SA 08:30, cap 07:00, offset 0 → cap = 07:00."""
        sunrise = datetime(2026, 1, 15, 8, 30, tzinfo=timezone.utc)
        now = datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "07:00", 0)
        assert result == datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc)

    def test_morning_offset_one_hour_pause(self):
        """morning_offset=1 dominiert: SA 07:30, cap 07:00, offset 1 → 06:25."""
        sunrise = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        now = datetime(2026, 12, 21, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "07:00", 1)
        assert result == datetime(2026, 12, 21, 6, 25, tzinfo=timezone.utc)

    def test_sunrise_none_returns_none(self):
        """Ohne Sunrise kann Slot B nicht laufen → None."""
        now = datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc)
        assert compute_b_window_end(now, None, "07:00", 0) is None

    def test_b_end_cap_late_evening_still_clamped_by_sunrise(self):
        """Cap weit nach Sunrise: sunrise−5min muss gewinnen (Mutex-Schutz)."""
        sunrise = datetime(2026, 6, 21, 4, 52, tzinfo=timezone.utc)
        now = datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc)
        result = compute_b_window_end(now, sunrise, "23:59", 0)
        # cap weit nach sunrise → sunrise−5min muss gewinnen
        assert result == datetime(2026, 6, 21, 4, 47, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Reasons-Catalog — D-09 additiv
# ---------------------------------------------------------------------------

class TestReasonsCatalog:
    """D-09: Slot-aware Reasons sind additiv im closed-set ALL_REASONS."""

    def test_all_8_new_reasons_in_all_reasons(self):
        new = {
            REASON_BEFORE_SLOT_A,
            REASON_SLOT_A_ACTIVE,
            REASON_SLOT_A_RESERVE_REACHED,
            REASON_BETWEEN_SLOTS,
            REASON_BEFORE_SLOT_B,
            REASON_SLOT_B_ACTIVE,
            REASON_SLOT_B_WINDOW_EXPIRED,
            REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
        }
        assert new.issubset(ALL_REASONS)

    def test_all_new_reasons_have_german_labels(self):
        keys = [
            REASON_BEFORE_SLOT_A,
            REASON_SLOT_A_ACTIVE,
            REASON_SLOT_A_RESERVE_REACHED,
            REASON_BETWEEN_SLOTS,
            REASON_BEFORE_SLOT_B,
            REASON_SLOT_B_ACTIVE,
            REASON_SLOT_B_WINDOW_EXPIRED,
            REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
        ]
        for key in keys:
            assert key in REASON_LABELS_DE
            assert REASON_LABELS_DE[key]  # nicht leer

    def test_decision_default_active_slot_is_none(self):
        """D-10: Decision()-Default für discharge_active_slot ist None."""
        d = Decision()
        assert d.discharge_active_slot is None


# ---------------------------------------------------------------------------
# Migration v14→v15 — D-03 + D-04 + T-11-01-01 / T-11-01-02
# ---------------------------------------------------------------------------

class TestMigrationV14ToV15:
    """Migration setzt slot-spezifische Defaults; SolarEdge bekommt XOR;
    User-Werte bleiben erhalten; v15-Entries werden nicht migriert."""

    @pytest.mark.asyncio
    async def test_non_solaredge_gets_dual_true(self):
        from custom_components.eeg_energy_optimizer import async_migrate_entry
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 14
        entry.data = {"inverter_type": "huawei_sun2000"}
        await async_migrate_entry(hass, entry)
        args, kwargs = hass.config_entries.async_update_entry.call_args
        new_data = kwargs.get("data") or args[1]
        assert new_data["enable_dual_discharge"] is True
        assert new_data["enable_slot_a"] is True
        assert new_data["enable_slot_b"] is True
        assert new_data["discharge_a_start_time"] == "20:00"
        assert new_data["discharge_b_start_time"] == "03:00"
        assert new_data["discharge_b_end_cap"] == "07:00"
        assert new_data["discharge_a_reserve_pct"] == 15
        assert kwargs.get("version") == 15

    @pytest.mark.asyncio
    async def test_solaredge_gets_xor_config(self):
        from custom_components.eeg_energy_optimizer import async_migrate_entry
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 14
        entry.data = {"inverter_type": "solaredge_storedge"}
        await async_migrate_entry(hass, entry)
        args, kwargs = hass.config_entries.async_update_entry.call_args
        new_data = kwargs.get("data") or args[1]
        assert new_data["enable_dual_discharge"] is False
        assert new_data["enable_slot_a"] is True
        assert new_data["enable_slot_b"] is False

    @pytest.mark.asyncio
    async def test_existing_user_values_preserved(self):
        """T-11-01-01: setdefault respektiert User-Overrides."""
        from custom_components.eeg_energy_optimizer import async_migrate_entry
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 14
        entry.data = {
            "inverter_type": "huawei_sun2000",
            "enable_dual_discharge": False,  # User hat explizit deaktiviert
            "discharge_a_start_time": "21:00",  # User-Override
        }
        await async_migrate_entry(hass, entry)
        args, kwargs = hass.config_entries.async_update_entry.call_args
        new_data = kwargs.get("data") or args[1]
        # setdefault muss vorhandene Werte respektieren
        assert new_data["enable_dual_discharge"] is False
        assert new_data["discharge_a_start_time"] == "21:00"
        # Defaults für nicht-gesetzte Keys
        assert new_data["enable_slot_a"] is True
        assert new_data["discharge_b_start_time"] == "03:00"

    @pytest.mark.asyncio
    async def test_migration_idempotent_when_already_v15(self):
        """T-11-01-02: Idempotenz — version=15 triggert keinen Update-Call."""
        from custom_components.eeg_energy_optimizer import async_migrate_entry
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 15
        entry.data = {"inverter_type": "huawei_sun2000"}
        await async_migrate_entry(hass, entry)
        # version<15 ist False → Update-Aufruf für v15-Block darf nicht passieren.
        # Frühere Blöcke (v3..v14) feuern auch nicht weil version=15.
        assert hass.config_entries.async_update_entry.call_count == 0
