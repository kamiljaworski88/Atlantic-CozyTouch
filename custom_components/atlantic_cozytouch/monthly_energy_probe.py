"""Privacy-safe monthly Atlantic energy API shape validation.

A numeric `producedQuantity` does NOT establish produced thermal heat; it
might refer to electricity production. No numeric kWh, account/device IDs,
raw fields, money, or timestamps are emitted by this diagnostic parser.
"""
from __future__ import annotations

from math import isfinite


def _valid_number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value) and 0 <= value < 1e9


def _code(value: object) -> int | None:
    return value if type(value) is int and 0 <= value <= 10000 else None


def monthly_energy_shape(payload: object) -> dict:
    """Return only bounded, non-identifying source metadata.

    Returned `producedQuantity` counts are generic production counts,
    never inferred to mean thermal production or verified COP.
    """
    if not isinstance(payload, list) or len(payload) > 128:
        return {"state": "nieprawidlowa_odpowiedz"}
    if not payload:
        return {"state": "brak_serii"}
    summaries: list[dict] = []
    total_prod, positive_prod, electric_rows = 0, 0, 0
    for item in payload:
        if not isinstance(item, dict):
            return {"state": "nieprawidlowa_odpowiedz"}
        periods = item.get("consumptionPeriods")
        if not isinstance(periods, list) or len(periods) > 240:
            return {"state": "nieprawidlowa_odpowiedz"}
        n_consumed = n_produced = n_positive = 0
        for period in periods:
            if not isinstance(period, dict):
                return {"state": "nieprawidlowa_odpowiedz"}
            if _valid_number(period.get("consumedQuantity")):
                n_consumed += 1
            if _valid_number(period.get("producedQuantity")):
                n_produced += 1
                if period["producedQuantity"] > 0:
                    n_positive += 1
        total_prod += n_produced
        positive_prod += n_positive
        type_code = _code(item.get("type"))
        unit_code = _code(item.get("unit"))
        if type_code == 1 and unit_code == 1:
            electric_rows += 1
        if len(summaries) < 12:
            summaries.append({
                "typ": type_code,
                "jednostka": unit_code,
                "kategoria": _code(item.get("category")),
                "liczba_okresow": len(periods),
                "okresy_z_pobrana": n_consumed,
                "okresy_z_produkcja": n_produced,
                "okresy_z_dodatnia_produkcja": n_positive,
            })
    return {
        "state": "dostepna",
        "liczba_serii": len(payload),
        "serie_pominiete": max(0, len(payload) - 12),
        "serie": summaries,
        "serie_elektryczne_wg_kodow": electric_rows,
        "okresy_z_liczbowa_produkcja": total_prod,
        "okresy_z_dodatnia_produkcja": positive_prod,
        "energia_cieplna_zweryfikowana": False,
        "cop_miesieczny_zweryfikowany": False,
        "uwaga": "Pole producedQuantity nie jest dowodem energii cieplnej",
    }
