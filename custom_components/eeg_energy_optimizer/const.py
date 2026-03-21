"""Constants for EEG Energy Optimizer integration."""

DOMAIN = "eeg_energy_optimizer"

CONF_INVERTER_TYPE = "inverter_type"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
CONF_BATTERY_CAPACITY_SENSOR = "battery_capacity_sensor"
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_HUAWEI_DEVICE_ID = "huawei_device_id"

INVERTER_TYPE_HUAWEI = "huawei_sun2000"

INVERTER_PREREQUISITES = {
    "huawei_sun2000": "huawei_solar",
}
