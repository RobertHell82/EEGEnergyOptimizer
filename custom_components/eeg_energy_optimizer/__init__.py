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
    CONF_PV_POWER_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_GRID_POWER_SENSOR,
    CONF_LOOKBACK_WEEKS,
    CONSUMPTION_SENSOR,
    DEFAULT_BATTERY_POWER_SENSOR,
    DEFAULT_GRID_POWER_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
)
from .inverter import create_inverter
from .optimizer import EEGOptimizer
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

_BACKFILL_SKIP_THRESHOLD = 168  # 1 week of hourly entries


async def async_backfill_hausverbrauch_stats(
    hass: HomeAssistant, config: dict
) -> None:
    """One-time backfill of Hausverbrauch statistics from source sensors.

    Calculates historical Hausverbrauch = max(PV - Battery - Grid, 0) per hour
    from the 3 source sensors and imports them into the HA recorder so that the
    ConsumptionCoordinator can build a consumption profile immediately.

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

        # --- Check if backfill is needed ---
        now = datetime.now(tz=timezone.utc)
        two_weeks_ago = now - timedelta(weeks=2)
        recorder_instance = get_instance(hass)

        existing = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            hass,
            two_weeks_ago,
            now,
            {CONSUMPTION_SENSOR},
            "hour",
            None,
            {"mean"},
        )
        existing_entries = existing.get(CONSUMPTION_SENSOR, [])
        if len(existing_entries) > _BACKFILL_SKIP_THRESHOLD:
            _LOGGER.info(
                "Hausverbrauch backfill skipped — sufficient data (%d entries)",
                len(existing_entries),
            )
            return

        # --- Read source sensor IDs from config ---
        # Fallback to Huawei defaults if not in config (pre-wizard configs)
        pv_id = config.get(CONF_PV_POWER_SENSOR, "") or "sensor.inverter_eingangsleistung"
        battery_id = config.get(CONF_BATTERY_POWER_SENSOR, DEFAULT_BATTERY_POWER_SENSOR)
        grid_id = config.get(CONF_GRID_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR)

        lookback_weeks = config.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS)
        start_time = now - timedelta(weeks=lookback_weeks)

        # --- Load mean statistics for all 3 source sensors ---
        result = await recorder_instance.async_add_executor_job(
            statistics_during_period,
            hass,
            start_time,
            now,
            {pv_id, battery_id, grid_id},
            "hour",
            None,
            {"mean"},
        )

        pv_entries = result.get(pv_id, [])
        battery_entries = result.get(battery_id, [])
        grid_entries = result.get(grid_id, [])

        if not pv_entries or not battery_entries or not grid_entries:
            _LOGGER.warning(
                "Hausverbrauch backfill skipped — missing source data "
                "(PV=%d, Battery=%d, Grid=%d entries)",
                len(pv_entries),
                len(battery_entries),
                len(grid_entries),
            )
            return

        # --- Index entries by start timestamp ---
        def _index_by_start(entries: list[dict]) -> dict[float, float]:
            indexed: dict[float, float] = {}
            for e in entries:
                ts = e.get("start") or e.get("start_ts")
                mean = e.get("mean")
                if ts is None or mean is None:
                    continue
                # Normalize to float timestamp
                if isinstance(ts, str):
                    ts_float = datetime.fromisoformat(ts).timestamp()
                else:
                    ts_float = float(ts)
                indexed[ts_float] = mean
            return indexed

        pv_by_ts = _index_by_start(pv_entries)
        battery_by_ts = _index_by_start(battery_entries)
        grid_by_ts = _index_by_start(grid_entries)

        # --- Calculate Hausverbrauch for each hour where all 3 have data ---
        common_timestamps = sorted(
            set(pv_by_ts.keys()) & set(battery_by_ts.keys()) & set(grid_by_ts.keys())
        )

        if not common_timestamps:
            _LOGGER.warning("Hausverbrauch backfill skipped — no overlapping timestamps")
            return

        statistics: list[StatisticData] = []
        for ts in common_timestamps:
            hausverbrauch = max(
                pv_by_ts[ts] - battery_by_ts[ts] - grid_by_ts[ts], 0.0
            )
            value = round(hausverbrauch, 3)
            hour_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            statistics.append(
                StatisticData(start=hour_dt, mean=value, state=value)
            )

        # --- Import statistics ---
        metadata = StatisticMetaData(
            has_mean=True,
            has_sum=False,
            name="EEG Energy Optimizer Hausverbrauch",
            source="recorder",
            statistic_id=CONSUMPTION_SENSOR,
            unit_of_measurement="kW",
        )

        async_import_statistics(hass, metadata, statistics)

        start_date = datetime.fromtimestamp(
            common_timestamps[0], tz=timezone.utc
        ).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(
            common_timestamps[-1], tz=timezone.utc
        ).strftime("%Y-%m-%d")
        _LOGGER.info(
            "Backfilled %d hourly statistics for Hausverbrauch from %s to %s",
            len(statistics),
            start_date,
            end_date,
        )

    except Exception:
        _LOGGER.exception("Hausverbrauch backfill failed (non-critical)")

PANEL_FRONTEND_URL = "/eeg_optimizer_panel"
PANEL_ICON = "mdi:battery-charging-high"
PANEL_TITLE = "EEG Optimizer"
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
        # ueberschuss_schwelle no longer used — safety_buffer_pct replaces it
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
    frontend_path = str(Path(__file__).parent / "frontend")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_FRONTEND_URL, frontend_path, cache_headers=False)]
    )

    # Read version from manifest for cache-busting query parameter
    manifest_path = Path(__file__).parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    panel_version = manifest.get("version", "0")

    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
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
            f"EEG Optimizer: Wechselrichter konnte nicht erstellt werden — {err}",
            title="EEG Optimizer Fehler",
            notification_id="eeg_inverter_error",
        )
        return False
    hass.data[DOMAIN][entry.entry_id]["inverter"] = inverter

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.data[DOMAIN][entry.entry_id]["platforms_loaded"] = True

    # After platforms are set up, coordinator/provider/select are available
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data.get("coordinator")
    provider = data.get("provider")

    if coordinator and provider:
        optimizer = EEGOptimizer(hass, entry.entry_id, config, inverter, coordinator, provider)
        data["optimizer"] = optimizer

        # Activity log: persistent ring buffer (last 5000 entries)
        from homeassistant.helpers.storage import Store
        ACTIVITY_STORE_KEY = f"{DOMAIN}_{entry.entry_id}_activity"
        activity_store = Store(hass, 1, ACTIVITY_STORE_KEY)
        activity_log = collections.deque(maxlen=2500)
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
                "ausfuehrung": decision.ausfuehrung,
            }
            activity_log.append(entry_data)
            hass.bus.async_fire("eeg_optimizer_activity", entry_data)
            hass.async_create_task(_save_activity_log())

        async def _optimizer_cycle(_now=None):
            select = data.get("select")
            mode = select._attr_current_option if select else MODE_AUS
            # Always run cycle to update status cards; optimizer only
            # executes inverter commands when mode is "Ein"
            decision = await optimizer.async_run_cycle(mode)
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
                    _log_activity(decision, decision.zustand)
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
            "EEG Optimizer: Optimizer konnte nicht gestartet werden — "
            "fehlende Komponenten: %s",
            ", ".join(missing),
        )
        from homeassistant.components.persistent_notification import async_create
        async_create(
            hass,
            f"EEG Optimizer konnte nicht vollstaendig starten. "
            f"Fehlende Komponenten: {', '.join(missing)}. "
            f"Bitte Setup-Wizard erneut durchlaufen.",
            title="EEG Optimizer Warnung",
            notification_id="eeg_init_warning",
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry update."""
    await hass.config_entries.async_reload(entry.entry_id)


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
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
