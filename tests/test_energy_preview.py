"""Evidence gates for raw Atlantic electricity and COP diagnostics (offline)."""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "atlantic_cozytouch" / "energy_preview.py"
spec = importlib.util.spec_from_file_location("atlantic_energy_preview_test", SOURCE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestEnergyPreview(unittest.TestCase):
    def setUp(self):
        self.device = {
            "id": "do_not_export",
            "reported_capability_ids": [57, 59, 164],
            "values": {57: 11629.0, 59: 7522.0, 164: 1298.0},
        }

    def test_only_preview_from_actual_reported_candidates(self):
        self.assertEqual(module.candidate_kwh(self.device, 57), 11.629)
        self.assertEqual(module.candidate_kwh(self.device, 59), 7.522)
        self.assertIsNone(module.candidate_kwh(self.device, 60))
        self.assertIsNone(module.candidate_kwh(self.device, 164))
        self.assertTrue(module.candidate_summary(self.device, 57)["pomiar_elektryczny_deklarowany_przez_id164"])
        self.assertTrue(module.candidate_summary(self.device, 59)["pomiar_elektryczny_deklarowany_przez_id164"])
        self.assertFalse(module.candidate_summary(self.device, 57)["przypisanie_i_skala_zweryfikowane"])
        self.assertNotIn("do_not_export", str(module.candidate_summary(self.device, 57)))

    def test_zero_is_not_missing_and_unavailable_is_not_zero(self):
        dev = {"reported_capability_ids": [57], "values": {57: 0}}
        self.assertEqual(module.candidate_kwh(dev, 57), 0.0)
        for value in (None, "11", -1, False, float("inf"), float("nan"), 10**12):
            dev["values"][57] = value
            self.assertIsNone(module.candidate_kwh(dev, 57))
        dev["values"][57] = 500
        dev["reported_capability_ids"] = []
        self.assertIsNone(module.candidate_kwh(dev, 57))

    def test_invalid_capability_masks_cannot_crash(self):
        for value in ("bad", None, True, -1, float("nan"), 10**1000):
            dev = dict(self.device)
            dev["values"] = dict(self.device["values"], **{164: value})
            self.assertIsNone(module.candidate_summary(dev, 57)["pomiar_elektryczny_deklarowany_przez_id164"])

    def test_cop_readiness_fails_closed_if_no_thermal_records(self):
        self.assertEqual(module.cop_readiness({"state": "dostepna", "okresy_z_energia_wyprodukowana": 0}), "brak_danych_energii_cieplnej")
        self.assertEqual(module.cop_readiness({"state": "dostepna", "okresy_z_energia_wyprodukowana": 1}), "produkcja_zero_lub_brak_danych")
        self.assertEqual(module.cop_readiness({"state": "dostepna", "okresy_z_dodatnia_produkcja": 1}), "produkcja_do_weryfikacji")
        self.assertEqual(module.cop_readiness({"state": "brak_endpointu"}), "historia_niedostepna")
        self.assertEqual(module.cop_readiness(None), "brak_danych_historii")

    def test_theoretical_formula_never_fills_missing_heat(self):
        self.assertEqual(module.cop_formula(26, 10), 2.6)
        self.assertEqual(module.cop_formula(0, 10), 0.0)
        for thermal, electric in ((None, 10), (20, None), (26, 0), (26, -1),
                                  (-3, 2), ("20", 5), (float("nan"), 10)):
            self.assertIsNone(module.cop_formula(thermal, electric))

    def test_ha_preview_has_no_statistics_or_energy_device_class(self):
        source = (ROOT / "custom_components" / "atlantic_cozytouch" / "sensor.py").read_text(encoding="utf-8")
        module_ast = ast.parse(source)
        klass = next(item for item in module_ast.body if isinstance(item, ast.ClassDef) and item.name == "AtlanticEnergyPreviewSensor")
        fragment = ast.get_source_segment(source, klass)
        self.assertNotIn("SensorStateClass.", fragment)
        self.assertNotIn("SensorDeviceClass.ENERGY", fragment)
        self.assertNotIn("_attr_state_class =", fragment)
        self.assertIn("EntityCategory.DIAGNOSTIC", fragment)


if __name__ == "__main__":
    unittest.main()
