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
        self.assertEqual(result[0]["values"][44], 5.0)
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
                    target.replace("daily", "monthly"),
                    API_ORIGIN + "/magellan/executions/writecapability"):
            with self.assertRaises(AtlanticError):
                client._request("GET", bad)
        with self.assertRaises(AtlanticError):
            client._request("POST", target)

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


if __name__ == "__main__":
    unittest.main()
