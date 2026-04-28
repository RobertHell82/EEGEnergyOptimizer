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

DEFAULT_LOOKBACK_WEEKS = 4
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
