"""Offline tests of cumulative compressor readings and bounded deltas."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "atlantic_cozytouch" / "compressor.py"
spec = importlib.util.spec_from_file_location("atlantic_compressor_pure_test", MODULE)
lib = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lib
spec.loader.exec_module(lib)


def device(start=21, runtime=32400, device_id="fake"):
    return [{"id": device_id, "values": {24: start, 27: runtime}}]


class TestCompressor(unittest.TestCase):
    def setUp(self):
        self.m = lib.CompressorMonitor()
        self.t = datetime(2026, 10, 23, tzinfo=timezone.utc)

    def test_first_snapshot_has_unknown_deltas(self):
        self.m.ingest(device(), self.t)
        m = self.m.metrics["fake"]
        self.assertEqual(m["runtime_hours"], 9)
        self.assertEqual(m["average_runtime_min_per_start"], 25.71)
        self.assertIsNone(m["starts_delta_last_poll"])
        self.assertIsNone(m["runtime_delta_seconds_last_poll"])

    def test_delta_from_two_valid_polls(self):
        self.m.ingest(device(), self.t)
        self.m.ingest(device(22, 32500), self.t + timedelta(seconds=180))
        x = self.m.metrics["fake"]
        self.assertEqual(x["starts_delta_last_poll"], 1)
        self.assertEqual(x["runtime_delta_seconds_last_poll"], 100)

    def test_gap_and_reset_cannot_produce_false_cycles(self):
        self.m.ingest(device(), self.t)
        self.m.ingest(device(25, 33100), self.t + timedelta(hours=1))
        self.assertIsNone(self.m.metrics["fake"]["starts_delta_last_poll"])
        self.assertIsNone(self.m.metrics["fake"]["runtime_delta_seconds_last_poll"])
        self.m.ingest(device(1, 100), self.t + timedelta(hours=1, seconds=180))
        self.assertIsNone(self.m.metrics["fake"]["starts_delta_last_poll"])
        self.assertIsNone(self.m.metrics["fake"]["runtime_delta_seconds_last_poll"])

    def test_unrealistic_runtime_increment_is_ignored(self):
        self.m.ingest(device(), self.t)
        self.m.ingest(device(22, 38000), self.t + timedelta(seconds=180))
        self.assertIsNone(self.m.metrics["fake"]["runtime_delta_seconds_last_poll"])

    def test_no_counters_no_metrics(self):
        self.m.ingest([{"id": "fake", "values": {109: 33.3}}], self.t)
        self.assertEqual(self.m.metrics, {})

    def test_only_runtime_does_not_fabricate_start_average(self):
        self.m.ingest([{"id": "fake", "values": {27: 3600}}], self.t)
        self.assertEqual(self.m.metrics["fake"]["runtime_hours"], 1)
        self.assertIsNone(self.m.metrics["fake"]["average_runtime_min_per_start"])

    def test_invalid_data_not_accepted(self):
        self.m.ingest([{"id": "fake", "values": {24: -1, 27: float("nan")}}], self.t)
        self.assertIsNone(self.m.metrics["fake"]["runtime_hours"])
        self.assertIsNone(self.m.metrics["fake"]["average_runtime_min_per_start"])

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            self.m.ingest(device(), datetime(2026, 10, 23))


if __name__ == "__main__":
    unittest.main()
