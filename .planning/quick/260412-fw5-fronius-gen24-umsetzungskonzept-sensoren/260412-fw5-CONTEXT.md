# Quick Task 260412-fw5: Fronius Gen24 Umsetzungskonzept - Sensoren und Wechselrichter-Ansteuerung - Context

**Gathered:** 2026-04-12
**Status:** Ready for planning

<domain>
## Task Boundary

Erstelle ein Umsetzungskonzept für die Fronius Gen24 Wechselrichter-Integration in den EEG Energy Optimizer. Fokus: Welche lesenden Sensoren sind verfügbar, und wie kann der Wechselrichter für Lade-/Entlade-Steuerung angesteuert werden. Ziel ist ein Konzeptdokument, nicht die Implementierung selbst.

</domain>

<decisions>
## Implementation Decisions

### HA-Integration vs. direkte API
- **Beides untersuchen**: Sowohl bestehende HA-Integrationen (fronius, custom) als auch direkte API-Wege (Modbus TCP, Solar API / HTTP Digest) recherchieren und Vor-/Nachteile vergleichen.

### Sensor-Umfang
- **Vollständiges Mapping**: Alle verfügbaren Fronius Gen24 Entities dokumentieren — gibt Gesamtbild für den Optimizer und zukünftige Features. Nicht nur die Minimum-Sensoren für den Optimizer.

### Steuerungsparadigma
- **Alle Wege untersuchen**: Direkte Lade-/Entlade-Befehle, Fronius-eigene Zeitpläne, und Batterie-Min/Max-SOC Steuerung — vollständiger Vergleich aller Ansätze mit Bewertung.

</decisions>

<specifics>
## Specific Ideas

- Vergleich mit den bestehenden Implementierungen (Huawei via HA Services, SolaX via solax_modbus, SolarEdge via solaredge_modbus_multi)
- Die abstrakte InverterBase (inverter/base.py) definiert: async_set_charge_limit, async_set_discharge, async_stop_forcible — Konzept muss zeigen, wie Fronius diese Methoden befüllen kann
- Der User hat eine Fronius-Instanz auf 192.168.100.211 mit Solcast

</specifics>

<canonical_refs>
## Canonical References

- inverter/base.py — Abstrakte Inverter-Schnittstelle die implementiert werden muss
- .planning/research/PITFALLS.md — Warnung vor leaky abstractions bei Huawei vs Fronius Paradigmenunterschied
- .planning/research/ARCHITECTURE.md — Architektur-Entscheidungen zum Inverter-Layer

</canonical_refs>
