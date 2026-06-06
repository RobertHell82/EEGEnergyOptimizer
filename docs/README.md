# EEG Energy Optimizer — Dokumentation

Willkommen! Hier findest du alle Anleitungen, um den EEG Energy Optimizer zu installieren und einzurichten — von der HACS-Installation bis zur Wechselrichter-Anbindung.

## 🚀 Installation

Am besten in dieser Reihenfolge:

1. **[HACS auf Home Assistant installieren](installation/hacs.md)** — der Community Store, über den die Integration verteilt wird
2. **[EEG Energy Optimizer über HACS installieren](installation/eeg-integration.md)** — Integration hinzufügen und Einrichtungsassistent starten

## 🔌 Wechselrichter anbinden

Anleitung für deinen Wechselrichter-Typ:

| Wechselrichter | Anleitung |
|---|---|
| **Huawei SUN2000** | [Huawei Solar Integration einrichten](guides/huawei.md) |
| | [Huawei Akkukapazität-Sensor aktivieren](guides/capacity_sensor.md) |
| **Fronius Gen24** | [Fronius Gen24 einrichten](guides/fronius.md) |
| **SolaX Gen4+** | [SolaX Modbus einrichten](guides/solax.md) |
| **SolarEdge StorEdge** | [SolarEdge Modbus Multi einrichten](guides/solaredge.md) |

## ☀️ PV-Prognose einrichten

Eine der beiden Prognose-Quellen wird benötigt:

- **[Solcast Solar einrichten](guides/solcast.md)** (empfohlen — 7-Tage-Prognose)
- **[Forecast.Solar einrichten](guides/forecast_solar.md)** (ohne Registrierung nutzbar)

> [!TIP]
> Alle Einrichtungs-Anleitungen sind auch direkt im Einrichtungsassistenten der Integration verfügbar — einfach auf die „Anleitung"-Buttons im Panel klicken.

## ℹ️ Funktionsweise

Wie Morgen-Einspeisung, Nacht-Entladung und PeakShare funktionieren, ist in der **[Projekt-Übersicht](../README.md)** beschrieben.
