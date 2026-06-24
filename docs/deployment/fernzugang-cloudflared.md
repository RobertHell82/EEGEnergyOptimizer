# Fernzugang einrichten (Cloudflare Tunnel)

Mit dieser Anleitung machst du deinen Home Assistant direkt unter einer eigenen Internetadresse verfügbar - ohne zusätzliche Kosten.
Der Zugang läuft über einen sogenannten **Cloudflare Tunnel**: Dein Home Assistant baut die Verbindung selbst nach außen auf und bleibt von außen unsichtbar.

> [!NOTE]
> Du musst **kein Konto bei Cloudflare** anlegen und dort nichts einstellen. Den
> technischen Teil übernimmt deine Energiegemeinschaft. Du brauchst nur die zwei
> Angaben, die du von uns bekommst (siehe Voraussetzungen).


## Voraussetzungen
- Home Assistant **OS** oder **Supervised** in **aktueller Version** (mit App Store — in älteren Versionen „Add-on Store" genannt)
- Zugriff auf Home Assistant als **Administrator**
- Von der Energiegemeinschaft EW Ansfelden erhalten. Falls Du diese Daten noch nicht hast aber benötigst, melde Dich bei uns unter: info@ew-ansfelden.at
  - ein **Tunnel-Token** (eine lange Zeichenkette)
  - deine **Adresse** (z.B. `sicherer_name.ew-ansfelden.cc`)

---

## Schritt 1: App installieren

> [!NOTE]
> Der Bereich **„Apps"** hieß in älteren Home-Assistant-Versionen **„Add-ons"** —
> gemeint ist dasselbe. Diese Anleitung verwendet die aktuelle Bezeichnung.

1. Klicke auf diesen Link, um das benötigte Repository in Home Assistant zu
   hinterlegen:<br>
   **[➕ Repository in Home Assistant öffnen](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbrenner-tobias%2Faddon-cloudflared)**<br>
   Bestätige im Dialog, der sich öffnet, mit **Hinzufügen**.

   _Alternativ manuell: **Einstellungen → Apps → App Store** (in älteren Versionen **Add-ons → Add-on Store**) → drei Punkte oben rechts → **Repositories** → folgende Adresse eintragen → **Hinzufügen**:_

   ```
   https://github.com/brenner-tobias/addon-cloudflared
   ```

2. Suche im **App Store** nach **„Cloudflared"** (ggf. Seite mit Strg+F5 neu
   laden) und klicke auf **Installieren**.

---

## Schritt 2: Token eintragen

1. Öffne in der **Cloudflared**-App den Tab **„Konfiguration"**.
2. Aktiviere das Feld **`tunnel_token`** und füge den von uns erhaltenen **Token**
   ein.
3. Klicke auf **Speichern**.

> [!WARNING]
> Der Token ist der Schlüssel zu deinem Fernzugang. Gib ihn nicht weiter und
> teile keine Screenshots davon.

---

## Schritt 3: Home Assistant für den Zugriff vorbereiten

Damit Home Assistant den Zugriff über den Tunnel akzeptiert, muss ein kleiner
Eintrag in der Datei `configuration.yaml` ergänzt werden.

1. Falls noch nicht vorhanden, installiere im **App Store** den **„File editor"**
   oder **„Studio Code Server"**, um die Datei bearbeiten zu können.
2. Öffne `configuration.yaml` und füge diesen Block ein. Ist bereits ein
   `http:`-Abschnitt vorhanden, ergänze nur die Zeilen darunter:

   ```yaml
   http:
     use_x_forwarded_for: true
     trusted_proxies:
       - 172.30.33.0/24
   ```

3. Starte Home Assistant neu: **Einstellungen → System →** Power-Symbol oben
   rechts **→ Home Assistant neu starten**.

> [!NOTE]
> Ohne diesen Eintrag zeigt Home Assistant beim Aufruf von außen die Meldung
> „400: Bad Request".

---

## Schritt 4: Starten und testen

1. Öffne wieder die **Cloudflared**-App, Tab **„Info"**.
2. Aktiviere **„Beim Booten starten"** und **„Watchdog"** (damit der Zugang
   zuverlässig läuft) und klicke auf **Starten**.
3. Rufe im Browser deine Adresse auf, z.B. `https://deinname.ew-ansfelden.cc`.
4. Es erscheint deine gewohnte Home-Assistant-Anmeldeseite — **fertig.** ✅

---

## Wichtig zur Sicherheit

> [!WARNING]
> Dein Home Assistant ist jetzt aus dem Internet erreichbar. Aktiviere unbedingt
> die **Zwei-Faktor-Anmeldung** für deinen Benutzer:
> **Profil (unten links) → Sicherheit → Authentifizierungsanwendung (TOTP)**.

Jeder Benutzer mit Login muss die Zwei-Faktor-Anmeldung einzeln aktivieren.

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| „Cloudflared" erscheint nicht im Store | Seite neu laden (Strg+F5); prüfen, ob das Repository hinterlegt ist (Schritt 1 erneut über den Link ausführen) |
| Kein Bereich „Apps"/„Add-ons" im Menü sichtbar | App Store direkt öffnen: **[my.home-assistant.io/redirect/supervisor_store](https://my.home-assistant.io/redirect/supervisor_store/)** (bekannter Anzeige-Fehler mancher Versionen — der Store ist über den Link weiterhin erreichbar) |
| „400: Bad Request" beim Aufruf | `trusted_proxies`-Eintrag aus Schritt 3 fehlt oder Home Assistant wurde nicht neu gestartet |
| Adresse lädt nicht / Tunnel offline | Im Protokoll (Log) der **Cloudflared**-App prüfen, ob der Token korrekt eingetragen ist; App neu starten |
| Backup-Upload über die Adresse schlägt fehl | Technisches Limit des Tunnels (max. 100 MB pro Upload) — Backups bitte lokal im Heimnetz erstellen |
