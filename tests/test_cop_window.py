"""Offline tests for bounded 3-minute heat coverage between meter increments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / (
    "custom_components/atlantic_cozytouch/cop_window.py"
)
spec = importlib.util.spec_from_file_location("offline_cop_window", PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
START = datetime(2026, 10, 25, 8, tzinfo=timezone.utc)
MODE_TS = int(START.timestamp()) - 500


def sample(minutes, raw, meter_minute, heat_kw=3.0, *, circuit="CO",
           source="private_device", mode_stamp=MODE_TS, supply=35.0, ret=31.0,
           stale=True, flow_stamp=None):
    when = START + timedelta(minutes=minutes)
    stamp = int(when.timestamp())
    return SimpleNamespace(
        seen=when,
        source_key=source,
        circuit=circuit,
        electric_raw=raw,
        electric_stamp=int((START + timedelta(minutes=meter_minute)).timestamp()) - 10,
        mode_stamp=mode_stamp,
        thermal_kw=heat_kw,
        supply=supply,
        ret=ret,
        supply_stamp=stamp - 11000,
        return_stamp=stamp - 11100,
        flow_stamp=stamp - 30 if flow_stamp is None else flow_stamp,
        stale_temperature=stale,
    )


def seed_and_fill(window, second_jump_raw=10400, change_minute=36):
    # Starting HA first poll cannot reconstruct previously consumed electricity.
    window.ingest(sample(0, 10000, -10))
    window.ingest(sample(3, 10100, 3))    # FIRST witnessed advance: anchor only
    for minute in range(6, change_minute, 3):
        window.ingest(sample(minute, 10100, 3))
    return window.ingest(sample(change_minute, second_jump_raw, change_minute))


class TestObservedEnergyWindows(unittest.TestCase):
    def setUp(self):
        self.window = mod.ObservedElectricWindow()

    def test_33_minute_window_properly_accounts_every_3min_segment(self):
        result = seed_and_fill(self.window)
        self.assertIsNotNone(result)
        self.assertEqual(result.seconds, 33 * 60)
        self.assertEqual(result.covered_seconds, result.seconds)
        self.assertEqual(result.segment_count, 11)
        self.assertAlmostEqual(result.heat_kwh, 1.65)
        self.assertAlmostEqual(result.electric_kwh, 0.3)
        self.assertEqual(self.window.diagnostics()["status"],
                         "zaakceptowane_okno_eksperymentalne")
        self.assertEqual(self.window.diagnostics()["pokrycie_procent"], 100.0)

    def test_51_wh_over_33_min_producing_three_kw_is_physically_rejected(self):
        result = seed_and_fill(self.window, second_jump_raw=10151)
        self.assertIsNone(result)
        self.assertEqual(
            self.window.diagnostics()["status"],
            "energia_cieplna_i_prad_fizycznie_niespojne",
        )

    def test_initial_first_jump_never_backfills_heat(self):
        self.window.ingest(sample(0, 10000, -10))
        self.assertIsNone(self.window.ingest(sample(3, 10100, 3)))
        self.assertEqual(self.window.diagnostics()["status"],
                         "punkt_odniesienia_po_pierwszym_skoku_licznika")

    def test_any_missed_3min_sample_resets_observation_coverage(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        self.window.ingest(sample(6, 10100, 3))
        self.assertIsNone(self.window.ingest(sample(18, 10100, 3)))
        self.assertEqual(self.window.diagnostics()["status"], "przerwa_miedzy_snapshotami")
        self.assertIsNone(self.window.ingest(sample(36, 10400, 36)))

    def test_mode_switch_or_generator_change_drops_window(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        self.window.ingest(sample(6, 10100, 3))
        self.window.ingest(sample(9, 10100, 3, circuit="CWU"))
        self.assertEqual(self.window.diagnostics()["status"],
                         "zmiana_trybu_lub_niespojne_czujniki")

    def test_old_temperature_drift_without_evidence_drops_window(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        self.window.ingest(sample(6, 10100, 3, supply=36.0))
        self.assertEqual(self.window.diagnostics()["status"],
                         "zmiana_trybu_lub_niespojne_czujniki")

    def test_short_meter_window_never_competes_with_legacy_short_estimator(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        for m in (6, 9, 12, 15):
            self.window.ingest(sample(m, 10100, 3))
        self.assertIsNone(self.window.ingest(sample(18, 10200, 18)))
        self.assertEqual(self.window.diagnostics()["status"],
                         "krotkie_okno_obslugiwane_przez_stary_algorytm")

    def test_reset_explicitly_wipes_unfinished_window(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        self.window.reset()
        self.assertIsNone(self.window.ingest(sample(36, 10400, 36)))
        self.assertIsNone(self.window.diagnostics()["okno_sekundy"])

    def test_no_private_device_identifiers_or_raw_counters_in_diagnostics(self):
        seed_and_fill(self.window)
        report = str(self.window.diagnostics())
        self.assertNotIn("private_device", report)
        self.assertNotIn("10100", report)
        self.assertNotIn("10400", report)
        self.assertNotIn("2026-10", report)

    def test_hourly_time_limit_is_bounded(self):
        self.window.ingest(sample(0, 10000, -10))
        self.window.ingest(sample(3, 10100, 3))
        for m in range(6, 67, 3):
            self.window.ingest(sample(m, 10100, 3))
        self.assertIsNone(self.window.ingest(sample(69, 10400, 69)))
        self.assertNotEqual(self.window.diagnostics()["status"],
                            "zaakceptowane_okno_eksperymentalne")


if __name__ == "__main__":
    unittest.main()
