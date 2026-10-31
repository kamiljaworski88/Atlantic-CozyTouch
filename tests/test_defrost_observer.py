"""Offline safety tests for the read-only defrost API observer."""
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
import sys
import unittest

FILE = Path(__file__).resolve().parents[1] / "custom_components" / "atlantic_cozytouch" / "defrost_observer.py"
spec = importlib.util.spec_from_file_location("atlantic_defrost_observer_tests", FILE)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

T0 = datetime(2026, 10, 31, 10, 0, tzinfo=UTC)


def devices(*, supply=24.0, ret=28.0, outdoor=1.0, mode="CO",
            split=False, ambiguous=False, recent=True):
    changed = int(T0.timestamp())
    pair = {
        "id": "SECRET_GENERATOR_ID",
        "name": "PERSONAL_DEVICE_NAME",
        "values": {109: supply, 116: ret},
        "updated_at": {109: changed if recent else changed - 60000,
                       116: changed if recent else changed - 60000},
    }
    interface = {"id": "SECRET_INTERFACE_ID", "values": {119: outdoor, 91: mode}}
    zone = {"id": "SECRET_ZONE_ID", "values": {181: "Ogrzewanie"}}
    if split:
        pair["values"].pop(109)
        interface["values"][109] = supply
    result = [interface, pair, zone]
    if ambiguous:
        result.append({"id": "OTHER_SECRET_GENERATOR_ID",
                       "values": {109: supply, 116: ret}})
    return result


class TestDefrostObserver(unittest.TestCase):
    def test_empty_has_no_confirmed_defrost(self):
        observer = module.DefrostApiObserver()
        report = observer.report()
        self.assertFalse(report["defrost_potwierdzony"])
        self.assertFalse(report["sygnal_do_sterowania"])
        self.assertEqual(report["tryb"], "dry_run_tylko_odczyt")
        self.assertIsNone(observer.delta_t)

    def test_pair_from_one_module_only(self):
        observer = module.DefrostApiObserver()
        observer.ingest(devices(supply=28, ret=25), T0)
        self.assertEqual(observer.delta_t, 3.0)
        self.assertEqual(observer.latest["obieg"], "CO")
        self.assertEqual(observer.status, "obserwacja")

    def test_split_hydraulic_values_are_not_combined(self):
        observer = module.DefrostApiObserver()
        observer.ingest(devices(split=True), T0)
        self.assertIsNone(observer.delta_t)
        self.assertEqual(observer.status, "brak_jednoznacznej_pary_temperatur")

    def test_ambiguous_two_modules(self):
        observer = module.DefrostApiObserver()
        observer.ingest(devices(ambiguous=True), T0)
        self.assertIsNone(observer.delta_t)

    def test_invalid_telemetry_not_converted_to_zero(self):
        for val in (None, True, "NaN", float("inf"), -273.15, "unknown"):
            observer = module.DefrostApiObserver()
            observer.ingest(devices(supply=val), T0)
            self.assertIsNone(observer.delta_t, msg=str(val))
            self.assertEqual(observer.status, "brak_waznych_temperatur")

    def test_candidate_needs_two_consecutive_negative_samples(self):
        observer = module.DefrostApiObserver()
        observer.ingest(devices(), T0)
        self.assertFalse(observer.latest["hipoteza"])
        observer.ingest(devices(), T0 + timedelta(minutes=3))
        self.assertTrue(observer.latest["hipoteza"])
        self.assertEqual(observer.status, "hipoteza_odszraniania_niepotwierdzona")
        self.assertFalse(observer.latest["defrost_potwierdzony"])
        self.assertFalse(observer.report()["sygnal_do_sterowania"])

    def test_candidate_requires_outside_and_co(self):
        for outside, mode in ((None, "CO"), (9, "CO"), (0, "CWU")):
            observer = module.DefrostApiObserver()
            for n in range(2):
                observer.ingest(devices(outdoor=outside, mode=mode), T0 + timedelta(minutes=3*n))
            self.assertFalse(observer.latest["hipoteza"])

    def test_old_modification_date_cannot_make_candidate(self):
        observer = module.DefrostApiObserver()
        for n in range(2):
            observer.ingest(devices(recent=False), T0 + timedelta(minutes=3*n))
        self.assertFalse(observer.latest["hipoteza"])

    def test_gap_and_duplicate_observations_do_not_make_candidate(self):
        for other in (T0, T0 + timedelta(minutes=15)):
            observer = module.DefrostApiObserver()
            observer.ingest(devices(), T0)
            observer.ingest(devices(), other)
            self.assertFalse(observer.latest["hipoteza"])

    def test_only_numeric_temperatures_and_states_no_identity(self):
        observer = module.DefrostApiObserver()
        observer.ingest(devices(), T0)
        report = str(observer.report())
        for secret in ("SECRET_GENERATOR_ID", "PERSONAL_DEVICE_NAME", "SECRET_INTERFACE_ID"):
            self.assertNotIn(secret, report)

    def test_buffer_is_bounded(self):
        observer = module.DefrostApiObserver()
        for i in range(270):
            observer.ingest(devices(supply=32, ret=30), T0 + timedelta(minutes=3*i))
        self.assertEqual(len(observer.samples), module.MAX_SAMPLES)
        self.assertLessEqual(len(observer.report()["ostatnie_probki"]), module.VISIBLE_SAMPLES)
        self.assertEqual(observer.report()["liczba_odczytow"], 270)

    def test_naive_time_fails_closed(self):
        observer = module.DefrostApiObserver()
        with self.assertRaises(ValueError):
            observer.ingest(devices(), datetime(2026, 10, 31, 10, 0))


if __name__ == "__main__":
    unittest.main()
