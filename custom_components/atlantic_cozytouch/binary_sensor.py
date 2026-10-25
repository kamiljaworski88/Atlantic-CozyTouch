"""Read-only Atlantic binary sensors with dynamic capability discovery."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .compressor import compressor_operating_state
from .discovery import compressor_host_devices, new_capabilities
from .readings import CAPABILITIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int]] = set()

    def add_new() -> None:
        discovered = new_capabilities(coordinator.data or [], kind="binary", seen=seen)
        entities = []
        # Register the compressor state on the real heat pump even if Magellan
        # does not expose ID 51. Keep the original ID51 unique_id stable.
        # Unknown is safer than inferring "on" from the selected heat circuit.
        for device in compressor_host_devices(coordinator.data or []):
            key = (device["id"], 51)
            if key not in seen:
                seen.add(key)
                entities.append(AtlanticCompressorStateSensor(coordinator, device))
        for device, cap_id in discovered:
            if (device["id"], cap_id) in seen:
                continue
            seen.add((device["id"], cap_id))
            entities.append(
                AtlanticCompressorStateSensor(coordinator, device)
                if cap_id == 51 else AtlanticReadOnlyBinarySensor(coordinator, device, cap_id)
            )
        if entities:
            async_add_entities(entities)

    async_add_entities([AtlanticCloudStatusSensor(coordinator, entry.entry_id)])
    add_new()
    unsub = coordinator.async_add_listener(add_new)
    entry.async_on_unload(unsub)


class AtlanticReadOnlyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """The vendor's binary status only; no control methods."""

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
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                return device["values"].get(self._capability_id)
        return None


class AtlanticCompressorStateSensor(AtlanticReadOnlyBinarySensor):
    """Stable entity for ID51; safely fall back to *fresh* ID72 only."""

    def __init__(self, coordinator, device: dict) -> None:
        super().__init__(coordinator, device, 51)

    def _reading(self) -> tuple[bool | None, str]:
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                return compressor_operating_state(
                    device.get("values", {}),
                    device.get("updated_at", {}),
                    datetime.now(UTC),
                )
        return None, "brak_urzadzenia_w_api"

    @property
    def is_on(self):
        if not self.coordinator.last_update_success:
            return None
        return self._reading()[0]

    @property
    def extra_state_attributes(self):
        _value, source = self._reading()
        return {
            "zrodlo_stanu": source,
            "ostroznosc": "unknown oznacza brak wiarygodnej telemetrii",
            "odczyt_zdalny_bez_sterowania": True,
        }


class AtlanticCloudStatusSensor(CoordinatorEntity, BinarySensorEntity):
    """Polling health, not the compressor or pump operating state."""

    _attr_has_entity_name = True
    _attr_name = "Odczyt z chmury Atlantic działa"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_cloud_read_ok"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.last_update_success)
