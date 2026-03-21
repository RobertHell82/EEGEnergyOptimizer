# Phase 4: Onboarding Panel - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Permanentes HA Sidebar Panel (LitElement/JS) mit zwei Bereichen: Dashboard (Optimizer-Status, Prognosen, Verbrauchsdaten in Echtzeit via WebSocket) und Einstellungs-Wizard (jederzeit wieder startbar, ersetzt Config Flow als primäre Konfigurationsoberfläche). Config Flow wird auf 1-Click-Minimum reduziert.

</domain>

<decisions>
## Implementation Decisions

### Panel-Struktur & Navigation
- **D-01:** Permanentes Sidebar-Panel, bleibt nach Erstsetup dauerhaft sichtbar
- **D-02:** Sidebar-Icon: `mdi:solar-power`, Name: "EEG Optimizer"
- **D-03:** Zwei Hauptbereiche: **Dashboard** (Startseite) und **Einstellungs-Wizard** (über Zahnrad-Button erreichbar)
- **D-04:** Vor erstem Wizard-Durchlauf: Dashboard zeigt großen Setup-Button + Hinweis "Setup noch nicht abgeschlossen"
- **D-05:** Nach erstem Wizard-Durchlauf: Dashboard normal, Wizard über Zahnrad-Icon oben rechts erreichbar
- **D-06:** Sprache: nur Deutsch für v1

### Wizard-Schritte (linear, vorwärts/zurück)
- **D-07:** Schritt 1 — **Willkommen**: Was die Integration tut, was sie braucht, welche Wechselrichter unterstützt werden (mit konkret getesteten Setups), was zwingende Voraussetzung ist (Forecast-Integration einrichten etc.)
- **D-08:** Schritt 2 — **Wechselrichter-Typ**: Auswahl des WR-Typs + Prerequisite-Check (ist Huawei Solar installiert?). Falls fehlend: blockieren + Anleitung mit Screenshots in Popup anzeigen
- **D-09:** Schritt 3 — **Restliche Prerequisites**: Forecast-Integration (Solcast ODER Forecast.Solar) prüfen. Falls fehlend: blockieren + Installationsanleitung mit Links zu HACS-Seiten
- **D-10:** Schritt 4 — **Batterie & PV Sensoren**: SOC-Sensor, Kapazitäts-Sensor (+ Hinweis auf Huawei Diagnostic-Sensor Aktivierung), PV-Sensor. Auto-Detection mit expliziter Bestätigung ("Wir haben diese Sensoren gefunden — stimmt das?")
- **D-11:** Schritt 5 — **Prognose-Sensoren**: Forecast-Quelle wählen, basierend darauf automatisch die richtigen Entities vorauswählen. Entity-Picker editierbar
- **D-12:** Schritt 6 — **Verbrauchssensor**: Verbrauchssensor wählen, Lookback-Weeks unter "Erweitert"
- **D-13:** Schritt 7 — **Optimizer-Parameter**: Überschuss-Schwelle, Morgen-Enduhrzeit, Entlade-Startzeit, Entladeleistung, Min-SOC, Sicherheitspuffer. Update-Intervalle unter "Erweitert"
- **D-14:** Schritt 8 — **Zusammenfassung**: Alle gewählten Einstellungen übersichtlich anzeigen, Fertig-Button
- **D-15:** Wizard ist linear (Schritt für Schritt), vorwärts/zurück Navigation
- **D-16:** Zwischenstand wird gespeichert — Abbruch und Wiederaufnahme möglich
- **D-17:** Wizard ist jederzeit erneut startbar für Re-Konfiguration, inkl. "Erweitert"-Bereich

### Prerequisite-Checks
- **D-18:** Wechselrichter-Integration (Huawei Solar) ist Pflicht — Wizard blockiert ohne
- **D-19:** Forecast-Integration (Solcast ODER Forecast.Solar) ist Pflicht — Wizard blockiert ohne
- **D-20:** Bei fehlender Prerequisite: Anleitung direkt im Wizard anzeigen, mit Links zu HACS-Seiten
- **D-21:** Längere Anleitungen (z.B. "Solcast über HACS installieren") als Popup/Dialog, damit sie nicht verloren gehen wenn der Wizard weitergeht
- **D-22:** Anleitungen möglichst gut und detailliert erstellen (Textanleitungen, Screenshots bei längeren Prozessen)

### Sensor-Mapping UX
- **D-23:** Auto-Detection bei erkannter Huawei-Integration: Sensoren vorausfüllen + explizite Bestätigung ("Stimmt das, oder hast du bessere Vorschläge?")
- **D-24:** Huawei Diagnostic-Sensor "Akkukapazität" (storage_rated_capacity) erkennen — wenn deaktiviert: gezielt darauf hinweisen wie man ihn aktiviert (Settings → Devices → Entities → Enable) + manuelle Kapazitäts-Eingabe als Alternative
- **D-25:** Forecast-Sensoren basierend auf gewählter Quelle automatisch vorauswählen (Solcast vs. Forecast.Solar haben unterschiedliche Entity-IDs)
- **D-26:** Kurze Kontext-Hilfe inline pro Sensor ("Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent")
- **D-27:** Auto-erkannte Sensoren sind editierbar (Entity-Picker bleibt offen)

### Dashboard
- **D-28:** Aktueller Optimizer-Status (Morgen-Einspeisung / Normal / Abend-Entladung / Test / Aus)
- **D-29:** Überschuss-Faktor + ob heute Überschuss-Tag
- **D-30:** Nächste geplante Aktion (aus Entscheidungs-Sensor)
- **D-31:** Batterie-SOC aktuell
- **D-32:** PV-Prognose heute/morgen
- **D-33:** Tagesverbrauchsprognosen als kleine Grafik (7 Tage)
- **D-34:** Stundenverbrauchsprofile pro Wochentag als zweite Grafik
- **D-35:** Live-Updates via WebSocket-Subscriptions (HA-typisch, kein manueller Refresh nötig)
- **D-36:** Layout: HA-typisch (Material Design, passend zum HA-Ökosystem)

### Config Flow Reduktion
- **D-37:** Config Flow wird auf Minimum reduziert: 1-Click "Integration hinzufügen" — gesamte Konfiguration im Panel
- **D-38:** Bestehende Config Flow Schritte (5 Steps) werden durch Panel-Wizard ersetzt
- **D-39:** Config VERSION Bump (3 → 4) mit Migration der bestehenden Config-Daten

### Claude's Discretion
- LitElement Komponentenstruktur und State-Management
- WebSocket-Subscription Implementierung (HA API Pattern)
- Panel-Registrierung in __init__.py (`async_register_built_in_panel` vs. Custom Panel)
- Grafik-Bibliothek für Verbrauchs-Charts (HA nutzt intern ApexCharts o.ä.)
- Popup/Dialog Implementierung für Anleitungen
- CSS/Styling im HA Material Design System
- Zwischenstand-Speicherung (localStorage vs. HA Config Entry)
- Responsive Layout für Mobile/Desktop

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Neue Integration (Phase 1-3 Output)
- `custom_components/eeg_energy_optimizer/__init__.py` — Entry Setup, Platform-Forwarding, 60s Timer (muss um Panel-Registrierung erweitert werden)
- `custom_components/eeg_energy_optimizer/config_flow.py` — Aktueller 5-Step Config Flow (wird auf Minimum reduziert)
- `custom_components/eeg_energy_optimizer/const.py` — Alle 20+ CONF_ Keys und Defaults (Panel muss diese kennen)
- `custom_components/eeg_energy_optimizer/strings.json` — Deutsche UI-Strings (Panel braucht eigene Strings)
- `custom_components/eeg_energy_optimizer/sensor.py` — 13 Sensoren inkl. EntscheidungsSensor (Dashboard liest diese)
- `custom_components/eeg_energy_optimizer/optimizer.py` — Decision Dataclass (Dashboard zeigt deren Felder)
- `custom_components/eeg_energy_optimizer/select.py` — OptimizerModeSelect (Dashboard zeigt Modus)
- `custom_components/eeg_energy_optimizer/manifest.json` — Dependencies (muss um Panel-Assets erweitert werden)

### Bestehende Integration (Referenz)
- `custom_components/energieoptimierung/` — Keine Panel-Referenz vorhanden, nur Config Flow

### Projekt-Dokumentation
- `.planning/REQUIREMENTS.md` — INF-04 (Onboarding Panel Requirement)
- `.planning/PROJECT.md` — Projektkontext, Constraints (LitElement/JS, HACS-kompatibel)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config_flow.py`: Enthält die gesamte Validierungs-Logik (Prerequisite-Checks, Entity-Detection, Huawei-Defaults) — Teile davon ins Panel übertragbar via WebSocket-Commands
- `const.py`: Alle Config-Keys und Defaults — Panel muss diese 1:1 kennen
- `sensor.py`: 13 Sensoren mit allen Daten die das Dashboard braucht — über HA State-API lesbar
- `optimizer.py`: Decision Dataclass mit allen Feldern für Dashboard-Anzeige

### Established Patterns
- HA Custom Panel: `async_register_built_in_panel()` oder `frontend.async_register_panel()`
- HA WebSocket API: `hass.connection.subscribeEntities()` für Live-Updates
- HA Entity-Picker: `<ha-entity-picker>` Web Component für Sensor-Auswahl
- HA Form Elements: `<ha-form>`, `<ha-selector>` für Wizard-Formulare
- HA Dialog: `<ha-dialog>` für Popup-Anleitungen

### Integration Points
- Panel-Registrierung in `__init__.py` via `hass.http.register_static_path()` + `frontend.async_register_panel()`
- WebSocket-Commands für Config-Lesen/Schreiben: `hass.components.websocket_api.async_register_command()`
- HA State API für Sensor-Werte (SOC, PV, Verbrauch, Optimizer-Status)
- Config Entry für persistente Einstellungen (Panel schreibt via WebSocket → Backend speichert in `entry.data`/`entry.options`)

</code_context>

<specifics>
## Specific Ideas

- "Konkret getestete Setups" auf der Willkommens-Seite — Huawei SUN2000 mit Batteriespeicher ist das erste offiziell getestete Setup
- Huawei Diagnostic-Sensor Aktivierung: gezielter Hinweis mit Pfad "Einstellungen → Geräte → Entities → Aktivieren" für storage_rated_capacity
- Anleitungen als Popup damit sie nicht verloren gehen beim Wizard-Weiterklicken
- Grafiken: Tagesverbrauchsprognosen als Balkendiagramm (7 Tage), Stundenprofile als Liniendiagramm (24h pro Tag)
- Großer Setup-Button vor erstem Wizard-Durchlauf, Zahnrad-Icon danach

</specifics>

<deferred>
## Deferred Ideas

- Englische Übersetzung des Panels — v2
- Fronius Gen24 als zweiter WR-Typ im Wizard — kommt mit INV-01
- SMA/weitere WR-Typen — Community-Beiträge
- Erweiterte Dashboard-Widgets (z.B. historische Charts, Einspeisung-Statistiken)
- Dark Mode spezifisches Styling (HA Dark Mode wird aber automatisch unterstützt via CSS Custom Properties)

</deferred>

---

*Phase: 04-onboarding-panel*
*Context gathered: 2026-03-21*
