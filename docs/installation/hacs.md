# HACS auf Home Assistant installieren

[HACS](https://hacs.xyz/) (Home Assistant Community Store) ist die Voraussetzung, um den EEG Energy Optimizer und mehrere benötigte Integrationen (z.B. Solcast, Huawei Solar, SolaX Modbus, SolarEdge Modbus Multi) zu installieren.

> [!NOTE]
> Diese Anleitung fasst die offiziellen Schritte zusammen. Bei Abweichungen gilt die offizielle Doku: [hacs.xyz/docs/use/download/download](https://hacs.xyz/docs/use/download/download/)

## Voraussetzungen

- Home Assistant **OS** oder **Supervised** (für andere Installationsarten siehe offizielle HACS-Doku)
- Ein **GitHub-Konto** (kostenlos) — wird für die Aktivierung von HACS benötigt
- Zugriff auf die Home Assistant Oberfläche als Administrator

## 1. Terminal-Add-on installieren

HACS wird über ein Download-Script installiert. Dafür brauchst du Terminal-Zugriff:

1. Gehe zu **Einstellungen → Add-ons → Add-on Store**
2. Suche nach **„Advanced SSH & Web Terminal"** (oder „Terminal & SSH")
3. Installiere das Add-on und starte es
4. Öffne das Terminal über die Seitenleiste oder die Add-on-Seite

## 2. HACS herunterladen

Führe im Terminal folgenden Befehl aus:

```bash
wget -O - https://get.hacs.xyz | bash -
```

Das Script lädt die aktuelle HACS-Version herunter und legt sie unter `config/custom_components/hacs` ab.

## 3. Home Assistant neu starten

1. Gehe zu **Einstellungen → System**
2. Klicke oben rechts auf das **Power-Symbol → Home Assistant neu starten**

## 4. HACS-Integration hinzufügen

1. Gehe zu **Einstellungen → Geräte & Dienste → Integration hinzufügen**
2. Suche nach **„HACS"** und wähle es aus
3. Bestätige die Hinweise (Checkboxen) und klicke auf **Senden**
4. Es erscheint ein **Gerätecode** — öffne [github.com/login/device](https://github.com/login/device)
5. Melde dich bei GitHub an und gib den Code ein
6. Autorisiere HACS — zurück in Home Assistant schließt sich der Dialog automatisch

## 5. Prüfen

- In der Seitenleiste erscheint der Eintrag **HACS**
- Unter **HACS** kannst du jetzt Community-Integrationen suchen und installieren

## Nächster Schritt

→ [EEG Energy Optimizer über HACS installieren](eeg-integration.md)

## Häufige Probleme

| Problem | Lösung |
|---|---|
| HACS taucht nach Neustart nicht unter Integrationen auf | Browser-Cache leeren (Strg+F5), Neustart wirklich durchgeführt? |
| `wget: command not found` | Anderes Terminal-Add-on verwenden oder `curl -fsSL https://get.hacs.xyz \| bash -` |
| GitHub-Code abgelaufen | Integration erneut hinzufügen, neuen Code anfordern |
