# Katalog identyfikatorów raportowanych przez Atlantic (diagnostyka v0.3.0)

> Słownik statyczny na podstawie numerycznych ID udostępnionych przez właściciela pompy. **Nie zawiera** wartości pomiarów, device ID, nazwy użytkownika, tokenów, hasła ani numerów seryjnych.

Źródło mapowania: [publiczna tabela Cozytouch](https://github.com/gduteil/cozytouch/blob/main/custom_components/cozytouch/capability_table.py). Nazwy i typy to deklaracje interoperacyjności, nie gwarancja zgodności z każdą serią Atlantic. Te metadane nie uprawniają do wysyłania poleceń sterujących.

W raporcie jest **191 wystąpień** identyfikatorów na 5 urządzeniach logicznych, **183 różnych ID**, z których **182 ma wpis** we wskazanej tabeli, a **1 nie ma**. Raport wskazuje **brak** standardowych ID sprężarki `24`, `27`, `51`, `72`.

## Priorytety weryfikacji

| ID | Obszar | Następny bezpieczny krok |
|---|---|---|
| 57, 59, 60 | Liczniki energii | Odczyty surowe; porównanie skali, przyrostów i resetów przed dodaniem kWh/statystyk |
| 91 | Aktywny obieg | Potwierdzenie zmiany CO / CWU podczas naturalnej pracy urządzenia |
| 112 | Przepływ obiegu | Walidacja jednostki, obiegu i sensora; bez przypisywania L/min przed kontrolą |
| 153, 181 | Stan ogrzewania / usługa | Tylko monitoring; żaden z nich nie dowodzi pracy sprężarki |
| 49, 50, 90 | Generator: płomień, modulacja, starty palnika CWU | Nie interpretować jako sprężarki; potrzebna weryfikacja znaczenia w pompie ciepła |
| 335, 94 | Numer seryjny / numer produktu | Nie ujawniać wartości w zwykłych sensorach ani raporcie diagnostycznym |
| 8 | Bez wpisu | Potrzebne informacje o typie/modelu i bezpiecznie zredagowane metadane; bez zgadywania |

**Klasy `SWITCH`, `SELECT`, `CLIMATE` i podobne w tabeli źródłowej nie oznaczają, że integracja ma je wdrażać jako sterowanie.** Nasz produkt pozostaje tylko do odczytu.

## Pełny katalog według indeksu urządzenia

### Urządzenie 1 (52 identyfikatorów)

| ID | Nazwa źródłowa | Typ źródłowy |
|---:|---|---|
| 109 | `boiler_water_temperature` | `TEMPERATURE` |
| 119 | `outside_temperature` | `TEMPERATURE` |
| 150 | `home_error_code` | `ERROR_CODE` |
| 180 | `outdoor_unit_error_code` | `STRING` |
| 8 | **Brak w tabeli** | — |
| 9 | `extra_heating_power_z2` | `POWER` |
| 11 | `extra_dhw_power` | `POWER` |
| 21 | `emergency_mode` | `STRING` |
| 23 | `dhw_comfort_setpoint` | `TEMPERATURE` |
| 39 | `dhw_eco_setpoint` | `TEMPERATURE` |
| 57 | `power_consumption` | `ENERGY` |
| 59 | `power_consumption` | `ENERGY` |
| 60 | `total_electricity_consumption` | `ENERGY` |
| 88 | `model_name` | `STRING` |
| 91 | `active_circuit` | `STRING` |
| 93 | `zones_count` | `STRING` |
| 94 | `product_number` | `STRING` |
| 106 | `nominal_heating_power` | `POWER` |
| 112 | `circulator_flow_rate` | `FLOW_RATE` |
| 120 | `product_type` | `STRING` |
| 152 | `away_mode` | `AWAY_MODE_SWITCH` |
| 164 | `energy_consumption_supported` | `STRING` |
| 171 | `away_mode_cooling_temperature` | `TEMPERATURE` |
| 172 | `away_mode_temperature` | `TEMPERATURE_ADJUSTMENT_NUMBER` |
| 179 | `wifi_signal` | `SIGNAL` |
| 182 | `home_active_errors` | `INT` |
| 188 | `home_services` | `STRING` |
| 218 | `connectivity_diagnosis` | `STRING` |
| 222 | `away_mode` | `AWAY_MODE_TIMESTAMPS` |
| 315 | `timezone` | `TIMEZONE` |
| 328 | `main_error_code` | `INT` |
| 329 | `min_schedule_ranges_per_day` | `STRING` |
| 334 | `main_error_code_display` | `INT` |
| 335 | `serial_number` | `STRING` |
| 342 | `dhw_setpoint_without_override_sif` | `TEMPERATURE` |
| 345 | `boiler_error_code` | `INT` |
| 346 | `dhw_minimum_weekly_slots` | `INT` |
| 349 | `dhw_maximum_weekly_slots` | `INT` |
| 351 | `connectivity_display_capabilities` | `STRING` |
| 370 | `hub_movable_subproducts` | `BINARY` |
| 380 | `outdoor_unit_error_code_cesa` | `INT` |
| 381 | `ble_pairing_compatibility` | `BINARY` |
| 100636 | `dhw_mode_b2b` | `STRING` |
| 101302 | `outside_temperature_available` | `BINARY` |
| 107060 | `generator_external_input_1_function` | `STRING` |
| 107078 | `boiler_switch_type` | `STRING` |
| 107079 | `cop_threshold` | `STRING` |
| 107083 | `backup_heater_type` | `STRING` |
| 107451 | `peak_electricity_price` | `INT` |
| 107452 | `off_peak_electricity_price` | `INT` |
| 107453 | `gas_price` | `INT` |
| 207451 | `base_electricity_price` | `INT` |

### Urządzenie 2 (4 identyfikatorów)

| ID | Nazwa źródłowa | Typ źródłowy |
|---:|---|---|
| 109 | `boiler_water_temperature` | `TEMPERATURE` |
| 19 | `temperature_setpoint` | `TEMPERATURE` |
| 218 | `connectivity_diagnosis` | `STRING` |
| 106000 | `circuit_driven_by_room` | `BINARY` |

### Urządzenie 3 (78 identyfikatorów)

| ID | Nazwa źródłowa | Typ źródłowy |
|---:|---|---|
| 117 | `thermostat_temperature_z1` | `TEMPERATURE` |
| 7 | `air_conditioner` | `CLIMATE` |
| 17 | `control_setpoint` | `TEMPERATURE` |
| 40 | `target_temperature` | `TEMPERATURE_ADJUSTMENT_NUMBER` |
| 73 | `available_thermostat_modes` | `STRING` |
| 75 | `ambient_compensation_z1` | `PERCENTAGE` |
| 153 | `heating_status` | `STRING` |
| 154 | `zone_1` | `STRING` |
| 157 | `override_setpoint_activation` | `BINARY` |
| 158 | `override_total_time_z1` | `DURATION_SELECT` |
| 159 | `override_remain_time_z1` | `TIME` |
| 160 | `temperature_adjustment_min` | `TEMPERATURE` |
| 161 | `temperature_adjustment_max` | `TEMPERATURE` |
| 162 | `cooling_temperature_min` | `TEMPERATURE` |
| 163 | `cooling_temperature_max` | `TEMPERATURE` |
| 166 | `system_operating_mode` | `STRING` |
| 177 | `target_cool_temperature` | `TEMPERATURE_ADJUSTMENT_NUMBER` |
| 181 | `service_in_progress` | `STRING` |
| 184 | `prog_mode` | `SWITCH` |
| 192 | `flow_temperature_at_minus_ten` | `TEMPERATURE` |
| 193 | `flow_temperature_at_twenty` | `TEMPERATURE` |
| 194 | `cooling_flow_temperature_at_thirty_five` | `TEMPERATURE` |
| 195 | `cooling_flow_temperature_at_twenty_five` | `TEMPERATURE` |
| 217 | `system_setpoint_mode` | `STRING` |
| 218 | `connectivity_diagnosis` | `STRING` |
| 294 | `target_temperature_step` | `STRING` |
| 295 | `schedule_time_step` | `STRING` |
| 296 | `schedule_minimum_interval` | `TIME` |
| 303 | `error_code` | `ERROR_CODE` |
| 306 | `max_schedule_slots_per_day` | `STRING` |
| 341 | `auto_mode_running_state` | `STRING` |
| 347 | `daily_schedule_transitions` | `INT` |
| 348 | `weekly_schedule_transitions` | `INT` |
| 350 | `air_circulation_supported_speeds` | `STRING` |
| 352 | `absence_day_heating_temperature` | `TEMPERATURE` |
| 353 | `presence_day_heating_temperature` | `TEMPERATURE` |
| 354 | `presence_night_heating_temperature` | `TEMPERATURE` |
| 355 | `absence_day_cooling_temperature` | `TEMPERATURE` |
| 356 | `presence_day_cooling_temperature` | `TEMPERATURE` |
| 357 | `presence_night_cooling_temperature` | `TEMPERATURE` |
| 358 | `thermal_ambiance_scope` | `STRING` |
| 361 | `boost_duration_step` | `TIME` |
| 362 | `boost_duration_min` | `TIME` |
| 100000 | `thermal_zones_count` | `STRING` |
| 100002 | `ventilation_options_supported` | `STRING` |
| 100004 | `ventilation_controls_available` | `STRING` |
| 100010 | `hydraulic_heater_type` | `STRING` |
| 100013 | `available_schedule_types` | `STRING` |
| 100021 | `ventilation_controls_supported` | `STRING` |
| 100022 | `supported_system_operating_modes` | `STRING` |
| 100023 | `supported_system_modes` | `STRING` |
| 100100 | `requested_thermal_comfort` | `STRING` |
| 100260 | `away_mode` | `AWAY_MODE_TIMESTAMPS` |
| 100300 | `schedule_start_day` | `STRING` |
| 100301 | `max_schedule_slots_per_week` | `STRING` |
| 100320 | `prog_heat_monday` | `PROG` |
| 100321 | `prog_heat_tuesday` | `PROG` |
| 100322 | `prog_heat_wednesday` | `PROG` |
| 100323 | `prog_heat_thursday` | `PROG` |
| 100324 | `prog_heat_friday` | `PROG` |
| 100325 | `prog_heat_saturday` | `PROG` |
| 100326 | `prog_heat_sunday` | `PROG` |
| 100327 | `prog_cool_monday` | `PROG` |
| 100328 | `prog_cool_tuesday` | `PROG` |
| 100329 | `prog_cool_wednesday` | `PROG` |
| 100330 | `prog_cool_thursday` | `PROG` |
| 100331 | `prog_cool_friday` | `PROG` |
| 100332 | `prog_cool_saturday` | `PROG` |
| 100333 | `prog_cool_sunday` | `PROG` |
| 100450 | `schedule_anticipation` | `SWITCH` |
| 100600 | `flow_control_heat` | `STRING` |
| 100601 | `flow_control_cool` | `STRING` |
| 100607 | `ambient_compensation_cool` | `PERCENTAGE` |
| 103014 | `room_type` | `INT` |
| 103034 | `room_controls_capabilities` | `STRING` |
| 103150 | `ambient_temperature_available` | `BINARY` |
| 103626 | `flow_temperature_offset_heat` | `TEMPERATURE` |
| 103627 | `flow_temperature_offset_cool` | `TEMPERATURE` |

### Urządzenie 4 (44 identyfikatorów)

| ID | Nazwa źródłowa | Typ źródłowy |
|---:|---|---|
| 111 | `dhw_temperature` | `TEMPERATURE` |
| 15 | `dhw_service_type` | `STRING` |
| 22 | `target_temperature_dhw` | `TEMPERATURE_ADJUSTMENT_NUMBER` |
| 23 | `dhw_comfort_setpoint` | `TEMPERATURE` |
| 86 | `domestic_hot_water` | `SWITCH` |
| 87 | `domestic_hot_water_mode` | `SELECT` |
| 99 | `dhw_pump` | `BINARY` |
| 165 | `domestic_hot_water_boost` | `SWITCH` |
| 168 | `available_dhw_modes` | `STRING` |
| 210 | `dhw_comfort_schedule_monday` | `STRING` |
| 211 | `dhw_comfort_schedule_tuesday` | `STRING` |
| 212 | `dhw_comfort_schedule_wednesday` | `STRING` |
| 213 | `dhw_comfort_schedule_thursday` | `STRING` |
| 214 | `dhw_comfort_schedule_friday` | `STRING` |
| 215 | `dhw_comfort_schedule_saturday` | `STRING` |
| 216 | `dhw_comfort_schedule_sunday` | `STRING` |
| 218 | `connectivity_diagnosis` | `STRING` |
| 223 | `dhw_system_operating_mode` | `STRING` |
| 224 | `dhw_estimation_supported` | `STRING` |
| 226 | `away_mode` | `AWAY_MODE_TIMESTAMPS` |
| 231 | `target_temperature` | `TEMPERATURE_ADJUSTMENT_NUMBER` |
| 244 | `max_schedule_ranges_per_day` | `STRING` |
| 252 | `target_temperature_max` | `TEMPERATURE` |
| 253 | `target_temperature_min` | `TEMPERATURE` |
| 284 | `dhw_sg_level_status` | `STRING` |
| 310 | `dhw_thermal_generator_capabilities` | `STRING` |
| 311 | `dhw_smart_grid_request_capabilities` | `STRING` |
| 312 | `dhw_current_control_target` | `TEMPERATURE` |
| 329 | `min_schedule_ranges_per_day` | `STRING` |
| 330 | `schedule_range_step` | `STRING` |
| 331 | `schedule_range_max_duration` | `TIME` |
| 332 | `schedule_range_min_duration` | `TIME` |
| 333 | `heating_period_max_duration` | `TIME` |
| 336 | `dhw_panel_capabilities` | `STRING` |
| 337 | `main_cursor_information` | `STRING` |
| 338 | `secondary_cursor_information` | `STRING` |
| 339 | `dhw_panel_data` | `STRING` |
| 340 | `water_setpoint_step` | `STRING` |
| 105011 | `supported_dhw_modes` | `STRING` |
| 105012 | `supported_dhw_system_operating_modes` | `STRING` |
| 105300 | `water_temperature_limit` | `TEMPERATURE` |
| 105301 | `dhw_lowest_water_setpoint` | `TEMPERATURE` |
| 105636 | `dhw_comfort_mode` | `STRING` |
| 105906 | `v40_applied_setpoint` | `TEMPERATURE_PERCENT_ADJUSTMENT_NUMBER` |

### Urządzenie 5 (13 identyfikatorów)

| ID | Nazwa źródłowa | Typ źródłowy |
|---:|---|---|
| 6 | `generator_error_code` | `INT` |
| 25 | `number_of_starts_ch_pump` | `INT` |
| 26 | `number_of_starts_dhw_pump` | `INT` |
| 28 | `number_of_hours_ch_pump` | `INT` |
| 29 | `number_of_hours_dhw_pump` | `INT` |
| 100 | `water_pressure` | `PRESSURE` |
| 109 | `boiler_water_temperature` | `TEMPERATURE` |
| 49 | `generator_flame_status` | `BINARY` |
| 50 | `generator_modulation_level` | `PERCENTAGE` |
| 90 | `generator_dhw_burner_starts` | `INT` |
| 116 | `exhaust_temperature` | `TEMPERATURE` |
| 218 | `connectivity_diagnosis` | `STRING` |
| 299 | `heat_cool_switch_type` | `STRING` |

## Ograniczenia i walidacja

- Lista potwierdza, **jakie identyfikatory urządzenie zgłasza**, a nie ich rzeczywiste wartości lub pomiarową poprawność.
- Liczniki energii mogą mieć różne znaczenie w różnych typach urządzeń; bez par pomiarów w czasie nie nadamy kWh ani `state_class: total_increasing`.
- Parametry konfiguracji i harmonogramów są pomijane jako kontrolki; nawet jeśli tabela nazywa je `SELECT`, `SWITCH` lub `CLIMATE`, nie tworzymy encji zapisu.
- Traktujemy dane identyfikujące urządzenie jako wrażliwe: nazwy kont, numery seryjne, identyfikatory urządzeń i tokeny nie mogą pojawić się w eksportach ani dziennikach.
- Do dalszej identyfikacji jednostek wystarczą wybrane wartości z diagnostycznych sensorów, nigdy pełna surowa odpowiedź API.
