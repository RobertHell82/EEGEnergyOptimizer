# Phase 2: Forecasting & Consumption Profile - Research

**Researched:** 2026-03-21
**Domain:** HA Recorder Statistics, Solcast Solar, Forecast.Solar, SensorEntity platform
**Confidence:** HIGH

## Summary

Phase 2 builds the data layer that feeds the optimizer in Phase 3. It reads PV production forecasts from either Solcast or Forecast.Solar (both as HA integrations, not direct API) and calculates consumption forecasts from HA recorder long-term statistics. The output is a set of HA sensor entities exposing all data the optimizer needs.

The existing `energieoptimierung` integration provides a proven pattern for both recorder statistics queries (coordinator.py) and sensor entity creation with dual update intervals (sensor.py). The new implementation changes weekday grouping from 4 zones to 7 individual days and simplifies consumption to a single sensor (no Heizstab/Wallbox subtraction). PV forecast providers need a simple abstraction layer since entity IDs differ between Solcast and Forecast.Solar.

**Primary recommendation:** Reuse the existing coordinator + sensor patterns from the old integration, adapting to 7-day grouping and adding a forecast provider abstraction. Use `DataUpdateCoordinator` (HA standard) for the consumption profile, and `async_track_time_interval` for fast-updating sensors that read live entity states.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Prognose ist Pflicht -- Integration funktioniert nicht ohne PV-Prognose-Quelle
- **D-02:** Zwei Quellen unterstuetzt: Solcast Solar und Forecast.Solar (beide als HA-Integration vorausgesetzt, nicht selbst eingebaut)
- **D-03:** Auswahl der Prognose-Quelle erfolgt im Onboarding Panel (Phase 4), NICHT im Config Flow
- **D-04:** Wenn gewaehlte Prognose-Integration nicht installiert ist: blockieren + Installationsanleitung anzeigen
- **D-05:** Fuer Phase 2 (ohne Onboarding): Prognose-Quelle im Config Flow als Zwischenloesung konfigurierbar, wird in Phase 4 ins Panel verschoben
- **D-06:** Forecast.Solar: HA Integration (`forecast_solar`) voraussetzen -- funktioniert gut, kein Grund direkte API einzubauen
- **D-07:** Ein einzelner Verbrauchssensor reicht -- kein Heizstab/Wallbox/Puffer-Abzug
- **D-08:** Huawei Default: `sensor.power_meter_verbrauch` (Stromzaehler Verbrauch, kWh, total_increasing)
- **D-09:** Lookback-Fenster: 8 Wochen default, konfigurierbar in erweiterten Onboarding-Einstellungen
- **D-10:** Wochentag-Gruppierung: 7 Einzeltage (Mo, Di, Mi, Do, Fr, Sa, So) -- nicht 4 Zonen
- **D-11:** Berechnung sofort starten, auch mit wenig History
- **D-12:** Tagesverbrauchsprognosen: heute + 6 weitere Tage = 7 Sensoren (basierend auf Verbrauchsprofil)
- **D-13:** Verbrauchsprofil: Stundendurchschnitte pro Wochentag als Sensor-Attribut (7 Tagesprofile)
- **D-14:** Batterie fehlende Energie: kWh bis Batterie voll (berechnet aus SOC + Kapazitaet)
- **D-15:** PV-Prognose heute (verbleibende Produktion) + PV-Prognose morgen = 2 Sensoren
- **D-16:** Prognose bis Sonnenaufgang: prognostizierter Verbrauch von jetzt bis Sonnenaufgang
- **D-17:** Kein Tesla, kein Puffer, kein Heizstab, kein Energy Dashboard
- **D-18:** Verbrauchsprofil: 15 Minuten (slow)
- **D-19:** Alle anderen Sensoren: 1 Minute (fast)
- **D-20:** Beide Intervalle konfigurierbar (Phase 4 Onboarding). Phase 2: Config Flow Zwischenloesung
- **D-21:** Config Flow bekommt zusaetzliche Schritte fuer Phase 2: Prognose-Quelle, Verbrauchssensor
- **D-22:** Wird in Phase 4 komplett ins Onboarding Panel verschoben

### Claude's Discretion
- Technische Architektur der Forecast-Provider (ABC oder einfache Klassen)
- Interne Coordinator-Struktur fuer Recorder-Abfragen
- Sensor-Entity Implementierung (SensorEntity Subklassen)
- Solcast vs. Forecast.Solar Entity-ID Mapping (welche Entities liefern was)
- Fehlerbehandlung bei fehlender Recorder-History

### Deferred Ideas (OUT OF SCOPE)
- Heizstab/Wallbox/Puffer als abziehbare Verbraucher
- Erweiterte Statistiken (Median statt Durchschnitt, Ausreisser-Erkennung)
- Energy Dashboard Integration (`state_class` fuer HA Energy)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FCST-01 | Solcast PV-Produktionsprognose -- verbleibende Produktion heute + Prognose morgen aus Solcast Solar HA-Integration lesen | Solcast entity IDs and attributes documented; provider abstraction pattern defined |
| FCST-02 | Forecast.Solar als Alternative -- kostenlose PV-Prognose als zweite Quelle, waehlbar im Setup | Forecast.Solar entity IDs documented; same provider interface; config flow selection step |
| FCST-03 | Verbrauchsprofil -- automatische Verbrauchsprognose aus HA Recorder Langzeit-Statistiken (7 Wochentag-Gruppen) | Recorder statistics API documented; existing coordinator pattern available; 7-day grouping architecture defined |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| homeassistant.components.recorder | HA Core | Long-term statistics query | Only way to access hourly consumption averages |
| homeassistant.components.sensor | HA Core | SensorEntity base class | Standard HA sensor platform |
| homeassistant.helpers.event | HA Core | async_track_time_interval | Timer-based sensor updates |
| homeassistant.util.dt | HA Core | Timezone-aware datetime handling | HA-standard datetime utilities |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| homeassistant.components.sun | HA Core | Sunrise/sunset times | Prognose bis Sonnenaufgang sensor |
| homeassistant.helpers.selector | HA Core | EntitySelector, SelectSelector | Config flow UI elements |
| voluptuous | HA bundled | Schema validation | Config flow step schemas |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| async_track_time_interval | DataUpdateCoordinator | DUC is HA-standard for API polling. For sensors that just read `hass.states.get()`, direct timer is simpler and matches existing pattern |
| ABC for providers | Simple class with methods | ABC adds no real value when there are only 2 implementations. Simple classes with a common interface are sufficient |

## Architecture Patterns

### Recommended Project Structure
```
custom_components/eeg_energy_optimizer/
  __init__.py              # Updated: add "sensor" to PLATFORMS, store coordinator
  const.py                 # Updated: add forecast/consumption config keys + defaults
  config_flow.py           # Updated: add forecast source + consumption sensor steps
  strings.json             # Updated: add new step translations
  translations/de.json     # Updated: German translations
  translations/en.json     # Updated: English translations
  manifest.json            # Updated: add recorder + sun to dependencies, solcast_solar + forecast_solar to after_dependencies
  sensor.py                # NEW: sensor platform with all forecast sensors
  coordinator.py           # NEW: consumption profile from recorder statistics
  forecast_provider.py     # NEW: PV forecast abstraction (Solcast + Forecast.Solar)
  inverter/                # Existing Phase 1 code (unchanged)
```

### Pattern 1: Forecast Provider Abstraction
**What:** Simple class hierarchy for PV forecast sources.
**When to use:** When reading PV forecasts from different HA integrations with different entity ID patterns.
**Example:**
```python
# forecast_provider.py
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

@dataclass
class PVForecast:
    """PV forecast data container."""
    remaining_today_kwh: float | None  # kWh remaining today
    tomorrow_kwh: float | None         # kWh expected tomorrow

class ForecastProvider:
    """Base class for PV forecast providers."""
    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def get_forecast(self) -> PVForecast:
        raise NotImplementedError

    @staticmethod
    def _read_float(hass: HomeAssistant, entity_id: str) -> float | None:
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

class SolcastProvider(ForecastProvider):
    """Read PV forecasts from Solcast Solar HA integration."""
    def __init__(self, hass, remaining_entity: str, tomorrow_entity: str):
        super().__init__(hass)
        self._remaining_id = remaining_entity
        self._tomorrow_id = tomorrow_entity

    def get_forecast(self) -> PVForecast:
        return PVForecast(
            remaining_today_kwh=self._read_float(self._hass, self._remaining_id),
            tomorrow_kwh=self._read_float(self._hass, self._tomorrow_id),
        )

class ForecastSolarProvider(ForecastProvider):
    """Read PV forecasts from Forecast.Solar HA integration."""
    def __init__(self, hass, remaining_entity: str, tomorrow_entity: str):
        super().__init__(hass)
        self._remaining_id = remaining_entity
        self._tomorrow_id = tomorrow_entity

    def get_forecast(self) -> PVForecast:
        return PVForecast(
            remaining_today_kwh=self._read_float(self._hass, self._remaining_id),
            tomorrow_kwh=self._read_float(self._hass, self._tomorrow_id),
        )
```

### Pattern 2: Consumption Profile Coordinator
**What:** Loads hourly consumption averages from HA recorder, grouped by 7 weekdays.
**When to use:** On slow update cycle (15 min) to refresh consumption statistics.
**Example:**
```python
# coordinator.py - key structure
class ConsumptionCoordinator:
    """Loads hourly averages from recorder, grouped by 7 individual weekdays."""

    WEEKDAYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]

    def __init__(self, hass, consumption_sensor: str, lookback_weeks: int):
        self.hass = hass
        self._consumption_id = consumption_sensor
        self._lookback_weeks = lookback_weeks
        # {weekday: {hour: avg_watts}} e.g. {"mo": {0: 350.0, 1: 280.0, ...}, ...}
        self.hourly_avg: dict[str, dict[int, float]] = {}
        self.stats_count: int = 0

    async def async_update(self) -> None:
        """Reload hourly averages from recorder statistics."""
        # Use statistics_during_period from recorder
        # Group by weekday index -> 7 individual days
        # Fallback chain: if a weekday has no data, use nearest weekday
        pass

    def calculate_period(self, start: datetime, end: datetime) -> dict:
        """Calculate consumption forecast for a time period using hourly averages."""
        # Walk hour-by-hour, lookup weekday + hour in hourly_avg
        # Return total kWh and hourly breakdown
        pass
```

### Pattern 3: Dual Update Timer (fast/slow)
**What:** Two separate update intervals for different sensor groups.
**When to use:** When some sensors need frequent updates (live state reads) and others are expensive (recorder queries).
**Example:**
```python
# sensor.py async_setup_entry pattern
async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = ConsumptionCoordinator(...)
    await coordinator.async_update()  # Initial load

    # Slow sensors: profile-based, 15min
    slow_sensors = [
        VerbrauchsprofilSensor(coordinator),
        SunriseForecastSensor(coordinator),
        *[DailyForecastSensor(coordinator, day_offset=d) for d in range(7)],
    ]

    # Fast sensors: live entity reads, 1min
    fast_sensors = [
        BatteryMissingEnergySensor(config),
        PVForecastTodaySensor(provider),
        PVForecastTomorrowSensor(provider),
    ]

    async_add_entities(slow_sensors + fast_sensors, True)

    async def _slow_update(_now=None):
        await coordinator.async_update()
        for s in slow_sensors:
            await s.async_update()
            s.async_write_ha_state()

    async def _fast_update(_now=None):
        for s in fast_sensors:
            await s.async_update()
            s.async_write_ha_state()

    async_track_time_interval(hass, _slow_update, timedelta(minutes=15))
    async_track_time_interval(hass, _fast_update, timedelta(minutes=1))
```

### Anti-Patterns to Avoid
- **Calling recorder in the event loop:** `statistics_during_period` is a sync DB function. Always use `get_instance(hass).async_add_executor_job()` or the async wrapper `async_statistics_during_period` if available.
- **Polling PV forecast APIs directly:** Solcast and Forecast.Solar are HA integrations. Read their entity states via `hass.states.get()`, do not make HTTP requests.
- **Hardcoding entity IDs:** Entity IDs for Solcast/Forecast.Solar vary by installation. Make them configurable (config flow) with sensible defaults.
- **Using `state_class` on forecast sensors:** These are forecasts, not measurements. Do not set `state_class` -- it would cause HA to record them as long-term statistics, which is wrong for predicted values.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Recorder statistics query | Custom DB queries | `statistics_during_period` from `homeassistant.components.recorder.statistics` | Handles DB versioning, schema changes, timezone conversion |
| Sunrise/sunset times | Custom astronomy | `hass.states.get("sun.sun")` attributes | HA already computes this, handles DST |
| Timezone handling | Manual UTC offsets | `homeassistant.util.dt` (as_local, now, utcnow) | Handles DST transitions in Austria correctly |
| Entity state reading | Direct DB access | `hass.states.get(entity_id)` | Standard HA pattern, always current |
| Periodic updates | Custom timers / threading | `async_track_time_interval` | HA-managed, properly cancelled on unload |

## PV Forecast Entity Mapping

### Solcast Solar (HACS Integration: `ha-solcast-solar`)

| Data | Entity ID Pattern | Unit | Notes |
|------|-------------------|------|-------|
| Remaining today | `sensor.solcast_pv_forecast_forecast_remaining_today` | kWh | Decreases through the day |
| Tomorrow total | `sensor.solcast_pv_forecast_forecast_tomorrow` | kWh | Full day forecast |
| Today total | `sensor.solcast_pv_forecast_forecast_today` | kWh | Full day (for reference) |

**Important:** Entity IDs may vary based on Solcast configuration name. The user's existing Fronius instance uses German entity names: `sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute` and `sensor.solcast_pv_forecast_prognose_morgen`. Entity IDs MUST be configurable in the config flow.

**Attributes:** Solcast sensors expose `detailedForecast` attribute with 30-minute interval data containing `period_start`, `pv_estimate`, `pv_estimate10`, `pv_estimate90`. Not needed for Phase 2 (simple kWh totals suffice) but good to know for Phase 3.

### Forecast.Solar (HA Core Integration: `forecast_solar`)

| Data | Entity ID Pattern | Unit | Notes |
|------|-------------------|------|-------|
| Remaining today | `sensor.{name}_energy_production_today_remaining` | kWh | |
| Tomorrow total | `sensor.{name}_energy_production_tomorrow` | kWh | |
| Today total | `sensor.{name}_energy_production_today` | kWh | For reference |

**Entity naming:** `{name}` is derived from the Forecast.Solar configuration entry name. Default pattern uses the integration name.

**Confidence:** MEDIUM -- exact entity ID patterns for Forecast.Solar need verification on the Huawei instance once installed. The config flow must use EntitySelector to let users pick the right entities.

## Recorder Statistics API

### How to Query Hourly Consumption Averages

```python
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.components.recorder import get_instance

async def _load_statistics(hass, sensor_id: str, lookback_weeks: int):
    """Load hourly mean statistics from recorder."""
    now = dt_util.now()
    start = now - timedelta(weeks=lookback_weeks)

    recorder = get_instance(hass)
    stats = await recorder.async_add_executor_job(
        statistics_during_period,
        hass,
        start,
        now,
        {sensor_id},     # statistic_ids (set)
        "hour",           # period
        None,             # units (None = original)
        {"mean"},         # types
    )
    return stats.get(sensor_id, [])
```

**Key points:**
- `statistics_during_period` is synchronous -- must run in executor via `get_instance(hass).async_add_executor_job()`
- Returns `dict[str, list[dict]]` where each dict has: `start` (timestamp), `mean`, `min`, `max`, `sum`, `state`
- The `start` field can be either a float (unix timestamp) or ISO string depending on HA version
- Only sensors with `state_class` set (MEASUREMENT, TOTAL, TOTAL_INCREASING) generate long-term statistics
- `sensor.power_meter_verbrauch` is `total_increasing` -- recorder stores hourly statistics for it automatically

### 7-Day Weekday Grouping

```python
WEEKDAY_KEYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]
# weekday() returns 0=Monday ... 6=Sunday
# Map: weekday_index -> WEEKDAY_KEYS[weekday_index]

# Fallback chain when a weekday has no data:
FALLBACKS = {
    "mo": ["di", "mi", "do", "fr"],   # Weekdays first
    "di": ["mo", "mi", "do", "fr"],
    "mi": ["di", "do", "mo", "fr"],
    "do": ["mi", "di", "mo", "fr"],
    "fr": ["do", "sa", "mo"],
    "sa": ["so", "fr"],
    "so": ["sa", "fr"],
}
```

## Sensor Inventory (Phase 2)

| # | Name | Type | Update | Calculation |
|---|------|------|--------|-------------|
| 1 | Verbrauchsprofil | profile | slow 15min | Hourly averages per weekday from recorder |
| 2 | Tagesverbrauchsprognose heute | forecast | fast 1min | Today's remaining consumption from profile |
| 3 | Tagesverbrauchsprognose morgen | forecast | fast 1min | Tomorrow 00:00-24:00 from profile |
| 4-8 | Tagesverbrauchsprognose Tag 2-6 | forecast | fast 1min | Day+2 through Day+6 from profile |
| 9 | Prognose bis Sonnenaufgang | forecast | fast 1min | Now -> next sunrise consumption from profile |
| 10 | Batterie fehlende Energie | live | fast 1min | (100% - SOC%) / 100 * capacity_kWh |
| 11 | PV Prognose heute | live | fast 1min | Remaining PV today from Solcast/Forecast.Solar |
| 12 | PV Prognose morgen | live | fast 1min | Tomorrow PV from Solcast/Forecast.Solar |

**Total:** 12 sensors

**Naming convention:** All sensors use `_attr_has_entity_name = True` with German names. Entity IDs auto-generated as `sensor.eeg_energy_optimizer_{snake_case_name}`.

**DeviceInfo:** All sensors belong to one device "EEG Energy Optimizer" with `identifiers={(DOMAIN, entry.entry_id)}`.

## Config Flow Extension

### New Steps (added to existing 2-step flow)

**Step 3: Prognose-Quelle** (after sensors step)
- Select forecast source: Solcast Solar / Forecast.Solar
- Validate that selected integration is installed and loaded
- Show entity selectors for remaining_today and tomorrow entities
- Pre-fill defaults based on selected source

**Step 4: Verbrauchsmessung** (after forecast step)
- Consumption sensor (EntitySelector, domain="sensor")
- Default: `sensor.power_meter_verbrauch`
- Lookback weeks (NumberSelector, default 8)
- Update intervals (fast_min, slow_min) as advanced settings

### New Config Keys
```python
# const.py additions
CONF_FORECAST_SOURCE = "forecast_source"
CONF_FORECAST_REMAINING_ENTITY = "forecast_remaining_entity"
CONF_FORECAST_TOMORROW_ENTITY = "forecast_tomorrow_entity"
CONF_CONSUMPTION_SENSOR = "consumption_sensor"
CONF_LOOKBACK_WEEKS = "lookback_weeks"
CONF_UPDATE_INTERVAL_FAST = "update_interval_fast_min"
CONF_UPDATE_INTERVAL_SLOW = "update_interval_slow_min"

FORECAST_SOURCE_SOLCAST = "solcast_solar"
FORECAST_SOURCE_FORECAST_SOLAR = "forecast_solar"

DEFAULT_CONSUMPTION_SENSOR = "sensor.power_meter_verbrauch"
DEFAULT_LOOKBACK_WEEKS = 8
DEFAULT_UPDATE_INTERVAL_FAST = 1   # minutes
DEFAULT_UPDATE_INTERVAL_SLOW = 15  # minutes
```

## Common Pitfalls

### Pitfall 1: Recorder Not Ready at Integration Start
**What goes wrong:** `statistics_during_period` fails because recorder hasn't finished initialization.
**Why it happens:** Custom integrations can load before recorder is fully ready, especially after HA restart.
**How to avoid:** Add `"recorder"` to `manifest.json` `dependencies` (not `after_dependencies`). This guarantees recorder is loaded first. Also handle empty/None returns gracefully.
**Warning signs:** Empty statistics on first load after restart, works after a few minutes.

### Pitfall 2: Statistics ID Mismatch
**What goes wrong:** `statistics_during_period` returns empty dict even though sensor has data.
**Why it happens:** The statistic_id must match exactly -- for HA-native sensors it's the entity_id, but for external statistics it may differ. Also, the sensor must have `state_class` set to generate long-term statistics.
**How to avoid:** Verify the consumption sensor has `state_class: total_increasing` before querying. Log available statistic IDs on first run for debugging.
**Warning signs:** `stats_count: 0` despite the sensor having history in HA.

### Pitfall 3: Timezone Handling in Statistics
**What goes wrong:** Hourly averages assigned to wrong weekday/hour near midnight or DST transitions.
**Why it happens:** Recorder stores timestamps in UTC. Converting to local time must use `dt_util.as_local()` which handles DST. Austria is CET/CEST (UTC+1/+2).
**How to avoid:** Always convert timestamps with `dt_util.as_local()` before extracting weekday/hour. The existing coordinator.py does this correctly -- follow the same pattern.
**Warning signs:** Consumption profile shows unexpected spikes at hour 0 or 23.

### Pitfall 4: Forecast.Solar Entity IDs Vary by Config Name
**What goes wrong:** Hardcoded entity IDs don't match the user's Forecast.Solar configuration.
**Why it happens:** Forecast.Solar entity IDs include the configuration entry name, e.g., `sensor.my_roof_energy_production_today`. Multiple roof configurations create different entity sets.
**How to avoid:** Use EntitySelector in config flow -- user picks entities, no hardcoding. Store selected entity IDs in config entry data.
**Warning signs:** "Entity not found" errors after installation.

### Pitfall 5: Empty History on Fresh Install
**What goes wrong:** Division by zero or None values when no recorder history exists yet.
**Why it happens:** New HA instance or new sensor has no long-term statistics yet (D-11 says "start immediately even with little history").
**How to avoid:** Return 0.0 for missing hours, not None. Log a warning about limited data. Show `stats_count` in sensor attributes so users can see data quality.
**Warning signs:** All forecast sensors show 0.0 kWh.

## Code Examples

### Battery Missing Energy Sensor
```python
# Reuses Phase 1 config: SOC sensor + capacity sensor/manual kWh
class BatteryMissingEnergySensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Batterie fehlende Energie"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_icon = "mdi:battery-charging-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, hass, config):
        self._hass = hass
        self._soc_id = config[CONF_BATTERY_SOC_SENSOR]
        # Capacity: prefer sensor, fallback to manual kWh
        self._capacity_sensor = config.get(CONF_BATTERY_CAPACITY_SENSOR)
        self._capacity_manual = config.get(CONF_BATTERY_CAPACITY_KWH)

    async def async_update(self):
        soc = self._read_float(self._soc_id)
        capacity_kwh = self._get_capacity_kwh()
        if soc is None or capacity_kwh is None:
            self._attr_native_value = None
            return
        self._attr_native_value = round(
            max(100.0 - soc, 0.0) / 100.0 * capacity_kwh, 2
        )

    def _get_capacity_kwh(self) -> float | None:
        if self._capacity_sensor:
            raw = self._read_float(self._capacity_sensor)
            if raw is not None:
                # Auto-detect Wh vs kWh (Huawei reports 15000 Wh)
                return raw / 1000.0 if raw > 1000 else raw
        return self._capacity_manual
```

### Verbrauchsprofil Sensor Attributes
```python
# 7 weekday profiles exposed as attributes for dashboard charts
attrs = {
    "mo_watts": [350, 280, 250, ...],  # 24 hourly values
    "mo_kwh": 8.5,
    "di_watts": [...],
    "di_kwh": 8.2,
    # ... all 7 days
    "stunden": ["00:00", "01:00", ..., "23:00"],
    "grundlage": "Durchschnitt 8 Wochen, 1344 Datenpunkte",
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 4 weekday zones (Mo-Do/Fr/Sa/So) | 7 individual weekdays | Phase 2 decision | More accurate consumption profiles |
| Heizstab+Wallbox subtraction | Single consumption sensor | Phase 2 decision | Simpler, less error-prone |
| Solcast only | Solcast or Forecast.Solar | Phase 2 decision | Broader compatibility |
| `statistics_during_period` with positional args | Same API, check for `async_statistics_during_period` | HA 2025.x | May need executor job fallback |
| `has_mean` in statistics metadata | `mean_type: StatisticMeanType` | HA 2025.10 | `has_mean` deprecated, removed in 2026.11 |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (not yet configured) |
| Config file | none -- see Wave 0 |
| Quick run command | `pytest tests/ -x --timeout=30` |
| Full suite command | `pytest tests/ --timeout=60` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FCST-01 | Solcast provider reads remaining_today + tomorrow from entity states | unit | `pytest tests/test_forecast_provider.py::test_solcast_provider -x` | Wave 0 |
| FCST-02 | Forecast.Solar provider reads remaining_today + tomorrow from entity states | unit | `pytest tests/test_forecast_provider.py::test_forecast_solar_provider -x` | Wave 0 |
| FCST-03a | Coordinator loads recorder statistics and groups by 7 weekdays | unit | `pytest tests/test_coordinator.py::test_weekday_grouping -x` | Wave 0 |
| FCST-03b | calculate_period returns correct kWh for arbitrary time range | unit | `pytest tests/test_coordinator.py::test_calculate_period -x` | Wave 0 |
| FCST-03c | Fallback chain when weekday has no data | unit | `pytest tests/test_coordinator.py::test_fallback_chain -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --timeout=30`
- **Per wave merge:** `pytest tests/ --timeout=60`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` -- shared fixtures (mock hass, mock states, mock recorder)
- [ ] `tests/test_coordinator.py` -- covers FCST-03a/b/c
- [ ] `tests/test_forecast_provider.py` -- covers FCST-01, FCST-02
- [ ] `tests/test_sensors.py` -- covers sensor update logic
- [ ] Framework install: `pip install pytest pytest-homeassistant-custom-component` -- if pytest not available
- [ ] `pytest.ini` or `pyproject.toml [tool.pytest]` configuration

## Open Questions

1. **Exact Forecast.Solar entity IDs on Huawei instance**
   - What we know: Pattern is `sensor.{name}_energy_production_today_remaining` but exact `{name}` depends on config entry
   - What's unclear: What name will be auto-assigned when installed on Huawei instance
   - Recommendation: Use EntitySelector in config flow. User picks entities. No hardcoding needed.

2. **HA version on Huawei instance**
   - What we know: Recorder API has evolved; `statistics_during_period` signature may differ between HA versions
   - What's unclear: Which HA version runs on 192.168.1.211
   - Recommendation: Use the same fallback approach as existing coordinator.py -- try async, fall back to executor job.

3. **Consumption sensor `state_class` verification**
   - What we know: `sensor.power_meter_verbrauch` is `total_increasing` (22999.99 kWh) -- should generate long-term statistics
   - What's unclear: Whether long-term statistics are actually being recorded (depends on recorder config)
   - Recommendation: Log available statistic IDs on first coordinator update for debugging.

## Sources

### Primary (HIGH confidence)
- Existing `coordinator.py` -- proven recorder statistics query pattern, tested in production
- Existing `sensor.py` -- proven dual-timer sensor update pattern
- CONTEXT.md -- locked user decisions on 7-day grouping, sensor scope, intervals

### Secondary (MEDIUM confidence)
- [HA Developer Docs - Recorder Statistics API Changes](https://developers.home-assistant.io/blog/2025/10/16/recorder-statistics-api-changes/) -- API evolution, deprecations
- [HA Developer Docs - Sensor Entity](https://developers.home-assistant.io/docs/core/entity/sensor/) -- SensorEntity best practices
- [HA Developer Docs - Fetching Data](https://developers.home-assistant.io/docs/integration_fetching_data/) -- DataUpdateCoordinator vs polling
- [Forecast.Solar Official Docs](https://www.home-assistant.io/integrations/forecast_solar/) -- entity list and attributes
- [Solcast Solar GitHub](https://github.com/BJReplay/ha-solcast-solar) -- entity patterns, attribute structure

### Tertiary (LOW confidence)
- [DeepWiki HA Core](https://deepwiki.com/home-assistant/core/3.1-recorder-and-statistics) -- statistics module structure
- WebSearch results for entity ID patterns -- need runtime verification

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- using only HA core APIs, proven in existing integration
- Architecture: HIGH -- adapting proven patterns from existing `coordinator.py` and `sensor.py`
- Pitfalls: HIGH -- documented from real production experience with existing integration
- PV entity mapping: MEDIUM -- Solcast verified from existing const.py, Forecast.Solar needs runtime verification

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (stable HA APIs, unlikely to change in 30 days)
