"""Gemeinsame Leistungsverteilung für Multi-Battery-Setups.

Verteilt eine Gesamt-Entladeleistung auf mehrere Batterien proportional zu
ihrer nutzbaren Energie ((SOC − Reserve) × Kapazität), gedeckelt an der
maximalen Entladeleistung je Einheit. Überschuss von gedeckelten Einheiten
wird iterativ auf die verbleibenden mit Headroom umverteilt.

Wird von SolarEdge (i1+i2+…) und Huawei (Master/Slave) genutzt — eine Quelle
der Wahrheit, damit beide Treiber dieselbe erprobte Logik teilen.
"""

from __future__ import annotations


def distribute_proportional(
    total_kw: float, units: list[dict], *, id_key: str = "key"
) -> dict:
    """Verteile total_kw proportional zu usable_kwh, gedeckelt an max_kw.

    Args:
        total_kw: Gesamt-Entladeleistung, die verteilt werden soll.
        units: Liste von Dicts mit den Schlüsseln ``id_key`` (eindeutige ID
            der Einheit), ``usable_kwh`` (nutzbare Energie) und ``max_kw``
            (maximale Entladeleistung der Einheit).
        id_key: Name des ID-Felds in den Dicts (SolarEdge: "prefix",
            Huawei: "device_id").

    Returns:
        Dict ``{id: power_kw}`` mit Σ power ≈ total_kw (begrenzt durch die
        Caps), Allokation proportional zu usable_kwh.

    Iterativ: Sobald eine Einheit ihren Cap erreicht, wird sie fixiert und der
    Rest auf den noch nicht gedeckelten Pool umverteilt. Begrenzt durch
    len(units) Iterationen (jede Runde deckelt ≥1 Einheit oder terminiert).
    """
    allocated = {u[id_key]: 0.0 for u in units}
    # Fallback: keine Einheit hat nutzbare Energie (alle an der Reserve)
    # → gleichmäßige Aufteilung, je Einheit gedeckelt.
    pool = [u for u in units if u["usable_kwh"] > 0]
    if not pool:
        if not units:
            return {}
        per = total_kw / len(units)
        return {u[id_key]: min(per, u["max_kw"]) for u in units}

    remaining = total_kw
    for _ in range(len(pool) + 1):
        if not pool or remaining <= 1e-6:
            break
        total_usable = sum(u["usable_kwh"] for u in pool)
        capped_now = []
        for u in pool:
            share = remaining * u["usable_kwh"] / total_usable
            headroom = u["max_kw"] - allocated[u[id_key]]
            if share >= headroom - 1e-6:
                allocated[u[id_key]] = u["max_kw"]
                capped_now.append(u)
        if capped_now:
            remaining = max(0.0, total_kw - sum(allocated.values()))
            for u in capped_now:
                pool.remove(u)
        else:
            # Alle proportionalen Anteile passen — finalisieren
            for u in pool:
                share = remaining * u["usable_kwh"] / total_usable
                allocated[u[id_key]] += share
            break
    return allocated
