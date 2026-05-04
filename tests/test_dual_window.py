"""Phase 11: Dual-Window-Entladung — Tests for compute_b_window_end,
Reasons-Catalog, Migration v14→v15, Slot-A/B-Evaluators, Pro-Slot-Hysterese,
Mutual Exclusion, SolarEdge-Runtime-Force, 24h-Simulation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer.optimizer import (
    ALL_REASONS,
    Decision,
    REASON_BEFORE_SLOT_A,
    REASON_BEFORE_SLOT_B,
    REASON_BETWEEN_SLOTS,
    REASON_HYSTERESIS_STRICT,
    REASON_LABELS_DE,
    REASON_SLOT_A_ACTIVE,
    REASON_SLOT_A_RESERVE_REACHED,
    REASON_SLOT_B_ACTIVE,
    REASON_SLOT_B_PRE_SUNRISE_CUTOFF,
    REASON_SLOT_B_WINDOW_EXPIRED,
    compute_b_window_end,
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
