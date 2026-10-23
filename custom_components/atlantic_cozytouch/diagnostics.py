"""Privacy-preserving device capability diagnostics. No parameter values."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .discovery import redacted_inventory


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "diagnostics_format": 4,
        "connection": "official_atlantic_cloud_read_only",
        "consumption_probe": dict(getattr(coordinator, "atlantic_consumptions", {"state": "nie_sprawdzono"})),
        "last_poll_ok": bool(coordinator.last_update_success),
        "device_capability_inventory": redacted_inventory(coordinator.data or []),
        "energy_validation": (
            coordinator.atlantic_energy.redacted_report(coordinator.data or [])
            if getattr(coordinator, "atlantic_energy", None) is not None else []
        ),
    }
