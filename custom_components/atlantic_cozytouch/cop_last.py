"""Validated, anonymous persistence of the *last observed* experimental COP.

Not official COP or a fresh measurement; stored values retain a UTC timestamp.
Separate from cumulative heat/energy sums to preserve existing HA storage.
No device IDs, credentials, raw telemetry or meter readings are persisted.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from math import isfinite

SCHEMA = 1
CIRCUITS = ("CO", "CWU")
SOURCES = ("krotki_przedzial", "pelne_okno_energii")
QUALITIES = ("niska", "umiarkowana")
MIN_COP = 0.5
MAX_COP = 10.0
START = datetime(2020, 1, 1, tzinfo=timezone.utc)


class LastCopMemory:
    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}

    def record(
        self, circuit: str, value: float, at: datetime, quality: str, source: str
    ) -> bool:
        if (
            circuit not in CIRCUITS or type(value) not in (int, float)
            or quality not in QUALITIES or source not in SOURCES
            or not isinstance(at, datetime) or at.tzinfo is None
        ):
            return False
        number = float(value)
        utc = at.astimezone(timezone.utc)
        if (
            not isfinite(number) or not MIN_COP <= number <= MAX_COP
            or not START <= utc <= datetime.now(timezone.utc) + timedelta(minutes=5)
        ):
            return False
        current = self._entries.get(circuit)
        if current and utc <= datetime.fromisoformat(current["at"]):
            return False
        self._entries[circuit] = {
            "value": round(number, 2),
            "at": utc.isoformat(),
            "quality": quality,
            "source": source,
        }
        return True

    def latest(self, circuit: str | None = None) -> dict | None:
        if circuit is not None:
            entry = self._entries.get(circuit)
            return dict(entry, circuit=circuit) if entry else None
        if not self._entries:
            return None
        mode = max(self._entries, key=lambda key: self._entries[key]["at"])
        return self.latest(mode)

    def export_state(self) -> dict:
        return {
            "schema": SCHEMA,
            "last_by_circuit": {
                key: dict(self._entries[key])
                for key in CIRCUITS if key in self._entries
            },
        }

    def restore_state(self, raw: object) -> bool:
        """All-or-nothing recovery; rejects tampered or future-dated records."""
        if not isinstance(raw, dict) or set(raw) != {"schema", "last_by_circuit"}:
            return False
        if type(raw["schema"]) is not int or raw["schema"] != SCHEMA:
            return False
        entries = raw["last_by_circuit"]
        if not isinstance(entries, dict) or not set(entries).issubset(CIRCUITS):
            return False
        recovered = LastCopMemory()
        for circuit, item in entries.items():
            if not isinstance(item, dict) or set(item) != {
                "value", "at", "quality", "source"
            }:
                return False
            stamp = item["at"]
            if not isinstance(stamp, str) or len(stamp) > 40:
                return False
            try:
                date = datetime.fromisoformat(stamp)
            except ValueError:
                return False
            if not recovered.record(
                circuit, item["value"], date, item["quality"], item["source"]
            ):
                return False
        self._entries = recovered._entries
        return True
