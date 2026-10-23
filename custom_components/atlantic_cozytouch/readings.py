"""Pure functions for interpreting read-only Atlantic capability responses.

This module has no Home Assistant or network dependency, enabling offline tests.
Only explicitly recognized capabilities become entities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    title: str
    kind: str = "number"  # number, text, binary
    unit: str | None = None
    category: str | None = None  # temperature, pressure, energy, duration
    cumulative: bool = False
    diagnostic: bool = False


CAPABILITIES: dict[int, CapabilitySpec] = {
    6: CapabilitySpec("Błąd generatora", kind="text", diagnostic=True),
    24: CapabilitySpec("Uruchomienia sprężarki", cumulative=True, diagnostic=True),
    27: CapabilitySpec("Czas pracy sprężarki", unit="s", category="duration", cumulative=True, diagnostic=True),
    44: CapabilitySpec("Zużycie energii elektrycznej CO", unit="kWh", category="energy", cumulative=True),
    45: CapabilitySpec("Zużycie energii elektrycznej CWU", unit="kWh", category="energy", cumulative=True),
    46: CapabilitySpec("Łączne zużycie energii elektrycznej", unit="kWh", category="energy", cumulative=True),
    51: CapabilitySpec("Sprężarka pracuje", kind="binary", diagnostic=True),
    64: CapabilitySpec("Grzałka CWU pracuje", kind="binary", diagnostic=True),
    72: CapabilitySpec("Modulacja sprężarki", unit="%", diagnostic=True),
    100: CapabilitySpec("Ciśnienie wody", unit="bar", category="pressure"),
    109: CapabilitySpec("Temperatura obiegu", unit="°C", category="temperature"),
    110: CapabilitySpec("Temperatura obiegu 2", unit="°C", category="temperature"),
    111: CapabilitySpec("Temperatura CWU", unit="°C", category="temperature"),
    117: CapabilitySpec("Temperatura pokojowa strefa 1", unit="°C", category="temperature"),
    118: CapabilitySpec("Temperatura pokojowa strefa 2", unit="°C", category="temperature"),
    119: CapabilitySpec("Temperatura zewnętrzna", unit="°C", category="temperature"),
    150: CapabilitySpec("Kod błędu domu", kind="text", diagnostic=True),
    180: CapabilitySpec("Kod błędu jednostki zewnętrznej", kind="text", diagnostic=True),
}


def normalize_value(capability_id: int, value: object) -> float | str | bool | None:
    """Do not invent a reading when the API sends an unavailable value."""
    spec = CAPABILITIES.get(capability_id)
    if spec is None or value is None:
        return None
    raw = str(value).strip()
    if raw in ("", "---", "None", "null"):
        return None

    if spec.kind == "binary":
        if raw.lower() in ("1", "true", "on"):
            return True
        if raw.lower() in ("0", "false", "off"):
            return False
        return None

    if spec.kind == "text":
        return raw[:128]

    try:
        number = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None

    if not (-1000000000000 < number < 1000000000000):
        return None
    if capability_id == 119 and number <= -327.68:
        return None
    # Atlantic publishes these electrical energy counters in Wh, not kWh.
    # Conversion is required BEFORE exposing native_unit_of_measurement="kWh".
    if capability_id in (44, 45, 46):
        return number / 1000.0
    return number


def extract_devices(payload: object) -> list[dict]:
    """Return minimal, sanitized devices and allowlisted measurements only."""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        raise ValueError("Unexpected Atlantic setup response")

    response = payload[0]
    devices = response.get("devices")
    if not isinstance(devices, list):
        raise ValueError("Atlantic setup has no devices list")

    result: list[dict] = []
    for item in devices:
        if not isinstance(item, dict):
            continue
        device_id = item.get("deviceId")
        if not isinstance(device_id, (str, int)) or not str(device_id):
            continue

        values: dict[int, float | str | bool | None] = {}
        raw_capabilities = item.get("capabilities", [])
        if isinstance(raw_capabilities, list):
            for cap in raw_capabilities:
                if not isinstance(cap, dict):
                    continue
                try:
                    cap_id = int(cap.get("capabilityId"))
                except (ValueError, TypeError):
                    continue
                if cap_id in CAPABILITIES:
                    values[cap_id] = normalize_value(cap_id, cap.get("value"))

        if values:
            result.append(
                {
                    "id": str(device_id),
                    "name": str(item.get("name") or "Atlantic")[:100],
                    "values": values,
                }
            )
    return result
