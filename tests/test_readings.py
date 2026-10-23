"""Offline regression tests that do not require HA or real Atlantic credentials."""

import ast
from pathlib import Path
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
READINGS = ROOT / "custom_components" / "atlantic_cozytouch" / "readings.py"
API = ROOT / "custom_components" / "atlantic_cozytouch" / "api.py"
INIT = ROOT / "custom_components" / "atlantic_cozytouch" / "__init__.py"
SENSOR = ROOT / "custom_components" / "atlantic_cozytouch" / "sensor.py"
BINARY_SENSOR = ROOT / "custom_components" / "atlantic_cozytouch" / "binary_sensor.py"

# Standalone load, avoiding importing Home Assistant in unit tests.
spec = importlib.util.spec_from_file_location("atlantic_readings_unit_test", READINGS)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class TestReadings(unittest.TestCase):
    def test_sanitizes_only_known_capabilities(self):
        sample = [{
            "devices": [{
                "deviceId": 987,
                "name": "Pompa",
                "capabilities": [
                    {"capabilityId": 24, "value": "21"},
                    {"capabilityId": 51, "value": "1"},
                    {"capabilityId": 119, "value": "5.5"},
                    {"capabilityId": 123456789, "value": "unknown"},
                ],
            }]
        }]
        data = module.extract_devices(sample)
        self.assertEqual(data[0]["values"], {24: 21.0, 51: True, 119: 5.5})
        self.assertNotIn(123456789, data[0]["values"])

    def test_energy_in_watt_hours_converted_to_kwh(self):
        self.assertEqual(module.normalize_value(44, 12345), 12.345)
        self.assertEqual(module.normalize_value(45, "500"), 0.5)
        self.assertEqual(module.normalize_value(46, 0), 0.0)
        for capability in (44, 45, 46):
            spec = module.CAPABILITIES[capability]
            self.assertEqual(spec.unit, "kWh")
            self.assertEqual(spec.category, "energy")
            self.assertTrue(spec.cumulative)

    def test_not_available_handled(self):
        self.assertIsNone(module.normalize_value(24, "---"))
        self.assertIsNone(module.normalize_value(51, "unrecognized"))
        self.assertIsNone(module.normalize_value(119, -327.68))
        self.assertIsNone(module.normalize_value(24, "nan"))
        with self.assertRaises(ValueError):
            module.extract_devices({"devices": []})

    def test_does_not_process_abnormally_large_api_response(self):
        with self.assertRaises(ValueError):
            module.extract_devices([{"devices": [{"deviceId": i} for i in range(129)]}])
        with self.assertRaises(ValueError):
            module.extract_devices([{"devices": [{"deviceId": 7, "capabilities": [
                {"capabilityId": 24, "value": 1} for _ in range(1025)
            ]}]}])

    def test_rejects_malformed_device_ids(self):
        result = module.extract_devices([{"devices": [
            {"deviceId": chr(0) + "bad", "capabilities": [{"capabilityId": 24, "value": 1}]},
            {"deviceId": True, "capabilities": [{"capabilityId": 24, "value": 1}]},
            {"deviceId": 7, "capabilities": [{"capabilityId": 24, "value": 1}]},
        ]}])
        self.assertEqual([dev["id"] for dev in result], ["7"])

    def test_has_sought_diagnostics(self):
        for cap_id in (24, 27, 51, 72):
            self.assertIn(cap_id, module.CAPABILITIES)


class TestNoWriteSurface(unittest.TestCase):
    def test_only_token_post_and_setup_get(self):
        tree = ast.parse(API.read_text(encoding="utf-8"))
        calls = []
        for parent in ast.walk(tree):
            if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute):
                if parent.func.attr in {"get", "post", "patch", "put", "delete", "request"}:
                    calls.append(parent.func.attr)
        # .get() on dictionaries is harmless; check actual HTTP session calls precisely.
        session_methods = [
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "_session"
        ]
        self.assertCountEqual(session_methods, ["post", "get"])
        self.assertNotIn("patch", session_methods)
        self.assertNotIn("put", session_methods)
        self.assertNotIn("delete", session_methods)

    def test_endpoints_are_exactly_vendor_cloud(self):
        const = (ROOT / "custom_components" / "atlantic_cozytouch" / "const.py").read_text(encoding="utf-8")
        self.assertIn('API_ORIGIN = "https://apis.groupe-atlantic.com"', const)
        self.assertIn('TOKEN_PATH = "/users/token"', const)
        self.assertIn('READ_PATH = "/magellan/cozytouch/setupviewv2"', const)
        client = API.read_text(encoding="utf-8")
        self.assertIn('options["allow_redirects"] = False', client)
        self.assertNotIn("ssl=False", client)
        self.assertNotIn("verify_ssl=False", client)

    def test_only_read_only_ha_platforms(self):
        root = INIT.read_text(encoding="utf-8")
        self.assertIn("Platform.SENSOR, Platform.BINARY_SENSOR", root)
        self.assertNotIn("Platform.SWITCH", root)
        self.assertNotIn("Platform.CLIMATE", root)
        self.assertNotIn("async_register", root)
        for path in (SENSOR, BINARY_SENSOR):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("async_turn_on", content)
            self.assertNotIn("async_set_", content)


if __name__ == "__main__":
    unittest.main()
