"""EEG Energy Optimizer integration for Home Assistant."""

from __future__ import annotations

import collections
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import logging

from .const import (
    DOMAIN,
    MODE_AUS,
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
    COMBINED_BATTERY_POWER_SENSOR_ID,
    COMBINED_GRID_POWER_SENSOR_ID,
    CONSUMPTION_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    INVERTER_SIGN_CONVENTIONS,
)
from .inverter import create_inverter
from .optimizer import EEGOptimizer, REASON_DISCHARGE_ABORTED_TODAY
from .websocket_api import async_register_websocket_commands

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.event import async_track_time_interval, async_call_later
except ImportError:
    async_track_time_interval = None  # type: ignore[assignment]
    async_call_later = None  # type: ignore[assignment]

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
            meta = StatisticMetaData(
                has_mean=True,
                has_sum=False,
                name=name,
                source="recorder",
                statistic_id=stat_id,
                unit_of_measurement="kW",
            )
            try:
                async_import_statistics(hass, meta, data, mean_type="arithmetic")
            except TypeError:
                async_import_statistics(hass, meta, data)

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
        # Pair-sensor support (Fronius). Schema-only bump — pair keys are
        # written by the wizard / auto-detect when (and only when) the user
        # actually has a Fronius / SolarNet split-sensor setup. Existing
        # entries with single signed sensors get the bump without their data
        # dict being touched.
        hass.config_entries.async_update_entry(entry, data=entry.data, version=13)

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

    # Read version from manifest for cache-busting query parameter
    manifest_path = Path(__file__).parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    panel_version = manifest.get("version", "0")

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
        optimizer = EEGOptimizer(hass, entry.entry_id, config, inverter, coordinator, provider, peakshare=peakshare_provider)
        data["optimizer"] = optimizer

        # Feed-in statistics tracker
        from .statistics import FeedinStatistics
        feedin_stats = FeedinStatistics(hass, entry.entry_id, config)
        await feedin_stats.async_load()
        data["feedin_stats"] = feedin_stats

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
            entry_data = {
                "timestamp": decision.timestamp,
                "zustand": decision.zustand,
                "reason": reason,
                "soc": round(decision.discharge_soc, 0),
                "min_soc": round(decision.min_soc_berechnet, 1),
                "pv_today": round(decision.morning_pv_today_kwh, 1),
                "pv_tomorrow": round(decision.discharge_pv_tomorrow_kwh, 1),
                "bedarf": round(decision.energiebedarf_kwh, 1),
                "discharge_bedarf": round(decision.discharge_demand_total_kwh, 1),
                "discharge_pv": round(decision.discharge_pv_tomorrow_kwh, 1),
                "ausführung": decision.ausführung,
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
                # Skip first cycle — sensors may not have real data yet
                if first_cycle[0]:
                    first_cycle[0] = False
                    prev_zustand[0] = decision.zustand
                elif decision.zustand != prev_zustand[0]:
                    reason = decision.zustand
                    # Watchdog: Begründung anhängen wenn Entladung wegen Netzbezug
                    # abgebrochen — Detektion über kanonischen Katalog-Key (D-09)
                    # statt String-Suche in der deutschen Freitext-Liste.
                    if (prev_zustand[0] == "Abend-Entladung"
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
            )
            new_optimizer._prev_zustand = optimizer._prev_zustand
            new_optimizer._startup_time = optimizer._startup_time
            new_optimizer._grace_period_logged = optimizer._grace_period_logged
            data["optimizer"] = new_optimizer
            _LOGGER.info("EEG Energy Optimizer: Config hot-reloaded")
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
