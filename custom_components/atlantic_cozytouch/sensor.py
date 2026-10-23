"""Read-only Atlantic sensors with dynamic discovery after startup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, POLL_SECONDS
from .energy_validation import freshness_status
from .compressor import COMPRESSOR_DERIVED_SPECS
from .discovery import new_capabilities, inventory_summary
from .readings import CAPABILITIES, provisional_energy_kwh


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int]] = set()
    seen_derived: set[tuple[str, str]] = set()
    seen_energy: set[tuple[str, int]] = set()
    seen_provisional: set[tuple[str, str]] = set()

    def add_new() -> None:
        discovered = new_capabilities(coordinator.data or [], kind="sensor", seen=seen)
        entities = []
        for device, cap_id in discovered:
            seen.add((device["id"], cap_id))
            entities.append(AtlanticReadOnlySensor(coordinator, device, cap_id))
        for device in coordinator.data or []:
            reported = set(device.get("reported_capability_ids", []))
            if not reported.intersection({24, 27, 51, 72}):
                continue
            for metric, info in COMPRESSOR_DERIVED_SPECS.items():
                if not info.required_capabilities.issubset(reported):
                    continue
                identity = (device["id"], metric)
                if identity not in seen_derived:
                    seen_derived.add(identity)
                    entities.append(AtlanticCompressorDerivedSensor(coordinator, device, metric))
        for device in coordinator.data or []:
            for cap_id in (57, 59):
                if cap_id not in device.get("reported_capability_ids", []):
                    continue
                key = (device["id"], cap_id)
                if key not in seen_energy:
                    seen_energy.add(key)
                    entities.append(AtlanticRawEnergyDeltaSensor(coordinator, device, cap_id))

            # Model-specific assumption from on-device monthly display:
            # 57 -> CO (Wh), 59 -> CWU (Wh). No long-term HA statistics.
            for cap_id in (57, 59):
                if cap_id not in reported:
                    continue
                assumed_key = (device["id"], str(cap_id))
                if assumed_key not in seen_provisional:
                    seen_provisional.add(assumed_key)
                    entities.append(AtlanticProvisionalEnergySensor(coordinator, device, cap_id))
            total_key = (device["id"], "sum")
            if {57, 59}.issubset(reported) and total_key not in seen_provisional:
                seen_provisional.add(total_key)
                entities.append(AtlanticProvisionalEnergySensor(coordinator, device, None))
            if 60 in device.get("reported_capability_ids", []):
                key = (device["id"], 60)
                if key not in seen_energy:
                    seen_energy.add(key)
                    entities.append(AtlanticEnergyValueStatusSensor(coordinator, device))
        if entities:
            async_add_entities(entities)

    # Preserve the existing diagnostic unique_id across upgrades.
    async_add_entities([
        AtlanticLastPollSensor(coordinator, entry.entry_id),
        AtlanticCapabilityInventorySensor(coordinator, entry.entry_id),
        AtlanticTelemetryFreshnessSensor(coordinator, entry.entry_id),
    ])
    add_new()
    unsub = coordinator.async_add_listener(add_new)
    entry.async_on_unload(unsub)


class AtlanticReadOnlySensor(CoordinatorEntity, SensorEntity):
    """Read a known vendor capability, identified by device ID and cap ID."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, device: dict, capability_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._capability_id = capability_id
        spec = CAPABILITIES[capability_id]

        self._attr_name = spec.title
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{capability_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"],
            manufacturer="Atlantic",
        )
        if spec.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = spec.unit
        if spec.category == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
        elif spec.category == "pressure":
            self._attr_device_class = SensorDeviceClass.PRESSURE
        elif spec.category == "energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
        elif spec.category == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION

        # Unverified numeric values are diagnostic only, never part of HA energy stats.
        if spec.kind == "number" and spec.publish_statistics:
            self._attr_state_class = (
                SensorStateClass.TOTAL_INCREASING
                if spec.cumulative
                else SensorStateClass.MEASUREMENT
            )

    @property
    def native_value(self):
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                return device["values"].get(self._capability_id)
        return None


class AtlanticProvisionalEnergySensor(CoordinatorEntity, SensorEntity):
    """Model-specific Wh->kWh hypothesis, without Energy Dashboard state class."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:lightning-bolt-outline"

    def __init__(self, coordinator, device: dict, cap_id: int | None) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._cap_id = cap_id
        self._attr_name = {
            57: "Energia elektryczna CO (robocza)",
            59: "Energia elektryczna CWU (robocza)",
            None: "Energia elektryczna CO i CWU (suma robocza)",
        }[cap_id]
        self._attr_unique_id = (
            f"{DOMAIN}_{self._device_id}_provisional_electric_"
            f"{cap_id if cap_id is not None else 'sum'}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"],
            manufacturer="Atlantic",
        )
        # Deliberately no SensorStateClass.TOTAL_INCREASING and no COP.

    @property
    def native_value(self):
        for device in self.coordinator.data or []:
            if device["id"] != self._device_id:
                continue
            reported = set(device.get("reported_capability_ids", []))
            required = (57, 59) if self._cap_id is None else (self._cap_id,)
            if not set(required).issubset(reported):
                return None
            parts = [provisional_energy_kwh(cap, device["values"].get(cap)) for cap in required]
            if any(part is None for part in parts):
                return None
            return round(sum(parts), 3)
        return None

    @property
    def extra_state_attributes(self):
        return {
            "source_capability_ids": [57, 59] if self._cap_id is None else [self._cap_id],
            "scaling_assumption": "Wh / 1000",
            "mapping_verified": False,
            "counter_period_verified": False,
            "home_assistant_energy_statistics": False,
        }


class AtlanticLastPollSensor(CoordinatorEntity, SensorEntity):
    """Timestamp of the most recent successful read from Atlantic."""

    _attr_has_entity_name = True
    _attr_name = "Ostatni udany odczyt"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_last_success"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return getattr(self.coordinator, "atlantic_last_success_at", None)


class AtlanticCapabilityInventorySensor(CoordinatorEntity, SensorEntity):
    """Count discovered capability IDs, never expose their raw values."""

    _attr_has_entity_name = True
    _attr_name = "Wykryte parametry Atlantic"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_capability_count"

    @property
    def native_value(self):
        return inventory_summary(self.coordinator.data or [])["reported_count"]

    @property
    def extra_state_attributes(self):
        summary = inventory_summary(self.coordinator.data or [])
        return {
            "known_capabilities": summary["known_count"],
            "unmapped_capabilities": summary["unmapped_count"],
            "devices": summary["device_count"],
        }


class AtlanticCompressorDerivedSensor(CoordinatorEntity, SensorEntity):
    """Calculated from counters reported by the same device; no commands."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device: dict, metric: str) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._metric = metric
        spec = COMPRESSOR_DERIVED_SPECS[metric]
        self._attr_name = spec.label
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_compressor_{metric}"
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"],
            manufacturer="Atlantic",
        )
        if spec.category == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = (
            SensorStateClass.TOTAL_INCREASING
            if spec.cumulative
            else SensorStateClass.MEASUREMENT
        )

    @property
    def native_value(self):
        monitor = self.coordinator.atlantic_compressor
        return monitor.metrics.get(self._device_id, {}).get(self._metric)


class AtlanticRawEnergyDeltaSensor(CoordinatorEntity, SensorEntity):
    """Unit-free difference between valid, continuous polls; NO HA statistics."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:delta"

    def __init__(self, coordinator, device: dict, cap_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._cap_id = cap_id
        self._attr_name = f"Przyrost surowego wskazania ID {cap_id}"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_energy_delta_{cap_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"], manufacturer="Atlantic",
        )

    @property
    def native_value(self):
        if not self.coordinator.last_update_success:
            return None
        return self.coordinator.atlantic_energy.statuses.get(self._device_id, {}).get(
            self._cap_id, {}
        ).get("delta_raw")

    @property
    def extra_state_attributes(self):
        item = self.coordinator.atlantic_energy.statuses.get(self._device_id, {}).get(
            self._cap_id, {}
        )
        return {
            "comparison_status": item.get("comparison", "not_reported"),
            "value_status": item.get("value_status", "not_reported"),
            "units_verified": False,
        }


class AtlanticEnergyValueStatusSensor(CoordinatorEntity, SensorEntity):
    """Reason why ID 60 reads unknown, without exposing raw vendor text."""

    _attr_has_entity_name = True
    _attr_name = "Diagnostyka wskazania ID 60"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clipboard-text-search-outline"

    def __init__(self, coordinator, device: dict) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_energy_status_60"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"], manufacturer="Atlantic",
        )

    @property
    def native_value(self):
        if not self.coordinator.last_update_success:
            return "ostatni_odczyt_nieudany"
        return self.coordinator.atlantic_energy.statuses.get(self._device_id, {}).get(
            60, {}
        ).get("value_status", "niezgloszony")


class AtlanticTelemetryFreshnessSensor(CoordinatorEntity, SensorEntity):
    """Freshness status recalculated once per minute, also during API outages."""

    _attr_has_entity_name = True
    _attr_name = "Aktualność telemetrii Atlantic"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-clock-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_telemetry_freshness"

    @property
    def available(self) -> bool:
        return True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_track_time_interval(
            self.hass, self._refresh_state, timedelta(minutes=1)
        ))

    def _refresh_state(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        return freshness_status(
            getattr(self.coordinator, "atlantic_last_success_at", None),
            self.coordinator.last_update_success,
            datetime.now(UTC),
            POLL_SECONDS,
        )

    @property
    def extra_state_attributes(self):
        return {
            "expected_poll_interval_seconds": POLL_SECONDS,
            "max_fresh_age_seconds": int(POLL_SECONDS * 2.5),
        }
