"""No-cloud, no-credential HTTP security regression tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "atlantic_cozytouch"

# Avoid importing Home Assistant and avoid all real HTTP calls.
aiohttp = types.ModuleType("aiohttp")
aiohttp.ClientError = type("ClientError", (Exception,), {})
aiohttp.ClientTimeout = lambda **kwargs: kwargs
aiohttp.FormData = lambda data: data
sys.modules.setdefault("aiohttp", aiohttp)

package = types.ModuleType("atlantic_cozytouch")
package.__path__ = [str(PACKAGE)]
sys.modules["atlantic_cozytouch"] = package

for module_name in ("const", "readings", "api"):
    fq_name = f"atlantic_cozytouch.{module_name}"
    spec = importlib.util.spec_from_file_location(fq_name, PACKAGE / f"{module_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fq_name] = module
    spec.loader.exec_module(module)

from atlantic_cozytouch.api import (
    AtlanticAuthError,
    AtlanticError,
    AtlanticRateLimited,
    AtlanticReadOnlyClient,
)
from atlantic_cozytouch.const import API_ORIGIN, READ_PATH, TOKEN_PATH


class Reply:
    def __init__(self, status: int, payload: object, headers=None) -> None:
        self.status = status
        self.payload = payload
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    """Records HTTP operations; never connects to a real server."""

    def __init__(self, *, login_status=200, read_status=200, headers=None, setup_payload=None, token_payload=None):
        self.calls = []
        self.login_status = login_status
        self.read_status = read_status
        self.headers = headers or {}
        self.token_payload = token_payload if token_payload is not None else {"access_token": "FAKE_UNIT_TEST_TOKEN", "expires_in": 3600}
        self.setup_payload = setup_payload if setup_payload is not None else [{
            "devices": [{
                "deviceId": 9,
                "name": "Simulated pump",
                "capabilities": [
                    {"capabilityId": 24, "value": "21"},
                    {"capabilityId": 44, "value": "5000"},
                    {"capabilityId": 51, "value": "1"},
                ],
            }]
        }]

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Reply(
            self.login_status,
            self.token_payload,
            headers=self.headers,
        )

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Reply(self.read_status, self.setup_payload, headers=self.headers)


class ConsumptionSession(Session):
    """Simulated daily series; no real account or Internet connection."""

    def __init__(self, *, status=200, consumption_payload=None, setup_id=123):
        super().__init__(setup_payload=[{
            "id": setup_id,
            "devices": [{"deviceId": 9, "capabilities": [
                {"capabilityId": 164, "value": "1298"},
            ]}],
        }])
        self.consumption_status = status
        self.consumption_payload = consumption_payload if consumption_payload is not None else [{
            "type": 1, "unit": 1, "deviceId": "NEVER_EXPORT",
            "consumptionPeriods": [{
                "consumedQuantity": 9.9, "producedQuantity": 23.4,
                "date": 1788825600,
            }],
        }]

    def get(self, url, **kwargs):
        if "/consumptions?periodicity=daily" in url:
            self.calls.append(("GET", url, kwargs))
            return Reply(self.consumption_status, self.consumption_payload)
        return super().get(url, **kwargs)


class TestHttpContract(unittest.IsolatedAsyncioTestCase):
    async def test_authorized_calls_are_exactly_login_and_read(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "test-secret")
        result = await client.async_read()
        self.assertEqual(result[0]["values"][44], 5000.0)  # raw GAS, not /1000 kWh electricity
        self.assertEqual(result[0]["values"][24], 21.0)
        self.assertTrue(result[0]["values"][51])
        self.assertEqual(
            [(method, url) for method, url, _ in session.calls],
            [("POST", API_ORIGIN + TOKEN_PATH), ("GET", API_ORIGIN + READ_PATH)],
        )
        for _, _, kwargs in session.calls:
            self.assertIs(kwargs["allow_redirects"], False)
            self.assertNotIn("ssl", kwargs)
            self.assertNotIn("proxy", kwargs)

    async def test_second_poll_reuses_token(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_read()
        self.assertEqual([method for method, _, _ in session.calls], ["POST", "GET", "GET"])

    async def test_wrong_http_methods_urls_hosts_are_refused_before_network(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        for method, url in (
            ("POST", API_ORIGIN + READ_PATH),
            ("GET", API_ORIGIN + TOKEN_PATH),
            ("PATCH", API_ORIGIN + READ_PATH),
            ("PUT", API_ORIGIN + "/magellan/v2/setups/1"),
            ("POST", API_ORIGIN + "/magellan/executions/writecapability"),
            ("GET", "https://example.invalid/collect"),
            ("GET", "http://apis.groupe-atlantic.com" + READ_PATH),
            ("GET", API_ORIGIN + READ_PATH + "?debug=true"),
        ):
            with self.subTest(method=method, url=url):
                with self.assertRaises(AtlanticError):
                    client._request(method, url)
        self.assertEqual(session.calls, [])

    async def test_cannot_override_tls_proxy_timeout_or_redirects(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        for kw in (
            {"ssl": False},
            {"proxy": "https://example.invalid"},
            {"auth": "unsafe"},
            {"allow_redirects": True},
            {"timeout": None},
            {"params": {"unexpected": "query"}},
        ):
            with self.subTest(overrides=kw):
                with self.assertRaises(AtlanticError):
                    client._request("GET", API_ORIGIN + READ_PATH, **kw)
        self.assertEqual(session.calls, [])

    async def test_redirect_is_never_followed(self):
        for kwargs in ({"login_status": 302}, {"read_status": 307}):
            with self.subTest(kwargs=kwargs):
                session = Session(**kwargs)
                client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
                with self.assertRaises(AtlanticError):
                    await client.async_read()
                for _, _, options in session.calls:
                    self.assertFalse(options["allow_redirects"])

    async def test_429_starts_cooldown_and_makes_no_immediate_new_request(self):
        for headers in ({}, {"Retry-After": "120"}, {"Retry-After": "36000"},
                        {"Retry-After": "garbage"}):
            with self.subTest(headers=headers):
                session = Session(read_status=429, headers=headers)
                client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
                with self.assertRaises(AtlanticRateLimited):
                    await client.async_read()
                before = list(session.calls)
                with self.assertRaises(AtlanticRateLimited):
                    await client.async_read()
                self.assertEqual(session.calls, before)

    async def test_login_429_is_not_retried(self):
        session = Session(login_status=429)
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticRateLimited):
            await client.async_read()
        with self.assertRaises(AtlanticRateLimited):
            await client.async_read()
        self.assertEqual(len(session.calls), 1)

    async def test_invalid_grant_in_http_200_is_an_auth_error(self):
        session = Session(token_payload={"error": "invalid_grant"})
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticAuthError):
            await client.async_read()
        self.assertEqual([x[0] for x in session.calls], ["POST"])

    async def test_invalid_login_is_not_retried(self):
        session = Session(login_status=401)
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticAuthError):
            await client.async_read()
        self.assertEqual([x[0] for x in session.calls], ["POST"])

    async def test_expired_session_reauths_only_once(self):
        session = Session(read_status=401)
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticAuthError):
            await client.async_read()
        self.assertEqual([x[0] for x in session.calls], ["POST", "GET", "POST", "GET"])

    async def test_malformed_payload_fails_closed(self):
        for payload in ({}, [{"devices": "broken"}]):
            with self.subTest(payload=payload):
                session = Session(setup_payload=payload)
                client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
                with self.assertRaises(AtlanticError):
                    await client.async_read()
                self.assertEqual([x[0] for x in session.calls], ["POST", "GET"])

    async def test_consumption_probe_only_calls_current_setup_exact_get(self):
        session = ConsumptionSession()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_probe_consumptions()
        self.assertEqual(client.consumption_summary["state"], "dostepna")
        self.assertEqual(client.consumption_summary["okresy_z_energia_wyprodukowana"], 1)
        self.assertNotIn("23.4", str(client.consumption_summary))
        target = API_ORIGIN + "/magellan/setups/123/consumptions?periodicity=daily"
        self.assertEqual([(m, u) for m, u, _ in session.calls], [
            ("POST", API_ORIGIN + TOKEN_PATH),
            ("GET", API_ORIGIN + READ_PATH), ("GET", target),
        ])
        await client.async_probe_consumptions()  # 15-minute minimum interval.
        self.assertEqual(len(session.calls), 3)
        for bad in (target + "&admin=true", target.replace("123", "124"),
                    target.replace("daily", "yearly"),
                    API_ORIGIN + "/magellan/executions/writecapability"):
            with self.assertRaises(AtlanticError):
                client._request("GET", bad)
        with self.assertRaises(AtlanticError):
            client._request("POST", target)

    async def test_daily_energy_payload_is_scrubbed_and_keeps_same_http_allowlist(self):
        from datetime import datetime, timezone

        day = int(datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp())
        session = ConsumptionSession(consumption_payload=[
            {"category": 1, "type": 1, "unit": 1, "serialNumber": "PRIVATE_ABC",
             "consumptionPeriods": [{"date": day, "mode": 0,
                                     "consumedQuantity": 2.35, "cost": 99999}]},
            {"category": 2, "type": 1, "unit": 1, "deviceId": "PRIVATE_DEVICE",
             "consumptionPeriods": [{"date": day, "mode": 0,
                                     "consumedQuantity": 1.4}]},
        ])
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_probe_consumptions()
        self.assertEqual(client.energy_daily, {
            1: {"2026-10-23": 2.35},
            2: {"2026-10-23": 1.4},
        })
        self.assertNotIn("PRIVATE", str(client.energy_daily))
        self.assertNotIn("2.35", str(client.consumption_summary))
        self.assertNotIn("99999", str(client.consumption_summary))
        self.assertEqual(len(session.calls), 3)
        await client.async_probe_consumptions()
        self.assertEqual(len(session.calls), 3)

    async def test_change_of_setup_erases_previous_account_energy(self):
        from datetime import datetime, timezone

        day = int(datetime(2026, 10, 23, tzinfo=timezone.utc).timestamp())
        session = ConsumptionSession(consumption_payload=[
            {"category": 1, "type": 1, "unit": 1, "consumptionPeriods": [
                {"date": day, "mode": 0, "consumedQuantity": 6.0}
            ]},
        ])
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_probe_consumptions()
        self.assertEqual(client.energy_daily[1]["2026-10-23"], 6.0)
        session.setup_payload[0]["id"] = 456
        await client.async_read()
        self.assertEqual(client.energy_daily, {})
        self.assertEqual(client.consumption_summary["state"], "nie_sprawdzono")

    async def test_unauthorized_or_missing_history_does_not_break_main_poll(self):
        for status, expected in ((403, "odmowa_dostepu"),
                                 (404, "brak_endpointu"),
                                 (500, "blad_http"),
                                 (429, "limit_zapytan")):
            with self.subTest(status=status):
                session = ConsumptionSession(status=status)
                client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
                devices = await client.async_read()
                await client.async_probe_consumptions()
                self.assertEqual(client.consumption_summary["state"], expected)
                self.assertEqual(devices[0]["values"][164], 1298.0)
                self.assertNotIn("deviceId", str(client.consumption_summary))

    async def test_without_numeric_setup_id_no_probe_get_is_sent(self):
        session = ConsumptionSession(setup_id="not-a-number")
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_probe_consumptions()
        self.assertEqual(client.consumption_summary["state"], "brak_id_instalacji")
        self.assertEqual([m for m, _, _ in session.calls], ["POST", "GET"])


class DeviceCapabilitySession(Session):
    """Mock the *official* per-device GET without network access."""

    def __init__(self, *, device_status=200, direct_caps=None, device_id=9):
        super().__init__(setup_payload=[{
            "id": 123,
            "devices": [{"deviceId": device_id, "name": "Simulated pump",
                         "capabilities": [
                             {"capabilityId": 91, "value": "1"},
                             {"capabilityId": 112, "value": "15.8"},
                         ]}],
        }])
        self.device_status = device_status
        self.direct_caps = direct_caps if direct_caps is not None else [
            {"capabilityId": 24, "value": "50"},
            {"capabilityId": 27, "value": "82800"},
            {"capabilityId": 51, "value": "1"},
            {"capabilityId": 72, "value": "45"},
            {"capabilityId": 99999, "value": "SECRET_DO_NOT_STORE"},
        ]

    def get(self, url, **kwargs):
        if "/magellan/capabilities/?deviceId=" in url:
            self.calls.append(("GET", url, kwargs))
            return Reply(self.device_status, self.direct_caps)
        return super().get(url, **kwargs)


class TestDeviceCompressorProbe(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_whitelist_is_limited_to_authenticated_device(self):
        session = DeviceCapabilitySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
        permitted = API_ORIGIN + "/magellan/capabilities/?deviceId=9"
        with self.assertRaises(AtlanticError):
            client._request("GET", permitted)
        devices = await client.async_read()
        self.assertEqual(devices[0]["values"][91], "CO")
        for method, url in (
            ("POST", permitted),
            ("GET", permitted + "&debug=1"),
            ("GET", API_ORIGIN + "/magellan/capabilities/?deviceId=10"),
            ("GET", "https://example.invalid/magellan/capabilities/?deviceId=9"),
            ("PATCH", permitted),
        ):
            with self.subTest(url=url, method=method), self.assertRaises(AtlanticError):
                client._request(method, url)
        self.assertEqual(len(session.calls), 2)
        await client.async_probe_compressor_capabilities(devices)
        self.assertEqual(client.compressor_probe_summary["state"], "uzupelniono")
        self.assertEqual(
            [(m, u) for m, u, _ in session.calls],
            [
                ("POST", API_ORIGIN + TOKEN_PATH),
                ("GET", API_ORIGIN + READ_PATH),
                ("GET", permitted),
            ],
        )
        self.assertEqual(devices[0]["values"][24], 50)
        self.assertEqual(devices[0]["values"][27], 82800)
        self.assertEqual(devices[0]["values"][51], True)
        self.assertEqual(devices[0]["values"][72], 45)
        self.assertNotIn("SECRET_DO_NOT_STORE", str(devices))
        self.assertNotIn("SECRET_DO_NOT_STORE", str(client.compressor_probe_summary))
        for _m, _u, kwargs in session.calls:
            self.assertEqual(kwargs["allow_redirects"], False)
            self.assertNotIn("proxy", kwargs)

    async def test_bounded_probe_and_cache_after_standard_poll(self):
        session = DeviceCapabilitySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
        original = await client.async_read()
        await client.async_probe_compressor_capabilities(original)
        after = await client.async_read()
        self.assertEqual(after[0]["values"][24], 50)
        self.assertEqual(after[0]["values"][51], True)
        await client.async_probe_compressor_capabilities(after)
        self.assertEqual(len([x for x in session.calls if "/capabilities/?deviceId=" in x[1]]), 1)

    async def test_optional_probe_failure_does_not_erase_setup_telemetry(self):
        for status, expected in (
            (403, "endpoint_niedostepny"),
            (404, "endpoint_niedostepny"),
            (429, "limit_zapytan"),
            (500, "blad_http"),
        ):
            with self.subTest(status=status):
                session = DeviceCapabilitySession(device_status=status)
                client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
                devices = await client.async_read()
                await client.async_probe_compressor_capabilities(devices)
                self.assertEqual(client.compressor_probe_summary["state"], expected)
                self.assertEqual(devices[0]["values"][112], 15.8)

    async def test_invalid_device_id_or_no_heat_pump_never_triggers_device_get(self):
        for device_id in ("attack&query=1", "001", "ABCDEFG"):
            with self.subTest(device_id=device_id):
                session = DeviceCapabilitySession(device_id=device_id)
                client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
                devices = await client.async_read()
                await client.async_probe_compressor_capabilities(devices)
                self.assertEqual([m for m, u, _ in session.calls if "/capabilities/?deviceId=" in u], [])
                self.assertEqual(client.compressor_probe_summary["state"], "brak_numerycznego_id_pompy")


class MonthlyEnergySession(ConsumptionSession):
    def __init__(self, status=200, monthly_payload=None):
        super().__init__(setup_id=123)
        self.monthly_status = status
        self.monthly_payload = monthly_payload if monthly_payload is not None else [
            {"type": 1, "unit": 1, "category": 1,
             "deviceId": "SENSITIVE_DEVICE", "consumptionPeriods": [
                 {"date": 1780000000, "consumedQuantity": 20.45,
                  "producedQuantity": 67.9, "cost": 99999}
             ]},
        ]

    def get(self, url, **kwargs):
        if "/consumptions?periodicity=monthly" in url:
            self.calls.append(("GET", url, kwargs))
            return Reply(self.monthly_status, self.monthly_payload)
        return super().get(url, **kwargs)


class TestMonthlyEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_monthly_endpoint_and_strict_allowlist(self):
        session = MonthlyEnergySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "faked")
        target = API_ORIGIN + "/magellan/setups/123/consumptions?periodicity=monthly"
        with self.assertRaises(AtlanticError):
            client._request("GET", target)
        await client.async_read()
        for method, url in (
            ("POST", target),
            ("GET", target + "&allAccounts=true"),
            ("GET", target.replace("123", "124")),
            ("GET", target.replace("monthly", "yearly")),
            ("GET", "https://example.invalid/steal"),
        ):
            with self.subTest(method=method, url=url), self.assertRaises(AtlanticError):
                client._request(method, url)
        await client.async_probe_monthly_energy()
        self.assertEqual(client.monthly_energy_summary["state"], "dostepna")
        self.assertEqual(client.monthly_energy_summary["okresy_z_dodatnia_produkcja"], 1)
        self.assertFalse(client.monthly_energy_summary["energia_cieplna_zweryfikowana"])
        self.assertNotIn("SENSITIVE_DEVICE", str(client.monthly_energy_summary))
        self.assertNotIn("67.9", str(client.monthly_energy_summary))
        self.assertEqual(len([x for x in session.calls if "monthly" in x[1]]), 1)
        await client.async_probe_monthly_energy()
        self.assertEqual(len([x for x in session.calls if "monthly" in x[1]]), 1)
        for _method, _url, opts in session.calls:
            self.assertIs(opts["allow_redirects"], False)
            self.assertNotIn("proxy", opts)
            self.assertNotIn("ssl", opts)

    async def test_monthly_403_404_429_do_not_break_setup_poll(self):
        for status, expected in ((403, "endpoint_niedostepny"),
                                 (404, "endpoint_niedostepny"),
                                 (429, "limit_zapytan"),
                                 (500, "blad_http")):
            with self.subTest(status=status):
                session = MonthlyEnergySession(status=status)
                client = AtlanticReadOnlyClient(session, "fake@example.invalid", "faked")
                devices = await client.async_read()
                await client.async_probe_monthly_energy()
                self.assertEqual(client.monthly_energy_summary["state"], expected)
                self.assertEqual(devices[0]["values"][164], 1298.0)

    async def test_setup_change_invalidates_monthly_diagnostic(self):
        session = MonthlyEnergySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "faked")
        await client.async_read()
        await client.async_probe_monthly_energy()
        session.setup_payload[0]["id"] = 456
        await client.async_read()
        self.assertEqual(client.monthly_energy_summary, {"state": "nie_sprawdzono"})
        self.assertEqual(client._monthly_energy_url(),
                         API_ORIGIN + "/magellan/setups/456/consumptions?periodicity=monthly")


class DeviceEnergySession(Session):
    """Network-free test of vendor device-specific daily/monthly consumption."""
    def __init__(self, device_status=200, daily_status=None, monthly_status=None):
        super().__init__(setup_payload=[{"id": 123, "devices": [{
            "deviceId": 9, "name": "Simulated pump", "capabilities": [
                {"capabilityId": 91, "value": "1"},
                {"capabilityId": 112, "value": "16.33"},
            ],
        }]}])
        self.device_status = device_status
        self.daily_status = daily_status
        self.monthly_status = monthly_status

    def get(self, url, **kwargs):
        if "/magellan/devices/9/consumptions?periodicity=" in url:
            self.calls.append(("GET", url, kwargs))
            period_status = (
                self.monthly_status if url.endswith("=monthly")
                else self.daily_status
            )
            return Reply(self.device_status if period_status is None else period_status, [{
                "deviceId": "SECRET_IDENTIFIER",
                "type": 1, "unit": 1, "category": 7,
                "consumptionPeriods": [{
                    "date": 1788825600,
                    "consumedQuantity": 123456.789,
                    "producedQuantity": 456789.123,
                }],
            }])
        return super().get(url, **kwargs)


class TestDeviceEnergyProbe(unittest.IsolatedAsyncioTestCase):
    async def test_only_this_accounts_pump_and_exact_period_can_be_requested(self):
        session = DeviceEnergySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
        day_url = API_ORIGIN + "/magellan/devices/9/consumptions?periodicity=daily"
        month_url = API_ORIGIN + "/magellan/devices/9/consumptions?periodicity=monthly"
        with self.assertRaises(AtlanticError):
            client._request("GET", day_url)
        await client.async_read()
        for method, url in (
            ("POST", day_url), ("PATCH", day_url),
            ("GET", day_url + "&includeSecrets=true"),
            ("GET", day_url.replace("/9/", "/10/")),
            ("GET", day_url.replace("daily", "yearly")),
        ):
            with self.subTest(method=method, url=url), self.assertRaises(AtlanticError):
                client._request(method, url)
        await client.async_probe_device_energy()
        self.assertEqual(client.device_energy_summary["state"], "dostepna")
        self.assertEqual(client.device_energy_summary["daily"]["kategorie"], [7])
        self.assertEqual(
            client.device_energy_summary["daily"]["dodatnia_produkcja_niezweryfikowana"], 1
        )
        self.assertEqual(client.device_energy_summary["monthly"]["state"], "dostepna")
        result = str(client.device_energy_summary)
        for private in ("SECRET", "123456", "456789", "/9/", "1788825600"):
            self.assertNotIn(private, result)
        self.assertEqual(
            [(m, u) for m, u, _ in session.calls][-2:],
            [("GET", month_url), ("GET", day_url)],
        )
        await client.async_probe_device_energy()
        self.assertEqual(
            len([u for m, u, _ in session.calls if "/magellan/devices/" in u]), 2
        )

    async def test_http_400_daily_does_not_hide_monthly_production_probe(self):
        session = DeviceEnergySession(daily_status=400, monthly_status=200)
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
        await client.async_read()
        await client.async_probe_device_energy()
        result = client.device_energy_summary
        self.assertEqual(result["state"], "dostepna")
        self.assertEqual(result["monthly"]["http_status"], 200)
        self.assertEqual(result["daily"]["http_status"], 400)
        self.assertEqual(result["daily"]["state"], "blad_http")
        self.assertEqual(
            result["monthly"]["audyt_surowych_kandydatow"]["state"],
            "kandydat_do_porownania_ze_sterownikiem"
        )
        self.assertNotIn("SECRET_IDENTIFIER", str(result))
        self.assertNotIn("123456", str(result))
        self.assertNotIn("456789", str(result))
        self.assertEqual(
            [u.split("=")[-1] for m, u, _ in session.calls
             if "/magellan/devices/" in u],
            ["monthly", "daily"]
        )

    async def test_http_500_monthly_still_checks_daily_with_explainable_code(self):
        session = DeviceEnergySession(monthly_status=500, daily_status=200)
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
        await client.async_read()
        await client.async_probe_device_energy()
        result = client.device_energy_summary
        self.assertEqual(result["state"], "dostepna")
        self.assertEqual(result["monthly"]["http_status"], 500)
        self.assertEqual(result["daily"]["http_status"], 200)

    async def test_401_and_429_do_not_issue_follow_up_energy_request(self):
        for status, expected in ((401, "brak_autoryzacji"), (429, "limit_zapytan")):
            with self.subTest(status=status):
                session = DeviceEnergySession(monthly_status=status)
                client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
                await client.async_read()
                await client.async_probe_device_energy()
                result = client.device_energy_summary
                self.assertEqual(result["state"], expected)
                self.assertEqual(result["monthly"]["http_status"], status)
                self.assertEqual(result["daily"], {})
                self.assertEqual(
                    len([u for _, u, _ in session.calls
                         if "/magellan/devices/" in u]), 1
                )

    async def test_rejected_or_throttled_device_history_does_not_break_pump_poll(self):
        for status, label in ((403, "endpoint_niedostepny"),
                              (404, "endpoint_niedostepny"),
                              (429, "limit_zapytan"), (500, "blad_http")):
            with self.subTest(status=status):
                session = DeviceEnergySession(device_status=status)
                client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fakepass")
                await client.async_read()
                await client.async_probe_device_energy()
                self.assertEqual(client.device_energy_summary["state"], label)
                self.assertNotIn("SECRET_IDENTIFIER", str(client.device_energy_summary))
                self.assertIn(112, (await client.async_read())[0]["values"]) if status != 429 else None



class TestAuditHttpRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_retry_after_ten_hours_is_not_shortened_to_one_hour(self):
        from datetime import datetime, timezone
        client = AtlanticReadOnlyClient(Session(), "fake@example.invalid", "fake")
        client._note_rate_limited(Reply(429, {}, {"Retry-After": "36000"}))
        remaining = (client._cooldown_until - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(remaining, 35990)

    async def test_http_date_retry_after_is_not_shortened(self):
        from datetime import datetime, timezone, timedelta
        from email.utils import format_datetime
        client = AtlanticReadOnlyClient(Session(), "fake@example.invalid", "fake")
        future = datetime.now(timezone.utc) + timedelta(hours=10)
        client._note_rate_limited(Reply(429, {}, {"Retry-After": format_datetime(future)}))
        self.assertGreater((client._cooldown_until - datetime.now(timezone.utc)).total_seconds(), 35990)

    async def test_nonfinite_and_overflowing_retry_after_do_not_crash(self):
        from datetime import datetime, timezone
        for header in ("nan", "inf", "-inf", "1e300", "garbage", "-1"):
            with self.subTest(header=header):
                client = AtlanticReadOnlyClient(Session(), "fake@example.invalid", "fake")
                client._note_rate_limited(Reply(429, {}, {"Retry-After": header}))
                self.assertGreater(client._cooldown_until, datetime.now(timezone.utc))

    async def test_daily_probe_after_other_probe_invalidates_token_sends_nothing(self):
        session = ConsumptionSession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
        await client.async_read()
        client._token = None
        before = list(session.calls)
        await client.async_probe_consumptions()
        self.assertEqual(session.calls, before)
        self.assertEqual(client.consumption_summary["state"], "brak_autoryzacji")


if __name__ == "__main__":
    unittest.main()
