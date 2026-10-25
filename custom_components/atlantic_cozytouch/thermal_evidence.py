"""Privacy-preserving evidence inventory for Atlantic thermal COP.

The reported `producedQuantity` can be ELECTRICAL production. Neither
a capability flag nor a positive producedQuantity proves heat in kWh.
This module examines existing anonymized summaries only; no network/HA access.
"""
from __future__ import annotations

# Do not ever return arbitrary strings received from vendor/diagnostic payloads.
ALLOWED_STATES = frozenset({
    "dostepna", "brak_danych", "brak_serii", "nie_sprawdzono",
    "brak_id_instalacji", "brak_id_lub_sesji", "brak_jednoznacznej_pompy",
    "endpoint_niedostepny", "odmowa_dostepu", "brak_endpointu",
    "blad_http", "blad_polaczenia", "limit_zapytan", "brak_autoryzacji",
    "nieprawidlowa_odpowiedz",
})
SUCCESSFUL_STATES = frozenset({"dostepna", "brak_danych", "brak_serii"})
MAX_COUNT = 1_000_000

# Only these fixed diagnostic source locations are permitted in output.
SOURCES = (
    ("instalacja_dzien", "okresy_z_dodatnia_produkcja"),
    ("instalacja_miesiac", "okresy_z_dodatnia_produkcja"),
    ("pompa_dzien", "dodatnia_produkcja_niezweryfikowana"),
    ("pompa_miesiac", "dodatnia_produkcja_niezweryfikowana"),
)


def _data(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _state(value: object) -> str:
    return value if isinstance(value, str) and value in ALLOWED_STATES else "nie_sprawdzono"


def _count(value: object) -> int | None:
    if type(value) is not int or not 0 <= value <= MAX_COUNT:
        return None
    return value


def thermal_evidence(
    setup_daily: object,
    setup_monthly: object,
    device_history: object,
    flags: object,
) -> dict:
    """Produce bounded, non-sensitive COP evidence summary.

    Never retain numeric energy values, IDs, arbitrary codes or timestamps.
    Do not aggregate positive counts across multiple endpoints: the same
    samples could be represented by several independent API routes.
    """
    device = _data(device_history)
    source_values = (
        _data(setup_daily),
        _data(setup_monthly),
        _data(device.get("daily")),
        _data(device.get("monthly")),
    )
    observations = []
    positive_candidate = False
    any_success = False
    incomplete = False
    all_unchecked = True

    for (source_name, count_key), value in zip(SOURCES, source_values):
        state = _state(value.get("state"))
        count = _count(value.get(count_key))
        # Missing count must not silently become a real zero.
        if state in SUCCESSFUL_STATES:
            any_success = True
            if count is None and state == "dostepna":
                incomplete = True
        if state != "nie_sprawdzono":
            all_unchecked = False
        if count is not None and count > 0 and state == "dostepna":
            positive_candidate = True
        observations.append({
            "zrodlo": source_name,
            "status": state,
            "rekordy_z_dodatnia_produkcja_nieokreslona": (
                count if state in SUCCESSFUL_STATES else None
            ),
        })

    monthly = _data(setup_monthly)
    monthly_pairs = _count(
        monthly.get("rekordy_z_para_poboru_i_produkcji_nieokreslonej")
    )
    supports = _data(flags)
    f_co = supports.get("produkcja_ciepla_co_bit_256")
    f_cwu = supports.get("produkcja_ciepla_cwu_bit_1024")
    f_co = f_co if type(f_co) is bool else None
    f_cwu = f_cwu if type(f_cwu) is bool else None

    if positive_candidate:
        status = "kandydat_do_weryfikacji"
        next_step = "sprawdz_typ_jednostke_i_znaczenie_producedQuantity"
    elif incomplete:
        status = "niekompletne_metadane"
        next_step = "sprawdz_strukture_historii"
    elif any_success:
        status = "brak_potwierdzonego_ciepla"
        next_step = "potwierdz_czy_cieplo_jest_udostepniane_przez_api"
    elif all_unchecked:
        status = "oczekiwanie_na_dane"
        next_step = "oczekuj_na_okresowy_odczyt"
    else:
        status = "zrodla_niedostepne"
        next_step = "sprawdz_stan_histori_i_uprawnienia"

    return {
        "status": status,
        "zrodla": observations,
        "miesieczne_pary_pobor_produkcja_nieokreslona": (
            monthly_pairs if _state(monthly.get("state")) == "dostepna" else None
        ),
        "hipoteza_obslugi_produkcji_co": f_co,
        "hipoteza_obslugi_produkcji_cwu": f_cwu,
        "kolejny_krok": next_step,
        "energia_cieplna_potwierdzona": False,
        "cop_okresowy_gotowy": False,
        "zastrzezenie": "producedQuantity_i_flaga_id164_nie_sa_pomiarem_ciepla",
    }
