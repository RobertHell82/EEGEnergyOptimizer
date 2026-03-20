# Feature Landscape

**Domain:** EEG/Grid-friendly battery optimization for Home Assistant
**Researched:** 2026-03-20

## Table Stakes

Features users expect from any battery optimization integration. Missing = users pick a competitor or don't trust the tool.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PV forecast-driven charge/discharge scheduling | Every competitor (EMHASS, Predbat, PowerSync, PV Opt) does this. Without it, users just use inverter defaults. | Med | Use Solcast as primary, Forecast.Solar as free fallback. Both already have HA integrations. |
| Morning feed-in priority (delay battery charging) | Core EEG value prop. Austrian EEG members need to feed during 6-9am when community consumption is high but PV is just starting. Mornings are when EEG feed-in earns the most. | Med | Guard-delay concept from existing integration is validated. Make the delay window configurable (not just "hours after sunrise" but also absolute time windows). |
| Evening battery discharge to grid | Second half of the EEG value prop. Discharge stored PV into the grid during 17-22h evening demand peak. Already implemented in reference integration. | Med | Must respect overnight consumption reserve (dynamic min-SOC). Reference integration's logic is mature. |
| Dynamic min-SOC calculation | Users will not discharge their battery to 0% overnight. System must calculate how much SOC is needed to cover consumption until sunrise + safety buffer. Without this, users disable discharge entirely. | Med | Formula: base min SOC + (overnight consumption forecast x safety buffer %). Reference integration has this. |
| Next-day surplus check before discharge | Discharging the battery makes no sense if tomorrow is cloudy and PV won't refill it. Every user asks this question. | Low | Simple: if PV forecast tomorrow < total demand tomorrow, don't discharge. Already in reference integration. |
| Configurable EEG time windows | EEG demand patterns vary by community. Some need 6-9 + 17-22, others 5-8 + 18-21. Hardcoded times are a dealbreaker. | Low | Two configurable time windows (morning + evening). Default to typical Austrian EEG pattern. |
| SOC-based safety guards | Battery must never be drained below safe levels. Critical guards (SOC < 10%) must always override optimization. Users need to trust the system won't damage their battery. | Low | Two-tier: KRITISCH (always active, non-negotiable) and HOCH (deferrable during EEG priority windows). Proven in reference integration. |
| Sensor entities for dashboard integration | Users want to see what the optimizer is doing and why. Decision sensor with strategy, reasoning, and inputs as attributes is expected by HA power users. | Low | Decision sensor + strategy sensor + current mode. Attributes expose full decision context for dashboards. |
| Dry-run / read-only mode | Users need to observe the optimizer's decisions before trusting it with real hardware control. Every serious optimization tool offers this (Predbat, PV Opt, EMHASS all do). | Low | Mode "Aus" calculates but doesn't execute. Already proven in reference integration. |
| HACS distribution | The standard way to install custom integrations. Without HACS support, adoption is negligible. Predbat, EMHASS, PowerSync, PV Opt, Solar Optimizer all distribute via HACS. | Low | Proper manifest.json, hacs.json, repository structure. Straightforward. |
| Human-readable decision reasoning | Users need to understand WHY the optimizer made a decision. "Charging battery because PV forecast exceeds demand by 1.5x" not just "charging=true". Predbat and the reference integration both do this well. | Low | German-language reasoning strings. Each decision includes a multi-line explanation. |

## Differentiators

Features that set this integration apart from EMHASS/Predbat/PowerSync. Not expected, but create competitive advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| EEG-first optimization philosophy | No existing HA integration optimizes specifically for energy community feed-in patterns. EMHASS/Predbat/PowerSync optimize for price (buy low, sell high). EEG communities don't use spot prices -- they use time-of-use patterns where community demand creates value. This is an unserved niche. | Low | This is not a feature to build but a design lens. Every decision should ask "does this maximize EEG value?" not "does this minimize cost?". Translates to: feed-in priority during community demand windows, charge during midday glut, discharge during evening demand. |
| Onboarding Panel (guided setup wizard) | EMHASS setup is notoriously complex (YAML config, docker, many parameters). Predbat requires AppDaemon + complex apps.yaml. PV Opt needs MQTT setup. A dedicated HA sidebar panel with step-by-step setup, prerequisite checks, and sensor mapping would dramatically lower the barrier to entry. | High | LitElement/JS custom panel. Checks: is Solcast/Forecast.Solar installed? Is Huawei Solar integration set up? Guides through sensor selection. This is the single biggest UX differentiator but also the highest complexity. |
| Abstract inverter interface | Predbat supports 15+ inverters but through per-inverter config templates (complex). PowerSync supports 5 brands. A clean Python ABC that maps to HA service calls (Huawei via `huawei_solar` services, Fronius via Modbus/API) makes adding new inverters a simple class implementation. | Med | Start with Huawei (simplest: HA services). Fronius second (HTTP Digest API from reference integration). SMA/Solis/GivEnergy as community contributions. The interface is: `set_charge_limit()`, `set_discharge()`, `set_grid_export()`, `get_soc()`, `get_capacity()`. |
| Zero-config consumption forecasting | Predbat requires historical data setup. EMHASS needs manual load configuration. This integration should auto-detect consumption patterns from HA's recorder (like the reference integration's coordinator.py does with rolling 4-zone weekday splits) without user configuration. | Med | Use HA recorder's long-term statistics. 8-week rolling window, split by day type (weekday/Friday/Saturday/Sunday). Already proven in reference integration's coordinator. |
| Surplus factor strategy selection | Instead of simple "charge/discharge" modes, automatically select strategy based on PV forecast vs. demand ratio: UEBERSCHUSS (>1.25x), BALANCIERT (0.8-1.25x), ENGPASS (<0.8x), NACHT. Gives users a clear mental model of what the system is doing. | Low | Already proven in reference integration. The ratio-based approach is intuitive and maps directly to user expectations. |
| Inverter throttle detection | When feed-in is at the grid export limit, the inverter throttles PV production. The system can't see "true" available PV. Speculatively assuming +2kW above reported PV breaks the deadlock and enables battery/load activation. No competitor does this. | Low | Simple heuristic: if feed-in >= limit - 100W, assume PV is throttled and add 2kW to available power calculation. Already validated in reference integration. |
| Nightly discharge preview (daytime) | During the day, show what tonight's discharge plan will be. Users checking their dashboard at 14:00 can see "Tonight: discharge planned, min-SOC 35%, PV tomorrow 28kWh >= demand 22kWh" or "Tonight: no discharge (PV tomorrow only covers 60% of demand)". No competitor shows this. | Low | Already implemented in reference integration. Pure calculation, no side effects. |
| Dual forecast source support | Support both Solcast (paid, more accurate) and Forecast.Solar (free, good enough for many users). User picks during setup. Predbat requires Solcast. EMHASS has its own forecasting. Offering both widens the user base. | Low | Both already have HA integrations. Just read different sensor entities based on config. |

## Anti-Features

Features to explicitly NOT build. Scope discipline is how this integration stays focused and maintainable.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Spot price / tariff optimization | EMHASS, Predbat, and PowerSync already solve this well. EEG communities don't use spot pricing for internal allocation. Adding price optimization would bloat the integration and compete where others are stronger. | Stay focused on EEG time-window optimization. Users who need price optimization should use EMHASS or Predbat alongside this. |
| EV charging optimization | Complex domain with its own integrations (evcc, go-eCharger, Tesla). Mixing battery and EV optimization creates coupling that's hard to maintain. | Expose enough sensor data that EV integrations can make informed decisions. Don't control the wallbox. |
| Heizstab / hot water control | The reference integration controls a heating rod (OhmPilot). This adds complexity and is site-specific. Not every user has an OhmPilot or heating rod. | Out of scope for v1. If demand emerges, add as optional module later. Keep core focused on battery + grid. |
| Linear programming solver | EMHASS and HAEO use LP/CVXPY/HiGHS for multi-variable optimization. This is academically elegant but operationally complex to configure and debug. Users can't understand why the LP solver made a decision. | Use rule-based strategies (surplus factor + guard system). Deterministic, explainable, debuggable. The reference integration proves this approach works in practice. |
| Multi-location support | Supporting multiple HA instances or locations adds massive complexity for a niche use case. | Single installation focus. Users with multiple locations run separate instances. |
| Real-time EEG demand API | No standardized API exists for Austrian Energiegemeinschaften. Building one would be a separate project. | Use configurable time windows as a pragmatic proxy for community demand patterns. |
| Grid frequency / ancillary services | Beyond residential scope. Regulatory requirements, certification needed. | Completely out of scope. |
| Machine learning / AI prediction | Adds dependency complexity (ML libraries), training data requirements, and black-box decisions. Rule-based forecasting with recorder data is sufficient and transparent. | Use simple rolling averages from HA recorder. Proven, lightweight, explainable. |

## Feature Dependencies

```
Solcast/Forecast.Solar integration (external) → PV forecast sensors → Surplus factor calculation → Strategy selection
                                                                    → Next-day surplus check → Evening discharge decision

HA Recorder (external) → Consumption history → Consumption forecast → Dynamic min-SOC calculation
                                             → Energy demand today → Surplus factor calculation

Inverter HA integration (external) → Abstract inverter interface → Charge/discharge execution
                                                                  → SOC reading → Safety guards

Safety guards → Morning feed-in priority (guard delay suppresses HOCH guards)
             → Evening discharge (SOC guards)

Configurable EEG time windows → Morning feed-in priority timing
                              → Evening discharge timing

Onboarding Panel → Prerequisite checks (Solcast? Inverter integration?)
                 → Sensor entity mapping
                 → EEG time window configuration
```

Simplified dependency chain:
```
1. Abstract inverter interface (foundation - everything needs to control the inverter)
2. PV forecast integration (needed for all strategy decisions)
3. Consumption forecasting (needed for demand calculation)
4. Strategy engine (surplus factor + guards + EEG time windows)
5. Decision execution (writes to inverter via abstract interface)
6. Sensor entities + dashboard (observability layer)
7. Onboarding Panel (UX layer, can be built last)
```

## MVP Recommendation

**Prioritize (Phase 1 - Core):**
1. Abstract inverter interface with Huawei implementation
2. Solcast PV forecast reading
3. EEG time windows (morning feed-in priority + evening discharge)
4. Surplus factor strategy selection (UEBERSCHUSS/BALANCIERT/ENGPASS/NACHT)
5. Safety guards (KRITISCH always active, HOCH with guard delay)
6. Dynamic min-SOC for discharge
7. Decision sensor with reasoning
8. Dry-run mode
9. HACS-compatible structure

**Phase 2 - Polish:**
1. Forecast.Solar as alternative forecast source
2. Consumption forecasting from recorder (auto-detect patterns)
3. Next-day surplus check
4. Nightly discharge preview
5. Inverter throttle detection

**Phase 3 - UX:**
1. Onboarding Panel (sidebar wizard)
2. Prerequisite checks
3. Sensor mapping UI

**Defer indefinitely:**
- Fronius inverter support: comes as second inverter type after Huawei is validated (per PROJECT.md decision)
- Heizstab control: explicitly out of scope
- EV charging: explicitly out of scope
- Price optimization: different problem domain

## Competitive Landscape Summary

| Integration | Focus | Inverters | Forecast | EEG Support | Setup UX | Confidence |
|-------------|-------|-----------|----------|-------------|----------|------------|
| **This project** | EEG time-window optimization | Huawei (v1), abstract interface | Solcast + Forecast.Solar | Primary focus | Onboarding Panel (planned) | N/A |
| EMHASS | Price-based LP optimization | Inverter-agnostic (HA automations) | Built-in + external | None | Complex YAML/Docker | HIGH |
| Predbat | Price-based prediction + scheduling | 15+ brands via AppDaemon | Solcast required | None | Complex apps.yaml + AppDaemon | HIGH |
| PowerSync | Price-based LP with spike detection | 5 brands (Tesla, FoxESS, etc.) | Built-in | None | Standard HA config flow | HIGH |
| PV Opt | Tariff optimization for Solis | Solis (primary), others via automation | Solcast required | None | MQTT + config | HIGH |
| Solar Optimizer | PV excess load switching | N/A (controls loads, not battery) | N/A | None | HACS + config flow | HIGH |
| Huawei Battery Optimizations | Self-consumption + TOU for Huawei | Huawei only | Solcast | None | YAML package | MEDIUM |
| HAEO | Price-based LP (pure optimizer) | None (outputs only, user wires execution) | None (external input) | None | Configuration | MEDIUM |

**Key insight:** No existing integration optimizes for EEG / energy community patterns. Every competitor focuses on electricity price arbitrage. This is an uncontested niche in the DACH region where Energiegemeinschaften are rapidly growing (Austrian EAG law, German Solarspitzengesetz 2025).

## Sources

- [EMHASS Documentation](https://emhass.readthedocs.io/)
- [Predbat/Batpred GitHub](https://github.com/springfall2008/batpred)
- [PowerSync Documentation](https://bolagnaise.github.io/PowerSync/)
- [PV Opt GitHub](https://github.com/fboundy/pv_opt)
- [HAEO GitHub](https://github.com/hass-energy/haeo)
- [Solar Optimizer GitHub](https://github.com/jmcollin78/solar_optimizer)
- [Huawei Solar Battery Optimizations GitHub](https://github.com/heinoskov/huawei-solar-battery-optimizations)
- [Energiesparhaus.at Forum - Optimiertes Batteriemanagement](https://www.energiesparhaus.at/forum-optimiertes-batteriemanagement-herstelleruebergreifend/82851)
- [Neoom - Intelligente Einspeisung mit CONNECT AI](https://wissen.neoom.com/intelligente-einspeisung-mit-connect-ai)
- [Predbat Inverter Setup](https://springfall2008.github.io/batpred/inverter-setup/)
- [Home Assistant Custom Panels](https://developers.home-assistant.io/docs/frontend/custom-ui/creating-custom-panels/)
