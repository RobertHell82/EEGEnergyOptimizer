# Phase 12 — SolaX Charge-Block ohne Battery-Idle

**Inserted:** 2026-05-15
**After:** Phase 11.1 (PeakShare-Steuerung der Slot-A/B-Fenster, verified)
**Trigger:** User-Observation auf SolaX-Live-Anlage — SOC bei ~19 % eingefroren in der Nacht 14./15. Mai trotz `selfuse_discharge_min_soc=10 %`.

## Diagnose

### Beobachtetes Symptom

User-Report (2026-05-15): „in der früh war die batterie immer leer ... kann es sein, dass wir davon ausgehen, dass die batterie bis 10 % entladen wird, aber bei 19% oder 20% irgendwie abriegelt?"

### Datengrundlage (HA Activity Log + REST API, beide Nächte)

**SolaX-Wechselrichter-Konfiguration (in beiden Nächten unverändert):**
- `select.solax_inverter_charger_use_mode` = "Self Use Mode"
- `number.solax_inverter_selfuse_discharge_min_soc` = 10
- `number.solax_inverter_backup_discharge_min_soc` = 20
- `number.solax_inverter_feedin_discharge_min_soc` = 15
- `number.solax_inverter_battery_charge_max_current` = 30 A (= Hardware-Max, bei ~488 V Batteriespannung ≈ 14,6 kW)

**Nacht 13./14. Mai — Batterie fiel sauber bis 10 %:**

| Zeit (lokal) | SOC | Zustand | min_soc (dyn) |
|---|---|---|---|
| 20:00 | 99 % | Normal | 75 |
| 22:39 | ~74 % | Nacht-Entladung Slot A (PeakShare 22:39–00:39) | 47 |
| 00:39 | ~55 % | Slot A endet → Normal | 47 |
| 04:20 | 40 % | Slot B aktiv (PeakShare 04:20–05:20) | 22 |
| 04:51 | 20 % | Slot B endet → Normal | 20 |
| 05:00 | 20 % | Normal (= Self-Use läuft, KEINE Morgen-Einspeisung) | 19 |
| 07:00 | **10 %** | Normal — Self-Use erreicht `selfuse_discharge_min_soc` ✓ | 77 |

→ Verhalten korrekt. Keine Morgen-Einspeisung wurde aktiviert, Self-Use entlud weiter bis `selfuse_discharge_min_soc = 10 %`.

**Nacht 14./15. Mai — SOC eingefroren bei 19 %:**

| Zeit (lokal) | SOC | Zustand | min_soc (dyn) |
|---|---|---|---|
| 20:00 | 95 % | Normal | 77 |
| 20:39 | 91 % | Nacht-Entladung Slot A (PeakShare 20:39–23:39) | 72 |
| 21:16 | 77 % | Slot A pausiert (Schmitt-Trigger) | 67 |
| 22:39 | 69 % | Slot A wieder aktiv (PeakShare 22:39–00:39) | 59 |
| 23:23 | 45 % | Slot A endet (SOC < dyn_min_soc 54) | 54 |
| 03:00 | 29 % | Normal (Slot B nicht aktiviert: SOC < min_soc 31) | 31 |
| 05:00 | 21 % | Normal (Self-Use läuft, SOC fällt) | 20 |
| **05:24** | **19 %** | **"Morgen-Einspeisung bis 11:00" startet** | 76 |
| 06:00–11:00 | **19 %** (eingefroren) | Morgen-Einspeisung | 76 |

→ Ab 05:24 friert SOC bei 19 % ein. Hausverbrauch (gemessen ~3 kW im Schnitt) wird AUS DEM NETZ bezogen, NICHT aus der Batterie.

### Root-Cause

`custom_components/eeg_energy_optimizer/inverter/solax.py:75–96` (`async_set_charge_limit(0)`):

```python
async def async_set_charge_limit(self, power_kw: float) -> bool:
    if power_kw == 0:
        await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
        await self._set_number("remotecontrol_active_power", 0)
    # ...
    await self._set_number("remotecontrol_duration", 300)
    await self._set_number("remotecontrol_autorepeat_duration", 60)
    await self._press_trigger()
```

Beim Auslösen von `STATE_MORGEN_EINSPEISUNG` (siehe `optimizer.py:1940-1941`) wird auf der SolaX:
1. `remotecontrol_power_control = "Enabled Battery Control"` gesetzt → Mode 1 aktiv
2. `remotecontrol_active_power = 0` → Batterie weder Laden noch Entladen (Idle)
3. `autorepeat_duration = 60` s → Wiederholung alle 60 s

Im Mode 1 mit `active_power = 0` ignoriert die SolaX den Self-Use-Mode und hält die Batterie statisch — auch wenn `selfuse_discharge_min_soc = 10 %` und SOC > 10 % wäre.

History-Bestätigung via REST-API (Sensor `sensor.solax_inverter_modbus_power_control`):
- 14.5. 18:00 UTC: "Disabled"
- 14.5. 18:39 UTC: "Enabled Power Control" (Slot A Discharge)
- 14.5. 19:16 UTC: "Disabled"
- 14.5. 20:39 UTC: "Enabled Power Control" (Slot A Re-Aktivierung)
- 14.5. 21:23 UTC: "Disabled"
- **15.5. 03:24 UTC: "Enabled Power Control" (Morgen-Einspeisung — bleibt 5+ Stunden aktiv)**

## Vergleich mit Huawei und Fronius

| Inverter | Bei `set_charge_limit(0)` | Verhalten der Batterie |
|---|---|---|
| **Huawei** (`huawei.py:54-73`) | Setzt `number.batterien_maximale_ladeleistung = 0` W | Self-Use läuft normal — Discharge frei bis HA-konfigurierte Untergrenze |
| **Fronius** (`fronius.py:327-339`) | Setzt SunSpec Model 124 `StorCtl_Mod = 1` (Bit 0 = Charge-Limit) + `InWRte = 0` (0 % Charge-Rate). Bit 1 (Discharge-Limit) bleibt 0. | Self-Use läuft normal — Discharge nicht beeinflusst |
| **SolaX** (`solax.py:75-96`) | Setzt Mode 1 + `active_power = 0` W | **Batterie idle — weder Laden noch Entladen** ❌ |

Die SolaX-Implementierung ist die einzige, die den natürlichen Self-Use-Mode überschreibt. Huawei und Fronius blockieren nur das Laden — Discharge bleibt unberührt.

## Ziel Phase 12

`SolaXInverter.async_set_charge_limit(0)` so umbauen, dass es analog zu Huawei und Fronius funktioniert:
- Nur das **Laden** wird blockiert (Mode 1 NICHT mehr aktiv).
- Self-Use-Mode läuft im Hintergrund weiter — Hausverbrauch kommt aus der Batterie bis `selfuse_discharge_min_soc = 10 %`.
- Beim Verlassen von Morgen-Einspeisung wird der Originalwert von `battery_charge_max_current` wiederhergestellt.

## Locked design answers (User-Diskussion 2026-05-15)

| # | Frage | Antwort |
|---|-------|---------|
| 1 | Welcher Hebel statt Mode 1? | `number.solax_inverter_battery_charge_max_current = 0` — entspricht 1:1 dem Huawei-Ansatz. |
| 2 | Wie wird der Originalwert ermittelt? | Beim ersten Eingriff State lesen, **nur wenn > 0** cachen. So bleibt der Cache bei Reboot-mitten-im-Block-State korrekt. |
| 3 | Persistierung des Originalwerts? | `homeassistant.helpers.storage.Store` (Variante b aus dem Designgespräch) — überlebt HA-Reboots. |
| 4 | Fallback bei leerem Store? | `attributes.max` des Entities (= 30 A bei aktueller Anlage, hardware-konfiguriertes Maximum). |
| 5 | Migration nötig? | Ja — Config-Version v12 → v13, neuer Key `solax_battery_charge_max_current` mit Default-Entity-ID. |
| 6 | `async_set_discharge` anpassen? | Nein. Mode 1 mit negativer Power funktioniert für Discharge korrekt. Nur `set_charge_limit` betroffen. |
| 7 | `async_stop_forcible` anpassen? | Ja. Muss zusätzlich zum Disable-of-Mode-1 den `battery_charge_max_current` aus dem Store restorieren. |
| 8 | UI-Change im Panel? | Nein. Kein User-sichtbares Setting. Der neue Config-Key ist intern (Entity-ID-Override für Power-User, analog zu den existierenden `solax_remotecontrol_*` Keys). |

## Implementierungs-Hinweise (für Plan-Phase)

### Storage-Schema

Storage-Key: `eeg_energy_optimizer.solax_inverter_state` (oder pro Config-Entry separat)

```json
{
  "version": 1,
  "battery_charge_max_current_original": 30.0
}
```

- `version`: für künftige Schema-Migrationen
- `battery_charge_max_current_original`: gecachter Originalwert in A

### `async_set_charge_limit(power_kw)` — neues Verhalten

```python
async def async_set_charge_limit(self, power_kw: float) -> bool:
    try:
        # Cache Original (nur wenn State > 0 — Reboot-Schutz)
        await self._ensure_original_cached()

        if power_kw == 0:
            # Block Laden via battery_charge_max_current = 0
            await self._set_number("battery_charge_max_current", 0)
        else:
            # Partial Limit — power_kw über Batteriespannung in A umrechnen
            voltage = self._read_battery_voltage()  # default 400V wenn unbekannt
            amps = min(power_kw * 1000 / voltage, self._max_charge_current_a)
            await self._set_number("battery_charge_max_current", amps)

        # Sicherstellen, dass Mode 1 NICHT aktiv ist
        await self._set_select("remotecontrol_power_control", "Disabled")
        return True
    except Exception:
        _LOGGER.exception("SolaX: Failed to set charge limit")
        return False
```

### `async_stop_forcible()` — Restore aus Store

```python
async def async_stop_forcible(self) -> bool:
    try:
        # Mode-1-Discharge sauber beenden
        await self._set_select("remotecontrol_power_control", "Disabled")
        await self._set_number("remotecontrol_active_power", 0)
        await self._set_number("remotecontrol_duration", 20)
        await self._set_number("remotecontrol_autorepeat_duration", 0)
        await self._press_trigger()

        # battery_charge_max_current wiederherstellen
        original = self._charge_current_original
        if original is None:
            # Fallback: attributes.max des Entities
            original = self._get_entity_max_a() or 30.0
        await self._set_number("battery_charge_max_current", original)
        return True
    except Exception:
        _LOGGER.exception("SolaX: Failed to stop forcible mode")
        return False
```

### Storage-Helper

```python
class SolaXStateStore:
    """Persistiert den Original-Wert von battery_charge_max_current über HA-Reboots."""

    STORAGE_KEY = "eeg_energy_optimizer.solax_state"
    STORAGE_VERSION = 1

    def __init__(self, hass):
        self._store = Store(hass, self.STORAGE_VERSION, self.STORAGE_KEY)
        self._data: dict = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self._data = data or {}

    async def async_save_original_current(self, amps: float) -> None:
        self._data["battery_charge_max_current_original"] = amps
        await self._store.async_save(self._data)

    @property
    def original_current(self) -> float | None:
        return self._data.get("battery_charge_max_current_original")
```

### Migration v12 → v13

```python
# __init__.py — async_migrate_entry
if config_entry.version < 13:
    new_data = dict(config_entry.data)
    new_data.setdefault(
        "solax_battery_charge_max_current",
        "number.solax_inverter_battery_charge_max_current",
    )
    hass.config_entries.async_update_entry(
        config_entry, data=new_data, version=13
    )
```

### Tests

| Test | Was prüft er |
|---|---|
| `test_solax_charge_limit_zero_sets_max_current_to_0` | `set_charge_limit(0)` schreibt `battery_charge_max_current = 0` |
| `test_solax_charge_limit_zero_disables_remote_control` | Nach `set_charge_limit(0)` ist `remotecontrol_power_control = "Disabled"` |
| `test_solax_charge_limit_caches_original_on_first_call` | Erster Eingriff cached den Originalwert im Store |
| `test_solax_charge_limit_skips_cache_when_state_is_zero` | Reboot-Schutz: wenn aktueller State 0 ist, wird Cache nicht überschrieben |
| `test_solax_stop_forcible_restores_original_current` | `stop_forcible` schreibt gecachten Originalwert |
| `test_solax_stop_forcible_uses_max_fallback_when_no_cache` | Wenn Store leer, wird `attributes.max` (30) genutzt |
| `test_solax_set_discharge_unchanged` | `set_discharge` nutzt weiterhin Mode 1 mit negativer Power (regression guard) |
| `test_migration_v12_to_v13_adds_charge_current_key` | Migration fügt neuen Config-Key mit Default-Entity-ID hinzu |

### CHANGELOG

Neuer Eintrag unter "Unreleased" (Patch-Version bleibt User-Entscheidung):

```markdown
### Geändert
- **SolaX:** Morgen-Einspeisung blockiert jetzt nur noch das Laden statt die Batterie komplett auf Idle zu setzen. Hausverbrauch wird wieder aus der Batterie gedeckt (bis `selfuse_discharge_min_soc`), nicht mehr aus dem Netz. Bringt das SolaX-Verhalten auf gleiches Niveau wie Huawei/Fronius.

### Verhaltensänderung beim Update
- Auf SolaX-Anlagen: Während Morgen-Einspeisung wird die Batterie nicht mehr eingefroren. Wenn vorher SOC bei ~19 % stehenblieb (siehe Phase-12-Diagnose), entlädt sie jetzt weiter bis zum konfigurierten `selfuse_discharge_min_soc`.
```

## Out-of-Phase

- Huawei/Fronius/SolarEdge bleiben unverändert — Verhalten dort bereits korrekt.
- Kein neues User-sichtbares Setting im Panel.
- `async_set_discharge` (Slot A/B / Manual Discharge) bleibt auf Mode 1 mit negativer Power.

## Project-Referenzen

- Quellcode-Anker: `custom_components/eeg_energy_optimizer/inverter/solax.py:75-96` (set_charge_limit), `:117-131` (stop_forcible)
- Aufruf-Punkt im Optimizer: `optimizer.py:1940-1948`
- Vergleich-Implementierungen: `inverter/huawei.py:54-73`, `inverter/fronius.py:327-367`
- Config-Migration: `__init__.py` (aktuell version 12)
- Default-Entity in SOLAX_ENTITY_DEFAULTS: muss um `battery_charge_max_current` ergänzt werden (`solax.py:26-33`)

## Next step

`/gsd-plan-phase 12` — Plan ist bereits manuell erstellt; falls re-planning gewünscht, dieses Command erneut ausführen.
