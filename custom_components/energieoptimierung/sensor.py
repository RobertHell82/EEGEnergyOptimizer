"""
Sensors for Energieoptimierung.

Creates 15 sensors:
  1.  sensor.prognose_bis_sonnenaufgang             (jetzt → Sonnenaufgang+1h)
  2.  sensor.prognose_bis_sonnenuntergang           (jetzt → Sonnenuntergang)
  3.  sensor.batterie_fehlende_energie              (kWh bis Batterie voll)
  4.  sensor.tesla_fehlende_ladeenergie             (kWh bis Tesla auf Ladelimit)
  5.  sensor.puffer_aufheizenergie                  (kWh bis Puffer auf Zieltemp)
  6.  sensor.energiebedarf_heute                    (Summe 2+3+4+5)
  7.  sensor.verbrauchsprofil                       (Ø Stundenprofil pro Zone)
  8.  sensor.prognose_morgen                        (Tag +1, 00:00-24:00)
  9-14. sensor.prognose_tag_2 .. _tag_7             (Tag +2 bis +7)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_CONSUMPTION_SENSOR,
    CONF_HEIZSTAB_SENSOR,
    CONF_WALLBOX_SENSOR,
    CONF_LOOKBACK_WEEKS,
    CONF_PUFFER_TARGET_TEMP,
    CONF_PUFFER_TEMP_SENSOR,
    CONF_PUFFER_VOLUME_L,
    CONF_SUNRISE_OFFSET,
    CONF_TESLA_CAPACITY_KWH,
    CONF_TESLA_EFFICIENCY,
    CONF_TESLA_HOME_ZONE,
    CONF_TESLA_LIMIT_SENSOR,
    CONF_TESLA_SOC_SENSOR,
    CONF_TESLA_TRACKER,
    CONF_UPDATE_INTERVAL,
    DATA_COORDINATOR,
    DATA_OPTIMIZER,
    DEFAULT_BATTERY_CAPACITY_SENSOR,
    DEFAULT_BATTERY_SOC_SENSOR,
    DEFAULT_CONSUMPTION_SENSOR,
    DEFAULT_HEIZSTAB_SENSOR,
    DEFAULT_WALLBOX_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_PUFFER_TARGET_TEMP,
    DEFAULT_PUFFER_TEMP_SENSOR,
    DEFAULT_PUFFER_VOLUME_L,
    DEFAULT_SUNRISE_OFFSET_H,
    DEFAULT_TESLA_CAPACITY_KWH,
    DEFAULT_TESLA_EFFICIENCY,
    DEFAULT_TESLA_HOME_ZONE,
    DEFAULT_TESLA_LIMIT_SENSOR,
    DEFAULT_TESLA_SOC_SENSOR,
    DEFAULT_TESLA_TRACKER,
    DEFAULT_UPDATE_INTERVAL_MIN,
    DOMAIN,
    STRATEGY_INAKTIV,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo

from .coordinator import VerbrauchsCoordinator

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, DOMAIN)},
    name="Energieoptimierung",
    manufacturer="Custom",
    model="Energieoptimierung",
    entry_type=DeviceEntryType.SERVICE,
)

_LOGGER = logging.getLogger(__name__)

WEEKDAY_NAMES_DE = [
    "Montag", "Dienstag", "Mittwoch", "Donnerstag",
    "Freitag", "Samstag", "Sonntag",
]

ZONE_MAP = {0: "mo-do", 1: "mo-do", 2: "mo-do", 3: "mo-do",
            4: "fr", 5: "sa", 6: "so"}


def format_stundenprofil(profil: list[dict]) -> dict[str, str]:
    """Format hourly profile as individual attributes per hour."""
    if not profil:
        return {}
    result = {}
    for h in profil:
        key = f"{h['stunde']} {h['zone']}"
        result[key] = f"{h['verbrauch_w']}W = {h['kwh']:.2f} kWh"
    return result


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all forecast sensors from a config entry."""
    conf = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})

    consumption_id = conf.get(CONF_CONSUMPTION_SENSOR, DEFAULT_CONSUMPTION_SENSOR)
    heizstab_id = conf.get(CONF_HEIZSTAB_SENSOR, DEFAULT_HEIZSTAB_SENSOR)
    wallbox_id = conf.get(CONF_WALLBOX_SENSOR, DEFAULT_WALLBOX_SENSOR)
    lookback = conf.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS)

    coordinator = VerbrauchsCoordinator(
        hass=hass,
        consumption_sensor=consumption_id,
        heizstab_sensor=heizstab_id,
        wallbox_sensor=wallbox_id,
        lookback_weeks=lookback,
    )
    hass.data[DOMAIN][DATA_COORDINATOR] = coordinator

    update_interval = conf.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN)

    _LOGGER.warning("Energieoptimierung: Loading initial statistics...")
    await coordinator.async_update()
    _LOGGER.warning(
        "Energieoptimierung: Loaded %d data points", coordinator.stats_count
    )

    meta = {
        "consumption_id": consumption_id,
        "heizstab_id": heizstab_id,
        "wallbox_id": wallbox_id,
        "lookback_weeks": lookback,
    }

    # Slow sensors: statistics-based, update every 15min (configurable)
    sunset_sensor = SunsetForecastSensor(hass, coordinator, meta)
    slow_sensors: list[SensorEntity] = [
        SunriseForecastSensor(hass, conf, coordinator, meta),
        sunset_sensor,
        VerbrauchsprofilSensor(hass, coordinator, meta),
    ] + [
        DailyForecastSensor(hass, coordinator, meta, day_offset=d)
        for d in range(0, 8)
    ]

    # Fast sensors: live state-based, update every 2min
    battery_sensor = BatteryMissingEnergySensor(hass, conf)
    tesla_sensor = TeslaMissingEnergySensor(hass, conf)
    puffer_sensor = PufferEnergySensor(hass, conf)
    demand_sensor = EnergyDemandTodaySensor(
        hass, battery_sensor, puffer_sensor, tesla_sensor, sunset_sensor,
    )
    fast_sensors: list[SensorEntity] = [
        battery_sensor,
        tesla_sensor,
        puffer_sensor,
        demand_sensor,
    ]

    # Optimizer decision sensor (reads from optimizer if available)
    optimizer = hass.data.get(DOMAIN, {}).get(DATA_OPTIMIZER)
    decision_sensor = OptimizerDecisionSensor(hass, optimizer)

    all_sensors = slow_sensors + fast_sensors + [decision_sensor]
    async_add_entities(all_sensors, True)

    async def _slow_update(_now=None):
        await coordinator.async_update()
        for sensor in slow_sensors:
            await sensor.async_update()
            sensor.async_write_ha_state()

    async def _fast_update(_now=None):
        for sensor in fast_sensors:
            await sensor.async_update()
            sensor.async_write_ha_state()

    async_track_time_interval(
        hass, _slow_update, timedelta(minutes=update_interval)
    )
    async_track_time_interval(
        hass, _fast_update, timedelta(minutes=2)
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 1: Prognose bis Sonnenaufgang
# ═══════════════════════════════════════════════════════════════════════════

class SunriseForecastSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Prognose bis Sonnenaufgang"
    _attr_unique_id = "energieoptimierung_prognose_bis_sonnenaufgang"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:crystal-ball"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, config, coordinator, meta):
        self.hass = hass
        self._coordinator = coordinator
        self._meta = meta
        self._sunrise_offset = config.get(CONF_SUNRISE_OFFSET, DEFAULT_SUNRISE_OFFSET_H)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        now = dt_util.now()
        target = self._get_target_time(now)
        if target is None or target <= now:
            self._attr_native_value = 0.0
            self._attr_extra_state_attributes = {"hinweis": "Kein Ziel"}
            return

        result = self._coordinator.calculate_period(now, target)
        zone = ZONE_MAP[now.weekday()]

        target_str = target.strftime("%H:%M")
        self._attr_native_value = round(result["verbrauch_kwh"], 2)
        attrs = {
            "zeitraum": f"Jetzt → {target_str} ({result['stunden']:.1f}h)",
            "tag": f"{WEEKDAY_NAMES_DE[now.weekday()]} ({zone})",
            "verbrauch": f"{result['verbrauch_kwh']:.2f} kWh",
            "grundlage": f"Ø {self._meta['lookback_weeks']} Wo, Zone {zone}, {self._coordinator.stats_count} Punkte",
        }
        attrs.update(format_stundenprofil(result["stundenprofil"]))
        self._attr_extra_state_attributes = attrs

    def _get_sunrise(self, now):
        sun = self.hass.states.get("sun.sun")
        if not sun:
            return None
        nr = sun.attributes.get("next_rising")
        try:
            return datetime.fromisoformat(str(nr)) if nr else None
        except (ValueError, TypeError):
            return None

    def _get_target_time(self, now):
        s = self._get_sunrise(now)
        return s + timedelta(hours=self._sunrise_offset) if s else None


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 2: Prognose bis Sonnenuntergang
# ═══════════════════════════════════════════════════════════════════════════

class SunsetForecastSensor(SensorEntity):
    """Forecast consumption from now until sunset.

    After sunset until midnight: shows 0.
    After midnight: shows forecast from now until next sunset.
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Prognose bis Sonnenuntergang"
    _attr_unique_id = "energieoptimierung_prognose_bis_sonnenuntergang"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:weather-sunset-down"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, coordinator, meta):
        self.hass = hass
        self._coordinator = coordinator
        self._meta = meta
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        now = dt_util.now()
        sunset = self._get_sunset(now)

        if sunset is None:
            # None means either no sun entity or after sunset until midnight
            sun = self.hass.states.get("sun.sun")
            if sun and sun.state == "below_horizon":
                self._attr_native_value = 0.0
                self._attr_extra_state_attributes = {"hinweis": "Nach Sonnenuntergang"}
            else:
                self._attr_native_value = None
                self._attr_extra_state_attributes = {"hinweis": "Kein Sonnenuntergang verfügbar"}
            return

        # Before sunset: calculate consumption from now until sunset
        result = self._coordinator.calculate_period(now, sunset)
        zone = ZONE_MAP[now.weekday()]

        self._attr_native_value = round(result["verbrauch_kwh"], 2)
        attrs = {
            "zeitraum": f"Jetzt → {sunset.strftime('%H:%M')} ({result['stunden']:.1f}h)",
            "tag": f"{WEEKDAY_NAMES_DE[now.weekday()]} ({zone})",
            "sonnenuntergang": sunset.strftime("%H:%M"),
            "verbrauch": f"{result['verbrauch_kwh']:.2f} kWh",
            "grundlage": f"Ø {self._meta['lookback_weeks']} Wo, Zone {zone}, {self._coordinator.stats_count} Punkte",
        }
        attrs.update(format_stundenprofil(result["stundenprofil"]))
        self._attr_extra_state_attributes = attrs

    def _get_sunset(self, now):
        """Get the relevant sunset time.

        Before sunset: returns today's sunset (next_setting).
        After sunset until midnight: returns None (signals 0).
        After midnight: returns today's upcoming sunset (next_setting).
        """
        sun = self.hass.states.get("sun.sun")
        if not sun:
            return None

        # sun.sun state is "below_horizon" after sunset
        if sun.state == "below_horizon":
            ns = sun.attributes.get("next_setting")
            try:
                next_setting = dt_util.as_local(datetime.fromisoformat(str(ns))) if ns else None
            except (ValueError, TypeError):
                return None
            # After midnight: next_setting is today's sunset → use it
            if next_setting and next_setting.date() == now.date():
                return next_setting
            # Between sunset and midnight: next_setting is tomorrow → return None
            return None

        # Sun is above horizon: next_setting is today's sunset
        ns = sun.attributes.get("next_setting")
        try:
            return dt_util.as_local(datetime.fromisoformat(str(ns))) if ns else None
        except (ValueError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 3: Fehlende Energie bis Batterie voll
# ═══════════════════════════════════════════════════════════════════════════

class BatteryMissingEnergySensor(SensorEntity):
    """Shows how much energy is needed to fully charge the battery.

    Formula: (100 - SOC%) / 100 * capacity_kWh
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Batterie fehlende Energie"
    _attr_unique_id = "energieoptimierung_batterie_fehlende_energie"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:battery-charging-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, config):
        self.hass = hass
        self._soc_id = config.get(CONF_BATTERY_SOC_SENSOR, DEFAULT_BATTERY_SOC_SENSOR)
        self._capacity_id = config.get(CONF_BATTERY_CAPACITY_SENSOR, DEFAULT_BATTERY_CAPACITY_SENSOR)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        soc = self._get_float(self._soc_id)
        capacity_raw = self._get_float(self._capacity_id)

        if soc is None or capacity_raw is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "hinweis": "SOC oder Kapazität nicht verfügbar",
                "soc_sensor": self._soc_id,
                "kapazitaet_sensor": self._capacity_id,
            }
            return

        # Auto-detect unit: if unit is Wh or value > 1000, assume Wh → convert to kWh
        capacity_kwh = capacity_raw
        cap_state = self.hass.states.get(self._capacity_id)
        unit = cap_state.attributes.get("unit_of_measurement", "") if cap_state else ""
        if unit.lower() in ("wh", "w·h") or (not unit and capacity_raw > 1000):
            capacity_kwh = capacity_raw / 1000.0

        missing = max(100.0 - soc, 0.0) / 100.0 * capacity_kwh
        self._attr_native_value = round(missing, 2)
        self._attr_extra_state_attributes = {
            "ladezustand": f"{soc:.1f}%",
            "kapazitaet": f"{capacity_kwh:.1f} kWh",
            "kapazitaet_raw": f"{capacity_raw:.0f} {unit}",
            "fehlend": f"{missing:.2f} kWh",
        }

    def _get_float(self, entity_id):
        s = self.hass.states.get(entity_id)
        if s is None or s.state in ("unknown", "unavailable"):
            return None
        try:
            return float(s.state)
        except (ValueError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 4: Tesla fehlende Ladeenergie
# ═══════════════════════════════════════════════════════════════════════════

class TeslaMissingEnergySensor(SensorEntity):
    """Shows how much energy is needed to charge the Tesla to its limit.

    Returns 0 when the Tesla is not at home.
    Formula: (limit% - SOC%) / 100 * capacity_kWh / efficiency
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Tesla fehlende Ladeenergie"
    _attr_unique_id = "energieoptimierung_tesla_fehlende_ladeenergie"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:car-electric"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, config):
        self.hass = hass
        self._tracker_id = config.get(CONF_TESLA_TRACKER, DEFAULT_TESLA_TRACKER)
        self._soc_id = config.get(CONF_TESLA_SOC_SENSOR, DEFAULT_TESLA_SOC_SENSOR)
        self._limit_id = config.get(CONF_TESLA_LIMIT_SENSOR, DEFAULT_TESLA_LIMIT_SENSOR)
        self._capacity = config.get(CONF_TESLA_CAPACITY_KWH, DEFAULT_TESLA_CAPACITY_KWH)
        self._efficiency = config.get(CONF_TESLA_EFFICIENCY, DEFAULT_TESLA_EFFICIENCY)
        self._home_zone = config.get(CONF_TESLA_HOME_ZONE, DEFAULT_TESLA_HOME_ZONE)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        if not self._is_home():
            self._attr_native_value = 0.0
            self._attr_extra_state_attributes = {"hinweis": "Nicht in Grünbach"}
            return

        soc = self._get_float(self._soc_id)
        limit = self._get_float(self._limit_id)

        if soc is None or limit is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "hinweis": "SOC oder Ladelimit nicht verfügbar",
            }
            return

        missing = (max(limit - soc, 0.0) / 100.0 * self._capacity) / self._efficiency
        self._attr_native_value = round(missing, 2)
        self._attr_extra_state_attributes = {
            "standort": "In Grünbach",
            "batteriestand": f"{soc:.1f}%",
            "ladelimit": f"{limit:.1f}%",
            "kapazitaet": f"{self._capacity:.0f} kWh",
            "effizienz": f"{self._efficiency:.0%}",
            "fehlend": f"{missing:.2f} kWh",
        }

    def _is_home(self):
        s = self.hass.states.get(self._tracker_id)
        return s is not None and s.state.lower() == self._home_zone.lower()

    def _get_float(self, entity_id):
        s = self.hass.states.get(entity_id)
        if s is None or s.state in ("unknown", "unavailable"):
            return None
        try:
            return float(s.state)
        except (ValueError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 5: Puffer Aufheizenergie
# ═══════════════════════════════════════════════════════════════════════════

SPECIFIC_HEAT_WATER_KJ = 4.186  # kJ/(kg·K)

class PufferEnergySensor(SensorEntity):
    """Shows how much electrical energy is needed to heat the buffer tank to target temp.

    Formula: volume_kg × 4.186 kJ/(kg·K) × (target - current) / 3600 = kWh
    """

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Puffer Aufheizenergie"
    _attr_unique_id = "energieoptimierung_puffer_aufheizenergie"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:water-boiler"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, config):
        self.hass = hass
        self._temp_sensor_id = config.get(CONF_PUFFER_TEMP_SENSOR, DEFAULT_PUFFER_TEMP_SENSOR)
        self._volume_l = config.get(CONF_PUFFER_VOLUME_L, DEFAULT_PUFFER_VOLUME_L)
        self._target_temp = config.get(CONF_PUFFER_TARGET_TEMP, DEFAULT_PUFFER_TARGET_TEMP)
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        current_temp = self._get_float(self._temp_sensor_id)

        if current_temp is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "hinweis": "Temperatur nicht verfügbar",
                "temp_sensor": self._temp_sensor_id,
            }
            return

        delta_t = max(self._target_temp - current_temp, 0.0)
        kwh = self._volume_l * SPECIFIC_HEAT_WATER_KJ * delta_t / 3600.0

        self._attr_native_value = round(kwh, 2)
        self._attr_extra_state_attributes = {
            "aktuelle_temperatur": f"{current_temp:.1f}°C",
            "zieltemperatur": f"{self._target_temp:.1f}°C",
            "differenz": f"{delta_t:.1f}°C",
            "volumen": f"{self._volume_l} L",
            "energie": f"{kwh:.2f} kWh",
        }

    def _get_float(self, entity_id):
        s = self.hass.states.get(entity_id)
        if s is None or s.state in ("unknown", "unavailable"):
            return None
        try:
            return float(s.state)
        except (ValueError, TypeError):
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 5: Energiebedarf heute (Summe aus Batterie + Puffer + Verbrauch)
# ═══════════════════════════════════════════════════════════════════════════

class EnergyDemandTodaySensor(SensorEntity):
    """Sum of battery + tesla + puffer + consumption until sunset."""

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Energiebedarf heute"
    _attr_unique_id = "energieoptimierung_energiebedarf_heute"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:sigma"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, battery_sensor, puffer_sensor, tesla_sensor, sunset_sensor):
        self.hass = hass
        self._battery = battery_sensor
        self._puffer = puffer_sensor
        self._tesla = tesla_sensor
        self._sunset = sunset_sensor
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        bat = self._battery.native_value
        puf = self._puffer.native_value
        tes = self._tesla.native_value
        sun = self._sunset.native_value

        parts = {
            "batterie": bat,
            "tesla": tes,
            "puffer": puf,
            "verbrauch_bis_sonnenuntergang": sun,
        }
        available = {k: v for k, v in parts.items() if v is not None}

        if not available:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"hinweis": "Keine Daten verfügbar"}
            return

        total = sum(available.values())
        self._attr_native_value = round(total, 2)
        self._attr_extra_state_attributes = {
            "batterie_fehlend": f"{bat:.2f} kWh" if bat is not None else "n/a",
            "tesla_laden": f"{tes:.2f} kWh" if tes is not None else "n/a",
            "puffer_aufheizen": f"{puf:.2f} kWh" if puf is not None else "n/a",
            "verbrauch_bis_su": f"{sun:.2f} kWh" if sun is not None else "n/a",
        }


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor 6: Verbrauchsprofil (Ø Stundenwerte pro Zone für Dashboard)
# ═══════════════════════════════════════════════════════════════════════════

class VerbrauchsprofilSensor(SensorEntity):
    """Exposes hourly averages per zone as attributes for dashboard charts."""

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Verbrauchsprofil"
    _attr_unique_id = "energieoptimierung_verbrauchsprofil"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_suggested_display_precision = 1

    def __init__(self, hass, coordinator, meta):
        self.hass = hass
        self._coordinator = coordinator
        self._meta = meta
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        avg = self._coordinator.hourly_avg
        if not avg:
            return

        attrs: dict[str, Any] = {}
        zone_totals = {}

        for zone in ("mo-do", "fr", "sa", "so"):
            hours_data = avg.get(zone, {})
            watts = [round(hours_data.get(h, 0.0)) for h in range(24)]
            kwh = sum(w / 1000.0 for w in watts)
            zone_totals[zone] = kwh

            # List for ApexCharts data_generator
            attrs[f"{zone}_watts"] = watts
            attrs[f"{zone}_kwh"] = round(kwh, 1)

            # Human readable summary
            peak_h = max(range(24), key=lambda h: watts[h])
            min_h = min(range(24), key=lambda h: watts[h])
            attrs[zone] = (
                f"{kwh:.1f} kWh/Tag, "
                f"Spitze {watts[peak_h]}W um {peak_h:02d}:00, "
                f"Min {watts[min_h]}W um {min_h:02d}:00"
            )

        self._attr_native_value = round(
            sum(zone_totals.values()) / len(zone_totals), 1
        )
        attrs["grundlage"] = (
            f"Ø {self._meta['lookback_weeks']} Wochen, "
            f"{self._coordinator.stats_count} Datenpunkte"
        )
        attrs["stunden"] = [f"{h:02d}:00" for h in range(24)]
        self._attr_extra_state_attributes = attrs


# ═══════════════════════════════════════════════════════════════════════════
#  Sensoren 3-9: Tagesprognose (morgen bis Tag +7)
# ═══════════════════════════════════════════════════════════════════════════

class DailyForecastSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:calendar-clock"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, coordinator, meta, day_offset):
        self.hass = hass
        self._coordinator = coordinator
        self._meta = meta
        self._day_offset = day_offset
        if day_offset == 0:
            self._attr_name = "Prognose heute"
            self._attr_unique_id = "energieoptimierung_prognose_heute"
        elif day_offset == 1:
            self._attr_name = "Prognose morgen"
            self._attr_unique_id = "energieoptimierung_prognose_morgen"
        else:
            self._attr_name = f"Prognose Tag {day_offset}"
            self._attr_unique_id = f"energieoptimierung_prognose_tag_{day_offset}"
        self._attr_native_value = None
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        now = dt_util.now()
        target_date = now.date() + timedelta(days=self._day_offset)
        start = now.replace(
            year=target_date.year, month=target_date.month,
            day=target_date.day, hour=0, minute=0, second=0, microsecond=0,
        )
        end = start + timedelta(days=1)

        result = self._coordinator.calculate_period(start, end)
        weekday_idx = target_date.weekday()
        zone = ZONE_MAP[weekday_idx]

        self._attr_native_value = round(result["verbrauch_kwh"], 2)
        attrs = {
            "datum": target_date.strftime("%d.%m.%Y"),
            "wochentag": f"{WEEKDAY_NAMES_DE[weekday_idx]} ({zone})",
            "verbrauch": f"{result['verbrauch_kwh']:.2f} kWh",
            "grundlage": f"Ø {self._meta['lookback_weeks']} Wo, Zone {zone}, {self._coordinator.stats_count} Punkte",
        }
        attrs.update(format_stundenprofil(result["stundenprofil"]))
        self._attr_extra_state_attributes = attrs


# ═══════════════════════════════════════════════════════════════════════════
#  Sensor: Optimizer-Entscheidung
# ═══════════════════════════════════════════════════════════════════════════

class OptimizerDecisionSensor(SensorEntity):
    """Shows the current optimizer strategy, actions, and reasoning."""

    _attr_has_entity_name = True
    _attr_device_info = DEVICE_INFO
    _attr_name = "Entscheidung"
    _attr_unique_id = "energieoptimierung_entscheidung"
    _attr_icon = "mdi:head-cog"

    def __init__(self, hass, optimizer):
        self.hass = hass
        self._optimizer = optimizer
        self._attr_native_value = STRATEGY_INAKTIV
        self._attr_extra_state_attributes = {}

    async def async_update(self):
        if self._optimizer is None or self._optimizer.last_decision is None:
            self._attr_native_value = STRATEGY_INAKTIV
            self._attr_extra_state_attributes = {
                "hinweis": "Noch keine Berechnung (wartet auf ersten Zyklus)",
            }
            return

        dec = self._optimizer.last_decision
        self._attr_native_value = dec.strategie
        self._attr_extra_state_attributes = dec.as_dict()
