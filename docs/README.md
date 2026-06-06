# EEG Energy Optimizer — Dokumentation

## Installation

1. [HACS auf Home Assistant installieren](installation/hacs.md)
2. [EEG Energy Optimizer über HACS installieren](installation/eeg-integration.md)

## Einrichtungs-Anleitungen

Diese Anleitungen sind identisch auch direkt im Einrichtungsassistenten der Integration verfügbar („Anleitung"-Buttons im Panel).

### Wechselrichter

- [Huawei Solar Integration einrichten](guides/huawei.md)
- [Huawei Akkukapazität-Sensor aktivieren](guides/capacity_sensor.md)
- [Fronius Gen24 einrichten](guides/fronius.md)
- [SolaX Modbus einrichten](guides/solax.md)
- [SolarEdge Modbus Multi einrichten](guides/solaredge.md)

### PV-Prognose

- [Solcast Solar einrichten](guides/solcast.md)
- [Forecast.Solar einrichten](guides/forecast_solar.md)

## Weitere Dokumente

- [Telemetrie-/Reporting-Konzept](reporting-concept.md)

---

## Hinweis für Entwickler: Synchronisation mit dem Panel

Die Dateien in `docs/guides/` und `docs/images/` sind die **Single Source of Truth** für die In-App-Anleitungen des Onboarding-Panels.

- **Bearbeiten:** Immer nur die Markdown-Dateien in `docs/guides/` ändern — niemals die generierten Dateien in `custom_components/eeg_energy_optimizer/frontend/guide/`.
- **Generieren:** Nach Änderungen `python scripts/build_guides.py` ausführen (benötigt `pip install markdown`). Das Script konvertiert die Markdown-Dateien zu HTML-Fragmenten und kopiert die Bilder in den Panel-Ordner.
- **Prüfen:** `python scripts/build_guides.py --check` schlägt fehl, wenn Quelle und generierte Dateien nicht übereinstimmen (läuft auch als GitHub Action bei jedem Push/PR).

Unterstützte Markdown-Konventionen in den Guides:

| Markdown | Darstellung im Panel |
|---|---|
| `# Titel` (genau eine H1) | Dialog-Überschrift |
| `## / ###` | Abschnitts-/Unterüberschriften |
| `> [!WARNING]` Blockquote | Orange Warnbox |
| `> [!NOTE]` Blockquote | Blaue Infobox |
| `> [!CAUTION]` Blockquote | Rote Pflicht-/Fehlerbox |
| `_kursiv_` | Grauer Sekundärtext (Hinweise) |
| `![alt](../images/...)` | Bild (Pfad wird automatisch umgeschrieben) |
| Tabellen, Listen, Links, `code`, `<br>` | wie üblich |
