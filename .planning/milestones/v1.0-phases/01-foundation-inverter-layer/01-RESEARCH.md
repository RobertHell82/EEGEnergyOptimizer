# Phase 1: Foundation & Inverter Layer - Research

**Researched:** 2026-03-21
**Domain:** Home Assistant custom integration development, HACS packaging, abstract inverter interface, Huawei SUN2000 battery control
**Confidence:** HIGH

## Summary

Phase 1 creates a new HACS-compatible Home Assistant custom integration (`eeg_energy_optimizer`) with an abstract inverter interface and a concrete Huawei SUN2000 implementation. The integration is entirely separate from the existing `energieoptimierung` integration -- no imports, just pattern reference.

The Huawei SUN2000 battery control works through HA service calls to the existing `huawei_solar` integration (by wlcrs). Three services are used: `huawei_solar.forcible_charge_soc` (charge to target SOC at given power), `huawei_solar.forcible_discharge_soc` (discharge to target SOC at given power), and `huawei_solar.stop_forcible_charge` (return to automatic mode). All require a `device_id` parameter. Battery SOC and capacity are read from HA sensor entities mapped during config flow -- not through the inverter interface.

The config flow has two steps: (1) select inverter type, (2) map sensors via entity pickers with `device_class` filtering. A hard validation step checks that the prerequisite integration (e.g., `huawei_solar`) is installed before allowing setup to proceed.

**Primary recommendation:** Use Python ABC for the inverter interface with three write methods (`async_set_charge_limit`, `async_set_discharge`, `async_stop_forcible`) plus a factory pattern for instantiation. Keep the interface minimal -- SOC/capacity reading stays in HA sensor entities, not the interface.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Domain: `eeg_energy_optimizer` with folder `custom_components/eeg_energy_optimizer/`
- Display name: "EEG Energy Optimizer"
- Language: German primary, English fallback in `translations/`
- Logo: peakshare.app EWA-Logo (https://peakshare.app/assets/logo_ewa.png)
- Three write commands in abstract interface: Ladelimit setzen (kW), Entladeleistung setzen (kW), Stopp (back to auto)
- Reading values (SOC, capacity) via HA sensor entities, NOT via the interface
- User maps SOC/capacity sensors in config flow
- Config flow step 1: select inverter type (Phase 1: Huawei SUN2000)
- Config flow step 2: map base sensors (SOC, capacity, PV sensor) via HA entity picker
- Hard validation: block setup if required HA integration not installed (Huawei Solar for Huawei, Fronius for Fronius, etc.)
- Entity picker with device_class filter for user-friendly sensor selection
- Own folder `custom_components/eeg_energy_optimizer/` -- completely separate from existing `energieoptimierung/`
- No imports from existing integration -- only use as read reference for algorithm patterns
- Both integrations run in parallel on the HA instance
- Standard HACS layout from the start: `hacs.json`, `README`, `manifest.json`
- Huawei Solar services: `forcible_charge`, `forcible_discharge_soc`, `stop_forcible_charge`
- HA Integration Registry for prerequisite check

### Claude's Discretion
- Technical architecture of abstract inverter interface (Python ABC design, method signatures, error handling)
- Internal code structure and module organization
- HACS-specific files (hacs.json content, manifest.json fields)
- Test strategy if desired

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INF-01 | Abstract inverter interface -- Python ABC with methods for charge/discharge control (set_charge_limit, set_discharge, stop_forcible) | Architecture Patterns section defines the ABC contract, method signatures, error handling, and factory pattern |
| INF-02 | Huawei SUN2000 implementation -- concrete implementation via HA Huawei Solar Integration services (forcible_charge_soc, forcible_discharge_soc, stop_forcible_charge) | Huawei service call details documented with parameters (device_id, power, target_soc) and async_call pattern |
| INF-03 | HACS-compatible repo structure -- manifest.json, hacs.json, correct directory structure, brand assets | Standard Stack and HACS structure sections define all required files and their content |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| homeassistant | 2025.3+ | HA core framework | Target platform, provides ConfigFlow, services, entity registry |
| voluptuous | (bundled with HA) | Config schema validation | Standard HA config flow validation, already used in existing integration |
| Python abc module | stdlib | Abstract base classes | Standard Python pattern for interface contracts, no external dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| homeassistant.helpers.selector | (bundled) | EntitySelector, EntitySelectorConfig | Config flow entity pickers with device_class filtering |
| homeassistant.config_entries | (bundled) | ConfigEntry, ConfigEntryState | Integration setup, prerequisite validation |
| aiohttp | (bundled with HA) | HTTP client | Only if direct API calls needed (not for Phase 1 Huawei -- uses HA services) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python ABC | Protocol (typing) | ABC provides runtime isinstance checks and clear error messages on missing methods; Protocol is structural typing without enforcement -- ABC is better for mandatory contracts |
| HA service calls | Direct Modbus via huawei-solar-lib | Service calls decouple from Modbus details, work with any huawei_solar config, and respect the integration's connection management; direct Modbus would duplicate work and conflict |

## Architecture Patterns

### Recommended Project Structure
```
custom_components/eeg_energy_optimizer/
  __init__.py           # async_setup_entry, platform forwarding
  config_flow.py        # 2-step config flow (inverter type + sensor mapping)
  const.py              # Domain, config keys, defaults, inverter type enum
  manifest.json         # HA integration manifest
  strings.json          # UI strings (German primary)
  translations/
    de.json             # German translations
    en.json             # English fallback
  inverter/
    __init__.py         # Factory function: get_inverter(type, hass, config) -> InverterBase
    base.py             # Abstract base class: InverterBase(ABC)
    huawei.py           # HuaweiInverter(InverterBase) -- HA service call implementation
```

Plus repository root:
```
hacs.json               # HACS manifest
README.md               # Required by HACS
custom_components/
  eeg_energy_optimizer/
    ...
```

### Pattern 1: Abstract Inverter Interface (INF-01)

**What:** Python ABC defining the write contract for any inverter type.
**When to use:** All inverter interactions go through this interface.

```python
# custom_components/eeg_energy_optimizer/inverter/base.py
from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant


class InverterBase(ABC):
    """Abstract base class for inverter battery control."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self._hass = hass
        self._config = config

    @abstractmethod
    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit in kW.

        Instructs the inverter to charge the battery at up to power_kw.
        Returns True on success, False on failure.
        """

    @abstractmethod
    async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
        """Set battery discharge at given power in kW.

        Optional target_soc (0-100) as SOC floor for discharge.
        Returns True on success, False on failure.
        """

    @abstractmethod
    async def async_stop_forcible(self) -> bool:
        """Stop any forced charge/discharge, return to automatic mode.

        Returns True on success, False on failure.
        """

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the inverter connection/service is available."""
```

### Pattern 2: Huawei SUN2000 Implementation (INF-02)

**What:** Concrete implementation that calls Huawei Solar HA services.
**When to use:** When user selects Huawei SUN2000 as inverter type.

```python
# custom_components/eeg_energy_optimizer/inverter/huawei.py
import logging
from homeassistant.core import HomeAssistant
from .base import InverterBase

_LOGGER = logging.getLogger(__name__)

HUAWEI_DOMAIN = "huawei_solar"


class HuaweiInverter(InverterBase):
    """Huawei SUN2000 inverter control via HA Huawei Solar services."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        super().__init__(hass, config)
        self._device_id: str = config["huawei_device_id"]

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        power_w = int(power_kw * 1000)
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "forcible_charge_soc",
                {
                    "device_id": self._device_id,
                    "power": str(power_w),
                    "target_soc": 100,  # charge to full, optimizer controls power
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set charge limit")
            return False

    async def async_set_discharge(self, power_kw: float, target_soc: float | None = None) -> bool:
        power_w = int(power_kw * 1000)
        soc = int(target_soc) if target_soc is not None else 10
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "forcible_discharge_soc",
                {
                    "device_id": self._device_id,
                    "power": str(power_w),
                    "target_soc": soc,
                },
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        try:
            await self._hass.services.async_call(
                HUAWEI_DOMAIN,
                "stop_forcible_charge",
                {"device_id": self._device_id},
                blocking=True,
            )
            return True
        except Exception:
            _LOGGER.exception("Huawei: Failed to stop forcible mode")
            return False

    @property
    def is_available(self) -> bool:
        entries = self._hass.config_entries.async_entries(HUAWEI_DOMAIN)
        return any(
            entry.state.value == "loaded" for entry in entries
        )
```

### Pattern 3: Factory Pattern for Inverter Instantiation

**What:** Simple factory function that creates the right inverter based on config.
**When to use:** In `__init__.py` during `async_setup_entry`.

```python
# custom_components/eeg_energy_optimizer/inverter/__init__.py
from homeassistant.core import HomeAssistant
from .base import InverterBase
from .huawei import HuaweiInverter

INVERTER_TYPES = {
    "huawei_sun2000": HuaweiInverter,
    # Future: "fronius_gen24": FroniusInverter,
}

def create_inverter(inverter_type: str, hass: HomeAssistant, config: dict) -> InverterBase:
    """Create an inverter instance based on the configured type."""
    cls = INVERTER_TYPES.get(inverter_type)
    if cls is None:
        raise ValueError(f"Unknown inverter type: {inverter_type}")
    return cls(hass, config)
```

### Pattern 4: Config Flow with Entity Selectors and Prerequisite Validation

**What:** 2-step config flow: inverter selection + sensor mapping.
**When to use:** Integration setup.

```python
# Config flow step 1: Inverter type selection
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
    EntitySelector, EntitySelectorConfig,
)

INVERTER_PREREQUISITES = {
    "huawei_sun2000": "huawei_solar",
    # Future: "fronius_gen24": "fronius",
}

# Step 1 schema
vol.Schema({
    vol.Required(CONF_INVERTER_TYPE): SelectSelector(
        SelectSelectorConfig(
            options=[
                {"value": "huawei_sun2000", "label": "Huawei SUN2000"},
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    ),
})

# Step 1 validation - check prerequisite integration
async def async_step_user(self, user_input):
    errors = {}
    if user_input is not None:
        inverter_type = user_input[CONF_INVERTER_TYPE]
        required_domain = INVERTER_PREREQUISITES.get(inverter_type)
        entries = self.hass.config_entries.async_entries(required_domain)
        loaded = [e for e in entries if e.state.value == "loaded"]
        if not loaded:
            errors["base"] = "prerequisite_not_installed"
        else:
            self._data.update(user_input)
            return await self.async_step_sensors()
    return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

# Step 2 schema - sensor mapping with device_class filter
vol.Schema({
    vol.Required(CONF_BATTERY_SOC_SENSOR): EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="battery")
    ),
    vol.Required(CONF_BATTERY_CAPACITY_SENSOR): EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="energy")
    ),
    vol.Required(CONF_PV_POWER_SENSOR): EntitySelector(
        EntitySelectorConfig(domain="sensor", device_class="power")
    ),
    vol.Required(CONF_HUAWEI_DEVICE_ID): str,  # Device ID for service calls
})
```

### Pattern 5: Prerequisite Integration Check

**What:** Validate that the required inverter integration is installed and loaded.
**When to use:** Config flow step 1, and optionally at runtime.

```python
from homeassistant.config_entries import ConfigEntryState

def is_integration_loaded(hass, domain: str) -> bool:
    """Check if a given HA integration domain is loaded."""
    entries = hass.config_entries.async_entries(domain)
    return any(entry.state == ConfigEntryState.LOADED for entry in entries)
```

### Anti-Patterns to Avoid
- **Direct Modbus/API calls to Huawei inverter:** The `huawei_solar` integration manages the Modbus connection. Calling Modbus directly would conflict with its connection management and break when that integration updates.
- **Storing SOC/capacity in the inverter interface:** These are read from HA sensor entities. The inverter interface is write-only for commands. Mixing read and write creates unnecessary coupling.
- **Single-file inverter module:** Putting the ABC and all implementations in one file makes adding new inverters require editing existing code. Separate files per implementation.
- **Hardcoding entity IDs:** The existing `energieoptimierung` integration hardcodes sensor entity IDs as defaults. The new integration should use entity pickers exclusively -- no hardcoded defaults for sensor entities.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Huawei Modbus communication | Custom Modbus client | `hass.services.async_call("huawei_solar", ...)` | huawei_solar manages connection, authentication, retries, and Modbus register mapping |
| Config flow entity selection | Text input for entity IDs | `EntitySelector(EntitySelectorConfig(...))` | Provides autocomplete, validation, device_class filtering, and proper HA UI experience |
| Integration prerequisite check | Custom HTTP check or file scan | `hass.config_entries.async_entries(domain)` | Uses HA's own registry, accurate and maintained |
| HACS packaging | Custom install scripts | Standard HACS directory layout + `hacs.json` | HACS handles download, installation, updates automatically |

**Key insight:** The Huawei implementation is deliberately thin -- it translates kW commands to HA service calls. All complex Modbus communication is handled by the existing `huawei_solar` integration.

## Common Pitfalls

### Pitfall 1: Huawei Solar "Elevate Permissions" Not Enabled
**What goes wrong:** Service calls to `forcible_charge_soc` / `forcible_discharge_soc` fail silently or raise errors because the Huawei Solar integration was set up without elevated permissions.
**Why it happens:** The Huawei Solar integration requires "Elevate permissions" during its own setup to expose battery control services. Users may not have enabled this.
**How to avoid:** Document this requirement clearly in setup instructions. Consider checking if the services exist in `hass.services.has_service(HUAWEI_DOMAIN, "forcible_charge_soc")` during config flow validation.
**Warning signs:** Service calls raise `ServiceNotFound` errors.

### Pitfall 2: Huawei device_id Discovery
**What goes wrong:** User doesn't know their Huawei battery `device_id` and enters it incorrectly.
**Why it happens:** `device_id` is an internal HA identifier, not user-visible. The batpred integration also requires this and users struggle with it.
**How to avoid:** Use a `DeviceSelector` with `DeviceSelectorConfig(integration="huawei_solar")` in the config flow to let the user pick the device visually instead of entering a raw ID. Alternatively, auto-discover by listing devices from the `huawei_solar` integration.
**Warning signs:** Service calls fail with "device not found" errors.

### Pitfall 3: Service Call Power Parameter as String
**What goes wrong:** Passing `power` as integer when Huawei Solar expects a string.
**Why it happens:** The Huawei Solar services.yaml defines `power` with a text selector, meaning it expects a string value, not an integer.
**How to avoid:** Always pass `power` as `str(int(power_kw * 1000))` in service call data.
**Warning signs:** Type validation errors in service calls.

### Pitfall 4: manifest.json Missing Required Fields
**What goes wrong:** HACS or HA refuses to load the integration.
**Why it happens:** Missing fields like `version`, `issue_tracker`, `codeowners`, or incorrect `integration_type`.
**How to avoid:** Include all required fields from the start. Reference the existing `energieoptimierung/manifest.json` for format, but with the new domain and metadata.
**Warning signs:** "Invalid manifest" errors in HA logs.

### Pitfall 5: Config Flow unique_id Collision
**What goes wrong:** Can't add the integration because of unique_id conflict.
**Why it happens:** Using `await self.async_set_unique_id(DOMAIN)` means only one instance ever. This is fine for Phase 1 (single inverter) but may need revisiting for multi-inverter support.
**How to avoid:** Use `DOMAIN` as unique_id for now (matching existing pattern). Document that multi-inverter support would need a different unique_id strategy.
**Warning signs:** "Already configured" error when adding second instance.

### Pitfall 6: HACS Brand Directory
**What goes wrong:** HACS shows generic icon, not the EWA logo.
**Why it happens:** HACS expects brand assets in a specific location.
**How to avoid:** Create a `custom_components/eeg_energy_optimizer/` directory with `icon.png` and/or `logo.png`. For HACS default repository listing, assets go in the homeassistant-brands repo, but for custom repositories, local icons in the integration directory work.
**Warning signs:** Missing icon in HACS store listing.

## Code Examples

### manifest.json (INF-03)
```json
{
  "domain": "eeg_energy_optimizer",
  "name": "EEG Energy Optimizer",
  "version": "0.1.0",
  "documentation": "https://github.com/OWNER/eeg-energy-optimizer",
  "issue_tracker": "https://github.com/OWNER/eeg-energy-optimizer/issues",
  "dependencies": [],
  "after_dependencies": ["huawei_solar"],
  "codeowners": [],
  "iot_class": "local_push",
  "integration_type": "hub",
  "config_flow": true
}
```

Key decisions:
- `after_dependencies` includes `huawei_solar` so it loads first if present
- `dependencies` is empty -- `huawei_solar` is checked at config flow time, not enforced as hard dependency (user might not have it yet when HACS installs)
- `iot_class`: `local_push` -- sends commands to local inverter via HA services
- `integration_type`: `hub` -- matches existing pattern, manages devices

### hacs.json
```json
{
  "name": "EEG Energy Optimizer",
  "homeassistant": "2025.1.0",
  "render_readme": true
}
```

### strings.json (German primary)
```json
{
  "config": {
    "step": {
      "user": {
        "title": "Wechselrichter-Typ",
        "description": "Waehle den Wechselrichter-Typ fuer die Batteriesteuerung.",
        "data": {
          "inverter_type": "Wechselrichter"
        }
      },
      "sensors": {
        "title": "Sensor-Zuordnung",
        "description": "Ordne die Sensoren fuer SOC, Kapazitaet und PV-Leistung zu.",
        "data": {
          "battery_soc_sensor": "Batterie-Ladezustand (SOC)",
          "battery_capacity_sensor": "Batterie-Kapazitaet",
          "pv_power_sensor": "PV-Leistung",
          "huawei_device_id": "Huawei Batterie-Geraet"
        }
      }
    },
    "error": {
      "prerequisite_not_installed": "Die {integration_name}-Integration muss installiert und geladen sein."
    }
  }
}
```

### async_setup_entry Pattern
```python
# custom_components/eeg_energy_optimizer/__init__.py
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .inverter import create_inverter

PLATFORMS = []  # No platforms in Phase 1 -- just the inverter layer

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EEG Energy Optimizer from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    config = {**entry.data, **entry.options}

    # Create inverter instance based on configured type
    inverter = create_inverter(config["inverter_type"], hass, config)
    hass.data[DOMAIN][entry.entry_id] = {
        "config": config,
        "inverter": inverter,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
```

### Using hass.services.async_call
```python
# Pattern for calling Huawei Solar services
await hass.services.async_call(
    "huawei_solar",
    "forcible_charge_soc",
    {
        "device_id": device_id,      # HA internal device ID (string)
        "power": str(power_watts),    # Power in W as STRING
        "target_soc": target_soc,     # Integer 0-100
    },
    blocking=True,  # Wait for completion
)
```

### DeviceSelector for Huawei Device
```python
from homeassistant.helpers.selector import DeviceSelector, DeviceSelectorConfig

# In config flow step 2 schema, for device_id selection:
vol.Required(CONF_HUAWEI_DEVICE_ID): DeviceSelector(
    DeviceSelectorConfig(integration="huawei_solar")
),
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-homeassistant-custom-component |
| Config file | `pytest.ini` or `pyproject.toml` (to be created in Wave 0) |
| Quick run command | `pytest tests/ -x --timeout=10` |
| Full suite command | `pytest tests/ --timeout=30` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INF-01 | ABC enforces all 3 methods + is_available | unit | `pytest tests/test_inverter_base.py -x` | No -- Wave 0 |
| INF-01 | Factory creates correct inverter type | unit | `pytest tests/test_inverter_factory.py -x` | No -- Wave 0 |
| INF-01 | Factory raises on unknown type | unit | `pytest tests/test_inverter_factory.py -x` | No -- Wave 0 |
| INF-02 | HuaweiInverter calls correct HA services | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | No -- Wave 0 |
| INF-02 | HuaweiInverter passes power as string | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | No -- Wave 0 |
| INF-02 | HuaweiInverter returns False on service error | unit (mock) | `pytest tests/test_huawei_inverter.py -x` | No -- Wave 0 |
| INF-03 | manifest.json has all required fields | unit | `pytest tests/test_manifest.py -x` | No -- Wave 0 |
| INF-03 | hacs.json is valid | unit | `pytest tests/test_manifest.py -x` | No -- Wave 0 |
| INF-03 | Config flow validates prerequisite | unit (mock) | `pytest tests/test_config_flow.py -x` | No -- Wave 0 |
| INF-03 | Config flow creates entry with correct data | unit (mock) | `pytest tests/test_config_flow.py -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x --timeout=10`
- **Per wave merge:** `pytest tests/ --timeout=30`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/conftest.py` -- shared fixtures, mock hass instance
- [ ] `tests/test_inverter_base.py` -- ABC contract tests
- [ ] `tests/test_inverter_factory.py` -- factory pattern tests
- [ ] `tests/test_huawei_inverter.py` -- Huawei service call mocks
- [ ] `tests/test_config_flow.py` -- config flow step tests
- [ ] `tests/test_manifest.py` -- manifest validation
- [ ] `pyproject.toml` or `pytest.ini` -- test configuration
- [ ] Framework install: `pip install pytest pytest-homeassistant-custom-component pytest-asyncio`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `async_forward_entry_setup` (singular) | `async_forward_entry_setups` (plural) | HA 2023.3 | Must use plural form |
| `hass.config_entries.async_setup_platforms` | `entry.async_forward_entry_setups` on ConfigEntry | HA 2022.8+ | Called on entry, not config_entries |
| Text input for entity IDs | `EntitySelector` / `DeviceSelector` | HA 2021.11+ | Provides UI dropdowns, autocomplete, filtering |
| services.yaml for service definitions | Both services.yaml and programmatic registration | HA 2023+ | Either approach works, yaml is simpler for Phase 1 |

**Deprecated/outdated:**
- `async_forward_entry_setup` (singular): Removed in HA 2023.3, use `async_forward_entry_setups`
- `hass.helpers.discovery.async_load_platform`: Legacy, use config_entries

## Open Questions

1. **Huawei device_id discovery in config flow**
   - What we know: The `device_id` is required for all Huawei service calls. `DeviceSelector(DeviceSelectorConfig(integration="huawei_solar"))` should list available devices.
   - What's unclear: Whether `DeviceSelector` correctly shows Huawei battery devices specifically (vs. inverter devices). The Huawei Solar integration creates multiple devices (inverter, battery, power meter).
   - Recommendation: Use `DeviceSelector` with `integration="huawei_solar"` filter. If further filtering is needed, add `model` filter for "Batteries" in `DeviceSelectorConfig`. Test on the live HA instance.

2. **Power parameter format for Huawei services**
   - What we know: The batpred template passes power as a string template `"{inverter_limit_charge}"`. The services.yaml uses a text selector for power.
   - What's unclear: Whether passing an integer would also work (service might coerce).
   - Recommendation: Always pass as string to be safe. Confidence: MEDIUM.

3. **HACS brand assets location**
   - What we know: HACS docs mention a `brand` directory. For default repos, brands go in `homeassistant-brands` repo.
   - What's unclear: Exact location for custom repository brand assets.
   - Recommendation: Place `icon.png` and `logo.png` in integration directory for now. Can adjust for HACS default repo later.

## Sources

### Primary (HIGH confidence)
- [wlcrs/huawei_solar GitHub](https://github.com/wlcrs/huawei_solar) - Integration structure, services, wiki
- [Huawei Solar Wiki - Force charge/discharge](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery) - Service descriptions and requirements
- [HACS Integration Publishing](https://hacs.xyz/docs/publish/integration/) - Required files and structure
- [HACS General Requirements](https://www.hacs.xyz/docs/publish/start/) - hacs.json, README, topics
- [HA Developer Docs - Config Entries](https://developers.home-assistant.io/docs/config_entries_index/) - ConfigEntry API, async_entries
- Existing `custom_components/energieoptimierung/` codebase - Verified patterns for config flow, setup, constants

### Secondary (MEDIUM confidence)
- [batpred Huawei template](https://raw.githubusercontent.com/springfall2008/batpred/main/templates/huawei.yaml) - Service call parameters and format (power as string)
- [HA Community - Huawei charge/discharge](https://community.home-assistant.io/t/huawei-fusionsolar-battery-charge-discharge/742124) - User experiences with services
- [HA Developer Docs - Service Actions](https://developers.home-assistant.io/docs/dev_101_services/) - async_call patterns

### Tertiary (LOW confidence)
- Brand assets location for HACS custom repos - could not verify exact path from official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using well-documented HA patterns and existing integration as reference
- Architecture: HIGH - ABC pattern is standard Python, factory pattern is straightforward, service call API is well-documented
- Pitfalls: HIGH - Verified through Huawei Solar issues, batpred templates, and community reports
- Huawei service parameters: MEDIUM - Verified from batpred template and wiki, but power-as-string detail needs live testing

**Research date:** 2026-03-21
**Valid until:** 2026-04-21 (stable domain -- HA and HACS patterns change slowly)
