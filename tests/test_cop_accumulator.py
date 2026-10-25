"""Offline tests: persisted cumulative COP uses only accepted energy intervals."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/atlantic_cozytouch"
spec = importlib.util.spec_from_file_location("cop_accumulator_offline_test", ROOT / "cop_accumulator.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class TestAccumulator(unittest.TestCase):
    def test_unknown_without_accepted_intervals(self):
        accumulator = mod.CopEnergyAccumulator()
        for name in ("CO", "CWU", "total"):
            row = accumulator.snapshot()[name]
            self.assertIsNone(row["cop"])
            self.assertEqual(row["intervals"], 0)
        self.assertEqual(accumulator.intervals, 0)

    def test_weighted_ratio_and_three_sensors(self):
        accumulator = mod.CopEnergyAccumulator()
        self.assertTrue(accumulator.add("CO", 0.6, 0.2, 300))   # COP 3.0
        self.assertTrue(accumulator.add("CO", 0.3, 0.2, 300))   # COP 1.5
        self.assertTrue(accumulator.add("CWU", 1.2, 0.3, 600))  # COP 4.0
        state = accumulator.snapshot()
        self.assertEqual(state["CO"]["cop"], 2.25)
        self.assertEqual(state["CWU"]["cop"], 4.0)
        self.assertEqual(state["total"]["cop"], 3.0)
        self.assertEqual(state["total"]["intervals"], 3)
        self.assertEqual(state["total"]["covered_hours"], 0.33)
        self.assertEqual(accumulator.intervals, 3)
        self.assertTrue(state["total"]["verified"] is False)

    def test_export_restore_is_exact_and_has_no_vendor_data(self):
        accumulator = mod.CopEnergyAccumulator()
        self.assertTrue(accumulator.add("CO", 0.6, 0.2, 300))
        exported = accumulator.export_state()
        self.assertEqual(set(exported), {"schema", "buckets"})
        self.assertNotIn("token", str(exported))
        self.assertNotIn("deviceId", str(exported))
        restored = mod.CopEnergyAccumulator()
        self.assertTrue(restored.restore_state(exported))
        self.assertEqual(restored.snapshot(), accumulator.snapshot())
        self.assertTrue(restored.add("CO", 0.6, 0.2, 300))
        self.assertEqual(restored.snapshot()["CO"]["cop"], 3.0)
        self.assertEqual(restored.snapshot()["CO"]["intervals"], 2)

    def test_reject_malformed_restore_without_partial_mutation(self):
        accumulator = mod.CopEnergyAccumulator()
        self.assertTrue(accumulator.add("CO", 0.6, 0.2, 300))
        before = accumulator.export_state()
        for corrupt in (
            None, [], {},
            {"schema": 44, "buckets": before["buckets"]},
            {"schema": 1, "buckets": {"CO": before["buckets"]["CO"]}},
            {"schema": 1, "buckets": {
                "CO": {**before["buckets"]["CO"], "thermal_kwh": True},
                "CWU": before["buckets"]["CWU"],
            }},
            {"schema": 1, "buckets": {
                "CO": before["buckets"]["CO"],
                "CWU": {**before["buckets"]["CWU"], "electric_kwh": -1},
            }},
        ):
            self.assertFalse(accumulator.restore_state(corrupt))
            self.assertEqual(accumulator.export_state(), before)

    def test_refuse_invalid_intervals(self):
        accumulator = mod.CopEnergyAccumulator()
        for args in (
            ("CO", 0.2, 0, 300),
            ("CO", 1, 0.001, 300),
            ("CO", 0.3, 0.2, 30),
            ("CO", 0.3, 0.2, 1500),
            ("CWU", True, 0.1, 300),
            ("CO", float("nan"), 0.1, 300),
            ("CO", 0.5, float("inf"), 300),
            ("other", 0.5, 0.2, 300),
        ):
            self.assertFalse(accumulator.add(*args))
        self.assertEqual(accumulator.intervals, 0)


if __name__ == "__main__":
    unittest.main()
