"""Read-only diagnostic binary sensors. No switches or writable entities."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .readings import CAPABILITIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for device in coordinator.data:
        for cap_id, spec in CAPABILITIES.items():
            if spec.kind != "binary" or cap_id not in device["values"]:
                continue
            entities.append(AtlanticReadOnlyBinarySensor(coordinator, device, cap_id))
    entities.append(AtlanticCloudStatusSensor(coordinator, entry.entry_id))
    async_add_entities(entities)


class AtlanticReadOnlyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A reported on/off state, never a command entity."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, device: dict, capability_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._capability_id = capability_id
        self._attr_name = CAPABILITIES[capability_id].title
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_{capability_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"],
            manufacturer="Atlantic",
        )

    @property
    def is_on(self):
        for device in self.coordinator.data:
            if device["id"] == self._device_id:
                return device["values"].get(self._capability_id)
        return None


class AtlanticCloudStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """HA-level polling health, not the compressor or physical pump state."""

    _attr_has_entity_name = True
    _attr_name = "Odczyt z chmury Atlantic działa"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_cloud_read_ok"

    @property
    def available(self) -> bool:
        # The health entity itself must remain visible on failed refreshes.
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)
