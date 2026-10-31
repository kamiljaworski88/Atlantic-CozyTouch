"""Bounded, read-only hydraulic observation for potential Atlantic defrost events.

No vendor defrost capability is confirmed. Neither this module nor its sensors
can safely operate an actuator; values are hypotheses for manual correlation.
All results are anonymous: no device IDs, names, credentials or raw payloads.
"""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from math import isfinite

MAX_SAMPLES = 240  # About 12 hours at the existing 180 s cloud polling rate.
VISIBLE_SAMPLES = 8
MAX_PAIR_GAP_SECONDS = 12 * 60
NEGATIVE_DELTA_THRESHOLD_C = -0.8
OUTSIDE_LIMIT_C = 7.0


def _number(value: object) -> float | None:
    """Guard absent, invalid, boolean and out-of-range temperature readings."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(val) or not -80 <= val <= 120:
        return None
    return val


def _single_value(devices: list[dict], capability_id: int) -> float | str | None:
    """Return one unambiguous value from the existing normalized snapshot."""
    values = [d.get("values", {}).get(capability_id)
              for d in devices if capability_id in d.get("values", {})]
    return values[0] if len(values) == 1 else None


class DefrostApiObserver:
    """Small local telemetry buffer; never reports a *confirmed* defrost."""

    def __init__(self) -> None:
        self.samples: deque[dict] = deque(maxlen=MAX_SAMPLES)
        self.total_observations = 0
        self.valid_pairs = 0
        self.hypotheses = 0
        self.status = "oczekiwanie_na_odczyt"
        self.latest: dict = {}
        self.last_candidate_utc: str | None = None

    def ingest(self, devices: list[dict], observed_at: datetime) -> None:
        if observed_at.tzinfo is None:
            raise ValueError("Observation timestamp must contain a timezone")
        stamp = observed_at.astimezone(UTC)
        stamp_s = stamp.isoformat(timespec="seconds")
        self.total_observations += 1

        # Pair must come from exactly one physical/logical component. Never
        # combine interface (109) with generator (116) by coincidental order.
        pairs = [
            d for d in devices
            if 109 in d.get("values", {}) and 116 in d.get("values", {})
        ]
        status = "obserwacja"
        supply = ret = delta = None
        if len(pairs) != 1:
            status = "brak_jednoznacznej_pary_temperatur"
        else:
            supply = _number(pairs[0]["values"].get(109))
            ret = _number(pairs[0]["values"].get(116))
            if supply is None or ret is None:
                status = "brak_waznych_temperatur"
            else:
                delta = round(supply - ret, 2)
                self.valid_pairs += 1

        outdoor = _number(_single_value(devices, 119))
        mode = _single_value(devices, 91)
        service = _single_value(devices, 181)
        if not isinstance(mode, str):
            mode = None
        if not isinstance(service, str):
            service = None

        sample = {
            "czas_odbioru_ha_utc": stamp_s,
            "zasilanie_c": supply,
            "powrot_c": ret,
            "delta_t_c": delta,
            "zewnetrzna_c": outdoor,
            "obieg": mode,
            "tryb": service,
            "zrodlo": "atlantic_cloud_180s",
        }

        # 'modificationDate' signals last VALUE change, NOT a physical sensor
        # sampling timestamp. Show ages only as optional diagnostic hints.
        changes = pairs[0].get("updated_at", {}) if len(pairs) == 1 else {}
        for cap, field in ((109, "ostatnia_zmiana_zasilania_s"),
                           (116, "ostatnia_zmiana_powrotu_s")):
            raw = changes.get(cap)
            if type(raw) is int and raw > 0:
                sample[field] = max(0, int(stamp.timestamp()) - raw)

        # A negative water delta alone is NOT defrost. Require two consecutive
        # observations, CO context, and outdoor conditions before labelling a
        # low-confidence *candidate*. No electrical control from this signal.
        prev = self.samples[-1] if self.samples else None
        candidate = (
            delta is not None
            and delta <= NEGATIVE_DELTA_THRESHOLD_C
            and outdoor is not None
            and outdoor <= OUTSIDE_LIMIT_C
            and mode == "CO"
            and prev is not None
            and prev.get("delta_t_c") is not None
            and prev["delta_t_c"] <= NEGATIVE_DELTA_THRESHOLD_C
            and prev.get("obieg") == "CO"
            and 0 < (stamp - datetime.fromisoformat(
                prev["czas_odbioru_ha_utc"])).total_seconds()
            <= MAX_PAIR_GAP_SECONDS
        )
        if candidate:
            status = "hipoteza_odszraniania_niepotwierdzona"
            self.hypotheses += 1
            self.last_candidate_utc = stamp_s
        sample["hipoteza"] = candidate
        sample["defrost_potwierdzony"] = False
        self.status = status
        self.latest = sample
        self.samples.append(sample)

    @property
    def delta_t(self) -> float | None:
        return self.latest.get("delta_t_c")

    def report(self) -> dict:
        return {
            "status": self.status,
            "tryb": "dry_run_tylko_odczyt",
            "defrost_potwierdzony": False,
            "sygnal_do_sterowania": False,
            "ma_bezposredni_sygnal_defrost": False,
            "liczba_odczytow": self.total_observations,
            "liczba_poprawnych_par": self.valid_pairs,
            "liczba_hipotez": self.hypotheses,
            "ostatnia_hipoteza_utc": self.last_candidate_utc,
            "ostatnia_probka": dict(self.latest),
            "ostatnie_probki": [dict(s) for s in list(self.samples)[-VISIBLE_SAMPLES:]],
            "uwaga": (
                "Hipoteza nie jest stanem pompy; modificationDate oznacza "
                "zmiane wartosci, a nie chwile pomiaru. Nie sterowac Shelly."
            ),
        }
