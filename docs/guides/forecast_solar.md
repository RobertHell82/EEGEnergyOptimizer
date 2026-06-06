# Forecast.Solar einrichten

## 1. Integration hinzufügen

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„Forecast.Solar"**
3. Klicke auf **Forecast.Solar**

## 2. Anlagendaten eingeben

Forecast.Solar berechnet die Prognose anhand deiner PV-Anlage:

| Feld | Wert |
|---|---|
| **Name** | Frei wählbar, z.B. „PV Süd" |
| **API Key** | Leer lassen (kostenlos) oder dein Forecast.Solar API-Key |
| **Latitude / Longitude** | Automatisch aus HA-Konfiguration — prüfen, nicht ändern |
| **Dachneigung (Declination)** | Neigung in Grad. Typisch DACH-Region: **30–35°**, Flachdach: 0–10° |
| **Azimuth** | Himmelsrichtung der Module:<br>**0° = Nord**, 90° = Ost, **180° = Süd**, 270° = West<br>_Achtung: HA nutzt Kompass-Konvention (0=Nord), nicht die Forecast.Solar-Website (0=Süd)!_ |
| **Leistung (kWp)** | Anlagenleistung **in Watt**, nicht kWp!<br>Beispiel: 10 kWp → **10000** eingeben |

_**Tipp:** Die häufigsten Fehler sind falscher Azimuth (Süd = 180°, nicht 0°) und kWp statt Watt._

## 3. Mehrere Ausrichtungen (Ost/West)

Bei Modulen in verschiedene Richtungen die Integration **mehrmals hinzufügen** — einmal pro Ausrichtung (z.B. „PV Ost" mit Azimuth 90° und „PV West" mit 270°).

_Die zweite Instanz erstellt Sensoren mit `_2` Suffix (z.B. `sensor.energy_production_tomorrow_2`)._

## 4. Prüfen

1. Warte 1–2 Minuten nach der Einrichtung
2. Prüfe unter **Entwicklerwerkzeuge → Zustände**: Suche nach `energy_production`
3. Die Sensoren `sensor.energy_production_today_remaining` und `sensor.energy_production_tomorrow` sollten kWh-Werte zeigen
4. Kehre hierher zurück — die Sensoren werden automatisch zugeordnet

_**Kostenlose Version:** 12 Abrufe/Stunde, Prognose für heute + morgen, 1h-Auflösung — vollkommen ausreichend für den EEG Energy Optimizer._
