"""Offline tests for safe, reproducible daily electricity semantics."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "atlantic_cozytouch"
PACKAGE_NAME = "daily_energy_test_pkg"
package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE)]
sys.modules[PACKAGE_NAME] = package

for name in ("consumption_probe", "energy_daily"):
    fq = f"{PACKAGE_NAME}.{name}"
    spec = importlib.util.spec_from_file_location(fq, PACKAGE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fq] = mod
    spec.loader.exec_module(mod)

from daily_energy_test_pkg.energy_daily import extract_electricity_days


def day_timestamp(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


class TestDailyElectricity(unittest.TestCase):
    def test_two_categories_and_daily_totals_with_tarrifs(self):
        day1 = day_timestamp(2026, 10, 22)
        day2 = day_timestamp(2026, 10, 23)
        payload = [
            {"category": 1, "type": 1, "unit": 1,
             "serialNumber": "PRIVATE_SN_123",
             "consumptionPeriods": [
                 {"date": day1, "mode": 0, "consumedQuantity": 1.025, "producedQuantity": None},
                 {"date": day2, "mode": 0, "consumedQuantity": 2.375, "producedQuantity": None},
             ]},
            {"category": 2, "type": 1, "unit": 1,
             "deviceId": "PRIVATE_ID_333",
             "consumptionPeriods": [
                 {"date": day1, "mode": 1, "consumedQuantity": 0.1, "cost": 999},
                 {"date": day1, "mode": 2, "consumedQuantity": 0.25, "cost": 888},
                 {"date": day2, "mode": 0, "consumedQuantity": 1.25},
             ]},
        ]
        result = extract_electricity_days(payload)
        self.assertEqual(result, {
            1: {"2026-10-22": 1.025, "2026-10-23": 2.375},
            2: {"2026-10-22": 0.35, "2026-10-23": 1.25},
        })
        for private in ("PRIVATE", "999", "888"):
            self.assertNotIn(private, str(result))

    def test_unknown_type_unit_categories_are_never_assumed(self):
        base = [{"category": 1, "type": 4, "unit": 1, "consumptionPeriods": []},
                {"category": 2, "type": 1, "unit": 2, "consumptionPeriods": []},
                {"category": 3, "type": 1, "unit": 1, "consumptionPeriods": []}]
        self.assertEqual(extract_electricity_days(base), {})
        self.assertEqual(extract_electricity_days([]), {})
        self.assertEqual(extract_electricity_days([{"category": True, "type": 1, "unit": 1, "consumptionPeriods": []}]), {})

    def test_invalid_value_unknown_mode_and_duplicate_mode_do_not_create_false_total(self):
        d1 = day_timestamp(2026, 10, 21)
        d2 = day_timestamp(2026, 10, 22)
        d3 = day_timestamp(2026, 10, 23)
        periods = [
            {"date": d1, "mode": 0, "consumedQuantity": 3},
            {"date": d1, "mode": 0, "consumedQuantity": 7},  # duplicate, not 10
            {"date": d2, "mode": 0, "consumedQuantity": 1},
            {"date": d2, "mode": 2, "consumedQuantity": 2},  # unsplit+split
            {"date": d3, "mode": 0, "consumedQuantity": 4},
            {"date": d3, "mode": 9, "consumedQuantity": 9},  # unknown tariff
        ]
        self.assertEqual(extract_electricity_days([
            {"category": 1, "type": 1, "unit": 1, "consumptionPeriods": periods}
        ]), {1: {}})

    def test_false_zero_missing_negative_and_oversized_values_are_distinct(self):
        day = day_timestamp(2026, 10, 22)
        for bad in (None, "5", -1, float("nan"), float("inf"), True, 1000000000, 10**400):
            with self.subTest(bad=str(bad)[:20]):
                result = extract_electricity_days([
                    {"category": 2, "type": 1, "unit": 1,
                     "consumptionPeriods": [{"date": day, "mode": 0, "consumedQuantity": bad}]},
                ])
                self.assertEqual(result, {2: {}})
        self.assertEqual(extract_electricity_days([
            {"category": 2, "type": 1, "unit": 1,
             "consumptionPeriods": [{"date": day, "mode": 0, "consumedQuantity": 0}]},
        ]), {2: {"2026-10-22": 0.0}})

    def test_repeated_category_series_fails_closed(self):
        day = day_timestamp(2026, 10, 22)
        sample = {"category": 1, "type": 1, "unit": 1, "consumptionPeriods":
                  [{"date": day, "mode": 0, "consumedQuantity": 3.5}]}
        result = extract_electricity_days([
            sample, sample,
            {"category": 2, "type": 1, "unit": 1, "consumptionPeriods":
             [{"date": day, "mode": 0, "consumedQuantity": 2.1}]},
        ])
        self.assertEqual(result, {2: {"2026-10-22": 2.1}})

    def test_bounded_history_and_data_schema(self):
        first = day_timestamp(2026, 8, 1)
        periods = [
            {"date": first + i*86400, "mode": 0, "consumedQuantity": float(i)}
            for i in range(80)
        ]
        res = extract_electricity_days([
            {"category": 1, "type": 1, "unit": 1, "consumptionPeriods": periods}
        ])
        self.assertEqual(len(res[1]), 40)
        self.assertEqual(list(res[1].values())[-1], 79.0)
        self.assertEqual(extract_electricity_days([{}]*257), {})
        self.assertEqual(extract_electricity_days({}), {})


if __name__ == "__main__":
    unittest.main()
