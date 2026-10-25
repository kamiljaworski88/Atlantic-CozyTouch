"""Offline regression tests of the snapshot COP estimator (NO network calls)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "atlantic_cozytouch"
package = ModuleType("atlantic_cop_snapshot_offline")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(
    package.__name__ + ".cop_snapshot", ROOT / "cop_snapshot.py"
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


MODE_STAMP = int(datetime(2026, 10, 25, 7, tzinfo=timezone.utc).timestamp())


def capture(when, *, co=10000, cwu=4000, circuit="CO",
            flow=17.16, supply=25.83, ret=24.89,
            flow_age=25, electric_age=25, supply_age=11037, return_age=11335,
            separate=True, mode_age=None, compressor=None, heater=False):
    ts = int(when.timestamp())
    interface = {
        "id": "interface-private",
        "reported_capability_ids": [57, 59, 91, 112],
        "values": {57: co, 59: cwu, 91: circuit, 112: flow},
        "updated_at": {
            57: ts - electric_age, 59: ts - electric_age,
            112: ts - flow_age,
            91: MODE_STAMP if mode_age is None else ts - mode_age,
        },
    }
    generator = {
        "id": "generator-private" if separate else "interface-private",
        "reported_capability_ids": [109, 116],
        "values": {109: supply, 116: ret},
        "updated_at": {109: ts - supply_age, 116: ts - return_age},
    }
    if compressor is not None:
        generator["reported_capability_ids"].append(51)
        generator["values"][51] = compressor
    if heater:
        generator["reported_capability_ids"].append(64)
        generator["values"][64] = True
    if separate:
        return [interface, generator]
    for key in ("reported_capability_ids",):
        interface[key].extend(generator[key])
    interface["values"].update(generator["values"])
    interface["updated_at"].update(generator["updated_at"])
    return [interface]


class SnapshotEstimatorTest(unittest.TestCase):
    def setUp(self):
        self.t = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
        self.est = mod.HydraulicCopEstimator(allow_unique_cross_device=True)

    def test_user_3_hour_stamps_and_point_94_delta_can_yield_low_confidence_cop(self):
        self.est.ingest(capture(self.t), self.t)
        self.assertEqual(self.est.metrics["status"], "zbieranie_pierwszej_probki")
        self.assertAlmostEqual(self.est.metrics["thermal_kw"], 1.126, places=2)
        later = self.t + timedelta(minutes=5)
        self.est.ingest(capture(later, co=10095, supply_age=11337,
                                return_age=11635), later)
        x = self.est.metrics
        self.assertEqual(x["status"], "szacunek_niska_pewnosc_stale_temperatury")
        self.assertEqual(x["confidence"], "niska")
        self.assertTrue("stale_wartosci" in x["temperature_evidence"])
        self.assertIsNotNone(x["cop"])
        self.assertEqual(x["cop_certified"], False)
        self.assertEqual(self.est.accumulated_intervals, 1)
        self.assertEqual(x["accumulated"]["CO"]["intervals"], 1)

    def test_consecutive_new_snapshots_accumulate_energy_ratio_not_mean_cop(self):
        self.est.ingest(capture(self.t), self.t)
        t1 = self.t + timedelta(minutes=5)
        self.est.ingest(capture(t1, co=10095, supply_age=11337, return_age=11635), t1)
        t2 = t1 + timedelta(minutes=5)
        self.est.ingest(capture(t2, co=10195, supply_age=11637, return_age=11935), t2)
        snap = self.est.accumulator.snapshot()
        self.assertEqual(snap["total"]["intervals"], 2)
        self.assertAlmostEqual(snap["CO"]["electric_kwh"], 0.195, places=3)
        self.assertAlmostEqual(snap["CO"]["heat_kwh"], 2 * 1.126 * 5 / 60, places=3)
        self.assertIsNotNone(snap["total"]["cop"])

    def test_opt_in_required_for_cross_device(self):
        est = mod.HydraulicCopEstimator()
        est.ingest(capture(self.t), self.t)
        self.assertEqual(est.metrics["status"], "niepotwierdzone_powiazanie_obiegu")
        self.assertIsNone(est.metrics["cop"])

    def test_same_device_without_optin_cannot_use_old_temperature(self):
        est = mod.HydraulicCopEstimator()
        est.ingest(capture(self.t, separate=False), self.t)
        self.assertEqual(est.metrics["status"], "stare_znaczniki_temperatur_wymagaja_opt_in")

    def test_temperature_older_than_12h_fails_closed(self):
        self.est.ingest(capture(self.t, supply_age=45000, return_age=45300), self.t)
        self.assertEqual(self.est.metrics["status"], "nieaktualne_pomiary_hydrauliczne")

    def test_stale_electric_meter_is_baseline_only_and_old_flow_is_blocked(self):
        self.est.ingest(capture(self.t, electric_age=1170), self.t)
        self.assertEqual(
            self.est.metrics["status"],
            "punkt_startowy_starego_licznika_czekamy_na_przyrost",
        )
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(
            self.est.metrics["electric_meter_diagnostics"]["last_change_age_seconds"],
            1170,
        )
        self.est.ingest(capture(self.t, flow_age=1500), self.t)
        self.assertEqual(self.est.metrics["status"], "nieaktualny_przeplyw")

    def test_old_counter_then_fresh_increment_can_start_new_valid_interval(self):
        self.est.ingest(capture(self.t, electric_age=3600), self.t)
        self.assertEqual(
            self.est.metrics["status"], "punkt_startowy_starego_licznika_czekamy_na_przyrost"
        )
        later = self.t + timedelta(minutes=5)
        self.est.ingest(capture(later, co=10095, electric_age=20,
                                supply_age=11337, return_age=11635), later)
        self.assertEqual(self.est.accumulated_intervals, 1)
        self.assertIsNotNone(self.est.metrics["cop"])
        self.assertEqual(
            self.est.metrics["electric_meter_diagnostics"]["counter_increment_seen"], True
        )

    def test_stale_meter_without_increment_never_generates_heat_or_cop(self):
        self.est.ingest(capture(self.t, electric_age=3600), self.t)
        later = self.t + timedelta(minutes=5)
        self.est.ingest(capture(later, electric_age=3900,
                                supply_age=11337, return_age=11635), later)
        self.assertEqual(self.est.metrics["status"], "licznik_bez_przyrostu_ponad_15_minut")
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_old_counter_increase_with_stale_vendor_time_must_not_generate_cop(self):
        self.est.ingest(capture(self.t, electric_age=3600), self.t)
        later = self.t + timedelta(minutes=5)
        # Raw increases, but the vendor only reports a last-change time
        # that precedes the first observed HA snapshot.
        self.est.ingest(capture(later, co=10095, electric_age=1800,
                                supply_age=11337, return_age=11635), later)
        self.assertEqual(
            self.est.metrics["status"], "przyrost_pradu_z_nieaktualnym_znacznikiem"
        )
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_old_counter_does_not_spoil_fresh_hydraulic_baseline(self):
        self.est.ingest(capture(self.t, electric_age=3600,
                                supply_age=60, return_age=65), self.t)
        self.assertEqual(
            self.est.metrics["status"], "punkt_startowy_starego_licznika_czekamy_na_przyrost"
        )
        self.assertIsNone(self.est.metrics["cop"])

    def test_counter_not_changed_for_month_can_still_seed_no_cop(self):
        self.est.ingest(capture(self.t, electric_age=30*86400), self.t)
        self.assertEqual(
            self.est.metrics["status"], "punkt_startowy_starego_licznika_czekamy_na_przyrost"
        )
        self.assertIsNone(self.est.metrics["cop"])

    def test_missing_timestamp_does_not_create_output(self):
        devices = capture(self.t)
        del devices[1]["updated_at"][116]
        self.est.ingest(devices, self.t)
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.metrics["status"], "brak_znacznikow_zmiany_wartosci")

    def test_small_delta_or_zero_flow_rejected(self):
        self.est.ingest(capture(self.t, ret=25.25), self.t)
        self.assertEqual(self.est.metrics["status"], "delta_t_za_mala_dla_szacowania_cop")
        self.est.ingest(capture(self.t, flow=0), self.t)
        self.assertEqual(self.est.metrics["status"], "przeplyw_lub_licznik_poza_zakresem")

    def test_heater_on_and_compressor_explicit_off_reset(self):
        self.est.ingest(capture(self.t, heater=True), self.t)
        self.assertEqual(self.est.metrics["status"], "grzalka_cwu_aktywna_niepelny_bilans_pradu")
        self.est.ingest(capture(self.t, compressor=False), self.t)
        self.assertEqual(self.est.metrics["status"], "sprezarka_wylaczona")

    def test_positive_auxiliary_heater_power_blocks_incomplete_energy_balance(self):
        devices = capture(self.t)
        devices[1]["reported_capability_ids"].append(8)
        devices[1]["values"][8] = 3.0
        self.est.ingest(devices, self.t)
        self.assertEqual(
            self.est.metrics["status"], "grzalka_wspomagajaca_moc_dodatnia_w_zakresie_katalogu"
        )
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_user_actual_id8_3000_does_not_falsely_assert_heater_on(self):
        baseline = capture(self.t)
        baseline[1]["reported_capability_ids"].append(8)
        baseline[1]["values"][8] = 3000.0
        self.est.ingest(baseline, self.t)
        self.assertEqual(self.est.metrics["status"], "zbieranie_pierwszej_probki")
        audit = self.est.metrics["heater_evidence"]
        self.assertEqual(
            audit["power_id_states"]["8"],
            "poza_zakresem_katalogu_skala_nieznana",
        )
        self.assertFalse(audit["heater_off_confirmed"])
        self.assertTrue(audit["uncertain"])
        self.assertEqual(self.est.metrics["confidence"], "niska")
        later = self.t + timedelta(minutes=5)
        second = capture(later, co=10095, supply_age=11337, return_age=11635)
        second[1]["reported_capability_ids"].append(8)
        second[1]["values"][8] = 3000.0
        self.est.ingest(second, later)
        self.assertEqual(self.est.accumulated_intervals, 1)
        self.assertIsNotNone(self.est.metrics["cop"])
        self.assertEqual(self.est.metrics["confidence"], "niska")
        self.assertFalse(self.est.metrics["cop_certified"])

    def test_confirmed_dhw_heater_still_blocks_even_if_id8_unscaled(self):
        devices = capture(self.t, heater=True)
        devices[1]["reported_capability_ids"].append(8)
        devices[1]["values"][8] = 3000.0
        self.est.ingest(devices, self.t)
        self.assertEqual(
            self.est.metrics["status"], "grzalka_cwu_aktywna_niepelny_bilans_pradu"
        )
        self.assertIsNotNone(self.est.metrics["delta_t_k"])
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_no_delta_does_not_invent_consumption_and_can_bridge_short_stall(self):
        self.est.ingest(capture(self.t), self.t)
        middle = self.t + timedelta(minutes=3)
        self.est.ingest(capture(middle, supply_age=11217, return_age=11515), middle)
        self.assertEqual(self.est.metrics["status"], "oczekiwanie_na_przyrost_energii")
        self.assertIsNone(self.est.metrics["cop"])
        end = self.t + timedelta(minutes=6)
        self.est.ingest(capture(end, co=10110, supply_age=11397, return_age=11695), end)
        self.assertEqual(self.est.accumulated_intervals, 1)

    def test_large_gap_after_poll_outage_not_integrated(self):
        self.est.ingest(capture(self.t), self.t)
        end = self.t + timedelta(minutes=21)
        self.est.ingest(capture(end, co=10300, supply_age=12297,
                                return_age=12595), end)
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertEqual(self.est.metrics["status"], "przerwa_lub_reset_probki")

    def test_transition_same_mode_stamp_changed_is_rejected(self):
        self.est.ingest(capture(self.t, mode_age=3000), self.t)
        end = self.t + timedelta(minutes=5)
        self.est.ingest(capture(end, co=10100, mode_age=10,
                                supply_age=11337, return_age=11635), end)
        self.assertEqual(self.est.metrics["status"], "zmiana_trybu_pracy")

    def test_counter_reset_and_clock_rollback(self):
        self.est.ingest(capture(self.t), self.t)
        end = self.t + timedelta(minutes=5)
        self.est.ingest(capture(end, co=9000, supply_age=11337, return_age=11635), end)
        self.assertEqual(self.est.metrics["status"], "reset_licznika")
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_unchanged_electric_change_stamp_not_accepted(self):
        self.est.ingest(capture(self.t), self.t)
        end = self.t + timedelta(minutes=5)
        self.est.ingest(capture(end, co=10095, electric_age=325,
                                supply_age=11337, return_age=11635), end)
        self.assertEqual(self.est.metrics["status"], "zmiana_pradu_bez_nowego_znacznika")

    def test_temperature_changes_with_old_stamp_are_not_integrated(self):
        self.est.ingest(capture(self.t), self.t)
        end = self.t + timedelta(minutes=5)
        self.est.ingest(capture(end, co=10095, supply=30,
                                supply_age=11337, return_age=11635), end)
        self.assertEqual(self.est.metrics["status"], "zmiana_jakosci_pomiarow")
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_cwu_is_separate_and_no_doubling_of_co_buckets(self):
        self.est.ingest(capture(self.t), self.t)
        end = self.t + timedelta(minutes=5)
        self.est.ingest(capture(end, co=10095, supply_age=11337,
                                return_age=11635), end)
        co = self.est.accumulator.snapshot()["CO"]["intervals"]
        switch = end + timedelta(minutes=3)
        self.est.ingest(capture(switch, circuit="CWU", mode_age=0,
                                supply_age=11517, return_age=11815), switch)
        self.assertEqual(self.est.metrics["status"], "zbieranie_pierwszej_probki")
        end2 = switch + timedelta(minutes=5)
        self.est.ingest(capture(end2, circuit="CWU", cwu=4095,
                                mode_age=300, supply_age=11817,
                                return_age=12115), end2)
        total = self.est.accumulator.snapshot()
        self.assertEqual(total["CO"]["intervals"], co)
        self.assertEqual(total["CWU"]["intervals"], 1)
        self.assertEqual(total["total"]["intervals"], co + 1)

    def test_invalid_data_types_and_ambiguous_sensors(self):
        with self.assertRaises(ValueError):
            mod.HydraulicCopEstimator(allow_unique_cross_device="true")
        self.est.ingest(capture(self.t) + [capture(self.t)[1]], self.t)
        self.assertEqual(self.est.metrics["status"], "brak_jednoznacznych_zrodel")
        self.est.ingest(capture(self.t, flow=True), self.t)
        self.assertEqual(self.est.metrics["status"], "brak_liczbowych_pomiarow")

    def test_long_observed_window_accepts_only_second_meter_jump(self):
        # 3m HA polling, real counter changes separated by 33 minutes.
        # First observed change at minute 3 opens a NEW window; no history
        # before that event is included in its thermal balance.
        self.est.ingest(capture(self.t), self.t)
        t1 = self.t + timedelta(minutes=3)
        self.est.ingest(capture(
            t1, co=10095, electric_age=15,
            supply_age=11037+180, return_age=11335+180,
        ), t1)
        early = self.est.accumulated_intervals
        for m in range(6, 36, 3):
            moment = self.t + timedelta(minutes=m)
            self.est.ingest(capture(
                moment, co=10095, electric_age=(m-3)*60+15,
                supply_age=11037+m*60, return_age=11335+m*60,
            ), moment)
        self.assertEqual(self.est.accumulated_intervals, early)
        end = self.t + timedelta(minutes=36)
        self.est.ingest(capture(
            end, co=10395, electric_age=15,
            supply_age=11037+36*60, return_age=11335+36*60,
        ), end)
        self.assertEqual(self.est.accumulated_intervals, early + 1)
        self.assertEqual(
            self.est.metrics["status"], "szacunek_niska_pewnosc_pelne_okno_licznika"
        )
        self.assertEqual(self.est.metrics["confidence"], "niska")
        self.assertAlmostEqual(
            self.est.metrics["electric_window_diagnostics"]["pokrycie_procent"],
            100.0,
        )
        self.assertFalse(self.est.metrics["cop_certified"])

    def test_long_observed_window_rejects_unphysical_51_unit_increment(self):
        self.est.ingest(capture(self.t), self.t)
        for m in range(3, 39, 3):
            moment = self.t + timedelta(minutes=m)
            raw = 10100 if m < 36 else 10151
            last_change = 3 if m < 36 else 36
            self.est.ingest(capture(
                moment, co=raw,
                electric_age=(m-last_change)*60+15,
                supply_age=11037+m*60, return_age=11335+m*60,
            ), moment)
        self.assertEqual(
            self.est.metrics["electric_window_diagnostics"]["status"],
            "energia_cieplna_i_prad_fizycznie_niespojne",
        )
        self.assertNotEqual(
            self.est.metrics["status"], "szacunek_niska_pewnosc_pelne_okno_licznika"
        )

    def test_no_private_identifiers_in_public_metrics_or_store(self):
        self.est.ingest(capture(self.t), self.t)
        self.assertNotIn("interface-private", str(self.est.metrics))
        self.assertNotIn("generator-private", str(self.est.metrics))
        self.assertNotIn("private", str(self.est.export_accumulated()))
        self.assertFalse(self.est.metrics["cop_certified"])


if __name__ == "__main__":
    unittest.main()
