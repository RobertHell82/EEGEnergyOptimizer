---
phase: quick-260327-blj
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - STORY_SOLAX_INVERTER.md
autonomous: true
requirements: [SOLAX-WRITE-DOCS]

must_haves:
  truths:
    - "Section 2 (Schreibende Zugriffe) is fully documented with concrete register tables, entity mappings, and implementation approach instead of TODO placeholders"
    - "Each InverterBase method (set_charge_limit, set_discharge, stop_forcible, is_available) has a clear implementation description with code pattern and rationale"
    - "Caveats and open questions from research are documented so future implementer knows the risks"
    - "Two-phase write architecture (DATA_LOCAL + trigger) is explained clearly"
  artifacts:
    - path: "STORY_SOLAX_INVERTER.md"
      provides: "Complete SolaX inverter story with write/control documentation"
      contains: "Zwei-Phasen-Schreibarchitektur"
  key_links:
    - from: "STORY_SOLAX_INVERTER.md"
      to: "RESEARCH.md"
      via: "Content transfer of research findings"
      pattern: "remotecontrol_trigger|Enabled Battery Control|0x7C"
---

<objective>
Update STORY_SOLAX_INVERTER.md Section 2 (Schreibende Zugriffe) to replace the TODO placeholders with the completed research findings from RESEARCH.md. Transfer register tables, entity mappings, InverterBase method implementations, duration/autorepeat strategy, and caveats into the story document.

Purpose: Consolidate the research into the canonical story document so it serves as the single implementation reference for the SolaX inverter feature.
Output: Fully documented STORY_SOLAX_INVERTER.md with no remaining TODO items in Section 2.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@STORY_SOLAX_INVERTER.md
@.planning/quick/260327-blj-solax-modbus-write-sensoren-recherche-sc/RESEARCH.md
@.planning/quick/260327-blj-solax-modbus-write-sensoren-recherche-sc/CONTEXT.md
</context>

<tasks>

<task type="auto">
  <name>Task 1: Replace Section 2 TODOs with researched write documentation</name>
  <files>STORY_SOLAX_INVERTER.md</files>
  <action>
Replace the entire Section 2 ("Schreibende Zugriffe") in STORY_SOLAX_INVERTER.md. Remove all TODO checkboxes and placeholder text. Replace with the following structured content derived from RESEARCH.md:

**2.1 Steuerungsarchitektur (Zwei-Phasen-Schreibmodell)**
- Explain DATA_LOCAL entities (stored in integration memory only, NOT written to Modbus)
- Explain trigger button mechanism (collects all DATA_LOCAL values, writes as single write_multiple_registers to 0x7C)
- Include the write method table: WRITE_SINGLE_MODBUS, WRITE_MULTISINGLE_MODBUS, WRITE_MULTI_MODBUS, WRITE_DATA_LOCAL
- Emphasize: remotecontrol_* entities use WRITE_DATA_LOCAL — actual Modbus write only on trigger press

**2.2 Register-Tabelle (Mode 1 Remote Control)**
- Transfer the Mode 1 register table from RESEARCH.md Section 2.1 (offsets at 0x7C: Active Power S32, Reactive Power, Duration, Target SOC, etc.)
- Include battery configuration registers from Section 2.3 (selfuse_discharge_min_soc at 0x61, battery_charge_max_current at 0x24, battery_charge_upper_soc at 0xE0)
- Include work mode register warning: charger_use_mode (0x1F) writes to EEPROM — do NOT toggle frequently

**2.3 HA Entity-Mapping (Schreibende Entities)**
- Transfer control entities table for Mode 1 from RESEARCH.md Section 3.1 (select, number, button entities with their config keys, platforms, and purposes)
- Transfer battery SOC/current direct-write entities from Section 3.3
- Include the required vs optional entity classification from Section 11
- Note: Entity prefix varies (solax_, solax_inverter_, solaxmodbus_) — auto-detection required

**2.4 remotecontrol_power_control Optionen**
- Transfer the options table from RESEARCH.md Section 4 (Disabled, Enabled Power Control, Enabled Grid Control, Enabled Battery Control, Enabled Self Use, Enabled Feedin Priority, Enabled No Discharge)
- Include power sign convention: positive = CHARGE, negative = DISCHARGE

**2.5 InverterBase-Methoden Implementierung**
For each method, provide: Zweck, Ansatz, Pseudocode-Pattern (from RESEARCH.md Section 6), and key notes:

- `async_set_charge_limit(power_kw)`: Use "Enabled Battery Control" with active_power=0 for charge blocking. Explain why NOT "Enabled No Discharge" (it allows charging, opposite of what we want). Mention "Enabled Feedin Priority" as alternative to test on hardware.
- `async_set_discharge(power_kw, target_soc)`: Use "Enabled Battery Control" with negative power. Set selfuse_discharge_min_soc as software floor. Note: firmware may not enforce min SOC during remote control — optimizer must monitor SOC in 30s cycle.
- `async_stop_forcible()`: Set "Disabled", active_power=0, autorepeat_duration=0, press trigger.
- `is_available`: Check config_entries for solax_modbus domain, state == loaded.
- Include helper method pattern (_set_number, _set_select, _press_trigger) with SOLAX_ENTITY_DEFAULTS dict.

**2.6 Duration und Autorepeat-Strategie**
- Transfer from RESEARCH.md Section 7: duration=60s, autorepeat_duration=120s, timeout=0
- Explain why: optimizer cycle is 30s, autorepeat gives 4x safety margin
- When stopping: set autorepeat_duration=0 before pressing trigger with "Disabled"

**2.7 Gen4 vs Gen5 vs Gen6 Kompatibilitaet**
- Brief table from RESEARCH.md Section 8: all three support Mode 1 with identical register layout
- Note: Gen2/Gen3 fundamentally different, NOT supported (no remote control entities)

**2.8 Caveats und Risiken**
Transfer all 7 caveats from RESEARCH.md Section 9 as numbered list:
1. Lock State muss entsperrt sein (Passwort 2014)
2. Target SOC nicht firmware-seitig enforced — Software-Monitoring Pflicht
3. Power Value Clamping (inverter clamps silently to rated capacity)
4. Einheiten: SolaX = Watts, InverterBase = kW — Umrechnung noetig
5. Sleep Mode: Modbus kann nachts ausfallen, Entities werden unavailable
6. X1 Fit (AC-coupled) hat moeglicherweise keinen remotecontrol_trigger
7. Entity-Prefix variiert — Auto-Detection erforderlich

Also update Section 5 ("Offene Fragen"):
- Mark resolved questions as erledigt with brief answer
- Keep genuinely open questions (hardware test needed) and add new ones from CONTEXT.md open questions
- Specifically: "Enabled Feedin Priority vs Enabled Battery Control (power=0)" needs hardware test
- Lock state handling needs hardware test
- X1 Fit compatibility needs hardware test

Keep all existing content in Sections 1, 3, and 4 unchanged. Keep the document style consistent: German text, ASCII-safe (no umlauts), Markdown tables.
  </action>
  <verify>
    <automated>grep -c "TODO" STORY_SOLAX_INVERTER.md | grep -q "^0$" && echo "PASS: No TODOs remain" || echo "FAIL: TODOs still present"</automated>
  </verify>
  <done>
    - Section 2 contains no TODO placeholders
    - All 4 InverterBase methods documented with implementation approach and pseudocode
    - Register table present with addresses (0x7C, 0x61, 0x24, etc.)
    - Entity mapping table present with config keys and default entity IDs
    - Caveats section lists all 7 risks
    - Duration/autorepeat strategy documented
    - Two-phase write architecture explained
    - Section 5 open questions updated (resolved items marked, hardware-test items kept)
  </done>
</task>

</tasks>

<verification>
- No TODO items remain in Section 2 of STORY_SOLAX_INVERTER.md
- Document contains key terms: "Zwei-Phasen", "remotecontrol_trigger", "0x7C", "Enabled Battery Control", "WRITE_DATA_LOCAL"
- Sections 1, 3, 4 remain unchanged
- Section 5 is updated with resolved/open status
</verification>

<success_criteria>
STORY_SOLAX_INVERTER.md is a complete, self-contained implementation reference for the SolaX inverter write operations. A developer can implement inverter/solax.py using only this document without needing to consult RESEARCH.md.
</success_criteria>

<output>
After completion, create `.planning/quick/260327-blj-solax-modbus-write-sensoren-recherche-sc/260327-blj-SUMMARY.md`
</output>
