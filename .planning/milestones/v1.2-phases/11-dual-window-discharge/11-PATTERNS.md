# Phase 11: Dual-Window-Entladung — Pattern Map

**Mapped:** 2026-05-04
**Phase:** 11 — Dual-Window-Entladung
**Files analyzed:** 15
**Analogs found:** 14 / 15 (1 file mit "no analog — research-pattern")

Diese Datei ist additiver Refactor + Erweiterung. Fast jede neue Code-Stelle hat einen exakten Geschwister-Pattern im selben Modul. Der Planner muss diese Geschwister kopieren, nicht neu erfinden.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `custom_components/eeg_energy_optimizer/const.py` | config-constants | static-data | `const.py:83-105` (Phase-3-Discharge-Konstanten-Block) | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (compute_b_window_end) | utility (pure-fn) | transform | `optimizer.py:175-208` (`compute_hard_cutoff`) | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (Reasons-Catalog +8 Keys) | constants | static-data | `optimizer.py:79-117` (Phase-8-Discharge-Reasons + ALL_REASONS) | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (REASON_LABELS_DE +8 Einträge) | i18n-mapping | static-data | `optimizer.py:120-142` | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (Decision.discharge_active_slot) | dataclass-field | data-shape | `optimizer.py:247-280` Decision-Dataclass `discharge_*`-Block | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (`_should_discharge` Refactor) | service-method | request-response | `optimizer.py:905-1055` (heutige `_should_discharge` als Body für `_evaluate_legacy_window`) | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (`_slot_a/b_activated_date` + Reset) | in-memory-state | state-machine | `optimizer.py:366-371` (`_morning_activated_date`/`_discharge_activated_date`) + `_evaluate`-Reset Z. 1081-1093 | exact |
| `custom_components/eeg_energy_optimizer/optimizer.py` (`_build_markdown` Slot-Rendering) | template | transform | `optimizer.py:1232-1298` | exact |
| `custom_components/eeg_energy_optimizer/peakshare.py` (Cache-Schema dict[a/b]) | service | CRUD | `peakshare.py:171-172` + `peakshare.py:295-394` (`get_discharge_plan`) | role-match |
| `custom_components/eeg_energy_optimizer/__init__.py` (Migration v14→v15) | migration | batch | `__init__.py:813-844` (v12/v13/v14-Blöcke) | exact |
| `custom_components/eeg_energy_optimizer/config_flow.py` (VERSION 14→15) | config | static-data | `config_flow.py:24` | exact |
| `custom_components/eeg_energy_optimizer/websocket_api.py` (Save-Path-XOR + Race) | controller | request-response | `websocket_api.py:395-441` (`ws_save_config` SolarEdge-/Fronius-Validation) | exact |
| `custom_components/eeg_energy_optimizer/frontend/eeg-optimizer-panel.js` (Wizard Step 4 + Settings Tab) | component | render | `eeg-optimizer-panel.js:2960-3061` (Wizard Step 4) + `:3200-3320` (Settings evening-Tab) | exact |
| `custom_components/eeg_energy_optimizer/strings.json` + `translations/{de,en}.json` | i18n | static-data | bestehende Reason-Labels in `optimizer.py:REASON_LABELS_DE` (kein UI-strings.json-Pendant nötig) | role-match |
| `tests/test_dual_window.py` (NEU) | test | request-response | `tests/test_optimizer.py:55-106` Helpers + Klassen-Layout | exact |
| `tests/conftest.py` (Helper-Extraktion) | test-fixtures | data-shape | `tests/conftest.py:1-30` + `tests/test_optimizer.py:63-106` (lokale Helpers) | exact |
| `tests/test_optimizer.py` (Legacy-Pfad-Tests) | test | request-response | bestehende `TestShouldDischarge`-Klassen-Methoden | exact |
| `tests/test_config_flow.py` (Migration-Tests) | test | request-response | `tests/test_config_flow.py` bestehende v13-/v14-Migrationstests | role-match |
| `CHANGELOG.md` | docs | static-data | bestehende v1.1.x-Einträge (Pattern: "Verhaltensänderung beim Update") | role-match |

---

## Pattern Assignments

### `const.py` — neue CONF_* + DEFAULT_* Keys (config-constants)

**Analog:** `custom_components/eeg_energy_optimizer/const.py:83-105` (Phase-3-Discharge-Block) und `:166-178` (`TELEMETRY_SETTINGS_KEYS`)

**Konstanten-Block-Pattern** (`const.py:83-105`):
```python
# Phase 3: Optimizer
CONF_ENABLE_MORNING_DELAY = "enable_morning_delay"
CONF_ENABLE_NIGHT_DISCHARGE = "enable_night_discharge"
CONF_MORNING_START_OFFSET = "morning_start_offset"
CONF_MORNING_END_TIME = "morning_end_time"
CONF_DISCHARGE_START_TIME = "discharge_start_time"
CONF_DISCHARGE_POWER_KW = "discharge_power_kw"
CONF_MIN_SOC = "min_soc"
CONF_SAFETY_BUFFER_PCT = "safety_buffer_pct"
CONF_ENABLE_PEAKSHARE = "enable_peakshare"
CONF_PEAKSHARE_COMMUNITY = "peakshare_community"

DEFAULT_ENABLE_PEAKSHARE = True
DEFAULT_PEAKSHARE_COMMUNITY = "BEG"
DEFAULT_MORNING_START_OFFSET = 0
DEFAULT_MORNING_END_TIME = "11:00"
DEFAULT_DISCHARGE_START_TIME = "01:00"
DEFAULT_DISCHARGE_POWER_KW = 5.0
DEFAULT_MIN_SOC = 10
DEFAULT_SAFETY_BUFFER_PCT = 25
```

**Pattern-Übernahme:** Block "Phase 11: Dual-Window-Entladung" direkt unter "Phase 3: Optimizer", **NICHT** den Phase-3-Block ändern. Bestehende Keys `CONF_DISCHARGE_START_TIME`/`DEFAULT_DISCHARGE_START_TIME = "01:00"` bleiben unverändert (Legacy-Anker für `enable_dual_discharge=False`).

**Telemetry-Whitelist-Pattern** (`const.py:166-178`):
```python
TELEMETRY_SETTINGS_KEYS = (
    "enable_morning_delay",
    "enable_night_discharge",
    "enable_peakshare",
    "morning_start_offset",
    "morning_end_time",
    "discharge_start_time",
    "discharge_power_kw",
    "min_soc",
    "safety_buffer_pct",
    "peakshare_community",
    "forecast_source",
)
```

Erweitern um die 7 neuen Slot-Keys am Ende des Tupels — nichts umsortieren (Backend erwartet positionsstabile Whitelist).

---

### `optimizer.py` (compute_b_window_end) — utility, transform

**Analog:** `optimizer.py:175-208` (`compute_hard_cutoff`)

**Funktions-Pattern** (`optimizer.py:175-208`):
```python
def compute_hard_cutoff(now: datetime, next_sunrise: datetime | None) -> datetime:
    """Berechne den dynamischen Hard-Cutoff für die Abend-Entladung.

    [Multiline-Docstring mit Begründung + Beispielen + Fallback-Verhalten]
    """
    if next_sunrise is None:
        anchor = now if now.hour < 12 else now + timedelta(days=1)
        return anchor.replace(hour=4, minute=0, second=0, microsecond=0)
    fixed_at_sunrise_day = next_sunrise.replace(
        hour=4, minute=0, second=0, microsecond=0
    )
    pre_sunrise = next_sunrise - timedelta(hours=1)
    return min(fixed_at_sunrise_day, pre_sunrise)
```

**Pattern-Konventionen, die `compute_b_window_end` 1:1 übernimmt:**
- Module-level Funktion (NICHT auf `EEGOptimizer` als Methode), damit sie ohne Optimizer-Instanz testbar ist
- `next_sunrise: datetime | None`-Parameter mit `None`-Frühabbruch (oben Fallback, hier `return None`)
- `replace(hour=, minute=, second=0, microsecond=0)` für Anchor an Sunrise-Tag
- `min(...)` über alle Schnittquellen — striktester Schnitt gewinnt
- Multiline-Docstring auf Deutsch mit Beispielen (siehe `compute_hard_cutoff`-Docstring) — Begründung MUSS die 5-Min-Pause-Garantie zur Morgen-Einspeisung wörtlich erwähnen
- Tz-aware bleiben — keine `datetime.now()`-Aufrufe in der Funktion (now wird übergeben)

**Empfohlene Signatur (aus RESEARCH 11-RESEARCH.md:255):**
```python
def compute_b_window_end(
    now: datetime,
    sunrise: datetime | None,
    b_end_cap: str,           # "07:00"
    morning_offset_h: float,  # CONF_MORNING_START_OFFSET (Default 0)
) -> datetime | None:
```

**Wichtig:** Die Funktion direkt unter `compute_hard_cutoff` (Zeile 209) platzieren, damit beide Geschwister-Funktionen gemeinsam gefunden werden. Der `peakshare.py`-Cross-Import auf `compute_hard_cutoff` (`peakshare.py:360`) ist die Convention — neue Funktion ist gleichermaßen importierbar.

---

### `optimizer.py` (Reasons-Catalog +8 Keys) — constants, static-data

**Analog:** `optimizer.py:79-117` (Phase-8-Discharge-Reasons-Block + `ALL_REASONS` frozenset)

**Reasons-Block-Pattern** (`optimizer.py:79-92`):
```python
# Abend-Entladung
REASON_NIGHT_DISCHARGE_DISABLED = "night_discharge_disabled"
REASON_OVERNIGHT_DEMAND_TOO_HIGH = "overnight_demand_too_high"
REASON_BEFORE_DISCHARGE_START = "before_discharge_start"
REASON_PEAKSHARE_BEFORE_WINDOW = "peakshare_before_window"
REASON_PEAKSHARE_WINDOW_ACTIVE = "peakshare_window_active"
REASON_PEAKSHARE_WINDOW_EXPIRED = "peakshare_window_expired"
REASON_HARD_CUTOFF_AFTER_4AM = "hard_cutoff_after_4am"
REASON_SOC_ABOVE_MIN = "soc_above_min"
REASON_SOC_BELOW_MIN = "soc_below_min"
REASON_TOMORROW_PV_SUFFICIENT = "tomorrow_pv_sufficient"
REASON_TOMORROW_PV_INSUFFICIENT = "tomorrow_pv_insufficient"
REASON_DISCHARGE_ABORTED_TODAY = "discharge_aborted_today"
REASON_BATTERY_SOC_UNAVAILABLE = "battery_soc_unavailable"
```

**ALL_REASONS frozenset-Pattern** (`optimizer.py:95-117`):
```python
ALL_REASONS: frozenset[str] = frozenset({
    REASON_PV_FORECAST_EXCEEDS_DEMAND,
    ...
    REASON_BATTERY_SOC_UNAVAILABLE,
})
```

**Pattern-Übernahme:**
- Neuer Kommentar-Block "# Phase 11: Dual-Window-Reasons" direkt nach `REASON_BATTERY_SOC_UNAVAILABLE` (Z. 92), **vor** `ALL_REASONS` (Z. 95)
- Snake_case-Wert MUSS exakt der Variablen-Suffix nach `REASON_` sein (Pattern verifiziert: `REASON_BEFORE_DISCHARGE_START = "before_discharge_start"`)
- Alle 8 neuen Keys in `ALL_REASONS` aufnehmen — **closed-set-Garantie für Backend**, Tests prüfen via `set(reasons).issubset(ALL_REASONS)` (siehe `tests/test_optimizer.py` und Reasons-Tests)
- Keine zwischengeschaltete Listen-Sortierung — am Ende des frozenset einfügen

**Konkrete neue Keys (aus 11-RESEARCH.md:687-697):**
```python
# Phase 11: Dual-Window
REASON_BEFORE_SLOT_A = "before_slot_a"
REASON_SLOT_A_ACTIVE = "slot_a_active"
REASON_SLOT_A_RESERVE_REACHED = "slot_a_reserve_reached"
REASON_BETWEEN_SLOTS = "between_slots"
REASON_BEFORE_SLOT_B = "before_slot_b"
REASON_SLOT_B_ACTIVE = "slot_b_active"
REASON_SLOT_B_WINDOW_EXPIRED = "slot_b_window_expired"
REASON_SLOT_B_PRE_SUNRISE_CUTOFF = "slot_b_pre_sunrise_cutoff"
```

---

### `optimizer.py` (REASON_LABELS_DE +8) — i18n-mapping

**Analog:** `optimizer.py:120-142`

**Pattern** (`optimizer.py:120-142`):
```python
REASON_LABELS_DE: dict[str, str] = {
    REASON_PV_FORECAST_EXCEEDS_DEMAND: "PV-Prognose deckt Bedarf inkl. Puffer",
    ...
    REASON_BEFORE_DISCHARGE_START: "Vor Entladestart-Zeit",
    REASON_PEAKSHARE_BEFORE_WINDOW: "PeakShare-Fenster noch nicht erreicht",
    REASON_PEAKSHARE_WINDOW_ACTIVE: "PeakShare-Fenster aktiv",
    REASON_PEAKSHARE_WINDOW_EXPIRED: "PeakShare-Fenster abgelaufen",
    ...
}
```

**Pattern-Übernahme:**
- Echte Umlaute (ä/ö/ü) verwenden — siehe Memory `feedback_umlaute.md`
- Stil: Deklarative Phrase, kein Satzzeichen am Ende, keine Anführungszeichen außer um Werte. Verifiziertes Beispiel: `"PeakShare-Fenster aktiv"` (3 Wörter)
- Slot-A/B in Klammern wenn Mehrdeutigkeit droht: `"Slot A aktiv (Abend-Entladung)"` — Phase-3-Pattern macht das bei `REASON_OVERNIGHT_DEMAND_TOO_HIGH: "Nachtverbrauch zu hoch (Min-SOC ≥ 100%)"`

**Konkrete Texte (aus 11-RESEARCH.md:704-714):** sind im Research-Doc wörtlich vorgegeben — Planner kopiert.

---

### `optimizer.py` (Decision.discharge_active_slot) — dataclass-field

**Analog:** `optimizer.py:247-280` und insbesondere die `discharge_*`-Felder (z.B. Z. 1180-1192 wo sie gesetzt werden)

**Decision-Dataclass-Pattern** (`optimizer.py:247-280`):
```python
@dataclass
class Decision:
    """Result of one optimizer evaluation cycle."""
    timestamp: str = ""
    zustand: str = "Normal"
    energiebedarf_kwh: float = 0.0
    ladung_blockiert: bool = False
    entladung_aktiv: bool = False
    entladeleistung_kw: float = 0.0
    min_soc_berechnet: float = 0.0
    nächste_aktion: str = ""
    markdown: str = ""
    ausführung: bool = False

    # Strukturierte Diagnose-Felder (D-09): kanonische snake_case-Keys aus
    # ALL_REASONS. Wird vom Telemetrie-Reporter 1:1 an State-Change-Events
    # gehängt. UI-Renderer übersetzen via REASON_LABELS_DE für Endnutzer.
    reasons: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)
    ...
```

**Pattern-Übernahme:**
- Optional[Literal] in Python 3.11+ ohne Klammer-Import: `discharge_active_slot: str | None = None` — `Literal["A", "B"]` ist möglich, aber bestehende Decision-Felder benutzen schlichte Annotations (siehe `discharge_status: str = ""` etc.). Empfehlung: `discharge_active_slot: str | None = None` mit Kommentar `# "A" | "B" | None`
- Default `None` (NICHT leerer String) — passend zu Snapshot-Pattern für `pv_remaining_today_kwh: float | None = None`
- Field-Block-Kommentar setzen wie bei Z. 262-264 ("Strukturierte Diagnose-Felder (D-09)…") — Plan-Hinweis: `# Phase 11: aktiver Slot ("A" | "B" | None für Legacy/Pause)`

---

### `optimizer.py` (`_should_discharge` Refactor) — service-method, request-response

**Analog (Body-Übernahme zu `_evaluate_legacy_window`):** `optimizer.py:905-1055` (heutige `_should_discharge`-Methode)

**Schnittstellen-Pattern** (`optimizer.py:905-916`):
```python
def _should_discharge(
    self, snap: Snapshot
) -> tuple[bool, float, list[str], list[str], bool]:
    """Determine if evening discharge should be active.

    Returns ``(should_discharge, min_soc, reasons, blocked_by, hysteresis_active)``
    per D-11. Alle Einträge in ``reasons``/``blocked_by`` sind snake_case-Keys
    aus ALL_REASONS (D-12).

    Wenn ``should_discharge=True`` → ``reasons`` listet die Pass-Gründe,
    ``blocked_by`` ist leer. Wenn ``should_discharge=False`` → ``reasons``
    ist leer, ``blocked_by`` listet jeden Guard.
    """
```

**Guard-Pattern (Anfang der Methode, Z. 918-926) — wird zu `_check_common_guards`:**
```python
# Guard 1: Feature aus
if not self._enable_night_discharge:
    return (False, float(self._min_soc), [], [REASON_NIGHT_DISCHARGE_DISABLED], False)

min_soc = self._calc_min_soc(snap)

# Guard 2: Nachtverbrauch verschlingt komplette Batterie
if min_soc >= 100.0:
    return (False, min_soc, [], [REASON_OVERNIGHT_DEMAND_TOO_HIGH], False)
```

**Hysterese-Pattern (Z. 931-940) — pro Slot dupliziert:**
```python
today_str = snap.now.strftime("%Y-%m-%d")
is_reactivation = (
    self._discharge_activated_date is not None
    and self._last_eval_zustand != STATE_ABEND_ENTLADUNG
)
```
→ Slot-A: `self._slot_a_activated_date is not None and self._last_active_slot != "A"`
→ Slot-B: analog mit `_slot_b_activated_date`

**Hysterese-SOC-Aufschlag-Pattern (Z. 1017-1029):**
```python
effective_min_soc = min_soc + 5 if is_reactivation else min_soc

if snap.battery_soc <= effective_min_soc:
    if is_reactivation:
        blocked_by.append(REASON_HYSTERESIS_STRICT)
    blocked_by.append(REASON_SOC_BELOW_MIN)
else:
    if is_reactivation:
        passing.append(REASON_HYSTERESIS_STRICT)
    passing.append(REASON_SOC_ABOVE_MIN)
```

**Tomorrow-PV-Surplus-Pattern (Z. 1031-1044) — gehört in `_check_common_guards`:**
```python
consumption_with_buffer = snap.consumption_tomorrow_daylight_kwh * (1 + self._safety_buffer_pct / 100)
battery_charge_needed = (
    (100 - self._min_soc) / 100 * snap.battery_capacity_kwh * snap.sim_factor
)
tomorrow_demand = consumption_with_buffer + battery_charge_needed
pv_tomorrow = snap.pv_tomorrow_kwh if snap.pv_tomorrow_kwh is not None else 0.0

if pv_tomorrow < tomorrow_demand:
    blocked_by.append(REASON_TOMORROW_PV_INSUFFICIENT)
else:
    passing.append(REASON_TOMORROW_PV_SUFFICIENT)
```

**SolarEdge-Watchdog-Pattern (Z. 1046-1049) — gehört in `_check_common_guards`:**
```python
if self._is_solaredge:
    if self._discharge_aborted_date == today_str:
        blocked_by.append(REASON_DISCHARGE_ABORTED_TODAY)
```

**Return-Mutual-Exclusion-Pattern (Z. 1051-1055):**
```python
# Mutual-Exclusion-Invariante: bei Pass werden passing-Keys reasons,
# bei Block bleibt reasons leer und blocked_by führt die Liste.
if not blocked_by:
    return (True, min_soc, passing, [], is_reactivation)
return (False, min_soc, [], blocked_by, is_reactivation)
```

**Pattern-Übernahme:**
- Heutiger `_should_discharge`-Body (Z. 918-1055) **wird 1:1 zu `_evaluate_legacy_window`** umbenannt — keine inhaltliche Änderung (D-05)
- Neuer `_should_discharge` ist nur Dispatcher (siehe 11-RESEARCH.md:400-433): zuerst `_check_common_guards()`, dann `enable_dual_discharge` + `_is_solaredge`-Branch
- `_evaluate_slot_a`/`_evaluate_slot_b` haben **gleiche Return-Tuple-Form** wie `_should_discharge` heute — `(passed: bool, reasons: list[str], blocked_by: list[str], hysteresis_active: bool)` (ohne min_soc, das kommt vom Common-Guard-Aufruf)
- Reaktivierungs-Aufschlag: Slot-A nutzt `+ self._discharge_a_reserve_pct` als Reserve und `+ 5` als Hysterese-Aufschlag → `effective = min_soc + reserve + (5 if is_reactivation else 0)`. Slot-B nutzt `+ 5` Hysterese-Aufschlag, **kein** Reserve-Aufschlag

---

### `optimizer.py` (Slot-State-Felder + Reset) — in-memory-state, state-machine

**Analog:** `optimizer.py:366-371` (Hysterese-Felder im `__init__`) + `optimizer.py:1081-1093` (Reset-Block in `_evaluate`)

**Init-Felder-Pattern** (`optimizer.py:366-371`):
```python
# Hysteresis: track dates when states were first activated today.
# If a state was already active and then deactivated on the same day,
# require a higher threshold to reactivate (prevents oscillation).
self._morning_activated_date: str | None = None
self._discharge_activated_date: str | None = None
self._last_eval_zustand: str = STATE_NORMAL
```

**SolarEdge-Flag-Pattern** (`optimizer.py:382-384`):
```python
self._grid_import_since: datetime | None = None
self._discharge_aborted_date: str | None = None  # ISO date "YYYY-MM-DD"
self._is_solaredge = inv_type_cfg == "solaredge_storedge"
```

**Reset-Block-Pattern** (`optimizer.py:1081-1093`):
```python
today_str = snap.now.strftime("%Y-%m-%d")
if (
    self._morning_activated_date is not None
    and self._morning_activated_date < today_str
):
    self._morning_activated_date = None
if (
    self._discharge_activated_date is not None
    and self._discharge_activated_date < today_str
    and snap.sunrise_today is not None
    and snap.now >= snap.sunrise_today
):
    self._discharge_activated_date = None
```

**Aktivierungsdatum-Setzen-Pattern** (`optimizer.py:1109-1119`):
```python
# Aktivierungsdatum nur beim erstmaligen Aktivieren setzen — bei
# durchgehender Sitzung (z.B. Abend-Entladung über Mitternacht)
# bleibt das ursprüngliche Startdatum erhalten, damit der Reset
# oben zum Sonnenaufgang sauber greift.
if zustand == STATE_MORGEN_EINSPEISUNG:
    if self._morning_activated_date is None:
        self._morning_activated_date = today_str
elif zustand == STATE_ABEND_ENTLADUNG:
    if self._discharge_activated_date is None:
        self._discharge_activated_date = today_str
self._last_eval_zustand = zustand
```

**Pattern-Übernahme:**
- Neue Felder `_slot_a_activated_date`, `_slot_b_activated_date`, `_last_active_slot` direkt nach `_discharge_activated_date` (Z. 370) ergänzen — Phase-3-Block bleibt zusammen
- Reset-Block in `_evaluate`: nach dem `_discharge_activated_date`-Reset (Z. 1093) **zwei zusätzliche Blöcke** für Slot-A und Slot-B mit identischer "after-sunrise"-Logik (siehe RESEARCH 11-RESEARCH.md:495-517)
- Aktivierungsdatum-Block: Innerhalb des `elif zustand == STATE_ABEND_ENTLADUNG`-Branches (Z. 1116-1118) **nach Erweiterung** auf `decision.discharge_active_slot == "A"`/`"B"` differenzieren — Beispielcode in 11-RESEARCH.md:533-541

---

### `optimizer.py` (`_build_markdown` Slot-Rendering) — template, transform

**Analog:** `optimizer.py:1232-1298` (`_build_markdown`)

**Pattern** (`optimizer.py:1260-1274`):
```python
if decision.entladung_aktiv:
    lines.append("### Abend-Entladung")
    lines.append(
        f"- Startzeit: {self._discharge_start_h:02d}:{self._discharge_start_m:02d}"
    )
    lines.append(f"- Leistung: {decision.entladeleistung_kw:.1f} kW")
    lines.append(f"- Ziel-SOC: {decision.min_soc_berechnet:.0f}%")
    if snap.pv_tomorrow_kwh is not None:
        lines.append(
            f"- PV-Prognose morgen: {snap.pv_tomorrow_kwh:.1f} kWh"
        )
    lines.append(
        f"- Verbrauchsprognose morgen: {snap.consumption_tomorrow_kwh:.1f} kWh"
    )
    lines.append("")
```

**Reasons-Rendering-Pattern** (`optimizer.py:1283-1294`):
```python
if decision.reasons:
    lines.append("### Diagnose (Gründe)")
    for key in decision.reasons:
        lines.append(f"- {REASON_LABELS_DE.get(key, key)}")
    lines.append("")
if decision.blocked_by:
    lines.append("### Diagnose (blockiert durch)")
    for key in decision.blocked_by:
        lines.append(f"- {REASON_LABELS_DE.get(key, key)}")
    lines.append("")
```

**Pattern-Übernahme:**
- Innerhalb `if decision.entladung_aktiv:` Block — wenn `decision.discharge_active_slot` gesetzt ist, eine zusätzliche Markdown-Zeile `f"- Aktiver Slot: {decision.discharge_active_slot}"` direkt nach "Startzeit"
- Echte Umlaute (Ziel-SOC schon mit Bindestrich richtig)
- `lines.append("")` als Sektions-Separator beibehalten

---

### `peakshare.py` (Cache-Schema dict[a/b]) — service, CRUD

**Analog (gleiche Datei):** `peakshare.py:171-172` (Init-Felder) + `peakshare.py:174-195` (`async_load`) + `peakshare.py:295-394` (`get_discharge_plan`)

**Init-Pattern** (`peakshare.py:171-172`):
```python
self._discharge_plan: tuple[datetime, datetime] | None = None
self._discharge_plan_date: str | None = None
```

**`get_discharge_plan` Cache-Lookup-Pattern** (`peakshare.py:320-325`):
```python
today_str = now.strftime("%Y-%m-%d")
# Already computed today (and not invalidated by fresh fetch):
# return cached plan
if self._discharge_plan_date == today_str:
    return self._discharge_plan
```

**Window-Resolution-Pattern** (`peakshare.py:349-379`):
```python
# Window: max(sunset, discharge_start_time) bis dynamischer Hard-Cutoff.
window_start = sunset_time
if discharge_start_lower_bound is not None:
    window_start = max(window_start, discharge_start_lower_bound)

from .optimizer import compute_hard_cutoff
next_day = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
    days=1
)
window_end = compute_hard_cutoff(next_day, next_sunrise)

# Edge-Case: Wenn die Untergrenze bereits nach Cutoff liegt → kein Fenster.
if window_start >= window_end:
    _LOGGER.info(
        "PeakShare: Untergrenze %s liegt nach Hard-Cutoff %s — kein Fenster",
        window_start.strftime("%H:%M"),
        window_end.strftime("%H:%M"),
    )
    self._discharge_plan = None
    self._discharge_plan_date = today_str
    return None
```

**Plan-Lock-Pattern** (`peakshare.py:382-393`):
```python
plan = find_discharge_window(
    api_hours,
    available_kwh,
    discharge_power_kw,
    window_start,
    window_end,
    jitter,
)

# Lock computation for today
self._discharge_plan = plan
self._discharge_plan_date = today_str
```

**`async_load`-Storage-Pattern** (`peakshare.py:174-195`):
```python
async def async_load(self) -> None:
    if self._store is None:
        return
    try:
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict):
            self._cache = stored.get("data")
            fetched_at = stored.get("fetched_at")
            if fetched_at:
                self._cache_time = datetime.fromisoformat(fetched_at)
            self._jitter_today = stored.get("jitter_value")
            self._jitter_date = stored.get("jitter_date")
    except Exception:
        _LOGGER.debug("PeakShare: no persisted cache found")
```

**Pattern-Übernahme:**
- Init-Schema-Wechsel: `self._discharge_plan: dict[str, tuple[datetime, datetime] | None] = {"a": None, "b": None}` — `_discharge_plan_date` bleibt skalar (Lock pro Tag, gemeinsam für a/b)
- `get_discharge_plan` bekommt `slot: str = "a"`-Parameter; Cache-Lookup wird `self._discharge_plan.get(slot)`; Plan-Lock wird `self._discharge_plan[slot] = plan`
- `async_fetch`-Cache-Invalidate (`peakshare.py:236-237`) verwendet heute `self._discharge_plan = None` — neu: `self._discharge_plan = {"a": None, "b": None}` (Schema-konsistent)
- `async_load`-Migration ist **best-effort verwerfen** (siehe RESEARCH 11-RESEARCH.md:573-579) — alte tuple-Form wird ignoriert, beim nächsten Cycle neu berechnet
- `_discharge_detail_status` (`optimizer.py:743-749`) und `_evaluate` (`optimizer.py:1135-1138`) lesen `getattr(self._peakshare, "_discharge_plan", None)` — dort muss der Lookup auf `dict.get("a")` oder Slot-spezifisch angepasst werden

---

### `__init__.py` (Migration v14→v15) — migration, batch

**Analog:** `__init__.py:813-844` (v12-/v13-/v14-Migrations-Blöcke)

**Migration-Block-Pattern** (`__init__.py:813-829`):
```python
if entry.version < 12:
    new_data = {**entry.data}
    new_data.setdefault("enable_peakshare", True)
    new_data.setdefault("peakshare_community", "BEG")
    # Don't change existing discharge_power_kw — only default for new installs is 5.0
    hass.config_entries.async_update_entry(entry, data=new_data, version=12)

if entry.version < 13:
    # v13 vereint zwei Migrations-Intents (gemeinsam gedraftet):
    #   1. Pair-sensor support (Fronius) — schema-only, pair keys werden
    #      vom Wizard/Auto-Detect geschrieben, wenn der User tatsächlich
    #      ein SolarNet split-sensor Setup hat.
    #   2. Phase 8 Telemetrie (D-02): CONF_TELEMETRY_ENABLED=False als
    #      sicherer Default für alle existierenden Installationen.
    new_data = {**entry.data}
    new_data.setdefault(CONF_TELEMETRY_ENABLED, False)
    hass.config_entries.async_update_entry(entry, data=new_data, version=13)
```

**Hard-Migration-Pattern (für Verhaltens-Default-Wechsel)** (`__init__.py:831-844`):
```python
if entry.version < 14:
    # v14 — Abend-Entladestart auf 01:00 vereinheitlichen.
    # Hard-Migration: ALLE bestehenden Entries werden auf "01:00" gesetzt,
    # unabhängig vom bisherigen Wert. Begründung:
    #   - In beiden Modi (Fixed + PeakShare) ist discharge_start_time jetzt
    #     der frühestmögliche Entladestart (PeakShare nutzt ihn als Sliding-
    #     Window-Untergrenze). Späterer Start = präzisere Verbrauchsprognose
    #     für den Restbedarf der Nacht = höhere realisierte Einspeisung.
    #   - Der zuvor empfohlene Default 20:00 produzierte zu konservative
    #     min_soc_dyn-Werte und damit kürzere Fenster.
    # User kann den Wert jederzeit im Wizard wieder ändern.
    new_data = {**entry.data}
    new_data["discharge_start_time"] = "01:00"
    hass.config_entries.async_update_entry(entry, data=new_data, version=14)
```

**Pattern-Übernahme:**
- Block direkt nach v14-Block (Z. 844) ergänzen, **vor** `return True` (Z. 846)
- `if entry.version < 15:`-Header
- `new_data = {**entry.data}` — flache Kopie zum Mutieren
- `new_data.setdefault(...)` für **additive** Defaults (User hat Wert vielleicht schon explizit gesetzt) — anders als bei v14, das Hard-Migration ist
- Inverter-Type aus `entry.data.get(CONF_INVERTER_TYPE, "")` lesen für SolarEdge-Branch
- Multi-line-Begründungs-Kommentar im Stil v13/v14 — was, warum, ob Hard- oder Soft-Migrate
- `hass.config_entries.async_update_entry(entry, data=new_data, version=15)` als Abschluss

**Konkreter Block (aus 11-RESEARCH.md:330-351 als Vorlage):**
```python
if entry.version < 15:
    new_data = {**entry.data}
    inverter_type = new_data.get(CONF_INVERTER_TYPE, "")
    is_solaredge = inverter_type == INVERTER_TYPE_SOLAREDGE
    if is_solaredge:
        new_data.setdefault("enable_dual_discharge", False)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", False)
    else:
        new_data.setdefault("enable_dual_discharge", True)
        new_data.setdefault("enable_slot_a", True)
        new_data.setdefault("enable_slot_b", True)
    new_data.setdefault("discharge_a_start_time", "20:00")
    new_data.setdefault("discharge_b_start_time", "03:00")
    new_data.setdefault("discharge_b_end_cap", "07:00")
    new_data.setdefault("discharge_a_reserve_pct", 15)
    hass.config_entries.async_update_entry(entry, data=new_data, version=15)
```

**Wichtig:** `INVERTER_TYPE_SOLAREDGE` wird heute noch **nicht** in `__init__.py` importiert — der Plan muss den Import in der Imports-Region oben hinzufügen oder den String `"solaredge_storedge"` direkt verwenden (so wie `optimizer.py:349` und `:384`).

---

### `config_flow.py` (VERSION 14→15) — config, static-data

**Analog:** `config_flow.py:24`

**Pattern** (`config_flow.py:24`):
```python
class EegEnergyOptimizerConfigFlow(ConfigFlow, domain=DOMAIN):
    ...
    VERSION = 14
```

**Pattern-Übernahme:** Einzeile ändern: `VERSION = 14` → `VERSION = 15`. **Muss synchron** mit `__init__.py:async_migrate_entry`-Block-Anhebung erfolgen.

---

### `websocket_api.py` (Save-Path SolarEdge-XOR + Race-Validation) — controller, request-response

**Analog:** `websocket_api.py:395-441` (`ws_save_config`)

**SolarEdge-Auto-Korrektur-Pattern** (`websocket_api.py:410-414`):
```python
# SolarEdge: enforce minimum discharge power of 5 kW
if new_data.get("inverter_type") == INVERTER_TYPE_SOLAREDGE:
    discharge_kw = new_data.get("discharge_power_kw")
    if discharge_kw is not None and float(discharge_kw) < 5.0:
        new_data["discharge_power_kw"] = 5.0
```

**Hard-Reject-Pattern (Fronius — NICHT für Phase 11 verwenden!)** (`websocket_api.py:420-441`):
```python
if new_data.get("inverter_type") == INVERTER_TYPE_FRONIUS:
    host = new_data.get("fronius_modbus_host", "")
    if not isinstance(host, str) or not host.strip() or len(host) > 255:
        connection.send_error(
            msg["id"], "invalid_config", "Invalid Fronius Modbus host"
        )
        return
    ...
```

**Pattern-Übernahme:**
- Phase 11 erweitert den **bestehenden SolarEdge-Block** (Z. 410-414) um die XOR-Erzwingung
- **Auto-Korrektur, NICHT Hard-Reject** (siehe 11-RESEARCH.md:729-740) — folgt dem `discharge_kw < 5.0`-Clamp-Pattern, nicht dem Fronius-Hard-Reject
- `_LOGGER.warning(...)`-Aufruf für jede Auto-Korrektur (siehe `optimizer.py:350-353` für Stil)
- Race-Validation-Block (b_start ≥ a_min_required_end + 5min) als **separater Block** nach den Inverter-spezifischen Blöcken — siehe konkreter Code in 11-RESEARCH.md:744-768
- `_parse_hhmm` Helper-Funktion existiert noch nicht — muss als Modul-private `_parse_hhmm(s: str) -> int` (Minuten seit Mitternacht) im selben File hinzugefügt werden

**SolarEdge-XOR-Block (aus 11-RESEARCH.md:646-664):**
```python
if new_data.get("inverter_type") == INVERTER_TYPE_SOLAREDGE:
    discharge_kw = new_data.get("discharge_power_kw")
    if discharge_kw is not None and float(discharge_kw) < 5.0:
        new_data["discharge_power_kw"] = 5.0
    # Phase 11: SolarEdge bleibt Single-Slot
    if new_data.get("enable_dual_discharge"):
        _LOGGER.warning(
            "SolarEdge: enable_dual_discharge=True nicht erlaubt — auf False gesetzt"
        )
        new_data["enable_dual_discharge"] = False
    if new_data.get("enable_slot_a") and new_data.get("enable_slot_b"):
        _LOGGER.warning("SolarEdge: nur ein Slot erlaubt — Slot A bevorzugt")
        new_data["enable_slot_b"] = False
    if not new_data.get("enable_slot_a") and not new_data.get("enable_slot_b"):
        new_data["enable_slot_a"] = True
```

---

### `frontend/eeg-optimizer-panel.js` (Wizard Step 4 + Settings evening Tab) — component, render

**Analog (Wizard):** `eeg-optimizer-panel.js:2960-3061` (`_renderStep4` Discharge-Sektion)
**Analog (Settings):** `eeg-optimizer-panel.js:3200-3320` (Settings-Tab "evening" Discharge-Sektion)

**Wizard-Discharge-Section-Pattern** (`eeg-optimizer-panel.js:2995-3027`):
```javascript
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
      <input type="number" data-field="discharge_power_kw" ...>
      ...
    </div>
    ...
  </div>` : "";
```

**SolarEdge-Conditional-Pattern (im selben File)** (`eeg-optimizer-panel.js:3017`):
```javascript
min="${this._wizardData.inverter_type === "solaredge_storedge" ? "5.0" : "0.5"}"
```

**Settings-Tab-Field-Prefix-Pattern** (`eeg-optimizer-panel.js:3244` vs Wizard Z. 3007):
```javascript
// Wizard:    data-field="discharge_start_time"
// Settings:  data-field="settings_discharge_start_time"
```
→ Settings-Tab nutzt `settings_*`-Präfix für `data-field`-Attribute, damit Save-Path die Quelle erkennt.

**Pattern-Übernahme:**
- **Master-Toggle** als zusätzliche Checkbox **vor** der `enable_peakshare`-Checkbox in der Discharge-Section: `<input type="checkbox" data-field="enable_dual_discharge" ${dualOn ? "checked" : ""}>`
- **Slot-A/Slot-B-Sub-Bereiche** als zwei `<div class="feature-params">`-Blöcke unterhalb des Master-Toggles, jeweils mit eigenem Label/Toggle (`enable_slot_a`, `enable_slot_b`) + Sub-Feldern (`discharge_a_start_time`, `discharge_a_reserve_pct`, `discharge_b_start_time`, `discharge_b_end_cap`)
- **Conditional Render**: Master-Toggle `enable_dual_discharge=true` → Slot-A/B-Sub-Bereiche; sonst Legacy-`discharge_start_time`-Feld
- **SolarEdge-Branch:** Bei `inverter_type === "solaredge_storedge"`: Master-Toggle ausblenden + Radio-Button rendern (siehe Visualisierung in 11-RESEARCH.md:670-680). Genaue Struktur:
  ```html
  <div class="field-group" title="NVRAM-Verschleiß: nur ein Slot pro Tag möglich">
    <label>Welcher Slot soll laufen?</label>
    <label><input type="radio" name="solaredge_slot" data-field="enable_slot_a" value="a" ${slotA ? "checked" : ""}> Slot A — Abend (Default)</label>
    <label><input type="radio" name="solaredge_slot" data-field="enable_slot_b" value="b" ${slotB ? "checked" : ""}> Slot B — Morgen</label>
  </div>
  ```
- Alle Texte mit echten Umlauten (siehe `feedback_umlaute.md`)
- Settings-Tab spiegelt Wizard 1:1 mit `settings_`-Präfix für `data-field`

**Decision-Card-Slot-Marker** — kein bestehender Anker (Decision-Card rendert heute den Markdown via `<ha-markdown>`); Markdown-Renderer im Backend (`optimizer.py:_build_markdown`) liefert die Slot-Info. Frontend-Lesen via `decision.discharge_active_slot` ist optional und kann durch Markdown-Rendering allein abgedeckt werden.

---

### `tests/test_dual_window.py` (NEU) — test, request-response

**Analog:** `tests/test_optimizer.py:55-106` (Helpers + Klassen-Layout) und `tests/test_optimizer.py:113-174` (TestShouldBlockCharging-Klasse als Beispiel)

**Helper-Pattern** (`tests/test_optimizer.py:63-106`):
```python
def _make_config(**overrides):
    """Create a minimal optimizer config dict.

    Test-Default: discharge_start_time="20:00" — die meisten Bestands-Tests
    wurden gegen diesen alten Wert geschrieben...
    """
    base = {
        CONF_BATTERY_SOC_SENSOR: "sensor.battery_soc",
        CONF_BATTERY_CAPACITY_SENSOR: "",
        CONF_BATTERY_CAPACITY_KWH: 10.0,
        CONF_DISCHARGE_START_TIME: "20:00",
    }
    base.update(overrides)
    return base


def _make_snapshot(**overrides):
    """Create a Snapshot with sensible defaults for testing."""
    now = overrides.pop("now", datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc))
    defaults = dict(
        now=now,
        battery_soc=50.0,
        battery_capacity_kwh=10.0,
        ...
    )
    defaults.update(overrides)
    return Snapshot(**defaults)


def _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider, config=None):
    cfg = config or _make_config()
    return EEGOptimizer(mock_hass, "test_entry_id", cfg, mock_inverter, mock_coordinator, mock_provider)
```

**Test-Klassen-Pattern** (`tests/test_optimizer.py:113-127`):
```python
class TestShouldBlockCharging:
    def test_morning_block_active_during_window_on_surplus_day(
        self, mock_hass, mock_inverter, mock_coordinator, mock_provider
    ):
        opt = _make_optimizer(mock_hass, mock_inverter, mock_coordinator, mock_provider)
        sunrise = datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)
        snap = _make_snapshot(
            now=datetime(2026, 6, 15, 6, 0, tzinfo=timezone.utc),
            sunrise=sunrise,
            sunrise_today=sunrise,
            pv_remaining_today_kwh=20.0,
            consumption_today_kwh=10.0,
        )
        assert opt._should_block_charging(snap)[0] is True
```

**Conftest-Fixtures-Pattern** (`tests/conftest.py:1-30`):
```python
"""Shared test fixtures for EEG Energy Optimizer."""

from unittest.mock import AsyncMock, MagicMock
import pytest

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.services.async_call = AsyncMock(return_value=None)
    hass.data = {}
    return hass

@pytest.fixture
def mock_inverter():
    inv = MagicMock()
    inv.async_set_charge_limit = AsyncMock(return_value=True)
    inv.async_set_discharge = AsyncMock(return_value=True)
    inv.async_stop_forcible = AsyncMock(return_value=True)
    inv.is_available = True
    return inv
```

**Pattern-Übernahme:**
- Helper-Extraktion: `_make_config`, `_make_snapshot`, `_make_optimizer` aus `test_optimizer.py:63-106` nach `tests/conftest.py` als Modul-Level-Funktionen verschieben (NICHT als Fixtures, weil sie parametrisierbar sein müssen)
- Imports am Datei-Anfang von `test_dual_window.py`: `from tests.test_optimizer import _make_config, _make_snapshot, _make_optimizer` ODER bevorzugt: aus `conftest.py` exportieren via `from tests.conftest import _make_config` etc.
- Test-Klassen-Layout (siehe 11-RESEARCH.md:786-832 für die vollständige Klassenstruktur): `TestComputeBWindowEnd`, `TestSlotBPreSunriseCutoff` (parametrisiert), `TestSlotAReserveLogic`, `TestSlotBLogic`, `TestProSlotHysteresis`, `TestSolarEdgeXOR`, `TestMutualExclusion`, `TestDualWindow24hSimulation`
- Mock-Fixtures (`mock_hass`, `mock_inverter`, `mock_coordinator`, `mock_provider`) aus bestehender `tests/conftest.py` weiterverwenden — kein Neu-Definieren
- Tz-aware datetime-Werte: `datetime(2026, 6, 15, 5, 30, tzinfo=timezone.utc)` (Pattern aus `test_optimizer.py:118`) — KEIN naive datetime
- Assert-Form: `assert opt._method(snap)[index] is True/False` (Pattern aus `test_optimizer.py:127`)

---

### `tests/test_optimizer.py` (Legacy-Pfad-Tests) — test, request-response

**Analog (im selben File):** Bestehende `TestShouldDischarge`-Klassen (heutige Tests prüfen genau den Legacy-Pfad)

**Pattern-Übernahme:**
- Neue Test-Klasse `TestEnableDualDischargeFalseLegacyPath` mit 3 Methoden (siehe 11-RESEARCH.md:844-849):
  ```python
  class TestEnableDualDischargeFalseLegacyPath:
      """Ensures byte-identical legacy behavior with enable_dual_discharge=False."""
      def test_legacy_path_called_when_dual_disabled(...)
      def test_legacy_path_called_when_solaredge(...)
      def test_legacy_uses_existing_discharge_start_time_default_01_00(...)
  ```
- Bestehende Tests bleiben **unverändert** — sie sollen weiter grün sein (das ist der Beweis für Backwards-Compat)

---

### `tests/test_config_flow.py` (Migration v14→v15-Tests) — test, request-response

**Analog:** Existierende v13-/v14-Migrationstests in `tests/test_config_flow.py` (Datei wurde im Phase-8/Phase-9-Plan etabliert)

**Pattern-Übernahme:**
- 4 Tests: `test_migration_v14_to_v15_non_solaredge_sets_dual_true`, `test_migration_v14_to_v15_solaredge_xor`, `test_migration_v14_to_v15_preserves_existing_discharge_start_time`, `test_save_config_solaredge_disables_dual_with_log_warning`
- Mock `entry.data` mit version=14, dann `await async_migrate_entry(hass, entry)`, dann `entry.data` prüfen
- WS-Save-Test mit gemocktem `connection.send_error` — falls XOR-Korrektur greift, wird **kein** `send_error` aufgerufen, stattdessen `_LOGGER.warning` (caplog testbar via pytest)

---

### `CHANGELOG.md` (v1.2.0-Eintrag) — docs

**Analog:** Bestehende Einträge in `CHANGELOG.md` — Pattern: Version-Header + Sektionen ("Added", "Changed", "Fixed"). Phase 8 hat den Pattern für "Verhaltensänderung beim Update" gesetzt (siehe Memory `project_pending_release_notes.md`).

**Pattern-Übernahme:**
- **Eigener Abschnitt** "Verhaltensänderung beim Update" am Anfang des v1.2.0-Eintrags (D-04 fordert das prominent)
- Erklärung: Bestands-Anlagen erhalten automatisch Dual-Window. Mitigation: Pro-Slot-Hysterese und PV-Tomorrow-Garantie
- Default-Werte explizit listen: `discharge_a_start_time="20:00"`, `discharge_b_start_time="03:00"`, `discharge_b_end_cap="07:00"`, `discharge_a_reserve_pct=15`
- SolarEdge-Sonderfall separat erwähnen
- Echte Umlaute

---

## Shared Patterns

### Snake_case-Reasons-Closed-Set (Phase 8 Pattern)
**Source:** `optimizer.py:79-117`
**Apply to:** Alle neuen Discharge-Reasons (Slot A/B Phase-Marker)

Pattern: Variablen-Konstante `REASON_FOO = "foo"` (snake_case-Wert exakt = Suffix nach `REASON_`), in `ALL_REASONS`-frozenset registrieren, in `REASON_LABELS_DE` deutsche UI-Übersetzung.

### Hysterese als Datums-Feld
**Source:** `optimizer.py:366-371` (Init) + `:1081-1093` (Reset) + `:1109-1119` (Set)
**Apply to:** Slot-A-/Slot-B-Aktivierungs-Felder + Reset-Trigger pro Slot

Pattern:
```python
# Init
self._{slot}_activated_date: str | None = None

# Reset (in _evaluate, vor Slot-Methoden)
if (
    self._{slot}_activated_date is not None
    and self._{slot}_activated_date < today_str
    and snap.sunrise_today is not None
    and snap.now >= snap.sunrise_today
):
    self._{slot}_activated_date = None

# Set (nach Zustand-Resolution)
if zustand == STATE_ABEND_ENTLADUNG and decision.discharge_active_slot == "{SLOT}":
    if self._{slot}_activated_date is None:
        self._{slot}_activated_date = today_str
```

### Auto-Korrektur statt Hard-Reject (im Save-Path)
**Source:** `websocket_api.py:410-414` (SolarEdge 5kW-Clamp) + `optimizer.py:349-354` (Runtime-Erzwingung)
**Apply to:** SolarEdge-XOR + Race-Validation in `ws_save_config`

Pattern: `_LOGGER.warning(...)` + Wert anpassen. **Kein** `connection.send_error(...)` für Optimierungs-Validation. Hard-Reject ist Setup-Fehlern vorbehalten (Fronius-Modbus-Host-leer).

### Tz-aware datetime mit Anchor-Pattern
**Source:** `optimizer.py:175-208` (`compute_hard_cutoff`) + `:600-626` (`_get_sun_times`)
**Apply to:** `compute_b_window_end` + alle Window-Berechnungen pro Slot

Pattern:
- `datetime` immer mit `tzinfo` (entweder via `_now()` oder `_as_local(datetime.fromisoformat(...))`)
- Anchor-Tag: `next_sunrise.replace(hour=, minute=, second=0, microsecond=0)` für Cap, `now + timedelta(days=1)` für Folgetags-Anchor wenn Sunrise unbekannt
- Striktester Schnitt: `min(...)` über alle Schnittquellen

### Defense-in-depth (Migration + Save + Runtime)
**Source:** SolarEdge ist heute schon dreifach abgesichert: Migration `__init__.py:813-844` (für Default), Save `websocket_api.py:410-414` (für Boot-time-Konsistenz), Runtime `optimizer.py:347-354` + `:384` (für unconditional Erzwingung)
**Apply to:** SolarEdge-XOR-Sperre für Phase 11 — alle drei Layer

Pattern: Migration setzt sicheren Default, Save-Path lehnt fehlerhafte Config-Mutation ab/korrigiert, Runtime ignoriert Config-Werte und erzwingt selbst (z.B. `if self._is_solaredge: self._enable_dual_discharge = False` im `__init__`).

### Dataclass-Erweiterung mit Default
**Source:** `optimizer.py:247-280` (Decision)
**Apply to:** `Decision.discharge_active_slot`

Pattern: Neues Field am Ende des relevanten Feld-Blocks, mit Default `None`/`""`/`False`/leerer Liste — niemals required argument hinzufügen (würde alle Decision()-Callsites brechen).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `strings.json` + `translations/{de,en}.json` Slot-Labels | i18n | static-data | Heute werden UI-Texte für Reasons/Panel-Labels **nicht** in `strings.json` geführt — sie leben hardcoded in `optimizer.py:REASON_LABELS_DE` und im Frontend-JS. `strings.json` enthält nur Config-Flow-Texte (heute generisch ohne phase-spezifische Reason-Liste). Planner sollte prüfen, ob neue UI-Strings überhaupt nach `strings.json` gehören oder weiter in `REASON_LABELS_DE` bleiben (Phase-8-Pattern). Empfehlung: weiter `REASON_LABELS_DE`, **kein** Touch von `strings.json/de.json/en.json` für Reasons. Falls Wizard-Step-Header neue strings.json-Keys benötigt, dem bestehenden Step-Naming-Pattern folgen. |

---

## Metadata

**Analog search scope:**
- `custom_components/eeg_energy_optimizer/` (alle Module)
- `tests/` (Test-Helpers, Conftest, bestehende test_optimizer.py)
- `.planning/milestones/v1.1-phases/08-ha-reporter-modul/` (Phase-8-Reasons-Pattern)

**Files scanned:** 12 (optimizer.py, peakshare.py, __init__.py, const.py, config_flow.py, websocket_api.py, frontend/eeg-optimizer-panel.js, tests/conftest.py, tests/test_optimizer.py, 11-SPEC.md, 11-CONTEXT.md, 11-RESEARCH.md)

**Pattern extraction date:** 2026-05-04

**Confidence:** HIGH — Phase 11 ist Refactor-Heavy. Jede neue Code-Stelle hat einen direkten Geschwister-Pattern im selben Modul. Der Planner kann fast überall durch "Geschwister kopieren + adaptieren" arbeiten, statt neu zu erfinden.

**Critical path for planner:**
1. Plan 11-01 (const.py + Migration + compute_b_window_end + Reasons + Decision-Field) — alle Patterns sind in dieser Datei adressiert
2. Plan 11-02 (Optimizer-Refactor + PeakShare-Cache) — `_should_discharge`-Body wird zu `_evaluate_legacy_window`, neue Geschwister-Methoden folgen exakter Tuple-Schnittstelle
3. Plan 11-03 (Panel + Save-Path + Translations) — Wizard/Settings spiegeln, Save-Path erweitert SolarEdge-Block + neuen Race-Block
4. Plan 11-04 (Validation Hardening + Markdown + Activity-Log + Backend-Schema-Hint) — Markdown-Renderer-Pattern direkt aus `_build_markdown`-Geschwister
