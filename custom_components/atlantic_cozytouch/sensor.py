"""Read-only sensors for known Atlantic capability identifiers."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .readings import CAPABILITIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device in coordinator.data:
        for cap_id, spec in CAPABILITIES.items():
            if spec.kind == "binary" or cap_id not in device["values"]:
                continue
            entities.append(AtlanticReadOnlySensor(coordinator, device, cap_id))
    async_add_entities(entities)


class AtlanticReadOnlySensor(CoordinatorEntity, SensorEntity):
    """Publish a value from the last Atlantic snapshot."""

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
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                return device["values"].get(self._capability_id)
        return None
