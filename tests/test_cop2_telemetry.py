"""Pure offline tests for COP2 local recorder and daily quality gates."""
import importlib.util
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "custom_components/atlantic_cozytouch/cop2_telemetry.py"
spec = importlib.util.spec_from_file_location("cop2_telemetry_independent_tests", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

DAY = datetime(2026, 10, 26, tzinfo=UTC)
NEXT = DAY + timedelta(days=1)
DAILY = {1: {"2026-10-26": 20.0}, 2: {"2026-10-26": 4.0}}


def readings(moment, *, mode="CO", flow=10., supply=35., ret=30.,
             compressor=None, heater=None, cross=False, fail=None):
    t = int(moment.timestamp()) - 30
    interface = {"id": "SENSITIVE_INTERFACE_ID", "name": "PRIVATE_PERSON",
                 "reported_capability_ids": [57, 59, 91, 112],
                 "values": {57: 34984., 59: 12481., 91: mode, 112: flow},
                 "updated_at": {57: t, 59: t, 91: t, 112: t}}
    generator = {"id": "SENSITIVE_GENERATOR_ID" if cross else "SENSITIVE_INTERFACE_ID",
                 "name": "PRIVATE_SERIAL",
                 "reported_capability_ids": [109, 116],
                 "values": {109: supply, 116: ret},
                 "updated_at": {109: t, 116: t}}
    if compressor is not None:
        generator["values"][51] = compressor
        generator["reported_capability_ids"].append(51)
    if heater is not None:
        generator["values"][64] = heater
        generator["reported_capability_ids"].append(64)
    if fail == "old_flow":
        interface["updated_at"][112] = t - 13 * 3600
    if fail == "missing_supply":
        generator["values"].pop(109)
    if fail == "missing_return_date":
        generator["updated_at"].pop(116)
    return [interface, generator]


class Cop2Contract(unittest.TestCase):
    def feed_full_day(self, rec, *, daily=DAILY):
        for i in range(481):
            t = DAY + timedelta(minutes=3*i)
            mode = "CO" if i < 400 else "CWU"
            rec.ingest(readings(t, mode=mode, cross=True), t, daily)
        return rec.result

    def test_no_earlier_day_no_cop2(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        t = NEXT
        rec.ingest(readings(t, cross=True), t, DAILY)
        self.assertEqual(rec.status, "niewystarczajace_pokrycie")
        self.assertIsNone(rec.result["cop2_total"])
        self.assertEqual(rec.result["coverage_pct"], 0)

    def test_full_day_heat_and_electric_same_utc_day(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        result = self.feed_full_day(rec)
        self.assertEqual(result["day_utc"], "2026-10-26")
        self.assertGreater(result["coverage_pct"], 99)
        self.assertLess(result["coverage_pct"], 100)
        self.assertGreater(result["estimated_thermal_co_kwh"], 65)
        self.assertGreater(result["estimated_thermal_cwu_kwh"], 12)
        self.assertTrue(3 < result["cop2_co"] < 4)
        self.assertTrue(3 < result["cop2_cwu"] < 4)
        self.assertTrue(3 < result["cop2_total"] < 4)
        self.assertEqual(result["status"], "szacunek_niska_pewnosc")
        self.assertEqual(result["unknown_compressor_pct"], 100)
        self.assertTrue(result["not_vendor_cop"])

    def _partial_day(self, sample_count):
        rec = mod.Cop2Telemetry(allow_cross=True)
        for i in range(sample_count):
            t = DAY + timedelta(minutes=i*3)
            rec.ingest(readings(t, mode="CO" if i < 300 else "CWU", cross=True),
                       t, DAILY)
        rec.evaluate(DAILY, NEXT)
        return rec

    def test_cop2_accepts_exactly_80_percent_observed_day_as_low_trust(self):
        # 384 intervals x 180 seconds = exactly 69,120 seconds = 80%.
        rec = self._partial_day(385)
        result = rec.result
        self.assertEqual(result["covered_seconds"], 69120)
        self.assertEqual(result["coverage_pct"], 80.0)
        self.assertEqual(result["minimum_coverage_pct"], 80)
        self.assertEqual(result["missing_seconds"], 17280)
        self.assertEqual(result["status"], "szacunek_niepelna_doba_niska_pewnosc")
        self.assertTrue(result["partial_day"])
        self.assertIsNotNone(result["cop2_total"])
        self.assertIsNotNone(result["partial_period_bias_warning"])
        self.assertFalse(result["thermal_energy_extrapolated"])
        self.assertFalse(result["periods_physically_aligned_confirmed"])

    def test_cop2_rejects_just_below_80_percent_without_rounding(self):
        rec = self._partial_day(384)
        result = rec.result
        self.assertLess(result["coverage_pct"], 80.0)
        self.assertEqual(result["status"], "niewystarczajace_pokrycie")
        self.assertIsNone(result["cop2_total"])
        self.assertIsNone(result["estimated_thermal_co_kwh"])
        self.assertFalse(result["partial_day"])

    def test_cop2_near_complete_does_not_get_partial_day_status(self):
        rec = self._partial_day(458)  # 457 * 180 = 95.208% of the day
        self.assertGreaterEqual(rec.result["coverage_pct"], 95)
        self.assertEqual(rec.result["status"], "szacunek_niska_pewnosc")
        self.assertFalse(rec.result["partial_day"])
        self.assertIsNone(rec.result["partial_period_bias_warning"])

    def test_no_automatic_extrapolation_from_80_percent_to_full_day(self):
        shorter = self._partial_day(385)
        full = self._partial_day(481)
        self.assertLess(shorter.result["estimated_thermal_co_kwh"],
                        full.result["estimated_thermal_co_kwh"])
        self.assertEqual(shorter.result["electric_co_kwh"], 20.0)
        self.assertEqual(full.result["electric_co_kwh"], 20.0)
        self.assertTrue(shorter.result["partial_day"])
        self.assertFalse(shorter.result["thermal_energy_extrapolated"])

    def test_coverage_not_guessed_from_discrete_meter_step(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        for i in range(20):
            t = NEXT - timedelta(minutes=3*(20-i))
            rec.ingest(readings(t, cross=True), t, DAILY)
        self.assertLess(rec.result["coverage_pct"], 10)
        self.assertIsNone(rec.result["cop2_total"])

    def test_mode_switch_only_one_transition_interval_excluded(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        a, b = readings(DAY, cross=True), readings(DAY+timedelta(minutes=3), mode="CWU", cross=True)
        x = mod._capture(a, DAY, True)
        y = mod._capture(b, DAY+timedelta(minutes=3), True)
        self.assertIsNone(mod._segment(x, y))

    def test_absent_unique_modules_and_missing_cross_optin(self):
        t = NEXT
        off = mod.Cop2Telemetry()
        off.ingest(readings(t, cross=True), t, DAILY)
        self.assertEqual(off.last_reason, "niepotwierdzone_powiazanie_obiegu")
        on = mod.Cop2Telemetry(allow_cross=True)
        on.ingest(readings(t, cross=True), t, DAILY)
        self.assertTrue(on.samples[-1]["valid"])
        ambiguous = readings(t, cross=True)
        ambiguous.append(dict(ambiguous[0], id="ANOTHER_INTERFACE"))
        on.ingest(ambiguous, t+timedelta(minutes=3), DAILY)
        self.assertEqual(on.last_reason, "brak_zrodel")

    def test_bad_time_and_hydraulic_freshness_rejected(self):
        t = NEXT
        rec = mod.Cop2Telemetry(allow_cross=True)
        for failure in ("old_flow", "missing_supply", "missing_return_date"):
            rec.ingest(readings(t, cross=True, fail=failure), t, DAILY)
            self.assertFalse(rec.samples[-1]["valid"])
            self.assertNotEqual(rec.samples[-1]["reason"], "ok_niska_pewnosc")
            t += timedelta(minutes=3)
        with self.assertRaises(ValueError):
            rec.ingest(readings(t, cross=True), t.replace(tzinfo=None), DAILY)

    def test_heater_active_blocks_and_compressor_off_zero(self):
        t = DAY
        x = mod._capture(readings(t, cross=True, heater=True), t, True)
        self.assertFalse(x["valid"])
        x = mod._capture(readings(t, cross=True, compressor=False), t, True)
        y = mod._capture(readings(t+timedelta(minutes=3), cross=True, compressor=False),
                         t+timedelta(minutes=3), True)
        self.assertEqual(mod._segment(x,y), ("CO", 0.0, False))
        on = mod._capture(readings(t+timedelta(minutes=3), cross=True, compressor=True),
                          t+timedelta(minutes=3), True)
        self.assertIsNone(mod._segment(x, on))

    def test_missing_cwu_daily_not_assumed_zero_and_revision_recalculates(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        self.feed_full_day(rec)
        old = rec.result["cop2_co"]
        rec.evaluate({1: {"2026-10-26": 25.0}}, NEXT)
        self.assertEqual(rec.status, "brak_pelnej_energii_elektrycznej")
        self.assertIsNone(rec.result["cop2_total"])
        self.assertIsNone(rec.result["cop2_cwu"])
        self.assertLess(rec.result["cop2_co"], old)

    def test_retention_dedup_and_privacy_after_restart(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        t = NEXT
        for idx in range(6):
            dt = t + timedelta(minutes=idx*3)
            rec.ingest(readings(dt, cross=True), dt, DAILY)
        saved = rec.export()
        data = json.dumps(saved)
        for sensitive in ("SENSITIVE_INTERFACE_ID", "SENSITIVE_GENERATOR_ID",
                          "PRIVATE_SERIAL", "PRIVATE_PERSON", "access_token"):
            self.assertNotIn(sensitive, data)
        other = mod.Cop2Telemetry()
        other.restore(saved, now=t+timedelta(hours=1))
        self.assertEqual(len(other.samples), 6)
        self.assertEqual(other.export(), saved)
        other.restore({"schema": 1, "samples": [{"t": "invalid"}]}, now=t)
        self.assertEqual(len(other.samples), 6)  # invalid restore fails closed

    def test_missing_and_too_old_history_not_spliced_after_restart(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        older = NEXT - timedelta(days=15)
        rec.ingest(readings(older, cross=True), older, DAILY)
        newer = NEXT
        rec.ingest(readings(newer, cross=True), newer, DAILY)
        self.assertEqual(len(rec.samples), 1)
        persist = mod.Cop2Telemetry(allow_cross=True)
        persist.restore(rec.export(), now=newer)
        later = newer + timedelta(hours=12)
        persist.ingest(readings(later, cross=True), later, DAILY)
        self.assertEqual(persist.result["coverage_pct"], 0)
        self.assertIsNone(persist.result["cop2_total"])

    def test_no_false_cop_when_heat_negative(self):
        rec = mod.Cop2Telemetry(allow_cross=True)
        for i in range(481):
            dt = DAY + timedelta(minutes=i*3)
            mode = "CO" if i < 400 else "CWU"
            rec.ingest(readings(dt, cross=True, mode=mode, supply=30., ret=35.), dt, DAILY)
        self.assertEqual(rec.status, "nieprawidlowy_bilans_lub_licznik")
        self.assertIsNone(rec.result["cop2_total"])

if __name__ == "__main__":
    unittest.main()
