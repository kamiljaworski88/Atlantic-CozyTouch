"""Read-only, unit-free comparison of Atlantic diagnostic energy counters.

Retain only normalized numeric readings in memory. Values and device identifiers
never appear in downloaded diagnostics; per-device statuses are indexed instead.
No conversion to kWh, COP, costs or HA statistics is performed.
"""

from __future__ import annotations

from datetime import datetime
from math import isfinite

RAW_COUNTER_IDS = (57, 59)
ALL_ENERGY_IDS = (57, 59, 60)
MAX_SAMPLE_GAP_SECONDS = 900


def _valid_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) and 0 <= number < 1_000_000_000_000 else None


class EnergyValidationMonitor:
    """Unit-free per-poll deltas for two samples of the SAME device and ID."""

    def __init__(self) -> None:
        self._previous: dict[tuple[str, int], tuple[datetime, float | None]] = {}
        self.statuses: dict[str, dict[int, dict[str, object]]] = {}

    def invalidate(self) -> None:
        """A failed poll breaks comparison continuity; do not bridge outages."""
        self._previous.clear()
        for by_id in self.statuses.values():
            for item in by_id.values():
                item["delta_raw"] = None
                item["comparison"] = "poll_failed"

    def ingest(self, devices: list[dict], observed_at: datetime) -> None:
        if observed_at.tzinfo is None:
            raise ValueError("A timezone-aware sample timestamp is required")
        statuses: dict[str, dict[int, dict[str, object]]] = {}
        currently_reported: set[tuple[str, int]] = set()
        for device in devices:
            dev_id = device["id"]
            reported = set(device.get("reported_capability_ids", []))
            values = device.get("values", {})
            raw_statuses = device.get("energy_status", {})
            by_id: dict[int, dict[str, object]] = {}
            for cap in ALL_ENERGY_IDS:
                if cap not in reported:
                    continue
                key = (dev_id, cap)
                currently_reported.add(key)
                value = _valid_number(values.get(cap))
                value_status = raw_statuses.get(cap, "valid" if value is not None else "missing")
                if value is None and value_status == "valid":
                    value_status = "out_of_range"
                item: dict[str, object] = {
                    "value_status": value_status,
                    "comparison": "not_applicable" if cap == 60 else "first_sample",
                    "delta_raw": None,
                }
                if cap in RAW_COUNTER_IDS:
                    previous = self._previous.get(key)
                    if value is None:
                        item["comparison"] = "value_unavailable"
                    elif previous is not None:
                        previous_at, previous_value = previous
                        seconds = (observed_at - previous_at).total_seconds()
                        if not 0 < seconds <= MAX_SAMPLE_GAP_SECONDS:
                            item["comparison"] = "gap"
                        elif previous_value is None:
                            item["comparison"] = "first_sample"
                        elif value < previous_value:
                            item["comparison"] = "decreased_or_reset"
                        else:
                            item["delta_raw"] = round(value - previous_value, 3)
                            item["comparison"] = "increased" if value > previous_value else "unchanged"
                    self._previous[key] = (observed_at, value)
                by_id[cap] = item
            if by_id:
                statuses[dev_id] = by_id
        # Do not join old and new snapshots across disappearance of a capability.
        self._previous = {k: v for k, v in self._previous.items() if k in currently_reported}
        self.statuses = statuses

    def redacted_report(self, devices: list[dict]) -> list[dict]:
        """Only statuses and anonymous device order; never values or IDs."""
        result: list[dict] = []
        for index, device in enumerate(devices, 1):
            by_id = self.statuses.get(device["id"], {})
            result.append({
                "index": index,
                "energy_ids": {
                    str(cap): {
                        "value_status": str(by_id[cap]["value_status"]),
                        "comparison": str(by_id[cap]["comparison"]),
                    }
                    for cap in ALL_ENERGY_IDS if cap in by_id
                },
            })
        return result


def freshness_status(last_success: datetime | None, last_poll_ok: bool,
                     observed_at: datetime, poll_seconds: int = 180) -> str:
    """Calculate freshness independently of the availability of the sensors."""
    if last_success is None:
        return "brak_udanego_odczytu"
    if last_success.tzinfo is None or observed_at.tzinfo is None:
        raise ValueError("Expected timezone-aware timestamps")
    age = (observed_at - last_success).total_seconds()
    if not last_poll_ok:
        return "blad_ostatniego_odczytu"
    return "opozniony" if age > poll_seconds * 2.5 else "aktualny"
