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


def _safe_code(value: object) -> int | None:
    """Export only bounded numeric codes, not arbitrary vendor text."""
    return value if type(value) is int and 0 <= value <= 10000 else None


def _utc_day(value: object) -> str | None:
    """An API period has a UTC epoch-seconds date; reject other forms."""
    from datetime import datetime, timezone

    if type(value) is not int or not 946684800 <= value <= 4102444799:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat()


def summarize_consumptions(payload: object) -> dict:
    """Summarize each reported series, never exposing raw measurements or IDs.

    This is a shape audit, NOT a CO/CWU mapping, meter, or verified COP.
    Dates are UTC calendar days only; no raw epoch timestamps are returned.
    """
    if not isinstance(payload, list) or len(payload) > 256:
        return {"state": "nieprawidlowa_odpowiedz"}
    kinds: set[int] = set()
    units: set[int] = set()
    consumed = produced = positive_production = 0
    details = []
    for index, series in enumerate(payload, start=1):
        if not isinstance(series, dict):
            return {"state": "nieprawidlowa_odpowiedz"}
        kind = _safe_code(series.get("type"))
        unit = _safe_code(series.get("unit"))
        category = _safe_code(series.get("category"))
        if kind is not None:
            kinds.add(kind)
        if unit is not None:
            units.add(unit)
        periods = series.get("consumptionPeriods")
        if periods is None:
            periods = []
        if not isinstance(periods, list) or len(periods) > 3660:
            return {"state": "nieprawidlowa_odpowiedz"}
        days = set()
        modes: set[int] = set()
        profiles: set[int] = set()
        taken = produced_count = positive_count = missing_production = 0
        invalid_dates = 0
        for period in periods:
            if not isinstance(period, dict):
                return {"state": "nieprawidlowa_odpowiedz"}
            day = _utc_day(period.get("date"))
            if day is not None:
                days.add(day)
            elif "date" in period:
                invalid_dates += 1
            mode = _safe_code(period.get("mode"))
            if mode is not None:
                modes.add(mode)
            profile = _safe_code(period.get("profil"))
            if profile is not None:
                profiles.add(profile)
            if _nonnegative_number(period.get("consumedQuantity")):
                taken += 1
            production = period.get("producedQuantity")
            if _nonnegative_number(production):
                produced_count += 1
                if production > 0:
                    positive_count += 1
            else:
                missing_production += 1
        consumed += taken
        produced += produced_count
        positive_production += positive_count
        if len(details) >= 12:
            continue
        details.append({
            "indeks": index,
            "kategoria_kod": category,
            "typ_kod": kind,
            "jednostka_kod": unit,
            "typ_wg_znanego_przykladu": (
                "energia_elektryczna" if kind == 1 else "niezweryfikowany"
            ),
            "jednostka_wg_znanego_przykladu": (
                "kWh" if kind == 1 and unit == 1 else "niezweryfikowana"
            ),
            "przypisanie_co_cwu": "niepotwierdzone",
            "liczba_rekordow": len(periods),
            "liczba_dni_utc": len(days),
            "data_od_utc": min(days) if days else None,
            "data_do_utc": max(days) if days else None,
            "nieprawidlowe_daty": invalid_dates,
            "tryby_kody": sorted(modes)[:12],
            "tryby_pominiete": max(0, len(modes) - 12),
            "profile_kody": sorted(profiles)[:12],
            "profile_pominiete": max(0, len(profiles) - 12),
            "okresy_z_energia_pobrana": taken,
            "okresy_z_energia_wyprodukowana": produced_count,
            "okresy_z_dodatnia_produkcja": positive_count,
            "okresy_bez_liczbowej_produkcji": missing_production,
        })
    return {
        "state": "dostepna" if payload else "brak_danych",
        "serie": len(payload),
        "typy": sorted(kinds),
        "jednostki": sorted(units),
        "okresy_z_energia_pobrana": consumed,
        "okresy_z_energia_wyprodukowana": produced,
        "mozliwy_pomiar_produkcji": produced > 0,
        "cop_zweryfikowany": False,
        "okresy_z_dodatnia_produkcja": positive_production,
        "serie_szczegoly": details,
        "serie_pominiete_w_szczegolach": max(0, len(payload) - len(details)),
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
    # Vendor enum HomeNRJConsCapabilities defines only bits 1..64:
    # gas heating=1, electricity CO=2, cooling=4, gas DHW=8,
    # electricity CWU=16, fuel heat=32, fuel DHW=64.
    # The 256 and 1024 bits observed on this pump have NO confirmed meaning.
    # They must never be reported as measured/available heat production.
    return {
        "status": "odczytany",
        "prad_co": bool(mask & 2),
        "prad_cwu": bool(mask & 16),
        "produkcja_ciepla_co": None,
        "produkcja_ciepla_cwu": None,
        "niezdefiniowane_bity_id164": mask & ~127,
        "maska_nie_potwierdza_produkcji_ciepla": True,
    }
