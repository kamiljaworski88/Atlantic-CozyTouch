"""Pure, bounded daily electric-energy parser for Atlantic Magellan history.

Only category 1 (CO) and 2 (CWU), with measured type=1 and unit=1 (kWh),
are eligible. The mapping is corroborated on comparable Magellan heat-pump
hardware and still requires comparison with this pump's display.

Never export device identifiers, costs, tariffs or raw responses.
"""
from __future__ import annotations

from math import fsum, isfinite

from .consumption_probe import _utc_day

CATEGORY_CO = 1
CATEGORY_CWU = 2
CATEGORIES = (CATEGORY_CO, CATEGORY_CWU)
MAX_HISTORY_DAYS = 40
MAX_DAY_KWH = 1_000_000.0
ALLOWED_MODES = (0, 1, 2)


def extract_electricity_days(payload: object) -> dict[int, dict[str, float]]:
    """Return safe UTC daily kWh, or omit uncertain/ambiguous readings.

    When multiple tariff periods occur for one day, sum distinct modes.
    Duplicate category series or repeated (day, mode) within a series are
    ambiguous: omit that category/day instead of double counting.
    Missing or malformed quantity invalidates its day, never treats it as 0.
    """
    if not isinstance(payload, list) or len(payload) > 256:
        return {}

    output: dict[int, dict[str, float]] = {}
    seen_categories: set[int] = set()
    ambiguous_categories: set[int] = set()
    for series in payload:
        if not isinstance(series, dict):
            return {}
        category = series.get("category")
        if type(category) is not int or category not in CATEGORIES:
            continue
        if series.get("type") != 1 or series.get("unit") != 1:
            # A reported category with unexpected type/unit cannot be
            # interpreted as electricity kWh. Fail closed for that category.
            ambiguous_categories.add(category)
            continue
        if category in seen_categories:
            ambiguous_categories.add(category)
            continue
        seen_categories.add(category)

        periods = series.get("consumptionPeriods")
        if not isinstance(periods, list) or len(periods) > 3660:
            ambiguous_categories.add(category)
            continue

        day_modes: dict[str, dict[int, float]] = {}
        invalid_days: set[str] = set()
        for period in periods:
            if not isinstance(period, dict):
                ambiguous_categories.add(category)
                break
            day = _utc_day(period.get("date"))
            if day is None:
                continue
            mode = period.get("mode")
            value = period.get("consumedQuantity")
            if (
                type(mode) is not int
                or mode not in ALLOWED_MODES
                or type(value) not in (float, int)
            ):
                invalid_days.add(day)
                continue
            try:
                valid = isfinite(value) and 0 <= value < MAX_DAY_KWH
            except (OverflowError, ValueError):
                valid = False
            if not valid:
                invalid_days.add(day)
                continue
            bucket = day_modes.setdefault(day, {})
            if mode in bucket:
                invalid_days.add(day)
                continue
            bucket[mode] = float(value)

        days: dict[str, float] = {}
        for day, modes in day_modes.items():
            if day in invalid_days or (0 in modes and len(modes) > 1):
                # Mode 0 means unsplit; mixed mode 0/1/2 is ambiguous.
                continue
            total = fsum(modes.values())
            if 0 <= total < MAX_DAY_KWH:
                days[day] = round(total, 6)
        output[category] = dict(sorted(days.items())[-MAX_HISTORY_DAYS:])

    return {
        category: values for category, values in output.items()
        if category not in ambiguous_categories
    }
