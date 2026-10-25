"""COP estimator integration: accumulated ratios from validated intervals only."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/atlantic_cozytouch"
pkg = ModuleType("offline_cop_aggregate")
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
spec = importlib.util.spec_from_file_location(pkg.__name__ + ".cop_hydraulic", ROOT / "cop_hydraulic.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def snapshot(at, co=10000, cwu=3000, mode="CO", supply=34, ret=29.5,
             flow=20, mode_stamp=None):
    ts = int(at.timestamp())
    mode_stamp = mode_stamp if mode_stamp is not None else int(datetime(
        2026, 10, 25, 7, tzinfo=timezone.utc
    ).timestamp())
    return [{
        "id": "interface", "reported_capability_ids": [57, 59, 91, 112],
        "values": {57: co, 59: cwu, 91: mode, 112: flow},
        "updated_at": {57: ts, 59: ts, 91: mode_stamp, 112: ts},
    }, {
        "id": "generator", "reported_capability_ids": [109, 116],
        "values": {109: supply, 116: ret},
        "updated_at": {109: ts, 116: ts},
    }]


class TestAggregateInEstimator(unittest.TestCase):
    def setUp(self):
        self.first = datetime(2026, 10, 25, 8, tzinfo=timezone.utc)
        self.est = mod.HydraulicCopEstimator(allow_unique_cross_device=True)

    def test_sum_not_mean_and_outages(self):
        t0 = self.first
        self.est.ingest(snapshot(t0), t0)
        t1 = t0 + timedelta(minutes=5)
        self.est.ingest(snapshot(t1, co=10200), t1)
        self.assertEqual(self.est.metrics["cop"], 2.62)
        self.assertEqual(self.est.accumulator.snapshot()["CO"]["intervals"], 1)
        t2 = t1 + timedelta(minutes=5)
        self.est.ingest(snapshot(t2, co=10300, supply=38.5), t2)
        total = self.est.accumulator.snapshot()["total"]
        self.assertEqual(total["intervals"], 2)
        self.assertAlmostEqual(total["electric_kwh"], .3, places=4)
        self.assertAlmostEqual(total["cop"], total["heat_kwh"]/total["electric_kwh"], places=1)

        # Idle pump, broken polls and restored HA state must not add estimates.
        t3 = t2 + timedelta(minutes=5)
        self.est.ingest(snapshot(t3, co=10300, supply=25.8, ret=25.7), t3)
        self.assertEqual(self.est.accumulator.snapshot()["total"], total)
        self.est.invalidate()
        self.assertEqual(self.est.accumulator.snapshot()["total"], total)
        copied = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        self.assertTrue(copied.restore_accumulated(self.est.export_accumulated()))
        self.assertEqual(copied.accumulated_intervals, 2)
        copied.ingest(snapshot(t3, co=10400), t3)
        self.assertEqual(copied.accumulated_intervals, 2)  # new baseline
        t4 = t3 + timedelta(minutes=5)
        copied.ingest(snapshot(t4, co=10600), t4)
        self.assertEqual(copied.accumulated_intervals, 3)

    def test_modes_and_resets_do_not_cross_accounting(self):
        t0 = self.first
        self.est.ingest(snapshot(t0), t0)
        t1 = t0 + timedelta(minutes=5)
        self.est.ingest(snapshot(t1, co=10200), t1)
        self.assertEqual(self.est.accumulated_intervals, 1)
        t2 = t1 + timedelta(minutes=5)
        self.est.ingest(snapshot(t2, co=10200, mode="CWU"), t2)
        self.assertEqual(self.est.accumulated_intervals, 1)
        t3 = t2 + timedelta(minutes=5)
        self.est.ingest(snapshot(t3, co=10200, cwu=3200, mode="CWU"), t3)
        buckets = self.est.accumulator.snapshot()
        self.assertEqual(buckets["CO"]["intervals"], 1)
        self.assertEqual(buckets["CWU"]["intervals"], 1)
        self.assertEqual(buckets["total"]["intervals"], 2)
        # A counter rollback must reset its baseline but preserve cumulative.
        t4 = t3 + timedelta(minutes=5)
        self.est.ingest(snapshot(t4, co=10200, cwu=3000, mode="CWU"), t4)
        self.assertEqual(self.est.metrics["status"], "przerwa_lub_reset_licznika")
        t5 = t4 + timedelta(minutes=5)
        self.est.ingest(snapshot(t5, co=10200, cwu=3200, mode="CWU"), t5)
        self.assertEqual(self.est.accumulator.snapshot()["CWU"]["intervals"], 2)

    def test_missing_growth_yields_unknown_cumulative_and_no_guess(self):
        t0 = self.first
        self.est.ingest(snapshot(t0), t0)
        t1 = t0 + timedelta(minutes=5)
        self.est.ingest(snapshot(t1), t1)
        self.assertEqual(self.est.metrics["status"], "oczekiwanie_na_przyrost_energii")
        self.assertIsNone(self.est.accumulator.snapshot()["total"]["cop"])


if __name__ == "__main__":
    unittest.main()
