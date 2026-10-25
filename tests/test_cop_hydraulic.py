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


MODE_STAMP = int(datetime(2026, 10, 25, 7, tzinfo=timezone.utc).timestamp())


def sample(moment, energy_co=10000, energy_cwu=3000, flow=20, supply=34, ret=29.5, mode="CO",
           flow_age=0, return_age=0, electric_age=0, separate=False, mode_age=None,
           supply_age=0):
    ts = int(moment.timestamp())
    interface = {
        "id": "private_interface", "reported_capability_ids": [57, 59, 91, 112],
        "values": {57: energy_co, 59: energy_cwu, 91: mode, 112: flow},
        "updated_at": {
            57: ts - electric_age, 59: ts - electric_age,
            91: MODE_STAMP if mode_age is None else ts - mode_age,
            112: ts - flow_age,
        },
    }
    generator = {
        "id": "private_generator" if separate else "private_interface",
        "reported_capability_ids": [109, 116],
        "values": {109: supply, 116: ret},
        "updated_at": {109: ts - supply_age, 116: ts - return_age},
    }
    if separate:
        return [interface, generator]
    # Safe synthetic fixture: all five measurements on ONE logical device.
    interface["reported_capability_ids"].extend(generator["reported_capability_ids"])
    interface["values"].update(generator["values"])
    interface["updated_at"].update(generator["updated_at"])
    return [interface]


class TestHydraulicCop(unittest.TestCase):
    def setUp(self):
        self.monitor = mod.HydraulicCopEstimator()
        self.t = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)

    def test_stable_vendor_temperature_last_change_can_be_experimental(self):
        estimator = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        # Independent time of last value change; both temperatures are > 1h old,
        # yet both are returned with a successful latest cloud snapshot.
        estimator.ingest(sample(
            self.t, separate=True, supply_age=4360, return_age=4658
        ), self.t)
        self.assertEqual(estimator.metrics["status"], "zbieranie_pierwszej_probki")
        later = self.t + timedelta(minutes=5)
        estimator.ingest(sample(
            later, energy_co=10200, separate=True,
            supply_age=4660, return_age=4958
        ), later)
        self.assertEqual(
            estimator.metrics["status"], "szacunek_eksperymentalny_stare_temperatury"
        )
        self.assertEqual(estimator.metrics["cop"], 2.62)
        self.assertFalse(estimator.metrics["cop_certified"])
        self.assertEqual(
            estimator.metrics["temperature_evidence"],
            "stare_znaczniki_zmian_niska_pewnosc",
        )

    def test_stale_electric_counter_not_accepted_with_old_temperatures(self):
        estimator = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        estimator.ingest(sample(
            self.t, separate=True, supply_age=4360, return_age=4658,
            electric_age=1075,
        ), self.t)
        self.assertEqual(estimator.metrics["status"], "odczyt_licznika_niespojny")
        self.assertIsNone(estimator.metrics["cop"])

    def test_older_than_two_hours_is_rejected(self):
        estimator = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        estimator.ingest(sample(
            self.t, separate=True, supply_age=8000, return_age=8250,
        ), self.t)
        self.assertEqual(estimator.metrics["status"], "nieaktualne_pomiary_hydrauliczne")
        self.assertIsNone(estimator.metrics["cop"])

    def test_stable_temperature_fallback_needs_user_opt_in(self):
        self.monitor.ingest(sample(
            self.t, supply_age=4360, return_age=4658
        ), self.t)
        self.assertEqual(self.monitor.metrics["status"], "nieaktualne_pomiary_hydrauliczne")

    def test_stable_temperature_fallback_rejects_divergent_pair(self):
        estimator = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        estimator.ingest(sample(
            self.t, separate=True, supply_age=4300, return_age=5150
        ), self.t)
        self.assertEqual(estimator.metrics["status"], "niespojne_czasy_probek")

    def test_stale_temperatures_must_not_change_across_poll(self):
        estimator = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        estimator.ingest(sample(
            self.t, separate=True, supply_age=4360, return_age=4658
        ), self.t)
        later = self.t + timedelta(minutes=5)
        estimator.ingest(sample(
            later, energy_co=10200, supply=35, separate=True,
            supply_age=4660, return_age=4958
        ), later)
        self.assertEqual(
            estimator.metrics["status"], "ponowna_walidacja_stalych_temperatur"
        )
        self.assertIsNone(estimator.metrics["cop"])

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

    def test_split_logical_devices_never_masquerade_as_one_loop(self):
        self.monitor.ingest(sample(self.t, separate=True), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=10200, separate=True), later)
        self.assertEqual(self.monitor.metrics["status"], "niepotwierdzone_powiazanie_obiegu")
        self.assertIsNone(self.monitor.metrics["thermal_kw"])
        self.assertIsNone(self.monitor.metrics["cop"])

    def test_vendor_timestamps_must_be_aligned_within_snapshot(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=10200, flow_age=240), later)
        self.assertEqual(self.monitor.metrics["status"], "niespojne_czasy_probek")
        self.assertIsNone(self.monitor.metrics["cop"])
        # Circuit mode stale even when temperatures are fresh.
        self.monitor.ingest(sample(later, energy_co=10200, mode_age=3600), later)
        # ID91 modificationDate records the last mode change, not heartbeat;
        # an old timestamp alone is legitimate when the mode is stable.
        self.assertEqual(self.monitor.metrics["status"], "zbieranie_pierwszej_probki")

    def test_trapezoidal_thermal_power_not_just_final_snapshot(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=10200, supply=37), later)
        result = self.monitor.metrics
        self.assertEqual(result["status"], "szacunek_diagnostyczny")
        self.assertAlmostEqual(result["thermal_kw"], 10.465, places=3)
        self.assertEqual(result["cop"], 3.49)

    def test_no_cop_after_unaligned_electric_update_then_new_baseline(self):
        self.monitor.ingest(sample(self.t), self.t)
        later = self.t + timedelta(minutes=5)
        self.monitor.ingest(sample(later, energy_co=10200, electric_age=300), later)
        self.assertEqual(self.monitor.metrics["status"], "niespojne_czasy_probek")
        self.assertIsNone(self.monitor.metrics["cop"])
        next_sample = later + timedelta(minutes=5)
        self.monitor.ingest(sample(next_sample, energy_co=10400), next_sample)
        self.assertEqual(self.monitor.metrics["status"], "zbieranie_pierwszej_probki")
        self.assertIsNone(self.monitor.metrics["cop"])

    def test_opt_in_allows_single_unique_pair_as_experimental_only(self):
        pump = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        pump.ingest(sample(self.t, separate=True, mode_age=3600), self.t)
        self.assertEqual(pump.metrics["status"], "zbieranie_pierwszej_probki")
        second = self.t + timedelta(minutes=5)
        pump.ingest(sample(second, energy_co=10200, separate=True,
                           mode_age=3900), second)
        self.assertEqual(pump.metrics["status"], "szacunek_eksperymentalny_miedzy_modulami")
        self.assertEqual(pump.metrics["topology"], "jedyna_para_miedzy_modulami_opt_in")
        self.assertEqual(pump.metrics["cop"], 2.62)
        self.assertFalse(pump.metrics["cop_certified"])

    def test_opt_in_still_rejects_ambiguous_generator(self):
        pump = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        devices = sample(self.t, separate=True)
        devices.append({**devices[1], "id": "other-generator"})
        pump.ingest(devices, self.t)
        self.assertEqual(pump.metrics["status"], "brak_jednoznacznych_zrodel")
        self.assertIsNone(pump.metrics["cop"])

    def test_cross_device_snapshot_skew_is_bounded(self):
        pump = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        pump.ingest(sample(self.t, separate=True, flow_age=650), self.t)
        self.assertEqual(pump.metrics["status"], "niespojne_czasy_probek")
        self.assertIsNone(pump.metrics["cop"])

    def test_mode_change_timestamp_resets_even_same_obieg(self):
        pump = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        pump.ingest(sample(self.t, separate=True, mode_age=3600), self.t)
        later = self.t + timedelta(minutes=5)
        pump.ingest(sample(later, energy_co=10200, separate=True,
                           mode_age=180), later)
        self.assertEqual(pump.metrics["status"], "zmiana_trybu_pracy")
        self.assertIsNone(pump.metrics["cop"])

    def test_idle_does_not_generate_false_cop_but_keeps_last_good(self):
        pump = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        pump.ingest(sample(self.t, separate=True), self.t)
        t2 = self.t + timedelta(minutes=5)
        pump.ingest(sample(t2, energy_co=10200, separate=True), t2)
        self.assertEqual(pump.metrics["cop"], 2.62)
        t3 = t2 + timedelta(minutes=5)
        pump.ingest(sample(t3, energy_co=10200, separate=True, supply=25.8, ret=25.7), t3)
        self.assertEqual(pump.metrics["status"], "brak_aktywnego_grzania")
        self.assertIsNone(pump.metrics["cop"])
        self.assertEqual(pump.metrics["last_cop"], 2.62)
        pump.ingest([], t3 + timedelta(hours=13))
        self.assertIsNone(pump.metrics["last_cop"])

    def test_invalid_option_type_rejected(self):
        for value in ("true", 1, None):
            with self.assertRaises(ValueError):
                mod.HydraulicCopEstimator(allow_unique_cross_device=value)

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
