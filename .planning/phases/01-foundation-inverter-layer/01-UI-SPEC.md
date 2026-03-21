---
phase: 1
slug: foundation-inverter-layer
status: approved
reviewed_at: 2026-03-21
shadcn_initialized: false
preset: none
created: 2026-03-21
---

# Phase 1 -- UI Design Contract

> Visual and interaction contract for the config flow UI in Home Assistant. Phase 1 has no custom frontend -- the only user-facing UI is HA's native config flow rendered by the HA frontend framework.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none -- Home Assistant native config flow |
| Preset | not applicable |
| Component library | HA built-in form components (selectors, data-entry-flow) |
| Icon library | mdi (Material Design Icons, HA standard) |
| Font | HA theme default (Roboto) -- no override |

**Rationale:** Phase 1 creates a Home Assistant custom integration. All UI is rendered by HA's frontend framework through `data_entry_flow`. There is no custom HTML, CSS, or JavaScript. Visual styling (typography, spacing, color) is entirely controlled by the user's HA theme. The design contract for this phase focuses on **config flow structure, copywriting, validation behavior, and interaction flow**.

---

## Spacing Scale

Not applicable for Phase 1. HA's config flow renderer controls all spacing. No custom CSS or layout code is written.

Exceptions: none

---

## Typography

Not applicable for Phase 1. HA's frontend renders all text using theme typography. The contract below specifies the **text content**, not the styling.

---

## Color

Not applicable for Phase 1. HA's theme controls all colors. The integration uses HA's standard error/success styling for validation feedback.

| Role | Value | Usage |
|------|-------|-------|
| Error text | HA theme `--error-color` | Config flow validation errors |
| Success | HA theme default | Successful setup completion |

Accent reserved for: not applicable (no custom UI elements)

---

## Config Flow Interaction Contract

This is the primary UI contract for Phase 1. The config flow has 2 steps rendered by HA's native form system.

### Step 1: Wechselrichter-Typ (Inverter Type Selection)

| Property | Value |
|----------|-------|
| Step ID | `user` |
| Title | Wechselrichter-Typ |
| Description | Waehle den Wechselrichter-Typ fuer die Batteriesteuerung. |
| Input | Single dropdown (SelectSelector, DROPDOWN mode) |
| Options | Huawei SUN2000 (value: `huawei_sun2000`) |
| Validation | Hard block if prerequisite HA integration not installed and loaded |

**Validation behavior:**
- On submit, check `hass.config_entries.async_entries("huawei_solar")` for a loaded entry
- If no loaded entry found: show error `prerequisite_not_installed` on the form (NOT a separate error page)
- User stays on Step 1 until prerequisite is resolved
- No automatic retry -- user must click submit again after installing the prerequisite

### Step 2: Sensor-Zuordnung (Sensor Mapping)

| Property | Value |
|----------|-------|
| Step ID | `sensors` |
| Title | Sensor-Zuordnung |
| Description | Ordne die Sensoren fuer SOC, Kapazitaet und PV-Leistung zu. |
| Inputs | 3 entity pickers + 1 device picker (see below) |

**Fields in order:**

| # | Field | Selector | Filter | Required |
|---|-------|----------|--------|----------|
| 1 | Batterie-Ladezustand (SOC) | EntitySelector | domain=sensor, device_class=battery | Yes |
| 2 | Batterie-Kapazitaet | EntitySelector | domain=sensor, device_class=energy | Yes |
| 3 | PV-Leistung | EntitySelector | domain=sensor, device_class=power | Yes |
| 4 | Huawei Batterie-Geraet | DeviceSelector | integration=huawei_solar | Yes |

**Validation behavior:**
- All 4 fields are required -- HA form blocks submit if any are empty
- Entity selectors show filtered dropdowns with autocomplete
- DeviceSelector shows only devices from the `huawei_solar` integration
- No cross-field validation needed in Phase 1
- On successful submit: config entry is created, integration loads

### Completion

| Property | Value |
|----------|-------|
| Success behavior | HA shows standard "Success" dialog, integration appears in Settings > Integrations |
| No redirect | Config flow ends normally (no custom success page) |

---

## Copywriting Contract

All copy is in German (primary) with English fallback. Source: `strings.json` and `translations/`.

### strings.json Structure

| Element | German Copy |
|---------|-------------|
| Step 1 title | Wechselrichter-Typ |
| Step 1 description | Waehle den Wechselrichter-Typ fuer die Batteriesteuerung. |
| Step 1 field: inverter_type | Wechselrichter |
| Step 2 title | Sensor-Zuordnung |
| Step 2 description | Ordne die Sensoren fuer SOC, Kapazitaet und PV-Leistung zu. |
| Step 2 field: battery_soc_sensor | Batterie-Ladezustand (SOC) |
| Step 2 field: battery_capacity_sensor | Batterie-Kapazitaet |
| Step 2 field: pv_power_sensor | PV-Leistung |
| Step 2 field: huawei_device_id | Huawei Batterie-Geraet |
| Error: prerequisite_not_installed | Die {integration_name}-Integration muss installiert und geladen sein. |
| Error: unknown | Unerwarteter Fehler. Bitte versuche es erneut. |
| Abort: already_configured | EEG Energy Optimizer ist bereits eingerichtet. |

### translations/en.json Structure

| Element | English Copy |
|---------|-------------|
| Step 1 title | Inverter Type |
| Step 1 description | Select the inverter type for battery control. |
| Step 1 field: inverter_type | Inverter |
| Step 2 title | Sensor Mapping |
| Step 2 description | Map the sensors for SOC, capacity, and PV power. |
| Step 2 field: battery_soc_sensor | Battery State of Charge (SOC) |
| Step 2 field: battery_capacity_sensor | Battery Capacity |
| Step 2 field: pv_power_sensor | PV Power |
| Step 2 field: huawei_device_id | Huawei Battery Device |
| Error: prerequisite_not_installed | The {integration_name} integration must be installed and loaded. |
| Error: unknown | Unexpected error. Please try again. |
| Abort: already_configured | EEG Energy Optimizer is already configured. |

### Empty State

| Context | What the User Sees |
|---------|-------------------|
| Integration not yet set up | Standard HA "Add Integration" flow -- no custom empty state needed |
| Huawei Solar not installed | Error on Step 1: "Die Huawei Solar-Integration muss installiert und geladen sein." User action: install Huawei Solar integration first, then retry |
| No matching sensors found | Entity picker shows empty filtered list. User action: verify Huawei Solar integration is configured with correct device classes |

### Destructive Actions

None in Phase 1. Config entry deletion uses HA's standard "Delete integration" confirmation dialog (built-in, no custom copy needed).

---

## Integration Identity

| Property | Value | Source |
|----------|-------|--------|
| Domain | eeg_energy_optimizer | CONTEXT.md locked decision |
| Display name | EEG Energy Optimizer | CONTEXT.md locked decision |
| Icon (HACS) | peakshare.app EWA-Logo | CONTEXT.md locked decision |
| Icon file | icon.png + logo.png in integration directory | RESEARCH.md recommendation |
| mdi icon (HA) | mdi:solar-power | Sensible default for energy optimization |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| Not applicable | No frontend dependencies | No shadcn, no npm, no third-party UI code |

Phase 1 has zero frontend JavaScript dependencies. All UI is rendered by HA's built-in data-entry-flow system.

---

## Component Inventory

Phase 1 uses only HA built-in selectors (no custom components):

| HA Selector | Used In | Purpose |
|-------------|---------|---------|
| SelectSelector (DROPDOWN) | Step 1 | Inverter type selection |
| EntitySelector (domain=sensor, device_class=battery) | Step 2 | SOC sensor picker |
| EntitySelector (domain=sensor, device_class=energy) | Step 2 | Capacity sensor picker |
| EntitySelector (domain=sensor, device_class=power) | Step 2 | PV power sensor picker |
| DeviceSelector (integration=huawei_solar) | Step 2 | Huawei device picker |

---

## Interaction State Machine

```
[Start] --> Step 1: Wechselrichter-Typ
  |
  |--(submit with valid prerequisite)--> Step 2: Sensor-Zuordnung
  |                                        |
  |                                        |--(all fields filled)--> [Success: Entry Created]
  |                                        |
  |                                        |--(missing fields)--> Step 2 (HA blocks submit)
  |
  |--(prerequisite missing)--> Step 1 (error: prerequisite_not_installed)
  |
  |--(already configured)--> [Abort: already_configured]
```

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS (deferred -- no custom visuals)
- [ ] Dimension 3 Color: PASS (deferred -- HA theme controlled)
- [ ] Dimension 4 Typography: PASS (deferred -- HA theme controlled)
- [ ] Dimension 5 Spacing: PASS (deferred -- HA theme controlled)
- [ ] Dimension 6 Registry Safety: PASS (no frontend dependencies)

**Approval:** pending
