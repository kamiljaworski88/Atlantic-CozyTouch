"""Conservative experimental COP from Magellan snapshots.

This is NOT the certified/instant COP of the heat pump. The only estimate
uses hydraulic flow + supply/return temperatures and change in an electric
energy counter over the SAME short interval. No invented energy production,
no actuator control, and no Home Assistant energy statistics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

HEAT_FACTOR = 4.186 / 60.0  # kW per (litre/minute * kelvin), pure water.
MAX_SENSOR_AGE_S = 900
MAX_INTERVAL_S = 1200
MIN_INTERVAL_S = 120


def _number(value: object) -> float | None:
    if type(value) not in (float, int):
        return None
    try:
        x = float(value)
        return x if isfinite(x) else None
    except (ValueError, OverflowError):
        return None


def _fresh(device: dict, capability: int, now: datetime) -> bool:
    timestamp = device.get("updated_at", {}).get(capability)
    if type(timestamp) is not int:
        return False
    age = now.timestamp() - timestamp
    return -60 <= age <= MAX_SENSOR_AGE_S


def _with_ids(devices: list[dict], *ids: int) -> list[dict]:
    """Only identify a unique reporting device; don't silently mix zones."""
    required = set(ids)
    return [
        d for d in devices if required.issubset(
            d.get("reported_capability_ids", [])
        )
    ]


class HydraulicCopEstimator:
    """Reset on discontinuities. Every output defaults to unknown, never zero."""

    def __init__(self) -> None:
        self._baseline: tuple[str, str, float, datetime] | None = None
        self.metrics: dict[str, object] = {}
        self.invalidate()

    def invalidate(self) -> None:
        self._baseline = None
        self.metrics = {
            "status": "brak_ciaglosci_odczytow", "thermal_kw": None,
            "electrical_kw": None, "cop": None, "circuit": None,
        }

    def ingest(self, devices: list[dict], now: datetime) -> None:
        self.metrics = {
            "status": "brak_danych", "thermal_kw": None,
            "electrical_kw": None, "cop": None, "circuit": None,
        }
        if now.tzinfo is None:
            raise ValueError("Timezone required")
        now = now.astimezone(timezone.utc)
        interfaces = _with_ids(devices, 57, 59, 91, 112)
        generators = _with_ids(devices, 109, 116)
        if len(interfaces) != 1 or len(generators) != 1:
            self._baseline = None
            self.metrics["status"] = "brak_jednoznacznych_zrodel"
            return
        interface, generator = interfaces[0], generators[0]
        circuit = interface.get("values", {}).get(91)
        self.metrics["circuit"] = circuit if circuit in ("CO", "CWU") else None
        if circuit not in ("CO", "CWU"):
            self._baseline = None
            self.metrics["status"] = "nieznany_obieg"
            return
        cap = 57 if circuit == "CO" else 59
        # All three hydraulic values must be independently recent. Using
        # poll time as sensor time would make stale cloud values look fresh.
        if not all(_fresh(d, c, now) for d, c in (
            (interface, 112), (generator, 109), (generator, 116)
        )):
            self._baseline = None
            self.metrics["status"] = "nieaktualne_pomiary_hydrauliczne"
            return
        flow = _number(interface.get("values", {}).get(112))
        supply = _number(generator.get("values", {}).get(109))
        ret = _number(generator.get("values", {}).get(116))
        if flow is None or supply is None or ret is None:
            self._baseline = None
            return
        difference = supply - ret
        if not (2 <= flow <= 80 and 0.3 <= difference <= 25):
            self._baseline = None
            self.metrics["status"] = "niewiarygodny_przeplyw_lub_delta_t"
            return
        thermal_kw = flow * difference * HEAT_FACTOR
        if not 0.1 < thermal_kw < 25:
            self._baseline = None
            self.metrics["status"] = "moc_cieplna_poza_zakresem"
            return
        self.metrics["thermal_kw"] = round(thermal_kw, 3)

        raw = _number(interface.get("values", {}).get(cap))
        if raw is None or not 0 <= raw < 1e12:
            self._baseline = None
            self.metrics["status"] = "brak_licznika_elektrycznego"
            return

        key = str(interface["id"])
        baseline = self._baseline
        if baseline is None or (baseline[0], baseline[1]) != (key, circuit):
            self._baseline = (key, circuit, raw, now)
            self.metrics["status"] = "zbieranie_pierwszej_probki"
            return
        previous_energy, previous_time = baseline[2], baseline[3]
        elapsed = (now - previous_time).total_seconds()
        delta_wh = raw - previous_energy
        if elapsed <= 0 or elapsed > MAX_INTERVAL_S or delta_wh < 0:
            self._baseline = (key, circuit, raw, now)
            self.metrics["status"] = "przerwa_lub_reset_licznika"
            return
        if delta_wh == 0:
            self.metrics["status"] = "oczekiwanie_na_przyrost_energii"
            return  # Keep the first baseline so discrete Wh doesn't spike.
        self._baseline = (key, circuit, raw, now)
        if elapsed < MIN_INTERVAL_S or not _fresh(interface, cap, now):
            self.metrics["status"] = "odczyt_licznika_niespojny"
            return

        # ID 57/59 appear to be Wh on comparable Magellan hardware. Until
        # verified on this model this ratio is explicitly *experimental*.
        electrical_kw = delta_wh * 3.6 / elapsed
        if not 0.1 < electrical_kw < 15:
            self.metrics["status"] = "moc_elektryczna_poza_zakresem"
            return
        self.metrics["electrical_kw"] = round(electrical_kw, 3)
        cop = thermal_kw / electrical_kw
        if not 0.5 <= cop <= 10:
            self.metrics["status"] = "cop_poza_zakresem"
            return
        self.metrics["cop"] = round(cop, 2)
        self.metrics["status"] = "szacunek_diagnostyczny"
