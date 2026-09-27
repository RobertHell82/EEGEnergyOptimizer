# Huawei Akkukapazität-Sensor aktivieren

> [!CAUTION]
> **Diese Version (1.x) ist veraltet und wird nicht mehr weiterentwickelt.**
> Der EEG Energy Optimizer geht als Version 2 weiter: **[EEGEnergyOptimizer2](https://github.com/RobertHell82/EEGEnergyOptimizer2)** — diese Seite dort: [docs/guides/capacity_sensor.md](https://github.com/RobertHell82/EEGEnergyOptimizer2/blob/main/docs/guides/capacity_sensor.md).

Der Sensor für die Akkukapazität ist bei Huawei Solar standardmäßig deaktiviert (Diagnostic-Sensor). So aktivierst du ihn:

1. Gehe zu **Einstellungen → Geräte & Dienste**
2. Klicke auf **Huawei Solar**
3. Klicke auf dein **Batterie-Gerät** (z.B. „LUNA2000")
4. Scrolle nach unten zur Entitäten-Liste
5. Klicke oben rechts auf **„Entitäten die nicht auf dem Dashboard angezeigt werden"** (oder den Filter für deaktivierte Entitäten)
6. Suche nach **„Akkukapazität"** oder **„Storage Rated Capacity"**
7. Klicke auf die Entität und dann auf **„Aktivieren"**
8. Warte ca. 30 Sekunden bis der Sensor Daten liefert

_Der Sensor heißt typischerweise `sensor.batterien_akkukapazitat` und zeigt die Kapazität in Wh an (z.B. 15000 für 15 kWh)._

_**Tipp:** Wenn du den Sensor nicht findest, kannst du die Kapazität auch manuell eingeben._
