"""Pure privacy-aware capability discovery; no HTTP access or HA dependency."""

from __future__ import annotations

from .readings import CAPABILITIES


def new_capabilities(devices: list[dict], kind: str, seen: set[tuple[str, int]]) -> list[tuple[dict, int]]:
    """Return entity descriptors only for newly reported, recognized capabilities."""
    if kind not in ("sensor", "binary"):
        raise ValueError("Unknown discovery platform")
    found = []
    for device in devices:
        for cap_id in device.get("values", {}):
            spec = CAPABILITIES.get(cap_id)
            if spec is None:
                continue
            if (spec.kind == "binary") != (kind == "binary"):
                continue
            identity = (device["id"], cap_id)
            if identity not in seen:
                found.append((device, cap_id))
    return found


def compressor_host_devices(devices: list[dict]) -> list[dict]:
    """Identify the actual heat-pump component without relying on its name.

    A compressor capability identifies it directly. On Extensa Magellan,
    the CO/CWU circuit (91) and hydraulic flow (112) identify the heat-pump
    device even when the cloud omits the compressor diagnostic capabilities.
    """
    result = []
    for device in devices:
        ids = set(device.get("reported_capability_ids", []))
        if {91, 112}.issubset(ids) or bool(ids & {24, 27, 51, 72}):
            result.append(device)
    return result


def redacted_inventory(devices: list[dict]) -> list[dict]:
    """Return ID lists only: no vendor values, names, IDs, serials or credentials."""
    result = []
    for index, device in enumerate(devices, start=1):
        ids = set(device.get("reported_capability_ids", []))
        result.append(
            {
                "index": index,
                "reported_count": len(ids),
                "known_capability_ids": sorted(ids & CAPABILITIES.keys()),
                "unmapped_capability_ids": sorted(ids - CAPABILITIES.keys()),
                "compressor_capability_ids": sorted(ids & {24, 27, 51, 72}),
            }
        )
    return result


def inventory_summary(devices: list[dict]) -> dict[str, int]:
    """Count unique reported parameter IDs across all devices."""
    ids = set()
    for device in devices:
        ids.update(device.get("reported_capability_ids", []))
    return {
        "reported_count": len(ids),
        "known_count": len(ids & CAPABILITIES.keys()),
        "unmapped_count": len(ids - CAPABILITIES.keys()),
        "device_count": len(devices),
    }
