"""Minimal privacy-preserving diagnostics; never exports user or device identifiers."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .readings import CAPABILITIES


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Expose capability *IDs*, not their values or identifying metadata."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = []
    for index, device in enumerate(coordinator.data or [], start=1):
        reported = device.get("reported_capability_ids", [])
        # All input originated from our sanitizing readings parser.
        known = sorted(x for x in reported if x in CAPABILITIES)
        unknown = sorted(x for x in reported if x not in CAPABILITIES)
        devices.append(
            {
                "index": index,
                "reported_count": len(reported),
                "known_capability_ids": known,
                "unmapped_capability_ids": unknown,
            }
        )
    return {
        "diagnostics_format": 1,
        "connection": "official_atlantic_cloud_read_only",
        "last_poll_ok": bool(coordinator.last_update_success),
        "device_capability_inventory": devices,
    }
