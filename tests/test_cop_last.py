"""Offline tests for read-only persisted LAST COP (not a live measurement)."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest

path = (
    Path(__file__).resolve().parents[1]
    / "custom_components/atlantic_cozytouch/cop_last.py"
)
spec = importlib.util.spec_from_file_location("cop_last_offline_unit", path)
cop_last = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cop_last
spec.loader.exec_module(cop_last)

NOW = datetime(2026, 10, 25, 17, 35, tzinfo=timezone.utc)


class TestLastCopMemory(unittest.TestCase):
    def setUp(self):
        self.memory = cop_last.LastCopMemory()

    def test_persist_last_accepted_separately_for_co_cwu(self):
        self.assertTrue(self.memory.record("CO", 9.44, NOW, "niska", "krotki_przedzial"))
        later = NOW + timedelta(minutes=20)
        self.assertTrue(self.memory.record("CWU", 3.1, later, "niska", "pelne_okno_energii"))
        self.assertEqual(self.memory.latest("CO")["value"], 9.44)
        self.assertEqual(self.memory.latest("CWU")["value"], 3.1)
        self.assertEqual(self.memory.latest()["circuit"], "CWU")
        self.assertEqual(self.memory.latest("CO")["at"], NOW.isoformat())

    def test_retains_last_valid_date_even_if_older_than_12_hours(self):
        self.assertTrue(self.memory.record("CO", 2.92, NOW, "niska", "krotki_przedzial"))
        export = self.memory.export_state()
        recovered = cop_last.LastCopMemory()
        self.assertTrue(recovered.restore_state(export))
        self.assertEqual(recovered.latest("CO")["at"], NOW.isoformat())
        self.assertEqual(recovered.latest()["value"], 2.92)

    def test_store_avoids_raw_meters_tokens_device_or_secret(self):
        self.memory.record("CO", 9.44, NOW, "niska", "krotki_przedzial")
        state = self.memory.export_state()
        self.assertEqual(set(state), {"schema", "last_by_circuit"})
        self.assertEqual(set(state["last_by_circuit"]["CO"]), {
            "value", "at", "quality", "source",
        })
        self.assertNotIn("device", str(state))
        self.assertNotIn("token", str(state))
        self.assertNotIn("28183", str(state))
        self.assertNotIn("password", str(state))

    def test_invalid_store_never_overwrites_good_value(self):
        self.memory.record("CO", 9.44, NOW, "niska", "krotki_przedzial")
        before = self.memory.export_state()
        examples = [
            None, {}, [], {"schema": 2, "last_by_circuit": {}},
            {"schema": 1, "last_by_circuit": {"unknown": {}}},
            {"schema": 1, "last_by_circuit": {"CO": {"value": 9.44}}},
            {"schema": 1, "last_by_circuit": {
                "CO": {"value": True, "at": NOW.isoformat(),
                       "quality": "niska", "source": "krotki_przedzial"}}},
            {"schema": 1, "last_by_circuit": {
                "CO": {"value": 100, "at": NOW.isoformat(),
                       "quality": "niska", "source": "krotki_przedzial"}}},
            {"schema": 1, "last_by_circuit": {
                "CO": {"value": 9.44, "at": "broken",
                       "quality": "niska", "source": "krotki_przedzial"}}},
            {"schema": 1, "last_by_circuit": {
                "CO": {"value": 9.44, "at": NOW.isoformat(),
                       "quality": "verified", "source": "krotki_przedzial"}}},
        ]
        for example in examples:
            with self.subTest(example=str(example)):
                self.assertFalse(self.memory.restore_state(example))
                self.assertEqual(self.memory.export_state(), before)

    def test_monotonic_utc_validation(self):
        self.assertTrue(self.memory.record("CO", 2.92, NOW, "niska", "krotki_przedzial"))
        self.assertFalse(self.memory.record("CO", 3.0, NOW, "niska", "krotki_przedzial"))
        self.assertFalse(self.memory.record(
            "CO", 3.0, NOW - timedelta(seconds=1), "niska", "krotki_przedzial"
        ))
        self.assertFalse(self.memory.record(
            "CO", float("nan"), NOW + timedelta(minutes=1), "niska", "krotki_przedzial"
        ))
        self.assertFalse(self.memory.record(
            "CO", 2.9, datetime(2026, 10, 25), "niska", "krotki_przedzial"
        ))
        self.assertEqual(self.memory.latest("CO")["value"], 2.92)


if __name__ == "__main__":
    unittest.main()
