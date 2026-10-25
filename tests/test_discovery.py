"""Standalone test suite for capability discovery and diagnostics redaction."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "atlantic_cozytouch"
pkg = types.ModuleType("test_discovery_pkg")
pkg.__path__ = [str(ROOT)]
sys.modules[pkg.__name__] = pkg
for name in ("readings", "discovery"):
    fq = f"{pkg.__name__}.{name}"
    spec = importlib.util.spec_from_file_location(fq, ROOT / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[fq] = mod
    spec.loader.exec_module(mod)
from test_discovery_pkg.discovery import compressor_host_devices, new_capabilities, redacted_inventory, inventory_summary


class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.devices = [{
            "id": "DO_NOT_EXPORT_SERIAL", "name": "DO_NOT_EXPORT_NAME",
            "reported_capability_ids": [24, 27, 51, 72, 100506],
            "values": {24: 21, 51: True, 27: 32400},
        }]

    def test_discovered_unknown_ids_cannot_become_entities(self):
        seen = set()
        sensors = new_capabilities(self.devices, "sensor", seen)
        self.assertEqual({cap for _, cap in sensors}, {24, 27})
        binaries = new_capabilities(self.devices, "binary", seen)
        self.assertEqual({cap for _, cap in binaries}, {51})
        self.assertEqual(new_capabilities(self.devices, "sensor", {("DO_NOT_EXPORT_SERIAL", 24), ("DO_NOT_EXPORT_SERIAL", 27)}), [])

    def test_diagnostics_only_identifiers_no_values_or_identity(self):
        result = redacted_inventory(self.devices)
        self.assertEqual(result[0]["compressor_capability_ids"], [24, 27, 51, 72])
        self.assertEqual(result[0]["unmapped_capability_ids"], [100506])
        raw = str(result)
        for secret in ("DO_NOT_EXPORT_", "32400", "SERIAL", "NAME"):
            self.assertNotIn(secret, raw)

    def test_thermal_controller_remains_compressor_host_without_vendor_counters(self):
        devices = [
            {"id": "heat_pump", "reported_capability_ids": [91, 112, 109]},
            {"id": "room", "reported_capability_ids": [117, 181]},
        ]
        self.assertEqual([x["id"] for x in compressor_host_devices(devices)], ["heat_pump"])
        # Reporting additional compressor IDs doesn't duplicate the host.
        devices[0]["reported_capability_ids"].extend([24, 51])
        self.assertEqual(len(compressor_host_devices(devices)), 1)

    def test_real_compressor_without_hydraulic_ids_is_recognized(self):
        self.assertEqual(
            len(compressor_host_devices([{"id": "hp", "reported_capability_ids": [27]}])),
            1,
        )
        self.assertEqual(
            compressor_host_devices([{"id": "room", "reported_capability_ids": [153, 181]}]),
            [],
        )

    def test_summary(self):
        result = inventory_summary(self.devices)
        self.assertEqual(result, {
            "reported_count": 5, "known_count": 4, "unmapped_count": 1, "device_count": 1,
        })

    def test_new_capability_becomes_entity_after_next_poll(self):
        seen = {("DO_NOT_EXPORT_SERIAL", 24), ("DO_NOT_EXPORT_SERIAL", 27)}
        self.devices[0]["values"][72] = 45
        result = new_capabilities(self.devices, "sensor", seen)
        self.assertEqual([x[1] for x in result], [72])


if __name__ == "__main__":
    unittest.main()
