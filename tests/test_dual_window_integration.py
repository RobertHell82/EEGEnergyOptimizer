"""Phase 11: Dual-Window-Integration — Markdown + Activity-Log-Slot-Kontext + 24h-_evaluate-Sequenz.

Diese Datei läuft parallel zu tests/test_dual_window.py (Plan 11-03 schreibt
dort TestSolarEdgeXOR + TestInverterRaceValidation). Trennung verhindert
Wave-3-Merge-Konflikte.

Adressiert:
- D-08: Status-Anzeige (Markdown) zeigt aktiven Slot
- D-09: Slot-Kontext im Activity-Log VERPFLICHTEND
- D-10: Decision.discharge_active_slot durchgereicht
- SPEC §7 (Telemetry-Reasons im Activity-Log konsistent)
- SPEC §8 (Independent Slot-Aktivierung im _evaluate-Pfad)

Phase 11.1-02 ergänzt:
- TestPeakShareSlotMarkdown: Slot-aware UI-Output (Status-Card-Startzeit,
  naechste_aktion-Text, Markdown-PeakShare-Marker)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.eeg_energy_optimizer import optimizer as optimizer_mod
from custom_components.eeg_energy_optimizer.optimizer import Decision
from tests.conftest import _make_config, _make_optimizer, _make_snapshot


@pytest.fixture
def real_now(monkeypatch):
    """Patch optimizer._now to return real datetime.

    Conftest stubt `homeassistant.util.dt` als MagicMock — der Import-Try in
    optimizer.py landet damit nicht im except-Branch, und `_now = dt_util.now`
    referenziert eine MagicMock-Method. Ergebnis: `_now()` liefert MagicMock,
    Vergleiche mit STARTUP_GRACE_SECONDS scheitern.

    Diese Fixture patcht `_now` zurück auf eine echte datetime-Funktion,
    damit `_evaluate`'s Grace-Period-Check rechnet.
    """
    monkeypatch.setattr(
        optimizer_mod, "_now", lambda: datetime.now(tz=timezone.utc)
    )
    yield


# ---------------------------------------------------------------------------
# TestMarkdownRendering — D-08, D-10
# ---------------------------------------------------------------------------

class TestMarkdownRendering:
    """_build_markdown rendert aktiven Slot + Slot-Konfigurations-Übersicht."""

    def test_markdown_shows_slot_a_marker(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = "A"
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        md = opt._build_markdown(snap, decision)
        assert "Aktiver Slot: A" in md
        assert "### Abend-Entladung" in md

    def test_markdown_shows_slot_b_marker(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 4, 0, tzinfo=timezone.utc),
            battery_soc=70.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = "B"
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        md = opt._build_markdown(snap, decision)
        assert "Aktiver Slot: B" in md
        assert "### Morgen-Entladung" in md

    def test_markdown_no_slot_marker_for_legacy(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(enable_dual_discharge=False)
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 1, 30, tzinfo=timezone.utc),
            battery_soc=80.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = None  # Legacy
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        md = opt._build_markdown(snap, decision)
        assert "Aktiver Slot:" not in md
        assert "### Abend-Entladung" in md

    def test_markdown_shows_slot_config_when_dual_enabled(
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
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot(now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc))
        decision = Decision()
        decision.zustand = "Normal"
        md = opt._build_markdown(snap, decision)
        assert "### Slot-Konfiguration" in md
        assert "Slot A: aktiv" in md
        assert "Slot B: aktiv" in md
        assert "20:00" in md
        assert "03:00" in md
        assert "Cap 07:00" in md

    def test_markdown_no_slot_config_when_legacy(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        cfg = _make_config(enable_dual_discharge=False)
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        snap = _make_snapshot()
        decision = Decision()
        decision.zustand = "Normal"
        md = opt._build_markdown(snap, decision)
        assert "### Slot-Konfiguration" not in md


# ---------------------------------------------------------------------------
# TestEvaluate24hSlotMarkerPersistence — SPEC §8
# ---------------------------------------------------------------------------

class TestEvaluate24hSlotMarkerPersistence:
    """Voller _evaluate-Pfad: Slot-Aktivierungs-Datum wird gesetzt + Reset.

    `_evaluate` ist synchron — kein asyncio nötig.
    """

    def test_slot_a_activated_date_set_on_first_activation(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider, real_now,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        # Grace-Period umgehen — Tests prüfen Decision-Flow, nicht Startup-Verhalten
        opt._startup_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        assert opt._slot_a_activated_date is None
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
            pv_tomorrow_kwh=40.0,  # > tomorrow_demand inkl. Sicherheitspuffer
            consumption_tomorrow_daylight_kwh=5.0,
            consumption_overnight_kwh=1.0,
        )
        decision = opt._evaluate(snap, mode="Test")
        assert decision.discharge_active_slot == "A"
        assert opt._slot_a_activated_date == "2026-06-15"

    def test_slot_b_activated_date_set_independently_from_a(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider, real_now,
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
        opt._startup_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 12, 21, 4, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            battery_capacity_kwh=10.0,
            # sunrise = next_rising — heutige Sonnenaufgang liegt noch in der Zukunft
            sunrise=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            # sunrise_today = SA-Datum heute (= Dec 21 07:30, in der Zukunft bei 04:00)
            sunrise_today=datetime(2026, 12, 21, 7, 30, tzinfo=timezone.utc),
            pv_tomorrow_kwh=40.0,
            consumption_tomorrow_daylight_kwh=5.0,
            consumption_overnight_kwh=1.0,
        )
        decision = opt._evaluate(snap, mode="Test")
        assert decision.discharge_active_slot == "B"
        assert opt._slot_b_activated_date == "2026-12-21"
        assert opt._slot_a_activated_date is None

    def test_slot_a_date_reset_after_sunrise(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider, real_now,
    ):
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True,
            enable_slot_b=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg
        )
        opt._startup_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        # Setze Datum aus Vortag — _evaluate Reset-Logik muss es nullen
        opt._slot_a_activated_date = "2026-06-14"
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
            battery_soc=80.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
            pv_tomorrow_kwh=20.0,
            consumption_tomorrow_daylight_kwh=10.0,
        )
        opt._evaluate(snap, mode="Test")
        assert opt._slot_a_activated_date is None


# ---------------------------------------------------------------------------
# TestActivityLogSlotContext — D-09 (KEIN Skip)
# ---------------------------------------------------------------------------

class TestActivityLogSlotContext:
    """D-09: discharge_active_slot ist Pflichtfeld im Activity-Log-Entry-Dict
    und im eeg_optimizer_activity-Bus-Event.

    `_log_activity` ist eine Closure innerhalb von `async_setup_entry` und
    nicht direkt importierbar. Wir verifizieren die Erweiterung über
    (a) einen Source-Pattern-Check der eindeutig die Code-Linie matcht, und
    (b) eine Reproduktion der Dict-Builder-Logik mit allen drei Slot-Werten
    (A / B / None).
    """

    def test_log_entry_carries_slot_marker(self):
        """D-09 Source-Pattern: _log_activity MUSS discharge_active_slot
        ins entry_data-Dict serialisieren (additiv, kein Migrations-Bedarf).
        """
        import pathlib

        init_path = pathlib.Path(
            "custom_components/eeg_energy_optimizer/__init__.py"
        )
        src = init_path.read_text(encoding="utf-8")
        assert (
            '"discharge_active_slot": decision.discharge_active_slot' in src
        ), (
            "D-09: _log_activity MUSS discharge_active_slot ins entry_data-Dict "
            "serialisieren. Erwartetes Pattern fehlt in __init__.py."
        )

    def test_log_entry_dict_shape_includes_slot_field(self):
        """Reproduktion der entry_data-Builder-Logik aus _log_activity.
        Verifiziert, dass das Schlüsselfeld bei A / B / None korrekt
        durchgereicht wird (kein Datentyp-Drift).
        """
        for slot in ("A", "B", None):
            decision = Decision()
            decision.zustand = "Abend-Entladung"
            decision.discharge_active_slot = slot
            decision.timestamp = "2026-06-15T20:00:00+00:00"
            decision.min_soc_berechnet = 25.0
            decision.morning_pv_today_kwh = 10.0
            decision.discharge_pv_tomorrow_kwh = 15.0
            decision.energiebedarf_kwh = 12.0
            decision.discharge_demand_total_kwh = 14.0
            decision.ausführung = True
            decision.snapshot = {"soc_pct": 75.0}

            # Reproduziere die entry_data-Builder-Logik aus _log_activity:
            snap_dict = decision.snapshot if isinstance(decision.snapshot, dict) else {}
            soc_val = snap_dict.get("soc_pct")
            entry_data = {
                "timestamp": decision.timestamp,
                "zustand": decision.zustand,
                "reason": "test",
                "soc": soc_val,
                "min_soc": round(decision.min_soc_berechnet, 1),
                "pv_today": round(decision.morning_pv_today_kwh, 1),
                "pv_tomorrow": round(decision.discharge_pv_tomorrow_kwh, 1),
                "bedarf": round(decision.energiebedarf_kwh, 1),
                "discharge_bedarf": round(decision.discharge_demand_total_kwh, 1),
                "discharge_pv": round(decision.discharge_pv_tomorrow_kwh, 1),
                "ausführung": decision.ausführung,
                "discharge_active_slot": decision.discharge_active_slot,
            }
            assert "discharge_active_slot" in entry_data
            assert entry_data["discharge_active_slot"] == slot


# ---------------------------------------------------------------------------
# TestPeakShareSlotMarkdown — Phase 11.1-02
# ---------------------------------------------------------------------------

class TestPeakShareSlotMarkdown:
    """Phase 11.1-02: End-to-End-Test für Slot-aware PeakShare-UI-Output.

    Drei Stellen werden geprüft:
      (A) `_discharge_detail_status` liest den passenden Slot-Plan
          (`a` vs `b`), nicht mehr hartkodiert "a".
      (B) `naechste_aktion`-Text zeigt slot-spezifische PeakShare-Times mit
          dem korrekten Slot-Label (Abend-Entladung vs Morgen-Entladung).
      (C) `_build_markdown` enthält einen `PeakShare-Fenster: HH:MM-HH:MM`-
          Marker im Slot-Header, wenn Plan aktiv ist.
    """

    # ----- (A) _discharge_detail_status -----

    def test_discharge_detail_status_shows_slot_b_plan_when_b_active(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Mit `active_slot='B'` zeigt `start_time` Slot-B-Plan-Times.

        Plan-Lookup muss `slot_key = "b"` benutzen, nicht hartkodiert "a".
        """
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            enable_peakshare=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        now = datetime(2026, 12, 22, 3, 30, tzinfo=timezone.utc)
        plan_a = (
            datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 21, 23, 0, tzinfo=timezone.utc),
        )
        plan_b = (
            datetime(2026, 12, 22, 3, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 22, 4, 0, tzinfo=timezone.utc),
        )
        ps = MagicMock()
        ps._discharge_plan = {"a": plan_a, "b": plan_b}
        ps._discharge_plan_date = "2026-12-22"
        opt._peakshare = ps
        opt._enable_peakshare = True
        snap = _make_snapshot(now=now, battery_soc=70.0)
        info = opt._discharge_detail_status(
            snap, should_discharge=True, min_soc=20.0,
            discharge_blocked_by=[], active_slot="B",
        )
        assert "03:00-04:00 (PeakShare)" in info["start_time"]
        # Sicherheitscheck: keine Verwechslung mit Slot-A-Plan
        assert "21:00" not in info["start_time"]

    def test_discharge_detail_status_shows_slot_a_plan_when_a_active(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Mit `active_slot='A'` zeigt `start_time` Slot-A-Plan-Times."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            enable_peakshare=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        now = datetime(2026, 12, 21, 21, 30, tzinfo=timezone.utc)
        plan_a = (
            datetime(2026, 12, 21, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 21, 23, 0, tzinfo=timezone.utc),
        )
        plan_b = (
            datetime(2026, 12, 22, 3, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 22, 4, 0, tzinfo=timezone.utc),
        )
        ps = MagicMock()
        ps._discharge_plan = {"a": plan_a, "b": plan_b}
        ps._discharge_plan_date = "2026-12-21"
        opt._peakshare = ps
        opt._enable_peakshare = True
        snap = _make_snapshot(now=now, battery_soc=80.0)
        info = opt._discharge_detail_status(
            snap, should_discharge=True, min_soc=20.0,
            discharge_blocked_by=[], active_slot="A",
        )
        assert "21:00-23:00 (PeakShare)" in info["start_time"]
        assert "03:00" not in info["start_time"]

    def test_discharge_detail_status_falls_back_to_fixed_time_without_plan(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Ohne Plan → `start_time` zeigt Fixzeit, kein `(PeakShare)`-Marker."""
        cfg = _make_config(
            enable_dual_discharge=False,
            enable_peakshare=False,
            discharge_start_time="22:15",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc),
            battery_soc=70.0,
        )
        info = opt._discharge_detail_status(
            snap, should_discharge=False, min_soc=20.0,
            discharge_blocked_by=[], active_slot=None,
        )
        assert info["start_time"] == "22:15"
        assert "PeakShare" not in info["start_time"]

    def test_discharge_detail_status_slot_b_fallback_uses_b_start_time(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Im Dual-Mode ohne Plan zeigt der Fallback bei Slot B die Slot-B-Startzeit
        (nicht den Legacy `_discharge_start_h/m`-Wert, der irrelevant ist)."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:30",
            enable_peakshare=False,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        snap = _make_snapshot(
            now=datetime(2026, 12, 22, 3, 45, tzinfo=timezone.utc),
            battery_soc=70.0,
        )
        info = opt._discharge_detail_status(
            snap, should_discharge=True, min_soc=20.0,
            discharge_blocked_by=[], active_slot="B",
        )
        assert info["start_time"] == "03:30"

    # ----- (B) naechste_aktion-Text -----

    def test_naechste_aktion_text_shows_slot_b_peakshare_window(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider, real_now,
    ):
        """`naechste_aktion` bei aktivem Slot B zeigt 'Morgen-Entladung HH:MM-HH:MM (PeakShare)'."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=False, enable_slot_b=True,
            discharge_b_start_time="03:00",
            discharge_b_end_cap="07:00",
            enable_peakshare=True,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        opt._startup_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 12, 22, 3, 30, tzinfo=timezone.utc)
        plan_b = (
            datetime(2026, 12, 22, 3, 0, tzinfo=timezone.utc),
            datetime(2026, 12, 22, 4, 0, tzinfo=timezone.utc),
        )
        ps = MagicMock()
        ps._discharge_plan = {"a": None, "b": plan_b}
        ps._discharge_plan_date = "2026-12-22"
        ps.get_discharge_plan = MagicMock(return_value=plan_b)
        opt._peakshare = ps
        opt._enable_peakshare = True
        opt._peakshare_community = "Testgemeinde"
        opt._slot_b_activated_date = None

        snap = _make_snapshot(
            now=now, battery_soc=80.0, battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 12, 22, 7, 30, tzinfo=timezone.utc),
            consumption_overnight_kwh=1.0,
            consumption_tomorrow_daylight_kwh=5.0,
            pv_tomorrow_kwh=40.0,
        )
        decision = opt._evaluate(snap, mode="Test")

        assert decision.discharge_active_slot == "B"
        assert "Morgen-Entladung" in decision.nächste_aktion
        assert "03:00-04:00 (PeakShare)" in decision.nächste_aktion

    def test_naechste_aktion_text_shows_slot_a_peakshare_window(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider, real_now,
    ):
        """`naechste_aktion` bei aktivem Slot A zeigt 'Abend-Entladung HH:MM-HH:MM (PeakShare)'."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
            enable_peakshare=True,
            min_soc=20,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        opt._startup_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        now = datetime(2026, 6, 15, 21, 30, tzinfo=timezone.utc)
        plan_a = (
            datetime(2026, 6, 15, 21, 0, tzinfo=timezone.utc),
            datetime(2026, 6, 15, 23, 0, tzinfo=timezone.utc),
        )
        ps = MagicMock()
        ps._discharge_plan = {"a": plan_a, "b": None}
        ps._discharge_plan_date = "2026-06-15"
        ps.get_discharge_plan = MagicMock(return_value=plan_a)
        opt._peakshare = ps
        opt._enable_peakshare = True
        opt._peakshare_community = "Testgemeinde"
        opt._slot_a_activated_date = None

        snap = _make_snapshot(
            now=now, battery_soc=80.0, battery_capacity_kwh=10.0,
            sunrise=datetime(2026, 6, 16, 4, 52, tzinfo=timezone.utc),
            sunrise_today=datetime(2026, 6, 15, 4, 52, tzinfo=timezone.utc),
            consumption_overnight_kwh=1.0,
            consumption_tomorrow_daylight_kwh=5.0,
            pv_tomorrow_kwh=40.0,
        )
        decision = opt._evaluate(snap, mode="Test")

        assert decision.discharge_active_slot == "A"
        assert "Abend-Entladung" in decision.nächste_aktion
        assert "21:00-23:00 (PeakShare)" in decision.nächste_aktion

    # ----- (C) Markdown-PeakShare-Marker -----

    def test_markdown_includes_peakshare_marker_when_slot_a_active(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Markdown enthält `PeakShare-Fenster: HH:MM-HH:MM` wenn Slot A
        aktiv ist und ein Plan vorhanden ist."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 30, tzinfo=timezone.utc),
            battery_soc=80.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = "A"
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        decision.discharge_peakshare_active = True
        decision.discharge_window_start = "21:00"
        decision.discharge_window_end = "23:00"

        md = opt._build_markdown(snap, decision)
        assert "PeakShare-Fenster: 21:00-23:00" in md
        assert "Aktiver Slot: A" in md
        # Slot-spezifische Startzeit (a_start_time = 20:00) statt Legacy
        assert "Startzeit: 20:00" in md

    def test_markdown_includes_peakshare_marker_when_slot_b_active(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Markdown bei aktivem Slot B zeigt PeakShare-Marker + Slot-B-Startzeit."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
            discharge_a_start_time="20:00",
            discharge_b_start_time="03:00",
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        snap = _make_snapshot(
            now=datetime(2026, 12, 22, 3, 30, tzinfo=timezone.utc),
            battery_soc=70.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = "B"
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        decision.discharge_peakshare_active = True
        decision.discharge_window_start = "03:00"
        decision.discharge_window_end = "04:00"

        md = opt._build_markdown(snap, decision)
        assert "PeakShare-Fenster: 03:00-04:00" in md
        assert "Aktiver Slot: B" in md
        # Slot-B-Startzeit (b_start_time = 03:00)
        assert "Startzeit: 03:00" in md

    def test_markdown_no_peakshare_marker_when_no_plan(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider,
    ):
        """Ohne Plan kein PeakShare-Marker — Slot-Marker bleibt unverändert."""
        cfg = _make_config(
            enable_dual_discharge=True,
            enable_slot_a=True, enable_slot_b=True,
        )
        opt = _make_optimizer(
            mock_hass, mock_inverter, mock_coordinator, mock_provider, config=cfg,
        )
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 21, 30, tzinfo=timezone.utc),
            battery_soc=80.0,
        )
        decision = Decision()
        decision.zustand = "Abend-Entladung"
        decision.entladung_aktiv = True
        decision.discharge_active_slot = "A"
        decision.entladeleistung_kw = 5.0
        decision.min_soc_berechnet = 25.0
        decision.discharge_peakshare_active = False
        decision.discharge_window_start = ""
        decision.discharge_window_end = ""

        md = opt._build_markdown(snap, decision)
        assert "PeakShare-Fenster" not in md
        assert "Aktiver Slot: A" in md
