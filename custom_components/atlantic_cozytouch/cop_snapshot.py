"""Snapshot-based, explicitly experimental hydraulic COP for Atlantic Magellan.

Source units from Atlantic ProductModels capability catalogue:
  109/116: water temperatures [degC]; 112: circulator flow [L/min]
  57/59: accumulated electricity [kWh] with raw resolution 0.001 kWh
The last raw counter mapping must still be checked against the controller.

IMPORTANT: modificationDate is a last-*change* timestamp, NOT proof that a
sensor was measured again. An authenticated successful API snapshot supplies
an observation timestamp; it does NOT guarantee upstream sensor freshness.
The optional low-confidence fallback uses unchanged old temperatures (up to
12h) only with recent flow, advancing electricity and explicit opt-in.
This estimates heat, NOT official Atlantic output and NOT HA Energy statistics.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from .cop_accumulator import CopEnergyAccumulator
from .heater_evidence import assess_heaters

HEAT_FACTOR = 4.186 / 60.0   # water, kW / (L/min * Kelvin)
WH_PER_RAW = 1.0             # candidate vendor 0.001 kWh per raw increment
MAX_LIVE_AGE_S = 900
MAX_TEMP_LAST_CHANGE_S = 43_200  # 12h *only* behind explicit opt-in
MAX_TEMP_PAIR_SKEW = 600
MIN_INTERVAL_S = 120
MAX_INTERVAL_S = 1200
MIN_HEATING_DT_K = 0.75       # low-trust territory below 1.5K
MAX_HEATING_DT_K = 25
LAST_GOOD_TTL_S = 12 * 3600


def _num(value: object) -> float | None:
    if type(value) not in (float, int):
        return None
    try:
        x = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return x if isfinite(x) else None


def _stamp(device: dict, cap: int) -> int | None:
    value = device.get("updated_at", {}).get(cap)
    return value if type(value) is int and 1577836800 <= value < 4102444799 else None


def _age(device: dict, cap: int, now: datetime) -> int | None:
    last = _stamp(device, cap)
    if last is None:
        return None
    age = round(now.timestamp() - last)
    return age if -60 <= age <= 86_400 else None


def _has(devices: list[dict], *caps: int) -> list[dict]:
    ids = set(caps)
    return [d for d in devices if ids.issubset(set(d.get("reported_capability_ids", [])))]


@dataclass(frozen=True)
class _Sample:
    source_key: str
    circuit: str
    seen: datetime
    electric_raw: float
    electric_stamp: int
    mode_stamp: int | None
    thermal_kw: float
    supply: float
    ret: float
    supply_stamp: int
    return_stamp: int
    flow_stamp: int
    stale_temperature: bool


class HydraulicCopEstimator:
    """Independent-interval COP, zero backfill and no hidden extrapolation.

    Keeps only one in-memory baseline and anonymous energy aggregates in HA
    .storage. Restart/mode change/flow outage never links old to new samples.
    """

    def __init__(self, allow_unique_cross_device: bool = False) -> None:
        if type(allow_unique_cross_device) is not bool:
            raise ValueError("Experimental cross-device COP requires a boolean")
        self.allow_unique_cross_device = allow_unique_cross_device
        self.accumulator = CopEnergyAccumulator()
        self._baseline: _Sample | None = None
        self._last_good: tuple[float, datetime] | None = None
        self.metrics: dict[str, object] = {}
        self.invalidate()

    @property
    def accumulated_intervals(self) -> int:
        return self.accumulator.intervals

    def export_accumulated(self) -> dict:
        return self.accumulator.export_state()

    def restore_accumulated(self, raw: object) -> bool:
        ok = self.accumulator.restore_state(raw)
        self.metrics = self._empty()
        return ok

    def _empty(self, now: datetime | None = None) -> dict[str, object]:
        last: float | None = None
        timestamp: str | None = None
        if self._last_good and now is not None:
            value, at = self._last_good
            age = (now - at).total_seconds()
            if 0 <= age <= LAST_GOOD_TTL_S:
                last, timestamp = value, at.isoformat()
        return {
            "status": "brak_danych",
            "thermal_kw": None, "electrical_kw": None, "cop": None,
            "circuit": None, "topology": "nieustalona",
            "source_ages_seconds": {},
            "last_cop": last, "last_cop_at": timestamp,
            "cop_certified": False,
            "temperature_evidence": "nie_sprawdzono",
            "confidence": "brak",
            "counter_scale": "eksperymentalna_0_001_kWh_na_jednostke",
            "heater_evidence": None,
            "observation_method": "kolejne_udane_snapshoty_ha",
            "accumulated": self.accumulator.snapshot(),
        }

    def invalidate(self) -> None:
        self._baseline = None
        self.metrics = self._empty()
        self.metrics["status"] = "brak_ciaglosci_odczytow"

    def _reject(self, code: str) -> None:
        self._baseline = None
        self.metrics["status"] = code

    def ingest(self, devices: list[dict], now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("A timezone-aware snapshot is required")
        now = now.astimezone(timezone.utc)
        self.metrics = self._empty(now)

        interfaces = _has(devices, 57, 59, 91, 112)
        generators = _has(devices, 109, 116)
        if len(interfaces) != 1 or len(generators) != 1:
            self._reject("brak_jednoznacznych_zrodel")
            return
        interface, generator = interfaces[0], generators[0]
        paired = interface.get("id") == generator.get("id")
        if not paired and not self.allow_unique_cross_device:
            self.metrics["topology"] = "oddzielne_moduly_wymaga_opcji_ha"
            self._reject("niepotwierdzone_powiazanie_obiegu")
            return
        self.metrics["topology"] = (
            "jeden_modul" if paired else "jedyna_para_miedzy_modulami_opt_in"
        )
        circuit = interface.get("values", {}).get(91)
        self.metrics["circuit"] = circuit if circuit in ("CO", "CWU") else None
        if circuit not in ("CO", "CWU"):
            self._reject("nieznany_obieg")
            return
        cap = 57 if circuit == "CO" else 59
        ages = {
            "przeplyw": _age(interface, 112, now),
            "zasilanie": _age(generator, 109, now),
            "powrot": _age(generator, 116, now),
            "licznik_pradu": _age(interface, cap, now),
        }
        self.metrics["source_ages_seconds"] = ages
        if any(v is None for v in ages.values()):
            self._reject("brak_znacznikow_zmiany_wartosci")
            return
        flow_age = ages["przeplyw"]
        electricity_age = ages["licznik_pradu"]
        if flow_age > MAX_LIVE_AGE_S:
            self._reject("nieaktualny_przeplyw")
            return
        if electricity_age > MAX_LIVE_AGE_S:
            self._reject("nieaktualny_licznik_pradu")
            return

        sup_ts, ret_ts = _stamp(generator, 109), _stamp(generator, 116)
        elec_ts, flow_ts = _stamp(interface, cap), _stamp(interface, 112)
        assert None not in (sup_ts, ret_ts, elec_ts, flow_ts)
        old_temp = ages["zasilanie"] > MAX_LIVE_AGE_S or ages["powrot"] > MAX_LIVE_AGE_S
        if old_temp:
            if not self.allow_unique_cross_device:
                self._reject("stare_znaczniki_temperatur_wymagaja_opt_in")
                return
            if (max(ages["zasilanie"], ages["powrot"]) > MAX_TEMP_LAST_CHANGE_S
                    or abs(sup_ts - ret_ts) > MAX_TEMP_PAIR_SKEW):
                self._reject("nieaktualne_pomiary_hydrauliczne")
                return
            self.metrics["temperature_evidence"] = "stale_wartosci_w_chmurze_niska_pewnosc"
            self.metrics["confidence"] = "niska"
        else:
            # With changed temperatures, a large discontinuity in vendor
            # timestamps between flow/thermal/electrical channels is suspicious.
            skew = max(sup_ts, ret_ts, elec_ts, flow_ts) - min(
                sup_ts, ret_ts, elec_ts, flow_ts
            )
            if skew > (600 if not paired else 180):
                self._reject("niespojne_czasy_probek")
                return
            self.metrics["temperature_evidence"] = "zmiana_do_15_minut"
            self.metrics["confidence"] = "umiarkowana"

        # Heater evidence is assessed after basic hydraulic diagnostics so
        # Delta T remains visible even if a *confirmed* heater status blocks.
        # ID8/9/11 raw=3000 exceeds catalogue max=20 kW and is NOT reliable
        # proof of an active heater in this model.
        # An explicit compressor OFF signal overrides hydraulic speculation;
        # unknown compressor states are allowed but reduce confidence.
        compressor = [
            d.get("values", {}).get(51)
            for d in devices if 51 in d.get("reported_capability_ids", [])
        ]
        if True not in compressor and False in compressor:
            self._reject("sprezarka_wylaczona")
            return
        if True not in compressor:
            self.metrics["confidence"] = "niska"

        v, g = interface.get("values", {}), generator.get("values", {})
        flow, supply, ret, raw = (
            _num(v.get(112)), _num(g.get(109)),
            _num(g.get(116)), _num(v.get(cap)),
        )
        if any(x is None for x in (flow, supply, ret, raw)):
            self._reject("brak_liczbowych_pomiarow")
            return
        assert flow is not None and supply is not None and ret is not None and raw is not None
        if not 2 <= flow <= 80 or not 0 <= raw < 1e12:
            self._reject("przeplyw_lub_licznik_poza_zakresem")
            return
        difference = supply - ret
        self.metrics["delta_t_k"] = round(difference, 2)
        if difference < MIN_HEATING_DT_K:
            self._reject("delta_t_za_mala_dla_szacowania_cop")
            return
        if difference > MAX_HEATING_DT_K:
            self._reject("delta_t_niewiarygodna")
            return
        if difference < 1.5:
            self.metrics["confidence"] = "niska"
            self.metrics["temperature_evidence"] += "_mala_delta_t"
        thermal = flow * difference * HEAT_FACTOR
        if not 0.15 < thermal < 25:
            self._reject("moc_cieplna_poza_zakresem")
            return
        self.metrics["thermal_kw"] = round(thermal, 3)
        heater = assess_heaters(devices)
        self.metrics["heater_evidence"] = {
            key: value for key, value in heater.items() if key != "block_reason"
        }
        if heater["block_reason"]:
            self._reject(heater["block_reason"])
            return
        if heater["uncertain"]:
            self.metrics["confidence"] = "niska"
        mode_stamp = _stamp(interface, 91)
        current = _Sample(
            source_key=str(interface["id"]) + ":" + str(generator["id"]),
            circuit=circuit, seen=now,
            electric_raw=raw, electric_stamp=elec_ts,
            mode_stamp=mode_stamp, thermal_kw=thermal, supply=supply, ret=ret,
            supply_stamp=sup_ts, return_stamp=ret_ts, flow_stamp=flow_ts,
            stale_temperature=old_temp,
        )
        prior = self._baseline
        self._baseline = current
        if prior is None or prior.source_key != current.source_key or prior.circuit != circuit:
            self.metrics["status"] = "zbieranie_pierwszej_probki"
            return
        if (prior.mode_stamp is not None and mode_stamp is not None
                and mode_stamp != prior.mode_stamp):
            self.metrics["status"] = "zmiana_trybu_pracy"
            return
        seconds = round((now - prior.seen).total_seconds())
        if not MIN_INTERVAL_S <= seconds <= MAX_INTERVAL_S:
            self.metrics["status"] = "przerwa_lub_reset_probki"
            return
        if elec_ts < prior.electric_stamp or flow_ts < prior.flow_stamp:
            self.metrics["status"] = "cofniecie_znacznikow"
            return
        delta_raw = raw - prior.electric_raw
        if delta_raw < 0:
            self.metrics["status"] = "reset_licznika"
            return
        if delta_raw == 0:
            # Keep the earlier baseline only while the observation gap remains
            # bounded; a delayed next increment may cover several cloud polls.
            self._baseline = prior
            self.metrics["status"] = "oczekiwanie_na_przyrost_energii"
            return
        if elec_ts == prior.electric_stamp:
            self.metrics["status"] = "zmiana_pradu_bez_znacznika"
            return

        # An old *unchanged* pair of temperatures is a weak reconstruction,
        # never a newly measured water reading. Do not bridge a temperature
        # change whose last-change stamp is itself old/contradictory.
        if (prior.supply_stamp != sup_ts or prior.return_stamp != ret_ts):
            if old_temp or prior.stale_temperature:
                self.metrics["status"] = "zmiana_temperatur_w_niepewnym_przedziale"
                return
        if (old_temp and (supply != prior.supply or ret != prior.ret)
                or not old_temp and prior.stale_temperature):
            self.metrics["status"] = "zmiana_jakosci_pomiarow"
            return

        electricity_kwh = delta_raw * WH_PER_RAW / 1000
        if not 0 < electricity_kwh < 5:
            self.metrics["status"] = "przyrost_pradu_poza_zakresem"
            return
        electrical_kw = electricity_kwh * 3600 / seconds
        self.metrics["electrical_kw"] = round(electrical_kw, 3)
        if not 0.1 < electrical_kw < 15:
            self.metrics["status"] = "moc_elektryczna_poza_zakresem"
            return
        thermal_kwh = (prior.thermal_kw + thermal) / 2 * seconds / 3600
        estimated = thermal_kwh / electricity_kwh
        if not 0.5 <= estimated <= 10:
            self.metrics["status"] = "cop_poza_zakresem"
            return
        if not self.accumulator.add(circuit, thermal_kwh, electricity_kwh, seconds):
            self.metrics["status"] = "odrzucony_przedzial_energii"
            return
        self.metrics["accumulated"] = self.accumulator.snapshot()
        result = round(estimated, 2)
        self._last_good = (result, now)
        self.metrics["cop"] = result
        self.metrics["last_cop"] = result
        self.metrics["last_cop_at"] = now.isoformat()
        self.metrics["status"] = (
            "szacunek_niska_pewnosc_stale_temperatury"
            if old_temp else
            "szacunek_niska_pewnosc_mala_delta_t"
            if self.metrics["confidence"] == "niska" else
            "szacunek_eksperymentalny_snapshot"
        )
