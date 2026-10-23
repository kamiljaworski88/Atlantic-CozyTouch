"""Offline contract tests of the actual Home Assistant daily sensor class.

Only the class is compiled from source so this runs without HA installed.
Official container import test separately checks all HA imports.
"""
from __future__ import annotations

import ast
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
import unittest

FILE = (Path(__file__).resolve().parents[1]
        / "custom_components" / "atlantic_cozytouch" / "sensor.py")


class FakeCoordinatorEntity:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    @property
    def available(self):
        return self.coordinator.last_update_success


class SensorEntity:
    pass


class FrozenDatetime:
    """Run at 2026-10-23 20:00 UTC for repeatable tests."""
    @staticmethod
    def now(zone):
        return datetime(2026, 10, 23, 20, tzinfo=zone)

    @staticmethod
    def combine(day, t, tzinfo):
        return datetime.combine(day, t, tzinfo=tzinfo)


def load_sensor():
    tree = ast.parse(FILE.read_text(encoding="utf-8"))
    sensor = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "AtlanticDailyElectricitySensor"
    )
    code = ast.Module(body=[sensor], type_ignores=[])
    ast.fix_missing_locations(code)
    namespace = {
        "CoordinatorEntity": FakeCoordinatorEntity,
        "SensorEntity": SensorEntity,
        "SensorDeviceClass": SimpleNamespace(ENERGY="energy"),
        "SensorStateClass": SimpleNamespace(TOTAL="total"),
        "datetime": FrozenDatetime, "UTC": UTC,
        "timedelta": timedelta, "time": time,
        "DOMAIN": "atlantic_cozytouch",
    }
    exec(compile(code, str(FILE), "exec"), namespace)
    return namespace["AtlanticDailyElectricitySensor"]


class TestDailySensorContract(unittest.TestCase):
    def setUp(self):
        self.cls = load_sensor()
        self.coord = SimpleNamespace(
            last_update_success=True,
            atlantic_consumptions={"state": "dostepna"},
            atlantic_daily_energy={
                1: {"2026-10-22": 1.0, "2026-10-23": 2.5},
                2: {"2026-10-22": 0.5, "2026-10-23": 1.25},
            },
        )

    def test_today_reset_and_history(self):
        sensor = self.cls(self.coord, "ENTRY", 1, 0)
        self.assertEqual(sensor.native_value, 2.5)
        self.assertEqual(sensor._attr_state_class, "total")
        self.assertEqual(sensor.last_reset, datetime(2026, 10, 23, tzinfo=UTC))
        self.assertEqual(sensor.extra_state_attributes["dzien_utc"], "2026-10-23")
        self.assertEqual(sensor._attr_unique_id,
                         "atlantic_cozytouch_ENTRY_energy_daily_co_today")
        self.assertEqual(len(sensor.extra_state_attributes["historia_ostatnich_7_dni_utc"]), 2)

    def test_yesterday_is_historical_not_a_meter(self):
        sensor = self.cls(self.coord, "ENTRY", 2, 1)
        self.assertEqual(sensor.native_value, 0.5)
        self.assertIsNone(sensor.last_reset)
        self.assertFalse(hasattr(sensor, "_attr_state_class"))
        self.assertNotIn("historia_ostatnich_7_dni_utc", sensor.extra_state_attributes)

    def test_stale_or_missing_data_never_becomes_zero(self):
        sensor = self.cls(self.coord, "ENTRY", 1, 0)
        del self.coord.atlantic_daily_energy[1]["2026-10-23"]
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)
        self.assertIsNone(sensor.last_reset)
        self.coord.atlantic_daily_energy[1]["2026-10-23"] = 2.5
        self.coord.atlantic_consumptions = {"state": "blad_http"}
        self.assertFalse(sensor.available)
        self.assertIsNone(sensor.native_value)
        self.coord.atlantic_consumptions = {"state": "dostepna"}
        self.coord.last_update_success = False
        self.assertFalse(sensor.available)

    def test_category_and_offset_allowlist(self):
        for cat, offset in ((0, 0), (3, 0), (1, 2)):
            with self.assertRaises(ValueError):
                self.cls(self.coord, "ENTRY", cat, offset)


if __name__ == "__main__":
    unittest.main()
