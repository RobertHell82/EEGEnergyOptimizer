---
phase: 12-solax-charge-block-fix
plan: 01
subsystem: inverter-solax
tags:
  - solax
  - inverter
  - morgen-einspeisung
  - storage
  - migration-v18
  - phase-12
dependency-graph:
  requires:
    - existierender solax_modbus-Driver mit Mode-1-Remote-Control (5-Write-Sequenz)
    - SOLAX_ENTITY_DEFAULTS-Resolver für solax_<key>-Overrides
    - homeassistant.helpers.storage.Store (für persistierten Original-Wert)
  provides:
    - "battery_charge_max_current=0"-basierter Charge-Block (analog Huawei/Fronius)
    - SolaXStateStore-Klasse für persistierten Original-Wert
    - async_stop_forcible mit automatischem Restore aus Store + max-Fallback
    - Config-Migration v17 → v18 mit solax_battery_charge_max_current-Default
  affects:
    - Live-SolaX-Anlagen: Self-Use-Discharge läuft während Morgen-Einspeisung weiter
    - Discharge-Pfad (async_set_discharge) bleibt unverändert auf Mode 1 (Regression-Guard)
tech-stack:
  added:
    - SolaXStateStore (Storage-Persistenz)
  patterns:
    - try/except-Import für Store (Test-Environment-Safe, Pattern wie ActivityLog)
    - Lazy-Cache mit Reboot-Schutz (State=0 darf bestehenden Original-Wert nicht überschreiben)
    - kW → Ampere via Batteriespannung (Fallback 400 V) + Clamp auf attributes.max (Fallback 30 A)
key-files:
  created:
    - .planning/milestones/v1.2-phases/12-solax-charge-block-fix/12-01-SUMMARY.md
  modified:
    - custom_components/eeg_energy_optimizer/inverter/solax.py
    - custom_components/eeg_energy_optimizer/__init__.py
    - custom_components/eeg_energy_optimizer/config_flow.py
    - tests/test_solax_inverter.py
    - tests/test_config_flow.py
    - CHANGELOG.md
decisions:
  - "battery_charge_max_current=0 statt Mode-1-Idle: bringt SolaX auf Huawei/Fronius-Verhalten und ermöglicht Self-Use-Discharge während Morgen-Einspeisung."
  - "Originalwert per Storage persistieren (nicht im Config-Entry): erlaubt Lazy-Erkennung beim ersten Eingriff ohne User-Konfigurationspflicht und überlebt Reboot/Reload."
  - "Reboot-Schutz: aktueller State=0 darf den Store nicht überschreiben. Andernfalls würde ein HA-Restart mitten in der Morgen-Einspeisung den Original-Wert auf 0 fixieren."
  - "Fallback bei leerem Store: attributes.max des battery_charge_max_current-Entities (typisch 30 A für SolaX-HV-Setups). Verhindert Endlos-Block, wenn der Store noch nie befüllt wurde (z.B. Erstinstallation)."
  - "Mode 1 nur noch in async_set_discharge (negative active_power für Slot A/B/Manual). async_set_charge_limit setzt explizit `Disabled`, um Bestands-Setups aus dem alten Mode-1-Idle herauszuziehen."
  - "Test-Fixture _install_noop_store schaltet die Store-Persistenz für Standard-Tests aus, gezielte Tests injizieren FakeStore mit Recording-Verhalten."
metrics:
  duration: "~45min"
  completed: "2026-05-15"
  tasks_completed: 7
  tests_added_or_updated: 16
  tests_total_pass: 463
verification:
  - "✓ Mode 1 entfernt aus async_set_charge_limit (grep `Enabled Battery Control` → nur in async_set_discharge)"
  - "✓ Mode 1 erhalten in async_set_discharge (Regression-Guard via test_discharge_uses_negative_active_power)"
  - "✓ VERSION = 18 in config_flow.py"
  - "✓ entry.version < 18 Migration in __init__.py mit solax_battery_charge_max_current-Default"
  - "✓ `python -m pytest tests/test_solax_inverter.py -v` → 28 passed"
  - "✓ `python -m pytest tests/` → 463 passed, 31 skipped"
  - "✓ battery_charge_max_current 16x in solax.py (Defaults + Methoden-Verwendungen)"
  - "✓ SolaXStateStore 3x in solax.py (Definition + Verwendung)"
must-haves-mapping:
  - id: 12-R1
    truth: "Bei SolaX-Wechselrichtern setzt async_set_charge_limit(0) das Entity battery_charge_max_current auf 0 und remotecontrol_power_control auf Disabled."
    evidence: "solax.py:async_set_charge_limit: _set_number('battery_charge_max_current', 0) + _set_select('remotecontrol_power_control', 'Disabled'). Test test_block_charging_sets_max_current_to_zero verifiziert beide Calls."
  - id: 12-R2
    truth: "Originalwert wird beim ersten Aufruf mit State>0 in Store persistiert; bei State=0 (Reboot mitten im Block) bleibt der Store unverändert."
    evidence: "solax.py:_ensure_original_cached prüft `if self._state_store.original_current is not None: return` und nur `if current > 0` wird gespeichert. Tests test_caches_original_on_first_call + test_skips_cache_when_state_is_zero."
  - id: 12-R3
    truth: "async_stop_forcible deaktiviert Mode 1 explizit und restoriert battery_charge_max_current aus Store (Fallback: attributes.max)."
    evidence: "solax.py:async_stop_forcible ruft _resolve_original_charge_current() und schreibt _set_number('battery_charge_max_current', original). Tests test_stop_forcible_restores_original_from_store + test_stop_forcible_uses_max_fallback_when_no_cache."
  - id: 12-R4
    truth: "Config-Migration v17 → v18 fügt solax_battery_charge_max_current mit Default hinzu, idempotent für Bestands-Anlagen."
    evidence: "__init__.py:async_migrate_entry hat `if entry.version < 18` Block mit setdefault() → idempotent. config_flow.py:VERSION = 18. test_config_flow_version_is_18 + test_version_in_sync_with_migration."
notes:
  - "Bei der Test-Implementierung trat ein subtiler Bug zutage: MagicMock-Instanzen unterstützen `__float__` und liefern per Default 1.0. Das hat den max_a-Fallback (None → 30.0) in `TestKWToAmpsConversion` kurzzeitig auf 1.0 geklemmt. Fix: `mock_hass.states.get = MagicMock(return_value=None)` in den betroffenen Tests."
  - "SolaXStateStore ist test-environment-safe: wenn `homeassistant.helpers.storage.Store` nicht importierbar ist (Test-Env ohne HA-Helpers), wird der Store-Pfad still genoopt (`_store = None`, async_load/save sind No-Ops). Verifiziert durch direkten SolaXStateStore-Konstruktor-Test in TestSolaXStateStore."
  - "Live-Validierung steht aus: ein Test-Update auf Live-SolaX-Instanz und Beobachtung des SOC-Verlaufs während Morgen-Einspeisung über 1–2 Tage ist nötig, um sicherzustellen, dass das Self-Use-Discharge-Verhalten tatsächlich greift und der SOC nicht mehr bei ~19 % stehenbleibt. UAT-Item für /gsd-verify-work."
---

# Plan 12-01 — SolaX Charge-Block via battery_charge_max_current

## Zweck

SolaX-Driver so umgebaut, dass `async_set_charge_limit(0)` nur das Laden blockiert (`battery_charge_max_current = 0`) statt die Batterie via Mode 1 mit `active_power=0` komplett auf Idle zu setzen. Self-Use-Mode des SolaX-Wechselrichters läuft im Hintergrund weiter — Hausverbrauch wird wieder aus der Batterie gedeckt bis `selfuse_discharge_min_soc`, statt aus dem Netz. Bringt die SolaX-Implementierung auf das gleiche Verhalten wie Huawei (`batterien_maximale_ladeleistung=0`) und Fronius (`StorCtl_Mod Bit 0 + InWRte=0`).

Fixt den in der Nacht 14./15. Mai 2026 beobachteten SOC-Einfrierungs-Bug bei ~19 % während Morgen-Einspeisung.

## Was wurde gebaut

### `custom_components/eeg_energy_optimizer/inverter/solax.py`

1. **Import-Guard für `Store`** (Pattern wie `__init__.py` für `ActivityLog`).
2. **Neue Klasse `SolaXStateStore`** — kapselt die Persistierung des Original-`battery_charge_max_current`-Werts:
   - `STORAGE_KEY = "eeg_energy_optimizer.solax_state"`
   - `async_load`/`async_save_original_current`/`original_current`-Property
   - Test-environment-safe: wenn `Store is None`, werden alle I/O-Pfade still genoopt.
3. **`SolaXInverter.__init__`** instanziert `SolaXStateStore(hass)` direkt.
4. **`async_set_charge_limit(power_kw)` komplett neu**:
   - `_ensure_original_cached()` cached den aktuellen `battery_charge_max_current` beim ersten Eingriff (nur wenn > 0 — Reboot-Schutz).
   - `power_kw == 0` → `_set_number("battery_charge_max_current", 0)`.
   - Partial limit → kW über Batteriespannung (Default 400 V) zu A gerechnet, geclampt auf `attributes.max` (Fallback 30 A).
   - Setzt explizit `remotecontrol_power_control = "Disabled"`, um Bestands-Setups aus altem Mode-1-Idle herauszuziehen.
5. **Neue Helper**: `_read_current_charge_max_current`, `_read_max_charge_current_attribute`, `_read_battery_voltage_or_default`, `_resolve_original_charge_current`.
6. **`async_stop_forcible`**: nach der bestehenden Mode-1-Disable-Sequenz wird `battery_charge_max_current` wiederhergestellt — aus Store, sonst Fallback auf `attributes.max`.
7. **`async_set_discharge` bleibt unverändert** — Mode 1 mit negativer `active_power` für Slot A/B/Manual-Discharge (Regression-Guard).

### `custom_components/eeg_energy_optimizer/__init__.py`

Migration-Block v18 angefügt:

```python
if entry.version < 18:
    new_data = {**entry.data}
    new_data.setdefault(
        "solax_battery_charge_max_current",
        "number.solax_inverter_battery_charge_max_current",
    )
    hass.config_entries.async_update_entry(entry, data=new_data, version=18)
```

`setdefault()` macht die Migration idempotent — User mit eigenem Override (Power-User) werden respektiert.

### `custom_components/eeg_energy_optimizer/config_flow.py`

`VERSION = 17` → `VERSION = 18`.

### `tests/test_solax_inverter.py`

16 Tests aktualisiert oder hinzugefügt:

**Phase-12-Verhalten neu**:
- `test_block_charging_sets_max_current_to_zero` — battery_charge_max_current=0 + Disabled, kein "Enabled Battery Control".
- `test_partial_charge_writes_amps_to_max_current` — 3.0 kW → 7.5 A.
- `test_partial_charge_clamped_to_hardware_max` — 20 kW @ 400V (=50 A) wird auf 30 A geclampt.
- `test_caches_original_on_first_call` — erster Eingriff mit State=25 → Store gespeichert.
- `test_skips_cache_when_state_is_zero` — Reboot-Schutz: vorhandene 30.0 wird nicht mit 0 überschrieben.
- `test_stop_forcible_restores_original_from_store` — Restore aus Store.
- `test_stop_forcible_uses_max_fallback_when_no_cache` — leerer Store → attributes.max (30 A).

**kW→A-Umrechnung neu**:
- `TestKWToAmpsConversion::test_fractional_kw_charge` — 2.5 kW → 6.25 A.
- `TestKWToAmpsConversion::test_small_charge_value` — 0.1 kW → 0.25 A.

**Entity-Resolution angepasst**:
- `test_uses_config_override_on_discharge` (alter Charge-5-Write-Test, jetzt auf Discharge umgezogen).
- `test_charge_block_respects_battery_charge_max_current_override` — neuer Test für `solax_battery_charge_max_current`-Override.
- `test_uses_defaults_when_no_config_on_discharge` — Defaults via Discharge.

**SolaXStateStore-Klasse direkt getestet**:
- `test_load_empty_store_yields_none`, `test_save_persists_value`, `test_load_returns_existing_value`.

**Regression-Guard (unverändert)**:
- `TestAsyncSetDischarge` (4 Tests) — Mode 1 mit negativer active_power.
- `TestAsyncStopForcible::test_stop_forcible_disables_mode_one` — Mode-1-Disable-Sequenz.
- `TestIsAvailable` (3 Tests).

### `tests/test_config_flow.py`

`test_version_in_sync_with_migration` und `test_config_flow_version_is_17` → `test_config_flow_version_is_18` mit Assertion `VERSION == 18`.

### `CHANGELOG.md`

Neuer `## Unreleased`-Block über `[1.2.5]` mit Sektionen *Geändert*, *Verhaltensänderung beim Update* und *Migration*.

## Verifikation

Alle Verifikations-Checks aus dem PLAN bestanden:

- Mode 1 in `async_set_charge_limit` entfernt (`grep "Enabled Battery Control"` nur noch in `async_set_discharge`).
- `battery_charge_max_current` 16× in `solax.py`, `SolaXStateStore` 3×.
- `VERSION = 18` in `config_flow.py`, `entry.version < 18`-Migration in `__init__.py`.
- `python -m pytest tests/test_solax_inverter.py -v` → **28 passed**.
- `python -m pytest tests/` → **463 passed, 31 skipped**.

## Self-Check: PASSED

Alle 7 Tasks ausgeführt, atomare Commits pro Task, SUMMARY.md erstellt. Goal-backward-Verifikation der 8 must-haves aus dem PLAN durch Tests + grep-Checks abgedeckt; Live-Validierung an SolaX-Instanz steht als manuelles UAT-Item offen.
