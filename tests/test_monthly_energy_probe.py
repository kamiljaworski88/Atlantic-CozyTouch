"""Offline tests for the monthly heat-production source audit."""
import importlib.util
from pathlib import Path
import sys
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/atlantic_cozytouch/monthly_energy_probe.py"
spec = importlib.util.spec_from_file_location("test_monthly_probe_pure", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestMonthlyEnergy(unittest.TestCase):
    def test_monthly_production_does_not_pretend_thermal_heat(self):
        data = [{
            "type": 1, "unit": 1, "category": 1,
            "serialNumber": "PRIVATE_SERIAL_DO_NOT_EXPORT",
            "consumptionPeriods": [{
                "date": "PRIVATE_DATE", "cost": 99999.123,
                "consumedQuantity": 12.4, "producedQuantity": 45.9,
            }],
        }]
        out = module.monthly_energy_shape(data)
        self.assertEqual(out["state"], "dostepna")
        self.assertEqual(out["okresy_z_dodatnia_produkcja"], 1)
        self.assertFalse(out["energia_cieplna_zweryfikowana"])
        self.assertFalse(out["cop_miesieczny_zweryfikowany"])
        for secret in ("PRIVATE_SERIAL", "PRIVATE_DATE", "99999", "45.9", "12.4"):
            self.assertNotIn(secret, str(out))

    def test_empty_missing_and_incorrect_responses(self):
        self.assertEqual(module.monthly_energy_shape([])["state"], "brak_serii")
        for response in ({}, None, [None], [{"consumptionPeriods": "bad"}]):
            self.assertEqual(module.monthly_energy_shape(response)["state"], "nieprawidlowa_odpowiedz")
        self.assertEqual(module.monthly_energy_shape([{"consumptionPeriods": []}] * 129)["state"], "nieprawidlowa_odpowiedz")
        self.assertEqual(module.monthly_energy_shape([{"consumptionPeriods": [{}] * 241}])["state"], "nieprawidlowa_odpowiedz")

    def test_bool_nan_strings_are_not_production(self):
        out = module.monthly_energy_shape([{
            "category": 2, "type": 1, "unit": 1,
            "consumptionPeriods": [
                {"producedQuantity": True},
                {"producedQuantity": "SECRET"},
                {"producedQuantity": float("nan")},
                {"producedQuantity": 0},
                {"producedQuantity": -2},
            ],
        }])
        self.assertEqual(out["okresy_z_liczbowa_produkcja"], 1)
        self.assertEqual(out["okresy_z_dodatnia_produkcja"], 0)

    def test_series_details_are_bounded(self):
        out = module.monthly_energy_shape([{"type": 1, "unit": 1, "consumptionPeriods": []}] * 15)
        self.assertEqual(len(out["serie"]), 12)
        self.assertEqual(out["serie_pominiete"], 3)


if __name__ == "__main__":
    unittest.main()
