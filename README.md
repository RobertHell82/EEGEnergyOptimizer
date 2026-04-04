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
- **SolaX Gen4+** (via [SolaX Modbus](https://github.com/wills106/homeassistant-solax-modbus) integration)

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

## Funktionsweise

### Verzögerte Ladung (Morgen-Einspeisung)

Die verzögerte Ladung stellt sicher, dass PV-Überschüsse bevorzugt am Morgen in das Netz der Energiegemeinschaft eingespeist werden — also dann, wenn die Gemeinschaft den Strom dringend braucht. Ohne diese Funktion würde die Batterie den PV-Überschuss sofort ab Sonnenaufgang aufladen. Die Einspeisung in die Energiegemeinschaft würde dann erst ab Mittag erfolgen, wenn ohnehin genug Strom vorhanden ist.

**Funktionsweise:** Die Batterieladung wird ab einer Stunde vor Sonnenaufgang blockiert und frühestens um die konfigurierte Endzeit (Standard: 10:00 Uhr) wieder freigegeben. Die Blockierung erfolgt nur, solange die PV-Prognose des aktuellen Tages den Gesamtbedarf übersteigt.

**Der Gesamtbedarf setzt sich zusammen aus:**
- Geschätzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang
- Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)
- Fehlende Energie zum Vollladen der Batterie (basierend auf aktuellem SOC)

Der Stromverbrauch wird anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 4 Wochen).

Reicht die PV-Prognose nicht aus, um den Gesamtbedarf zu decken, wird die Batterie sofort geladen — damit der Haushalt bis zum Abend versorgt ist.

### Abend-Entladung (Nachteinspeisung)

Die Abend-Entladung speist unter Tags gewonnene Energie, die der eigene Haushalt nicht benötigt, um über die Nacht zu kommen, in die Energiegemeinschaft ein. So steht Strom zu einem Zeitpunkt zur Verfügung, an dem ansonsten keine PV-Erzeugung im Netz vorhanden ist.

**Funktionsweise:** Ab der konfigurierten Startzeit (Standard: 20:00 Uhr) wird die Batterie mit einstellbarer Leistung entladen, bis der dynamisch berechnete Ziel-SOC erreicht ist.

**Der Ziel-SOC ergibt sich aus:**
- Konfigurierter Mindest-SOC der Batterie
- Geschätzter Stromverbrauch in der Nacht (Entladestart bis eine Stunde nach Sonnenaufgang)
- Sicherheitspuffer auf den Nachtverbrauch (konfigurierbar, Standard: 25%)

**Die Entladung erfolgt nur, wenn alle Bedingungen erfüllt sind:**
- Aktueller SOC liegt über dem berechneten Ziel-SOC
- Die PV-Prognose für morgen deckt den erwarteten Gesamtbedarf

**Der Gesamtbedarf für morgen setzt sich zusammen aus:**
- Geschätzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang
- Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)
- Benötigte Energie zum Laden der Batterie (von Mindest-SOC auf 100%)

Der Stromverbrauch wird jeweils anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 4 Wochen).

So wird sichergestellt, dass die Batterie am nächsten Tag wieder vollständig über PV geladen werden kann und der Haushalt versorgt ist.

## Requirements

- Home Assistant 2025.1.0 or newer
- A supported inverter integration installed and configured (Huawei Solar or SolaX Modbus)
- A PV forecast integration (Solcast Solar or Forecast.Solar)

## License

MIT
