"""EEG Energy Optimizer integration for Home Assistant."""

from __future__ import annotations

import collections
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import logging

from .const import (
    DOMAIN,
    MODE_AUS,
    MODE_EIN,
    MODE_TEST,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_FORECAST_SOURCE,
    CONF_INVERTER_TYPE,
    CONF_PV_POWER_SENSOR,
    CONF_PV_POWER_SENSOR_2,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_POWER_CHARGE_SENSOR,
    CONF_BATTERY_POWER_DISCHARGE_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_GRID_POWER_EXPORT_SENSOR,
    CONF_GRID_POWER_IMPORT_SENSOR,
    CONF_LOOKBACK_WEEKS,
    CONF_TELEMETRY_ENABLED,
    COMBINED_BATTERY_POWER_SENSOR_ID,
    COMBINED_GRID_POWER_SENSOR_ID,
    CONSUMPTION_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    FAILURE_DEDUP_WINDOW_S,
    FORECAST_NONE_STREAK_THRESHOLD,
    INVERTER_SIGN_CONVENTIONS,
    SENSOR_UNAVAIL_THRESHOLD_S,
    STATE_ABEND_ENTLADUNG,
    STATE_MORGEN_EINSPEISUNG,
    STATE_NORMAL,
    TELEMETRY_SETTINGS_KEYS,
)
from .inverter import create_inverter
from .optimizer import EEGOptimizer, REASON_DISCHARGE_ABORTED_TODAY
from .telemetry import TelemetryReporter
from .telemetry_buffer import TelemetryBuffer
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.event import (
        async_call_later,
        async_track_time_change,
        async_track_time_interval,
    )
except ImportError:
    async_track_time_interval = None  # type: ignore[assignment]
    async_track_time_change = None  # type: ignore[assignment]
    async_call_later = None  # type: ignore[assignment]

try:
    from homeassistant.util import dt as dt_util
except ImportError:  # pragma: no cover — only triggered outside HA
    dt_util = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Phase 8 — geteilte Module-Level-Helfer (W-2 / W-3 / W-6 / I-4)
#
# Diese drei Helfer sind die *einzigen* Stellen, an denen ihre jeweilige
# Aufgabe erledigt wird. Sowohl _async_update_listener als auch
# websocket_api.py::ws_telemetry_enable importieren _build_telemetry_profile
# direkt aus diesem Modul, damit Profil-Shape und integration_started_at-
# Resolver garantiert identisch sind.
# ---------------------------------------------------------------------------


# Stabile Telemetrie-event_types für umbenannte UI-Zustände.
# Das UI-Label "Nacht-Entladung" muss am Backend weiterhin als "abend_entladung"
# erscheinen, damit Auswertungen über die Umbenennung hinweg konsistent bleiben.
_TELEMETRY_EVENT_TYPE_OVERRIDES = {
    "Nacht-Entladung": "abend_entladung",
}


def _normalize_state(zustand):
    """W-2 / W-6 — kanonisiert Decision.zustand-Labels in lowercase snake_case.

    Genutzt von:
      - State-Change `transition`-Strings (W-2)
      - Snapshot.state-Feld (W-6)
      - Outcome.event_type (W-2)
      - block_predictions Dict-Key (W-2)

    Beispiele:
      "Normal"             -> "normal"
      "Morgen-Einspeisung" -> "morgen_einspeisung"
      "Nacht-Entladung"    -> "abend_entladung"  (Override für Backend-Stabilität)
    """
    if zustand is None:
        return None
    if zustand in _TELEMETRY_EVENT_TYPE_OVERRIDES:
        return _TELEMETRY_EVENT_TYPE_OVERRIDES[zustand]
    return zustand.lower().replace(" ", "_").replace("-", "_")


def _resolve_integration_started_at(entry, identity_registered_at):
    """W-3 — einziger Resolver für profile.integration_started_at.

    Reihenfolge:
      1. entry.created_at (HA 2024.x+) → UTC ISO
      2. identity_registered_at (von TelemetryBuffer.set_identity)
      3. None
    """
    created_at = getattr(entry, "created_at", None)
    if created_at is not None:
        try:
            # Bevorzugt UTC-Konvertierung über astimezone — funktioniert für
            # alle datetime-Instanzen unabhängig vom HA dt_util-Stub im Test.
            if hasattr(created_at, "astimezone"):
                return created_at.astimezone(timezone.utc).isoformat()
            if dt_util is not None:
                result = dt_util.as_utc(created_at).isoformat()
                if isinstance(result, str):
                    return result
            return str(created_at)
        except Exception:  # pragma: no cover
            pass
    return identity_registered_at


def _resolve_battery_capacity_kwh(hass, config) -> float | None:
    """Spiegelt EEGOptimizer._resolve_capacity für den Profile-Builder.

    Reihenfolge: Sensor (mit Wh→kWh-Normalisierung) → manueller Fix-Wert → None.
    """
    cap_id = config.get(CONF_BATTERY_CAPACITY_SENSOR, "")
    if cap_id and hass is not None and hasattr(hass, "states"):
        state = hass.states.get(cap_id)
        if state is not None and state.state not in ("unknown", "unavailable", "", None):
            try:
                raw = float(state.state)
            except (ValueError, TypeError):
                raw = None
            if raw is not None:
                unit = ""
                if hasattr(state, "attributes"):
                    unit = state.attributes.get("unit_of_measurement", "") or ""
                if unit.lower() in ("wh", "w·h") or (not unit and raw > 1000):
                    return raw / 1000.0
                return raw
    manual = config.get(CONF_BATTERY_CAPACITY_KWH)
    try:
        return float(manual) if manual is not None else None
    except (ValueError, TypeError):
        return None


_APP_VERSION_CACHE: str | None = None


def _read_manifest_version_sync() -> str:
    """Synchroner Manifest-Read — NUR aus einem Executor-Thread aufrufen.

    Wird von _load_app_version via async_add_executor_job verwendet, damit
    das Lesen der manifest.json niemals den HA-Event-Loop blockiert.
    """
    try:
        import json as _json
        import pathlib as _pathlib
        manifest = _json.loads(
            (_pathlib.Path(__file__).parent / "manifest.json").read_text()
        )
        return manifest.get("version", "") or ""
    except Exception:  # pragma: no cover
        return ""


async def _load_app_version(hass) -> str:
    """Lädt die Integrations-Version einmalig in den Modul-Cache.

    Idempotent: bei wiederholtem Aufruf wird der Cache zurückgegeben, ohne
    erneuten Disk-IO. Ein Cache-Miss läuft im Executor (kein Event-Loop-Block).
    """
    global _APP_VERSION_CACHE
    if _APP_VERSION_CACHE is None:
        try:
            _APP_VERSION_CACHE = await hass.async_add_executor_job(
                _read_manifest_version_sync
            )
        except Exception:  # pragma: no cover — defensive
            _APP_VERSION_CACHE = ""
    return _APP_VERSION_CACHE or ""


def _cached_app_version() -> str:
    """Gibt die gecachte Version zurück. Leerstring solange nicht geladen.

    Sync-Caller (z.B. _build_telemetry_profile) müssen ein Pre-Load über
    _load_app_version sicherstellen — der Boot-Pfad in async_setup_entry
    erledigt das vor dem ersten Telemetrie-Send.
    """
    return _APP_VERSION_CACHE or ""


def _build_telemetry_profile(hass, entry, identity_registered_at):
    """I-4 / W-3 — einziger Profil-Builder.

    Wird von BEIDEN Pfaden genutzt:
      - _async_update_listener (Settings-Change → reporter.update_profile)
      - websocket_api.ws_telemetry_enable (Initial-Register → reporter.register)

    Reporter._shape_profile wendet die Whitelist defensiv erneut an, aber die
    Wahrheit lebt hier.
    """
    try:
        from homeassistant.const import __version__ as HA_VERSION
    except ImportError:  # pragma: no cover — Test-Umgebung ohne HA
        HA_VERSION = None

    # HA-Konvention: data + options gemerged
    _data = getattr(entry, "data", {}) or {}
    _options = getattr(entry, "options", {}) or {}
    config = {**_data, **_options}
    app_version = _cached_app_version() or None

    settings = {k: config.get(k) for k in TELEMETRY_SETTINGS_KEYS if k in config}

    return {
        "integration_started_at": _resolve_integration_started_at(
            entry, identity_registered_at
        ),
        "app_version": app_version,
        "ha_version": HA_VERSION,
        "inverter_type": config.get(CONF_INVERTER_TYPE),
        "battery_capacity_kwh": _resolve_battery_capacity_kwh(hass, config),
        "pv_peak_kwp": None,                # D-24
        "forecast_provider": config.get(CONF_FORECAST_SOURCE),
        "country_iso": getattr(hass.config, "country", None),
        "settings": settings,
    }


def _now_utc() -> datetime:
    """Helper für deterministische UTC-now (Telemetrie-Timestamps)."""
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Reine Payload-Builder — kein I/O, frei testbar (Hook-Glue Verifikation).
# ---------------------------------------------------------------------------


def _build_state_change_payload(decision, prev_zustand, mode_str):
    """W-2 — baut die StateChangePayload aus einer Decision-Übergangs-Beobachtung.

    `transition` und Snapshot.state nutzen denselben _normalize_state-Helper.

    Args:
        decision: Aktuelle Decision (neuer Zustand).
        prev_zustand: Voriger Zustand (deutscher Label-String).
        mode_str: "ein" oder "test" (lowercase). Caller hat MODE_AUS bereits gefiltert.
    """
    from_norm = _normalize_state(prev_zustand)
    to_norm = _normalize_state(decision.zustand)
    return {
        "ts": decision.timestamp,
        "transition": f"{from_norm}->{to_norm}",
        "mode": mode_str,
        "reasons": list(decision.reasons),
        "blocked_by": list(decision.blocked_by),
        "snapshot": dict(decision.snapshot),
    }


def _build_snapshot_payload(decision, mode_str, now):
    """W-6 — baut die SnapshotPayload aus der zuletzt berechneten Decision.

    `state` wird durch den gemeinsamen _normalize_state-Helper kanonisiert,
    damit Phase-9-JOINs zwischen `snapshots.state` und `state_changes.transition`
    sauber matchen.
    """
    payload = {
        "ts": now.isoformat() if hasattr(now, "isoformat") else str(now),
        "state": _normalize_state(decision.zustand),
        "mode": mode_str,
    }
    payload.update(dict(decision.snapshot))
    return payload


def _build_block_predictions(decision):
    """Captured beim Block-Start — predicted-Werte für späteren Outcome-Vergleich (W-1).

    Skaliert ``predicted_pv_kwh`` / ``predicted_consumption_kwh`` linear über
    24h auf die geplante Block-Dauer. Verbessert die Vergleichbarkeit mit
    ``actual_*_kwh`` (Trapez über das Block-Fenster) signifikant gegenüber
    dem rohen Tagesforecast. Backwards-kompatibel: ohne ``planned_block_end``
    bleibt fraction=1.0 (Legacy-Pfad / Tests).
    """
    if decision.zustand == STATE_MORGEN_EINSPEISUNG:
        day_pv = float(decision.morning_pv_today_kwh)
        day_consumption = float(decision.morning_consumption_kwh)
    elif decision.zustand == STATE_ABEND_ENTLADUNG:
        day_pv = float(decision.discharge_pv_tomorrow_kwh)
        day_consumption = float(decision.discharge_consumption_daylight_kwh)
    else:
        day_pv = 0.0
        day_consumption = 0.0

    fraction = 1.0
    if decision.planned_block_end and decision.timestamp:
        try:
            t_start = datetime.fromisoformat(
                decision.timestamp.replace("Z", "+00:00")
            )
            t_end = datetime.fromisoformat(
                decision.planned_block_end.replace("Z", "+00:00")
            )
            block_h = max(0.0, (t_end - t_start).total_seconds() / 3600.0)
            fraction = min(block_h / 24.0, 1.0)
        except (ValueError, TypeError, AttributeError):
            fraction = 1.0

    predicted_pv = day_pv * fraction
    predicted_consumption = day_consumption * fraction

    soc_start = decision.discharge_soc
    if not soc_start:
        soc_start = (decision.snapshot or {}).get("soc_pct") or 0
    return {
        "started_at": decision.timestamp,
        "soc_start_pct": int(round(soc_start)),
        "predicted_pv_kwh": predicted_pv,
        "predicted_consumption_kwh": predicted_consumption,
    }

PLATFORMS: list[str] = ["sensor", "select"]

async def async_backfill_hausverbrauch_stats(
    hass: HomeAssistant, config: dict
) -> None:
    """Backfill Hausverbrauch statistics from source sensors on every startup.

    Calculates historical Hausverbrauch = max(PV - Battery - Grid, 0) per hour
    from the 3 source sensors and imports them into the HA recorder so that the
    ConsumptionCoordinator can build a consumption profile immediately.

    Runs on every startup — async_import_statistics overwrites existing data
    for the same timestamps, so config changes (e.g. adding a second PV sensor)
    are automatically reflected without manual intervention.

    Silently returns on any error to never block integration startup.
    """
    try:
        from datetime import timezone
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.statistics import (
            statistics_during_period,
            async_import_statistics,
        )
        from homeassistant.components.recorder.models import (
            StatisticMetaData,
            StatisticData,
        )
        # StatisticMeanType ist neueres HA — vor 2026.x lebt mean_type als
        # kwarg von async_import_statistics. Wir versuchen den modernen Pfad
        # und fallen sonst auf das Legacy-Verhalten zurück.
        try:
            from homeassistant.components.recorder.models import StatisticMeanType
        except ImportError:  # pragma: no cover — alte HA-Versionen
            StatisticMeanType = None  # type: ignore[assignment]

        now = datetime.now(tz=timezone.utc)
        recorder_instance = get_instance(hass)

        # --- Read source sensor IDs from config ---
        pv_id = config.get(CONF_PV_POWER_SENSOR, "")
        pv2_id = config.get(CONF_PV_POWER_SENSOR_2, "")
        # Battery: either a single signed sensor OR a charge / discharge pair
        battery_charge_id = config.get(CONF_BATTERY_POWER_CHARGE_SENSOR, "")
        battery_discharge_id = config.get(CONF_BATTERY_POWER_DISCHARGE_SENSOR, "")
        has_battery_pair = bool(battery_charge_id and battery_discharge_id)
        battery_single_id = config.get(CONF_BATTERY_POWER_SENSOR, "")
        # Grid: either a single signed sensor OR an export / import pair
        grid_export_id = config.get(CONF_GRID_POWER_EXPORT_SENSOR, "")
        grid_import_id = config.get(CONF_GRID_POWER_IMPORT_SENSOR, "")
        has_grid_pair = bool(grid_export_id and grid_import_id)
        grid_single_id = config.get(CONF_GRID_POWER_SENSOR, "")

        # Decide which entity IDs to actually load history for
        battery_source_ids = (
            [battery_charge_id, battery_discharge_id]
            if has_battery_pair
            else [battery_single_id] if battery_single_id else []
        )
        grid_source_ids = (
            [grid_export_id, grid_import_id]
            if has_grid_pair
            else [grid_single_id] if grid_single_id else []
        )

        if not pv_id or not battery_source_ids or not grid_source_ids:
            _LOGGER.warning(
                "Hausverbrauch backfill skipped — sensor IDs not configured "
                "(PV=%s, Battery=%s, Grid=%s)",
                pv_id or "(empty)",
                battery_source_ids or "(empty)",
                grid_source_ids or "(empty)",
            )
            return

        # Sign conventions per inverter type. For pair configs the synthetic
        # sensor is already canonical, so the convention is identity (1, 1)
        # for those — encoded in INVERTER_SIGN_CONVENTIONS for fronius_gen24.
        inv_type = config.get(CONF_INVERTER_TYPE, "")
        signs = INVERTER_SIGN_CONVENTIONS.get(inv_type, {})
        battery_sign = signs.get("battery_sign", 1)
        grid_sign = signs.get("grid_sign", 1)
        pv_includes_battery = signs.get("pv_includes_battery", False)

        lookback_weeks = config.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS)
        start_time = now - timedelta(weeks=lookback_weeks)

        # --- Determine unit conversion factors for source sensors ---
        # Statistics are stored in the sensor's native unit.
        # If a sensor reports in W, we must divide by 1000 to get kW.
        def _unit_factor(entity_id: str) -> float:
            """Return 0.001 if sensor reports in W, else 1.0 (assumes kW)."""
            state = hass.states.get(entity_id)
            if state and hasattr(state, "attributes"):
                unit = (state.attributes.get("unit_of_measurement") or "").strip()
                if unit == "W":
                    return 0.001
            return 1.0

        pv_factor = _unit_factor(pv_id)
        pv2_factor = _unit_factor(pv2_id) if pv2_id else 1.0
        battery_factors = {eid: _unit_factor(eid) for eid in battery_source_ids}
        grid_factors = {eid: _unit_factor(eid) for eid in grid_source_ids}

        _LOGGER.debug(
            "Backfill unit factors: PV=%.3f, PV2=%.3f, Battery=%s, Grid=%s",
            pv_factor, pv2_factor, battery_factors, grid_factors,
        )

        # --- Load mean statistics for all source sensors ---
        sensor_ids = {pv_id, *battery_source_ids, *grid_source_ids}
        if pv2_id:
            sensor_ids.add(pv2_id)

        result = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            hass,
            start_time,
            now,
            sensor_ids,
            "hour",
            None,
            {"mean"},
        )

        pv_entries = result.get(pv_id, [])
        pv2_entries = result.get(pv2_id, []) if pv2_id else []

        # --- Index entries by start timestamp, converting to kW ---
        def _index_by_start(entries: list[dict], factor: float = 1.0) -> dict[float, float]:
            indexed: dict[float, float] = {}
            for e in entries:
                ts = e.get("start") or e.get("start_ts")
                mean = e.get("mean")
                if ts is None or mean is None:
                    continue
                if isinstance(ts, str):
                    ts_float = datetime.fromisoformat(ts).timestamp()
                else:
                    ts_float = float(ts)
                indexed[ts_float] = mean * factor
            return indexed

        # Battery / grid pair-or-single: produce a signed kW series per metric.
        # When a pair is configured: signed = pos − neg (canonical), then *
        # sign convention from INVERTER_SIGN_CONVENTIONS (identity for Fronius).
        # When a single sensor is configured: raw * sign convention as before.
        def _combine_pair_signed(
            entries_pos: list[dict], entries_neg: list[dict],
            factor_pos: float, factor_neg: float,
            sign: int,
        ) -> dict[float, float]:
            pos = _index_by_start(entries_pos, factor_pos)
            neg = _index_by_start(entries_neg, factor_neg)
            keys = set(pos.keys()) | set(neg.keys())
            return {ts: (pos.get(ts, 0.0) - neg.get(ts, 0.0)) * sign for ts in keys}

        def _single_signed(entries: list[dict], factor: float, sign: int) -> dict[float, float]:
            return {ts: v * sign for ts, v in _index_by_start(entries, factor).items()}

        any_battery_entries = any(result.get(eid) for eid in battery_source_ids)
        any_grid_entries = any(result.get(eid) for eid in grid_source_ids)
        use_history_fallback = (
            not pv_entries or not any_battery_entries or not any_grid_entries
        )

        if use_history_fallback:
            _LOGGER.info(
                "Backfill: no long-term statistics for source sensors "
                "(PV=%d, Battery=%s, Grid=%s), trying state history fallback",
                len(pv_entries),
                {eid: len(result.get(eid, [])) for eid in battery_source_ids},
                {eid: len(result.get(eid, [])) for eid in grid_source_ids},
            )
            # --- Fallback: read short-term state history and aggregate hourly ---
            from homeassistant.components.recorder.history import (
                get_significant_states,
            )

            def _load_history():
                return get_significant_states(
                    hass, start_time, now, list(sensor_ids),
                    significant_changes_only=False,
                )

            history = await recorder_instance.async_add_executor_job(_load_history)

            def _history_to_hourly_means(
                states: list,
            ) -> dict[float, float]:
                """Aggregate state history entries into hourly means."""
                from collections import defaultdict
                hourly: dict[float, list[float]] = defaultdict(list)
                for state in states:
                    try:
                        val = float(state.state)
                    except (ValueError, TypeError):
                        continue
                    # Truncate to hour
                    ts = state.last_updated.replace(
                        minute=0, second=0, microsecond=0
                    )
                    hour_ts = ts.timestamp()
                    hourly[hour_ts].append(val)
                result: dict[float, float] = {}
                for hour_ts, values in hourly.items():
                    result[hour_ts] = sum(values) / len(values)
                return result

            pv_by_ts = _history_to_hourly_means(history.get(pv_id, []))
            pv2_by_ts = _history_to_hourly_means(
                history.get(pv2_id, [])
            ) if pv2_id else {}

            def _apply_factor(by_ts: dict[float, float], factor: float) -> dict[float, float]:
                if factor == 1.0:
                    return by_ts
                return {ts: v * factor for ts, v in by_ts.items()}

            pv_by_ts = _apply_factor(pv_by_ts, pv_factor)
            pv2_by_ts = _apply_factor(pv2_by_ts, pv2_factor) if pv2_by_ts else {}

            if has_battery_pair:
                pos_h = _apply_factor(
                    _history_to_hourly_means(history.get(battery_charge_id, [])),
                    battery_factors[battery_charge_id],
                )
                neg_h = _apply_factor(
                    _history_to_hourly_means(history.get(battery_discharge_id, [])),
                    battery_factors[battery_discharge_id],
                )
                keys = set(pos_h) | set(neg_h)
                battery_by_ts = {
                    ts: (pos_h.get(ts, 0.0) - neg_h.get(ts, 0.0)) * battery_sign
                    for ts in keys
                }
            else:
                bat_h = _apply_factor(
                    _history_to_hourly_means(history.get(battery_single_id, [])),
                    battery_factors[battery_single_id],
                )
                battery_by_ts = {ts: v * battery_sign for ts, v in bat_h.items()}

            if has_grid_pair:
                pos_h = _apply_factor(
                    _history_to_hourly_means(history.get(grid_export_id, [])),
                    grid_factors[grid_export_id],
                )
                neg_h = _apply_factor(
                    _history_to_hourly_means(history.get(grid_import_id, [])),
                    grid_factors[grid_import_id],
                )
                keys = set(pos_h) | set(neg_h)
                grid_by_ts = {
                    ts: (pos_h.get(ts, 0.0) - neg_h.get(ts, 0.0)) * grid_sign
                    for ts in keys
                }
            else:
                grid_h = _apply_factor(
                    _history_to_hourly_means(history.get(grid_single_id, [])),
                    grid_factors[grid_single_id],
                )
                grid_by_ts = {ts: v * grid_sign for ts, v in grid_h.items()}

            if not pv_by_ts or not battery_by_ts or not grid_by_ts:
                _LOGGER.warning(
                    "Hausverbrauch backfill skipped — no state history "
                    "(PV=%d, Battery=%d, Grid=%d hours)",
                    len(pv_by_ts), len(battery_by_ts), len(grid_by_ts),
                )
                return

            _LOGGER.info(
                "Backfill: loaded state history "
                "(PV=%d, Battery=%d, Grid=%d hours)",
                len(pv_by_ts), len(battery_by_ts), len(grid_by_ts),
            )
        else:
            pv_by_ts = _index_by_start(pv_entries, pv_factor)
            pv2_by_ts = _index_by_start(pv2_entries, pv2_factor) if pv2_entries else {}

            if has_battery_pair:
                battery_by_ts = _combine_pair_signed(
                    result.get(battery_charge_id, []),
                    result.get(battery_discharge_id, []),
                    battery_factors[battery_charge_id],
                    battery_factors[battery_discharge_id],
                    battery_sign,
                )
            else:
                battery_by_ts = _single_signed(
                    result.get(battery_single_id, []),
                    battery_factors[battery_single_id],
                    battery_sign,
                )

            if has_grid_pair:
                grid_by_ts = _combine_pair_signed(
                    result.get(grid_export_id, []),
                    result.get(grid_import_id, []),
                    grid_factors[grid_export_id],
                    grid_factors[grid_import_id],
                    grid_sign,
                )
            else:
                grid_by_ts = _single_signed(
                    result.get(grid_single_id, []),
                    grid_factors[grid_single_id],
                    grid_sign,
                )

        # --- Calculate Hausverbrauch for each hour where all 3 have data ---
        common_timestamps = sorted(
            set(pv_by_ts.keys()) & set(battery_by_ts.keys()) & set(grid_by_ts.keys())
        )

        if not common_timestamps:
            _LOGGER.warning("Hausverbrauch backfill skipped — no overlapping timestamps")
            return

        # battery_by_ts / grid_by_ts are already in canonical signed kW
        # (positive = charging / positive = export). No further sign flip.
        statistics: list[StatisticData] = []
        battery_stats: list[StatisticData] = []
        grid_stats: list[StatisticData] = []
        skipped = 0
        for ts in common_timestamps:
            pv = pv_by_ts[ts] + pv2_by_ts.get(ts, 0.0)
            bat = battery_by_ts[ts]
            # SolarEdge: PV sensor includes battery discharge → correct
            # Don't clamp — negative from conversion losses needed for accuracy
            if pv_includes_battery:
                pv = pv + bat
            grid = grid_by_ts[ts]
            hausverbrauch = max(pv - bat - grid, 0.0)
            # Discard unrealistic values (wrong signs in historical data)
            if hausverbrauch > 50.0:
                skipped += 1
                continue
            value = round(hausverbrauch, 3)
            hour_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            statistics.append(
                StatisticData(start=hour_dt, mean=value, state=value)
            )
            # Synthetic combined sensors get their own historical statistics
            # so the Energy Dashboard / charts can show them just like a
            # native sensor with full history.
            if has_battery_pair:
                battery_stats.append(
                    StatisticData(start=hour_dt, mean=round(bat, 3), state=round(bat, 3))
                )
            if has_grid_pair:
                grid_stats.append(
                    StatisticData(start=hour_dt, mean=round(grid, 3), state=round(grid, 3))
                )
        if skipped:
            _LOGGER.info("Backfill: skipped %d entries > 50 kW (unrealistic)", skipped)

        # --- Import statistics ---
        def _import(stat_id: str, name: str, data: list[StatisticData]) -> None:
            if not data:
                return
            # Neuere HA-Versionen (2026.x+) erwarten mean_type als Feld in
            # StatisticMetaData. Auf älteren Versionen lebt es als kwarg.
            # HA 2026.11: unit_class wird Pflicht — "power" passt zur Einheit
            # kW (analog Energie/Volume/...). Ohne dieses Feld loggt
            # homeassistant.helpers.frame eine Deprecation-Warnung.
            meta_kwargs = {
                "has_mean": True,
                "has_sum": False,
                "name": name,
                "source": "recorder",
                "statistic_id": stat_id,
                "unit_of_measurement": "kW",
                "unit_class": "power",
            }
            if StatisticMeanType is not None:
                meta_kwargs["mean_type"] = StatisticMeanType.ARITHMETIC
            try:
                meta = StatisticMetaData(**meta_kwargs)
            except TypeError:
                # Älteres HA ohne unit_class- und/oder mean_type-Felder.
                # Schrittweise abwerfen, bis StatisticMetaData die Kwargs
                # akzeptiert (Legacy-Kompatibilität).
                meta_kwargs.pop("unit_class", None)
                try:
                    meta = StatisticMetaData(**meta_kwargs)
                except TypeError:
                    meta_kwargs.pop("mean_type", None)
                    meta = StatisticMetaData(**meta_kwargs)
            try:
                async_import_statistics(hass, meta, data)
            except TypeError:
                # Theoretisch unerreichbar — wenn StatisticMetaData den
                # mean_type aufgenommen hat, akzeptiert async_import_statistics
                # ihn nicht mehr als kwarg. Defensiver Fallback auf Legacy-API.
                async_import_statistics(hass, meta, data, mean_type="arithmetic")

        _import(
            CONSUMPTION_SENSOR,
            "EEG Energy Optimizer Hausverbrauch",
            statistics,
        )
        if has_battery_pair:
            _import(
                COMBINED_BATTERY_POWER_SENSOR_ID,
                "EEG Energy Optimizer Batterieleistung",
                battery_stats,
            )
        if has_grid_pair:
            _import(
                COMBINED_GRID_POWER_SENSOR_ID,
                "EEG Energy Optimizer Netzleistung",
                grid_stats,
            )

        start_date = datetime.fromtimestamp(
            common_timestamps[0], tz=timezone.utc
        ).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(
            common_timestamps[-1], tz=timezone.utc
        ).strftime("%Y-%m-%d")
        extra = ""
        if has_battery_pair or has_grid_pair:
            extra = (
                f" (+ {len(battery_stats)} Batterie / {len(grid_stats)} Netz "
                "synthetic statistics)"
            )
        _LOGGER.info(
            "Backfilled %d hourly statistics for Hausverbrauch from %s to %s%s",
            len(statistics),
            start_date,
            end_date,
            extra,
        )

    except Exception:
        _LOGGER.exception("Hausverbrauch backfill failed (non-critical)")

PANEL_FRONTEND_URL = "/eeg_optimizer_panel"
PANEL_ICON = "mdi:battery-charging-high"
PANEL_TITLE = "EEG Energy Optimizer"
PANEL_URL_PATH = "eeg-optimizer"


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from older versions."""
    if entry.version < 3:
        new_data = {**entry.data}
        # Add Phase 3 defaults for missing keys
        new_data.setdefault("ueberschuss_schwelle", 1.25)
        new_data.setdefault("morning_end_time", "10:00")
        new_data.setdefault("discharge_start_time", "20:00")
        new_data.setdefault("discharge_power_kw", 3.0)
        new_data.setdefault("min_soc", 10)
        new_data.setdefault("safety_buffer_pct", 25)
        hass.config_entries.async_update_entry(entry, data=new_data, version=3)

    if entry.version < 4:
        new_data = {**entry.data}
        new_data.setdefault("setup_complete", False)
        hass.config_entries.async_update_entry(entry, data=new_data, version=4)

    if entry.version < 5:
        new_data = {**entry.data}
        new_data.setdefault("enable_morning_delay", True)
        new_data.setdefault("enable_night_discharge", True)
        # überschuss_schwelle no longer used — safety_buffer_pct replaces it
        new_data.pop("ueberschuss_schwelle", None)
        hass.config_entries.async_update_entry(entry, data=new_data, version=5)

    if entry.version < 6:
        new_data = {**entry.data}
        new_data.setdefault("grid_power_sensor", "sensor.power_meter_wirkleistung")
        hass.config_entries.async_update_entry(entry, data=new_data, version=6)

    if entry.version < 7:
        new_data = {**entry.data}
        new_data.setdefault("battery_power_sensor", "sensor.batteries_lade_entladeleistung")
        hass.config_entries.async_update_entry(entry, data=new_data, version=7)

    if entry.version < 8:
        new_data = {**entry.data}
        # Switch default consumption sensor to own Hausverbrauch sensor
        if new_data.get("consumption_sensor") == "sensor.power_meter_verbrauch":
            new_data["consumption_sensor"] = "sensor.eeg_energy_optimizer_hausverbrauch"
        hass.config_entries.async_update_entry(entry, data=new_data, version=8)

    if entry.version < 9:
        new_data = {**entry.data}
        new_data.pop("consumption_sensor", None)
        hass.config_entries.async_update_entry(entry, data=new_data, version=9)

    if entry.version < 10:
        new_data = {**entry.data}
        # Preserve existing expert behavior: if expert_mode was on,
        # enable both new features to maintain current dashboard
        is_expert = new_data.get("expert_mode", False)
        new_data.setdefault("enable_simulation", is_expert)
        new_data.setdefault("enable_manual_control", is_expert)
        hass.config_entries.async_update_entry(entry, data=new_data, version=10)

    if entry.version < 11:
        # v11 only bumps the schema version to mark Fronius support — no
        # data backfill needed because fronius_modbus_host/port are written
        # by the wizard when (and only when) the user actually selects
        # Fronius. Existing Huawei/SolaX/SolarEdge entries get the bump
        # without their data dict being touched.
        hass.config_entries.async_update_entry(entry, data=entry.data, version=11)

    if entry.version < 12:
        new_data = {**entry.data}
        new_data.setdefault("enable_peakshare", True)
        new_data.setdefault("peakshare_community", "BEG")
        # Don't change existing discharge_power_kw — only default for new installs is 5.0
        hass.config_entries.async_update_entry(entry, data=new_data, version=12)

    if entry.version < 13:
        # v13 vereint zwei Migrations-Intents (gemeinsam gedraftet):
        #   1. Pair-sensor support (Fronius) — schema-only, pair keys werden
        #      vom Wizard/Auto-Detect geschrieben, wenn der User tatsächlich
        #      ein SolarNet split-sensor Setup hat.
        #   2. Phase 8 Telemetrie (D-02): CONF_TELEMETRY_ENABLED=False als
        #      sicherer Default für alle existierenden Installationen.
        new_data = {**entry.data}
        new_data.setdefault(CONF_TELEMETRY_ENABLED, False)
        hass.config_entries.async_update_entry(entry, data=new_data, version=13)

    if entry.version < 14:
        # v14 — Abend-Entladestart auf 01:00 vereinheitlichen.
        # Hard-Migration: ALLE bestehenden Entries werden auf "01:00" gesetzt,
        # unabhängig vom bisherigen Wert. Begründung:
        #   - In beiden Modi (Fixed + PeakShare) ist discharge_start_time jetzt
        #     der frühestmögliche Entladestart (PeakShare nutzt ihn als Sliding-
        #     Window-Untergrenze). Späterer Start = präzisere Verbrauchsprognose
        #     für den Restbedarf der Nacht = höhere realisierte Einspeisung.
        #   - Der zuvor empfohlene Default 20:00 produzierte zu konservative
        #     min_soc_dyn-Werte und damit kürzere Fenster.
        # User kann den Wert jederzeit im Wizard wieder ändern.
        new_data = {**entry.data}
        new_data["discharge_start_time"] = "01:00"
        hass.config_entries.async_update_entry(entry, data=new_data, version=14)

    if entry.version < 15:
        # v15 — Phase 11: Dual-Window-Entladung
        # Additive Migration: setzt neue Slot-Konfigurations-Keys mit Defaults.
        # Default-Wechsel (D-04, intendiert) — Bestands-Anlagen (nicht
        # SolarEdge) erhalten Dual-Window automatisch beim Update. Mitigation:
        # Pro-Slot-Hysterese und PV-Tomorrow-Garantie verhindern aggressive
        # Erstaktivierung; CHANGELOG dokumentiert die Verhaltensänderung
        # prominent ("Verhaltensänderung beim Update").
        # SolarEdge-Sonderfall (D-03): NVRAM-Verschleiß erlaubt nur einen
        # Slot pro Tag → enable_dual_discharge=False, enable_slot_a=True,
        # enable_slot_b=False. Defense-in-depth in 11-03 (Save-Path) und
        # 11-02 (Runtime-Erzwingung).
        # setdefault statt Hard-Set respektiert vorhandene User-Werte (T-11-01-01).
        new_data = {**entry.data}
        inverter_type = new_data.get("inverter_type", "")
        is_solaredge = inverter_type == "solaredge_storedge"
        if is_solaredge:
            new_data.setdefault("enable_dual_discharge", False)
            new_data.setdefault("enable_slot_a", True)
            new_data.setdefault("enable_slot_b", False)
        else:
            new_data.setdefault("enable_dual_discharge", True)
            new_data.setdefault("enable_slot_a", True)
            new_data.setdefault("enable_slot_b", True)
        new_data.setdefault("discharge_a_start_time", "20:00")
        new_data.setdefault("discharge_b_start_time", "03:00")
        new_data.setdefault("discharge_b_end_cap", "07:00")
        hass.config_entries.async_update_entry(entry, data=new_data, version=15)

    if entry.version < 16:
        # v16 — Phase 12: Dual-Window-Master-Toggle entfernt, Slot-A/B sind
        # die einzige Discharge-Logik. discharge_start_time + enable_dual_discharge
        # werden aus der Config entfernt (Optimizer-Code liest sie nicht mehr).
        # SolarEdge-Sonderfall: bisheriger discharge_start_time wird auf den
        # passenden Slot übertragen, damit das gewohnte Zeitfenster erhalten
        # bleibt. start < 12:00 → Slot B (Morgen-Entladung), sonst Slot A.
        new_data = {**entry.data}
        inv_type = new_data.get("inverter_type", "")
        is_solaredge = inv_type == "solaredge_storedge"
        old_start = new_data.get("discharge_start_time", "")
        if is_solaredge and old_start:
            try:
                old_h = int(str(old_start).split(":")[0])
                if old_h < 12:
                    new_data["enable_slot_a"] = False
                    new_data["enable_slot_b"] = True
                    new_data["discharge_b_start_time"] = old_start
                else:
                    new_data["enable_slot_a"] = True
                    new_data["enable_slot_b"] = False
                    new_data["discharge_a_start_time"] = old_start
            except (ValueError, AttributeError):
                pass
        new_data.pop("discharge_start_time", None)
        new_data.pop("enable_dual_discharge", None)
        hass.config_entries.async_update_entry(entry, data=new_data, version=16)

    if entry.version < 17:
        # v17 — Slot-B-Reserve entfernt. discharge_a_reserve_pct wird aus der
        # Config gestrichen; Slot A entlädt immer bis min_soc_dyn, Slot B
        # nutzt den verbleibenden SOC oberhalb min_soc als Budget.
        new_data = {**entry.data}
        new_data.pop("discharge_a_reserve_pct", None)
        hass.config_entries.async_update_entry(entry, data=new_data, version=17)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EEG Energy Optimizer from a config entry."""
    from homeassistant.components.frontend import (
        async_register_built_in_panel,
        async_remove_panel,
    )
    from homeassistant.components.http import StaticPathConfig

    hass.data.setdefault(DOMAIN, {})
    config = {**entry.data, **entry.options}
    setup_complete = config.get("setup_complete", False)

    # Cache-Invalidate: Module-State bleibt bei Config-Entry-Reload bestehen,
    # daher würde der nach HACS-Update geänderte manifest.json-Wert nicht
    # gelesen werden, bevor HA komplett neu startet. Beim Setup-Aufruf den
    # Cache zurücksetzen, damit _load_app_version frisch von Disk liest.
    global _APP_VERSION_CACHE
    _APP_VERSION_CACHE = None

    # Register WebSocket commands (always — panel needs them even before setup)
    async_register_websocket_commands(hass)

    # Register frontend panel (always — user needs panel to complete setup)
    # Skip if already registered (e.g. during config entry reload)
    frontend_path = str(Path(__file__).parent / "frontend")
    if not hass.data.get(f"{DOMAIN}_static_registered"):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(PANEL_FRONTEND_URL, frontend_path, cache_headers=False)]
            )
            hass.data[f"{DOMAIN}_static_registered"] = True
        except Exception:
            hass.data[f"{DOMAIN}_static_registered"] = True  # Already registered

    # Read version from manifest for cache-busting query parameter.
    # Cached in module state to avoid blocking disk IO on every panel load
    # (HA 2026.x detects this as a blocking_call_inside_event_loop offense
    # and the warmer-than-expected manifest.json access measurably stalls
    # the loop on slow storage).
    panel_version = await _load_app_version(hass) or "0"

    # Always re-register panel to update cache-busting version in js_url
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        async_remove_panel(hass, PANEL_URL_PATH)
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        frontend_url_path=PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "eeg-optimizer-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{PANEL_FRONTEND_URL}/eeg-optimizer-panel.js?v={panel_version}",
            }
        },
        require_admin=False,
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "inverter": None,
        "platforms_loaded": False,
    }

    # If setup not complete, register panel only — skip platforms and optimizer
    if not setup_complete:
        entry.async_on_unload(entry.add_update_listener(_async_update_listener))
        return True

    # Full setup: inverter, platforms, optimizer
    try:
        inverter = create_inverter(config.get("inverter_type", ""), hass, config)
    except ValueError as err:
        _LOGGER.error("Failed to create inverter: %s", err)
        from homeassistant.components.persistent_notification import async_create
        async_create(
            hass,
            f"EEG Energy Optimizer: Wechselrichter konnte nicht erstellt werden — {err}",
            title="EEG Energy Optimizer Fehler",
            notification_id="eeg_inverter_error",
        )
        return False
    hass.data[DOMAIN][entry.entry_id]["inverter"] = inverter

    # Restore persisted register write counter
    from homeassistant.helpers.storage import Store as _Store
    writes_store = _Store(hass, 1, f"{DOMAIN}_{entry.entry_id}_register_writes")
    try:
        stored_writes = await writes_store.async_load()
        if stored_writes and isinstance(stored_writes, int):
            inverter.register_writes = stored_writes
            _LOGGER.debug("Restored register write counter: %d", stored_writes)
    except Exception:
        pass
    hass.data[DOMAIN][entry.entry_id]["writes_store"] = writes_store

    # Migration: earlier builds of the synthetic Fronius pair sensors used
    # suggested_object_id without pinning entity_id. HA prefixed the device
    # slug anyway, producing IDs like
    #   sensor.eeg_energy_optimizer_eeg_energy_optimizer_battery_power
    # which do not match the canonical IDs the rest of the integration
    # writes into config (CONF_BATTERY_POWER_SENSOR / CONF_GRID_POWER_SENSOR
    # → COMBINED_*_SENSOR_ID). Result: Hausverbrauch / Netzleistung /
    # Batterieleistung read from a non-existent entity → "unknown".
    # Rename the legacy registry entries back to canonical before the
    # platforms are forwarded so the new sensor classes attach cleanly.
    try:
        from homeassistant.helpers import entity_registry as er
        ent_reg = er.async_get(hass)
        for unique_id, canonical in (
            (f"{DOMAIN}_{entry.entry_id}_battery_power_combined", COMBINED_BATTERY_POWER_SENSOR_ID),
            (f"{DOMAIN}_{entry.entry_id}_grid_power_combined", COMBINED_GRID_POWER_SENSOR_ID),
        ):
            existing = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
            if existing and existing != canonical:
                # Free the canonical slot if a stale entity squats on it
                blocker = ent_reg.async_get(canonical)
                if blocker and blocker.unique_id != unique_id:
                    ent_reg.async_update_entity(
                        canonical, new_entity_id=f"{canonical}_legacy"
                    )
                ent_reg.async_update_entity(existing, new_entity_id=canonical)
                _LOGGER.info(
                    "Renamed combined sensor %s -> %s", existing, canonical
                )
    except Exception:
        _LOGGER.exception("Combined-sensor entity_id migration failed (non-fatal)")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.data[DOMAIN][entry.entry_id]["platforms_loaded"] = True

    # After platforms are set up, coordinator/provider/select are available
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.get("coordinator")
    provider = data.get("provider")

    # Create PeakShare provider (before optimizer so it can be passed in)
    from .peakshare import PeakShareProvider
    peakshare_provider = PeakShareProvider(hass, entry.entry_id)
    await peakshare_provider.async_load()
    await peakshare_provider.async_fetch()
    data["peakshare"] = peakshare_provider

    if coordinator and provider:
        # Feed-in statistics tracker (vor Optimizer, damit der failure_callback
        # darauf zugreifen könnte; Reporter wird unmittelbar danach injiziert)
        from .statistics import FeedinStatistics
        feedin_stats = FeedinStatistics(hass, entry.entry_id, config)
        await feedin_stats.async_load()
        data["feedin_stats"] = feedin_stats

        # ----------------------------------------------------------
        # Phase 8: Telemetry Reporter Lifecycle (D-04 .. D-06)
        # ----------------------------------------------------------
        telemetry_buffer = TelemetryBuffer(hass)
        await telemetry_buffer.load()
        reporter = TelemetryReporter(hass, telemetry_buffer)
        data["telemetry_buffer"] = telemetry_buffer
        data["telemetry_reporter"] = reporter
        # W-1: snapshot_queue wird vom 60-min Flush gedrained.
        data["snapshot_queue"] = []
        # event_type (snake_case) -> {predicted_pv_kwh, predicted_consumption_kwh,
        #                             started_at, soc_start_pct}
        data["block_predictions"] = {}
        # Hochauflösendes Power-Sampling während eines aktiven Blocks (30s-Cycle).
        # Quelle für outcome.actual_pv_kwh / actual_consumption_kwh — entkoppelt
        # vom 30-/60-min Snapshot-Telemetrie-Pfad, damit der 60-min Flush die
        # Block-Aggregation nicht löscht und kürzere Blocks (< 30 min) trotzdem
        # genug Stützstellen für die Trapezregel haben.
        # event_type (snake_case) -> list[{ts, pv_now_kw, consumption_now_kw, grid_now_kw}]
        data["block_samples"] = {}
        # event_type (snake_case) -> {pv_seen, cons_seen, grid_seen, actuals_invalid}
        # Trackt pro Block, ob ein bereits gesehener Sensor mid-block ausfällt
        # (None nach mindestens einem nicht-None-Sample). Outcome trägt dann
        # actuals_invalid=true, damit das Backend zwischen "Sensor nicht
        # konfiguriert" (Wert fehlt von Anfang an) und "Sensor zwischenzeitlich
        # ausgefallen" (Aktuals verfälscht) unterscheiden kann.
        data["block_actuals_state"] = {}
        # (category, message_hash) -> last-emit datetime (UTC)
        data["telemetry_failure_dedup"] = {}
        data["telemetry_forecast_none_streak"] = 0
        # sensor_role -> datetime|None (None = aktuell verfügbar)
        data["telemetry_sensor_unavail_since"] = {}
        # Drift-Self-Heal: Wert der zuletzt erfolgreich gesendeten
        # battery_capacity_kwh. Schlüssel fehlt, solange noch kein Profil
        # gesendet wurde — dann findet auch keine Drift-Prüfung statt.
        # Notwendig, weil Sensoren wie sensor.batterien_akkukapazitat beim
        # Boot häufig noch unknown sind und der Resolver auf den manuellen
        # Wizard-Default (z.B. 10 kWh) zurückfällt.

        # Reporter + data dict in FeedinStatistics einklinken (für Outcome-Hook)
        if hasattr(feedin_stats, "set_reporter"):
            feedin_stats.set_reporter(reporter, data)

        # ----------------------------------------------------------
        # Telemetrie-Failure-Helper (closures über data + reporter)
        # ----------------------------------------------------------
        def _emit_failure_dedup(*, category, severity, message_hash, context):
            key = (category, message_hash)
            last = data["telemetry_failure_dedup"].get(key)
            now_ts = _now_utc()
            if last is not None and (now_ts - last).total_seconds() < FAILURE_DEDUP_WINDOW_S:
                return
            data["telemetry_failure_dedup"][key] = now_ts
            payload = {
                "ts": now_ts.isoformat(),
                "category": category,
                "severity": severity,
                "message_hash": message_hash,
                "context": context,
            }
            try:
                hass.async_create_task(reporter.send_failure(payload))
            except Exception:  # pragma: no cover — defensive
                _LOGGER.exception("Telemetry: failed to schedule send_failure")

        def _optimizer_failure_callback(category, exc, action):
            """W-4 — Inverter-Write-Exception → /v1/failure (D-16)."""
            blob = (type(exc).__name__ + str(exc)[:200]).encode("utf-8")
            mh = hashlib.sha256(blob).hexdigest()[:16]
            _emit_failure_dedup(
                category=category,
                severity="error",
                message_hash=mh,
                context={
                    "inverter_type": config.get(CONF_INVERTER_TYPE),
                    "action": action,
                },
            )

        def _check_sensor_unavailability():
            """D-16 — 10-min Watchdog auf 5 essenzielle Sensoren."""
            roles = {
                "battery_soc": config.get(CONF_BATTERY_SOC_SENSOR, ""),
                "pv_power": config.get(CONF_PV_POWER_SENSOR, ""),
                "grid_power": config.get(CONF_GRID_POWER_SENSOR, ""),
                "battery_power": config.get(CONF_BATTERY_POWER_SENSOR, ""),
                "hausverbrauch": CONSUMPTION_SENSOR,
            }
            now_ts = _now_utc()
            for role, eid in roles.items():
                if not eid:
                    data["telemetry_sensor_unavail_since"][role] = None
                    continue
                state = hass.states.get(eid)
                unavailable = (
                    state is None
                    or getattr(state, "state", None) in ("unknown", "unavailable", "")
                )
                since = data["telemetry_sensor_unavail_since"].get(role)
                if unavailable:
                    if since is None:
                        data["telemetry_sensor_unavail_since"][role] = now_ts
                    elif (now_ts - since).total_seconds() >= SENSOR_UNAVAIL_THRESHOLD_S:
                        _emit_failure_dedup(
                            category="sensor_unavailable",
                            severity="warning",
                            message_hash=role,
                            context={"sensor_role": role, "entity_id": eid},
                        )
                else:
                    data["telemetry_sensor_unavail_since"][role] = None

        def _check_forecast_streak(forecast):
            """D-16 — 3 None-Forecasts in Folge → Failure (1 h Dedup)."""
            try:
                remaining = forecast.remaining_today_kwh
                tomorrow = forecast.tomorrow_kwh
            except AttributeError:
                return
            if remaining is None and tomorrow is None:
                data["telemetry_forecast_none_streak"] += 1
                if data["telemetry_forecast_none_streak"] >= FORECAST_NONE_STREAK_THRESHOLD:
                    _emit_failure_dedup(
                        category="forecast_provider",
                        severity="warning",
                        message_hash="all_none",
                        context={
                            "forecast_source": config.get(CONF_FORECAST_SOURCE),
                        },
                    )
            else:
                data["telemetry_forecast_none_streak"] = 0

        def _emit_state_change(decision, prev, mode):
            """W-2 — sendet StateChange-Event mit normalisiertem transition-String."""
            mode_str = "ein" if mode == MODE_EIN else "test"
            payload = _build_state_change_payload(decision, prev, mode_str)
            try:
                hass.async_create_task(reporter.send_state_change(payload))
            except Exception:  # pragma: no cover
                _LOGGER.exception("Telemetry: failed to schedule send_state_change")

        def _capture_block_predictions(decision):
            """W-2 — speichert Predictions beim Block-Start für späteren Outcome.

            Initialisiert außerdem den hochauflösenden Block-Samples-Buffer für
            diesen event_type (vorherige stale Samples werden verworfen).
            """
            event_type = _normalize_state(decision.zustand)
            if event_type:
                data["block_predictions"][event_type] = _build_block_predictions(decision)
                # Frische Sitzung: alten Buffer für diesen Block-Typ wegwerfen.
                data["block_samples"][event_type] = []
                data["block_actuals_state"][event_type] = {
                    "pv_seen": False,
                    "cons_seen": False,
                    "grid_seen": False,
                    "actuals_invalid": False,
                }

        def _record_block_sample(decision):
            """Erfasst einen Power-Sample während eines aktiven Blocks.

            Wird im 30s-Optimizer-Cycle aufgerufen. Liest die Live-Werte aus
            decision.snapshot (pv_now_kw, consumption_now_kw, grid_now_kw) und
            hängt sie an den Buffer für den aktuellen event_type. None-Werte
            für einzelne Felder bleiben erhalten — die Trapez-Aggregation am
            Block-Ende filtert None korrekt heraus.
            """
            event_type = _normalize_state(decision.zustand)
            if event_type not in ("morgen_einspeisung", "abend_entladung"):
                return
            snap = decision.snapshot or {}
            pv_val = snap.get("pv_now_kw")
            cons_val = snap.get("consumption_now_kw")
            grid_val = snap.get("grid_now_kw")
            sample = {
                "ts": decision.timestamp,
                "pv_now_kw": pv_val,
                "consumption_now_kw": cons_val,
                "grid_now_kw": grid_val,
            }
            buf = data["block_samples"].setdefault(event_type, [])
            buf.append(sample)

            # Aktuals-Validität tracken: ein Sensor gilt als "kritisch ausgefallen"
            # nur wenn er im selben Block bereits mindestens einen Wert geliefert hat
            # und danach None wird. Das schließt nicht-konfigurierte Sensoren aus
            # (die liefern durchgängig None und setzen das Flag nicht).
            state = data["block_actuals_state"].setdefault(
                event_type,
                {"pv_seen": False, "cons_seen": False, "grid_seen": False, "actuals_invalid": False},
            )
            for seen_key, val in (
                ("pv_seen", pv_val),
                ("cons_seen", cons_val),
                ("grid_seen", grid_val),
            ):
                if val is not None:
                    state[seen_key] = True
                elif state[seen_key]:
                    state["actuals_invalid"] = True

        def _on_snapshot_tick(now):
            """D-14 — alle 30 min (xx:00, xx:30) ein Snapshot in den Queue schreiben."""
            current_optimizer = data.get("optimizer")
            if current_optimizer is None:
                return
            last_dec = current_optimizer.last_decision
            if last_dec is None:
                return
            select = data.get("select")
            mode = select._attr_current_option if select else MODE_AUS
            if mode == MODE_AUS:
                return  # D-08: keine Telemetrie wenn Aus
            mode_str = "ein" if mode == MODE_EIN else "test"
            snap_payload = _build_snapshot_payload(last_dec, mode_str, now)
            data["snapshot_queue"].append(snap_payload)

        async def _on_snapshot_flush(_now):
            """D-14 — 60-min Flush: Queue → send_snapshot_batch + Buffer-Drain."""
            queue = data.get("snapshot_queue") or []
            data["snapshot_queue"] = []
            cfg_enabled = config.get(CONF_TELEMETRY_ENABLED, False)
            if (
                queue
                and cfg_enabled
                and reporter.is_configured
                and telemetry_buffer.identity_known()
            ):
                try:
                    await reporter.send_snapshot_batch(queue)
                except Exception:
                    _LOGGER.exception("Telemetry: snapshot batch send failed")
            # Auch den persistenten Buffer drainen (alte Events von Backend-Down-Phasen)
            if reporter.is_configured and telemetry_buffer.identity_known():
                try:
                    await reporter.flush_buffer()
                except Exception:  # pragma: no cover
                    _LOGGER.exception("Telemetry: buffer flush failed")

        # Optimizer mit failure_callback erzeugen (W-4)
        optimizer = EEGOptimizer(
            hass, entry.entry_id, config, inverter, coordinator, provider,
            peakshare=peakshare_provider,
            failure_callback=_optimizer_failure_callback,
        )
        data["optimizer"] = optimizer

        # Telemetrie-Hooks im Closure-Scope für späteren Zugriff (Tests)
        data["_emit_state_change"] = _emit_state_change
        data["_capture_block_predictions"] = _capture_block_predictions
        data["_on_snapshot_tick"] = _on_snapshot_tick
        data["_on_snapshot_flush"] = _on_snapshot_flush
        data["_check_sensor_unavailability"] = _check_sensor_unavailability
        data["_check_forecast_streak"] = _check_forecast_streak
        data["_emit_failure_dedup"] = _emit_failure_dedup

        # Activity log: persistent ring buffer (last 5000 entries)
        from homeassistant.helpers.storage import Store
        ACTIVITY_STORE_KEY = f"{DOMAIN}_{entry.entry_id}_activity"
        activity_store = Store(hass, 1, ACTIVITY_STORE_KEY)
        activity_log = collections.deque(maxlen=5000)
        data["activity_log"] = activity_log
        activity_dirty = [False]

        # Load persisted entries
        try:
            stored = await activity_store.async_load()
            if stored and isinstance(stored, list):
                activity_log.extend(stored)
                _LOGGER.debug("Loaded %d activity log entries", len(stored))
        except Exception:
            _LOGGER.debug("No persisted activity log found")

        async def _save_activity_log():
            """Mark log as dirty — actual save happens at end of each cycle."""
            activity_dirty[0] = True

        async def _flush_activity_log():
            """Persist activity log to disk if dirty."""
            if not activity_dirty[0]:
                return
            activity_dirty[0] = False
            try:
                await activity_store.async_save(list(activity_log))
            except Exception as err:
                _LOGGER.warning("Failed to save activity log: %s", err)

        prev_zustand = [None]  # mutable container for closure
        last_heartbeat_hour = [None]  # track last logged hour
        first_cycle = [True]  # skip logging on first cycle (sensors not ready)

        def _log_activity(decision, reason):
            """Append an activity entry and fire a HA event."""
            # SOC aus dem Telemetrie-Snapshot (kann None sein, wenn Sensor unavailable).
            snap_dict = decision.snapshot if isinstance(decision.snapshot, dict) else {}
            soc_val = snap_dict.get("soc_pct")
            entry_data = {
                "timestamp": decision.timestamp,
                "zustand": decision.zustand,
                "reason": reason,
                "soc": soc_val,
                "min_soc": round(decision.min_soc_berechnet, 1),
                "pv_today": round(decision.morning_pv_today_kwh, 1),
                "pv_tomorrow": round(decision.discharge_pv_tomorrow_kwh, 1),
                "bedarf": round(decision.energiebedarf_kwh, 1),
                "discharge_bedarf": round(decision.discharge_demand_total_kwh, 1),
                "discharge_pv": round(decision.discharge_pv_tomorrow_kwh, 1),
                "ausführung": decision.ausführung,
                # Phase 11 (D-09): Slot-Kontext für Frontend-Anzeige + Telemetrie
                "discharge_active_slot": decision.discharge_active_slot,
            }
            activity_log.append(entry_data)
            hass.bus.async_fire("eeg_optimizer_activity", entry_data)
            hass.async_create_task(_save_activity_log())

        async def _optimizer_cycle(_now=None):
            select = data.get("select")
            mode = select._attr_current_option if select else MODE_AUS
            # Always run cycle to update status cards; optimizer only
            # executes inverter commands when mode is "Ein"
            # Read from data dict so hot-reload picks up the new optimizer
            current_optimizer = data.get("optimizer")
            if not current_optimizer:
                return
            decision = await current_optimizer.async_run_cycle(mode)
            decision_sensor = data.get("decision_sensor")
            if decision_sensor and decision:
                decision_sensor.update_from_decision(decision)

            # Activity logging: on state change + at full hours (:00)
            if decision:
                # ----------------------------------------------------------
                # Phase 8 — Telemetry State-Change + Watchdogs (D-13 / D-16)
                # ----------------------------------------------------------
                cfg_enabled = config.get(CONF_TELEMETRY_ENABLED, False)
                telemetry_active = (
                    cfg_enabled
                    and reporter.is_configured
                    and telemetry_buffer.identity_known()
                )
                if (
                    telemetry_active
                    and not first_cycle[0]
                    and mode != MODE_AUS
                    and decision.zustand != prev_zustand[0]
                ):
                    _emit_state_change(decision, prev_zustand[0], mode)
                    # Predictions auf Normal → Block-Übergang capturen (D-15)
                    if (
                        prev_zustand[0] == STATE_NORMAL
                        and decision.zustand in (
                            STATE_MORGEN_EINSPEISUNG,
                            STATE_ABEND_ENTLADUNG,
                        )
                    ):
                        _capture_block_predictions(decision)

                # Hochauflösendes Power-Sampling während aktiver Blocks (W-1).
                # Läuft jeden 30s-Cycle, unabhängig von State-Changes — speist
                # actual_pv_kwh / actual_consumption_kwh im Outcome.
                if (
                    telemetry_active
                    and not first_cycle[0]
                    and mode != MODE_AUS
                    and decision.zustand in (
                        STATE_MORGEN_EINSPEISUNG,
                        STATE_ABEND_ENTLADUNG,
                    )
                ):
                    try:
                        _record_block_sample(decision)
                    except Exception:  # pragma: no cover — defensive
                        _LOGGER.exception("Telemetry: block sample recording failed")

                if telemetry_active and not first_cycle[0] and mode != MODE_AUS:
                    # Watchdogs (D-16) — Sensor-Unavailability + Forecast-Streak
                    try:
                        _check_sensor_unavailability()
                    except Exception:  # pragma: no cover
                        _LOGGER.exception("Telemetry: sensor watchdog failed")
                    try:
                        _check_forecast_streak(
                            current_optimizer._provider.get_forecast()
                        )
                    except Exception:  # pragma: no cover
                        _LOGGER.exception("Telemetry: forecast watchdog failed")

                # Profile-Drift-Self-Heal: Wenn der Kapazitäts-Sensor beim Boot
                # noch unknown war, hat _boot_telemetry_send den manuellen
                # Fallback gesendet (z.B. 10 kWh). Sobald der Sensor jetzt
                # einen anderen Wert liefert, gleichen wir das Backend-Profil
                # einmalig nach. Läuft nur, wenn überhaupt schon ein Profil
                # gesendet wurde (Schlüssel im data-Dict vorhanden).
                if (
                    telemetry_active
                    and "telemetry_last_profile_capacity_kwh" in data
                ):
                    try:
                        live_cap = _resolve_battery_capacity_kwh(hass, config)
                    except Exception:  # pragma: no cover — defensive
                        live_cap = None
                    if live_cap != data["telemetry_last_profile_capacity_kwh"]:
                        # Sofort markieren, damit ein laufender Cycle nicht
                        # mehrfach denselben Re-Send queued.
                        data["telemetry_last_profile_capacity_kwh"] = live_cap

                        async def _resend_profile_for_capacity_drift():
                            try:
                                ident = telemetry_buffer.get_identity() or {}
                                profile = _build_telemetry_profile(
                                    hass, entry,
                                    identity_registered_at=ident.get("registered_at"),
                                )
                                await reporter.update_profile(profile)
                                # Authoritative: was tatsächlich gesendet wurde.
                                data["telemetry_last_profile_capacity_kwh"] = (
                                    profile.get("battery_capacity_kwh")
                                )
                            except Exception:  # pragma: no cover
                                _LOGGER.exception(
                                    "Telemetry: capacity drift profile "
                                    "re-send failed",
                                )
                        hass.async_create_task(
                            _resend_profile_for_capacity_drift()
                        )

                # Skip first cycle — sensors may not have real data yet
                if first_cycle[0]:
                    first_cycle[0] = False
                    prev_zustand[0] = decision.zustand
                elif decision.zustand != prev_zustand[0]:
                    reason = decision.zustand
                    # Watchdog: Begründung anhängen wenn Entladung wegen Netzbezug
                    # abgebrochen — Detektion über kanonischen Katalog-Key (D-09)
                    # statt String-Suche in der deutschen Freitext-Liste.
                    if (prev_zustand[0] == STATE_ABEND_ENTLADUNG
                            and REASON_DISCHARGE_ABORTED_TODAY in decision.blocked_by):
                        reason = "Normal — Netzbezug > 1 kW für > 5 Min, Entladung für heute abgebrochen"
                    _log_activity(decision, reason)
                    prev_zustand[0] = decision.zustand
                else:
                    from datetime import datetime as dt
                    now = dt.now()
                    current_hour = now.hour
                    if current_hour != last_heartbeat_hour[0]:
                        _log_activity(decision, "Heartbeat")
                        last_heartbeat_hour[0] = current_hour

            # Persist activity log to disk if changed
            await _flush_activity_log()

            # Update feed-in statistics
            _fstats = data.get("feedin_stats")
            if _fstats and decision:
                from datetime import datetime as _dt, timezone as _tz
                await _fstats.async_update(decision, _dt.now(tz=_tz.utc))
                await _fstats.async_flush()

            # Persist register write counter (only if changed)
            _ws = data.get("writes_store")
            if _ws and inverter.register_writes > 0:
                try:
                    await _ws.async_save(inverter.register_writes)
                except Exception:
                    pass

        data["_run_cycle"] = _optimizer_cycle

        if async_track_time_interval is not None:
            unsub = async_track_time_interval(
                hass, _optimizer_cycle, timedelta(seconds=30)
            )
            entry.async_on_unload(unsub)

            # Run initial cycle immediately — sensors are already populated
            # by the synchronous slow+fast update in async_setup_entry
            await _optimizer_cycle()

            # ----------------------------------------------------------
            # Phase 8: Snapshot-Timer (30 min) + Flush-Timer (60 min)
            # ----------------------------------------------------------
            cfg_enabled = config.get(CONF_TELEMETRY_ENABLED, False)
            if cfg_enabled and reporter.is_configured and async_track_time_change is not None:
                try:
                    unsub_snap = async_track_time_change(
                        hass, _on_snapshot_tick, hour=None, minute=[0, 30], second=0,
                    )
                    entry.async_on_unload(unsub_snap)
                except Exception:  # pragma: no cover — defensive
                    _LOGGER.exception("Telemetry: failed to register snapshot timer")
                try:
                    unsub_flush = async_track_time_interval(
                        hass, _on_snapshot_flush, timedelta(minutes=60),
                    )
                    entry.async_on_unload(unsub_flush)
                except Exception:  # pragma: no cover
                    _LOGGER.exception("Telemetry: failed to register flush timer")

                # Boot-Send: Profile-Update + Buffer-Drain.
                # WICHTIG — Delay von 180 s: Beim HA-Start sind Modbus-/
                # Cloud-Sensoren (z.B. sensor.batterien_akkukapazitat,
                # PV-Forecasts) häufig noch unknown/unavailable. Würden wir
                # sofort senden, ginge der Profile-Resolver auf den manuellen
                # Wizard-Default zurück (z.B. 10 kWh statt der echten 15 kWh
                # vom Huawei-Sensor) und das Backend bekäme dauerhaft den
                # falschen Wert. 3 min reichen für 1–2 Modbus-Polls.
                # Defence-in-Depth: Falls der Sensor auch nach 180 s noch
                # nicht da ist, fängt die Drift-Detection im Optimizer-Cycle
                # die spätere Aktualisierung ab.
                _BOOT_TELEMETRY_DELAY_S = 180

                if telemetry_buffer.identity_known():
                    async def _boot_telemetry_send(_now=None):
                        try:
                            identity = telemetry_buffer.get_identity() or {}
                            profile = _build_telemetry_profile(
                                hass, entry,
                                identity_registered_at=identity.get("registered_at"),
                            )
                            await reporter.update_profile(profile)
                            data["telemetry_last_profile_capacity_kwh"] = (
                                profile.get("battery_capacity_kwh")
                            )
                            await reporter.flush_buffer()
                        except Exception:  # pragma: no cover
                            _LOGGER.exception("Telemetry boot send failed")
                    if async_call_later is not None:
                        unsub_boot = async_call_later(
                            hass, _BOOT_TELEMETRY_DELAY_S, _boot_telemetry_send,
                        )
                        entry.async_on_unload(unsub_boot)
                    else:  # pragma: no cover — Fallback ohne HA-Helper
                        hass.async_create_task(_boot_telemetry_send())
                else:
                    # Default-on Opt-Out: neue Installationen werden mit
                    # cfg_enabled=True angelegt (config_flow.py). Damit das Flag
                    # auch wirkt, registrieren wir hier einmalig im Hintergrund.
                    # Bestehende Installationen mit explizit gewähltem False
                    # landen nicht in diesem Block, weil cfg_enabled bereits
                    # oben gefiltert hat.
                    async def _auto_register(_now=None):
                        try:
                            profile = _build_telemetry_profile(
                                hass, entry, identity_registered_at=None,
                            )
                            ok = await reporter.register(profile)
                            if ok:
                                data["telemetry_last_profile_capacity_kwh"] = (
                                    profile.get("battery_capacity_kwh")
                                )
                        except Exception:  # pragma: no cover
                            _LOGGER.exception("Telemetry auto-register failed")
                    if async_call_later is not None:
                        unsub_reg = async_call_later(
                            hass, _BOOT_TELEMETRY_DELAY_S, _auto_register,
                        )
                        entry.async_on_unload(unsub_reg)
                    else:  # pragma: no cover — Fallback ohne HA-Helper
                        hass.async_create_task(_auto_register())
    else:
        missing = []
        if not coordinator:
            missing.append("Verbrauchsprofil (coordinator)")
        if not provider:
            missing.append("PV-Prognose (provider)")
        _LOGGER.error(
            "EEG Energy Optimizer: Optimizer konnte nicht gestartet werden — "
            "fehlende Komponenten: %s",
            ", ".join(missing),
        )
        from homeassistant.components.persistent_notification import async_create
        async_create(
            hass,
            f"EEG Energy Optimizer konnte nicht vollstaendig starten. "
            f"Fehlende Komponenten: {', '.join(missing)}. "
            f"Bitte Setup-Wizard erneut durchlaufen.",
            title="EEG Energy Optimizer Warnung",
            notification_id="eeg_init_warning",
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry update — hot-reload optimizer or full restart after wizard."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if not data:
        return

    config = {**entry.data, **entry.options}

    if not data.get("platforms_loaded"):
        # Wizard just finished — need full reload to create platforms/sensors
        await hass.config_entries.async_reload(entry.entry_id)
        return

    # Hot-reload: re-create optimizer with updated config
    data["config"] = config
    optimizer = data.get("optimizer")
    if optimizer:
        inverter = data.get("inverter")
        coordinator = data.get("coordinator")
        provider = data.get("provider")
        peakshare_provider = data.get("peakshare")  # preserve across hot-reloads
        if inverter and coordinator and provider:
            # Sync lookback_weeks into coordinator if changed; trigger
            # background refresh so profile + dependent sensors reflect new window.
            new_lookback = config.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS)
            if getattr(coordinator, "_lookback_weeks", None) != new_lookback:
                coordinator._lookback_weeks = new_lookback
                refresh_fn = data.get("refresh_consumption_profile")
                if refresh_fn is not None:
                    hass.async_create_task(refresh_fn())

            new_optimizer = EEGOptimizer(
                hass, entry.entry_id, config, inverter, coordinator, provider,
                peakshare=peakshare_provider,
                # failure_callback aus dem ursprünglichen Optimizer übernehmen
                failure_callback=getattr(optimizer, "_failure_callback", None),
            )
            new_optimizer._prev_zustand = optimizer._prev_zustand
            new_optimizer._startup_time = optimizer._startup_time
            new_optimizer._grace_period_logged = optimizer._grace_period_logged
            data["optimizer"] = new_optimizer
            _LOGGER.info("EEG Energy Optimizer: Config hot-reloaded")

            # ----------------------------------------------------------
            # Phase 8: Profile-Update bei Settings-Change (D-17, W-3, I-4)
            # ----------------------------------------------------------
            reporter = data.get("telemetry_reporter")
            buffer = data.get("telemetry_buffer")
            if (
                reporter is not None
                and reporter.is_configured
                and config.get(CONF_TELEMETRY_ENABLED, False)
                and buffer is not None
                and buffer.identity_known()
            ):
                try:
                    identity = buffer.get_identity() or {}
                    profile = _build_telemetry_profile(
                        hass, entry,
                        identity_registered_at=identity.get("registered_at"),
                    )
                    await reporter.update_profile(profile)
                    data["telemetry_last_profile_capacity_kwh"] = (
                        profile.get("battery_capacity_kwh")
                    )
                except Exception:  # pragma: no cover — defensive
                    _LOGGER.exception("Telemetry profile update failed")

            # Run cycle immediately so dashboard reflects changes
            cycle_fn = data.get("_run_cycle")
            if cycle_fn:
                await cycle_fn()


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    """Unload EEG Energy Optimizer config entry."""
    from homeassistant.components.frontend import async_remove_panel

    async_remove_panel(hass, PANEL_URL_PATH)

    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    platforms_loaded = data.get("platforms_loaded", False)

    if platforms_loaded:
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, PLATFORMS
        )
    else:
        unload_ok = True

    if unload_ok:
        # Close inverter resources (e.g. Fronius pymodbus TCP socket)
        # before dropping the entry. Other inverters use HA-managed
        # services/entities and do not need explicit cleanup.
        inverter = data.get("inverter")
        disconnect = getattr(inverter, "async_disconnect", None)
        if disconnect is not None:
            try:
                await disconnect()
            except Exception:
                _LOGGER.exception(
                    "EEG Energy Optimizer: error disconnecting inverter on unload"
                )
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
