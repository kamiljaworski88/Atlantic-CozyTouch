"""Offline tests for privacy-safe, read-only Atlantic thermal source discovery."""
import importlib.util
from pathlib import Path
import sys
from datetime import datetime, timezone
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "custom_components/atlantic_cozytouch/heat_production_probe.py"
spec = importlib.util.spec_from_file_location("production_probe_test", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def month_ts(y, m, day=1):
    return int(datetime(y, m, day, tzinfo=timezone.utc).timestamp())


class TestHeatCandidates(unittest.TestCase):
    def test_october_co_cwu_candidates_are_not_mislabelled_as_heat(self):
        payload = [{
            "deviceId": "PRIVATE_DEVICE_ID", "serialNumber": "PRIVATE_SERIAL",
            "type": 1, "unit": 1, "category": 2,
            "consumptionPeriods": [{
                "date": month_ts(2026, 10), "mode": 2,
                "consumedQuantity": 26, "producedQuantity": 76,
                "cost": 88, "privateToken": "SECRET",
            }, {
                "date": month_ts(2026, 9), "mode": 1,
                "consumedQuantity": 10, "producedQuantity": 36,
            }],
        }]
        actual = mod.summarize_production_candidates(payload, "2026-10")
        self.assertEqual(actual["dodatnie_producedquantity"], 2)
        self.assertTrue(actual["kandydaci"][0]["produkcja_dodatnia"])
        self.assertTrue(actual["kandydaci"][0]["pobor_liczbowy"])
        self.assertEqual(actual["kandydaci"][0]["miesiac_utc"], "2026-10")
        self.assertEqual(actual["kandydaci"][1]["miesiac_utc"], "2026-09")
        self.assertEqual(actual["czy_to_cieplo"], "NIEZWERYFIKOWANE")
        self.assertFalse(actual["czy_dostepny_cop"])
        self.assertNotIn("PRIVATE_DEVICE_ID", str(actual))
        self.assertNotIn("PRIVATE_SERIAL", str(actual))
        self.assertNotIn("SECRET", str(actual))
        self.assertNotIn("76", str(actual))
        self.assertNotIn("36", str(actual))
        self.assertNotIn("PRIVATE_SERIAL", str(actual))
        self.assertNotIn("PRIVATE_DEVICE_ID", str(actual))

    def test_outside_date_and_missing_produced_quantity_remain_empty(self):
        actual = mod.summarize_production_candidates([{
            "type": 1, "unit": 1, "category": 2,
            "consumptionPeriods": [
                {"date": month_ts(2026, 10), "producedQuantity": None},
                {"date": month_ts(2026, 8), "producedQuantity": 76},
            ],
        }], "2026-10")
        self.assertEqual(actual["state"], "brak_dodatnich_producedquantity")
        self.assertEqual(actual["sprawdzone_okresy"], 1)
        self.assertEqual(actual["kandydaci"], [])

    def test_caps_output_count_and_no_secret_copy(self):
        payload = [{"type": 1, "unit": 1, "category": 2,
                    "consumptionPeriods": [{
                        "date": month_ts(2026, 10), "mode": 2,
                        "consumedQuantity": 5, "producedQuantity": 15,
                        "token": "private",
                    } for _ in range(200)]}]
        actual = mod.summarize_production_candidates(payload, "2026-10")
        self.assertEqual(len(actual["kandydaci"]), 24)
        self.assertEqual(actual["pominiete_kandydaty"], 176)
        self.assertNotIn("private", str(actual))

    def test_invalid_or_unbounded_vendor_payloads_fail_closed(self):
        for data in (None, {}, [None], [{"consumptionPeriods": None}],
                     [{"consumptionPeriods": [{}] * 3661}], [{}] * 129):
            self.assertEqual(mod.summarize_production_candidates(
                data, "2026-10"
            )["state"], "nieprawidlowy_format")
        for value in (True, float("nan"), float("inf"), -1, 1e15, "76"):
            self.assertEqual(mod.summarize_production_candidates([{
                "type": 1, "unit": 1, "category": 1,
                "consumptionPeriods": [{
                    "date": month_ts(2026, 10), "producedQuantity": value
                }],
            }], "2026-10")["dodatnie_producedquantity"], 0)

    def test_response_code_and_month_are_validated(self):
        self.assertEqual(
            mod.summarize_production_candidates([], "2026-99")["state"],
            "nieprawidlowy_miesiac"
        )
        self.assertEqual(mod.summarize_production_candidates([
            {"type": 1, "unit": 1, "category": 1,
             "consumptionPeriods": [
                 {"date": month_ts(2026, 10), "producedQuantity": 1,
                  "mode": "PRIVATE_VALUE"},
             ]}
        ], "2026-10")["kandydaci"][0]["tryb_kod"], None)


if __name__ == "__main__":
    unittest.main()
