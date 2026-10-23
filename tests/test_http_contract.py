"""Offline HTTP contract tests: no Atlantic credentials or network access."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "atlantic_cozytouch"

# The HTTP client is tested in isolation, without installing or importing
# Home Assistant or making an Internet connection.
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
    AtlanticError,
    AtlanticRateLimited,
    AtlanticReadOnlyClient,
)
from atlantic_cozytouch.const import API_ORIGIN, READ_PATH, TOKEN_PATH


class Reply:
    def __init__(self, status: int, payload: object) -> None:
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class Session:
    """Records all HTTP operations; has no connection to any network."""

    def __init__(self, *, login_status=200, read_status=200):
        self.calls = []
        self.login_status = login_status
        self.read_status = read_status

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return Reply(
            self.login_status,
            {"access_token": "TEST_ONLY_TOKEN", "expires_in": 3600},
        )

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Reply(self.read_status, [{
            "devices": [{
                "deviceId": 9,
                "name": "Simulated pump",
                "capabilities": [
                    {"capabilityId": 24, "value": "21"},
                    {"capabilityId": 44, "value": "5000"},
                    {"capabilityId": 51, "value": "1"},
                ],
            }]
        }])


class TestHttpContract(unittest.IsolatedAsyncioTestCase):
    async def test_success_never_contacts_nonvendor_and_never_writes_device(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "test-secret")
        result = await client.async_read()
        self.assertEqual(result[0]["values"][44], 5.0)
        self.assertEqual(result[0]["values"][24], 21.0)
        self.assertTrue(result[0]["values"][51])
        self.assertEqual(
            [(method, url) for method, url, _ in session.calls],
            [
                ("POST", API_ORIGIN + TOKEN_PATH),
                ("GET", API_ORIGIN + READ_PATH),
            ],
        )
        for _, _, kwargs in session.calls:
            self.assertIs(kwargs["allow_redirects"], False)

    async def test_second_poll_reuses_token_and_only_gets(self):
        session = Session()
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        await client.async_read()
        await client.async_read()
        self.assertEqual(
            [method for method, _, _ in session.calls],
            ["POST", "GET", "GET"],
        )

    async def test_redirect_does_not_follow_to_third_party(self):
        session = Session(login_status=302)
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticError):
            await client.async_read()
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(session.calls[0][2]["allow_redirects"])

    async def test_rate_limit_does_not_retry_unboundedly(self):
        session = Session(read_status=429)
        client = AtlanticReadOnlyClient(session, "test@example.invalid", "pass")
        with self.assertRaises(AtlanticRateLimited):
            await client.async_read()
        self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
