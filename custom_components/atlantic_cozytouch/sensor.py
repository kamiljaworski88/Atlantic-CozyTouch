"""Read-only Atlantic sensors with dynamic discovery after startup."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .compressor import COMPRESSOR_DERIVED_SPECS
from .discovery import new_capabilities, inventory_summary
from .readings import CAPABILITIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int]] = set()
    seen_derived: set[tuple[str, str]] = set()

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
        if entities:
            async_add_entities(entities)

    # Preserve the existing diagnostic unique_id across upgrades.
    async_add_entities([
        AtlanticLastPollSensor(coordinator, entry.entry_id),
        AtlanticCapabilityInventorySensor(coordinator, entry.entry_id),
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

        if spec.kind == "number":
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
