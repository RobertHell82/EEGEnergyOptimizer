# Architecture Patterns

**Domain:** Home Assistant custom integration for EEG battery optimization with onboarding panel
**Researched:** 2026-03-20

## Recommended Architecture

The integration consists of three major subsystems: a **Python backend** (HA integration), a **JavaScript frontend** (custom sidebar panel), and an **abstract inverter layer** bridging optimization logic to physical hardware. Communication between frontend and backend uses HA's WebSocket API with custom commands.

```
+---------------------------------------------------+
|              Home Assistant Core                    |
|                                                     |
|  +---------------------------------------------+   |
|  |     eeg_optimizer (custom_components/)       |   |
|  |                                               |   |
|  |  __init__.py                                  |   |
|  |    - async_setup_entry()                      |   |
|  |    - Register static paths for frontend       |   |
|  |    - Register sidebar panel                   |   |
|  |    - Register WebSocket commands              |   |
|  |    - Start optimizer timer (60s cycle)        |   |
|  |                                               |   |
|  |  optimizer.py (Decision Engine)               |   |
|  |    - Gather inputs (sensors, forecasts)       |   |
|  |    - Evaluate strategy (EEG time windows)     |   |
|  |    - Execute via InverterInterface            |   |
|  |                                               |   |
|  |  inverter/                                    |   |
|  |    - base.py (InverterInterface ABC)          |   |
|  |    - huawei.py (HuaweiSUN2000Inverter)        |   |
|  |    - [fronius.py] (future)                    |   |
|  |                                               |   |
|  |  websocket.py                                 |   |
|  |    - Custom WS commands for panel             |   |
|  |                                               |   |
|  |  frontend/                                    |   |
|  |    - eeg-optimizer-panel.js (LitElement)      |   |
|  |    - Onboarding wizard + status dashboard     |   |
|  |                                               |   |
|  |  config_flow.py (minimal, defers to panel)    |   |
|  |  sensor.py / switch.py / number.py            |   |
|  +---------------------------------------------+   |
|                                                     |
|  External Integrations (not bundled):               |
|  - huawei_solar (wlcrs) -- Modbus to inverter      |
|  - solcast_solar -- PV forecasts                    |
|  - forecast_solar -- Free PV forecasts              |
+---------------------------------------------------+
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `__init__.py` | Entry point: setup, timer, platform forwarding, panel registration | All components, HA core |
| `optimizer.py` | Decision engine: strategy selection, EEG window logic | Sensors (read), InverterInterface (write) |
| `inverter/base.py` | Abstract interface defining inverter capabilities | Nothing directly (ABC) |
| `inverter/huawei.py` | Huawei SUN2000 implementation via HA service calls | HA service bus (`huawei_solar` services) |
| `websocket.py` | Custom WS commands for frontend panel | optimizer.py (status), config store (settings) |
| `frontend/` | Onboarding panel + runtime dashboard (LitElement) | Backend via WebSocket API |
| `config_flow.py` | Minimal config flow (integration discovery/init) | HA config entries |
| `sensor.py` | Expose optimizer state, forecasts, demand as entities | optimizer.py (data source) |
| `coordinator.py` | Consumption history from recorder | HA recorder integration |

### Data Flow

```
1. INPUTS (every 60s cycle):
   Solcast/Forecast.Solar sensors ──┐
   Battery SOC sensor ──────────────┤
   PV production sensor ────────────┤──► optimizer._gather_inputs() ──► Snapshot
   Grid feed-in sensor ─────────────┤
   Consumption history (recorder) ──┘

2. DECISION:
   Snapshot ──► optimizer._evaluate()
     - Check EEG time windows (morning feed-in, evening discharge)
     - Check guards (battery SOC thresholds)
     - Select strategy: MORNING_FEEDIN / CHARGE / EVENING_DISCHARGE / IDLE
   ──► Decision (strategy + actions)

3. EXECUTION:
   Decision ──► InverterInterface.execute(actions)
     - HuaweiSUN2000Inverter calls HA services:
       * huawei_solar.forcible_charge(power, duration)
       * huawei_solar.forcible_discharge_soc(target_soc, power)
       * huawei_solar.stop_forcible_charge()

4. FRONTEND (on-demand via WebSocket):
   Panel ──ws──► websocket.py ──► optimizer.get_status()
   Panel ──ws──► websocket.py ──► config_store.update_settings()
   Panel ◄──ws── hass state changes (entity subscriptions)
```

## Key Architectural Decisions

### 1. Panel Registration (Integration-Managed, Not YAML)

The panel is registered programmatically in `__init__.py`, not via `panel_custom` in `configuration.yaml`. This is the correct approach for a HACS-distributed integration because users should not need to manually edit YAML.

**Implementation pattern** (HIGH confidence, verified from community guide and HA source):

```python
# __init__.py
from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig

async def async_setup_entry(hass, entry):
    # 1. Serve frontend files
    panel_path = os.path.join(os.path.dirname(__file__), "frontend")
    panel_url = f"/{DOMAIN}_panel"
    await hass.http.async_register_static_paths([
        StaticPathConfig(panel_url, panel_path, cache_headers=False)
    ])

    # 2. Register sidebar panel
    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="eeg-optimizer-panel",
        frontend_url_path=DOMAIN,
        sidebar_title="EEG Optimizer",
        sidebar_icon="mdi:solar-power-variant",
        module_url=f"{panel_url}/eeg-optimizer-panel.js",
        embed_iframe=False,
        require_admin=False,
    )
```

**manifest.json must declare dependencies:**
```json
{
  "dependencies": ["http", "frontend", "panel_custom", "recorder"]
}
```

### 2. Frontend-Backend Communication via WebSocket API

The panel communicates with the backend through custom WebSocket commands, not REST. This is HA's standard pattern for real-time bidirectional communication.

**Backend registration** (HIGH confidence, from official HA developer docs):

```python
# websocket.py
from homeassistant.components import websocket_api
import voluptuous as vol

@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/get_status",
})
@callback
def ws_get_status(hass, connection, msg):
    optimizer = hass.data[DOMAIN].get("optimizer")
    connection.send_result(msg["id"], optimizer.get_status_dict())

@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/update_config",
    vol.Required("config"): dict,
})
@websocket_api.async_response
async def ws_update_config(hass, connection, msg):
    # Validate and persist config changes
    ...
    connection.send_result(msg["id"], {"success": True})

# Register in async_setup_entry:
websocket_api.async_register_command(hass, ws_get_status)
websocket_api.async_register_command(hass, ws_update_config)
```

**Frontend invocation:**
```javascript
// In LitElement panel
const result = await this.hass.connection.sendMessagePromise({
    type: "eeg_optimizer/get_status"
});
```

### 3. Abstract Inverter Interface

Use Python's ABC (Abstract Base Class) to define the inverter contract. Each inverter type is a concrete implementation. The optimizer never knows which inverter it is talking to.

**Pattern** (HIGH confidence, standard Python pattern + HA convention of separating device communication):

```python
# inverter/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

class ChargeMode(Enum):
    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"

@dataclass
class BatteryStatus:
    soc_percent: float
    capacity_kwh: float
    current_power_w: float  # positive=charging, negative=discharging
    is_forcible_active: bool

@dataclass
class InverterAction:
    mode: ChargeMode
    power_w: float = 0
    target_soc: float | None = None
    duration_minutes: int | None = None

class InverterInterface(ABC):
    """Abstract interface for inverter battery control."""

    @abstractmethod
    async def async_get_battery_status(self) -> BatteryStatus:
        """Read current battery state."""

    @abstractmethod
    async def async_execute_action(self, action: InverterAction) -> bool:
        """Execute a charge/discharge/idle action. Returns success."""

    @abstractmethod
    async def async_stop_forcible(self) -> bool:
        """Cancel any active forcible charge/discharge."""

    @abstractmethod
    def get_required_entities(self) -> list[str]:
        """Return entity IDs this inverter needs (for onboarding validation)."""
```

```python
# inverter/huawei.py
class HuaweiSUN2000Inverter(InverterInterface):
    """Huawei SUN2000 via huawei_solar integration services."""

    REQUIRED_SERVICES = [
        "huawei_solar.forcible_charge",
        "huawei_solar.forcible_discharge_soc",
        "huawei_solar.stop_forcible_charge",
    ]

    async def async_execute_action(self, action: InverterAction) -> bool:
        if action.mode == ChargeMode.CHARGE:
            await self.hass.services.async_call(
                "huawei_solar", "forcible_charge",
                {"device_id": self._device_id, "power": action.power_w, ...}
            )
        elif action.mode == ChargeMode.DISCHARGE:
            await self.hass.services.async_call(
                "huawei_solar", "forcible_discharge_soc",
                {"device_id": self._device_id, "target_soc": action.target_soc, ...}
            )
        elif action.mode == ChargeMode.IDLE:
            await self.async_stop_forcible()
```

### 4. Onboarding Panel Architecture

The panel serves two purposes: **onboarding wizard** (first-time setup) and **runtime dashboard** (ongoing status/control). Use a single LitElement component with view routing.

**Panel structure:**
```
frontend/
  eeg-optimizer-panel.js      -- Main entry, router, hass property receiver
  views/
    onboarding-welcome.js     -- Step 0: Welcome + prerequisite checks
    onboarding-inverter.js    -- Step 1: Select inverter type
    onboarding-sensors.js     -- Step 2: Map required sensors
    onboarding-forecast.js    -- Step 3: Configure PV forecast source
    onboarding-eeg.js         -- Step 4: EEG time windows
    onboarding-summary.js     -- Step 5: Review + activate
    dashboard.js              -- Runtime status + controls
```

**Note on bundling:** HA custom panels are loaded as ES modules. For a multi-file setup, either use a build step (Rollup/Vite) to bundle into a single JS file, or use dynamic `import()` with relative paths from the static URL. Bundling into a single file is strongly recommended for HACS distribution to avoid path resolution issues.

### 5. Config Flow vs. Panel for Configuration

Use a **minimal config flow** just to create the config entry (HA requires this for integration setup). All meaningful configuration happens in the onboarding panel via WebSocket commands that update `config_entry.options`.

```python
# config_flow.py
class EEGOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="EEG Optimizer", data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
```

The panel then stores configuration via WebSocket commands that call:
```python
hass.config_entries.async_update_entry(entry, options=new_config)
```

## Patterns to Follow

### Pattern 1: Inverter Factory

Select the concrete inverter implementation based on user's choice during onboarding.

```python
# inverter/__init__.py
from .base import InverterInterface
from .huawei import HuaweiSUN2000Inverter

INVERTER_TYPES = {
    "huawei_sun2000": HuaweiSUN2000Inverter,
}

def create_inverter(hass, inverter_type: str, config: dict) -> InverterInterface:
    cls = INVERTER_TYPES.get(inverter_type)
    if cls is None:
        raise ValueError(f"Unknown inverter type: {inverter_type}")
    return cls(hass, config)
```

### Pattern 2: Prerequisite Validation

The onboarding panel checks prerequisites before allowing setup. Backend provides a validation endpoint.

```python
@websocket_api.websocket_command({
    vol.Required("type"): "eeg_optimizer/check_prerequisites",
})
@websocket_api.async_response
async def ws_check_prerequisites(hass, connection, msg):
    checks = {
        "huawei_solar_installed": "huawei_solar" in hass.config.components,
        "solcast_installed": "solcast_solar" in hass.config.components,
        "forecast_solar_installed": "forecast_solar" in hass.config.components,
        "has_pv_forecast": any([...]),  # Check for Solcast or Forecast.Solar entities
    }
    connection.send_result(msg["id"], checks)
```

### Pattern 3: Optimizer Status as Sensor Attributes

Expose the full optimizer decision as sensor attributes (not just state). This makes data available both to the panel and to standard HA dashboards/automations.

```python
# sensor.py
class EEGDecisionSensor(SensorEntity):
    @property
    def native_value(self):
        return self._decision.strategy.value  # e.g., "morning_feedin"

    @property
    def extra_state_attributes(self):
        return {
            "strategy": self._decision.strategy.value,
            "reason": self._decision.reason,
            "battery_action": self._decision.battery_action,
            "target_power_w": self._decision.target_power_w,
            "eeg_window_active": self._decision.eeg_window_active,
            "next_transition": self._decision.next_transition,
        }
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Direct Modbus Communication
**What:** Talking to the Huawei inverter directly via Modbus from this integration.
**Why bad:** Modbus supports only one connection at a time. The `huawei_solar` integration already holds that connection. A second connection causes constant disconnects for both.
**Instead:** Always go through `huawei_solar` HA services. This is why the abstract interface uses `hass.services.async_call()`.

### Anti-Pattern 2: Storing Config in Files
**What:** Writing configuration to custom JSON/YAML files in the config directory.
**Why bad:** Bypasses HA's config entry system, breaks backup/restore, no migration path.
**Instead:** Use `config_entry.data` (immutable after setup) for identity and `config_entry.options` (mutable) for all user-changeable settings. Update via `hass.config_entries.async_update_entry()`.

### Anti-Pattern 3: Polling from Frontend
**What:** JavaScript panel polling the backend every N seconds for status updates.
**Why bad:** Wasteful, laggy, and doesn't scale. HA already pushes entity state changes over WebSocket.
**Instead:** Subscribe to entity state changes in the panel:
```javascript
// The hass object is automatically updated by HA when entities change
// In LitElement, just react to hass property changes:
updated(changedProps) {
    if (changedProps.has("hass")) {
        this._updateFromHass();
    }
}
```

### Anti-Pattern 4: Monolithic Panel JS
**What:** One giant JavaScript file with all panel logic.
**Why bad:** Unmaintainable, slow to develop, hard to test.
**Instead:** Use a build tool (Rollup or Vite) to bundle multiple source files into a single distributable JS module. Develop with proper module structure, distribute as single file.

### Anti-Pattern 5: Tight Coupling to Inverter Brand
**What:** Calling `huawei_solar` services directly from the optimizer.
**Why bad:** Adding Fronius requires changing optimizer.py core logic.
**Instead:** Optimizer only calls `InverterInterface` methods. The concrete implementation translates to brand-specific service calls.

## Suggested Build Order (Dependencies)

The architecture has clear dependency chains that dictate build order:

```
Phase 1: Foundation
  ├── manifest.json, __init__.py (minimal setup)
  ├── config_flow.py (minimal, creates entry)
  ├── const.py (domain, defaults)
  └── inverter/base.py (ABC definition)
       │
Phase 2: Inverter Layer
  ├── inverter/huawei.py (Huawei implementation)
  ├── inverter/__init__.py (factory)
  └── Basic service call validation
       │
Phase 3: Optimizer Core
  ├── optimizer.py (strategy engine using InverterInterface)
  ├── coordinator.py (consumption history)
  ├── sensor.py (decision + forecast sensors)
  └── switch.py / number.py (controls)
       │
Phase 4: Frontend Panel
  ├── frontend/ (LitElement panel)
  ├── websocket.py (custom WS commands)
  ├── Panel registration in __init__.py
  └── Onboarding wizard views
       │
Phase 5: Polish + HACS
  ├── hacs.json, brand assets
  ├── Runtime dashboard view
  ├── Translations (de, en)
  └── Documentation
```

**Rationale for this order:**
1. Foundation first because everything depends on integration skeleton and the inverter ABC contract.
2. Inverter layer second because the optimizer cannot be tested without a way to read battery state and issue commands.
3. Optimizer core third because it is the product's core value and can be validated with HA entities before any panel exists.
4. Frontend panel fourth because it depends on working WebSocket endpoints and a functional optimizer to display meaningful data.
5. HACS polish last because distribution concerns should not drive architecture.

## Scalability Considerations

| Concern | Single Inverter | Multiple Inverter Types | Multiple Instances |
|---------|----------------|------------------------|-------------------|
| Inverter interface | One concrete class | Factory pattern selects class | One interface per config entry |
| Config storage | config_entry.options | options includes `inverter_type` key | Separate config entries |
| Panel | Single optimizer view | Inverter-specific settings panels | Panel shows all instances |
| Service calls | Direct to one device | device_id in config routes calls | Each optimizer has own device_id |

## HACS Repository Structure

```
repository-root/
├── hacs.json                           # HACS metadata
├── custom_components/
│   └── eeg_optimizer/
│       ├── manifest.json
│       ├── __init__.py
│       ├── config_flow.py
│       ├── const.py
│       ├── optimizer.py
│       ├── coordinator.py
│       ├── sensor.py
│       ├── switch.py
│       ├── number.py
│       ├── websocket.py
│       ├── strings.json
│       ├── translations/
│       │   ├── de.json
│       │   └── en.json
│       ├── inverter/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   └── huawei.py
│       └── frontend/
│           └── eeg-optimizer-panel.js  # Bundled from source
├── frontend-src/                       # Source (not distributed)
│   ├── package.json
│   ├── rollup.config.js
│   └── src/
│       ├── eeg-optimizer-panel.js
│       └── views/
│           ├── onboarding-welcome.js
│           ├── onboarding-inverter.js
│           ├── onboarding-sensors.js
│           ├── onboarding-forecast.js
│           ├── onboarding-eeg.js
│           ├── onboarding-summary.js
│           └── dashboard.js
└── tests/
```

## Sources

- [Creating Custom Panels - HA Developer Docs](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/) (HIGH confidence)
- [Extending the WebSocket API - HA Developer Docs](https://developers.home-assistant.io/docs/frontend/extending/websocket-api/) (HIGH confidence)
- [Integration File Structure - HA Developer Docs](https://developers.home-assistant.io/docs/creating_integration_file_structure/) (HIGH confidence)
- [How to Add a Sidebar Panel - HA Community](https://community.home-assistant.io/t/how-to-add-a-sidebar-panel-to-a-home-assistant-integration/981585) (MEDIUM confidence)
- [Huawei Solar Integration](https://github.com/wlcrs/huawei_solar) (HIGH confidence)
- [Huawei Solar Force Charge/Discharge Wiki](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery) (HIGH confidence)
- [HSEM - Huawei Solar Energy Management](https://github.com/woopstar/hsem) (MEDIUM confidence, reference architecture)
- [HACS Integration Publishing](https://hacs.xyz/docs/publish/integration/) (HIGH confidence)
- [StaticPathConfig deprecation](https://github.com/hacs/integration/issues/3828) (HIGH confidence, `async_register_static_paths` is the current API)
