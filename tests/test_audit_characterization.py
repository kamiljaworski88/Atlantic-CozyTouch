"""Characterization of unresolved v0.5.22 COP limitations, NOT acceptance criteria.

These passing tests reproduce unsafe assumptions. When accounting is redesigned,
replace them with rejection assertions and preserve the physical counterexamples.
"""
import unittest
from test_cop_window import mod, sample
from test_cop_snapshot import capture, NOW, mod as estimator_module
from datetime import timedelta


def observe_window(minutes, heat_kw, increment, step=3):
    window = mod.ObservedElectricWindow()
    window.ingest(sample(0, 10000, -10, heat_kw))
    window.ingest(sample(3, 10100, 3, heat_kw))
    for minute in range(3 + step, 3 + minutes, step):
        window.ingest(sample(minute, 10100, 3, heat_kw))
    result = window.ingest(sample(3 + minutes, 10100 + increment, 3 + minutes, heat_kw))
    return result, window


class AuditCharacterization(unittest.TestCase):
    def test_exact_reported_six_minute_case_is_rejected(self):
        result, window = observe_window(6, 4.91, 52)
        self.assertIsNone(result)
        self.assertIn("za_krotkie", window.last_reason)

    def test_same_energies_still_accepted_over_twelve_minutes(self):
        result, window = observe_window(12, 2.455, 52)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.heat_kwh, .491)
        self.assertAlmostEqual(result.electric_kwh, .052)
        self.assertAlmostEqual(result.heat_kwh/result.electric_kwh, 9.4423076923)

    def test_eight_minute_sampling_is_reported_as_full_coverage(self):
        result, window = observe_window(32, 3, 400, step=8)
        self.assertIsNotNone(result)
        self.assertEqual(result.segment_count, 4)
        self.assertEqual(window.diagnostics()["pokrycie_procent"], 100.0)

    def test_production_estimator_accepts_same_energies_without_period_evidence(self):
        estimator = estimator_module.HydraulicCopEstimator(True)
        flow = 2.455 / (4 * estimator_module.HEAT_FACTOR)
        for minute in (0, 3, 6, 9, 12, 15):
            when = NOW + timedelta(minutes=minute)
            raw = 10000 if minute == 0 else 10100 if minute < 15 else 10152
            event = -10 if minute == 0 else 3 if minute < 15 else 15
            estimator.ingest(capture(
                when, co=raw, flow=flow, supply=35, ret=31,
                electric_age=(minute-event)*60+15,
                supply_age=11037+minute*60, return_age=11335+minute*60,
            ), when)
        self.assertEqual(estimator.metrics["live_cop"], 9.44)
        self.assertEqual(estimator.accumulated_intervals, 1)
        self.assertFalse(estimator.metrics["cop_certified"])

    def test_legacy_944_is_mixed_with_new_energy_in_same_schema(self):
        accumulator = estimator_module.CopEnergyAccumulator()
        self.assertTrue(accumulator.add("CO", .491, .052, 360))
        restored = estimator_module.CopEnergyAccumulator()
        self.assertTrue(restored.restore_state(accumulator.export_state()))
        self.assertTrue(restored.add("CO", 1, .3, 1200))
        self.assertEqual(restored.snapshot()["CO"]["intervals"], 2)
        self.assertAlmostEqual(restored.snapshot()["CO"]["cop"], 4.24)
