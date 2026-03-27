"""Constants for EEG Energy Optimizer integration."""

DOMAIN = "eeg_energy_optimizer"

CONF_INVERTER_TYPE = "inverter_type"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
CONF_BATTERY_CAPACITY_SENSOR = "battery_capacity_sensor"
CONF_BATTERY_CAPACITY_KWH = "battery_capacity_kwh"
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_GRID_POWER_SENSOR = "grid_power_sensor"
CONF_BATTERY_POWER_SENSOR = "battery_power_sensor"
CONF_HUAWEI_DEVICE_ID = "huawei_device_id"

INVERTER_TYPE_HUAWEI = "huawei_sun2000"
INVERTER_TYPE_SOLAX = "solax_gen4"

INVERTER_PREREQUISITES = {
    "huawei_sun2000": "huawei_solar",
    "solax_gen4": "solax_modbus",
}

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
CONF_UEBERSCHUSS_SCHWELLE = "ueberschuss_schwelle"
CONF_MORNING_END_TIME = "morning_end_time"
CONF_DISCHARGE_START_TIME = "discharge_start_time"
CONF_DISCHARGE_POWER_KW = "discharge_power_kw"
CONF_MIN_SOC = "min_soc"
CONF_SAFETY_BUFFER_PCT = "safety_buffer_pct"

DEFAULT_UEBERSCHUSS_SCHWELLE = 1.25
DEFAULT_MORNING_END_TIME = "10:00"
DEFAULT_DISCHARGE_START_TIME = "20:00"
DEFAULT_DISCHARGE_POWER_KW = 3.0
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

# Phase 4: Onboarding Panel
CONF_SETUP_COMPLETE = "setup_complete"
CONF_EXPERT_MODE = "expert_mode"
