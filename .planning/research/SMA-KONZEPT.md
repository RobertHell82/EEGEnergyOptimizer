# Konzept: SMA-Wechselrichter-Support (Machbarkeitsstudie + Umsetzungsplan)

**Stand:** 17.08.2026 · **Status:** Machbarkeit bestätigt, Umsetzung wartet auf Beta-Gerät
**Vorbild:** Kostal-Treiber (1.3.8-dev) — gleiche Architektur (direktes Modbus TCP + Watchdog-Keepalive)

## 1. Ergebnis in einem Satz

SMA ist als fünfter/sechster Wechselrichter-Typ **machbar**: Steuerung über die
„6-Parameter-Methode" des externen Batteriemanagements (CmpBMS-Register) per
direktem Modbus TCP, Sensorik über die rein lesende HA-Core-Integration `sma`
(WebConnect) — keine existierende HA-Integration kann die Steuerung, ein
eigener Treiber nach Fronius/Kostal-Muster ist nötig.

## 2. Zielgeräte

| Gerät | Typ | Status |
|---|---|---|
| Sunny Tripower Smart Energy (STP 5.0–10.0 SE) | Hybrid, DC-gekoppelt | **v1-Ziel** (Community-erprobt mit BYD HVS) |
| Sunny Boy Storage (SBS 3.7/5.0/6.0) | AC-gekoppelt (BYD) | **v1-Ziel** (evcc-Template vorhanden) |
| Sunny Boy Smart Energy | Hybrid | v1-Ziel (gleiche Registerfamilie) |
| Sunny Island | Insel/AC | **ausgeklammert** — andere Register (40149/40151), mit SHM2-Firmware teils defekt |
| Tripower X u. a. ennexOS | ohne Batterie | irrelevant; HA-Core-Integration unterstützt ennexOS ohnehin nicht |

## 3. Steuerung: die 6-Parameter-Methode (CmpBMS)

Quelle: evcc-Templates `sma-hybrid.yaml` / `sma-sbs-modbus.yaml` (produktiv),
Photovoltaikforum-Thread 251643 (Home Assistant + STP10.0-SE + BYD HVS,
preisbasierte Lade-/Entladesteuerung mit exakt diesen Registern).

**Verbindung:** Modbus TCP Port **502**, Unit-ID **3**, Schreiben via FC16
(writemultiple). Alle Register U32, außer GridWSpt (S32).

| Register | Name | Bedeutung |
|---|---|---|
| **40236** | CmpBMS.OpMod | Betriebsart BMS: 2424=Default, 2289=Laden, 2290=Entladen, 303=Aus, 1438=Auto. ⚠️ Manche Geräte/Firmwares nutzen **41259** — am Gerät prüfen |
| **40793** | BatChaMinW | Min. Ladeleistung (W) |
| **40795** | BatChaMaxW | Max. Ladeleistung (W) — **0 = Laden blockiert** |
| **40797** | BatDschMinW | Min. Entladeleistung (W) |
| **40799** | BatDschMaxW | Max. Entladeleistung (W) |
| **40801** | CmpBMS.GridWSpt | **Sollwert Netzaustauschleistung** (S32) — Wechselrichter regelt den Netzanschlusspunkt auf diesen Wert |

**Protokollregeln (SMA-Doku):**
- Alle 6 Register müssen **innerhalb von 10 s als Block** geschrieben werden, sonst werden sie ignoriert
- Refresh mindestens **alle 300 s** (evcc nutzt 60-s-Watchdog); Timeout → Rückfall auf interne Automatik = **eingebauter Failsafe** (identische Semantik wie Kostal)

### Abbildung auf unsere Optimizer-Zustände

| Zustand | OpMod | ChaMin/Max | DschMin/Max | GridWSpt |
|---|---|---|---|---|
| **Morgen-Einspeisung** (Laden blockieren) | 2424 | 0 / **0** | 0 / max | 0 |
| **Nacht-Entladung** (ins Netz) | 2424 o. 2290 | 0 / 0 | 0 / P_entlade | **Export-Sollwert** (Vorzeichen verifizieren!) |
| **Einspeisebegrenzung** (Ladelimit X W) | 2424 | 0 / **X** | 0 / max | 0 |
| **Normal / Stop** | 2424 + Defaults schreiben, dann Keepalive stoppen → Watchdog-Rückfall | | | |

⚠️ **Wichtigste Erkenntnis:** OpMod 2290 („Batterie entladen") allein entlädt
NUR bei Netzbezug — bei Einspeisung geht die Batterie in Standby. Erzwungene
Netz-Einspeisung geht ausschließlich über **GridWSpt**. Das ist konzeptionell
sogar besser als bei Fronius/Kostal: Der Wechselrichter regelt den
Netzanschlusspunkt selbst, der Hausverbrauch wird automatisch mitkompensiert
(die eingespeiste Leistung ist direkt die EEG-wirksame Leistung).

**Einspeisebegrenzung:** Wattgenaues Ladelimit über BatChaMaxW → SMA könnte
das Feature von Anfang an unterstützen (anders als Kostal, wo das Encoding
unklar ist) — trotzdem erst nach Gerätetest freischalten.

## 4. Flash-Verschleiß: Entwarnung mit klarer Abgrenzung

SMA hat **zwei Registerklassen**:

1. **Statische Parameter** (z. B. SelfCsmp.BatChaSttMin, WMax): werden im
   Flash **persistiert**, begrenzte Schreibzyklen — SMA warnt explizit, dass
   zyklisches Schreiben den Flash zerstört. → **Der Treiber fasst diese
   Register niemals an.**
2. **Dynamische Sollwerte** (die 6 CmpBMS-Register): Write-Only, flüchtig,
   nicht persistiert — zyklisches Schreiben ist hier **vorgeschrieben**
   (Watchdog). → Kein Verschleiß, Gegenteil des SolarEdge-NVRAM-Problems.

Regel fürs Review: Jede Registeradresse außerhalb {40236/41259, 40793, 40795,
40797, 40799, 40801} im Schreibpfad ist ein Bug.

## 5. Sensorik: HA-Core-Integration `sma` (WebConnect)

- Rein lesend, Config: Host + Passwort + Gruppe (user/installer)
- Liefert **direktionale Paare** — passt 1:1 auf unsere vorhandene
  Fronius-Pair-Infrastruktur (synthetische Kombi-Sensoren):
  - `battery_power_charge_total` / `battery_power_discharge_total`
  - `metering_power_supplied` (Einspeisung) / `metering_power_absorbed` (Bezug)
  - `pv_power`, `battery_soc_total`
- Kapazitätssensor: vermutlich nicht vorhanden → manuelle Eingabe wie Kostal
  (kein bekanntes Modbus-Kapazitätsregister — prüfen, sonst Wizard-Feld)

Auto-Detect im Wizard: Entity-Registry-basiert auf `sma`-Config-Entries
(Muster identisch zu Fronius/Kostal), Pair-Suffixe statt Single-Sensoren.

## 6. Onboarding-Hürden

| Hürde | Schwere | Details |
|---|---|---|
| Modbus-TCP-Server aktivieren | **niedrig** | Lokales WebUI, Installateur-Gruppe — KEIN Grid-Guard-Code, kein PARAKO-Äquivalent; Anlagenbetreiber kommen i. d. R. selbst rein |
| **Sunny Home Manager 2** | **hoch** | „Prognosebasiertes Laden" MUSS deaktiviert werden (evcc-Requirement, Steuerungskonflikt). SHM regelt selbst am Netzpunkt — Koexistenz am Gerät testen. Bekannte Fälle, wo SHM-Firmware-Updates Modbus-Steuerpfade (40149/40151) zerstört haben; der CmpBMS-Pfad war davon nicht betroffen |
| Nur ein steuerndes System | mittel | Nicht parallel zu evcc-Batteriesteuerung o. ä. (wie bei allen Treibern) |

## 7. Treiber-Architektur (Entwurf)

`inverter/sma.py`, Muster = `kostal.py`:

- Config: `sma_modbus_host`, `sma_modbus_port` (Default 502), Unit-ID 3 konstant
- **Keepalive-Task** (aus kostal.py bewährt): schreibt den aktiven
  6-Register-Block alle 60 s neu; ±1-W-Jitter vermutlich unnötig (SMA-Doku
  fordert nur Refresh ≤ 300 s), Block-Write in einer FC16-Sequenz < 10 s
- Aktiver Zustand als Dataclass (OpMod, ChaMin/Max, DschMin/Max, GridWSpt)
  statt Tupel — 6 Werte je Modus
- Stop: Default-Block einmal schreiben, Keepalive stoppen → Watchdog-Rückfall
- Kein Hardware-Ziel-SOC (wie Kostal) → Optimizer überwacht, Watchdog = Failsafe
- `probe_sma` (read-only Wizard-Check): Geräteklasse/Seriennummer lesen
  (30053 Gerätetyp / 30057 Seriennummer aus SMA-Profil), SOC 30845,
  Batterieleistungen 31393/31395 — Erreichbarkeits- und Plausibilitätstest
- Grid-Import-Watchdog des Optimizers: SMA fällt in die „Pause"-Klasse
  (wie Huawei/Fronius/Kostal), nicht in die SolarEdge-Abbruch-Klasse

## 8. Beta-Checkliste (am Gerät verifizieren, VOR Release)

1. **GridWSpt-Vorzeichen** und: erzwingt es wirklich Einspeisung über den
   Hausverbrauch hinaus? (Kernfunktion Nacht-Entladung)
2. **OpMod-Adresse** 40236 vs. 41259 auf der Ziel-Firmware
3. Verhalten bei vorhandenem **SHM2** (Koexistenz, Übersteuerung)
4. HA-`sma`-Sensoren: Verfügbarkeit + Vorzeichen der Paare
5. Rückfallverhalten nach Watchdog-Timeout (Dauer, Zustand)
6. Block-Write-Timing: akzeptiert die Firmware 6 einzelne FC16-Writes
   innerhalb 10 s oder braucht es einen zusammenhängenden Multi-Write?

## 9. Blocker & nächster Schritt

**Blocker:** Kein Referenz-/Beta-Gerät verfügbar (Stand Aug 2026). Bei Kostal
gab es das Nutzer-Setup als Referenz; für SMA braucht es einen Beta-Tester aus
der EEG-Community (idealerweise STP Smart Energy + BYD, gerne mit SHM2 —
deckt Checkliste 3 gleich mit ab).

**Nächster Schritt:** Beta-Tester finden → Checkliste 1–6 mit einem
Test-Skript (read-only + kurzer überwachter Steuertest) abarbeiten → dann
Implementierung (Aufwand dank Kostal-Vorbild überschaubar: Treiber +
Pair-Detection + Wizard-Karte + Guide + Tests).

## Quellen

- evcc-Templates: [sma-hybrid.yaml](https://github.com/evcc-io/evcc/blob/master/templates/definition/meter/sma-hybrid.yaml), [sma-sbs-modbus.yaml](https://github.com/evcc-io/evcc/blob/master/templates/definition/meter/sma-sbs-modbus.yaml), [sma-si-modbus.yaml](https://github.com/evcc-io/evcc/blob/master/templates/definition/meter/sma-si-modbus.yaml)
- [Photovoltaikforum 251643 — HA-Steuerung der Batterie, 6-Parameter-Modbus-Methode](https://www.photovoltaikforum.com/thread/251643-home-assistant-steuerung-der-batterie-6-parameter-modbus-methode-b%C3%B6rsen-strompre/)
- [Photovoltaikforum 206718 — STP10.0-SE Register zum Laden](https://www.photovoltaikforum.com/thread/206718-sma-stp10-0-3se-40-welcher-modbus-register-zum-laden-der-batterie/?pageNo=23)
- [SMA Modbus Technische Beschreibung (SMA_Modbus-TB-de-13)](https://forum.iobroker.net/assets/uploads/files/721_sma_modbus-tb-de-13.pdf)
- [HA-Doku: SMA Solar Integration](https://www.home-assistant.io/integrations/sma/)
- evcc-Issues [#15294](https://github.com/evcc-io/evcc/issues/15294), [#13924](https://github.com/evcc-io/evcc/issues/13924) (SHM2/40149-Probleme)
