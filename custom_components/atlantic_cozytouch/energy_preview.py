"""Conservative energy preview and COP-readiness rules for Atlantic CozyTouch.

Neither a capability mask nor a guessed Wh scale proves measured heat output.
Preview values are diagnostic ONLY: never HA Energy statistics or a cost input.
"""
from __future__ import annotations

from math import isfinite

ENERGY_CANDIDATES = {
    57: ("CO", 2),
    59: ("CWU", 16),
}

def candidate_kwh(device: dict, cap_id: int) -> float | None:
    """Tentatively convert raw Wh -> kWh, only for properly reported readings.

    Even valid results are NOT confirmed energy readings. No synthetic zero.
    """
    if cap_id not in ENERGY_CANDIDATES:
        return None
    if cap_id not in device.get("reported_capability_ids", []):
        return None
    value = device.get("values", {}).get(cap_id)
    if type(value) not in (int, float):
        return None
    try:
        if not isfinite(value) or value < 0 or value >= 10**12:
            return None
    except (OverflowError, ValueError):
        return None
    return round(value / 1000.0, 3)


def candidate_summary(device: dict, cap_id: int) -> dict:
    """Only non-sensitive flags and an explicit verification disclaimer."""
    role, flag = ENERGY_CANDIDATES[cap_id]
    mask = device.get("values", {}).get(164)
    supported = (
        bool(int(mask) & flag)
        if type(mask) in (int, float) and isfinite(mask)
        and float(mask).is_integer() and 0 <= mask < 2**31
        else None
    )
    return {
        "hipoteza_obieg": role,
        "zrodlo_capability_id": cap_id,
        "hipoteza_jednostki_surowej": "Wh",
        "jednostka_prezentacji": "kWh",
        "pomiar_elektryczny_deklarowany_przez_id164": supported,
        "przypisanie_i_skala_zweryfikowane": False,
        "okres_licznika_zweryfikowany": False,
        "zastosowanie": "diagnostyka_bez_statystyk",
    }


def cop_readiness(consumption: dict | None) -> str:
    """Do not present a made-up COP if thermal energy is absent or unverified."""
    if not isinstance(consumption, dict):
        return "brak_danych_historii"
    state = consumption.get("state")
    if state != "dostepna":
        return "historia_niedostepna" if state not in (None, "nie_sprawdzono") else "nie_sprawdzono"
    if consumption.get("okresy_z_dodatnia_produkcja", 0) > 0:
        return "produkcja_do_weryfikacji"
    if consumption.get("okresy_z_energia_wyprodukowana", 0) > 0:
        return "produkcja_zero_lub_brak_danych"
    return "brak_danych_energii_cieplnej"


def cop_formula(thermal_kwh: object, electrical_kwh: object) -> float | None:
    """Pure validation formula. Not exposed as entity without trusted measurements.

    For the *same* device and exact interval only, with externally validated
    units and series mapping, Q_out / E_in yields a period COP.
    """
    if type(thermal_kwh) not in (int, float) or type(electrical_kwh) not in (int, float):
        return None
    if not (isfinite(thermal_kwh) and isfinite(electrical_kwh)):
        return None
    if thermal_kwh < 0 or electrical_kwh <= 0:
        return None
    return round(thermal_kwh / electrical_kwh, 3)
