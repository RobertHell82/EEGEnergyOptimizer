# Quick Task: SolarEdge Anleitung im Panel - Research

**Researched:** 2026-04-06
**Domain:** SolarEdge StorEdge + solaredge-modbus-multi Integration Setup Guide
**Confidence:** HIGH (verified against live system + GitHub wiki + community posts)

## Summary

Die SolarEdge-Anleitung soll als `DIALOG_CONTENT.solaredge` im Panel eingefuegt werden, analog zur bestehenden Huawei-Anleitung. Sie muss drei Bereiche abdecken: (1) Wechselrichter-Vorbereitung (Modbus TCP aktivieren), (2) HACS Integration installieren und konfigurieren, (3) StorEdge Power Control aktivieren. Der kritische Unterschied zu Huawei: Nach der Integration-Installation muss der Benutzer **explizit** "Allow StorEdge Control" in den Options aktivieren, da sonst die Steuerungs-Entities (`storage_command_mode`, `storage_charge_limit` etc.) gar nicht erstellt werden.

**Primary recommendation:** Dreistufige Anleitung mit Schwerpunkt auf dem oft vergessenen StorEdge-Control-Aktivierungsschritt.

## Bestehendes Huawei-Guide-Format (Referenz)

Die Huawei-Anleitung in `DIALOG_CONTENT.huawei` (Zeile 126-196 in panel.js) folgt diesem Muster:

```
1. Wechselrichter vorbereiten (5 Schritte, mit Warnung)
2. HACS Integration installieren (2 Schritte)
3. Integration konfigurieren (8 Schritte, mit Hinweis "vergessen?")
4. Pruefen (4 Schritte)
Haeufige Probleme (Tabelle, 5 Eintraege)
```

Die SolarEdge-Anleitung soll dasselbe Muster verwenden, mit einem zusaetzlichen Abschnitt fuer StorEdge-Aktivierung.

## SolarEdge Wechselrichter-Vorbereitung

### SetApp-Wechselrichter (ohne LCD-Display, neuere Modelle)

Confidence: HIGH (aus GitHub Wiki Configuration-Seite verifiziert)

1. **Roten DIP-Schalter** am Wechselrichter fuer weniger als 5 Sekunden auf "P" stellen (WiFi Direct aktivieren)
2. Mit dem WLAN-Hotspot des Wechselrichters verbinden (Netzwerkname steht auf dem Geraet)
3. Im Browser `http://172.16.0.1` oeffnen
4. **Site Communication** oeffnen
5. **Modbus/TCP** aktivieren

**Kritisch:** Die Integration muss sich **innerhalb von 2 Minuten** nach dem Aktivieren verbinden! Danach bleibt der Port offen. Falls die 2 Minuten ueberschritten werden: Modbus TCP aus- und wieder einschalten.

### LCD-Wechselrichter (aeltere Modelle)

1. "OK" fuer 5 Sekunden druecken (Installer-Modus)
2. Standard-Passwort: `12312312`
3. **Communications -> LAN setup** navigieren
4. Modbus/TCP Port konfigurieren

### Wichtige Einschraenkung

SolarEdge erlaubt **nur eine Modbus/TCP-Verbindung gleichzeitig**. Andere Modbus-Integrationen muessen deaktiviert werden.

## solaredge-modbus-multi Integration

### Installation

Confidence: HIGH

- **Repository:** WillCodeForCats/solaredge-modbus-multi
- **Installation:** HACS -> Integrationen -> Suche "SolarEdge Modbus Multi"
- **Neustart** von Home Assistant nach Installation erforderlich

### Konfiguration

1. **Einstellungen -> Geraete & Dienste -> Integration hinzufuegen**
2. Suche nach **"SolarEdge Modbus Multi"**
3. **IP-Adresse** des Wechselrichters eingeben
4. **Port: 1502** (Standard fuer SolarEdge Modbus TCP)
5. **Device ID: 1** (Standard, bei Multi-Inverter-Setups anpassen)
6. Polling Frequency: Standard 300s (5 Minuten) ist ok

### StorEdge Power Control aktivieren (KRITISCHER SCHRITT!)

Confidence: HIGH (verifiziert am Live-System ha.linzner.cloud - Entities fehlten ohne diesen Schritt)

**Ohne diesen Schritt werden die Steuerungs-Entities NICHT erstellt!**

1. Gehe zu **Einstellungen -> Integrationen -> SolarEdge Modbus Multi**
2. Klicke auf **"Konfigurieren"** (Drei-Punkte-Menue)
3. In den **Options**: **"Allow StorEdge Control"** (oder "Storage Control") aktivieren
4. Speichern und **Integration neu laden**
5. Nach dem Neuladen sollten folgende Entities erscheinen:
   - `select.solaredge_i1_storage_control_mode`
   - `select.solaredge_i1_storage_command_mode`
   - `number.solaredge_i1_storage_charge_limit`
   - `number.solaredge_i1_storage_discharge_limit`
   - `number.solaredge_i1_backup_reserve`

**Warnung:** Power Control Options koennen Netzvertraege verletzen. Nur verwenden, wenn man weiss, was man tut.

## Entity-Naming / Prefix-Varianten

Confidence: HIGH (verifiziert am Live-System)

### Bekanntes Problem

Der Entity-Prefix variiert je nach Installation:
- **Single-Inverter:** `solaredge_i1_` (haeufigster Fall, bestaetigt auf Testsystem)
- **Theoretisch moeglich:** `solaredge_` (ohne i1), `solaredge_i2_` (zweiter Inverter)

### Entity-Mapping (Live-System ha.linzner.cloud)

| Config-Key | Entity-ID | Typ |
|---|---|---|
| battery_soc_sensor | `sensor.solaredge_i1_b1_state_of_energy` | sensor (%) |
| pv_power_sensor | `sensor.solaredge_i1_ac_power` | sensor (W) |
| grid_power_sensor | `sensor.solaredge_i1_m1_ac_power` | sensor (W) |
| battery_power_sensor | `sensor.solaredge_i1_b1_dc_power` | sensor (W) |
| battery_capacity | `sensor.solaredge_i1_b1_maximum_energy` | sensor (kWh) |
| storage_control_mode | `select.solaredge_i1_storage_control_mode` | select |
| storage_command_mode | `select.solaredge_i1_storage_command_mode` | select |
| storage_charge_limit | `number.solaredge_i1_storage_charge_limit` | number (W) |
| storage_discharge_limit | `number.solaredge_i1_storage_discharge_limit` | number (W) |
| backup_reserve | `number.solaredge_i1_backup_reserve` | number (%) |

### Suffix-Varianten

`backup_reserve` heisst bei manchen Installationen `storage_backup_reserve`. Unser Code in `solaredge.py` handhabt das bereits ueber `SOLAREDGE_SUFFIX_VARIANTS`.

## Vorzeichen-Konvention (Sign Convention)

Confidence: MEDIUM (aus Sensor-Check, benoetigt Validierung mit aktivem StorEdge)

| Sensor | Positiv | Negativ |
|---|---|---|
| Battery (`b1_dc_power`) | Ladung | Entladung |
| Grid (`m1_ac_power`) | Import (Bezug) | Export (Einspeisung) |
| PV (`ac_power`) | Produktion | — |

**Wichtig fuer die Anleitung:** Die Vorzeichen sind **invertiert zu Huawei** bei der Batterie! Unser Optimizer-Code muss das beruecksichtigen (ueber `battery_sign` / `grid_sign` in const.py).

## Anleitung-Inhalt fuer DIALOG_CONTENT.solaredge

### Empfohlene Struktur (5 Abschnitte)

```
1. Wechselrichter vorbereiten (Modbus TCP aktivieren)
   - SetApp-Variante (5 Schritte + 2-Minuten-Warnung)
   - LCD-Variante (4 Schritte)
   - Warnung: Nur EINE Modbus-Verbindung gleichzeitig

2. HACS Integration installieren
   - HACS -> Suche "SolarEdge Modbus Multi"
   - Neustart

3. Integration konfigurieren
   - IP, Port 1502, Device ID 1
   - Batterie-Erkennung aktivieren

4. StorEdge Speichersteuerung aktivieren (WICHTIG!)
   - Options -> Allow StorEdge Control
   - Integration neu laden
   - Pruef-Entities auflisten
   - Warnung-Box: "Unser Optimizer setzt storage_control_mode automatisch auf Remote Control"

5. Pruefen
   - Integration "geladen"
   - Batterie-SOC Entity vorhanden
   - storage_command_mode Entity vorhanden (= StorEdge aktiv)
   - Zurueck zum Wizard

Haeufige Probleme (Tabelle):
   - Connection refused → Modbus TCP nicht aktiviert
   - Connection timeout → Port 1502 pruefen, 2-Minuten-Fenster beachten
   - Keine Batterie-Entities → Batterie-Erkennung in Options aktivieren
   - Keine Storage-Entities → "Allow StorEdge Control" in Options aktivieren
   - Verbindung bricht ab → Nur EINE Modbus-Verbindung moeglich
```

### HTML-Encoding Hinweise

Die bestehenden Guides verwenden HTML-Entities fuer Umlaute:
- ae = `&auml;` / oe = `&ouml;` / ue = `&uuml;`
- AE = `&Auml;` / OE = `&Ouml;` / UE = `&Uuml;`
- ss = `&szlig;`
- Pfeil = `&rarr;`
- Anfuehrungszeichen = `&ldquo;` / `&rdquo;`

## Haeufige Probleme (fuer Troubleshooting-Tabelle)

Confidence: HIGH

| Problem | Ursache | Loesung |
|---|---|---|
| Connection refused | Modbus TCP nicht am Inverter aktiviert | Schritt 1: WiFi Direct -> 172.16.0.1 -> Modbus TCP aktivieren |
| Connection timeout | 2-Minuten-Fenster verpasst | Modbus TCP aus/ein, innerhalb 2 Min verbinden |
| Keine Batterie-Entities | Auto-Detect Batteries deaktiviert | Options -> "Detect Batteries" aktivieren |
| Keine Storage-Control-Entities | StorEdge Control nicht aktiviert | Options -> "Allow StorEdge Control" aktivieren |
| Nur 1 Verbindung | SolarEdge limitiert auf 1 Modbus TCP Client | Andere Modbus-Integrationen deaktivieren |
| Entity-Prefix unbekannt | Variiert je Installation (solaredge_ vs solaredge_i1_) | Unser Optimizer erkennt den Prefix automatisch |

## Implementierungshinweise

### Wo einfuegen

In `eeg-optimizer-panel.js`, im `DIALOG_CONTENT`-Objekt (Zeile 125), neuer Key `solaredge`:

```javascript
const DIALOG_CONTENT = {
  huawei: { ... },    // Zeile 126-196
  solcast: { ... },   // Zeile 198-249
  forecast_solar: { ... }, // Zeile 251-307
  capacity_sensor: { ... }, // Zeile 308-324
  solaredge: {         // NEU
    title: "SolarEdge Modbus Multi einrichten",
    content: `...`
  },
};
```

### Button im Wizard

Bereits vorhanden: Die SolarEdge-Karte im Wizard (Zeile 1691-1698) hat KEINEN Anleitung-Button. Es muss ein Button analog zu Huawei (Zeile 1681) hinzugefuegt werden:

```html
<button class="btn-secondary" style="margin-top:8px" data-action="show-dialog" data-dialog="solaredge">Anleitung</button>
```

## Sources

### Primary (HIGH confidence)
- GitHub Wiki Configuration: https://github.com/WillCodeForCats/solaredge-modbus-multi/wiki/Configuration
- Live-System Sensor-Check: `.planning/quick/260406-sel-solaredge-ha-sensor-check-via-api/260406-sel-SUMMARY.md`
- Bestehende Inverter-Implementierung: `custom_components/eeg_energy_optimizer/inverter/solaredge.py`

### Secondary (MEDIUM confidence)
- GitHub Discussion #207 (Power Control Functions): https://github.com/WillCodeForCats/solaredge-modbus-multi/discussions/207
- HA Community Thread: https://community.home-assistant.io/t/solaredge-modbus-multi-config-for-single-inverter-battery-and-backup-module-meter/915187
- GitHub README: https://github.com/WillCodeForCats/solaredge-modbus-multi
