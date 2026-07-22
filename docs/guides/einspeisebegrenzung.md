# Einspeisebegrenzung optimieren

Viele Netzbetreiber begrenzen, wie viel Leistung deine PV-Anlage ins Netz einspeisen darf (z. B. 4 kW). An sonnigen Tagen produziert die Anlage oft mehr, als eingespeist werden darf — der Wechselrichter **regelt den Überschuss dann ab, und diese Energie geht verloren**.

Diese Optimierung lädt den Überschuss stattdessen in die Batterie und hält die Netzeinspeisung dabei genau am erlaubten Limit.

## Voraussetzungen

- Wechselrichter **Huawei SUN2000** oder **Fronius Gen24** (nur diese erlauben eine gezielte, variable Ladeleistungs-Begrenzung)
- Ein korrekt konfigurierter **Netzleistungs-Sensor** (misst Einspeisung/Bezug)
- Eine Batterie mit freier Aufnahmekapazität

## So funktioniert es

Sobald die Netzeinspeisung am Limit „klebt" — das Anzeichen dafür, dass der Wechselrichter gerade abregelt — erhöht der Optimizer die Batterie-Ladeleistung schrittweise, bis der Überschuss vollständig in die Batterie fließt und die Einspeisung knapp unter dem Limit bleibt.

- **Nachregelung alle 60 Sekunden**: langsames, vorsichtiges Anheben der Ladeleistung.
- **Sofortiger Netzbezug-Schutz**: Bricht die PV-Leistung ein (z. B. Wolke), wird die Ladeleistung umgehend reduziert, damit die Batterie **niemals aus dem Netz** lädt.
- **Kombiniert mit der Morgen-Einspeisung**: Auch während der morgendlichen Einspeisung wird nur der Anteil oberhalb des Limits geladen — der Rest fließt weiter in die Energiegemeinschaft.

## Konfiguration

| Feld | Bedeutung |
|---|---|
| **Einspeisebegrenzung optimieren** | Schaltet die Funktion ein/aus (Standard: aus) |
| **Einspeiselimit (kW)** | Die maximale Einspeiseleistung laut Vorgabe deines Netzbetreibers (z. B. 4) |
| **PV-Spitzenleistung (kWp)** | Optional. Nur für die serverseitige Plausibilitätsprüfung der Prognosewerte — für die Regelung selbst nicht erforderlich |

> [!NOTE]
> **Hinweis:** Diese Funktion ersetzt nicht die harte, netzseitig verpflichtende Einspeisebegrenzung deines Wechselrichters — die bleibt beim Gerät. Sie optimiert nur, ob der Überschuss geladen statt abgeregelt wird.

> [!WARNING]
> **Volle Batterie:** Ist die Batterie voll, kann kein Überschuss mehr aufgenommen werden — dann regelt der Wechselrichter wie gewohnt ab. Das ist unvermeidbar und kein Fehler.
