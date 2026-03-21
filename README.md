# EEG Energy Optimizer

HACS-compatible Home Assistant integration for predictive energy management with abstract inverter layer. Optimized for energy communities (Energiegemeinschaften / EEG) in the DACH region.

## Features

- Abstract inverter interface supporting multiple inverter types
- Huawei SUN2000 battery control via HA Huawei Solar integration
- Morning feed-in priority to maximize EEG value
- Evening battery discharge under configurable conditions
- Solcast and Forecast.Solar PV forecast support

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

The setup wizard will guide you through:
1. Selecting your inverter type
2. Mapping battery and PV sensors

## Requirements

- Home Assistant 2025.1.0 or newer
- A supported inverter integration installed and configured (e.g. Huawei Solar)

## License

MIT
