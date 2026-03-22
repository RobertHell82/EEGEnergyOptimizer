/**
 * EEG Optimizer Panel - Shell custom element for HA sidebar panel.
 *
 * Provides dashboard/wizard view toggle and loads config via WebSocket.
 * Dashboard and wizard content are filled by subsequent plans.
 */

const WATCHED = [
  "select.eeg_energy_optimizer_optimizer",
  "sensor.eeg_energy_optimizer_entscheidung",
];

class EegOptimizerPanel extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: "open" });
    this._hass = null;
    this._view = "dashboard";
    this._config = null;
    this._setupComplete = false;
    this._wizardStep = 0;
    this._wizardData = {};
    this._narrow = false;
    this._initialized = false;

    // Event delegation on shadow root
    this._shadow.addEventListener("click", (e) => {
      const action = e.target.dataset?.action;
      if (!action) {
        // Check parent elements for data-action
        const btn = e.target.closest("[data-action]");
        if (btn) {
          this._handleAction(btn.dataset.action);
        }
        return;
      }
      this._handleAction(action);
    });
  }

  _handleAction(action) {
    switch (action) {
      case "start-wizard":
      case "open-wizard":
        this._view = "wizard";
        this._render();
        break;
      case "back-to-dashboard":
        this._view = "dashboard";
        this._render();
        break;
    }
  }

  set hass(hass) {
    const firstLoad = this._hass === null;
    const oldHass = this._hass;
    this._hass = hass;

    if (firstLoad) {
      this._loadConfig();
      return;
    }

    // Selective re-render: only if watched entities changed
    if (oldHass) {
      let changed = false;
      for (const eid of WATCHED) {
        const oldState = oldHass.states[eid];
        const newState = hass.states[eid];
        if (oldState !== newState) {
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
          <div id="wizard-root">
            <div class="card">
              <p>Wizard wird geladen...</p>
            </div>
          </div>
        </div>`;
    } else if (!this._setupComplete) {
      content = `
        <div class="content">
          <div class="card setup-card">
            <ha-icon icon="mdi:solar-power" class="setup-icon"></ha-icon>
            <h2>Setup noch nicht abgeschlossen</h2>
            <p>Richte den EEG Energy Optimizer ein, um die Batteriesteuerung für deine Energiegemeinschaft zu optimieren.</p>
            <button class="btn-primary" data-action="start-wizard">Setup starten</button>
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
        .toolbar h1 {
          font-size: 20px;
          font-weight: 400;
          margin: 0;
        }
        .toolbar button {
          background: none;
          border: none;
          color: inherit;
          cursor: pointer;
          padding: 8px;
          border-radius: 50%;
        }
        .toolbar button:hover {
          background: rgba(255, 255, 255, 0.1);
        }
        .toolbar ha-icon {
          --mdc-icon-size: 24px;
        }
        .content {
          padding: 16px;
          max-width: 900px;
          margin: 0 auto;
        }
        .card {
          background: var(--card-background-color, #fff);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,0.1));
          padding: 24px;
        }
        .setup-card {
          text-align: center;
          padding: 48px 24px;
        }
        .setup-card .setup-icon {
          --mdc-icon-size: 64px;
          color: var(--primary-color);
          margin-bottom: 16px;
        }
        .setup-card h2 {
          color: var(--primary-text-color);
          margin-bottom: 16px;
          font-size: 24px;
          font-weight: 400;
        }
        .setup-card p {
          color: var(--secondary-text-color);
          margin-bottom: 24px;
          line-height: 1.5;
        }
        .btn-primary {
          background: var(--primary-color);
          color: var(--text-primary-color);
          border: none;
          border-radius: 4px;
          padding: 12px 32px;
          cursor: pointer;
          font-size: 16px;
          font-weight: 500;
          transition: opacity 0.2s;
        }
        .btn-primary:hover {
          opacity: 0.9;
        }
      </style>
      <div class="toolbar">
        <h1>EEG Optimizer</h1>
        <div class="toolbar-actions">
          ${headerRight}
        </div>
      </div>
      ${content}
    `;
  }
}

customElements.define("eeg-optimizer-panel", EegOptimizerPanel);
