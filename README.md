# EEG Energy Optimizer

HACS-compatible Home Assistant integration for predictive battery management, optimized for energy communities (Energiegemeinschaften / EEG) in the DACH region.

## Features

- **Morning feed-in priority** — blocks battery charging so PV surplus feeds into the EEG grid
- **Evening battery discharge** — discharges battery during peak community demand hours
- **Dynamic Min-SOC** — automatically reserves enough battery for overnight household consumption
- **PV forecast integration** — Solcast Solar and Forecast.Solar support with 7-day outlook
- **Consumption profiling** — learns your hourly usage patterns per weekday from HA recorder data
- **Live dashboard** — sidebar panel with energy flow diagram, charts, manual inverter controls, and activity log
- **Guided setup wizard** — step-by-step onboarding with auto-detection of sensors

## Supported Inverters

- **Huawei SUN2000** (via [Huawei Solar](https://github.com/wlcrs/huawei_solar) integration)

## Installation

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add the repository URL and select "Integration" as the category
5. Click "Add" and then install "EEG Energy Optimizer"
6. Restart Home Assistant

## Configuration

After installation, add the integration via:

**Settings > Devices & Services > Add Integration > EEG Energy Optimizer**

The sidebar panel (`/eeg-optimizer`) will guide you through:
1. Prerequisite checks
2. Inverter type selection + automatic sensor detection
3. Battery & PV sensor mapping
4. Forecast source selection (Solcast / Forecast.Solar)
5. Optimizer settings (morning window, discharge time, min-SOC, safety buffer)
6. Inverter connection test

## Requirements

- Home Assistant 2025.1.0 or newer
- A supported inverter integration installed and configured (e.g. Huawei Solar)
- A PV forecast integration (Solcast Solar or Forecast.Solar)

## License

MIT
