"""Conservative, explicitly experimental hydraulic COP from Atlantic snapshots.

No certified thermal meter exists in the known cloud data for this pump.
Cross-logical-device matching is OFF by default and needs an HA user opt-in.
Even with opt-in, exactly one interface and one generator must be present.
Never publish this estimate as Home Assistant Energy statistics or official COP.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

HEAT_FACTOR = 4.186 / 60.0  # Approximation for pure water, kW/(l/min*K).
MAX_SENSOR_AGE_S = 900
MAX_SNAPSHOT_SKEW_S = 180
MAX_CROSS_DEVICE_SKEW_S = 600  # Explicit opt-in accepts slower cloud joins.
MAX_INTERVAL_S = 1200
MIN_INTERVAL_S = 120
LAST_GOOD_TTL_S = 12 * 3600


def _number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        result = float(value)
        return result if isfinite(result) else None
    except (ValueError, OverflowError):
        return None


def _timestamp(device: dict, capability: int, now: datetime) -> int | None:
    """Check a measurement's vendor timestamp for realistic recent activity."""
    ts = device.get("updated_at", {}).get(capability)
    if type(ts) is not int:
        return None
    age = now.timestamp() - ts
    return ts if -60 <= age <= MAX_SENSOR_AGE_S else None


def _with_ids(devices: list[dict], *ids: int) -> list[dict]:
    required = set(ids)
    return [dev for dev in devices
            if required.issubset(dev.get("reported_capability_ids", []))]


class HydraulicCopEstimator:
    """Fail closed on ambiguous circuits, stale data and reset energy counters.

    The vendor modificationDate for the active circuit (ID 91) is the LAST
    MODE TRANSITION, not a periodic sampling timestamp. It can remain old
    during a long heating cycle; age-checking it suppresses legitimate COP.
    """

    def __init__(self, allow_unique_cross_device: bool = False) -> None:
        if type(allow_unique_cross_device) is not bool:
            raise ValueError("Cross-device experimental COP must be a boolean")
        self.allow_unique_cross_device = allow_unique_cross_device
        # device, circuit, raw Wh, vendor Wh timestamp, thermal kW, mode timestamp
        self._baseline: tuple[str, str, float, int, float, int | None] | None = None
        self._last_good: tuple[float, datetime] | None = None
        self.metrics: dict[str, object] = {}
        self.invalidate()

    def _empty(self, now: datetime | None = None) -> dict[str, object]:
        last_cop: float | None = None
        last_at: str | None = None
        if self._last_good is not None and now is not None:
            value, when = self._last_good
            age = (now - when).total_seconds()
            if 0 <= age <= LAST_GOOD_TTL_S:
                last_cop = value
                last_at = when.isoformat()
        return {
            "status": "brak_danych",
            "thermal_kw": None, "electrical_kw": None, "cop": None,
            "circuit": None, "topology": "nieustalona",
            "last_cop": last_cop, "last_cop_at": last_at,
            "cop_certified": False,
        }

    def invalidate(self) -> None:
        """Invalidate only the current calculation on a polling failure."""
        self._baseline = None
        self.metrics = self._empty()
        self.metrics["status"] = "brak_ciaglosci_odczytow"

    def ingest(self, devices: list[dict], now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("Timezone required")
        now = now.astimezone(timezone.utc)
        self.metrics = self._empty(now)

        interfaces = _with_ids(devices, 57, 59, 91, 112)
        generators = _with_ids(devices, 109, 116)
        if len(interfaces) != 1 or len(generators) != 1:
            self._baseline = None
            self.metrics["status"] = "brak_jednoznacznych_zrodel"
            return
        interface, generator = interfaces[0], generators[0]
        paired = interface.get("id") == generator.get("id")
        if not paired and not self.allow_unique_cross_device:
            self._baseline = None
            self.metrics["status"] = "niepotwierdzone_powiazanie_obiegu"
            return
        self.metrics["topology"] = (
            "jeden_modul" if paired else "jedyna_para_miedzy_modulami_opt_in"
        )

        circuit = interface.get("values", {}).get(91)
        self.metrics["circuit"] = circuit if circuit in ("CO", "CWU") else None
        if circuit not in ("CO", "CWU"):
            self._baseline = None
            self.metrics["status"] = "nieznany_obieg"
            return
        cap = 57 if circuit == "CO" else 59

        # ID91 modificationDate marks the last mode SWITCH, so do not
        # require it to be younger than 15 min. Compare across baselines
        # to catch a mode transition even if the end state matches.
        mode_ts = interface.get("updated_at", {}).get(91)
        if type(mode_ts) is not int:
            mode_ts = None

        timestamps = [
            _timestamp(interface, 112, now),
            _timestamp(generator, 109, now),
            _timestamp(generator, 116, now),
        ]
        if any(ts is None for ts in timestamps):
            self._baseline = None
            self.metrics["status"] = "nieaktualne_pomiary_hydrauliczne"
            return
        electric_ts = _timestamp(interface, cap, now)
        if electric_ts is None:
            self._baseline = None
            self.metrics["status"] = "odczyt_licznika_niespojny"
            return
        limit = MAX_SNAPSHOT_SKEW_S if paired else MAX_CROSS_DEVICE_SKEW_S
        if max([*timestamps, electric_ts]) - min([*timestamps, electric_ts]) > limit:
            self._baseline = None
            self.metrics["status"] = "niespojne_czasy_probek"
            return

        a = interface.get("values", {})
        b = generator.get("values", {})
        flow = _number(a.get(112))
        supply = _number(b.get(109))
        ret = _number(b.get(116))
        if flow is None or supply is None or ret is None:
            self._baseline = None
            self.metrics["status"] = "brak_liczbowych_pomiarow"
            return
        if not 2 <= flow <= 80:
            self._baseline = None
            self.metrics["status"] = "brak_przeplywu_lub_wartosc_poza_zakresem"
            return
        difference = supply - ret
        # 0.1 K on the screenshot is idle / within typical probe resolution.
        if -0.5 <= difference < 0.5:
            self._baseline = None
            self.metrics["status"] = "brak_aktywnego_grzania"
            return
        if not 1.0 <= difference <= 25:
            self._baseline = None
            self.metrics["status"] = "delta_t_niewiarygodna"
            return
        thermal_kw = flow * difference * HEAT_FACTOR
        if not 0.1 < thermal_kw < 25:
            self._baseline = None
            self.metrics["status"] = "moc_cieplna_poza_zakresem"
            return
        self.metrics["thermal_kw"] = round(thermal_kw, 3)

        raw = _number(a.get(cap))
        if raw is None or not 0 <= raw < 1e12:
            self._baseline = None
            self.metrics["status"] = "brak_licznika_elektrycznego"
            return

        key = str(interface["id"])
        baseline = self._baseline
        if baseline is None or (baseline[0], baseline[1]) != (key, circuit):
            self._baseline = (key, circuit, raw, electric_ts, thermal_kw, mode_ts)
            self.metrics["status"] = "zbieranie_pierwszej_probki"
            return

        previous_energy, previous_ts, previous_thermal_kw, previous_mode_ts = baseline[2:]
        if (previous_mode_ts is not None and mode_ts is not None
                and mode_ts != previous_mode_ts):
            self._baseline = (key, circuit, raw, electric_ts, thermal_kw, mode_ts)
            self.metrics["status"] = "zmiana_trybu_pracy"
            return
        elapsed = electric_ts - previous_ts
        delta_wh = raw - previous_energy
        if elapsed < 0 or elapsed > MAX_INTERVAL_S or delta_wh < 0:
            self._baseline = (key, circuit, raw, electric_ts, thermal_kw, mode_ts)
            self.metrics["status"] = "przerwa_lub_reset_licznika"
            return
        if delta_wh == 0:
            self.metrics["status"] = "oczekiwanie_na_przyrost_energii"
            return
        if elapsed < MIN_INTERVAL_S:
            self._baseline = None
            self.metrics["status"] = "odczyt_licznika_niespojny"
            return

        self._baseline = (key, circuit, raw, electric_ts, thermal_kw, mode_ts)
        # Vendor Wh scale for ID57/59 is still a corroborated hypothesis.
        electrical_kw = delta_wh * 3.6 / elapsed
        if not 0.1 < electrical_kw < 15:
            self.metrics["status"] = "moc_elektryczna_poza_zakresem"
            return
        self.metrics["electrical_kw"] = round(electrical_kw, 3)
        estimated_cop = (previous_thermal_kw + thermal_kw) / (2 * electrical_kw)
        if not 0.5 <= estimated_cop <= 10:
            self.metrics["status"] = "cop_poza_zakresem"
            return

        good = round(estimated_cop, 2)
        self._last_good = (good, now)
        self.metrics["cop"] = good
        self.metrics["last_cop"] = good
        self.metrics["last_cop_at"] = now.isoformat()
        self.metrics["status"] = (
            "szacunek_eksperymentalny_miedzy_modulami"
            if not paired else "szacunek_diagnostyczny"
        )
