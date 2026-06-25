# Inbetriebnahme deines EEG-Geräts (Home Assistant Green)

Dein Home Assistant Green wurde bereits vorbereitet: Alle benötigten Programme,
der EEG Energy Optimizer und der Fernzugang sind installiert. Diese Anleitung
führt dich durch die wenigen Schritte, bis dein System läuft.

> [!NOTE]
> Du musst **nichts installieren** und keinen Einrichtungsassistenten
> durchlaufen — das ist alles schon erledigt. Es geht nur noch um anschließen,
> anmelden und ein paar persönliche Einstellungen.

**Zeitaufwand:** ca. 20 Minuten · **Schritte 1–3** kann jeder selbst, **Schritte 4–6** brauchen die Daten deiner PV-Anlage.

---

## Schritt 1: Gerät anschließen (Strom & Netzwerk)

1. **Netzwerk:** Stecke das **Netzwerkkabel** vom Gerät in einen freien LAN-Port
   deines Routers. _(Kabel ist stabiler als WLAN — empfohlen.)_
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
| **Passwort ändern** | Profil (Name unten links) → *Passwort ändern* | Voreingestelltes Passwort durch ein eigenes ersetzen |
| **Name des Systems** | Einstellungen → System → Allgemein | z.B. „EEG Familie Muster" |
| **Standort** ⚠️ | Einstellungen → System → Allgemein | Ab Werk auf **„Linz Hauptplatz"** voreingestellt — **unbedingt auf deine eigene Adresse ändern** (Karte oder Lat/Lon), Höhe & Zeitzone prüfen |
| **HACS autorisieren** | HACS (Seitenleiste) | GitHub-Gerätecode auf [github.com/login/device](https://github.com/login/device) eingeben |

> [!WARNING]
> Der **Standort** ist ab Werk auf **„Linz Hauptplatz"** voreingestellt und **muss
> nach dem ersten Start auf deine eigene Adresse geändert werden**. Der Optimizer
> berechnet Sonnenauf-/-untergang und PV-Prognose daraus — ohne korrekten Standort
> arbeitet er mit falschen Zeiten.

> [!IMPORTANT]
> Ändere das voreingestellte **Passwort** unbedingt — es war für alle Geräte
> gleich. Den **Fernzugang (Cloudflare)** musst du **nicht** einrichten, der ist
> bereits für dein Gerät vorbereitet.

---

## Schritt 4: PV-Prognose (Solcast)

Für die genaueste Prognose nutzen wir **Solcast** — jedes Mitglied braucht ein
**eigenes, kostenloses** Konto (ein gemeinsames ist nicht möglich).

→ **[Solcast Solar einrichten](../guides/solcast.md)** _(Konto anlegen, PV-Anlage erfassen, API-Key in Home Assistant eintragen, Prognose-Sensoren aktivieren)_

> [!TIP]
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
6. PeakShare-Community wählen (optional)
7. Wechselrichter-Verbindungstest

> [!TIP]
> Bei jedem Schritt im Panel gibt es einen **„Anleitung"-Button**, der genau die
> oben verlinkten Hilfen direkt anzeigt.

---

## Fertig 🎉

Wenn alle Schritte erledigt sind, läuft der EEG Energy Optimizer und steuert
deinen Speicher passend zu den Einspeise-Zeitfenstern der Energiegemeinschaft.
Den Status siehst du jederzeit im **EEG Optimizer Panel**.

## Häufige Probleme

| Problem | Lösung |
|---|---|
| `homeassistant.local` nicht erreichbar | IP-Adresse des Geräts in der Router-Geräteliste suchen und stattdessen aufrufen |
| Kein Login möglich | Benutzername/Passwort prüfen (Groß-/Kleinschreibung); ggf. bei uns melden |
| Optimizer zeigt falsche Sonnenzeiten | Standort unter Einstellungen → System → Allgemein korrekt gesetzt? (Schritt 3) |
| HACS-GitHub-Code abgelaufen | Vorgang erneut starten, neuen Code anfordern |
| Wechselrichter-Verbindungstest schlägt fehl | Anleitung des jeweiligen Wechselrichters prüfen (Schritt 5); IP/Zugangsdaten korrekt? |
