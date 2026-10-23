"""Offline read-only energy-validation regression tests (no HA required)."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

MODULE = (Path(__file__).resolve().parents[1] / "custom_components" /
          "atlantic_cozytouch" / "energy_validation.py")
spec = importlib.util.spec_from_file_location("energy_validation_pure_test", MODULE)
lib = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = lib
spec.loader.exec_module(lib)


def sample(id57=11581.0, id59=6571.0, id60=None, device_id="PRIVATE_DEVICE"):
    return [{
        "id": device_id,
        "values": {57: id57, 59: id59, 60: id60},
        "reported_capability_ids": [57, 59, 60],
        "energy_status": {
            57: "valid" if id57 is not None else "missing",
            59: "valid" if id59 is not None else "missing",
            60: "valid" if id60 is not None else "missing",
        },
    }]


class TestUnitFreeMonitor(unittest.TestCase):
    def setUp(self):
        self.monitor = lib.EnergyValidationMonitor()
        self.now = datetime(2026, 10, 23, tzinfo=timezone.utc)

    def test_first_snapshot_has_no_invented_delta(self):
        self.monitor.ingest(sample(), self.now)
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"])
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "first_sample")
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][60]["value_status"], "missing")

    def test_only_positive_same_device_deltas(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(11681, 6600), self.now + timedelta(seconds=180))
        stats = self.monitor.statuses["PRIVATE_DEVICE"]
        self.assertEqual(stats[57]["delta_raw"], 100)
        self.assertEqual(stats[59]["delta_raw"], 29)
        self.assertEqual(stats[57]["comparison"], "increased")
        self.assertIsNone(stats[60]["delta_raw"])
        self.assertEqual(stats[60]["comparison"], "not_applicable")
        other = sample(9999, 2222, device_id="OTHER_DEVICE")
        self.monitor.ingest(other, self.now + timedelta(seconds=360))
        self.assertIsNone(self.monitor.statuses["OTHER_DEVICE"][57]["delta_raw"])

    def test_stable_values_zero_delta_but_no_energy_unit(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(), self.now + timedelta(seconds=180))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"], 0)
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "unchanged")

    def test_decrease_or_reset_never_yields_negative_delta(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(2, 2), self.now + timedelta(seconds=180))
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"])
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"],
                         "decreased_or_reset")

    def test_long_gap_or_failed_poll_is_not_compared(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(13000, 6600), self.now + timedelta(hours=2))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "gap")
        self.monitor.invalidate()
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"])
        self.monitor.ingest(sample(13001, 6601), self.now + timedelta(hours=2, seconds=180))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "first_sample")

    def test_missing_value_or_disappearing_id_breaks_comparison(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(id57=None), self.now + timedelta(seconds=180))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"],
                         "value_unavailable")
        self.monitor.ingest(sample(11600), self.now + timedelta(seconds=360))
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"])
        missing = sample()
        missing[0]["reported_capability_ids"] = [59, 60]
        self.monitor.ingest(missing, self.now + timedelta(seconds=540))
        self.assertNotIn(57, self.monitor.statuses["PRIVATE_DEVICE"])
        self.monitor.ingest(sample(11800), self.now + timedelta(seconds=720))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "first_sample")

    def test_invalid_numeric_and_reversed_timestamp_not_compared(self):
        self.monitor.ingest(sample(), self.now)
        self.monitor.ingest(sample(id57=float("nan"), id59=-123),
                            self.now + timedelta(seconds=180))
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][57]["delta_raw"])
        self.assertIsNone(self.monitor.statuses["PRIVATE_DEVICE"][59]["delta_raw"])
        self.monitor.ingest(sample(), self.now + timedelta(seconds=90))
        self.assertEqual(self.monitor.statuses["PRIVATE_DEVICE"][57]["comparison"], "gap")
        with self.assertRaises(ValueError):
            self.monitor.ingest(sample(), datetime(2026, 10, 23))

    def test_report_contains_only_statuses_and_indices(self):
        self.monitor.ingest(sample(), self.now)
        report = self.monitor.redacted_report(sample())
        self.assertEqual(report[0]["index"], 1)
        self.assertEqual(report[0]["energy_ids"]["60"]["value_status"], "missing")
        serialized = str(report)
        for leaked in ("11581", "6571", "PRIVATE_DEVICE"):
            self.assertNotIn(leaked, serialized)

    def test_status_does_not_invent_unreported_energy_ids(self):
        device = [{"id": "device", "values": {57: 30},
                   "reported_capability_ids": [57], "energy_status": {57: "valid"}}]
        self.monitor.ingest(device, self.now)
        self.assertEqual(set(self.monitor.statuses["device"]), {57})
        self.assertEqual(set(self.monitor.redacted_report(device)[0]["energy_ids"]), {"57"})


class TestFreshness(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, tzinfo=timezone.utc)

    def test_recent_fresh_and_late(self):
        self.assertEqual(lib.freshness_status(self.now, True,
                                             self.now + timedelta(minutes=3)), "aktualny")
        self.assertEqual(lib.freshness_status(self.now, True,
                                             self.now + timedelta(minutes=8)), "opozniony")

    def test_failed_poll_and_no_success(self):
        self.assertEqual(lib.freshness_status(None, False, self.now),
                         "brak_udanego_odczytu")
        self.assertEqual(lib.freshness_status(self.now, False,
                                             self.now + timedelta(minutes=1)),
                         "blad_ostatniego_odczytu")

    def test_naive_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            lib.freshness_status(datetime(2026, 10, 23), True, self.now)


if __name__ == "__main__":
    unittest.main()
