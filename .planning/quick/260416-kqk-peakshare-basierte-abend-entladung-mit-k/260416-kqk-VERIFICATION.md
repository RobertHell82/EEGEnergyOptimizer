---
phase: 260416-kqk
verified: 2026-04-16T00:00:00Z
status: human_needed
score: 7/7 must-haves verified
overrides_applied: 0
human_verification:
  - test: "PeakShare-Checkbox im Wizard Step 4 — Conditional field visibility"
    expected: "Wenn PeakShare aktiv: Startzeit und Entladeleistung ausgeblendet, Community-Dropdown eingeblendet. Wenn deaktiviert: umgekehrt."
    why_human: "Nur visuell durch Bedienen des Wizards in einem Browser pruefbar"
  - test: "Settings-Seite — PeakShare-Checkbox togglet Felder"
    expected: "Gleiche Conditional-Visibility wie Wizard; Settings-Aenderungen persistieren nach Speichern"
    why_human: "UI-Interaktion und Persistenz nur live testbar"
  - test: "Community-Dropdown laedt aus WebSocket und waehlt 'BEG' vor"
    expected: "Beim Oeffnen von Wizard Step 4 oder Settings wird get_peakshare_communities aufgerufen; Dropdown zeigt verfuegbare Communities; 'BEG' ist vorausgewaehlt"
    why_human: "Erfordert laufende HA-Instanz mit Internetzugang zum PeakShare API"
  - test: "Dashboard Discharge-Karte zeigt PeakShare-Fenster"
    expected: "Wenn discharge_peakshare_active=true: 'Geplant HH:MM-HH:MM (PeakShare)' statt fixer Startzeit"
    why_human: "Erfordert laufenden Optimizer im Abend-Entladungs-Fenster"
  - test: "Fallback auf fixe Startzeit bei API-Ausfall"
    expected: "Wenn PeakShare API nicht erreichbar und Cache abgelaufen (>24h): Optimizer verwendet konfigurierte Startzeit (Default 20:00)"
    why_human: "Erfordert simulierten API-Ausfall und abgelaufenen Cache"
---

# Quick Task 260416-kqk: PeakShare-basierte Abend-Entladung Verification Report

**Phase Goal:** PeakShare-basierte Abend-Entladung mit konsistenter Begrifflichkeit — Integration der PeakShare REST API fuer bedarfsgesteuerte Batterieentladung.
**Verified:** 2026-04-16
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PeakShare API wird alle 6h abgefragt und liefert Community-Bedarfsdaten | VERIFIED | `peakshare.py` CACHE_FRESH_SECONDS=6*3600 (line 40); async_fetch() returns cached if age < 6h, otherwise fetches from peakshare.app/api/public/community-grid-import-forecast with 30s timeout |
| 2 | Optimizer berechnet einmalig um Sonnenuntergang ein optimales Entladefenster aus PeakShare-Daten | VERIFIED | `peakshare.py` get_discharge_plan(): date-locked by today_str (line 307), only computed after sunset - 30min (line 313), find_discharge_window() sliding window algorithm confirmed |
| 3 | Jitter von +/-60 Minuten wird einmal pro Tag gewuerfelt und bleibt stabil | VERIFIED | `peakshare.py` get_jitter_today() uses random.randint(-60, 60) (line 274), persisted in Store with jitter_value + jitter_date keys (lines 186-187, 239-240), restored on async_load() |
| 4 | Bei PeakShare-Ausfall greift Fallback-Kette: Cache (24h) > fixe Startzeit | VERIFIED | `peakshare.py` CACHE_MAX_SECONDS=24*3600 (line 41), async_fetch() returns cache if < 24h on API error (lines 251-256); optimizer.py falls back to fixed discharge_start when peakshare_plan is None (lines 725-728) |
| 5 | Settings zeigen PeakShare-Checkbox mit Community-Dropdown wenn aktiv | VERIFIED | `eeg-optimizer-panel.js` lines 2716-2732 (Settings) and 2485-2501 (Wizard Step 4): PeakShare checkbox rendered, community dropdown conditional on enable_peakshare; event handler at lines 782-788 strips settings_ prefix correctly |
| 6 | Alle Nachteinspeisung-Referenzen sind durch Abend-Entladung ersetzt | VERIFIED | grep found zero occurrences of "Nachteinspeisung" in panel JS or CLAUDE.md; optimizer.py line 689 shows "Abend-Entladung deaktiviert" (was "Nachteinspeisung deaktiviert"); only "Nachtverbrauch" remains (intentional — refers to consumption, not the feature, per CONTEXT.md) |
| 7 | Upgrade von bestehenden Instanzen setzt enable_peakshare=True automatisch, ohne Konfigurationsverlust | VERIFIED | `__init__.py` migration v12 (lines 375-380): setdefault("enable_peakshare", True) and setdefault("peakshare_community", "BEG") — existing keys untouched, version bumped to 12 |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `peakshare.py` | PeakShareProvider + find_discharge_window() | VERIFIED | 371 lines (min 100); PeakShareProvider with async_load, async_fetch, get_communities, get_jitter_today, get_discharge_plan; find_discharge_window standalone function with sliding window |
| `const.py` | CONF_ENABLE_PEAKSHARE, CONF_PEAKSHARE_COMMUNITY, DEFAULT_DISCHARGE_POWER_KW=5.0 | VERIFIED | Lines 73-74, 83: all three constants present with correct values |
| `optimizer.py` | PeakShare-integrated _should_discharge() + Abend-Entladung terminology | VERIFIED | lines 699-728: PeakShare plan integration; line 689: "Abend-Entladung deaktiviert"; Decision dataclass fields discharge_peakshare_active, discharge_window_start, discharge_window_end at lines 145-147 |
| `__init__.py` | PeakShareProvider creation, migration v12, hot-reload support | VERIFIED | Lines 483-490: provider created and passed to optimizer; lines 665, 669: preserved across hot-reload; lines 375-380: migration v12 |
| `websocket_api.py` | eeg_optimizer/get_peakshare_communities WS command | VERIFIED | Command function at line 886, registered at line 254 |
| `frontend/eeg-optimizer-panel.js` | PeakShare checkbox, community dropdown, Abend-Entladung terminology | VERIFIED | enable_peakshare in DEFAULT_CONFIG (lines 96-97); checkbox in Wizard (line 2501) and Settings (line 2732); get_peakshare_communities WS call (line 1431); zero remaining "Nachteinspeisung" occurrences |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| peakshare.py | PeakShare API | aiohttp GET with User-Agent header | VERIFIED | Lines 219-222: session.get(PEAKSHARE_API_URL, headers={"User-Agent": PEAKSHARE_USER_AGENT}, timeout=30s) |
| optimizer.py | peakshare.py | PeakShareProvider.async_fetch() + get_discharge_plan() | VERIFIED | lines 1075-1076 (async_fetch in async_run_cycle); lines 700-711 (_should_discharge calls get_discharge_plan) |
| __init__.py | peakshare.py | PeakShareProvider creation + data dict storage | VERIFIED | Lines 484-487: import, create, async_load, store in data["peakshare"] |
| frontend/eeg-optimizer-panel.js | websocket_api.py | eeg_optimizer/get_peakshare_communities WebSocket call | VERIFIED | Panel line 1431: callWS get_peakshare_communities; api registered at websocket_api.py line 254 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| peakshare.py | _cache | async_fetch() from peakshare.app API, persisted via Store | Yes — live API fetch with aiohttp, Store persistence | FLOWING |
| optimizer.py | discharge_peakshare_active | Decision dataclass populated from peakshare._discharge_plan (lines 886-892) | Yes — derived from real PeakShare plan or None | FLOWING |
| eeg-optimizer-panel.js | peakshare communities dropdown | ws get_peakshare_communities -> peakshare.get_communities() -> _cache | Yes — from API cache | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED — cannot run Python or HA integration tests in this environment (Python not available via bash). The plan's inline automated verification scripts could not be executed.

Note: All code paths were verified manually via grep/read and are substantive. The plan's verify scripts test the same things covered manually above.

### Requirements Coverage

No explicit requirement IDs referenced in PLAN frontmatter — task uses must_haves directly.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| peakshare.py | — | None found | — | — |
| optimizer.py | — | None found | — | — |
| eeg-optimizer-panel.js | — | None found | — | — |
| __init__.py | — | None found | — | — |
| websocket_api.py | — | None found | — | — |

Note: .pyc bytecache files in __pycache__/ contain old "Nachteinspeisung" strings — these are compiled artifacts from before the fix and are irrelevant to source-level correctness.

### Human Verification Required

#### 1. PeakShare-Checkbox im Wizard Step 4 — Conditional field visibility

**Test:** Wizard Step 4 oeffnen; PeakShare-Checkbox aktivieren/deaktivieren
**Expected:** Aktiv: Startzeit und Entladeleistung verschwinden, Community-Dropdown erscheint. Deaktiviert: umgekehrt. "Minimaler Ladezustand (%)" immer sichtbar.
**Why human:** Nur visuell durch Bedienen des Wizards in einem Browser pruefbar

#### 2. Settings-Seite — PeakShare-Checkbox togglet Felder korrekt

**Test:** Settings oeffnen, PeakShare-Checkbox umschalten, Speichern
**Expected:** Gleiche Conditional-Visibility wie Wizard; nach Speichern bleiben Werte erhalten (enable_peakshare, peakshare_community persistiert)
**Why human:** UI-Interaktion und Persistenz nur live testbar

#### 3. Community-Dropdown laedt aus WebSocket und waehlt "BEG" vor

**Test:** Wizard Step 4 oder Settings mit aktivem PeakShare oeffnen
**Expected:** get_peakshare_communities WS-Call wird ausgefuehrt; Dropdown zeigt echte Communities von peakshare.app; "BEG" ist vorausgewaehlt
**Why human:** Erfordert laufende HA-Instanz mit Internetzugang

#### 4. Dashboard Discharge-Karte zeigt PeakShare-Fenster zur Laufzeit

**Test:** Abwarten bis Abend-Entladung aktiv ist (oder manuell per Testoverride simulieren)
**Expected:** Dashboard zeigt "Geplant HH:MM-HH:MM (PeakShare)" statt fixer Startzeit; bei aktivem Fenster "AKTIV — X kW bis HH:MM / Y% SOC (PeakShare)"
**Why human:** Erfordert Optimizer im aktiven Entladungszustand

#### 5. Fallback auf fixe Startzeit bei API-Ausfall und abgelaufenem Cache

**Test:** PeakShare API blockieren (z.B. hosts-Datei) und Cache manuell loeschen/ablaufen lassen; Abend-Entladung beobachten
**Expected:** Optimizer faellt auf konfigurierte Startzeit (Default 20:00) zurueck, kein Fehler, kein Absturz
**Why human:** Erfordert simulierten Netzwerkfehler und abgelaufenen Cache (>24h)

### Gaps Summary

Keine Luecken gefunden. Alle 7 must-haves sind vollstaendig implementiert und verdrahtet. Die verbleibenden offenen Punkte sind ausschliesslich UI/Runtime-Verhalten, das eine laufende HA-Instanz erfordert.

---

_Verified: 2026-04-16_
_Verifier: Claude (gsd-verifier)_
