"""Bounded evidence collection; never a heat meter or device command."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
import re
from urllib.parse import urlencode

from .const import API_ORIGIN

CORE_IDS = frozenset((8, 9, 11, 24, 27, 51, 57, 58, 59, 60, 64, 72, 91, 109, 112, 116, 164))
CATALOGUE_URL = API_ORIGIN + "/magellan/productmodels/capabilities"
UNITS = frozenset(("kWh", "Wh", "kW", "W", "°C", "l/min", "L/min", "s", "h", "%"))
MAX_BODY_BYTES = 1_000_000
MAX_ERROR_BYTES = 16_384


def error_summary(raw):
    """Classify bounded error text; output only constants, never server strings.

    Mentions are clues, not proof that a particular parameter caused rejection.
    No raw message, URL, numeric code, value or identifier leaves this function.
    """
    text = raw.decode("utf-8", errors="replace").lower()
    parameters = [name for name in ("fromDate", "toDate", "periodicity", "deviceId", "setupId")
                  if re.search(r"(?<![a-z])" + name.lower() + r"(?![a-z])", text)]
    formats = [label for marker, label in (
        ("yyyy-mm-dd", "yyyy-MM-dd"), ("yyyyMMdd".lower(), "yyyyMMdd"),
        ("iso 8601", "ISO8601"), ("iso8601", "ISO8601"),
        ("unix", "unix_mentioned"), ("timestamp", "timestamp_mentioned"),
        ("integer", "integer_mentioned"), ("int64", "int64_mentioned"),
        ("milliseconds", "milliseconds_mentioned"),
    ) if marker in text]
    reasons = [label for marker, label in (
        ("required", "required"), ("missing", "missing"),
        ("invalid", "invalid"), ("format", "format"),
        ("convert", "conversion"), ("parse", "parse"),
        ("range", "range"), ("unsupported", "unsupported"),
    ) if marker in text]
    return {"state": "recognized_clues" if parameters or formats or reasons else "unrecognized_body",
            "parameter_mentions": parameters, "format_mentions": sorted(set(formats)),
            "reason_hints": reasons, "cause_confirmed": False}



def number(value):
    if type(value) not in (str, float, int) or (isinstance(value, str) and len(value) > 40):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) and abs(result) < 1e12 else None


def valid_id(value):
    return (isinstance(value, str) and value.isascii() and value.isdecimal()
            and 1 <= len(value) <= 18 and not value.startswith("0"))


def targets(devices):
    interfaces = [d for d in devices if {91, 112}.issubset(d.get("reported_capability_ids", []))]
    if len(interfaces) != 1 or not valid_id(interfaces[0].get("id")):
        return []
    result = [("interfejs", interfaces[0]["id"])]
    generators = [d for d in devices if {109, 116}.issubset(d.get("reported_capability_ids", []))]
    if len(generators) == 1 and valid_id(generators[0].get("id")):
        if generators[0]["id"] != result[0][1]:
            result.append(("generator", generators[0]["id"]))
    return result


def catalogue_summary(payload):
    if not isinstance(payload, list) or len(payload) > 2048:
        raise ValueError("catalogue shape")
    rows, extra = [], set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("catalogue item")
        cap = item.get("id")
        if type(cap) is not int or not 0 <= cap <= 2147483647:
            continue
        # Classify metadata locally; never export free text from the catalogue.
        parts = [item.get(key) for key in ("name", "description")]
        name = " ".join(part.lower() for part in parts
                        if isinstance(part, str) and len(part) <= 2048)
        thermal = any(x in name for x in ("produc", "deliver", "output")) and any(
            x in name for x in ("heat", "thermal", "calori"))
        defrost = any(x in name for x in ("defrost", "deicing", "degivr", "dégivr"))
        topics = [label for words, label in (
            (("energy", "consum", "energie", "énergie", "kwh"), "energy"),
            (("electric", "elec", "powerinput"), "electricity"),
            (("backup", "auxiliary", "resistance", "appoint"), "auxiliary_heater"),
        ) if any(word in name for word in words)]
        unit = item.get("unit")
        # Unknown capabilities are presence-only; never export their values.
        if (thermal or defrost or topics) and cap not in CORE_IDS and item.get("isSensitiveData") is False and len(extra) < 16:
            extra.add(cap)
        if cap in CORE_IDS or cap in extra:
            if len(rows) >= 64:
                continue
            rows.append({"capability_id": cap,
                         "unit": unit if isinstance(unit, str) and unit in UNITS else None,
                         "topic_hints": topics,
                         "resolution": number(item.get("resolution")),
                         "thermal_name_candidate": thermal,
                         "defrost_name_candidate": defrost})
    return {"state": "katalog_odczytany", "rows": rows,
            "candidate_ids": sorted(extra), "raw_scale_confirmed": False}, extra


@dataclass(frozen=True)
class Probe:
    key: str
    url: str
    target_id: str | None = None
    setup_id: int | None = None


def build_plan(devices, setup_id, _extra_ids, _now):
    selected = targets(devices)
    if not selected:
        return []
    # The account test showed that adding catalogue-only candidates makes the
    # whole capabilities request fail with HTTP 400. Keep candidate discovery
    # as metadata-only and query only the established, reviewed IDs.
    ids = sorted(CORE_IDS)
    if len(ids) > len(CORE_IDS) + 16 or any(type(x) is not int or not 0 <= x <= 2147483647 for x in ids):
        raise ValueError("capability bounds")
    plan = [Probe("capabilities_" + role, API_ORIGIN + "/magellan/capabilities/?" + urlencode({
        "deviceid": device_id, "capabilities": ";".join(map(str, ids))}), device_id)
        for role, device_id in selected]
    interface = selected[0][1]
    # Captured clients and an independent installation use these minimal,
    # lowercase WCF requests successfully. OpenAPI marks date and deviceId as
    # required, but both ISO dates and enum-case changes returned HTTP 400 on
    # this account. Test the observed wire shape without automatic variants.
    if type(setup_id) is int and 0 < setup_id <= 999999999999999999:
        for key, period in (("setup_daily_minimal", "daily"),
                            ("setup_monthly_minimal", "monthly")):
            plan.append(Probe(key, API_ORIGIN + f"/magellan/setups/{setup_id}/consumptions?"
                              + urlencode({"periodicity": period}), setup_id=setup_id))
    plan.append(Probe("device_monthly_minimal",
                      API_ORIGIN + f"/magellan/devices/{interface}/consumptions?"
                      + urlencode({"periodicity": "monthly"}), interface))
    return plan


def capability_summary(payload, reported, requested_ids):
    if not isinstance(payload, list) or len(payload) > 1024:
        raise ValueError("capability shape")
    rows = []
    seen = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("capability item")
        cap = item.get("capabilityId")
        if type(cap) is not int or cap not in requested_ids or cap in seen:
            continue
        seen.add(cap)
        stamp = item.get("modificationDate")
        rows.append({"capability_id": cap, "present_in_setup": cap in reported,
                     "numeric_value_raw": number(item.get("value")) if cap in CORE_IDS else None,
                     "last_change_epoch": stamp if type(stamp) is int and 1577836800 <= stamp < 4102444800 else None,
                     "measurement_time_confirmed": False})
    return {"state": "parametry_odczytane", "rows": rows,
            "missing_requested_ids": sorted(requested_ids - seen)}


def history_summary(payload):
    if not isinstance(payload, list) or len(payload) > 128:
        raise ValueError("history shape")
    rows = []
    count = 0
    for series in payload:
        if not isinstance(series, dict):
            raise ValueError("history series")
        periods = series.get("consumptionPeriods")
        if not isinstance(periods, list) or len(periods) > 3660:
            raise ValueError("history periods")
        def code(value):
            return value if type(value) is int and 0 <= value <= 10000 else None
        for item in periods:
            if not isinstance(item, dict):
                raise ValueError("history period")
            date = item.get("date")
            if type(date) is not int or not 1577836800 <= date < 4102444800:
                continue
            count += 1
            rows.append({"date_epoch": date, "category": code(series.get("category")),
                         "type": code(series.get("type")), "unit": code(series.get("unit")),
                         "mode": code(item.get("mode")), "profil": code(item.get("profil")),
                         "consumed_quantity_raw": number(item.get("consumedQuantity")),
                         "produced_quantity_raw": number(item.get("producedQuantity"))})
            # Keep output bounded during processing, not just afterwards.
            if len(rows) > 48:
                rows = sorted(rows, key=lambda x: x["date_epoch"], reverse=True)[:24]
    rows = sorted(rows, key=lambda x: x["date_epoch"], reverse=True)[:24]
    return {"state": "historia_odczytana" if count else "brak_okresow",
            "rows": rows, "omitted_rows": max(0, count-len(rows)),
            "thermal_energy_confirmed": False, "period_end_confirmed": False,
            "date_encoding": "epoch_seconds_hypothesis", "cop_ready": False}
