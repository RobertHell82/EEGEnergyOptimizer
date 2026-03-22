/**
 * EEG Optimizer Panel - Custom element for HA sidebar panel.
 *
 * Provides dashboard/wizard view toggle and loads config via WebSocket.
 * Wizard: 8-step setup for inverter, prerequisites, sensors, forecasts,
 * consumption, optimizer params, and summary with config save.
 */

const WATCHED = [
  "select.eeg_energy_optimizer_optimizer",
  "sensor.eeg_energy_optimizer_entscheidung",
];

const WIZARD_KEY = "eeg_optimizer_wizard_state";

const WIZARD_STEPS = [
  "Willkommen",
  "Wechselrichter-Typ",
  "Prognose-Integration",
  "Batterie & PV Sensoren",
  "Prognose-Sensoren",
  "Verbrauchssensor",
  "Optimizer-Parameter",
  "Zusammenfassung",
];

const WIZARD_DEFAULTS = {
  inverter_type: "huawei_sun2000",
  battery_soc_sensor: "",
  battery_capacity_sensor: "",
  battery_capacity_kwh: 10,
  pv_power_sensor: "",
  huawei_device_id: "",
  forecast_source: "solcast_solar",
  forecast_remaining_entity: "",
  forecast_tomorrow_entity: "",
  consumption_sensor: "sensor.power_meter_verbrauch",
  lookback_weeks: 8,
  update_interval_fast_min: 1,
  update_interval_slow_min: 15,
  ueberschuss_schwelle: 1.25,
  morning_end_time: "10:00",
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

    // Event delegation on shadow root
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
        if (target.tagName === "SELECT") {
          this._wizardData[field] = target.value;
          // Auto-suggest forecast entities when source changes
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
      case "toggle-advanced":
        const section = dataset?.section || "default";
        this._showAdvanced[section] = !this._showAdvanced[section];
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
    if (step === 1 || step === 2) {
      await this._checkPrerequisites();
      return; // _checkPrerequisites calls _render
    }
    // Load entity picker for sensor steps
    if (step === 3 || step === 4 || step === 5) {
      await this._ensureEntityPicker();
      if (step === 3 && !this._detectedSensors) {
        await this._detectSensors();
        return; // _detectSensors calls _render
      }
    }
    this._render();
  }

  async _nextStep() {
    const valid = this._validateCurrentStep();
    if (!valid) return;

    this._wizardStep = Math.min(WIZARD_STEPS.length - 1, this._wizardStep + 1);
    this._saveWizardProgress();
    await this._refreshStepData();
  }

  _validateCurrentStep() {
    switch (this._wizardStep) {
      case 1: { // Wechselrichter-Typ
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
      case 2: { // Prognose-Integration
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
        return true;
      }
      case 3: // Batterie & PV Sensoren
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
        if (!this._wizardData.pv_power_sensor) {
          this._showValidationError("PV-Sensor ist erforderlich.");
          return false;
        }
        return true;
      case 4: // Prognose-Sensoren
        if (!this._wizardData.forecast_remaining_entity) {
          this._showValidationError("PV Prognose verbleibend heute ist erforderlich.");
          return false;
        }
        if (!this._wizardData.forecast_tomorrow_entity) {
          this._showValidationError("PV Prognose morgen ist erforderlich.");
          return false;
        }
        return true;
      case 5: // Verbrauchssensor
        if (!this._wizardData.consumption_sensor) {
          this._showValidationError("Verbrauchssensor ist erforderlich.");
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
      await this._hass.callWS({
        type: "eeg_optimizer/save_config",
        config: { ...this._wizardData },
      });
      this._clearWizardProgress();
      this._setupComplete = true;
      this._config = { ...this._wizardData };
      this._view = "dashboard";
    } catch (err) {
      console.error("Failed to save config:", err);
      this._wizardData.setup_complete = false;
    }
    this._wizardLoading = false;
    this._render();
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
    this._wizardLoading = false;
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
    if (this._entityPickerLoaded) return;
    if (customElements.get("ha-entity-picker")) {
      this._entityPickerLoaded = true;
      return;
    }
    try {
      const helpers = await window.loadCardHelpers?.();
      if (helpers) {
        await helpers.createCardElement({ type: "entity", entity: "sun.sun" });
      }
      await customElements.whenDefined("ha-entity-picker");
      this._entityPickerLoaded = true;
    } catch (e) {
      console.warn(
        "ha-entity-picker not available, using text inputs as fallback"
      );
    }
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
      for (const eid of WATCHED) {
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
    } catch (err) {
      if (err.code === "not_configured") {
        this._setupComplete = false;
      }
      this._config = null;
    }
    this._initialized = true;
    this._render();
  }

  /* ── Entity picker helper ─────────────────────── */

  _entityPickerHtml(field, value, label, helpText, domain) {
    if (this._entityPickerLoaded) {
      const domainFilter = domain ? ` include-domains='["${domain}"]'` : "";
      return `
        <div class="field-group">
          <label>${label}</label>
          <ha-entity-picker
            data-field="${field}"
            .value="${value || ""}"
            allow-custom-entity
            ${domainFilter}
          ></ha-entity-picker>
          ${helpText ? `<div class="help-text">${helpText}</div>` : ""}
        </div>`;
    }
    // Fallback: plain text input
    return `
      <div class="field-group">
        <label>${label}</label>
        <input type="text" data-field="${field}" value="${value || ""}"
               placeholder="sensor.xxx">
        ${helpText ? `<div class="help-text">${helpText}</div>` : ""}
      </div>`;
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
      case 7:
        stepContent = this._renderStep7();
        break;
    }

    const backBtn =
      step > 0
        ? `<button class="btn-secondary" data-action="prev-step">Zurück</button>`
        : `<div></div>`;

    let forwardBtn = "";
    if (step === 7) {
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
    // Step 1: block if Huawei not installed
    if (step === 1 && this._prerequisites && !this._prerequisites.huawei_solar) {
      return true;
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

    const huaweiAutoDetect = huaweiOk && this._detectedSensors?.detected
      ? '<div style="margin-top:6px;font-size:12px;color:var(--success-color,#4caf50)">✓ Sensoren automatisch erkannt</div>'
      : "";

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
      <button class="btn-secondary" data-action="recheck-prerequisites">Erneut prüfen</button>`;
  }

  /* ── Step 2: Prognose-Integration ─────────────── */

  _renderStep2() {
    const p = this._prerequisites;
    const solcastOk = p && p.solcast_solar;
    const forecastOk = p && p.forecast_solar;
    const noneInstalled = p && !solcastOk && !forecastOk;

    let blockMsg = "";

    const solcastBadge = solcastOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';
    const forecastBadge = forecastOk
      ? '<span class="status-badge installed">Installiert</span>'
      : '<span class="status-badge missing">Nicht installiert</span>';

    const selected = this._wizardData.forecast_source || "";
    const solcastSelected = selected === "solcast_solar";
    const forecastSelected = selected === "forecast_solar";

    return `
      ${blockMsg}
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
      <button class="btn-secondary" data-action="recheck-prerequisites">Erneut prüfen</button>`;
  }

  /* ── Step 3: Batterie & PV Sensoren ───────────── */

  _renderStep3() {
    const detected = this._detectedSensors && this._detectedSensors.detected;

    let detectionInfo = "";
    if (detected) {
      detectionInfo = `
        <div class="success-card">
          Huawei-Sensoren erkannt! Bitte überprüfe die Vorauswahl.
        </div>`;
    }

    const socHelp =
      "Der SOC-Sensor zeigt den aktuellen Ladestand deiner Batterie in Prozent.";
    const capHelp =
      "Zeigt die Gesamtkapazität deiner Batterie. Bei Huawei: Einstellungen → Geräte → Entitäten → ‘Akkukapazität’ aktivieren (ist standardmäßig deaktiviert).";
    const pvHelp = "Sensor für die aktuelle PV-Erzeugungsleistung.";

    return `
      ${detectionInfo}
      ${this._entityPickerHtml(
        "battery_soc_sensor",
        this._wizardData.battery_soc_sensor,
        "SOC-Sensor *",
        socHelp,
        "sensor"
      )}
      ${this._entityPickerHtml(
        "battery_capacity_sensor",
        this._wizardData.battery_capacity_sensor,
        "Kapazitäts-Sensor",
        capHelp,
        "sensor"
      )}
      <div class="field-group">
        <label>Kapazität manuell (kWh)</label>
        <input type="number" data-field="battery_capacity_kwh"
               value="${this._wizardData.battery_capacity_kwh || ""}"
               min="1" max="100" step="0.5"
               placeholder="z.B. 10">
        <div class="help-text">Alternativ: Kapazität manuell eingeben (z.B. 10 für LUNA2000-10, 15 für LUNA2000-15).</div>
      </div>
      ${this._entityPickerHtml(
        "pv_power_sensor",
        this._wizardData.pv_power_sensor,
        "PV-Sensor *",
        pvHelp,
        "sensor"
      )}`;
  }

  /* ── Step 4: Prognose-Sensoren ────────────────── */

  _renderStep4() {
    const p = this._prerequisites || {};
    const solcastOk = p.solcast_solar;
    const forecastOk = p.forecast_solar;

    // Build forecast source options
    let options = "";
    if (solcastOk) {
      options += `<option value="solcast_solar" ${
        this._wizardData.forecast_source === "solcast_solar" ? "selected" : ""
      }>Solcast Solar</option>`;
    }
    if (forecastOk) {
      options += `<option value="forecast_solar" ${
        this._wizardData.forecast_source === "forecast_solar" ? "selected" : ""
      }>Forecast.Solar</option>`;
    }

    // Auto-suggest if entities are still default/empty
    if (
      !this._wizardData.forecast_remaining_entity ||
      this._wizardData.forecast_remaining_entity ===
        SOLCAST_DEFAULTS.forecast_remaining_entity ||
      this._wizardData.forecast_remaining_entity ===
        FORECAST_SOLAR_DEFAULTS.forecast_remaining_entity
    ) {
      this._applyForecastDefaults(this._wizardData.forecast_source);
    }

    return `
      <div class="field-group">
        <label>Prognose-Quelle</label>
        <select data-field="forecast_source">${options}</select>
      </div>
      ${this._entityPickerHtml(
        "forecast_remaining_entity",
        this._wizardData.forecast_remaining_entity,
        "PV Prognose verbleibend heute *",
        "Verbleibende PV-Produktion für den heutigen Tag in kWh.",
        "sensor"
      )}
      ${this._entityPickerHtml(
        "forecast_tomorrow_entity",
        this._wizardData.forecast_tomorrow_entity,
        "PV Prognose morgen *",
        "Prognostizierte PV-Produktion für morgen in kWh.",
        "sensor"
      )}`;
  }

  /* ── Step 5: Verbrauchssensor ─────────────────── */

  _renderStep5() {
    const advOpen = this._showAdvanced["consumption"];

    return `
      ${this._entityPickerHtml(
        "consumption_sensor",
        this._wizardData.consumption_sensor,
        "Verbrauchssensor *",
        "Sensor der den Gesamt-Stromverbrauch in kWh misst (total_increasing).",
        "sensor"
      )}
      <div class="collapsible-header" data-action="toggle-advanced" data-section="consumption">
        <ha-icon icon="mdi:chevron-${advOpen ? "down" : "right"}"></ha-icon>
        Erweitert
      </div>
      ${
        advOpen
          ? `<div class="collapsible-content">
              <div class="field-group">
                <label>Lookback Wochen</label>
                <input type="number" data-field="lookback_weeks"
                       value="${this._wizardData.lookback_weeks}"
                       min="1" max="52">
                <div class="help-text">Anzahl Wochen für den rollenden Verbrauchsdurchschnitt.</div>
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
            </div>`
          : ""
      }`;
  }

  /* ── Step 6: Optimizer-Parameter ──────────────── */

  _renderStep6() {
    const advOpen = this._showAdvanced["optimizer"];

    return `
      <div class="field-group">
        <label>Überschuss-Schwelle</label>
        <input type="number" data-field="ueberschuss_schwelle"
               value="${this._wizardData.ueberschuss_schwelle}"
               min="0.5" max="3.0" step="0.05">
        <div class="help-text">Ab welchem PV/Verbrauch-Verhältnis ein Tag als Überschuss-Tag gilt.</div>
      </div>
      <div class="field-group">
        <label>Morgen-Einspeisung Ende</label>
        <input type="time" data-field="morning_end_time"
               value="${this._wizardData.morning_end_time}">
        <div class="help-text">Bis wann morgens die Batterieladung blockiert wird.</div>
      </div>
      <div class="field-group">
        <label>Entladung Startzeit</label>
        <input type="time" data-field="discharge_start_time"
               value="${this._wizardData.discharge_start_time}">
        <div class="help-text">Ab wann abends die Batterie ins Netz entladen wird.</div>
      </div>
      <div class="field-group">
        <label>Entladeleistung (kW)</label>
        <input type="number" data-field="discharge_power_kw"
               value="${this._wizardData.discharge_power_kw}"
               min="0.5" max="10.0" step="0.5">
        <div class="help-text">Entladeleistung der Batterie in kW.</div>
      </div>
      <div class="collapsible-header" data-action="toggle-advanced" data-section="optimizer">
        <ha-icon icon="mdi:chevron-${advOpen ? "down" : "right"}"></ha-icon>
        Erweitert
      </div>
      ${
        advOpen
          ? `<div class="collapsible-content">
              <div class="field-group">
                <label>Min SOC (%)</label>
                <input type="number" data-field="min_soc"
                       value="${this._wizardData.min_soc}"
                       min="5" max="50">
                <div class="help-text">Minimaler Ladezustand, unter den die Batterie nicht entladen wird.</div>
              </div>
              <div class="field-group">
                <label>Sicherheitspuffer (%)</label>
                <input type="number" data-field="safety_buffer_pct"
                       value="${this._wizardData.safety_buffer_pct}"
                       min="0" max="100" step="5">
                <div class="help-text">Sicherheitsaufschlag auf den Nachtverbrauch bei der Min-SOC Berechnung.</div>
              </div>
            </div>`
          : ""
      }`;
  }

  /* ── Step 7: Zusammenfassung ──────────────────── */

  _renderStep7() {
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
        ${row("SOC-Sensor", d.battery_soc_sensor || "—")}
        ${row(
          "Kapazität",
          d.battery_capacity_sensor
            ? d.battery_capacity_sensor
            : d.battery_capacity_kwh + " kWh (manuell)"
        )}
        ${row("PV-Sensor", d.pv_power_sensor || "—")}
      </div>

      <div class="summary-section">
        <h3>Prognose</h3>
        ${row("Quelle", forecastName)}
        ${row("Verbleibend heute", d.forecast_remaining_entity || "—")}
        ${row("Morgen", d.forecast_tomorrow_entity || "—")}
      </div>

      <div class="summary-section">
        <h3>Verbrauch</h3>
        ${row("Sensor", d.consumption_sensor || "—")}
        ${row("Lookback", d.lookback_weeks + " Wochen")}
      </div>

      <div class="summary-section">
        <h3>Optimizer</h3>
        ${row("Überschuss-Schwelle", d.ueberschuss_schwelle)}
        ${row("Morgen-Ende", d.morning_end_time)}
        ${row("Entlade-Start", d.discharge_start_time)}
        ${row("Leistung", d.discharge_power_kw + " kW")}
        ${row("Min SOC", d.min_soc + " %")}
        ${row("Sicherheitspuffer", d.safety_buffer_pct + " %")}
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
            <div class="card">
              <p>Dashboard wird geladen...</p>
            </div>
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
        .prereq-cards .card { box-shadow: none; border: 2px solid var(--divider-color); transition: border-color 0.2s; }
        .forecast-option.selected { border-color: var(--primary-color); background: var(--primary-color-light, rgba(3,169,244,0.08)); }
      </style>
      <div class="toolbar">
        <h1>EEG Optimizer</h1>
        <div class="toolbar-actions">${headerRight}</div>
      </div>
      ${content}
    `;

    // After innerHTML, wire up ha-entity-pickers with hass object
    if (this._view === "wizard" && this._hass) {
      requestAnimationFrame(() => {
        const pickers = this._shadow.querySelectorAll("ha-entity-picker");
        pickers.forEach((p) => {
          p.hass = this._hass;
          // Set value via property since attribute binding doesn't work for dynamic values
          const field = p.dataset.field;
          if (field && this._wizardData[field]) {
            p.value = this._wizardData[field];
          }
        });
      });
    }
  }
}

customElements.define("eeg-optimizer-panel", EegOptimizerPanel);
