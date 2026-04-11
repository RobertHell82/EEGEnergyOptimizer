# EEG Energy Optimizer

HACS-kompatible Home Assistant Integration für vorausschauendes Batteriemanagement, optimiert für Energiegemeinschaften (EEG) im DACH-Raum.

## Funktionen

- **Morgen-Einspeisung** — blockiert die Batterieladung, damit PV-Überschüsse ins EEG-Netz eingespeist werden
- **Abend-Entladung** — entlädt die Batterie während der Spitzenverbrauchszeiten der Gemeinschaft
- **Dynamischer Min-SOC** — reserviert automatisch genug Batterie für den Nachtverbrauch des Haushalts
- **PV-Prognose** — Solcast Solar und Forecast.Solar Unterstützung mit 7-Tage-Ausblick
- **Verbrauchsprofil** — lernt stündliche Verbrauchsmuster pro Wochentag aus den HA-Recorder-Daten
- **Live-Dashboard** — Sidebar-Panel mit Energiefluss, Diagrammen, manueller Wechselrichtersteuerung und Aktivitätsprotokoll
- **Einrichtungsassistent** — schrittweises Onboarding mit automatischer Sensorerkennung

## Unterstützte Wechselrichter

- **Huawei SUN2000** (via [Huawei Solar](https://github.com/wlcrs/huawei_solar) Integration)
- **SolarEdge StorEdge** (via [SolarEdge Modbus Multi](https://github.com/WillCodeForCats/solaredge-modbus-multi) Integration) — max. 2 Wechselrichter
- **SolaX Gen4+** (via [SolaX Modbus](https://github.com/wills106/homeassistant-solax-modbus) Integration)

### Hinweis zu SolarEdge NVRAM-Schreibvorgängen

Die SolarEdge-Steuerung schreibt Modbus-Register, die im Flash-Speicher (NVRAM) des Wechselrichters persistiert werden. Flash-Speicher hat eine begrenzte Anzahl Schreibzyklen (typisch 100.000+).

Die Integration minimiert Schreibvorgänge: Im Worst Case (jeden Tag Morgen-Blockierung + Abend-Entladung) sind es **max. ~12 Writes pro Tag**. An bewölkten Tagen oder im Winter 0 Writes. Realistisch im Jahresdurchschnitt ~7 Writes/Tag — das ergibt bei 100.000 Zyklen **~39 Jahre Lebensdauer**.

## Installation

1. HACS in Home Assistant öffnen
2. Oben rechts auf die drei Punkte klicken
3. "Benutzerdefinierte Repositories" auswählen
4. Repository-URL eingeben und als Kategorie "Integration" wählen
5. "Hinzufügen" klicken und "EEG Energy Optimizer" installieren
6. Home Assistant neu starten

## Konfiguration

Nach der Installation die Integration hinzufügen:

**Einstellungen > Geräte & Dienste > Integration hinzufügen > EEG Energy Optimizer**

Das Sidebar-Panel (`/eeg-optimizer`) führt durch die Einrichtung:
1. Voraussetzungsprüfung
2. Wechselrichtertyp wählen + automatische Sensorerkennung
3. Batterie- & PV-Sensoren zuordnen
4. Prognosequelle wählen (Solcast / Forecast.Solar)
5. Optimizer-Einstellungen (Morgenfenster, Entladezeit, Min-SOC, Sicherheitspuffer)
6. Wechselrichter-Verbindungstest

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

### Abend-Entladung (Nachteinspeisung)

<img src="https://raw.githubusercontent.com/RobertHell82/EEGEnergyOptimizer/main/docs/evening-discharge.svg" alt="Abend-Entladung" width="700">

Die Abend-Entladung speist unter Tags gewonnene Energie, die der eigene Haushalt nicht benötigt, um über die Nacht zu kommen, in die Energiegemeinschaft ein. So steht Strom zu einem Zeitpunkt zur Verfügung, an dem ansonsten keine PV-Erzeugung im Netz vorhanden ist.

**Funktionsweise:** Ab der konfigurierten Startzeit (Standard: 20:00 Uhr) wird die Batterie mit einstellbarer Leistung entladen, bis der dynamisch berechnete Ziel-SOC erreicht ist.

**Der Ziel-SOC ergibt sich aus:**
- Konfigurierter Mindest-SOC der Batterie
- Geschätzter Stromverbrauch in der Nacht (Entladestart bis eine Stunde nach Sonnenaufgang)
- Sicherheitspuffer auf den Nachtverbrauch (konfigurierbar, Standard: 25%)

**Die Entladung erfolgt nur, wenn alle Bedingungen erfüllt sind:**
- Aktueller SOC liegt über dem berechneten Ziel-SOC
- Die PV-Prognose für morgen deckt den erwarteten Gesamtbedarf

**Der Gesamtbedarf für morgen setzt sich zusammen aus:**
- Geschätzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang
- Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)
- Benötigte Energie zum Laden der Batterie (von Mindest-SOC auf 100%)

Der Stromverbrauch wird jeweils anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 4 Wochen).

So wird sichergestellt, dass die Batterie am nächsten Tag wieder vollständig über PV geladen werden kann und der Haushalt versorgt ist.

## Voraussetzungen

- Home Assistant 2025.1.0 oder neuer
- Eine unterstützte Wechselrichter-Integration installiert und konfiguriert (Huawei Solar, SolaX Modbus oder SolarEdge Modbus Multi)
- Eine PV-Prognose-Integration (Solcast Solar oder Forecast.Solar)

## Lizenz

MIT
