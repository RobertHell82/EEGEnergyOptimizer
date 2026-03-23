/**
 * EEG Optimizer Panel - Custom element for HA sidebar panel.
 *
 * Provides dashboard/wizard view toggle and loads config via WebSocket.
 * Wizard: 8-step setup for inverter, prerequisites, sensors, forecasts,
 * consumption, optimizer params, and summary with config save.
 */

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
  huawei_device_id: "",
  forecast_source: "solcast_solar",
  forecast_remaining_entity: "",
  forecast_tomorrow_entity: "",
  lookback_weeks: 4,
  update_interval_fast_min: 1,
  update_interval_slow_min: 15,
  enable_morning_delay: true,
  morning_end_time: "10:00",
  enable_night_discharge: true,
  discharge_start_time: "20:00",
  discharge_power_kw: 3.0,
  min_soc: 10,
  safety_buffer_pct: 25,
};

const SOLCAST_DEFAULTS = {
  forecast_remaining_entity: "sensor.solcast_pv_forecast_prognose_fuer_heute",
  forecast_tomorrow_entity: "sensor.solcast_pv_forecast_prognose_fuer_morgen",
};

const FORECAST_SOLAR_DEFAULTS = {
  forecast_remaining_entity: "sensor.energy_production_today_remaining",
  forecast_tomorrow_entity: "sensor.energy_production_tomorrow",
};

const DIALOG_CONTENT = {
  huawei: {
    title: "Huawei Solar Integration installieren",
    content: `
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&lsquo;Huawei Solar&rsquo;</strong></li>
        <li>Gib die IP-Adresse deines Wechselrichters ein</li>
        <li>W&auml;hle <strong>&lsquo;Installer&rsquo;</strong> als Verbindungstyp f&uuml;r die Batteriesteuerung</li>
        <li>Starte Home Assistant neu und kehre hierher zur&uuml;ck</li>
      </ol>`,
  },
  solcast: {
    title: "Solcast Solar installieren",
    content: `
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>HACS &rarr; Integrationen &rarr; Suche &lsquo;Solcast PV Forecast&rsquo;</strong></li>
        <li>Installiere die Integration und starte HA neu</li>
        <li>Unter <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Solcast Solar</strong> hinzuf&uuml;gen</li>
        <li>Trage deinen Solcast API-Key ein (kostenlos auf <a href="https://solcast.com" target="_blank">solcast.com</a>)</li>
      </ol>`,
  },
  forecast_solar: {
    title: "Forecast.Solar installieren",
    content: `
      <ol style="padding-left:20px;line-height:1.8">
        <li>Gehe zu <strong>Einstellungen &rarr; Ger&auml;te &amp; Dienste &rarr; Integration hinzuf&uuml;gen</strong></li>
        <li>Suche nach <strong>&lsquo;Forecast.Solar&rsquo;</strong></li>
        <li>Gib deine Anlagen-Daten ein (Neigung, Ausrichtung, kWp)</li>
      </ol>`,
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
};

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
    this._simSocEnabled = false;

    // Event delegation on shadow root
    // Legend hover: highlight matching weekday line
    this._shadow.addEventListener("mouseover", (e) => {
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
      const legendItem = e.target.closest(".wl-legend");
      if (!legendItem) return;
      const svg = legendItem.closest("svg");
      if (!svg) return;
      svg.querySelectorAll(".wl").forEach(g => g.classList.remove("wl-legend-hover"));
    });

    this._shadow.addEventListener("click", (e) => {
      // Close dialog when clicking overlay background (not the card itself)
      if (e.target.classList.contains("dialog-overlay")) {
        this._showDialog = null;
        this._render();
        return;
      }
      const btn = e.target.closest("[data-action]") || e.target;
      const action = btn?.dataset?.action;
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
        const type = target.type;
        if (type === "number") {
          this._wizardData[field] = parseFloat(target.value) || 0;
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

  _handleAction(action, dataset) {
    switch (action) {
      case "start-wizard":
      case "open-wizard":
        this._startWizard();
        break;
      case "back-to-dashboard":
        this._view = "dashboard";
        this._render();
        break;
      case "next-step":
        this._nextStep();
        break;
      case "prev-step":
        this._wizardStep = Math.max(0, this._wizardStep - 1);
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
          power_kw: this._manualDischargeKw || this._config?.discharge_power_kw || 3.0,
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
        if (invValue) {
          this._wizardData.inverter_type = invValue;
          this._render();
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
        const factor = this._simFactor;
        const params = { type: "eeg_optimizer/set_test_overrides", consumption_factor: factor };
        if (this._simSocEnabled && this._simSocOverride !== null) {
          params.soc_override = this._simSocOverride;
        }
        this._hass.callWS(params).then(res => {
          if (res.success) {
            this._simActive = true;
            this._render();
          }
        }).catch(err => console.error("set_test_overrides failed:", err));
        break;
      }
      case "sim-reset":
        this._hass.callWS({ type: "eeg_optimizer/clear_test_overrides" }).then(() => {
          this._simActive = false;
          this._simFactor = 1.0;
          this._simSocOverride = null;
          this._simSocEnabled = false;
          this._render();
        }).catch(err => console.error("clear_test_overrides failed:", err));
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
      // Re-configuration: pre-fill from existing config
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
      if (!this._detectedSensors) {
        await this._detectSensors();
        return; // _detectSensors calls _render
      }
      this._render();
      return;
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
      if (!this._detectedSensors) {
        await this._detectSensors();
        return; // _detectSensors calls _render
      }
    }
    this._render();
  }

  async _nextStep() {
    if (this._navigating) return;
    this._navigating = true;
    try {
      const valid = this._validateCurrentStep();
      if (!valid) return;

      this._wizardStep = Math.min(WIZARD_STEPS.length - 1, this._wizardStep + 1);
      this._saveWizardProgress();
      await this._refreshStepData();
    } finally {
      this._navigating = false;
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
          this._showValidationError("PV Prognose verbleibend heute ist erforderlich.");
          return false;
        }
        if (!this._wizardData.forecast_tomorrow_entity) {
          this._showValidationError("PV Prognose morgen ist erforderlich.");
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
    // Simple alert — could be upgraded to inline message
    const el = this._shadow.querySelector(".validation-error");
    if (el) {
      el.textContent = msg;
      el.style.display = "block";
    }
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

      // Integration reloads after config save — reload panel after a short delay
      // so the new config (with setup_complete=true) is picked up
      setTimeout(() => {
        this._loadConfig();
      }, 2000);
    } catch (err) {
      console.error("Failed to save config:", err);
      this._wizardData.setup_complete = false;
      this._wizardLoading = false;
      this._render();
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
    // Auto-select forecast source based on what's installed
    const p = this._prerequisites;
    if (p) {
      const currentSource = this._wizardData.forecast_source;
      const currentInstalled =
        (currentSource === "solcast_solar" && p.solcast_solar) ||
        (currentSource === "forecast_solar" && p.forecast_solar);
      if (!currentInstalled) {
        // Current selection not installed — pick best available
        if (p.solcast_solar) {
          this._wizardData.forecast_source = "solcast_solar";
          this._applyForecastDefaults("solcast_solar");
        } else if (p.forecast_solar) {
          this._wizardData.forecast_source = "forecast_solar";
          this._applyForecastDefaults("forecast_solar");
        }
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
    const defaults =
      source === "solcast_solar" ? SOLCAST_DEFAULTS : FORECAST_SOLAR_DEFAULTS;
    this._wizardData.forecast_remaining_entity =
      defaults.forecast_remaining_entity;
    this._wizardData.forecast_tomorrow_entity =
      defaults.forecast_tomorrow_entity;
  }

  /* ── Hass / panel setters ─────────────────────── */

  set hass(hass) {
    const firstLoad = this._hass === null;
    const oldHass = this._hass;
    this._hass = hass;

    if (firstLoad) {
      this._loadConfig();
      return;
    }

    // Update entity pickers in shadow DOM with new hass
    if (this._view === "wizard") {
      const pickers = this._shadow.querySelectorAll("ha-entity-picker");
      pickers.forEach((p) => (p.hass = hass));
    }

    // Selective re-render for dashboard: only if watched entities changed
    if (oldHass && this._view === "dashboard") {
      let changed = false;
      const watchList = [...(this._watchedEntities || DEFAULT_WATCHED)];
      if (this._config?.battery_soc_sensor) watchList.push(this._config.battery_soc_sensor);
      if (this._config?.pv_power_sensor) watchList.push(this._config.pv_power_sensor);
      if (this._config?.battery_power_sensor) watchList.push(this._config.battery_power_sensor);
      if (this._config?.grid_power_sensor) watchList.push(this._config.grid_power_sensor);
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
    }

    this._initialized = true;
    this._render();
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
    const total = WIZARD_STEPS.length;
    const progress = ((step + 1) / total) * 100;

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
      const disabled = this._isNextDisabled() ? " btn-disabled" : "";
      forwardBtn = `<button class="btn-primary${disabled}" data-action="next-step">Weiter</button>`;
    }

    return `
      <div class="step-indicator">Schritt ${step + 1} von ${total} — ${WIZARD_STEPS[step]}</div>
      <div class="progress-bar">
        <div class="progress-bar-fill" style="width:${progress}%"></div>
      </div>
      <div class="card">
        <h2>${WIZARD_STEPS[step]}</h2>
        <div class="validation-error" style="display:none;color:var(--error-color,#f44336);margin-bottom:12px;font-size:14px"></div>
        ${this._wizardLoading ? '<div class="loading">Laden...</div>' : stepContent}
        <div class="wizard-nav">
          ${backBtn}
          ${forwardBtn}
        </div>
      </div>`;
  }

  _isNextDisabled() {
    const step = this._wizardStep;
    // Step 1: block if Huawei not installed or Hausverbrauch sensors missing
    if (step === 1) {
      if (this._prerequisites && !this._prerequisites.huawei_solar) return true;
      const d = this._wizardData;
      if (d.inverter_type === "huawei_sun2000" &&
          (!d.pv_power_sensor || !d.battery_power_sensor || !d.grid_power_sensor)) {
        return true;
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
        Diese Integration optimiert deine Hausbatterie für die Energiegemeinschaft (EEG).
        Morgens wird die Batterieladung verzögert, damit Solarstrom ins Netz fließt.
        Abends wird die Batterie ins Netz entladen, wenn genug Reserve für die Nacht bleibt.
      </p>
      <h3 style="margin-bottom:8px">Was du brauchst</h3>
      <ul style="line-height:1.8;margin-bottom:20px;padding-left:20px">
        <li>Einen unterstützten Wechselrichter mit Batteriespeicher</li>
        <li>Eine PV-Prognose-Integration (Solcast Solar oder Forecast.Solar)</li>
      </ul>
      <h3 style="margin-bottom:8px">Getestete Setups</h3>
      <ul style="line-height:1.8;padding-left:20px">
        <li>Huawei SUN2000 mit LUNA2000 Batteriespeicher</li>
      </ul>`;
  }

  /* ── Step 1: Wechselrichter-Typ ───────────────── */

  _renderStep1() {
    const p = this._prerequisites;
    const huaweiOk = p && p.huawei_solar;
    const selected = this._wizardData.inverter_type || "";
    const huaweiSelected = selected === "huawei_sun2000";

    const huaweiBadge = huaweiOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const huaweiAutoDetect = "";

    return `
      <p style="margin-bottom:12px;color:var(--secondary-text-color)">Wähle deinen Wechselrichter-Typ:</p>
      <div class="prereq-cards" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div class="card forecast-option ${huaweiSelected ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-inverter" data-value="huawei_sun2000">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">
            <img src="https://brands.home-assistant.io/huawei_solar/logo.png" alt="Huawei" style="max-width:120px;max-height:60px;height:auto" onerror="this.style.display='none'">
          </div>
          <h3 style="margin:0 0 8px">Huawei SUN2000</h3>
          ${huaweiBadge}
          ${huaweiAutoDetect}
          <button class="btn-secondary" style="margin-top:8px" data-action="show-dialog" data-dialog="huawei">Anleitung</button>
        </div>
        <div class="card forecast-option" style="padding:16px;cursor:default;text-align:center;opacity:0.4">
          <div style="font-size:48px;margin-bottom:8px;color:var(--secondary-text-color)">+</div>
          <h3 style="margin:0 0 8px;color:var(--secondary-text-color)">Weitere folgen</h3>
          <p style="font-size:12px;color:var(--secondary-text-color);margin:0">Fronius, SMA, ...</p>
        </div>
      </div>
      ${huaweiSelected ? `
      <div class="card" style="padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 4px">Hausverbrauch-Sensoren</h3>
        <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 12px">
          Diese Sensoren werden f&uuml;r die Berechnung des Hausverbrauchs verwendet (PV &minus; Batterie &minus; Netz).
        </p>
        ${this._entityPickerHtml(
          "pv_power_sensor",
          this._wizardData.pv_power_sensor,
          "PV-Eingangsleistung *",
          "Aktuelle PV-Produktion in W oder kW (Huawei: sensor.inverter_eingangsleistung).",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "battery_power_sensor",
          this._wizardData.battery_power_sensor,
          "Batterie Lade-/Entladeleistung *",
          "Lade- und Entladeleistung der Batterie in W oder kW (Huawei: sensor.batteries_lade_entladeleistung).",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "grid_power_sensor",
          this._wizardData.grid_power_sensor,
          "Netzbezug/-einspeisung *",
          "Wirkleistung am Netzanschluss in W oder kW (Huawei: sensor.power_meter_wirkleistung).",
          "sensor"
        )}
      </div>
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
    if (
      selected &&
      (!this._wizardData.forecast_remaining_entity ||
        this._wizardData.forecast_remaining_entity === SOLCAST_DEFAULTS.forecast_remaining_entity ||
        this._wizardData.forecast_remaining_entity === FORECAST_SOLAR_DEFAULTS.forecast_remaining_entity)
    ) {
      this._applyForecastDefaults(selected);
    }

    // Sensor fields shown below cards when a source is selected
    const sensorFields = selected ? `
      <div style="margin-top:16px">
        ${this._entityPickerHtml(
          "forecast_remaining_entity",
          this._wizardData.forecast_remaining_entity,
          "Sensor für PV Prognose verbleibend heute *",
          solcastSelected
            ? "Verbleibende PV-Produktion f\u00fcr den heutigen Tag in kWh (Solcast: sensor.solcast_pv_forecast_prognose_fuer_heute)."
            : "Verbleibende PV-Produktion f\u00fcr den heutigen Tag in kWh (Forecast.Solar: sensor.energy_production_today_remaining).",
          "sensor"
        )}
        ${this._entityPickerHtml(
          "forecast_tomorrow_entity",
          this._wizardData.forecast_tomorrow_entity,
          "Sensor für PV Prognose morgen *",
          solcastSelected
            ? "Prognostizierte PV-Produktion f\u00fcr morgen in kWh (Solcast: sensor.solcast_pv_forecast_prognose_fuer_morgen)."
            : "Prognostizierte PV-Produktion f\u00fcr morgen in kWh (Forecast.Solar: sensor.energy_production_tomorrow).",
          "sensor"
        )}
      </div>` : "";

    return `
      <p style="margin-bottom:12px;color:var(--secondary-text-color)">Wähle deine PV-Prognose-Quelle:</p>
      <div class="prereq-cards" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div class="card forecast-option ${forecastSelected ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-forecast" data-value="forecast_solar">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">
            <img src="https://brands.home-assistant.io/forecast_solar/logo.png" alt="Forecast.Solar" style="max-width:100px;max-height:60px;height:auto" onerror="this.style.display='none'">
          </div>
          <h3 style="margin:0 0 8px">Forecast.Solar</h3>
          ${forecastBadge}
          <p style="font-size:13px;color:var(--secondary-text-color);margin:8px 0">Einfachere Einrichtung, keine Registrierung nötig.</p>
          <button class="btn-secondary" data-action="show-dialog" data-dialog="forecast_solar">Anleitung</button>
        </div>
        <div class="card forecast-option ${solcastSelected ? "selected" : ""}" style="padding:16px;cursor:pointer;text-align:center;display:flex;flex-direction:column;align-items:center" data-action="select-forecast" data-value="solcast_solar">
          <div style="height:60px;display:flex;align-items:center;justify-content:center;margin-bottom:8px">
            <img src="https://brands.home-assistant.io/solcast_solar/logo.png" alt="Solcast" style="max-width:100px;max-height:60px;height:auto" onerror="this.style.display='none'">
          </div>
          <h3 style="margin:0 0 8px">Solcast Solar</h3>
          ${solcastBadge}
          <p style="font-size:13px;color:var(--secondary-text-color);margin:8px 0">Genauere Prognosen, kostenloser API-Key erforderlich.</p>
          <button class="btn-secondary" data-action="show-dialog" data-dialog="solcast">Anleitung</button>
        </div>
      </div>
      <button class="btn-secondary" data-action="recheck-prerequisites">Erneut prüfen</button>
      ${sensorFields}`;
  }

  /* ── Step 3: Batteriesensoren ───────────── */

  _renderStep3() {
    const detected = this._detectedSensors && this._detectedSensors.detected;

    let detectionInfo = "";

    const socHelp =
      "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent.";

    // Auto-select capacity mode: if sensor was detected, pick "sensor"; else "manual"
    // Re-evaluate after detection (don't cache stale pre-detection default)
    if (!this._capacityMode || (detected && !this._capacityModeUserSet)) {
      this._capacityMode = this._wizardData.battery_capacity_sensor ? "sensor" : "manual";
    }
    const capSensor = this._capacityMode === "sensor";

    const capSensorHtml = capSensor ? this._entityPickerHtml(
      "battery_capacity_sensor",
      this._wizardData.battery_capacity_sensor,
      "Sensor für Batteriekapazität",
      "Gesamtkapazit\u00e4t der Batterie in kWh oder Wh (Huawei: sensor.batterien_akkukapazitat).",
      "sensor"
    ) : "";

    const capManualHtml = !capSensor ? `
      <div class="field-group">
        <label>Batteriekapazität (in kWh)</label>
        <input type="number" data-field="battery_capacity_kwh"
               value="${this._wizardData.battery_capacity_kwh || ""}"
               min="1" max="100" step="0.5"
               placeholder="z.B. 10">
        <div class="help-text">z.B. 10 für LUNA2000-10, 15 für LUNA2000-15</div>
      </div>` : "";

    return `
      ${detectionInfo}
      ${this._entityPickerHtml(
        "battery_soc_sensor",
        this._wizardData.battery_soc_sensor,
        "Sensor für Batterieladezustand (SOC) *",
        "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent (Huawei: sensor.batteries_batterieladung).",
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
        ${capSensor ? `<div class="help-text" style="margin-top:8px;margin-bottom:8px">
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

    const morningFields = mDelay ? `
      <div class="feature-params">
        <div class="field-group">
          <label>Batterieladung blockiert bis maximal</label>
          <input type="time" data-field="morning_end_time"
                 value="${this._wizardData.morning_end_time}">
          <div class="help-text">Maximal bis zu dieser Uhrzeit wird die Batterieladung morgens blockiert, damit der Strom stattdessen ins Netz eingespeist wird.</div>
        </div>
      </div>` : "";

    const dischargeFields = nDischarge ? `
      <div class="feature-params">
        <div class="field-group">
          <label>Startzeit der Entladung</label>
          <input type="time" data-field="discharge_start_time"
                 value="${this._wizardData.discharge_start_time}">
          <div class="help-text">Ab wann abends die Batterie ins Netz entladen wird.</div>
        </div>
        <div class="field-group">
          <label>Entladeleistung (kW)</label>
          <input type="number" data-field="discharge_power_kw"
                 value="${this._wizardData.discharge_power_kw}"
                 min="0.5" max="10.0" step="0.5">
          <div class="help-text">Leistung der Batterieentladung ins Netz.</div>
        </div>
        <div class="field-group">
          <label>Minimaler Ladezustand (%)</label>
          <input type="number" data-field="min_soc"
                 value="${this._wizardData.min_soc}"
                 min="5" max="50">
          <div class="help-text">Die Einspeisung erfolgt nicht bis zu diesem Ladestand, sondern sorgt dafür, dass dieser Ladestand + der durchschnittliche Verbrauch in der Nacht + Sicherheitspuffer in der Batterie bleibt.</div>
        </div>
      </div>` : "";

    return `
      <p style="margin-bottom:16px;color:var(--secondary-text-color)">
        Wähle aus, welche Optimierungen aktiv sein sollen. Beide können unabhängig voneinander aktiviert werden.
      </p>
      <div class="feature-toggle">
        <div class="feature-card ${mDelay ? "selected" : ""}" data-action="toggle-feature" data-feature="enable_morning_delay">
          <div class="feature-card-header">
            <ha-icon icon="mdi:weather-sunset-up"></ha-icon>
            <div class="feature-card-text">
              <span class="feature-title">Verzögerte Batterieladung</span>
              <span class="feature-desc">Morgens wird die Batterie nicht sofort geladen, sondern die Energie direkt ins Netz und die EEG eingespeist — dort, wo sie zu dieser Zeit am dringendsten gebraucht wird. Das geschieht jedoch nur, wenn die PV-Prognose für den heutigen Tag im Verhältnis zum Verbrauch gut genug ist, damit die Batterie im Laufe des Tages sicher wieder vollgeladen wird.</span>
            </div>
            <div class="feature-badge ${mDelay ? "on" : "off"}">${mDelay ? "Aktiv" : "Aus"}</div>
          </div>
        </div>
        ${morningFields}
      </div>

      <div class="feature-toggle" style="margin-top:16px">
        <div class="feature-card ${nDischarge ? "selected" : ""}" data-action="toggle-feature" data-feature="enable_night_discharge">
          <div class="feature-card-header">
            <ha-icon icon="mdi:battery-arrow-down-outline"></ha-icon>
            <div class="feature-card-text">
              <span class="feature-title">Nachteinspeisung</span>
              <span class="feature-desc">Abends wird überschüssige Energie aus der Batterie ins Netz entladen. Jedoch nur wenn die Prognose des morgigen Tags so gut ist, dass die Batterie morgen wieder vollgeladen werden kann. Und nur so viel, dass man die Nacht auf Basis der bekannten Verbrauchsdaten trotzdem mit dem eigenen Strom auskommt.</span>
            </div>
            <div class="feature-badge ${nDischarge ? "on" : "off"}">${nDischarge ? "Aktiv" : "Aus"}</div>
          </div>
        </div>
        ${dischargeFields}
      </div>

      <div style="margin-top:24px">
        <h3 style="margin:0 0 12px;font-size:16px">Allgemeine Einstellungen</h3>
        <div class="field-group">
          <label>Sicherheitspuffer (%)</label>
          <input type="number" data-field="safety_buffer_pct"
                 value="${this._wizardData.safety_buffer_pct}"
                 min="0" max="100" step="5">
          <div class="help-text">Aufschlag auf den berechneten Energiebedarf. Gilt für beide Optimierungen — sorgt dafür, dass immer eine Reserve eingeplant wird.</div>
        </div>
      </div>`;
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
      </div>`;
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
        ${row("Typ", "Huawei SUN2000")}
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
        ${row("Batterie-Leistung", d.battery_power_sensor || "—")}
        ${row("Netz-Leistung", d.grid_power_sensor || "—")}
      </div>

      <div class="summary-section">
        <h3>Prognose</h3>
        ${row("Quelle", forecastName)}
        ${row("Verbleibend heute", d.forecast_remaining_entity || "—")}
        ${row("Morgen", d.forecast_tomorrow_entity || "—")}
      </div>

      <div class="summary-section">
        <h3>Verzögerte Batterieladung</h3>
        ${row("Status", d.enable_morning_delay ? "Aktiv" : "Deaktiviert")}
        ${d.enable_morning_delay ? row("Blockiert bis", d.morning_end_time) : ""}
      </div>

      <div class="summary-section">
        <h3>Nachteinspeisung</h3>
        ${row("Status", d.enable_night_discharge ? "Aktiv" : "Deaktiviert")}
        ${d.enable_night_discharge ? `
          ${row("Startzeit", d.discharge_start_time)}
          ${row("Leistung", d.discharge_power_kw + " kW")}
          ${row("Min SOC", d.min_soc + " %")}
        ` : ""}
      </div>

      <div class="summary-section">
        <h3>Allgemein</h3>
        ${row("Sicherheitspuffer", d.safety_buffer_pct + " %")}
        ${row("Verbrauchsdurchschnitt", d.lookback_weeks + " Wochen")}
      </div>`;
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
    const mStatus = ma.morning_status || "deaktiviert";
    const dStatus = ma.discharge_status || "deaktiviert";

    // --- Left card: Verzogerte Ladung ---
    let mIndicator = "";
    let mColorClass = "gray";
    let mConditionsHtml = "";

    if (mStatus === "aktiv") {
      mColorClass = "green";
      mIndicator = `\u25CF AKTIV \u2014 Ladung blockiert bis ${ma.morning_end_time || ""}`;
    } else if (mStatus === "nicht_aktiv") {
      mColorClass = "red";
      mIndicator = `\u2715 Nicht aktiv \u2014 PV reicht nicht fuer Bedarf + Puffer`;
    } else if (mStatus === "morgen_erwartet") {
      mColorClass = "blue";
      mIndicator = `\u25CB Morgen ab ${ma.morning_sunrise_tomorrow || ""} (PV ausreichend)`;
    } else if (mStatus === "morgen_nicht_erwartet") {
      mColorClass = "red";
      mIndicator = `\u2715 Morgen nicht geplant \u2014 PV Prognose zu gering`;
    } else {
      mColorClass = "gray";
      mIndicator = `\u2014 Deaktiviert`;
    }

    if (mStatus !== "deaktiviert") {
      const pvVal = ma.morning_pv_today_kwh != null ? Number(ma.morning_pv_today_kwh).toFixed(1) : "---";
      const threshold = ma.morning_threshold_kwh != null ? Number(ma.morning_threshold_kwh).toFixed(1) : "---";
      const consumption = ma.morning_consumption_kwh != null ? Number(ma.morning_consumption_kwh).toFixed(1) : "---";
      const buffer = ma.morning_buffer_kwh != null ? Number(ma.morning_buffer_kwh).toFixed(1) : "---";
      const battery = ma.morning_battery_kwh != null ? Number(ma.morning_battery_kwh).toFixed(1) : "---";
      const pvOk = Number(ma.morning_pv_today_kwh || 0) > Number(ma.morning_threshold_kwh || 0);
      const pvLabel = (mStatus === "morgen_erwartet" || mStatus === "morgen_nicht_erwartet") ? "PV Prognose morgen" : "PV Prognose heute";
      const fensterStart = ma.morning_sunrise_tomorrow || "---";
      const fensterEnd = ma.morning_end_time || "---";

      mConditionsHtml = `
        <hr class="status-divider">
        <div class="condition-row">
          <span>Bedarf SA\u2192SU</span>
          <span>${consumption} kWh</span>
        </div>
        <div class="condition-row">
          <span>Sicherheitspuffer</span>
          <span>${buffer} kWh</span>
        </div>
        <div class="condition-row">
          <span>Batterieladung</span>
          <span>${battery} kWh</span>
        </div>
        <div class="condition-row" style="font-weight:500">
          <span>Gesamtbedarf</span>
          <span>${threshold} kWh</span>
        </div>
        <div class="condition-row">
          <span>${pvLabel}</span>
          <span>${pvVal} kWh <span class="${pvOk ? "check" : "cross"}">${pvOk ? "\u2713" : "\u2717"}</span></span>
        </div>
        <div class="condition-row">
          <span>Fenster</span>
          <span>${fensterStart} bis ${fensterEnd}</span>
        </div>`;
    }

    // --- Right card: Abend-Entladung ---
    let dIndicator = "";
    let dColorClass = "gray";
    let dConditionsHtml = "";

    if (dStatus === "aktiv") {
      dColorClass = "green";
      const pw = ma.discharge_power_kw != null ? Number(ma.discharge_power_kw).toFixed(1) : "---";
      const minSoc = ma.discharge_min_soc != null ? Math.round(Number(ma.discharge_min_soc)) : "---";
      dIndicator = `\u25CF AKTIV \u2014 ${pw} kW Entladung bis ${minSoc}% SOC`;
    } else if (dStatus === "geplant") {
      dColorClass = "blue";
      const minSoc = ma.discharge_min_soc != null ? Math.round(Number(ma.discharge_min_soc)) : "---";
      dIndicator = `\u25CB Geplant ab ${ma.discharge_start_time || ""} bis ${minSoc}% SOC`;
    } else if (dStatus === "nicht_geplant") {
      dColorClass = "red";
      // Build reason text from reasons array
      const reasons = ma.discharge_reasons || [];
      let reasonParts = [];
      reasons.forEach(r => {
        if (r.includes("SOC")) reasonParts.push("SOC zu niedrig");
        if (r.includes("PV")) reasonParts.push("PV morgen nicht ausreichend");
      });
      const reasonText = reasonParts.length > 0 ? reasonParts.join(", ") : "Bedingungen nicht erfuellt";
      dIndicator = `\u2715 Nicht geplant \u2014 ${reasonText}`;
    } else {
      dColorClass = "gray";
      dIndicator = `\u2014 Deaktiviert`;
    }

    if (dStatus !== "deaktiviert") {
      const soc = ma.discharge_soc != null ? Math.round(Number(ma.discharge_soc)) : "---";
      const minSoc = ma.discharge_min_soc != null ? Math.round(Number(ma.discharge_min_soc)) : "---";
      const pvTom = ma.discharge_pv_tomorrow_kwh != null ? Number(ma.discharge_pv_tomorrow_kwh).toFixed(1) : "---";
      const overnightDemand = ma.discharge_demand_overnight_kwh != null ? Number(ma.discharge_demand_overnight_kwh).toFixed(1) : "---";
      const socOk = Number(ma.discharge_soc || 0) > Number(ma.discharge_min_soc || 0);
      const pvOk = Number(ma.discharge_pv_tomorrow_kwh || 0) >= Number(ma.discharge_demand_overnight_kwh || 0);

      const infoTooltip = "Der Ziel-SOC ergibt sich aus: Eingestellter Mindest-SOC + geschätzter Nachtverbrauch (Entladestart bis Sonnenaufgang) + Sicherheitspuffer. So bleibt genug Energie für die Nacht.";

      dConditionsHtml = `
        <hr class="status-divider">
        <div class="condition-row">
          <span>Aktueller SOC</span>
          <span>${soc}% <span class="${socOk ? "check" : "cross"}">${socOk ? "\u2713" : "\u2717"}</span></span>
        </div>
        <div class="condition-row">
          <span>Entlade-Ziel SOC <ha-icon icon="mdi:information-outline" style="--mdc-icon-size:16px;color:var(--secondary-text-color);cursor:help;vertical-align:middle" title="${infoTooltip}"></ha-icon></span>
          <span>${minSoc}%</span>
        </div>
        <div class="condition-row">
          <span>Nachtverbrauch (Entladestart\u2192SA)</span>
          <span>${overnightDemand} kWh</span>
        </div>
        <div class="condition-row">
          <span>PV Prognose morgen</span>
          <span>${pvTom} kWh <span class="${pvOk ? "check" : "cross"}">${pvOk ? "\u2713" : "\u2717"}</span></span>
        </div>`;
      if (dStatus === "aktiv") {
        const pw = ma.discharge_power_kw != null ? Number(ma.discharge_power_kw).toFixed(1) : "---";
        dConditionsHtml += `
        <div class="condition-row">
          <span>Entladeleistung</span>
          <span>${pw} kW</span>
        </div>`;
      }
    }

    return `
      <div class="status-cards-row">
        <div class="card">
          <h3 class="status-card-title" style="margin-top:0">
            <ha-icon icon="mdi:weather-sunny" style="--mdc-icon-size:20px;color:var(--warning-color,#ff9800)"></ha-icon>
            Verz&ouml;gerte Ladung
          </h3>
          <div class="status-indicator ${mColorClass}">${mIndicator}</div>
          ${mConditionsHtml}
        </div>
        <div class="card">
          <h3 class="status-card-title" style="margin-top:0">
            <ha-icon icon="mdi:weather-night" style="--mdc-icon-size:20px;color:var(--info-color,#2196f3)"></ha-icon>
            Abend-Entladung
          </h3>
          <div class="status-indicator ${dColorClass}">${dIndicator}</div>
          ${dConditionsHtml}
        </div>
      </div>`;
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
        bars += `<text x="${x1 + barW/2}" y="${y1 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${d.value.toFixed(1)}</text>`;

        // PV bar (right)
        const pvVal = pvData[i]?.value || 0;
        if (pvVal > 0) {
          const x2 = x1 + barW + gap;
          const barH2 = (pvVal / maxVal) * chartH;
          const y2 = padding.top + chartH - barH2;
          bars += `<rect x="${x2}" y="${y2}" width="${barW}" height="${barH2}" fill="#FF9800" rx="3"/>`;
          bars += `<text x="${x2 + barW/2}" y="${y2 - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${pvVal.toFixed(1)}</text>`;
        }

        // Day label centered under group
        bars += `<text x="${slotX + slotW/2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="var(--secondary-text-color)">${d.label}</text>`;
      } else {
        // Original single-bar rendering
        const x = slotX + (slotW - barW) / 2;
        const barH = (d.value / maxVal) * chartH;
        const y = padding.top + chartH - barH;
        bars += `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" fill="var(--primary-color)" rx="3"/>`;
        bars += `<text x="${x + barW/2}" y="${y - 5}" text-anchor="middle" font-size="11" fill="var(--primary-text-color)">${d.value.toFixed(1)}</text>`;
        bars += `<text x="${x + barW/2}" y="${height - 10}" text-anchor="middle" font-size="11" fill="var(--secondary-text-color)">${d.label}</text>`;
      }
    });

    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = (maxVal * (4 - i) / 4).toFixed(0);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // Legend for grouped bars
    let legend = "";
    if (grouped) {
      const lx = width - padding.right - 200;
      const ly = 14;
      legend += `<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="var(--primary-color)" rx="2"/>`;
      legend += `<text x="${lx + 14}" y="${ly}" font-size="11" fill="var(--primary-text-color)">Verbrauch</text>`;
      legend += `<rect x="${lx + 100}" y="${ly - 8}" width="10" height="10" fill="#FF9800" rx="2"/>`;
      legend += `<text x="${lx + 114}" y="${ly}" font-size="11" fill="var(--primary-text-color)">PV Erzeugung</text>`;
    }

    return `<svg viewBox="0 0 ${width} ${height}" style="width:100%;height:auto;">${yLines}${bars}${legend}</svg>`;
  }

  _renderLineChart(datasets, highlightIndex = 0) {
    if (!datasets || datasets.length === 0) return "<p>Keine Daten verfügbar</p>";
    const width = 700, height = 280, padding = {top: 20, right: 20, bottom: 55, left: 50};
    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const allVals = datasets.flatMap(ds => ds.data);
    const maxVal = Math.max(...allVals, 0.1) * 1.1;

    // Y-axis grid
    let yLines = "";
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      const val = (maxVal * (4 - i) / 4).toFixed(1);
      yLines += `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="var(--divider-color)" stroke-dasharray="4"/>`;
      yLines += `<text x="${padding.left - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--secondary-text-color)">${val}</text>`;
    }

    // X-axis labels
    let xLabels = "";
    for (let h = 0; h < 24; h += 3) {
      const x = padding.left + (h / 23) * chartW;
      xLabels += `<text x="${x}" y="${padding.top + chartH + 15}" text-anchor="middle" font-size="10" fill="var(--secondary-text-color)">${h}:00</text>`;
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
      // Invisible wide hit area for easier hover
      allLines += `<polyline points="${pts}" fill="none" stroke="transparent" stroke-width="12" style="pointer-events:stroke"/>`;
      // Area fill (visible on highlight or hover)
      allLines += `<polygon class="wl-area" points="${areaPts}" fill="${color}" opacity="${isHighlight ? '0.12' : '0'}"/>`;
      // Visible line
      allLines += `<polyline class="wl-line" points="${pts}" fill="none" stroke="${color}" stroke-width="${baseSw}" opacity="${baseOpacity}"/>`;
      allLines += `</g>`;
    });

    // Legend (compact horizontal, below x-axis) — each item is a hoverable group linked to its line
    let legend = "";
    const legendY = height - 8;
    const legendStartX = padding.left;
    const legendSpacing = (width - padding.left - padding.right) / datasets.length;
    datasets.forEach((ds, idx) => {
      const lx = legendStartX + idx * legendSpacing;
      const isHighlight = idx === highlightIndex;
      const color = weekdayColors[idx % weekdayColors.length];
      const fw = isHighlight ? "bold" : "normal";
      const opacity = isHighlight ? "1" : "0.5";
      const sw = isHighlight ? "2.5" : "1.5";
      legend += `<g class="wl-legend" data-idx="${idx}" style="cursor:pointer">`;
      // Invisible wider hit area for easier hover
      legend += `<rect x="${lx - 4}" y="${legendY - 12}" width="${legendSpacing}" height="20" fill="transparent"/>`;
      legend += `<line x1="${lx}" y1="${legendY - 4}" x2="${lx + 14}" y2="${legendY - 4}" stroke="${color}" stroke-width="${sw}" opacity="${opacity}"/>`;
      legend += `<text x="${lx + 18}" y="${legendY}" font-size="10" font-weight="${fw}" fill="var(--primary-text-color)" opacity="${opacity}">${ds.label}</text>`;
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

    const naechsteAktion = decisionState?.attributes?.naechste_aktion || decisionState?.state || "---";
    const energiebedarf = decisionState?.attributes?.energiebedarf_kwh;
    const energiebedarfText = energiebedarf != null ? `${Number(energiebedarf).toFixed(1)} kWh` : "---";

    // --- Metrics ---
    const socSensor = this._config?.battery_soc_sensor;
    const socVal = socSensor ? this._readFloat(socSensor) : null;
    const socText = socVal != null ? `${Math.round(socVal)}` : (socSensor ? "---" : "Nicht konfiguriert");
    const socColorClass = socVal == null ? "" : socVal > 50 ? "soc-green" : socVal >= 25 ? "soc-yellow" : "soc-red";

    // --- PV forecast: read from original Solcast/Forecast.Solar sensors ---
    const forecastTomorrowId = this._config?.forecast_tomorrow_entity || "";
    const forecastRemainingId = this._config?.forecast_remaining_entity || "";

    // Derive prefix from configured sensors
    // Solcast: "sensor.solcast_pv_forecast_prognose_morgen" → prefix "sensor.solcast_pv_forecast_prognose_"
    // Forecast.Solar: "sensor.energy_production_tomorrow" → prefix "sensor.energy_production_"
    let solcastPrefix = "";
    let forecastSolarPrefix = "";
    if (forecastTomorrowId.includes("solcast")) {
      solcastPrefix = forecastTomorrowId.replace(/morgen$/, "");
    } else if (forecastTomorrowId.includes("energy_production")) {
      forecastSolarPrefix = forecastTomorrowId.replace(/tomorrow$/, "");
    }

    // PV total today
    let pvHeute = null;
    if (solcastPrefix) {
      pvHeute = this._readFloat(solcastPrefix + "heute");
    } else if (forecastSolarPrefix) {
      pvHeute = this._readFloat(forecastSolarPrefix + "today");
    }
    if (pvHeute == null) {
      pvHeute = this._readFloat(this._entityIds?.pv_heute || "sensor.eeg_energy_optimizer_pv_prognose_heute");
    }
    const pvHeuteText = pvHeute != null ? `${pvHeute.toFixed(1)}` : "---";

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
    const pvMorgenText = pvMorgen != null ? `${pvMorgen.toFixed(1)}` : "---";

    // 7-day PV forecast array (Solcast provides day 3-7, Forecast.Solar only today+tomorrow)
    const pvWeek = [
      pvHeute || 0,
      pvMorgen || 0,
      solcastPrefix ? (this._readFloat(solcastPrefix + "tag_3") || 0) : 0,
      solcastPrefix ? (this._readFloat(solcastPrefix + "tag_4") || 0) : 0,
      solcastPrefix ? (this._readFloat(solcastPrefix + "tag_5") || 0) : 0,
      solcastPrefix ? (this._readFloat(solcastPrefix + "tag_6") || 0) : 0,
      solcastPrefix ? (this._readFloat(solcastPrefix + "tag_7") || 0) : 0,
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
      const val = this._readFloat(eid);
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
    const _toKw = (entityId) => {
      const val = this._readFloat(entityId);
      if (val == null) return 0;
      const state = this._readState(entityId);
      const unit = state?.attributes?.unit_of_measurement || "";
      return unit === "W" ? val / 1000 : val;
    };
    const pvKw = _toKw(this._config?.pv_power_sensor || "sensor.inverter_eingangsleistung");
    const batKw = _toKw(this._config?.battery_power_sensor || "sensor.batteries_lade_entladeleistung");
    const gridKw = _toKw(this._config?.grid_power_sensor || "sensor.power_meter_wirkleistung");
    const hausKw = this._readFloat("sensor.eeg_energy_optimizer_hausverbrauch") || Math.max(0, pvKw - batKw - gridKw);
    const batLabel = batKw >= 0 ? "Ladung" : "Entladung";
    const batColor = "val-orange";
    const gridLabel = gridKw >= 0 ? "Bezug" : "Einspeisung";
    const gridColor = gridKw >= 0 ? "val-red" : "val-green";
    const socColor = socVal == null ? "" : socVal > 50 ? "val-green" : socVal >= 25 ? "val-orange" : "val-red";

    const fmtTime = (isoStr) => {
      if (!isoStr) return "---";
      try { return new Date(isoStr).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
      catch { return "---"; }
    };
    const optimizerTs = fmtTime(decisionState?.attributes?.letzte_aktualisierung);
    const profilTs = fmtTime(profilState?.last_updated);

    const simBanner = this._simActive ? `
      <div style="background:var(--warning-color, #ff9800);color:#fff;padding:12px 16px;border-radius:12px;
        margin-bottom:16px;display:flex;align-items:center;gap:8px;font-weight:500;flex-wrap:wrap">
        <ha-icon icon="mdi:flask-outline" style="--mdc-icon-size:20px"></ha-icon>
        Simulation aktiv — Verbrauchsfaktor: ${this._simFactor}x${this._simSocOverride !== null ? `, SOC: ${this._simSocOverride}%` : ""}
        <button style="margin-left:auto;background:rgba(255,255,255,0.2);border:none;color:#fff;
          padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px"
          data-action="sim-reset">Zuruecksetzen</button>
      </div>` : "";

    return `
      <div class="dashboard-grid${narrowClass}">
        ${simBanner}
        <!-- Header Card: Toggle + Live Values + Timestamps -->
        <div class="card header-card">
          <div class="header-top">
            <div class="header-live-values">
              <div class="hlv"><span class="hlv-label">PV</span><span class="hlv-val val-green">${pvKw.toFixed(2)} kW</span></div>
              <div class="hlv"><span class="hlv-label">Batterie</span><span class="hlv-val ${batColor}">${Math.abs(batKw).toFixed(2)} kW <small>(${batLabel})</small></span></div>
              <div class="hlv"><span class="hlv-label">SOC</span><span class="hlv-val ${socColor}">${socText}%</span></div>
              <div class="hlv"><span class="hlv-label">Netz</span><span class="hlv-val ${gridColor}">${Math.abs(gridKw).toFixed(2)} kW <small>(${gridLabel})</small></span></div>
              <div class="hlv"><span class="hlv-label">Haus</span><span class="hlv-val val-blue">${hausKw.toFixed(2)} kW</span></div>
            </div>
            <div class="header-toggle">
              <div class="mode-toggle ${modeToggleClass}" data-action="toggle-mode">
                <div class="toggle-knob"></div>
              </div>
              <span class="mode-toggle-label">${modeValue === "Ein" ? "Ein" : "Testmodus"}</span>
            </div>
          </div>
          <div class="header-timestamps">
            <span>Optimizer: ${optimizerTs}</span>
            <span>Verbrauchsdaten: ${profilTs}</span>
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
          <h3>Energieprognose (7 Tage)</h3>
          ${this._renderBarChart(forecastData, pvForecastData)}
        </div>

        <!-- Hourly Profile Chart -->
        <div class="card chart-card">
          <h3>Verbrauchsprofil (Wochentage)</h3>
          ${this._renderLineChart(weekdayDatasets, highlightIdx >= 0 ? highlightIdx : 0)}
        </div>
        `}

        <!-- Manual Control Card -->
        <div class="card">
          <h3 style="margin-top:0">Manuelle Steuerung</h3>
          <p style="color:var(--secondary-text-color);font-size:14px">
            Wechselrichter direkt steuern. Achtung: Der Optimizer &uuml;berschreibt manuelle Befehle im n&auml;chsten Zyklus.
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
              Die manuelle Steuerung ist erst nach Abschluss der Einrichtung verf&uuml;gbar. Bitte zuerst den Wizard abschlie&szlig;en.
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
                  value="${this._manualDischargeKw || this._config?.discharge_power_kw || 3.0}"
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
        </div>

        <!-- Simulation Card -->
        ${this._config?.setup_complete ? `
        <div class="card">
          <h3 style="margin-top:0">
            <ha-icon icon="mdi:flask-outline" style="--mdc-icon-size:20px;vertical-align:middle"></ha-icon>
            Simulation
          </h3>
          <p style="color:var(--secondary-text-color);font-size:14px">
            Verbrauchswerte skalieren und SOC ueberschreiben, um Optimizer-Entscheidungen zu testen.
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
              style="flex:1">
              <ha-icon icon="mdi:play"></ha-icon>
              <span>Anwenden</span>
            </button>
            <button class="btn-manual btn-manual-normal" data-action="sim-reset"
              style="flex:1" ${!this._simActive ? "disabled" : ""}>
              <ha-icon icon="mdi:restore"></ha-icon>
              <span>Zuruecksetzen</span>
            </button>
          </div>
          ${this._simActive ? `
            <div class="help-text" style="margin-top:12px;color:var(--warning-color, #ff9800)">
              <ha-icon icon="mdi:alert-outline" style="--mdc-icon-size:16px;vertical-align:middle"></ha-icon>
              Override aktiv. Werte werden im naechsten Optimizer-Zyklus (60s) angewendet.
            </div>
          ` : ""}
        </div>
        ` : ""}

      </div>`;
  }

  /* ── Main render ──────────────────────────────── */

  _render() {
    if (!this._initialized) return;

    let headerRight = "";
    if (this._setupComplete && this._view === "dashboard") {
      headerRight = `
        <button data-action="open-wizard" title="Einstellungen">
          <ha-icon icon="mdi:cog"></ha-icon>
        </button>`;
    } else if (this._view === "wizard") {
      headerRight = `
        <button data-action="back-to-dashboard" title="Zurück">
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
          </div>`;
      }
    } catch (err) {
      console.error("EEG Optimizer render error:", err);
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
        .toolbar h1 { font-size: 20px; font-weight: 400; margin: 0; }
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
        .step-indicator { text-align: center; margin-bottom: 16px; color: var(--secondary-text-color); font-size: 14px; }
        .progress-bar { height: 4px; background: var(--divider-color); border-radius: 2px; margin-bottom: 24px; }
        .progress-bar-fill { height: 100%; background: var(--primary-color); border-radius: 2px; transition: width 0.3s; }
        .field-group { margin-bottom: 16px; }
        .field-group label { display: block; font-weight: 500; margin-bottom: 4px; color: var(--primary-text-color); }
        .field-group .help-text { font-size: 12px; color: var(--secondary-text-color); margin-top: 4px; }
        .field-group input, .field-group select {
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
          padding: 24px; max-width: 500px; width: 90%; max-height: 80vh; overflow-y: auto;
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
          color: var(--primary-color); border-radius: 4px; padding: 8px 16px; cursor: pointer;
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
        .timestamps-row { display: flex; justify-content: space-between; padding: 4px 8px; font-size: 12px; color: var(--secondary-text-color, #999); }
        .header-card { padding: 16px; }
        .header-top { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
        .header-live-values { display: flex; flex-wrap: wrap; gap: 12px 20px; flex: 1; }
        .hlv { display: flex; flex-direction: column; gap: 2px; min-width: 70px; }
        .hlv-label { font-size: 11px; color: var(--secondary-text-color, #999); text-transform: uppercase; letter-spacing: 0.5px; }
        .hlv-val { font-size: 15px; font-weight: 600; }
        .hlv-val small { font-weight: 400; font-size: 12px; opacity: 0.7; }
        .val-green { color: #4caf50; }
        .val-orange { color: #ff9800; }
        .val-red { color: #f44336; }
        .val-blue { color: #2196f3; }
        .header-toggle { display: flex; flex-direction: column; align-items: center; gap: 4px; }
        .header-timestamps { display: flex; justify-content: space-between; margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--divider-color, #e0e0e0); font-size: 11px; color: var(--secondary-text-color, #999); }
        .dashboard-grid.narrow .header-top { flex-direction: column; }
        .dashboard-grid.narrow .header-toggle { flex-direction: row; }
        .status-card-title { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: 16px; }
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
      </style>
      <div class="toolbar">
        <h1>EEG Optimizer</h1>
        <div class="toolbar-actions">${headerRight}</div>
      </div>
      ${content}
    `;

    // After innerHTML, populate entity datalists
    if (this._view === "wizard" && this._hass) {
      requestAnimationFrame(() => this._bindEntityPickers());
    }
  }
}

customElements.define("eeg-optimizer-panel", EegOptimizerPanel);
