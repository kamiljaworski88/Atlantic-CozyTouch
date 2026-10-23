"""Privacy-safe, non-statistical inspection of Atlantic consumption capabilities.

An endpoint's existence does NOT prove that producedQuantity is thermal
energy, nor that a device reports a COP. No raw series or account IDs retained.
"""
from __future__ import annotations

from math import isfinite


def parse_setup_id(payload: object) -> int | None:
    """Take only a positive decimal installation identifier from setupviewv2."""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return None
    raw = payload[0].get("id")
    if type(raw) is int:
        value = raw
    elif isinstance(raw, str) and raw.isascii() and raw.isdecimal() and len(raw) <= 18:
        value = int(raw)
    else:
        return None
    return value if 0 < value < 10**18 else None


def _nonnegative_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value) and value >= 0
    except (OverflowError, ValueError):
        return False


def summarize_consumptions(payload: object) -> dict:
    """Return counts/types only, never raw consumption, dates or identifiers."""
    if not isinstance(payload, list) or len(payload) > 256:
        return {"state": "nieprawidlowa_odpowiedz"}
    kinds: set[int] = set()
    units: set[int] = set()
    rows = 0
    consumed = produced = 0
    for series in payload:
        if not isinstance(series, dict):
            return {"state": "nieprawidlowa_odpowiedz"}
        rows += 1
        kind = series.get("type")
        unit = series.get("unit")
        if type(kind) is int and 0 <= kind <= 10000:
            kinds.add(kind)
        if type(unit) is int and 0 <= unit <= 10000:
            units.add(unit)
        periods = series.get("consumptionPeriods")
        if periods is None:
            continue
        if not isinstance(periods, list) or len(periods) > 3660:
            return {"state": "nieprawidlowa_odpowiedz"}
        for period in periods:
            if not isinstance(period, dict):
                return {"state": "nieprawidlowa_odpowiedz"}
            if _nonnegative_number(period.get("consumedQuantity")):
                consumed += 1
            if _nonnegative_number(period.get("producedQuantity")):
                produced += 1
    return {
        "state": "dostepna" if rows else "brak_danych",
        "serie": rows,
        "typy": sorted(kinds),
        "jednostki": sorted(units),
        "okresy_z_energia_pobrana": consumed,
        "okresy_z_energia_wyprodukowana": produced,
        "mozliwy_pomiar_produkcji": produced > 0,
        "cop_zweryfikowany": False,
    }


def energy_capabilities_summary(devices: list[dict]) -> dict:
    """Decode HOME_EnergyConsumptionCapabilities (164), without raw values."""
    masks: list[int] = []
    reported = 0
    for device in devices:
        if 164 not in device.get("reported_capability_ids", []):
            continue
        reported += 1
        raw = device.get("values", {}).get(164)
        if type(raw) is int or (type(raw) is float and raw.is_integer()):
            value = int(raw)
            if 0 <= value < 2**31:
                masks.append(value)
    if not masks:
        return {"status": "nieczytelny" if reported else "niezgloszony"}
    mask = 0
    for item in masks:
        mask |= item
    return {
        "status": "odczytany",
        "prad_co": bool(mask & 2),
        "prad_cwu": bool(mask & 16),
        "produkcja_ciepla_co": bool(mask & 256),
        "produkcja_ciepla_cwu": bool(mask & 1024),
    }
