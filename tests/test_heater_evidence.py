"""Privacy-safe interpretations for Atlantic raw heater IDs."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components/atlantic_cozytouch/heater_evidence.py"
spec = importlib.util.spec_from_file_location("offline_heater_evidence", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def device(values, ids=None):
    if ids is None:
        ids = list(values.keys())
    return {"id": "DO_NOT_LEAK", "reported_capability_ids": ids, "values": values}


class HeaterEvidenceTest(unittest.TestCase):
    def test_3000_raw_is_scale_ambiguity_not_factual_on_or_off(self):
        actual = mod.assess_heaters([device({8: 3000.0, 64: False})])
        self.assertIsNone(actual["block_reason"])
        self.assertTrue(actual["uncertain"])
        self.assertFalse(actual["heater_off_confirmed"])
        self.assertEqual(actual["power_id_states"]["8"],
                         "poza_zakresem_katalogu_skala_nieznana")
        self.assertNotIn("DO_NOT_LEAK", str(actual))
        self.assertNotIn("3000", str(actual))

    def test_true_dhw_heater_blocks_regardless_of_invalid_power_scale(self):
        actual = mod.assess_heaters([device({8: 3000.0, 64: True})])
        self.assertEqual(actual["block_reason"],
                         "grzalka_cwu_aktywna_niepelny_bilans_pradu")

    def test_in_range_positive_power_blocks_conservatively(self):
        actual = mod.assess_heaters([device({8: 3.0, 64: False})])
        self.assertEqual(actual["block_reason"],
                         "grzalka_wspomagajaca_moc_dodatnia_w_zakresie_katalogu")
        self.assertFalse(actual["uncertain"])

    def test_zeros_do_not_prove_all_backup_heaters_off(self):
        actual = mod.assess_heaters([device({8: 0.0, 9: 0.0})])
        self.assertIsNone(actual["block_reason"])
        self.assertEqual(actual["power_id_states"]["11"], "niedostepny")
        self.assertFalse(actual["heater_off_confirmed"])

    def test_invalid_power_does_not_create_false_active(self):
        for value in (True, "3000", -5, float("nan"), float("inf")):
            with self.subTest(value=str(value)):
                actual = mod.assess_heaters([device({8: value})])
                self.assertIsNone(actual["block_reason"])
                self.assertTrue(actual["uncertain"])
                self.assertEqual(actual["power_id_states"]["8"],
                                 "nieprawidlowy_odczyt")

    def test_unreported_raw_is_not_interpreted(self):
        actual = mod.assess_heaters([device({8: 3000}, ids=[91])])
        self.assertEqual(actual["power_id_states"]["8"], "niedostepny")
        self.assertIsNone(actual["block_reason"])


if __name__ == "__main__":
    unittest.main()
