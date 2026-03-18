# Verbrauchsprognose - Installation & Dokumentation

## Sensoren

Die Integration erstellt **8 Sensoren**:

| Sensor | Zeitraum |
|--------|---------|
| `sensor.verbrauchsprognose_bis_sonnenaufgang` | Jetzt → nächster Sonnenaufgang + 1h |
| `sensor.verbrauchsprognose_morgen` | Morgen 00:00 – 24:00 |
| `sensor.verbrauchsprognose_tag_2` | Übermorgen 00:00 – 24:00 |
| `sensor.verbrauchsprognose_tag_3` | Tag +3 |
| `sensor.verbrauchsprognose_tag_4` | Tag +4 |
| `sensor.verbrauchsprognose_tag_5` | Tag +5 |
| `sensor.verbrauchsprognose_tag_6` | Tag +6 |
| `sensor.verbrauchsprognose_tag_7` | Tag +7 |

Jeder Sensor zeigt den **Netto-Strombedarf in kWh** = was aus Batterie/Netz
kommen muss (Verbrauch ohne Heizstab minus PV-Prognose).

## Berechnungslogik

### Pro Stunde im Prognosezeitraum:

```
1. Ø Verbrauch OHNE Heizstab für diese Tagesstunde
   - Aus recorder Langzeit-Statistiken (stündliche Mittelwerte)
   - Getrennt: Werktag (Mo-Fr) vs. Wochenende (Sa-So)
   - Rollierendes 8-Wochen-Fenster → automatisch saisonbereinigt

2. PV-Prognose für diese Stunde (Solcast detailedHourly)

3. Netto-Bedarf = max(Verbrauch - PV, 0)
```

### Sonnenaufgang-Sensor zusätzlich:

```
+ Tesla-Ladung falls in Grünbach:
  (Ladelimit% - SOC%) × 75 kWh ÷ 0.90 Effizienz
```

### Tages-Sensoren zusätzlich:

```
Autarkiegrad = min(PV, Verbrauch) / Verbrauch × 100%
```

## Installation

### 1. Dateien kopieren

```
config/custom_components/verbrauchsprognose/
  __init__.py
  const.py
  coordinator.py
  manifest.json
  sensor.py
```

### 2. configuration.yaml

Minimal (alle Defaults passen für Grünbach):

```yaml
verbrauchsprognose:
```

Vollständig:

```yaml
verbrauchsprognose:
  consumption_sensor: sensor.solarnet_leistung_verbrauch
  heizstab_sensor: sensor.ohmpilot_leistung
  tesla_tracker: device_tracker.tesla_standort
  tesla_soc_sensor: sensor.tesla_batteriestand
  tesla_limit_sensor: number.tesla_ladelimit
  tesla_capacity_kwh: 75.0
  tesla_efficiency: 0.90
  tesla_home_zone: home
  lookback_weeks: 8
  update_interval_min: 15
  sunrise_offset_h: 1.0
```

### 3. HA neu starten

## Sensor-Attribute

### Sonnenaufgang-Sensor

| Attribut | Beschreibung |
|----------|-------------|
| `gesamt_kwh` | Netto + Tesla |
| `grundverbrauch_kwh` | Brutto ohne Heizstab |
| `pv_produktion_kwh` | PV im Zeitraum |
| `nettoverbrauch_kwh` | Aus Batterie/Netz |
| `tesla_ladung_kwh` | Tesla Energie (0 wenn nicht in Grünbach) |
| `stunden_bis_ziel` | Stunden bis Zielzeit |
| `zielzeit` | Sonnenaufgang + Offset |
| `tesla_in_gruenbach` | true/false |
| `tesla_soc` | Aktueller SOC % |
| `wochentag_typ` | Werktag / Wochenende |
| `stundenprofil` | Stündliche Aufschlüsselung |

### Tages-Sensoren

| Attribut | Beschreibung |
|----------|-------------|
| `datum` | Datum (YYYY-MM-DD) |
| `wochentag` | z.B. "Montag" |
| `wochentag_typ` | Werktag / Wochenende |
| `grundverbrauch_kwh` | Brutto ohne Heizstab |
| `pv_produktion_kwh` | PV-Prognose gesamt |
| `nettoverbrauch_kwh` | Netto aus Batterie/Netz |
| `autarkiegrad` | z.B. "85%" |
| `stundenprofil` | Stündliche Aufschlüsselung |

## Stundenprofil (Beispiel)

```json
{"stunde": "14:00", "tag": "WE", "anteil": 1.0,
 "verbrauch_w": 460, "pv_w": 4200, "netto_w": 0, "netto_kwh": 0.0}
```

- `tag`: WT = Werktag, WE = Wochenende
- `anteil`: 1.0 = volle Stunde, <1.0 = anteilig (erste/letzte)
- `verbrauch_w`: Ø historischer Verbrauch ohne Heizstab
- `pv_w`: Solcast PV-Prognose
- `netto_w`: Was wirklich aus Batterie/Netz kommen muss
