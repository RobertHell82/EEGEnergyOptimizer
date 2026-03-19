# Energieoptimierung – Installation & Dokumentation

## Überblick

Custom Integration für Home Assistant zur prädiktiven Energieoptimierung. Steuert Heizstab (OhmPilot), Batterie-Ladelimit und Netzeinspeisung basierend auf PV-Prognosen, Verbrauchshistorie und Echtzeit-Sensordaten.

## Installation

### 1. Dateien kopieren

```
config/custom_components/energieoptimierung/
  __init__.py
  config_flow.py
  const.py
  coordinator.py
  fronius_api.py
  fronius_sync.py
  manifest.json
  number.py
  optimizer.py
  sensor.py
  switch.py
  strings.json
  translations/de.json
```

### 2. HA neu starten

### 3. Integration hinzufügen

Einstellungen → Geräte & Dienste → Integration hinzufügen → "Energieoptimierung"

Es folgt ein 6-stufiger Config Flow:

| Schritt | Inhalt |
|---------|--------|
| Energiemessung | Verbrauchssensor, Heizstab-Sensor, Wallbox-Sensor, Rückblick-Wochen, Update-Intervall, Sonnenaufgang-Offset |
| Hausbatterie | SOC-Sensor, Kapazitäts-Sensor |
| Warmwasserpuffer | Temperatursensor, Volumen (L), Zieltemperatur (°C) |
| Tesla-Fahrzeug | Standort-Tracker, SOC, Ladelimit, Kapazität, Effizienz, Home-Zone |
| Optimizer | PV-Sensor, Einspeise-Sensor, Solcast-Sensoren, Holzvergaser, Einspeiselimit (kW), Überschuss-Faktor, Guard-Delay (h) |
| Abend-Entladung & Fronius | Entladeleistung, Startzeit, Min-SOC, Sicherheitspuffer, Min-WW-Temp, Fronius IP/User/Passwort |

## Sensoren (16 Stück)

### Slow-Sensoren (Update alle 15 min, konfigurierbar)

| Sensor | Entity ID | Beschreibung |
|--------|-----------|-------------|
| Prognose bis Sonnenaufgang | `sensor.energieoptimierung_prognose_bis_sonnenaufgang` | Verbrauchsprognose jetzt → Sonnenaufgang + Offset |
| Prognose bis Sonnenuntergang | `sensor.energieoptimierung_prognose_bis_sonnenuntergang` | Verbrauchsprognose jetzt → Sonnenuntergang |
| Verbrauchsprofil | `sensor.energieoptimierung_verbrauchsprofil` | Ø Stundenwerte pro Zone für Dashboard-Charts |
| Prognose heute | `sensor.energieoptimierung_prognose_heute` | Tagesverbrauch heute |
| Prognose morgen | `sensor.energieoptimierung_prognose_morgen` | Tagesverbrauch morgen |
| Prognose Tag 2–7 | `sensor.energieoptimierung_prognose_tag_2` bis `_tag_7` | Tagesverbrauch +2 bis +7 Tage |

### Fast-Sensoren (Update alle 2 min)

| Sensor | Entity ID | Beschreibung |
|--------|-----------|-------------|
| Batterie fehlende Energie | `sensor.energieoptimierung_batterie_fehlende_energie` | kWh bis Batterie voll: (100% - SOC%) × Kapazität |
| Tesla fehlende Ladeenergie | `sensor.energieoptimierung_tesla_fehlende_ladeenergie` | kWh bis Tesla auf Ladelimit (0 wenn nicht zu Hause) |
| Puffer Aufheizenergie | `sensor.energieoptimierung_puffer_aufheizenergie` | kWh bis Puffer auf Zieltemperatur |
| Energiebedarf heute | `sensor.energieoptimierung_energiebedarf_heute` | Summe: Batterie + Tesla + Puffer + Verbrauch bis Sonnenuntergang |

### Optimizer-Sensor (Update alle 60s)

| Sensor | Entity ID | Beschreibung |
|--------|-----------|-------------|
| Entscheidung | `sensor.energieoptimierung_entscheidung` | Aktuelle Strategie als State, vollständige Decision als Attribute |

## Switches & Number

| Entity | Typ | Beschreibung |
|--------|-----|-------------|
| `switch.energieoptimierung_optimizer` | Switch | AN = Aktionen werden ausgeführt, AUS = nur Berechnung (Dry-Run) |
| `switch.energieoptimierung_einspeisung` | Switch | Einspeisung an/aus, triggert Fronius-Sync |
| `number.energieoptimierung_einspeiseleistung` | Number | Einspeiseleistung 0–12 kW, triggert Fronius-Sync |

## Output-Entities (vom Optimizer geschrieben)

| Entity | Beschreibung |
|--------|-------------|
| `input_select.heizstab` | Aus / 1-Phasig / 3-Phasig |
| `input_number.batterie_ladelimit_kw` | Ladelimit in kW |
| `switch.energieoptimierung_einspeisung` | Einspeisung aktiv |
| `number.energieoptimierung_einspeiseleistung` | Einspeiseleistung in kW |
| Fronius API | HYB_EM_MODE (0=auto, 1=manual), HYB_EM_POWER (negative W = Entladung) |

## Optimizer-Logik

### Strategien

Der Überschuss-Faktor bestimmt die Tagesstrategie:

```
Faktor = Solcast Restprognose heute / Energiebedarf heute

≥ 1.25 (konfigurierbar) → ÜBERSCHUSS
≥ 0.80                  → BALANCIERT
< 0.80                  → ENGPASS
Sonne unter Horizont    → NACHT
```

**ÜBERSCHUSS** – Guter PV-Tag:
- Einspeiselimit (default 4 kW) wird zuerst reserviert
- Überschuss geht an Heizstab + Batterie
- Inverter-Drosselung wird erkannt (+2 kW spekulativ)

**BALANCIERT** – Mäßiger PV-Tag:
- Batterie hat Vorrang (60% der verfügbaren Leistung) bis SOC 80%
- Rest für Heizstab
- Überschuss geht ins Netz

**ENGPASS** – Schlechter PV-Tag:
- Eigenverbrauch maximieren, keine Einspeisung
- Batterie zuerst, WW nur wenn nötig (< 55°C)

**NACHT** – Nach Sonnenuntergang:
- Heizstab 3P und Ladelimit 4 kW als Defaults (kosten nichts, da nur PV-gespeist)
- Abend-Entladung wenn Bedingungen erfüllt

### Guards (Sicherheitsprüfungen)

Guards werden **jeden Zyklus** geprüft und können die Strategie überschreiben.

**KRITISCH** (immer aktiv):
- WW < 40°C → Heizstab 3P, Einspeisung gestoppt
- Batterie < 10% → Alles für Batterie, Heizstab aus

**HOCH** (mit Guard-Delay nach Sonnenaufgang):
- WW < 55°C → Heizstab mindestens 1-Phasig
- Batterie < 25% → Ladelimit mindestens 2 kW

**MITTEL**:
- Holzvergaser aktiv + PV < 6kW → Heizstab aus

### Guard-Delay (EEG-Vorrang am Morgen)

HOCH-Guards werden in den ersten Stunden nach Sonnenaufgang unterdrückt (`guard_delay_h`, default 3h). Damit hat morgens die Netzeinspeisung für die EEG-Gemeinschaft Vorrang. KRITISCH-Guards bleiben immer aktiv.

Beispiel bei Sonnenaufgang 06:30 und Guard-Delay 3h:
- 06:30–09:30: HOCH-Guards unterdrückt → PV geht ins Netz
- Ab 09:30: HOCH-Guards greifen → WW/Batterie werden bei Bedarf versorgt

Im Dashboard wird angezeigt: "Guard-Delay: 1.2h seit Sonnenaufgang < 3h → HOCH-Guards unterdrückt (EEG-Vorrang)"

### Abend-Entladung

Nachtentladung wird freigegeben wenn ALLE Bedingungen erfüllt sind:
1. Startzeit erreicht (default 20:00)
2. SOC > dynamischer Min-SOC (absoluter Min-SOC + Nachtverbrauch × Sicherheitspuffer)
3. Morgen ist ein Überschusstag: PV-Prognose ≥ Gesamtbedarf
   - Gesamtbedarf = Hausverbrauch + Batterie (min_soc→100%) + Puffer (40°C→Ziel)

Tagsüber wird eine Vorschau der Nachtentladung in der Begründung angezeigt.

## Verbrauchsprofil

### Zonen (4 Tagtypen)

| Zone | Tage |
|------|------|
| mo-do | Montag – Donnerstag |
| fr | Freitag |
| sa | Samstag |
| so | Sonntag |

### Berechnung

```
Pro Stunde im Prognosezeitraum:
1. Ø Verbrauch OHNE Heizstab und Wallbox für diese Tagesstunde
   - Aus recorder Langzeit-Statistiken (stündliche Mittelwerte)
   - Getrennt nach Zone (mo-do/fr/sa/so)
   - Rollierendes 8-Wochen-Fenster (konfigurierbar)
   - Fallback-Kette wenn keine Daten: fr→mo-do, sa→so, etc.

2. Netto-Verbrauch = Verbrauch - Heizstab - Wallbox (min 0)
```

### Sensor-Attribute (Beispiel Verbrauchsprofil)

```
mo-do: "12.5 kWh/Tag, Spitze 850W um 18:00, Min 180W um 03:00"
mo-do_watts: [180, 170, 165, 180, 200, ...]  (24 Werte für ApexCharts)
mo-do_kwh: 12.5
```

## Fronius-Integration

Die Fronius-Steuerung nutzt HTTP Digest Auth gegen die lokale API des Wechselrichters.

- **Login**: GET `/api/commands/Login?user=customer` → 401 Challenge → Digest Auth
- **Config**: POST `/api/config/batteries` mit `{"HYB_EM_MODE": 1, "HYB_EM_POWER": -3000}`
- **Hybrid-Auth**: HA1=MD5, HA2+Response=SHA256 (Fronius Gen24 Besonderheit)
- **Auto-Mode**: `{"HYB_EM_MODE": 0}` → Fronius regelt selbst

Die Sync-Funktion (`fronius_sync.py`) wird bei jeder Änderung des Einspeisung-Switches oder der Einspeiseleistung aufgerufen.

## Abhängigkeiten

- **recorder** — Langzeit-Stundenstatistiken für Verbrauchshistorie
- **sun** — Sonnenauf-/untergang, Guard-Delay-Timing
- **solcast_solar** (after_dependency) — PV-Produktionsprognosen
