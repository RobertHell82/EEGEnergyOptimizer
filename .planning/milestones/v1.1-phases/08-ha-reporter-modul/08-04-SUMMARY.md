---
phase: 08-ha-reporter-modul
plan: 04
subsystem: panel
tags: [panel, telemetry, opt-in, translations, version-bump, ux]
requires: [08-03]
provides:
  - "Panel-Sektion „Community-Statistik" zwischen Ladung & Einspeisung und Erweiterten Einstellungen (D-28)"
  - "_renderTelemetrySection() Render-Helfer mit Toggle, Status-Zeile, rotem Daten-löschen-Button (D-29)"
  - "_handleTelemetryToggle / _handleTelemetryForget verdrahtet auf telemetry_enable / disable / forget (D-30, D-31, D-32, D-33)"
  - "Status-Loader im _loadConfig-Pfad (defensiv, blockiert Settings-Load nicht)"
  - "Translations panel.telemetry-Namespace in de.json + en.json (14 Keys)"
  - "Version-Bump 1.0.11-dev-06 → 1.1.0-dev-01 (Phase-8-Milestone, forciert Cache-Bust)"
  - "README-Sektion „Community-Statistik (optional)" unter Funktionen"
affects:
  - "panel.js _loadConfig — feuert telemetry_get_status fire-and-forget nach Setup-Complete"
  - "panel.js Click-Listener — neue Branches für toggle-telemetry und forget-telemetry vor _handleAction-Dispatcher"
  - "panel.js _renderSettings — Karten-Insert zwischen Card 2 (Ladung & Einspeisung) und Card 3 (Erweiterte Einstellungen)"
  - "manifest.json version-Feld (gelesen von __init__.py für Panel-Cache-Bust-Query-Parameter)"
tech-stack:
  added: []
  patterns:
    - "Plain HTMLElement + Shadow DOM (kein LitElement, kein CDN-Import) — konsistent mit bestehendem Panel-Pattern"
    - "Native window.confirm() für destruktive Forget-Aktion — Null-Dependency, funktioniert in HA-Frontend"
    - "Defensiver Status-Load: callWS-Fehler → fallback {configured:false}, never-throw, console.warn statt UI-Fehler"
    - "Action-Dispatch via data-action-Attribut + closest()-Walk im Shadow-Click-Listener (bestehendes Muster)"
    - "Telemetrie-Sektion liest ausschließlich aus this._telemetryStatus (Cached Status), refresht via callWS nach jeder Aktion — Backend ist Single Source of Truth"
key-files:
  created: []
  modified:
    - "custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js (+140 LOC: Render-Helfer, 2 Action-Handler, Status-Loader-Hook, Click-Dispatcher-Branches, Konstruktor-State-Init, Card-Insert in _renderSettings)"
    - "custom_components/eeg_energy_optimizer/translations/de.json (+18 LOC: panel.telemetry mit 14 Keys, echte Umlaute)"
    - "custom_components/eeg_energy_optimizer/translations/en.json (+18 LOC: panel.telemetry mirror, English)"
    - "custom_components/eeg_energy_optimizer/manifest.json (1 LOC: Version 1.0.11-dev-06 → 1.1.0-dev-01)"
    - "README.md (+4 LOC: Sub-Sektion „Community-Statistik (optional)")"
decisions:
  - "Panel-JS-Strings bleiben inline in Deutsch (konsistent mit bestehendem Panel — die Translations-Datei wird vom JS heute nicht gelesen). Translations werden trotzdem strukturiert in de.json / en.json gepflegt, damit ein zukünftiger i18n-Helfer sie nutzen kann (Plan-Hinweis explizit dokumentiert)."
  - "Toggle und Button beide via data-action im Click-Dispatcher (statt change-Event), weil ein Click auf eine Checkbox sowohl click als auch change feuert — und beim Click ist target.checked bereits aktualisiert. Das vermeidet Doppelpfade und hält den Action-Vertrag einheitlich."
  - "Status-Refresh nach JEDER Toggle/Forget-Aktion via separatem telemetry_get_status-Call — auch im Fehlerfall. Backend ist Single Source of Truth, Panel zeigt nur an. Verhindert Drift zwischen UI-Zustand und tatsächlich gespeichertem Identity/Enabled-Flag."
  - "Native window.confirm() statt Custom-Modal für die Forget-Bestätigung. Plan empfiehlt ausdrücklich diese Variante (Null-Abhängigkeit, ein-Liner, in HA bewährt — siehe sim-apply-Branch)."
  - "Daten-löschen-Button wird auch dann angezeigt, wenn der User pausiert hat (s.installation_id_prefix vorhanden, aber !s.enabled). Das matcht D-32/D-33: Disable = Pause, Forget = Vergessen — User braucht im pausierten Zustand weiterhin Zugriff auf den Forget-Pfad."
  - "Status-Text bei nicht-konfigurietem Backend (DEV-Build) ist „Backend-URL noch nicht eingerichtet (DEV-Build)" + Toggle disabled. Vermeidet Verwirrung in DEV-Setups, ohne den Code zu zweigen."
metrics:
  duration_minutes: 25
  completed: "2026-04-29"
  task_count: 2
  test_count: 308   # baseline unverändert — keine neuen Python-Tests, kein Python-Code geändert
  added_tests: 0
  file_count: 5
---

# Phase 08 Plan 04: Panel-Sektion „Community-Statistik" Summary

**One-liner:** Telemetrie-Opt-In ist jetzt im Panel sichtbar — eine neue Karte zwischen den Settings-Sektionen mit Toggle, Status-Zeile (anonymer 8-char-Prefix + Registrierungs-Datum) und rotem „Daten löschen"-Button mit `window.confirm`-Dialog, vollständig verdrahtet auf die 4 WebSocket-Befehle aus 08-03 — und die Integration trägt jetzt die Phase-8-Version 1.1.0-dev-01.

## Was wurde gebaut

Plan 08-04 ist die User-facing Naht der Phase 8: alle Backend-Pfade (Reporter, Buffer, Hooks, WS-Befehle) aus 08-01 / 08-02 / 08-03 sind unsichtbar, bis der User in dieser Karte den Toggle umlegt. Der Plan hat genau einen Ziel: aus „technisch komplett" → „User kann opt-in / opt-out / forget".

Die Karte folgt 1:1 dem bestehenden Card-Stil der „Ladung & Einspeisung"-Sektion (D-28): `<div class="card">`, gleiche margin-bottom, gleiche Toggle-Patterns mit `data-action`-Attributen. Kein LitElement, kein neues Dependency, kein CDN-Import — plain HTMLElement + Shadow DOM, exakt wie der Rest des Panels.

### Wave-Integration

- **Plan 08-03** stellte die 4 WS-Befehle bereit: `telemetry_get_status` / `telemetry_enable` / `telemetry_disable` / `telemetry_forget`. 08-04 nutzt sie 1:1 — keine Schema-Änderungen, keine Wrapper-Schicht. Die Status-Response (`{configured, enabled, registered, installation_id_prefix, registered_at, queue_size, buffer_size, last_send_at}`) wird direkt aus `this._telemetryStatus` gerendert.

## Tasks & Commits

| Task | Beschreibung                                                                          | Commit    |
| ---- | ------------------------------------------------------------------------------------- | --------- |
| 1    | Translations panel.telemetry + Render-Helfer + Handler + Status-Loader + Click-Branch | `8dffa6c` |
| 2    | manifest.json Version-Bump 1.1.0-dev-01 + README Community-Statistik-Sektion          | `0578972` |

## Was im einzelnen entstanden ist

### `frontend/eeg-optimizer-panel.js` (~140 LOC)

1. **Konstruktor-State** (Z. 660–664):
   ```javascript
   this._telemetryStatus = null;
   this._telemetryError = null;
   this._telemetryBusy = false;
   ```

2. **Status-Loader** im `_loadConfig`-Pfad — fire-and-forget nach Setup-Complete:
   ```javascript
   this._hass.callWS({ type: "eeg_optimizer/telemetry_get_status" })
     .then(s => { this._telemetryStatus = s; this._render(); })
     .catch(err => {
       console.warn("EEG Optimizer: telemetry status load failed", err);
       this._telemetryStatus = { configured: false, enabled: false, registered: false };
       this._render();
     });
   ```
   Defensiv — Fehler dürfen den Settings-Load nicht blockieren.

3. **`_renderTelemetrySection()`** — Render-Helfer (~60 LOC). Status-Text-Resolution:
   - `!s.configured` → „Backend-URL noch nicht eingerichtet (DEV-Build)" + Toggle disabled
   - `s.registered && s.registered_at` → „Registriert als anonyme Anlage `<prefix>` seit `<DD.MM.YYYY>`" (Date via `toLocaleDateString("de-DE")`)
   - `s.installation_id_prefix && !s.enabled` → „Pausiert — Identität bleibt gespeichert"
   - `s.enabled && !s.registered` → „Registrierung läuft …" (transient, sollte selten erscheinen)
   - sonst → „Nicht registriert"
   
   Daten-löschen-Button (rot, `var(--error-color,#d33)`) wird angezeigt, wenn registered ODER `installation_id_prefix` vorhanden — auch im pausierten Zustand bleibt der Forget-Pfad verfügbar.

4. **`_handleTelemetryToggle(checked)`** — async:
   - Setzt `_telemetryBusy=true`, `_telemetryError=null`, re-rendert
   - Ruft `telemetry_enable` (checked) oder `telemetry_disable` (unchecked)
   - Bei `success===false` oder Exception: setzt `_telemetryError` (deutsche Meldung)
   - **Immer im finally**: refreshed `_telemetryStatus` via separatem `telemetry_get_status` und re-rendert
   - Backend ist Single Source of Truth — UI-Zustand kommt aus dem Status-Call, nicht aus dem optimistischen Toggle-Wert

5. **`_handleTelemetryForget()`** — async:
   - `window.confirm("Wirklich alle Daten löschen?\n\nAlle gesendeten ...")` — Cancel → return
   - Ruft `telemetry_forget`, behandelt `res.backend_deleted === false` → Warning-Meldung „Backend-Aufruf fehlgeschlagen — lokale Daten wurden trotzdem gelöscht."
   - Exception-Pfad: identische Warning-Meldung (UX blockiert nie auf Backend — D-31)
   - **Immer im finally**: Status-Refresh + re-render

6. **Click-Dispatcher-Branches** (Z. 749–757) — eingefügt VOR der generischen `_handleAction`-Dispatch:
   ```javascript
   if (action === "toggle-telemetry") { this._handleTelemetryToggle(!!btn.checked); return; }
   if (action === "forget-telemetry") { this._handleTelemetryForget(); return; }
   ```
   Klick auf Checkbox feuert sowohl click als auch change — wir nutzen den click-Path, weil `target.checked` zum Click-Zeitpunkt schon den neuen Wert trägt.

7. **Card-Insert in `_renderSettings()`**:
   ```javascript
   <!-- Card: Community-Statistik (D-28, Phase 8 Telemetrie-Opt-In) -->
   ${this._renderTelemetrySection()}
   ```
   Eingefügt zwischen dem schließenden `</div>` der „Ladung & Einspeisung"-Card und der Öffnung der „Erweiterte Einstellungen"-Card.

### `translations/de.json` (+18 LOC)

Neue Top-Level-Sektion `panel.telemetry` mit 14 Keys: `title`, `description`, `toggle_label`, `status_registered`, `status_not_registered`, `status_disabled`, `status_not_configured`, `delete_button`, `delete_confirm_title`, `delete_confirm_body`, `delete_confirm_ok`, `delete_confirm_cancel`, `enable_error`, `forget_warning`. Alle Strings verwenden echte Umlaute (`ä/ö/ü`) — Spot-Check via `python -c` bestätigt: „Identität", „löschen", „rückgängig", „Endgültig" alle als UTF-8-Literale, keine `\u00xx`-Encoding.

### `translations/en.json` (+18 LOC)

Spiegel der deutschen Sektion mit englischen Werten. Gleiche 14 Keys.

### `manifest.json`

Version-Bump:
```diff
-  "version": "1.0.11-dev-06",
+  "version": "1.1.0-dev-01",
```
Phase-8-Milestone — markiert den Übergang von v1.0-Patches zu v1.1-Telemetrie. Die Version wird auch von `__init__.py` als Cache-Bust-Query-Parameter für die Panel-JS-URL gelesen — damit lädt jeder Client das neue JS beim ersten Reload nach dem Update zwingend nach.

### `README.md` (+4 LOC)

Neue Sub-Sektion `### Community-Statistik (optional)` direkt unter den Funktionen-Bulletpoints, vor dem Abschnitt „Unterstützte Wechselrichter". Beschreibt:
- Opt-in via Panel
- Was übermittelt wird: State-Changes, halbstündliche Snapshots, Outcome-Events, Failure-Events (anonymisiert, keine Personenbezug)
- Was NICHT übermittelt wird: Sensor-IDs, IP-Adressen, Anlagenname, Adresse, EEG-Mitgliedsdaten
- Wie sich Daten löschen lassen: Panel → Einstellungen → Community-Statistik
- Standardmäßig **aus**

Kein Link zu Privacy.md (das ist Phase 10, wie im Plan dokumentiert). Prosa-Stil, keine Bullets, in einem Absatz.

## Verifikation

### Automatisierte Checks

```bash
node -e "const fs=require('fs'); const js=fs.readFileSync('custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js','utf8'); ['_renderTelemetrySection','telemetry_get_status','telemetry_enable','telemetry_disable','telemetry_forget','_handleTelemetryToggle','_handleTelemetryForget','toggle-telemetry','forget-telemetry'].forEach(c=>{ if(!js.includes(c)) throw new Error('missing '+c); });"
# → alle 9 Marker präsent

python -c "import json; m=json.load(open('custom_components/eeg_energy_optimizer/manifest.json',encoding='utf-8')); assert m['version']=='1.1.0-dev-01'"
# → Version 1.1.0-dev-01 bestätigt

python -c "
import json
for p in ['custom_components/eeg_energy_optimizer/translations/de.json',
          'custom_components/eeg_energy_optimizer/translations/en.json']:
    d = json.load(open(p, encoding='utf-8'))
    assert 'panel' in d and 'telemetry' in d['panel']
    keys = set(d['panel']['telemetry'].keys())
    expected = {'title','description','toggle_label','status_registered',
                'status_not_registered','status_disabled','status_not_configured',
                'delete_button','delete_confirm_title','delete_confirm_body',
                'delete_confirm_ok','delete_confirm_cancel','enable_error',
                'forget_warning'}
    assert not (expected - keys), (p, expected - keys)
"
# → 14/14 Keys in beiden Dateien

node --check custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js
# → Syntax OK
```

### Umlaute-Check

```bash
python -c "
with open('custom_components/eeg_energy_optimizer/translations/de.json', encoding='utf-8') as f:
    raw = f.read()
for word in ['Identität', 'löschen', 'rückgängig', 'Endgültig']:
    assert word in raw, f'missing real Umlaut: {word!r}'
"
# → alle als UTF-8-Literal, kein \u00xx-Encoding
```

Spot-Check der Commit-Messages: beide Commits enthalten echte Umlaute (`fügt`, `Lösch`, `Identität`, `Wirksamkeitsdaten`, `aktivieren`, `unterstützte`).

### pytest

```bash
python -m pytest tests/ -q
# → 308 passed in 13.89s (Baseline aus 08-03 unverändert — keine Python-Änderungen)
```

## Deviations from Plan

**Keine — Plan wurde exakt wie geschrieben ausgeführt.**

Notiz zu zwei Mikro-Anpassungen am Verhalten, die im Plan-Pseudocode bereits angedeutet waren:

1. **`<code>`-Tag um den Installation-Prefix in der Status-Zeile** — der Plan-Pseudocode rendert den 8-char-Prefix als Plaintext (`${s.installation_id_prefix}`). Im Card-HTML wird er stattdessen in `<code>...</code>` gewrapped, damit der monospace-Anker visuell als technische ID erkennbar ist. Vertrag bleibt erfüllt: Format „Registriert als anonyme Anlage `<prefix>` seit `<datum>`" matcht D-29.

2. **Toggle und Button werden während `_telemetryBusy=true` `disabled`** — der Plan-Pseudocode disabled die Checkbox nur bei `notConfigured`. Wir disable'n sie zusätzlich während laufenden Calls, damit kein Doppel-Klick mehrere parallele `enable/disable`-Calls auslöst. Konsistent zur `_telemetryBusy`-Re-Entry-Guard in beiden Handlern.

Beide Anpassungen sind UX-Polish ohne Vertragsabweichung. Sie wurden nicht als formale Deviations gelogged, weil sie weder zusätzliche Funktionalität, noch geänderte Endpoints, noch Test-Anpassungen erfordern.

## HTTP-Vertrags-Verifikation

Der Panel-Code ruft die 4 WS-Befehle aus 08-03 mit den exakt erwarteten `type`-Strings auf:

| Aktion              | WS-Type                              | Erwartete Response-Felder                                                                              |
| ------------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| Status-Load         | `eeg_optimizer/telemetry_get_status` | `{configured, enabled, registered, installation_id_prefix, registered_at, queue_size, buffer_size, last_send_at}` |
| Toggle ON           | `eeg_optimizer/telemetry_enable`     | `{success, installation_id_prefix?, error?}` (oder `{success: true, already_active: true}`)            |
| Toggle OFF          | `eeg_optimizer/telemetry_disable`    | `{success: true}`                                                                                      |
| Daten löschen       | `eeg_optimizer/telemetry_forget`     | `{success, backend_deleted}`                                                                           |

Panel liest und nutzt: `s.configured` / `s.enabled` / `s.registered` / `s.installation_id_prefix` / `s.registered_at` aus Status, `res.success` / `res.error` aus Enable, `res.backend_deleted === false` aus Forget. Alle Felder kommen aus 08-03-`websocket_api.py` (siehe Lines 8–10 dieser Phase 08-03-SUMMARY.md). Kein Schema-Drift.

## Self-Check: PASSED

- `_renderTelemetrySection` Definition + Aufruf in panel.js: 2 Treffer ✓
- 4 WS-Commands referenziert: `telemetry_get_status` / `telemetry_enable` / `telemetry_disable` / `telemetry_forget` — jeweils mind. 1 Treffer ✓
- `_handleTelemetryToggle` / `_handleTelemetryForget` als Methoden vorhanden ✓
- `data-action="toggle-telemetry"` + `data-action="forget-telemetry"` in Render-Output ✓
- `window.confirm(...)` mit „Wirklich alle Daten löschen?" Vorlage präsent ✓
- de.json + en.json: jeweils 14/14 Keys unter `panel.telemetry` ✓
- de.json: echte Umlaute (`Identität`, `löschen`, `rückgängig`, `Endgültig`) bestätigt ✓
- manifest.json `version === "1.1.0-dev-01"` ✓
- README.md enthält `Community-Statistik` Sub-Heading ✓
- `node --check` der Panel-JS: Syntax OK ✓
- `pytest tests/`: 308 PASS (Baseline unverändert) ✓
- Beide Commits (`8dffa6c`, `0578972`) im git log vorhanden ✓

## Commits

| Hash      | Type   | Subject                                                              |
| --------- | ------ | -------------------------------------------------------------------- |
| `8dffa6c` | feat   | Community-Statistik-Sektion + Render-Helfer + Handler + Translations |
| `0578972` | chore  | Version 1.1.0-dev-01 + README Community-Statistik-Sektion            |

## Was Phase 9 jetzt nutzen kann

- Die Karte ist für den User die Schalter-Stelle. Phase 9 (Dashboard) baut darauf auf, dass irgendein User-Pool tatsächlich opt-in geklickt hat.
- `installation_id_prefix` wird als 8-char Anker im UI verwendet — Phase 9 kann denselben Prefix als Filter-/Such-Hilfe im Dashboard zeigen, wenn der User sich identifizieren möchte.
- Die Translation-Keys unter `panel.telemetry` sind für späteren i18n-Helfer vorbereitet — Phase 9 könnte den Helfer ergänzen, ohne das Schema noch einmal anfassen zu müssen.
- Der pausierte Zustand („Identität bleibt gespeichert") gibt Phase 9 die Garantie: ein User, der pausiert, kommt mit dem gleichen `installation_id` zurück — das Dashboard kann historische Daten weiter zuordnen, sobald er wieder aktiviert.
