"""Constants for EEG Energy Optimizer integration."""

DOMAIN = "eeg_energy_optimizer"

CONF_INVERTER_TYPE = "inverter_type"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
CONF_BATTERY_CAPACITY_SENSOR = "battery_capacity_sensor"
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor"
# Optional split-sensor pairs — used when an inverter exposes only directional
# (positive-only) sensors instead of one signed sensor (e.g. Fronius).
# When both *_export/*_charge AND *_import/*_discharge are set, the signed
# value is computed as (export − import) / (charge − discharge).
# The single-sensor convention (with INVERTER_SIGN_CONVENTIONS) still
# applies whenever the pair is incomplete.
CONF_GRID_POWER_EXPORT_SENSOR = "grid_power_export_sensor"
CONF_GRID_POWER_IMPORT_SENSOR = "grid_power_import_sensor"
CONF_BATTERY_POWER_CHARGE_SENSOR = "battery_power_charge_sensor"
CONF_BATTERY_POWER_DISCHARGE_SENSOR = "battery_power_discharge_sensor"
CONF_HUAWEI_DEVICE_ID = "huawei_device_id"

INVERTER_TYPE_HUAWEI = "huawei_sun2000"
INVERTER_TYPE_SOLAX = "solax_gen4"
INVERTER_TYPE_SOLAREDGE = "solaredge_storedge"
INVERTER_TYPE_FRONIUS = "fronius_gen24"

INVERTER_PREREQUISITES = {
    "huawei_sun2000": "huawei_solar",
    "solax_gen4": "solax_modbus",
    "solaredge_storedge": "solaredge_modbus_multi",
    "fronius_gen24": None,  # No HA integration needed for control — uses pymodbus directly
}

# Sign conventions per inverter type for battery and grid power sensors.
# battery_sign: +1 = positive means charging (Huawei), -1 = positive means discharging (SolaX)
# grid_sign:    +1 = positive means export (Huawei),   -1 = positive means import (SolaX)
# pv_includes_battery: True = PV sensor includes battery discharge power (SolarEdge ac_power)
#   → real PV = pv_raw + battery_raw (before sign normalization)
INVERTER_SIGN_CONVENTIONS = {
    "huawei_sun2000": {"battery_sign": 1, "grid_sign": 1},
    "solax_gen4":     {"battery_sign": -1, "grid_sign": -1},
    "solaredge_storedge": {"battery_sign": 1, "grid_sign": 1, "pv_includes_battery": True},
    # Fronius exposes only directional sensors (charging/discharging,
    # netzeinspeisung/netzbezug) — never a single signed value. The setup
    # therefore creates synthetic combined sensors that are *already canonical*
    # (positive = charging / positive = export). Sign convention = identity.
    "fronius_gen24": {"battery_sign": 1, "grid_sign": 1},
}

# Entity IDs of the synthetic combined sensors created at setup time when
# the user (or auto-detect) configures pair sensors. Held as constants so
# wizard, backfill, and sensor platform agree on the names.
COMBINED_BATTERY_POWER_SENSOR_ID = "sensor.eeg_energy_optimizer_battery_power"
COMBINED_GRID_POWER_SENSOR_ID = "sensor.eeg_energy_optimizer_grid_power"

CONF_FRONIUS_MODBUS_HOST = "fronius_modbus_host"
CONF_FRONIUS_MODBUS_PORT = "fronius_modbus_port"
DEFAULT_FRONIUS_MODBUS_PORT = 502

CONF_PV_POWER_SENSOR_2 = "pv_power_sensor_2"

# Phase 2: Forecast & Consumption
CONF_FORECAST_SOURCE = "forecast_source"
CONF_FORECAST_REMAINING_ENTITY = "forecast_remaining_entity"
CONF_FORECAST_TOMORROW_ENTITY = "forecast_tomorrow_entity"
CONF_LOOKBACK_WEEKS = "lookback_weeks"
CONF_UPDATE_INTERVAL_FAST = "update_interval_fast_min"
CONF_UPDATE_INTERVAL_SLOW = "update_interval_slow_min"

CONSUMPTION_SENSOR = "sensor.eeg_energy_optimizer_hausverbrauch"

FORECAST_SOURCE_SOLCAST = "solcast_solar"
FORECAST_SOURCE_FORECAST_SOLAR = "forecast_solar"

DEFAULT_LOOKBACK_WEEKS = 2
DEFAULT_UPDATE_INTERVAL_FAST = 1   # minutes
DEFAULT_UPDATE_INTERVAL_SLOW = 15  # minutes

WEEKDAY_KEYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]

# Phase 3: Optimizer
CONF_ENABLE_MORNING_DELAY = "enable_morning_delay"
CONF_ENABLE_NIGHT_DISCHARGE = "enable_night_discharge"
CONF_ÜBERSCHUSS_SCHWELLE = "ueberschuss_schwelle"  # legacy config key, do not rename string
CONF_MORNING_START_OFFSET = "morning_start_offset"
CONF_MORNING_END_TIME = "morning_end_time"
CONF_DISCHARGE_START_TIME = "discharge_start_time"
CONF_DISCHARGE_POWER_KW = "discharge_power_kw"
CONF_MIN_SOC = "min_soc"
CONF_SAFETY_BUFFER_PCT = "safety_buffer_pct"
CONF_ENABLE_PEAKSHARE = "enable_peakshare"
CONF_PEAKSHARE_COMMUNITY = "peakshare_community"

DEFAULT_ENABLE_PEAKSHARE = True
DEFAULT_PEAKSHARE_COMMUNITY = "BEG"

DEFAULT_UEBERSCHUSS_SCHWELLE = 1.25
DEFAULT_MORNING_START_OFFSET = 0
DEFAULT_MORNING_END_TIME = "11:00"
DEFAULT_DISCHARGE_START_TIME = "20:00"
DEFAULT_DISCHARGE_POWER_KW = 5.0
DEFAULT_MIN_SOC = 10
DEFAULT_SAFETY_BUFFER_PCT = 25

# Optimizer modes (D-17)
MODE_EIN = "Ein"
MODE_TEST = "Test"
MODE_AUS = "Aus"
OPTIMIZER_MODES = [MODE_EIN, MODE_TEST]

# Optimizer states (D-22)
STATE_MORGEN_EINSPEISUNG = "Morgen-Einspeisung"
STATE_NORMAL = "Normal"
STATE_ABEND_ENTLADUNG = "Abend-Entladung"

# Startup grace period: delay inverter commands after HA restart
# to let sensors (PV forecast, sun.sun) settle with valid data
STARTUP_GRACE_SECONDS = 90

# Feed-in statistics: compact session details to daily aggregates after N days
STATS_COMPACT_AFTER_DAYS = 90

# Map optimizer states to statistics keys
STATE_TO_STATS_KEY = {
    STATE_MORGEN_EINSPEISUNG: "morning",
    STATE_ABEND_ENTLADUNG: "evening",
}

# Phase 4: Onboarding Panel
CONF_SETUP_COMPLETE = "setup_complete"
CONF_EXPERT_MODE = "expert_mode"
CONF_ENABLE_SIMULATION = "enable_simulation"
CONF_ENABLE_MANUAL_CONTROL = "enable_manual_control"

# ------------------------------------------------------------------
# Phase 8: Telemetry (v1.1)
# ------------------------------------------------------------------
# Backend-URL und Bootstrap-Token werden nur im RELEASE-Repo gefüllt.
# Im DEV-Repo bleiben sie leer → TelemetryReporter ist ein No-Op.
# Siehe .planning/milestones/v1.1-phases/08-ha-reporter-modul/08-CONTEXT.md, D-01.
TELEMETRY_BACKEND_URL = "https://eeg-telemetry.robert-hell.workers.dev"
# Siehe 08-CONTEXT.md D-01 — Bootstrap-Token gibt Anlagen das Recht, sich am Backend
# einmalig zu registrieren. Pro Anlage wird ein eigener api_key generiert; der hardcoded
# Bootstrap-Token dient nur als IP-Rate-Limit-Schutz, nicht als echte Authentifizierung.
TELEMETRY_BOOTSTRAP_TOKEN = "4c604d119e5e4c08f0a020e3d2aab487bcd05ab62de3fcaf0dd9138185744fa6"

# Storage-Keys (D-04, D-06). Identity und Buffer nutzen GETRENNTE Dateien,
# damit ein korrupter Buffer die Identity nicht zerstören kann.
STORAGE_TELEMETRY = f"{DOMAIN}.telemetry"
STORAGE_TELEMETRY_BUFFER = f"{DOMAIN}.telemetry_buffer"

# Config-Entry-Flag, default False (08-03 ergänzt es via async_migrate_entry v12→v13).
CONF_TELEMETRY_ENABLED = "telemetry_enabled"

# Buffer- und HTTP-Defaults
TELEMETRY_BUFFER_MAX = 100        # D-06: Ringbuffer-Maximum
TELEMETRY_HTTP_TIMEOUT = 10       # D-34: Per-Request-Timeout in Sekunden
TELEMETRY_BACKOFF_MIN_S = 60      # D-36: 1 min initialer Backoff
TELEMETRY_BACKOFF_MAX_S = 1800    # D-36: 30 min Maximum
TELEMETRY_FLUSH_BATCH = 10        # D-35: maximal Events pro erfolgreichem Send-Drain

# Settings-Whitelist für /v1/profile (D-18, D-19). NICHTS außerhalb dieses
# Tupels wird gesendet — entity_ids, IPs, Gerätenamen etc. können nicht leaken.
TELEMETRY_SETTINGS_KEYS = (
    "enable_morning_delay",
    "enable_night_discharge",
    "enable_peakshare",
    "morning_start_offset",
    "morning_end_time",
    "discharge_start_time",
    "discharge_power_kw",
    "min_soc",
    "safety_buffer_pct",
    "peakshare_community",
    "forecast_source",
)

# Phase 8 — Runtime Watchdog-Schwellen (08-03, D-16)
SENSOR_UNAVAIL_THRESHOLD_S = 600        # Sensor 10 min unverfügbar → Failure
FORECAST_NONE_STREAK_THRESHOLD = 3      # 3 aufeinanderfolgende None-Forecasts → Failure
FAILURE_DEDUP_WINDOW_S = 3600           # 1 h Dedup pro (category, message_hash)
