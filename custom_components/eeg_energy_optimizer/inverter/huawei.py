"""Huawei SUN2000 inverter control via HA Huawei Solar services.

Unterstützt Single-Inverter und Master/Slave-Setups mit mehreren
Wechselrichtern + Batterien. Jede Batterie ist in huawei_solar ein eigenes
Gerät (device_id) mit eigenem SOC/Kapazität/Ladelimit und eigenen
forcible_charge/discharge-Services — die Integration summiert nichts über
Geräte hinweg. Dieser Treiber:

- steuert **alle** konfigurierten Batteriegeräte (Laden blockieren / entladen
  / stoppen) statt nur des ersten,
- verteilt die Entladeleistung proportional zur nutzbaren Energie je Batterie,
- liefert über get_combined_battery_state() einen kapazitätsgewichteten
  Gesamt-SOC + Summenkapazität (nur bei ≥2 Geräten; Single-Inverter bleibt
  bit-identisch zum bisherigen Verhalten).

Pro-Gerät-Entities (Ladelimit, SOC, Kapazität) werden über die HA-Entity-
Registry aufgelöst (device_id → Entities) — robust gegen DE/EN-Namen und
abweichende Gerätenamen. Nur im Single-Device-Legacy-Modus greift zusätzlich
der alte globale States-Scan als Fallback.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from .base import InverterBase
from ._distribution import distribute_proportional

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

HUAWEI_DOMAIN = "huawei_solar"
MAX_CHARGE_POWER_CANDIDATES = [
    "number.batteries_maximale_ladeleistung",
    "number.batterien_maximale_ladeleistung",
]
# Die Entity-ID hängt von HA-Sprache und Gerätename zum Erstellzeitpunkt ab —
# Fallback-Suche über sprachtypische Suffixe (DE/EN) statt exakter IDs.
MAX_CHARGE_POWER_SUFFIXES = (
    "maximale_ladeleistung",
    "maximum_charging_power",
)
MAX_DISCHARGE_POWER_SUFFIXES = (
    "maximale_entladeleistung",
    "maximum_discharging_power",
)
# Per-Batterie-Sensoren (für Combined-SOC + proportionale Entladung). Innerhalb
# eines Geräts (registry-gefiltert) eindeutig, daher reicht Suffix-Matching.
SOC_SUFFIXES = (
    "batterieladung",
    "battery_state_of_capacity",
    "state_of_capacity",
)
CAPACITY_SUFFIXES = (
    "akkukapazitat",
    "rated_capacity",
    "nutzbare_kapazitat",
)


class HuaweiInverter(InverterBase):
    """Huawei SUN2000 inverter control via HA Huawei Solar services."""

    def __init__(self, hass: Any, config: dict) -> None:
        super().__init__(hass, config)
        # Multi-Device: Liste aller Batteriegeräte. Fallback auf Legacy-Single-
        # Key, damit Bestandsanlagen ohne Neukonfiguration weiterlaufen.
        ids = list(config.get("huawei_device_ids") or [])
        if not ids:
            single = config.get("huawei_device_id")
            if single:
                ids = [single]
        if not ids:
            raise ValueError(
                "HuaweiInverter requires 'huawei_device_id' in config — "
                "device was not auto-detected. Re-run setup wizard to detect the Huawei device."
            )
        self._device_ids: list[str] = ids
        # Pro Gerät das Ladeleistungs-Entity auflösen (None = noch nicht da).
        self._charge_entities: dict[str, str | None] = {
            did: self._resolve_charge_entity(did) for did in ids
        }
        if all(v is None for v in self._charge_entities.values()):
            _LOGGER.warning(
                "Huawei: Kein Ladeleistungs-Entity gefunden (erwartet: %s). "
                "Laden-Blockieren (Morgen-Einspeisung) bleibt deaktiviert, bis das "
                "Entity verfügbar ist. Prüfe, ob die huawei_solar-Integration mit "
                "erweiterten Berechtigungen (Installer-Login) eingerichtet ist.",
                MAX_CHARGE_POWER_CANDIDATES,
            )

    # ------------------------------------------------------------------
    # Backwards-compat: erstes (oder einziges) Ladeleistungs-Entity.
    # ------------------------------------------------------------------
    @property
    def _max_charge_entity(self) -> str | None:
        """Ladeleistungs-Entity des ersten Geräts (Legacy-Attribut)."""
        return self._charge_entities.get(self._device_ids[0])

    # ------------------------------------------------------------------
    # Entity-Auflösung
    # ------------------------------------------------------------------
    def _registry_entities_for_device(self, device_id: str) -> list[str]:
        """Alle Entity-IDs, die in der HA-Registry diesem Gerät zugeordnet sind."""
        try:
            from homeassistant.helpers import entity_registry as er

            ent_reg = er.async_get(self._hass)
            return [
                e.entity_id
                for e in ent_reg.entities.values()
                if e.device_id == device_id
            ]
        except Exception:
            # Keine Registry verfügbar (z. B. Test-Umgebung) → leer, Aufrufer
            # fällt auf den globalen States-Scan zurück.
            return []

    def _device_entity_by_suffix(
        self, device_id: str, domain: str, suffixes: tuple[str, ...]
    ) -> str | None:
        """Entity dieses Geräts in `domain`, dessen Name auf ein Suffix endet.

        Word-Boundary-Check (Suffix beginnt an einer ``_``-Grenze), damit
        z. B. ``maximale_entladeleistung`` nicht als Lade-Entity durchgeht.

        huawei_solar hängt bei Master/Slave einen Geräte-Index an das ENDE des
        Namens (``batterien_batterieladung_2`` für den Slave). Dieses optionale
        ``_<zahl>``-Suffix wird vor dem Vergleich entfernt, damit der Slave-
        Sensor genauso gefunden wird wie der des Masters.
        """
        for eid in self._registry_entities_for_device(device_id):
            if not eid.startswith(f"{domain}."):
                continue
            name = eid.split(".", 1)[1]
            core = re.sub(r"_\d+$", "", name)
            for suf in suffixes:
                for cand in (name, core):
                    if cand.endswith(suf) and (
                        cand == suf or cand[: -len(suf)].endswith("_")
                    ):
                        return eid
        return None

    def _resolve_charge_entity(self, device_id: str) -> str | None:
        """Find this device's max-charge-power entity, or None if not (yet) there."""
        # 1. Registry: number-Entity dieses Geräts mit Lade-Suffix.
        eid = self._device_entity_by_suffix(
            device_id, "number", MAX_CHARGE_POWER_SUFFIXES
        )
        if eid and self._hass.states.get(eid) is not None:
            _LOGGER.debug("Huawei: Using charge power entity %s (registry)", eid)
            return eid
        # 2. Single-Device-Fallback: globaler States-Scan (Legacy-Bestandsanlagen).
        #    Bei Multi-Device unzulässig — würde beiden Geräten dasselbe Entity
        #    zuweisen.
        if len(self._device_ids) <= 1:
            for entity_id in MAX_CHARGE_POWER_CANDIDATES:
                if self._hass.states.get(entity_id) is not None:
                    _LOGGER.debug("Huawei: Using charge power entity %s", entity_id)
                    return entity_id
            for state in self._hass.states.async_all("number"):
                if any(
                    state.entity_id.endswith(f"_{suffix}")
                    for suffix in MAX_CHARGE_POWER_SUFFIXES
                ):
                    _LOGGER.debug(
                        "Huawei: Using charge power entity %s (suffix match)",
                        state.entity_id,
                    )
                    return state.entity_id
        return None

    def _ensure_charge_entity(self, device_id: str) -> str | None:
        """Re-resolve lazily — the entity may appear after a slow huawei_solar start."""
        if self._charge_entities.get(device_id) is None:
            resolved = self._resolve_charge_entity(device_id)
            if resolved is not None:
                self._charge_entities[device_id] = resolved
                _LOGGER.info(
                    "Huawei: Ladeleistungs-Entity nachträglich gefunden: %s",
                    resolved,
                )
        return self._charge_entities.get(device_id)

    # ------------------------------------------------------------------
    # Sensor-Reads (pro Gerät)
    # ------------------------------------------------------------------
    def _read_sensor_float(self, entity_id: str | None) -> float | None:
        """Read an entity state and parse as float. Returns None if unavailable."""
        if not entity_id:
            return None
        state = self._hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown", None):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _get_max_charge_power(self, entity_id: str) -> float:
        """Read the hardware max of the charge power number entity."""
        state = self._hass.states.get(entity_id)
        if state is None:
            return 5000.0
        return float(state.attributes.get("max", 5000))

    def _read_battery_soc_pct(self, device_id: str) -> float | None:
        eid = self._device_entity_by_suffix(device_id, "sensor", SOC_SUFFIXES)
        return self._read_sensor_float(eid)

    def _read_battery_capacity_kwh(self, device_id: str) -> float | None:
        """Battery capacity (kWh) for a device.

        Sensor value wins; falls back to the per-device manual capacity from
        config (``huawei_battery_capacities``) — required on installations
        where huawei_solar exposes no akkukapazitat value.
        """
        eid = self._device_entity_by_suffix(device_id, "sensor", CAPACITY_SUFFIXES)
        cap = self._read_sensor_float(eid)
        if cap is not None and cap > 0:
            return cap
        manual = (self._config.get("huawei_battery_capacities") or {}).get(device_id)
        if manual:
            try:
                val = float(manual)
                if val > 0:
                    return val
            except (ValueError, TypeError):
                pass
        return None

    def _read_max_discharge_power_w(self, device_id: str) -> float | None:
        """Hardware max discharge power (W) from the discharge-limit number entity."""
        eid = self._device_entity_by_suffix(
            device_id, "number", MAX_DISCHARGE_POWER_SUFFIXES
        )
        if not eid:
            return None
        state = self._hass.states.get(eid)
        if state is None:
            return None
        try:
            return float(state.attributes.get("max", state.state))
        except (ValueError, TypeError):
            return None

    # ------------------------------------------------------------------
    # Combined battery state (Multi-Device)
    # ------------------------------------------------------------------
    def get_combined_battery_state(self) -> tuple[float | None, float | None]:
        """Capacity-weighted SOC + total capacity across all battery devices.

        Nur bei ≥2 Geräten aktiv — Single-Inverter liefert (None, None), sodass
        der Optimizer wie bisher den konfigurierten battery_soc_sensor nutzt.

        Liegen alle Einzelkapazitäten vor (Sensor oder manuell), wird der SOC
        kapazitätsgewichtet und die Summenkapazität zurückgegeben. Fehlt eine
        Kapazität (manche Huawei-Anlagen liefern keinen akkukapazitat-Wert),
        wird auf den ungewichteten SOC-Mittelwert zurückgegriffen und keine
        Kapazität gemeldet (Optimizer nutzt dann battery_capacity_kwh). So geht
        der SOC nie verloren, nur weil die Kapazität fehlt. (None, None) erst,
        wenn KEIN Gerät einen SOC liefert.
        """
        if len(self._device_ids) < 2:
            return (None, None)
        socs: list[float] = []
        total_cap = 0.0
        weighted = 0.0
        all_caps = True
        for did in self._device_ids:
            soc = self._read_battery_soc_pct(did)
            if soc is None:
                _LOGGER.debug("Huawei: kein SOC für %s", did)
                continue
            socs.append(soc)
            cap = self._read_battery_capacity_kwh(did)
            if cap is not None and cap > 0:
                total_cap += cap
                weighted += soc * cap
            else:
                all_caps = False
        if not socs:
            return (None, None)
        if all_caps and total_cap > 0:
            return (weighted / total_cap, total_cap)
        _LOGGER.debug(
            "Huawei: Combined-SOC ohne vollständige Kapazitäten — ungewichteter "
            "Mittelwert über %d Batterie(n)", len(socs),
        )
        return (sum(socs) / len(socs), None)

    @property
    def has_combined_battery_state(self) -> bool:
        """≥2 Batteriegeräte → Combined-Sensoren anlegen (strukturell).

        Bewusst nicht wertbasiert: huawei_solar exponiert die SOC-Sensoren beim
        Start teils erst nach >10s. Der Combined-Sensor wird trotzdem angelegt
        und füllt sich, sobald die Quell-Sensoren verfügbar sind.
        """
        return len(self._device_ids) >= 2

    def _compute_discharge_distribution(self, total_kw: float) -> dict | None:
        """Per-device discharge power proportional to usable energy.

        usable_kwh = soc% × capacity (Reserve 0 — der Optimizer steuert das
        Min-SOC-Stop selbst; relevant ist nur das Verhältnis der Batterien).
        Returns None, wenn ein Sensor fehlt → Aufrufer nutzt Gleichverteilung.
        """
        units = []
        for did in self._device_ids:
            soc = self._read_battery_soc_pct(did)
            cap = self._read_battery_capacity_kwh(did)
            max_w = self._read_max_discharge_power_w(did)
            if soc is None or cap is None or max_w is None:
                _LOGGER.debug(
                    "Huawei: %s missing sensor for proportional split "
                    "(soc=%s cap=%s max_w=%s) — fallback to equal",
                    did, soc, cap, max_w,
                )
                return None
            units.append({
                "device_id": did,
                "usable_kwh": max(0.0, cap * soc / 100.0),
                "max_kw": max_w / 1000.0,
            })
        return distribute_proportional(total_kw, units, id_key="device_id")

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------
    async def async_set_charge_limit(self, power_kw: float) -> bool:
        """Set battery max charge power on all devices.

        power_kw=0 blocks charging, any other value sets the limit. A device
        without a resolvable charge entity is skipped (logged); a partial
        failure returns False so the optimizer treats it conservatively.
        """
        power_w = int(power_kw * 1000)
        any_ok = False
        all_ok = True
        for did in self._device_ids:
            entity_id = self._ensure_charge_entity(did)
            if entity_id is None:
                _LOGGER.warning(
                    "Huawei: Ladelimit %.1f kW für %s nicht gesetzt — "
                    "kein Ladeleistungs-Entity verfügbar",
                    power_kw, did,
                )
                all_ok = False
                continue
            try:
                await self._hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": entity_id, "value": power_w},
                    blocking=True,
                )
                any_ok = True
            except Exception:
                _LOGGER.exception(
                    "Huawei: Failed to set charge limit via %s", entity_id
                )
                all_ok = False
        return any_ok and all_ok

    async def async_set_discharge(
        self, power_kw: float, target_soc: float | None = None
    ) -> bool:
        """Start forced battery discharge across all devices.

        Total power is distributed proportional to each battery's usable
        energy, capped at its max discharge power. Falls back to an equal
        split when any battery sensor is unavailable.
        """
        soc = max(int(target_soc) if target_soc is not None else 12, 12)
        distribution = self._compute_discharge_distribution(power_kw)
        if distribution is None:
            per = power_kw / len(self._device_ids)
            distribution = {did: per for did in self._device_ids}
            _LOGGER.info(
                "Huawei: discharge equal split (sensor fallback): %.2f kW × %d",
                per, len(self._device_ids),
            )
        else:
            _LOGGER.info(
                "Huawei: discharge proportional split (total %.2f kW): %s",
                power_kw,
                {did: f"{kw:.2f}kW" for did, kw in distribution.items()},
            )
        any_ok = False
        all_ok = True
        for did in self._device_ids:
            power_w = str(int(distribution.get(did, 0.0) * 1000))
            try:
                await self._hass.services.async_call(
                    HUAWEI_DOMAIN,
                    "forcible_discharge_soc",
                    {
                        "device_id": did,
                        "power": power_w,
                        "target_soc": soc,
                    },
                    blocking=True,
                )
                any_ok = True
            except Exception:
                _LOGGER.exception("Huawei: Failed to set discharge on %s", did)
                all_ok = False
        return any_ok and all_ok

    async def async_stop_forcible(self) -> bool:
        """Stop forced charge/discharge on all devices, return to automatic mode.

        Per device: restore max charge power (if entity available), then stop
        any forcible charge/discharge. Each device is handled independently so
        a partial Modbus failure does not block the rest.
        """
        all_ok = True
        for did in self._device_ids:
            entity_id = self._ensure_charge_entity(did)
            try:
                # Restore max charge power (skip if the entity is unavailable —
                # stopping the forcible mode must still go through)
                if entity_id is not None:
                    max_power = self._get_max_charge_power(entity_id)
                    await self._hass.services.async_call(
                        "number",
                        "set_value",
                        {"entity_id": entity_id, "value": max_power},
                        blocking=True,
                    )
                # Stop forcible charge/discharge if active
                await self._hass.services.async_call(
                    HUAWEI_DOMAIN,
                    "stop_forcible_charge",
                    {"device_id": did},
                    blocking=True,
                )
            except Exception:
                _LOGGER.exception("Huawei: Failed to stop forcible mode on %s", did)
                all_ok = False
        return all_ok

    @property
    def is_available(self) -> bool:
        """Whether the Huawei Solar integration is loaded and available."""
        entries = self._hass.config_entries.async_entries(HUAWEI_DOMAIN)
        return any(entry.state.value == "loaded" for entry in entries)
