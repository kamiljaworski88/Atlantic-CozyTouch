"""Offline estimator tests; synthetic data only, no credentials or HTTP."""
from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "custom_components" / "atlantic_cozytouch" / "cop_hydraulic.py"
spec = importlib.util.spec_from_file_location("cop_hydraulic_test", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def sample(moment, energy_co=10000, energy_cwu=3000, flow=20, supply=34, ret=29.5, mode="CO",
           flow_age=0, return_age=0, electric_age=0):
    ts = int(moment.timestamp())
    return [
        {"id": "private_interface", "reported_capability_ids": [57, 59, 91, 112],
         "values": {57: energy_co, 59: energy_cwu, 91: mode, 112: flow},
         "updated_at": {57: ts - electric_age, 59: ts - electric_age,
                        112: ts - flow_age}},
        {"id": "private_generator", "reported_capability_ids": [109, 116],
         "values": {109: supply, 116: ret},
         "updated_at": {109: ts, 116: ts - return_age}},
    ]


class TestHydraulicCop(unittest.TestCase):
    def setUp(self):
        self.monitor = mod.HydraulicCopEstimator()
        self.t = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)

    def test_valid_interval_yields_explicitly_experimental_cop(self):
        self.monitor.ingest(sample(self.t), self.t)
        self.assertIsNone(self.monitor.metrics["cop"])
        t2 = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(t2, energy_co=10200), t2)
        result = self.monitor.metrics
        self.assertEqual(result["status"], "szacunek_diagnostyczny")
        self.assertAlmostEqual(result["thermal_kw"], 6.279, places=3)
        self.assertAlmostEqual(result["electrical_kw"], 2.4, places=3)
        self.assertEqual(result["cop"], 2.62)

    def test_no_delta_is_unknown_not_zero_and_baseline_doesnt_shift(self):
        self.monitor.ingest(sample(self.t), self.t)
        mid = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(mid), mid)
        self.assertIsNone(self.monitor.metrics["cop"])
        end = self.t + timedelta(minutes=10)
        self.monitor.ingest(sample(end, energy_co=10400), end)
        self.assertAlmostEqual(self.monitor.metrics["electrical_kw"], 2.4)

    def test_stale_hydraulic_data_cannot_produce_cop(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=10200, return_age=3600), later)
        self.assertIsNone(self.monitor.metrics["cop"])
        self.assertEqual(self.monitor.metrics["status"], "nieaktualne_pomiary_hydrauliczne")

    def test_reset_or_mode_switch_cannot_create_a_ratio(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=9000), later)
        self.assertIsNone(self.monitor.metrics["cop"])
        last = self.t + timedelta(minutes=10)
        self.monitor.ingest(sample(last, energy_co=9400, mode="CWU"), last)
        self.assertIsNone(self.monitor.metrics["cop"])
        self.assertEqual(self.monitor.metrics["circuit"], "CWU")

    def test_missing_or_ambiguous_devices_never_merge(self):
        self.monitor.ingest([], self.t)
        self.assertIsNone(self.monitor.metrics["cop"])
        self.assertEqual(self.monitor.metrics["status"], "brak_jednoznacznych_zrodel")
        twice = sample(self.t)
        self.monitor.ingest(twice + [twice[0]], self.t)
        self.assertIsNone(self.monitor.metrics["cop"])

    def test_zero_flow_and_bad_values_fail_closed(self):
        self.monitor.ingest(sample(self.t, flow=0), self.t)
        self.assertIsNone(self.monitor.metrics["thermal_kw"])
        self.monitor.ingest(sample(self.t, supply=27, ret=30), self.t)
        self.assertIsNone(self.monitor.metrics["thermal_kw"])
        self.monitor.ingest(sample(self.t, flow=True), self.t)
        self.assertIsNone(self.monitor.metrics["cop"])

    def test_interval_and_electric_freshness(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=21)
        self.monitor.ingest(sample(later, energy_co=10800), later)
        self.assertIsNone(self.monitor.metrics["cop"])
        next_sample = later + timedelta(minutes=5)
        self.monitor.ingest(sample(next_sample, energy_co=11000, electric_age=2000), next_sample)
        self.assertEqual(self.monitor.metrics["status"], "odczyt_licznika_niespojny")
        self.assertIsNone(self.monitor.metrics["cop"])


if __name__ == "__main__":
    unittest.main()
