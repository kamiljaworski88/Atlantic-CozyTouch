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
from .cop_last import LastCopMemory
from .heater_evidence import assess_heaters
from .cop_window import ObservedElectricWindow

HEAT_FACTOR = 4.186 / 60.0   # water, kW / (L/min * Kelvin)
MAX_LIVE_AGE_S = 900
# A cumulative meter can legitimately keep last-change time through extended
# inactivity. Only the *new*, positive increment must have a recent stamp.
MAX_METER_LAST_CHANGE_S = 366 * 86_400
MAX_HYDRAULIC_LAST_CHANGE_S = 43_200  # 12h *only* behind explicit opt-in
# modificationDate from Magellan is last VALUE change (NOT observation time).
# Do not compare the dates of two stable water sensors as if they were
# clock-synchronized measurements.
MIN_HEATING_DT_K = 0.75       # low-trust territory below 1.5K
MAX_HEATING_DT_K = 25
# Last accepted COP is a *historical* reading; no TTL hides it.
# Its UTC timestamp and age must always accompany it in HA.


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


def _meter_age(device: dict, cap: int, now: datetime) -> int | None:
    """Age of a counter last *value change* (not last poll); can be months."""
    last = _stamp(device, cap)
    if last is None:
        return None
    age = round(now.timestamp() - last)
    return age if -60 <= age <= MAX_METER_LAST_CHANGE_S else None


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
    flow: float
    stale_flow: bool
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
        self.last_cops = LastCopMemory()
        self.window = ObservedElectricWindow()
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

    def export_last_cops(self) -> dict:
        return self.last_cops.export_state()

    def restore_last_cops(self, raw: object) -> bool:
        ok = self.last_cops.restore_state(raw)
        if ok:
            self.metrics = self._empty()
            self.metrics["status"] = "ostatni_zachowany_wynik_historyczny"
        return ok

    def _accepted(self, value: float, at: datetime, circuit: str, quality: str,
                  source: str) -> None:
        # Keep last accepted results by circuit independently from any future
        # failed sample, mode transition or Atlantic API outage.
        self.last_cops.record(circuit, value, at, quality, source)
        self.metrics["cop"] = value
        self.metrics["live_cop"] = value
        self.metrics["last_cop"] = value
        self.metrics["last_cop_at"] = at.isoformat()
        self.metrics["last_cop_circuit"] = circuit
        self.metrics["last_cop_quality"] = quality
        self.metrics["last_cop_source"] = source
        self.metrics["last_cop_co"] = (self.last_cops.latest("CO") or {}).get("value")
        self.metrics["last_cop_cwu"] = (self.last_cops.latest("CWU") or {}).get("value")
        self.metrics["cop_is_historical"] = False
        self.metrics["cop_display_source"] = "ostatni_zaakceptowany_przedzial"
        self.metrics["cop_uses_cumulative_fallback"] = False
        self.metrics["cop_display_circuit"] = circuit


    def _empty(self, now: datetime | None = None) -> dict[str, object]:
        latest = self.last_cops.latest()
        co = self.last_cops.latest("CO")
        cwu = self.last_cops.latest("CWU")
        # Versions <=0.5.18 persisted valid *cumulative* COP, but did not
        # persist the timestamp/value of the last individual accepted sample.
        # A read-only display fallback prevents 'unknown' after an upgrade.
        # NEVER claim that an aggregate ratio is the latest interval or
        # assign an invented timestamp. The source is explicitly identified.
        snapshot = self.accumulator.snapshot()
        rows = snapshot["total"]
        fallback = (
            rows["cop"] if latest is None and rows["intervals"] > 0 else None
        )
        display = latest["value"] if latest else fallback
        has_co = snapshot["CO"]["intervals"] > 0
        has_cwu = snapshot["CWU"]["intervals"] > 0
        fallback_circuit = (
            "CO+CWU" if has_co and has_cwu else
            "CO" if has_co else
            "CWU" if has_cwu else None
        )
        return {
            "status": "brak_danych",
            "thermal_kw": None, "electrical_kw": None,
            "cop": display,
            "live_cop": None,
            "circuit": None, "topology": "nieustalona",
            "source_ages_seconds": {},
            "last_change_skew_temperatures_seconds": None,
            "hydraulic_observation_evidence": "ostatnia_zmiana_nie_data_pomiaru",
            "last_cop": latest["value"] if latest else None,
            "last_cop_at": latest["at"] if latest else None,
            "last_cop_circuit": latest["circuit"] if latest else None,
            "last_cop_quality": latest["quality"] if latest else None,
            "last_cop_source": latest["source"] if latest else None,
            "last_cop_co": co["value"] if co else None,
            "last_cop_cwu": cwu["value"] if cwu else None,
            "cop_is_historical": display is not None,
            "cop_display_source": (
                "ostatni_zaakceptowany_przedzial" if latest else
                "zastepczy_cop_skumulowany_bez_daty" if fallback is not None else
                "brak"
            ),
            "cop_uses_cumulative_fallback": fallback is not None,
            "cop_display_circuit": (
                latest["circuit"] if latest else fallback_circuit
            ),
            "cop_certified": False,
            "temperature_evidence": "nie_sprawdzono",
            "confidence": "brak",
            "counter_scale": "eksperymentalna_0_001_kWh_na_jednostke",
            "heater_evidence": None,
            "observation_method": "kolejne_udane_snapshoty_ha",
            "electric_window_diagnostics": self.window.diagnostics(),
            "accumulated": self.accumulator.snapshot(),
        }

    def invalidate(self) -> None:
        self.window.reset()
        self.metrics = self._empty()
        self.metrics["status"] = "brak_ciaglosci_odczytow"

    def _reject(self, code: str) -> None:
        self.window.reset()
        self.metrics["status"] = code
        self.metrics["electric_window_diagnostics"] = self.window.diagnostics()

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
            "licznik_pradu": _meter_age(interface, cap, now),
        }
        self.metrics["source_ages_seconds"] = ages
        if any(v is None for v in ages.values()):
            self._reject("brak_znacznikow_zmiany_wartosci")
            return
        flow_age = ages["przeplyw"]
        electricity_age = ages["licznik_pradu"]
        # A constant valid flow can keep its last-change timestamp for
        # hours. Sampling the setup again doesn't prove the sensor is fresh,
        # but neither does an unchanged value prove failure. Experimental
        # opt-in, bounded last-change age and cross-snapshot invariants are
        # required to use unchanged old hydraulic values.
        stale_flow = flow_age > MAX_LIVE_AGE_S
        if flow_age > MAX_HYDRAULIC_LAST_CHANGE_S:
            self._reject("nieaktualny_przeplyw")
            return
        if stale_flow and not self.allow_unique_cross_device:
            self._reject("stary_znacznik_przeplywu_wymaga_opt_in")
            return
        # Don't reject the *baseline* because the cumulative meter has not
        # changed for >15 minutes. When there is no increment there is no COP.
        # For any later positive increment require a newly advanced, recent
        # vendor last-change timestamp and unchanged circuit.
        self.metrics["electric_meter_diagnostics"] = {
            "capability_id": cap,
            "last_change_age_seconds": electricity_age,
            "last_change_is_recent": electricity_age <= MAX_LIVE_AGE_S,
            "timestamp_semantics": "ostatnia_zmiana_nie_ostatni_odczyt",
            "counter_increment_seen": False,
        }

        sup_ts, ret_ts = _stamp(generator, 109), _stamp(generator, 116)
        elec_ts, flow_ts = _stamp(interface, cap), _stamp(interface, 112)
        assert None not in (sup_ts, ret_ts, elec_ts, flow_ts)
        self.metrics["last_change_skew_temperatures_seconds"] = abs(sup_ts - ret_ts)
        old_temp = ages["zasilanie"] > MAX_LIVE_AGE_S or ages["powrot"] > MAX_LIVE_AGE_S
        if old_temp:
            if not self.allow_unique_cross_device:
                self._reject("stare_znaczniki_temperatur_wymagaja_opt_in")
                return
            if max(ages["zasilanie"], ages["powrot"]) > MAX_HYDRAULIC_LAST_CHANGE_S:
                self._reject("nieaktualne_pomiary_hydrauliczne")
                return
            # The dates may differ by hours while one value stays exactly
            # constant. The paired values must stay unchanged in every
            # observed hydraulic interval while at least one is old.
            self.metrics["temperature_evidence"] = (
                "stare_znaczniki_wartosci_niska_pewnosc"
            )
            self.metrics["confidence"] = "niska"
        else:
            # With changed temperatures, a large discontinuity in vendor
            # timestamps between flow/thermal/electrical channels is suspicious.
            # A counter that has not changed must not force the *fresh*
            # hydraulic measurements to look time-incompatible. Once the
            # counter increments its vendor timestamp is included again.
            check_stamps = (
                (sup_ts, ret_ts, flow_ts) if electricity_age > MAX_LIVE_AGE_S
                else (sup_ts, ret_ts, elec_ts, flow_ts)
            )
            skew = max(check_stamps) - min(check_stamps)
            if skew > (600 if not paired else 180):
                self._reject("niespojne_czasy_probek")
                return
            self.metrics["temperature_evidence"] = "zmiana_do_15_minut"
            self.metrics["confidence"] = "umiarkowana"

        if stale_flow:
            self.metrics["confidence"] = "niska"
            self.metrics["temperature_evidence"] += "_przeplyw_ze_starym_znacznikiem"

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
            flow=flow, stale_flow=stale_flow, stale_temperature=old_temp,
        )
        # A short 3-6min "instant" ratio from one raw ID57/59 step is NOT
        # temporally aligned with the heat integral; we observed false COP=9.44
        # from 0.491kWh heat / 0.052kWh of late/batched electricity.
        #
        # Only meter-to-meter windows starting and ending at two WITNESSED
        # counter changes can write to the energy accumulator. Every 3min
        # hydraulic segment inside the 12-60min window must be observed.
        # FIRST change anchors; no historical inference/backfill.
        candidate = self.window.ingest(current)
        window_info = self.window.diagnostics()
        self.metrics["electric_window_diagnostics"] = window_info
        meter_info = self.metrics.get("electric_meter_diagnostics")
        if isinstance(meter_info, dict):
            meter_info["counter_increment_seen"] = (
                window_info["przyrost_licznika_w_biezacym_odczycie"]
            )
        if candidate is None:
            self.metrics["status"] = "okno_energii_" + self.window.last_reason
            return

        if not self.accumulator.add(
            circuit, candidate.heat_kwh, candidate.electric_kwh, candidate.seconds,
        ):
            self.metrics["status"] = "okno_energii_odrzucone_przez_akumulator"
            return
        self.metrics["accumulated"] = self.accumulator.snapshot()
        self.metrics["electrical_kw"] = round(
            candidate.electric_kwh * 3600 / candidate.seconds, 3
        )
        estimated = round(candidate.heat_kwh / candidate.electric_kwh, 2)
        self._accepted(estimated, now, circuit, "niska", "pelne_okno_energii")
        self.metrics["confidence"] = "niska"
        self.metrics["status"] = "szacunek_niska_pewnosc_pelne_okno_licznika"
