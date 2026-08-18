# EEG Energy Optimizer über HACS installieren

Der EEG Energy Optimizer wird als **benutzerdefiniertes Repository** (Custom Repository) über HACS installiert.

> [!NOTE]
> **Voraussetzung:** [HACS muss installiert sein](hacs.md).

## 1. Repository in HACS hinzufügen

1. Öffne **HACS** in der Seitenleiste
2. Klicke oben rechts auf das **Drei-Punkte-Menü → Benutzerdefinierte Repositories**
3. Trage ein:
   - **Repository:** `https://github.com/RobertHell82/EEGEnergyOptimizer`
   - **Typ:** `Integration`
4. Klicke auf **Hinzufügen** und schließe den Dialog

## 2. Integration herunterladen

1. Suche in HACS nach **„EEG Energy Optimizer"**
2. Öffne den Eintrag und klicke auf **Herunterladen**
3. **Starte Home Assistant neu** (Einstellungen → System → Power-Symbol → Neu starten)

## 3. Integration einrichten

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„EEG Energy Optimizer"** und füge ihn hinzu
3. In der Seitenleiste erscheint der Eintrag **EEG Optimizer** — das Panel führt dich durch die restliche Einrichtung:
   1. Voraussetzungsprüfung
   2. Wechselrichtertyp wählen + automatische Sensorerkennung
   3. Batterie- & PV-Sensoren zuordnen
   4. Prognosequelle wählen (Solcast / Forecast.Solar)
   5. Optimizer-Einstellungen (Morgenfenster, Entladezeit, Min-SOC, Sicherheitspuffer)
   6. PeakShare-Community wählen (optional)
   7. Wechselrichter-Verbindungstest

## Voraussetzungen für den Betrieb

- Home Assistant **2025.1.0** oder neuer
- Eine unterstützte **Wechselrichter-Integration**, eingerichtet und funktionsfähig:
  - [Fronius Gen24](../guides/fronius.md)
  - [Huawei SUN2000](../guides/huawei.md)
  - [Kostal Plenticore](../guides/kostal.md) (Beta)
  - [SMA Smart Energy](../guides/sma.md) (Beta)
  - [SolarEdge StorEdge](../guides/solaredge.md)
  - [SolaX Gen4+](../guides/solax.md)
- Eine **PV-Prognose-Integration**:
  - [Solcast Solar](../guides/solcast.md) (empfohlen)
  - [Forecast.Solar](../guides/forecast_solar.md)

Die Wechselrichter- und Prognose-Anleitungen sind auch direkt im Einrichtungsassistenten über die „Anleitung"-Buttons erreichbar.

## Updates

Updates erscheinen automatisch in HACS bzw. unter **Einstellungen → Geräte & Dienste → Updates**, sobald eine neue Version veröffentlicht wird. Nach einem Update Home Assistant neu starten.
