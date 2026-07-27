# EEG Energy Optimizer

HACS-kompatible Home Assistant Integration für vorausschauendes Batteriemanagement, optimiert für Energiegemeinschaften (EEG) im DACH-Raum.

## Funktionen

- **Morgen-Einspeisung** — blockiert die Batterieladung, damit PV-Überschüsse ins EEG-Netz eingespeist werden
- **Nacht-Entladung** — entlädt die Batterie während der Spitzenverbrauchszeiten der Gemeinschaft
- **Einspeisebegrenzung optimieren** (Huawei/Fronius) — lädt PV-Überschuss oberhalb des Einspeiselimits in die Batterie, statt ihn vom Wechselrichter abregeln zu lassen
- **PeakShare-Integration** — optimiert das Entladefenster automatisch nach dem realen Bedarf deiner EEG-Community (Sliding-Window über Community-Bedarfsprognose)
- **Dynamischer Min-SOC** — reserviert automatisch genug Batterie für den Nachtverbrauch des Haushalts
- **PV-Prognose** — Solcast Solar und Forecast.Solar Unterstützung mit 7-Tage-Ausblick
- **Verbrauchsprofil** — lernt stündliche Verbrauchsmuster pro Wochentag aus den HA-Recorder-Daten
- **Live-Dashboard** — Sidebar-Panel mit Energiefluss, Diagrammen, PeakShare-Bedarfskurve, manueller Wechselrichtersteuerung und Aktivitätsprotokoll
- **Einrichtungsassistent** — schrittweises Onboarding mit automatischer Sensorerkennung

### EEG-Statistik

Der EEG Energy Optimizer sendet anonymisierte Diagnose- und Wirksamkeitsdaten an einen vom Maintainer betriebenen Cloudflare-Backend. Damit lassen sich Schwachstellen schneller finden und die Wirksamkeit der EEG-Steuerung über mehrere Anlagen hinweg auswerten — ohne Personenbezug. Die Funktion ist bei **neuen Installationen standardmäßig aktiv**; deaktivieren und vollständig löschen lässt sie sich jederzeit im Panel unter *Einstellungen → EEG-Statistik*. Bestehende Installationen behalten ihre vorherige Einstellung (Default war zuvor *aus*).

#### Was übermittelt wird

| Kategorie | Frequenz | Inhalt |
|-----------|----------|--------|
| **Profil** | bei Setup, Restart, Settings-Change | App-Version, HA-Version, Wechselrichter-Typ, Batterie-Kapazität, PV-Peak, Prognose-Quelle, Länder-ISO-Code, ausgewählte EEG-Community (sofern PeakShare aktiv), gefilterte Settings (Whitelist) |
| **Snapshot** | alle 30 Min, gebündelt 1×/h | Zeitstempel, Zustand (Normal/Morgen-Einspeisung/Nacht-Entladung), Modus (Ein/Test), SOC %, PV-/Verbrauchs-/Netz-/Batterie-Leistung, dynamischer Min-SOC, Hysterese-Flag |
| **State-Change** | bei jedem Übergang (sofort) | Zeitstempel, Übergang (von→nach), Begründungs-Codes (`reasons`/`blocked_by`), Snapshot |
| **Outcome** | nach Block-Ende | Block-Typ, Start/Ende, Dauer, ins Netz eingespeiste kWh, Peak-Leistung, SOC-Start/-Ende, predicted-vs-actual PV/Verbrauch |
| **Failure** | bei Auftreten (mit Dedup) | Zeitstempel, Kategorie, Schweregrad, gehashte Fehlermeldung, Kontext-JSON |

Die Settings-Whitelist enthält ausschließlich numerische/kategorische Konfigurationswerte (Sicherheitspuffer, Mindest-SOC, Morgenfenster-Endzeit, Entlade-Leistung etc.) — **keine Entity-IDs**, keine Sensor-Namen.

#### Was nicht übermittelt wird

- Keine Entity-IDs / Sensor-Namen
- Keine IP-Adressen (werden serverseitig nicht persistiert)
- Kein Anlagenname, keine Adresse, keine Geokoordinaten
- Keine Mitgliedsdaten der Energiegemeinschaft
- Keine sonstigen personenbezogenen Daten

#### Identifikation

Pro Anlage wird einmalig eine zufällige **UUIDv4** + ein **API-Key** erzeugt und lokal gespeichert. Es gibt keinen Bezug zu HA-Account, IP, Hardware-ID oder sonstigen Identifikatoren. Beim Klick auf „Daten löschen" werden alle Daten dieser Anlage serverseitig kaskadiert gelöscht und die UUID lokal entfernt.

## Unterstützte Wechselrichter

- **Huawei SUN2000** (via [Huawei Solar](https://github.com/wlcrs/huawei_solar) Integration) — Single oder Master/Slave (mehrere Wechselrichter + Batterien). Direkte Anbindung an den Wechselrichter/Dongle oder über das EMMA-Energiemanagement (`sensor.emma_*`-Sensoren, Netz-Vorzeichen wird automatisch korrigiert — siehe [Huawei-Guide](docs/guides/huawei.md)).
- **Fronius Gen24** (via native [Fronius](https://www.home-assistant.io/integrations/fronius/) Integration + direkte Modbus TCP Steuerung)
- **SolarEdge StorEdge** (via [SolarEdge Modbus Multi](https://github.com/WillCodeForCats/solaredge-modbus-multi) Integration) — max. 2 Wechselrichter
- **SolaX Gen4+** (via [SolaX Modbus](https://github.com/wills106/homeassistant-solax-modbus) Integration)

### Hinweis zu Fronius Gen24

Die Fronius-Steuerung nutzt direkte Modbus TCP Verbindung zum Wechselrichter (SunSpec Model 124). Sensordaten (PV, Batterie, Netz) werden über die native HA Fronius Integration (Solar API) gelesen. Es wird keine zusätzliche HACS-Integration benötigt — nur die Fronius Core Integration und eine Netzwerkverbindung zum Wechselrichter (Standard-Port 502).

### Hinweis zu SolarEdge NVRAM-Schreibvorgängen

Die SolarEdge-Steuerung schreibt Modbus-Register, die im Flash-Speicher (NVRAM) des Wechselrichters persistiert werden. Flash-Speicher hat eine begrenzte Anzahl Schreibzyklen (typisch 100.000+).

Die Integration minimiert Schreibvorgänge: Im Worst Case (jeden Tag Morgen-Blockierung + Nacht-Entladung) sind es **max. ~12 Writes pro Tag**. An bewölkten Tagen oder im Winter 0 Writes. Realistisch im Jahresdurchschnitt ~7 Writes/Tag — das ergibt bei 100.000 Zyklen **~39 Jahre Lebensdauer**.

## Installation

1. HACS in Home Assistant öffnen
2. Oben rechts auf die drei Punkte klicken
3. "Benutzerdefinierte Repositories" auswählen
4. Repository-URL eingeben und als Kategorie "Integration" wählen
5. "Hinzufügen" klicken und "EEG Energy Optimizer" installieren
6. Home Assistant neu starten

Ausführliche Schritt-für-Schritt-Anleitungen (inkl. HACS-Installation, Wechselrichter-Anbindung und PV-Prognose-Einrichtung) gibt es in der **[Dokumentation](docs/README.md)**.

## Konfiguration

Nach der Installation die Integration hinzufügen:

**Einstellungen > Geräte & Dienste > Integration hinzufügen > EEG Energy Optimizer**

Das Sidebar-Panel (`/eeg-optimizer`) führt durch die Einrichtung:
1. Voraussetzungsprüfung
2. Wechselrichtertyp wählen + automatische Sensorerkennung
3. Batterie- & PV-Sensoren zuordnen
4. Prognosequelle wählen (Solcast / Forecast.Solar)
5. Optimizer-Einstellungen (Morgenfenster, Entladezeit, Min-SOC, Sicherheitspuffer)
6. PeakShare-Community wählen (optional — aktiviert das dynamische Entladefenster)
7. Wechselrichter-Verbindungstest

## Funktionsweise

### Morgen-Einspeisung

<img src="https://raw.githubusercontent.com/RobertHell82/EEGEnergyOptimizer/main/docs/delayed-charging.svg" alt="Morgen-Einspeisung" width="700">

Die Morgen-Einspeisung stellt sicher, dass PV-Überschüsse bevorzugt am Morgen in das Netz der Energiegemeinschaft eingespeist werden — also dann, wenn die Gemeinschaft den Strom dringend braucht. Ohne diese Funktion würde die Batterie den PV-Überschuss sofort ab Sonnenaufgang aufladen. Die Einspeisung in die Energiegemeinschaft würde dann erst ab Mittag erfolgen, wenn ohnehin genug Strom vorhanden ist.

**Funktionsweise:** Die Batterieladung wird ab einer Stunde vor Sonnenaufgang blockiert und frühestens um die konfigurierte Endzeit (Standard: 11:00 Uhr) wieder freigegeben. Die Blockierung erfolgt nur, solange die PV-Prognose des aktuellen Tages den Gesamtbedarf übersteigt.

**Der Gesamtbedarf setzt sich zusammen aus:**
- Geschätzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang
- Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)
- Fehlende Energie zum Vollladen der Batterie (basierend auf aktuellem SOC)

Der Stromverbrauch wird anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 4 Wochen).

Reicht die PV-Prognose nicht aus, um den Gesamtbedarf zu decken, wird die Batterie sofort geladen — damit der Haushalt bis zum Abend versorgt ist.

### Nacht-Entladung

<img src="https://raw.githubusercontent.com/RobertHell82/EEGEnergyOptimizer/main/docs/evening-discharge.svg" alt="Nacht-Entladung" width="700">

Die Nacht-Entladung speist unter Tags gewonnene Energie, die der eigene Haushalt nicht benötigt, um über die Nacht zu kommen, in die Energiegemeinschaft ein. So steht Strom zu einem Zeitpunkt zur Verfügung, an dem ansonsten keine PV-Erzeugung im Netz vorhanden ist.

**Funktionsweise:** Die Batterie wird mit einstellbarer Leistung entladen, bis der dynamisch berechnete Ziel-SOC erreicht ist. Die Entladung endet spätestens um 04:00 Uhr.

Der Startzeitpunkt richtet sich nach dem gewählten Modus:
- **Mit PeakShare (empfohlen):** Das Entladefenster wird automatisch anhand der Bedarfsprognose der EEG-Community berechnet (Sliding-Window-Algorithmus findet den Zeitblock mit dem höchsten Gemeinschaftsbedarf)
- **Ohne PeakShare:** Feste Startzeit (Standard: 20:00 Uhr)

**Der Ziel-SOC ergibt sich aus:**
- Konfigurierter Mindest-SOC der Batterie
- Geschätzter Stromverbrauch in der Nacht (Entladestart bis eine Stunde nach Sonnenaufgang)
- Sicherheitspuffer auf den Nachtverbrauch (konfigurierbar, Standard: 25%)

**Die Entladung erfolgt nur, wenn alle Bedingungen erfüllt sind:**
- Aktueller SOC liegt über dem berechneten Ziel-SOC
- Die PV-Prognose für morgen deckt den erwarteten Gesamtbedarf

**Hysterese:** Wurde eine Aktion (Morgen-Einspeisung oder Nacht-Entladung) am selben Tag bereits aktiviert und dann deaktiviert, gelten strengere Schwellen für eine erneute Aktivierung. So wird ein schnelles Hin-und-Herspringen zwischen Zuständen verhindert.

### Einspeisebegrenzung optimieren

Viele Netzbetreiber begrenzen die maximale Einspeiseleistung (z. B. 4 kW). An sonnigen Tagen produziert die Anlage oft mehr, als eingespeist werden darf — der Wechselrichter regelt den Überschuss dann ab, und diese Energie geht verloren. Diese Optimierung lädt den Überschuss stattdessen in die Batterie und hält die Netzeinspeisung genau am erlaubten Limit.

**Funktionsweise:** Sobald die Einspeisung am Limit „klebt" (Anzeichen für Abregelung), erhöht der Optimizer die Batterie-Ladeleistung schrittweise, bis der Überschuss geladen wird. Die Regelung ist ein Feedback auf die gemessene Netzeinspeisung, das alle 60 Sekunden nachjustiert — asymmetrisch: langsames Anheben, aber sofortiges Absenken bei PV-Einbruch, damit die Batterie nie aus dem Netz lädt.

- Nur für **Huawei SUN2000** und **Fronius Gen24** (variable Ladeleistungs-Begrenzung), standardmäßig **aus**
- Kombiniert sich mit der Morgen-Einspeisung — auch dort wird nur der Anteil oberhalb des Limits geladen
- Ersetzt **nicht** die harte, netzseitig verpflichtende Einspeisebegrenzung des Wechselrichters; bei voller Batterie regelt der Wechselrichter wie gewohnt ab

**Der Gesamtbedarf für morgen setzt sich zusammen aus:**
- Geschätzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang
- Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)
- Benötigte Energie zum Laden der Batterie (von Mindest-SOC auf 100%)

Der Stromverbrauch wird jeweils anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 4 Wochen).

So wird sichergestellt, dass die Batterie am nächsten Tag wieder vollständig über PV geladen werden kann und der Haushalt versorgt ist.

## Voraussetzungen

- Home Assistant 2025.1.0 oder neuer
- Eine unterstützte Wechselrichter-Integration installiert und konfiguriert (Huawei Solar, Fronius, SolaX Modbus oder SolarEdge Modbus Multi)
- Eine PV-Prognose-Integration (Solcast Solar oder Forecast.Solar)

## Lizenz

MIT
