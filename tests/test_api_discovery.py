"""Offline contract, privacy and request-budget tests for API research."""
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlsplit, parse_qs
from test_http_contract import AtlanticReadOnlyClient, AtlanticError, Session, Reply
from atlantic_cozytouch import api_discovery as d


class Content:
    def __init__(self, payload, raw=None):
        self.raw = raw if raw is not None else json.dumps(payload).encode()

    async def iter_chunked(self, size):
        for i in range(0, len(self.raw), size):
            yield self.raw[i:i+size]


class DiscoverySession(Session):
    def __init__(self, status=200, raw=None):
        super().__init__(setup_payload=[{"id": 123, "devices": [
            {"deviceId": 9, "capabilities": [
                {"capabilityId": 91, "value": "1"}, {"capabilityId": 112, "value": "17"}]},
            {"deviceId": 10, "capabilities": [
                {"capabilityId": 109, "value": "35"}, {"capabilityId": 116, "value": "31"}]},
        ]}])
        self.discovery_status = status
        self.raw = raw

    def get(self, url, **kwargs):
        if "productmodels" not in url and "capabilities=" not in url and "fromDate=" not in url:
            return super().get(url, **kwargs)
        self.calls.append(("GET", url, kwargs))
        if "productmodels" in url:
            payload = [{"id": 57, "name": "HOME_ElecHeatConsumptionCumulated", "unit": "kWh", "resolution": .001},
                       {"id": 999, "name": "ThermalHeatProduced", "unit": "kWh", "isSensitiveData": False}]
        elif "capabilities=" in url:
            payload = [{"capabilityId": 57, "value": "12345", "modificationDate": 1793000000},
                       {"capabilityId": 999, "value": "PRIVATE_UNREVIEWED_VALUE"},
                       {"capabilityId": 335, "value": "SECRET_SERIAL"}]
        else:
            payload = [{"deviceId": "SECRET_ID", "serialNumber": "SECRET_SERIAL", "category": 1, "type": 1, "unit": 1,
                        "consumptionPeriods": [{"date": 1793000000, "mode": 0, "profil": 1,
                                                "consumedQuantity": 26, "producedQuantity": 76}]}]
        reply = Reply(self.discovery_status, payload)
        reply.content = Content(payload, self.raw)
        return reply


class DiscoveryContract(unittest.IsolatedAsyncioTestCase):
    async def test_six_gets_spread_across_polls_and_no_cop_or_device_mutation(self):
        session = DiscoverySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
        devices = await client.async_read()
        original = json.dumps(devices, sort_keys=True)
        for index in range(6):
            before = len(session.calls)
            await client.async_probe_energy_discovery(devices)
            self.assertEqual(len(session.calls), before + 1)
        before = len(session.calls)
        await client.async_probe_energy_discovery(devices)
        self.assertEqual(len(session.calls), before)
        self.assertEqual(json.dumps(devices, sort_keys=True), original)
        self.assertFalse(client.discovery_summary["cop_ready"])
        self.assertEqual(len(client.discovery_summary["results"]), 6)
        report = json.dumps(client.discovery_summary)
        for secret in ("SECRET_SERIAL", "SECRET_ID", "PRIVATE_UNREVIEWED_VALUE", "fake@example.invalid", "Bearer"):
            self.assertNotIn(secret, report)
        self.assertEqual(client.discovery_summary["results"]["device_monthly"]["rows"][0]["produced_quantity_raw"], 76)
        for method, url, options in session.calls[2:]:
            self.assertEqual(method, "GET")
            self.assertEqual(urlsplit(url).netloc, "apis.groupe-atlantic.com")
            self.assertFalse(options["allow_redirects"])
        self.assertEqual(client._discovery_urls, frozenset())

    async def test_dates_and_device_filter_are_bounded_and_explicit(self):
        plan = d.build_plan([{"id": "9", "reported_capability_ids": [91,112]}], 123, set(),
                            datetime(2026, 1, 20, tzinfo=timezone.utc))
        query = parse_qs(urlsplit(plan[-1].url).query)
        self.assertEqual(query["fromDate"], ["2025-12-01T00:00:00Z"])
        self.assertEqual(query["toDate"], ["2026-01-20T00:00:00Z"])
        self.assertEqual(query["deviceId"], ["9"])
        self.assertEqual(query["periodicity"], ["Monthly"])

    async def test_catalogue_candidates_stay_metadata_only(self):
        plan = d.build_plan(
            [{"id": "9", "reported_capability_ids": [91, 112]}],
            123, {900, 901}, datetime(2026, 1, 20, tzinfo=timezone.utc),
        )
        capability_query = parse_qs(urlsplit(plan[0].url).query)
        requested = set(map(int, capability_query["capabilities"][0].split(";")))
        self.assertEqual(requested, set(d.CORE_IDS))
        self.assertNotIn(900, requested)

    async def test_periodicity_uses_case_sensitive_wcf_enum_hypothesis(self):
        plan = d.build_plan(
            [{"id": "9", "reported_capability_ids": [91, 112]}],
            123, set(), datetime(2026, 1, 20, tzinfo=timezone.utc),
        )
        history = {
            probe.key: parse_qs(urlsplit(probe.url).query)
            for probe in plan if "consumptions" in probe.url
        }
        self.assertEqual(history["device_monthly"]["periodicity"], ["Monthly"])
        self.assertEqual(history["device_daily"]["periodicity"], ["Daily"])
        self.assertEqual(
            history["setup_monthly_filtered"]["periodicity"], ["Monthly"]
        )
    async def test_urls_not_authorized_outside_single_internal_probe(self):
        session = DiscoverySession()
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
        for method, url in (("GET", d.CATALOGUE_URL), ("POST", d.CATALOGUE_URL),
                            ("GET", d.API_ORIGIN + "/magellan/devices/999/consumptions?periodicity=monthly")):
            with self.assertRaises(AtlanticError):
                client._request(method, url)
        self.assertEqual(session.calls, [])

    async def test_401_and_429_stop_entire_investigation(self):
        for status in (401,429):
            session = DiscoverySession(status=status)
            client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
            devices = await client.async_read()
            await client.async_probe_energy_discovery(devices)
            self.assertEqual(client.discovery_summary["state"], "przerwano_401_lub_429")
            before = len(session.calls)
            await client.async_probe_energy_discovery(devices)
            self.assertEqual(len(session.calls), before)

    async def test_large_or_malformed_json_is_isolated(self):
        for raw in (b"[" * 2000, b"x" * (d.MAX_BODY_BYTES+1)):
            session = DiscoverySession(raw=raw)
            client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
            devices = await client.async_read()
            await client.async_probe_energy_discovery(devices)
            self.assertEqual(client.discovery_summary["results"]["catalogue"]["state"], "blad_odczytu_lub_formatu")
            self.assertEqual(client._discovery_urls, frozenset())
            self.assertEqual(devices[0]["values"][112],17)

    async def test_changed_target_stops_pending_requests(self):
        session = DiscoverySession()
        client = AtlanticReadOnlyClient(session,"fake@example.invalid","fake")
        devices = await client.async_read()
        await client.async_probe_energy_discovery(devices)
        devices[0]["id"] = "11"
        before = len(session.calls)
        await client.async_probe_energy_discovery(devices)
        self.assertEqual(len(session.calls),before)
        self.assertEqual(client.discovery_summary["state"],"zmiana_zrodla_przerwano")

    async def test_ambiguous_pumps_make_no_requests(self):
        client = AtlanticReadOnlyClient(DiscoverySession(),"fake@example.invalid","fake")
        devices = [{"id":str(i),"reported_capability_ids":[91,112]} for i in (1,2)]
        await client.async_probe_energy_discovery(devices)
        self.assertEqual(client.discovery_summary["state"],"brak_jednoznacznej_pompy")
        self.assertEqual(client._session.calls,[])


class DiscoveryParsing(unittest.TestCase):
    def test_catalogue_sensitivity_and_unknown_values(self):
        summary, extra = d.catalogue_summary([
            {"id":999,"name":"HeatProduced","isSensitiveData":False,"unit":"kWh"},
            {"id":998,"name":"HeatProduced","isSensitiveData":True},
            {"id":997,"name":"HeatProduced"}])
        self.assertEqual(extra,{999})
        result = d.capability_summary([{"capabilityId":999,"value":"123456789"}], set(), {999})
        self.assertIsNone(result["rows"][0]["numeric_value_raw"])

    def test_bad_values_and_unexpected_fields_do_not_escape(self):
        for value in (True, "nan", "inf", "secret", "9"*100):
            self.assertIsNone(d.number(value))
        self.assertFalse(d.valid_id("9&deviceId=10"))
        self.assertFalse(d.valid_id("001"))
        with self.assertRaises(ValueError):
            d.history_summary({"token":"secret"})

    def test_history_is_not_summed_and_is_bounded(self):
        periods=[{"date":1793000000+i,"consumedQuantity":1,"producedQuantity":3} for i in range(100)]
        result=d.history_summary([{"category":1,"type":1,"unit":1,"consumptionPeriods":periods}])
        self.assertEqual(len(result["rows"]),24)
        self.assertEqual(result["omitted_rows"],76)
        self.assertEqual(result["rows"][0]["date_epoch"],1793000099)
        self.assertFalse(result["thermal_energy_confirmed"])
        self.assertFalse(result["cop_ready"])


class ErrorEvidence(unittest.IsolatedAsyncioTestCase):
    async def test_400_extracts_clues_without_secrets_or_extra_requests(self):
        raw = b'{"message":"Invalid fromDate format yyyy-MM-dd for secret@example.invalid token=SECRET_SERIAL deviceId=123456"}'
        session = DiscoverySession(status=400, raw=raw)
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
        devices = await client.async_read()
        for _ in range(8):
            await client.async_probe_energy_discovery(devices)
        self.assertEqual(len(client.discovery_summary["results"]), 6)
        self.assertEqual(len(session.calls), 8)  # Login/setup plus six probes.
        result = client.discovery_summary["results"]["device_monthly"]
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["error_evidence"]["format_mentions"], ["yyyy-MM-dd"])
        self.assertIn("fromDate", result["error_evidence"]["parameter_mentions"])
        self.assertFalse(result["error_evidence"]["cause_confirmed"])
        report = json.dumps(client.discovery_summary)
        for secret in ("secret@example.invalid", "SECRET_SERIAL", "123456", "token="):
            self.assertNotIn(secret, report)
        self.assertEqual(client._discovery_urls, frozenset())

    async def test_400_large_body_preserves_status(self):
        session = DiscoverySession(status=400, raw=b"x" * (d.MAX_ERROR_BYTES + 1))
        client = AtlanticReadOnlyClient(session, "fake@example.invalid", "fake")
        devices = await client.async_read()
        await client.async_probe_energy_discovery(devices)
        result = client.discovery_summary["results"]["catalogue"]
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["error_evidence"], {"state": "body_too_large"})

    async def test_400_body_read_failure_preserves_status(self):
        class BrokenContent:
            async def iter_chunked(self, size):
                raise TimeoutError()
                yield b""
        class BrokenSession(DiscoverySession):
            def get(self, url, **kwargs):
                reply = super().get(url, **kwargs)
                if "productmodels" in url:
                    reply.content = BrokenContent()
                return reply
        client = AtlanticReadOnlyClient(BrokenSession(status=400), "fake@example.invalid", "fake")
        devices = await client.async_read()
        await client.async_probe_energy_discovery(devices)
        result = client.discovery_summary["results"]["catalogue"]
        self.assertEqual(result["http_status"], 400)
        self.assertEqual(result["error_evidence"]["state"], "body_read_failed")

    def test_unrecognized_or_invalid_utf8_never_exports_body(self):
        for raw in (b"", b"SECRET_TOKEN", b"<html>private account</html>", b"\xff\xfe"):
            result = d.error_summary(raw)
            self.assertEqual(result["state"], "unrecognized_body")
            self.assertFalse(result["cause_confirmed"])

    def test_catalogue_description_topics_and_limits(self):
        payload = [{"id": 200+i, "name": "Opaque", "description": "Electrical energy consumption SECRET_SERIAL",
                    "unit": {}, "isSensitiveData": False} for i in range(30)]
        report, ids = d.catalogue_summary(payload)
        self.assertEqual(len(ids), 16)
        self.assertEqual(len(report["rows"]), 16)
        self.assertIn("energy", report["rows"][0]["topic_hints"])
        self.assertIsNone(report["rows"][0]["unit"])
        self.assertNotIn("SECRET_SERIAL", json.dumps(report))
        for row in payload:
            row["isSensitiveData"] = True
        self.assertEqual(d.catalogue_summary(payload)[1], set())

    def test_catalogue_detects_thermal_and_defrost_in_description(self):
        report, ids = d.catalogue_summary([
            {"id": 900, "description": "Delivered thermal energy", "isSensitiveData": False},
            {"id": 901, "description": "Deicing active", "isSensitiveData": False}])
        self.assertEqual(ids, {900, 901})
        self.assertTrue(report["rows"][0]["thermal_name_candidate"])
        self.assertTrue(report["rows"][1]["defrost_name_candidate"])
