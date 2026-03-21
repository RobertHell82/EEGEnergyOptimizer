# Phase 3: Optimizer & Safety System - Research

**Researched:** 2026-03-21
**Domain:** Home Assistant custom integration — async optimizer engine, select entity, decision sensor with Markdown attributes
**Confidence:** HIGH

## Summary

Phase 3 implements the core optimizer decision engine for the EEG Energy Optimizer integration. The engine runs on a configurable timer (default 60s), gathers sensor inputs into a Snapshot dataclass, evaluates morning feed-in blocking and evening discharge logic, and outputs decisions via a sensor entity with Markdown-formatted attributes. A Select entity (Ein/Test/Aus) controls execution mode with RestoreEntity persistence.

The existing `energieoptimierung` integration provides a battle-tested reference for the Snapshot/Decision pattern, discharge logic with dynamic Min-SOC, and the Ueberschuss-Faktor calculation. The new implementation is significantly simpler: no guards (D-14), no Heizstab/Warmwasser control, no multiple strategies. Only three internal states exist: Morgen-Einspeisung, Normal, Abend-Entladung.

**Primary recommendation:** Implement the optimizer as a single `optimizer.py` module with Snapshot/Decision dataclasses, a `select.py` for the mode entity, and extend `sensor.py` with the Entscheidungs-Sensor. Wire the 60s timer in `__init__.py`. Extend `const.py` and `config_flow.py` for new parameters. Use the existing inverter interface (`async_set_charge_limit`, `async_set_discharge`, `async_stop_forcible`) for all hardware commands.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 1 Stunde vor Sonnenaufgang: Batterie-Ladelimit auf 0 kW setzen via Inverter-Interface
- **D-02:** Sperre gilt bis konfigurierbare Enduhrzeit (z.B. 10:00 oder 11:00)
- **D-03:** Sperre greift NUR an Ueberschuss-Tagen (Ueberschuss-Faktor >= Schwelle). An normalen Tagen: kein Eingriff morgens
- **D-04:** Mittags (nach Enduhrzeit): kein Eingriff, Batterie laedt normal vom Wechselrichter
- **D-05:** Entladung startet ab konfigurierbarer Uhrzeit (Default: 20:00)
- **D-06:** Feste Entladeleistung in kW (konfigurierbar)
- **D-07:** Entladung laeuft bis berechneter Min-SOC erreicht ist, keine End-Uhrzeit
- **D-08:** Min-SOC Berechnung: konfigurierter Basis-Min-SOC + (prognostizierter Verbrauch bis Sonnenaufgang x Sicherheitspuffer-%) umgerechnet in SOC-Prozent
- **D-09:** Entlade-Bedingung: Nur wenn PV-Prognose morgen >= Gesamtbedarf morgen (Ueberschuss-Tag)
- **D-10:** Batterie hat zusaetzlich Hardware-seitigen Min-SOC vom Hersteller als absolute Untergrenze
- **D-11:** Ueberschuss-Faktor = PV-Prognose / Energiebedarf -- entscheidet ob ein Tag ein Ueberschuss-Tag ist
- **D-12:** Schwellwert konfigurierbar (z.B. 1.25 als Default aus bestehender Integration)
- **D-13:** Steuert BEIDES: Morgen-Einspeisung UND Abend-Entladung. Faktor unter Schwelle: weder Morgen-Sperre noch Abend-Entladung
- **D-14:** KEINE zweistufigen Safety-Guards (kein KRITISCH/HOCH/MITTEL System)
- **D-15:** Min-SOC bei Entladung + Hardware-Schutz des Wechselrichters reichen als Sicherheitsnetz
- **D-16:** SAF-01 (SOC-Guards) und SAF-02 (dynamischer Min-SOC als Guard) entfallen. Der dynamische Min-SOC lebt als Entlade-Berechnung weiter (D-08), nicht als Guard
- **D-17:** Drei Modi: Ein (volle Optimierung), Test (berechnet + zeigt, fuehrt nicht aus), Aus (komplett inaktiv)
- **D-18:** Select-Entity, persistent ueber HA-Neustarts (restore_state)
- **D-19:** Kein Feed-In Switch, kein Power-Number -- Optimizer steuert alles selbst
- **D-20:** Alle Entities (Select + Sensoren) unter einem gemeinsamen Device
- **D-21:** Kein separater Switch oder Number fuer Einspeisung -- nur der Modus-Select
- **D-22:** Drei interne Zustaende: Morgen-Einspeisung, Normal, Abend-Entladung
- **D-23:** Kein "Inaktiv"-Zustand separat -- wenn Modus "Aus" dann laeuft der Zyklus nicht
- **D-24:** EIN Sensor fuer alles -- kein separater Entlade-Vorschau-Sensor (SENS-02 wird Attribut)
- **D-25:** State: Naechste geplante Aktion (z.B. "Abend-Entladung 20:00")
- **D-26:** Hauptattribut: Markdown-formatierter Textblock als Mini-Dashboard
- **D-27:** Markdown-Inhalt je nach Tageszeit: Aktueller Status, Naechste Aktion, Uebernaechste Aktion
- **D-28:** Abend-Entladungs-Block: Startzeit, PV-Prognose morgen, Verbrauchsprognose morgen, Ueberschuss-Faktor, berechneter Ziel-SOC
- **D-29:** Morgen-Einspeisungs-Block: Ob Ladung blockiert wird (ja/nein), bis wann blockiert, PV-Prognose heute, Verbrauchsprognose heute, Ueberschuss-Faktor
- **D-30:** Update-Intervall: minuetlich (Default), konfigurierbar in erweiterten Einstellungen

### Claude's Discretion
- Optimizer-Zyklus Architektur (async timer, Snapshot/Decision Pattern)
- Markdown-Formatierung und Layout des Entscheidungs-Sensors
- Config Flow Erweiterung fuer Phase-3-Parameter (Zeitfenster, Entladeleistung, Min-SOC etc.)
- Interne Berechnung des Ueberschuss-Faktors
- Fehlerbehandlung bei fehlenden Sensor-Werten
- 60-Sekunden-Zyklus vs. konfigurierbares Intervall

### Deferred Ideas (OUT OF SCOPE)
- Intelligentere Entlade-Startzeit (z.B. basierend auf Strompreis oder EEG-Bedarf)
- SAF-01/SAF-02 Guards koennten als optionales Feature zurueckkommen wenn Nutzer es brauchen
- Feed-In Switch + Power Number als manuelle Override-Entities
- Zusaetzliche Optimizer-Modi (z.B. "Nur Einspeisung" ohne Entladung)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OPT-01 | Morgen-Einspeisevorrang -- Batterie-Laden verzögern, PV morgens ins Netz einspeisen | Inverter interface `async_set_charge_limit(0)` blocks charging; sun.sun entity provides sunrise time; Ueberschuss-Faktor from ForecastProvider + ConsumptionCoordinator determines if surplus day |
| OPT-02 | Abend-Entladung -- Batterie abends ins Netz entladen unter konfigurierbaren Bedingungen | Inverter interface `async_set_discharge(power, target_soc)` handles discharge; reference `_check_entladung()` provides battle-tested logic |
| OPT-03 | Optimale Entlade-Strategie -- dynamischer Min-SOC basierend auf Nachtverbrauch + Sicherheitspuffer | Reference `_calc_min_soc_entladung()` provides exact formula; ConsumptionCoordinator `calculate_period(now, sunrise)` provides overnight consumption forecast |
| SAF-01 | SOC-Guards -- zweistufig: KRITISCH/HOCH | **ENTFAELLT per D-14/D-16** -- keine Guards implementieren |
| SAF-02 | Dynamischer Min-SOC | **ENTFAELLT als Guard per D-16** -- lebt als Entlade-Berechnung in OPT-03 weiter |
| SAF-03 | Naechster-Tag-Check -- Entladung nur wenn PV-Prognose morgen >= Gesamtbedarf morgen | ForecastProvider `get_forecast().tomorrow_kwh` vs. ConsumptionCoordinator tomorrow consumption; reference `_calc_energiebedarf_morgen()` provides calculation (simplified: no Heizstab/Puffer) |
| SAF-04 | Dry-Run Modus -- berechnet und zeigt Entscheidungen, fuehrt nicht aus | Select entity with "Test" mode; optimizer always calculates, only calls inverter when mode == "Ein" |
| SENS-01 | Entscheidungs-Sensor -- aktuelle Strategie als State, vollständige Decision als Attribute | SensorEntity with `extra_state_attributes` containing Markdown block; existing dual-timer pattern for updates |
| SENS-02 | Entladungs-Vorschau -- tagsüber anzeigen ob heute Nacht Entladung geplant ist | **Merged into SENS-01 as attribute per D-24** -- Markdown block includes discharge preview section |
| SENS-03 | EEG Zeitfenster -- konfigurierbare Morgen- und Abend-Fenster | Config flow step for morning end-time and evening start-time; used by optimizer state machine to determine current phase |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| homeassistant | 2026.3+ | Framework: SensorEntity, SelectEntity, RestoreEntity, async_track_time_interval | The platform; all integration code runs within HA |
| voluptuous | (bundled) | Config flow schema validation | HA's standard config validation library |
| dataclasses | stdlib | Snapshot/Decision data containers | Proven pattern from reference integration, zero dependencies |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| math | stdlib | `math.ceil` for Min-SOC rounding | Dynamic Min-SOC calculation |
| datetime / timedelta | stdlib | Time arithmetic for sunrise offsets, discharge windows | Everywhere in the optimizer |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Dataclass Snapshot | Dict | Dataclass gives autocomplete, type safety, and clear structure -- use dataclass |
| Custom timer | DataUpdateCoordinator | DUC is for polling external APIs; the optimizer is an internal engine that writes to actuators -- `async_track_time_interval` is the correct pattern |
| Multiple sensor entities for decision | Single sensor with attributes | Single sensor with Markdown attributes is the user decision (D-24) |

## Architecture Patterns

### Recommended Project Structure (new/modified files)
```
custom_components/eeg_energy_optimizer/
├── __init__.py          # ADD: 60s optimizer timer, select platform forwarding
├── const.py             # ADD: optimizer config keys, defaults, mode constants, state constants
├── config_flow.py       # ADD: Step 5 (optimizer params) with options flow
├── optimizer.py          # NEW: Snapshot, Decision dataclasses, EEGOptimizer engine
├── select.py            # NEW: OptimizerModeSelect (Ein/Test/Aus) with RestoreEntity
├── sensor.py            # ADD: EntscheidungsSensor (13th sensor)
├── strings.json         # ADD: step 5 strings, select entity strings
├── translations/de.json # ADD: same as strings.json
├── coordinator.py       # UNCHANGED (used by optimizer for consumption forecasts)
├── forecast_provider.py # UNCHANGED (used by optimizer for PV forecasts)
└── inverter/
    ├── base.py          # UNCHANGED (async_set_charge_limit, async_set_discharge, async_stop_forcible)
    └── huawei.py        # UNCHANGED
```

### Pattern 1: Optimizer Cycle (async_track_time_interval)
**What:** A 60s timer calls the optimizer's main cycle method. The optimizer gathers inputs, evaluates, and optionally executes.
**When to use:** Every integration that needs periodic decision-making with side effects.
**Example:**
```python
# In __init__.py async_setup_entry:
from homeassistant.helpers.event import async_track_time_interval

optimizer = EEGOptimizer(hass, config, inverter, coordinator, provider)
hass.data[DOMAIN][entry.entry_id]["optimizer"] = optimizer

async def _optimizer_cycle(_now=None):
    mode_state = hass.states.get(f"select.{DOMAIN}_optimizer")
    mode = mode_state.state if mode_state else MODE_AUS
    if mode != MODE_AUS:
        await optimizer.async_run_cycle(mode)

unsub = async_track_time_interval(hass, _optimizer_cycle, timedelta(seconds=60))
entry.async_on_unload(unsub)
```

### Pattern 2: Snapshot/Decision Dataclasses
**What:** Immutable input snapshot gathered once per cycle, pure-function evaluation producing a Decision, then optional execution.
**When to use:** Separating data gathering from logic from side effects.
**Example:**
```python
@dataclass
class Snapshot:
    now: datetime
    battery_soc: float = 0.0
    battery_capacity_kwh: float = 0.0
    pv_remaining_today_kwh: float = 0.0
    pv_tomorrow_kwh: float = 0.0
    consumption_today_kwh: float = 0.0
    consumption_tomorrow_kwh: float = 0.0
    consumption_to_sunrise_kwh: float = 0.0
    sunrise: datetime | None = None
    sunset: datetime | None = None
    sun_above_horizon: bool = True

@dataclass
class Decision:
    timestamp: str = ""
    zustand: str = "Normal"       # Morgen-Einspeisung / Normal / Abend-Entladung
    ueberschuss_faktor: float = 0.0
    ladung_blockiert: bool = False
    entladung_aktiv: bool = False
    entladeleistung_kw: float = 0.0
    min_soc_berechnet: float = 0.0
    naechste_aktion: str = ""     # State for SENS-01
    markdown: str = ""            # Markdown attribute for SENS-01
    ausfuehrung: bool = False
```

### Pattern 3: SelectEntity + RestoreEntity for Mode
**What:** A select entity with three options that persists its state across HA restarts.
**When to use:** User-facing mode control that needs to survive reboots.
**Example:**
```python
# Source: existing energieoptimierung/select.py (proven pattern)
class OptimizerModeSelect(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_options = [MODE_EIN, MODE_TEST, MODE_AUS]
    _attr_current_option = MODE_AUS

    async def async_added_to_hass(self):
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in self._attr_options:
            self._attr_current_option = last_state.state
```

### Pattern 4: Markdown Sensor Attributes
**What:** A sensor entity where `extra_state_attributes` contains a `markdown` key with pre-formatted Markdown text for Lovelace Markdown cards.
**When to use:** Dashboard-ready decision display without custom frontend code.
**Example:**
```python
class EntscheidungsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Entscheidung"
    _attr_icon = "mdi:robot"

    def update_from_decision(self, decision: Decision):
        self._attr_native_value = decision.naechste_aktion
        self._attr_extra_state_attributes = {
            "markdown": decision.markdown,
            "zustand": decision.zustand,
            "ueberschuss_faktor": decision.ueberschuss_faktor,
            "entladung_aktiv": decision.entladung_aktiv,
            "min_soc": decision.min_soc_berechnet,
            "letzte_aktualisierung": decision.timestamp,
        }
        self.async_write_ha_state()
```

### Anti-Patterns to Avoid
- **Writing to inverter on every cycle:** Track previous state and only call inverter when the action changes (e.g., charge_limit goes from normal to 0, or discharge starts/stops). The reference integration tracks `_prev_*` values.
- **Mixing evaluation and execution:** Keep `_evaluate()` as a pure function that returns a Decision. `_execute()` is a separate step that reads the Decision and calls the inverter. This makes Test mode trivial.
- **Hardcoding sunrise/sunset times:** Always read from `sun.sun` entity and its `next_rising`/`next_setting` attributes. The reference integration derives today's sunrise as `next_rising - 24h` when the sun is above the horizon.
- **Storing optimizer state in hass.data only:** The Decision must also flow to the EntscheidungsSensor. The optimizer should hold a reference to the sensor (or use a callback) so the sensor gets updated each cycle.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| State persistence across reboots | Custom file/DB storage | `RestoreEntity` mixin | HA-native, handles serialization, storage cleanup |
| Periodic timer | `asyncio.create_task` with sleep loop | `async_track_time_interval` | Proper HA lifecycle integration, auto-cleanup via `entry.async_on_unload` |
| Sunrise/sunset calculation | `astral` library or manual calculation | `sun.sun` entity attributes (`next_rising`, `next_setting`) | HA already computes this, stays in sync with location config |
| Reading sensor float values | Inline `hass.states.get()` with try/except everywhere | Shared `_read_float(hass, entity_id)` helper | Already established in sensor.py and forecast_provider.py |
| Dynamic Min-SOC formula | Custom approximation | Direct port of `_calc_min_soc_entladung()` from reference | Battle-tested formula: `min_soc + ceil((overnight_kwh * (1 + buffer%)) / capacity_kwh * 100)` |

**Key insight:** The reference integration (`energieoptimierung/optimizer.py`) has already solved every algorithmic problem this phase needs. The job is to port the relevant logic (discharge, min-soc, ueberschuss-faktor) while dropping the complexity (guards, Heizstab, Warmwasser, multiple strategies) that the user explicitly excluded.

## Common Pitfalls

### Pitfall 1: Optimizer Runs Before Sensors Are Ready
**What goes wrong:** On HA startup, the optimizer timer fires before forecast/consumption sensors have their first update. Snapshot contains all zeros, leading to incorrect decisions.
**Why it happens:** `async_track_time_interval` fires immediately after setup. Sensor platforms may not have completed their first update.
**How to avoid:** Add a startup delay (skip the first 1-2 cycles) or check if critical snapshot values are non-zero before evaluating. The reference integration uses `execute=False` for the initial cycle.
**Warning signs:** Logs showing "Entladung blockiert" right after startup despite full battery, or charge limit set to 0 on a non-surplus day.

### Pitfall 2: Sun State Edge Cases
**What goes wrong:** `sun.sun` entity's `next_rising` is always the NEXT sunrise. During daytime, that's tomorrow's sunrise. During nighttime after midnight, that's today's sunrise.
**Why it happens:** The `next_rising` attribute rolls over at the actual sunrise moment.
**How to avoid:** Use the reference pattern: when `sun.state == "above_horizon"`, today's sunrise = `next_rising - 24h`. For "1h before sunrise" morning blocking, this means: if nighttime and `next_rising - 1h < now`, start blocking.
**Warning signs:** Morning blocking starts 23 hours late or never triggers.

### Pitfall 3: Optimizer Mode Entity Not Yet Available When Timer Fires
**What goes wrong:** The `select.eeg_energy_optimizer_optimizer` entity may not exist when the first timer callback runs, because platform setup is async.
**Why it happens:** `async_forward_entry_setups` schedules platform loading but the optimizer timer in `__init__.py` may fire before the select platform completes.
**How to avoid:** Read mode from the optimizer's own state (stored reference to the select entity or a mode property on the optimizer itself) rather than reading from `hass.states`. Or: start the timer after a short delay, or use `async_track_time_interval` with an initial check.
**Warning signs:** `hass.states.get("select.eeg_energy_optimizer_optimizer")` returns None in first cycle.

### Pitfall 4: Inverter Called Every Cycle Instead of On Change
**What goes wrong:** The inverter gets 60 commands per hour even though the desired state hasn't changed. This can stress the Huawei Solar integration or hit rate limits.
**Why it happens:** No deduplication of inverter commands.
**How to avoid:** Track previous actions (`_prev_charge_limit`, `_prev_discharge_active`) and only call inverter methods when the new decision differs from the previous one.
**Warning signs:** Huawei Solar logs showing repeated forcible_charge_soc calls with identical parameters.

### Pitfall 5: Config Flow VERSION Not Bumped
**What goes wrong:** Users who installed in Phase 2 can't add Phase 3 config entries because the schema has new required fields but the VERSION hasn't changed.
**Why it happens:** Forgetting to increment `VERSION` and add a migration path.
**How to avoid:** Bump config flow VERSION to 3. Add `async_migrate_entry` in `__init__.py` to supply default values for new keys when upgrading from VERSION 2.
**Warning signs:** Config entry fails to load after update, or HA shows "failed to set up" errors.

### Pitfall 6: Markdown Formatting in Sensor Attributes
**What goes wrong:** The Markdown in `extra_state_attributes` gets HTML-escaped or newlines get lost when displayed in a Lovelace Markdown card.
**Why it happens:** HA serializes attributes as JSON. Markdown cards use `{{ state_attr(...) }}` which outputs raw strings.
**How to avoid:** Use plain Markdown syntax with `\n` newlines in the Python string. Test the attribute value in a Markdown card with `{{ state_attr('sensor.eeg_energy_optimizer_entscheidung', 'markdown') }}`. Avoid HTML tags.
**Warning signs:** Markdown card shows literal `\n` characters or `&lt;` instead of `<`.

## Code Examples

### Ueberschuss-Faktor Calculation (simplified for new integration)
```python
# Source: energieoptimierung/optimizer.py _calc_ueberschuss_faktor, simplified
def _calc_ueberschuss_faktor(self, snap: Snapshot) -> float:
    """PV forecast / consumption forecast. Higher = more surplus."""
    # For morning: use today's values
    # For evening: use tomorrow's values
    if snap.pv_remaining_today_kwh is None or snap.pv_remaining_today_kwh <= 0:
        return 0.0
    consumption = snap.consumption_today_kwh
    if consumption <= 0:
        return 99.0
    return snap.pv_remaining_today_kwh / consumption
```

### Dynamic Min-SOC Calculation
```python
# Source: energieoptimierung/optimizer.py _calc_min_soc_entladung (exact port)
def _calc_min_soc(self, snap: Snapshot) -> float:
    """Minimum SOC for evening discharge.

    Formula: base_min_soc + (overnight_consumption * (1 + safety_buffer%)) as SOC%.
    """
    if snap.battery_capacity_kwh <= 0:
        return float(self._min_soc)

    overnight_kwh = snap.consumption_to_sunrise_kwh
    buffer_factor = 1.0 + (self._safety_buffer_pct / 100.0)
    needed_kwh = overnight_kwh * buffer_factor

    overnight_soc = (needed_kwh / snap.battery_capacity_kwh) * 100.0
    return math.ceil(self._min_soc + overnight_soc)
```

### Morning Blocking Logic
```python
def _should_block_charging(self, snap: Snapshot) -> bool:
    """Check if morning charge blocking should be active (D-01 to D-04)."""
    # Only on surplus days (D-03)
    factor = self._calc_ueberschuss_faktor(snap)
    if factor < self._ueberschuss_schwelle:
        return False

    # Time window: 1h before sunrise until configured end time (D-01, D-02)
    if snap.sunrise is None:
        return False

    block_start = snap.sunrise - timedelta(hours=1)
    block_end = snap.now.replace(
        hour=self._morning_end_hour, minute=self._morning_end_min,
        second=0, microsecond=0
    )

    return block_start <= snap.now < block_end
```

### Evening Discharge Check
```python
def _should_discharge(self, snap: Snapshot) -> tuple[bool, float, list[str]]:
    """Check if evening discharge should be active (D-05 to D-09).

    Returns (should_discharge, min_soc, block_reasons).
    """
    reasons: list[str] = []
    min_soc = self._calc_min_soc(snap)

    # Not time yet (D-05)
    if snap.now.hour < self._discharge_start_h or (
        snap.now.hour == self._discharge_start_h
        and snap.now.minute < self._discharge_start_m
    ):
        return False, min_soc, ["Vor Startzeit"]

    # SOC check (D-07)
    if snap.battery_soc <= min_soc:
        reasons.append(f"SOC {snap.battery_soc:.0f}% <= Min {min_soc:.0f}%")

    # Tomorrow surplus check (D-09, simplified: no Puffer/Heizstab)
    tomorrow_demand = snap.consumption_tomorrow_kwh
    # Battery charge from min_soc to 100%
    if snap.battery_capacity_kwh > 0:
        tomorrow_demand += (100.0 - self._min_soc) / 100.0 * snap.battery_capacity_kwh

    if snap.pv_tomorrow_kwh is not None and tomorrow_demand > 0:
        if snap.pv_tomorrow_kwh < tomorrow_demand:
            reasons.append(
                f"Morgen kein Ueberschusstag "
                f"(PV {snap.pv_tomorrow_kwh:.0f} < Bedarf {tomorrow_demand:.0f})"
            )

    return len(reasons) == 0, min_soc, reasons
```

### Config Flow Step 5 (Optimizer Parameters)
```python
# New config flow step for optimizer settings
STEP_OPTIMIZER_SCHEMA = vol.Schema({
    vol.Required(CONF_UEBERSCHUSS_SCHWELLE, default=1.25): NumberSelector(
        NumberSelectorConfig(min=0.5, max=3.0, step=0.05, mode=NumberSelectorMode.BOX)
    ),
    vol.Required(CONF_MORNING_END_TIME, default="10:00"): TimeSelector(TimeSelectorConfig()),
    vol.Required(CONF_DISCHARGE_START_TIME, default="20:00"): TimeSelector(TimeSelectorConfig()),
    vol.Required(CONF_DISCHARGE_POWER_KW, default=3.0): NumberSelector(
        NumberSelectorConfig(min=0.5, max=10.0, step=0.5, unit_of_measurement="kW", mode=NumberSelectorMode.BOX)
    ),
    vol.Required(CONF_MIN_SOC, default=10): NumberSelector(
        NumberSelectorConfig(min=5, max=50, step=1, unit_of_measurement="%", mode=NumberSelectorMode.BOX)
    ),
    vol.Required(CONF_SAFETY_BUFFER_PCT, default=25): NumberSelector(
        NumberSelectorConfig(min=0, max=100, step=5, unit_of_measurement="%", mode=NumberSelectorMode.BOX)
    ),
})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Guards system (KRITISCH/HOCH/MITTEL) | No guards, hardware Min-SOC + dynamic Min-SOC only | D-14 (this phase) | Drastically simpler optimizer, fewer states to manage |
| Multiple strategies (Ueberschuss/Balanciert/Engpass/Nacht) | Three states (Morgen-Einspeisung/Normal/Abend-Entladung) | D-22 (this phase) | No Heizstab/Warmwasser control, no strategy matrix |
| 5 optimizer modes | 3 modes (Ein/Test/Aus) | D-17 (this phase) | No Eigenverbrauch modes needed (no Heizstab) |
| Fronius HTTP Digest Auth | Huawei Solar HA services | Phase 1 | Inverter calls are simple HA service calls, no HTTP client |
| Separate switch/number for feed-in | Optimizer controls everything | D-19 (this phase) | Fewer entities to manage |

## Open Questions

1. **Morning block start: exactly 1h before sunrise or configurable?**
   - What we know: D-01 says "1 Stunde vor Sonnenaufgang". The reference integration uses a configurable `sunrise_offset_h`.
   - What's unclear: Whether this offset should be configurable or hard-coded at 1h.
   - Recommendation: Hard-code at 1h per D-01. If users want configurability later, it's a simple addition.

2. **Optimizer timer start: immediately or after platforms are ready?**
   - What we know: The reference integration fires immediately. Phase 2 sensors also start their timers in `async_setup_entry`.
   - What's unclear: Whether the optimizer should wait for the select entity to be available.
   - Recommendation: Start timer immediately but skip the first cycle if the select entity is not yet available (graceful degradation).

3. **Config migration from VERSION 2 to 3**
   - What we know: Config flow is currently VERSION 2. New keys (discharge params, morning end time, etc.) need default values.
   - What's unclear: Whether to use `async_migrate_entry` or make all new keys optional with defaults.
   - Recommendation: Use `async_migrate_entry` to add defaults, ensuring clean upgrade path. All new config keys should also have defaults in const.py.

4. **Ueberschuss-Faktor: today's remaining PV vs. today's total PV**
   - What we know: The reference uses `solcast_remaining_kwh / energy_demand_kwh`. But energy_demand_kwh is a composite sensor (battery + puffer + hausverbrauch). New integration has no composite "Energiebedarf" sensor.
   - What's unclear: Exact formula for the new integration's Ueberschuss-Faktor.
   - Recommendation: Use `pv_remaining_today / consumption_remaining_today` for daytime morning decisions. Use `pv_tomorrow / (consumption_tomorrow + battery_charge_kwh)` for evening discharge decisions (SAF-03).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pyproject.toml` ([tool.pytest.ini_options]) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OPT-01 | Morning charge blocking on surplus days, no blocking on non-surplus days | unit | `python -m pytest tests/test_optimizer.py::test_morning_block -x` | Wave 0 |
| OPT-02 | Evening discharge starts at configured time, stops at min-SOC | unit | `python -m pytest tests/test_optimizer.py::test_evening_discharge -x` | Wave 0 |
| OPT-03 | Dynamic Min-SOC formula correctness | unit | `python -m pytest tests/test_optimizer.py::test_min_soc_calculation -x` | Wave 0 |
| SAF-01 | ENTFAELLT | - | - | - |
| SAF-02 | ENTFAELLT (lives as OPT-03 discharge calc) | - | - | - |
| SAF-03 | Discharge only when PV tomorrow >= demand tomorrow | unit | `python -m pytest tests/test_optimizer.py::test_next_day_check -x` | Wave 0 |
| SAF-04 | Test mode calculates but does not execute inverter commands | unit | `python -m pytest tests/test_optimizer.py::test_dry_run_mode -x` | Wave 0 |
| SENS-01 | Decision sensor state and Markdown attributes | unit | `python -m pytest tests/test_decision_sensor.py -x` | Wave 0 |
| SENS-02 | Discharge preview in sensor attributes (merged with SENS-01) | unit | `python -m pytest tests/test_decision_sensor.py::test_discharge_preview -x` | Wave 0 |
| SENS-03 | Configurable morning/evening time windows respected | unit | `python -m pytest tests/test_optimizer.py::test_time_windows -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_optimizer.py` -- covers OPT-01, OPT-02, OPT-03, SAF-03, SAF-04, SENS-03
- [ ] `tests/test_decision_sensor.py` -- covers SENS-01, SENS-02
- [ ] `tests/test_select.py` -- covers SAF-04 (mode entity persistence, state transitions)
- [ ] Update `tests/conftest.py` -- add optimizer-specific fixtures (mock sun state, mock forecast/coordinator)

*(Existing test files for Phase 1+2 remain unchanged)*

## Sources

### Primary (HIGH confidence)
- `custom_components/energieoptimierung/optimizer.py` -- Reference implementation: Snapshot/Decision pattern, discharge logic, Min-SOC formula, Ueberschuss-Faktor, guard system (for understanding what to NOT port)
- `custom_components/energieoptimierung/select.py` -- Reference: RestoreEntity + SelectEntity pattern
- `custom_components/energieoptimierung/const.py` -- Reference: config keys, defaults, mode constants
- `custom_components/eeg_energy_optimizer/` -- Target codebase: __init__.py, sensor.py, coordinator.py, forecast_provider.py, inverter/base.py, config_flow.py
- `.planning/phases/03-optimizer-safety-system/03-CONTEXT.md` -- User decisions D-01 through D-30

### Secondary (MEDIUM confidence)
- [Home Assistant Developer Docs: Entity](https://developers.home-assistant.io/docs/core/entity/) -- Entity lifecycle, RestoreEntity
- [Home Assistant: Select Integration](https://www.home-assistant.io/integrations/select/) -- SelectEntity API
- [HA Community: Custom component scan_interval](https://community.home-assistant.io/t/custom-component-how-to-implement-scan-interval/385749) -- async_track_time_interval usage patterns

### Tertiary (LOW confidence)
- None -- all critical patterns verified against existing working code in the repository

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries are HA-native, no external dependencies
- Architecture: HIGH -- direct port of proven patterns from reference integration, simplified per user decisions
- Pitfalls: HIGH -- derived from actual issues observed in the reference implementation and standard HA integration development patterns

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (stable domain, HA core APIs rarely break)
