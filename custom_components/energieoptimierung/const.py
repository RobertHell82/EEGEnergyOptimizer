"""Constants for Energieoptimierung."""

DOMAIN = "energieoptimierung"

# ── Existing sensor defaults ─────────────────────────────────────────────
DEFAULT_CONSUMPTION_SENSOR = "sensor.solarnet_leistung_verbrauch"
DEFAULT_HEIZSTAB_SENSOR = "sensor.ohmpilot_leistung"
DEFAULT_WALLBOX_SENSOR = "sensor.goe_073871_nrg_11"
DEFAULT_TESLA_TRACKER = "device_tracker.tesla_standort"
DEFAULT_TESLA_SOC_SENSOR = "sensor.tesla_batteriestand"
DEFAULT_TESLA_LIMIT_SENSOR = "number.tesla_ladelimit"
DEFAULT_TESLA_CAPACITY_KWH = 75.0
DEFAULT_TESLA_EFFICIENCY = 0.90
DEFAULT_TESLA_HOME_ZONE = "home"
DEFAULT_BATTERY_SOC_SENSOR = "sensor.byd_battery_box_premium_hv_ladezustand"
DEFAULT_BATTERY_CAPACITY_SENSOR = "sensor.byd_battery_box_premium_hv_maximale_kapazitat"
DEFAULT_PUFFER_TEMP_SENSOR = "sensor.ohmpilot_temperatur"
DEFAULT_PUFFER_VOLUME_L = 600
DEFAULT_PUFFER_TARGET_TEMP = 80.0
DEFAULT_LOOKBACK_WEEKS = 8
DEFAULT_UPDATE_INTERVAL_MIN = 15
DEFAULT_SUNRISE_OFFSET_H = 1.0

# ── Existing config keys ─────────────────────────────────────────────────
CONF_CONSUMPTION_SENSOR = "consumption_sensor"
CONF_HEIZSTAB_SENSOR = "heizstab_sensor"
CONF_WALLBOX_SENSOR = "wallbox_sensor"
CONF_TESLA_TRACKER = "tesla_tracker"
CONF_TESLA_SOC_SENSOR = "tesla_soc_sensor"
CONF_TESLA_LIMIT_SENSOR = "tesla_limit_sensor"
CONF_TESLA_CAPACITY_KWH = "tesla_capacity_kwh"
CONF_TESLA_EFFICIENCY = "tesla_efficiency"
CONF_TESLA_HOME_ZONE = "tesla_home_zone"
CONF_BATTERY_SOC_SENSOR = "battery_soc_sensor"
CONF_BATTERY_CAPACITY_SENSOR = "battery_capacity_sensor"
CONF_PUFFER_TEMP_SENSOR = "puffer_temp_sensor"
CONF_PUFFER_VOLUME_L = "puffer_volume_l"
CONF_PUFFER_TARGET_TEMP = "puffer_target_temp"
CONF_LOOKBACK_WEEKS = "lookback_weeks"
CONF_UPDATE_INTERVAL = "update_interval_min"
CONF_SUNRISE_OFFSET = "sunrise_offset_h"

# ── Shared data keys ─────────────────────────────────────────────────────
DATA_COORDINATOR = "coordinator"
DATA_OPTIMIZER = "optimizer"

# ── Optimizer config keys ────────────────────────────────────────────────
CONF_PV_POWER_SENSOR = "pv_power_sensor"
CONF_FEED_IN_SENSOR = "feed_in_sensor"
CONF_SOLCAST_REMAINING_SENSOR = "solcast_remaining_sensor"
CONF_SOLCAST_MORGEN_SENSOR = "solcast_morgen_sensor"
CONF_HOLZVERGASER_SENSOR = "holzvergaser_sensor"
CONF_EINSPEISELIMIT_KW = "einspeiselimit_kw"
CONF_UEBERSCHUSS_FAKTOR = "ueberschuss_faktor"
CONF_MIN_SOC_ENTLADUNG = "min_soc_entladung"
CONF_ENTLADELEISTUNG_KW = "entladeleistung_kw"
CONF_ENTLADE_STARTZEIT = "entlade_startzeit"
CONF_SICHERHEITSPUFFER_PROZENT = "sicherheitspuffer_prozent"
CONF_MIN_WW_ENTLADUNG = "min_ww_entladung"
CONF_FRONIUS_IP = "fronius_ip"
CONF_FRONIUS_USER = "fronius_user"
CONF_FRONIUS_PASSWORD = "fronius_password"

# ── Optimizer defaults ───────────────────────────────────────────────────
DEFAULT_PV_POWER_SENSOR = "sensor.solarnet_pv_leistung"
DEFAULT_FEED_IN_SENSOR = "sensor.solarnet_leistung_netzeinspeisung"
DEFAULT_SOLCAST_REMAINING_SENSOR = "sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute"
DEFAULT_SOLCAST_MORGEN_SENSOR = "sensor.solcast_pv_forecast_prognose_morgen"
DEFAULT_HOLZVERGASER_SENSOR = "switch.holzvergaser_pumpe"
DEFAULT_EINSPEISELIMIT_KW = 4.0
DEFAULT_UEBERSCHUSS_FAKTOR = 1.25
DEFAULT_MIN_SOC_ENTLADUNG = 10
DEFAULT_ENTLADELEISTUNG_KW = 3.0
DEFAULT_ENTLADE_STARTZEIT = "20:00"
DEFAULT_SICHERHEITSPUFFER_PROZENT = 20
DEFAULT_MIN_WW_ENTLADUNG = 40.0
DEFAULT_FRONIUS_IP = "192.168.100.57"
DEFAULT_FRONIUS_USER = "customer"
DEFAULT_FRONIUS_PASSWORD = ""

# ── Strategies ───────────────────────────────────────────────────────────
STRATEGY_UEBERSCHUSS = "Überschuss"
STRATEGY_BALANCIERT = "Balanciert"
STRATEGY_ENGPASS = "Engpass"
STRATEGY_NACHT = "Nacht"
STRATEGY_INAKTIV = "Inaktiv"

# ── Heizstab modes ───────────────────────────────────────────────────────
HEIZSTAB_AUS = "Aus"
HEIZSTAB_1P = "1-Phasig"
HEIZSTAB_3P = "3-Phasig"
HEIZSTAB_POWER_KW = {HEIZSTAB_AUS: 0.0, HEIZSTAB_1P: 2.0, HEIZSTAB_3P: 6.0}

# ── HA entity IDs the optimizer writes to ────────────────────────────────
ENTITY_HEIZSTAB = "input_select.heizstab"
ENTITY_LADELIMIT = "input_number.batterie_ladelimit_kw"
ENTITY_EINSPEISUNG_AKTIV = "switch.energieoptimierung_einspeisung"
ENTITY_EINSPEISEWERT = "number.energieoptimierung_einspeiseleistung"

# ── Own sensor entity IDs (read by optimizer) ────────────────────────────
ENTITY_ENERGIEBEDARF = "sensor.energieoptimierung_energiebedarf_heute"
ENTITY_PROGNOSE_SUNRISE = "sensor.energieoptimierung_prognose_bis_sonnenaufgang"
ENTITY_PROGNOSE_MORGEN = "sensor.energieoptimierung_prognose_morgen"
