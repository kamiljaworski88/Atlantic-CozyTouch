"""Pure read-only compressor analytics; no HA or cloud dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True, slots=True)
class DerivedMetric:
    label: str
    required_capabilities: frozenset[int]
    unit: str | None = None
    category: str | None = None
    cumulative: bool = False


COMPRESSOR_DERIVED_SPECS: dict[str, DerivedMetric] = {
    "runtime_hours": DerivedMetric(
        "Czas pracy sprężarki — godziny", frozenset({27}),
        unit="h", category="duration", cumulative=True,
    ),
    "average_runtime_min_per_start": DerivedMetric(
        "Średni czas pracy sprężarki na start", frozenset({24, 27}),
        unit="min", category="duration",
    ),
    "starts_delta_last_poll": DerivedMetric(
        "Przyrost uruchomień sprężarki od ostatniego odczytu", frozenset({24}),
    ),
    "runtime_delta_seconds_last_poll": DerivedMetric(
        "Przyrost czasu pracy sprężarki od ostatniego odczytu",
        frozenset({27}), unit="s", category="duration",
    ),
}


def _count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(value) or value < 0 or not float(value).is_integer():
        return None
    return int(value)


def _seconds(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(value) or value < 0:
        return None
    return float(value)


class CompressorMonitor:
    """Per-device in-memory deltas with unknown first sample, gaps or resets."""

    def __init__(self) -> None:
        self._previous: dict[str, tuple[datetime, int | None, float | None]] = {}
        self.metrics: dict[str, dict[str, float | int | None]] = {}

    def invalidate(self) -> None:
        """Invalidate interval comparisons after a failed Atlantic poll.

        The cumulative totals will be read again on the next successful poll.
        Do not infer a continuous cycle across a failed API request.
        """
        self._previous.clear()
        for metrics in self.metrics.values():
            metrics["starts_delta_last_poll"] = None
            metrics["runtime_delta_seconds_last_poll"] = None

    def ingest(self, devices: list[dict], observed_at: datetime) -> None:
        if observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")

        current: dict[str, dict[str, float | int | None]] = {}
        for device in devices:
            values = device.get("values", {})
            if not any(k in values for k in (24, 27, 51, 72)):
                continue

            starts = _count(values.get(24))
            runtime = _seconds(values.get(27))
            metric: dict[str, float | int | None] = {
                "runtime_hours": round(runtime / 3600, 3) if runtime is not None else None,
                "average_runtime_min_per_start": (
                    round(runtime / starts / 60, 2)
                    if runtime is not None and starts is not None and starts > 0
                    else None
                ),
                "starts_delta_last_poll": None,
                "runtime_delta_seconds_last_poll": None,
            }

            previous = self._previous.get(device["id"])
            if previous is not None:
                prev_time, prev_starts, prev_runtime = previous
                elapsed = (observed_at - prev_time).total_seconds()
                if 0 < elapsed <= 900:
                    if starts is not None and prev_starts is not None and starts >= prev_starts:
                        metric["starts_delta_last_poll"] = starts - prev_starts
                    if runtime is not None and prev_runtime is not None:
                        increment = runtime - prev_runtime
                        if 0 <= increment <= elapsed + 60:
                            metric["runtime_delta_seconds_last_poll"] = round(increment, 1)

            self._previous[device["id"]] = (observed_at, starts, runtime)
            current[device["id"]] = metric

        self.metrics = current
