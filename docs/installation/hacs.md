# HACS auf Home Assistant installieren

[HACS](https://hacs.xyz/) (Home Assistant Community Store) ist die Voraussetzung, um den EEG Energy Optimizer und mehrere benötigte Integrationen (z.B. Solcast, Huawei Solar, SolaX Modbus, SolarEdge Modbus Multi) zu installieren.

> [!NOTE]
> Diese Anleitung fasst die offiziellen Schritte zusammen. Bei Abweichungen gilt die offizielle Doku: [hacs.xyz/docs/use/download/download](https://hacs.xyz/docs/use/download/download/)

## Voraussetzungen

- Home Assistant **OS** oder **Supervised** (für andere Installationsarten siehe offizielle HACS-Doku)
- Ein **GitHub-Konto** (kostenlos) — wird für die Aktivierung von HACS benötigt
- Zugriff auf die Home Assistant Oberfläche als Administrator

## 1. HACS herunterladen (per „Get HACS" Add-on — kein Terminal nötig)

1. Klicke auf diesen Link, um das HACS Add-on-Repository hinzuzufügen:<br>
   **[➕ Add-on-Repository in Home Assistant öffnen](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fhacs%2Faddons)**<br>
   _Alternativ manuell: **Einstellungen → Add-ons → Add-on Store** → Drei-Punkte-Menü oben rechts → **Repositories** → `https://github.com/hacs/addons` eintragen → **Hinzufügen**_
2. Im **Add-on Store** nach **„Get HACS"** suchen (ggf. Seite neu laden) und das Add-on **installieren**
3. Das Add-on **starten** — es lädt HACS automatisch herunter (Fortschritt im Log des Add-ons sichtbar)
4. Danach kann das Add-on **wieder deinstalliert** werden — es wird nur einmalig gebraucht

## 2. Home Assistant neu starten

1. Gehe zu **Einstellungen → System**
2. Klicke oben rechts auf das **Power-Symbol → Home Assistant neu starten**

## 3. HACS-Integration hinzufügen

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„HACS"** und wähle es aus
3. Bestätige die Hinweise (Checkboxen) und klicke auf **Senden**
4. Es erscheint ein **Gerätecode** — öffne [github.com/login/device](https://github.com/login/device)
5. Melde dich bei GitHub an und gib den Code ein
6. Autorisiere HACS — zurück in Home Assistant schließt sich der Dialog automatisch

## 4. Prüfen

- In der Seitenleiste erscheint der Eintrag **HACS**
- Unter **HACS** kannst du jetzt Community-Integrationen suchen und installieren

## Alternative: Installation per Terminal

Falls du das Add-on nicht nutzen kannst oder willst, geht es auch klassisch per Download-Script:

1. **Einstellungen → Add-ons → Add-on Store** → **„Advanced SSH & Web Terminal"** (oder „Terminal & SSH") installieren und starten
2. Im Terminal ausführen:

   ```bash
   wget -O - https://get.hacs.xyz | bash -
   ```

3. Weiter mit Schritt 2 (Neustart) oben

## Nächster Schritt

→ [EEG Energy Optimizer über HACS installieren](eeg-integration.md)

## Häufige Probleme

| Problem | Lösung |
|---|---|
| „Get HACS" taucht im Add-on Store nicht auf | Seite neu laden (Strg+F5); prüfen, ob das Repository `hacs/addons` unter Repositories eingetragen ist |
| HACS taucht nach Neustart nicht unter Integrationen auf | Browser-Cache leeren (Strg+F5); wurde der Neustart wirklich durchgeführt? |
| GitHub-Code abgelaufen | Integration erneut hinzufügen, neuen Code anfordern |
