# Milestones

## v1.0 EEG Energy Optimizer (Shipped: 2026-03-22)

**Phases completed:** 6 phases, 14 plans, 27 tasks

**Key accomplishments:**

- InverterBase ABC with 3 write methods + is_available property, HACS packaging (manifest/hacs.json/README), factory pattern, and 14 passing pytest tests
- HuaweiInverter sending forcible charge/discharge/stop to huawei_solar HA services, with a 2-step config flow that blocks setup when the prerequisite integration is absent — verified by live HA testing.
- PV forecast abstraction (Solcast + Forecast.Solar) and consumption coordinator with 7-day weekday grouping from HA recorder statistics, plus Phase 2 config constants
- 12 sensor entities (PV forecasts, consumption profile, daily forecasts, battery missing energy, sunrise forecast) with dual update timers and full HA integration wiring
- 4-step config flow with Solcast/Forecast.Solar prerequisite validation, EntitySelector-based PV forecast entity mapping, and consumption sensor configuration
- EEG optimizer with morning charge blocking, evening discharge with dynamic min-SOC, surplus-day detection, and Ein/Test/Aus mode select entity
- 60s optimizer timer with select platform forwarding, 5-step config flow with TimeSelector/NumberSelector, and VERSION 3 migration
- EntscheidungsSensor as 13th sensor with Markdown dashboard attribute, showing optimizer state, discharge preview, and morning block info
- WebSocket API with 4 commands, HA sidebar panel with Shadow DOM shell, 1-click config flow replacing 5-step flow, v3-to-v4 migration
- Live dashboard with optimizer status badges, battery/PV metric cards, 7-day SVG bar chart, and hourly profile line chart -- all updating via hass property
- Hardened init with safe Huawei device_id access, inverter factory try/except, and persistent notifications for silent init failures
- Explicit MODE_TEST dry-run check in optimizer and ForecastProvider upgraded to proper ABC with @abstractmethod
- Dynamic entity ID resolution via SENSOR_SUFFIXES map with fallback defaults, plus inverter test button disabled with guidance text when setup incomplete

---
