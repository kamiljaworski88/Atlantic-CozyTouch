"""Offline regression tests: real COP needs two observed meter changes.

No HTTP; fake Atlantic device IDs never reach public HA diagnostic attributes.
Old six-minute COP=9.44 from 0.491kWh/0.052kWh MUST NOT be accepted.
"""
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

NOW = datetime(2026, 10, 25, 10, tzinfo=timezone.utc)
MODE_STAMP = int(NOW.timestamp()) - 3600


def capture(when, *, co=10000, cwu=4000, circuit="CO",
            flow=17.16, supply=25.83, ret=24.89,
            flow_age=25, electric_age=25, supply_age=11037, return_age=11335,
            separate=True, mode_age=None, compressor=None, heater=False,
            auxiliary_raw=None):
    ts = int(when.timestamp())
    interface = {
        "id": "private-interface",
        "reported_capability_ids": [57, 59, 91, 112],
        "values": {57: co, 59: cwu, 91: circuit, 112: flow},
        "updated_at": {
            57: ts - electric_age, 59: ts - electric_age,
            112: ts - flow_age,
            91: MODE_STAMP if mode_age is None else ts - mode_age,
        },
    }
    generator = {
        "id": "private-generator" if separate else "private-interface",
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
    if auxiliary_raw is not None:
        generator["reported_capability_ids"].append(8)
        generator["values"][8] = auxiliary_raw
    if separate:
        return [interface, generator]
    interface["reported_capability_ids"].extend(generator["reported_capability_ids"])
    interface["values"].update(generator["values"])
    interface["updated_at"].update(generator["updated_at"])
    return [interface]


class SnapshotEstimatorTest(unittest.TestCase):
    def setUp(self):
        self.t = NOW
        self.est = mod.HydraulicCopEstimator(allow_unique_cross_device=True)

    def observe(self, minute, *, co=10000, cwu=4000, meter_min=-10,
                circuit="CO", **kwargs):
        when = self.t + timedelta(minutes=minute)
        # Device counter stamp changes only on a real meter jump.
        age = int((minute - meter_min) * 60) + 15
        args = dict(
            co=co, cwu=cwu, circuit=circuit, electric_age=age,
            supply_age=11037 + minute * 60,
            return_age=11335 + minute * 60,
        )
        args.update(kwargs)
        self.est.ingest(capture(when, **args), when)

    def run_valid_co_window(self):
        self.observe(0)
        self.observe(3, co=10100, meter_min=3)
        for minute in (6, 9, 12, 15):
            self.observe(minute, co=10100, meter_min=3)
        self.observe(18, co=10350, meter_min=18)

    def test_initial_short_bucket_not_a_real_cop(self):
        self.est.ingest(capture(self.t), self.t)
        when = self.t + timedelta(minutes=6)
        self.est.ingest(capture(
            when, co=10052, supply_age=11037+360,
            return_age=11335+360,
        ), when)
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertIsNone(self.est.metrics["live_cop"])
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_punkt_odniesienia_po_pierwszym_skoku_licznika")

    def test_two_meter_jumps_and_continuous_hydraulic_data_can_create_cop(self):
        self.run_valid_co_window()
        self.assertEqual(self.est.accumulated_intervals, 1)
        self.assertEqual(self.est.metrics["status"],
                         "szacunek_niska_pewnosc_pelne_okno_licznika")
        self.assertEqual(self.est.metrics["confidence"], "niska")
        self.assertEqual(self.est.metrics["last_cop_source"], "pelne_okno_energii")
        self.assertEqual(self.est.metrics["last_cop_circuit"], "CO")
        self.assertAlmostEqual(
            self.est.metrics["electric_window_diagnostics"]["pokrycie_procent"], 100
        )
        self.assertAlmostEqual(
            self.est.accumulator.snapshot()["CO"]["electric_kwh"], 0.25
        )
        self.assertFalse(self.est.metrics["cop_certified"])

    def test_51wh_for_15min_with_approx_5kw_heat_is_rejected(self):
        for minute in range(0, 19, 3):
            co = 10000 if minute == 0 else 10100 if minute < 18 else 10151
            event = -10 if minute == 0 else 3 if minute < 18 else 18
            self.observe(
                minute, co=co, meter_min=event,
                supply=35.0, ret=31.0,
            )
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertIsNone(self.est.metrics["live_cop"])
        self.assertEqual(
            self.est.metrics["electric_window_diagnostics"]["status"],
            "energia_cieplna_i_prad_fizycznie_niespojne",
        )

    def test_last_accepted_retained_without_current_increment(self):
        self.run_valid_co_window()
        accepted = self.est.metrics["cop"]
        self.assertIsNotNone(accepted)
        self.observe(21, co=10350, meter_min=18)
        self.assertEqual(self.est.metrics["cop"], accepted)
        self.assertIsNone(self.est.metrics["live_cop"])
        self.assertEqual(self.est.metrics["cop_display_source"],
                         "ostatni_zaakceptowany_przedzial")
        self.assertTrue(self.est.metrics["cop_is_historical"])

    def test_new_accepted_cop_persists_through_restart(self):
        self.run_valid_co_window()
        accepted = self.est.metrics["cop"]
        saved = self.est.export_last_cops()
        history = self.est.export_accumulated()
        est = mod.HydraulicCopEstimator(allow_unique_cross_device=True)
        self.assertTrue(est.restore_accumulated(history))
        self.assertTrue(est.restore_last_cops(saved))
        self.assertEqual(est.metrics["cop"], accepted)
        self.assertEqual(est.metrics["last_cop_at"],
                         (self.t+timedelta(minutes=18)).isoformat())
        self.assertIsNone(est.metrics["live_cop"])
        self.assertNotIn("private", str(saved))

    def test_legacy_one_interval_9_44_kept_as_clearly_labeled_fallback(self):
        self.assertTrue(self.est.accumulator.add("CO", 0.491, 0.052, 360))
        self.est.invalidate()
        self.assertAlmostEqual(self.est.metrics["cop"], 9.44)
        self.assertTrue(self.est.metrics["cop_uses_cumulative_fallback"])
        self.assertIsNone(self.est.metrics["last_cop_at"])
        self.assertIsNone(self.est.metrics["live_cop"])
        self.assertFalse(self.est.metrics["cop_certified"])
        new_est = mod.HydraulicCopEstimator()
        self.assertTrue(new_est.restore_accumulated(self.est.export_accumulated()))
        self.assertEqual(new_est.metrics["cop"], 9.44)

    def test_legacy_multiple_intervals_must_be_labeled_aggregate_not_last(self):
        self.assertTrue(self.est.accumulator.add("CO", .4, .1, 600))
        self.assertTrue(self.est.accumulator.add("CO", .4, .2, 600))
        self.est.invalidate()
        self.assertEqual(self.est.metrics["cop"], 2.67)
        self.assertEqual(self.est.metrics["cop_display_source"],
                         "zastepczy_cop_skumulowany_bez_daty")
        self.assertIsNone(self.est.metrics["last_cop"])

    def test_legacy_fallback_is_replaced_by_witnessed_accepted_window(self):
        self.assertTrue(self.est.accumulator.add("CO", .491, .052, 360))
        self.est.invalidate()
        self.run_valid_co_window()
        self.assertFalse(self.est.metrics["cop_uses_cumulative_fallback"])
        self.assertEqual(self.est.metrics["last_cop_at"],
                         (self.t+timedelta(minutes=18)).isoformat())
        self.assertEqual(self.est.accumulated_intervals, 2)

    def test_empty_history_is_unknown_not_invented(self):
        self.est.invalidate()
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.metrics["cop_display_source"], "brak")

    def test_stale_meter_is_seed_not_confirmed_power_draw(self):
        self.est.ingest(capture(self.t, electric_age=3600), self.t)
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_czekamy_na_pierwszy_zaobserwowany_skok_licznika")
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.accumulated_intervals, 0)

    def test_old_meter_without_real_increment_never_generates_cop(self):
        self.est.ingest(capture(self.t, electric_age=3600), self.t)
        when = self.t+timedelta(minutes=3)
        self.est.ingest(capture(
            when, electric_age=3780,
            supply_age=11217, return_age=11515,
        ), when)
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertIsNone(self.est.metrics["cop"])

    def test_reset_or_invalid_vendor_last_change_blocks(self):
        self.est.ingest(capture(self.t), self.t)
        when = self.t+timedelta(minutes=3)
        self.est.ingest(capture(
            when, co=9000, supply_age=11217, return_age=11515,
        ), when)
        self.assertEqual(self.est.metrics["status"], "okno_energii_reset_licznika")
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.est.ingest(capture(self.t), self.t)
        self.est.ingest(capture(
            when, co=10095, electric_age=210,
            supply_age=11217, return_age=11515,
        ), when)
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_niespojny_czas_skoku_licznika")
        self.assertIsNone(self.est.metrics["cop"])

    def test_opt_in_required_for_distinct_device_modules(self):
        est = mod.HydraulicCopEstimator()
        est.ingest(capture(self.t), self.t)
        self.assertEqual(est.metrics["status"], "niepotwierdzone_powiazanie_obiegu")

    def test_opt_in_also_required_for_temperature_older_than_15m(self):
        est = mod.HydraulicCopEstimator()
        est.ingest(capture(self.t, separate=False), self.t)
        self.assertEqual(est.metrics["status"],
                         "stare_znaczniki_temperatur_wymagaja_opt_in")

    def test_temperature_older_than_12h_is_rejected(self):
        self.est.ingest(capture(
            self.t, supply_age=45000, return_age=45300,
        ), self.t)
        self.assertEqual(self.est.metrics["status"],
                         "nieaktualne_pomiary_hydrauliczne")
        self.assertIsNone(self.est.metrics["cop"])

    def test_flow_older_than_15m_is_rejected(self):
        self.est.ingest(capture(self.t, flow_age=1500), self.t)
        self.assertEqual(self.est.metrics["status"], "nieaktualny_przeplyw")

    def test_missing_timestamp_fails_closed(self):
        devices = capture(self.t)
        del devices[1]["updated_at"][116]
        self.est.ingest(devices, self.t)
        self.assertEqual(self.est.metrics["status"],
                         "brak_znacznikow_zmiany_wartosci")

    def test_small_or_negative_delta_t_never_counted(self):
        self.est.ingest(capture(self.t, ret=25.25), self.t)
        self.assertEqual(self.est.metrics["status"], "delta_t_za_mala_dla_szacowania_cop")
        self.est.ingest(capture(self.t, ret=26), self.t)
        self.assertEqual(self.est.metrics["status"], "delta_t_za_mala_dla_szacowania_cop")

    def test_off_compressor_or_heater_blocks_and_resets_window(self):
        self.est.ingest(capture(self.t, compressor=False), self.t)
        self.assertEqual(self.est.metrics["status"], "sprezarka_wylaczona")
        self.est.ingest(capture(self.t, heater=True), self.t)
        self.assertEqual(self.est.metrics["status"],
                         "grzalka_cwu_aktywna_niepelny_bilans_pradu")
        self.est.ingest(capture(self.t, auxiliary_raw=3.0), self.t)
        self.assertEqual(self.est.metrics["status"],
                         "grzalka_wspomagajaca_moc_dodatnia_w_zakresie_katalogu")

    def test_raw_id8_3000_not_assumed_live_heater(self):
        self.est.ingest(capture(self.t, auxiliary_raw=3000.0), self.t)
        self.assertIsNone(self.est.metrics["cop"])
        self.assertEqual(self.est.metrics["confidence"], "niska")
        audit = self.est.metrics["heater_evidence"]
        self.assertTrue(audit["uncertain"])
        self.assertFalse(audit["heater_off_confirmed"])

    def test_missing_intermediate_snapshot_blocks_window(self):
        self.observe(0)
        self.observe(3, co=10100, meter_min=3)
        self.observe(6, co=10100, meter_min=3)
        self.observe(18, co=10350, meter_min=18)
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_przerwa_miedzy_snapshotami")

    def test_mode_transition_blocks_interval(self):
        self.observe(0)
        self.observe(3, co=10100, meter_min=3)
        self.observe(6, co=10100, meter_min=3, circuit="CWU")
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_zmiana_trybu_lub_niespojne_czujniki")

    def test_stale_temperatures_cannot_drift_mid_window(self):
        self.observe(0)
        self.observe(3, co=10100, meter_min=3)
        self.observe(6, co=10100, meter_min=3, supply=30)
        self.assertEqual(self.est.accumulated_intervals, 0)
        self.assertEqual(self.est.metrics["status"],
                         "okno_energii_zmiana_trybu_lub_niespojne_czujniki")

    def test_invalid_data_types_rejected_not_published(self):
        self.est.ingest(capture(self.t, flow=True), self.t)
        self.assertEqual(self.est.metrics["status"], "brak_liczbowych_pomiarow")
        self.est.ingest(capture(self.t)+[capture(self.t)[1]], self.t)
        self.assertEqual(self.est.metrics["status"], "brak_jednoznacznych_zrodel")

    def test_no_private_identifiers_enter_published_metrics(self):
        self.est.ingest(capture(self.t), self.t)
        self.assertNotIn("private", str(self.est.metrics))
        self.assertNotIn("private", str(self.est.export_accumulated()))
        self.assertFalse(self.est.metrics["cop_certified"])


if __name__ == "__main__":
    unittest.main()
