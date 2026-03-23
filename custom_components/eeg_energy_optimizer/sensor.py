"""Sensor platform for EEG Energy Optimizer.

Creates 14 sensors:
  1.  Verbrauchsprofil                    (slow, hourly averages per weekday)
  2-8. Tagesverbrauchsprognose heute..Tag 6  (fast, daily consumption forecasts)
  9.  Prognose bis Sonnenaufgang          (fast, consumption now -> next sunrise)
  10. Batterie fehlende Energie           (fast, kWh to full charge)
  11. PV Prognose heute                   (fast, remaining PV today)
  12. PV Prognose morgen                  (fast, PV forecast tomorrow)
  13. Hausverbrauch                       (fast, calculated house consumption kW)
  14. Entscheidung                        (optimizer timer, decision + Markdown dashboard)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .const import (
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BATTERY_CAPACITY_SENSOR,
    CONF_BATTERY_POWER_SENSOR,
    CONF_BATTERY_SOC_SENSOR,
    CONF_FORECAST_REMAINING_ENTITY,
    CONF_FORECAST_SOURCE,
    CONF_FORECAST_TOMORROW_ENTITY,
    CONF_GRID_POWER_SENSOR,
    CONF_LOOKBACK_WEEKS,
    CONF_PV_POWER_SENSOR,
    CONF_UPDATE_INTERVAL_FAST,
    CONF_UPDATE_INTERVAL_SLOW,
    CONSUMPTION_SENSOR,
    DEFAULT_BATTERY_POWER_SENSOR,
    DEFAULT_GRID_POWER_SENSOR,
    DEFAULT_LOOKBACK_WEEKS,
    DEFAULT_UPDATE_INTERVAL_FAST,
    DEFAULT_UPDATE_INTERVAL_SLOW,
    DOMAIN,
    FORECAST_SOURCE_SOLCAST,
    WEEKDAY_KEYS,
)
from .coordinator import ConsumptionCoordinator
from .forecast_provider import (
    ForecastSolarProvider,
    SolcastProvider,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

# Timezone/time utilities - imported at module level for easy test patching
try:
    from homeassistant.util import dt as dt_util

    _now = dt_util.now
except ImportError:
    _now = lambda: datetime.now(tz=timezone.utc)  # noqa: E731

# HA imports guarded for test environment
try:
    from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
    from homeassistant.const import UnitOfEnergy, UnitOfPower
    from homeassistant.helpers.device_registry import DeviceEntryType
    from homeassistant.helpers.entity import DeviceInfo
    from homeassistant.helpers.event import async_track_time_interval
except ImportError:
    # Stubs for test environment without full HA
    class SensorEntity:  # type: ignore[no-redef]
        """Stub."""

        _attr_has_entity_name: bool = False
        _attr_name: str = ""
        _attr_unique_id: str = ""
        _attr_native_value: Any = None
        _attr_native_unit_of_measurement: str | None = None
        _attr_device_class: str | None = None
        _attr_icon: str | None = None
        _attr_suggested_display_precision: int | None = None
        _attr_device_info: Any = None
        _attr_extra_state_attributes: dict = {}

        @property
        def native_value(self) -> Any:
            return self._attr_native_value

        @property
        def extra_state_attributes(self) -> dict:
            return self._attr_extra_state_attributes

        async def async_update(self) -> None:
            pass

        def async_write_ha_state(self) -> None:
            pass

    class SensorDeviceClass:  # type: ignore[no-redef]
        ENERGY = "energy"
        POWER = "power"

    class SensorStateClass:  # type: ignore[no-redef]
        MEASUREMENT = "measurement"

    class UnitOfEnergy:  # type: ignore[no-redef]
        KILO_WATT_HOUR = "kWh"

    class UnitOfPower:  # type: ignore[no-redef]
        KILO_WATT = "kW"

    class DeviceEntryType:  # type: ignore[no-redef]
        SERVICE = "service"

    class DeviceInfo(dict):  # type: ignore[no-redef]
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)

    async_track_time_interval = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_float(hass: Any, entity_id: str) -> float | None:
    """Read a float value from an entity state.

    Returns None for missing, unavailable, unknown, or non-numeric states.
    """
    state = hass.states.get(entity_id)
    if state is None:
        return None
    if state.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(state.state)
    except (ValueError, TypeError):
        return None


def _device_info(entry_id: str) -> DeviceInfo:
    """Return shared DeviceInfo for all sensors of this integration."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="EEG Energy Optimizer",
        manufacturer="Custom",
        model="EEG Energy Optimizer",
        entry_type=DeviceEntryType.SERVICE,
    )


# ---------------------------------------------------------------------------
# Sensor 1: Verbrauchsprofil (slow)
# ---------------------------------------------------------------------------

class VerbrauchsprofilSensor(SensorEntity):
    """Exposes hourly averages per weekday as attributes for dashboard charts."""

    _attr_has_entity_name = True
    _attr_name = "Verbrauchsprofil"
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _attr_suggested_display_precision = 1

    def __init__(
        self, hass: Any, entry: Any, coordinator: ConsumptionCoordinator
    ) -> None:
        self.hass = hass
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_verbrauchsprofil"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        avg = self._coordinator.hourly_avg
        if not avg:
            return

        attrs: dict[str, Any] = {}
        day_totals: list[float] = []

        for day in WEEKDAY_KEYS:
            hours_data = avg.get(day, {})
            watts = [round(hours_data.get(h, 0.0)) for h in range(24)]
            kwh = sum(w / 1000.0 for w in watts)
            day_totals.append(kwh)

            attrs[f"{day}_watts"] = watts
            attrs[f"{day}_kwh"] = round(kwh, 1)

        # State: average daily total across all weekdays
        self._attr_native_value = round(sum(day_totals) / len(day_totals), 1) if day_totals else None

        attrs["stunden"] = [f"{h:02d}:00" for h in range(24)]
        attrs["grundlage"] = (
            f"Durchschnitt {self._coordinator.stats_count} Datenpunkte"
        )
        attrs["stats_count"] = self._coordinator.stats_count
        self._attr_extra_state_attributes = attrs


# ---------------------------------------------------------------------------
# Sensors 2-8: Tagesverbrauchsprognose (fast) - 7 instances
# ---------------------------------------------------------------------------

_DAY_NAMES = {
    0: "Tagesverbrauchsprognose heute",
    1: "Tagesverbrauchsprognose morgen",
}

class DailyForecastSensor(SensorEntity):
    """Daily consumption forecast sensor. 7 instances (day_offset 0-6)."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        hass: Any,
        entry: Any,
        coordinator: ConsumptionCoordinator,
        day_offset: int,
    ) -> None:
        self.hass = hass
        self._coordinator = coordinator
        self._day_offset = day_offset

        if day_offset == 0:
            self._attr_name = "Tagesverbrauchsprognose heute"
            suffix = "tagesverbrauch_heute"
        elif day_offset == 1:
            self._attr_name = "Tagesverbrauchsprognose morgen"
            suffix = "tagesverbrauch_morgen"
        else:
            self._attr_name = f"Tagesverbrauchsprognose Tag {day_offset}"
            suffix = f"tagesverbrauch_tag_{day_offset}"

        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{suffix}"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        now = _now()

        if self._day_offset == 0:
            # Today: remaining from now to end of day
            start = now
            end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            # Future days: full 24h
            target_date = now.date() + timedelta(days=self._day_offset)
            start = now.replace(
                year=target_date.year,
                month=target_date.month,
                day=target_date.day,
                hour=0, minute=0, second=0, microsecond=0,
            )
            end = start + timedelta(days=1)

        result = self._coordinator.calculate_period(start, end)
        self._attr_native_value = round(result["verbrauch_kwh"], 2)
        self._attr_extra_state_attributes = {
            "stunden": round(result["stunden"], 1),
        }


# ---------------------------------------------------------------------------
# Sensor 9: Prognose bis Sonnenaufgang (fast)
# ---------------------------------------------------------------------------

class SunriseForecastSensor(SensorEntity):
    """Calculates consumption from now to next sunrise."""

    _attr_has_entity_name = True
    _attr_name = "Prognose bis Sonnenaufgang"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:weather-sunset-up"
    _attr_suggested_display_precision = 2

    def __init__(
        self, hass: Any, entry: Any, coordinator: ConsumptionCoordinator
    ) -> None:
        self.hass = hass
        self._coordinator = coordinator
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_prognose_sonnenaufgang"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        now = _now()
        sun_state = self.hass.states.get("sun.sun")
        if sun_state is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"hinweis": "sun.sun nicht verfügbar"}
            return

        next_rising = sun_state.attributes.get("next_rising")
        if next_rising is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {"hinweis": "Kein Sonnenaufgang verfügbar"}
            return

        try:
            sunrise = datetime.fromisoformat(str(next_rising))
        except (ValueError, TypeError):
            self._attr_native_value = None
            return

        if sunrise <= now:
            self._attr_native_value = 0.0
            return

        result = self._coordinator.calculate_period(now, sunrise)
        self._attr_native_value = round(result["verbrauch_kwh"], 2)
        self._attr_extra_state_attributes = {
            "sonnenaufgang": str(next_rising),
            "stunden": round(result["stunden"], 1),
        }


# ---------------------------------------------------------------------------
# Sensor 10: Batterie fehlende Energie (fast)
# ---------------------------------------------------------------------------

class BatteryMissingEnergySensor(SensorEntity):
    """Shows kWh needed to fully charge the battery.

    Formula: max(100 - SOC, 0) / 100 * capacity_kWh
    Auto-detects Wh vs kWh (>1000 threshold).
    Falls back to manual capacity config if sensor unavailable.
    """

    _attr_has_entity_name = True
    _attr_name = "Batterie fehlende Energie"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:battery-charging-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, hass: Any, entry: Any, config: dict) -> None:
        self.hass = hass
        self._soc_id = config.get(CONF_BATTERY_SOC_SENSOR, "")
        self._capacity_id = config.get(CONF_BATTERY_CAPACITY_SENSOR, "")
        self._manual_capacity_kwh = config.get(CONF_BATTERY_CAPACITY_KWH)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_batterie_fehlend"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        soc = _read_float(self.hass, self._soc_id) if self._soc_id else None

        if soc is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "hinweis": "SOC nicht verfügbar",
            }
            return

        # Try capacity sensor first, then manual fallback
        capacity_kwh = self._resolve_capacity()
        if capacity_kwh is None:
            self._attr_native_value = None
            self._attr_extra_state_attributes = {
                "hinweis": "Kapazität nicht verfügbar",
            }
            return

        missing = max(100.0 - soc, 0.0) / 100.0 * capacity_kwh
        self._attr_native_value = round(missing, 2)
        self._attr_extra_state_attributes = {
            "ladezustand": f"{soc:.1f}%",
            "kapazitaet_kwh": round(capacity_kwh, 1),
        }

    def _resolve_capacity(self) -> float | None:
        """Resolve battery capacity: sensor -> manual fallback."""
        if self._capacity_id:
            raw = _read_float(self.hass, self._capacity_id)
            if raw is not None:
                # Auto-detect Wh vs kWh
                cap_state = self.hass.states.get(self._capacity_id)
                unit = ""
                if cap_state and hasattr(cap_state, "attributes"):
                    unit = cap_state.attributes.get("unit_of_measurement", "")
                if unit.lower() in ("wh", "w·h") or (not unit and raw > 1000):
                    return raw / 1000.0
                return raw
        # Fallback to manual config
        return self._manual_capacity_kwh


# ---------------------------------------------------------------------------
# Sensor 11: PV Prognose heute (fast)
# ---------------------------------------------------------------------------

class PVForecastTodaySensor(SensorEntity):
    """PV forecast remaining today from forecast provider."""

    _attr_has_entity_name = True
    _attr_name = "PV Prognose heute"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:solar-power"
    _attr_suggested_display_precision = 1

    def __init__(self, hass: Any, entry: Any, provider: Any) -> None:
        self.hass = hass
        self._provider = provider
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_pv_prognose_heute"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None

    async def async_update(self) -> None:
        forecast = self._provider.get_forecast()
        self._attr_native_value = forecast.remaining_today_kwh


# ---------------------------------------------------------------------------
# Sensor 12: PV Prognose morgen (fast)
# ---------------------------------------------------------------------------

class PVForecastTomorrowSensor(SensorEntity):
    """PV forecast for tomorrow from forecast provider."""

    _attr_has_entity_name = True
    _attr_name = "PV Prognose morgen"
    _attr_native_unit_of_measurement = "kWh"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:solar-power"
    _attr_suggested_display_precision = 1

    def __init__(self, hass: Any, entry: Any, provider: Any) -> None:
        self.hass = hass
        self._provider = provider
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_pv_prognose_morgen"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None

    async def async_update(self) -> None:
        forecast = self._provider.get_forecast()
        self._attr_native_value = forecast.tomorrow_kwh


# ---------------------------------------------------------------------------
# Sensor 13: Hausverbrauch (fast, calculated house consumption)
# ---------------------------------------------------------------------------

class HausverbrauchSensor(SensorEntity):
    """Calculates actual house consumption from PV input, battery, and grid power.

    Formula: Hausverbrauch = PV-Eingangsleistung - Batterie-Lade/Entladeleistung - Netz-Wirkleistung
    (battery positive = charging, negative = discharging; grid positive = export, negative = import)
    Result clamped to >= 0.
    state_class=MEASUREMENT so HA recorder stores mean statistics.
    """

    _attr_has_entity_name = True
    _attr_name = "Hausverbrauch"
    _attr_native_unit_of_measurement = "kW"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_suggested_display_precision = 2

    def __init__(self, hass: Any, entry: Any, config: dict) -> None:
        self.hass = hass
        self._pv_sensor_id = config.get(CONF_PV_POWER_SENSOR, "")
        self._battery_power_sensor_id = config.get(CONF_BATTERY_POWER_SENSOR, DEFAULT_BATTERY_POWER_SENSOR)
        self._grid_sensor_id = config.get(CONF_GRID_POWER_SENSOR, DEFAULT_GRID_POWER_SENSOR)
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_hausverbrauch"
        self._attr_device_info = _device_info(entry.entry_id)
        self._attr_native_value: float | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_update(self) -> None:
        pv_power = _read_float(self.hass, self._pv_sensor_id)
        battery_power = _read_float(self.hass, self._battery_power_sensor_id)
        grid_power = _read_float(self.hass, self._grid_sensor_id)

        if pv_power is None or battery_power is None or grid_power is None:
            self._attr_native_value = None
            hints = []
            if pv_power is None:
                hints.append(f"PV-Sensor ({self._pv_sensor_id}) nicht verfügbar")
            if battery_power is None:
                hints.append(f"Batterie-Sensor ({self._battery_power_sensor_id}) nicht verfügbar")
            if grid_power is None:
                hints.append(f"Netz-Sensor ({self._grid_sensor_id}) nicht verfügbar")
            self._attr_extra_state_attributes = {"hinweis": ", ".join(hints)}
            return

        # PV input - battery power - grid power
        # battery positive = charging, negative = discharging
        # grid positive = export, negative = import
        hausverbrauch = max(pv_power - battery_power - grid_power, 0.0)
        self._attr_native_value = round(hausverbrauch, 3)
        self._attr_extra_state_attributes = {
            "pv_leistung_kw": round(pv_power, 3),
            "batterie_leistung_kw": round(battery_power, 3),
            "netz_leistung_kw": round(grid_power, 3),
        }


# ---------------------------------------------------------------------------
# Sensor 14: Entscheidung (optimizer timer)
# ---------------------------------------------------------------------------

class EntscheidungsSensor(SensorEntity):
    """Optimizer decision sensor with Markdown dashboard attribute.

    State: Next planned action (e.g. 'Abend-Entladung 20:00', 'Normalbetrieb')
    Attributes: Markdown mini-dashboard, zustand, ueberschuss_faktor,
                entladung_aktiv, min_soc, letzte_aktualisierung

    Updated by the optimizer timer in __init__.py, NOT by the dual-timer system.
    No state_class set (no recorder pollution, per Phase 2 decision).
    """

    _attr_has_entity_name = True
    _attr_name = "Entscheidung"
    _attr_icon = "mdi:robot"

    def __init__(self, entry_id: str) -> None:
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_entscheidung"
        self._attr_device_info = _device_info(entry_id)
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    def update_from_decision(self, decision: Any) -> None:
        """Update sensor state and attributes from an optimizer Decision.

        Called by the optimizer timer in __init__.py after each cycle.
        Uses duck typing to avoid circular imports with optimizer.py.
        """
        self._attr_native_value = decision.naechste_aktion
        self._attr_extra_state_attributes = {
            "markdown": decision.markdown,
            "zustand": decision.zustand,
            "energiebedarf_kwh": round(decision.energiebedarf_kwh, 2),
            "entladung_aktiv": decision.entladung_aktiv,
            "ladung_blockiert": decision.ladung_blockiert,
            "min_soc": decision.min_soc_berechnet,
            "entladeleistung_kw": decision.entladeleistung_kw,
            "ausfuehrung": decision.ausfuehrung,
            "letzte_aktualisierung": decision.timestamp,
        }
        self.async_write_ha_state()


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: Any,
    entry: Any,
    async_add_entities: Any,
) -> None:
    """Set up sensor platform for EEG Energy Optimizer."""
    data = hass.data[DOMAIN][entry.entry_id]
    config = data["config"]

    # Backfill Hausverbrauch statistics before first coordinator load
    from .__init__ import async_backfill_hausverbrauch_stats
    await async_backfill_hausverbrauch_stats(hass, config)

    # Create coordinator (now finds backfilled data immediately)
    lookback_weeks = config.get(CONF_LOOKBACK_WEEKS, DEFAULT_LOOKBACK_WEEKS)
    coordinator = ConsumptionCoordinator(hass, CONSUMPTION_SENSOR, lookback_weeks)
    await coordinator.async_update()

    # Create forecast provider
    source = config.get(CONF_FORECAST_SOURCE, FORECAST_SOURCE_SOLCAST)
    remaining_id = config.get(CONF_FORECAST_REMAINING_ENTITY, "")
    tomorrow_id = config.get(CONF_FORECAST_TOMORROW_ENTITY, "")

    if source == FORECAST_SOURCE_SOLCAST:
        provider = SolcastProvider(hass, remaining_id, tomorrow_id)
    else:
        provider = ForecastSolarProvider(hass, remaining_id, tomorrow_id)

    # Store for other components
    data["coordinator"] = coordinator
    data["provider"] = provider

    # Create sensors
    profil_sensor = VerbrauchsprofilSensor(hass, entry, coordinator)

    daily_sensors = [
        DailyForecastSensor(hass, entry, coordinator, day_offset=d)
        for d in range(7)
    ]

    sunrise_sensor = SunriseForecastSensor(hass, entry, coordinator)
    battery_sensor = BatteryMissingEnergySensor(hass, entry, config)
    pv_today_sensor = PVForecastTodaySensor(hass, entry, provider)
    pv_tomorrow_sensor = PVForecastTomorrowSensor(hass, entry, provider)
    hausverbrauch_sensor = HausverbrauchSensor(hass, entry, config)

    # Sensor 14: Entscheidungs-Sensor (updated by optimizer timer, not by fast/slow timers)
    decision_sensor = EntscheidungsSensor(entry.entry_id)
    data["decision_sensor"] = decision_sensor

    slow_sensors: list[SensorEntity] = [profil_sensor]
    fast_sensors: list[SensorEntity] = (
        daily_sensors
        + [sunrise_sensor, battery_sensor, pv_today_sensor, pv_tomorrow_sensor, hausverbrauch_sensor]
    )

    async_add_entities(slow_sensors + fast_sensors + [decision_sensor], True)

    # Dual update timers
    slow_interval = config.get(CONF_UPDATE_INTERVAL_SLOW, DEFAULT_UPDATE_INTERVAL_SLOW)
    fast_interval = config.get(CONF_UPDATE_INTERVAL_FAST, DEFAULT_UPDATE_INTERVAL_FAST)

    async def _slow_update(_now_dt: Any = None) -> None:
        await coordinator.async_update()
        for sensor in slow_sensors:
            await sensor.async_update()
            sensor.async_write_ha_state()

    async def _fast_update(_now_dt: Any = None) -> None:
        for sensor in fast_sensors:
            await sensor.async_update()
            sensor.async_write_ha_state()

    if async_track_time_interval is not None:
        unsub_slow = async_track_time_interval(
            hass, _slow_update, timedelta(minutes=slow_interval)
        )
        unsub_fast = async_track_time_interval(
            hass, _fast_update, timedelta(minutes=fast_interval)
        )
        entry.async_on_unload(unsub_slow)
        entry.async_on_unload(unsub_fast)
