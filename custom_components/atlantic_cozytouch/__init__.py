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
from homeassistant.helpers.storage import Store

from .api import AtlanticAuthError, AtlanticError, AtlanticReadOnlyClient
from .const import DOMAIN, POLL_SECONDS, OPT_EXPERIMENTAL_CROSS_DEVICE_COP, OPT_API_DISCOVERY, OPT_COP2
from .compressor import CompressorMonitor
from .cop_snapshot import HydraulicCopEstimator
from .cop2_telemetry import Cop2Telemetry
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
    cop_monitor = HydraulicCopEstimator(
        allow_unique_cross_device=(
            entry.options.get(OPT_EXPERIMENTAL_CROSS_DEVICE_COP) is True
        )
    )

    # Store only anonymous estimated energy sums in HA's local .storage,
    # segregated by config entry. No cloud writes or device identifiers.
    cop_store = Store(hass, 1, f"{DOMAIN}.cop_accumulated_{entry.entry_id}")
    stored = await cop_store.async_load()
    if stored is not None:
        cop_monitor.restore_accumulated(stored)

    # Independent, versioned store; legacy accumulated COP storage is never
    # modified or reinterpreted as an individual last accepted COP sample.
    last_cop_store = Store(hass, 1, f"{DOMAIN}.last_cop_{entry.entry_id}")
    saved_last = await last_cop_store.async_load()
    if saved_last is not None:
        cop_monitor.restore_last_cops(saved_last)

    cop2_enabled = entry.options.get(OPT_COP2) is True
    cop2 = Cop2Telemetry(
        allow_cross=entry.options.get(OPT_EXPERIMENTAL_CROSS_DEVICE_COP) is True
    ) if cop2_enabled else None
    cop2_store = Store(hass, 1, f"{DOMAIN}.cop2_telemetry_{entry.entry_id}")
    if cop2_enabled:
        cop2.restore(await cop2_store.async_load())

    async def update():
        try:
            devices = await client.async_read()
            # Timestamp the setup observation before unrelated history probes.
            observed_at = datetime.now(UTC)
            # Bounded optional device GET. Its failure never prevents standard
            # telemetry or causes device writes.
            await client.async_probe_compressor_capabilities(devices)
            coordinator.atlantic_compressor_probe = dict(client.compressor_probe_summary)
            # Optional endpoint; errors are isolated from standard telemetry.
            await client.async_probe_consumptions()
            await client.async_probe_monthly_energy()
            await client.async_probe_device_energy()
            coordinator.atlantic_device_energy = dict(client.device_energy_summary)
            coordinator.atlantic_monthly_energy = dict(client.monthly_energy_summary)
            coordinator.atlantic_consumptions = dict(client.consumption_summary)
            coordinator.atlantic_daily_energy = {
                category: dict(days) for category, days in client.energy_daily.items()
            }
            compressor_monitor.ingest(devices, observed_at)
            energy_monitor.ingest(devices, observed_at)
            if cop2 is not None:
                # COP2 never mutates existing COP1 state, statistics or Energy.
                cop2.ingest(devices, observed_at, coordinator.atlantic_daily_energy)
                # Preserve bounded samples about every 15 minutes, not each poll.
                if observed_at - coordinator.atlantic_cop2_last_persist >= timedelta(minutes=15):
                    cop2_store.async_delay_save(cop2.export, 30)
                    coordinator.atlantic_cop2_last_persist = observed_at
            old_intervals = cop_monitor.accumulated_intervals
            old_last_cops = cop_monitor.export_last_cops()
            cop_monitor.ingest(devices, observed_at)
            if cop_monitor.export_last_cops() != old_last_cops:
                last_cop_store.async_delay_save(cop_monitor.export_last_cops, 60)
            if cop_monitor.accumulated_intervals != old_intervals:
                # Debounced disk write: preserve accepted intervals across
                # normal restarts without writing every poll.
                cop_store.async_delay_save(cop_monitor.export_accumulated, 60)
            if entry.options.get(OPT_API_DISCOVERY) is True:
                await client.async_probe_energy_discovery(devices)
                coordinator.atlantic_api_discovery = client.discovery_summary
            coordinator.atlantic_last_success_at = observed_at
            return devices
        except AtlanticAuthError as exc:
            compressor_monitor.invalidate()
            energy_monitor.invalidate()
            cop_monitor.invalidate()
            raise ConfigEntryAuthFailed("Atlantic rejected credentials") from exc
        except AtlanticError as exc:
            compressor_monitor.invalidate()
            energy_monitor.invalidate()
            cop_monitor.invalidate()
            raise UpdateFailed("Atlantic could not be polled") from exc

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="Atlantic CozyTouch read-only",
        update_method=update,
        update_interval=timedelta(seconds=POLL_SECONDS),
    )
    coordinator.atlantic_last_success_at = None
    coordinator.atlantic_cop2 = cop2
    coordinator.atlantic_cop2_store = cop2_store if cop2_enabled else None
    coordinator.atlantic_cop2_last_persist = datetime.min.replace(tzinfo=UTC)
    coordinator.atlantic_compressor = compressor_monitor
    coordinator.atlantic_energy = energy_monitor
    coordinator.atlantic_hydraulic_cop = cop_monitor
    coordinator.atlantic_cop_store = cop_store
    coordinator.atlantic_last_cop_store = last_cop_store
    coordinator.atlantic_compressor_probe = dict(client.compressor_probe_summary)
    coordinator.atlantic_consumptions = dict(client.consumption_summary)
    coordinator.atlantic_monthly_energy = dict(client.monthly_energy_summary)
    coordinator.atlantic_device_energy = dict(client.device_energy_summary)
    coordinator.atlantic_daily_energy = {}
    coordinator.atlantic_api_discovery = {"state": "wylaczone", "results": {}, "cop_ready": False}
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload without sending any device command."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Flush once when HA unloads/reloads the integration, including
        # user option changes. Never transmit aggregates to Atlantic.
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.atlantic_cop_store.async_save(
            coordinator.atlantic_hydraulic_cop.export_accumulated()
        )
        await coordinator.atlantic_last_cop_store.async_save(
            coordinator.atlantic_hydraulic_cop.export_last_cops()
        )
        if coordinator.atlantic_cop2 is not None:
            await coordinator.atlantic_cop2_store.async_save(
                coordinator.atlantic_cop2.export()
            )
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Restart one estimator after opt-in changes; never mix old baselines."""
    await hass.config_entries.async_reload(entry.entry_id)
