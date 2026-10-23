"""Privacy-preserving device capability diagnostics. No parameter values."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .discovery import redacted_inventory


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "diagnostics_format": 3,
        "connection": "official_atlantic_cloud_read_only",
        "last_poll_ok": bool(coordinator.last_update_success),
        "device_capability_inventory": redacted_inventory(coordinator.data or []),
        "energy_validation": (
            coordinator.atlantic_energy.redacted_report(coordinator.data or [])
            if getattr(coordinator, "atlantic_energy", None) is not None else []
        ),
    }
