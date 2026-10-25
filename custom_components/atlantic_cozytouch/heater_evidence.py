"""Fail-closed-but-meaningful reading of Atlantic auxiliary heater signals.

The public Atlantic ProductModels catalogue lists capabilities 8/9/11 as
power in kW with a declared maximum of 20. An actual Extensa S returned
raw value 3000 for ID8. This exceeds the documented maximum and is likely
encoded in a different scale (perhaps W), so interpreting ANY positive
raw value as unambiguous active heat is unsound.

We deliberately DO NOT convert 3000 to kW, declare the heater OFF, or
treat the three power values as confirmed real-time relay state. A binary
explicitly reporting the DHW heater ON (ID64) remains a hard blocker.
"""
from __future__ import annotations

from math import isfinite

POWER_IDS = (8, 9, 11)
MAX_CATALOGUE_KW = 20.0


def _number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if isfinite(v) and v >= 0 else None


def assess_heaters(devices: list[dict]) -> dict:
    """Anonymized, conservative evidence only: no device IDs or raw amounts.

    In-range positive power may mean active heating and blocks COP (conservative).
    Positive but *out-of-range* raw numbers cannot prove instantaneous power.
    They leave COP explicitly low-confidence, *never* 'heater is off'.
    """
    reported: dict[int, list[float | None]] = {k: [] for k in POWER_IDS}
    binary: list[bool | None] = []
    for device in devices:
        ids = set(device.get("reported_capability_ids", []))
        values = device.get("values", {})
        for cap in POWER_IDS:
            if cap in ids:
                reported[cap].append(_number(values.get(cap)))
        if 64 in ids:
            bit = values.get(64)
            binary.append(bit if type(bit) is bool else None)

    power_labels: dict[str, str] = {}
    in_range_active: list[int] = []
    uncertain: list[int] = []
    for cap in POWER_IDS:
        entries = reported[cap]
        if not entries:
            power_labels[str(cap)] = "niedostepny"
        elif any(v is None for v in entries):
            power_labels[str(cap)] = "nieprawidlowy_odczyt"
            uncertain.append(cap)
        elif any(v > MAX_CATALOGUE_KW for v in entries if v is not None):
            power_labels[str(cap)] = "poza_zakresem_katalogu_skala_nieznana"
            uncertain.append(cap)
        elif any(v > 0 for v in entries if v is not None):
            power_labels[str(cap)] = "dodatnia_moc_w_zakresie_katalogu"
            in_range_active.append(cap)
        else:
            power_labels[str(cap)] = "zero_surowe"

    explicit_on = any(v is True for v in binary)
    binary_label = (
        "wlaczona" if explicit_on else
        "niejednoznaczna" if any(v is None for v in binary) or (True in binary and False in binary) else
        "wylaczona" if binary else "niedostepna"
    )
    if binary_label == "niejednoznaczna":
        uncertain.append(64)
    reason = (
        "grzalka_cwu_aktywna_niepelny_bilans_pradu" if explicit_on else
        "grzalka_wspomagajaca_moc_dodatnia_w_zakresie_katalogu" if in_range_active else
        None
    )
    return {
        "block_reason": reason,
        "uncertain": bool(uncertain),
        "power_id_states": power_labels,
        "dhw_heater_state": binary_label,
        "interpretation": "kW_katalogowe_a_surowa_skala_niezweryfikowana",
        "heater_off_confirmed": False,
    }
