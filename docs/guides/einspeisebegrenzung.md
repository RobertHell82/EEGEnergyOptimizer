# Einspeisebegrenzung optimieren

Viele Netzbetreiber begrenzen, wie viel Leistung deine PV-Anlage ins Netz einspeisen darf (z. B. 4 kW). Normalerweise lädt die Batterie zuerst mit voller Leistung — ist sie voll, **regelt der Wechselrichter alles über dem Limit ab, und diese Energie geht verloren**.

Diese Optimierung dreht das um: Solange die Batterie laut Prognose heute sicher noch voll wird, speist der PV-Überschuss **bis zum erlaubten Limit ins Netz** ein — nur der Anteil darüber lädt die Batterie. So wird maximal in die Energiegemeinschaft eingespeist, nichts abgeregelt, und die Batterie füllt sich trotzdem — verteilt über den Tag.

## Voraussetzungen

- Wechselrichter **Huawei SUN2000** oder **Fronius Gen24** (nur diese erlauben eine gezielte, variable Ladeleistungs-Begrenzung)
- Ein korrekt konfigurierter **Netzleistungs-Sensor** (misst Einspeisung/Bezug)
- Eine **PV-Prognose** (Solcast / Forecast.Solar) — sie entscheidet, ob die Batterie heute sicher noch voll wird
- Eine Batterie mit freier Aufnahmekapazität

## So funktioniert es

Die Optimierung wird aktiv, wenn die PV-Restprognose für heute den restlichen Tagesverbrauch (inkl. Sicherheitspuffer) **plus** die noch fehlende Batterieenergie übersteigt — dieselbe Prüfung wie bei der Morgen-Einspeisung, aber ohne deren Zeitfenster. Nur dann darf das Laden gedrosselt werden; reicht die Prognose nicht, lädt die Batterie ganz normal mit voller Leistung (die Batterie hat Vorrang).

Ist die Optimierung aktiv:

- **Einspeisung unter dem Limit**: Das Laden ist blockiert — der gesamte Überschuss fließt ins Netz.
- **Einspeisung am Limit** (der Wechselrichter würde abregeln): Die Batterie-Ladeleistung wird schrittweise erhöht, bis genau der Anteil oberhalb des Limits in die Batterie fließt und die Einspeisung am Limit bleibt.
- **Nachregelung alle 60 Sekunden**: langsames, vorsichtiges Anheben der Ladeleistung.
- **Sofortiger Netzbezug-Schutz**: Bricht die PV-Leistung ein (z. B. Wolke), wird die Ladeleistung umgehend reduziert, damit die Batterie **niemals aus dem Netz** lädt.
- **Kombiniert mit der Morgen-Einspeisung**: Auch während der morgendlichen Einspeisung wird nur der Anteil oberhalb des Limits geladen — der Rest fließt weiter in die Energiegemeinschaft.
- Sinkt die Prognose im Tagesverlauf unter den Restbedarf, deaktiviert sich die Optimierung und die Batterie lädt wieder mit voller Leistung, damit sie bis zum Abend voll wird.

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
