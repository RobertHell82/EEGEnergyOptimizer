# Quick Task 260412-r3n: Fronius Gen24 Umsetzungskonzept — Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Task Boundary

Erstelle ein Umsetzungskonzept für die Integration eines Fronius Gen24 Wechselrichters in den EEG Energy Optimizer. Fokus auf:
1. Welche lesenden Sensoren können verwendet werden (PV, Batterie, Grid, SOC etc.)
2. Wie kann der Wechselrichter angesteuert werden (Laden blockieren, Entladen erzwingen, Normalbetrieb)
3. Vergleich der verschiedenen Integrationswege mit Vor-/Nachteilen

Ziel ist ein Umsetzungskonzept, NICHT die Umsetzung selbst.

</domain>

<decisions>
## Implementation Decisions

### Integrationsweg
- Alle Wege vergleichen: HA Fronius-Integration, Modbus TCP direkt, Fronius Solar API
- Pro/Contra-Vergleich mit Empfehlung
- Fokus auf Praxistauglichkeit für den EEG Energy Optimizer Use-Case

### Batterie-Setup
- BYD HVS/HVM als Referenz-Setup (gängigste Kombination mit Gen24)
- Konzept soll aber die Batterie-Steuerung über den Wechselrichter abbilden, nicht direkt zur Batterie

### Konzept-Tiefe
- Praxistauglich detailliert: Konkrete Entity-IDs, Modbus-Register oder API-Endpoints mit Parametern
- So dass man direkt damit implementieren könnte
- Keine Code-Snippets oder Timing-Diagramme nötig, aber konkrete technische Details

### Claude's Discretion
- Keine weiteren offenen Punkte

</decisions>

<specifics>
## Specific Ideas

- Mapping auf die bestehende InverterBase-Abstraktion (async_set_charge_limit, async_set_discharge, async_stop_forcible)
- Vergleich mit der bestehenden Huawei/SolaX/SolarEdge-Implementierung
- Besonderheiten des Fronius Gen24 bei der Batteriesteuerung beachten

</specifics>

<canonical_refs>
## Canonical References

- `custom_components/eeg_energy_optimizer/inverter/base.py` — InverterBase ABC
- `custom_components/eeg_energy_optimizer/inverter/huawei.py` — Referenz-Implementierung Huawei
- `custom_components/eeg_energy_optimizer/inverter/solax.py` — Referenz SolaX
- `custom_components/eeg_energy_optimizer/inverter/solaredge.py` — Referenz SolarEdge

</canonical_refs>
