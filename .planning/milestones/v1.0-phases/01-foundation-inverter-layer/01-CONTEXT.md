# Phase 1: Foundation & Inverter Layer - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

HACS-kompatibles Integrations-Skelett mit abstraktem Wechselrichter-Interface und Huawei SUN2000-Implementierung. Die Integration lädt über HACS, definiert einen Inverter-Vertrag, und kann Batterie-SOC lesen sowie Lade-/Entlade-Befehle an einen Huawei SUN2000 senden.

</domain>

<decisions>
## Implementation Decisions

### Integration Identity
- Domain: `eeg_energy_optimizer` → Ordner `custom_components/eeg_energy_optimizer/`
- Anzeigename in HA / HACS: "EEG Energy Optimizer"
- Sprache: Deutsch primär, English als Fallback in `translations/`
- Logo: peakshare.app EWA-Logo als Möglichkeit für HACS-Branding (https://peakshare.app/assets/logo_ewa.png)

### Inverter-Interface
- Drei Schreibbefehle im abstrakten Interface:
  1. **Ladelimit** setzen (kW) — steuert wie viel die Batterie laden darf
  2. **Entladeleistung** setzen (kW) — steuert Entladung ins Netz
  3. **Stopp** — WR zurück in Automatik-Modus
- Lesende Werte (SOC, Kapazität) kommen über HA-Sensor-Entities, nicht über das Interface
- User mapped SOC/Kapazitäts-Sensoren im Config Flow

### Config Flow Ersteinrichtung
- Schritt 1: WR-Typ auswählen (Phase 1: Huawei SUN2000)
- Schritt 2: Basis-Sensoren mappen (SOC, Kapazität, PV-Sensor) via HA Entity-Picker
- Keine Verbindungsdaten nötig — Huawei Solar Integration muss separat installiert sein
- **Harte Validierung**: Setup blockiert wenn die zum WR-Typ passende HA-Integration nicht installiert ist (Huawei Solar bei Huawei, Fronius bei Fronius, etc.)
- Entity-Picker mit device_class Filter für benutzerfreundliche Sensor-Auswahl

### Repo & Code-Struktur
- Eigener Ordner: `custom_components/eeg_energy_optimizer/` — komplett getrennt von bestehender `energieoptimierung/`
- Eigenständiger Code — kein Import aus bestehender Integration, nur als Lese-Referenz für Algorithmen
- Beide Integrationen laufen parallel auf der HA-Instanz
- Standard HACS Layout von Anfang an: `hacs.json`, `README`, `manifest.json` im richtigen Format

### Claude's Discretion
- Technische Architektur des abstrakten Inverter-Interface (Python ABC Design, Method Signatures, Error Handling)
- Interne Code-Struktur und Modul-Aufteilung
- HACS-spezifische Dateien (hacs.json Inhalt, manifest.json Felder)
- Test-Strategie falls gewünscht

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Bestehende Integration (Referenz)
- `custom_components/energieoptimierung/__init__.py` — async_setup_entry Pattern, Timer-Setup, Platform-Forwarding
- `custom_components/energieoptimierung/config_flow.py` — 6-Step Config Flow mit voluptuous, Entity-Selektoren
- `custom_components/energieoptimierung/fronius_api.py` — Fronius Batterie-Steuerung (set_discharge, set_auto_mode) als Referenz für Inverter-Interface Design
- `custom_components/energieoptimierung/const.py` — Konstanten-Organisation, Config-Keys, Defaults
- `custom_components/energieoptimierung/manifest.json` — HA Manifest-Struktur

### Projekt-Dokumentation
- `.planning/PROJECT.md` — Projektkontext, Key Decisions, Constraints
- `.planning/REQUIREMENTS.md` — INF-01 (Abstract Interface), INF-02 (Huawei Impl.), INF-03 (HACS Repo-Struktur)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `fronius_api.py`: Zeigt Inverter-Steuerungs-Pattern (async methods, error handling, mode switching) — dient als Vorlage für das abstrakte Interface
- `config_flow.py`: Mehrstufiger Config Flow mit voluptuous Schemas — Pattern für neuen Config Flow
- `__init__.py`: async_setup_entry mit Platform-Forwarding und Timer — Setup-Pattern übertragbar

### Established Patterns
- Home Assistant config_entries Flow mit `ConfigFlow` + `OptionsFlow`
- `hass.data[DOMAIN]` für Shared State zwischen Platforms
- `async_track_time_interval` für periodische Updates
- voluptuous Schemas für Config-Validierung

### Integration Points
- Huawei Solar HA-Integration: Services `forcible_charge`, `forcible_discharge_soc`, `stop_forcible_charge`
- HA Entity-Registry für Sensor-Auswahl im Config Flow
- HA Integration-Registry für Prerequisite-Prüfung (ist Huawei Solar installiert?)

</code_context>

<specifics>
## Specific Ideas

- Logo von peakshare.app (EWA-Logo) für HACS-Branding: https://peakshare.app/assets/logo_ewa.png
- Bestehende energieoptimierung-Integration läuft weiter und dient als lebende Referenz für Algorithmen
- WR-Typ-Validierung soll WR-spezifisch sein: Huawei prüft auf Huawei Solar, Fronius auf Fronius-Integration etc.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-inverter-layer*
*Context gathered: 2026-03-20*
