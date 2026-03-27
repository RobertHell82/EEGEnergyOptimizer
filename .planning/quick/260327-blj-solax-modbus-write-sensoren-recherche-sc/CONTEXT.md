# Context: SolaX Modbus Write-Sensoren Recherche

## Task
Recherche und Dokumentation der schreibenden Sensoren/Register für SolaX Batteriesteuerung via homeassistant-solax-modbus Integration.

## Key Decisions

1. **Mode 1 "Enabled Battery Control" ist der primäre Steuermechanismus** — Positive Leistung = Laden, Negative = Entladen, 0 = Batterie idle (PV geht ins Netz). Kein custom HA Service nötig, alles über Standard-Entity-Services.

2. **Zwei-Phasen-Schreibarchitektur** — Werte werden erst in `remotecontrol_*` Entities geschrieben, dann über `button.solax_remotecontrol_trigger` als Multi-Register-Payload ab Holding Register 0x7C gesendet.

3. **Target SOC nicht firmware-seitig enforced** — `selfuse_discharge_min_soc` (0x61) gilt möglicherweise nicht im Remote Control Modus. Software-seitiges SOC-Monitoring im 30s-Zyklus ist Pflicht.

4. **Entity-Prefix variiert** — `solax_`, `solax_inverter_`, `solaxmodbus_` oder custom. Auto-Detection via `*_remotecontrol_power_control` Pattern erforderlich.

## Open Questions (für Hardware-Test)

- `Enabled Feedin Priority` vs `Enabled Battery Control (power=0)` für Morning Charge Blocking — beides plausibel, Hardware-Test nötig
- Lock State Handling: Muss vor jedem Schreiben explizit entsperrt werden (Passwort 2014)?
- X1 Fit (AC-coupled): Hat möglicherweise keinen `remotecontrol_trigger` Button

## Research Source
- RESEARCH.md in diesem Verzeichnis (detaillierte Register-Tabellen, Entity-Mappings, Implementierungsansatz)
