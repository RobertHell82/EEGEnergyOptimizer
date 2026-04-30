# Phase 8: HA Reporter-Modul — Context

**Gathered:** 2026-04-29
**Status:** Ready for planning
**Milestone:** v1.1 Telemetrie & Wirksamkeitsanalyse (Phase 2 von 4)
**Depends on:** Phase 7 (Backend-Skelett) — ✅ deployed nach `https://eeg-telemetry.robert-hell.workers.dev`

<domain>
## Phase Boundary

HA-Integration kann sich anonym am Telemetrie-Backend registrieren und sendet Events (State-Changes sofort, Snapshots gebündelt, Outcomes am Block-Ende, Failures bei Fehlern). Opt-in im Panel, Recht-auf-Vergessen via DELETE. Decision-Engine wird so refactored, dass `reasons` und `blocked_by` als strukturierte Listen für Diagnose verfügbar sind.

**Was nicht in dieser Phase:**
- Dashboard zum Lesen der Daten (Phase 9)
- Rate-Limiting-Härtung im Backend (Phase 10)
- Privacy-README-Doku (Phase 10)

</domain>

<decisions>
## Implementation Decisions

### Backend-Anbindung
- **D-01:** Backend-URL `https://eeg-telemetry.robert-hell.workers.dev` und Bootstrap-Token werden hardcoded in `const.py` als Konstanten. Werte landen nur im Release-Repo. DEV-Repo verwendet entweder Test-Backend-URL/-Token oder leere Werte → Reporter no-op, wenn URL/Token leer.
- **D-02:** Reporter-Modul wird nur initialisiert, wenn `CONF_TELEMETRY_ENABLED == True` und `TELEMETRY_BACKEND_URL` und `TELEMETRY_BOOTSTRAP_TOKEN` gesetzt sind.
- **D-03:** Backend-Schema ist verbindlich (siehe `EEGEnergyOptimzierBackend/src/types.ts`). Payloads matchen 1:1.

### Storage & Identität
- **D-04:** `installation_id` und `api_key` werden via `homeassistant.helpers.storage.Store` persistiert (Storage-Key: `eeg_energy_optimizer.telemetry`, Version 1). NICHT im Config Entry (Logging-Risiko).
- **D-05:** Storage-Inhalt: `{"installation_id": "<uuid>", "api_key": "<base64url>", "registered_at": "<iso>"}`. Wird beim Opt-out komplett gelöscht.
- **D-06:** Buffer für Events bei Backend-Unerreichbarkeit: persistent via Store (zweiter Storage-Key `eeg_energy_optimizer.telemetry_buffer`, Version 1), Ringbuffer max 100 Events. Events überleben HA-Restart.

### Test-Mode-Verhalten
- **D-07:** Telemetrie wird auch im Optimizer-Modus „Test" gesendet. State-Change-Events tragen das Feld `mode: "ein"|"test"`. Snapshots/Outcomes ebenfalls. Backend kann später filtern.
- **D-08:** Im Modus „Aus" werden keine Events gesendet (Optimizer evaluiert nicht).

### Decision-Refactor (sauber, vollständige Migration)
- **D-09:** `Decision`-Dataclass bekommt drei neue kanonische Felder:
  - `reasons: list[str]` — Begründungen für aktuelle Entscheidung (z.B. `["pv_forecast_exceeds_demand", "in_morning_window"]`)
  - `blocked_by: list[str]` — Bedingungen, die einen anderen Zustand verhindern (z.B. `["soc_below_min", "tomorrow_pv_insufficient"]`)
  - `snapshot: dict` — Schlanke Kopie der Schnapsbar-Inputs (soc_pct, pv_now_kw, consumption_now_kw, grid_now_kw, battery_now_kw, min_soc_dyn, hysteresis) zur Mitlieferung am State-Change
- **D-10:** `block_reasons` (redundant, wurde nirgends gerendert) wird vollständig entfernt. `discharge_reasons` (deutsche Freitext-Strings, vom Panel-Status-Card konsumiert) bleibt erhalten — getrennte Semantik: `discharge_reasons` = UI-Freitext für Panel, neues `reasons` = strukturierte snake_case-Katalog-Keys für Telemetrie-Diagnose. **Begründung der Trennung:** Vermeidet Translation-Mapping-Layer im Panel, hält UI-Strings dort wo sie sind, und macht den Telemetrie-Pfad deterministisch. Konsumenten (Markdown-Renderer in optimizer.py, Sensor `Entscheidung` in sensor.py, Activity-Log in __init__.py) werden im selben Plan auf die neuen `reasons`-Keys umgestellt, soweit sie heute `block_reasons` nutzen.
- **D-11:** `_should_block_charging` und `_should_discharge` ändern Signatur von `(bool, str)` auf `(bool, list[str], list[str])` — `(decision, reasons, blocked_by)`. Atomarer Refactor mit Tests.
- **D-12:** Begründungs-Strings sind ein **fixierter, dokumentierter Schlüssel-Katalog** (snake_case-Keys, kein Freitext). Katalog wird in `optimizer.py` als Konstanten am Modul-Anfang definiert. Beispiele: `pv_forecast_exceeds_demand`, `pv_forecast_below_threshold`, `soc_above_min`, `soc_below_min`, `tomorrow_pv_insufficient`, `outside_morning_window`, `peakshare_window_active`, `hysteresis_strict`, `hard_cutoff_after_4am`. Closed Set, leichter zu lokalisieren und für Backend-Auswertung deterministisch.

### Event-Strategie
- **D-13:** State-Change-Events: sofort, bei jedem Übergang zwischen `Normal`/`Morgen-Einspeisung`/`Abend-Entladung`. Body enthält `transition` (z.B. `"normal->morgen_einspeisung"`), `mode`, `reasons`, `blocked_by`, `snapshot`.
- **D-14:** Snapshots: alle 30 min in lokale Queue, Versand alle 60 min als Batch (also 2 Snapshots pro Batch, 24 Batches/Tag). Trigger: Optimizer-Cycle prüft Zeitstempel des letzten Snapshots.
- **D-15:** Outcomes: bei Übergang `Morgen-Einspeisung → Normal` und `Abend-Entladung → Normal`. `event_type` aus dem verlassenen State. Predicted-Werte werden beim **Block-Start** im Reporter gepuffert (PV-Forecast-Sensor + Verbrauchsprognose-Sensor zum Block-Start abrufen, lokal speichern, beim Block-Ende zusammen mit Actual-Werten senden). Actual-Werte: `feed-in statistics`-Tracker liefert `grid_export_kwh`, SOC-Differenz aus Snapshots.
- **D-16:** Failures: gesendet bei (a) Inverter-Write-Fehler (Exception in `async_set_*`), (b) Forecast-Provider-Fehler (Provider liefert None mehrfach hintereinander), (c) Sensor-Unavailability >10 min (Battery-SOC, PV-Power, Grid-Power, Verbrauchsprofil). `category`-Werte: `inverter_write`, `forecast_provider`, `sensor_unavailable`, `peakshare_fetch`. `severity`: `warning`/`error`. `message_hash` ist sha256(Exception-Klassenname + erste 200 Zeichen Message) — keine Stack-Traces, keine PII.
- **D-17:** Profile-Update: einmal beim Opt-in als Teil von `/v1/register`. Außerdem bei Settings-Änderung (Config-Reload-Listener) via `POST /v1/profile`.

### Settings-Inhalt (was im Profil gesendet wird)
- **D-18:** `settings_json` enthält **nur folgende Keys** (whitelist, KEINE `*_sensor`/`*_entity`/IP-Adressen):
  - `enable_morning_delay`, `enable_night_discharge`, `enable_peakshare`
  - `morning_start_offset`, `morning_end_time`, `discharge_start_time`
  - `discharge_power_kw`, `min_soc`, `safety_buffer_pct`
  - `peakshare_community` (String — der Community-Name ist nicht-personenbezogen, da Communities öffentlich sind)
  - `forecast_source` (`solcast` / `forecast_solar`)
- **D-19:** Whitelist als Konstante `TELEMETRY_SETTINGS_KEYS` in `const.py`. Reporter filtert vor Versand.

### Profile-Felder
- **D-20:** `app_version`: aus `manifest.json` zur Laufzeit gelesen.
- **D-21:** `ha_version`: aus `homeassistant.const.__version__`.
- **D-22:** `inverter_type`: aus Config-Entry (`huawei`/`fronius`/`solax`/`solaredge`).
- **D-23:** `battery_capacity_kwh`: aus Config / Sensor zur Opt-in-Zeit.
- **D-24:** `pv_peak_kwp`: NICHT verfügbar — Feld bleibt vorerst `null`. Optional later via Wizard ergänzen, separater Backlog-Eintrag.
- **D-25:** `forecast_provider`: aus Config (`solcast`/`forecast_solar`).
- **D-26:** `country_iso`: aus `hass.config.country` (z.B. `"AT"`, `"DE"`). Wenn nicht gesetzt → `null`. Kein Timezone-Heuristik-Fallback.
- **D-27:** `integration_started_at`: ISO-Timestamp der Config-Entry-Erstellung — gelesen aus dem Config-Entry-Erstelldatum oder, falls nicht verfügbar, dem Zeitpunkt des ersten Opt-ins.

### Opt-in-UX
- **D-28:** Neue Panel-Sektion „Community-Statistik" zwischen den bestehenden Settings-Sektionen, im gleichen Card-Stil wie die anderen.
- **D-29:** Inhalt: Toggle (default Aus), 2-3-Satz-Beschreibung der Idee, Link zu README/Privacy-Sektion (Phase 10), Status-Zeile („Registriert als anonyme Anlage `<8-Zeichen-Prefix>` seit `<datum>`" wenn aktiv), Button „Daten löschen" (rot, mit Bestätigungs-Dialog).
- **D-30:** Beim Aktivieren: 1) `POST /v1/register`, 2) Storage-Schreib, 3) sofort `POST /v1/profile` mit Settings, 4) UI zeigt Erfolg. Bei Fehler (Bootstrap-Token-Reject, Netzwerk): Fehlermeldung im Panel, Toggle bleibt aus.
- **D-31:** Beim „Daten löschen": Bestätigungs-Dialog → `DELETE /v1/installation` → Storage-Lösch → Toggle aus. Wenn Backend-Call fehlschlägt: Storage trotzdem lokal löschen + Warnhinweis im Panel.

### WebSocket-Commands
- **D-32:** Vier neue Commands (Schema analog zu bestehenden 17):
  - `eeg_optimizer/telemetry_get_status` → `{enabled, installation_id_prefix, registered_at, last_send_at, queue_size}`
  - `eeg_optimizer/telemetry_enable` → triggert Register-Flow
  - `eeg_optimizer/telemetry_disable` → entfernt UUID/Key lokal, behält keine Daten ABER ohne DELETE-Call (das ist „Pause", nicht „Forget")
  - `eeg_optimizer/telemetry_forget` → ruft DELETE-Endpoint und Lösch lokal (das ist „Recht auf Vergessen")
- **D-33:** Begründung Disable/Forget-Trennung: User soll Telemetrie pausieren können, ohne historische Daten zu verlieren. Wenn er „Forget" klickt → alles weg.

### Retry & Backoff
- **D-34:** HTTP-Client: `aiohttp.ClientSession`. Timeout 10 s pro Request. Bei Fehler: 1× sofortiger Retry, dann Event in Buffer schieben.
- **D-35:** Buffer-Flush: bei jedem Send-Versuch werden gepufferte Events FIFO mitgeschickt (max 10 pro Versuch, damit kein Burst). Wenn Send erfolgreich → aus Buffer entfernen.
- **D-36:** Backoff bei wiederholten 5xx/Network-Errors: exponentiell ab 1 min bis max 30 min. Reporter nutzt eigenen Timer, blockiert nicht den Optimizer-Cycle.

### Bestehende Optimizer-Logik
- **D-37:** Refactor `_should_block_charging` / `_should_discharge` ist BREAKING für interne Caller. Tests werden mitgezogen (in `tests/`).
- **D-38:** Activity-Log-Strings in `__init__.py` werden NICHT umgestellt — die sind userfreundliche deutsche Texte. Reasons-Keys werden separat geführt.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Backend (verbindlich, Phase 7)
- `EEGEnergyOptimzierBackend/src/types.ts` — Payload-Schemas (Snapshot, StateChange, Outcome, Failure, Profile, Register, Delete)
- `EEGEnergyOptimzierBackend/src/endpoints.ts` — Validation-Logik (z.B. Snapshot-Batch max 100, Pflichtfelder)
- `EEGEnergyOptimzierBackend/src/auth.ts` — Bootstrap-Token-Header `X-Bootstrap-Token`, Bearer-Format
- `EEGEnergyOptimzierBackend/migrations/0001_init.sql` — D1-Schema (für Verständnis der Felder)

### Bestehende HA-Integration (zu touchieren)
- `custom_components/eeg_energy_optimizer/optimizer.py` — Decision-Dataclass + `_should_*` Funktionen — Hauptziel des Refactors
- `custom_components/eeg_energy_optimizer/__init__.py` — async_setup_entry, 30-s-Timer, Activity-Log, Config-Migration — Reporter-Init
- `custom_components/eeg_energy_optimizer/statistics.py` — Feed-in-Stats — Outcome-Trigger-Punkt am Block-Ende
- `custom_components/eeg_energy_optimizer/sensor.py` — Sensor `Entscheidung` (Markdown-Renderer) — auf neue `reasons`-Felder umstellen
- `custom_components/eeg_energy_optimizer/const.py` — neue Telemetrie-Konstanten + Whitelist
- `custom_components/eeg_energy_optimizer/websocket_api.py` — WS-Command-Pattern (17 bestehende Commands als Vorlage)
- `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` — Panel-Sektion-Pattern, Translation-Keys
- `custom_components/eeg_energy_optimizer/translations/de.json`, `en.json` — neue Strings

### Roadmap & Memory
- `.planning/milestones/v1.1-telemetry-ROADMAP.md` — Success Criteria, Anhang A (D1-Schema), Anhang B (Auth-Flow), Anhang C (Sende-Frequenz)
- Memory: `project_reporting.md` — Eckdaten, verworfene Varianten

</canonical_refs>

<code_context>
## Existing Code Insights (aus Pre-Discuss-Scout)

- `Decision`-Dataclass hat **bereits** `block_reasons: list[str]` (Zeile 118) und `discharge_reasons: list[str]` (Zeile 134). Die Refactor-Arbeit ist also: Vereinheitlichen + `blocked_by` hinzufügen + `snapshot: dict` hinzufügen.
- `Snapshot`-Dataclass (Zeile 82-101) ist bereits gut strukturiert — ein Helper `Snapshot.to_telemetry_dict()` reicht für Feld 16/17 der State-Change-Payload.
- Activity-Log nutzt bereits `homeassistant.helpers.storage.Store` (siehe `__init__.py`) — gleicher Pattern für Telemetrie-Storage anwendbar, kein neues Abstraction-Layer nötig.
- Statistik-Tracker (`statistics.py`) tracked bereits `grid_export_kwh` und Session-Dauer pro State — perfekter Hook-Punkt für Outcome-Trigger.
- WebSocket-API hat bereits 17 Commands mit konsistentem Pattern (`@websocket_api.async_response`, Error-Handling) — neue 4 Commands folgen diesem Muster.
- HACS-Manifest (`manifest.json`) enthält `version` — auslesbar zur Laufzeit via `homeassistant.loader.async_get_integration(hass, DOMAIN)`.

</code_context>

<deferred_ideas>
## Deferred (für späteres Phasing oder Backlog)

- **`pv_peak_kwp` automatisch ermitteln** — heute nicht im Wizard erfasst. Backlog-Eintrag, kann bei Onboarding-V2 ergänzt werden.
- **Telemetrie-Diagnose-Card im Panel** — z.B. „letzte 10 Events, Buffer-Größe, letzte Antwort vom Backend" für User-Debugging. Nice-to-have für Phase 9 oder später.
- **Privacy-Doku-Generator** — automatisches Markdown aus `TELEMETRY_SETTINGS_KEYS` für README. Phase 10 (Sicherheit & Pflege).
- **HMAC-Body-Signatur** — als 30-Zeilen-Patch nachrüstbar, wenn ein Bedrohungsmodell-Update das fordert. Verworfen für V1.

</deferred_ideas>

<plans_preview>
## Plans (Vorschau, wird in /gsd-plan-phase finalisiert)

- **08-01-PLAN.md** — Decision-Refactor: `reasons`/`blocked_by`/`snapshot` Felder, Reasons-Katalog, `_should_*`-Signaturen, Konsumenten-Migration (sensor.py + Markdown), Tests.
- **08-02-PLAN.md** — `telemetry.py` (Reporter-Klasse: HTTP, Queue, Retry, Backoff) + `telemetry_buffer.py` (persistente Storage-Wrapper) + Mock-Server-Tests.
- **08-03-PLAN.md** — Hooks: Reporter-Init in `__init__.py`, Snapshot-Timer (30 min), Outcome-Trigger in `statistics.py`, Failure-Detektion (Sensor-Unavailability + Inverter/Forecast-Errors), 4 WebSocket-Commands.
- **08-04-PLAN.md** — Panel-Sektion „Community-Statistik" (Toggle, Status, Forget-Button), Translations, manifest.json Version-Bump auf 1.1.0-dev-01.

</plans_preview>
