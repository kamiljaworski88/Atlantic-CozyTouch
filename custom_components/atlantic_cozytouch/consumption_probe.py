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


def production_heat_feature_flags(devices: list[dict]) -> dict:
    """Read two *hypothesized* thermal-production support flags from ID164.

    The independent CozyTouch interoperability table maps bit 256 to heating
    production and bit 1024 to DHW production. Atlantic's publicly published
    v1.9 catalogue omits these names. Flags are NOT numeric heat meters.

    Require one unambiguous heat pump with both active-circuit (91) and
    flow (112) capabilities. Never OR different devices' feature masks.
    """
    pumps = [
        d for d in devices
        if {91, 112}.issubset(set(d.get("reported_capability_ids", [])))
    ]
    base = {
        "produkcja_ciepla_co_bit_256": None,
        "produkcja_ciepla_cwu_bit_1024": None,
        "prad_co_bit_2": None,
        "prad_cwu_bit_16": None,
        "zrodlo_mapowania": "niezalezne_mapowanie_cozytouch_nie_katalog_oem",
        "licznik_energii_cieplnej_kwh": False,
        "cop_wyliczony_z_flag": False,
    }
    if len(pumps) != 1:
        return {"status": "brak_jednoznacznej_pompy", **base}
    device = pumps[0]
    if 164 not in device.get("reported_capability_ids", []):
        return {"status": "brak_id_164", **base}
    raw = device.get("values", {}).get(164)
    if (
        type(raw) not in (int, float)
        or not isfinite(raw)
        or not 0 <= raw < 2**31
        or not float(raw).is_integer()
    ):
        return {"status": "bledna_maska_id_164", **base}
    mask = int(raw)
    return {
        "status": (
            "hipoteza_co_i_cwu" if mask & 256 and mask & 1024
            else "hipoteza_co" if mask & 256
            else "hipoteza_cwu" if mask & 1024
            else "brak_flag_produkcji"
        ),
        **{
            **base,
            "produkcja_ciepla_co_bit_256": bool(mask & 256),
            "produkcja_ciepla_cwu_bit_1024": bool(mask & 1024),
            "prad_co_bit_2": bool(mask & 2),
            "prad_cwu_bit_16": bool(mask & 16),
        },
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
    # Official HOME_EnergyConsumptionCapabilities enum documents ONLY bits
    # 1, 2, 4, 8, 16, 32, 64 (gas/electric/fuel *consumption*).
    # Bits 256/1024 appear on this model but do not have an evidenced meaning;
    # they MUST NOT be misrepresented as produced thermal energy.
    return {
        "status": "odczytany",
        "prad_co": bool(mask & 2),
        "prad_cwu": bool(mask & 16),
        "produkcja_ciepla_co": None,
        "produkcja_ciepla_cwu": None,
        "niezdefiniowane_bity": mask & ~127,
        "produkcja_ciepla_wg_katalogu": "brak_potwierdzonej_flagi",
    }
