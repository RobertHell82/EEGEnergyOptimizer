# Inbetriebnahme deines EEG-Geräts (Home Assistant Green)

Dein Home Assistant Green wurde bereits vorbereitet: Alle benötigten Programme,
der EEG Energy Optimizer und der Fernzugang sind installiert. Diese Anleitung
führt dich durch die wenigen Schritte, bis dein System läuft.

---

## Schritt 1: Gerät anschließen (Strom & Netzwerk)

1. **Netzwerk:** Stecke das **Netzwerkkabel** vom Gerät in einen freien LAN-Port
   deines Routers bzw. verbinde es an einem passenden Ort mit Deinem Netzwerk.
2. **Strom:** Verbinde das **Netzteil** mit dem Gerät und der Steckdose. Das
   Gerät startet automatisch.
3. **Warten:** Der erste Start dauert einige Minuten — warte, bis die Status-LED
   ruhig leuchtet (nicht mehr blinkt).

> [!TIP]
> Das Gerät bezieht seine Netzwerkadresse **automatisch** vom Router (DHCP). Am
> Router musst du nichts einstellen.

---

## Schritt 2: Erste Anmeldung

1. Öffne an einem Gerät **im selben Netzwerk** einen Browser.
2. Rufe **`http://homeassistant.local:8123`** auf.
3. Melde dich auf der **Anmeldeseite** mit dem **Benutzernamen und Passwort** an,
   die du von uns erhalten hast.

> [!NOTE]
> Funktioniert `homeassistant.local` nicht, findest du die IP-Adresse des Geräts
> in der Geräteliste deines Routers und rufst sie direkt auf, z.B.
> `http://192.168.1.50:8123`.

---

## Schritt 3: Basiseinrichtung

| Einstellung | Wo | Was |
|---|---|---|
| **Standort** (wichtigster Schritt!) | Einstellungen → System → Allgemein | Ab Werk auf **„Linz Hauptplatz"** voreingestellt — **unbedingt auf deine eigene Adresse ändern** (Karte oder Lat/Lon), Höhe & Zeitzone prüfen. Ohne korrekten Standort berechnet der Optimizer Sonnenauf-/-untergang und PV-Prognose mit falschen Zeiten. |
| **Passwort ändern** (Benutzer `ewa-mitglied`) | Profil (Name unten links) → *Passwort ändern* | Voreingestelltes Passwort durch ein eigenes ersetzen |

---

## Schritt 4: PV-Prognose (Solcast)

Eine wesentliche Vorraussetzung ist die Installation und Einrichtung der PV-Prognose. Die beste Option ist hier Solcast, jedes Mitglied muss sich hier ein **eigenes, kostenloses** Konto erstellen und die Daten der PV-Anlage erfassen.

→ **[Solcast Solar einrichten](../guides/solcast.md)** _(Konto anlegen, PV-Anlage erfassen, API-Key in Home Assistant eintragen, Prognose-Sensoren aktivieren)_

> [!Hinweis]
> Alternativ kannst du **[Forecast.Solar](../guides/forecast_solar.md)** nutzen —
> ohne Registrierung, aber etwas ungenauer. Es muss als Integration hinzugefügt werden.

---

## Schritt 5: Wechselrichter anbinden

Damit der Optimizer deinen Speicher steuern kann, wird er mit deinem
Wechselrichter verbunden. Folge der Anleitung für deinen Typ:

| Wechselrichter | Anleitung |
|---|---|
| **Huawei SUN2000** | [Huawei Solar einrichten](../guides/huawei.md) + [Akkukapazität-Sensor](../guides/capacity_sensor.md) |
| **Fronius Gen24** | [Fronius Gen24 einrichten](../guides/fronius.md) |
| **SolaX Gen4+** | [SolaX Modbus einrichten](../guides/solax.md) |
| **SolarEdge StorEdge** | [SolarEdge Modbus Multi einrichten](../guides/solaredge.md) |

---

## Schritt 6: EEG Optimizer fertig einrichten

Zum Schluss verbindest du im **EEG Optimizer Panel** (Seitenleiste) den Optimizer
mit deiner Anlage. Das Panel führt dich durch:

1. Voraussetzungsprüfung
2. Wechselrichtertyp wählen + automatische Sensorerkennung
3. Batterie- & PV-Sensoren zuordnen
4. Prognosequelle wählen (Solcast / Forecast.Solar)
5. Optimizer-Einstellungen (Morgenfenster, Entladezeit, Min-SOC, Sicherheitspuffer)
6. PeakShare-Community wählen
7. Wechselrichter-Verbindungstest

> [!TIP]
> Bei jedem Schritt im Panel gibt es einen **„Anleitung"-Button**, der genau die
> oben verlinkten Hilfen direkt anzeigt.

---

## Fertig 🎉

Wenn alle Schritte erledigt sind, läuft der EEG Energy Optimizer und steuert
deinen Speicher passend zu den Einspeise-Zeitfenstern der Energiegemeinschaft.
Den Status siehst du jederzeit im **EEG Optimizer Panel**.

> [!TIP]
> Auf deinem Gerät ist ein **Fernzugang für die EEG** eingerichtet. Zweck ist eine
> einfache Unterstützung beim Setup. Sobald das Gerät einmal läuft, kann dieser bei
> Bedarf gerne deaktiviert werden.
