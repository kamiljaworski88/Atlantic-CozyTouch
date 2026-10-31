"""COP2 research-only local telemetry and daily hydraulic heat estimate.

Never a vendor heat meter, never HA Energy statistics and never a verified COP.
Uses an independent storage namespace and calculations; existing COP1 is untouched.
No network operations. All stored values are allowlisted numeric observations.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from math import isfinite

RETENTION_DAYS = 14
MAX_SAMPLES = RETENTION_DAYS * 24 * 30  # 10,080; <14d at 3-minute polling
MAX_GAP_S = 480
MAX_HYDRAULIC_CHANGE_AGE_S = 12 * 3600
# Research gate: require >=80% *observed* 24-hour hydraulic coverage.
# The old 95% remains the reference for a near-complete day, NOT a new gate.
# A partial-day Q divided by a full-day E is biased/period-mismatched.
MIN_DAY_COVERAGE = 0.80
NEAR_COMPLETE_DAY_COVERAGE = 0.95
THERMAL_ENERGY_MINIMUM_COVERAGE = 0.94
WATER_KW_FACTOR = 4.186 / 60.0  # approximation for water, NOT glycol
MAX_HEAT_KW = 25.0
MAX_COP2 = 12.0


def _num(value, lo, hi):
    if type(value) not in (int, float):
        return None
    try:
        val = float(value)
    except (ValueError, OverflowError):
        return None
    return val if isfinite(val) and lo <= val <= hi else None


def _timestamp(value):
    return value if type(value) is int and 1577836800 <= value < 4102444800 else None


def _match(devices, required):
    matches = [
        device for device in devices
        if isinstance(device, dict) and required.issubset(
            set(device.get("reported_capability_ids", []))
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _topology_verified(interface, generator):
    """Use only explicit setup hierarchy; never infer a hydraulic relation."""
    interface_id = interface.get("id")
    generator_id = generator.get("id")
    if interface_id == generator_id:
        return True
    interface_master = interface.get("master_id")
    generator_master = generator.get("master_id")
    return bool(
        (interface_master and interface_master == generator_id)
        or (generator_master and generator_master == interface_id)
        or (
            interface_master
            and generator_master
            and interface_master == generator_master
        )
    )


def _capture(devices, now, allow_cross):
    """Match one interface and one generator; never export their identifiers."""
    row = {"t": int(now.timestamp()), "mode": None, "f": None,
           "s": None, "r": None, "eco": None, "ecwu": None,
           "compressor": None, "heater": None, "chg": {},
           "topology_verified": False,
           "valid": False, "reason": "brak_zrodel"}
    interface = _match(devices, {57, 59, 91, 112})
    generator = _match(devices, {109, 116})
    if not interface or not generator:
        return row
    if interface.get("id") != generator.get("id") and not allow_cross:
        row["reason"] = "niepotwierdzone_powiazanie_obiegu"
        return row
    row["topology_verified"] = _topology_verified(interface, generator)
    iv, gv = interface.get("values", {}), generator.get("values", {})
    row["mode"] = iv.get(91) if iv.get(91) in ("CO", "CWU") else None
    row["f"] = _num(iv.get(112), 0, 80)
    row["s"] = _num(gv.get(109), 0, 90)
    row["r"] = _num(gv.get(116), 0, 90)
    row["eco"] = _num(iv.get(57), 0, 1e12)
    row["ecwu"] = _num(iv.get(59), 0, 1e12)
    for d in (interface, generator):
        v = d.get("values", {})
        if row["compressor"] is None and type(v.get(51)) is bool:
            row["compressor"] = v[51]
        if row["heater"] is None and type(v.get(64)) is bool:
            row["heater"] = v[64]
    stamps = ((112, "f", interface), (109, "s", generator),
              (116, "r", generator), (57, "eco", interface),
              (59, "ecwu", interface), (91, "mode", interface))
    for cap, field, d in stamps:
        stamp = _timestamp(d.get("updated_at", {}).get(cap))
        if stamp is not None:
            row["chg"][field] = stamp
    if row["mode"] is None:
        row["reason"] = "nieznany_obieg"
    elif any(row[k] is None for k in ("f", "s", "r")):
        row["reason"] = "brak_hydrauliki"
    elif row["heater"] is True:
        row["reason"] = "grzalka_aktywna"
    elif any(
        field not in row["chg"] or not 0 <= row["t"] - row["chg"][field] <= MAX_HYDRAULIC_CHANGE_AGE_S
        for field in ("f", "s", "r")
    ):
        row["reason"] = "brak_lub_zbyt_stary_znacznik_zmiany"
    elif abs(row["s"] - row["r"]) > 25:
        row["reason"] = "delta_t_poza_zakresem"
    else:
        row["reason"] = "ok_niska_pewnosc"
        row["valid"] = True
    return row


def _power(row):
    flow, supply, ret = row["f"], row["s"], row["r"]
    if flow is None or supply is None or ret is None:
        return None
    result = flow * (supply - ret) * WATER_KW_FACTOR
    if not isfinite(result) or abs(result) > MAX_HEAT_KW:
        return None
    return result


def _segment(a, b):
    """Return (mode, kW average) only for unambiguous consecutive observations.

    Do NOT interpolate across mode changes, heater-on observations or gaps.
    Reported compressor OFF at both endpoints is observed as zero heat; unknown
    compressor is allowed but lowers confidence and must be disclosed.
    """
    dt = b["t"] - a["t"]
    if not 120 <= dt <= MAX_GAP_S:
        return None
    if not a["valid"] or not b["valid"] or a["mode"] != b["mode"]:
        return None
    if a["heater"] is True or b["heater"] is True:
        return None
    if a["compressor"] is False and b["compressor"] is False:
        return a["mode"], 0.0, False
    if a["compressor"] is False or b["compressor"] is False:
        return None  # transition time cannot be located
    p1, p2 = _power(a), _power(b)
    if p1 is None or p2 is None:
        return None
    return a["mode"], (p1 + p2) / 2, (
        a["compressor"] is None or b["compressor"] is None
    )


def _day_energy(samples, day):
    """Signed heat over a complete UTC day; never fill missing intervals."""
    start = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())
    end = start + 86400
    totals = {"CO": 0.0, "CWU": 0.0}
    covered_s, low_trust_s, topology_verified_s, segments = 0, 0, 0, 0
    for a, b in zip(samples, samples[1:]):
        if a["t"] >= end or b["t"] <= start:
            continue
        usable = _segment(a, b)
        if usable is None:
            continue
        begin, finish = max(a["t"], start), min(b["t"], end)
        if finish <= begin:
            continue
        mode, kw, unknown_compressor = usable
        seconds = finish - begin
        totals[mode] += kw * seconds / 3600.0
        covered_s += seconds
        low_trust_s += seconds if unknown_compressor else 0
        if a.get("topology_verified") is True and b.get("topology_verified") is True:
            topology_verified_s += seconds
        segments += 1
    return {
        "covered_s": covered_s,
        "coverage_pct": round(100 * covered_s / 86400, 2),
        "unknown_compressor_pct": round(100 * low_trust_s / max(1, covered_s), 2),
        "topology_verified_pct": round(
            100 * topology_verified_s / max(1, covered_s), 2
        ),
        "segments": segments,
        "thermal_kwh": {key: round(value, 3) for key, value in totals.items()},
    }


def _electric(daily, category, day):
    values = daily.get(category)
    if not isinstance(values, dict):
        return None
    return _num(values.get(day), 0, 1e6)


class Cop2Telemetry:
    """Local bounded recorder. Read-only, without personal/account identifiers."""

    def __init__(self, allow_cross=False):
        self.allow_cross = allow_cross
        self.samples: list[dict] = []
        self.last_reason = "oczekiwanie"
        self.status = "oczekiwanie"
        self.result = {"status": "oczekiwanie", "cop2_co": None,
                       "cop2_cwu": None, "cop2_total": None}

    def restore(self, payload, now=None):
        now = now or datetime.now(UTC)
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            return
        samples = payload.get("samples")
        if not isinstance(samples, list) or len(samples) > MAX_SAMPLES:
            return
        recent = []
        now_s = int(now.timestamp())
        for row in samples:
            if not isinstance(row, dict):
                return
            t = row.get("t")
            if type(t) is not int:
                return  # corrupted storage must not erase previous samples
            if not now_s - RETENTION_DAYS*86400 <= t <= now_s + 60:
                continue
            if type(row.get("valid")) is not bool or row.get("mode") not in ("CO", "CWU", None):
                return
            if type(row.get("reason")) is not str or len(row["reason"]) > 80:
                return
            if any(row.get(k) is not None and _num(row[k], 0, 1e12) is None
                   for k in ("f", "s", "r", "eco", "ecwu")):
                return
            stamps = row.get("chg")
            if not isinstance(stamps, dict) or len(stamps) > 6:
                return
            if any(k not in ("f", "s", "r", "eco", "ecwu", "mode") or _timestamp(v) is None
                   for k, v in stamps.items()):
                return
            if any(row.get(k) is not None and type(row[k]) is not bool
                   for k in ("compressor", "heater")):
                return
            # Canonical, restricted schema; never restore extra/untrusted keys.
            recent.append({k: row.get(k) for k in (
                "t", "mode", "f", "s", "r", "eco", "ecwu",
                "compressor", "heater", "valid", "reason",
                "topology_verified"
            )} | {"chg": dict(stamps)})
            recent[-1]["topology_verified"] = row.get("topology_verified") is True
        recent.sort(key=lambda x: x["t"])
        self.samples = [r for i, r in enumerate(recent)
                        if i == 0 or r["t"] > recent[i-1]["t"]][-MAX_SAMPLES:]

    def export(self):
        return {"schema": 1, "samples": list(self.samples)}

    def ingest(self, devices, now, daily):
        if now.tzinfo is None:
            raise ValueError("COP2 observation time must be timezone-aware")
        row = _capture(devices, now, self.allow_cross)
        now_s = row["t"]
        cutoff = now_s - RETENTION_DAYS * 86400
        self.samples = [r for r in self.samples if cutoff <= r["t"] < now_s]
        self.samples.append(row)
        self.samples = self.samples[-MAX_SAMPLES:]
        self.last_reason = row["reason"]
        self.evaluate(daily, now)
        return True

    def evaluate(self, daily, now):
        # Only the previous COMPLETED UTC calendar day; no live COP2 and no
        # mixing the current day's partially populated electric bucket.
        day = (now.astimezone(UTC).date() - timedelta(days=1)).isoformat()
        calc = _day_energy(self.samples, day)
        co_e, cwu_e = _electric(daily, 1, day), _electric(daily, 2, day)
        # Use unrounded seconds, never the rounded display percentage at 80%.
        ready = (
            calc["covered_s"] >= 86400 * MIN_DAY_COVERAGE
            and calc["segments"] > 0
        )
        partial_day = (
            ready and calc["covered_s"] < 86400 * NEAR_COMPLETE_DAY_COVERAGE
        )
        totals = calc["thermal_kwh"]
        strict_thermal_ready = (
            calc["covered_s"] >= 86400 * THERMAL_ENERGY_MINIMUM_COVERAGE
            and calc["segments"] > 0
            and calc["topology_verified_pct"] == 100.0
        )
        if calc["covered_s"] < 86400 * THERMAL_ENERGY_MINIMUM_COVERAGE:
            thermal_status = "niewystarczajace_pokrycie_94"
        elif calc["topology_verified_pct"] < 100.0:
            thermal_status = "niepotwierdzone_powiazanie_modulow"
        elif totals["CO"] < 0 or totals["CWU"] < 0:
            strict_thermal_ready = False
            thermal_status = "ujemny_bilans_ciepla"
        else:
            thermal_status = "szacunek_hydrauliczny_gotowy_niska_pewnosc"
        ratios = {"CO": None, "CWU": None, "TOTAL": None}
        if ready:
            for mode, energy in (("CO", co_e), ("CWU", cwu_e)):
                heat = totals[mode]
                if energy is not None and energy > 0 and heat >= 0:
                    cop = heat / energy
                    if 0 <= cop <= MAX_COP2:
                        ratios[mode] = round(cop, 3)
            if co_e is not None and cwu_e is not None and co_e + cwu_e > 0:
                heat = totals["CO"] + totals["CWU"]
                if heat >= 0 and 0 <= heat / (co_e + cwu_e) <= MAX_COP2:
                    ratios["TOTAL"] = round(heat / (co_e + cwu_e), 3)
        if not ready:
            status = "niewystarczajace_pokrycie"
        elif co_e is None or cwu_e is None:
            status = "brak_pelnej_energii_elektrycznej"
        elif any(v is None for v in ratios.values()):
            status = "nieprawidlowy_bilans_lub_licznik"
        elif partial_day:
            # The numerator is integrated ONLY over observed segments; the
            # denominator is the ENTIRE daily electricity bucket. This is a
            # research indicator, not like-for-like period COP. Never rescale
            # missing heat data to a full day.
            status = "szacunek_niepelna_doba_niska_pewnosc"
        else:
            status = "szacunek_niska_pewnosc"
        self.status = status
        self.result = {
            "status": status,
            "day_utc": day,
            "method": "COP2_hydrauliczny_dobowy_woda_approx",
            "not_vendor_cop": True,
            "cross_module_verified": False if self.allow_cross else None,
            "last_rejection": self.last_reason,
            "samples": len(self.samples),
            "first_observed_at": (
                datetime.fromtimestamp(self.samples[0]["t"], tz=UTC).isoformat()
                if self.samples else None
            ),
            "last_observed_at": (
                datetime.fromtimestamp(self.samples[-1]["t"], tz=UTC).isoformat()
                if self.samples else None
            ),
            "retention_days": RETENTION_DAYS,
            "coverage_pct": calc["coverage_pct"],
            "minimum_coverage_pct": round(100 * MIN_DAY_COVERAGE),
            "near_complete_coverage_pct": round(100 * NEAR_COMPLETE_DAY_COVERAGE),
            "covered_seconds": calc["covered_s"],
            "missing_seconds": max(0, 86400 - calc["covered_s"]),
            "partial_day": partial_day,
            "partial_period_bias_warning": (
                "Cieplo tylko z obserwowanych odcinkow / prad z calej doby; "
                "nie jest to porownywalny okres COP"
                if partial_day else None
            ),
            "periods_physically_aligned_confirmed": False,
            "thermal_energy_extrapolated": False,
            "segments": calc["segments"],
            "unknown_compressor_pct": calc["unknown_compressor_pct"],
            "topology_verified_pct": calc["topology_verified_pct"],
            "thermal_energy_status": thermal_status,
            "thermal_energy_ready": strict_thermal_ready,
            "thermal_energy_minimum_coverage_pct": round(
                100 * THERMAL_ENERGY_MINIMUM_COVERAGE
            ),
            "estimated_thermal_co_kwh": totals["CO"] if ready else None,
            "estimated_thermal_cwu_kwh": totals["CWU"] if ready else None,
            "publishable_thermal_co_kwh": (
                totals["CO"] if strict_thermal_ready else None
            ),
            "publishable_thermal_cwu_kwh": (
                totals["CWU"] if strict_thermal_ready else None
            ),
            "publishable_thermal_total_kwh": (
                round(totals["CO"] + totals["CWU"], 3)
                if strict_thermal_ready else None
            ),
            "electric_co_kwh": co_e,
            "electric_cwu_kwh": cwu_e,
            "cop2_co": ratios["CO"],
            "cop2_cwu": ratios["CWU"],
            "cop2_total": ratios["TOTAL"],
        }
