# Inbetriebnahme deines EEG-Geräts (Home Assistant Green)

Dein Home Assistant Green wurde bereits vorbereitet: Alle benötigten Programme,
der EEG Energy Optimizer und der Fernzugang sind installiert. Diese Anleitung
führt dich durch die wenigen Schritte, bis dein System läuft.

---

## Schritt 1: Gerät anschließen (Strom & Netzwerk)

1. **Netzwerk:** Verbinde das **Netzwerkkabel** mit dem Gerät und einem freien
   LAN-Port deines Routers (oder einer Netzwerkdose in deinem Heimnetz).
2. **Strom:** Verbinde das **Netzteil** mit dem Gerät und der Steckdose. Das
   Gerät startet automatisch.
3. **Warten:** Der erste Start dauert einige Minuten — warte, bis die Status-LED
   ruhig leuchtet (nicht mehr blinkt).

> [!TIP]
> Das Gerät bezieht seine Netzwerkadresse **automatisch** vom Router (DHCP). Am
> Router musst du nichts einstellen.

---

## Schritt 2: Erste Anmeldung

1. Öffne auf einem PC, Tablet oder Handy **im selben Netzwerk** einen Browser.
2. Rufe **`http://homeassistant.local:8123`** auf — das ist die
   **Home-Assistant-Oberfläche** deines Geräts. Alle weiteren Schritte dieser
   Anleitung finden dort statt.
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
| **Standort** (wichtigster Schritt!) | Einstellungen → System → Allgemein | Ab Werk auf **„Linz Hauptplatz"** voreingestellt — **unbedingt auf deine eigene Adresse ändern** (auf der Karte oder per Koordinaten), Höhe & Zeitzone prüfen. Ohne korrekten Standort berechnet der Optimizer Sonnenauf-/-untergang und PV-Prognose mit falschen Zeiten. |
| **Passwort ändern** (Benutzer `ewa-mitglied`) | Profil (Name unten links) → *Passwort ändern* | Voreingestelltes Passwort durch ein eigenes ersetzen |

---

## Schritt 4: PV-Prognose (Solcast)

Der Optimizer braucht eine PV-Prognose für deine Anlage. Empfohlen ist **Solcast**: Jedes Mitglied erstellt sich ein **eigenes, kostenloses** Konto und erfasst dort die Daten seiner PV-Anlage.

→ **[Solcast Solar einrichten](../guides/solcast.md)** _(Konto anlegen, PV-Anlage erfassen, API-Key in Home Assistant eintragen, Prognose-Sensoren aktivieren)_

> [!NOTE]
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

Zum Schluss verbindest du den Optimizer mit deiner Anlage:

1. Öffne **Home Assistant im Browser** (gleiche Adresse wie in Schritt 2:
   `http://homeassistant.local:8123`).
2. Klicke in der **Seitenleiste links** auf den Eintrag **„EEG Optimizer"** —
   das öffnet das Einrichtungs-Panel.

Das Panel führt dich Schritt für Schritt durch:

1. Voraussetzungsprüfung
2. Wechselrichtertyp wählen + automatische Sensorerkennung
3. Prognosequelle wählen (Solcast / Forecast.Solar)
4. Batterie- & PV-Sensoren zuordnen
5. Optimizer-Einstellungen (Morgenfenster, Entladezeit, Min-SOC, Sicherheitspuffer, PeakShare-Community)
6. Einspeisebegrenzung optimieren (optional, nur Huawei/Fronius)
7. Wechselrichter-Verbindungstest

> [!TIP]
> Bei jedem Schritt im Panel gibt es einen **„Anleitung"-Button**, der genau die
> oben verlinkten Hilfen direkt anzeigt.

---

## Fertig 🎉

Wenn alle Schritte erledigt sind, läuft der EEG Energy Optimizer und steuert
deinen Speicher passend zu den Einspeise-Zeitfenstern der Energiegemeinschaft.
Den Status siehst du jederzeit im **EEG Optimizer Panel**.

> [!NOTE]
> **Einlaufzeit — mindestens eine Woche laufen lassen:** Der Optimizer lernt das
> Verbrauchsprofil deines Haushalts aus den aufgezeichneten Daten — getrennt nach
> Wochentag und Stunde. Direkt nach der Inbetriebnahme sind noch keine
> Verbrauchsdaten vorhanden; erst nach **etwa einer Woche** Dauerbetrieb liegt
> für jeden Wochentag ein eigenes Profil vor. Bis dahin behilft sich der
> Optimizer mit den Daten ähnlicher Wochentage — die Prognosen (und damit die
> Lade-/Entladeentscheidungen) werden mit jeder weiteren Woche genauer. Lass das
> Gerät daher durchgehend laufen und beurteile das Verhalten des Optimizers
> frühestens nach einer Woche.

> [!TIP]
> Auf deinem Gerät ist ein **Fernzugang für die EEG** eingerichtet, damit wir dich
> beim Setup unterstützen können. Sobald alles läuft, kannst du ihn bei Bedarf
> deaktivieren.
