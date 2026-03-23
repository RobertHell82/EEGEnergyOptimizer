# Quick Task 260323-m0o: Dashboard Status-Header überarbeiten — Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Task Boundary

Dashboard oberen Bereich (über den Grafiken) komplett überarbeiten. Ziel: Benutzer sieht auf einen Blick den aktuellen Status beider Optimizer-Features — warum eine Entscheidung getroffen wurde und warum nicht.

</domain>

<decisions>
## Implementation Decisions

### Layout-Struktur
- **Zwei gleichwertige Status-Cards nebeneinander**: Links "☀ Verzögerte Ladung", rechts "🌙 Abend-Entladung"
- Jede Card zeigt: Titel, Status-Zeile mit Begründung, Trennlinie, 2-3 Bedingungszeilen mit Werten und ✓/✗

### Detail-Tiefe & Status-Texte
- Status-Zeile enthält immer eine **Begründung** bei "Nicht geplant":
  - "Nicht geplant — SOC zu niedrig"
  - "Nicht geplant — PV morgen nicht ausreichend"
  - "Nicht aktiv — PV reicht nicht für Bedarf + Puffer"
- Bei "Geplant" wird **Ziel-SOC** angezeigt: "Geplant ab 20:00 bis 35% SOC"
- Bei "Aktiv": "AKTIV — 3.0 kW Entladung bis 35% SOC" / "AKTIV — Ladung blockiert bis 10:00"

### Abend-Entladung — Zustände
1. **Geplant** (vor Startzeit, Bedingungen erfüllt): "○ Geplant ab 20:00 bis 35% SOC" + Bedingungen mit ✓
2. **Nicht geplant — SOC zu niedrig**: "✕ Nicht geplant — SOC zu niedrig" + SOC-Zeile mit ✗
3. **Nicht geplant — PV morgen nicht ausreichend**: "✕ Nicht geplant — PV morgen nicht ausreichend" + PV-Zeile mit ✗
4. **Nicht geplant — mehrere Gründe**: Kombinierte Begründung
5. **Aktiv** (läuft gerade): "● AKTIV — 3.0 kW Entladung bis 35% SOC" + SOC→Ziel, Leistung, PV
6. **Deaktiviert**: "— Deaktiviert" + Hinweis auf Einstellungen

### Verzögerte Ladung — Zustände
1. **Aktiv** (im Zeitfenster, PV reicht): "● AKTIV — Ladung blockiert bis 10:00" + PV/Bedarf/Überschuss
2. **Im Zeitfenster, nicht aktiv**: "✕ Nicht aktiv — PV reicht nicht für Bedarf + Puffer" + Fehlmenge
3. **Außerhalb Zeitfenster, morgen erwartet**: "○ Morgen ab ~06:15 (PV ausreichend)" + PV morgen/Bedarf
4. **Außerhalb Zeitfenster, morgen nicht erwartet**: "✕ Morgen nicht erwartet — PV Prognose zu gering"
5. **Deaktiviert**: "— Deaktiviert" + Hinweis auf Einstellungen

### Claude's Discretion
- **Backend-Daten**: Decision-Attribute erweitern (neue Felder in Decision-Dataclass + Sensor-Attribute). Nutzt bestehenden 60s-Update-Mechanismus, kein neuer WebSocket-Befehl nötig.

</decisions>

<specifics>
## Specific Ideas

- Farbcodierung: ● grün (aktiv), ○ blau (geplant), ✕ rot (nicht möglich), — grau (deaktiviert)
- Bedingungszeilen mit ✓/✗ Indikatoren und konkreten Werten (z.B. "SOC 72% > Min 35%")
- Kompakte Card-Höhe, deaktivierte Features minimal (1 Zeile + Hinweis)

</specifics>
