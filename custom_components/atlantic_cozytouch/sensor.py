"""Read-only Atlantic sensors with dynamic discovery after startup."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, POLL_SECONDS
from .energy_validation import freshness_status
from .consumption_probe import energy_capabilities_summary, production_heat_feature_flags
from .energy_preview import ENERGY_CANDIDATES, candidate_kwh, candidate_summary, cop_readiness
from .thermal_evidence import thermal_evidence
from .compressor import COMPRESSOR_DERIVED_SPECS
from .discovery import compressor_host_devices, new_capabilities, inventory_summary
from .readings import CAPABILITIES


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int]] = set()
    seen_derived: set[tuple[str, str]] = set()
    seen_energy: set[tuple[str, int]] = set()
    seen_previews: set[tuple[str, int]] = set()

    def add_new() -> None:
        discovered = new_capabilities(coordinator.data or [], kind="sensor", seen=seen)
        entities = []
        for device, cap_id in discovered:
            seen.add((device["id"], cap_id))
            entities.append(AtlanticReadOnlySensor(coordinator, device, cap_id))
        for device in compressor_host_devices(coordinator.data or []):
            # All compressor cards are registered for the heat pump, even if
            # the Atlantic cloud omits 24/27/72. Missing readings stay unknown.
            for cap_id in (24, 27, 72):
                key = (device["id"], cap_id)
                if key not in seen:
                    seen.add(key)
                    entities.append(AtlanticReadOnlySensor(coordinator, device, cap_id))
            for metric in COMPRESSOR_DERIVED_SPECS:
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
            if 60 in device.get("reported_capability_ids", []):
                key = (device["id"], 60)
                if key not in seen_energy:
                    seen_energy.add(key)
                    entities.append(AtlanticEnergyValueStatusSensor(coordinator, device))
        # Tentative electrical energy preview: new diagnostic entities only.
        # No Energy device_class/state_class until comparison with the controller.
        for device in coordinator.data or []:
            for cap_id in ENERGY_CANDIDATES:
                key = (device["id"], cap_id)
                if cap_id in device.get("reported_capability_ids", []) and key not in seen_previews:
                    seen_previews.add(key)
                    entities.append(AtlanticEnergyPreviewSensor(coordinator, device, cap_id))
        if entities:
            async_add_entities(entities)

    # Preserve the existing diagnostic unique_id across upgrades.
    async_add_entities([
        AtlanticApiDiscoverySensor(coordinator, entry.entry_id),
        AtlanticLastPollSensor(coordinator, entry.entry_id),
        AtlanticCapabilityInventorySensor(coordinator, entry.entry_id),
        AtlanticTelemetryFreshnessSensor(coordinator, entry.entry_id),
        AtlanticConsumptionProbeSensor(coordinator, entry.entry_id),
        AtlanticThermalProductionSupportSensor(coordinator, entry.entry_id),
        AtlanticMonthlyEnergyProbeSensor(coordinator, entry.entry_id),
        AtlanticDeviceEnergyProbeSensor(coordinator, entry.entry_id),
        AtlanticCompressorProbeSensor(coordinator, entry.entry_id),
        AtlanticCopReadinessSensor(coordinator, entry.entry_id),
        AtlanticThermalEvidenceSensor(coordinator, entry.entry_id),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "cop"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "live_cop"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "last_cop_co"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "last_cop_cwu"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "last_cop"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "cumulative_total"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "cumulative_co"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "cumulative_cwu"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "thermal_kw"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "electrical_kw"),
        AtlanticHydraulicCopSensor(coordinator, entry.entry_id, "status"),
        AtlanticDailyElectricitySensor(coordinator, entry.entry_id, 1, 0),
        AtlanticDailyElectricitySensor(coordinator, entry.entry_id, 2, 0),
        AtlanticDailyElectricitySensor(coordinator, entry.entry_id, 1, 1),
        AtlanticDailyElectricitySensor(coordinator, entry.entry_id, 2, 1),
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

    @property
    def extra_state_attributes(self):
        if self._capability_id in (8, 9, 11):
            return {
                "surowy_odczyt_bez_jednostki": True,
                "katalog_atlantic_jednostka": "kW",
                "katalog_atlantic_maksimum_kw": 20,
                "skala_surowej_wartosci_zweryfikowana": False,
                "czy_grzalka_pracuje_potwierdzone": False,
                "uwaga": "Sam dodatni odczyt nie dowodzi pracy grzalki",
            }
        if self._capability_id not in (24, 27, 72):
            return {}
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                reported = self._capability_id in device.get("reported_capability_ids", [])
                return {
                    "zgloszone_przez_api": reported,
                    "status": "odczyt_z_chmury" if reported else "brak_parametru_w_api",
                }
        return {"status": "brak_urzadzenia_w_api"}


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

    @property
    def extra_state_attributes(self):
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                required = COMPRESSOR_DERIVED_SPECS[self._metric].required_capabilities
                missing = sorted(required - set(device.get("reported_capability_ids", [])))
                return {
                    "brakujace_id_w_api": missing,
                    "status": "brak_telemetrii" if missing else "zalezy_od_danych_i_ciaglosci_odczytow",
                    "wynik_dodatkowego_odczytu": getattr(
                        self.coordinator, "atlantic_compressor_probe", {}
                    ).get("state", "nie_sprawdzono"),
                }
        return {"status": "brak_urzadzenia_w_api"}


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


class AtlanticCompressorProbeSensor(CoordinatorEntity, SensorEntity):
    """Result of the optional per-device read; no raw identifiers or values."""

    _attr_has_entity_name = True
    _attr_name = "Diagnostyka odczytu sprężarki z API"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-search-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_compressor_direct_probe"

    @property
    def native_value(self):
        return getattr(self.coordinator, "atlantic_compressor_probe", {}).get(
            "state", "nie_sprawdzono"
        )

    @property
    def extra_state_attributes(self):
        return dict(getattr(self.coordinator, "atlantic_compressor_probe", {}))


class AtlanticMonthlyEnergyProbeSensor(CoordinatorEntity, SensorEntity):
    """Anonymized monthly history: production field is not confirmed heat."""

    _attr_has_entity_name = True
    _attr_name = "Historia energii Atlantic · miesięczna kontrola"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar-search"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_monthly_energy_probe"

    @property
    def native_value(self):
        return getattr(self.coordinator, "atlantic_monthly_energy", {}).get(
            "state", "nie_sprawdzono"
        )

    @property
    def extra_state_attributes(self):
        return dict(getattr(self.coordinator, "atlantic_monthly_energy", {}))


class AtlanticDeviceEnergyProbeSensor(CoordinatorEntity, SensorEntity):
    """Schema-only device consumption diagnostics, without private values."""

    _attr_has_entity_name = True
    _attr_name = "Historia energii Atlantic · odczyt urządzenia"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-search-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_device_energy_probe"

    @property
    def native_value(self):
        return getattr(self.coordinator, "atlantic_device_energy", {}).get(
            "state", "nie_sprawdzono"
        )

    @property
    def extra_state_attributes(self):
        return dict(getattr(self.coordinator, "atlantic_device_energy", {}))


class AtlanticThermalProductionSupportSensor(CoordinatorEntity, SensorEntity):
    """Show *support* flags from 164, not produced heat or COP readings."""

    _attr_has_entity_name = True
    _attr_name = "Możliwości produkcji ciepła · ID 164 (hipoteza)"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:heat-wave"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_heat_production_support"

    @property
    def native_value(self):
        return production_heat_feature_flags(self.coordinator.data or [])["status"]

    @property
    def extra_state_attributes(self):
        return production_heat_feature_flags(self.coordinator.data or [])


class AtlanticConsumptionProbeSensor(CoordinatorEntity, SensorEntity):
    """Safe API endpoint status: no raw energy values, tokens, or setup ID."""

    _attr_has_entity_name = True
    _attr_name = "Historia energii Atlantic · test API"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_consumption_probe"

    @property
    def native_value(self):
        status = getattr(self.coordinator, "atlantic_consumptions", {})
        return status.get("state", "nie_sprawdzono")

    @property
    def extra_state_attributes(self):
        status = getattr(self.coordinator, "atlantic_consumptions", {})
        return {
            **status,
            "deklarowane_pomiary_id164": energy_capabilities_summary(
                self.coordinator.data or []
            ),
            "hipoteza_flag_produkcji": production_heat_feature_flags(
                self.coordinator.data or []
            ),
        }


class AtlanticEnergyPreviewSensor(CoordinatorEntity, SensorEntity):
    """Hypothetical kWh only. Never contributes to Home Assistant statistics."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "kWh"
    _attr_icon = "mdi:flash-outline"

    def __init__(self, coordinator, device: dict, cap_id: int) -> None:
        super().__init__(coordinator)
        self._device_id = device["id"]
        self._cap_id = cap_id
        self._attr_name = (
            "Hipoteza energii CO · ID 57" if cap_id == 57
            else "Hipoteza energii CWU · ID 59"
        )
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_preview_kwh_{cap_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device["name"], manufacturer="Atlantic",
        )
        # Deliberately no energy device class or statistics state class.

    @property
    def native_value(self):
        if not self.coordinator.last_update_success:
            return None
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                return candidate_kwh(device, self._cap_id)
        return None

    @property
    def extra_state_attributes(self):
        for device in self.coordinator.data or []:
            if device["id"] == self._device_id:
                return candidate_summary(device, self._cap_id)
        return {"przypisanie_i_skala_zweryfikowane": False}


class AtlanticCopReadinessSensor(CoordinatorEntity, SensorEntity):
    """Status of COP evidence; deliberately never reports a numeric COP."""

    _attr_has_entity_name = True
    _attr_name = "COP Atlantic · gotowość danych"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_cop_readiness"

    @property
    def native_value(self):
        return cop_readiness(getattr(self.coordinator, "atlantic_consumptions", None))

    @property
    def extra_state_attributes(self):
        s = getattr(self.coordinator, "atlantic_consumptions", {})
        return {
            "stan_historii_miesiecznej": getattr(
                self.coordinator, "atlantic_monthly_energy", {}
            ).get("state", "nie_sprawdzono"),
            # producedQuantity may mean electricity; never label it heat.
            "rekordy_produkcji_ciepla": None,
            "rekordy_produkcji_nieokreslonej": s.get("okresy_z_energia_wyprodukowana", 0),
            "rekordy_dodatniej_produkcji_nieokreslonej": s.get("okresy_z_dodatnia_produkcja", 0),
            "miesieczne_pary_pobor_produkcja_nieokreslona": getattr(
                self.coordinator, "atlantic_monthly_energy", {}
            ).get("rekordy_z_para_poboru_i_produkcji_nieokreslonej", 0),
            "produkcja_ciepla_zidentyfikowana": False,
            "deklarowane_pomiary_id164": energy_capabilities_summary(self.coordinator.data or []),
            "hipoteza_flag_produkcji": production_heat_feature_flags(self.coordinator.data or []),
            "cop_wyliczony": False,
            "powod": "Brak zweryfikowanych pomiarów ciepła i energii elektrycznej w tym samym okresie",
        }

class AtlanticThermalEvidenceSensor(CoordinatorEntity, SensorEntity):
    """Read-only anonymized four-source audit; never exposes heat kWh or COP."""

    _attr_has_entity_name = True
    _attr_name = "COP Atlantic · audyt źródeł ciepła"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clipboard-search-outline"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_thermal_evidence"

    def _summary(self) -> dict:
        return thermal_evidence(
            getattr(self.coordinator, "atlantic_consumptions", {}),
            getattr(self.coordinator, "atlantic_monthly_energy", {}),
            getattr(self.coordinator, "atlantic_device_energy", {}),
            production_heat_feature_flags(self.coordinator.data or []),
        )

    @property
    def native_value(self):
        return self._summary()["status"]

    @property
    def extra_state_attributes(self):
        summary = self._summary()
        return {k: v for k, v in summary.items() if k != "status"}


class AtlanticDailyElectricitySensor(CoordinatorEntity, SensorEntity):
    """Daily cloud electricity for exactly one category and one UTC day.

    These are account-level daily buckets, not lifetime device meters.
    We never mix two different categories or inject historical statistics.
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator, entry_id: str, category: int, offset: int) -> None:
        super().__init__(coordinator)
        if category not in (1, 2) or offset not in (0, 1):
            raise ValueError("Unsupported Atlantic daily electricity category/day")
        self._category = category
        self._offset = offset
        role = "CO" if category == 1 else "CWU"
        day_name = "dzisiaj" if offset == 0 else "wczoraj"
        suffix = "today" if offset == 0 else "yesterday"
        role_id = "co" if category == 1 else "cwu"
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_energy_daily_{role_id}_{suffix}"
        self._attr_name = f"Energia elektryczna {role} · {day_name} (UTC)"
        self._attr_icon = "mdi:radiator" if category == 1 else "mdi:water-boiler"
        if offset == 0:
            # Cloud may revise the current UTC day's amount up or down.
            # TOTAL with last_reset at UTC midnight prevents false negative
            # consumption when the day rolls over.
            self._attr_state_class = SensorStateClass.TOTAL

    @property
    def _day(self) -> str:
        return (datetime.now(UTC).date() - timedelta(days=self._offset)).isoformat()

    @property
    def _values(self) -> dict[str, float]:
        return getattr(self.coordinator, "atlantic_daily_energy", {}).get(
            self._category, {}
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and getattr(self.coordinator, "atlantic_consumptions", {}).get("state")
            == "dostepna"
            and self._day in self._values
        )

    @property
    def native_value(self):
        return self._values.get(self._day) if self.available else None

    @property
    def last_reset(self):
        # For TOTAL today's sensor only, never for a historical snapshot.
        if self._offset != 0 or not self.available:
            return None
        return datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)

    @property
    def extra_state_attributes(self):
        today = datetime.now(UTC).date().isoformat()
        history = [
            {"dzien_utc": day, "kwh": kwh}
            for day, kwh in sorted(self._values.items())
            if day <= today
        ][-7:]
        result = {
            "dzien_utc": self._day,
            "kategoria_api": self._category,
            "typ_api": 1,
            "jednostka_api": 1,
            "okres": "dzien_utc",
            "mapowanie": "co_cwu_potwierdzone_na_podobnej_pompie_do_walidacji_lokalnej",
        }
        # Seven days of local history are a display aid, NOT historical
        # recorder/statistics backfill. Do not use it for an Energy sum.
        if self._offset == 0:
            result["historia_ostatnich_7_dni_utc"] = history
        return result


class AtlanticHydraulicCopSensor(CoordinatorEntity, SensorEntity):
    """Experimental hydraulic estimate, NEVER a verified COP or energy meter."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    LABELS = {
        "cop": ("COP Atlantic · szacunkowy", None),
        "live_cop": ("COP Atlantic · aktualna próbka (chwilowy)", None),
        "last_cop": ("COP Atlantic · ostatni zaakceptowany (historyczny)", None),
        "last_cop_co": ("COP Atlantic · ostatni zaakceptowany CO", None),
        "last_cop_cwu": ("COP Atlantic · ostatni zaakceptowany CWU", None),
        "cumulative_total": ("COP Atlantic · skumulowany (zaakceptowane próbki)", None),
        "cumulative_co": ("COP Atlantic · skumulowany CO (zaakceptowane próbki)", None),
        "cumulative_cwu": ("COP Atlantic · skumulowany CWU (zaakceptowane próbki)", None),
        "thermal_kw": ("Moc cieplna Atlantic · szacunkowa", "kW"),
        "electrical_kw": ("Moc elektryczna Atlantic · szacunkowa", "kW"),
        "status": ("COP Atlantic · status obliczeń", None),
    }

    def __init__(self, coordinator, entry_id: str, metric: str) -> None:
        super().__init__(coordinator)
        if metric not in self.LABELS:
            raise ValueError("Unsupported hydraulic metric")
        self._metric = metric
        self._attr_name, self._attr_native_unit_of_measurement = self.LABELS[metric]
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_hydraulic_{metric}"
        # Deliberately no state_class: no HA long-term/energy statistics.

    def _cumulative_summary(self) -> dict | None:
        bucket = {
            "cumulative_total": "total",
            "cumulative_co": "CO",
            "cumulative_cwu": "CWU",
        }.get(self._metric)
        if bucket is None:
            return None
        return self.coordinator.atlantic_hydraulic_cop.accumulator.snapshot()[bucket]

    @property
    def available(self):
        # Historical accepted intervals remain usable during a transient
        # Atlantic cloud failure; do not erase them with coordinator.available.
        if self._metric.startswith("cumulative_") or self._metric in (
            "cop", "last_cop", "last_cop_co", "last_cop_cwu"
        ):
            # Last accepted value is historical, not the most recent cloud
            # sample: it must survive polls with zero energy AND outages.
            return True
        return super().available

    @property
    def native_value(self):
        summary = self._cumulative_summary()
        if summary is not None:
            return summary["cop"]
        if not self.coordinator.last_update_success and self._metric not in (
            "cop", "last_cop", "last_cop_co", "last_cop_cwu"
        ):
            return None
        return self.coordinator.atlantic_hydraulic_cop.metrics.get(self._metric)

    @property
    def extra_state_attributes(self):
        summary = self._cumulative_summary()
        if summary is not None:
            return {
                "zaakceptowane_przedzialy": summary["intervals"],
                "pokryty_czas_h": summary["covered_hours"],
                "energia_cieplna_szac_kwh": summary["heat_kwh"],
                "energia_elektryczna_szac_kwh": summary["electric_kwh"],
                "zakres": summary["coverage"],
                "licznik_lokalny_ha": True,
                "cop_potwierdzony": False,
                "metoda": "suma_szac_ciepla_kwh_przez_sume_szac_pradu_kwh",
                "ograniczenie": "nie_jest_sezonowym_cop_pompy_ani_pelnym_czasem_pracy",
            }
        metrics = self.coordinator.atlantic_hydraulic_cop.metrics
        cop_monitor = self.coordinator.atlantic_hydraulic_cop
        if self._metric in ("last_cop_co", "last_cop_cwu"):
            last = cop_monitor.last_cops.latest(
                "CO" if self._metric == "last_cop_co" else "CWU"
            )
        else:
            last = cop_monitor.last_cops.latest()
        last_at = None
        age_hours = None
        if last is not None:
            last_at = last["at"]
            try:
                seconds = (datetime.now(UTC) - datetime.fromisoformat(last_at)).total_seconds()
                if seconds >= 0:
                    age_hours = round(seconds / 3600, 2)
            except (TypeError, ValueError, OverflowError):
                pass
        is_last_sample = self._metric in (
            "cop", "last_cop", "last_cop_co", "last_cop_cwu"
        )
        return {
            "cop_ostatni_zapisany_historyczny": is_last_sample,
            "zrodlo_wyswietlanego_cop": metrics.get("cop_display_source"),
            "zastepczy_cop_skumulowany": metrics.get("cop_uses_cumulative_fallback") is True,
            "obieg_wyswietlanego_cop": metrics.get("cop_display_circuit"),
            "uwaga_daty": (
                "Brak daty pojedynczego wyniku z poprzedniej wersji; wartość skumulowana"
                if self._metric == "cop" and metrics.get("cop_uses_cumulative_fallback")
                else None
            ),
            "cop_pochodzi_z_biezacej_probki": (
                self._metric == "live_cop" and metrics.get("live_cop") is not None
            ),
            "ostatni_zaakceptowany_cop_utc": last_at,
            "wiek_ostatniego_wyniku_h": age_hours,
            "ostatni_zaakceptowany_obieg": last["circuit"] if last else None,
            "ostatni_zaakceptowany_poziom_pewnosci": last["quality"] if last else None,
            "ostatni_zaakceptowany_typ_okna": last["source"] if last else None,
            "ostatni_wynik_nie_jest_aktualnym_cop": is_last_sample,
            "aktywny_obieg": metrics.get("circuit"),
            "topologia_zrodel": metrics.get("topology"),
            "wiek_probek_s": metrics.get("source_ages_seconds"),
            "rozbieznosc_znacznikow_temperatur_s": metrics.get(
                "last_change_skew_temperatures_seconds"
            ),
            "semantyka_znacznikow": metrics.get(
                "hydraulic_observation_evidence"
            ),
            "wiarygodnosc_temperatur": metrics.get("temperature_evidence"),
            "pewnosc_szacunku": metrics.get("confidence"),
            "roznica_temperatur_k": metrics.get("delta_t_k"),
            "diagnostyka_grzalek": metrics.get("heater_evidence"),
            "metoda_probkowania": metrics.get("observation_method"),
            "skala_pradu_nadal_do_weryfikacji": metrics.get("counter_scale"),
            "diagnostyka_licznika_pradu": metrics.get("electric_meter_diagnostics"),
            "diagnostyka_okna_energii": metrics.get("electric_window_diagnostics"),
            "ostatni_poprawny_szacunek_utc": metrics.get("last_cop_at"),
            "algorytm_eksperymentalny": True,
            "status_walidacji": metrics.get("status"),
            "metoda": "snapshot_ha_przeplyw_delta_t_przyrost_pradu",
            "potwierdzony_pomiar_cop": False,
            "do_rozliczen_energii": False,
        }


class AtlanticApiDiscoverySensor(CoordinatorEntity, SensorEntity):
    """Local bounded numeric research evidence; no device identifiers or secrets."""
    _attr_has_entity_name = True
    _attr_name = "Atlantic · badanie źródeł API"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:flask-outline"

    def __init__(self, coordinator, entry_id):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_api_discovery"

    @property
    def native_value(self):
        return getattr(self.coordinator, "atlantic_api_discovery", {}).get("state", "wylaczone")

    @property
    def extra_state_attributes(self):
        return getattr(self.coordinator, "atlantic_api_discovery", {})
