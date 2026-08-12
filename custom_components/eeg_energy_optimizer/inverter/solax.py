"""SolaX Gen4+ inverter control via HA solax_modbus integration.

Uses Mode 1 Remote Control with two-phase write model:
  Phase 1: Set parameters via number.set_value / select.select_option (DATA_LOCAL)
  Phase 2: Press trigger button to write all params to Modbus registers

Entity prefix varies by installation — resolved from config or SOLAX_ENTITY_DEFAULTS.
All power values converted from InverterBase kW to SolaX Watts.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .base import InverterBase

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.storage import Store
except ImportError:  # pragma: no cover — test environment
    Store = None  # type: ignore

_LOGGER = logging.getLogger(__name__)

SOLAX_DOMAIN = "solax_modbus"

# Entity Key -> Default Entity ID Mapping
SOLAX_ENTITY_DEFAULTS = {
    "remotecontrol_power_control": "select.solax_inverter_remotecontrol_power_control",
    "remotecontrol_active_power": "number.solax_inverter_remotecontrol_active_power",
    "remotecontrol_autorepeat_duration": "number.solax_inverter_remotecontrol_autorepeat_duration",
    "remotecontrol_duration": "number.solax_inverter_remotecontrol_duration",
    "remotecontrol_trigger": "button.solax_inverter_remotecontrol_trigger",
    "battery_charge_max_current": "number.solax_inverter_battery_charge_max_current",
}

# Suffix-Muster je Steuer-Entity. Neuere solax_modbus-Versionen (≥2025.x)
# hängen Mode-Suffixe an die Entity-Namen an (remotecontrol_power_control_mode_1,
# remotecontrol_trigger_mode_1_7, …), ältere nutzen die Basisnamen. Die
# Mode-Bereiche in den Suffixen (z. B. _mode_1_7) können sich zwischen
# Versionen ändern, daher generisches [0-9_]+. *_direct-Varianten
# (Direktregister-Schreibmodus) werden bewusst NICHT gematcht — der Treiber
# nutzt das Zwei-Phasen-Modell (Parameter setzen + Trigger).
SOLAX_CONTROL_ENTITY_PATTERNS: dict[str, tuple[str, re.Pattern]] = {
    "remotecontrol_power_control": ("select", re.compile(r"remotecontrol_power_control(_mode_1)?$")),
    "remotecontrol_active_power": ("number", re.compile(r"remotecontrol_active_power(_mode_1)?$")),
    "remotecontrol_autorepeat_duration": ("number", re.compile(r"remotecontrol_autorepeat_duration(_mode_[0-9_]+)?$")),
    "remotecontrol_duration": ("number", re.compile(r"remotecontrol_duration(_mode_[0-9_]+)?$")),
    "remotecontrol_trigger": ("button", re.compile(r"remotecontrol_trigger(_mode_[0-9_]+)?$")),
    "battery_charge_max_current": ("number", re.compile(r"battery_charge_max_current$")),
    "selfuse_discharge_min_soc": ("number", re.compile(r"selfuse_discharge_min_soc$")),
}


def find_solax_control_entity(hass: Any, config_key: str) -> str | None:
    """Suche die SolaX-Steuer-Entity per Suffix-Scan (versionstolerant).

    Liefert None, wenn keine passende Entity existiert. Bei mehreren Treffern
    (Übergangsinstallationen mit alter + neuer Benennung) gewinnt der kürzeste
    Name — das ist der Basisname ohne Mode-Suffix.
    """
    domain, pattern = SOLAX_CONTROL_ENTITY_PATTERNS[config_key]
    try:
        matches = [
            state.entity_id
            for state in hass.states.async_all(domain)
            if pattern.search(state.entity_id.split(".", 1)[1])
        ]
    except TypeError:  # Test-Umgebung ohne echte State-Machine
        return None
    if not matches:
        return None
    return min(matches, key=len)


class SolaXStateStore:
    """Persistiert den Original-Wert von battery_charge_max_current über HA-Reboots.

    Wird beim ersten async_set_charge_limit-Aufruf mit aktuellem State > 0 befüllt.
    async_stop_forcible liest den Wert beim Beenden von Morgen-Einspeisung wieder aus.
    """

    STORAGE_KEY = "eeg_energy_optimizer.solax_state"
    STORAGE_VERSION = 1

    def __init__(self, hass: Any) -> None:
        self._store = (
            Store(hass, self.STORAGE_VERSION, self.STORAGE_KEY)
            if Store is not None
            else None
        )
        self._data: dict = {}
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        if self._store is None:
            self._loaded = True
            return
        data = await self._store.async_load()
        self._data = data if isinstance(data, dict) else {}
        self._loaded = True

    async def async_save_original_current(self, amps: float) -> None:
        self._data["battery_charge_max_current_original"] = float(amps)
        if self._store is not None:
            await self._store.async_save(self._data)

    @property
    def original_current(self) -> float | None:
        val = self._data.get("battery_charge_max_current_original")
        return float(val) if val is not None else None


class SolaXInverter(InverterBase):
    """SolaX Gen4+ inverter control via solax_modbus HA integration."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        self._state_store = SolaXStateStore(hass)

    def _resolve_entity(self, config_key: str) -> str:
        """Löse die Steuer-Entity auf: Config → Suffix-Scan → Default.

        Der konfigurierte Wert gilt nur, solange die Entity auch existiert —
        nach einem solax_modbus-Update mit umbenannten Entities (Mode-Suffixe)
        greift sonst automatisch der Suffix-Scan.
        """
        configured = self._config.get(f"solax_{config_key}")
        if configured and self._hass.states.get(configured) is not None:
            return configured
        found = find_solax_control_entity(self._hass, config_key)
        if found:
            return found
        return configured or SOLAX_ENTITY_DEFAULTS[config_key]

    async def _set_number(self, config_key: str, value: float) -> None:
        """Set a number entity value. Resolves entity from config, scan or defaults."""
        await self._hass.services.async_call(
            "number", "set_value",
            {"entity_id": self._resolve_entity(config_key), "value": value},
            blocking=True,
        )

    async def _set_select(self, config_key: str, option: str) -> None:
        """Set a select entity option. Resolves entity from config, scan or defaults."""
        await self._hass.services.async_call(
            "select", "select_option",
            {"entity_id": self._resolve_entity(config_key), "option": option},
            blocking=True,
        )

    async def _press_trigger(self) -> None:
        """Press the remote control trigger button to execute Modbus write."""
        await self._hass.services.async_call(
            "button", "press",
            {"entity_id": self._resolve_entity("remotecontrol_trigger")},
            blocking=True,
        )

    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery charge limit. power_kw=0 blocks charging only (NOT discharge).

        Uses battery_charge_max_current entity (Ampere) — analog zu Huawei
        batterien_maximale_ladeleistung und Fronius StorCtl_Mod Bit 0 + InWRte=0.
        Self-Use-Mode der SolaX läuft im Hintergrund weiter; Discharge bleibt
        möglich bis selfuse_discharge_min_soc.

        Der Originalwert wird beim ersten Eingriff in einen Store persistiert
        (siehe SolaXStateStore). Bei Reboot mitten im Block (aktueller State = 0)
        wird der Cache NICHT überschrieben.
        """
        try:
            await self._ensure_original_cached()

            if power_kw == 0:
                await self._set_number("battery_charge_max_current", 0)
            else:
                voltage = self._read_battery_voltage_or_default()
                max_a = self._read_max_charge_current_attribute() or 30.0
                amps = max(0.0, min(power_kw * 1000.0 / voltage, max_a))
                await self._set_number("battery_charge_max_current", amps)

            # Sicherstellen, dass Mode 1 NICHT aktiv ist (Migration für
            # Bestands-Setups, die noch im alten Mode-1-Idle stehen).
            await self._set_select("remotecontrol_power_control", "Disabled")
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to set charge limit")
            return False

    async def _ensure_original_cached(self) -> None:
        """Cache aktuellen battery_charge_max_current in Store, falls > 0 und noch nicht gespeichert."""
        if self._state_store is None:
            return
        await self._state_store.async_load()
        if self._state_store.original_current is not None:
            return
        current = self._read_current_charge_max_current()
        if current is not None and current > 0:
            await self._state_store.async_save_original_current(current)

    def _read_current_charge_max_current(self) -> float | None:
        """Liest aktuellen State von battery_charge_max_current Entity. Liefert None wenn nicht verfügbar."""
        state = self._hass.states.get(self._resolve_entity("battery_charge_max_current"))
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _read_max_charge_current_attribute(self) -> float | None:
        """Liest attributes.max des battery_charge_max_current Entities (Hardware-Maximum)."""
        state = self._hass.states.get(self._resolve_entity("battery_charge_max_current"))
        if state is None:
            return None
        max_val = state.attributes.get("max")
        try:
            return float(max_val) if max_val is not None else None
        except (TypeError, ValueError):
            return None

    def _read_battery_voltage_or_default(self) -> float:
        """Liest aktuelle Batteriespannung. Fallback: 400 V (typischer SolaX-Hochvolt-Bereich)."""
        state = self._hass.states.get("sensor.solax_inverter_battery_voltage_charge")
        if state is not None:
            try:
                v = float(state.state)
                if v > 50:
                    return v
            except (TypeError, ValueError):
                pass
        return 400.0

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Start forced battery discharge at given power.

        Uses "Enabled Battery Control" with negative active_power.
        """
        try:
            power_w = -abs(int(power_kw * 1000))
            await self._set_select("remotecontrol_power_control", "Enabled Battery Control")
            await self._set_number("remotecontrol_active_power", power_w)
            await self._set_number("remotecontrol_duration", 300)
            await self._set_number("remotecontrol_autorepeat_duration", 60)
            await self._press_trigger()
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to set discharge")
            return False

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge, return to automatic mode.

        Beendet Mode 1 (Disabled + active_power=0 + autorepeat=0 + trigger)
        UND restoriert battery_charge_max_current aus dem Store. Fallback wenn
        Store leer: attributes.max des Entities (typisch 30 A).
        """
        try:
            await self._set_select("remotecontrol_power_control", "Disabled")
            await self._set_number("remotecontrol_active_power", 0)
            await self._set_number("remotecontrol_duration", 20)
            await self._set_number("remotecontrol_autorepeat_duration", 0)
            await self._press_trigger()

            original = await self._resolve_original_charge_current()
            if original is not None:
                await self._set_number("battery_charge_max_current", original)
            return True
        except Exception:
            _LOGGER.exception("SolaX: Failed to stop forcible mode")
            return False

    async def _resolve_original_charge_current(self) -> float | None:
        """Liefert gecachten Originalwert; Fallback ist attributes.max des Entities."""
        if self._state_store is not None:
            await self._state_store.async_load()
            original = self._state_store.original_current
            if original is not None:
                return original
        return self._read_max_charge_current_attribute()

    @property
    def is_available(self) -> bool:
        """Whether the SolaX Modbus integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(SOLAX_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
