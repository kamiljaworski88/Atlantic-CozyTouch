"""Read-only energy-production discovery for Atlantic Magellan history.

This is a CONTROLLED SCHEMA PROBE, not a thermal-energy meter. Numeric
producedQuantity in an Atlantic consumption response could mean electricity
production; no unverified field is promoted to a COP/energy entity.

Only at most 24 anonymous recent entries with presence/positivity flags
and bounded enum codes are shown in HA diagnostics. Numeric private energy
values, device IDs, serials, URLs and exact dates are not exported.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

MAX_SERIES = 128
MAX_PERIODS = 3660
MAX_ROWS = 24
MAX_QUANTITY = 100_000_000.0


def _code(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 10_000 else None


def _num(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        x = float(value)
    except (ValueError, OverflowError, TypeError):
        return None
    return round(x, 3) if isfinite(x) and 0 <= x <= MAX_QUANTITY else None


def _month(value: object) -> str | None:
    if type(value) is not int or not 946684800 <= value <= 4102444799:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m")


def summarize_production_candidates(
    payload: object, reference_month: str | None = None
) -> dict:
    """Look only for candidate heat energy in present/current-previous months.

    An exact one-to-one physical comparison with the controller's CO/CWU heat
    outputs is required before considering any producedQuantity a heat meter.
    This intentionally does not sum across series or mixed modes/tariffs.
    """
    if reference_month is None:
        reference_month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        current = datetime.strptime(reference_month, "%Y-%m")
    except (ValueError, TypeError):
        return {"state": "nieprawidlowy_miesiac"}
    previous = (current.replace(day=1)
                .replace(year=current.year - 1, month=12)
                if current.month == 1
                else current.replace(month=current.month - 1))
    relevant = {current.strftime("%Y-%m"), previous.strftime("%Y-%m")}
    if not isinstance(payload, list) or len(payload) > MAX_SERIES:
        return {"state": "nieprawidlowy_format"}

    inspected = with_production = 0
    candidates = []
    for index, series in enumerate(payload, 1):
        if not isinstance(series, dict):
            return {"state": "nieprawidlowy_format"}
        periods = series.get("consumptionPeriods")
        if not isinstance(periods, list) or len(periods) > MAX_PERIODS:
            return {"state": "nieprawidlowy_format"}
        for period in periods:
            if not isinstance(period, dict):
                return {"state": "nieprawidlowy_format"}
            month = _month(period.get("date"))
            if month not in relevant:
                continue
            inspected += 1
            amount = _num(period.get("producedQuantity"))
            if amount is None or amount <= 0:
                continue
            with_production += 1
            if len(candidates) >= MAX_ROWS:
                continue
            candidates.append({
                "seria_indeks": index,  # stable only within the API response
                "miesiac_utc": month,
                "kategoria_kod": _code(series.get("category")),
                "typ_kod": _code(series.get("type")),
                "jednostka_kod": _code(series.get("unit")),
                "tryb_kod": _code(period.get("mode")),
                "pobor_liczbowy": _num(period.get("consumedQuantity")) is not None,
                "produkcja_dodatnia": True,
            })
    candidates.sort(key=lambda x: (x["miesiac_utc"], x["seria_indeks"]), reverse=True)
    return {
        "state": (
            "kandydat_do_porownania_ze_sterownikiem"
            if with_production else "brak_dodatnich_producedquantity"
        ),
        "sprawdzone_okresy": inspected,
        "dodatnie_producedquantity": with_production,
        "kandydaci": candidates,
        "pominiete_kandydaty": max(0, with_production - len(candidates)),
        "referencyjny_miesiac_utc": current.strftime("%Y-%m"),
        "czy_to_cieplo": "NIEZWERYFIKOWANE",
        "czy_dostepny_cop": False,
        "wazne": (
            "Pole mode moze byc taryfa szczyt/poza_szczytem, nie CO/CWU; "
            "unit/type/category nie potwierdzaja energii cieplnej. "
            "Nie sumuj danych z roznych endpointow ani serii."
        ),
    }
