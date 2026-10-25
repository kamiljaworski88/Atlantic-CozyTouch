"""Offline privacy and schema tests for the optional cloud consumption probe."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

FILE = (Path(__file__).resolve().parents[1]
        / "custom_components" / "atlantic_cozytouch" / "consumption_probe.py")
spec = importlib.util.spec_from_file_location("atlantic_consumption_probe_test", FILE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestConsumptionProbe(unittest.TestCase):
    def test_setup_id_is_strictly_numeric_and_local_only(self):
        self.assertEqual(module.parse_setup_id([{"id": 456}]), 456)
        self.assertEqual(module.parse_setup_id([{"id": "456"}]), 456)
        for value in (-1, True, 1.5, "123/../../devices", "A12", "", None, 10**20):
            self.assertIsNone(module.parse_setup_id([{"id": value}]))
        self.assertIsNone(module.parse_setup_id({"id": 123}))
        self.assertIsNone(module.parse_setup_id([{"devices": []}]))

    def test_summarizes_only_shape_and_never_sensitive_numbers(self):
        fixture = [{
            "serialNumber": "PRIVATE_SERIAL_123",
            "deviceId": "PRIVATE_DEVICE_ID",
            "type": 1,
            "unit": 1,
            "consumptionPeriods": [{
                "date": 1788825600,
                "consumedQuantity": 123456.789,
                "producedQuantity": 456789.123,
            }],
        }]
        out = module.summarize_consumptions(fixture)
        self.assertEqual(out["state"], "dostepna")
        self.assertEqual(out["typy"], [1])
        self.assertEqual(out["jednostki"], [1])
        self.assertEqual(out["okresy_z_energia_pobrana"], 1)
        self.assertEqual(out["okresy_z_energia_wyprodukowana"], 1)
        self.assertTrue(out["mozliwy_pomiar_produkcji"])
        self.assertFalse(out["cop_zweryfikowany"])
        for secret in ("PRIVATE", "123456", "456789", "1788825600"):
            self.assertNotIn(secret, str(out))

    def test_null_production_is_not_counted_as_measured(self):
        out = module.summarize_consumptions([{
            "type": 1, "unit": 1, "consumptionPeriods": [
                {"consumedQuantity": 3.3, "producedQuantity": None},
            ],
        }])
        self.assertEqual(out["okresy_z_energia_wyprodukowana"], 0)
        self.assertFalse(out["mozliwy_pomiar_produkcji"])

    def test_malformed_and_excessive_payload_fails_closed(self):
        self.assertEqual(module.summarize_consumptions([])["state"], "brak_danych")
        for value in (None, {}, [17], [{"consumptionPeriods": "evil"}],
                      [{"consumptionPeriods": [{}] * 3661}], [{}] * 257):
            self.assertEqual(module.summarize_consumptions(value)["state"], "nieprawidlowa_odpowiedz")

    def test_two_series_are_not_assumed_to_be_co_and_cwu(self):
        from datetime import datetime, timezone
        day1 = 1726358400
        day2 = day1 + 86400
        payload = [
            {
                "category": 3, "type": 1, "unit": 1,
                "serialNumber": "PRIVATE_SERIAL_ABC",
                "deviceId": "PRIVATE_DEVICE_X",
                "consumptionPeriods": [
                    {"date": day1, "mode": 1, "profil": 0,
                     "consumedQuantity": 11.629, "producedQuantity": None,
                     "cost": 99999.99},
                    {"date": day1, "mode": 2, "profil": 0,
                     "consumedQuantity": 0.3, "producedQuantity": None},
                    {"date": day2, "mode": 1, "profil": 0,
                     "consumedQuantity": 1.0, "producedQuantity": None},
                ],
            },
            {
                "category": 7, "type": 1, "unit": 1,
                "deviceUrl": "PRIVATE_URL_X",
                "consumptionPeriods": [
                    {"date": day2, "mode": 2, "profil": 3,
                     "consumedQuantity": 7.522, "producedQuantity": None},
                ],
            },
        ]
        out = module.summarize_consumptions(payload)
        self.assertEqual(out["serie"], 2)
        self.assertEqual(out["okresy_z_energia_pobrana"], 4)
        self.assertEqual(out["okresy_z_energia_wyprodukowana"], 0)
        self.assertFalse(out["cop_zweryfikowany"])
        first, second = out["serie_szczegoly"]
        self.assertEqual(first["kategoria_kod"], 3)
        self.assertEqual(second["kategoria_kod"], 7)
        self.assertEqual(first["przypisanie_co_cwu"], "niepotwierdzone")
        self.assertEqual(second["przypisanie_co_cwu"], "niepotwierdzone")
        self.assertEqual(first["tryby_kody"], [1, 2])
        self.assertEqual(second["tryby_kody"], [2])
        self.assertEqual(first["liczba_dni_utc"], 2)  # Three tariff records, two days.
        self.assertEqual(second["liczba_dni_utc"], 1)
        self.assertEqual(
            first["data_od_utc"],
            datetime.fromtimestamp(day1, tz=timezone.utc).date().isoformat(),
        )
        self.assertEqual(
            first["data_do_utc"],
            datetime.fromtimestamp(day2, tz=timezone.utc).date().isoformat(),
        )
        self.assertEqual(first["jednostka_wg_znanego_przykladu"], "kWh")
        self.assertEqual(second["profile_kody"], [3])
        for secret in ("PRIVATE", "11.629", "7.522", "99999.99", str(day1)):
            self.assertNotIn(secret, str(out))

    def test_zero_production_does_not_prove_any_heat_output(self):
        out = module.summarize_consumptions([{
            "type": 1, "unit": 1,
            "consumptionPeriods": [
                {"producedQuantity": 0, "consumedQuantity": 1},
                {"producedQuantity": -20, "consumedQuantity": False},
                {"producedQuantity": "500", "consumedQuantity": "12"},
                {},
            ],
        }])
        self.assertEqual(out["okresy_z_energia_wyprodukowana"], 1)
        self.assertEqual(out["okresy_z_dodatnia_produkcja"], 0)
        self.assertEqual(
            out["serie_szczegoly"][0]["okresy_bez_liczbowej_produkcji"], 3
        )
        self.assertFalse(out["cop_zweryfikowany"])

    def test_untrusted_codes_dates_and_output_sizes_are_bounded(self):
        from datetime import datetime, timezone
        payload = [{
            "category": "PRIVATE_IDENTIFYING_CATEGORY",
            "type": "1;PRIVATE",
            "unit": 999999999,
            "serialNumber": "PRIVATE_SERIAL_X",
            "consumptionPeriods": [
                {"date": "2026-10-23", "mode": "PRIVATE_MODE", "profil": True,
                 "consumedQuantity": 99},
                {"date": 10**30, "mode": 50000, "profil": -1,
                 "consumedQuantity": 20},
            ],
        }]
        out = module.summarize_consumptions(payload)
        item = out["serie_szczegoly"][0]
        self.assertIsNone(item["kategoria_kod"])
        self.assertIsNone(item["typ_kod"])
        self.assertIsNone(item["jednostka_kod"])
        self.assertEqual(item["data_od_utc"], None)
        self.assertEqual(item["nieprawidlowe_daty"], 2)
        self.assertEqual(item["tryby_kody"], [])
        self.assertEqual(item["profile_kody"], [])
        self.assertNotIn("PRIVATE", str(out))
        many = module.summarize_consumptions([
            {"type": 1, "unit": 1, "consumptionPeriods": []} for _ in range(100)
        ])
        self.assertEqual(many["serie"], 100)
        self.assertEqual(len(many["serie_szczegoly"]), 12)
        self.assertEqual(many["serie_pominiete_w_szczegolach"], 88)
        from datetime import timedelta
        self.assertEqual(
            module._utc_day(int(datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp())),
            "2026-10-23",
        )

    def test_energy_support_mask_distinguishes_electricity_and_heat(self):
        devices = [{
            "reported_capability_ids": [164],
            "values": {164: 2 + 16 + 256 + 1024},
        }]
        result = module.energy_capabilities_summary(devices)
        self.assertEqual(result, {
            "status": "odczytany",
            "prad_co": True, "prad_cwu": True,
            "produkcja_ciepla_co": None, "produkcja_ciepla_cwu": None,
            "niezdefiniowane_bity": 256 + 1024,
            "produkcja_ciepla_wg_katalogu": "brak_potwierdzonej_flagi",
        })
        self.assertEqual(module.energy_capabilities_summary([])["status"], "niezgloszony")
        self.assertEqual(module.energy_capabilities_summary([{
            "reported_capability_ids": [164], "values": {164: None},
        }])["status"], "nieczytelny")


if __name__ == "__main__":
    unittest.main()
