"""Locally persisted, experimental COP over *accepted* hydraulic intervals.

Cumulative COP is a ratio of SUMS of energy, never a sum/mean of COPs.
No history backfill, calendar/season claims, HA energy statistics or vendor IDs.
Values reflect only intervals accepted by HydraulicCopEstimator. The electrical
Wh scale and thermal readings remain unverified estimates on this pump.
"""
from __future__ import annotations

from math import isfinite

SCHEMA = 1
CIRCUITS = ("CO", "CWU")
MAX_ENERGY_KWH = 100_000_000.0
MAX_INTERVALS = 50_000_000
MAX_SECONDS = 1_000_000_000
MIN_SECONDS_PER_INTERVAL = 120
MAX_SECONDS_PER_INTERVAL = 1200


def _num(value: object, maximum: float) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError, TypeError):
        return None
    return number if isfinite(number) and 0 <= number <= maximum else None


def _zero() -> dict[str, float | int]:
    return {
        "thermal_kwh": 0.0,
        "electric_kwh": 0.0,
        "intervals": 0,
        "covered_seconds": 0,
    }


class CopEnergyAccumulator:
    """Validated all-time-integration-uptime estimate saved only in HA .storage."""

    def __init__(self) -> None:
        self._buckets = {circuit: _zero() for circuit in CIRCUITS}

    @property
    def intervals(self) -> int:
        return sum(self._buckets[circuit]["intervals"] for circuit in CIRCUITS)

    def add(self, circuit: str, heat_kwh: float, electric_kwh: float,
            seconds: int) -> bool:
        """Accept only an already validated finite interval; no partial writes."""
        if circuit not in CIRCUITS or type(seconds) is not int:
            return False
        heat = _num(heat_kwh, MAX_ENERGY_KWH)
        electric = _num(electric_kwh, MAX_ENERGY_KWH)
        if (
            heat is None or electric is None or heat <= 0 or electric <= 0
            or not MIN_SECONDS_PER_INTERVAL <= seconds <= MAX_SECONDS_PER_INTERVAL
            or not 0.5 <= heat / electric <= 10
        ):
            return False
        current = self._buckets[circuit]
        if (
            current["thermal_kwh"] + heat > MAX_ENERGY_KWH
            or current["electric_kwh"] + electric > MAX_ENERGY_KWH
            or current["intervals"] >= MAX_INTERVALS
            or current["covered_seconds"] + seconds > MAX_SECONDS
        ):
            return False
        current["thermal_kwh"] += heat
        current["electric_kwh"] += electric
        current["intervals"] += 1
        current["covered_seconds"] += seconds
        return True

    @staticmethod
    def _summary(value: dict) -> dict:
        heat, electricity = value["thermal_kwh"], value["electric_kwh"]
        return {
            "cop": round(heat / electricity, 2) if electricity > 0 else None,
            "heat_kwh": round(heat, 3),
            "electric_kwh": round(electricity, 3),
            "intervals": value["intervals"],
            "covered_hours": round(value["covered_seconds"] / 3600, 2),
            "coverage": "tylko_poprawne_przedzialy_nie_calosc_pracy",
            "verified": False,
        }

    def snapshot(self) -> dict[str, dict]:
        """New values only from valid intervals; no guessed calendar coverage."""
        total = _zero()
        result = {}
        for circuit in CIRCUITS:
            bucket = self._buckets[circuit]
            result[circuit] = self._summary(bucket)
            for key in total:
                total[key] += bucket[key]
        result["total"] = self._summary(total)
        return result

    def export_state(self) -> dict:
        """No personal info, device identifiers, tokens, timestamps or settings."""
        return {
            "schema": SCHEMA,
            "buckets": {
                circuit: dict(self._buckets[circuit]) for circuit in CIRCUITS
            },
        }

    def restore_state(self, raw: object) -> bool:
        """Atomic fail-closed recovery of local .storage data."""
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
            return False
        entries = raw.get("buckets")
        if not isinstance(entries, dict) or set(entries) != set(CIRCUITS):
            return False
        validated = {}
        for circuit in CIRCUITS:
            item = entries[circuit]
            if not isinstance(item, dict) or set(item) != set(_zero()):
                return False
            heat = _num(item["thermal_kwh"], MAX_ENERGY_KWH)
            electricity = _num(item["electric_kwh"], MAX_ENERGY_KWH)
            periods = item["intervals"]
            seconds = item["covered_seconds"]
            if (
                heat is None or electricity is None
                or type(periods) is not int or not 0 <= periods <= MAX_INTERVALS
                or type(seconds) is not int or not 0 <= seconds <= MAX_SECONDS
                or (periods == 0 and (heat != 0 or electricity != 0 or seconds != 0))
                or (periods > 0 and (heat <= 0 or electricity <= 0
                                    or not periods * MIN_SECONDS_PER_INTERVAL
                                    <= seconds <= periods * MAX_SECONDS_PER_INTERVAL))
                or (electricity > 0 and not 0.5 <= heat / electricity <= 10)
            ):
                return False
            validated[circuit] = {
                "thermal_kwh": heat, "electric_kwh": electricity,
                "intervals": periods, "covered_seconds": seconds,
            }
        self._buckets = validated
        return True
