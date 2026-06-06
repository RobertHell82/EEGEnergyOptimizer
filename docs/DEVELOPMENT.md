# Entwickler-Hinweise: Dokumentation

> Diese Datei richtet sich an Entwickler. Die Enduser-Dokumentation startet in [README.md](README.md).

## Synchronisation mit dem Panel

Die Dateien in `docs/guides/` und `docs/images/` sind die **Single Source of Truth** für die In-App-Anleitungen des Onboarding-Panels.

- **Bearbeiten:** Immer nur die Markdown-Dateien in `docs/guides/` ändern — niemals die generierten Dateien in `custom_components/eeg_energy_optimizer/frontend/guide/`.
- **Generieren:** Nach Änderungen `python scripts/build_guides.py` ausführen (benötigt `pip install markdown`). Das Script konvertiert die Markdown-Dateien zu HTML-Fragmenten und kopiert die Bilder in den Panel-Ordner.
- **Prüfen:** `python scripts/build_guides.py --check` schlägt fehl, wenn Quelle und generierte Dateien nicht übereinstimmen (läuft auch als GitHub Action bei jedem Push/PR).

Die Installations-Anleitungen (`docs/installation/`) existieren nur in `docs/` — sie haben kein Panel-Gegenstück.

## Markdown-Konventionen in den Guides

| Markdown | Darstellung im Panel |
|---|---|
| `# Titel` (genau eine H1) | Dialog-Überschrift |
| `## / ###` | Abschnitts-/Unterüberschriften |
| `> [!WARNING]` Blockquote | Orange Warnbox |
| `> [!NOTE]` Blockquote | Blaue Infobox |
| `> [!CAUTION]` Blockquote | Rote Pflicht-/Fehlerbox |
| `_kursiv_` | Grauer Sekundärtext (Hinweise) |
| `![alt](../images/...)` | Bild (Pfad wird automatisch umgeschrieben) |
| Tabellen, Listen, Links, `code`, `<br>` | wie üblich |

## Weitere interne Dokumente

- [Telemetrie-/Reporting-Konzept](reporting-concept.md)
