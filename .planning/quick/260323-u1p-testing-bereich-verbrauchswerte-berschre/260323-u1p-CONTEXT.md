# Quick Task 260323-u1p: Testing-Bereich — Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Task Boundary

Testing-Bereich unter manueller Steuerung: Verbrauchswerte überschreiben um Optimizer-Entscheidungen zu simulieren.

</domain>

<decisions>
## Implementation Decisions

### Ansatz
- **Faktor + SOC Override**: Ein Verbrauchs-Faktor (0.1x–3x, Step 0.1, Default 1.0) + ein SOC-Override-Feld (%, optional)
- Faktor wird auf alle Consumption-Werte im Optimizer angewendet (daylight, overnight)
- SOC-Override ersetzt battery_soc im Snapshot
- Zwei Buttons: "Anwenden" setzt die Werte, "Zurücksetzen" stellt Default wieder her

### Persistenz
- Nur Laufzeit — Overrides gelten bis HA-Neustart/Reload, werden NICHT in Config gespeichert
- Gespeichert in `hass.data[DOMAIN][entry_id]["test_overrides"]`

### UI
- Bereich "Simulation" unter "Manuelle Steuerung" im Dashboard
- Zeigt aktuelle berechnete Werte (Bedarf SA→SU, Nachtverbrauch, SOC) und wie sie mit Faktor aussehen
- Deutliche Warnung wenn Override aktiv ist (farbiger Banner)
- WebSocket Commands: `eeg_optimizer/set_test_overrides` und `eeg_optimizer/clear_test_overrides`

</decisions>
