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

    def test_energy_support_mask_distinguishes_electricity_and_heat(self):
        devices = [{
            "reported_capability_ids": [164],
            "values": {164: 2 + 16 + 256 + 1024},
        }]
        result = module.energy_capabilities_summary(devices)
        self.assertEqual(result, {
            "status": "odczytany",
            "prad_co": True, "prad_cwu": True,
            "produkcja_ciepla_co": True, "produkcja_ciepla_cwu": True,
        })
        self.assertEqual(module.energy_capabilities_summary([])["status"], "niezgloszony")
        self.assertEqual(module.energy_capabilities_summary([{
            "reported_capability_ids": [164], "values": {164: None},
        }])["status"], "nieczytelny")


if __name__ == "__main__":
    unittest.main()
