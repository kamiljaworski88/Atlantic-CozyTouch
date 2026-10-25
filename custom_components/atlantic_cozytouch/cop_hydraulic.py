"""Conservative experimental COP from time-aligned Magellan measurements.

Not a manufacturer-certified COP or a thermal energy meter. Only use
measurements from ONE identified logical device; topology across Atlantic
devices has not been verified on the target Extensa. No commands or statistics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

HEAT_FACTOR = 4.186 / 60.0  # Water: kW per (litre/minute * kelvin).
MAX_SENSOR_AGE_S = 900
MAX_SNAPSHOT_SKEW_S = 180
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


def _timestamp(device: dict, capability: int, now: datetime) -> int | None:
    """Read the producer's timestamp, never substitute local poll time."""
    timestamp = device.get("updated_at", {}).get(capability)
    if type(timestamp) is not int:
        return None
    age = now.timestamp() - timestamp
    return timestamp if -60 <= age <= MAX_SENSOR_AGE_S else None


def _with_ids(devices: list[dict], *ids: int) -> list[dict]:
    """Identify one device without merging physical zones or logical hosts."""
    required = set(ids)
    return [
        d for d in devices
        if required.issubset(d.get("reported_capability_ids", []))
    ]


class HydraulicCopEstimator:
    """Reset on every discontinuity; unknown is preferable to fictitious COP."""

    def __init__(self) -> None:
        # device, circuit, raw Wh, vendor timestamp of Wh, thermal kW
        self._baseline: tuple[str, str, float, int, float] | None = None
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

        # The OEM splits a setup into logical devices. A unique pair of
        # different devices does NOT prove they represent one hydraulic loop.
        # A future release may provide explicit verified topology metadata.
        if interface["id"] != generator["id"]:
            self._baseline = None
            self.metrics["status"] = "niepotwierdzone_powiazanie_obiegu"
            return

        circuit = interface.get("values", {}).get(91)
        self.metrics["circuit"] = circuit if circuit in ("CO", "CWU") else None
        if circuit not in ("CO", "CWU"):
            self._baseline = None
            self.metrics["status"] = "nieznany_obieg"
            return

        cap = 57 if circuit == "CO" else 59
        hydraulic_ids = (91, 112, 109, 116)
        hydraulic_times = [_timestamp(interface, c, now) for c in hydraulic_ids]
        if any(ts is None for ts in hydraulic_times):
            self._baseline = None
            self.metrics["status"] = "nieaktualne_pomiary_hydrauliczne"
            return

        electric_ts = _timestamp(interface, cap, now)
        if electric_ts is None:
            self._baseline = None
            self.metrics["status"] = "odczyt_licznika_niespojny"
            return

        # Even fresh measurements can describe different instants.
        timestamps = [*hydraulic_times, electric_ts]
        if max(timestamps) - min(timestamps) > MAX_SNAPSHOT_SKEW_S:
            self._baseline = None
            self.metrics["status"] = "niespojne_czasy_probek"
            return

        values = interface.get("values", {})
        flow = _number(values.get(112))
        supply = _number(values.get(109))
        ret = _number(values.get(116))
        if flow is None or supply is None or ret is None:
            self._baseline = None
            self.metrics["status"] = "brak_liczbowych_pomiarow"
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

        raw = _number(values.get(cap))
        if raw is None or not 0 <= raw < 1e12:
            self._baseline = None
            self.metrics["status"] = "brak_licznika_elektrycznego"
            return

        key = str(interface["id"])
        baseline = self._baseline
        if baseline is None or (baseline[0], baseline[1]) != (key, circuit):
            self._baseline = (key, circuit, raw, electric_ts, thermal_kw)
            self.metrics["status"] = "zbieranie_pierwszej_probki"
            return

        previous_energy, previous_ts, previous_thermal_kw = baseline[2:]
        elapsed = electric_ts - previous_ts
        delta_wh = raw - previous_energy

        if elapsed < 0 or elapsed > MAX_INTERVAL_S or delta_wh < 0:
            self._baseline = (key, circuit, raw, electric_ts, thermal_kw)
            self.metrics["status"] = "przerwa_lub_reset_licznika"
            return
        if delta_wh == 0:
            # Keep the original baseline while the discrete energy meter
            # hasn't advanced; a repeated cloud snapshot is not a new sample.
            self.metrics["status"] = "oczekiwanie_na_przyrost_energii"
            return
        if elapsed < MIN_INTERVAL_S:
            self._baseline = None
            self.metrics["status"] = "odczyt_licznika_niespojny"
            return

        self._baseline = (key, circuit, raw, electric_ts, thermal_kw)

        # Wh scale for ID 57/59 is still a hypothesis on this model.
        electrical_kw = delta_wh * 3.6 / elapsed
        if not 0.1 < electrical_kw < 15:
            self.metrics["status"] = "moc_elektryczna_poza_zakresem"
            return
        self.metrics["electrical_kw"] = round(electrical_kw, 3)

        # Trapezoidal mean is less misleading than comparing a single
        # end-of-interval thermal snapshot to interval electric energy.
        mean_thermal_kw = (previous_thermal_kw + thermal_kw) / 2
        cop = mean_thermal_kw / electrical_kw
        if not 0.5 <= cop <= 10:
            self.metrics["status"] = "cop_poza_zakresem"
            return
        self.metrics["cop"] = round(cop, 2)
        self.metrics["status"] = "szacunek_diagnostyczny"
