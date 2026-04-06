# SolarEdge HA Sensor-Check — Ergebnisse

**Datum:** 2026-04-06
**HA-Instanz:** ha.linzner.cloud (HA 2026.4.1)
**Integration:** solaredge_modbus_multi (loaded) + solaredge Cloud (loaded)
**Inverter:** SE10K-RWB48BFN4
**Batterie:** SolarEdge Home Battery 23kWh (24.25 kWh max)

## Entity-Prefix

**Abweichung gefunden:** Der Prefix ist `solaredge_i1_` statt dem erwarteten `solaredge_`.

Unsere `SOLAREDGE_DEFAULTS` und `_find_solaredge_prefix()` suchen nach `*storage_command_mode` — das wird hier nicht gefunden, weil die StorEdge-Entities fehlen (siehe unten).

## Sensor-Mapping (Read-Only Sensoren)

| Unsere Config-Key | Erwarteter Default | Tatsächliche Entity | Status | Wert (zum Zeitpunkt) |
|---|---|---|---|---|
| `battery_soc_sensor` | `sensor.solaredge_b1_state_of_energy` | `sensor.solaredge_i1_b1_state_of_energy` | Name weicht ab (i1_ Prefix) | 95.74% |
| `pv_power_sensor` | `sensor.solaredge_ac_power` | `sensor.solaredge_i1_ac_power` | Name weicht ab (i1_ Prefix) | 237.48 W |
| `pv_power_sensor` (alt) | `sensor.solaredge_dc_power` | `sensor.solaredge_i1_dc_power` | Name weicht ab (i1_ Prefix) | 241.09 W |
| `grid_power_sensor` | `sensor.solaredge_m1_ac_power` | `sensor.solaredge_i1_m1_ac_power` | Name weicht ab (i1_ Prefix) | 10.87 W |
| `battery_power_sensor` | `sensor.solaredge_b1_dc_power` | `sensor.solaredge_i1_b1_dc_power` | Name weicht ab (i1_ Prefix) | -318.0 W |

### Sensorwerte plausibel?

- **SOC 95.74%** — Batterie fast voll, plausibel
- **PV AC 237 W** — Abendstunde (18:27 UTC), niedrige PV-Produktion, plausibel
- **Grid 10.87 W** — Fast 0 Netzeinspeisung, plausibel (PV ~ Verbrauch + Batterieladung)
- **Battery -318 W** — **Negativ = Laden** (B_STATUS_DISCHARGE sagt Entladen, aber Wert ist negativ → Sign Convention klären!)
- **Battery Status: B_STATUS_DISCHARGE** — Widerspruch zum negativen Wert? Möglicherweise ist -318W aus Sicht des Inverters "Entladung zum Netz" (negativ = Strom fließt vom Battery DC zum Inverter)

### Sign Convention Analyse

| Sensor | Wert | Interpretation |
|---|---|---|
| `i1_b1_dc_power` = -318 W | Batterie Status = DISCHARGE | **Negativ = Entladung** (Strom fließt aus Batterie) |
| `i1_m1_ac_power` = +10.87 W | Netz | **Positiv = Import** (Bezug), Negativ = Export (Einspeisung) |
| `i1_ac_power` = +237 W | Inverter AC Output | **Positiv = Produktion** |

**Vorzeichen-Konvention bei solaredge-modbus-multi:**
- Battery: **Negativ = Entladung**, Positiv = Ladung (invertiert zu Huawei!)
- Grid (Meter): **Positiv = Import**, Negativ = Export
- Unsere `const.py` hat `battery_sign: 1, grid_sign: 1` — das muss geprüft werden!

## StorEdge Control-Entities — FEHLEN!

**Kritisches Problem:** Die folgenden Entities, die unsere `SolarEdgeInverter`-Klasse benötigt, existieren NICHT:

| Erwartete Entity | Status |
|---|---|
| `select.*storage_command_mode` | **NICHT VORHANDEN** |
| `number.*storage_charge_limit` | **NICHT VORHANDEN** |
| `number.*storage_discharge_limit` | **NICHT VORHANDEN** |
| `number.*storage_backup_reserve` | **NICHT VORHANDEN** |

Vorhandene select/number Entities:
- `number.solaredge_i1_active_power_limit` (0-100%, Leistungsbegrenzung in %)
- `select.solaredge_i1_reactive_power_mode` (Blindleistung, nicht relevant)

### Mögliche Ursachen

1. **StorEdge Power Control nicht aktiviert:** In der solaredge-modbus-multi Integration muss "Allow StorEdge Control" explizit aktiviert werden (Options → Advanced Power Control). Ohne diese Einstellung werden die Storage-Entities nicht erstellt.
2. **Ältere Integration Version:** Möglicherweise eine Version, die StorEdge noch nicht voll unterstützt.
3. **Inverter-Firmware:** Der SE10K-RWB48BFN4 hat StorEdge-Fähigkeit (Batterie ist angeschlossen!), aber die Modbus-Register müssen freigeschaltet sein.

## Zusätzliche nützliche Sensoren

| Entity | Wert | Beschreibung |
|---|---|---|
| `sensor.solaredge_i1_b1_available_energy` | 23.82 kWh | Verfügbare Energie (für battery_capacity) |
| `sensor.solaredge_i1_b1_maximum_energy` | 24.25 kWh | Max Kapazität |
| `sensor.solaredge_i1_b1_max_charge_power` | 5000 W | Max Ladeleistung |
| `sensor.solaredge_i1_b1_max_discharge_power` | 5000 W | Max Entladeleistung |
| `sensor.solaredge_i1_b1_state_of_health` | 99% | Batterie-Gesundheit |
| `sensor.solaredge_i1_ac_energy` | 17095 kWh | Gesamtproduktion |

## Handlungsbedarf

### 1. Prefix-Handling anpassen
Unsere `SOLAREDGE_DEFAULTS` verwenden `sensor.solaredge_*` — der tatsächliche Prefix ist `solaredge_i1_`. Die Auto-Detection via `_find_solaredge_prefix()` kann den Prefix nicht finden, weil sie nach `*storage_command_mode` sucht, die nicht existiert.

**Empfehlung:** Fallback-Erkennung über andere bekannte Entities (z.B. `*b1_state_of_energy` oder `*ac_power`).

### 2. StorEdge Power Control aktivieren
Der Benutzer muss in der solaredge-modbus-multi Integration unter Options "Allow StorEdge Control" aktivieren. Erst dann werden die Storage-Control-Entities erstellt.

### 3. Sign Convention prüfen
`battery_sign: 1` und `grid_sign: 1` in `const.py` muss gegen die tatsächlichen Vorzeichen validiert werden, sobald StorEdge aktiv ist und die Batterie gesteuert wird.

## Gesamt-Status

| Bereich | Status |
|---|---|
| Read-Only Sensoren | Vorhanden, aber mit `i1_` Prefix |
| Sensorwerte | Plausibel |
| StorEdge Control | **FEHLT** — muss in Integration aktiviert werden |
| Auto-Detection | Wird fehlschlagen (kein `storage_command_mode`) |
| Sign Convention | Muss nach StorEdge-Aktivierung validiert werden |
