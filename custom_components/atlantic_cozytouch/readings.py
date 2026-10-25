"""Pure functions for interpreting read-only Atlantic capability responses.

This module has no Home Assistant or network dependency, enabling offline tests.
Only explicitly recognized capabilities become entities.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    title: str
    kind: str = "number"  # number, text, binary, enum
    unit: str | None = None
    category: str | None = None  # temperature, pressure, energy, duration
    cumulative: bool = False
    diagnostic: bool = False
    publish_statistics: bool = True  # disabled for unverified vendor raw readings


MAX_DEVICES_PER_ACCOUNT = 128
MAX_CAPABILITIES_PER_DEVICE = 1024
MAX_CAPABILITY_ID = 2_147_483_647  # Vendor also uses six-digit identifiers.

CAPABILITIES: dict[int, CapabilitySpec] = {
    6: CapabilitySpec("Błąd generatora", kind="text", diagnostic=True),
    24: CapabilitySpec("Uruchomienia sprężarki", cumulative=True, diagnostic=True),
    25: CapabilitySpec("Uruchomienia pompy obiegu CO", cumulative=True, diagnostic=True),
    26: CapabilitySpec("Uruchomienia pompy obiegu CWU", cumulative=True, diagnostic=True),
    27: CapabilitySpec("Czas pracy sprężarki", unit="s", category="duration", cumulative=True, diagnostic=True),
    28: CapabilitySpec("Czas pracy pompy CO", unit="h", category="duration", cumulative=True, diagnostic=True),
    29: CapabilitySpec("Czas pracy pompy CWU", unit="h", category="duration", cumulative=True, diagnostic=True),
    44: CapabilitySpec("Zużycie energii elektrycznej CO", unit="kWh", category="energy", cumulative=True),
    45: CapabilitySpec("Zużycie energii elektrycznej CWU", unit="kWh", category="energy", cumulative=True),
    46: CapabilitySpec("Łączne zużycie energii elektrycznej", unit="kWh", category="energy", cumulative=True),
    # 57/59/60 appear in the Atlantic vendor mapping as ENERGY, but their
    # scaling, reset semantics and meaning on this model are not field-verified.
    # Expose raw numeric diagnostics WITHOUT kWh, energy device_class or statistics.
    57: CapabilitySpec("Wskazanie energii · ID 57 (surowe)", diagnostic=True, publish_statistics=False),
    59: CapabilitySpec("Wskazanie energii · ID 59 (surowe)", diagnostic=True, publish_statistics=False),
    60: CapabilitySpec("Wskazanie energii · ID 60 (surowe)", diagnostic=True, publish_statistics=False),
    91: CapabilitySpec("Aktywny obieg CO/CWU · ID 91", kind="enum", diagnostic=True),
    99: CapabilitySpec("Stan funkcji CWU · ID 99", kind="binary", diagnostic=True),
    112: CapabilitySpec("Odczyt przepływu · ID 112 (surowy)", diagnostic=True, publish_statistics=False),
    116: CapabilitySpec("Temperatura powrotu obiegu · ID 116", unit="°C", category="temperature", diagnostic=True, publish_statistics=False),
    153: CapabilitySpec("Stan ogrzewania · ID 153", kind="enum", diagnostic=True),
    164: CapabilitySpec("Możliwości pomiaru energii · ID 164", diagnostic=True, publish_statistics=False),
    181: CapabilitySpec("Wykonywany tryb · ID 181", kind="enum", diagnostic=True),
    380: CapabilitySpec("Kod diagnostyczny CESA · ID 380", diagnostic=True, publish_statistics=False),
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


# Interoperability codes cross-checked with Cozytouch's public capability table.
# Unknown values stay unknown; never guess or treat modes as compressor activity.
READ_ONLY_ENUMS: dict[int, dict[str, str]] = {
    91: {"1": "CO", "3": "CWU"},
    153: {"0": "Wyłączone", "1": "Ogrzewanie", "2": "Chłodzenie"},
    181: {
        "0": "Wyłączony", "1": "Automatyczny", "3": "Chłodzenie",
        "4": "Ogrzewanie", "5": "Ogrzewanie awaryjne",
        "6": "Chłodzenie wstępne", "7": "Wentylacja",
        "8": "Osuszanie", "9": "Nocny",
    },
}


def energy_value_status(value: object) -> str:
    """Classify an energy field without retaining or disclosing its raw text."""
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return "invalid_format"
    raw = str(value).strip()
    if raw.lower() in ("", "---", "none", "null", "unknown", "unavailable"):
        return "empty"
    try:
        number = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return "invalid_format"
    if not (0 <= number < 1_000_000_000_000):
        return "negative" if number < 0 else "out_of_range"
    return "valid"


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

    if spec.kind == "enum":
        return READ_ONLY_ENUMS[capability_id].get(raw)

    try:
        number = float(raw.replace(",", "."))
    except (TypeError, ValueError):
        return None

    if not (-1000000000000 < number < 1000000000000):
        return None
    # The vendor sometimes reports ~-273 °C for an inactive temperature probe.
    # This is an invalid sentinel, not a physical water/room temperature.
    if spec.category == "temperature" and (number <= -200 or number > 180):
        return None
    # Cumulative counters cannot be negative. Modulation is a percentage.
    if capability_id in (24, 25, 26, 27, 28, 29) and number < 0:
        return None
    if capability_id == 72 and not 0 <= number <= 100:
        return None
    if capability_id in (57, 59, 60, 112) and number < 0:
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
    if len(devices) > MAX_DEVICES_PER_ACCOUNT:
        raise ValueError("Atlantic setup exceeds allowed device count")

    result: list[dict] = []
    for item in devices:
        if not isinstance(item, dict):
            continue
        device_id = item.get("deviceId")
        if isinstance(device_id, bool) or not isinstance(device_id, (str, int)):
            continue
        safe_id = str(device_id).strip()
        if not safe_id or len(safe_id) > 128 or not safe_id.isprintable():
            continue

        values: dict[int, float | str | bool | None] = {}
        reported_ids: set[int] = set()
        energy_status: dict[int, str] = {}
        updated_at: dict[int, int] = {}
        raw_capabilities = item.get("capabilities", [])
        if isinstance(raw_capabilities, list):
            if len(raw_capabilities) > MAX_CAPABILITIES_PER_DEVICE:
                raise ValueError("Atlantic device exceeds allowed capability count")
            for cap in raw_capabilities:
                if not isinstance(cap, dict):
                    continue
                try:
                    cap_id = int(cap.get("capabilityId"))
                except (ValueError, TypeError):
                    continue
                if not 0 <= cap_id <= MAX_CAPABILITY_ID:
                    continue
                reported_ids.add(cap_id)
                if cap_id in (51, 57, 59, 72, 91, 109, 112, 116):
                    timestamp = cap.get("modificationDate")
                    if type(timestamp) is int and 1577836800 <= timestamp <= 4102444799:
                        updated_at[cap_id] = timestamp
                if cap_id in (57, 59, 60):
                    energy_status[cap_id] = energy_value_status(cap.get("value"))
                if cap_id in CAPABILITIES:
                    values[cap_id] = normalize_value(cap_id, cap.get("value"))

        if values or reported_ids:
            result.append(
                {
                    "id": safe_id,
                    "name": str(item.get("name") or "Atlantic")[:100],
                    "values": values,
                    "energy_status": energy_status,
                    "updated_at": updated_at,  # bounded capability timestamps, not poll time
                    # IDs only; no unknown measurements are retained/exported.
                    "reported_capability_ids": sorted(reported_ids),
                }
            )
    return result
