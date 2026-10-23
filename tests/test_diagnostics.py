"""Privacy tests for the real HA diagnostics handler, run without HA installed."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "custom_components" / "atlantic_cozytouch" / "diagnostics.py"


def load_handler():
    """Compile the real handler only; stub dependency names instead of HA."""
    tree = ast.parse(DIAGNOSTICS.read_text(encoding="utf-8"))
    func = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                and n.name == "async_get_config_entry_diagnostics")
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        func,
    ], type_ignores=[])
    ast.fix_missing_locations(module)
    # Execute the real redaction helper rather than mocking it.
    import importlib.util
    import sys
    import types
    pkg = types.ModuleType("privacy_test_pkg")
    pkg.__path__ = [str(ROOT / "custom_components" / "atlantic_cozytouch")]
    sys.modules[pkg.__name__] = pkg
    for name in ("readings", "discovery"):
        fq = f"{pkg.__name__}.{name}"
        spec = importlib.util.spec_from_file_location(fq, Path(pkg.__path__[0]) / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[fq] = mod
        spec.loader.exec_module(mod)
    from privacy_test_pkg.discovery import redacted_inventory
    globals_ = {"DOMAIN": "atlantic_cozytouch", "redacted_inventory": redacted_inventory}
    exec(compile(module, str(DIAGNOSTICS), "exec"), globals_)
    return globals_["async_get_config_entry_diagnostics"]


class TestDiagnosticsPrivacy(unittest.IsolatedAsyncioTestCase):
    async def test_returns_ids_and_counts_never_values_or_secrets(self):
        handler = load_handler()
        entry = SimpleNamespace(entry_id="EXAMPLE_PRIVATE_ENTRY",
                                data={"username": "user@example.invalid", "password": "SECRET_PASSWORD"})
        coordinator = SimpleNamespace(
            last_update_success=True,
            data=[{
                "id": "PRIVATE_DEVICE_123",
                "name": "PRIVATE_ROOM_NAME",
                "gatewaySerialNumber": "PRIVATE_SERIAL_888",
                "values": {24: "SECRET_VALUE", 109: 33.3},
                "reported_capability_ids": [24, 109, 555],
            }],
        )
        hass = SimpleNamespace(data={"atlantic_cozytouch": {entry.entry_id: coordinator}})
        report = await handler(hass, entry)

        self.assertEqual(report["device_capability_inventory"], [{
            "index": 1,
            "reported_count": 3,
            "known_capability_ids": [24, 109],
            "unmapped_capability_ids": [555],
            "compressor_capability_ids": [24],
        }])
        self.assertTrue(report["last_poll_ok"])
        self.assertEqual(report["diagnostics_format"], 5)
        self.assertEqual(report["energy_validation"], [])
        self.assertEqual(report["consumption_probe"], {"state": "nie_sprawdzono"})
        dumped = json.dumps(report, ensure_ascii=False)
        for secret in ("SECRET_", "PRIVATE_", "user@example", "33.3", "gatewaySerial", "password"):
            self.assertNotIn(secret, dumped)

    async def test_report_reveals_only_energy_status_not_energy_values(self):
        import importlib.util
        from datetime import datetime, timezone

        spec = importlib.util.spec_from_file_location(
            "energy_privacy_diagnostics_test",
            ROOT / "custom_components" / "atlantic_cozytouch" / "energy_validation.py"
        )
        mod = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)

        readings = [{
            "id": "PRIVATE_DEVICE_ID",
            "name": "PRIVATE_DEVICE_NAME",
            "reported_capability_ids": [57, 59, 60],
            "values": {57: 11581, 59: 6571, 60: None},
            "energy_status": {57: "valid", 59: "valid", 60: "empty"},
        }]
        monitor = mod.EnergyValidationMonitor()
        monitor.ingest(readings, datetime(2026, 10, 23, tzinfo=timezone.utc))
        coordinator = SimpleNamespace(
            data=readings, last_update_success=True, atlantic_energy=monitor
        )
        entry = SimpleNamespace(
            entry_id="PRIVATE_ENTRY", data={"password": "PRIVATE_PASSWORD"}
        )
        hass = SimpleNamespace(data={"atlantic_cozytouch": {entry.entry_id: coordinator}})
        report = await load_handler()(hass, entry)
        self.assertEqual(report["energy_validation"], [{
            "index": 1,
            "energy_ids": {
                "57": {"value_status": "valid", "comparison": "first_sample"},
                "59": {"value_status": "valid", "comparison": "first_sample"},
                "60": {"value_status": "empty", "comparison": "not_applicable"},
            },
        }])
        for private_value in ("PRIVATE_", "11581", "6571", "password"):
            self.assertNotIn(private_value, json.dumps(report, ensure_ascii=False))

    async def test_no_device_snapshot_retained_after_failure(self):
        handler = load_handler()
        entry = SimpleNamespace(entry_id="e", data={"password": "SECRET"})
        coordinator = SimpleNamespace(data=None, last_update_success=False)
        hass = SimpleNamespace(data={"atlantic_cozytouch": {"e": coordinator}})
        report = await handler(hass, entry)
        self.assertEqual(report["device_capability_inventory"], [])
        self.assertFalse(report["last_poll_ok"])


if __name__ == "__main__":
    unittest.main()
