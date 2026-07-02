# Fernzugang einrichten (Cloudflare Tunnel)

Mit dieser Anleitung machst du deinen Home Assistant direkt unter einer eigenen Internetadresse verfügbar - ohne zusätzliche Kosten.
Der Zugang läuft über einen sogenannten **Cloudflare Tunnel**: Dein Home Assistant baut die Verbindung selbst nach außen auf und bleibt von außen unsichtbar.

> [!NOTE]
> Du musst **kein Konto bei Cloudflare** anlegen und dort nichts einstellen. Den
> technischen Teil übernimmt deine Energiegemeinschaft.


## Voraussetzungen
- Home Assistant **OS** oder **Supervised** in **aktueller Version** (mit App Store)
- Zugriff auf Home Assistant als **Administrator**
- Von der Energiegemeinschaft EW Ansfelden erhalten. Falls Du noch keine Zugangsdaten erhalten hast und Interesse hast, melde Dich unter: info@ew-ansfelden.at
  - ein **Tunnel-Token** (eine lange Zeichenkette)
  - deine **Adresse** (z.B. `sicherer_name.ew-ansfelden.cc`)

---

## Schritt 1: Cloudflared App installieren

1. Öffne **Einstellungen → Apps**.
2. Klicke rechts unten auf **App installieren**.
3. Klicke oben rechts auf die **drei Punkte** und wähle **Repositories**.
4. Trage folgende Adresse ein und klicke auf **Hinzufügen**:

   ```
   https://github.com/homeassistant-apps/repository
   ```

5. Suche nach **„Cloudflared"** (ggf. Seite mit Strg+F5 neu laden) und klicke
   auf **Installieren**.

---

## Schritt 2: Token eintragen

1. Öffne in der **Cloudflared**-App den Tab **„Konfiguration"**.
2. Klicke auf **„Nicht verwendete Konfigurationsoptionen einblenden"**.
3. Trage im Feld **„Cloudflare Tunnel Token"** den von der Energiegemeinschaft
   erhaltenen **Token** ein.
4. Klicke auf **Speichern**.

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
2. Aktiviere **„Beim Systemstart starten"**.
3. Aktiviere **„Automatische Updates"**.
4. Aktiviere **„Watchdog"** (damit der Zugang zuverlässig läuft).
5. Klicke auf **Starten**.

Der Home Assistant ist nun mit Cloudflare verbunden. Zum Prüfen:

6. Rufe im Browser deine Adresse auf, z.B. `https://deinname.ew-ansfelden.cc`.
7. Es erscheint deine gewohnte Home-Assistant-Anmeldeseite — **fertig.** ✅

---

## Häufige Probleme

| Problem | Lösung |
|---|---|
| „Cloudflared" erscheint nicht im Store | Seite neu laden (Strg+F5); prüfen, ob das Repository hinterlegt ist (Schritt 1 erneut ausführen) |
| Kein Bereich „Apps" im Menü sichtbar | App Store direkt öffnen: **[my.home-assistant.io/redirect/supervisor_store](https://my.home-assistant.io/redirect/supervisor_store/)** |
| „400: Bad Request" beim Aufruf | `trusted_proxies`-Eintrag aus Schritt 3 fehlt oder Home Assistant wurde nicht neu gestartet |
| Adresse lädt nicht / Tunnel offline | Im Protokoll (Log) der **Cloudflared**-App prüfen, ob der Token korrekt eingetragen ist; App neu starten |
| Backup-Upload über die Adresse schlägt fehl | Technisches Limit des Tunnels (max. 100 MB pro Upload) — Backups bitte lokal im Heimnetz erstellen |
