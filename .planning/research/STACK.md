# Technology Stack

**Project:** EEG Energy Optimizer
**Researched:** 2026-03-20

## Recommended Stack

### Backend: Home Assistant Custom Integration (Python)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.12+ | Integration runtime | HA 2026.x requirement | HIGH |
| homeassistant core | 2026.3+ | Framework, entity platform, config flow | Target platform | HIGH |
| asyncio | stdlib | Async I/O for all sensor reads, service calls | HA mandates async throughout | HIGH |
| voluptuous | (bundled w/ HA) | Config validation, WebSocket message schemas | Standard HA pattern for all config validation | HIGH |
| pytest | 8.x | Unit/integration testing | Standard Python testing | HIGH |
| pytest-homeassistant-custom-component | 0.13.x | HA test fixtures (MockConfigEntry, hass fixture) | Extracts HA core test utilities daily; v0.13.318 supports HA 2026.3.2 | HIGH |
| hassfest | (HA core action) | Manifest & translation validation | Required for HACS publication, catches errors early | HIGH |
| ruff | 0.9+ | Linting + formatting | Replaces flake8+black+isort; HA core uses it | MEDIUM |

### Frontend: Custom Panel (JavaScript/Lit)

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Lit | 3.3.x | Web component framework | HA frontend uses Lit 3.3.2 natively; maximum compatibility with HA theming and styles | HIGH |
| lit-html | 3.3.x | Template rendering | Comes with Lit 3; same version as HA frontend | HIGH |
| TypeScript | 5.9+ | Type safety for panel code | HA frontend uses TS 5.9.3; catches bugs in complex wizard logic | MEDIUM |
| Rollup | 4.x | Bundle panel JS into single file | HA frontend uses Rollup; produces clean ES modules. Simpler than Webpack for a single-panel output | MEDIUM |
| home-assistant-js-websocket | 9.6.x | WebSocket communication with HA backend | Official HA library for frontend-to-backend communication. Provides typed `callWS()`, `subscribeEntities()` | HIGH |
| @mdi/js | 7.4+ | Material Design Icons | HA uses MDI icons throughout; consistent with sidebar | HIGH |

### Distribution

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| HACS | 2.x | Community distribution channel | De facto standard for HA custom integrations; 2.0 added proper update notifications | HIGH |
| GitHub Releases | - | Versioned distribution | HACS shows last 5 releases; enables clean version selection | HIGH |
| hacs.json | - | HACS metadata | Required for HACS repository validation | HIGH |

### Inverter Interfaces

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| huawei_solar (HACS) | 1.6.0 | Huawei SUN2000 battery control | Provides `forcible_charge`, `forcible_discharge`, `forcible_charge_soc`, `forcible_discharge_soc`, `stop_forcible_charge` services via HA. Modbus-based, elevated permissions needed | HIGH |
| Fronius Gen24 (future) | - | Fronius battery control via HTTP Digest Auth | Already implemented in existing integration; second inverter type | HIGH |

### PV Forecast Sources

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Solcast Solar (HACS) | latest | Paid PV forecast — remaining today, tomorrow, 7-day | Entities: forecast today/tomorrow/remaining today. Attributes contain 30-min interval data. Most accurate for DACH region | HIGH |
| Forecast.Solar (HA core) | built-in | Free PV forecast alternative | Entities: `sensor.energy_production_today`, `_remaining_today`, `_tomorrow`, `_now` (power). No API key needed for basic use | HIGH |

## Architecture-Relevant Stack Details

### Panel Registration from Integration

The integration registers its sidebar panel programmatically from `__init__.py` — no `configuration.yaml` editing required. This is the HACS pattern (same as HACS itself).

```python
# __init__.py — panel registration pattern
from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig

async def async_setup_entry(hass, entry):
    # Serve frontend files
    panel_path = os.path.join(os.path.dirname(__file__), "frontend")
    panel_url = f"/{DOMAIN}_panel"
    await hass.http.async_register_static_paths([
        StaticPathConfig(panel_url, panel_path, cache_headers=False)
    ])

    # Register sidebar panel
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

Panel removal on unload:
```python
from homeassistant.components.frontend import async_remove_panel
async_remove_panel(hass, DOMAIN)
```

### WebSocket API for Panel Communication

Backend registers WebSocket commands; frontend calls them via `hass.callWS()`:

```python
# Backend (Python)
@websocket_api.websocket_command({"type": f"{DOMAIN}/get_config"})
@websocket_api.async_response
async def ws_get_config(hass, connection, msg):
    connection.send_result(msg["id"], {"status": "ok", "config": {...}})
```

```javascript
// Frontend (JS/Lit)
const result = await this.hass.callWS({ type: "eeg_optimizer/get_config" });
```

### Huawei SUN2000 Battery Control Services

```python
# Service calls for battery control
await hass.services.async_call("huawei_solar", "forcible_charge_soc", {
    "device_id": device_id,
    "target_soc": 100,
})
await hass.services.async_call("huawei_solar", "forcible_discharge_soc", {
    "device_id": device_id,
    "target_soc": 20,
})
await hass.services.async_call("huawei_solar", "stop_forcible_charge", {
    "device_id": device_id,
})
```

Note: Requires "Elevate permissions" during Huawei Solar integration setup.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Frontend framework | Lit 3 (native) | React | React requires `embed_iframe=True`, loses access to HA theming, adds bundle bloat. HA itself uses Lit — stay aligned |
| Frontend framework | Lit 3 (native) | Vue | Same iframe isolation problem as React. No HA ecosystem alignment |
| Bundler | Rollup | Vite | Vite is overkill for a single panel file; Rollup produces cleaner output and matches HA frontend toolchain |
| Bundler | Rollup | Webpack | Heavier config, larger output. HA moved away from Webpack toward Rollup |
| Bundler | Rollup | No bundler (CDN imports) | CDN imports (unpkg) work for prototyping but fail offline and are fragile for production. HA docs example uses CDN but real integrations bundle |
| Testing | pytest-homeassistant-custom-component | Manual testing only | The existing integration has zero tests; the new one should not repeat this. Automated tests catch regressions before HA updates break things |
| Linter | ruff | flake8 + black + isort | ruff is a single tool replacing all three, 10-100x faster, HA core uses it |
| Inverter (v1) | Huawei via HA services | Direct Modbus | HA services abstract the protocol; no need to implement Modbus ourselves. Huawei Solar integration already handles it |
| PV Forecast | Solcast + Forecast.Solar (user choice) | Open-Meteo Solar | Less established in HA ecosystem, fewer users, no native HA integration |

## Project File Structure

```
eeg_energy_optimizer/                    # Repo root (eventually own repo)
+-- custom_components/
|   +-- eeg_energy_optimizer/
|       +-- __init__.py                  # Entry, panel registration, platform forwarding
|       +-- manifest.json                # HA + HACS metadata
|       +-- config_flow.py               # Minimal config flow (panel handles wizard)
|       +-- const.py                     # Constants, enums, defaults
|       +-- optimizer.py                 # Decision engine
|       +-- sensor.py                    # Sensor platform
|       +-- switch.py                    # Enable/disable switch
|       +-- inverter/
|       |   +-- __init__.py              # Abstract inverter interface
|       |   +-- huawei.py                # Huawei SUN2000 implementation
|       |   +-- fronius.py               # Fronius Gen24 (future)
|       +-- forecast/
|       |   +-- __init__.py              # Abstract forecast interface
|       |   +-- solcast.py               # Solcast adapter
|       |   +-- forecast_solar.py        # Forecast.Solar adapter
|       +-- frontend/
|       |   +-- eeg-optimizer-panel.js   # Built panel (Rollup output)
|       +-- translations/
|       |   +-- de.json
|       |   +-- en.json
|       +-- strings.json
+-- frontend/                            # Panel source (not shipped)
|   +-- src/
|   |   +-- eeg-optimizer-panel.ts       # Main panel entry
|   |   +-- views/
|   |   |   +-- wizard.ts               # Onboarding wizard
|   |   |   +-- dashboard.ts            # Status dashboard
|   |   +-- components/
|   |       +-- sensor-picker.ts         # Entity selector component
|   |       +-- prerequisite-check.ts    # Dependency checker
|   +-- rollup.config.js
|   +-- tsconfig.json
|   +-- package.json
+-- tests/
|   +-- conftest.py
|   +-- test_optimizer.py
|   +-- test_config_flow.py
|   +-- test_inverter_huawei.py
|   +-- test_forecast_solcast.py
+-- hacs.json
+-- README.md
+-- pyproject.toml                       # Python project config (ruff, pytest)
```

## Installation Commands

### Python (Development)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install HA core for development (pins to your target version)
pip install homeassistant==2026.3.2

# Install test dependencies
pip install pytest pytest-homeassistant-custom-component pytest-asyncio pytest-cov

# Install linter
pip install ruff
```

### Frontend (Development)

```bash
cd frontend/

# Install dependencies
npm install lit@3.3.2 home-assistant-js-websocket@9.6.0 @mdi/js@7.4.47

# Install dev dependencies
npm install -D typescript@5.9.3 rollup@4.x @rollup/plugin-typescript @rollup/plugin-node-resolve @rollup/plugin-terser tslib
```

### pyproject.toml

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Sources

- [HA Developer Docs: Creating Custom Panels](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/) (HIGH confidence)
- [HA Frontend package.json (dev branch)](https://github.com/home-assistant/frontend/blob/dev/package.json) — Lit 3.3.2, TS 5.9.3 (HIGH confidence)
- [HACS Publication Requirements](https://hacs.xyz/docs/publish/integration/) (HIGH confidence)
- [HACS __init__.py panel registration pattern](https://github.com/hacs/integration/blob/main/custom_components/hacs/__init__.py) (HIGH confidence)
- [Community guide: Adding sidebar panel to integration](https://community.home-assistant.io/t/how-to-add-a-sidebar-panel-to-a-home-assistant-integration/981585) (MEDIUM confidence)
- [Huawei Solar integration](https://github.com/wlcrs/huawei_solar) — v1.6.0, battery control services (HIGH confidence)
- [Huawei Solar Wiki: Force charge/discharge](https://github.com/wlcrs/huawei_solar/wiki/Force-charge-discharge-battery) (HIGH confidence)
- [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component) — v0.13.318 (HIGH confidence)
- [Forecast.Solar integration docs](https://www.home-assistant.io/integrations/forecast_solar/) (HIGH confidence)
- [Solcast Solar HA integration](https://github.com/BJReplay/ha-solcast-solar) (HIGH confidence)
