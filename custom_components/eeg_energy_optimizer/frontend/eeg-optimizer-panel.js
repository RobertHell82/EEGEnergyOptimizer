/**
 * EEG Energy Optimizer Panel - Custom element for HA sidebar panel.
 *
 * Provides dashboard/wizard view toggle and loads config via WebSocket.
 * Wizard: 8-step setup for inverter, prerequisites, sensors, forecasts,
 * consumption, optimizer params, and summary with config save.
 */

// Guard against duplicate script loading (HA may reload after reconnect)
if (customElements.get("eeg-optimizer-panel")) {
  // Already registered — skip entire script to avoid const redeclaration errors
} else {

// Sensor suffixes matching sensor.py unique_id pattern
const SENSOR_SUFFIXES = {
  entscheidung: "entscheidung",
  pv_heute: "pv_prognose_heute",
  pv_morgen: "pv_prognose_morgen",
  verbrauchsprofil: "verbrauchsprofil",
  prognose_heute: "tagesverbrauchsprognose_heute",
  prognose_morgen: "tagesverbrauchsprognose_morgen",
  prognose_tag2: "tagesverbrauchsprognose_tag_2",
  prognose_tag3: "tagesverbrauchsprognose_tag_3",
  prognose_tag4: "tagesverbrauchsprognose_tag_4",
  prognose_tag5: "tagesverbrauchsprognose_tag_5",
  prognose_tag6: "tagesverbrauchsprognose_tag_6",
};
const SELECT_SUFFIX = "optimizer";

const DEFAULT_WATCHED = [
  "select.eeg_energy_optimizer_optimizer",
  "sensor.eeg_energy_optimizer_entscheidung",
  "sensor.eeg_energy_optimizer_pv_prognose_heute",
  "sensor.eeg_energy_optimizer_pv_prognose_morgen",
  "sensor.eeg_energy_optimizer_verbrauchsprofil",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_heute",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_morgen",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_2",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_3",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_4",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_5",
  "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_6",
];

const WIZARD_KEY = "eeg_optimizer_wizard_state";

const WIZARD_STEPS = [
  "Willkommen",
  "Wechselrichter",
  "Prognose",
  "Batterie",
  "Ladung & Einspeisung",
  "Erweiterte Einstellungen",
  "Zusammenfassung",
];


const WIZARD_DEFAULTS = {
  inverter_type: "huawei_sun2000",
  battery_soc_sensor: "",
  battery_capacity_sensor: "",
  battery_capacity_kwh: 10,
  pv_power_sensor: "",
  battery_power_sensor: "",
  grid_power_sensor: "",
  // Fronius / SolarNet split-sensor pairs. When both pair fields are filled
  // the backend redirects battery_power_sensor / grid_power_sensor at the
  // synthetic combined sensor on save.
  battery_power_charge_sensor: "",
  battery_power_discharge_sensor: "",
  grid_power_export_sensor: "",
  grid_power_import_sensor: "",
  huawei_device_id: "",
  pv_power_sensor_2: "",
  solax_remotecontrol_power_control: "",
  solax_remotecontrol_active_power: "",
  solax_remotecontrol_autorepeat_duration: "",
  solax_remotecontrol_trigger: "",
  solax_selfuse_discharge_min_soc: "",
  solaredge_storage_control_mode: "",
  solaredge_storage_command_mode: "",
  solaredge_storage_charge_limit: "",
  solaredge_storage_discharge_limit: "",
  solaredge_storage_backup_reserve: "",
  fronius_modbus_host: "",
  fronius_modbus_port: 502,
  forecast_source: "solcast_solar",
  forecast_remaining_entity: "",
  forecast_tomorrow_entity: "",
  forecast_today_entity: "",
  forecast_day3_entity: "",
  forecast_day4_entity: "",
  forecast_day5_entity: "",
  forecast_day6_entity: "",
  forecast_day7_entity: "",
  lookback_weeks: 2,
  update_interval_fast_min: 1,
  update_interval_slow_min: 15,
  enable_morning_delay: true,
  morning_start_offset: 0,
  morning_end_time: "11:00",
  enable_night_discharge: true,
  enable_peakshare: true,
  peakshare_community: "BEG",
  discharge_start_time: "01:00",
  discharge_power_kw: 5.0,
  min_soc: 10,
  safety_buffer_pct: 25,
  expert_mode: false,
  enable_simulation: false,
  enable_manual_control: false,
};

// Solcast sensor names changed across versions — support both conventions
const SOLCAST_DEFAULTS_CANDIDATES = {
  forecast_remaining_entity: [
    "sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute",
    "sensor.solcast_pv_forecast_prognose_fuer_heute",
  ],
  forecast_tomorrow_entity: [
    "sensor.solcast_pv_forecast_prognose_morgen",
    "sensor.solcast_pv_forecast_prognose_fuer_morgen",
  ],
};

const FORECAST_SOLAR_DEFAULTS = {
  forecast_remaining_entity: "sensor.energy_production_today_remaining",
  forecast_tomorrow_entity: "sensor.energy_production_tomorrow",
};

const DIALOG_CONTENT = {
  huawei: {
    title: "Huawei Solar Integration einrichten",
    content: `
      <h3 style="margin:16px 0 8px">1. Wechselrichter vorbereiten</h3>
      <p style="margin-bottom:8px">Modbus TCP muss am Wechselrichter aktiviert sein, damit Home Assistant zugreifen kann:</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Handy-WLAN mit dem Wechselrichter-Hotspot verbinden (<code>SUN2000-&lt;Seriennummer&gt;</code>)
          <br><span style="color:var(--secondary-text-color)">Passwort steht auf dem Dongle-Aufkleber. Mobile Daten am Handy deaktivieren!</span>
        </li>
        <li><strong>FusionSolar App</strong> oder <strong>SUN2000 App</strong> &ouml;ffnen &rarr; <strong>Ger&auml;te-Inbetriebnahme</strong></li>
        <li>Login als <strong>Installer</strong> mit Passwort <code>00000a</code>
          <br><span style="color:var(--secondary-text-color)">Standard-Passwort (6 Zeichen). Falls ge&auml;ndert: aktuelles Installer-Passwort verwenden.</span>
        </li>
        <li><strong>Einstellungen &rarr; Kommunikationskonfiguration &rarr; Dongle-Parameter</strong></li>
        <li>Modbus-TCP auf <strong>&ldquo;Aktivieren (uneingeschr&auml;nkt)&rdquo;</strong> setzen</li>
      </ol>
      <div style="background:var(--warning-color,#ff9800);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9888; Wichtig:</strong> Nur EINE Modbus-Verbindung gleichzeitig m&ouml;glich! FusionSolar App komplett schlie&szlig;en (nicht nur minimieren) bevor die HA-Integration gestartet wird.
      </div>
      <h3 style="margin:16px 0 8px">2. HACS Integration installieren</h3>
      <p style="margin-bottom:8px;color:var(--secondary-text-color)"><strong>Voraussetzung:</strong> <a href="https://hacs.xyz/" target="_blank">HACS</a> muss installiert sein.</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>HACS &rarr; Integrationen &rarr; Suche &ldquo;Huawei Solar&rdquo;</strong>
          <br><span style="color:var(--secondary-text-color)">Repository: wlcrs/huawei_solar</span>
        </li>
        <li>Installiere die Integration und <strong>starte Home Assistant neu</strong></li>
      </ol>
      <h3 style="margin:16px 0 8px">3. Integration konfigurieren</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&ldquo;Huawei Solar&rdquo;</strong></li>
        <li>W&auml;hle <strong>Netzwerk</strong> als Verbindungstyp</li>
        <li>Gib die <strong>IP-Adresse</strong> des Wechselrichters/Dongles ein</li>
        <li>Port: <strong>6607</strong> (neuere Firmware) oder <strong>502</strong> (EMMA / &auml;ltere Firmware)</li>
        <li>Slave ID: <strong>1</strong> (Standard, bei Problemen 0 versuchen)</li>
        <li><strong>Elevated Permissions: MUSS aktiviert werden!</strong>
          <br><span style="color:var(--secondary-text-color)">Ohne Elevated Permissions keine Batteriesteuerung &mdash; der EEG Energy Optimizer kann dann nicht steuern.</span>
        </li>
        <li>Installer-Passwort: <code>00000a</code> eingeben</li>
      </ol>
      <p style="margin:8px 0;color:var(--secondary-text-color);font-size:13px"><strong>Elevated Permissions vergessen?</strong> Unter Einstellungen &rarr; Integrationen &rarr; Huawei Solar &rarr; Drei-Punkte-Men&uuml; &rarr; &ldquo;Neu konfigurieren&rdquo; nachtr&auml;glich aktivieren.</p>
      <h3 style="margin:16px 0 8px">4. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Unter <strong>Einstellungen &rarr; Integrationen</strong>: Huawei Solar zeigt <strong>&ldquo;geladen&rdquo;</strong></li>
        <li><strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: <code>sensor.battery_state_of_capacity</code> zeigt SOC (0&ndash;100%)</li>
        <li><code>number.batteries_maximale_ladeleistung</code> existiert (= Elevated Permissions aktiv)</li>
        <li>Kehre hierher zur&uuml;ck &mdash; der Wechselrichter wird automatisch erkannt</li>
      </ol>
      <h3 style="margin:16px 0 8px">H&auml;ufige Probleme</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Connection refused</strong></td>
          <td style="padding:4px 8px">Modbus TCP nicht aktiviert &rarr; Schritt 1 wiederholen</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Connection timeout</strong></td>
          <td style="padding:4px 8px">Port 6607 statt 502 versuchen (oder umgekehrt)</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Keine Batterie-Entities</strong></td>
          <td style="padding:4px 8px">Elevated Permissions fehlen &rarr; neu konfigurieren</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Permission denied</strong></td>
          <td style="padding:4px 8px">Passwort <code>00000a</code> oder <code>0000000a</code> (8 Zeichen) versuchen</td>
        </tr>
        <tr>
          <td style="padding:4px 8px"><strong>Verbindung bricht ab</strong></td>
          <td style="padding:4px 8px">FusionSolar App komplett schlie&szlig;en, nicht nur minimieren</td>
        </tr>
      </table>`,
  },
  solcast: {
    title: "Solcast Solar einrichten",
    content: `
      <style>.guide-img { max-width:100%; border-radius:8px; margin:8px 0 12px; border:1px solid var(--divider-color); cursor:pointer; } .guide-img:hover { opacity:0.9; }</style>
      <h3 style="margin:16px 0 8px">1. Registrierung bei Solcast</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe auf <a href="https://toolkit.solcast.com.au/" target="_blank">toolkit.solcast.com.au</a> um Dich zu registrieren.</li>
        <li>W&auml;hle dort den Accounttyp <strong>Home User</strong>.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/01_Home_User.png" alt="Home User w&auml;hlen">
        </li>
        <li>W&auml;hle <strong>Hobbyist</strong>, gib Deine Daten ein und klicke auf <strong>Submit</strong>.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/02_Registration.png" alt="Registrierung">
        </li>
        <li>W&auml;hle ein Passwort und klicke auf <strong>Submit</strong>.</li>
        <li>Du erh&auml;ltst eine E-Mail zur Best&auml;tigung &mdash; &ouml;ffne den Link darin.</li>
        <li>Melde Dich mit dem neuen Benutzer an.</li>
        <li>Klicke auf <strong>&ldquo;Add your first Home PV System to get started&rdquo;</strong>.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/03_Add_PV_System.png" alt="PV System hinzuf&uuml;gen">
        </li>
        <li>Daten der PV-Anlage erfassen:
          <ul style="margin:4px 0;padding-left:16px">
            <li><strong>Capacity (kW)</strong> &mdash; Anlagenleistung in kWp (z.B. 10)</li>
            <li><strong>Tilt</strong> &mdash; Dachneigung in Grad (typisch 30&ndash;35&deg;)</li>
            <li><strong>Azimuth</strong> &mdash; Ausrichtung: 0&deg;=Nord, -90&deg;=Ost, &plusmn;180&deg;=S&uuml;d, 90&deg;=West</li>
          </ul>
          Auf <strong>Submit</strong> klicken.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/04_Save_PV_System.png" alt="PV System speichern">
        </li>
        <li><strong>Mehrere Ausrichtungen (Ost/West)?</strong> Klicke auf <strong>&ldquo;Add another PV System&rdquo;</strong> und erfasse die zweite Dachfl&auml;che separat. Beide nutzen denselben API-Key.</li>
        <li>&Ouml;ffne oben rechts das Men&uuml; neben dem Benutzernamen und klicke auf <strong>Your API Key</strong>.</li>
        <li>Kopiere den angezeigten Key f&uuml;r sp&auml;ter.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/05_API_Key.png" alt="API Key kopieren">
        </li>
      </ol>
      <h3 style="margin:16px 0 8px">2. Installation der Integration</h3>
      <p style="margin-bottom:8px;color:var(--secondary-text-color)"><strong>Voraussetzung:</strong> <a href="https://hacs.xyz/" target="_blank">HACS</a> muss installiert sein (Solcast ist eine Custom Integration, kein HA-Standard).</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>HACS &rarr; Integrationen &rarr; Suche &ldquo;Solcast PV Forecast&rdquo;</strong></li>
        <li>Installiere die Integration und starte Home Assistant neu.</li>
        <li>Unter <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Solcast Solar</strong> hinzuf&uuml;gen.</li>
        <li>Gib den zuvor kopierten API-Key ein, lasse die restlichen Einstellungen wie vorausgew&auml;hlt und klicke auf <strong>OK</strong>.</li>
        <li>Aktiviere die deaktivierten Prognose-Sensoren f&uuml;r die Tage 3 bis 7: Klicke den Sensor an, dann auf das Zahnrad und stelle ihn auf <strong>Aktiviert</strong>.
          <br><img class="guide-img" src="/eeg_optimizer_panel/guide/solcast/06_Prognosesensoren.png" alt="Sensoren aktivieren">
        </li>
      </ol>
      <h3 style="margin:16px 0 8px">3. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Warte 1&ndash;2 Minuten nach der Einrichtung</li>
        <li>Pr&uuml;fe unter <strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: Suche nach <code>solcast</code></li>
        <li>Die Sensoren <code>sensor.solcast_pv_forecast_prognose_fuer_heute</code> und <code>sensor.solcast_pv_forecast_prognose_fuer_morgen</code> sollten kWh-Werte zeigen</li>
        <li>Kehre hierher zur&uuml;ck &mdash; die Sensoren werden automatisch zugeordnet</li>
      </ol>`,
  },
  forecast_solar: {
    title: "Forecast.Solar einrichten",
    content: `
      <h3 style="margin:16px 0 8px">1. Integration hinzuf&uuml;gen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&ldquo;Forecast.Solar&rdquo;</strong></li>
        <li>Klicke auf <strong>Forecast.Solar</strong></li>
      </ol>
      <h3 style="margin:16px 0 8px">2. Anlagendaten eingeben</h3>
      <p style="margin-bottom:8px">Forecast.Solar berechnet die Prognose anhand deiner PV-Anlage:</p>
      <table style="width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:14px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Name</strong></td>
          <td style="padding:6px 8px">Frei w&auml;hlbar, z.B. &ldquo;PV S&uuml;d&rdquo;</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>API Key</strong></td>
          <td style="padding:6px 8px">Leer lassen (kostenlos) oder dein Forecast.Solar API-Key</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Latitude / Longitude</strong></td>
          <td style="padding:6px 8px">Automatisch aus HA-Konfiguration &mdash; pr&uuml;fen, nicht &auml;ndern</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Dachneigung (Declination)</strong></td>
          <td style="padding:6px 8px">Neigung in Grad. Typisch DACH-Region: <strong>30&ndash;35&deg;</strong>, Flachdach: 0&ndash;10&deg;</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Azimuth</strong></td>
          <td style="padding:6px 8px">
            Himmelsrichtung der Module:<br>
            <strong>0&deg; = Nord</strong>, 90&deg; = Ost, <strong>180&deg; = S&uuml;d</strong>, 270&deg; = West<br>
            <span style="color:var(--secondary-text-color)">Achtung: HA nutzt Kompass-Konvention (0=Nord), nicht die Forecast.Solar-Website (0=S&uuml;d)!</span>
          </td>
        </tr>
        <tr>
          <td style="padding:6px 8px"><strong>Leistung (kWp)</strong></td>
          <td style="padding:6px 8px">
            Anlagenleistung <strong>in Watt</strong>, nicht kWp!<br>
            Beispiel: 10 kWp &rarr; <strong>10000</strong> eingeben
          </td>
        </tr>
      </table>
      <p style="margin:4px 0 0;color:var(--secondary-text-color);font-size:13px"><strong>Tipp:</strong> Die h&auml;ufigsten Fehler sind falscher Azimuth (S&uuml;d = 180&deg;, nicht 0&deg;) und kWp statt Watt.</p>
      <h3 style="margin:16px 0 8px">3. Mehrere Ausrichtungen (Ost/West)</h3>
      <p style="margin-bottom:8px">Bei Modulen in verschiedene Richtungen die Integration <strong>mehrmals hinzuf&uuml;gen</strong> &mdash; einmal pro Ausrichtung (z.B. &ldquo;PV Ost&rdquo; mit Azimuth 90&deg; und &ldquo;PV West&rdquo; mit 270&deg;).</p>
      <p style="color:var(--secondary-text-color);font-size:13px">Die zweite Instanz erstellt Sensoren mit <code>_2</code> Suffix (z.B. <code>sensor.energy_production_tomorrow_2</code>).</p>
      <h3 style="margin:16px 0 8px">4. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Warte 1&ndash;2 Minuten nach der Einrichtung</li>
        <li>Pr&uuml;fe unter <strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: Suche nach <code>energy_production</code></li>
        <li>Die Sensoren <code>sensor.energy_production_today_remaining</code> und <code>sensor.energy_production_tomorrow</code> sollten kWh-Werte zeigen</li>
        <li>Kehre hierher zur&uuml;ck &mdash; die Sensoren werden automatisch zugeordnet</li>
      </ol>
      <p style="margin:12px 0 4px;color:var(--secondary-text-color);font-size:13px"><strong>Kostenlose Version:</strong> 12 Abrufe/Stunde, Prognose f&uuml;r heute + morgen, 1h-Aufl&ouml;sung &mdash; vollkommen ausreichend f&uuml;r den EEG Energy Optimizer.</p>`,
  },
  capacity_sensor: {
    title: "Huawei Akkukapazität-Sensor aktivieren",
    content: `
      <p style="margin-bottom:12px">Der Sensor für die Akkukapazität ist bei Huawei Solar standardmäßig deaktiviert (Diagnostic-Sensor). So aktivierst du ihn:</p>
      <ol style="padding-left:20px;line-height:2">
        <li>Gehe zu <strong>Einstellungen → Geräte &amp; Dienste</strong></li>
        <li>Klicke auf <strong>Huawei Solar</strong></li>
        <li>Klicke auf dein <strong>Batterie-Gerät</strong> (z.B. "LUNA2000")</li>
        <li>Scrolle nach unten zur Entitäten-Liste</li>
        <li>Klicke oben rechts auf <strong>"Entitäten die nicht auf dem Dashboard angezeigt werden"</strong> (oder den Filter für deaktivierte Entitäten)</li>
        <li>Suche nach <strong>"Akkukapazität"</strong> oder <strong>"Storage Rated Capacity"</strong></li>
        <li>Klicke auf die Entität und dann auf <strong>"Aktivieren"</strong></li>
        <li>Warte ca. 30 Sekunden bis der Sensor Daten liefert</li>
      </ol>
      <p style="margin-top:12px;color:var(--secondary-text-color)">Der Sensor heißt typischerweise <code>sensor.batterien_akkukapazitat</code> und zeigt die Kapazität in Wh an (z.B. 15000 für 15 kWh).</p>
      <p style="margin-top:8px;color:var(--secondary-text-color)"><strong>Tipp:</strong> Wenn du den Sensor nicht findest, kannst du die Kapazität auch manuell eingeben.</p>`,
  },
  solax: {
    title: "SolaX Modbus einrichten",
    content: `
      <h3 style="margin:16px 0 8px">1. Unterst&uuml;tzte Wechselrichter</h3>
      <p style="margin-bottom:8px">Nur <strong>Gen4, Gen5 und Gen6</strong> Wechselrichter werden unterst&uuml;tzt. &Auml;ltere Generationen (Gen2/Gen3) haben keine Remote Control Funktion.</p>
      <h3 style="margin:16px 0 8px">2. Wechselrichter-Einstellungen</h3>
      <p style="margin-bottom:8px">Diese Einstellungen m&uuml;ssen am Wechselrichter oder in der SolaX-App korrekt gesetzt sein:</p>
      <table style="width:100%;border-collapse:collapse;margin:8px 0 16px;font-size:14px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Work Mode</strong></td>
          <td style="padding:6px 8px"><strong>Self Use</strong> (charger_use_mode = 0)</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:6px 8px"><strong>Night Charge</strong></td>
          <td style="padding:6px 8px"><strong>Aus</strong> &mdash; sonst l&auml;dt die Batterie nachts aus dem Netz</td>
        </tr>
        <tr>
          <td style="padding:6px 8px"><strong>Smart Schedule / Zeitplan</strong></td>
          <td style="padding:6px 8px"><strong>Aus</strong> &mdash; kollidiert mit der Optimizer-Steuerung</td>
        </tr>
      </table>
      <div style="background:var(--warning-color,#ff9800);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9888; Wichtig:</strong> Der Work Mode darf <strong>NICHT</strong> auf &ldquo;Feedin Priority&rdquo; oder &ldquo;Force Time Use&rdquo; stehen! Der EEG Energy Optimizer steuert die Batterie &uuml;ber Remote Control (Mode 1) und setzt voraus, dass der Wechselrichter im Self Use Modus l&auml;uft.
      </div>
      <h3 style="margin:16px 0 8px">3. HACS Integration installieren</h3>
      <p style="margin-bottom:8px;color:var(--secondary-text-color)"><strong>Voraussetzung:</strong> <a href="https://hacs.xyz/" target="_blank">HACS</a> muss installiert sein.</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>HACS &rarr; Integrationen &rarr; Suche &ldquo;SolaX Inverter Modbus&rdquo;</strong>
          <br><span style="color:var(--secondary-text-color)">Repository: wills106/homeassistant-solax-modbus</span>
        </li>
        <li>Installiere die Integration und <strong>starte Home Assistant neu</strong></li>
      </ol>
      <h3 style="margin:16px 0 8px">4. Integration konfigurieren</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&ldquo;SolaX Inverter Modbus&rdquo;</strong></li>
        <li>Gib die <strong>IP-Adresse</strong> des Wechselrichters / WiFi-Dongles ein</li>
        <li>Port: <strong>502</strong> (Standard f&uuml;r Modbus TCP)</li>
        <li>Pr&uuml;fe, dass <strong>&ldquo;Gen4+ Inverter&rdquo;</strong> als Typ ausgew&auml;hlt ist</li>
      </ol>
      <h3 style="margin:16px 0 8px">5. Batterie-Kapazit&auml;t</h3>
      <p style="margin-bottom:8px">SolaX stellt <strong>keinen Sensor f&uuml;r die Batteriekapazit&auml;t</strong> bereit. Du gibst die Kapazit&auml;t sp&auml;ter im Wizard manuell ein (z.B. 5.8 kWh f&uuml;r eine T-BAT 5.8).</p>
      <h3 style="margin:16px 0 8px">6. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Unter <strong>Einstellungen &rarr; Integrationen</strong>: SolaX Inverter Modbus zeigt <strong>&ldquo;geladen&rdquo;</strong></li>
        <li><strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: <code>sensor.solax_*battery_capacity</code> zeigt SOC (0&ndash;100%)</li>
        <li><code>button.solax_*remotecontrol_trigger</code> existiert (= Remote Control verf&uuml;gbar)</li>
        <li>Kehre hierher zur&uuml;ck &mdash; der Wechselrichter wird automatisch erkannt</li>
      </ol>
      <p style="margin:4px 0;color:var(--secondary-text-color);font-size:13px"><strong>Hinweis:</strong> Der Entity-Prefix variiert je Installation (z.B. <code>solax_inverter_</code> statt <code>solax_</code>). Der EEG Energy Optimizer erkennt den Prefix automatisch.</p>
      <h3 style="margin:16px 0 8px">H&auml;ufige Probleme</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Connection refused</strong></td>
          <td style="padding:4px 8px">WiFi-Dongle nicht erreichbar &rarr; IP und Netzwerk pr&uuml;fen</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Kein remotecontrol_trigger</strong></td>
          <td style="padding:4px 8px">Gen2/Gen3 oder X1 Fit (AC-coupled) &rarr; nicht unterst&uuml;tzt</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Kommandos ohne Wirkung</strong></td>
          <td style="padding:4px 8px">Work Mode auf &ldquo;Self Use&rdquo; pr&uuml;fen, Night Charge und Smart Schedule aus</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Batterie l&auml;dt trotz Blockierung</strong></td>
          <td style="padding:4px 8px">Lock State pr&uuml;fen &mdash; Passwort <code>2014</code> zum Entsperren</td>
        </tr>
        <tr>
          <td style="padding:4px 8px"><strong>Sensoren &ldquo;unavailable&rdquo; nachts</strong></td>
          <td style="padding:4px 8px">Normal &mdash; Wechselrichter im Sleep Mode (kein PV, keine Last)</td>
        </tr>
      </table>`,
  },
  solaredge: {
    title: "SolarEdge Modbus Multi einrichten",
    content: `
      <h3 style="margin:16px 0 8px">1. Wechselrichter vorbereiten</h3>
      <p style="margin-bottom:8px">Modbus TCP muss am Wechselrichter aktiviert sein. Je nach Modell gibt es zwei Varianten:</p>
      <h4 style="margin:12px 0 4px">SetApp-Wechselrichter (ohne LCD-Display)</h4>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Roten <strong>DIP-Schalter</strong> am Wechselrichter kurz (< 5 Sek.) auf <strong>&ldquo;P&rdquo;</strong> stellen
          <br><span style="color:var(--secondary-text-color)">Aktiviert den WiFi-Direct-Hotspot des Wechselrichters.</span>
        </li>
        <li>Handy-WLAN mit dem Wechselrichter-Hotspot verbinden (Netzwerkname steht auf dem Ger&auml;t)</li>
        <li>Im Browser <code>http://172.16.0.1</code> &ouml;ffnen</li>
        <li><strong>Site Communication</strong> &ouml;ffnen</li>
        <li><strong>Modbus/TCP</strong> aktivieren</li>
      </ol>
      <div style="background:var(--warning-color,#ff9800);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9888; Zeitfenster:</strong> Die Integration muss sich <strong>innerhalb von 2 Minuten</strong> nach dem Aktivieren verbinden! Danach bleibt der Port offen. Falls zu sp&auml;t: Modbus TCP aus- und wieder einschalten.
      </div>
      <h4 style="margin:12px 0 4px">LCD-Wechselrichter (&auml;ltere Modelle)</h4>
      <ol style="padding-left:20px;line-height:1.8">
        <li><strong>&ldquo;OK&rdquo;</strong> f&uuml;r 5 Sekunden dr&uuml;cken (Installer-Modus)</li>
        <li>Passwort: <code>12312312</code></li>
        <li><strong>Communications &rarr; LAN setup</strong> navigieren</li>
        <li>Modbus/TCP Port konfigurieren</li>
      </ol>
      <div style="background:var(--warning-color,#ff9800);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9888; Wichtig:</strong> SolarEdge erlaubt nur <strong>EINE Modbus-Verbindung</strong> gleichzeitig! Andere Modbus-Integrationen m&uuml;ssen deaktiviert werden.
      </div>
      <h3 style="margin:16px 0 8px">2. HACS Integration installieren</h3>
      <p style="margin-bottom:8px;color:var(--secondary-text-color)"><strong>Voraussetzung:</strong> <a href="https://hacs.xyz/" target="_blank">HACS</a> muss installiert sein.</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>HACS &rarr; Integrationen &rarr; Suche &ldquo;SolarEdge Modbus Multi&rdquo;</strong>
          <br><span style="color:var(--secondary-text-color)">Repository: WillCodeForCats/solaredge-modbus-multi</span>
        </li>
        <li>Installiere die Integration und <strong>starte Home Assistant neu</strong></li>
      </ol>
      <h3 style="margin:16px 0 8px">3. Integration konfigurieren</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&ldquo;SolarEdge Modbus Multi&rdquo;</strong></li>
        <li>Gib die <strong>IP-Adresse</strong> des Wechselrichters ein</li>
        <li>Port: <strong>1502</strong> (Standard f&uuml;r SolarEdge Modbus TCP)</li>
        <li>Device ID: <strong>1</strong></li>
      </ol>
      <h3 style="margin:16px 0 8px">4. Speichersteuerung aktivieren</h3>
      <div style="background:var(--error-color,#db4437);color:#fff;padding:8px 12px;border-radius:8px;margin:0 0 12px;font-size:13px">
        <strong>&#9888; Pflichtschritt!</strong> Ohne diesen Schritt fehlen die Steuerungs-Entities und der EEG Energy Optimizer kann die Batterie nicht steuern.
      </div>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Integrationen &rarr; SolarEdge Modbus Multi</strong></li>
        <li>Klicke auf das <strong>Drei-Punkte-Men&uuml;</strong> &rarr; <strong>&ldquo;Konfigurieren&rdquo;</strong></li>
        <li>Aktiviere <strong>&ldquo;Allow StorEdge Control&rdquo;</strong> (Speichersteuerung)</li>
        <li>Speichern und <strong>Integration neu laden</strong></li>
      </ol>
      <p style="margin:8px 0;color:var(--secondary-text-color);font-size:13px">Nach dem Neuladen sollten diese Entities erscheinen: <code>select.*storage_command_mode</code>, <code>number.*storage_charge_limit</code>, <code>number.*storage_discharge_limit</code></p>
      <p style="margin:4px 0;color:var(--secondary-text-color);font-size:13px"><strong>Hinweis:</strong> Der EEG Energy Optimizer setzt <code>storage_control_mode</code> bei Bedarf automatisch auf &ldquo;Remote Control&rdquo; und stellt den Originalzustand danach wieder her.</p>
      <div style="background:var(--info-color,#039be5);color:#fff;padding:8px 12px;border-radius:8px;margin:8px 0 12px;font-size:13px">
        <strong>&#9432; NVRAM-Schreibvorg&auml;nge:</strong> SolarEdge speichert Modbus-Register&auml;nderungen im Flash-Speicher (NVRAM). Der EEG Energy Optimizer minimiert Schreibvorg&auml;nge: max. ~12 Writes/Tag (Worst Case), an bew&ouml;lkten Tagen oder im Winter 0 Writes. Realistisch ~7 Writes/Tag im Jahresdurchschnitt &rarr; ~39 Jahre bei 100.000 Flash-Zyklen.
      </div>
      <h3 style="margin:16px 0 8px">5. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Unter <strong>Einstellungen &rarr; Integrationen</strong>: SolarEdge Modbus Multi zeigt <strong>&ldquo;geladen&rdquo;</strong></li>
        <li><strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: <code>sensor.solaredge_*_b1_state_of_energy</code> zeigt SOC (0&ndash;100%)</li>
        <li><code>select.solaredge_*_storage_command_mode</code> existiert (= Speichersteuerung aktiv)</li>
        <li>Kehre hierher zur&uuml;ck &mdash; der Wechselrichter wird automatisch erkannt</li>
      </ol>
      <p style="margin:4px 0;color:var(--secondary-text-color);font-size:13px"><strong>Hinweis:</strong> Der Entity-Prefix variiert je Installation (z.B. <code>solaredge_i1_</code> statt <code>solaredge_</code>). Der EEG Energy Optimizer erkennt den Prefix automatisch.</p>
      <h3 style="margin:16px 0 8px">H&auml;ufige Probleme</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Connection refused</strong></td>
          <td style="padding:4px 8px">Modbus TCP nicht aktiviert &rarr; Schritt 1 wiederholen</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Connection timeout</strong></td>
          <td style="padding:4px 8px">Port 1502 pr&uuml;fen. Bei SetApp: 2-Minuten-Fenster beachten</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Keine Batterie-Entities</strong></td>
          <td style="padding:4px 8px">Options &rarr; &ldquo;Detect Batteries&rdquo; aktivieren</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Keine Storage-Entities</strong></td>
          <td style="padding:4px 8px">&ldquo;Allow StorEdge Control&rdquo; in Options nicht aktiviert &rarr; Schritt 4</td>
        </tr>
        <tr>
          <td style="padding:4px 8px"><strong>Verbindung bricht ab</strong></td>
          <td style="padding:4px 8px">Nur EINE Modbus-Verbindung m&ouml;glich &mdash; andere Integrationen deaktivieren</td>
        </tr>
      </table>`,
  },
  fronius: {
    title: "Fronius Gen24 einrichten",
    content: `
      <h3 style="margin:16px 0 8px">1. Fronius Integration in Home Assistant</h3>
      <p style="margin-bottom:8px">Die native Fronius Integration wird f&uuml;r das Lesen der Sensoren (PV, Batterie, SOC, Netz) ben&ouml;tigt:</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Wird normalerweise <strong>automatisch via Auto-Discovery</strong> erkannt
          <br><span style="color:var(--secondary-text-color)">Falls nicht: Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen &rarr; &ldquo;Fronius&rdquo;</span>
        </li>
        <li>IP-Adresse des Wechselrichters angeben</li>
        <li>Die <strong>Solar API</strong> muss im Fronius Web-Interface aktiviert sein (Standard ab FW 1.14.1)</li>
      </ol>

      <h3 style="margin:16px 0 8px">2. Modbus TCP am Wechselrichter aktivieren</h3>
      <p style="margin-bottom:8px">Der EEG Energy Optimizer steuert die Batterie &uuml;ber Modbus TCP (SunSpec Model 124). Daf&uuml;r muss Modbus am Wechselrichter aktiviert werden:</p>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Fronius Web-Interface &ouml;ffnen: <code>http://&lt;IP des Wechselrichters&gt;</code></li>
        <li><strong>Communication &rarr; Modbus &rarr; Aktivieren</strong></li>
        <li>Mode: <strong>TCP Server</strong></li>
        <li>SunSpec Model Type: <strong>int + SF</strong>
          <br><span style="color:var(--secondary-text-color)">Wichtig: Nicht &ldquo;float&rdquo; w&auml;hlen &mdash; die Register-Adressen unterscheiden sich!</span>
        </li>
        <li>Port: <strong>502</strong> (Standard)</li>
        <li><strong>Allow Control via Modbus: EIN</strong>
          <br><span style="color:var(--secondary-text-color)">Ohne diese Einstellung werden alle Schreibzugriffe abgelehnt!</span>
        </li>
      </ol>
      <div style="background:var(--warning-color,#ff9800);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9888; Wichtig:</strong> Alle Scheduled (Dis)Charging Zeitpl&auml;ne im Web-Interface deaktivieren! Modbus und Web-Interface konkurrieren &mdash; der h&ouml;here Wert gewinnt.
      </div>
      <div style="background:var(--info-color,#2196f3);color:#fff;padding:8px 12px;border-radius:8px;margin:12px 0;font-size:13px">
        <strong>&#9432; Hinweis:</strong> Der Wechselrichter beh&auml;lt Modbus-Einstellungen (z.B. Lade-/Entladesperre) auch nach einem Absturz oder Neustart des Optimizers bei, bis ein neuer Schreibbefehl kommt oder der Wechselrichter selbst neu gestartet wird. Im Normalbetrieb stellt der Optimizer den Ausgangszustand automatisch wieder her.
      </div>

      <h3 style="margin:16px 0 8px">3. Firmware</h3>
      <ul style="padding-left:20px;line-height:1.8">
        <li><strong>Minimum:</strong> >= 1.34.6-1</li>
        <li><strong>Empfohlen:</strong> >= 1.40.0</li>
      </ul>

      <h3 style="margin:16px 0 8px">4. Pr&uuml;fen</h3>
      <ol style="padding-left:20px;line-height:1.8">
        <li>Unter <strong>Einstellungen &rarr; Integrationen</strong>: Fronius zeigt <strong>&ldquo;geladen&rdquo;</strong></li>
        <li><strong>Entwicklerwerkzeuge &rarr; Zust&auml;nde</strong>: Suche nach <code>power_photovoltaics</code> / <code>pv_leistung</code> und <code>state_of_charge</code> / <code>ladezustand</code></li>
        <li>Kehre hierher zur&uuml;ck &mdash; die Sensoren werden automatisch erkannt</li>
      </ol>

      <h3 style="margin:16px 0 8px">H&auml;ufige Probleme</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Modbus Connection refused</strong></td>
          <td style="padding:4px 8px">Modbus TCP nicht aktiviert oder &ldquo;Allow Control&rdquo; nicht EIN &rarr; Schritt 2 wiederholen</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Alle Werte 0 oder unsinnig</strong></td>
          <td style="padding:4px 8px">Falscher SunSpec-Modus &rarr; &ldquo;int + SF&rdquo; statt &ldquo;float&rdquo; einstellen</td>
        </tr>
        <tr style="border-bottom:1px solid var(--divider-color)">
          <td style="padding:4px 8px"><strong>Keine Fronius-Sensoren in HA</strong></td>
          <td style="padding:4px 8px">Fronius Integration pr&uuml;fen: Solar API im Web-Interface aktiviert?</td>
        </tr>
        <tr>
          <td style="padding:4px 8px"><strong>Steuerung funktioniert manchmal nicht</strong></td>
          <td style="padding:4px 8px">Scheduled Charging/Discharging im Web-Interface deaktivieren (konkurriert mit Modbus)</td>
        </tr>
      </table>`,
  },
};

// Suppress HA-internal unhandled promise rejections that crash the panel
window.addEventListener("unhandledrejection", (e) => {
  const msg = e.reason?.message || String(e.reason || "");
  if (msg.includes("Subscription not found") ||
      msg.includes("Transition was") ||
      msg.includes("message channel closed") ||
      msg.includes("asynchronous response")) {
    e.preventDefault();
    if (msg.includes("Transition")) {
      // Force panel recovery after View Transition failure
      const panel = document.querySelector("eeg-optimizer-panel");
      if (panel && panel._initialized && panel._shadow) {
        if (!panel._shadow.querySelector(".content")) {
          panel._render();
        }
      }
    }
  }
});

// Also suppress synchronous errors from HA internals / extensions
window.addEventListener("error", (e) => {
  const msg = e.message || "";
  if (msg.includes("message channel closed") ||
      msg.includes("asynchronous response")) {
    e.preventDefault();
  }
});

// Format a number with German decimal comma instead of dot.
const fmtDe = (value, decimals = 1) => Number(value).toFixed(decimals).replace(".", ",");

class EegOptimizerPanel extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: "open" });
    this._hass = null;
    this._view = "dashboard";
    this._config = null;
    this._setupComplete = false;
    this._wizardStep = 0;
    this._wizardData = { ...WIZARD_DEFAULTS };
    this._narrow = false;
    this._initialized = false;
    this._prerequisites = null;
    this._detectedSensors = null;
    this._wizardLoading = false;
    this._showDialog = null;
    this._activeInfoModal = null;
    this._infoImageZoomed = false;
    this._entityPickerLoaded = false;
    this._showAdvanced = {};
    this._capacityMode = null;
    this._capacityModeUserSet = false;
    this._manualAction = null;
    this._manualResult = null;
    this._manualDischargeKw = null;
    this._manualDischargeSoc = 25;
    this._simFactor = 1.0;
    this._simSocOverride = null;
    this._simActive = false;
    this._simLoading = false;
    this._simSocEnabled = false;
    this._activityLog = [];
    this._activityLogLoaded = false;
    this._activityUnsub = null;
    this._activityTotal = 0;
    this._activityHasMore = false;
    this._activityLoadingMore = false;
    this._activityShowAll = false;
    this._activityFilter = ""; // "" = alle, "Morgen-Einspeisung", "Abend-Entladung"
    this._activityLogOpen = this._loadPref("activity_log_open", "0", ["0", "1"]) === "1";
    this._loadConfigPending = false;
    this._connectionLostSeen = false;
    this._manualControlOpen = false;
    this._simulationOpen = false;
    this._feedinStats = null;
    this._feedinStatsLoaded = false;
    this._feedinStatsOpen = false;
    this._feedinStatsPeriod = "month";
    this._profilOpen = false;
    // Persisted in localStorage so the user's last choice survives page reloads.
    this._profilChartVariant = this._loadPref("profil_chart_variant", "hourly", ["hourly", "daynight"]);
    this._statusViewVariant = this._loadPref("status_view_variant", "values", ["values", "flow"]);
    this._settingsTab = this._loadPref("settings_tab", "morning", ["morning", "evening", "telemetry", "advanced"]);
    this._dischargeTile1Open = false;
    this._dischargeTile2Open = false;
    this._morningTile1Open = false;
    this._profileRefreshing = false;
    this._profileRefreshResult = null;
    this._peakshareDataOpen = false;
    this._peakshareData = null;
    this._peakshareDataLoaded = false;
    this._settingsData = {};
    this._peakshareCommunitiesCache = [];
    this._peakshareCommunitiesLoading = false;
    // Community-Statistik (Phase 8: Telemetrie-Opt-In)
    this._telemetryStatus = null;
    this._telemetryError = null;
    this._telemetryBusy = false;
    this._lastHassUpdate = Date.now();

    // Recover from network switches / long sleep when tab becomes visible
    this._onVisibilityChange = () => {
      if (document.visibilityState === "visible" && this._hass) {
        const elapsed = Date.now() - this._lastHassUpdate;
        // If no hass update for >30s, the connection likely dropped
        if (elapsed > 30000) {
          console.info("EEG Energy Optimizer: tab visible after " + Math.round(elapsed / 1000) + "s, refreshing");
          this._loadConfigPending = false;
          this._loadConfigWithRetry();
        }
      }
    };
    document.addEventListener("visibilitychange", this._onVisibilityChange);

    // Start watchdog for active-tab connection drops
    this._watchdogInterval = null;
    this._startWatchdog();

    // Event delegation on shadow root
    // Legend hover: highlight matching weekday line
    this._shadow.addEventListener("mouseover", (e) => {
      const dot = e.target.closest(".ps-dot, .ps-dot-hit");
      if (dot) {
        const wrapper = dot.closest(".ps-chart-card");
        const tt = wrapper?.querySelector(".ps-tooltip");
        if (tt) {
          const dotRect = dot.getBoundingClientRect();
          const wrapRect = wrapper.getBoundingClientRect();
          const inWin = dot.dataset.inWindow === "1";
          const badge = inWin ? ` <span style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:8px;background:#4CAF50;color:#fff;font-size:10px;font-weight:500">Entladung</span>` : "";
          const dayLine = dot.dataset.day ? `<div style="color:var(--secondary-text-color);font-size:11px;margin-bottom:2px">${dot.dataset.day}</div>` : "";
          tt.innerHTML = `${dayLine}<div style="font-weight:600;margin-bottom:2px">${dot.dataset.hour}${badge}</div><div style="color:var(--secondary-text-color)">Bedarf: <strong style="color:var(--primary-text-color)">${dot.dataset.deficit} kWh</strong></div>`;
          tt.style.display = "block";
          tt.style.left = `${dotRect.left - wrapRect.left + dotRect.width / 2}px`;
          tt.style.top = `${dotRect.top - wrapRect.top - 8}px`;
        }
      }
      const legendItem = e.target.closest(".wl-legend");
      if (!legendItem) return;
      const idx = legendItem.dataset.idx;
      const svg = legendItem.closest("svg");
      if (!svg) return;
      svg.querySelectorAll(".wl").forEach(g => g.classList.remove("wl-legend-hover"));
      const target = svg.querySelector(`.wl[data-idx="${idx}"]`);
      if (target) target.classList.add("wl-legend-hover");
    });
    this._shadow.addEventListener("mouseout", (e) => {
      const dot = e.target.closest(".ps-dot, .ps-dot-hit");
      if (dot) {
        const wrapper = dot.closest(".ps-chart-card");
        const tt = wrapper?.querySelector(".ps-tooltip");
        if (tt) tt.style.display = "none";
      }
      const legendItem = e.target.closest(".wl-legend");
      if (!legendItem) return;
      const svg = legendItem.closest("svg");
      if (!svg) return;
      svg.querySelectorAll(".wl").forEach(g => g.classList.remove("wl-legend-hover"));
    });

    // Info popup toggle for touch devices
    this._shadow.addEventListener("click", (e) => {
      const trigger = e.target.closest(".info-popup-trigger");
      if (trigger) {
        e.stopPropagation();
        // Close any other open popups
        this._shadow.querySelectorAll(".info-popup-trigger.active").forEach(t => {
          if (t !== trigger) t.classList.remove("active");
        });
        trigger.classList.toggle("active");
        return;
      }
      // Close popups when clicking elsewhere
      this._shadow.querySelectorAll(".info-popup-trigger.active").forEach(t => t.classList.remove("active"));

      // Close dialog/info-modal when clicking overlay background (not the card itself)
      if (e.target.classList.contains("dialog-overlay")) {
        this._showDialog = null;
        this._render();
        return;
      }
      if (e.target.classList.contains("info-modal-overlay")) {
        this._activeInfoModal = null;
        this._infoImageZoomed = false;
        this._render();
        return;
      }
      const btn = e.target.closest("[data-action]") || e.target;
      const action = btn?.dataset?.action;
      if (action === "toggle-telemetry") {
        // Checkbox: nutze den (nach Klick aktualisierten) checked-Zustand
        this._handleTelemetryToggle(!!btn.checked);
        return;
      }
      if (action === "forget-telemetry") {
        this._handleTelemetryForget();
        return;
      }
      if (action) {
        this._handleAction(action, btn.dataset);
      }
    });

    // Listen for value-changed events from ha-entity-picker
    this._shadow.addEventListener("value-changed", (e) => {
      const target = e.target.closest("[data-field]");
      if (target) {
        const field = target.dataset.field;
        this._wizardData[field] = e.detail?.value || "";
      }
    });

    // Listen for input/change events for native inputs
    this._shadow.addEventListener("input", (e) => {
      const target = e.target.closest("[data-field]");
      if (target) {
        const field = target.dataset.field;
        if (field === "manual_discharge_kw") {
          this._manualDischargeKw = parseFloat(target.value) || 3.0;
          return;
        }
        if (field === "manual_discharge_soc") {
          this._manualDischargeSoc = parseFloat(target.value) || 12;
          return;
        }
        if (field === "sim_factor") {
          this._simFactor = parseFloat(target.value) || 1.0;
          return;
        }
        if (field === "sim_soc") {
          this._simSocOverride = parseFloat(target.value);
          return;
        }
        if (field.startsWith("settings_")) {
          const realField = field.replace("settings_", "");
          const type = target.type;
          if (type === "checkbox") {
            this._settingsData[realField] = target.checked;
            this._render();
          } else if (type === "number") {
            let numVal = parseFloat(target.value) || 0;
            // SolarEdge: enforce minimum discharge power of 5 kW
            if (realField === "discharge_power_kw" && this._config?.inverter_type === "solaredge_storedge" && numVal < 5.0) {
              numVal = 5.0;
              target.value = "5.0";
            }
            this._settingsData[realField] = numVal;
          } else {
            this._settingsData[realField] = target.value;
          }
          return;
        }
        const type = target.type;
        if (type === "number") {
          let numVal = parseFloat(target.value) || 0;
          if (field === "discharge_power_kw" && this._wizardData.inverter_type === "solaredge_storedge" && numVal < 5.0) {
            numVal = 5.0;
            target.value = "5.0";
          }
          this._wizardData[field] = numVal;
        } else {
          this._wizardData[field] = target.value;
        }
      }
    });

    this._shadow.addEventListener("change", (e) => {
      const target = e.target.closest("[data-field]");
      if (target) {
        const field = target.dataset.field;
        if (field === "sim_soc_enabled") {
          this._simSocEnabled = target.checked;
          this._render();
          return;
        }
        if (field === "activity_filter") {
          this._activityFilter = target.value;
          this._render();
          return;
        }
        if (field.startsWith("settings_")) {
          const realField = field.replace("settings_", "");
          const type = target.type;
          if (type === "checkbox") {
            this._settingsData[realField] = target.checked;
            if (realField === "enable_peakshare" && target.checked && this._peakshareCommunitiesCache.length === 0) {
              this._loadPeakShareCommunities();
            }
            // Re-render only for toggles that change UI visibility (e.g. enable_peakshare reveals the community dropdown).
            // For simple number/text inputs we skip _render() — otherwise a click on "Speichern" right after editing
            // a value triggers blur→change→render, which replaces the save button DOM node and swallows the click.
            this._render();
          } else if (type === "number") {
            let numVal = parseFloat(target.value) || 0;
            if (realField === "discharge_power_kw" && this._config?.inverter_type === "solaredge_storedge" && numVal < 5.0) {
              numVal = 5.0;
              target.value = "5.0";
            }
            this._settingsData[realField] = numVal;
          } else {
            this._settingsData[realField] = target.value;
          }
          return;
        }
        if (field === "expert_mode") {
          this._wizardData[field] = target.checked;
          // Skip step 5 if leaving expert mode while on it
          if (!target.checked && this._wizardStep === 5) {
            this._wizardStep = 6;
          }
          this._saveWizardProgress();
          this._render();
          return;
        }
        if (field === "enable_simulation" || field === "enable_manual_control") {
          this._wizardData[field] = target.checked;
          this._saveWizardProgress();
          this._render();
          return;
        }
        if (field === "enable_peakshare") {
          this._wizardData[field] = target.checked;
          if (target.checked && this._peakshareCommunitiesCache.length === 0) {
            this._loadPeakShareCommunities();
          }
          this._saveWizardProgress();
          this._render();
          return;
        }
        if (target.tagName === "SELECT") {
          this._wizardData[field] = target.value;
          if (field === "forecast_source") {
            this._applyForecastDefaults(target.value);
            this._render();
          }
        } else if (target.type === "radio") {
          this._wizardData[field] = target.value;
        }
      }
    });
  }

  // localStorage-backed UI preferences (e.g. last-selected chart variants).
  // Wrapped so SSR/test environments without window.localStorage don't crash.
  _loadPref(key, fallback, allowed) {
    try {
      const raw = window.localStorage?.getItem(`eeg_optimizer_panel_${key}`);
      if (raw && (!allowed || allowed.includes(raw))) return raw;
    } catch (e) { /* ignore */ }
    return fallback;
  }

  _savePref(key, value) {
    try {
      window.localStorage?.setItem(`eeg_optimizer_panel_${key}`, String(value));
    } catch (e) { /* ignore */ }
  }

  _handleAction(action, dataset) {
    switch (action) {
      case "start-wizard":
      case "open-wizard":
        this._startWizard();
        break;
      case "open-settings":
        this._settingsData = {...this._config};
        this._view = "settings";
        if (this._settingsData.enable_peakshare !== false && this._peakshareCommunitiesCache.length === 0) {
          this._loadPeakShareCommunities();
        }
        this._render();
        break;
      case "restart-wizard":
        this._clearWizardProgress();
        this._wizardStep = 0;
        this._wizardData = {...WIZARD_DEFAULTS, ...this._config};
        this._view = "wizard";
        this._render();
        break;
      case "save-settings":
        this._saveSettings();
        break;
      case "toggle-settings-feature": {
        const feat = dataset?.feature;
        if (feat) { this._settingsData[feat] = !this._settingsData[feat]; this._render(); }
        break;
      }
      case "back-to-dashboard":
        this._view = "dashboard";
        this._render();
        break;
      case "dismiss-toast":
        if (this._toastTimer) {
          clearTimeout(this._toastTimer);
          this._toastTimer = null;
        }
        this._toast = null;
        this._render();
        break;
      case "next-step":
        this._nextStep();
        break;
      case "prev-step":
        this._wizardStep = Math.max(0, this._wizardStep - 1);
        // Skip "Erweiterte Einstellungen" (step 5) in non-expert mode
        if (this._wizardStep === 5 && !this._wizardData.expert_mode) {
          this._wizardStep = 4;
        }
        this._saveWizardProgress();
        this._refreshStepData();
        break;
      case "finish-wizard":
        this._finishWizard();
        break;
      case "show-dialog":
        this._showDialog = DIALOG_CONTENT[dataset?.dialog] || null;
        this._render();
        break;
      case "close-dialog":
        this._showDialog = null;
        this._render();
        break;
      case "recheck-prerequisites":
        this._checkPrerequisites();
        break;
      case "toggle-sidebar":
        this._toggleHaSidebar();
        break;
      case "refresh-activity-log":
        this._activityLog = [];
        this._activityTotal = 0;
        this._activityHasMore = false;
        this._loadActivityLog();
        break;
      case "show-more-activity":
        this._loadMoreActivity();
        break;
      case "toggle-activity-show-all":
        this._activityShowAll = !this._activityShowAll;
        this._render();
        break;
      case "show-info": {
        this._activeInfoModal = dataset.info || null;
        this._infoImageZoomed = false;
        this._render();
        break;
      }
      case "close-info-modal": {
        this._activeInfoModal = null;
        this._infoImageZoomed = false;
        this._render();
        break;
      }
      case "open-lightbox": {
        this._infoImageZoomed = true;
        this._render();
        break;
      }
      case "close-lightbox": {
        this._infoImageZoomed = false;
        this._render();
        break;
      }
      case "show-entity": {
        const entityId = dataset.entity;
        if (entityId) {
          const event = new Event("hass-more-info", { composed: true, bubbles: true });
          event.detail = { entityId };
          this._shadow.host.dispatchEvent(event);
        }
        break;
      }
      case "toggle-mode": {
        const modeState = this._readState(this._entityIds?.select || "select.eeg_energy_optimizer_optimizer");
        const currentMode = modeState ? modeState.state : "Test";
        const newMode = currentMode === "Ein" ? "Test" : "Ein";
        this._hass.callService("select", "select_option", {
          entity_id: this._entityIds?.select || "select.eeg_energy_optimizer_optimizer",
          option: newMode
        });
        break;
      }
      case "manual-stop":
        this._executeManualAction("stop", { type: "eeg_optimizer/manual_stop" });
        break;
      case "manual-discharge":
        this._executeManualAction("discharge", {
          type: "eeg_optimizer/manual_discharge",
          power_kw: this._manualDischargeKw || this._config?.discharge_power_kw || 5.0,
          target_soc: this._manualDischargeSoc,
        });
        break;
      case "manual-block-charge":
        this._executeManualAction("block", { type: "eeg_optimizer/manual_block_charge" });
        break;
      case "select-forecast": {
        const value = dataset?.value;
        if (value) {
          this._wizardData.forecast_source = value;
          this._applyForecastDefaults(value);
          this._render();
        }
        break;
      }
      case "select-inverter": {
        const invValue = dataset?.value;
        if (invValue && invValue !== this._wizardData.inverter_type) {
          this._wizardData.inverter_type = invValue;
          // SolarEdge: default 5 kW, minimum 5 kW
          if (invValue === "solaredge_storedge") {
            this._wizardData.discharge_power_kw = 5.0;
          } else {
            this._wizardData.discharge_power_kw = 3.0;
          }
          // Clear sensor fields so auto-detection can re-fill them
          const sensorKeys = [
            "pv_power_sensor", "battery_power_sensor", "grid_power_sensor",
            "battery_power_charge_sensor", "battery_power_discharge_sensor",
            "grid_power_export_sensor", "grid_power_import_sensor",
            "battery_soc_sensor", "battery_capacity_sensor", "huawei_device_id",
            "pv_power_sensor_2",
            "solax_remotecontrol_power_control", "solax_remotecontrol_active_power",
            "solax_remotecontrol_autorepeat_duration", "solax_remotecontrol_trigger",
            "solax_selfuse_discharge_min_soc",
          ];
          for (const k of sensorKeys) this._wizardData[k] = "";
          this._detectedSensors = null;
          this._detectSensors();
        }
        break;
      }
      case "set-cap-mode": {
        const radio = this._shadow.querySelector('input[name="cap_mode"]:checked');
        if (radio) {
          this._capacityMode = radio.value;
          this._capacityModeUserSet = true;
          if (radio.value === "manual") {
            this._wizardData.battery_capacity_sensor = "";
          } else {
            this._wizardData.battery_capacity_kwh = "";
          }
          this._render();
        }
        break;
      }
      case "toggle-feature": {
        const feature = dataset?.feature;
        if (feature) {
          this._wizardData[feature] = !this._wizardData[feature];
          this._render();
        }
        break;
      }
      case "set-cap-mode-card": {
        const mode = dataset?.value;
        if (mode) {
          this._capacityMode = mode;
          this._capacityModeUserSet = true;
          if (mode === "manual") {
            this._wizardData.battery_capacity_sensor = "";
          } else {
            this._wizardData.battery_capacity_kwh = "";
          }
          this._render();
        }
        break;
      }
      case "toggle-advanced":
        const section = dataset?.section || "default";
        this._showAdvanced[section] = !this._showAdvanced[section];
        this._render();
        break;
      case "sim-apply": {
        if (!confirm("Willst du wirklich in den Simulationsmodus wechseln?\n\nHinweis: Dadurch kann die Batterieladung verhindert werden oder aus der Batterie eingespeist werden, obwohl dies nicht sinnvoll ist.")) break;
        const factor = this._simFactor;
        const params = { type: "eeg_optimizer/set_test_overrides", consumption_factor: factor };
        if (this._simSocEnabled && this._simSocOverride !== null) {
          params.soc_override = this._simSocOverride;
        }
        this._simLoading = true;
        this._render();
        this._hass.callWS(params).then(res => {
          if (res.success) this._simActive = true;
        }).catch(err => console.error("set_test_overrides failed:", err))
        .finally(() => { this._simLoading = false; this._render(); });
        break;
      }
      case "sim-reset":
        this._simLoading = true;
        this._render();
        this._hass.callWS({ type: "eeg_optimizer/clear_test_overrides" }).then(() => {
          this._simActive = false;
          this._simFactor = 1.0;
          this._simSocOverride = null;
          this._simSocEnabled = false;
        }).catch(err => console.error("clear_test_overrides failed:", err))
        .finally(() => { this._simLoading = false; this._render(); });
        break;
      case "toggle-manual-control":
        this._manualControlOpen = !this._manualControlOpen;
        this._render();
        break;
      case "toggle-activity-log":
        this._activityLogOpen = !this._activityLogOpen;
        this._savePref("activity_log_open", this._activityLogOpen ? "1" : "0");
        this._render();
        break;
      case "toggle-simulation":
        this._simulationOpen = !this._simulationOpen;
        this._render();
        break;
      case "toggle-feedin-stats":
        this._feedinStatsOpen = !this._feedinStatsOpen;
        this._render();
        break;
      case "toggle-profil":
        this._profilOpen = !this._profilOpen;
        this._render();
        break;
      case "set-profil-variant": {
        const variant = dataset?.variant;
        if (variant && variant !== this._profilChartVariant) {
          this._profilChartVariant = variant;
          this._savePref("profil_chart_variant", variant);
          this._render();
        }
        break;
      }
      case "set-status-view": {
        const variant = dataset?.variant;
        if (variant && variant !== this._statusViewVariant) {
          this._statusViewVariant = variant;
          this._savePref("status_view_variant", variant);
          this._render();
        }
        break;
      }
      case "set-settings-tab": {
        const tab = dataset?.tab;
        if (tab && tab !== this._settingsTab) {
          this._settingsTab = tab;
          this._savePref("settings_tab", tab);
          this._render();
        }
        break;
      }
      case "toggle-discharge-tile-1":
        this._dischargeTile1Open = !this._dischargeTile1Open;
        this._render();
        break;
      case "toggle-discharge-tile-2":
        this._dischargeTile2Open = !this._dischargeTile2Open;
        this._render();
        break;
      case "toggle-morning-tile-1":
        this._morningTile1Open = !this._morningTile1Open;
        this._render();
        break;
      case "refresh-consumption-profile": {
        if (this._profileRefreshing) break;
        this._profileRefreshing = true;
        this._profileRefreshResult = null;
        this._render();
        this._hass.callWS({ type: "eeg_optimizer/refresh_consumption_profile" })
          .then(res => {
            this._profileRefreshResult = res;
          })
          .catch(err => {
            console.error("refresh_consumption_profile failed:", err);
            this._profileRefreshResult = { success: false, error: String(err?.message || err) };
          })
          .finally(() => {
            this._profileRefreshing = false;
            this._render();
            // Auto-clear das Erfolg-/Fehlerbanner nach 6 Sekunden
            if (this._profileRefreshResult) {
              const tag = this._profileRefreshResult;
              setTimeout(() => {
                if (this._profileRefreshResult === tag) {
                  this._profileRefreshResult = null;
                  this._render();
                }
              }, 6000);
            }
          });
        break;
      }
      case "toggle-peakshare-data":
        this._peakshareDataOpen = !this._peakshareDataOpen;
        if (this._peakshareDataOpen && !this._peakshareDataLoaded) {
          this._loadPeakShareData();
        }
        this._render();
        break;
      case "feedin-period-week":
        this._feedinStatsPeriod = "week";
        this._render();
        break;
      case "feedin-period-month":
        this._feedinStatsPeriod = "month";
        this._render();
        break;
      case "feedin-period-year":
        this._feedinStatsPeriod = "year";
        this._render();
        break;
      case "feedin-period-total":
        this._feedinStatsPeriod = "total";
        this._render();
        break;
    }
  }

  /* ── Wizard lifecycle ─────────────────────────── */

  _startWizard() {
    this._view = "wizard";

    // Try restore from localStorage
    const saved = this._loadWizardProgress();
    if (saved) {
      this._wizardStep = saved.step;
      this._wizardData = { ...WIZARD_DEFAULTS, ...saved.data };
    } else if (this._config && this._config.setup_complete) {
      // Re-configuration: jump to Ladung & Einspeisung
      this._wizardStep = 4;
      this._wizardData = { ...WIZARD_DEFAULTS };
      for (const key of Object.keys(WIZARD_DEFAULTS)) {
        if (this._config[key] !== undefined && this._config[key] !== null) {
          this._wizardData[key] = this._config[key];
        }
      }
    } else {
      this._wizardStep = 0;
      this._wizardData = { ...WIZARD_DEFAULTS };
    }

    this._prerequisites = null;
    this._detectedSensors = null;
    this._capacityMode = null;
    this._capacityModeUserSet = false;
    this._render();

    // Preload logos and prerequisites in background
    this._checkPrerequisites();
    const logos = [
      "https://brands.home-assistant.io/huawei_solar/logo.png",
      "https://brands.home-assistant.io/forecast_solar/logo.png",
      "https://brands.home-assistant.io/solcast_solar/logo.png",
    ];
    logos.forEach(src => { const img = new Image(); img.src = src; });
  }

  async _refreshStepData() {
    const step = this._wizardStep;
    // Always refresh prerequisites on steps that show install status
    if (step === 1) {
      await this._checkPrerequisites();
      await this._ensureEntityPicker();
      await this._detectSensors();
      return; // _detectSensors calls _render
    }
    if (step === 2) {
      await this._checkPrerequisites();
      await this._ensureEntityPicker();
      this._render();
      return;
    }
    // Load entity picker for sensor steps
    if (step === 3) {
      await this._ensureEntityPicker();
    }
    // Load PeakShare communities when entering step 4 with PeakShare enabled
    if (step === 4 && this._wizardData.enable_peakshare !== false && this._peakshareCommunitiesCache.length === 0) {
      this._loadPeakShareCommunities();
    }
    this._render();
  }

  async _nextStep() {
    if (this._navigating) return;
    this._navigating = true;
    try {
      this._clearValidationError();
      const valid = this._validateCurrentStep();
      if (!valid) return;

      // Async post-validation: read-only Modbus probe to confirm the
      // entered IP belongs to a Fronius inverter before letting the
      // user move past step 1.
      if (
        this._wizardStep === 1 &&
        this._wizardData.inverter_type === "fronius_gen24" &&
        this._wizardData.fronius_modbus_host
      ) {
        const ok = await this._probeFroniusConnection();
        if (!ok) return;
      }

      this._wizardStep = Math.min(WIZARD_STEPS.length - 1, this._wizardStep + 1);
      // Skip "Erweiterte Einstellungen" (step 5) in non-expert mode
      if (this._wizardStep === 5 && !this._wizardData.expert_mode) {
        this._wizardStep = 6;
      }
      this._saveWizardProgress();
      await this._refreshStepData();
    } finally {
      this._navigating = false;
    }
  }

  async _probeFroniusConnection() {
    const host = (this._wizardData.fronius_modbus_host || "").trim();
    const port = parseInt(this._wizardData.fronius_modbus_port, 10) || 502;
    this._froniusProbing = true;
    this._render();
    try {
      const res = await this._hass.callWS({
        type: "eeg_optimizer/probe_fronius",
        host,
        port,
      });
      if (!res || !res.success) {
        this._showValidationError(
          `Fronius unter ${host}:${port} nicht erreichbar — ${res?.error || "unbekannter Fehler"}`
        );
        return false;
      }
      if (!res.is_fronius) {
        this._showValidationError(
          `Gerät unter ${host}:${port} antwortet, ist aber kein Fronius (Hersteller: ${res.manufacturer || "unbekannt"}). Bitte IP prüfen.`
        );
        return false;
      }
      return true;
    } catch (err) {
      this._showValidationError(
        `Verbindungstest fehlgeschlagen: ${err?.message || err}`
      );
      return false;
    } finally {
      this._froniusProbing = false;
      this._render();
    }
  }

  _validateCurrentStep() {
    switch (this._wizardStep) {
      case 1: { // Wechselrichter
        if (!this._wizardData.inverter_type) {
          this._showValidationError("Bitte wähle einen Wechselrichter-Typ aus.");
          return false;
        }
        const invType = this._wizardData.inverter_type;
        const invP = this._prerequisites;
        if (invType === "huawei_sun2000" && invP && !invP.huawei_solar) {
          this._showValidationError("Huawei Solar Integration muss zuerst installiert werden.");
          return false;
        }
        if (invType === "solax_gen4" && invP && !invP.solax_modbus) {
          this._showValidationError("SolaX Modbus Integration muss zuerst installiert werden.");
          return false;
        }
        if (invType === "solaredge_storedge" && invP && !invP.solaredge_modbus_multi) {
          this._showValidationError("SolarEdge Modbus Multi Integration muss zuerst installiert werden.");
          return false;
        }
        if (invType === "fronius_gen24" && invP && !invP.fronius) {
          this._showValidationError("Fronius Integration nicht gefunden. Diese wird f\u00fcr die Sensoren ben\u00f6tigt. Klicke auf 'Anleitung' f\u00fcr Hilfe.");
          return false;
        }
        if (invType === "fronius_gen24" && !this._wizardData.fronius_modbus_host) {
          this._showValidationError("Bitte gib die Modbus IP-Adresse des Fronius Wechselrichters ein.");
          return false;
        }
        return true;
      }
      case 2: { // Prognose
        if (!this._wizardData.forecast_source) {
          this._showValidationError("Bitte wähle eine Prognose-Quelle aus.");
          return false;
        }
        const fcSrc = this._wizardData.forecast_source;
        const fcP = this._prerequisites;
        if (fcSrc === "solcast_solar" && fcP && !fcP.solcast_solar) {
          this._showValidationError("Solcast Solar muss zuerst installiert werden. Klicke auf 'Anleitung' für Hilfe.");
          return false;
        }
        if (fcSrc === "forecast_solar" && fcP && !fcP.forecast_solar) {
          this._showValidationError("Forecast.Solar muss zuerst installiert werden. Klicke auf 'Anleitung' für Hilfe.");
          return false;
        }
        if (!this._wizardData.forecast_remaining_entity) {
          this._showValidationError("PV-Prognose verbleibend heute ist erforderlich.");
          return false;
        }
        if (!this._wizardData.forecast_tomorrow_entity) {
          this._showValidationError("PV-Prognose morgen ist erforderlich.");
          return false;
        }
        return true;
      }
      case 3: // Batterie
        if (!this._wizardData.battery_soc_sensor) {
          this._showValidationError("SOC-Sensor ist erforderlich.");
          return false;
        }
        if (
          !this._wizardData.battery_capacity_sensor &&
          !this._wizardData.battery_capacity_kwh
        ) {
          this._showValidationError(
            "Entweder Kapazitäts-Sensor oder manuelle Kapazität ist erforderlich."
          );
          return false;
        }
        return true;
      default:
        return true;
    }
  }

  _showValidationError(msg) {
    this._showToast(msg, "error");
  }

  _clearValidationError() {
    if (this._toastTimer) {
      clearTimeout(this._toastTimer);
      this._toastTimer = null;
    }
    this._toast = null;
    this._render();
  }

  _showToast(msg, type = "error") {
    this._toast = { msg, type };
    if (this._toastTimer) clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this._toast = null;
      this._toastTimer = null;
      this._render();
    }, 7000);
    this._render();
  }

  async _finishWizard() {
    this._wizardLoading = true;
    this._render();

    try {
      this._wizardData.setup_complete = true;
      const saveData = { ...this._wizardData };
      delete saveData.consumption_sensor;
      await this._hass.callWS({
        type: "eeg_optimizer/save_config",
        config: saveData,
      });
      this._clearWizardProgress();
      this._setupComplete = true;
      this._config = { ...this._wizardData };
      this._view = "dashboard";
      this._wizardLoading = false;
      this._render();

      // Integration reloads after config save — poll until optimizer is ready
      this._waitForOptimizer();
    } catch (err) {
      console.error("Failed to save config:", err);
      this._wizardData.setup_complete = false;
      this._wizardLoading = false;
      this._render();
    }
  }

  async _saveSettings() {
    try {
      // Re-read all settings inputs to catch values not yet captured by events
      for (const el of this._shadow.querySelectorAll("[data-field^='settings_']")) {
        const realField = el.dataset.field.replace("settings_", "");
        if (el.type === "checkbox") {
          this._settingsData[realField] = el.checked;
        } else if (el.type === "number") {
          this._settingsData[realField] = parseFloat(el.value) || 0;
        } else {
          this._settingsData[realField] = el.value;
        }
      }
      const changed = {};
      const cfg = this._config || {};
      for (const [k, v] of Object.entries(this._settingsData)) {
        if (JSON.stringify(v) !== JSON.stringify(cfg[k])) changed[k] = v;
      }
      if (Object.keys(changed).length === 0) {
        this._view = "dashboard"; this._render(); return;
      }
      await this._hass.callWS({ type: "eeg_optimizer/save_config", config: changed });
      // Update local config immediately (no full reload anymore)
      this._config = {...this._config, ...changed};
      // Reload PeakShare data if community or enable_peakshare changed
      if ("peakshare_community" in changed || "enable_peakshare" in changed) {
        this._peakshareDataLoaded = false;
        this._peakshareData = null;
        if (this._peakshareDataOpen) this._loadPeakShareData();
      }
      this._view = "dashboard";
      this._render();
    } catch (err) {
      console.error("Settings save error:", err);
      alert("Fehler beim Speichern: " + err.message);
    }
  }

  /* ── localStorage persistence ─────────────────── */

  _saveWizardProgress() {
    localStorage.setItem(
      WIZARD_KEY,
      JSON.stringify({
        step: this._wizardStep,
        data: this._wizardData,
        ts: Date.now(),
      })
    );
  }

  _loadWizardProgress() {
    const raw = localStorage.getItem(WIZARD_KEY);
    if (!raw) return null;
    try {
      const state = JSON.parse(raw);
      if (Date.now() - state.ts > 86400000) {
        // 24h expiry
        localStorage.removeItem(WIZARD_KEY);
        return null;
      }
      return state;
    } catch {
      localStorage.removeItem(WIZARD_KEY);
      return null;
    }
  }

  _clearWizardProgress() {
    localStorage.removeItem(WIZARD_KEY);
  }

  _toggleHaSidebar() {
    // Fire the hass-toggle-menu event that HA's shell listens for.
    // This works on both desktop (toggle sidebar) and mobile (open drawer).
    const ev = new Event("hass-toggle-menu", { bubbles: true, composed: true });
    this.dispatchEvent(ev);
  }

  async _waitForOptimizer(attempt = 0) {
    // Poll config every 2s until setup_complete is reflected (max 15 attempts = 30s)
    if (attempt >= 15) {
      this._loadConfig();
      return;
    }
    try {
      const res = await this._hass.callWS({ type: "eeg_optimizer/get_config" });
      if (res?.config?.setup_complete) {
        await this._loadConfig();
        this._loadActivityLog();
        this._loadFeedinStats();
        this._subscribeActivityEvents();
        return;
      }
    } catch (_) { /* integration still reloading */ }
    setTimeout(() => this._waitForOptimizer(attempt + 1), 2000);
  }

  async _loadActivityLog() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_activity_log",
        offset: 0,
        limit: 100,
      });
      this._activityLog = result?.entries || [];
      this._activityTotal = result?.total || 0;
      this._activityHasMore = result?.has_more || false;
      this._activityLogLoaded = true;
      this._render();
    } catch (e) {
      // Silently ignore — log may not be available yet
    }
  }

  async _loadFeedinStats() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_feedin_statistics",
        days: 0,
      });
      this._feedinStats = result;
      this._feedinStatsLoaded = true;
      this._render();
    } catch (e) {
      // Silently ignore — stats may not be available yet
    }
  }

  async _loadPeakShareCommunities() {
    if (!this._hass || this._peakshareCommunitiesLoading) return;
    this._peakshareCommunitiesLoading = true;
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_peakshare_communities",
      });
      this._peakshareCommunitiesCache = result?.communities || [];
      this._render();
    } catch (e) {
      console.error("Failed to load PeakShare communities:", e);
    } finally {
      this._peakshareCommunitiesLoading = false;
    }
  }

  async _loadPeakShareData() {
    if (!this._hass) return;
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_peakshare_data",
      });
      this._peakshareData = result;
      this._peakshareDataLoaded = true;
      this._render();
    } catch (e) {
      console.error("Failed to load PeakShare data:", e);
    }
  }

  _renderPeakShareDashboard() {
    const d = this._peakshareData;
    if (!d || !d.hours || d.hours.length === 0) {
      return `<p style="color:var(--secondary-text-color);font-size:14px">Keine PeakShare-Daten verf\u00fcgbar. Die Daten werden beim n\u00e4chsten API-Abruf geladen.</p>`;
    }

    const community = d.community || "---";
    const isBeg = community === "BEG";
    const displayCommunity = (isBeg || community === "---") ? community : `EEG ${community}`;
    const legendLabel = isBeg ? "Energiebedarf in der BEG" : "Energiebedarf in der EEG";
    const cacheAge = d.cache_age_minutes != null ? d.cache_age_minutes : null;
    const cacheText = cacheAge != null ? (cacheAge < 60 ? `vor ${cacheAge} Min` : `vor ${Math.round(cacheAge / 60)}h`) : "---";
    const plan = d.discharge_plan;

    // Plan info banner
    let planHtml = "";
    if (plan) {
      planHtml = `<div style="background:var(--primary-color);color:#fff;padding:10px 14px;border-radius:10px;margin-bottom:12px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
        <ha-icon icon="mdi:battery-arrow-down" style="--mdc-icon-size:20px"></ha-icon>
        <strong>Abend-Entladung: ${plan.start}\u2013${plan.end}</strong>
        <span style="opacity:0.8;font-size:13px">(Jitter: ${plan.jitter >= 0 ? "+" : ""}${plan.jitter} Min)</span>
      </div>`;
    } else {
      planHtml = `<div style="background:var(--secondary-text-color)22;padding:10px 14px;border-radius:10px;margin-bottom:12px;font-size:14px;color:var(--secondary-text-color)">
        <ha-icon icon="mdi:clock-outline" style="--mdc-icon-size:18px;vertical-align:middle"></ha-icon>
        Keine Entladung geplant
      </div>`;
    }

    // Line chart of hourly deficit
    const hours = d.hours.filter(h => h.timestamp && h.deficitKwh != null);
    if (hours.length === 0) return planHtml + `<p style="color:var(--secondary-text-color);font-size:13px">Keine Stundendaten vorhanden</p>`;

    const width = 700, height = 300, padding = {top: 25, right: 20, bottom: 58, left: 55};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const values = hours.map(h => Math.max(0, h.deficitKwh));
    const maxVal = Math.max(...values, 1) * 1.15;

    // Parse plan window for highlight
    let planStartMin = -1, planEndMin = -1;
    if (plan) {
      const [sh, sm] = plan.start.split(":").map(Number);
      const [eh, em] = plan.end.split(":").map(Number);
      planStartMin = sh * 60 + sm;
      planEndMin = eh * 60 + em;
      // Overnight: e.g. 20:00-01:00 -> endMin will be < startMin
    }

    const _hourMin = (h) => {
      const ts = new Date(h.timestamp);
      return ts.getHours() * 60 + ts.getMinutes();
    };

    const _inPlanWindow = (min) => {
      if (planStartMin < 0) return false;
      if (planStartMin <= planEndMin) {
        return min >= planStartMin && min < planEndMin;
      }
      // Overnight window
      return min >= planStartMin || min < planEndMin;
    };

    // Build line points
    const _fmtDay = (dt) => dt.toLocaleDateString("de-DE", {weekday: "short", day: "2-digit", month: "2-digit"});
    const _fmtDayShort = (dt) => dt.toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit"});
    const _dayKey = (dt) => `${dt.getFullYear()}-${dt.getMonth()}-${dt.getDate()}`;
    const points = hours.map((h, i) => {
      const x = padding.left + (i / Math.max(hours.length - 1, 1)) * chartW;
      const y = padding.top + chartH - (values[i] / maxVal) * chartH;
      const dt = new Date(h.timestamp);
      return {x, y, hour: dt.getHours(), min: _hourMin(h), deficit: values[i], dayLabel: _fmtDay(dt), dayShort: _fmtDayShort(dt), dayKey: _dayKey(dt)};
    });

    // Discharge window highlight area (green shaded region behind the line)
    let windowArea = "";
    if (plan) {
      // Find points inside the plan window
      const windowPts = [];
      points.forEach((p, i) => {
        if (_inPlanWindow(p.min)) windowPts.push(p);
      });
      if (windowPts.length > 0) {
        const first = windowPts[0];
        const last = windowPts[windowPts.length - 1];
        let areaPath = `M ${first.x},${padding.top + chartH}`;
        windowPts.forEach(p => { areaPath += ` L ${p.x},${p.y}`; });
        areaPath += ` L ${last.x},${padding.top + chartH} Z`;
        windowArea = `<path d="${areaPath}" fill="#4CAF50" fill-opacity="0.25"/>`;
        // Vertical markers for window start/end
        windowArea += `<line x1="${first.x}" y1="${padding.top}" x2="${first.x}" y2="${padding.top + chartH}" stroke="#4CAF50" stroke-width="1.5" stroke-dasharray="6,3"/>`;
        windowArea += `<line x1="${last.x}" y1="${padding.top}" x2="${last.x}" y2="${padding.top + chartH}" stroke="#4CAF50" stroke-width="1.5" stroke-dasharray="6,3"/>`;
        // Labels
        windowArea += `<text x="${first.x}" y="${padding.top - 6}" text-anchor="middle" font-size="10" fill="#4CAF50" font-weight="500">${plan.start}</text>`;
        windowArea += `<text x="${last.x}" y="${padding.top - 6}" text-anchor="middle" font-size="10" fill="#4CAF50" font-weight="500">${plan.end}</text>`;
      }
    }

    // Area fill under the line (light blue)
    let areaPath = `M ${points[0].x},${padding.top + chartH}`;
    points.forEach(p => { areaPath += ` L ${p.x},${p.y}`; });
    areaPath += ` L ${points[points.length - 1].x},${padding.top + chartH} Z`;
    const areaFill = `<path d="${areaPath}" fill="var(--primary-color, #03a9f4)" fill-opacity="0.1"/>`;

    // The line itself
    let linePath = `M ${points[0].x},${points[0].y}`;
    for (let i = 1; i < points.length; i++) {
      linePath += ` L ${points[i].x},${points[i].y}`;
    }
    const lineEl = `<path d="${linePath}" fill="none" stroke="var(--primary-color, #03a9f4)" stroke-width="2.5" stroke-linejoin="round"/>`;

    // Data points with custom HTML tooltips
    let dots = "";
    points.forEach(p => {
      const hourStr = `${String(p.hour).padStart(2, "0")}:00`;
      const color = _inPlanWindow(p.min) ? "#4CAF50" : "var(--primary-color, #03a9f4)";
      const inWindow = _inPlanWindow(p.min) ? "1" : "0";
      dots += `<circle class="ps-dot" cx="${p.x}" cy="${p.y}" r="4" fill="${color}" stroke="var(--card-background-color,#fff)" stroke-width="1.5" data-hour="${hourStr}" data-deficit="${fmtDe(p.deficit, 0)}" data-in-window="${inWindow}" data-day="${p.dayLabel}" style="cursor:pointer"></circle>`;
      dots += `<circle class="ps-dot-hit" cx="${p.x}" cy="${p.y}" r="12" fill="transparent" data-hour="${hourStr}" data-deficit="${fmtDe(p.deficit, 0)}" data-in-window="${inWindow}" data-day="${p.dayLabel}" style="cursor:pointer"></circle>`;
    });

    // Day change marker at midnight (vertical dotted line + date label above)
    let dayMarkers = "";
    for (let i = 1; i < points.length; i++) {
      if (points[i].dayKey !== points[i - 1].dayKey) {
        const mx = (points[i - 1].x + points[i].x) / 2;
        dayMarkers += `<line x1="${mx}" y1="${padding.top + 4}" x2="${mx}" y2="${padding.top + chartH}" stroke="var(--secondary-text-color)" stroke-opacity="0.35" stroke-width="1" stroke-dasharray="2,3"/>`;
      }
    }

    // X-axis labels (hour + per-day row below)
    let xLabels = "";
    const labelEvery = hours.length > 16 ? 3 : 2;
    points.forEach((p, i) => {
      if (i % labelEvery === 0) {
        xLabels += `<text x="${p.x}" y="${padding.top + chartH + 14}" text-anchor="middle" font-size="10" fill="var(--secondary-text-color)">${String(p.hour).padStart(2, "0")}:00</text>`;
      }
    });
    // Per-day labels centered under each day's span
    const dayRanges = [];
    let curStart = 0;
    for (let i = 1; i <= points.length; i++) {
      if (i === points.length || points[i].dayKey !== points[curStart].dayKey) {
        dayRanges.push({start: curStart, end: i - 1, label: points[curStart].dayLabel});
        curStart = i;
      }
    }
    dayRanges.forEach(r => {
      const mx = (points[r.start].x + points[r.end].x) / 2;
      xLabels += `<text x="${mx}" y="${padding.top + chartH + 30}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)" font-weight="500">${r.label}</text>`;
    });

    // Y-axis grid
    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = (maxVal * (4 - i) / 4).toFixed(0);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // Y-axis label
    const yLabel = `<text x="14" y="${padding.top + chartH / 2}" text-anchor="middle" font-size="10" fill="var(--secondary-text-color)" transform="rotate(-90,14,${padding.top + chartH / 2})">kWh</text>`;

    // Legend
    let legendHtml = `
      <rect x="${width - 280}" y="6" width="10" height="10" fill="var(--primary-color, #03a9f4)" rx="2"/>
      <text x="${width - 266}" y="14" font-size="11" fill="var(--primary-text-color)">${legendLabel}</text>`;
    if (plan) {
      legendHtml += `
      <rect x="${width - 100}" y="6" width="10" height="10" fill="#4CAF50" rx="2" fill-opacity="0.5"/>
      <text x="${width - 86}" y="14" font-size="11" fill="var(--primary-text-color)">Entladung</text>`;
    }

    const chartTitle = `<div style="font-size:14px;font-weight:500;color:var(--primary-text-color);margin-bottom:4px">Energiebedarf ${displayCommunity} <span style="font-weight:400;font-size:12px;color:var(--secondary-text-color)">(Quelle: PeakShare, ${cacheText})</span></div>`;
    const chartHtml = `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;overflow:visible">${yLines}${yLabel}${areaFill}${windowArea}${dayMarkers}${lineEl}${dots}${xLabels}${legendHtml}</svg>`;
    const tooltipHtml = `<div class="ps-tooltip" style="position:absolute;display:none;pointer-events:none;background:var(--card-background-color,#fff);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:8px;padding:6px 10px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,0.18);transform:translate(-50%,-100%);white-space:nowrap;z-index:10"></div>`;

    return planHtml + `<div class="chart-card ps-chart-card" style="margin-top:4px;position:relative">${chartTitle}${chartHtml}${tooltipHtml}</div>`;
  }

  async _loadMoreActivity() {
    if (this._activityLoadingMore || !this._activityHasMore) return;
    this._activityLoadingMore = true;
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_activity_log",
        offset: this._activityLog.length,
        limit: 100,
      });
      this._activityLog = this._activityLog.concat(result?.entries || []);
      this._activityTotal = result?.total || this._activityTotal;
      this._activityHasMore = result?.has_more || false;
    } catch (e) {
      console.error("Failed to load more activity:", e);
    }
    this._activityLoadingMore = false;
    this._render();
  }

  _subscribeActivityEvents() {
    // Clean up stale subscription first
    if (this._activityUnsub) {
      try { this._activityUnsub(); } catch (_) { /* already gone */ }
      this._activityUnsub = null;
    }
    if (!this._hass?.connection) return;
    try {
      this._hass.connection.subscribeEvents((ev) => {
        try {
          if (ev.data) {
            // Prepend new event (newest first)
            this._activityLog.unshift(ev.data);
            this._activityTotal += 1;
            this._render();
          }
        } catch (err) {
          console.warn("EEG: error in activity event handler:", err);
        }
      }, "eeg_optimizer_activity").then(unsub => {
        this._activityUnsub = unsub;
      }).catch((err) => {
        console.warn("EEG: activity subscription failed, will retry on next hass update:", err);
        this._activityUnsub = null;
      });
    } catch (err) {
      console.warn("EEG: could not subscribe to activity events:", err);
      this._activityUnsub = null;
    }
  }

  /* ── Async data loading ───────────────────────── */

  async _checkPrerequisites() {
    this._wizardLoading = true;
    this._render();
    try {
      this._prerequisites = await this._hass.callWS({
        type: "eeg_optimizer/check_prerequisites",
      });
    } catch (err) {
      console.error("Failed to check prerequisites:", err);
      this._prerequisites = {
        huawei_solar: false,
        solcast_solar: false,
        forecast_solar: false,
      };
    }
    // Auto-select inverter type: first detected (alphabetically by label)
    const p = this._prerequisites;
    if (p) {
      const detected = [
        p.huawei_solar && { key: "huawei_sun2000", label: "Huawei" },
        p.solax_modbus && { key: "solax_gen4", label: "SolaX" },
        p.solaredge_modbus_multi && { key: "solaredge_storedge", label: "SolarEdge" },
        p.fronius && { key: "fronius_gen24", label: "Fronius" },
      ].filter(Boolean).sort((a, b) => a.label.localeCompare(b.label));
      if (detected.length > 0) {
        this._wizardData.inverter_type = detected[0].key;
      }
      // Auto-select forecast source — always prefer Solcast when installed
      if (p.solcast_solar) {
        this._wizardData.forecast_source = "solcast_solar";
        this._applyForecastDefaults("solcast_solar");
      } else if (p.forecast_solar) {
        this._wizardData.forecast_source = "forecast_solar";
        this._applyForecastDefaults("forecast_solar");
      }
    }

    this._wizardLoading = false;
    this._render();
  }

  async _executeManualAction(actionName, wsPayload) {
    this._manualAction = actionName;
    this._manualResult = null;
    this._render();
    try {
      const result = await this._hass.callWS(wsPayload);
      this._manualResult = result;
    } catch (err) {
      console.error("Manual action failed:", err);
      this._manualResult = {
        success: false,
        error: "Kommunikationsfehler: " + (err.message || err),
      };
    }
    this._manualAction = null;
    this._render();
  }

  async _detectSensors() {
    this._wizardLoading = true;
    this._render();
    try {
      this._detectedSensors = await this._hass.callWS({
        type: "eeg_optimizer/detect_sensors",
      });
      if (this._detectedSensors.detected && this._detectedSensors.sensors) {
        // Pre-fill detected sensors only if user hasn't already chosen values
        const sensors = this._detectedSensors.sensors;
        for (const [key, val] of Object.entries(sensors)) {
          if (!this._wizardData[key]) {
            this._wizardData[key] = val;
          }
        }
        if (
          this._detectedSensors.huawei_device_id &&
          !this._wizardData.huawei_device_id
        ) {
          this._wizardData.huawei_device_id =
            this._detectedSensors.huawei_device_id;
        }
        // SolaX control entity prefix detection
        if (this._detectedSensors.solax_prefix) {
          const solaxKeys = [
            "solax_remotecontrol_power_control",
            "solax_remotecontrol_active_power",
            "solax_remotecontrol_autorepeat_duration",
            "solax_remotecontrol_trigger",
            "solax_selfuse_discharge_min_soc",
          ];
          for (const key of solaxKeys) {
            if (this._detectedSensors[key] && !this._wizardData[key]) {
              this._wizardData[key] = this._detectedSensors[key];
            }
          }
        }
        // SolarEdge control entity detection
        if (this._detectedSensors.solaredge_prefix) {
          const solaredgeKeys = [
            "solaredge_storage_control_mode",
            "solaredge_storage_command_mode",
            "solaredge_storage_charge_limit",
            "solaredge_storage_discharge_limit",
            "solaredge_storage_backup_reserve",
          ];
          for (const key of solaredgeKeys) {
            if (this._detectedSensors[key] && !this._wizardData[key]) {
              this._wizardData[key] = this._detectedSensors[key];
            }
          }
        }
      }
    } catch (err) {
      console.error("Failed to detect sensors:", err);
      this._detectedSensors = { detected: false, sensors: {} };
    }
    this._wizardLoading = false;
    this._render();
  }

  async _ensureEntityPicker() {
    // We use our own autocomplete, no HA component loading needed
    this._entityPickerLoaded = true;
  }

  _applyForecastDefaults(source) {
    if (source === "solcast_solar") {
      // Auto-detect which Solcast naming convention exists
      const states = this._hass?.states || {};
      const pick = (candidates) => candidates.find(id => states[id]) || candidates[0];
      this._wizardData.forecast_remaining_entity =
        pick(SOLCAST_DEFAULTS_CANDIDATES.forecast_remaining_entity);
      this._wizardData.forecast_tomorrow_entity =
        pick(SOLCAST_DEFAULTS_CANDIDATES.forecast_tomorrow_entity);
      // Auto-detect additional Solcast sensors (today + day 3-7)
      const prefix = this._wizardData.forecast_tomorrow_entity.replace(/morgen$/, "");
      // Handle old "fuer_" prefix — tag sensors don't have "fuer_"
      const tagPrefix = prefix.endsWith("fuer_") && !states[prefix + "tag_3"]
        ? prefix.replace(/fuer_$/, "") : prefix;
      const tryFind = (id) => states[id] ? id : "";
      this._wizardData.forecast_today_entity = tryFind(tagPrefix + "heute");
      this._wizardData.forecast_day3_entity = tryFind(tagPrefix + "tag_3");
      this._wizardData.forecast_day4_entity = tryFind(tagPrefix + "tag_4");
      this._wizardData.forecast_day5_entity = tryFind(tagPrefix + "tag_5");
      this._wizardData.forecast_day6_entity = tryFind(tagPrefix + "tag_6");
      this._wizardData.forecast_day7_entity = tryFind(tagPrefix + "tag_7");
    } else {
      this._wizardData.forecast_remaining_entity =
        FORECAST_SOLAR_DEFAULTS.forecast_remaining_entity;
      this._wizardData.forecast_tomorrow_entity =
        FORECAST_SOLAR_DEFAULTS.forecast_tomorrow_entity;
      this._wizardData.forecast_today_entity = "";
      this._wizardData.forecast_day3_entity = "";
      this._wizardData.forecast_day4_entity = "";
      this._wizardData.forecast_day5_entity = "";
      this._wizardData.forecast_day6_entity = "";
      this._wizardData.forecast_day7_entity = "";
    }
  }

  /* ── Hass / panel setters ─────────────────────── */

  set hass(hass) {
    try {
      this._setHassInner(hass);
    } catch (err) {
      console.error("EEG Energy Optimizer: error in set hass():", err);
    }
  }

  _setHassInner(hass) {
    const firstLoad = this._hass === null;
    const oldHass = this._hass;
    this._hass = hass;
    this._lastHassUpdate = Date.now();

    if (firstLoad) {
      this._loadConfigWithRetry();
      return;
    }

    // Detect reconnect: if we lost connection and hass is back, reload
    if (!this._initialized && !this._loadConfigPending) {
      this._loadConfigWithRetry();
      return;
    }

    // Detect connection object change (HA reconnect after network switch)
    if (oldHass && hass && oldHass.connection !== hass.connection) {
      console.info("EEG Energy Optimizer: connection changed (network switch?), reloading");
      this._activityUnsub = null; // old subscription is dead
      this._loadConfigPending = false;
      this._loadConfigWithRetry();
      return;
    }

    // Recover silently-dead activity subscription
    if (this._setupComplete && !this._activityUnsub && this._initialized) {
      console.info("EEG Energy Optimizer: activity subscription missing, re-subscribing");
      this._subscribeActivityEvents();
    }

    // Update entity pickers in shadow DOM with new hass
    if (this._view === "wizard") {
      const pickers = this._shadow.querySelectorAll("ha-entity-picker");
      pickers.forEach((p) => (p.hass = hass));
    }

    // Recover from blank panel (View Transition may wipe or corrupt shadow DOM)
    // Check for the .content div — every successful render produces one.
    if (this._initialized && this._shadow) {
      if (!this._shadow.querySelector(".content")) {
        this._render();
        return;
      }
    }

    // Selective re-render for dashboard: only if watched entities changed
    if (oldHass && this._view === "dashboard") {
      let changed = false;
      const watchList = [...(this._watchedEntities || DEFAULT_WATCHED)];
      if (this._config?.battery_soc_sensor) watchList.push(this._config.battery_soc_sensor);
      watchList.push("sensor.eeg_energy_optimizer_pv_leistung");
      watchList.push("sensor.eeg_energy_optimizer_batterieleistung");
      watchList.push("sensor.eeg_energy_optimizer_netzleistung");
      watchList.push("sensor.eeg_energy_optimizer_hausverbrauch");
      // Watch Solcast/Forecast.Solar original sensors for PV chart updates
      const fTomorrow = this._config?.forecast_tomorrow_entity;
      if (fTomorrow && fTomorrow.includes("solcast")) {
        const pfx = fTomorrow.replace(/morgen$/, "");
        ["heute", "morgen", "tag_3", "tag_4", "tag_5", "tag_6", "tag_7"].forEach(s => watchList.push(pfx + s));
      } else if (fTomorrow && fTomorrow.includes("energy_production")) {
        const pfx = fTomorrow.replace(/tomorrow$/, "");
        ["today", "tomorrow"].forEach(s => watchList.push(pfx + s));
      }
      for (const eid of watchList) {
        if (oldHass.states[eid] !== hass.states[eid]) {
          changed = true;
          break;
        }
      }
      if (changed) {
        // Reload feed-in stats periodically (at most every 60s)
        const now = Date.now();
        if (!this._lastFeedinReload || now - this._lastFeedinReload > 60000) {
          this._lastFeedinReload = now;
          this._loadFeedinStats();
        }
        this._render();
      }
    }
  }

  set panel(panel) {
    this._panel = panel;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._render();
  }

  async _loadConfigWithRetry(attempt = 0) {
    if (this._loadConfigPending) return;
    this._loadConfigPending = true;
    try {
      await this._loadConfig();
    } catch (_) {
      // Retry up to 5 times with increasing delay (2s, 4s, 6s, 8s, 10s)
      if (attempt < 5) {
        this._loadConfigPending = false;
        const delay = (attempt + 1) * 2000;
        console.warn(`EEG Energy Optimizer: config load failed, retry ${attempt + 1}/5 in ${delay}ms`);
        setTimeout(() => this._loadConfigWithRetry(attempt + 1), delay);
        return;
      }
      console.error("EEG Energy Optimizer: config load failed after 5 retries");
    }
    this._loadConfigPending = false;
  }

  async _loadConfig() {
    try {
      const result = await this._hass.callWS({
        type: "eeg_optimizer/get_config",
      });
      this._config = result;
      this._setupComplete = !!result.setup_complete;
      this._resolveEntityIds();
    } catch (err) {
      if (err.code === "not_configured") {
        this._setupComplete = false;
      } else {
        // Connection error — rethrow so retry logic kicks in
        throw err;
      }
      this._config = null;
    }
    // Load test overrides state
    if (this._setupComplete) {
      try {
        const ovRes = await this._hass.callWS({ type: "eeg_optimizer/get_test_overrides" });
        if (ovRes.overrides) {
          this._simFactor = ovRes.overrides.consumption_factor || 1.0;
          this._simSocOverride = ovRes.overrides.soc_override ?? null;
          this._simSocEnabled = this._simSocOverride !== null;
          this._simActive = true;
        }
      } catch (_) { /* ignore */ }

      // Telemetrie-Status laden (Community-Statistik). Fire-and-forget — Fehler dürfen
      // den Settings-Load nicht blockieren.
      this._hass.callWS({ type: "eeg_optimizer/telemetry_get_status" })
        .then(s => { this._telemetryStatus = s; this._render(); })
        .catch(err => {
          console.warn("EEG Optimizer: telemetry status load failed", err);
          this._telemetryStatus = { configured: false, enabled: false, registered: false };
          this._render();
        });
    }

    this._initialized = true;
    this._render();

    // Load activity log, feed-in stats, and subscribe to live events
    if (this._setupComplete) {
      this._loadActivityLog();
      this._loadFeedinStats();
      // Re-subscribe if previous subscription was lost (e.g. after reconnect)
      if (!this._activityUnsub) {
        this._subscribeActivityEvents();
      }
    }
  }

  _resolveEntityIds() {
    const entryId = this._config?.entry_id;
    if (!entryId) return;

    // Build entity IDs from the unique_id pattern used in sensor.py
    // unique_id = f"eeg_energy_optimizer_{entry_id}_{suffix}"
    // HA entity registry maps unique_id -> entity_id
    const domain = "eeg_energy_optimizer";
    this._entityIds = {};

    for (const [key, suffix] of Object.entries(SENSOR_SUFFIXES)) {
      // Try exact match first (works for first installation)
      const defaultId = `sensor.${domain}_${suffix}`;
      const state = this._hass?.states?.[defaultId];
      if (state) {
        this._entityIds[key] = defaultId;
      } else {
        // Fallback: search all states for matching entity
        const pattern = `sensor.${domain}_${suffix}`;
        const found = Object.keys(this._hass?.states || {}).find(
          eid => eid === pattern || eid.startsWith(pattern + "_")
        );
        this._entityIds[key] = found || defaultId;
      }
    }

    // Select entity
    const selectDefault = `select.${domain}_${SELECT_SUFFIX}`;
    const selectFound = Object.keys(this._hass?.states || {}).find(
      eid => eid === selectDefault || eid.startsWith(selectDefault + "_")
    );
    this._entityIds.select = selectFound || selectDefault;

    // Build watched list for state subscriptions
    this._watchedEntities = [
      this._entityIds.select,
      ...Object.values(this._entityIds).filter(id => id.startsWith("sensor."))
    ];
  }

  /* ── Entity picker helper ─────────────────────── */

  _entityPickerHtml(field, value, label, helpText, domain) {
    // Show current sensor value if entity exists in HA
    let valuePreview = "";
    if (value && this._hass?.states?.[value]) {
      const stateObj = this._hass.states[value];
      const stateVal = stateObj.state;
      const unit = stateObj.attributes?.unit_of_measurement || "";
      const friendly = stateObj.attributes?.friendly_name || "";
      if (stateVal !== "unavailable" && stateVal !== "unknown") {
        valuePreview = `<div class="ep-value-preview" data-preview-for="${field}">Aktuell: <strong>${stateVal}${unit ? " " + unit : ""}</strong>${friendly ? ` — ${friendly}` : ""}</div>`;
      } else {
        valuePreview = `<div class="ep-value-preview unavailable" data-preview-for="${field}">Sensor nicht verfügbar</div>`;
      }
    }
    return `
      <div class="field-group entity-picker-wrap">
        <label>${label}</label>
        <div class="ep-container">
          <input type="text" class="entity-input" data-field="${field}" data-domain="${domain || ""}"
                 value="${value || ""}" placeholder="Tippen zum Suchen..." autocomplete="off">
          <svg class="ep-chevron" viewBox="0 0 24 24" width="20" height="20">
            <path fill="currentColor" d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/>
          </svg>
          <div class="ep-dropdown" data-for="${field}"></div>
        </div>
        ${valuePreview}
        ${helpText ? `<div class="help-text">${helpText}</div>` : ""}
      </div>`;
  }

  /** Bind focus/input events to entity picker inputs for custom dropdown. */
  _bindEntityPickers() {
    if (!this._hass) return;
    const inputs = this._shadow.querySelectorAll("input.entity-input");
    inputs.forEach((input) => {
      const domain = input.dataset.domain;
      const field = input.dataset.field;
      const dropdown = this._shadow.querySelector(`.ep-dropdown[data-for="${field}"]`);
      if (!dropdown) return;

      const states = this._hass.states || {};
      const allEntities = Object.keys(states)
        .filter((eid) => !domain || eid.startsWith(domain + "."))
        .sort()
        .map((eid) => ({
          id: eid,
          name: states[eid]?.attributes?.friendly_name || "",
        }));

      const showDropdown = (filter) => {
        const q = (filter || "").toLowerCase();
        const matches = allEntities
          .filter((e) => !q || e.id.includes(q) || e.name.toLowerCase().includes(q))
          .slice(0, 50);
        if (matches.length === 0) {
          dropdown.style.display = "none";
          return;
        }
        dropdown.innerHTML = matches
          .map((e) => `<div class="ep-option" data-value="${e.id}">
            <span class="ep-name">${e.name || e.id}</span>
            <span class="ep-id">${e.id}</span>
          </div>`)
          .join("");
        dropdown.style.display = "block";
      };

      input.addEventListener("focus", () => showDropdown(input.value));
      input.addEventListener("input", () => {
        this._wizardData[field] = input.value;
        showDropdown(input.value);
      });

      const updatePreview = (entityId) => {
        const preview = this._shadow.querySelector(`.ep-value-preview[data-preview-for="${field}"]`);
        const stateObj = entityId && states[entityId];
        if (stateObj) {
          const sv = stateObj.state;
          const unit = stateObj.attributes?.unit_of_measurement || "";
          const friendly = stateObj.attributes?.friendly_name || "";
          const unavail = sv === "unavailable" || sv === "unknown";
          if (!preview) {
            // Insert preview after ep-container
            const container = input.closest(".ep-container");
            const div = document.createElement("div");
            div.className = "ep-value-preview" + (unavail ? " unavailable" : "");
            div.setAttribute("data-preview-for", field);
            div.innerHTML = unavail ? "Sensor nicht verfügbar" : `Aktuell: <strong>${sv}${unit ? " " + unit : ""}</strong>${friendly ? ` — ${friendly}` : ""}`;
            container.parentNode.insertBefore(div, container.nextSibling);
          } else {
            preview.className = "ep-value-preview" + (unavail ? " unavailable" : "");
            preview.innerHTML = unavail ? "Sensor nicht verfügbar" : `Aktuell: <strong>${sv}${unit ? " " + unit : ""}</strong>${friendly ? ` — ${friendly}` : ""}`;
          }
        } else if (preview) {
          preview.remove();
        }
      };

      dropdown.addEventListener("mousedown", (ev) => {
        ev.preventDefault(); // Prevent blur before click registers
        const opt = ev.target.closest(".ep-option");
        if (opt) {
          input.value = opt.dataset.value;
          this._wizardData[field] = opt.dataset.value;
          dropdown.style.display = "none";
          updatePreview(opt.dataset.value);
        }
      });

      input.addEventListener("blur", () => {
        setTimeout(() => {
          dropdown.style.display = "none";
          updatePreview(input.value);
        }, 150);
      });
    });
  }

  /* ── Wizard step rendering ────────────────────── */

  _renderWizard() {
    const step = this._wizardStep;
    const isExpert = this._wizardData.expert_mode;
    const total = isExpert ? WIZARD_STEPS.length : WIZARD_STEPS.length - 1;
    // In non-expert mode, step 6 (Zusammenfassung) becomes display-step 5
    const displayStep = (!isExpert && step > 5) ? step - 1 : step;
    const progress = ((displayStep + 1) / total) * 100;

    let stepContent = "";
    switch (step) {
      case 0:
        stepContent = this._renderStep0();
        break;
      case 1:
        stepContent = this._renderStep1();
        break;
      case 2:
        stepContent = this._renderStep2();
        break;
      case 3:
        stepContent = this._renderStep3();
        break;
      case 4:
        stepContent = this._renderStep4();
        break;
      case 5:
        stepContent = this._renderStep5();
        break;
      case 6:
        stepContent = this._renderStep6();
        break;
    }

    const backBtn =
      step > 0
        ? `<button class="btn-secondary" data-action="prev-step">Zurück</button>`
        : `<div></div>`;

    let forwardBtn = "";
    if (step === WIZARD_STEPS.length - 1) {
      forwardBtn = `<button class="btn-primary" data-action="finish-wizard"${
        this._wizardLoading ? " disabled" : ""
      }>Fertig</button>`;
    } else {
      const probing = !!this._froniusProbing;
      const disabled = (this._isNextDisabled() || probing) ? " btn-disabled" : "";
      const label = probing ? "Prüfe Fronius-Verbindung…" : "Weiter";
      forwardBtn = `<button class="btn-primary${disabled}" data-action="next-step">${label}</button>`;
    }

    return `
      <div class="step-indicator">
        <span>Schritt ${displayStep + 1} von ${total} — ${WIZARD_STEPS[step]}</span>
        <label class="expert-toggle">
          <input type="checkbox" data-field="expert_mode"
                 ${this._wizardData.expert_mode ? "checked" : ""}>
          <span>Expertenmodus</span>
        </label>
      </div>
      <div class="progress-bar">
        <div class="progress-bar-fill" style="width:${progress}%"></div>
      </div>
      <div class="card">
        <h2>${WIZARD_STEPS[step]}</h2>
        ${this._wizardLoading ? '<div class="loading">Laden...</div>' : stepContent}
        <div class="wizard-nav">
          ${backBtn}
          ${forwardBtn}
        </div>
      </div>`;
  }

  _isNextDisabled() {
    const step = this._wizardStep;
    // Step 1: block if no supported inverter installed or Hausverbrauch sensors missing
    if (step === 1) {
      const p = this._prerequisites;
      if (p && !p.huawei_solar && !p.solax_modbus && !p.solaredge_modbus_multi && !p.fronius) return true;
      const d = this._wizardData;
      if (!d.inverter_type) return true;
      if (!d.pv_power_sensor) return true;
      // Fronius requires the directional pair (charge/discharge, export/import).
      // Other inverters use a single signed sensor each.
      if (d.inverter_type === "fronius_gen24") {
        if (!d.battery_power_charge_sensor || !d.battery_power_discharge_sensor) return true;
        if (!d.grid_power_export_sensor || !d.grid_power_import_sensor) return true;
      } else {
        if (!d.battery_power_sensor || !d.grid_power_sensor) return true;
      }
    }
    // Step 2: block if no forecast integration
    if (
      step === 2 &&
      this._prerequisites &&
      !this._prerequisites.solcast_solar &&
      !this._prerequisites.forecast_solar
    ) {
      return true;
    }
    return false;
  }

  /* ── Step 0: Willkommen ───────────────────────── */

  _renderStep0() {
    return `
      <div style="text-align:center;margin-bottom:20px">
        <img src="/eeg_optimizer_panel/logo.png" alt="EEG Energy Optimizer" style="max-width:180px;height:auto">
      </div>
      <p style="line-height:1.6;margin-bottom:20px">
        Diese Home Assistant Integration optimiert deine Hausbatterie für die Energiegemeinschaft (EEG).
        Morgens wird die Batterieladung blockiert, damit Solarstrom direkt ins Netz der Energiegemeinschaft fließt.
        Abends wird die Batterie ins Netz entladen — jedoch nur soweit, dass der Eigenverbrauch mit der Restladung der Batterie gesichert ist.
      </p>
      <h3 style="margin-bottom:8px">Was du brauchst</h3>
      <ul style="line-height:1.8;margin-bottom:20px;padding-left:20px">
        <li>Einen unterstützten Wechselrichter mit Batteriespeicher</li>
        <li>Eine PV-Prognose-Integration (Solcast Solar oder Forecast.Solar)</li>
      </ul>
      <h3 style="margin-bottom:8px">Getestete Setups</h3>
      <ul style="line-height:1.8;padding-left:20px">
        <li>Huawei SUN2000 mit LUNA2000 Batteriespeicher</li>
        <li>SolaX Gen4+ mit Triple Power Batteriespeicher</li>
        <li>SolarEdge mit StorEdge Batteriespeicher (LG RESU, BYD, Energy Bank)</li>
        <li>Fronius Gen24 mit BYD Batteriespeicher</li>
      </ul>`;
  }

  /* ── Step 1: Wechselrichter-Typ ───────────────── */

  _renderStep1() {
    const p = this._prerequisites;
    const huaweiOk = p && p.huawei_solar;
    const solaxOk = p && p.solax_modbus;
    const solaredgeOk = p && p.solaredge_modbus_multi;
    const froniusOk = p && p.fronius;
    const selected = this._wizardData.inverter_type || "";
    const huaweiSelected = selected === "huawei_sun2000";
    const solaxSelected = selected === "solax_gen4";
    const solaredgeSelected = selected === "solaredge_storedge";
    const froniusSelected = selected === "fronius_gen24";

    const huaweiBadge = huaweiOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const solaxBadge = solaxOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const solaredgeBadge = solaredgeOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const froniusBadge = froniusOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const huaweiAutoDetect = "";

    const pvHelp = huaweiSelected
      ? "Aktuelle PV-Produktion in W oder kW (Huawei: sensor.inverter_eingangsleistung)."
      : solaredgeSelected
      ? "Aktuelle PV-Produktion in W (SolarEdge: sensor.solaredge_[i1_]ac_power)."
      : froniusSelected
      ? "Aktuelle PV-Produktion in W (Fronius: sensor.*_power_photovoltaics oder *_pv_leistung)."
      : "Aktuelle PV-Produktion in W (SolaX: sensor.solax_energy_dashboard_solax_solar_power).";
    const batteryHelp = huaweiSelected
      ? "Lade- und Entladeleistung der Batterie in W oder kW (Huawei: sensor.batteries_lade_entladeleistung)."
      : solaredgeSelected
      ? "Lade- und Entladeleistung der Batterie in W (SolarEdge: sensor.solaredge_[i1_]b1_dc_power)."
      : froniusSelected
      ? "Lade- und Entladeleistung der Batterie in W (Fronius: sensor.*_power_battery oder *_leistung_batterie). Bei Fronius-Installationen mit getrennten Lade-/Entladesensoren bitte den signed Sensor wählen."
      : "Lade- und Entladeleistung der Batterie in W (SolaX: sensor.solax_energy_dashboard_solax_battery_power).";
    const gridHelp = huaweiSelected
      ? "Wirkleistung am Netzanschluss in W oder kW (Huawei: sensor.power_meter_wirkleistung)."
      : solaredgeSelected
      ? "Wirkleistung am Netzanschluss in W (SolarEdge: sensor.solaredge_[i1_]m1_ac_power)."
      : froniusSelected
      ? "Wirkleistung am Netzanschluss in W (Fronius: sensor.*_power_grid oder *_leistung_netz). Bei Fronius-Installationen mit getrennten Bezugs-/Einspeisesensoren bitte den signed Sensor wählen."
      : "Wirkleistung am Netzanschluss in W (SolaX: sensor.solax_energy_dashboard_solax_grid_power).";

    // Build inverter cards, sort: detected first (alphabetically), then undetected (alphabetically)
    const inverterDefs = [
      { key: "huawei_sun2000", label: "Huawei SUN2000", subtitle: "", detected: huaweiOk, badge: huaweiBadge, dialog: "huawei",
        logo: `<img src="https://brands.home-assistant.io/huawei_solar/logo.png" alt="Huawei" style="max-width:120px;max-height:60px;height:auto" onerror="this.style.display='none'">` },
      { key: "solax_gen4", label: "SolaX Gen4+", subtitle: "Gen4, Gen5, Gen6", detected: solaxOk, badge: solaxBadge, dialog: "solax",
        logo: `<span style="font-size:32px">SolaX</span>` },
      { key: "solaredge_storedge", label: "SolarEdge", subtitle: "StorEdge Batteriespeicher", detected: solaredgeOk, badge: solaredgeBadge, dialog: "solaredge",
        logo: `<img src="https://brands.home-assistant.io/_/solaredge/logo.png" alt="SolarEdge" style="max-width:120px;max-height:60px;height:auto" onerror="this.outerHTML='<span style=font-size:32px>SolarEdge</span>'">` },
      { key: "fronius_gen24", label: "Fronius Gen24", subtitle: "mit BYD Batteriespeicher", detected: froniusOk, badge: froniusBadge, dialog: "fronius",
        logo: `<img src="https://brands.home-assistant.io/fronius/logo.png" alt="Fronius" style="max-width:120px;max-height:60px;height:auto" onerror="this.outerHTML='<span style=font-size:32px>Fronius</span>'">` },
    ];
    inverterDefs.sort((a, b) => {
      if (a.detected !== b.detected) return a.detected ? -1 : 1;
      return a.label.localeCompare(b.label);
    });

    const inverterCards = inverterDefs.map(inv => {
      const isSel = selected === inv.key;
      const sub = inv.subtitle ? `<p style="font-size:11px;color:var(--secondary-text-color);margin:0 0 8px">${inv.subtitle}</p>` : "";
      const guide = inv.dialog ? `<button class="btn-secondary" style="margin-top:8px" data-action="show-dialog" data-dialog="${inv.dialog}">Anleitung</button>` : "";
      return `<div class="card forecast-option ${isSel ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-inverter" data-value="${inv.key}">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">${inv.logo}</div>
          <h3 style="margin:0 0 ${inv.subtitle ? "4px" : "8px"}">${inv.label}</h3>
          ${sub}${inv.badge}${guide}
        </div>`;
    }).join("\n        ");

    return `
      <p style="margin-bottom:12px;color:var(--secondary-text-color)">Wähle deinen Wechselrichter-Typ:</p>
      <div class="prereq-cards" style="display:grid;grid-template-columns:repeat(auto-fit, minmax(150px, 1fr));gap:16px;margin-bottom:16px">
        ${inverterCards}
      </div>
      ${huaweiSelected || solaxSelected || solaredgeSelected || froniusSelected ? `
      <div class="card" style="padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 4px">Hausverbrauch-Sensoren</h3>
        <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 12px">
          Diese Sensoren werden f&uuml;r die Berechnung des Hausverbrauchs verwendet (PV &minus; Batterie &minus; Netz).
        </p>
        ${this._entityPickerHtml(
          "pv_power_sensor",
          this._wizardData.pv_power_sensor,
          "PV-Eingangsleistung *",
          pvHelp,
          "sensor"
        )}
        ${froniusSelected ? `
          <p style="font-size:12px;color:var(--secondary-text-color);margin:8px 0 4px;line-height:1.5">
            Fronius liefert Batterie- und Netzleistung als <strong>zwei getrennte, immer positive Sensoren</strong>
            (Lade-/Entladeleistung bzw. Bezug/Einspeisung). Trage je beide ein &mdash; die Integration kombiniert sie automatisch
            zu signed Werten und legt die kombinierten Sensoren mit Verlaufsdaten an.
          </p>
          ${this._entityPickerHtml(
            "battery_power_charge_sensor",
            this._wizardData.battery_power_charge_sensor,
            "Batterie-Ladeleistung *",
            "Positiver W-Wert beim Laden, 0 sonst (Fronius: sensor.*_battery_power_charging oder *_ladeleistung).",
            "sensor"
          )}
          ${this._entityPickerHtml(
            "battery_power_discharge_sensor",
            this._wizardData.battery_power_discharge_sensor,
            "Batterie-Entladeleistung *",
            "Positiver W-Wert beim Entladen, 0 sonst (Fronius: sensor.*_battery_power_discharging oder *_entladeleistung).",
            "sensor"
          )}
          ${this._entityPickerHtml(
            "grid_power_export_sensor",
            this._wizardData.grid_power_export_sensor,
            "Netzeinspeisung *",
            "Positiver W-Wert bei Einspeisung, 0 sonst (Fronius: sensor.*_leistung_netzeinspeisung).",
            "sensor"
          )}
          ${this._entityPickerHtml(
            "grid_power_import_sensor",
            this._wizardData.grid_power_import_sensor,
            "Netzbezug *",
            "Positiver W-Wert bei Bezug, 0 sonst (Fronius: sensor.*_leistung_netzbezug).",
            "sensor"
          )}
        ` : `
          ${this._entityPickerHtml(
            "battery_power_sensor",
            this._wizardData.battery_power_sensor,
            "Batterie Lade-/Entladeleistung *",
            batteryHelp,
            "sensor"
          )}
          ${this._entityPickerHtml(
            "grid_power_sensor",
            this._wizardData.grid_power_sensor,
            "Netzbezug/-einspeisung *",
            gridHelp,
            "sensor"
          )}
        `}
        ${solaxSelected ? this._entityPickerHtml(
          "pv_power_sensor_2",
          this._wizardData.pv_power_sensor_2,
          "Zweiter PV-Sensor (optional)",
          "Für Anlagen mit Generator-Wechselrichter über Meter 2 (sensor.solax_inverter_meter_2_measured_power).",
          "sensor"
        ) : ""}
      </div>
      ${froniusSelected ? `
      <div class="card" style="padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 4px">Modbus TCP Verbindung</h3>
        <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 12px">
          IP-Adresse und Port f\u00fcr die direkte Modbus-Verbindung zum Wechselrichter (f\u00fcr Batterie-Steuerung).
        </p>
        <div style="margin-bottom:12px">
          <label style="display:block;font-weight:500;margin-bottom:4px">Modbus IP-Adresse *</label>
          <input type="text" value="${this._wizardData.fronius_modbus_host || ""}"
                 data-field="fronius_modbus_host" placeholder="z.B. 192.168.1.100"
                 style="width:100%;padding:8px;border:1px solid var(--divider-color);border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color)">
          <div class="help-text">Die IP-Adresse des Fronius Wechselrichters (gleiche wie im Fronius Web-Interface).</div>
        </div>
        <div style="margin-bottom:12px">
          <label style="display:block;font-weight:500;margin-bottom:4px">Modbus Port</label>
          <input type="number" value="${this._wizardData.fronius_modbus_port || 502}"
                 data-field="fronius_modbus_port" min="1" max="65535"
                 style="width:100%;padding:8px;border:1px solid var(--divider-color);border-radius:4px;background:var(--card-background-color);color:var(--primary-text-color)">
          <div class="help-text">Standard: 502. Manche Installationen nutzen 1502.</div>
        </div>
      </div>` : ""}
      ` : ""}
      <button class="btn-secondary" data-action="recheck-prerequisites">Erneut prüfen</button>`;
  }

  /* ── Step 2: Prognose-Integration ─────────────── */

  _renderStep2() {
    const p = this._prerequisites;
    const solcastOk = p && p.solcast_solar;
    const forecastOk = p && p.forecast_solar;

    const solcastBadge = solcastOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';
    const forecastBadge = forecastOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const selected = this._wizardData.forecast_source || "";
    const solcastSelected = selected === "solcast_solar";
    const forecastSelected = selected === "forecast_solar";

    // Auto-suggest sensor defaults when source is selected
    const allSolcastCandidates = [
      ...SOLCAST_DEFAULTS_CANDIDATES.forecast_remaining_entity,
      ...SOLCAST_DEFAULTS_CANDIDATES.forecast_tomorrow_entity,
    ];
    const isDefaultOrEmpty = !this._wizardData.forecast_remaining_entity
      || allSolcastCandidates.includes(this._wizardData.forecast_remaining_entity)
      || this._wizardData.forecast_remaining_entity === FORECAST_SOLAR_DEFAULTS.forecast_remaining_entity;
    if (selected && isDefaultOrEmpty) {
      this._applyForecastDefaults(selected);
    }

    // Sensor fields shown below cards when a source is selected
    const solcastRemainingHint = "Verbleibende PV-Produktion f\u00fcr den heutigen Tag in kWh. "
      + "Solcast-Sensornamen variieren je nach Version, z.B.: "
      + "sensor.solcast_pv_forecast_prognose_verbleibende_leistung_heute oder "
      + "sensor.solcast_pv_forecast_prognose_fuer_heute.";
    const solcastTomorrowHint = "Prognostizierte PV-Produktion f\u00fcr morgen in kWh. "
      + "Solcast-Sensornamen variieren je nach Version, z.B.: "
      + "sensor.solcast_pv_forecast_prognose_morgen oder "
      + "sensor.solcast_pv_forecast_prognose_fuer_morgen.";
    const sensorFields = selected ? `
      <div style="margin-top:16px">
        ${this._entityPickerHtml(
          "forecast_remaining_entity",
          this._wizardData.forecast_remaining_entity,
          "Sensor f\u00fcr PV-Prognose verbleibend heute *",
          solcastSelected
            ? solcastRemainingHint
            : "Verbleibende PV-Produktion f\u00fcr den heutigen Tag in kWh (Forecast.Solar: sensor.energy_production_today_remaining).",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_tomorrow_entity",
          this._wizardData.forecast_tomorrow_entity,
          "Sensor f\u00fcr PV-Prognose morgen *",
          solcastSelected
            ? solcastTomorrowHint
            : "Prognostizierte PV-Produktion f\u00fcr morgen in kWh (Forecast.Solar: sensor.energy_production_tomorrow).",
          "sensor"
        )}
      </div>` : "";

    return `
      <p style="margin-bottom:12px;color:var(--secondary-text-color)">Wähle deine PV-Prognose-Quelle:</p>
      <div class="prereq-cards" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div class="card forecast-option ${solcastSelected ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-forecast" data-value="solcast_solar">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">
            <img src="https://brands.home-assistant.io/solcast_solar/logo.png" alt="Solcast" style="max-width:100px;max-height:60px;height:auto" onerror="this.style.display='none'">
          </div>
          <h3 style="margin:0 0 8px">Solcast Solar (empfohlen)</h3>
          ${solcastBadge}
          <p style="font-size:13px;color:var(--secondary-text-color);margin:8px 0">Genauere Prognosen, kostenloser API-Key erforderlich.</p>
          <button class="btn-secondary" data-action="show-dialog" data-dialog="solcast">Anleitung</button>
        </div>
        <div class="card forecast-option ${forecastSelected ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-forecast" data-value="forecast_solar">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">
            <img src="https://brands.home-assistant.io/forecast_solar/logo.png" alt="Forecast.Solar" style="max-width:100px;max-height:60px;height:auto" onerror="this.style.display='none'">
          </div>
          <h3 style="margin:0 0 8px">Forecast.Solar</h3>
          ${forecastBadge}
          <p style="font-size:13px;color:var(--secondary-text-color);margin:8px 0">Einfachere Einrichtung, keine Registrierung n\u00f6tig.</p>
          <button class="btn-secondary" data-action="show-dialog" data-dialog="forecast_solar">Anleitung</button>
        </div>
      </div>
      <button class="btn-secondary" data-action="recheck-prerequisites">Erneut pr\u00fcfen</button>
      ${sensorFields}
      ${selected && this._wizardData.expert_mode && solcastSelected ? `
      <div style="margin-top:16px">
        <h3 style="margin:0 0 12px;font-size:15px">Weitere Prognose-Sensoren (optional)</h3>
        <p style="font-size:13px;color:var(--secondary-text-color);margin-bottom:12px">
          Diese Sensoren werden automatisch erkannt. Nur \u00e4ndern wenn die Auto-Erkennung nicht funktioniert.
        </p>
        ${this._entityPickerHtml(
          "forecast_today_entity",
          this._wizardData.forecast_today_entity,
          "PV-Prognose heute (gesamt)",
          "Gesamte PV-Produktion f\u00fcr heute in kWh, z.B. sensor.solcast_pv_forecast_prognose_heute.",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_day3_entity",
          this._wizardData.forecast_day3_entity,
          "PV-Prognose Tag 3",
          "z.B. sensor.solcast_pv_forecast_prognose_tag_3",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_day4_entity",
          this._wizardData.forecast_day4_entity,
          "PV-Prognose Tag 4",
          "z.B. sensor.solcast_pv_forecast_prognose_tag_4",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_day5_entity",
          this._wizardData.forecast_day5_entity,
          "PV-Prognose Tag 5",
          "z.B. sensor.solcast_pv_forecast_prognose_tag_5",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_day6_entity",
          this._wizardData.forecast_day6_entity,
          "PV-Prognose Tag 6",
          "z.B. sensor.solcast_pv_forecast_prognose_tag_6",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_day7_entity",
          this._wizardData.forecast_day7_entity,
          "PV-Prognose Tag 7",
          "z.B. sensor.solcast_pv_forecast_prognose_tag_7",
          "sensor"
        )}
      </div>` : ""}`;
  }

  /* ── Step 3: Batteriesensoren ───────────── */

  _renderStep3() {
    const detected = this._detectedSensors && this._detectedSensors.detected;

    let detectionInfo = "";

    const socHelp =
      "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent.";

    // Auto-select capacity mode: if sensor was detected, pick "sensor"; else "manual"
    // Re-evaluate after detection (don't cache stale pre-detection default)
    // SolaX has no capacity sensor — always default to manual
    if (this._wizardData.inverter_type === "solax_gen4" && !this._capacityModeUserSet) {
      this._capacityMode = "manual";
    } else if (!this._capacityMode || (detected && !this._capacityModeUserSet)) {
      this._capacityMode = this._wizardData.battery_capacity_sensor ? "sensor" : "manual";
    }
    const capSensor = this._capacityMode === "sensor";

    const capSensorHtml = capSensor ? this._entityPickerHtml(
      "battery_capacity_sensor",
      this._wizardData.battery_capacity_sensor,
      "Sensor für Batteriekapazität",
      this._wizardData.inverter_type === "huawei_sun2000"
        ? "Gesamtkapazität der Batterie in kWh oder Wh (Huawei: sensor.batterien_akkukapazitat)."
        : "Gesamtkapazität der Batterie in kWh oder Wh.",
      "sensor"
    ) : "";

    const capManualHtml = !capSensor ? `
      <div class="field-group">
        <label>Batteriekapazität (in kWh)</label>
        <input type="number" data-field="battery_capacity_kwh"
               value="${this._wizardData.battery_capacity_kwh || ""}"
               min="1" max="100" step="0.5"
               placeholder="z.B. 10">
        <div class="help-text">${this._wizardData.inverter_type === "huawei_sun2000"
          ? "z.B. 10 für LUNA2000-10, 15 für LUNA2000-15"
          : this._wizardData.inverter_type === "solax_gen4"
          ? "z.B. 5.8 für Triple Power T58, 11.6 für zwei Module"
          : this._wizardData.inverter_type === "solaredge_storedge"
          ? "z.B. 9.8 für LG RESU10H, 4.8 für BYD LVS 4.0"
          : "Nutzbare Gesamtkapazität deines Batteriespeichers in kWh"}</div>
      </div>` : "";

    return `
      ${detectionInfo}
      ${this._entityPickerHtml(
        "battery_soc_sensor",
        this._wizardData.battery_soc_sensor,
        "Sensor für Batterieladezustand (SOC) *",
        this._wizardData.inverter_type === "huawei_sun2000"
          ? "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent (Huawei: sensor.batteries_batterieladung)."
          : "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent.",
        "sensor"
      )}
      <div class="field-group">
        <label>Batteriekapazität *</label>
        <div class="cap-mode-cards">
          <div class="cap-mode-card ${!capSensor ? "selected" : ""}" data-action="set-cap-mode-card" data-value="manual">
            <ha-icon icon="mdi:pencil-box-outline"></ha-icon>
            <span>Manuell eingeben</span>
          </div>
          <div class="cap-mode-card ${capSensor ? "selected" : ""}" data-action="set-cap-mode-card" data-value="sensor">
            <ha-icon icon="mdi:auto-fix"></ha-icon>
            <span>Über Sensor</span>
          </div>
        </div>
        ${capSensor && this._wizardData.inverter_type === "huawei_sun2000" ? `<div class="help-text" style="margin-top:8px;margin-bottom:8px">
          Bei Huawei ist der Kapazitätssensor standardmäßig deaktiviert.
          <button class="btn-link" data-action="show-dialog" data-dialog="capacity_sensor">Anleitung zur Aktivierung</button>
        </div>` : ""}
      </div>
      ${capSensorHtml}
      ${capManualHtml}`;
  }

  /* ── Step 4: Ladung & Einspeisung ────────────── */

  _renderStep4() {
    const mDelay = this._wizardData.enable_morning_delay;
    const nDischarge = this._wizardData.enable_night_discharge;

    const isExpert = this._wizardData.expert_mode;
    const morningFields = mDelay ? `
      <div class="feature-params">
        <div class="field-group">
          <label>Vorlaufzeit vor Sonnenaufgang (Std.)</label>
          <input type="number" data-field="morning_start_offset"
                 value="${this._wizardData.morning_start_offset ?? 0}"
                 min="0" max="3" step="0.5" style="width:80px">
          <div class="help-text">So viele Stunden vor Sonnenaufgang beginnt die Ladeblockierung. 0 = ab Sonnenaufgang.</div>
        </div>
        <div class="field-group">
          <label>Batterieladung blockiert bis maximal</label>
          <input type="text" data-field="morning_end_time" placeholder="HH:MM" pattern="[0-2][0-9]:[0-5][0-9]" maxlength="5"
                 value="${this._wizardData.morning_end_time}" style="width:80px">
          <div class="help-text">Maximal bis zu dieser Uhrzeit wird die Batterieladung morgens blockiert, damit der Strom stattdessen ins Netz eingespeist wird.</div>
        </div>
      </div>` : "";

    const peakshare = this._wizardData.enable_peakshare !== false;
    const peakshareCommunitiesHtml = (() => {
      const communities = this._peakshareCommunitiesCache || [];
      const selected = this._wizardData.peakshare_community || "BEG";
      if (communities.length === 0) return `<div class="help-text" style="margin-top:4px">Communities werden geladen...</div>`;
      const opts = communities.map(c => `<option value="${c}" ${c === selected ? "selected" : ""}>${c}</option>`).join("");
      return `<div class="field-group">
          <label>Deine Energiegemeinschaft</label>
          <select data-field="peakshare_community">${opts}</select>
          <div class="help-text">W\u00e4hle die Energiegemeinschaft, nach deren Bedarf der Entladezeitpunkt optimiert wird.</div>
        </div>`;
    })();

    const dischargeFields = nDischarge ? `
      <div class="feature-params">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:12px">
          <input type="checkbox" data-field="enable_peakshare" ${peakshare ? "checked" : ""}>
          <div>
            <div style="font-weight:500">PeakShare-Bedarfssteuerung</div>
            <div class="help-text" style="margin-top:2px">Entladezeitpunkt wird automatisch nach dem Bedarf der Energiegemeinschaft optimiert.</div>
          </div>
        </label>
        ${peakshare ? peakshareCommunitiesHtml : ""}
        <div class="field-group">
          <label>Frühester Entladestart</label>
          <input type="text" data-field="discharge_start_time" placeholder="HH:MM" pattern="[0-2][0-9]:[0-5][0-9]" maxlength="5"
                 value="${this._wizardData.discharge_start_time}" style="width:80px">
          <div class="help-text">${peakshare
            ? "Untergrenze für das automatisch berechnete Fenster — PeakShare darf später starten, aber nie früher. Empfehlung 01:00: je später der Start, desto präziser die Verbrauchsprognose und desto mehr wird eingespeist."
            : "Genauer Startzeitpunkt der Entladung. Empfehlung 01:00: je später der Start, desto präziser die Verbrauchsprognose und desto mehr wird eingespeist."}</div>
        </div>
        <div class="field-group">
          <label>Entladeleistung (kW)</label>
          <input type="number" data-field="discharge_power_kw"
                 value="${this._wizardData.discharge_power_kw}"
                 min="${this._wizardData.inverter_type === "solaredge_storedge" ? "5.0" : "0.5"}" max="10.0" step="0.5">
          <div class="help-text">Leistung der Batterieentladung ins Netz.${peakshare ? " Bestimmt die Dauer des Entladefensters (Energie \u00f7 Leistung)." : ""}${this._wizardData.inverter_type === "solaredge_storedge" ? " Bei SolarEdge min. 5 kW." : ""}</div>
        </div>
        <div class="field-group">
          <label>Minimaler Ladezustand (%)</label>
          <input type="number" data-field="min_soc"
                 value="${this._wizardData.min_soc}"
                 min="5" max="50">
          <div class="help-text">Die Einspeisung erfolgt nicht bis zu diesem Ladestand, sondern sorgt daf\u00fcr, dass dieser Ladestand + der durchschnittliche Verbrauch in der Nacht + Sicherheitspuffer in der Batterie bleibt.</div>
        </div>
      </div>` : "";

    return `
      <p style="margin-bottom:16px;color:var(--secondary-text-color)">
        Klicke auf eine Karte, um die jeweilige Optimierung ein- oder auszuschalten. Beide k\u00f6nnen unabh\u00e4ngig voneinander aktiviert werden.
      </p>
      <div class="feature-toggle">
        <div class="feature-card ${mDelay ? "selected" : ""}" data-action="toggle-feature" data-feature="enable_morning_delay" style="cursor:pointer">
          <div class="feature-card-header">
            <ha-icon icon="mdi:weather-sunset-up"></ha-icon>
            <div class="feature-card-text">
              <span class="feature-title">Morgen-Einspeisung</span>
              <span class="feature-desc">Morgens wird die Batterie nicht sofort geladen, sondern die Energie direkt ins Netz und die EEG eingespeist \u2014 dort, wo sie zu dieser Zeit am dringendsten gebraucht wird. Das geschieht jedoch nur, wenn die PV-Prognose f\u00fcr den heutigen Tag im Verh\u00e4ltnis zum Verbrauch gut genug ist, damit die Batterie im Laufe des Tages sicher wieder vollgeladen wird.</span>
            </div>
            <div class="feature-badge ${mDelay ? "on" : "off"}">${mDelay ? "Aktiv" : "Aus"}</div>
          </div>
          <div style="text-align:center;font-size:12px;color:var(--secondary-text-color);margin-top:4px">Zum ${mDelay ? "Deaktivieren" : "Aktivieren"} hier klicken</div>
        </div>
        ${morningFields}
      </div>

      <div class="feature-toggle" style="margin-top:16px">
        <div class="feature-card ${nDischarge ? "selected" : ""}" data-action="toggle-feature" data-feature="enable_night_discharge" style="cursor:pointer">
          <div class="feature-card-header">
            <ha-icon icon="mdi:battery-arrow-down-outline"></ha-icon>
            <div class="feature-card-text">
              <span class="feature-title">Abend-Entladung</span>
              <span class="feature-desc">Abends wird \u00fcbersch\u00fcssige Energie aus der Batterie ins Netz entladen. Jedoch nur wenn die Prognose des morgigen Tags so gut ist, dass die Batterie morgen wieder vollgeladen werden kann. Und nur so viel, dass man die Nacht auf Basis der bekannten Verbrauchsdaten trotzdem mit dem eigenen Strom auskommt.</span>
            </div>
            <div class="feature-badge ${nDischarge ? "on" : "off"}">${nDischarge ? "Aktiv" : "Aus"}</div>
          </div>
          <div style="text-align:center;font-size:12px;color:var(--secondary-text-color);margin-top:4px">Zum ${nDischarge ? "Deaktivieren" : "Aktivieren"} hier klicken</div>
        </div>
        ${dischargeFields}
      </div>

      ${isExpert ? `<div style="margin-top:24px">
        <h3 style="margin:0 0 12px;font-size:16px">Allgemeine Einstellungen</h3>
        <div class="field-group">
          <label>Sicherheitspuffer (%)</label>
          <input type="number" data-field="safety_buffer_pct"
                 value="${this._wizardData.safety_buffer_pct}"
                 min="0" max="100" step="5">
          <div class="help-text">Aufschlag auf den berechneten Energiebedarf. Gilt für beide Optimierungen — sorgt dafür, dass immer eine Reserve eingeplant wird.</div>
        </div>
      </div>` : ""}`;
  }

  /* ── Step 5: Erweiterte Einstellungen ────────── */

  _renderStep5() {
    return `
      <div class="field-group">
        <label>Anzahl der Wochen für den Verbrauchsdurchschnitt</label>
        <input type="number" data-field="lookback_weeks"
               value="${this._wizardData.lookback_weeks}"
               min="1" max="52">
        <div class="help-text">Legt die Anzahl an Wochen fest, die wir im durchschnittlichen Verbrauchswert pro Tag berücksichtigen.</div>
      </div>
      <div class="field-group">
        <label>Schnelles Update-Intervall (Minuten)</label>
        <input type="number" data-field="update_interval_fast_min"
               value="${this._wizardData.update_interval_fast_min}"
               min="1" max="60">
        <div class="help-text">Update-Intervall für Batterie- und PV-Sensoren.</div>
      </div>
      <div class="field-group">
        <label>Langsames Update-Intervall (Minuten)</label>
        <input type="number" data-field="update_interval_slow_min"
               value="${this._wizardData.update_interval_slow_min}"
               min="5" max="120">
        <div class="help-text">Update-Intervall für das Verbrauchsprofil.</div>
      </div>
      <div class="help-text" style="margin-top:8px">
        <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:16px;vertical-align:middle"></ha-icon>
        Der Expertenmodus kann jederzeit oben im Wizard-Fortschritt ein- und ausgeschaltet werden.
      </div>
      ${this._wizardData.expert_mode ? `
      <div style="margin-top:24px">
        <h3 style="margin:0 0 12px;font-size:16px">Test- und Simulation</h3>
        <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer">
          <input type="checkbox" data-field="enable_simulation" ${this._wizardData.enable_simulation ? "checked" : ""}>
          Simulation am Dashboard anzeigen
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="checkbox" data-field="enable_manual_control" ${this._wizardData.enable_manual_control ? "checked" : ""}>
          Manuelle Steuerung am Dashboard anzeigen
        </label>
      </div>` : ""}`;
  }

  /* ── Step 6: Zusammenfassung ──────────────────── */

  _renderStep6() {
    const d = this._wizardData;
    const forecastName =
      d.forecast_source === "solcast_solar" ? "Solcast Solar" : "Forecast.Solar";

    const row = (label, value) =>
      `<div class="summary-row"><span class="label">${label}</span><span class="value">${value}</span></div>`;

    return `
      <p style="margin-bottom:16px;color:var(--secondary-text-color)">
        Überprüfe deine Einstellungen und klicke auf &ldquo;Fertig&rdquo; zum Speichern.
      </p>

      <div class="summary-section">
        <h3>Wechselrichter</h3>
        ${row("Typ", ({"huawei_sun2000": "Huawei SUN2000", "solax_gen4": "SolaX Gen4+", "solaredge_storedge": "SolarEdge StorEdge", "fronius_gen24": "Fronius Gen24"})[d.inverter_type] || d.inverter_type)}
      </div>

      <div class="summary-section">
        <h3>Batterie &amp; PV</h3>
        ${row("Batterieladezustand (SOC)", d.battery_soc_sensor || "—")}
        ${row(
          "Kapazität",
          d.battery_capacity_sensor
            ? d.battery_capacity_sensor
            : d.battery_capacity_kwh + " kWh (manuell)"
        )}
        ${row("PV-Sensor", d.pv_power_sensor || "—")}
        ${d.pv_power_sensor_2 ? row("PV-Sensor 2", d.pv_power_sensor_2) : ""}
        ${(d.battery_power_charge_sensor && d.battery_power_discharge_sensor)
          ? row("Batterie-Leistung", `${d.battery_power_charge_sensor} − ${d.battery_power_discharge_sensor}`)
          : row("Batterie-Leistung", d.battery_power_sensor || "—")}
        ${(d.grid_power_export_sensor && d.grid_power_import_sensor)
          ? row("Netz-Leistung", `${d.grid_power_export_sensor} − ${d.grid_power_import_sensor}`)
          : row("Netz-Leistung", d.grid_power_sensor || "—")}
      </div>

      <div class="summary-section">
        <h3>Prognose</h3>
        ${row("Quelle", forecastName)}
        ${row("Verbleibend heute", d.forecast_remaining_entity || "—")}
        ${row("Morgen", d.forecast_tomorrow_entity || "—")}
      </div>

      <div class="summary-section">
        <h3>Morgen-Einspeisung</h3>
        ${row("Status", d.enable_morning_delay ? "Aktiv" : "Deaktiviert")}
        ${d.enable_morning_delay ? row("Vorlaufzeit", (d.morning_start_offset || 0) + " Std. vor Sonnenaufgang") : ""}
        ${d.enable_morning_delay ? row("Blockiert bis", d.morning_end_time) : ""}
      </div>

      <div class="summary-section">
        <h3>Abend-Entladung</h3>
        ${row("Status", d.enable_night_discharge ? "Aktiv" : "Deaktiviert")}
        ${d.enable_night_discharge ? `
          ${d.enable_peakshare !== false ? `
            ${row("Modus", "PeakShare-Bedarfssteuerung")}
            ${row("Deine Energiegemeinschaft", d.peakshare_community || "BEG")}
          ` : `
            ${row("Startzeit", d.discharge_start_time)}
            ${row("Leistung", d.discharge_power_kw + " kW")}
          `}
          ${row("Min SOC", d.min_soc + " %")}
        ` : ""}
      </div>

      <div class="summary-section">
        <h3>Allgemein</h3>
        ${d.expert_mode ? row("Sicherheitspuffer", d.safety_buffer_pct + " %") : ""}
        ${d.expert_mode ? row("Verbrauchsdurchschnitt", d.lookback_weeks + " Wochen") : ""}
        ${row("Expertenmodus", d.expert_mode ? "Aktiviert" : "Deaktiviert")}
      </div>`;
  }

  /* ── Settings screen ──────────────────────────── */

  _renderSettings() {
    const d = this._settingsData;
    const isExpert = d.expert_mode;
    const mDelay = d.enable_morning_delay;
    const nDischarge = d.enable_night_discharge;

    const morningFields = mDelay ? `
      <div class="feature-params">
        <div class="field-group">
          <label>Vorlaufzeit vor Sonnenaufgang (Std.)</label>
          <input type="number" data-field="settings_morning_start_offset"
                 value="${d.morning_start_offset ?? 0}"
                 min="0" max="3" step="0.5" style="width:80px">
          <div class="help-text">So viele Stunden vor Sonnenaufgang beginnt die Ladeblockierung. 0 = ab Sonnenaufgang.</div>
        </div>
        <div class="field-group">
          <label>Batterieladung blockiert bis maximal</label>
          <input type="text" data-field="settings_morning_end_time" placeholder="HH:MM" pattern="[0-2][0-9]:[0-5][0-9]" maxlength="5"
                 value="${d.morning_end_time || "11:00"}" style="width:80px">
          <div class="help-text">Maximal bis zu dieser Uhrzeit wird die Batterieladung morgens blockiert.</div>
        </div>
      </div>` : "";

    const settingsPeakshare = d.enable_peakshare !== false;
    const settingsPeakshareCommunitiesHtml = (() => {
      const communities = this._peakshareCommunitiesCache || [];
      const selected = d.peakshare_community || "BEG";
      if (communities.length === 0) return `<div class="help-text" style="margin-top:4px">Communities werden geladen...</div>`;
      const opts = communities.map(c => `<option value="${c}" ${c === selected ? "selected" : ""}>${c}</option>`).join("");
      return `<div class="field-group">
          <label>Deine Energiegemeinschaft</label>
          <select data-field="settings_peakshare_community">${opts}</select>
          <div class="help-text">W\u00e4hle die Energiegemeinschaft, nach deren Bedarf der Entladezeitpunkt optimiert wird.</div>
        </div>`;
    })();

    const dischargeFields = nDischarge ? `
      <div class="feature-params">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:12px">
          <input type="checkbox" data-field="settings_enable_peakshare" ${settingsPeakshare ? "checked" : ""}>
          <div>
            <div style="font-weight:500">PeakShare-Bedarfssteuerung</div>
            <div class="help-text" style="margin-top:2px">Entladezeitpunkt wird automatisch nach dem Bedarf der Energiegemeinschaft optimiert.</div>
          </div>
        </label>
        ${settingsPeakshare ? settingsPeakshareCommunitiesHtml : ""}
        <div class="field-group">
          <label>Frühester Entladestart</label>
          <input type="text" data-field="settings_discharge_start_time" placeholder="HH:MM" pattern="[0-2][0-9]:[0-5][0-9]" maxlength="5"
                 value="${d.discharge_start_time || "01:00"}" style="width:80px">
          <div class="help-text">${settingsPeakshare
            ? "Untergrenze für das automatisch berechnete Fenster — PeakShare darf später starten, aber nie früher. Empfehlung 01:00: je später der Start, desto präziser die Verbrauchsprognose und desto mehr wird eingespeist."
            : "Genauer Startzeitpunkt der Entladung. Empfehlung 01:00: je später der Start, desto präziser die Verbrauchsprognose und desto mehr wird eingespeist."}</div>
        </div>
        <div class="field-group">
          <label>Entladeleistung (kW)</label>
          <input type="number" data-field="settings_discharge_power_kw"
                 value="${d.discharge_power_kw || 5.0}"
                 min="${d.inverter_type === "solaredge_storedge" ? "5.0" : "0.5"}" max="10.0" step="0.5">
          <div class="help-text">Leistung der Batterieentladung ins Netz.${settingsPeakshare ? " Bestimmt die Dauer des Entladefensters (Energie \u00f7 Leistung)." : ""}${d.inverter_type === "solaredge_storedge" ? " Bei SolarEdge min. 5 kW." : ""}</div>
        </div>
        <div class="field-group">
          <label>Minimaler Ladezustand (%)</label>
          <input type="number" data-field="settings_min_soc"
                 value="${d.min_soc || 10}"
                 min="5" max="50">
          <div class="help-text">Die Einspeisung sorgt daf\u00fcr, dass dieser Ladestand + der durchschnittliche Verbrauch in der Nacht + Sicherheitspuffer in der Batterie bleibt.</div>
        </div>
      </div>` : "";

    const activeTab = this._settingsTab || "morning";

    const tabBar = `
      <div class="settings-tabs" role="tablist">
        <button class="settings-tab ${activeTab === "morning" ? "active" : ""}" data-action="set-settings-tab" data-tab="morning" role="tab">
          <ha-icon icon="mdi:weather-sunset-up" style="--mdc-icon-size:18px"></ha-icon>
          <span>Morgen-Einspeisung</span>
        </button>
        <button class="settings-tab ${activeTab === "evening" ? "active" : ""}" data-action="set-settings-tab" data-tab="evening" role="tab">
          <ha-icon icon="mdi:battery-arrow-down-outline" style="--mdc-icon-size:18px"></ha-icon>
          <span>Abend-Entladung</span>
        </button>
        <button class="settings-tab ${activeTab === "telemetry" ? "active" : ""}" data-action="set-settings-tab" data-tab="telemetry" role="tab">
          <ha-icon icon="mdi:chart-line" style="--mdc-icon-size:18px"></ha-icon>
          <span>EEG-Statistik</span>
        </button>
        <button class="settings-tab ${activeTab === "advanced" ? "active" : ""}" data-action="set-settings-tab" data-tab="advanced" role="tab">
          <ha-icon icon="mdi:tune" style="--mdc-icon-size:18px"></ha-icon>
          <span>Erweitert</span>
        </button>
      </div>`;

    const morningTab = `
      <div class="card" style="margin-bottom:16px">
        <div class="feature-toggle">
          <div class="feature-card ${mDelay ? "selected" : ""}" data-action="toggle-settings-feature" data-feature="enable_morning_delay" style="cursor:pointer">
            <div class="feature-card-header">
              <ha-icon icon="mdi:weather-sunset-up"></ha-icon>
              <div class="feature-card-text">
                <span class="feature-title">Morgen-Einspeisung</span>
                <span class="feature-desc">Morgens wird die Batterie nicht sofort geladen, sondern die Energie direkt ins Netz eingespeist.</span>
              </div>
              <div class="feature-badge ${mDelay ? "on" : "off"}">${mDelay ? "Aktiv" : "Aus"}</div>
            </div>
          </div>
          ${morningFields}
        </div>
      </div>`;

    const eveningTab = `
      <div class="card" style="margin-bottom:16px">
        <div class="feature-toggle">
          <div class="feature-card ${nDischarge ? "selected" : ""}" data-action="toggle-settings-feature" data-feature="enable_night_discharge" style="cursor:pointer">
            <div class="feature-card-header">
              <ha-icon icon="mdi:battery-arrow-down-outline"></ha-icon>
              <div class="feature-card-text">
                <span class="feature-title">Abend-Entladung</span>
                <span class="feature-desc">Abends wird \u00fcbersch\u00fcssige Energie aus der Batterie ins Netz entladen.</span>
              </div>
              <div class="feature-badge ${nDischarge ? "on" : "off"}">${nDischarge ? "Aktiv" : "Aus"}</div>
            </div>
          </div>
          ${dischargeFields}
        </div>
      </div>`;

    const telemetryTab = this._renderTelemetrySection();

    const advancedTab = `
      <div class="card" style="margin-bottom:16px">
        <label style="display:flex;align-items:center;gap:12px;cursor:pointer">
          <input type="checkbox" data-field="settings_expert_mode" ${isExpert ? "checked" : ""}>
          <div>
            <div style="font-weight:500">Expertenmodus</div>
            <div class="help-text" style="margin-top:4px">Zeigt zus\u00e4tzliche Optionen (Test &amp; Simulation)</div>
          </div>
        </label>
      </div>

      <div class="card" style="margin-bottom:16px">
        <h3 style="margin:0 0 16px">Allgemeine Einstellungen</h3>
        <div class="field-group">
          <label>Sicherheitspuffer (%)</label>
          <input type="number" data-field="settings_safety_buffer_pct"
                 value="${d.safety_buffer_pct || 25}"
                 min="0" max="100" step="5">
          <div class="help-text">Aufschlag auf den berechneten Energiebedarf. Gilt f\u00fcr beide Optimierungen.</div>
        </div>
        <div class="field-group">
          <label>Anzahl der Wochen f\u00fcr den Verbrauchsdurchschnitt</label>
          <input type="number" data-field="settings_lookback_weeks"
                 value="${d.lookback_weeks || 2}"
                 min="1" max="52">
        </div>
        <div class="field-group">
          <label>Schnelles Update-Intervall (Minuten)</label>
          <input type="number" data-field="settings_update_interval_fast_min"
                 value="${d.update_interval_fast_min || 1}"
                 min="1" max="60">
        </div>
        <div class="field-group">
          <label>Langsames Update-Intervall (Minuten)</label>
          <input type="number" data-field="settings_update_interval_slow_min"
                 value="${d.update_interval_slow_min || 15}"
                 min="5" max="120">
        </div>
        ${isExpert ? `
        <div style="margin-top:24px">
          <h3 style="margin:0 0 12px;font-size:16px">Test- und Simulation</h3>
          <label style="display:flex;align-items:center;gap:8px;margin-bottom:12px;cursor:pointer">
            <input type="checkbox" data-field="settings_enable_simulation" ${d.enable_simulation ? "checked" : ""}>
            Simulation am Dashboard anzeigen
          </label>
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" data-field="settings_enable_manual_control" ${d.enable_manual_control ? "checked" : ""}>
            Manuelle Steuerung am Dashboard anzeigen
          </label>
        </div>` : ""}
      </div>

      <div class="card" style="margin-bottom:16px">
        <button class="btn-secondary" data-action="restart-wizard" style="width:100%;display:flex;align-items:center;justify-content:center;gap:8px;padding:12px">
          <ha-icon icon="mdi:refresh" style="--mdc-icon-size:20px"></ha-icon> Wizard nochmal starten
        </button>
      </div>`;

    let tabContent;
    switch (activeTab) {
      case "evening":   tabContent = eveningTab; break;
      case "telemetry": tabContent = telemetryTab; break;
      case "advanced":  tabContent = advancedTab; break;
      case "morning":
      default:          tabContent = morningTab; break;
    }

    return `
      <div style="max-width:600px;margin:0 auto">
        ${tabBar}
        ${tabContent}
        <button class="btn-primary" data-action="save-settings" style="width:100%;padding:12px">Speichern</button>
      </div>`;
  }

  /* ── EEG-Statistik (Telemetrie-Opt-In) ───── */

  _renderTelemetrySection() {
    const s = this._telemetryStatus || { configured: false, enabled: false, registered: false };
    const enabled = !!s.enabled;
    const registered = !!s.registered;
    const notConfigured = !s.configured;
    const hasIdentity = !!(s.installation_id || s.installation_id_prefix);
    const fullId = s.installation_id || s.installation_id_prefix || "";
    // GUID auf die ersten drei Abschnitte kürzen (z.B. "8fcb4c46-ab80-4b2b…").
    const idParts = fullId.split("-");
    const shortId = idParts.length >= 3 ? `${idParts.slice(0, 3).join("-")}…` : fullId;

    let statusText;
    if (notConfigured) {
      statusText = "Backend-URL noch nicht eingerichtet (DEV-Build)";
    } else if (registered && s.registered_at) {
      const d = new Date(s.registered_at);
      const dStr = isNaN(d.getTime()) ? s.registered_at : d.toLocaleDateString("de-DE");
      statusText = `Registriert als anonyme Anlage <code title="${fullId}">${shortId}</code> seit ${dStr}`;
    } else if (hasIdentity && !enabled) {
      statusText = "Pausiert — Identität bleibt gespeichert";
    } else if (enabled && !registered) {
      statusText = "Registrierung läuft …";
    } else {
      statusText = "Nicht registriert";
    }

    const errorRow = this._telemetryError
      ? `<div class="help-text" style="color:var(--error-color,#d33);margin-bottom:12px">${this._telemetryError}</div>`
      : "";

    const showDeleteBtn = registered || hasIdentity;
    const deleteBtn = showDeleteBtn
      ? `<button class="btn-secondary"
                 data-action="forget-telemetry"
                 ${this._telemetryBusy ? "disabled" : ""}
                 style="background:var(--error-color,#d33);color:#fff;border:0;width:100%;padding:12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px">
           <ha-icon icon="mdi:delete-forever"></ha-icon>Daten löschen
         </button>`
      : "";

    return `
      <div class="card" style="margin-bottom:16px">
        <h3 style="margin:0 0 8px">EEG-Statistik</h3>
        <div class="help-text" style="margin-bottom:12px">
          Hilf Deiner EEG: deine Anlage sendet anonymisierte Diagnose- und
          Wirksamkeits-Daten an die EEG. Keine personenbezogenen Daten, keine
          IP-Adressen. Du kannst jederzeit aussteigen und die übermittelten
          Daten auch löschen.
        </div>
        <label style="display:flex;align-items:center;gap:12px;cursor:pointer;margin-bottom:12px">
          <input type="checkbox"
                 data-action="toggle-telemetry"
                 ${enabled ? "checked" : ""}
                 ${notConfigured || this._telemetryBusy ? "disabled" : ""}>
          <div>
            <div style="font-weight:500">EEG-Statistik aktivieren</div>
          </div>
        </label>
        <div class="help-text" style="margin-bottom:12px;word-break:break-all">${statusText}</div>
        <details style="margin-bottom:12px">
          <summary style="cursor:pointer;font-size:13px;color:var(--secondary-text-color);user-select:none">
            Datenschutz-Details (was wird gesendet?)
          </summary>
          <div class="help-text" style="margin-top:10px;line-height:1.5">
            <strong>Übermittelt:</strong>
            <ul style="margin:6px 0 10px 18px;padding:0">
              <li><strong>Profil</strong> (bei Setup, Restart, Settings-Change): App-/HA-Version, Wechselrichter-Typ, Batterie-Kapazität, PV-Peak, Prognose-Quelle, Land, ausgewählte EEG-Community (sofern PeakShare aktiv), Whitelist-Settings (numerische/kategorische Werte, keine Entity-IDs)</li>
              <li><strong>Snapshot</strong> (alle 30 Min, gebündelt 1×/h): Zustand, Modus, SOC %, PV-/Verbrauchs-/Netz-/Batterie-Leistung, dynamischer Min-SOC, Hysterese</li>
              <li><strong>State-Change</strong> (sofort): Übergang, Begründungs-Codes, Snapshot</li>
              <li><strong>Outcome</strong> (Block-Ende): eingespeiste kWh, Dauer, SOC-Start/-Ende, predicted-vs-actual PV/Verbrauch</li>
              <li><strong>Failure</strong> (bei Auftreten): Kategorie, Schweregrad, gehashte Fehlermeldung</li>
            </ul>
            <strong>Nicht übermittelt:</strong>
            <ul style="margin:6px 0 10px 18px;padding:0">
              <li>Keine Entity-IDs / Sensor-Namen</li>
              <li>Keine IP-Adressen (serverseitig nicht persistiert)</li>
              <li>Kein Anlagenname, keine Adresse, keine Geokoordinaten</li>
              <li>Keine EEG-Mitgliedsdaten, keine personenbezogenen Daten</li>
            </ul>
            <strong>Identifikation:</strong> einmalig erzeugte UUIDv4 + API-Key, lokal gespeichert. Beim Löschen werden alle Daten serverseitig kaskadiert entfernt und die UUID lokal verworfen.
          </div>
        </details>
        ${errorRow}
        ${deleteBtn}
      </div>
    `;
  }

  async _handleTelemetryToggle(checked) {
    if (this._telemetryBusy) return;
    this._telemetryBusy = true;
    this._telemetryError = null;
    this._render();
    try {
      const cmd = checked ? "eeg_optimizer/telemetry_enable" : "eeg_optimizer/telemetry_disable";
      const res = await this._hass.callWS({ type: cmd });
      if (!res || res.success === false) {
        const errKey = res && res.error ? `: ${res.error}` : "";
        this._telemetryError = `Aktivieren fehlgeschlagen${errKey}`;
      }
    } catch (err) {
      this._telemetryError = `Aktivieren fehlgeschlagen: ${err && err.message ? err.message : err}`;
    } finally {
      // Status nach jedem Toggle frisch holen — Quelle der Wahrheit ist das Backend.
      try {
        this._telemetryStatus = await this._hass.callWS({ type: "eeg_optimizer/telemetry_get_status" });
      } catch (_) { /* ignore */ }
      this._telemetryBusy = false;
      this._render();
    }
  }

  async _handleTelemetryForget() {
    if (this._telemetryBusy) return;
    const ok = window.confirm(
      "Wirklich alle Daten löschen?\n\n" +
      "Alle gesendeten Telemetriedaten werden vom Server entfernt und die lokale " +
      "Anmeldung wird gelöscht. Diese Aktion kann nicht rückgängig gemacht werden."
    );
    if (!ok) return;
    this._telemetryBusy = true;
    this._telemetryError = null;
    this._render();
    try {
      const res = await this._hass.callWS({ type: "eeg_optimizer/telemetry_forget" });
      if (res && res.backend_deleted === false) {
        this._telemetryError = "Backend-Aufruf fehlgeschlagen — lokale Daten wurden trotzdem gelöscht.";
      }
    } catch (err) {
      this._telemetryError = "Backend-Aufruf fehlgeschlagen — lokale Daten wurden trotzdem gelöscht.";
    } finally {
      try {
        this._telemetryStatus = await this._hass.callWS({ type: "eeg_optimizer/telemetry_get_status" });
      } catch (_) { /* ignore */ }
      this._telemetryBusy = false;
      this._render();
    }
  }

  /* ── Info modal overlay ─────────────────────────── */

  _renderInfoModal() {
    if (!this._activeInfoModal) return "";
    const isZoomed = this._infoImageZoomed;
    const info = this._activeInfoModal === "morning" ? {
      title: "Morgen-Einspeisung",
      image: "/eeg_optimizer_panel/delayed-charging.svg",
      content: `
        <p>Stellt sicher, dass PV-\u00dcbersch\u00fcsse bevorzugt am Morgen ins Netz der Energiegemeinschaft eingespeist werden \u2014 also dann, wenn die Gemeinschaft den Strom dringend braucht. Ohne diese Funktion w\u00fcrde die Batterie den PV-\u00dcberschuss sofort ab Sonnenaufgang aufladen. Die Einspeisung in die Energiegemeinschaft w\u00fcrde dann erst ab Mittag erfolgen, wenn ohnehin genug Strom vorhanden ist.</p>
        <strong>Funktionsweise</strong>
        <p>Die Batterieladung wird ab einer Stunde vor Sonnenaufgang blockiert und fr\u00fchestens um die konfigurierte Endzeit (Standard: 11:00 Uhr) wieder freigegeben. Die Blockierung erfolgt nur, solange die PV-Prognose des aktuellen Tages den Gesamtbedarf \u00fcbersteigt.</p>
        <strong>Der Gesamtbedarf setzt sich zusammen aus</strong>
        <ul>
          <li>Gesch\u00e4tzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang</li>
          <li>Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)</li>
          <li>Fehlende Energie zum Vollladen der Batterie (basierend auf aktuellem SOC)</li>
        </ul>
        <p>Der Stromverbrauch wird anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 2 Wochen).</p>
        <p>Reicht die PV-Prognose nicht aus, um den Gesamtbedarf zu decken, wird die Batterie sofort geladen \u2014 damit der Haushalt bis zum Abend versorgt ist.</p>`
    } : {
      title: "Abend-Entladung",
      image: "/eeg_optimizer_panel/evening-discharge.svg",
      content: `
        <p>Speist unter Tags gewonnene Energie, die der eigene Haushalt nicht ben\u00f6tigt, um \u00fcber die Nacht zu kommen, in die Energiegemeinschaft ein. So steht Strom zu einem Zeitpunkt zur Verf\u00fcgung, an dem ansonsten keine PV-Erzeugung im Netz vorhanden ist.</p>
        <strong>Funktionsweise</strong>
        <p>Im PeakShare-Modus wird der Entladezeitpunkt automatisch nach dem Bedarf der Energiegemeinschaft optimiert. Ohne PeakShare wird ab der konfigurierten festen Startzeit entladen.</p>
        <p>Die Batterie wird mit einstellbarer Leistung entladen, bis der dynamisch berechnete Ziel-SOC erreicht ist.</p>
        <strong>Der Ziel-SOC ergibt sich aus</strong>
        <ul>
          <li>Konfigurierter Mindest-SOC der Batterie</li>
          <li>Gesch\u00e4tzter Stromverbrauch in der Nacht (Entladestart bis eine Stunde nach Sonnenaufgang)</li>
          <li>Sicherheitspuffer auf den Nachtverbrauch (konfigurierbar, Standard: 25%)</li>
        </ul>
        <strong>Die Entladung erfolgt nur, wenn alle Bedingungen erf\u00fcllt sind</strong>
        <ul>
          <li>Aktueller SOC liegt \u00fcber dem berechneten Ziel-SOC</li>
          <li>Die PV-Prognose f\u00fcr morgen deckt den erwarteten Gesamtbedarf</li>
        </ul>
        <strong>Der Gesamtbedarf f\u00fcr morgen setzt sich zusammen aus</strong>
        <ul>
          <li>Gesch\u00e4tzter Stromverbrauch von Sonnenaufgang bis Sonnenuntergang</li>
          <li>Sicherheitspuffer auf den Verbrauch (konfigurierbar, Standard: 25%)</li>
          <li>Ben\u00f6tigte Energie zum Laden der Batterie (von Mindest-SOC auf 100%)</li>
        </ul>
        <p>Der Stromverbrauch wird jeweils anhand des durchschnittlichen Verbrauchs desselben Wochentags der letzten Wochen berechnet (konfigurierbar, Standard: 2 Wochen).</p>
        <p>So wird sichergestellt, dass die Batterie am n\u00e4chsten Tag wieder vollst\u00e4ndig \u00fcber PV geladen werden kann und der Haushalt versorgt ist.</p>`
    };
    return `
      <div class="info-modal-overlay" data-action="close-info-modal">
        <div class="info-modal" @click.stop>
          <button class="info-modal-close" data-action="close-info-modal">\u00d7</button>
          <h2 class="info-modal-title">${info.title}</h2>
          <div class="info-modal-image" data-action="open-lightbox">
            <img src="${info.image}" alt="${info.title}">
          </div>
          <div class="info-modal-body">${info.content}</div>
        </div>
      </div>
      ${isZoomed ? `<div class="info-image-lightbox" data-action="close-lightbox">
        <button class="info-image-lightbox-close" data-action="close-lightbox">\u00d7</button>
        <img src="${info.image}" alt="${info.title}">
      </div>` : ""}`;
  }

  /* ── Dialog overlay ───────────────────────────── */

  _renderDialog() {
    if (!this._showDialog) return "";
    return `
      <div class="dialog-overlay">
        <div class="dialog-card">
          <h2 style="margin-top:0">${this._showDialog.title}</h2>
          ${this._showDialog.content}
          <div style="text-align:right;margin-top:16px">
            <button class="btn-primary" data-action="close-dialog">Schließen</button>
          </div>
        </div>
      </div>`;
  }

  /* ── Dashboard rendering ─────────────────────── */

  _getWeekdayKey(date) {
    return ["so", "mo", "di", "mi", "do", "fr", "sa"][date.getDay()];
  }

  _getWeekdayLabel(date) {
    return ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"][date.getDay()];
  }

  _getWeekdayShort(date) {
    return ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"][date.getDay()];
  }

  _readState(entityId) {
    if (!this._hass || !entityId) return null;
    const s = this._hass.states[entityId];
    if (!s) return null;
    if (s.state === "unavailable" || s.state === "unknown") return null;
    return s;
  }


  _readFloat(entityId) {
    const s = this._readState(entityId);
    if (!s) return null;
    const v = parseFloat(s.state);
    return isNaN(v) ? null : v;
  }

  _renderStatusCards(decisionState) {
    const ma = decisionState?.attributes || {};

    // If optimizer hasn't run yet, show loading state
    if (!ma.letzte_aktualisierung) {
      return `
        <div class="status-cards-row">
          <div class="card" style="text-align:center;padding:24px">
            <div class="manual-spinner" style="margin:0 auto 12px"></div>
            <p style="color:var(--secondary-text-color);margin:0">Wird berechnet\u2026</p>
          </div>
          <div class="card" style="text-align:center;padding:24px">
            <div class="manual-spinner" style="margin:0 auto 12px"></div>
            <p style="color:var(--secondary-text-color);margin:0">Wird berechnet\u2026</p>
          </div>
        </div>`;
    }

    const mStatus = ma.morning_status || "deaktiviert";
    const dStatus = ma.discharge_status || "deaktiviert";

    // --- Left card: Morgen-Einspeisung ---
    let mIndicator = "";
    let mColorClass = "gray";
    let mConditionsHtml = "";

    if (mStatus === "aktiv") {
      mColorClass = "green";
      mIndicator = `\u25CF AKTIV \u2014 Ladung blockiert bis ${ma.morning_end_time || ""}`;
    } else if (mStatus === "nicht_aktiv") {
      mColorClass = "red";
      mIndicator = `\u2715 Nicht aktiv \u2014 PV reicht nicht für Bedarf + Puffer`;
    } else if (mStatus === "morgen_erwartet") {
      mColorClass = "blue";
      mIndicator = `\u25CB Morgen ab ${ma.morning_sunrise_tomorrow || ""} (PV ausreichend)`;
    } else if (mStatus === "morgen_nicht_erwartet") {
      mColorClass = "red";
      mIndicator = `\u2715 Morgen nicht geplant \u2014 PV-Prognose zu gering`;
    } else {
      mColorClass = "gray";
      mIndicator = `\u2014 Deaktiviert`;
    }

    if (mStatus !== "deaktiviert") {
      mConditionsHtml = this._renderMorningConditions(ma, mStatus);
    }

    // --- Right card: Abend-Entladung ---
    let dIndicator = "";
    let dColorClass = "gray";
    let dConditionsHtml = "";

    if (dStatus === "aktiv") {
      dColorClass = "green";
      const pw = ma.discharge_power_kw != null ? fmtDe(ma.discharge_power_kw, 1) : "---";
      const minSoc = ma.discharge_min_soc != null ? Math.round(Number(ma.discharge_min_soc)) : "---";
      if (ma.discharge_peakshare_active && ma.discharge_window_end) {
        dIndicator = `\u25CF AKTIV \u2014 ${pw} kW bis ${ma.discharge_window_end} / ${minSoc}% SOC (PeakShare)`;
      } else {
        dIndicator = `\u25CF AKTIV \u2014 ${pw} kW Entladung bis ${minSoc}% SOC`;
      }
    } else if (dStatus === "geplant") {
      dColorClass = "blue";
      const minSoc = ma.discharge_min_soc != null ? Math.round(Number(ma.discharge_min_soc)) : "---";
      if (ma.discharge_peakshare_active && ma.discharge_window_start) {
        dIndicator = `\u25CB Geplant ${ma.discharge_window_start}-${ma.discharge_window_end} bis ${minSoc}% SOC (PeakShare)`;
      } else {
        dIndicator = `\u25CB Geplant ab ${ma.discharge_start_time || ""} bis ${minSoc}% SOC`;
      }
    } else if (dStatus === "nicht_geplant") {
      dColorClass = "red";
      // Build reason text from reasons array — unknown reasons pass through verbatim
      const reasons = ma.discharge_reasons || [];
      let reasonParts = [];
      reasons.forEach(r => {
        if (r.includes("Nachtverbrauch")) reasonParts.push("Nachtverbrauch zu hoch");
        else if (r.includes("SOC")) reasonParts.push("SOC zu niedrig");
        else if (r.includes("PV-Prognose morgen")) reasonParts.push("PV morgen nicht ausreichend");
        else if (r.includes("abgelaufen")) reasonParts.push("Entladefenster abgelaufen");
        else if (r.includes("04:00")) reasonParts.push("Entladung endet um 04:00");
        else if (r.includes("Netzbezug")) reasonParts.push("Netzbezug-Schutz aktiv");
        else reasonParts.push(r);
      });
      const reasonText = reasonParts.length > 0 ? reasonParts.join(", ") : "Bedingungen nicht erfüllt";
      dIndicator = `\u2715 Nicht geplant \u2014 ${reasonText}`;
    } else {
      dColorClass = "gray";
      dIndicator = `\u2014 Deaktiviert`;
    }

    if (dStatus !== "deaktiviert") {
      dConditionsHtml = this._renderDischargeConditions(ma, dStatus);
    }

    return `
      <div class="status-cards-row">
        <div class="card">
          <h3 class="status-card-title" style="margin-top:0">
            <ha-icon icon="mdi:weather-sunny" style="--mdc-icon-size:20px;color:var(--warning-color,#ff9800)"></ha-icon>
            Morgen-Einspeisung
            <span data-action="show-info" data-info="morning" style="cursor:pointer;display:inline-flex;align-items:center" title="Mehr erfahren">
              <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:18px;color:var(--secondary-text-color)"></ha-icon>
            </span>
          </h3>
          <div class="status-indicator ${mColorClass}">${mIndicator}</div>
          ${mConditionsHtml}
        </div>
        <div class="card">
          <h3 class="status-card-title" style="margin-top:0">
            <ha-icon icon="mdi:weather-night" style="--mdc-icon-size:20px;color:var(--info-color,#2196f3)"></ha-icon>
            Abend-Entladung
            <span data-action="show-info" data-info="discharge" style="cursor:pointer;display:inline-flex;align-items:center" title="Mehr erfahren">
              <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:18px;color:var(--secondary-text-color)"></ha-icon>
            </span>
          </h3>
          <div class="status-indicator ${dColorClass}">${dIndicator}</div>
          ${dConditionsHtml}
        </div>
      </div>`;
  }

  _renderFeedinStatistics() {
    if (!this._feedinStatsLoaded || !this._feedinStats) {
      return `<p style="color:var(--secondary-text-color);font-size:14px">Statistik wird geladen\u2026</p>`;
    }

    const s = this._feedinStats;
    const period = this._feedinStatsPeriod;
    const data = s[period] || {morning: {kwh: 0, count: 0, duration_min: 0}, evening: {kwh: 0, count: 0, duration_min: 0}};
    const m = data.morning || {kwh: 0, count: 0, duration_min: 0};
    const e = data.evening || {kwh: 0, count: 0, duration_min: 0};

    const fmtDur = (min) => {
      if (min < 60) return min + " Min";
      const h = Math.floor(min / 60);
      const r = min % 60;
      return r > 0 ? h + "h " + r + "m" : h + "h";
    };

    const periods = [
      {key: "week", label: "Woche"},
      {key: "month", label: "Monat"},
      {key: "year", label: "Jahr"},
      {key: "total", label: "Gesamt"},
    ];
    const periodBtns = periods.map(p =>
      `<button data-action="feedin-period-${p.key}" style="padding:4px 12px;border:1px solid var(--divider-color);background:${period === p.key ? "var(--primary-color)" : "var(--card-background-color,#fff)"};color:${period === p.key ? "#fff" : "var(--primary-text-color)"};border-radius:16px;font-size:12px;cursor:pointer">${p.label}</button>`
    ).join("");

    const summaryHtml = `
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;margin-bottom:12px">${periodBtns}</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
        <div style="background:var(--card-background-color,#fff);border:1px solid var(--divider-color);border-radius:12px;padding:14px">
          <div style="font-size:13px;color:var(--secondary-text-color);margin-bottom:6px">
            <ha-icon icon="mdi:weather-sunny" style="--mdc-icon-size:16px;color:#FF9800;vertical-align:middle"></ha-icon>
            Morgen-Einspeisung
          </div>
          <div style="font-size:24px;font-weight:600;color:var(--primary-text-color)">${fmtDe(m.kwh, 1)} <span style="font-size:14px;font-weight:400">kWh</span></div>
          <div style="font-size:12px;color:var(--secondary-text-color);margin-top:4px">${m.count}\u00d7 aktiv \u00b7 ${fmtDur(m.duration_min)}</div>
        </div>
        <div style="background:var(--card-background-color,#fff);border:1px solid var(--divider-color);border-radius:12px;padding:14px">
          <div style="font-size:13px;color:var(--secondary-text-color);margin-bottom:6px">
            <ha-icon icon="mdi:weather-night" style="--mdc-icon-size:16px;color:#2196F3;vertical-align:middle"></ha-icon>
            Abend-Entladung
          </div>
          <div style="font-size:24px;font-weight:600;color:var(--primary-text-color)">${fmtDe(e.kwh, 1)} <span style="font-size:14px;font-weight:400">kWh</span></div>
          <div style="font-size:12px;color:var(--secondary-text-color);margin-top:4px">${e.count}\u00d7 aktiv \u00b7 ${fmtDur(e.duration_min)}</div>
        </div>
      </div>`;

    // Bar chart: daily feed-in data
    const chartHtml = this._renderFeedinBarChart();

    return summaryHtml + chartHtml;
  }

  _renderFeedinBarChart() {
    if (!this._feedinStats?.daily) return "";
    const daily = this._feedinStats.daily;
    const period = this._feedinStatsPeriod;

    // Determine how many days to show and whether to aggregate by month
    let byMonth = false;
    let daysBack = 30;
    if (period === "week") daysBack = 7;
    else if (period === "month") daysBack = 30;
    else if (period === "year") { daysBack = 365; byMonth = true; }
    else if (period === "total") { daysBack = 99999; byMonth = true; }

    if (byMonth) {
      return this._renderFeedinMonthlyChart(daily);
    }

    // Daily bars
    const today = new Date();
    const entries = [];
    for (let i = daysBack - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      const dayData = daily[key] || {};
      const mKwh = dayData.morning?.total_kwh || 0;
      const eKwh = dayData.evening?.total_kwh || 0;
      const mDur = dayData.morning?.total_duration_min || 0;
      const eDur = dayData.evening?.total_duration_min || 0;
      const label = d.toLocaleDateString("de-DE", {day: "2-digit", month: "2-digit"});
      entries.push({label, morning: mKwh, evening: eKwh, morningDur: mDur, eveningDur: eDur});
    }

    if (entries.length === 0) return `<p style="color:var(--secondary-text-color);font-size:13px">Noch keine Daten vorhanden</p>`;
    return this._renderGroupedFeedinBars(entries);
  }

  _renderFeedinMonthlyChart(daily) {
    // Aggregate daily data into months
    const months = {};
    for (const [dateStr, dayData] of Object.entries(daily)) {
      const monthKey = dateStr.slice(0, 7); // YYYY-MM
      if (!months[monthKey]) months[monthKey] = {morning: 0, evening: 0, morningDur: 0, eveningDur: 0};
      months[monthKey].morning += dayData.morning?.total_kwh || 0;
      months[monthKey].evening += dayData.evening?.total_kwh || 0;
      months[monthKey].morningDur += dayData.morning?.total_duration_min || 0;
      months[monthKey].eveningDur += dayData.evening?.total_duration_min || 0;
    }

    const sortedKeys = Object.keys(months).sort();
    if (sortedKeys.length === 0) return `<p style="color:var(--secondary-text-color);font-size:13px">Noch keine Daten vorhanden</p>`;

    const monthNames = ["Jan", "Feb", "M\u00e4r", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
    const entries = sortedKeys.map(k => {
      const m = parseInt(k.slice(5, 7)) - 1;
      return {label: monthNames[m] + " " + k.slice(2, 4), morning: months[k].morning, evening: months[k].evening, morningDur: months[k].morningDur, eveningDur: months[k].eveningDur};
    });

    return this._renderGroupedFeedinBars(entries);
  }

  _renderGroupedFeedinBars(entries) {
    const width = 700, height = 300, padding = {top: 30, right: 20, bottom: 40, left: 50};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const maxVal = Math.max(...entries.map(e => Math.max(e.morning, e.evening)), 0.1) * 1.15;
    const slotW = chartW / Math.max(entries.length, 1);
    const barW = Math.min(slotW * 0.35, 30);
    const gap = 2;

    const fmtDur = (min) => {
      if (!min) return "0 Min";
      if (min < 60) return min + " Min";
      const h = Math.floor(min / 60);
      const r = min % 60;
      return r > 0 ? h + "h " + r + "m" : h + "h";
    };

    let bars = "";
    entries.forEach((d, i) => {
      const slotX = padding.left + i * slotW;
      const x1 = slotX + (slotW - barW * 2 - gap) / 2;

      // Morning bar (left, orange)
      if (d.morning > 0) {
        const barH1 = (d.morning / maxVal) * chartH;
        const y1 = padding.top + chartH - barH1;
        const mTip = `${d.label} Morgen-Einspeisung\nEnergie: ${fmtDe(d.morning, 2)} kWh\nDauer: ${fmtDur(d.morningDur || 0)}`;
        bars += `<rect x="${x1}" y="${y1}" width="${barW}" height="${barH1}" fill="#FF9800" rx="3" style="cursor:pointer"><title>${mTip}</title></rect>`;
        if (entries.length <= 14) bars += `<text x="${x1 + barW/2}" y="${y1 - 4}" text-anchor="middle" font-size="10" fill="var(--primary-text-color)" style="pointer-events:none">${fmtDe(d.morning, 1)}</text>`;
      }

      // Evening bar (right, blue)
      const x2 = x1 + barW + gap;
      if (d.evening > 0) {
        const barH2 = (d.evening / maxVal) * chartH;
        const y2 = padding.top + chartH - barH2;
        const eTip = `${d.label} Abend-Entladung\nEnergie: ${fmtDe(d.evening, 2)} kWh\nDauer: ${fmtDur(d.eveningDur || 0)}`;
        bars += `<rect x="${x2}" y="${y2}" width="${barW}" height="${barH2}" fill="#2196F3" rx="3" style="cursor:pointer"><title>${eTip}</title></rect>`;
        if (entries.length <= 14) bars += `<text x="${x2 + barW/2}" y="${y2 - 4}" text-anchor="middle" font-size="10" fill="var(--primary-text-color)" style="pointer-events:none">${fmtDe(d.evening, 1)}</text>`;
      }

      // Skip some labels if too many entries
      const labelEvery = entries.length > 20 ? Math.ceil(entries.length / 12) : 1;
      if (i % labelEvery === 0) {
        bars += `<text x="${slotX + slotW/2}" y="${height - 10}" text-anchor="middle" font-size="${entries.length > 14 ? 9 : 11}" fill="var(--secondary-text-color)">${d.label}</text>`;
      }
    });

    // Y-axis grid
    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = fmtDe(maxVal * (4 - i) / 4, 1);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // Legend
    const lx = width - padding.right - 240;
    const ly = 14;
    const legend = `
      <rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="#FF9800" rx="2"/>
      <text x="${lx + 14}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Morgen-Einspeisung</text>
      <rect x="${lx + 135}" y="${ly - 8}" width="10" height="10" fill="#2196F3" rx="2"/>
      <text x="${lx + 149}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Abend-Entladung</text>`;

    const mobileStyle = `<style>@media (max-width: 600px) { text { font-size: 13px !important; } }</style>`;
    return `<div class="chart-card" style="margin-top:4px"><svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">${mobileStyle}${yLines}${bars}${legend}</svg></div>`;
  }

  _renderActivityTimeline() {
    if (!this._activityLog || this._activityLog.length === 0) {
      return `<p style="color:var(--secondary-text-color);font-size:14px;text-align:center;margin:16px 0">
        Noch keine Eintr\u00e4ge. Das Protokoll f\u00fcllt sich automatisch w\u00e4hrend der Optimizer l\u00e4uft.
      </p>`;
    }

    const zustandIcon = (z) => {
      if (z === "Morgen-Einspeisung") return "\u2600\uFE0F";
      if (z === "Abend-Entladung") return "\uD83C\uDF19";
      return "\u26A1";
    };
    const zustandColor = (z) => {
      if (z === "Morgen-Einspeisung") return "var(--info-color, #2196F3)";
      if (z === "Abend-Entladung") return "#FF9800";
      return "var(--success-color, #4CAF50)";
    };

    // Already sorted newest-first from server
    const baseEntries = this._activityShowAll
      ? this._activityLog
      : this._activityLog.filter(e => e.reason !== "Heartbeat");

    // Optional state filter: show entries of the chosen state plus the
    // "Normal" entry that follows it (i.e. the return to normal mode).
    // Newest-first array \u2192 "follower" entry sits at index i, predecessor at i+1.
    const entries = this._activityFilter
      ? baseEntries.filter((e, i, arr) => {
          if (e.zustand === this._activityFilter) return true;
          if (e.zustand === "Normal" && i + 1 < arr.length && arr[i + 1].zustand === this._activityFilter) return true;
          return false;
        })
      : baseEntries;

    if (entries.length === 0) {
      const emptyMsg = this._activityFilter
        ? `Keine Eintr\u00e4ge f\u00fcr "${this._activityFilter}".`
        : `Keine Status\u00e4nderungen vorhanden. Aktiviere "Alle Eintr\u00e4ge", um auch Heartbeats zu sehen.`;
      return `<p style="color:var(--secondary-text-color);font-size:14px;text-align:center;margin:16px 0">${emptyMsg}</p>`;
    }

    const rows = entries.map(e => {
      const ts = e.timestamp ? new Date(e.timestamp) : null;
      const timeStr = ts ? `${String(ts.getHours()).padStart(2,"0")}:${String(ts.getMinutes()).padStart(2,"0")}` : "---";
      const dateStr = ts ? `${String(ts.getDate()).padStart(2,"0")}.${String(ts.getMonth()+1).padStart(2,"0")}` : "";
      const icon = zustandIcon(e.zustand);
      const color = zustandColor(e.zustand);
      const reason = e.reason === "Heartbeat" ? `<span style="opacity:0.5">${e.zustand}</span>` : `<strong>${e.zustand}</strong>`;
      const changeBadge = e.reason === "Heartbeat" ? "" : `<span class="activity-badge" style="background:${color}">\u00C4nderung</span>`;
      const testBadge = e.ausführung === false ? `<span class="activity-badge" style="background:var(--warning-color,#ff9800)">Testmodus</span>` : "";
      return `<div class="activity-entry">
        <div class="activity-time">${dateStr}<br>${timeStr}</div>
        <div class="activity-dot" style="background:${color}">${icon}</div>
        <div class="activity-content">
          <div class="activity-header">${reason} ${changeBadge} ${testBadge}</div>
          <div class="activity-details">SOC ${e.soc != null ? e.soc + "%" : "—"}${e.zustand === "Abend-Entladung" ? ` &rarr; Ziel-SOC ${fmtDe(e.min_soc, 0)}%` : ""} &middot; ${e.zustand === "Abend-Entladung" ? `PV morgen ${fmtDe(e.discharge_pv != null ? e.discharge_pv : e.pv_tomorrow, 1)} kWh &middot; Gesamtbedarf ${fmtDe(e.discharge_bedarf != null ? e.discharge_bedarf : e.bedarf, 1)} kWh` : `PV-Prognose (Rest) ${fmtDe(e.pv_today, 1)} kWh &middot; Gesamtbedarf ${fmtDe(e.bedarf, 1)} kWh`}</div>
        </div>
      </div>`;
    }).join("");

    const remaining = this._activityTotal - this._activityLog.length;
    let moreBtn = "";
    if (this._activityLoadingMore) {
      moreBtn = `<div style="text-align:center;padding:12px;color:var(--secondary-text-color)">Laden\u2026</div>`;
    } else if (this._activityHasMore && remaining > 0) {
      moreBtn = `<div style="text-align:center;padding:8px">
        <button class="btn-secondary" data-action="show-more-activity" style="font-size:13px">
          Mehr laden (${remaining} weitere)
        </button>
      </div>`;
    }

    return `<div class="activity-timeline">${rows}</div>${moreBtn}`;
  }

  _renderBarChart(data, pvData = null) {
    if (!data || data.length === 0) return "<p>Keine Daten verfügbar</p>";
    const width = 700, height = 300, padding = {top: 30, right: 20, bottom: 40, left: 50};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const maxVal = Math.max(...data.map(d => d.value), ...(pvData || []).map(d => d.value || 0), 1) * 1.1;
    const slotW = chartW / data.length;
    const grouped = pvData != null;
    const barW = grouped ? slotW * 0.35 : slotW * 0.7;
    const gap = grouped ? 2 : slotW * 0.3;

    let bars = "";
    data.forEach((d, i) => {
      const slotX = padding.left + i * slotW;
      if (grouped) {
        // Consumption bar (left)
        const x1 = slotX + (slotW - barW * 2 - gap) / 2;
        const barH1 = (d.value / maxVal) * chartH;
        const y1 = padding.top + chartH - barH1;
        bars += `<rect x="${x1}" y="${y1}" width="${barW}" height="${barH1}" fill="var(--primary-color)" rx="3"/>`;
        bars += `<text class="bc-val" x="${x1 + barW/2}" y="${y1 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${fmtDe(d.value, 1)}</text>`;

        // PV bar (right)
        const pvVal = pvData[i]?.value || 0;
        if (pvVal > 0) {
          const x2 = x1 + barW + gap;
          const barH2 = (pvVal / maxVal) * chartH;
          const y2 = padding.top + chartH - barH2;
          bars += `<rect x="${x2}" y="${y2}" width="${barW}" height="${barH2}" fill="#FF9800" rx="3"/>`;
          bars += `<text class="bc-val" x="${x2 + barW/2}" y="${y2 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${fmtDe(pvVal, 1)}</text>`;
        }

        // Day label centered under group
        bars += `<text class="bc-day" x="${slotX + slotW/2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="var(--secondary-text-color)">${d.label}</text>`;
      } else {
        // Original single-bar rendering
        const x = slotX + (slotW - barW) / 2;
        const barH = (d.value / maxVal) * chartH;
        const y = padding.top + chartH - barH;
        bars += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" fill="var(--primary-color)" rx="3"/>`;
        bars += `<text class="bc-val" x="${x + barW/2}" y="${y - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${fmtDe(d.value, 1)}</text>`;
        bars += `<text class="bc-day" x="${x + barW/2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="var(--secondary-text-color)">${d.label}</text>`;
      }
    });

    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = (maxVal * (4 - i) / 4).toFixed(0);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text class="bc-axis" x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // Legend for grouped bars
    let legend = "";
    if (grouped) {
      const lx = width - padding.right - 200;
      const ly = 14;
      legend += `<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="var(--primary-color)" rx="2"/>`;
      legend += `<text class="bc-legend" x="${lx + 14}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Verbrauch</text>`;
      legend += `<rect x="${lx + 100}" y="${ly - 8}" width="10" height="10" fill="#FF9800" rx="2"/>`;
      legend += `<text class="bc-legend" x="${lx + 114}" y="${ly}" font-size="11" fill="var(--primary-text-color)">PV-Prognose</text>`;
    }

    const mobileStyle = `<style>
      @media (max-width: 600px) {
        .bc-val { font-size: 15px; font-weight: 500; }
        .bc-day { font-size: 15px; font-weight: 500; }
        .bc-axis { font-size: 13px; }
        .bc-legend { font-size: 14px; }
      }
    </style>`;

    return `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">${mobileStyle}${yLines}${bars}${legend}</svg>`;
  }

  _renderEnergyFlow(pvKw, batKw, gridKw, hausKw, socVal, ids = {}) {
    // --- Decompose flows from the four signed values ---
    const pv = Math.max(pvKw, 0);
    const batCharge = Math.max(batKw, 0);          // battery charging (sink)
    const batDischarge = Math.max(-batKw, 0);      // battery discharging (source)
    const gridExport = Math.max(gridKw, 0);        // feed-in to grid
    const gridImport = Math.max(-gridKw, 0);       // import from grid
    const haus = Math.max(hausKw, 0);

    // Priority: PV → Haus → Batterie → Netz
    const pvToHaus = Math.min(pv, haus);
    let pvLeft = pv - pvToHaus;
    const pvToBat = Math.min(pvLeft, batCharge);
    pvLeft -= pvToBat;
    const pvToGrid = Math.min(pvLeft, gridExport);

    // Remaining demand on the house side
    const hausFromBat = Math.min(haus - pvToHaus, batDischarge);
    const hausFromGrid = Math.max(haus - pvToHaus - hausFromBat, 0);
    // Battery filled by something other than PV (rare: from grid)
    const batFromGrid = Math.max(batCharge - pvToBat, 0);

    // --- Layout ---
    const W = 600, H = 320;
    const NW = 150, NH = 64;
    const positions = {
      pv:    { cx: 300, cy: 50 },
      bat:   { cx: 95,  cy: 160 },
      house: { cx: 300, cy: 270 },
      grid:  { cx: 505, cy: 160 },
    };

    // Trim line to box edge so arrow doesn't hide under the rect
    const trim = (from, to) => {
      const dx = to.cx - from.cx;
      const dy = to.cy - from.cy;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len, uy = dy / len;
      const tFrom = Math.min((NW / 2 + 4) / Math.max(Math.abs(ux), 0.001), (NH / 2 + 4) / Math.max(Math.abs(uy), 0.001));
      const tTo   = Math.min((NW / 2 + 4) / Math.max(Math.abs(ux), 0.001), (NH / 2 + 4) / Math.max(Math.abs(uy), 0.001));
      return {
        x1: from.cx + ux * tFrom,
        y1: from.cy + uy * tFrom,
        x2: to.cx - ux * tTo,
        y2: to.cy - uy * tTo,
      };
    };

    // --- Flow lines ---
    const flows = [
      { from: positions.pv,    to: positions.house, value: pvToHaus,      color: "#FFC107" },
      { from: positions.pv,    to: positions.bat,   value: pvToBat,       color: "#FFC107" },
      { from: positions.pv,    to: positions.grid,  value: pvToGrid,      color: "#4CAF50" },
      { from: positions.bat,   to: positions.house, value: hausFromBat,   color: "#FF9800" },
      { from: positions.grid,  to: positions.house, value: hausFromGrid,  color: "#F44336" },
      { from: positions.grid,  to: positions.bat,   value: batFromGrid,   color: "#F44336" },
    ];

    let activeLines = "";
    let inactiveLines = "";
    let labels = "";
    flows.forEach(f => {
      const e = trim(f.from, f.to);
      if (f.value > 0.02) {
        const sw = Math.min(Math.max(2, f.value * 0.7), 5);
        activeLines += `<line class="flow-line" x1="${e.x1}" y1="${e.y1}" x2="${e.x2}" y2="${e.y2}" stroke="${f.color}" stroke-width="${sw}" fill="none"/>`;
        // Label at midpoint
        const mx = (e.x1 + e.x2) / 2;
        const my = (e.y1 + e.y2) / 2;
        labels += `<g transform="translate(${mx} ${my})">
          <rect class="ef-flow-label" x="-24" y="-10" width="48" height="20" rx="10"/>
          <text class="ef-flow-text" x="0" y="4" text-anchor="middle">${fmtDe(f.value, 2)}</text>
        </g>`;
      } else {
        inactiveLines += `<line x1="${e.x1}" y1="${e.y1}" x2="${e.x2}" y2="${e.y2}" stroke="var(--divider-color, #e0e0e0)" stroke-width="1.5" stroke-dasharray="2 5" opacity="0.5"/>`;
      }
    });

    // --- Node renderer ---
    const node = (pos, icon, title, mainText, subText, accent, active, entityId) => {
      const x = pos.cx - NW / 2;
      const y = pos.cy - NH / 2;
      const opacity = active ? 1 : 0.55;
      const clickable = entityId ? `data-action="show-entity" data-entity="${entityId}" style="cursor:pointer"` : "";
      return `<g class="ef-node" opacity="${opacity}" ${clickable}>
        <rect x="${x}" y="${y}" width="${NW}" height="${NH}" rx="14"
          fill="var(--card-background-color, #fff)"
          stroke="${accent}" stroke-width="${active ? 2.5 : 1.5}"/>
        <foreignObject x="${x + 10}" y="${y + (NH - 36) / 2}" width="36" height="36">
          <div xmlns="http://www.w3.org/1999/xhtml" style="display:flex;align-items:center;justify-content:center;width:36px;height:36px">
            <ha-icon icon="${icon}" style="--mdc-icon-size:30px;color:${accent}"></ha-icon>
          </div>
        </foreignObject>
        <text x="${x + 54}" y="${y + 22}" font-size="11" fill="var(--secondary-text-color)" style="text-transform:uppercase;letter-spacing:0.5px">${title}</text>
        <text x="${x + 54}" y="${y + 40}" font-size="15" font-weight="600" fill="var(--primary-text-color)">${mainText}</text>
        ${subText ? `<text x="${x + 54}" y="${y + 55}" font-size="10" fill="var(--secondary-text-color)">${subText}</text>` : ""}
      </g>`;
    };

    // PV
    const pvNode = node(positions.pv, "mdi:solar-power", "Photovoltaik", `${fmtDe(pv, 2)} kW`, "", "#FFC107", pv > 0.02, ids.pvEntity);

    // Battery
    let batMain = socVal != null ? `${socVal} %` : "—";
    let batSub = "Idle";
    let batAccent = "#9E9E9E";
    if (batCharge > 0.02) {
      batSub = `+${fmtDe(batCharge, 2)} kW · Ladung`;
      batAccent = "#4CAF50";
    } else if (batDischarge > 0.02) {
      batSub = `${fmtDe(batDischarge, 2)} kW · Entladung`;
      batAccent = "#FF9800";
    }
    const batNode = node(positions.bat, "mdi:battery", "Batterie", batMain, batSub, batAccent, batCharge > 0.02 || batDischarge > 0.02, ids.batEntity);

    // House
    const houseNode = node(positions.house, "mdi:home", "Haus", `${fmtDe(haus, 2)} kW`, "", "#2196F3", haus > 0.02, ids.hausEntity);

    // Grid
    let gridMain = "0 kW";
    let gridSub = "";
    let gridAccent = "#9E9E9E";
    if (gridExport > 0.02) {
      gridMain = `${fmtDe(gridExport, 2)} kW`;
      gridSub = "Einspeisung";
      gridAccent = "#4CAF50";
    } else if (gridImport > 0.02) {
      gridMain = `${fmtDe(gridImport, 2)} kW`;
      gridSub = "Bezug";
      gridAccent = "#F44336";
    }
    const gridNode = node(positions.grid, "mdi:transmission-tower", "Netz", gridMain, gridSub, gridAccent, gridExport > 0.02 || gridImport > 0.02, ids.gridEntity);

    return `<svg class="energy-flow-svg" viewBox="0 0 ${W} ${H}">
      ${inactiveLines}
      ${activeLines}
      ${labels}
      ${pvNode}
      ${batNode}
      ${houseNode}
      ${gridNode}
    </svg>`;
  }

  _renderDayNightChart(data, sunriseHour, sunsetHour, dischargeStartHour, nightEndDecimal) {
    if (!data || data.length === 0) return "<p>Keine Daten verfügbar</p>";

    // Format end-of-night time from decimal hours (e.g. 6.77 → "06:46")
    const fmtDecimal = (dec) => {
      const h = Math.floor(dec);
      const m = Math.round((dec - h) * 60);
      const hh = m === 60 ? h + 1 : h;
      const mm = m === 60 ? 0 : m;
      return `${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
    };
    const nightStart = `${String(dischargeStartHour).padStart(2, "0")}:00`;
    const nightEnd = fmtDecimal(nightEndDecimal);

    // Threshold for evening discharge: max night consumption that still leaves
    // enough headroom to discharge. Mirrors optimizer._calc_min_soc:
    //   min_soc_dynamic = base_min_soc + ceil(overnight * (1 + buf/100) / capacity * 100)
    // Solving min_soc_dynamic < 100 for overnight gives:
    //   overnight_max = (100 - base_min_soc) / 100 * capacity / (1 + buf/100)
    // Capacity resolution mirrors optimizer._resolve_capacity: sensor first, manual fallback.
    let capKwh = 0;
    const capSensorId = this._config?.battery_capacity_sensor || "";
    if (capSensorId) {
      const s = this._readState(capSensorId);
      if (s) {
        const v = parseFloat(s.state);
        if (!isNaN(v) && v > 0) {
          const unit = s.attributes?.unit_of_measurement || "";
          capKwh = (unit.toLowerCase() === "wh" || (!unit && v > 1000)) ? v / 1000 : v;
        }
      }
    }
    if (!capKwh) {
      capKwh = parseFloat(this._config?.battery_capacity_kwh) || 0;
    }
    const baseMinSoc = parseFloat(this._config?.min_soc ?? 10);
    const buffer = parseFloat(this._config?.safety_buffer_pct ?? 25);
    const thresholdKwh = capKwh > 0
      ? (100 - baseMinSoc) / 100 * capKwh / (1 + buffer / 100)
      : null;

    const width = 700, height = 320, padding = {top: 30, right: 20, bottom: 50, left: 50};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const allValues = data.flatMap(d => [d.tag, d.nacht]);
    if (thresholdKwh != null) allValues.push(thresholdKwh);
    const maxVal = Math.max(...allValues, 1) * 1.1;
    const slotW = chartW / data.length;
    const barW = slotW * 0.35;
    const gap = 2;

    const fmtHour = (h) => `${String(h).padStart(2, "0")}:00`;

    let bars = "";
    data.forEach((d, i) => {
      const slotX = padding.left + i * slotW;

      // Day bar (left, orange)
      const x1 = slotX + (slotW - barW * 2 - gap) / 2;
      const barH1 = (d.tag / maxVal) * chartH;
      const y1 = padding.top + chartH - barH1;
      bars += `<rect x="${x1}" y="${y1}" width="${barW}" height="${barH1}" fill="#FF9800" rx="3">
        <title>${d.label} Tag-Verbrauch (Rest des Tages außerhalb der Nachtperiode): ${fmtDe(d.tag, 2)} kWh</title>
      </rect>`;
      if (d.tag > 0) {
        bars += `<text class="bc-val" x="${x1 + barW/2}" y="${y1 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${fmtDe(d.tag, 1)}</text>`;
      }

      // Night bar (right) — red if it exceeds the discharge threshold
      const x2 = x1 + barW + gap;
      const barH2 = (d.nacht / maxVal) * chartH;
      const y2 = padding.top + chartH - barH2;
      const overThreshold = thresholdKwh != null && d.nacht > thresholdKwh;
      const nightColor = overThreshold ? "#F44336" : "#2196F3";
      const tooltipExtra = overThreshold ? "\n⚠ Über Limit für Abend-Entladung" : "";
      bars += `<rect x="${x2}" y="${y2}" width="${barW}" height="${barH2}" fill="${nightColor}" rx="3">
        <title>${d.label} Nacht-Verbrauch (${nightStart} → ${nightEnd} Folgetag): ${fmtDe(d.nacht, 2)} kWh${tooltipExtra}</title>
      </rect>`;
      if (d.nacht > 0) {
        bars += `<text class="bc-val" x="${x2 + barW/2}" y="${y2 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${fmtDe(d.nacht, 1)}</text>`;
      }

      // Day label centered under the group
      bars += `<text class="bc-day" x="${slotX + slotW/2}" y="${height - 16}" text-anchor="middle" font-size="11" fill="var(--secondary-text-color)">${d.label}</text>`;
    });

    // Y-axis grid + label
    let yLines = `<text x="${padding.left - 36}" y="${padding.top - 8}" font-size="10" fill="var(--secondary-text-color)">kWh</text>`;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = fmtDe(maxVal * (4 - i) / 4, 1);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text class="bc-axis" x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // Threshold line
    let thresholdHtml = "";
    if (thresholdKwh != null && thresholdKwh > 0 && thresholdKwh < maxVal) {
      const ty = padding.top + chartH - (thresholdKwh / maxVal) * chartH;
      thresholdHtml = `
        <line x1="${padding.left}" y1="${ty}" x2="${width - padding.right}" y2="${ty}"
              stroke="#F44336" stroke-width="2" stroke-dasharray="6 4"/>
        <text class="bc-legend" x="${width - padding.right - 4}" y="${ty - 4}" text-anchor="end"
              font-size="11" font-weight="600" fill="#F44336">
          max. ${fmtDe(thresholdKwh, 1)} kWh
        </text>`;
    }

    // Legend
    const lx = padding.left;
    const ly = 14;
    let legend = `
      <rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="#FF9800" rx="2"/>
      <text class="bc-legend" x="${lx + 14}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Tag</text>
      <rect x="${lx + 60}" y="${ly - 8}" width="10" height="10" fill="#2196F3" rx="2"/>
      <text class="bc-legend" x="${lx + 74}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Nacht (${nightStart} → ${nightEnd} Folgetag)</text>`;
    if (thresholdKwh != null) {
      legend += `
        <line x1="${lx + 290}" y1="${ly - 3}" x2="${lx + 314}" y2="${ly - 3}" stroke="#F44336" stroke-width="2" stroke-dasharray="6 4"/>
        <text class="bc-legend" x="${lx + 318}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Limit Nacht</text>`;
    }

    const mobileStyle = `<style>
      @media (max-width: 600px) {
        .bc-val { font-size: 13px; font-weight: 500; }
        .bc-day { font-size: 13px; font-weight: 500; }
        .bc-axis { font-size: 12px; }
        .bc-legend { font-size: 12px; }
      }
    </style>`;

    const hint = thresholdKwh != null
      ? `<p style="margin:8px 4px 0;font-size:12px;color:var(--secondary-text-color);line-height:1.4">
           Die rote Linie zeigt den maximalen Nachtverbrauch, bis zu dem die Abend-Entladung &uuml;berhaupt m&ouml;glich ist
           (${fmtDe(capKwh, 0)}&nbsp;kWh Batterie, Mindest-SOC ${baseMinSoc}&nbsp;%, Sicherheitspuffer ${buffer}&nbsp;%).
           Wochentage mit Nachtverbrauch dar&uuml;ber sind rot eingef&auml;rbt &mdash; an diesen Tagen blockiert der dynamische Mindest-SOC die Entladung.
         </p>`
      : `<p style="margin:8px 4px 0;font-size:12px;color:var(--secondary-text-color)">
           Limit-Linie ben&ouml;tigt die Batteriekapazit&auml;t aus den Einstellungen.
         </p>`;

    return `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">${mobileStyle}${yLines}${thresholdHtml}${bars}${legend}</svg>${hint}`;
  }

  _renderMorningConditions(ma, mStatus) {
    const pvVal = Number(ma.morning_pv_today_kwh || 0);
    const threshold = Number(ma.morning_threshold_kwh || 0);
    const consumption = ma.morning_consumption_kwh != null ? Number(ma.morning_consumption_kwh) : 0;
    const buffer = ma.morning_buffer_kwh != null ? Number(ma.morning_buffer_kwh) : 0;
    const battery = ma.morning_battery_kwh != null ? Number(ma.morning_battery_kwh) : 0;
    const pvOk = pvVal > threshold;
    const isFutureView = mStatus === "morgen_erwartet" || mStatus === "morgen_nicht_erwartet";
    const pvLabel = isFutureView ? "PV-Prognose morgen" : "PV-Prognose heute";
    const demandLabel = isFutureView ? "Gesamtbedarf morgen" : "Gesamtbedarf heute";
    const fensterStart = ma.morning_sunrise_tomorrow || "---";
    const fensterEnd = ma.morning_end_time || "---";

    const scaleMax = Math.max(pvVal, threshold, 0.1) * 1.1;
    const pvBarPct = Math.max(0, Math.min(100, (pvVal / scaleMax) * 100));
    const demandMarkerPct = Math.max(0, Math.min(100, (threshold / scaleMax) * 100));
    const tileColor = pvOk ? "var(--success-color, #4caf50)" : "var(--error-color, #f44336)";

    const open = this._morningTile1Open;
    const tileDetails = open ? `
      <div class="cond-tile-details-body">
        <strong>${demandLabel} ${fmtDe(threshold, 1)} kWh</strong> =
        ${fmtDe(consumption + buffer, 1)} kWh (Tagesverbrauch inkl. Sicherheitspuffer) +
        ${fmtDe(battery, 1)} kWh (Batterieladung)
      </div>` : "";

    return `
      <hr class="status-divider">
      <div class="cond-tile" style="margin-top:4px">
        <div class="cond-tile-header">
          <span class="${pvOk ? "check" : "cross"}" style="font-size:18px">${pvOk ? "✓" : "✗"}</span>
          <span class="cond-tile-title">PV-Deckung</span>
        </div>
        <div class="cond-tile-sub">${pvOk ? "PV deckt den Bedarf" : "PV reicht nicht für den Bedarf"}</div>
        <div class="cond-tile-bar">
          <div class="cond-tile-bar-fill" style="width:${pvBarPct}%;background:${tileColor}"></div>
          <div class="cond-tile-bar-marker" style="left:${demandMarkerPct}%"
            title="${demandLabel} ${fmtDe(threshold, 1)} kWh"></div>
        </div>
        <div class="cond-tile-row">
          <span><strong>${fmtDe(pvVal, 1)} kWh</strong> <span class="cond-tile-muted">${pvLabel}</span></span>
          <span class="cond-tile-muted">Bedarf ${fmtDe(threshold, 1)} kWh</span>
        </div>
        <div class="cond-tile-row">
          <span class="cond-tile-muted">Fenster</span>
          <span class="cond-tile-muted">${fensterStart} bis ${fensterEnd}</span>
        </div>
        <div data-action="toggle-morning-tile-1" class="cond-tile-details-toggle">
          <ha-icon icon="mdi:chevron-${open ? "up" : "down"}" style="--mdc-icon-size:16px"></ha-icon>
          <span>Details ${open ? "ausblenden" : "anzeigen"}</span>
        </div>
        ${tileDetails}
      </div>`;
  }

  _renderDischargeConditions(ma, dStatus) {
    const soc = Number(ma.discharge_soc || 0);
    const minSoc = Number(ma.discharge_min_soc || 0);
    const hyst = !!ma.discharge_hysteresis_active;
    const effectiveMin = hyst ? minSoc + 5 : minSoc;
    const overnightDemand = ma.discharge_demand_overnight_kwh != null ? fmtDe(ma.discharge_demand_overnight_kwh, 1) : "---";

    const pvTom = Number(ma.discharge_pv_tomorrow_kwh || 0);
    const consDaylight = ma.discharge_consumption_daylight_kwh != null ? fmtDe(ma.discharge_consumption_daylight_kwh, 1) : "---";
    const safetyBuffer = ma.discharge_safety_buffer_kwh != null ? fmtDe(ma.discharge_safety_buffer_kwh, 1) : "---";
    const battCharge = ma.discharge_battery_charge_needed_kwh != null ? fmtDe(ma.discharge_battery_charge_needed_kwh, 1) : "---";
    const demandTotal = Number(ma.discharge_demand_total_kwh || 0);

    const socOk = soc > effectiveMin;
    const pvOk = pvTom >= demandTotal;

    // --- Tile 1: Nachtreserve (SOC vs. effective min) ---
    const socPct = Math.max(0, Math.min(100, soc));
    const minMarkerPct = Math.max(0, Math.min(100, effectiveMin));
    const tile1Color = socOk ? "var(--success-color, #4caf50)" : "var(--error-color, #f44336)";

    const hystBadge = hyst
      ? `<span style="display:inline-block;margin-left:6px;padding:1px 6px;border-radius:4px;
          background:var(--warning-color,#ff9800);color:#fff;font-size:11px;font-weight:500"
          title="Eine erneute Entladung erfordert SOC > Min-SOC + 5 % (Hysterese aktiv)">+5 % Hysterese</span>`
      : "";

    const open1 = this._dischargeTile1Open;
    const overnightWithBuffer = ma.discharge_demand_overnight_kwh != null
      ? fmtDe(Number(ma.discharge_demand_overnight_kwh) * (1 + (this._config?.safety_buffer_pct ?? 25) / 100), 1)
      : "---";
    const tile1Details = open1 ? `
      <div class="cond-tile-details-body">
        <strong>Min-SOC ${fmtDe(minSoc, 0)} %</strong> =
        ${this._config?.min_soc ?? 10} % (Minimaler Ladezustand) +
        ${overnightWithBuffer} kWh (Nachtverbrauch inkl. Sicherheitspuffer)${hyst ? `<br>+ 5 % Hysterese → <strong>${fmtDe(effectiveMin, 0)} %</strong>` : ""}
      </div>` : "";

    const tile1 = `
      <div class="cond-tile">
        <div class="cond-tile-header">
          <span class="${socOk ? "check" : "cross"}" style="font-size:18px">${socOk ? "✓" : "✗"}</span>
          <span class="cond-tile-title">Nachtreserve</span>
          ${hystBadge}
        </div>
        <div class="cond-tile-sub">${socOk ? "SOC reicht über die Nacht" : "SOC zu niedrig für die Nacht"}</div>
        <div class="cond-tile-bar">
          <div class="cond-tile-bar-fill" style="width:${socPct}%;background:${tile1Color}"></div>
          <div class="cond-tile-bar-marker" style="left:${minMarkerPct}%"
            title="Min-SOC ${fmtDe(effectiveMin, 0)} %"></div>
        </div>
        <div class="cond-tile-row">
          <span><strong>${fmtDe(soc, 0)} %</strong> <span class="cond-tile-muted">aktuell</span></span>
          <span class="cond-tile-muted">Min ${fmtDe(effectiveMin, 0)} %</span>
        </div>
        <div data-action="toggle-discharge-tile-1" class="cond-tile-details-toggle">
          <ha-icon icon="mdi:chevron-${open1 ? "up" : "down"}" style="--mdc-icon-size:16px"></ha-icon>
          <span>Details ${open1 ? "ausblenden" : "anzeigen"}</span>
        </div>
        ${tile1Details}
      </div>`;

    // --- Tile 2: Tagesdeckung (PV morgen vs. Gesamtbedarf) ---
    const scaleMax = Math.max(pvTom, demandTotal, 0.1) * 1.1;
    const pvBarPct = Math.max(0, Math.min(100, (pvTom / scaleMax) * 100));
    const demandMarkerPct = Math.max(0, Math.min(100, (demandTotal / scaleMax) * 100));
    const tile2Color = pvOk ? "var(--success-color, #4caf50)" : "var(--error-color, #f44336)";

    const open2 = this._dischargeTile2Open;
    const consDaylightWithBuffer = (ma.discharge_consumption_daylight_kwh != null && ma.discharge_safety_buffer_kwh != null)
      ? fmtDe(Number(ma.discharge_consumption_daylight_kwh) + Number(ma.discharge_safety_buffer_kwh), 1)
      : "---";
    const tile2Details = open2 ? `
      <div class="cond-tile-details-body">
        <strong>Gesamtbedarf morgen ${fmtDe(demandTotal, 1)} kWh</strong> =
        ${consDaylightWithBuffer} kWh (Tagesverbrauch inkl. Sicherheitspuffer) +
        ${battCharge} kWh (Batterie nachladen)
      </div>` : "";

    const tile2 = `
      <div class="cond-tile">
        <div class="cond-tile-header">
          <span class="${pvOk ? "check" : "cross"}" style="font-size:18px">${pvOk ? "✓" : "✗"}</span>
          <span class="cond-tile-title">Tagesdeckung</span>
        </div>
        <div class="cond-tile-sub">${pvOk ? "PV morgen deckt den Bedarf" : "PV morgen reicht nicht"}</div>
        <div class="cond-tile-bar">
          <div class="cond-tile-bar-fill" style="width:${pvBarPct}%;background:${tile2Color}"></div>
          <div class="cond-tile-bar-marker" style="left:${demandMarkerPct}%"
            title="Gesamtbedarf ${fmtDe(demandTotal, 1)} kWh"></div>
        </div>
        <div class="cond-tile-row">
          <span><strong>${fmtDe(pvTom, 1)} kWh</strong> <span class="cond-tile-muted">PV morgen</span></span>
          <span class="cond-tile-muted">Bedarf ${fmtDe(demandTotal, 1)} kWh</span>
        </div>
        <div data-action="toggle-discharge-tile-2" class="cond-tile-details-toggle">
          <ha-icon icon="mdi:chevron-${open2 ? "up" : "down"}" style="--mdc-icon-size:16px"></ha-icon>
          <span>Details ${open2 ? "ausblenden" : "anzeigen"}</span>
        </div>
        ${tile2Details}
      </div>`;

    // --- Optional: Entladeleistung-Zeile bei aktivem Status ---
    let activeRow = "";
    if (dStatus === "aktiv") {
      const pw = ma.discharge_power_kw != null ? fmtDe(ma.discharge_power_kw, 1) : "---";
      activeRow = `
        <div class="cond-tile-row" style="margin-top:8px;font-size:13px">
          <span class="cond-tile-muted">Entladeleistung</span>
          <span><strong>${pw} kW</strong></span>
        </div>`;
    }

    return `
      <hr class="status-divider">
      <div class="cond-tiles">
        ${tile1}
        ${tile2}
      </div>
      ${activeRow}`;
  }

  _renderConsumptionProfileStatus(profilState) {
    const attrs = profilState?.attributes || {};
    const statsCount = attrs.stats_count ?? 0;
    const lookback = attrs.lookback_weeks ?? this._config?.lookback_weeks ?? "?";
    const lastRefresh = attrs.last_refresh;
    const durationMs = attrs.last_duration_ms;

    const fmtRefresh = (iso) => {
      if (!iso) return "noch nie";
      try {
        return new Date(iso).toLocaleString("de-DE", {
          day: "2-digit", month: "2-digit", year: "numeric",
          hour: "2-digit", minute: "2-digit", second: "2-digit",
        });
      } catch { return "---"; }
    };

    let resultBanner = "";
    const r = this._profileRefreshResult;
    if (r) {
      if (r.success) {
        const dur = r.duration_ms != null ? `${fmtDe(r.duration_ms / 1000, 1)} s` : "";
        const cnt = r.stats_count != null ? `${r.stats_count} Datenpunkte` : "";
        const parts = [cnt, dur].filter(Boolean).join(", ");
        resultBanner = `<div class="inverter-test-result success" style="margin-top:8px">
          <ha-icon icon="mdi:check-circle"></ha-icon> Verbrauchsprofil aktualisiert${parts ? ` (${parts})` : ""}.
        </div>`;
      } else if (r.busy) {
        resultBanner = `<div class="inverter-test-result error" style="margin-top:8px">
          <ha-icon icon="mdi:timer-sand"></ha-icon> Eine Neuberechnung läuft bereits — bitte kurz warten.
        </div>`;
      } else {
        resultBanner = `<div class="inverter-test-result error" style="margin-top:8px">
          <ha-icon icon="mdi:alert-circle"></ha-icon> ${r.error || "Neuberechnung fehlgeschlagen."}
        </div>`;
      }
    }

    const running = this._profileRefreshing;
    const btnLabel = running ? "Wird neu berechnet…" : "Verbrauchsprofil neu berechnen";
    const durationHint = durationMs != null ? ` · letzte Dauer: ${fmtDe(durationMs / 1000, 1)} s` : "";

    return `
      <div style="margin-top:12px;padding:12px;background:var(--secondary-background-color);border-radius:8px">
        <div style="display:flex;flex-wrap:wrap;gap:12px 24px;font-size:13px;color:var(--secondary-text-color)">
          <div><strong style="color:var(--primary-text-color)">Datenpunkte:</strong> ${statsCount}</div>
          <div><strong style="color:var(--primary-text-color)">Fenster:</strong> ${lookback} Wochen (laut gespeicherter Konfig)</div>
          <div><strong style="color:var(--primary-text-color)">Letzte Berechnung:</strong> ${fmtRefresh(lastRefresh)}${durationHint}</div>
        </div>
        <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <button data-action="refresh-consumption-profile"
            ${running ? "disabled" : ""}
            style="padding:8px 14px;border-radius:8px;border:none;cursor:${running ? "default" : "pointer"};
              background:var(--primary-color,#03a9f4);color:#fff;font-size:14px;font-weight:500;
              opacity:${running ? "0.6" : "1"};display:inline-flex;align-items:center;gap:8px">
            ${running
              ? `<div class="manual-spinner" style="width:14px;height:14px;border-width:2px"></div>`
              : `<ha-icon icon="mdi:refresh" style="--mdc-icon-size:18px"></ha-icon>`}
            <span>${btnLabel}</span>
          </button>
          <span style="font-size:12px;color:var(--secondary-text-color)">
            Liest die Verbrauchsstatistik der letzten ${lookback} Wochen aus dem Recorder neu ein.
          </span>
        </div>
        ${resultBanner}
      </div>`;
  }

  _renderLineChart(datasets, highlightIndex = 0) {
    if (!datasets || datasets.length === 0) return "<p>Keine Daten verfügbar</p>";
    const width = 700, height = 330, padding = {top: 20, right: 20, bottom: 80, left: 55};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const allVals = datasets.flatMap(ds => ds.data);
    const maxVal = Math.max(...allVals, 0.1) * 1.1;

    // Y-axis grid
    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = fmtDe(maxVal * (4 - i) / 4, 1);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text class="lc-axis" x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // X-axis labels — every 3h
    let xLabels = "";
    for (let h = 0; h < 24; h += 3) {
      const x = padding.left + (h / 23) * chartW;
      xLabels += `<text class="lc-axis" x="${x}" y="${padding.top + chartH + 15}" text-anchor="middle" font-size="10" fill="var(--secondary-text-color)">${h}:00</text>`;
    }

    // Weekday colors (7 distinct colors)
    const weekdayColors = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#00BCD4", "#FF5722"];

    // All lines as hoverable groups
    let allLines = "";
    datasets.forEach((ds, idx) => {
      const color = weekdayColors[idx % weekdayColors.length];
      const isHighlight = idx === highlightIndex;
      let pts = "";
      let areaPts = `${padding.left},${padding.top + chartH} `;
      ds.data.forEach((val, i) => {
        const x = padding.left + (i / 23) * chartW;
        const y = padding.top + chartH - (val / maxVal) * chartH;
        pts += `${x},${y} `;
        areaPts += `${x},${y} `;
      });
      areaPts += `${padding.left + chartW},${padding.top + chartH}`;

      const baseOpacity = isHighlight ? "1" : "0.3";
      const baseSw = isHighlight ? "2.5" : "1";
      allLines += `<g class="wl${isHighlight ? " wl-today" : ""}" data-idx="${idx}">`;
      // Invisible wide hit area for easier hover/touch
      allLines += `<polyline points="${pts}" fill="none" stroke="transparent" stroke-width="16" style="pointer-events:stroke"/>`;
      // Area fill (visible on highlight or hover)
      allLines += `<polygon class="wl-area" points="${areaPts}" fill="${color}" opacity="${isHighlight ? '0.12' : '0'}"/>`;
      // Visible line
      allLines += `<polyline class="wl-line" points="${pts}" fill="none" stroke="${color}" stroke-width="${baseSw}" opacity="${baseOpacity}"/>`;
      allLines += `</g>`;
    });

    // Legend — 2 rows of 4+3 for better mobile readability
    let legend = "";
    const legendRow1Y = padding.top + chartH + 40;
    const legendRow2Y = legendRow1Y + 22;
    const itemsPerRow = 4;
    const legendItemW = chartW / itemsPerRow;
    datasets.forEach((ds, idx) => {
      const row = Math.floor(idx / itemsPerRow);
      const col = idx % itemsPerRow;
      const lx = padding.left + col * legendItemW;
      const ly = row === 0 ? legendRow1Y : legendRow2Y;
      const isHighlight = idx === highlightIndex;
      const color = weekdayColors[idx % weekdayColors.length];
      const fw = isHighlight ? "bold" : "normal";
      const opacity = isHighlight ? "1" : "0.6";
      const sw = isHighlight ? "2.5" : "1.5";
      legend += `<g class="wl-legend" data-idx="${idx}" style="cursor:pointer">`;
      // Invisible wider hit area for easier hover/touch
      legend += `<rect x="${lx - 4}" y="${ly - 14}" width="${legendItemW}" height="22" fill="transparent"/>`;
      legend += `<line x1="${lx}" y1="${ly - 4}" x2="${lx + 16}" y2="${ly - 4}" stroke="${color}" stroke-width="${sw}" opacity="${opacity}"/>`;
      legend += `<text class="lc-legend" x="${lx + 20}" y="${ly}" font-size="10" font-weight="${fw}" fill="var(--primary-text-color)" opacity="${opacity}">${ds.label}</text>`;
      legend += `</g>`;
    });

    return `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">
      <style>
        .wl { cursor: pointer; }
        .wl:hover .wl-line, .wl.wl-legend-hover .wl-line { stroke-width: 2.5 !important; opacity: 1 !important; }
        .wl:hover .wl-area, .wl.wl-legend-hover .wl-area { opacity: 0.12 !important; }
        svg:has(.wl:hover) .wl:not(:hover):not(.wl-today) .wl-line { opacity: 0.12 !important; }
        svg:has(.wl:hover) .wl-today:not(:hover) .wl-line { opacity: 0.4 !important; }
        svg:has(.wl-legend-hover) .wl:not(.wl-legend-hover):not(.wl-today) .wl-line { opacity: 0.12 !important; }
        svg:has(.wl-legend-hover) .wl-today:not(.wl-legend-hover) .wl-line { opacity: 0.4 !important; }
        @media (max-width: 600px) {
          .lc-axis { font-size: 13px; }
          .lc-legend { font-size: 13px; }
        }
      </style>
      ${yLines}
      ${allLines}
      ${xLabels}
      ${legend}
    </svg>`;
  }


  _renderDashboard() {
    const h = this._hass;
    if (!h) return "<p>Lade...</p>";

    // --- Status card ---
    const modeState = this._readState(this._entityIds?.select || "select.eeg_energy_optimizer_optimizer");
    const modeValue = modeState ? modeState.state : "---";
    const modeToggleClass = modeValue === "Ein" ? "ein" : "test";

    const decisionState = this._readState(this._entityIds?.entscheidung || "sensor.eeg_energy_optimizer_entscheidung");

    // Connection lost banner
    if (!decisionState && !modeState) {
      return `<div class="connection-lost">
        <div class="connection-lost-icon">&#9888;</div>
        <h2>Verbindung verloren</h2>
        <p>Warte auf Verbindung zum Home Assistant Server...</p>
        <div class="connection-lost-spinner"></div>
      </div>`;
    }

    const zustand = decisionState?.attributes?.zustand || decisionState?.state || "---";
    const zustandBadgeClass =
      zustand === "Morgen-Einspeisung" ? "blue" :
      zustand === "Normal" ? "green" :
      zustand === "Abend-Entladung" ? "orange" : "gray";

    const nächsteAktion = decisionState?.attributes?.nächste_aktion || decisionState?.state || "---";
    const energiebedarf = decisionState?.attributes?.energiebedarf_kwh;
    const energiebedarfText = energiebedarf != null ? `${fmtDe(energiebedarf, 1)} kWh` : "---";

    // --- Metrics ---
    const socSensor = this._config?.battery_soc_sensor;
    const socVal = socSensor ? this._readFloat(socSensor) : null;
    const socText = socVal != null ? `${Math.round(socVal)}` : (socSensor ? "---" : "Nicht konfiguriert");
    const socColorClass = socVal == null ? "" : socVal > 50 ? "soc-green" : socVal >= 25 ? "soc-yellow" : "soc-red";

    // --- PV forecast: read from original Solcast/Forecast.Solar sensors ---
    const forecastTomorrowId = this._config?.forecast_tomorrow_entity || "";
    const forecastRemainingId = this._config?.forecast_remaining_entity || "";

    // Derive prefix from configured sensors
    // Solcast new: "sensor.solcast_pv_forecast_prognose_morgen" → prefix "sensor.solcast_pv_forecast_prognose_"
    // Solcast old: "sensor.solcast_pv_forecast_prognose_fuer_morgen" → prefix "sensor.solcast_pv_forecast_prognose_fuer_"
    // Forecast.Solar: "sensor.energy_production_tomorrow" → prefix "sensor.energy_production_"
    let solcastPrefix = "";
    let forecastSolarPrefix = "";
    if (forecastTomorrowId.includes("solcast")) {
      solcastPrefix = forecastTomorrowId.replace(/morgen$/, "");
      // If old "fuer_" prefix doesn't find tag sensors, try without "fuer_"
      const states = this._hass?.states || {};
      if (solcastPrefix.endsWith("fuer_") && !states[solcastPrefix + "tag_3"]) {
        solcastPrefix = solcastPrefix.replace(/fuer_$/, "");
      }
    } else if (forecastTomorrowId.includes("energy_production")) {
      forecastSolarPrefix = forecastTomorrowId.replace(/tomorrow$/, "");
    }

    // PV total today — prefer configured sensor, then auto-detect
    let pvHeute = null;
    if (this._config?.forecast_today_entity) {
      pvHeute = this._readFloat(this._config.forecast_today_entity);
    }
    if (pvHeute == null && solcastPrefix) {
      pvHeute = this._readFloat(solcastPrefix + "heute");
    } else if (pvHeute == null && forecastSolarPrefix) {
      pvHeute = this._readFloat(forecastSolarPrefix + "today");
    }
    if (pvHeute == null) {
      pvHeute = this._readFloat(this._entityIds?.pv_heute || "sensor.eeg_energy_optimizer_pv_prognose_heute");
    }
    const pvHeuteText = pvHeute != null ? fmtDe(pvHeute, 1) : "---";

    // PV tomorrow
    let pvMorgen = null;
    if (solcastPrefix) {
      pvMorgen = this._readFloat(solcastPrefix + "morgen");
    } else if (forecastSolarPrefix) {
      pvMorgen = this._readFloat(forecastSolarPrefix + "tomorrow");
    }
    if (pvMorgen == null) {
      pvMorgen = this._readFloat(this._entityIds?.pv_morgen || "sensor.eeg_energy_optimizer_pv_prognose_morgen");
    }
    const pvMorgenText = pvMorgen != null ? fmtDe(pvMorgen, 1) : "---";

    // 7-day PV forecast array — prefer configured sensors, then auto-detect from prefix
    const _pvDay = (dayNum) => {
      const cfgKey = `forecast_day${dayNum}_entity`;
      if (this._config?.[cfgKey]) return this._readFloat(this._config[cfgKey]) || 0;
      if (solcastPrefix) return this._readFloat(solcastPrefix + `tag_${dayNum}`) || 0;
      return 0;
    };
    const pvWeek = [
      pvHeute || 0,
      pvMorgen || 0,
      _pvDay(3), _pvDay(4), _pvDay(5), _pvDay(6), _pvDay(7),
    ];

    // --- 7-day forecast chart ---
    const forecastSensors = [
      this._entityIds?.prognose_heute || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_heute",
      this._entityIds?.prognose_morgen || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_morgen",
      this._entityIds?.prognose_tag2 || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_2",
      this._entityIds?.prognose_tag3 || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_3",
      this._entityIds?.prognose_tag4 || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_4",
      this._entityIds?.prognose_tag5 || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_5",
      this._entityIds?.prognose_tag6 || "sensor.eeg_energy_optimizer_tagesverbrauchsprognose_tag_6",
    ];
    const today = new Date();
    const forecastData = forecastSensors.map((eid, i) => {
      let val;
      if (i === 0) {
        // Today: use full-day total from attribute instead of remaining
        const s = this._readState(eid);
        val = s?.attributes?.tagesverbrauch_gesamt_kwh != null
          ? Number(s.attributes.tagesverbrauch_gesamt_kwh) : this._readFloat(eid);
      } else {
        val = this._readFloat(eid);
      }
      let label;
      if (i === 0) label = "Heute";
      else if (i === 1) label = "Morgen";
      else {
        const d = new Date(today);
        d.setDate(d.getDate() + i);
        label = this._getWeekdayShort(d);
      }
      return { label, value: val || 0 };
    });

    // --- PV forecast data for grouped bar chart (all 7 days if Solcast) ---
    const pvForecastData = forecastData.map((d, i) => {
      return { label: d.label, value: pvWeek[i] || 0 };
    });
    const _solcastDay37Missing = solcastPrefix && pvWeek.slice(2).every(v => v === 0);

    // --- Hourly profile chart (all weekdays) ---
    const profilState = this._readState(this._entityIds?.verbrauchsprofil || "sensor.eeg_energy_optimizer_verbrauchsprofil");
    const dayKey = this._getWeekdayKey(today);
    const weekdayKeys = ["mo", "di", "mi", "do", "fr", "sa", "so"];
    const weekdayLabels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
    const weekdayDatasets = [];
    weekdayKeys.forEach((key, idx) => {
      const watts = profilState?.attributes?.[`${key}_watts`];
      if (watts && Array.isArray(watts) && watts.length === 24) {
        weekdayDatasets.push({
          data: watts.map(w => w / 1000),
          label: weekdayLabels[idx],
          key: key
        });
      }
    });
    const highlightIdx = weekdayDatasets.findIndex(ds => ds.key === dayKey);

    // --- Day/Night dataset for the alternative chart variant ---
    const sunriseHour = Number(profilState?.attributes?.sunrise_hour ?? 6);
    const sunsetHour = Number(profilState?.attributes?.sunset_hour ?? 20);
    const dischargeStartHour = Number(profilState?.attributes?.discharge_start_hour
      ?? (this._config?.discharge_start_time
        ? parseInt(String(this._config.discharge_start_time).split(":")[0], 10)
        : 20));
    const nightEndDecimal = Number(profilState?.attributes?.night_end_decimal
      ?? (sunriseHour + 1));
    const daynightData = weekdayKeys.map((key, idx) => ({
      key,
      label: weekdayLabels[idx],
      tag: Number(profilState?.attributes?.[`${key}_tag_kwh`] ?? 0),
      nacht: Number(profilState?.attributes?.[`${key}_nacht_kwh`] ?? 0),
    }));

    // --- Manual control status ---
    const manualAction = this._manualAction;
    const manualResult = this._manualResult;
    let manualStatusHtml = "";
    if (manualAction) {
      const actionLabels = { stop: "Normalbetrieb wird aktiviert", discharge: "Entladung wird gestartet", block: "Ladung wird blockiert" };
      manualStatusHtml = `<div class="manual-loading">
        <div class="manual-spinner"></div>
        <span>${actionLabels[manualAction] || "Befehl wird ausgef\u00fchrt"}\u2026</span>
      </div>`;
    } else if (manualResult) {
      if (manualResult.success) {
        manualStatusHtml = `<div class="inverter-test-result success" style="margin-top:12px">
          <ha-icon icon="mdi:check-circle"></ha-icon> ${manualResult.message}
        </div>`;
      } else {
        manualStatusHtml = `<div class="inverter-test-result error" style="margin-top:12px">
          <ha-icon icon="mdi:alert-circle"></ha-icon> ${manualResult.error}
        </div>`;
      }
    }

    const narrowClass = this._narrow ? " narrow" : "";

    // --- Live values for header card ---
    // Read power sensors and normalize to kW
    // Read all values from our own calculated sensors (normalized, multi-inverter aware)
    const pvKw = this._readFloat("sensor.eeg_energy_optimizer_pv_leistung") || 0;
    const batKw = this._readFloat("sensor.eeg_energy_optimizer_batterieleistung") || 0;
    let gridKw = this._readFloat("sensor.eeg_energy_optimizer_netzleistung") || 0;
    const hausKw = this._readFloat("sensor.eeg_energy_optimizer_hausverbrauch") || 0;
    const batLabel = batKw >= 0 ? "Ladung" : "Entladung";
    const batColor = "val-orange";
    const gridLabel = gridKw >= 0 ? "Einspeisung" : "Bezug";
    const gridColor = gridKw >= 0 ? "val-green" : "val-red";
    const socColor = socVal == null ? "" : socVal > 50 ? "val-green" : socVal >= 25 ? "val-orange" : "val-red";

    // Entity IDs for clickable live values — all our own calculated sensors
    const pvEntity = "sensor.eeg_energy_optimizer_pv_leistung";
    const batEntity = "sensor.eeg_energy_optimizer_batterieleistung";
    const gridEntity = "sensor.eeg_energy_optimizer_netzleistung";
    const socEntity = this._config?.battery_soc_sensor || "";
    const hausEntity = "sensor.eeg_energy_optimizer_hausverbrauch";

    const fmtTime = (isoStr) => {
      if (!isoStr) return "---";
      try { return new Date(isoStr).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
      catch { return "---"; }
    };
    const optimizerTs = fmtTime(decisionState?.attributes?.letzte_aktualisierung);
    const profilTs = fmtTime(profilState?.last_updated);
    const telemetryEnabled = !!(this._telemetryStatus && this._telemetryStatus.enabled && this._telemetryStatus.registered);
    const telemetryTs = telemetryEnabled
      ? (this._telemetryStatus.last_send_at ? fmtTime(this._telemetryStatus.last_send_at) : "—")
      : null;

    const simBanner = this._simActive ? `
      <div style="background:var(--warning-color, #ff9800);color:#fff;padding:12px 16px;border-radius:12px;
        margin-bottom:16px;display:flex;align-items:center;gap:8px;font-weight:500;flex-wrap:wrap">
        <ha-icon icon="mdi:flask-outline" style="--mdc-icon-size:20px"></ha-icon>
        Simulation aktiv — Verbrauchsfaktor: ${this._simFactor}x${this._simSocOverride !== null ? `, SOC: ${this._simSocOverride}%` : ""}
        <button style="margin-left:auto;background:rgba(255,255,255,0.2);border:none;color:#fff;
          padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px"
          data-action="sim-reset">Zur\u00fccksetzen</button>
      </div>` : "";

    return `
      <div class="dashboard-grid${narrowClass}">
        ${simBanner}
        <!-- Header Card: Live Values Grid OR Energy Flow + Mode Toggle + Timestamps -->
        <div class="card header-card">
          <div class="header-card-top">
            <h3 class="status-card-title" style="margin:0;display:flex;align-items:center;gap:8px;flex:1;min-width:0">
              <ha-icon icon="mdi:pulse" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);flex-shrink:0"></ha-icon>
              <span style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">Aktueller Status</span>
              ${this._config?.inverter_type === "solaredge_storedge" ? `<span style="cursor:pointer;display:inline-flex;align-items:center;flex-shrink:0"
                title="NVRAM-Schreibvorg\u00e4nge: ${this._readFloat("sensor.eeg_energy_optimizer_register_schreibvorgange") ?? 0} seit Installation">
                <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:18px;color:var(--secondary-text-color)"></ha-icon>
              </span>` : ""}
            </h3>
            <div class="status-view-pills">
              <button class="view-pill ${this._statusViewVariant === "values" ? "active" : ""}" data-action="set-status-view" data-variant="values" title="Werte-Anzeige">
                <ha-icon icon="mdi:view-grid-outline" style="--mdc-icon-size:16px"></ha-icon>
              </button>
              <button class="view-pill ${this._statusViewVariant === "flow" ? "active" : ""}" data-action="set-status-view" data-variant="flow" title="Energieflu\u00dfdiagramm">
                <ha-icon icon="mdi:transit-connection-variant" style="--mdc-icon-size:16px"></ha-icon>
              </button>
            </div>
            <div class="header-mode-toggle">
              <div class="mode-toggle ${modeToggleClass}" data-action="toggle-mode">
                <div class="toggle-knob"></div>
              </div>
              <span class="mode-toggle-label">${modeValue === "Ein" ? "Ein" : "Testmodus"}</span>
            </div>
          </div>
          ${this._statusViewVariant === "flow"
            ? this._renderEnergyFlow(pvKw, batKw, gridKw, hausKw, socVal, {pvEntity, batEntity, gridEntity, hausEntity, socEntity})
            : `<div class="header-grid">
                <div class="hlv${pvEntity ? " hlv-clickable" : ""}" ${pvEntity ? `data-action="show-entity" data-entity="${pvEntity}"` : ""}><span class="hlv-label">PV</span><span class="hlv-val val-green">${fmtDe(pvKw, 2)} kW</span></div>
                <div class="hlv${batEntity ? " hlv-clickable" : ""}" ${batEntity ? `data-action="show-entity" data-entity="${batEntity}"` : ""}><span class="hlv-label">Batterie</span><span class="hlv-val ${batColor}">${fmtDe(Math.abs(batKw), 2)} kW <small>(${batLabel})</small></span></div>
                <div class="hlv${socEntity ? " hlv-clickable" : ""}" ${socEntity ? `data-action="show-entity" data-entity="${socEntity}"` : ""}><span class="hlv-label">SOC</span><span class="hlv-val ${socColor}">${socText}%</span></div>
                <div class="hlv${gridEntity ? " hlv-clickable" : ""}" ${gridEntity ? `data-action="show-entity" data-entity="${gridEntity}"` : ""}><span class="hlv-label">Netz</span><span class="hlv-val ${gridColor}">${fmtDe(Math.abs(gridKw), 2)} kW <small>(${gridLabel})</small></span></div>
                <div class="hlv hlv-clickable" data-action="show-entity" data-entity="${hausEntity}"><span class="hlv-label">Haus</span><span class="hlv-val val-blue">${fmtDe(hausKw, 2)} kW</span></div>
              </div>`}
          <div class="header-timestamps">
            <span>Optimizer: ${optimizerTs}</span>
            <span>Verbrauchsdaten: ${profilTs}</span>
            ${telemetryTs ? `<span>EEG-Statistik: ${telemetryTs}</span>` : ""}
          </div>
        </div>

        <!-- Status Cards Row -->
        ${this._renderStatusCards(decisionState)}

        <!-- Charts (or loading hint if no consumption data yet) -->
        ${(profilState?.attributes?.stats_count || 0) === 0 ? `
        <div class="card" style="text-align:center;padding:32px">
          <ha-icon icon="mdi:chart-line" style="--mdc-icon-size:48px;color:var(--secondary-text-color);opacity:0.5"></ha-icon>
          <h3 style="margin:16px 0 8px;color:var(--secondary-text-color)">Verbrauchsdaten werden berechnet...</h3>
          <p style="color:var(--secondary-text-color);font-size:14px;margin:0">
            Die historischen Verbrauchsdaten werden aus deinen Sensoren berechnet. Das kann beim ersten Start einige Sekunden dauern.
          </p>
        </div>
        ` : `
        <!-- 7-Day Forecast Chart -->
        <div class="card chart-card">
          <h3 class="status-card-title" style="margin-top:0">
            <ha-icon icon="mdi:chart-bar" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4)"></ha-icon>
            Energieprognose (7 Tage)
            <span class="info-popup-trigger">
              <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:18px;color:var(--secondary-text-color);cursor:pointer"></ha-icon>
              <div class="info-popup">
                <strong>Energieprognose</strong>
                <p>Das Diagramm zeigt f\u00fcr die n\u00e4chsten 7 Tage den durchschnittlichen Energieverbrauch desselben Wochentags der letzten Wochen (konfigurierbar, Standard: 2 Wochen) sowie den von der Prognosesoftware gesch\u00e4tzten PV-Ertrag des jeweiligen Tages.</p>
              </div>
            </span>
          </h3>
          ${this._renderBarChart(forecastData, pvForecastData)}
          ${_solcastDay37Missing ? `<p style="margin:8px 0 0;padding:10px 12px;background:var(--warning-color,#ff9800)22;border-left:3px solid var(--warning-color,#ff9800);border-radius:4px;font-size:0.85em;color:var(--primary-text-color)">
            <ha-icon icon="mdi:alert-outline" style="--mdc-icon-size:16px;vertical-align:middle;margin-right:4px;color:var(--warning-color,#ff9800)"></ha-icon>
            Bitte die Sensoren f\u00fcr die Tage 3\u20137 in der Solcast Integration aktivieren, um die fehlenden Prognosedaten anzeigen zu lassen.</p>` : ""}
        </div>

        <!-- Feed-in Statistics Card -->
        <div class="card">
          <div data-action="toggle-feedin-stats" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:chart-timeline-variant-shimmer" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);vertical-align:middle"></ha-icon>
              Einspeise-Statistik
            </h3>
            <ha-icon icon="mdi:chevron-${this._feedinStatsOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._feedinStatsOpen ? this._renderFeedinStatistics() : ""}
        </div>

        <!-- Hourly Profile Chart (collapsible) -->
        <div class="card">
          <div data-action="toggle-profil" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:chart-line" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);vertical-align:middle"></ha-icon>
              Verbrauchsprofil (Wochentage)
            </h3>
            <ha-icon icon="mdi:chevron-${this._profilOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._profilOpen && this._config?.expert_mode ? this._renderConsumptionProfileStatus(profilState) : ""}
          ${this._profilOpen ? (() => {
            const variant = this._profilChartVariant || "hourly";
            const pillStyle = (active) => `padding:6px 14px;border:1px solid var(--divider-color);background:${active ? "var(--primary-color)" : "var(--card-background-color,#fff)"};color:${active ? "#fff" : "var(--primary-text-color)"};border-radius:16px;font-size:12px;cursor:pointer`;
            const toggleBar = `
              <div style="display:flex;gap:8px;margin:12px 0;flex-wrap:wrap">
                <button data-action="set-profil-variant" data-variant="hourly" style="${pillStyle(variant === "hourly")}">Stundenverlauf</button>
                <button data-action="set-profil-variant" data-variant="daynight" style="${pillStyle(variant === "daynight")}">Tag / Nacht</button>
              </div>`;
            const chart = variant === "daynight"
              ? this._renderDayNightChart(daynightData, sunriseHour, sunsetHour, dischargeStartHour, nightEndDecimal)
              : this._renderLineChart(weekdayDatasets, highlightIdx >= 0 ? highlightIdx : 0);
            return toggleBar + chart;
          })() : ""}
        </div>

        ${this._config?.enable_peakshare !== false ? (() => {
          const psComm = this._config?.peakshare_community || "BEG";
          const psDisplay = psComm === "BEG" ? "BEG" : `EEG ${psComm}`;
          return `
        <!-- PeakShare Energiebedarf (collapsible) -->
        <div class="card">
          <div data-action="toggle-peakshare-data" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:transmission-tower" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);vertical-align:middle"></ha-icon>
              Energiebedarf ${psDisplay}
            </h3>
            <ha-icon icon="mdi:chevron-${this._peakshareDataOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._peakshareDataOpen ? this._renderPeakShareDashboard() : ""}
        </div>`;
        })() : ""}
        `}

        <!-- Activity Timeline (collapsible) -->
        <div class="card">
          <div data-action="toggle-activity-log" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:history" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);vertical-align:middle"></ha-icon>
              Aktivit\u00e4tsprotokoll
            </h3>
            <ha-icon icon="mdi:chevron-${this._activityLogOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._activityLogOpen ? `
          <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end;margin-top:12px">
            <select data-field="activity_filter" style="font-size:12px;padding:2px 4px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);border-radius:4px">
              <option value="" ${this._activityFilter === "" ? "selected" : ""}>Alle Zust\u00e4nde</option>
              <option value="Morgen-Einspeisung" ${this._activityFilter === "Morgen-Einspeisung" ? "selected" : ""}>Morgen-Einspeisung</option>
              <option value="Abend-Entladung" ${this._activityFilter === "Abend-Entladung" ? "selected" : ""}>Abend-Entladung</option>
            </select>
            <label data-action="toggle-activity-show-all" style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--secondary-text-color);cursor:pointer;user-select:none">
              <input type="checkbox" ${this._activityShowAll ? "checked" : ""} style="pointer-events:none;margin:0"> Alle Eintr\u00e4ge
            </label>
            <button class="btn-link" data-action="refresh-activity-log" style="font-size:12px">
              <ha-icon icon="mdi:refresh" style="--mdc-icon-size:14px;vertical-align:middle"></ha-icon> Aktualisieren
            </button>
          </div>
          ${this._renderActivityTimeline()}
          ` : ""}
        </div>

        ${this._config?.enable_manual_control ? `
        <!-- Manual Control Card -->
        <div class="card">
          <div data-action="toggle-manual-control" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:gamepad-variant-outline" style="--mdc-icon-size:20px;color:var(--primary-color,#03a9f4);vertical-align:middle"></ha-icon>
              Manuelle Steuerung
            </h3>
            <ha-icon icon="mdi:chevron-${this._manualControlOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._manualControlOpen ? `
          <p style="color:var(--secondary-text-color);font-size:14px;margin-top:8px">
            Wechselrichter testweise ansteuern, um die Kommunikation ausprobieren zu k\u00f6nnen. Achtung: Der Optimizer \u00fcberschreibt manuelle Befehle im n\u00e4chsten Zyklus.
          </p>
          ${!this._config?.setup_complete ? `
            <div class="btn-manual-grid">
              <button class="btn-manual btn-manual-normal" disabled>
                <ha-icon icon="mdi:flash-auto"></ha-icon>
                <span>Normalbetrieb</span>
              </button>
              <button class="btn-manual btn-manual-discharge" disabled>
                <ha-icon icon="mdi:battery-arrow-down"></ha-icon>
                <span>Entladung starten</span>
              </button>
              <button class="btn-manual btn-manual-block" disabled>
                <ha-icon icon="mdi:battery-off"></ha-icon>
                <span>Ladung blockieren</span>
              </button>
            </div>
            <div class="help-text" style="margin-top:12px">
              <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:16px;vertical-align:middle"></ha-icon>
              Die manuelle Steuerung ist erst nach Abschluss der Einrichtung verf\u00fcgbar. Bitte zuerst den Wizard abschlie\u00dfen.
            </div>
          ` : `
            <div class="btn-manual-grid">
              <button class="btn-manual btn-manual-normal" data-action="manual-stop"
                ${manualAction ? "disabled" : ""}>
                <ha-icon icon="mdi:flash-auto"></ha-icon>
                <span>Normalbetrieb</span>
              </button>
              <button class="btn-manual btn-manual-discharge" data-action="manual-discharge"
                ${manualAction ? "disabled" : ""}>
                <ha-icon icon="mdi:battery-arrow-down"></ha-icon>
                <span>Entladung starten</span>
              </button>
              <button class="btn-manual btn-manual-block" data-action="manual-block-charge"
                ${manualAction ? "disabled" : ""}>
                <ha-icon icon="mdi:battery-off"></ha-icon>
                <span>Ladung blockieren</span>
              </button>
            </div>
            <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:12px 0">
              <label style="font-size:14px;display:flex;align-items:center;gap:6px">
                Leistung:
                <input type="number" data-field="manual_discharge_kw" min="0.5" max="12" step="0.5"
                  value="${this._manualDischargeKw || this._config?.discharge_power_kw || 5.0}"
                  style="width:70px;border-radius:8px;border:1px solid var(--divider-color);padding:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:14px"> kW
              </label>
              <label style="font-size:14px;display:flex;align-items:center;gap:6px">
                Ziel-SOC:
                <input type="number" data-field="manual_discharge_soc" min="5" max="100" step="5"
                  value="${this._manualDischargeSoc}"
                  style="width:70px;border-radius:8px;border:1px solid var(--divider-color);padding:8px;background:var(--card-background-color);color:var(--primary-text-color);font-size:14px"> %
              </label>
            </div>
            ${manualStatusHtml}
          `}
          ` : ""}
        </div>
        ` : ""}

        ${this._config?.enable_simulation ? `
        <!-- Simulation Card -->
        <div class="card">
          <div data-action="toggle-simulation" style="display:flex;justify-content:space-between;align-items:center;cursor:pointer;user-select:none">
            <h3 style="margin:0">
              <ha-icon icon="mdi:flask-outline" style="--mdc-icon-size:20px;vertical-align:middle"></ha-icon>
              Simulation
              ${this._simActive ? `<span style="font-size:12px;font-weight:normal;color:var(--warning-color, #ff9800);margin-left:8px">Aktiv</span>` : ""}
            </h3>
            <ha-icon icon="mdi:chevron-${this._simulationOpen ? "up" : "down"}" style="--mdc-icon-size:24px;color:var(--secondary-text-color)"></ha-icon>
          </div>
          ${this._simulationOpen ? `
          <p style="color:var(--secondary-text-color);font-size:14px;margin-top:8px">
            Verbrauchswerte skalieren und SOC \u00fcberschreiben, um Optimizer-Entscheidungen zu testen.
          </p>
          <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin:12px 0">
            <label style="font-size:14px;display:flex;align-items:center;gap:6px">
              Verbrauchsfaktor:
              <input type="number" data-field="sim_factor" min="0.1" max="3.0" step="0.1"
                value="${this._simFactor}"
                style="width:70px;border-radius:8px;border:1px solid var(--divider-color);
                  padding:8px;background:var(--card-background-color);
                  color:var(--primary-text-color);font-size:14px">x
            </label>
            <label style="font-size:14px;display:flex;align-items:center;gap:6px">
              <input type="checkbox" data-field="sim_soc_enabled"
                ${this._simSocEnabled ? "checked" : ""}>
              SOC Override:
              <input type="number" data-field="sim_soc" min="0" max="100" step="1"
                value="${this._simSocOverride ?? 50}"
                ${!this._simSocEnabled ? "disabled" : ""}
                style="width:70px;border-radius:8px;border:1px solid var(--divider-color);
                  padding:8px;background:var(--card-background-color);
                  color:var(--primary-text-color);font-size:14px">%
            </label>
          </div>
          <div style="display:flex;gap:8px;margin-top:12px">
            <button class="btn-manual btn-manual-discharge" data-action="sim-apply"
              style="flex:1" ${this._simLoading ? "disabled" : ""}>
              <ha-icon icon="mdi:play"></ha-icon>
              <span>Anwenden</span>
            </button>
            <button class="btn-manual btn-manual-normal" data-action="sim-reset"
              style="flex:1" ${!this._simActive || this._simLoading ? "disabled" : ""}>
              <ha-icon icon="mdi:restore"></ha-icon>
              <span>Zur\u00fccksetzen</span>
            </button>
          </div>
          ${this._simLoading ? `
          <div class="manual-loading">
            <div class="manual-spinner"></div>
            <span>Simulation wird angewendet\u2026</span>
          </div>` : ""}
          ${!this._simLoading && this._simActive ? `
            <div class="help-text" style="margin-top:12px;color:var(--warning-color, #ff9800)">
              <ha-icon icon="mdi:alert-outline" style="--mdc-icon-size:16px;vertical-align:middle"></ha-icon>
              Override aktiv.
            </div>
          ` : ""}
          ` : ""}
        </div>
        ` : ""}

        <div style="text-align:center;margin-top:32px;padding:16px 0 8px;font-size:11px;color:var(--secondary-text-color,#999);line-height:1.6">
          <img src="/eeg_optimizer_panel/logo.png" alt="EEG Energy Optimizer" style="max-height:36px;width:auto;display:block;margin:0 auto 8px;filter:brightness(1) saturate(1.2) hue-rotate(-10deg)">
          <div style="opacity:0.35">EEG Energy Optimizer${this._config?.version ? " v" + this._config.version : ""}</div>
          <div style="max-width:480px;margin:4px auto 0;font-size:10px;opacity:0.35">Diese Software steuert Batteriespeicher automatisch. Nutzung auf eigene Verantwortung \u2014 keine Haftung f\u00fcr Sch\u00e4den an Ger\u00e4ten, Ertragsausf\u00e4lle oder fehlerhafte Steuerung.</div>
        </div>

      </div>`;
  }

  /* ── Main render ──────────────────────────────── */

  _render() {
    try {
      this._renderInner();
      // Verify render succeeded
    } catch (outerErr) {
      console.error("EEG Energy Optimizer fatal render error:", outerErr);
      try {
        this._shadow.innerHTML = `
          <div style="padding:24px;font-family:sans-serif">
            <h3 style="color:#db4437;margin-top:0">Dashboard-Fehler</h3>
            <p>Ein unerwarteter Fehler ist aufgetreten.</p>
            <pre style="font-size:12px;overflow:auto;background:#f5f5f5;padding:12px;border-radius:4px">${outerErr.message}\n${outerErr.stack}</pre>
            <button onclick="location.reload()" style="margin-top:12px;padding:8px 16px;cursor:pointer">Seite neu laden</button>
          </div>`;
      } catch (_) { /* truly fatal */ }
    }
  }

  _renderInner() {
    if (!this._initialized) {
      // Show loading indicator instead of blank white screen
      this._shadow.innerHTML = `
        <style>
          :host { display:block; height:100%; background:var(--primary-background-color,#fafafa); }
          .loading-screen { display:flex; flex-direction:column; align-items:center; justify-content:center; height:100%; gap:16px; color:var(--secondary-text-color,#666); }
          .loading-spinner { width:40px; height:40px; border:3px solid var(--divider-color,#e0e0e0); border-top-color:var(--primary-color,#03a9f4); border-radius:50%; animation:spin 1s linear infinite; }
          @keyframes spin { to { transform:rotate(360deg); } }
        </style>
        <div class="loading-screen">
          <div class="loading-spinner"></div>
          <div>Verbindung wird hergestellt\u2026</div>
        </div>`;
      return;
    }

    let headerRight = "";
    if (this._setupComplete && this._view === "dashboard") {
      headerRight = `
        <button data-action="open-settings" title="Einstellungen">
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>`;
    } else if (this._view === "settings") {
      headerRight = `
        <button data-action="back-to-dashboard" title="Zur\u00fcck">
          <ha-icon icon="mdi:arrow-left"></ha-icon>
        </button>`;
    } else if (this._view === "wizard") {
      headerRight = `
        <button data-action="back-to-dashboard" title="Zur\u00fcck">
          <ha-icon icon="mdi:arrow-left"></ha-icon>
        </button>`;
    }

    let content = "";
    try {
      if (this._view === "wizard") {
        content = `
          <div class="content">
            ${this._renderWizard()}
          </div>
          ${this._renderDialog()}`;
      } else if (this._view === "settings") {
        content = `
          <div class="content">
            ${this._renderSettings()}
          </div>`;
      } else if (!this._setupComplete) {
        content = `
          <div class="content">
            <div class="card setup-card">
              <img src="/eeg_optimizer_panel/logo.png" alt="EEG Energy Optimizer" class="setup-logo">
              <h2>Die Einrichtung wurde noch nicht abgeschlossen</h2>
              <p>Richte den EEG Energy Optimizer ein, um die Batteriesteuerung für deine Energiegemeinschaft zu optimieren.</p>
              <button class="btn-primary" data-action="start-wizard">Einrichtung starten</button>
            </div>
          </div>`;
      } else {
        content = `
          <div class="content">
            <div id="dashboard-root">
              ${this._renderDashboard()}
            </div>
          </div>
          ${this._renderInfoModal()}`;
      }
    } catch (err) {
      console.error("EEG Energy Optimizer render error:", err);
      content = `
        <div class="content">
          <div class="card" style="border-left:4px solid var(--error-color, #db4437); margin:16px">
            <h3 style="color:var(--error-color, #db4437); margin-top:0">Render-Fehler</h3>
            <p style="color:var(--secondary-text-color)">Das Dashboard konnte nicht gerendert werden. Details:</p>
            <pre style="font-size:12px; overflow:auto; background:var(--secondary-background-color, #f5f5f5); padding:12px; border-radius:4px">${err.message}\n${err.stack}</pre>
          </div>
        </div>`;
    }

    this._shadow.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          background: var(--primary-background-color, #fafafa);
          color: var(--primary-text-color, #212121);
          font-family: var(--paper-font-body1_-_font-family, "Roboto", sans-serif);
        }
        .toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 16px;
          height: 56px;
          background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, var(--text-primary-color));
        }
        .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
        .toolbar .menu-btn { margin-right: 8px; }
        .toolbar button {
          background: none; border: none; color: inherit;
          cursor: pointer; padding: 8px; border-radius: 50%;
        }
        .toolbar button:hover { background: rgba(255, 255, 255, 0.1); }
        .toolbar ha-icon { --mdc-icon-size: 24px; }
        .content { padding: 16px; max-width: 900px; margin: 0 auto; }
        .card {
          background: var(--card-background-color, #fff);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,0.1));
          padding: 24px;
        }
        .setup-card { text-align: center; padding: 48px 24px; }
        .setup-card .setup-logo {
          max-width: 200px; height: auto; margin-bottom: 24px;
        }
        .setup-card h2 {
          color: var(--primary-text-color); margin-bottom: 16px;
          font-size: 24px; font-weight: 400;
        }
        .setup-card p {
          color: var(--secondary-text-color); margin-bottom: 24px; line-height: 1.5;
        }
        .btn-primary {
          background: var(--primary-color); color: var(--text-primary-color);
          border: none; border-radius: 4px; padding: 12px 32px;
          cursor: pointer; font-size: 16px; font-weight: 500; transition: opacity 0.2s;
        }
        .btn-primary:hover { opacity: 0.9; }
        /* Wizard styles */
        .wizard-nav { display: flex; justify-content: space-between; margin-top: 24px; }
        .step-indicator { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; color: var(--secondary-text-color); font-size: 14px; }
        .expert-toggle { display: flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer; opacity: 0.7; transition: opacity 0.2s; white-space: nowrap; }
        .expert-toggle:hover { opacity: 1; }
        .expert-toggle input { margin: 0; cursor: pointer; }
        .progress-bar { height: 4px; background: var(--divider-color); border-radius: 2px; margin-bottom: 24px; }
        .progress-bar-fill { height: 100%; background: var(--primary-color); border-radius: 2px; transition: width 0.3s; }
        .field-group { margin-bottom: 16px; }
        .field-group label { display: block; font-weight: 500; margin-bottom: 4px; color: var(--primary-text-color); }
        .field-group label.checkbox-label { display: flex !important; align-items: center; gap: 8px; cursor: pointer; }
        .field-group .help-text { font-size: 12px; color: var(--secondary-text-color); margin-top: 4px; }
        .field-group input:not([type="checkbox"]), .field-group select {
          width: 100%; padding: 8px 12px; border: 1px solid var(--divider-color);
          border-radius: 4px; background: var(--card-background-color); color: var(--primary-text-color);
          font-size: 14px; box-sizing: border-box;
        }
        .field-group ha-entity-picker { display: block; width: 100%; }
        .blocked-card {
          border: 2px solid var(--error-color, #f44336); padding: 16px;
          border-radius: 8px; margin-bottom: 16px;
        }
        .blocked-card .status { color: var(--error-color, #f44336); font-weight: 500; }
        .success-card {
          border: 2px solid var(--success-color, #4caf50); padding: 16px;
          border-radius: 8px; margin-bottom: 16px;
        }
        .collapsible-header {
          cursor: pointer; display: flex; align-items: center; gap: 8px;
          color: var(--primary-color); font-weight: 500; margin-top: 16px;
        }
        .collapsible-content { padding-top: 8px; }
        .dialog-overlay {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.5); z-index: 999;
          display: flex; align-items: center; justify-content: center;
        }
        .dialog-card {
          background: var(--card-background-color); border-radius: 12px;
          padding: 24px; max-width: 700px; width: 92%; max-height: 85vh; overflow-y: auto;
        }
        .summary-section { margin-bottom: 16px; }
        .summary-section h3 { font-size: 16px; color: var(--primary-color); margin-bottom: 8px; }
        .summary-row {
          display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px;
        }
        .summary-row .label { color: var(--secondary-text-color); }
        .summary-row .value { color: var(--primary-text-color); font-weight: 500; max-width: 60%; text-align: right; word-break: break-all; }
        .btn-secondary {
          background: transparent; border: 1px solid var(--primary-color);
          color: var(--primary-color); border-radius: 4px; padding: 12px 32px;
          cursor: pointer; font-size: 16px; font-weight: 500;
        }
        .btn-secondary:hover { background: var(--primary-color); color: var(--text-primary-color); }
        .btn-disabled { opacity: 0.5; cursor: not-allowed; pointer-events: none; }
        .status-badge {
          display: inline-block; padding: 4px 12px; border-radius: 12px;
          font-size: 12px; font-weight: 500; margin-right: 8px;
        }
        .status-badge.installed { background: var(--success-color, #4caf50); color: white; }
        .status-badge.missing { background: var(--error-color, #f44336); color: white; }
        .loading { text-align: center; padding: 24px; color: var(--secondary-text-color); }
        .feature-toggle { margin-bottom: 4px; }
        .feature-card {
          border: 2px solid var(--divider-color); border-radius: 8px;
          padding: 16px; cursor: pointer; transition: border-color 0.2s, background 0.2s;
        }
        .feature-card:hover { border-color: var(--primary-color); }
        .feature-card.selected {
          border-color: var(--primary-color);
          background: var(--primary-color-light, rgba(3,169,244,0.08));
        }
        .feature-card-header {
          display: flex; align-items: flex-start; gap: 12px;
        }
        .feature-card-header ha-icon { --mdc-icon-size: 28px; color: var(--secondary-text-color); flex-shrink: 0; margin-top: 2px; }
        .feature-card.selected ha-icon { color: var(--primary-color); }
        .feature-card-text { flex: 1; }
        .feature-title { display: block; font-weight: 500; font-size: 14px; margin-bottom: 4px; }
        .feature-desc { display: block; font-size: 12px; color: var(--secondary-text-color); line-height: 1.4; }
        .feature-badge {
          flex-shrink: 0; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 500;
        }
        .feature-badge.on { background: var(--success-color, #4caf50); color: white; }
        .feature-badge.off { background: var(--disabled-color, #bdbdbd); color: white; }
        .feature-params { padding: 12px 0 0 40px; }
        .cap-mode-cards { display: flex; gap: 12px; margin: 8px 0; }
        .cap-mode-card {
          flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8px;
          padding: 16px 12px; border: 2px solid var(--divider-color); border-radius: 8px;
          cursor: pointer; transition: border-color 0.2s, background 0.2s;
          background: var(--card-background-color);
        }
        .cap-mode-card:hover { border-color: var(--primary-color); }
        .cap-mode-card.selected {
          border-color: var(--primary-color);
          background: var(--primary-color-light, rgba(3,169,244,0.08));
        }
        .cap-mode-card ha-icon { --mdc-icon-size: 28px; color: var(--secondary-text-color); }
        .cap-mode-card.selected ha-icon { color: var(--primary-color); }
        .cap-mode-card span { font-size: 13px; font-weight: 500; text-align: center; }
        .btn-link {
          background: none; border: none; color: var(--primary-color); cursor: pointer;
          font-size: 12px; text-decoration: underline; padding: 0;
        }
        .btn-link:hover { opacity: 0.8; }
        .inverter-test-result {
          display: flex; align-items: center; gap: 8px; padding: 12px;
          border-radius: 8px; font-size: 14px; font-weight: 500;
        }
        .inverter-test-result.success {
          background: rgba(76, 175, 80, 0.1); color: var(--success-color, #4caf50);
        }
        .inverter-test-result.error {
          background: rgba(244, 67, 54, 0.1); color: var(--error-color, #f44336);
        }
        .inverter-test-result ha-icon { --mdc-icon-size: 20px; }
        .ep-value-preview {
          font-size: 12px; color: var(--success-color, #4caf50); margin-top: 4px;
          display: flex; align-items: center; gap: 4px;
        }
        .ep-value-preview.unavailable { color: var(--error-color, #f44336); }
        .ep-container { position: relative; }
        .ep-chevron {
          position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
          color: var(--secondary-text-color); pointer-events: none;
        }
        .ep-container input.entity-input { padding-right: 32px; }
        .ep-dropdown {
          display: none; position: absolute; top: 100%; left: 0; right: 0; z-index: 10;
          max-height: 200px; overflow-y: auto;
          background: var(--card-background-color); border: 1px solid var(--divider-color);
          border-top: none; border-radius: 0 0 4px 4px;
          box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }
        .ep-option {
          padding: 8px 12px; cursor: pointer; display: flex; flex-direction: column;
        }
        .ep-option:hover { background: var(--primary-color-light, rgba(3,169,244,0.08)); }
        .ep-name { font-size: 14px; color: var(--primary-text-color); }
        .ep-id { font-size: 11px; color: var(--secondary-text-color); }
        .prereq-cards .card { box-shadow: none; border: 2px solid var(--divider-color); transition: border-color 0.2s; }
        .forecast-option.selected { border-color: var(--primary-color); background: var(--primary-color-light, rgba(3,169,244,0.08)); }
        /* Dashboard styles */
        .dashboard-grid { display: grid; gap: 16px; }
        .mode-toggle-row { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-bottom: 12px; }
        .mode-toggle-label { font-size: 14px; font-weight: 500; color: var(--primary-text-color); }
        .mode-toggle { position: relative; width: 56px; height: 28px; border-radius: 14px; cursor: pointer; transition: background 0.2s; }
        .mode-toggle.ein { background: var(--success-color, #4caf50); }
        .mode-toggle.test { background: var(--warning-color, #ff9800); }
        .mode-toggle .toggle-knob { position: absolute; top: 3px; width: 22px; height: 22px; border-radius: 50%; background: white; transition: left 0.2s; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
        .mode-toggle.ein .toggle-knob { left: 31px; }
        .mode-toggle.test .toggle-knob { left: 3px; }
        .status-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
        .status-item { display: flex; align-items: center; gap: 8px; }
        .status-item .label { font-size: 14px; color: var(--secondary-text-color); }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 500; color: white; }
        .badge.green { background: var(--success-color, #4caf50); }
        .badge.yellow { background: var(--warning-color, #ff9800); }
        .badge.blue { background: var(--info-color, #2196f3); }
        .badge.orange { background: #ff5722; }
        .badge.gray { background: var(--disabled-color, #9e9e9e); }
        .next-action { font-size: 14px; color: var(--primary-text-color); padding: 8px 0; border-top: 1px solid var(--divider-color); margin-top: 8px; }
        .chart-card { padding: 16px; }
        .chart-card h3 { font-size: 16px; margin: 0 0 12px; color: var(--primary-text-color); }
        .activity-timeline { max-height: 400px; overflow-y: auto; }
        .activity-entry { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--divider-color); }
        .activity-entry:last-child { border-bottom: none; }
        .activity-time { font-size: 13px; font-weight: 500; color: var(--secondary-text-color); min-width: 40px; padding-top: 2px; }
        .activity-dot { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; flex-shrink: 0; }
        .activity-content { flex: 1; min-width: 0; }
        .activity-header { font-size: 14px; color: var(--primary-text-color); }
        .activity-details { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; }
        .activity-badge { font-size: 10px; color: white; padding: 1px 6px; border-radius: 8px; margin-left: 6px; vertical-align: middle; }
        .soc-green { color: var(--success-color, #4caf50); }
        .soc-yellow { color: var(--warning-color, #ff9800); }
        .soc-red { color: var(--error-color, #f44336); }
        .status-cards-row { display: flex; gap: 16px; margin-bottom: 0; }
        .status-cards-row .card { flex: 1; min-width: 260px; }
        .status-indicator { font-weight: 600; margin-bottom: 8px; font-size: 15px; }
        .status-indicator.green { color: var(--success-color, #4caf50); }
        .status-indicator.blue { color: var(--info-color, #2196f3); }
        .status-indicator.red { color: var(--error-color, #f44336); }
        .status-indicator.gray { color: var(--secondary-text-color, #999); }
        .condition-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 14px; }
        .condition-row .check { color: var(--success-color, #4caf50); }
        .condition-row .cross { color: var(--error-color, #f44336); }
        .status-divider { border: none; border-top: 1px solid var(--divider-color, #e0e0e0); margin: 8px 0; }
        /* Discharge condition tiles */
        .cond-tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 4px; }
        .cond-tile { background: var(--secondary-background-color, rgba(0,0,0,0.03)); border-radius: 10px; padding: 10px 12px; }
        .cond-tile-header { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
        .cond-tile-header .check { color: var(--success-color, #4caf50); }
        .cond-tile-header .cross { color: var(--error-color, #f44336); }
        .cond-tile-title { font-weight: 600; font-size: 14px; }
        .cond-tile-sub { font-size: 12px; color: var(--secondary-text-color, #999); margin-bottom: 8px; }
        .cond-tile-bar { position: relative; height: 8px; background: var(--divider-color, #e0e0e0); border-radius: 4px; overflow: visible; margin: 6px 0 4px; }
        .cond-tile-bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s ease; }
        .cond-tile-bar-marker {
          position: absolute; top: -3px; width: 2px; height: 14px;
          background: var(--primary-text-color, #333); border-radius: 1px;
          pointer-events: auto; cursor: help;
        }
        .cond-tile-bar-marker::after {
          content: ""; position: absolute; top: -4px; left: -4px;
          width: 10px; height: 4px; background: var(--primary-text-color, #333); border-radius: 1px;
        }
        .cond-tile-row { display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-top: 4px; }
        .cond-tile-muted { color: var(--secondary-text-color, #999); font-size: 12px; }
        .cond-tile-details-toggle {
          display: inline-flex; align-items: center; gap: 4px; cursor: pointer;
          color: var(--secondary-text-color, #999); font-size: 12px; user-select: none;
          padding: 4px 0; margin-top: 6px;
        }
        .cond-tile-details-toggle:hover { color: var(--primary-text-color, #333); }
        .cond-tile-details-body {
          margin-top: 6px; padding: 10px 12px; background: var(--secondary-background-color, rgba(0,0,0,0.03));
          border-radius: 8px; font-size: 12.5px; color: var(--primary-text-color, #333); line-height: 1.5;
        }
        @media (max-width: 540px) {
          .cond-tiles { grid-template-columns: 1fr; }
        }
        .timestamps-row { display: flex; justify-content: space-between; padding: 4px 8px; font-size: 12px; color: var(--secondary-text-color, #999); }
        .header-card { padding: 16px; }
        .header-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .hlv { display: flex; flex-direction: column; gap: 2px; }
        .hlv-clickable { cursor: pointer; border-radius: 8px; padding: 4px 6px; margin: -4px -6px; transition: background 0.15s; }
        .hlv-clickable:hover { background: var(--secondary-background-color, rgba(0,0,0,0.05)); }
        .hlv-label { font-size: 11px; color: var(--secondary-text-color, #999); text-transform: uppercase; letter-spacing: 0.5px; }
        .hlv-val { font-size: 15px; font-weight: 600; }
        .hlv-val small { font-weight: 400; font-size: 12px; opacity: 0.7; }
        .val-green { color: #4caf50; }
        .val-orange { color: #ff9800; }
        .val-red { color: #f44336; }
        .val-blue { color: #2196f3; }
        .header-toggle-cell { display: flex; flex-direction: row; align-items: center; gap: 8px; justify-content: flex-end; }
        .header-card-top { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
        .header-mode-toggle { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .status-view-pills { display: inline-flex; background: var(--secondary-background-color, rgba(0,0,0,0.05)); border-radius: 999px; padding: 3px; gap: 0; flex-shrink: 0; }
        .view-pill { background: transparent; border: none; cursor: pointer; padding: 6px 12px; border-radius: 999px; color: var(--secondary-text-color, #666); display: inline-flex; align-items: center; justify-content: center; transition: background 0.15s, color 0.15s; }
        .view-pill:hover { color: var(--primary-text-color); }
        .view-pill.active { background: var(--card-background-color, #fff); color: var(--primary-color, #03a9f4); box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .settings-tabs {
          display: flex; gap: 4px; margin-bottom: 16px; padding: 4px;
          background: var(--secondary-background-color, rgba(0,0,0,0.05));
          border-radius: 12px; overflow-x: auto; scrollbar-width: thin;
        }
        .settings-tab {
          flex: 1 1 0; min-width: max-content; background: transparent; border: none; cursor: pointer;
          padding: 10px 12px; border-radius: 8px; color: var(--secondary-text-color, #666);
          display: inline-flex; align-items: center; justify-content: center; gap: 6px;
          font-size: 13px; font-weight: 500; white-space: nowrap;
          transition: background 0.15s, color 0.15s;
        }
        .settings-tab:hover { color: var(--primary-text-color); }
        .settings-tab.active {
          background: var(--card-background-color, #fff);
          color: var(--primary-color, #03a9f4);
          box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        @media (max-width: 540px) {
          .settings-tab span { display: none; }
          .settings-tab { flex: 1 1 0; padding: 10px 8px; }
        }
        .energy-flow-svg { width: 100%; height: auto; max-height: 360px; display: block; }
        .energy-flow-svg .flow-line { stroke-linecap: round; stroke-dasharray: 6 6; animation: flow-anim 1.2s linear infinite; }
        .energy-flow-svg .flow-line.reverse { animation-direction: reverse; }
        @keyframes flow-anim { to { stroke-dashoffset: -24; } }
        .energy-flow-svg .ef-node { cursor: pointer; transition: transform 0.15s; }
        .energy-flow-svg .ef-node:hover { transform: scale(1.04); transform-origin: center; transform-box: fill-box; }
        .energy-flow-svg .ef-flow-label { fill: var(--card-background-color, #fff); stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
        .energy-flow-svg .ef-flow-text { fill: var(--primary-text-color); font-size: 11px; font-weight: 500; pointer-events: none; }
        @media (max-width: 540px) {
          .energy-flow-svg .ef-flow-text { font-size: 13px; }
        }
        .header-timestamps { display: flex; justify-content: space-between; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--divider-color, #e0e0e0); font-size: 11px; color: var(--secondary-text-color, #999); }
        .status-card-title { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 16px; }
        .info-popup-trigger {
          position: relative; display: inline-flex; align-items: center;
        }
        .info-popup {
          display: none; position: absolute; top: calc(100% + 8px); left: 50%;
          transform: translateX(-50%); z-index: 100; width: 380px; max-width: 90vw;
          max-height: 70vh; overflow-y: auto;
          background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
          border: 1px solid var(--divider-color, #e0e0e0); border-radius: 12px;
          padding: 16px; box-shadow: 0 4px 24px rgba(0,0,0,0.15);
          font-size: 13px; font-weight: normal; line-height: 1.5; text-align: left;
        }
        .info-popup strong { display: block; font-size: 14px; margin-bottom: 6px; }
        .info-popup p { margin: 6px 0; }
        .info-popup ul { margin: 6px 0; padding-left: 20px; }
        .info-popup li { margin: 3px 0; }
        .info-popup-trigger:hover .info-popup,
        .info-popup-trigger:focus-within .info-popup,
        .info-popup-trigger.active .info-popup { display: block; }

        /* Info Modal */
        .info-modal-overlay {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.6); z-index: 1000;
          display: flex; align-items: center; justify-content: center;
          padding: 16px;
        }
        .info-modal {
          background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
          border-radius: 16px; width: 850px; max-width: 100%;
          max-height: calc(100vh - 32px); overflow-y: auto;
          padding: 28px; position: relative;
          box-shadow: 0 8px 40px rgba(0,0,0,0.3);
          font-size: 14px; line-height: 1.6;
        }
        .info-modal-close {
          position: sticky; top: 0; float: right;
          background: var(--secondary-background-color, #f5f5f5); border: none;
          width: 36px; height: 36px; border-radius: 50%;
          font-size: 22px; cursor: pointer; z-index: 2;
          color: var(--primary-text-color, #212121);
          display: flex; align-items: center; justify-content: center;
        }
        .info-modal-close:hover { background: var(--divider-color, #e0e0e0); }
        .info-modal-image {
          cursor: pointer; border-radius: 12px; overflow: hidden;
          margin-bottom: 16px; background: #1a1a2e;
        }
        .info-modal-image img { width: 100%; display: block; }
        .info-modal-title { font-size: 18px; margin: 0 0 16px; }
        .info-modal-body strong { display: block; font-size: 14px; margin: 12px 0 6px; }
        .info-modal-body p { margin: 8px 0; }
        .info-modal-body ul { margin: 6px 0; padding-left: 20px; }
        .info-modal-body li { margin: 4px 0; }
        /* Fullscreen image lightbox */
        .info-image-lightbox {
          position: fixed; top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.92); z-index: 1100;
          display: flex; align-items: center; justify-content: center;
          cursor: zoom-out; padding: 16px;
          overflow: auto; touch-action: pan-x pan-y pinch-zoom;
          -webkit-overflow-scrolling: touch;
        }
        .info-image-lightbox img {
          max-width: 100%; max-height: 100%; object-fit: contain;
        }
        .info-image-lightbox-close {
          position: fixed; top: 12px; right: 12px;
          background: rgba(255,255,255,0.15); border: none;
          width: 40px; height: 40px; border-radius: 50%;
          font-size: 24px; cursor: pointer; color: #fff;
          display: flex; align-items: center; justify-content: center;
          z-index: 1101;
        }
        .info-image-lightbox-close:hover { background: rgba(255,255,255,0.3); }
        @media (max-width: 600px) {
          .info-modal-overlay { padding: 0; }
          .info-modal {
            width: 100%; height: 100%; max-height: 100%;
            border-radius: 0; padding: 16px;
          }
          .info-image-lightbox {
            padding: 0; align-items: stretch; justify-content: stretch;
          }
          .info-image-lightbox img {
            max-width: none; max-height: none;
            width: 200%; min-height: 100%;
            object-fit: contain; object-position: left top;
          }
        }
        .dashboard-grid.narrow .status-cards-row { flex-direction: column; }
        .btn-manual-grid { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
        .btn-manual {
          display: flex; flex-direction: column; align-items: center; gap: 8px;
          padding: 16px 20px; border-radius: 12px; border: 1px solid var(--divider-color);
          background: var(--card-background-color); cursor: pointer;
          font-size: 14px; font-weight: 500; color: var(--primary-text-color);
          min-width: 120px; transition: all 0.2s;
        }
        .btn-manual:hover:not([disabled]) { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .btn-manual[disabled] { opacity: 0.5; cursor: not-allowed; }
        .btn-manual ha-icon { --mdc-icon-size: 28px; }
        .btn-manual-normal { border-color: #4caf50; }
        .btn-manual-normal ha-icon { color: #4caf50; }
        .btn-manual-normal:hover:not([disabled]) { background: rgba(76,175,80,0.1); }
        .btn-manual-discharge { border-color: #ff9800; }
        .btn-manual-discharge ha-icon { color: #ff9800; }
        .btn-manual-discharge:hover:not([disabled]) { background: rgba(255,152,0,0.1); }
        .btn-manual-block { border-color: #2196f3; }
        .btn-manual-block ha-icon { color: #2196f3; }
        .btn-manual-block:hover:not([disabled]) { background: rgba(33,150,243,0.1); }
        @keyframes spin { to { transform: rotate(360deg); } }
        .manual-loading {
          display: flex; flex-direction: column; align-items: center; gap: 12px;
          padding: 24px 16px; margin-top: 12px;
          background: var(--secondary-background-color, #f5f5f5); border-radius: 12px;
        }
        .manual-spinner {
          width: 40px; height: 40px; border-radius: 50%;
          border: 4px solid var(--divider-color, #e0e0e0);
          border-top-color: var(--primary-color, #03a9f4);
          animation: spin 0.8s linear infinite;
        }
        .manual-loading span { font-size: 15px; font-weight: 500; }
        .manual-loading-hint { font-size: 12px; font-weight: 400; color: var(--secondary-text-color, #999); }
        .connection-lost { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 60vh; text-align: center; }
        .connection-lost-icon { font-size: 48px; color: var(--warning-color, #ffa726); margin-bottom: 8px; }
        .connection-lost h2 { color: var(--primary-text-color); font-weight: 500; margin: 8px 0; }
        .connection-lost p { color: var(--secondary-text-color, #666); font-size: 14px; margin: 4px 0 24px; }
        .connection-lost-spinner { width: 32px; height: 32px; border: 3px solid var(--divider-color, #e0e0e0); border-top-color: var(--warning-color, #ffa726); border-radius: 50%; animation: conn-spin 1s linear infinite; }
        @keyframes conn-spin { to { transform: rotate(360deg); } }

        /* Energy Flow Diagram */

        /* Live Values Card */
        .val-green { color: #4CAF50; }
        .val-red { color: #f44336; }
        .val-orange { color: #FF9800; }
        .val-blue { color: #2196F3; }
        .toast {
          position: fixed;
          left: 50%;
          bottom: 32px;
          transform: translateX(-50%);
          max-width: min(90vw, 560px);
          padding: 14px 20px;
          border-radius: 10px;
          color: #fff;
          font-size: 14px;
          line-height: 1.45;
          box-shadow: 0 8px 24px rgba(0,0,0,0.25);
          z-index: 9999;
          display: flex;
          align-items: flex-start;
          gap: 12px;
          animation: toast-in 0.22s ease-out;
        }
        .toast-error { background: #c62828; }
        .toast-info { background: #1976d2; }
        .toast-success { background: #2e7d32; }
        .toast-close {
          background: transparent;
          border: none;
          color: rgba(255,255,255,0.9);
          font-size: 18px;
          line-height: 1;
          cursor: pointer;
          padding: 0 0 0 4px;
          margin-left: auto;
        }
        .toast-close:hover { color: #fff; }
        @keyframes toast-in {
          from { opacity: 0; transform: translate(-50%, 12px); }
          to   { opacity: 1; transform: translate(-50%, 0); }
        }
      </style>
      <div class="toolbar">
        <button class="menu-btn" data-action="toggle-sidebar" title="Men\u00fc">
          <ha-icon icon="mdi:menu"></ha-icon>
        </button>
        <h1>EEG Energy Optimizer</h1>
        <div class="toolbar-actions">${headerRight}</div>
      </div>
      ${content}
      ${this._toast ? `
        <div class="toast toast-${this._toast.type}" role="alert">
          <ha-icon icon="mdi:${this._toast.type === "error" ? "alert-circle" : this._toast.type === "success" ? "check-circle" : "information"}"></ha-icon>
          <span>${this._toast.msg}</span>
          <button class="toast-close" data-action="dismiss-toast" title="Schlie\u00dfen">\u00d7</button>
        </div>
      ` : ""}
    `;

    // After innerHTML, populate entity datalists
    if (this._view === "wizard" && this._hass) {
      requestAnimationFrame(() => this._bindEntityPickers());
    }
  }

  disconnectedCallback() {
    window.__eegPanelConnected = false;
    this._disconnectedAt = Date.now();
    if (this._activityUnsub) {
      try { this._activityUnsub(); } catch (_) { /* connection already gone */ }
      this._activityUnsub = null;
    }
    if (this._onVisibilityChange) {
      document.removeEventListener("visibilitychange", this._onVisibilityChange);
    }
    this._stopTelemetryRefresh();
  }

  connectedCallback() {
    this._disconnectedAt = null;
    window.__eegPanelConnected = true;
    // Re-register visibilitychange listener (disconnectedCallback removes it)
    if (this._onVisibilityChange) {
      document.addEventListener("visibilitychange", this._onVisibilityChange);
    }
    // If already initialized before detach, re-init data + subscription
    if (this._hass && this._initialized) {
      console.info("EEG Energy Optimizer: panel reattached, refreshing");
      this._loadConfigPending = false;
      this._loadConfigWithRetry();
    }
    // Start watchdog
    this._startWatchdog();
    this._startTelemetryRefresh();
  }

  _startTelemetryRefresh() {
    this._stopTelemetryRefresh();
    // Backend flusht alle 60 min — wir refreshen den Status alle 60 s,
    // damit Dashboard ("EEG-Statistik: HH:MM:SS") nicht hängenbleibt.
    this._telemetryRefreshInterval = setInterval(() => {
      if (!this._hass || !this._initialized) return;
      this._hass.callWS({ type: "eeg_optimizer/telemetry_get_status" })
        .then(s => {
          const old = this._telemetryStatus || {};
          if (
            old.last_send_at !== s.last_send_at ||
            old.queue_size !== s.queue_size ||
            old.registered !== s.registered
          ) {
            this._telemetryStatus = s;
            this._render();
          } else {
            this._telemetryStatus = s;
          }
        })
        .catch(() => { /* ignore — UI bleibt mit altem Status */ });
    }, 60000);
  }

  _stopTelemetryRefresh() {
    if (this._telemetryRefreshInterval) {
      clearInterval(this._telemetryRefreshInterval);
      this._telemetryRefreshInterval = null;
    }
  }

  _startWatchdog() {
    this._stopWatchdog();
    this._watchdogInterval = setInterval(() => {
      // Disconnection recovery: element was removed from DOM by HA.
      // Check URL NOW (not at disconnect time) — HA updates the URL
      // after removing the element, so we must wait before checking.
      if (!this.isConnected && this._disconnectedAt) {
        const disconnectedFor = Date.now() - this._disconnectedAt;
        if (disconnectedFor > 3000) {
          // User navigated away → URL changed → stop watchdog, no recovery
          if (window.location.pathname !== "/eeg-optimizer") {
            this._disconnectedAt = null;
            this._stopWatchdog();
            return;
          }
          // Check if a new panel instance has connected in the meantime
          if (window.__eegPanelConnected) {
            this._disconnectedAt = null;
            this._stopWatchdog();
            return;
          }
          // No active panel on /eeg-optimizer → reload to recover
          console.warn("EEG: panel removed while on /eeg-optimizer — reloading");
          this._stopWatchdog();
          window.location.reload();
          return;
        }
      }

      // Remaining checks only when tab is visible
      if (document.visibilityState !== "visible" || !this._initialized) return;

      // Check for missing content
      if (this._shadow && !this._shadow.querySelector(".content")) {
        console.warn("EEG: content missing, re-rendering");
        this._render();
      }

      const elapsed = Date.now() - this._lastHassUpdate;
      if (elapsed > 120000) {
        console.warn("EEG: no hass update for " + Math.round(elapsed / 1000) + "s, reloading config");
        this._loadConfigPending = false;
        this._loadConfigWithRetry();
      }
    }, 5000);
  }

  _stopWatchdog() {
    if (this._watchdogInterval) {
      clearInterval(this._watchdogInterval);
      this._watchdogInterval = null;
    }
  }
}

customElements.define("eeg-optimizer-panel", EegOptimizerPanel);

} // end duplicate-load guard
