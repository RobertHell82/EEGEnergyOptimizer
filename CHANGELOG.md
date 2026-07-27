# Changelog

Alle nennenswerten Änderungen am EEG Energy Optimizer.

Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [SemVer](https://semver.org/lang/de/).

> Hinweis: DEV-Repo nutzt Patch-Versionen (1.x.y); Release-Versionen werden im Release-Repo getaggt.

## [1.3.3] - 2026-07-27

> Release konsolidiert die DEV-Iterationen 1.3.0-dev bis 1.3.3-dev (Einspeisebegrenzung optimieren + Huawei-EMMA-Support).

### Hinzugefügt

- **Neues Feature „Einspeisebegrenzung optimieren" (Huawei/Fronius, opt-in).** Solange die PV-Restprognose für heute den restlichen Tagesverbrauch (inkl. Sicherheitspuffer) plus die fehlende Batterieenergie übersteigt — dieselbe Prüfung wie bei der Morgen-Einspeisung, aber ohne deren Zeitfenster (aktiv nur tagsüber ab 1 h vor Sonnenaufgang, Hysterese ×1,1 bei Reaktivierung am selben Tag) — wird das Voll-Laden der Batterie gedrosselt: Die Einspeisung geht bis zum konfigurierten Einspeiselimit ins Netz, nur der Überschuss darüber lädt die Batterie (Ladeleistung 0 = Laden vollständig blockiert). Feedback-Regelung auf die gemessene Netzeinspeisung (Nachregelung alle 60 s), asymmetrisch: langsames Anheben, sofortiges Absenken bei PV-Einbruch (Netzbezug-Schutz in jedem Zyklus). Zustandspriorität: geregelte Ladeleistung > 0 vor Morgen-Einspeisung; bei 0 im Morgen-Fenster wird weiterhin „Morgen-Einspeisung" angezeigt (identische Ausführung), die Nacht-Entladung (inkl. Slot B) behält Vorrang. Neuer Optimizer-Zustand „Einspeisebegrenzung", neue Wizard-Seite + Settings-Sektion (nur Huawei/Fronius), neuer Anleitungs-Guide. Standardmäßig **aus** — bestehende Installationen bleiben unverändert (Config-Migration v20).

### Geändert

- **Huawei-EMMA-Sensoren werden jetzt unterstützt (automatische Netz-Vorzeichen-Korrektur).** Die Einspeiseleistung des EMMA-Energiemanagements (entity_id-Präfix `sensor.emma_…`) liefert das Netz-Vorzeichen umgekehrt gegenüber der direkten SUN2000-Anbindung. Die neue zentrale Vorzeichen-Auflösung `power_readings.resolve_sign` erkennt solche Sensoren bei Huawei-Setups und dreht das Netz-Vorzeichen automatisch um; die Batterieleistung folgt der normalen SUN2000-Konvention und bleibt unverändert. Hausverbrauch, Netz-/Batterieleistung, Feed-in-Statistik, Optimizer-Snapshot und Statistik-Backfill leiten ihr Vorzeichen einheitlich hierüber ab. Der bisherige Hinweis „Huawei über EMMA wird nicht unterstützt" (Guide + README) entfällt.

## [1.3.3-dev] - 2026-07-27

### Behoben

- **Huawei EMMA: Vorzeichen-Inversion gilt nur noch für die Netzleistung (Einspeiseleistung).** Die in 1.3.0 eingeführte EMMA-Erkennung (`resolve_sign`) drehte das Vorzeichen fälschlich auch für die Batterieleistung um — die EMMA-Batterieleistung folgt aber der normalen SUN2000-Konvention (positiv = Laden). Jetzt wird nur noch das Netz-Vorzeichen (`grid_sign`) bei `sensor.emma_*`-Sensoren invertiert; `battery_sign` bleibt unverändert. Betrifft Hausverbrauch-/Batterieleistung-Sensor, Optimizer-Snapshot, Feed-in-Statistik und Statistik-Backfill (heilt sich beim nächsten Neustart selbst).

## [1.3.2-dev] - 2026-07-23

### Behoben

- **Huawei EMMA: Statistik-Backfill verfälschte den historischen Hausverbrauch bei jedem Neustart.** Der Backfill (`async_backfill_hausverbrauch_stats`), der beim HA-Start den Hausverbrauch aus den Quellsensoren nachberechnet und die Langzeit-Statistik im Lookback-Fenster überschreibt, nutzte die Vorzeichen-Konvention direkt — **ohne** die in 1.3.0 eingeführte EMMA-Inversion (`resolve_sign`). Bei EMMA-Anlagen wurden Netz- und Batterieleistung dadurch mit umgekehrtem Vorzeichen verrechnet: Der historische Hausverbrauch war um `2 × (Export + Entladung)` überhöht (an Sonnentagen 3–6-facher Tagesverbrauch, z. B. 95 statt ~15 kWh) — und der Backfill machte auch korrekt live aufgezeichnete Werte bei jedem Neustart wieder kaputt. Da das Verbrauchsprofil aus genau diesen Statistiken lernt, waren alle Verbrauchsprognosen (Morgen-Einspeisung, Min-SOC, Einspeisebegrenzung) massiv zu hoch. **Der Fix ist selbstheilend:** Beim nächsten Neustart rechnet der Backfill das komplette Lookback-Fenster korrekt neu und überschreibt die fehlerhaften Werte — kein manuelles Löschen nötig. Neue gemeinsame Vorzeichen-Auflösung `power_readings.resolve_backfill_signs` (Single-Sensor via `resolve_sign` inkl. EMMA, Paar-Konfigurationen behalten das Basis-Vorzeichen).
- **Vorzeichen-Audit:** Auch der SolarEdge-Netzbezug-Watchdog löst sein Netz-Vorzeichen jetzt über `resolve_sign` auf (statt Direktzugriff auf die Konventions-Tabelle) — funktional unverändert (der Watchdog läuft nur bei SolarEdge), aber damit gehen alle Vorzeichen-Auflösungen im Code über eine einzige Stelle. Doku-Korrektur: Der Netzleistung-Sensor ist positiv = Einspeisung (CLAUDE.md nannte fälschlich positiv = Bezug).

## [1.3.1-dev] - 2026-07-22

### Geändert

- **„Einspeisebegrenzung optimieren" grundlegend überarbeitet: prognosebasiertes Drosseln statt reaktiver Abregelungs-Erkennung.** Das Feature greift jetzt, sobald die PV-Restprognose für heute den restlichen Tagesverbrauch (inkl. Sicherheitspuffer) plus die fehlende Batterieenergie übersteigt — dieselbe Prüfung wie bei der Morgen-Einspeisung, aber ohne deren Zeitfenster (Hysterese ×1,1 bei Reaktivierung am selben Tag, aktiv nur tagsüber ab 1 h vor Sonnenaufgang). Solange die Batterie heute sicher noch voll wird, wird das Voll-Laden gedrosselt: Einspeisung bis zum Limit, nur der Überschuss darüber lädt die Batterie (Ladeleistung 0 = Laden vollständig blockiert, kein Austritt mehr). Reicht die Prognose nicht, lädt die Batterie normal mit voller Leistung. Bisher aktivierte sich die Regelung nur, wenn die Einspeisung bereits am Limit klebte — was außerhalb der Morgen-Einspeisung praktisch nie eintrat, weil der Überschuss zuerst in die Batterie floss. Zustandspriorität: bei geregelter Ladeleistung > 0 vor der Morgen-Einspeisung; bei 0 im Morgen-Fenster wird weiterhin „Morgen-Einspeisung" angezeigt (identische Ausführung), die Nacht-Entladung (inkl. Slot B) behält Vorrang. Neue Diagnose-Keys `feedin_limit_forecast_low`/`feedin_limit_not_daytime` (ersetzt `feedin_limit_no_surplus`); Statustexte, Panel-Beschreibungen und Guide entsprechend aktualisiert.

## [1.3.0-dev] - 2026-07-22

### Hinzugefügt

- **Neues Feature „Einspeisebegrenzung optimieren" (Huawei/Fronius, opt-in).** Regelt die Batterie-Ladeleistung dynamisch, sodass die Netzeinspeisung am konfigurierten Einspeiselimit bleibt und PV-Überschuss geladen statt vom Wechselrichter abgeregelt wird. Erkennt das Abregeln daran, dass die Einspeisung am Limit „klebt", und tastet die Ladeleistung testend hoch (Feedback auf die gemessene Netzeinspeisung, Nachregelung alle 60 s). Asymmetrische Regelung — langsames Anheben, sofortiges Absenken bei PV-Einbruch (Netzbezug-Schutz). Kombiniert sich mit der Morgen-Einspeisung (rettet dort sonst abgeregelte Energie) und hat Vorrang, solange Überschuss über dem Limit anfällt. Neuer Optimizer-Zustand `Einspeisebegrenzung`, neue Wizard-Seite + Settings-Sektion (nur Huawei/Fronius), neuer Anleitungs-Guide. Standardmäßig **aus** — bestehende Installationen bleiben unverändert (Config-Migration v20).

### Geändert

- **Huawei-EMMA-Sensoren werden jetzt unterstützt (automatische Vorzeichen-Korrektur).** Sensoren des Huawei-EMMA-Energiemanagements (entity_id-Präfix `sensor.emma_…`) liefern Netz- und Batterieleistung mit umgekehrtem Vorzeichen gegenüber der direkten SUN2000-Anbindung. Die neue zentrale Funktion `power_readings.resolve_sign` erkennt solche Sensoren bei Huawei-Setups und dreht das Vorzeichen automatisch um — Hausverbrauch, Netz-/Batterieleistung, Feed-in-Statistik und Optimizer-Snapshot leiten ihr Vorzeichen jetzt einheitlich hierüber ab. Der bisherige Hinweis „Huawei über EMMA wird nicht unterstützt" (Guide + README) entfällt.

## [1.2.18] - 2026-07-17

> Release: Huawei über EMMA offiziell als nicht unterstützt ausgewiesen.

### Geändert

- **Huawei-Doku: Verbindung über EMMA wird nicht unterstützt.** Der Huawei-Guide (`docs/guides/huawei.md`) und die README-Liste der unterstützten Wechselrichter weisen nun ausdrücklich aus, dass nur die **direkte** Anbindung an den SUN2000-Wechselrichter/Dongle unterstützt wird. Bei einer Verbindung über das EMMA-Energiemanagement (`sensor.emma_*`) ist keine Batteriesteuerung möglich — EMMA übernimmt selbst das Batteriemanagement, sodass die zum Steuern nötigen Dienste (`forcible_discharge_soc`, Ladeleistungs-Limit) nicht bereitstehen; zusätzlich weichen Sensor-Namen und -Vorzeichen ab (u. a. invertiertes Netz-Vorzeichen bei `sensor.emma_einspeiseleistung`, was zu falschem Hausverbrauch/Netzfluss führt). Der Port-Hinweis nennt Port 502 nur noch als „ältere Firmware", nicht mehr als EMMA-Option.

### Nicht verhaltensrelevant

Reine Dokumentationsänderungen, keine Änderungen an der Optimizer-/Steuerungslogik.

## [1.2.17] - 2026-07-02

> Release: Enduser-Doku für den Fernzugang und Feinschliff der Inbetriebnahme-Anleitung.

### Hinzugefügt

- **Anleitung „Fernzugang einrichten (Cloudflare Tunnel)"** (`docs/deployment/fernzugang-cloudflared.md`): Schritt-für-Schritt-Einrichtung des Cloudflared-Add-ons ohne eigenes Cloudflare-Konto — Installation, Token-Eintragung, `trusted_proxies`-Vorbereitung via File editor, Starten und Testen, plus Problem-Tabelle.

### Geändert

- **Inbetriebnahme-Anleitung gestrafft:** Standort als Priorität 1, TIP-Hinweis zum vorbereiteten EEG-Fernzugang, Forecast.Solar als optionale Alternative statt vorinstalliert, Werk-Platzhalter für den Standort gekennzeichnet, Hinweise auf ältere HA-Versionen entfernt, an neue HA-Terminologie „Apps" angepasst.

### Nicht verhaltensrelevant

Reine Dokumentationsänderungen, keine Änderungen an der Optimizer-/Steuerungslogik.

## [1.2.11] - 2026-06-06

> Release: Doku-Feinschliff.

### Geändert

- **HACS-Installationsanleitung:** „Get HACS" Add-on als primäre Methode (ohne Terminal), inkl. My-Home-Assistant-Link zum direkten Hinzufügen des Add-on-Repositories; Terminal-Variante bleibt als Alternative.
- **Huawei-Guide:** Warnhinweis „Nur EINE Modbus-Verbindung gleichzeitig möglich / FusionSolar App komplett schließen" entfernt.

### Nicht verhaltensrelevant

Reine Dokumentationsänderungen, keine Änderungen an Optimizer-/Steuerungslogik.

## [1.2.10] - 2026-06-06

> Release: Dokumentationsordner mit Enduser-Anleitungen, In-App-Guides aus zentraler Quelle generiert.

### Hinzugefügt

- **`docs/`-Ordner als zentrale Dokumentation.** Enduser-Einstiegsseite (`docs/README.md`) mit Schritt-für-Schritt-Anleitungen: HACS-Installation, Installation der EEG-Integration über HACS, sowie alle 7 Einrichtungs-Guides (Huawei, Huawei-Kapazitätssensor, Fronius, SolaX, SolarEdge, Solcast, Forecast.Solar) als Markdown — auf GitHub direkt lesbar inkl. Screenshots. Entwickler-Hinweise separat in `docs/DEVELOPMENT.md`.
- **Single Source of Truth + Sync-Guard.** `docs/guides/` + `docs/images/` sind die einzige Quelle der In-App-Anleitungen. `scripts/build_guides.py` generiert daraus die HTML-Fragmente für das Panel (`--check`-Modus für Verifikation); GitHub Action `docs-sync.yml` schlägt bei Divergenz fehl. Redundanter Root-Ordner `guide screenshots/` entfernt (nach `docs/images/` konsolidiert).

### Geändert

- **Panel lädt Anleitungen zur Laufzeit.** `DIALOG_CONTENT` enthält nur noch Datei-Referenzen; die „Anleitung"-Dialoge laden die generierten HTML-Fragmente per `fetch()` von `/eeg_optimizer_panel/guide/` (mit Cache, Lade- und Fehlerzustand). ~430 Zeilen Inline-HTML aus dem Panel-JS entfernt, Guide-Styling zentral als CSS (inkl. Alert-Boxen aus GitHub-Alert-Syntax).

### Nicht verhaltensrelevant

Keine Änderungen an der Optimizer-/Steuerungslogik. Suite 496 passed, 31 skipped.

## [1.2.9] - 2026-05-28

> Release konsolidiert die DEV-Iteration 1.2.9-dev-01 (SolarEdge Multi-Inverter Combined-SOC + proportionale Discharge-Verteilung).

### Hinzugefügt

- **SolarEdge Multi-Inverter: kapazitätsgewichteter Combined-SOC + Summenkapazität.** Bei Setups mit mehreren SolarEdge-Invertern (i1+i2+…) liefert die `solaredge_modbus_multi`-Integration pro Inverter einen eigenen `b1_state_of_energy`/`b1_maximum_energy`. Der Optimizer las bisher nur den ersten (i1) → falscher Maßstab, der die Slot-B-Entladung zu früh stoppte (Live-Befund 28.05.2026 Linzner: i1=44 % / i2=19 %, gewichtet 34,6 % — Optimizer sah aber „44 %" und plante mit `available_kwh = (44−min)/100 × 24.25 kWh` statt mit 38.8 kWh Summenkapazität). Neue optionale `InverterBase.get_combined_battery_state()` mit SolarEdge-Override: `combined_soc = Σ(soc_i × cap_i) / Σ(cap_i)`, `combined_cap = Σ(cap_i)`. Optimizer-Snapshot überstimmt damit Config-Sensor + manuelle Kapazität automatisch. Default `(None, None)` für Single-Battery-Driver (Huawei/Fronius/SolaX) — unverändertes Verhalten.
- **Zwei neue HA-Sensoren für SolarEdge-Multi:** `sensor.eeg_energy_optimizer_combined_soc` (% gewichtet, `device_class: battery`) und `sensor.eeg_energy_optimizer_combined_capacity` (kWh Summe). Werden nur registriert, wenn der Driver `get_combined_battery_state()` non-None liefert. Single-Battery-Setups bekommen keine zusätzlichen Entities.
- **Wizard kennt SolarEdge-Sonderfall.** Step 3 (Batteriesensoren) zeigt bei `inverter_type=solaredge_storedge` nur einen Info-Block statt der SOC-/Kapazitäts-Eingaben; Validation skippt die Pflichtfelder, Auto-Detection befüllt `battery_soc_sensor`/`battery_capacity_sensor` nicht mehr mit i1-Sensoren, beim Save trägt der Wizard die pinned Combined-Sensor-IDs ein.
- **Migration v18 → v19.** Bestehende SolarEdge-Entries werden beim Reload automatisch auf die Combined-Sensor-IDs umgestellt. Andere Inverter unverändert. `battery_capacity_kwh` bleibt aus Nachvollziehbarkeit in der Config.

### Geändert

- **SolarEdge `async_set_discharge` verteilt Power proportional zur freien Restkapazität.** Bisher: `power_kw / num_inverters` (stur halbiert). Bei ungleichen Batterien (z. B. i1=24.25 kWh / i2=14.55 kWh, Backup je 20 %) erreichte die kleinere viel früher das Backup-Limit, danach lief nur i1 weiter — Slot-B-Energie unausgeschöpft. Neu: pro Inverter `usable_kwh = max(0, (soc − backup) / 100 × cap)`, Power-Anteil proportional zur Summe, gecappt auf `max_discharge_power` pro Inverter, mit iterativer Cap-Redistribution. Fallback auf Equal-Split, falls ein Sensor unavailable. Effekt: Beide Batterien erreichen ungefähr gleichzeitig die Backup-Reserve — ~14.8 kWh statt ~10 kWh in 2 h bei `discharge_power_kw=8`.

### Behoben

- **SolarEdge: `_resolve_entity_for_prefix` kannte keine Suffix-Varianten.** Bei i2 wurde z. B. `number.solaredge_i2_storage_backup_reserve` gesucht, in vielen Installationen heißt die Entity aber `number.solaredge_i2_backup_reserve` (ohne `storage_`-Präfix). Der Resolver fiel auf den Default ohne Prefix zurück → falsche/fehlende Reads. `SOLAREDGE_SUFFIX_VARIANTS` wird nun auch im Prefix-Pfad konsultiert, analog zum primären Resolver.

### Nicht verhaltensrelevant

3 neue Migration-Tests (v19 SolarEdge / Other / Idempotenz), 16 neue SolarEdge-Driver-Tests (Distribution + Combined-State), `mock_inverter`-Fixture liefert `get_combined_battery_state() → (None, None)` als sauberen Default. Suite **480 passed, 31 skipped**.

## [1.2.9-dev-01] - 2026-05-28

### Hinzugefügt

- **SolarEdge Multi-Inverter: kapazitätsgewichteter Combined-SOC + Summenkapazität.** Bei Setups mit mehreren SolarEdge-Invertern (i1+i2+…) liefert die `solaredge_modbus_multi`-Integration pro Inverter einen eigenen `b1_state_of_energy`/`b1_maximum_energy`. Der Optimizer las bisher nur den ersten (i1) → falscher Maßstab, der die Slot-B-Entladung zu früh stoppte (Live-Befund 28.05.2026 Linzner: i1=44 % / i2=19 %, gewichtet 34,6 % — Optimizer sah aber „44 %" und plante mit `available_kwh = (44−min)/100 × 24.25 kWh` statt mit 38.8 kWh Summenkapazität). Neue optionale `InverterBase.get_combined_battery_state()` mit SolarEdge-Override: `combined_soc = Σ(soc_i × cap_i) / Σ(cap_i)`, `combined_cap = Σ(cap_i)`. Optimizer-Snapshot überstimmt damit Config-Sensor + manuelle Kapazität automatisch. Default `(None, None)` für Single-Battery-Driver (Huawei/Fronius/SolaX) — unverändertes Verhalten.
- **Zwei neue HA-Sensoren für SolarEdge-Multi:** `sensor.eeg_energy_optimizer_combined_soc` (% gewichtet, `device_class: battery`) und `sensor.eeg_energy_optimizer_combined_capacity` (kWh Summe). Werden nur registriert, wenn der Driver `get_combined_battery_state()` non-None liefert. Single-Battery-Setups bekommen keine zusätzlichen Entities.
- **Wizard kennt SolarEdge-Sonderfall.** Step 3 (Batteriesensoren) zeigt bei `inverter_type=solaredge_storedge` nur einen Info-Block statt der SOC-/Kapazitäts-Eingaben; Validation skippt die Pflichtfelder, Auto-Detection befüllt `battery_soc_sensor`/`battery_capacity_sensor` nicht mehr mit i1-Sensoren, beim Save trägt der Wizard die pinned Combined-Sensor-IDs ein.
- **Migration v18 → v19.** Bestehende SolarEdge-Entries werden beim Reload automatisch auf die Combined-Sensor-IDs umgestellt. Andere Inverter unverändert. `battery_capacity_kwh` bleibt aus Nachvollziehbarkeit in der Config.

### Geändert

- **SolarEdge `async_set_discharge` verteilt Power proportional zur freien Restkapazität.** Bisher: `power_kw / num_inverters` (stur halbiert). Bei ungleichen Batterien (z. B. i1=24.25 kWh / i2=14.55 kWh, Backup je 20 %) erreichte die kleinere viel früher das Backup-Limit, danach lief nur i1 weiter — Slot-B-Energie unausgeschöpft. Neu: pro Inverter `usable_kwh = max(0, (soc − backup) / 100 × cap)`, Power-Anteil proportional zur Summe, gecappt auf `max_discharge_power` pro Inverter, mit iterativer Cap-Redistribution. Fallback auf Equal-Split, falls ein Sensor unavailable. Effekt: Beide Batterien erreichen ungefähr gleichzeitig die Backup-Reserve — ~14.8 kWh statt ~10 kWh in 2 h bei `discharge_power_kw=8`.

### Behoben

- **SolarEdge: `_resolve_entity_for_prefix` kannte keine Suffix-Varianten.** Bei i2 wurde z. B. `number.solaredge_i2_storage_backup_reserve` gesucht, in vielen Installationen heißt die Entity aber `number.solaredge_i2_backup_reserve` (ohne `storage_`-Präfix). Der Resolver fiel auf den Default ohne Prefix zurück → falsche/fehlende Reads. `SOLAREDGE_SUFFIX_VARIANTS` wird nun auch im Prefix-Pfad konsultiert, analog zum primären Resolver.

### Nicht verhaltensrelevant

3 neue Migration-Tests (v19 SolarEdge / Other / Idempotenz), 16 neue SolarEdge-Driver-Tests (Distribution + Combined-State), `mock_inverter`-Fixture liefert `get_combined_battery_state() → (None, None)` als sauberen Default. Suite **480 passed, 31 skipped**.

## [1.2.7-dev-02] - 2026-05-21

### Behoben

- **Morgen-Einspeisungs-Karte zeigte fälschlich „aktiv" während Hysterese blockierte.** `_morning_delay_status` (Status-Karte) prüfte `pv_today > bedarf`, während `_should_block_charging` bei Reaktivierung am selben Tag die strengere Schwelle `pv_today > bedarf × 1.1` anlegt. Folge: Karte meldete grün „● AKTIV — Ladung blockiert bis 11:00", obwohl der Optimizer korrekt im Normalbetrieb war und die Batterie weiter aus PV-Überschuss lud (Live-Beispiel 21.05.2026 Traun: PV-Prognose 35,3 kWh, Bedarf 33,2 kWh, Hysterese-Schwelle 36,5 kWh — Karte „aktiv", `ladung_blockiert=false`, Inverter `Max. Ladeleistung = 5000 W`). Jetzt: Karte spiegelt dieselbe Hysterese-Logik wie der Block-Pfad, neues Decision-Feld `morning_hysteresis_active` + Sensor-Attribut, Frontend zeigt orange „+10 % Hysterese"-Badge analog zur Discharge-Karte; Threshold-Anzeige und Details-Body geben Basis-Bedarf und ×1.1-Schwelle aus.

### Nicht verhaltensrelevant

Reine Anzeige-Korrektur. Die Lade-Steuerung (`_should_block_charging`, Inverter-Befehle) war bereits korrekt und ist nicht berührt. Drei neue Unit-Tests in `TestHysteresis` decken den Karten-Pfad gegen den Block-Pfad ab; Suite 477 passed.

## [1.2.7] - 2026-05-18

> Release konsolidiert die DEV-Iteration 1.2.7-dev-01 (Telemetry Backend-Quality Fixes).

### Behoben

- **Telemetrie: Abend-Outcome enthielt PV-Forecast für morgen.** `_build_block_predictions` schrieb für `abend_entladung` `predicted_pv_kwh = discharge_pv_tomorrow_kwh` (Tages-PV-Prognose nächster Tag) und `predicted_consumption_kwh = discharge_consumption_daylight_kwh` ins Outcome — beide Werte gelten für den nächsten Tag, nicht für den Abend-Block (Sonnenuntergang → 04:00). Folge: 50/55 Abend-Outcomes mit `avg(predicted_pv_kwh) = 25,56 kWh` bei `avg(actual) = 0,23`. Jetzt: `predicted_pv_kwh = 0.0`, `predicted_consumption_kwh = discharge_demand_overnight_kwh` (block-spezifisch).
- **Telemetrie: voller Tagesforecast statt Block-Skalierung.** Bei leerem `planned_block_end` (mehrere Fallback-Pfade in `_compute_planned_block_end` lieferten `""` — z. B. `compute_hard_cutoff = None`, PeakShare-Parse-Fehler) blieb die fraction-Skalierung bei `1.0` und der gesamte 24h-Forecast landete als Block-Wert ins Outcome (Production-Belege mit `predicted_pv_kwh` = 102.3 / 119.2 / 87.3 kWh in 5–15 min Blöcken). Jetzt: ohne valides `planned_block_end` werden `predicted_*` als `None` gesetzt (Backend ist null-tolerant). Skalierungspfad bleibt nur für Morgen-Einspeisung aktiv.
- **Telemetrie: Restart-Cluster (mehrere Outcomes pro echtem Block).** `block_predictions` / `block_samples` / `block_actuals_state` lebten ausschließlich im Memory und gingen beim HA-Restart verloren, während `FeedinStats._current_session` aus dem `Store` rehydriert wurde. Beim Boot-Race (Mode noch `MODE_AUS`, weil die `select`-Entity noch nicht hydratisiert war) feuerte der erste Cycle fälschlich ein Block-Ende. Folge: derselbe Abend-Block produzierte 4–6 Outcomes mit identischen `predicted_*`. Jetzt: dedizierter Store `{DOMAIN}_{entry_id}_block_state` persistiert alle drei Strukturen (sofort bei Block-Start/Ende, throttled alle 5 min während der Sample-Phase). `FeedinStats.async_update` überspringt im ersten Cycle nach Restart das `_close_session`.
- **Telemetrie: Zeitzonen-Inkonsistenz `started_at` ↔ `ended_at`.** `started_at` kam aus `decision.timestamp` (lokale tz, z. B. `+02:00 CEST`), `ended_at` war hart UTC (`+00:00`). Mischbetrieb im selben Outcome führte am Backend zu falscher Tageszuordnung beim `substr(ts, 1, 10)`-Bucketing. Jetzt: Helper `_to_utc_iso` normalisiert beide Felder konsistent auf UTC.
- **Telemetrie: Outcomes mit allen 4 Forecast-Feldern NULL.** Wenn weder Predictions (`_capture_block_predictions` lief nicht — z. B. nach Restart, da `prev_zustand = None` ≠ `STATE_NORMAL`) noch Block-Samples vorlagen, wurde trotzdem ein nutzloser Metadaten-Outcome ans Backend gesendet (22 Records in der Production-Stichprobe). Jetzt: early return mit State-Cleanup, wenn beide Quellen fehlen — Backend-Forecast-MAE-Statistik bleibt sauber.

### Geändert

- **Telemetrie-Profile-Payload trägt jetzt `pv_peak_kwp`.** Neue optionale Konfigurationsoption „PV-Spitzenleistung (kWp)" im Setup-Wizard (PV-Sensor-Step). Wird ins Profile-Payload mitgesendet, sodass das Backend serverseitige Sanity-Caps anwenden kann (z. B. `predicted_pv_kwh ≤ 2 × pv_peak_kwp`). Leer lassen wenn unbekannt — Backend nimmt dann keine Caps an. Bestehende Installationen bleiben unverändert, bis der Wert manuell im Wizard ergänzt wird.

### Nicht verhaltensrelevant

Alle Fixes betreffen ausschließlich den Telemetrie-Pfad (Predictions, Outcomes, Profile). Die Lade-/Entlade-Steuerung (`_should_block_charging`, `_should_discharge`, PeakShare-Plan-Logik) ist davon nicht berührt — die operativen Forecasts in `Snapshot` werden nicht skaliert und nicht über die Block-Capture-Pfade gelesen.

## [1.2.7-dev-01] - 2026-05-18

### Behoben

- **Telemetrie: Abend-Outcome enthielt PV-Forecast für morgen.** `_build_block_predictions` schrieb für `abend_entladung` `predicted_pv_kwh = discharge_pv_tomorrow_kwh` (Tages-PV-Prognose nächster Tag) und `predicted_consumption_kwh = discharge_consumption_daylight_kwh` ins Outcome — beide Werte gelten für den nächsten Tag, nicht für den Abend-Block (Sonnenuntergang → 04:00). Folge: 50/55 Abend-Outcomes mit `avg(predicted_pv_kwh) = 25,56 kWh` bei `avg(actual) = 0,23`. Jetzt: `predicted_pv_kwh = 0.0`, `predicted_consumption_kwh = discharge_demand_overnight_kwh` (block-spezifisch).
- **Telemetrie: voller Tagesforecast statt Block-Skalierung.** Bei leerem `planned_block_end` (mehrere Fallback-Pfade in `_compute_planned_block_end` lieferten `""` — z. B. `compute_hard_cutoff = None`, PeakShare-Parse-Fehler) blieb die fraction-Skalierung bei `1.0` und der gesamte 24h-Forecast landete als Block-Wert ins Outcome (Production-Belege mit `predicted_pv_kwh` = 102.3 / 119.2 / 87.3 kWh in 5–15 min Blöcken). Jetzt: ohne valides `planned_block_end` werden `predicted_*` als `None` gesetzt (Backend ist null-tolerant). Skalierungspfad bleibt nur für Morgen-Einspeisung aktiv.
- **Telemetrie: Restart-Cluster (mehrere Outcomes pro echtem Block).** `block_predictions` / `block_samples` / `block_actuals_state` lebten ausschließlich im Memory und gingen beim HA-Restart verloren, während `FeedinStats._current_session` aus dem `Store` rehydriert wurde. Beim Boot-Race (Mode noch `MODE_AUS`, weil die `select`-Entity noch nicht hydratisiert war) feuerte der erste Cycle fälschlich ein Block-Ende. Folge: derselbe Abend-Block produzierte 4–6 Outcomes mit identischen `predicted_*`. Jetzt: dedizierter Store `{DOMAIN}_{entry_id}_block_state` persistiert alle drei Strukturen (sofort bei Block-Start/Ende, throttled alle 5 min während der Sample-Phase). `FeedinStats.async_update` überspringt im ersten Cycle nach Restart das `_close_session`.
- **Telemetrie: Zeitzonen-Inkonsistenz `started_at` ↔ `ended_at`.** `started_at` kam aus `decision.timestamp` (lokale tz, z. B. `+02:00 CEST`), `ended_at` war hart UTC (`+00:00`). Mischbetrieb im selben Outcome führte am Backend zu falscher Tageszuordnung beim `substr(ts, 1, 10)`-Bucketing. Jetzt: Helper `_to_utc_iso` normalisiert beide Felder konsistent auf UTC.
- **Telemetrie: Outcomes mit allen 4 Forecast-Feldern NULL.** Wenn weder Predictions (`_capture_block_predictions` lief nicht — z. B. nach Restart, da `prev_zustand = None` ≠ `STATE_NORMAL`) noch Block-Samples vorlagen, wurde trotzdem ein nutzloser Metadaten-Outcome ans Backend gesendet (22 Records in der Production-Stichprobe). Jetzt: early return mit State-Cleanup, wenn beide Quellen fehlen — Backend-Forecast-MAE-Statistik bleibt sauber.

### Geändert

- **Telemetrie-Profile-Payload trägt jetzt `pv_peak_kwp`.** Neue optionale Konfigurationsoption „PV-Spitzenleistung (kWp)" im Setup-Wizard (PV-Sensor-Step). Wird ins Profile-Payload mitgesendet, sodass das Backend serverseitige Sanity-Caps anwenden kann (z. B. `predicted_pv_kwh ≤ 2 × pv_peak_kwp`). Leer lassen wenn unbekannt — Backend nimmt dann keine Caps an. Bestehende Installationen bleiben unverändert, bis der Wert manuell im Wizard ergänzt wird.

### Nicht verhaltensrelevant

Alle Fixes betreffen ausschließlich den Telemetrie-Pfad (Predictions, Outcomes, Profile). Die Lade-/Entlade-Steuerung (`_should_block_charging`, `_should_discharge`, PeakShare-Plan-Logik) ist davon nicht berührt — die operativen Forecasts in `Snapshot` werden nicht skaliert und nicht über die Block-Capture-Pfade gelesen.

## [1.2.6] - 2026-05-18

> Release konsolidiert die DEV-Iteration 1.2.6-dev-01 (SolaX Charge-Block ohne Battery-Idle + PeakShare Plan-Verriegelung).

### Behoben

- **PeakShare-Mini-Blöcke bei Cache-Refresh.** Ein laufender PeakShare-Entladeplan wurde verworfen, sobald `async_fetch` nach dem 6-h-Cache-Ablauf neue API-Daten zog. Der Recompute lief mit dem inzwischen reduzierten Restspeicher und ggf. veränderten Stündlich-Forecast-Werten — das beste Fenster verschob sich häufig in die Zukunft, und der gerade aktive Discharge brach nach wenigen Minuten in `Normalbetrieb` ab (Live-Bug 17./18.05.2026: Slot A 21:11–21:16, dann 00:00–00:04). Der Plan ist nun verriegelt, solange `now` innerhalb `[plan_start, plan_end)` liegt — sowohl im `async_fetch`-Invalidate-Pfad als auch bei Mitternachts-Datumswechseln in `get_discharge_plan`.

### Geändert

- **SolaX:** Morgen-Einspeisung blockiert jetzt nur noch das Laden statt die Batterie via Mode 1 komplett auf Idle zu setzen. Hausverbrauch wird wieder aus der Batterie gedeckt (bis `selfuse_discharge_min_soc`, typisch 10 %), nicht mehr aus dem Netz. Bringt das SolaX-Verhalten auf gleiches Niveau wie Huawei und Fronius.
- **SolaX:** `async_stop_forcible` setzt das Lade-Limit jetzt automatisch auf den vor dem Eingriff gespeicherten Originalwert zurück. Persistierung via `homeassistant.helpers.storage.Store` — überlebt HA-Reboots.

### Verhaltensänderung beim Update

Auf SolaX-Anlagen: Während Morgen-Einspeisung wird die Batterie nicht mehr eingefroren. Wenn vorher der SOC bei ~19 % stehengeblieben ist, weil Mode 1 mit `active_power=0` die Batterie komplett stillgelegt hat, entlädt sie jetzt weiter bis zum konfigurierten `selfuse_discharge_min_soc` des Wechselrichters (Default 10 %). Der Original-Wert von `battery_charge_max_current` wird beim ersten Optimizer-Cycle nach dem Update automatisch erkannt und gespeichert.

### Migration

- Config-Schema v17 → v18: Neuer interner Entity-Override-Key `solax_battery_charge_max_current` (Default: `number.solax_inverter_battery_charge_max_current`). Automatisch via `async_migrate_entry` gesetzt — keine User-Aktion nötig.

## [1.2.6-dev-01] - 2026-05-18

### Behoben

- **PeakShare-Mini-Blöcke bei Cache-Refresh.** Ein laufender PeakShare-Entladeplan wurde verworfen, sobald `async_fetch` nach dem 6-h-Cache-Ablauf neue API-Daten zog. Der Recompute lief mit dem inzwischen reduzierten Restspeicher und ggf. veränderten Stündlich-Forecast-Werten — das beste Fenster verschob sich häufig in die Zukunft, und der gerade aktive Discharge brach nach wenigen Minuten in `Normalbetrieb` ab (Live-Bug 17./18.05.2026: Slot A 21:11–21:16, dann 00:00–00:04). Der Plan ist nun verriegelt, solange `now` innerhalb `[plan_start, plan_end)` liegt — sowohl im `async_fetch`-Invalidate-Pfad als auch bei Mitternachts-Datumswechseln in `get_discharge_plan`. (Phase 12)

### Geändert

- **SolaX:** Morgen-Einspeisung blockiert jetzt nur noch das Laden statt die Batterie via Mode 1 komplett auf Idle zu setzen. Hausverbrauch wird wieder aus der Batterie gedeckt (bis `selfuse_discharge_min_soc`, typisch 10 %), nicht mehr aus dem Netz. Bringt das SolaX-Verhalten auf gleiches Niveau wie Huawei und Fronius. (Phase 12)
- **SolaX:** `async_stop_forcible` setzt das Lade-Limit jetzt automatisch auf den vor dem Eingriff gespeicherten Originalwert zurück. Persistierung via `homeassistant.helpers.storage.Store` — überlebt HA-Reboots. (Phase 12)

### Verhaltensänderung beim Update

Auf SolaX-Anlagen: Während Morgen-Einspeisung wird die Batterie nicht mehr eingefroren. Wenn vorher der SOC bei ~19 % stehengeblieben ist, weil Mode 1 mit `active_power=0` die Batterie komplett stillgelegt hat, entlädt sie jetzt weiter bis zum konfigurierten `selfuse_discharge_min_soc` des Wechselrichters (Default 10 %). Der Original-Wert von `battery_charge_max_current` wird beim ersten Optimizer-Cycle nach dem Update automatisch erkannt und gespeichert.

### Migration

- Config-Schema v17 → v18: Neuer interner Entity-Override-Key `solax_battery_charge_max_current` (Default: `number.solax_inverter_battery_charge_max_current`). Automatisch via `async_migrate_entry` gesetzt — keine User-Aktion nötig.

## [1.2.5] - 2026-05-11

> Release konsolidiert die DEV-Iteration 1.2.5-dev-01 (Slot-B-Vormittags-Fix).

### Behoben

- **Slot B (Morgen-Entladung) konnte fälschlich am späten Vormittag aktivieren.** Bei `now` zwischen heutigem Slot-B-Ende und 12:00 Uhr wurde `b_start` aus `snap.now` abgeleitet und blieb am heutigen Tag, während `b_end` über `snap.sunrise` bereits am morgigen Tag verankert war — das effektive Slot-B-Fenster spannte sich dadurch über ~25 h und Slot B konnte vormittags entladen, sobald der SOC über `min_soc` lag. `b_start` wird nun konsistent am Tag des nächsten Sonnenaufgangs verankert.

## [1.2.5-dev-01] - 2026-05-11

### Behoben

- **Slot B (Morgen-Entladung) konnte fälschlich am späten Vormittag aktivieren.** Bei `now` zwischen heutigem Slot-B-Ende und 12:00 Uhr wurde `b_start` aus `snap.now` abgeleitet und blieb am heutigen Tag, während `b_end` über `snap.sunrise` bereits am morgigen Tag verankert war — das effektive Slot-B-Fenster spannte sich dadurch über ~25 h und Slot B konnte vormittags entladen, sobald der SOC über `min_soc` lag. `b_start` wird nun konsistent am Tag des nächsten Sonnenaufgangs verankert. Regressionstest `test_b_late_morning_after_todays_sunrise_returns_before_slot_b` deckt den Field-Report-Fall (2026-05-11, 11:54 lokal) ab.

## [1.2.4] - 2026-05-08

> Release konsolidiert die DEV-Iteration 1.2.4-dev-01 (Slot-B-Reserve entfernt).

### Entfernt

- **Konfigurationsoption „Reserve für Slot B (%)" (`discharge_a_reserve_pct`) entfernt.** Slot A entlädt jetzt immer bis zum dynamischen `min_soc` ohne zusätzlichen Aufschlag; Slot B nutzt den verbleibenden SOC oberhalb von `min_soc` als verfügbares Energie-Budget für die PeakShare-Sliding-Window-Berechnung. Bestehende Configs werden über die Migration **v17** automatisch um den Key bereinigt; das UI-Feld in Wizard und Settings ist entfallen.

## [1.2.4-dev-01] - 2026-05-08

### Entfernt

- **Konfigurationsoption „Reserve für Slot B (%)" (`discharge_a_reserve_pct`) entfernt.** Slot A entlädt jetzt immer bis zum dynamischen `min_soc` ohne zusätzlichen Aufschlag; Slot B nutzt den verbleibenden SOC oberhalb von `min_soc` als verfügbares Energie-Budget für die PeakShare-Sliding-Window-Berechnung. Bestehende Configs werden über die Migration **v17** automatisch um den Key bereinigt; das UI-Feld in Wizard und Settings ist entfallen.

## [1.2.3] - 2026-05-07

> Release konsolidiert die DEV-Iteration 1.2.3-dev-01 (Optimizer-Hysterese, PeakShare-Window, HA 2026.11).

### Behoben (Optimizer)

- **Mini-Blöcke bei Slot A / Slot B durch dynamischen `min_soc`-Drift behoben.** Über die Nacht schrumpft `consumption_overnight_kwh` (Restzeit bis Sonnenaufgang sinkt), wodurch `_calc_min_soc` ~8 %/h nach unten driftete. Die Schmitt-Trigger-Hysterese (Exit −2 / Default-Eintritt +5) hat innerhalb einer Stunde ihre 7-%-Spanne verloren, sodass der Slot nach einem Self-Stop kurz wieder anlief und sofort wieder stoppte. Reproduktion 06.05.2026: Entladung in 7 Mini-Blöcken zwischen 1 und 20 min, mit Pausen bis 79 min.
  - Neue Felder `_slot_a_latched_min_soc` / `_slot_b_latched_min_soc` frieren `min_soc` beim erstmaligen Slot-Eintritt der Session ein und werden für Schmitt-/Default-/Reaktivierungs-Schwellen genutzt.
  - Reset gemeinsam mit `_slot_a_activated_date` / `_slot_b_activated_date` nach Sonnenaufgang.
- **PeakShare-End-Anchor verhindert 4-Min-Pläne kurz vor Sonnenaufgang.** Bisher wurde `end_time` an `window_end` geclampt, wenn der höchste-Demand-Block + Jitter über das Window hinausragte — Live-Bug 07.05.2026: Plan 05:26–05:30 statt 04:30–05:30. Neue Logik schiebt den Block nach links, wenn `start + required_hours > window_end`, und behält die volle `required_hours`-Dauer bis zum Window-Ende (z.B. Sonnenaufgang).

### Behoben (Telemetrie)

- **`app_version`-Cache wird beim `async_setup_entry` invalidiert.** Bisher behielt der Modul-Cache `_APP_VERSION_CACHE` einen alten Wert, wenn HA nach einem HACS-Update nur die Integration neu lud (statt Core-Restart). Folge: Telemetrie-Backend bekam dauerhaft die alte Version. Reset jetzt am Anfang jedes Setup-Aufrufs, sodass `_load_app_version` frisch von Disk liest.

### Behoben (HA-Kompatibilität)

- **`unit_class="power"` in `async_import_statistics`-Aufrufen ergänzt.** HA 2026.11 macht das Feld zur Pflicht und loggt sonst eine Deprecation-Warnung in `homeassistant.helpers.frame`. Fallback auf älteres HA, das das Feld noch nicht kennt, bleibt erhalten.

## [1.2.3-dev-01] - 2026-05-07

### Behoben (Optimizer)

- **Mini-Blöcke bei Slot A / Slot B durch dynamischen `min_soc`-Drift behoben.** Über die Nacht schrumpft `consumption_overnight_kwh` (Restzeit bis Sonnenaufgang sinkt), wodurch `_calc_min_soc` ~8 %/h nach unten driftete. Die Schmitt-Trigger-Hysterese (Exit −2 / Default-Eintritt +5) hat innerhalb einer Stunde ihre 7-%-Spanne verloren, sodass der Slot nach einem Self-Stop kurz wieder anlief und sofort wieder stoppte. Reproduktion 06.05.2026: Entladung in 7 Mini-Blöcken zwischen 1 und 20 min, mit Pausen bis 79 min.
  - Neue Felder `_slot_a_latched_min_soc` / `_slot_b_latched_min_soc` frieren `min_soc` beim erstmaligen Slot-Eintritt der Session ein und werden für Schmitt-/Default-/Reaktivierungs-Schwellen genutzt.
  - Reset gemeinsam mit `_slot_a_activated_date` / `_slot_b_activated_date` nach Sonnenaufgang.
- **PeakShare-End-Anchor verhindert 4-Min-Pläne kurz vor Sonnenaufgang.** Bisher wurde `end_time` an `window_end` geclampt, wenn der höchste-Demand-Block + Jitter über das Window hinausragte — Live-Bug 07.05.2026: Plan 05:26–05:30 statt 04:30–05:30. Neue Logik schiebt den Block nach links, wenn `start + required_hours > window_end`, und behält die volle `required_hours`-Dauer bis zum Window-Ende (z.B. Sonnenaufgang).

### Behoben (Telemetrie)

- **`app_version`-Cache wird beim `async_setup_entry` invalidiert.** Bisher behielt der Modul-Cache `_APP_VERSION_CACHE` einen alten Wert, wenn HA nach einem HACS-Update nur die Integration neu lud (statt Core-Restart). Folge: Telemetrie-Backend bekam dauerhaft die alte Version. Reset jetzt am Anfang jedes Setup-Aufrufs, sodass `_load_app_version` frisch von Disk liest.

### Behoben (HA-Kompatibilität)

- **`unit_class="power"` in `async_import_statistics`-Aufrufen ergänzt.** HA 2026.11 macht das Feld zur Pflicht und loggt sonst eine Deprecation-Warnung in `homeassistant.helpers.frame`. Fallback auf älteres HA, das das Feld noch nicht kennt, bleibt erhalten.

## [1.2.2] - 2026-05-06

> Release konsolidiert die DEV-Iteration 1.2.1-dev-01 (UI-Umbenennung Abend-Entladung → Nacht-Entladung).

### Geändert (UI)

- **„Abend-Entladung" wurde überall im UI in „Nacht-Entladung" umbenannt.** Mit aktiver PeakShare-Bedarfssteuerung verschiebt sich das Entladefenster regelmäßig in die Nacht hinein (oft bis zum 04:00-Cutoff) — der bisherige Begriff war damit irreführend. Betroffen sind Wizard, Settings-Tab, Status-Karte, Statistik-Karte, Activity-Log-Filter, Bar-Chart-Tooltips/Legende, Konsumprofil-Hinweis sowie das Erklär-SVG.
- **Sensor-`unique_id` und Entity-IDs bleiben unverändert** — die Long-Term-Statistik in HA bricht nicht. Lediglich der angezeigte Sensorname (`Abend-Entladung Energie heute` → `Nacht-Entladung Energie heute`) und der Decision-Sensor-State (`Abend-Entladung` → `Nacht-Entladung`) ändern sich.
- **Telemetrie-`event_type` bleibt stabil bei `abend_entladung`.** Im Backend gespeicherte Auswertungen über die Umbenennung hinweg bleiben konsistent (`_normalize_state`-Override).
- **Activity-Log-Einträge aus früheren Versionen (Zustand `Abend-Entladung`) werden im Frontend weiterhin korrekt gerendert** — Icon, Farbe, Slot-Marker und Filter-Match funktionieren über beide Labels hinweg.

## [1.2.1] - 2026-05-06

### Behoben

- **Dashboard-Statuskarte „Abend-Entladung" zeigt in der A→B-Pause nicht mehr fälschlich Rot.** `_discharge_detail_status` betrachtet jetzt auch die Slot-spezifischen Wartezeit-Reasons (`REASON_BEFORE_SLOT_A`, `REASON_BEFORE_SLOT_B`, `REASON_BETWEEN_SLOTS`, `REASON_SLOT_A_RESERVE_REACHED`) als Time-Reasons. Folge: vor Slot-A-Start, in der Pause zwischen Slot A und Slot B sowie vor Slot-B-Start zeigt die Karte „Geplant" (blau) statt „Nicht geplant" (rot). Bedingungs-bedingte Blocker (z.B. SOC zu niedrig) bleiben weiterhin rot.

### Geändert (Telemetrie)

- **Outcome trägt jetzt `actuals_invalid=true`, wenn ein Power-Sensor mid-block ausfällt.** Pro Block wird getrackt, ob `pv_now_kw` / `consumption_now_kw` / `grid_now_kw` nach mindestens einem nicht-None-Sample wieder None liefern (= Sensor-Ausfall während des laufenden Blocks). In diesem Fall wird `actuals_invalid=true` ins Outcome-Payload geschrieben — das Backend kann jetzt zwischen „Sensor nicht konfiguriert" (Feld fehlt seit jeher) und „Sensor zwischenzeitlich ausgefallen" (Aktuals verfälscht) unterscheiden. Sensoren, die durchgängig None liefern (z.B. nicht konfiguriert), setzen das Flag nicht.
- **Outcomes von Spike-Blöcken (< 5 min) werden nicht mehr ans Backend gesendet.** Schwellen-Toggle-Spikes (Block startet, SOC erreicht sofort die Reserve, Block endet binnen Sekunden) verzerrten bisher die Forecast-MAE-Statistik im Backend. Neuer Cutoff `MIN_BLOCK_OUTCOME_MINUTES = 5`: Blöcke unter 5 Minuten werden geskippt; Block-Predictions / -Samples / -Actuals-State werden trotzdem aufgeräumt, damit der nächste echte Block sauber startet. Lokale Feed-In-Statistik bleibt unberührt — die UI sieht den Spike nach wie vor.
- **`predicted_pv_kwh` / `predicted_consumption_kwh` werden jetzt block-skaliert ausgegeben.** Bisher wurden Tagesforecasts ans Backend gemeldet, die mit den über das Block-Fenster integrierten `actual_*_kwh`-Werten nicht vergleichbar waren (Forecast-MAE für eine 7h-Abend-Entladung wurde mit dem ganzen morgigen 24h-Tagesforecast gegengerechnet). Neuer Decision-Pfad: Optimizer setzt `decision.planned_block_end` bei Block-Start (Morgen-Einspeisung: `morning_end_time`; Slot A: 5min vor Slot-B-Start oder hard_cutoff; Slot B: `compute_b_window_end`; PeakShare: `discharge_window_end`). `_build_block_predictions` skaliert dann linear über 24h: `predicted = day_forecast × min(block_h / 24, 1)`. Backwards-kompatibel: ohne `planned_block_end` (Legacy/Tests) bleibt fraction=1.0.

### Geändert (Optimizer)

- **Schmitt-Trigger-Hysterese auf Reserve-Schwellen + Eintritts-Mindestreserve.** Drei-stufige Schwellen-Logik in Slot A und Slot B (Reaktivierung > Default-Eintritt > Currently-Active-Austritt):
  - **Default-Eintritt** (`RESERVE_ENTRY_BONUS_PCT = 5`): ein Slot startet erst, wenn SOC die Reserve um mindestens 5% übersteigt. Verhindert Mini-Blöcke mit nutzbarem 1%-Spielraum (Live-Bug 06.05.2026: Slot B startete bei SOC=19% mit Ziel-SOC=18% und entlud nur 1%).
  - **Currently-Active-Austritt** (`RESERVE_EXIT_HYSTERESIS_PCT = 2`): solange der Slot bereits aktiv läuft, sinkt die Austrittsschwelle um 2% — der Block bleibt aktiv, bis SOC echte 2% UNTER die Reserve fällt. Anti-Toggle bei SOC-Oszillation.
  - **Reaktivierung** (+5% wie bisher): erschwert Wiedereinstieg in einen Slot, der heute schon einmal aktiv war und verlassen wurde.
  - Schwellen werden bei 0% geclampt; Konstante `RESERVE_HYSTERESIS_PCT` umbenannt in `RESERVE_EXIT_HYSTERESIS_PCT` (interne API).

## [1.2.0] - 2026-05-05

> Release konsolidiert die DEV-Iterationen 31–34 (Phase 11 Dual-Window, Phase 11.1 PeakShare-per-Slot, Phase 12 UI-Vereinfachung).

### UI-Feinschliff (späteste Iterationen)

**UI-Feinschliff:**
- Slot A / Slot B Erklärtexte (Wizard + Settings + SolarEdge-XOR-Radio) ergänzen sich dynamisch um „Genaue Uhrzeit wird auf Basis der PeakShare-Bedarfssteuerung ermittelt." sobald PeakShare aktiv ist; bei deaktiviertem PeakShare bleibt nur der Standard-Hinweis sichtbar.
- Button „Wizard nochmal starten" wird jetzt unter jedem Settings-Tab (Morgen-Einspeisung / Abend-Entladung / EEG-Statistik / Erweitert) angezeigt, nicht mehr nur im Erweitert-Tab.

### Phase 12: Dual-Window-Toggle entfernt — Slot A/B als einziger Discharge-Pfad

**UI-Vereinfachung Abend-Entladung (Wizard + Settings-Panel):**
- Master-Toggle „Dual-Window-Entladung" entfernt. Slot A und Slot B sind jetzt zwei direkte Checkboxen mit kurzem Erklärtext (Slot A — Abend / Slot B — Morgen).
- Default für neue Anlagen: beide Slots aktiv. Per-Slot-Detailfelder (Start-Zeiten, Slot-A-Reserve, Slot-B-Spätestes-Ende) sind nur noch im Expertenmodus sichtbar.
- Eingabefeld „Frühester Entladestart" entfernt — die Slot-Startzeiten ersetzen es.
- PeakShare-Bedarfssteuerung + Energiegemeinschaftsauswahl an oberster Stelle der Abend-Entladung-Sektion.
- Vorlaufzeit vor Sonnenaufgang (Morgen-Einspeisung) in Expertenmodus verschoben.
- SolarEdge: bleibt XOR-Radio (genau ein Slot pro Tag, NVRAM-Schutz), erweiterte Erklärtexte.

**Backend-Refactor (kein User-sichtbares Verhalten geändert für non-SolarEdge):**
- Legacy-Single-Window-Pfad (`_evaluate_legacy_window`) komplett entfernt. `_should_discharge` evaluiert direkt Slot A + Slot B.
- `discharge_start_time` aus Schema entfernt (`CONF_DISCHARGE_START_TIME`/`DEFAULT_DISCHARGE_START_TIME` in `const.py` gelöscht).
- `enable_dual_discharge` aus Optimizer-Logik entfernt (war `True`-Default für non-SolarEdge ohnehin).
- SolarEdge-Defense-in-depth: Force schaltet jetzt Slot-XOR statt `enable_dual_discharge=False`.

**Migration v15 → v16:**
- Entries werden auf Schema-Version 16 gehoben.
- `discharge_start_time` und `enable_dual_discharge` werden aus der Config entfernt (Optimizer liest sie nicht mehr).
- SolarEdge-Sonderfall: bisheriger `discharge_start_time` wird auf den passenden Slot übertragen — Start < 12:00 → Slot B (Morgen), sonst Slot A. Damit bleibt das gewohnte Zeitfenster für SolarEdge-Bestände erhalten.
- non-SolarEdge: `discharge_start_time` war im Dual-Modus seit v15 dead config — wird einfach entsorgt.

**Tests:** 414 passed, 25 als skipped markiert (Legacy-Pfad-Tests, dokumentieren das alte Single-Window-Verhalten und sind durch Slot-A/B-Tests in `test_dual_window.py` abgedeckt).

### Phase 11.1: PeakShare-Steuerung der Slot-A/B-Fenster

**Neu:**
- PeakShare optimiert jetzt auch im Dual-Window-Modus (Slot A + Slot B) das Entlade-Sub-Fenster INNERHALB der konfigurierten Slot-Zeiten. Beispiel: Slot A 20:00–03:00 → PeakShare findet automatisch das beste Sub-Fenster (z.B. 22:00–00:00), wenn der EEG-Bedarf dort am höchsten ist.
- Slot A wird immer bevorzugt; Slot B nutzt die Reserve-Energie (siehe Default-Wechsel unten).
- Pro Slot getrennt entscheidbar: Wenn PeakShare-Daten den Slot-Zeitraum nicht abdecken, fällt der betroffene Slot auf das Fixzeit-Verhalten zurück. Der andere Slot kann separat PeakShare-gesteuert laufen.

**Verhaltensänderung beim Update:**
- **Default für `discharge_a_reserve_pct` (Slot-A-Reserve für Slot B) wurde von 15 % auf 5 % gesenkt.** Bei aktiver PeakShare-Steuerung pro Slot bekommt Slot A das Hauptenergie-Budget; Slot B wird nur als kleine Morgen-Spitze bedient.
- **Bestands-Setups behalten ihren bisher konfigurierten Wert** (kein Auto-Override; setdefault-Migration ändert nur Setups, die den Wert noch nicht explizit gesetzt haben).
- User, die bewusst eine größere Slot-B-Energiereserve wollen, können `discharge_a_reserve_pct` weiterhin im Panel auf bis zu 50 % setzen (Voluptuous-Range unverändert).

**Bug-Fix:**
- PeakShare-Cache-Tageslock blockierte zuvor den zweiten Slot-Plan-Compute am selben Tag. Slot A und Slot B können jetzt unabhängig PeakShare-Pläne berechnen (Per-Slot-Compute-Tracking via `_discharge_plan_computed_dates`).

**Schließt Spec-Lücke aus Phase 11:**
- Phase 11 SPEC §"In scope" Z. 75 hatte "PeakShare-Integration für Dual-Mode (zwei separate Sliding-Window-Suchen, eine pro Slot, mit slot-spezifischem `available_kwh`)" zugesagt. Plan 11-02 hatte das Cache-Schema (dict[a/b]) vorbereitet, aber den eigentlichen PeakShare-Aufruf nie nachgereicht. Phase 11.1 schließt diese Lücke.

**UI-Anzeige:**
- Decision-Markdown zeigt im aktiven Slot den PeakShare-Window-Marker (z.B. „- PeakShare-Fenster: 22:00-00:00").
- „Nächste Aktion"-Text zeigt slot-spezifische PeakShare-Window-Times (Slot A: „Abend-Entladung HH:MM-HH:MM (PeakShare)", Slot B: „Morgen-Entladung HH:MM-HH:MM (PeakShare)").
- Status-Card-Startzeit ist slot-aware (Slot-A-Plan vs Slot-B-Plan abhängig vom aktiven Slot); Fixzeit-Fallback nutzt die Slot-spezifische Startzeit statt Legacy `discharge_start_time` im Dual-Mode.

### Verhaltensänderung beim Update

Mit Phase 11 wird die **Dual-Window-Entladung** zum Standard für alle Wechselrichter außer SolarEdge. Bestands-Anlagen werden beim Update automatisch auf das neue Modell migriert (Config-Entry-Version-Bump v14 → v15).

**Was sich ändert:**
- Die Abend-Entladung läuft nun in **zwei unabhängigen Slots** statt einem einzigen Fenster:
  - **Slot A — Abend** (Default 20:00 bis 5min vor Slot-B-Start): Adressiert den EEG-Abendpeak (18:00–23:00).
  - **Slot B — Morgen** (Default 03:00 bis spätestens 07:00 oder Sonnenaufgang−5min): Adressiert den EEG-Morgenpeak und die Wintermorgen, wenn der Bedarf der Energiegemeinschaft hoch ist und PV noch nicht trägt.
- **Pro-Slot-Hysterese:** Slot A und Slot B haben jeweils unabhängige Reaktivierungs-Schwellen (+5% SOC bei Reaktivierung), damit oszillierendes Ein/Aus vermieden wird.
- **Energie-Reserve:** Slot A endet bei `min_soc + 15%` (Default), damit Slot B genug Energie übrig hat. Bei Slot-A-only oder Slot-B-only entfällt der Aufschlag, das jeweilige Fenster nutzt die volle Restkapazität.

**Mitigation gegen unerwünschtes Entladen:**
- Pro-Slot-Hysterese verhindert oszillierende Aktivierung.
- PV-Tomorrow-Garantie: Beide Slots prüfen weiterhin, dass die PV-Prognose für morgen den Bedarf inklusive Sicherheitspuffer deckt; sonst wird nicht entladen.
- Konfiguration jederzeit umstellbar: Im Onboarding-Panel → Einstellungen → Abend-Entladung kann jeder User die `Dual-Window-Entladung` deaktivieren und auf das alte Single-Window-Verhalten zurückkehren — der Legacy-Code-Pfad bleibt 1:1 erhalten und ist durch eigene Tests abgedeckt.

**SolarEdge-Sonderfall:**
SolarEdge-Wechselrichter schreiben Entlade-Kommandos in NVRAM-Speicher mit begrenzten Schreibzyklen. Daher ist Dual-Window auf SolarEdge **nicht verfügbar**. Stattdessen gibt es ein Radio-Auswahl-Feld "Slot A — Abend (Default) | Slot B — Morgen" im Panel; pro Tag läuft genau einer der beiden Slots. Dies ist dreifach abgesichert (Defense-in-depth): Migration setzt den Default, der Save-Path normalisiert die Konfiguration, und der Optimizer erzwingt das Verhalten zur Laufzeit.

### Added
- **Dual-Window-Entladung** mit Slot A (Abend) und Slot B (Morgen) — neue Konfigurationskeys `enable_dual_discharge`, `enable_slot_a`, `enable_slot_b`, `discharge_a_start_time`, `discharge_b_start_time`, `discharge_b_end_cap`, `discharge_a_reserve_pct`.
- Funktion `compute_b_window_end()` für adaptives Slot-B-Ende vor Sonnenaufgang. Schneidet automatisch auf `min(b_end_cap, sunrise − 5min)`, sodass Slot B niemals in die Morgen-Einspeisungs-Phase überlappt.
- Acht neue Telemetrie-Reasons für Slot-Phasen: `before_slot_a`, `slot_a_active`, `slot_a_reserve_reached`, `between_slots`, `before_slot_b`, `slot_b_active`, `slot_b_window_expired`, `slot_b_pre_sunrise_cutoff`. Additiv zur Phase-8-Reasons-Liste, kein Schemabruch.
- `Decision.discharge_active_slot`-Feld (Werte "A", "B" oder None) für slotunabhängige Statusanzeige.
- Activity-Log-Feld `discharge_active_slot` für Slot-Kontext im Aktivitätsverlauf (D-09). Sichtbar im HA-Dashboard und im `eeg_optimizer_activity`-Bus-Event.
- SolarEdge-XOR-Radio im Onboarding-Panel mit Tooltip-Erklärung "NVRAM-Verschleiß: nur ein Slot pro Tag möglich".
- Markdown-Sektion "Slot-Konfiguration" im Decision-Sensor zeigt aktuelle Slot-A/Slot-B-Werte.
- Frontend-Aktivitäts-Timeline zeigt Slot-Suffix "(Slot A)" / "(Slot B)" bei Abend-Entladung-Einträgen.

### Changed
- **Default-Verhalten:** Bestands-Anlagen erhalten beim Update Dual-Window automatisch (Config v14 → v15). SolarEdge-Bestände bekommen Slot-A-only (XOR-Konfiguration). Siehe "Verhaltensänderung beim Update" oben.
- `_should_discharge` ist nun ein Dispatcher mit drei Pfaden (`_evaluate_legacy_window` / `_evaluate_slot_a` / `_evaluate_slot_b`); gemeinsame Guards in `_check_common_guards`. Legacy-Pfad bleibt byte-identisch erhalten für Setups mit `enable_dual_discharge=False`.
- PeakShare-Cache `_discharge_plan` ist nun ein slot-indiziertes Dict (`{"a": ..., "b": ...}`) statt single tuple. Alte Cache-Form wird beim Update verworfen und neu berechnet — keine Migration nötig, da Cache-Inhalte ohnehin täglich neu berechnet werden.
- WebSocket-Save-Path validiert SolarEdge-XOR und Inverter-Race (`b_start ≥ a_start + 30min + 5min`) mit Auto-Korrektur statt Hard-Reject. Konsistent mit dem bestehenden SolarEdge-5kW-Clamp-Pattern.
- Onboarding-Panel: Discharge-Sektion (Wizard Schritt 4 + Settings-Tab "Abend-Entladung") um Master-Toggle und Slot-A/Slot-B-Sub-Karten erweitert.

### Migration
- Config-Entry-Version: 14 → 15.
- Migration ist additiv: bestehende User-Werte bleiben erhalten (`setdefault`).
- Nicht-SolarEdge-Bestände: `enable_dual_discharge=True`, `enable_slot_a=True`, `enable_slot_b=True`, Defaults für die neuen Zeit-/Reserve-Keys.
- SolarEdge-Bestände: `enable_dual_discharge=False`, `enable_slot_a=True`, `enable_slot_b=False` (XOR-Default Slot A).

### Tests
- Neue Test-Datei `tests/test_dual_window.py` (Plan 11-01 + 11-02 + 11-03) mit ~50 Tests in 12 Klassen, deckt `compute_b_window_end`, Reasons-Catalog, Migration v14→v15, Slot-A/B-Logik, Pro-Slot-Hysterese, Mutual Exclusion, SolarEdge-Runtime-Force, PeakShare-Cache-Schema, 24h-Simulation, SolarEdge-XOR-Save-Path und Inverter-Race-Validation ab.
- Neue Test-Datei `tests/test_dual_window_integration.py` (Plan 11-04) mit 10 Tests in 3 Klassen für Markdown-Rendering, _evaluate-Slot-Marker-Persistenz und Activity-Log-Slot-Kontext.

### Manual UAT
Final-UAT ist eine 7-Tage-Beobachtung an mindestens einer Test-HA-Instanz (Huawei und/oder Fronius). User entscheidet "gute Idee oder nicht" auf Basis realer EEG-Bedarfsdaten und Inverter-Reaktion. Siehe `.planning/milestones/v1.2-phases/11-dual-window-discharge/11-VALIDATION.md`.

## [1.1.3] - 2026-04-16

Vorletzter Release vor Phase-11. Details siehe Git-Tag `v1.1.3` und Quick-Tasks im DEV-Repo.

## [1.1.2] - 2026-04-15

Details siehe Git-Tag `v1.1.2`.
