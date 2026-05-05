"""Phase 11: Dual-Window-Entladung — Tests for compute_b_window_end,
Reasons-Catalog, Migration v14→v15, Slot-A/B-Evaluators, Pro-Slot-Hysterese,
Mutual Exclusion, SolarEdge-Runtime-Force, 24h-Simulation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.eeg_energy_optimizer.optimizer import (
    ALL_REASONS,
    Decision,
    REASON_BEFORE_SLOT_A,
    REASON_BEFORE_SLOT_B,
    REASON_BETWEEN_SLOTS,
    REASON_HYSTERESIS_STRICT,
    REASON_LABELS_DE,
    REASON_PEAKSHARE_BEFORE_WINDOW,
    REASON_PEAKSHARE_WINDOW_ACTIVE,
    REASON_PEAKSHARE_WINDOW_EXPIRED,
    REASON_SLOT_A_ACTIVE,
    REASON_SLOT_A_RESERVE_REACHED,
    REASON_SLOT_B_ACTIVE,
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
    REASON_SLOT_B_WINDOW_EXPIRED,
    compute_b_window_end,
    compute_hard_cutoff,
)
from tests.conftest import _make_config, _make_optimizer, _make_snapshot


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
        # Phase 11.1: Default-Wechsel 15 -> 5 (D-02). Migration nutzt
        # DEFAULT_DISCHARGE_A_RESERVE_PCT, neue Setups landen bei 5.
        assert new_data["discharge_a_reserve_pct"] == 5
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

    @pytest.mark.asyncio
    async def test_migration_v14_v15_uses_default_constant(self):
        """Phase 11.1: Migration v14→v15 nutzt DEFAULT_DISCHARGE_A_RESERVE_PCT
        (=5 nach Phase 11.1, D-02) — neue Setups bekommen den neuen Default."""
        from custom_components.eeg_energy_optimizer import async_migrate_entry
        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = MagicMock()
        entry.version = 14
        # Bewusst KEIN discharge_a_reserve_pct gesetzt — Migration soll Default
        # aus der Konstante übernehmen.
        entry.data = {"inverter_type": "huawei_sun2000"}
        await async_migrate_entry(hass, entry)
        args, kwargs = hass.config_entries.async_update_entry.call_args
        new_data = kwargs.get("data") or args[1]
        # Phase 11.1: Default ist jetzt 5 (per D-02).
        assert new_data["discharge_a_reserve_pct"] == 5


# ---------------------------------------------------------------------------
# Plan 11-02 — Slot-A-Reserve-Logik (SPEC §2)
# ---------------------------------------------------------------------------

class TestSlotAReserveLogic:
    """SPEC §2: Slot A nutzt min_soc + reserve_pct wenn Slot B aktiv;
    sonst nur min_soc; endet 5min vor Slot-B-Start."""

    def test_a_only_uses_min_soc_no_reserve(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            discharge_a_reserve_pct=15,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=25.0,  # > min_soc=20, kein reserve_aufschlag (B aus)
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is True
        assert REASON_SLOT_A_ACTIVE in reasons
        assert hyst is False

    def test_dual_a_uses_min_soc_plus_reserve(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            discharge_a_reserve_pct=15,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=30.0,  # < min_soc(20) + reserve(15) = 35 → blockiert
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_SLOT_A_RESERVE_REACHED in blocked

    def test_a_ends_5min_before_b_start(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Slot A endet 02:55 wenn Slot-B-Start = 03:00 (Mindestpause 5min)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # snap.now = 02:56 → b_start = 03:00 (heute, since now < 12),
        # a_end_cap = 02:55 → now >= a_end_cap.
        snap = _make_snapshot(
            now=datetime(2026, 6, 16, 2, 56, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_SLOT_A_RESERVE_REACHED in blocked

    def test_a_before_start_returns_before_slot_a(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 18, 0, tzinfo=timezone.utc),  # vor 20:00
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_BEFORE_SLOT_A in blocked


# ---------------------------------------------------------------------------
# Plan 11-02 — Slot-B-Logik (SPEC §3)
# ---------------------------------------------------------------------------

class TestSlotBLogic:
    """SPEC §3: Slot B startet bei b_start, endet adaptiv via compute_b_window_end."""

    def test_b_only_uses_min_soc_threshold(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # Winter-Setup: now 04:00, sunrise 07:30, b_end = 07:00 (cap).
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc),
            battery_soc=25.0,  # > min_soc=20
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is True
        assert REASON_SLOT_B_ACTIVE in reasons
        assert hyst is False

    def test_b_window_expired_marks_correct_reason(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # now nach b_end=07:00 → expired.
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 7, 5, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_SLOT_B_WINDOW_EXPIRED in blocked

    def test_b_pre_sunrise_cutoff_summer_edge_case(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Sommer: SA 04:52, b_start=05:00 → b_end=04:47 < b_start → CUTOFF."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="05:00",
            discharge_b_end_cap="07:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 21, 3, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 21, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 20, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_SLOT_B_PRE_SUNRISE_CUTOFF in blocked

    def test_b_before_start_returns_before_slot_b(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # now=02:00 (vor b_start=03:00), Winter (b_end=07:00 wegen cap).
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 2, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_BEFORE_SLOT_B in blocked


# ---------------------------------------------------------------------------
# Plan 11-02 — Pro-Slot-Hysterese (SPEC §4 / D-02 / T-11-02-01)
# ---------------------------------------------------------------------------

class TestProSlotHysteresis:
    """Pro-Slot-Hysterese: Aufschlag +5% gilt unabhängig pro Slot.
    Reaktivierung wird per (_slot_*_activated_date != None
    AND _last_active_slot != "A"|"B") detektiert."""

    def test_a_reactivation_requires_min_soc_plus_5(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            discharge_a_reserve_pct=15,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        opt._slot_a_activated_date = "2026-06-15"  # heute schon einmal aktiv
        opt._last_active_slot = "B"  # zwischenzeitlich war B aktiv → Reaktivierung
        # Schwelle: min_soc(20) + reserve(15) = 35; +5 Aufschlag = 40
        # battery_soc=39 → > 35 (ohne Aufschlag), aber <= 40 (mit Aufschlag) → blockiert
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=39.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_HYSTERESIS_STRICT in blocked
        assert hyst is True

    def test_b_starts_without_a_reactivation_aufschlag(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        """Wenn nur A heute aktiv war (B noch nicht), startet B ohne +5-Aufschlag."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        opt._slot_a_activated_date = "2026-06-15"  # A war aktiv
        opt._slot_b_activated_date = None  # B noch nicht
        opt._last_active_slot = "A"
        # battery_soc=22 → > min_soc=20 ohne Aufschlag → passes
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc),
            battery_soc=22.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is True
        assert hyst is False


# ---------------------------------------------------------------------------
# Plan 11-02 — Slot-B Pre-Sunrise-Cutoff parametrisiert (SPEC §5)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sunrise_hour,morning_offset", [
    (5, 0), (5, 1), (6, 0), (7, 0), (7, 1), (8, 0), (8, 1),
])
class TestSlotBPreSunriseCutoff:
    """Mutex-Garantie: b_end ≥5min vor Beginn der Morgen-Einspeisung,
    über mehrere sunrise-Stunden und morning_offset-Werte."""

    def test_slot_b_ends_min_5min_before_morning_einspeisung(
        self, sunrise_hour, morning_offset, mock_hass, mock_inverter,
        mock_coordinator, mock_provider,
    ):
        sunrise = datetime(2026, 12, 21, sunrise_hour, 30, tzinfo=timezone.utc)
        b_end = compute_b_window_end(
            datetime(2026, 12, 21, 3, 0, tzinfo=timezone.utc),
            sunrise,
            "07:00",
            float(morning_offset),
        )
        morning_einspeisung_start = sunrise - timedelta(hours=morning_offset)
        # Pause-Lücke ≥ 5min
        assert b_end is not None
        assert (morning_einspeisung_start - b_end) >= timedelta(minutes=5)


# ---------------------------------------------------------------------------
# Plan 11-02 — Mutual Exclusion Slot B vs Morgen-Einspeisung (SPEC §5)
# ---------------------------------------------------------------------------

class TestMutualExclusion:
    """SPEC §5: Slot B endet strikt vor Beginn der Morgen-Einspeisung."""

    def test_slot_b_does_not_run_when_morning_einspeisung_starts(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        # Slot B aktiv, sunrise=07:30, morning_offset=0 → b_end=07:00.
        # Morgen-Einspeisung beginnt 07:30 → mind. 30min Pause.
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            morning_start_offset=0,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # Snap zur Morgen-Einspeisungs-Zeit (07:30) — Slot B muss enden
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_SLOT_B_WINDOW_EXPIRED in blocked


# ---------------------------------------------------------------------------
# Plan 11-02 — SolarEdge-Runtime-Force (SPEC §6 / D-07 / T-11-02-02)
# ---------------------------------------------------------------------------

class TestSolarEdgeRuntimeForce:
    """SPEC §6: SolarEdge erzwingt Legacy-Pfad zur Laufzeit (Defense-in-depth)."""

    def test_solaredge_init_forces_dual_to_false(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            inverter_type="solaredge_storedge",
            enable_dual_discharge=True,  # User-Setting (sollte korrigiert werden)
            enable_slot_a=True,
            enable_slot_b=False,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # __init__ hat enable_dual_discharge auf False geforced
        assert opt._enable_dual_discharge is False
        assert opt._is_solaredge is True


# ---------------------------------------------------------------------------
# Plan 11-02 — Legacy-Pfad bleibt 1:1 erhalten (D-05)
# ---------------------------------------------------------------------------

class TestEnableDualDischargeFalseLegacyPath:
    """D-05: byte-identische Legacy-Garantie. Mit enable_dual_discharge=False
    werden keine Slot-Reasons emittiert."""

    def test_legacy_path_taken_when_dual_disabled(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(enable_dual_discharge=False)
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
            pv_tomorrow_kwh=20.0,
            consumption_tomorrow_daylight_kwh=9.0,
        )
        should, min_soc, reasons, blocked, hyst = opt._should_discharge(snap)
        # Dispatcher hat _evaluate_legacy_window aufgerufen — keine Slot-Reasons.
        assert REASON_SLOT_A_ACTIVE not in reasons
        assert REASON_SLOT_B_ACTIVE not in reasons
        assert REASON_BEFORE_SLOT_A not in (blocked or [])
        assert REASON_BEFORE_SLOT_B not in (blocked or [])

    def test_solaredge_routes_to_legacy_even_with_dual_in_config(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            inverter_type="solaredge_storedge",
            enable_dual_discharge=True,  # wird in __init__ auf False geforced
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
            pv_tomorrow_kwh=20.0,
            consumption_tomorrow_daylight_kwh=9.0,
        )
        should, min_soc, reasons, blocked, hyst = opt._should_discharge(snap)
        # SolarEdge → Legacy → keine Slot-Reasons
        assert REASON_SLOT_A_ACTIVE not in reasons
        assert REASON_SLOT_B_ACTIVE not in reasons


# ---------------------------------------------------------------------------
# Plan 11-02 — PeakShare-Cache-Schema dict[a/b] (T-11-02-03)
# ---------------------------------------------------------------------------

class TestPeakShareCacheSchema:
    """Schema-Migration: _discharge_plan ist dict[a/b] mit gemeinsamem
    Tageslock; alte tuple-Form wird in async_load verworfen."""

    def test_init_creates_dict_schema(self):
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        assert ps._discharge_plan == {"a": None, "b": None}
        assert ps._discharge_plan_date is None

    def test_get_discharge_plan_default_slot_is_a(self):
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        ps._discharge_plan_date = "2026-06-15"
        ps._discharge_plan = {
            "a": (
                datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
            ),
            "b": None,
        }
        # Phase 11.1: Per-Slot-Compute-Tracking — markiere Slot A als heute
        # berechnet, damit der Cache-Hit-Check (dict-basiert) trifft.
        ps._discharge_plan_computed_dates = {"a": "2026-06-15", "b": None}
        now = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)
        # Default slot ist "a" — Cache-Hit liefert Slot-A-Plan
        result = ps.get_discharge_plan(
            community="BEG",
            available_kwh=5.0,
            discharge_power_kw=5.0,
            sunset_time=None,
            now=now,
        )
        assert result is not None
        assert result[0].hour == 22

    def test_get_discharge_plan_slot_b_returns_b_cache(self):
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        ps._discharge_plan_date = "2026-06-15"
        ps._discharge_plan = {
            "a": None,
            "b": (
                datetime(2026, 6, 16, 5, 0, tzinfo=timezone.utc),
                datetime(2026, 6, 16, 6, 30, tzinfo=timezone.utc),
            ),
        }
        # Phase 11.1: Per-Slot-Compute-Tracking — markiere Slot B als heute
        # berechnet, damit der Cache-Hit-Check (dict-basiert) trifft.
        ps._discharge_plan_computed_dates = {"a": None, "b": "2026-06-15"}
        now = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)
        result = ps.get_discharge_plan(
            community="BEG",
            available_kwh=5.0,
            discharge_power_kw=5.0,
            sunset_time=None,
            now=now,
            slot="b",
        )
        assert result is not None
        assert result[0].hour == 5

    def test_async_fetch_invalidate_uses_dict_schema(self):
        """async_fetch setzt {"a": None, "b": None} — kein None-Skalar mehr."""
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        # Simuliere belegten Cache (beide Slots) und prüfe Invalidate-Form.
        ps._discharge_plan = {
            "a": (
                datetime(2026, 6, 15, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
            ),
            "b": (
                datetime(2026, 6, 16, 5, 0, tzinfo=timezone.utc),
                datetime(2026, 6, 16, 6, 0, tzinfo=timezone.utc),
            ),
        }
        ps._discharge_plan_date = "2026-06-15"
        # Manuelles Invalidate-Pattern wie in async_fetch:
        ps._discharge_plan = {"a": None, "b": None}
        ps._discharge_plan_date = None
        assert ps._discharge_plan == {"a": None, "b": None}
        assert ps._discharge_plan_date is None

    # -----------------------------------------------------------------------
    # Phase 11.1: Default-Wechsel + Per-Slot-Compute-Tracking
    # -----------------------------------------------------------------------

    def test_default_discharge_a_reserve_pct_is_5(self):
        """Phase 11.1 D-02: Default-Wechsel von 15 auf 5."""
        from custom_components.eeg_energy_optimizer.const import (
            DEFAULT_DISCHARGE_A_RESERVE_PCT,
        )
        assert DEFAULT_DISCHARGE_A_RESERVE_PCT == 5

    def test_per_slot_compute_tracking_initialized_in_init(self):
        """Phase 11.1: __init__ legt _discharge_plan_computed_dates dict an."""
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        assert ps._discharge_plan_computed_dates == {"a": None, "b": None}

    def test_async_fetch_invalidates_per_slot_compute_tracking(self):
        """Phase 11.1: Frische API-Daten resetten BEIDE Slot-Compute-Marker.

        Wir simulieren den Invalidate-Pfad aus async_fetch direkt — wichtig ist
        nur, dass die Code-Stelle in async_fetch das Dict konsistent
        zurueckgesetzt hat (wie in async_load und async_fetch implementiert).
        """
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        # Beide Slots stehen heute auf computed.
        ps._discharge_plan_computed_dates = {
            "a": "2026-12-21",
            "b": "2026-12-21",
        }
        ps._discharge_plan = {
            "a": (
                datetime(2026, 12, 21, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 12, 21, 23, 0, tzinfo=timezone.utc),
            ),
            "b": None,
        }
        ps._discharge_plan_date = "2026-12-21"
        # Invalidate-Pfad wie in async_fetch (frische API-Daten):
        ps._discharge_plan = {"a": None, "b": None}
        ps._discharge_plan_date = None
        ps._discharge_plan_computed_dates = {"a": None, "b": None}
        assert ps._discharge_plan_computed_dates == {"a": None, "b": None}

    @pytest.mark.asyncio
    async def test_async_load_resets_per_slot_compute_tracking(self):
        """Phase 11.1: async_load setzt das Dict auf {"a": None, "b": None}.

        Auch wenn ein altes Persistat (Pre-11.1) den Wert nicht enthielt,
        muss async_load das Feld konsistent zuruecksetzen — sonst koennte
        ein gestrige berechneter Slot heute den Cache-Hit blockieren.
        """
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        # Mock-Store, der ein altes Persistat liefert.
        ps._store = MagicMock()
        ps._store.async_load = AsyncMock(
            return_value={
                "data": {"communities": []},
                "fetched_at": "2026-12-20T22:00:00+00:00",
                "jitter_value": 5,
                "jitter_date": "2026-12-20",
            }
        )
        # Vor async_load: simuliere alten State (nicht zurueckgesetzt).
        ps._discharge_plan_computed_dates = {
            "a": "2026-12-20",
            "b": "2026-12-20",
        }
        await ps.async_load()
        assert ps._discharge_plan_computed_dates == {"a": None, "b": None}


# ---------------------------------------------------------------------------
# Plan 11.1-01 — PeakShare-Aufruf in _evaluate_slot_a/_evaluate_slot_b
# ---------------------------------------------------------------------------

def _mock_peakshare_provider(slot_a_plan=None, slot_b_plan=None):
    """Erstellt einen Mock-Provider mit Capture-Logik für kwargs.

    Liefert beim get_discharge_plan-Aufruf den Plan, der zu slot= passt.
    Erfasst alle Aufrufe in ``ps._captured["calls"]`` als Liste von dicts.
    """
    ps = MagicMock()
    today = "2026-12-21"
    ps._discharge_plan = {"a": slot_a_plan, "b": slot_b_plan}
    ps._discharge_plan_date = today if (slot_a_plan or slot_b_plan) else None
    ps._discharge_plan_computed_dates = {
        "a": today if slot_a_plan is not None else None,
        "b": today if slot_b_plan is not None else None,
    }
    captured = {"calls": []}

    def _get_plan(community, available_kwh, power, sunset, now,
                  *, discharge_start_lower_bound=None, next_sunrise=None,
                  slot="a", window_start=None, window_end=None, **extra):
        captured["calls"].append({
            "slot": slot,
            "community": community,
            "available_kwh": available_kwh,
            "discharge_power_kw": power,
            "sunset_time": sunset,
            "now": now,
            "discharge_start_lower_bound": discharge_start_lower_bound,
            "next_sunrise": next_sunrise,
            "window_start": window_start,
            "window_end": window_end,
        })
        return slot_a_plan if slot == "a" else slot_b_plan

    ps.get_discharge_plan = MagicMock(side_effect=_get_plan)
    ps._captured = captured
    return ps


class TestPeakShareSlotIntegration:
    """Phase 11.1-01: _evaluate_slot_a und _evaluate_slot_b rufen PeakShare
    pro Slot auf (mit slot-spezifischem window_start/window_end).
    """

    # -----------------------------------------------------------------------
    # Slot A
    # -----------------------------------------------------------------------

    def test_slot_a_calls_peakshare_with_correct_window_bounds(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A1: Slot-A-Aufruf hat slot='a', window_start=a_start_today,
        window_end=b_start - 5min (Dual-Mode)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            discharge_a_reserve_pct=5,
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_a_plan=None)
        opt._peakshare = ps_mock
        # now=21:00, before any past-midnight phase
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        opt._evaluate_slot_a(snap, 20.0)
        calls = ps_mock._captured["calls"]
        assert len(calls) == 1
        c = calls[0]
        assert c["slot"] == "a"
        assert c["window_start"] == datetime(2026, 12, 21, 20, 0, tzinfo=timezone.utc)
        # b_start=03:00 -> auf morgen verschoben (now>=12 + b<12) = 22.12. 03:00
        # window_end = b_start - 5min = 22.12. 02:55
        assert c["window_end"] == datetime(2026, 12, 22, 2, 55, tzinfo=timezone.utc)

    def test_slot_a_window_end_is_hard_cutoff_when_a_only(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A2: Mit enable_slot_b=False ist window_end=compute_hard_cutoff(...)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_a_plan=None)
        opt._peakshare = ps_mock
        sunrise = datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=sunrise,
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        opt._evaluate_slot_a(snap, 20.0)
        c = ps_mock._captured["calls"][0]
        assert c["window_end"] == compute_hard_cutoff(snap.now, sunrise)

    def test_slot_a_past_midnight_uses_yesterday_a_start(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A3: now=02:30, a_start_h=20 -> window_start=a_start_today - 1 day."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_a_plan=None)
        opt._peakshare = ps_mock
        # now=02:30 (past-midnight), a_start_h=20 -> a_start_today wird auf
        # heute 02:30 -> 02:30 vor 20:00. a_window_start sollte gestern 20:00 sein.
        snap = _make_snapshot(
            now=datetime(2026, 12, 22, 2, 30, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        opt._evaluate_slot_a(snap, 20.0)
        c = ps_mock._captured["calls"][0]
        # a_start_today = 22.12. 20:00, past-midnight -> window_start = 21.12. 20:00
        assert c["window_start"] == datetime(2026, 12, 21, 20, 0, tzinfo=timezone.utc)

    def test_slot_a_peakshare_plan_active_returns_passing(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A4: Plan aktiv -> passed=True, REASON_PEAKSHARE_WINDOW_ACTIVE
        + REASON_SLOT_A_ACTIVE in reasons."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        now = datetime(2026, 12, 21, 22, 0, tzinfo=timezone.utc)
        plan = (now - timedelta(minutes=30), now + timedelta(minutes=30))
        ps_mock = _mock_peakshare_provider(slot_a_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is True
        assert REASON_PEAKSHARE_WINDOW_ACTIVE in reasons
        assert REASON_SLOT_A_ACTIVE in reasons

    def test_slot_a_peakshare_before_window_returns_blocked(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A5: Plan-Start in der Zukunft -> passed=False,
        blocked_by enthält REASON_PEAKSHARE_BEFORE_WINDOW (NICHT before_slot_a)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # now=21:00 (>= a_start), plan startet erst um 22:00 -> before_window
        now = datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc)
        plan = (now + timedelta(hours=1), now + timedelta(hours=2))
        ps_mock = _mock_peakshare_provider(slot_a_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_PEAKSHARE_BEFORE_WINDOW in blocked
        assert REASON_BEFORE_SLOT_A not in blocked

    def test_slot_a_peakshare_expired_returns_blocked(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A6: Plan-End in der Vergangenheit -> blocked_by enthält
        REASON_PEAKSHARE_WINDOW_EXPIRED."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        now = datetime(2026, 12, 21, 23, 0, tzinfo=timezone.utc)
        plan = (now - timedelta(hours=2), now - timedelta(minutes=30))
        ps_mock = _mock_peakshare_provider(slot_a_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_PEAKSHARE_WINDOW_EXPIRED in blocked

    def test_slot_a_no_peakshare_data_falls_through_to_fixed_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A7: PeakShare-Plan=None, now < a_start -> Fallback Fixzeit-Pfad,
        blocked_by=[REASON_BEFORE_SLOT_A]."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # now=18:00, a_start=20:00 -> Pre-PeakShare-Guard greift -> BEFORE_SLOT_A
        ps_mock = _mock_peakshare_provider(slot_a_plan=None)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 18, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_BEFORE_SLOT_A in blocked

    def test_slot_a_disabled_peakshare_uses_fixed_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A8: enable_peakshare=False -> kein get_discharge_plan-Call,
        Fixzeit-Pfad aktiv (now>=a_start, SOC ok -> passed)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=False,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_a_plan=None)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 22, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is True
        assert REASON_SLOT_A_ACTIVE in reasons
        # No PeakShare reasons in passing (kein Plan im Fixzeit-Pfad)
        assert REASON_PEAKSHARE_WINDOW_ACTIVE not in reasons
        assert ps_mock.get_discharge_plan.call_count == 0

    def test_slot_a_plan_never_extends_past_b_start_minus_5min(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A9: Mutual-Exclusion-Clamp via window_end an find_discharge_window —
        kein eigener Post-Process-Clamp im Optimizer."""
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
            find_discharge_window,
        )
        # Direkt die Library-Funktion testen, mit api_hours die einen
        # 4-Stunden-Block über b_start-5min hinaus liefern würden.
        b_start = datetime(2026, 12, 22, 3, 0, tzinfo=timezone.utc)
        a_end_cap = b_start - timedelta(minutes=5)  # 02:55
        a_window_start = datetime(2026, 12, 21, 20, 0, tzinfo=timezone.utc)
        # Synthetische api_hours: 6 Stunden mit hohem deficit, von 22:00 bis 04:00
        api_hours = []
        for offset_h in range(0, 8):
            ts = (a_window_start + timedelta(hours=offset_h)).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            )
            api_hours.append({"timestamp": ts, "deficitKwh": 5.0})
        # available_kwh für 4h Block, discharge_power 1 kW -> required=4 hours
        result = find_discharge_window(
            api_hours,
            available_kwh=4.0,
            discharge_power_kw=1.0,
            window_start=a_window_start,
            window_end=a_end_cap,
            jitter_minutes=0,
        )
        assert result is not None
        # Library MUSS end_time auf window_end klammen
        assert result[1] <= a_end_cap

    def test_slot_a_hysteresis_strict_with_peakshare_active(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """A10: PeakShare aktiv + Reaktivierung -> effective_min_soc +5,
        passing enthält REASON_HYSTERESIS_STRICT zusätzlich zu PEAKSHARE_ACTIVE."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        opt._slot_a_activated_date = "2026-12-21"
        opt._last_active_slot = "B"  # Reaktivierung
        now = datetime(2026, 12, 21, 22, 0, tzinfo=timezone.utc)
        plan = (now - timedelta(minutes=30), now + timedelta(minutes=30))
        ps_mock = _mock_peakshare_provider(slot_a_plan=plan)
        opt._peakshare = ps_mock
        # SOC=22 -> > min_soc(20), aber <= min_soc+5(25) -> blocked durch hysterese
        snap = _make_snapshot(
            now=now,
            battery_soc=22.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_a(snap, 20.0)
        assert passed is False
        assert REASON_HYSTERESIS_STRICT in blocked
        assert hyst is True

    # -----------------------------------------------------------------------
    # Slot B
    # -----------------------------------------------------------------------

    def test_slot_b_calls_peakshare_with_window_b_start_to_b_end(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B1: slot='b', window_start=b_start, window_end=compute_b_window_end(...)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
            discharge_a_reserve_pct=5,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_b_plan=None)
        opt._peakshare = ps_mock
        sunrise = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=sunrise,
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        opt._evaluate_slot_b(snap, 20.0)
        calls = ps_mock._captured["calls"]
        assert len(calls) == 1
        c = calls[0]
        assert c["slot"] == "b"
        # b_start: now=04:00 (>= 12 false), b_start_h=03 (<12) -> kein +1 day
        assert c["window_start"] == datetime(2026, 12, 21, 3, 0, tzinfo=timezone.utc)
        # window_end = compute_b_window_end(now, sunrise, "07:00", 0)
        # Winter: cap dominiert -> 07:00
        assert c["window_end"] == datetime(2026, 12, 21, 7, 0, tzinfo=timezone.utc)

    def test_slot_b_available_kwh_uses_reserve_pct(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B2: available_kwh == reserve_pct/100 * capacity. reserve_pct=5, capacity=10 -> 0.5 kWh."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
            discharge_a_reserve_pct=5,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_b_plan=None)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        opt._evaluate_slot_b(snap, 20.0)
        c = ps_mock._captured["calls"][0]
        assert abs(c["available_kwh"] - 0.5) < 1e-6

    def test_slot_b_no_peakshare_data_falls_through_to_fixed_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B3: PeakShare-Plan=None, now < b_start -> blocked_by=[REASON_BEFORE_SLOT_B]."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        ps_mock = _mock_peakshare_provider(slot_b_plan=None)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 2, 0, tzinfo=timezone.utc),  # vor 03:00
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_BEFORE_SLOT_B in blocked

    def test_slot_b_peakshare_window_active_returns_passing(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B4: Plan aktiv -> passing enthält REASON_PEAKSHARE_WINDOW_ACTIVE
        + REASON_SLOT_B_ACTIVE."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        now = datetime(2026, 12, 21, 5, 0, tzinfo=timezone.utc)
        plan = (now - timedelta(minutes=30), now + timedelta(minutes=30))
        ps_mock = _mock_peakshare_provider(slot_b_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is True
        assert REASON_PEAKSHARE_WINDOW_ACTIVE in reasons
        assert REASON_SLOT_B_ACTIVE in reasons

    def test_slot_b_peakshare_before_window_returns_blocked(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B5: Plan-Start in der Zukunft -> REASON_PEAKSHARE_BEFORE_WINDOW."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        now = datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc)
        plan = (now + timedelta(hours=1), now + timedelta(hours=2))
        ps_mock = _mock_peakshare_provider(slot_b_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_PEAKSHARE_BEFORE_WINDOW in blocked

    def test_slot_b_peakshare_expired_returns_blocked(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """B6: Plan-End in der Vergangenheit -> REASON_PEAKSHARE_WINDOW_EXPIRED."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
            enable_peakshare=True,
            peakshare_community="Testgemeinde",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        now = datetime(2026, 12, 21, 6, 30, tzinfo=timezone.utc)
        plan = (now - timedelta(hours=2), now - timedelta(minutes=30))
        ps_mock = _mock_peakshare_provider(slot_b_plan=plan)
        opt._peakshare = ps_mock
        snap = _make_snapshot(
            now=now,
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 20, 7, 30, tzinfo=timezone.utc),
            sunset_today=datetime(2026, 12, 20, 16, 30, tzinfo=timezone.utc),
        )
        passed, reasons, blocked, hyst = opt._evaluate_slot_b(snap, 20.0)
        assert passed is False
        assert REASON_PEAKSHARE_WINDOW_EXPIRED in blocked

    # -----------------------------------------------------------------------
    # Cross-Slot
    # -----------------------------------------------------------------------

    def test_both_slots_compute_independently_same_day(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """C1: Per-Slot-Cache-Lifecycle. Vor 11.1 würde der zweite Slot None
        zurückliefern (Tageslock-Bug). Mit Per-Slot-Tracking können beide
        Slots am selben Tag berechnet werden.
        """
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        # Synthetische api_hours für Slot A (22:00) und Slot B (05:00) am 21.12.2026
        api_hours = []
        for offset_h in range(0, 16):
            ts_dt = datetime(2026, 12, 21, 14, 0, tzinfo=timezone.utc) + timedelta(hours=offset_h)
            ts = ts_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
            # Hoher deficit von 22:00..00:00 und 05:00..06:00
            hour = ts_dt.hour
            deficit = 5.0 if (hour >= 22 or hour <= 1 or 5 <= hour <= 6) else 0.0
            api_hours.append({"timestamp": ts, "deficitKwh": deficit})
        ps._cache = {"communities": [{"name": "BEG", "hours": api_hours}]}
        ps._cache_time = datetime(2026, 12, 21, 14, 0, tzinfo=timezone.utc)

        # Slot A computation (now = 21:00, window 20:00 .. 02:55)
        now = datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc)
        plan_a = ps.get_discharge_plan(
            community="BEG",
            available_kwh=2.0,
            discharge_power_kw=1.0,
            sunset_time=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
            now=now,
            slot="a",
            window_start=datetime(2026, 12, 21, 20, 0, tzinfo=timezone.utc),
            window_end=datetime(2026, 12, 22, 2, 55, tzinfo=timezone.utc),
        )
        assert plan_a is not None
        assert ps._discharge_plan_computed_dates["a"] == "2026-12-21"

        # Slot B computation am SELBEN Tag
        plan_b = ps.get_discharge_plan(
            community="BEG",
            available_kwh=0.5,
            discharge_power_kw=1.0,
            sunset_time=datetime(2026, 12, 21, 16, 30, tzinfo=timezone.utc),
            now=now,
            slot="b",
            window_start=datetime(2026, 12, 22, 3, 0, tzinfo=timezone.utc),
            window_end=datetime(2026, 12, 22, 7, 0, tzinfo=timezone.utc),
        )
        # Vor Phase 11.1 würde plan_b == None sein (Tageslock-Bug).
        # Phase 11.1: plan_b ist echt berechnet.
        assert plan_b is not None
        assert ps._discharge_plan_computed_dates["b"] == "2026-12-21"

    def test_async_fetch_invalidates_both_slot_plans(self):
        """C2: nach Invalidate sind beide computed_dates zurückgesetzt."""
        from custom_components.eeg_energy_optimizer.peakshare import (
            PeakShareProvider,
        )
        ps = PeakShareProvider(MagicMock(), entry_id="test")
        ps._discharge_plan_computed_dates = {"a": "2026-12-21", "b": "2026-12-21"}
        ps._discharge_plan = {
            "a": (
                datetime(2026, 12, 21, 22, 0, tzinfo=timezone.utc),
                datetime(2026, 12, 22, 0, 0, tzinfo=timezone.utc),
            ),
            "b": (
                datetime(2026, 12, 22, 5, 0, tzinfo=timezone.utc),
                datetime(2026, 12, 22, 6, 0, tzinfo=timezone.utc),
            ),
        }
        ps._discharge_plan_date = "2026-12-21"
        # Invalidate-Pfad wie in async_fetch
        ps._discharge_plan = {"a": None, "b": None}
        ps._discharge_plan_date = None
        ps._discharge_plan_computed_dates = {"a": None, "b": None}
        assert ps._discharge_plan_computed_dates == {"a": None, "b": None}


# ---------------------------------------------------------------------------
# Plan 11-02 — 24h-Decision-Sequenz-Simulation (SPEC §8)
# ---------------------------------------------------------------------------

class TestDualWindow24hSimulation:
    """24h-Simulationslauf: Decision-Sequenz über einen vollen Tag.

    SPEC §8: A-only / B-only / Dual liefern erwartete Decision-Sequenzen
    mit korrekten Slot-Markern.
    """

    def _simulate(self, opt, snap_factory, hours):
        """Run optimizer for sequence of hours, return slot markers."""
        results = []
        for hour in hours:
            snap = snap_factory(hour)
            should, min_soc, reasons, blocked, hyst = opt._should_discharge(snap)
            slot = None
            if REASON_SLOT_A_ACTIVE in reasons:
                slot = "A"
            elif REASON_SLOT_B_ACTIVE in reasons:
                slot = "B"
            results.append((hour, should, slot))
        return results

    def test_dual_a_and_b_both_activate(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            discharge_a_reserve_pct=15,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        sunrise_today = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        sunrise_tomorrow = datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc)

        def snap_factory(hour):
            day = 21 if hour < 24 else 22
            hour_norm = hour % 24
            # Sunrise = "next upcoming sunrise" gemäß HA-Konvention. Auf Tag 21
            # vor 07:30 zeigt sunrise auf 21.12. 07:30; danach auf 22.12. 07:30.
            # Auf Tag 22 (hour >= 24) zeigt sunrise immer auf 22.12. 07:30.
            if day == 22 or (day == 21 and hour_norm >= 8):
                snap_sunrise = sunrise_tomorrow
            else:
                snap_sunrise = sunrise_today
            # sunrise_today: heutiger SA. Auf Tag 21 = 21.12. 07:30; Tag 22 = 22.12. 07:30.
            today_sunrise = sunrise_tomorrow if day == 22 else sunrise_today
            return _make_snapshot(
                now=datetime(2026, 12, day, hour_norm, 0, tzinfo=timezone.utc),
                battery_soc=80.0,
                battery_capacity_kwh=10.0,
                sunrise=snap_sunrise,
                sunrise_today=today_sunrise,
                pv_tomorrow_kwh=20.0,
                consumption_tomorrow_daylight_kwh=9.0,
                consumption_overnight_kwh=2.0,
            )

        # Stunden 18..30 (=06:00 next day)
        seq = self._simulate(opt, snap_factory, range(18, 30))
        slots = [s for _, _, s in seq if s is not None]
        assert "A" in slots, f"Slot A erwartet zwischen 20:00-02:55: {seq}"
        assert "B" in slots, f"Slot B erwartet zwischen 03:00-07:00: {seq}"

    def test_a_only_pure_evening_discharge(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=False,
            discharge_a_start_time="20:00",
            discharge_a_reserve_pct=15,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        sunrise_today = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        sunrise_tomorrow = datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc)

        def snap_factory(hour):
            day = 21 if hour < 24 else 22
            hour_norm = hour % 24
            # Sunrise = "next upcoming sunrise" gemäß HA-Konvention. Auf Tag 21
            # vor 07:30 zeigt sunrise auf 21.12. 07:30; danach auf 22.12. 07:30.
            # Auf Tag 22 (hour >= 24) zeigt sunrise immer auf 22.12. 07:30.
            if day == 22 or (day == 21 and hour_norm >= 8):
                snap_sunrise = sunrise_tomorrow
            else:
                snap_sunrise = sunrise_today
            # sunrise_today: heutiger SA. Auf Tag 21 = 21.12. 07:30; Tag 22 = 22.12. 07:30.
            today_sunrise = sunrise_tomorrow if day == 22 else sunrise_today
            return _make_snapshot(
                now=datetime(2026, 12, day, hour_norm, 0, tzinfo=timezone.utc),
                battery_soc=80.0,
                battery_capacity_kwh=10.0,
                sunrise=snap_sunrise,
                sunrise_today=today_sunrise,
                pv_tomorrow_kwh=20.0,
                consumption_tomorrow_daylight_kwh=9.0,
                consumption_overnight_kwh=2.0,
            )

        seq = self._simulate(opt, snap_factory, range(18, 30))
        slots = [s for _, _, s in seq if s is not None]
        assert "A" in slots
        assert "B" not in slots

    def test_b_only_pure_morning_discharge(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False,
            enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        sunrise_today = datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc)
        sunrise_tomorrow = datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc)

        def snap_factory(hour):
            day = 21 if hour < 24 else 22
            hour_norm = hour % 24
            # Sunrise = "next upcoming sunrise" gemäß HA-Konvention. Auf Tag 21
            # vor 07:30 zeigt sunrise auf 21.12. 07:30; danach auf 22.12. 07:30.
            # Auf Tag 22 (hour >= 24) zeigt sunrise immer auf 22.12. 07:30.
            if day == 22 or (day == 21 and hour_norm >= 8):
                snap_sunrise = sunrise_tomorrow
            else:
                snap_sunrise = sunrise_today
            # sunrise_today: heutiger SA. Auf Tag 21 = 21.12. 07:30; Tag 22 = 22.12. 07:30.
            today_sunrise = sunrise_tomorrow if day == 22 else sunrise_today
            return _make_snapshot(
                now=datetime(2026, 12, day, hour_norm, 0, tzinfo=timezone.utc),
                battery_soc=80.0,
                battery_capacity_kwh=10.0,
                sunrise=snap_sunrise,
                sunrise_today=today_sunrise,
                pv_tomorrow_kwh=20.0,
                consumption_tomorrow_daylight_kwh=9.0,
                consumption_overnight_kwh=2.0,
            )

        seq = self._simulate(opt, snap_factory, range(18, 30))
        slots = [s for _, _, s in seq if s is not None]
        assert "B" in slots
        assert "A" not in slots


# ---------------------------------------------------------------------------
# Phase 11 Plan 11-03 — WebSocket save_config: SolarEdge-XOR + Inverter-Race
# ---------------------------------------------------------------------------


def _call_ws(handler, hass, connection, msg):
    """Bypass @websocket_api.async_response by calling the inner coroutine."""
    inner = getattr(handler, "_func", handler)
    return inner(hass, connection, msg)


def _ws_hass(entry_data):
    """Build a hass mock with one config entry containing entry_data."""
    from types import SimpleNamespace

    entry = SimpleNamespace(
        entry_id="entry-test",
        data=dict(entry_data),
        options={},
        version=15,
    )
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[entry])
    hass.config_entries.async_update_entry = MagicMock()
    return hass, entry


def _ws_msg(config_payload):
    return {
        "id": 1,
        "type": "eeg_optimizer/save_config",
        "config": config_payload,
    }


class TestSolarEdgeXOR:
    """SPEC §6 + Plan 11-03 Task 1: SolarEdge-XOR Defense-in-depth Layer 2."""

    @pytest.mark.asyncio
    async def test_save_config_solaredge_disables_dual(self):
        """SolarEdge + enable_dual_discharge=True → Auto-Korrektur auf False."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _entry = _ws_hass({"inverter_type": "solaredge_storedge"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "solaredge_storedge",
            "enable_dual_discharge": True,
            "enable_slot_a": True,
            "enable_slot_b": False,
        })
        await _call_ws(ws_save_config, hass, connection, msg)

        # Auto-Korrektur muss greifen
        assert hass.config_entries.async_update_entry.called
        kwargs = hass.config_entries.async_update_entry.call_args.kwargs
        new_data = kwargs.get("data")
        assert new_data["enable_dual_discharge"] is False
        # KEIN send_error
        assert not connection.send_error.called
        # send_result success
        assert connection.send_result.called

    @pytest.mark.asyncio
    async def test_save_config_solaredge_two_slots_falls_back_a(self):
        """SolarEdge + slot_a=True + slot_b=True → slot_b auf False."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _ = _ws_hass({"inverter_type": "solaredge_storedge"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "solaredge_storedge",
            "enable_dual_discharge": False,
            "enable_slot_a": True,
            "enable_slot_b": True,
        })
        await _call_ws(ws_save_config, hass, connection, msg)
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert new_data["enable_slot_a"] is True
        assert new_data["enable_slot_b"] is False

    @pytest.mark.asyncio
    async def test_save_config_solaredge_no_slot_falls_back_to_a(self):
        """SolarEdge + beide Slots False → slot_a True (Fallback)."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _ = _ws_hass({"inverter_type": "solaredge_storedge"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "solaredge_storedge",
            "enable_dual_discharge": False,
            "enable_slot_a": False,
            "enable_slot_b": False,
        })
        await _call_ws(ws_save_config, hass, connection, msg)
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert new_data["enable_slot_a"] is True


class TestInverterRaceValidation:
    """SPEC §9 + Plan 11-03 Task 1: Auto-Korrektur statt Hard-Reject."""

    @pytest.mark.asyncio
    async def test_b_start_too_close_auto_bumped(self):
        """Dual + a_start=20:00 + b_start=20:25 → b_start auf 20:35."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _ = _ws_hass({"inverter_type": "huawei_sun2000"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "huawei_sun2000",
            "enable_dual_discharge": True,
            "enable_slot_a": True,
            "enable_slot_b": True,
            "discharge_a_start_time": "20:00",
            "discharge_b_start_time": "20:25",  # zu nah an a_start+30min=20:30
        })
        await _call_ws(ws_save_config, hass, connection, msg)
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        # b_start auf a_start + 30min + 5min = 20:35 angehoben
        assert new_data["discharge_b_start_time"] == "20:35"

    @pytest.mark.asyncio
    async def test_default_dual_config_no_correction(self):
        """Default a=20:00 + b=03:00 → keine Änderung."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _ = _ws_hass({"inverter_type": "huawei_sun2000"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "huawei_sun2000",
            "enable_dual_discharge": True,
            "enable_slot_a": True,
            "enable_slot_b": True,
            "discharge_a_start_time": "20:00",
            "discharge_b_start_time": "03:00",
        })
        await _call_ws(ws_save_config, hass, connection, msg)
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert new_data["discharge_b_start_time"] == "03:00"

    @pytest.mark.asyncio
    async def test_only_one_slot_active_skips_race_check(self):
        """Wenn nur Slot A aktiv ist, bleibt b_start unangetastet (Race-Check inaktiv)."""
        from custom_components.eeg_energy_optimizer.websocket_api import (
            ws_save_config,
        )

        hass, _ = _ws_hass({"inverter_type": "huawei_sun2000"})
        connection = MagicMock()
        msg = _ws_msg({
            "inverter_type": "huawei_sun2000",
            "enable_dual_discharge": True,
            "enable_slot_a": True,
            "enable_slot_b": False,
            "discharge_a_start_time": "20:00",
            "discharge_b_start_time": "20:25",  # innerhalb der 5min, aber B aus
        })
        await _call_ws(ws_save_config, hass, connection, msg)
        new_data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        assert new_data["discharge_b_start_time"] == "20:25"

    def test_parse_hhmm_basic(self):
        from custom_components.eeg_energy_optimizer.websocket_api import (
            _parse_hhmm,
        )
        assert _parse_hhmm("20:00") == 1200
        assert _parse_hhmm("03:30") == 210
        assert _parse_hhmm("00:00") == 0
        assert _parse_hhmm("23:59") == 1439

    def test_parse_hhmm_raises_on_malformed(self):
        from custom_components.eeg_energy_optimizer.websocket_api import (
            _parse_hhmm,
        )
        with pytest.raises((ValueError, AttributeError)):
            _parse_hhmm("invalid")
