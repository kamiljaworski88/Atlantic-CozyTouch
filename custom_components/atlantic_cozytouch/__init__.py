"""Atlantic CozyTouch read-only integration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AtlanticAuthError, AtlanticError, AtlanticReadOnlyClient
from .const import DOMAIN, POLL_SECONDS
from .compressor import CompressorMonitor
from .energy_validation import EnergyValidationMonitor

_LOGGER = logging.getLogger(__name__)

# Deliberately expose *no* actuator platforms.
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize only polling entities and never register command services."""
    client = AtlanticReadOnlyClient(
        async_get_clientsession(hass), entry.data["username"], entry.data["password"]
    )

    compressor_monitor = CompressorMonitor()
    energy_monitor = EnergyValidationMonitor()

    async def update():
        try:
            devices = await client.async_read()
            observed_at = datetime.now(UTC)
            compressor_monitor.ingest(devices, observed_at)
            energy_monitor.ingest(devices, observed_at)
            coordinator.atlantic_last_success_at = observed_at
            return devices
        except AtlanticAuthError as exc:
            compressor_monitor.invalidate()
            energy_monitor.invalidate()
            raise ConfigEntryAuthFailed("Atlantic rejected credentials") from exc
        except AtlanticError as exc:
            compressor_monitor.invalidate()
            raise UpdateFailed("Atlantic could not be polled") from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Atlantic CozyTouch read-only",
        update_method=update,
        update_interval=timedelta(seconds=POLL_SECONDS),
    )
    coordinator.atlantic_last_success_at = None
    coordinator.atlantic_compressor = compressor_monitor
    coordinator.atlantic_energy = energy_monitor
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload without sending any device command."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
