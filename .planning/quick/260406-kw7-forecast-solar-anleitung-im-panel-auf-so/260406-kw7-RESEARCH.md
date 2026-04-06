# Forecast.Solar Anleitung - Research

**Researched:** 2026-04-05
**Domain:** Home Assistant Forecast.Solar integration setup
**Confidence:** HIGH

## Summary

Forecast.Solar is a **native HA Core integration** (no HACS needed). Setup is straightforward: add via Integrations UI, enter PV system parameters (tilt, azimuth, kWp). The main gotcha is the **azimuth convention** which differs between the Forecast.Solar API (0=South) and the HA integration (0=North, 180=South). Free tier is sufficient for most users with 12 requests/hour and 1-hour data resolution.

**Primary recommendation:** Expand the existing 3-line panel guide to a detailed step-by-step with azimuth explanation, multiple-array hint, and entity verification.

## Forecast.Solar Integration Details

### Setup Flow (HA Core native)

1. Einstellungen -> Geraete & Dienste -> Integration hinzufuegen
2. Suche "Forecast.Solar"
3. Configuration dialog asks for:

| Field | Description | Default | Notes |
|-------|-------------|---------|-------|
| **Latitude** | Standort Breitengrad | HA home location | Wird automatisch uebernommen |
| **Longitude** | Standort Laengengrad | HA home location | Wird automatisch uebernommen |
| **Declination (Neigung)** | Winkel der Module zur Horizontalen | — | 0 = flach, 30-35 = typisch DACH-Region, 90 = senkrecht |
| **Azimuth (Ausrichtung)** | Himmelsrichtung der Modulflaeche | — | **0 = Nord, 90 = Ost, 180 = Sued, 270 = West** |
| **Modules Power (kWp)** | Gesamtleistung aller Module | — | In **Watt** eingeben! (z.B. 10000 fuer 10 kWp) |

### Post-Setup Configuration Options

After initial setup, via "Konfigurieren":

| Option | Description | Default |
|--------|-------------|---------|
| **API Key** | Fuer bezahlte Accounts | leer (kostenlos) |
| **Damping Factor (Morgen)** | Daempfung Morgenprognose | 0 |
| **Damping Factor (Abend)** | Daempfung Abendprognose | 0 |
| **Inverter Size** | Begrenzt Prognose auf WR-Maximum | — |

### Entity IDs Created

| Entity ID | Description | Unit | Relevant fuer EEG Optimizer |
|-----------|-------------|------|----------------------------|
| `sensor.energy_production_today` | Geschaetzte Produktion heute | kWh | Nein (Gesamttag) |
| **`sensor.energy_production_today_remaining`** | Verbleibende Produktion heute | kWh | **JA - forecast_remaining_entity** |
| **`sensor.energy_production_tomorrow`** | Geschaetzte Produktion morgen | kWh | **JA - forecast_tomorrow_entity** |
| `sensor.energy_current_hour` | Produktion aktuelle Stunde | kWh | Nein |
| `sensor.energy_next_hour` | Produktion naechste Stunde | kWh | Nein |
| `sensor.power_production_now` | Aktuelle geschaetzte Leistung | W | Nein |
| `sensor.power_highest_peak_time_today` | Zeitpunkt Spitzenleistung heute | — | Nein |
| `sensor.power_highest_peak_time_tomorrow` | Zeitpunkt Spitzenleistung morgen | — | Nein |

**Bei mehreren Instanzen:** Entity IDs bekommen Suffix `_2`, `_3`, etc. (z.B. `sensor.energy_production_today_remaining_2`).

**Wichtig:** Die Entity IDs im Panel-Code matchen bereits:
- `FORECAST_SOLAR_DEFAULTS.forecast_remaining_entity = "sensor.energy_production_today_remaining"`
- `FORECAST_SOLAR_DEFAULTS.forecast_tomorrow_entity = "sensor.energy_production_tomorrow"`

### Multiple PV Arrays (Ost/West-Anlagen)

Forecast.Solar unterstuetzt nur **eine Dachflaeche pro Instanz**. Fuer Ost/West-Anlagen:

1. Integration **zweimal** hinzufuegen (einmal Ost-Seite, einmal West-Seite)
2. Entities bekommen automatisch `_2` Suffix
3. Fuer den EEG Optimizer: Template-Sensor anlegen der beide addiert, ODER:
   - Nur die groessere Seite eintragen (einfacher, aber weniger genau)
4. **Bezahlte Plaene** (Personal Plus ab 28 EUR/Jahr): Multi-Plane in einer Abfrage moeglich

## Azimuth-Konvention (Haupt-Stolperfalle)

**KRITISCH: Die HA-Integration verwendet eine ANDERE Konvention als die Forecast.Solar API!**

| Konvention | Nord | Ost | Sued | West |
|------------|------|-----|------|------|
| **HA Integration (im Setup-Dialog)** | 0 | 90 | **180** | 270 |
| Forecast.Solar API (direkt) | -180/180 | -90 | **0** | 90 |
| Kompass (Geographisch) | 0 | 90 | **180** | 270 |

**Fuer die Anleitung im Panel:** Die HA-Integration nutzt die Kompass-Konvention. Nutzer muessen einfach die Kompass-Richtung ihrer Module eingeben. Typische DACH-Werte:
- Sued-Dach: **180**
- Suedwest: **225**
- Suedost: **135**
- Ost/West-Anlage: **90** und **270** (zwei Instanzen)

## Pricing / API Limits

| Plan | Preis | Aufloesung | Horizont | Planes | Rate Limit |
|------|-------|------------|----------|--------|------------|
| **Public (Free)** | Kostenlos | 1 Stunde | Heute + morgen | 1 | 12 Requests/Stunde |
| Personal | 16 EUR/Jahr | 30 Min | +3 Tage | 1 | Hoeher |
| Personal Plus | 28 EUR/Jahr | 15 Min | +3 Tage | 2 | Hoeher |
| Professional | 70 EUR/Jahr | 15 Min | +6 Tage | 3 | Hoeher |

**Fuer den EEG Optimizer reicht der Free-Plan voellig aus** -- die Integration pollt automatisch und benoetigt nur "heute verbleibend" und "morgen" als Tageswerte.

## Common Pitfalls

### Pitfall 1: kWp in Watt eingeben
**Was passiert:** Nutzer gibt "10" statt "10000" ein, Prognose ist Faktor 1000 zu niedrig.
**Vermeidung:** In der Anleitung explizit "in Watt, NICHT in kWp" hervorheben.

### Pitfall 2: Azimuth falsch
**Was passiert:** Nutzer verwechselt Sued=0 (API) mit Sued=180 (HA).
**Vermeidung:** Klare Tabelle: "Sued-Dach = 180 eingeben".

### Pitfall 3: Neigung (Declination) verwechselt mit Azimuth
**Was passiert:** Nutzer vertauscht die beiden Winkel.
**Vermeidung:** Erklaerung mit Bild/Beschreibung: Neigung = wie steil, Ausrichtung = wohin.

### Pitfall 4: API Rate Limit beim Setup
**Was passiert:** Mehrfaches Hinzufuegen/Entfernen verbraucht Rate-Limit, Setup schlaegt fehl.
**Vermeidung:** Hinweis: Bei Fehler 15 Minuten warten.

### Pitfall 5: Abweichende Entity IDs bei mehreren Instanzen
**Was passiert:** Zweite Forecast.Solar-Instanz erstellt `_2`-Entities, aber im EEG Optimizer stehen die Standard-Entities.
**Vermeidung:** Im Expertenmodus die Entity-Picker verwenden.

## Current Panel State

The existing guide at line 174-182 in `eeg-optimizer-panel.js` is minimal (3 steps). The `FORECAST_SOLAR_DEFAULTS` at line 119-122 correctly map to the standard entity IDs.

**Was fehlt in der aktuellen Anleitung:**
1. Erklaerung Neigung (typisch 30-35 Grad in DACH)
2. Erklaerung Azimuth mit Himmelsrichtung (180 = Sued)
3. Hinweis kWp in Watt eingeben
4. Hinweis Ost/West-Anlagen (zwei Instanzen)
5. Hinweis Free-Tier reicht aus
6. Verifizierung: nach Setup pruefen ob Sensoren Werte liefern

## Sources

### Primary (HIGH confidence)
- [Forecast.Solar HA Integration Docs](https://www.home-assistant.io/integrations/forecast_solar/) - Full setup documentation
- [Forecast.Solar Homepage](https://forecast.solar/) - Pricing tiers verified
- [Forecast.Solar API Docs](https://doc.forecast.solar/api) - Rate limits

### Secondary (MEDIUM confidence)
- [HA Community: Forecast.Solar and Azimuth](https://community.home-assistant.io/t/forecast-solar-and-azimuth/928535) - Azimuth confusion documented
- [GitHub Issue #91225](https://github.com/home-assistant/core/issues/91225) - Rate limiting behavior

### Project Sources (HIGH confidence)
- `eeg-optimizer-panel.js` lines 119-122, 174-182 - Current defaults and guide content
- `forecast_provider.py` - ForecastSolarProvider implementation

## Metadata

**Confidence breakdown:**
- Entity IDs: HIGH - verified against both HA docs and existing code defaults
- Azimuth convention: HIGH - verified via official docs + community confirmation
- Pricing/limits: HIGH - verified on forecast.solar homepage
- Setup flow: HIGH - native HA Core integration, well-documented

**Research date:** 2026-04-05
**Valid until:** 2026-07-05 (stable integration, rarely changes)
