# Quick Task 260412-t0k: Fronius Gen24 Inverter Support — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Task Boundary

Implementiere den Fronius Gen24 Wechselrichter-Support basierend auf dem fertigen Umsetzungskonzept aus Quick Task 260412-r3n.

</domain>

<decisions>
## Implementation Decisions

Alle Entscheidungen sind im Konzeptdokument festgehalten:
- **Konzept:** `.planning/quick/260412-r3n-fronius-gen24-umsetzungskonzept-sensoren/FRONIUS-GEN24-KONZEPT.md`

### Kernentscheidungen (aus Konzept):
- **Sensoren lesen:** Via native HA Fronius Integration (Core, Auto-Discovery)
- **Steuerung:** Direkte Modbus TCP via pymodbus (SunSpec Model 124)
- **Keine HACS-Dependency:** Kein fronius_modbus nötig
- **SunSpec Discovery:** Scan ab Register 40000, Model-Header iterieren bis 124 gefunden
- **WChaMax:** Einmal täglich lesen und cachen (ist konstant)
- **Register-Operationen:** StorCtl_Mod, InWRte, OutWRte — max 3 Register pro Operation
- **Panel-Anleitung:** Fronius Integration einrichten + Modbus TCP aktivieren

### Claude's Discretion
- Implementierungsdetails die nicht im Konzept stehen

</decisions>

<specifics>
## Specific Ideas

- FroniusInverter analog zu SolaXInverter/SolarEdgeInverter aufbauen
- pymodbus AsyncModbusTcpClient mit 3 Retries, 200ms Pause
- Entity-Konfiguration im Wizard/Panel (Entity-Picker für Fronius-Sensoren)

</specifics>

<canonical_refs>
## Canonical References

- `.planning/quick/260412-r3n-fronius-gen24-umsetzungskonzept-sensoren/FRONIUS-GEN24-KONZEPT.md` — Vollständiges Umsetzungskonzept
- `custom_components/eeg_energy_optimizer/inverter/base.py` — InverterBase ABC
- `custom_components/eeg_energy_optimizer/inverter/solax.py` — Referenz-Implementierung (Entity-basiert)
- `custom_components/eeg_energy_optimizer/inverter/solaredge.py` — Referenz-Implementierung (Entity-basiert)

</canonical_refs>
