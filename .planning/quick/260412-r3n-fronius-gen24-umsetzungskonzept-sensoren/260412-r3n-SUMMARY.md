---
phase: quick-260412-r3n
plan: 01
subsystem: documentation/inverter
tags: [fronius, gen24, umsetzungskonzept, modbus, sunspec]
dependency_graph:
  requires: [inverter/base.py]
  provides: [FRONIUS-GEN24-KONZEPT.md]
  affects: [inverter/fronius.py (future)]
key_files:
  created:
    - .planning/quick/260412-r3n-fronius-gen24-umsetzungskonzept-sensoren/FRONIUS-GEN24-KONZEPT.md
decisions:
  - "Empfehlung: Native HA Fronius (Lesen) + fronius_modbus callifo Fork (Steuerung)"
  - "Entity-Keys konfigurierbar machen (nicht hardcoden) wegen fronius_modbus WIP-Status"
  - "Alternativer Weg: Direkte Modbus TCP (pymodbus) als Fallback dokumentiert"
  - "Undokumentierte Web API als nicht empfohlen eingestuft (Firmware-Breaking-Changes)"
metrics:
  duration: 4min
  completed: "2026-04-12T17:50:00Z"
  tasks: 1
  files: 1
---

# Quick Task 260412-r3n: Fronius Gen24 Umsetzungskonzept Summary

Vollstaendiges Umsetzungskonzept fuer Fronius Gen24 + BYD HVS/HVM: 4 Integrationswege verglichen, InverterBase-Mapping dokumentiert, Empfehlung fuer fronius_modbus HACS (callifo) + native HA Fronius

## Completed Tasks

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Fronius Gen24 Umsetzungskonzept erstellen | e34bb17 | FRONIUS-GEN24-KONZEPT.md (607 Zeilen) |

## What Was Built

Umfassendes Konzeptdokument (607 Zeilen, 9 Kapitel) als Implementierungsgrundlage fuer einen `FroniusInverter`-Treiber:

1. **Ziel und Scope** — Referenz-Setup (Gen24 + BYD HVS/HVM), Abgrenzung Konzept vs. Implementierung
2. **Lesende Sensoren** — Vollstaendiges Entity-Mapping (Power Flow + Storage), Vorzeichen-Konventionen, Einheiten-Umrechnung
3. **Wechselrichter-Ansteuerung** — 4 Methoden detailliert: HA nativ (read-only), Modbus direkt (Register-Tabelle), fronius_modbus HACS (Entity-basiert), undokumentierte Web API
4. **Vergleichstabelle** — Alle 4 Methoden in 11 Kriterien verglichen
5. **Empfehlung** — Primaer: fronius_modbus callifo Fork, Alternativ: pymodbus direkt, Nicht empfohlen: Web API
6. **InverterBase-Mapping** — Alle 4 Methoden (set_charge_limit, set_discharge, stop_forcible, is_available) fuer beide Wege (HACS + direkt), Vergleichstabelle mit Huawei/SolaX/SolarEdge
7. **Voraussetzungen** — Fronius Web-Interface Konfiguration, HACS Installation, Firmware-Empfehlung
8. **Offene Fragen** — 5 Punkte fuer Testgeraet-Verifizierung (192.168.100.211)
9. **Besonderheiten/Pitfalls** — 7 Pitfalls: Prozentwerte, kein Auto-Revert, konkurrierende Einstellungen, dynamische Register, float/int+SF, Allow Control, WIP-Status

## Decisions Made

1. **Primaere Empfehlung:** Native HA Fronius Integration (Sensoren lesen) + fronius_modbus HACS callifo Fork (Steuerung) — begruendet durch HA-native Entities, SunSpec-Stabilitaet, aktive Entwicklung
2. **Entity-Keys konfigurierbar:** Wegen WIP-Status von fronius_modbus muessen Entity-Keys als Config mit Defaults implementiert werden (Muster wie SolaX/SolarEdge)
3. **Kein Auto-Revert:** Fronius Gen24 revertiert Modbus-Werte nicht automatisch — async_stop_forcible() ist kritisch (vergleichbar mit SolarEdge NVRAM)
4. **Web API ausgeschlossen:** Undokumentiert, Firmware-Breaking-Changes (FW 1.38/1.39), CSRF/Digest-Auth Komplexitaet

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] FRONIUS-GEN24-KONZEPT.md existiert (607 Zeilen, >= 200 Anforderung erfuellt)
- [x] Alle 9 Kapitel vorhanden
- [x] Alle 4 Integrationswege verglichen
- [x] InverterBase-Mapping fuer alle Methoden beschrieben
- [x] Testgeraet 192.168.100.211 referenziert
- [x] Echte Umlaute verwendet (keine ae/oe/ue)
- [x] Commit e34bb17 existiert
