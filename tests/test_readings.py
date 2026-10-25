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

    def test_inactive_temperature_sentinel_and_normal_values(self):
        for cap in (109, 110, 111, 117, 118, 119):
            for invalid in (-273.15, "-273,2", -327.68):
                self.assertIsNone(module.normalize_value(cap, invalid))
            self.assertEqual(module.normalize_value(cap, 33.3), 33.3)
        self.assertEqual(module.normalize_value(119, -55), -55.0)
        self.assertIsNone(module.normalize_value(109, 999))

    def test_capability_inventory_keeps_ids_not_unmapped_values(self):
        payload = [{"devices": [{"deviceId": 55, "name": "Test", "capabilities": [
            {"capabilityId": 109, "value": -273.15},
            {"capabilityId": 1234, "value": "PRIVATE_NEVER_SAVE_THIS_VALUE"},
            {"capabilityId": 24, "value": 21},
        ]}]}]
        device = module.extract_devices(payload)[0]
        self.assertEqual(device["reported_capability_ids"], [24, 109, 1234])
        self.assertIsNone(device["values"][109])
        self.assertNotIn(1234, device["values"])
        self.assertNotIn("PRIVATE_NEVER_SAVE_THIS_VALUE", str(device))

    def test_large_vendor_capability_ids_are_retained_in_inventory(self):
        payload = [{"devices": [{"deviceId": "s", "capabilities": [
            {"capabilityId": 100506, "value": "must not be exported"},
            {"capabilityId": 2147483648, "value": "out of bounded range"},
        ]}]}]
        devices = module.extract_devices(payload)
        self.assertEqual(devices[0]["reported_capability_ids"], [100506])
        self.assertNotIn("must not be exported", str(devices))

    def test_44_45_46_are_gas_not_electricity_and_have_no_statistics(self):
        # Vendor's Magellan_ProductModels catalogue: HOME_Gaz*ConsumptionCumulated.
        # Do not continue populating HA electricity statistics with gas counters.
        self.assertEqual(module.normalize_value(44, 12345), 12345)
        self.assertEqual(module.normalize_value(45, "500"), 500)
        self.assertEqual(module.normalize_value(46, 0), 0.0)
        for cap_id in (44, 45, 46):
            spec = module.CAPABILITIES[cap_id]
            self.assertIn("Gaz", spec.title)
            self.assertIsNone(spec.unit)
            self.assertIsNone(spec.category)
            self.assertFalse(spec.publish_statistics)
            self.assertTrue(spec.diagnostic)
            self.assertIsNone(module.normalize_value(cap_id, -2))

    def test_compressor_modulation_timestamp_is_parsed_safely(self):
        payload = [{"devices": [{
            "deviceId": "pump",
            "capabilities": [
                {"capabilityId": 72, "value": "36", "modificationDate": 1792900000},
                {"capabilityId": 51, "value": "1", "modificationDate": 1792900000},
                {"capabilityId": 109, "value": "31", "modificationDate": "SECRET"},
            ],
        }]}]
        device = module.extract_devices(payload)[0]
        self.assertEqual(device["updated_at"][72], 1792900000)
        self.assertEqual(device["updated_at"][51], 1792900000)
        self.assertNotIn(109, device["updated_at"])
        self.assertEqual(device["values"][51], True)

    def test_new_read_only_operating_modes(self):
        self.assertEqual(module.normalize_value(91, "1"), "CO")
        self.assertEqual(module.normalize_value(91, 3), "CWU")
        self.assertIsNone(module.normalize_value(91, 5))
        self.assertEqual(module.normalize_value(153, "1"), "Ogrzewanie")
        self.assertIsNone(module.normalize_value(153, "999"))
        self.assertEqual(module.normalize_value(181, "4"), "Ogrzewanie")
        self.assertEqual(module.normalize_value(99, 0), False)
        self.assertIsNone(module.normalize_value(99, "private text"))

    def test_energy_probe_is_unscaled_and_has_no_statistics(self):
        for cap in (57, 59, 60):
            self.assertEqual(module.normalize_value(cap, "12345.6"), 12345.6)
            self.assertIsNone(module.normalize_value(cap, -1))
            spec = module.CAPABILITIES[cap]
            self.assertIsNone(spec.unit)
            self.assertIsNone(spec.category)
            self.assertFalse(spec.publish_statistics)
            self.assertTrue(spec.diagnostic)
            self.assertFalse(spec.cumulative)
        self.assertEqual(module.normalize_value(112, 9.5), 9.5)
        self.assertIsNone(module.normalize_value(112, -5))
        self.assertFalse(module.CAPABILITIES[112].publish_statistics)

    def test_known_modes_and_values_are_sanitized(self):
        sample = [{"devices": [{
            "deviceId": 1, "name": "Atlantic",
            "capabilities": [
                {"capabilityId": 91, "value": "3"},
                {"capabilityId": 153, "value": "1"},
                {"capabilityId": 57, "value": 123456},
                {"capabilityId": 59, "value": "SECRET_PRIVATE_VALUE"},
                {"capabilityId": 112, "value": "5,5"},
                {"capabilityId": 335, "value": "DO_NOT_EXPORT_SERIAL"},
            ],
        }]}]
        result = module.extract_devices(sample)[0]
        self.assertEqual(result["values"][91], "CWU")
        self.assertEqual(result["values"][57], 123456)
        self.assertIsNone(result["values"][59])
        self.assertEqual(result["values"][112], 5.5)
        self.assertNotIn("DO_NOT_EXPORT_SERIAL", str(result))

    def test_energy_value_status_reasons_without_raw_text(self):
        classify = module.energy_value_status
        self.assertEqual(classify(None), "missing")
        self.assertEqual(classify("   "), "empty")
        self.assertEqual(classify("---"), "empty")
        self.assertEqual(classify("unknown"), "empty")
        self.assertEqual(classify("user@example.invalid SECRET"), "invalid_format")
        self.assertEqual(classify("nan"), "out_of_range")
        self.assertEqual(classify("inf"), "out_of_range")
        self.assertEqual(classify("-10"), "negative")
        self.assertEqual(classify(True), "invalid_format")
        self.assertEqual(classify("11581.0"), "valid")
        self.assertEqual(classify("6,571"), "valid")

    def test_parser_discards_invalid_id60_contents(self):
        payload = [{"devices": [{
            "deviceId": "device",
            "capabilities": [
                {"capabilityId": 57, "value": "11581"},
                {"capabilityId": 59, "value": "6571"},
                {"capabilityId": 60, "value": "SECRET_PRIVATE_TEXT"},
            ],
        }]}]
        result = module.extract_devices(payload)[0]
        self.assertEqual(result["energy_status"], {
            57: "valid", 59: "valid", 60: "invalid_format"
        })
        self.assertIsNone(result["values"][60])
        self.assertNotIn("SECRET_PRIVATE_TEXT", str(result))

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
