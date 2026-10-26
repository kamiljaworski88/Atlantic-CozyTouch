"""Atlantic HTTP client with a strict, read-only operation allowlist.

No operation can mutate the device: POST is permitted only for OAuth login,
and GET only for setup, authorized device capabilities and consumption history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging
import json
from math import isfinite

import aiohttp

from .const import (
    API_ORIGIN,
    ATLANTIC_PUBLIC_CLIENT_ID,
    HTTP_TIMEOUT_SECONDS,
    READ_PATH,
    TOKEN_PATH,
)
from . import api_discovery as discovery_api
from .readings import extract_devices
from .discovery import compressor_host_devices
from .consumption_probe import parse_setup_id, summarize_consumptions
from .energy_daily import extract_electricity_days
from .monthly_energy_probe import monthly_energy_shape
from .heat_production_probe import summarize_production_candidates

_LOGGER = logging.getLogger(__name__)

# An exact-method, exact-URL allowlist, not merely a hostname filter.
_ALLOWED_HTTP_OPERATIONS = frozenset(
    {
        ("POST", API_ORIGIN + TOKEN_PATH),  # Authentication, never device control.
        ("GET", API_ORIGIN + READ_PATH),   # Status/measurement snapshot.
    }
)
_MIN_THROTTLE_SECONDS = 300
_DEFAULT_THROTTLE_SECONDS = 900


class AtlanticError(Exception):
    """The Atlantic service could not supply valid data."""


class AtlanticAuthError(AtlanticError):
    """Atlantic rejected the account credentials."""


class AtlanticRateLimited(AtlanticError):
    """Atlantic requested fewer requests."""


class AtlanticReadOnlyClient:
    """Read-only vendor cloud client with a deny-by-default HTTP boundary."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._discovery_urls: frozenset[str] = frozenset()
        self._discovery_queue = None
        self._discovery_requested_ids = set(discovery_api.CORE_IDS)
        self.discovery_summary = {"state": "wylaczone", "results": {}, "cop_ready": False}
        self._session = session
        self._username = username.strip()
        self._password = password
        self._token: str | None = None
        self._token_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self._cooldown_until = datetime.min.replace(tzinfo=timezone.utc)
        self._setup_id: int | None = None
        self._consumption_due = datetime.min.replace(tzinfo=timezone.utc)
        self._consumption_disabled = False
        self.consumption_summary: dict = {"state": "nie_sprawdzono"}
        self.energy_daily: dict[int, dict[str, float]] = {}
        self._monthly_probe_due = datetime.min.replace(tzinfo=timezone.utc)
        self._monthly_probe_disabled = False
        self.monthly_energy_summary: dict[str, object] = {"state": "nie_sprawdzono"}
        self._compressor_device_ids: set[str] = set()
        self._compressor_probe_due = datetime.min.replace(tzinfo=timezone.utc)
        self._compressor_probe_disabled = False
        self._compressor_setup_missing: set[str] = set()
        self._compressor_cache: dict[str, tuple[datetime, dict]] = {}
        self.compressor_probe_summary: dict[str, object] = {"state": "nie_sprawdzono"}
        self._device_energy_ids: set[str] = set()
        self._device_energy_due = datetime.min.replace(tzinfo=timezone.utc)
        self._device_energy_disabled = False
        self.device_energy_summary: dict[str, object] = {"state": "nie_sprawdzono"}

    def _request(self, method: str, url: str, **kwargs):
        """Reject all methods/routes except vendor login and snapshot read.

        The caller cannot override TLS verification, configure a proxy or
        enable HTTP redirects via request parameters.
        """
        # A third GET is allowed ONLY for this account's validated numeric
        # setup id, never for caller-supplied URLs or arbitrary Magellan paths.
        consumption_allowed = (
            method == "GET"
            and self._setup_id is not None
            and url == self._consumption_url()
        )
        monthly_allowed = (
            method == "GET"
            and self._setup_id is not None
            and url == self._monthly_energy_url()
        )
        capability_allowed = (
            method == "GET"
            and any(url == self._compressor_capabilities_url(device_id)
                    for device_id in self._compressor_device_ids)
        )
        device_energy_allowed = (
            method == "GET"
            and any(
                url == self._device_energy_url(device_id, period)
                for device_id in self._device_energy_ids
                for period in ("daily", "monthly")
            )
        )
        if ((method, url) not in _ALLOWED_HTTP_OPERATIONS
                and not consumption_allowed and not monthly_allowed
                and not capability_allowed and not device_energy_allowed
                and not (method == "GET" and url in self._discovery_urls)):
            raise AtlanticError("Blocked operation outside read-only HTTP allowlist")
        if {"ssl", "proxy", "proxy_auth", "auth", "allow_redirects", "timeout", "params"} & kwargs.keys():
            raise AtlanticError("Forbidden request transport override")

        options = dict(kwargs)
        options["timeout"] = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        options["allow_redirects"] = False

        if method == "POST":
            return self._session.post(url, **options)
        return self._session.get(url, **options)

    def _consumption_url(self) -> str:
        if self._setup_id is None:
            raise AtlanticError("No valid setup identifier")
        return (
            API_ORIGIN + f"/magellan/setups/{self._setup_id}/consumptions"
            "?periodicity=daily"
        )

    def _monthly_energy_url(self) -> str:
        if self._setup_id is None:
            raise AtlanticError("No valid setup identifier")
        return (
            API_ORIGIN + f"/magellan/setups/{self._setup_id}/consumptions"
            "?periodicity=monthly"
        )

    @staticmethod
    def _valid_device_id(value: object) -> bool:
        return (
            isinstance(value, str) and 1 <= len(value) <= 18
            and value.isascii() and value.isdecimal()
            and value[0] != "0" and int(value) <= 999999999999999999
        )

    def _compressor_capabilities_url(self, device_id: str) -> str:
        if not self._valid_device_id(device_id) or device_id not in self._compressor_device_ids:
            raise AtlanticError("Device is not an authorized compressor probe target")
        return API_ORIGIN + "/magellan/capabilities/?deviceId=" + device_id

    def _device_energy_url(self, device_id: str, period: str) -> str:
        if (
            not self._valid_device_id(device_id)
            or device_id not in self._device_energy_ids
            or period not in ("daily", "monthly")
        ):
            raise AtlanticError("Device energy GET outside authenticated allowlist")
        return (
            API_ORIGIN + "/magellan/devices/" + device_id
            + "/consumptions?periodicity=" + period
        )

    def _ensure_not_throttled(self) -> None:
        if datetime.now(timezone.utc) < self._cooldown_until:
            raise AtlanticRateLimited("Atlantic rate-limit cooldown active")

    def _note_rate_limited(self, response: object) -> None:
        """Respect finite Retry-After values without retrying before the server allows."""
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After", "")
        wait = _DEFAULT_THROTTLE_SECONDS
        if retry_after:
            try:
                wait = float(retry_after)
            except (ValueError, TypeError):
                try:
                    retry_date = parsedate_to_datetime(str(retry_after))
                    if retry_date.tzinfo is None:
                        retry_date = retry_date.replace(tzinfo=timezone.utc)
                    wait = (retry_date - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    wait = _DEFAULT_THROTTLE_SECONDS
        # A maximum of one hour would violate a longer vendor Retry-After.
        # Malformed/nonfinite values use the conservative default. Saturate at
        # datetime.max rather than overflowing on very large finite headers.
        if not isfinite(wait) or wait < 0:
            wait = _DEFAULT_THROTTLE_SECONDS
        wait = max(_MIN_THROTTLE_SECONDS, wait)
        now = datetime.now(timezone.utc)
        latest = datetime.max.replace(tzinfo=timezone.utc)
        self._cooldown_until = (
            latest if wait >= (latest - now).total_seconds()
            else now + timedelta(seconds=wait)
        )

    async def _authenticate(self) -> None:
        """The only HTTP POST: exchange user credentials for an access token."""
        self._ensure_not_throttled()
        form = aiohttp.FormData(
            {
                "grant_type": "password",
                "scope": "openid",
                "username": "GA-PRIVATEPERSON/" + self._username,
                "password": self._password,
            }
        )
        try:
            async with self._request(
                "POST",
                API_ORIGIN + TOKEN_PATH,
                data=form,
                headers={"Authorization": "Basic " + ATLANTIC_PUBLIC_CLIENT_ID},
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    raise AtlanticError("Atlantic login redirected unexpectedly")
                if response.status == 429:
                    self._note_rate_limited(response)
                    raise AtlanticRateLimited("Atlantic login rate limited")
                if response.status in (400, 401, 403):
                    raise AtlanticAuthError("Atlantic login rejected")
                if response.status != 200:
                    raise AtlanticError("Atlantic login service unavailable")
                body = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            # No URL, password, token or raw HTTP body is logged.
            raise AtlanticError("Atlantic login connection failed") from None

        if isinstance(body, dict) and body.get("error") == "invalid_grant":
            raise AtlanticAuthError("Atlantic login rejected")
        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str) or not body["access_token"]:
            raise AtlanticError("Atlantic returned no access token")

        self._token = body["access_token"]
        seconds = body.get("expires_in", 3600)
        try:
            valid_for = float(seconds)
            if not (60 <= valid_for <= 86400):
                valid_for = 3600
        except (ValueError, TypeError):
            valid_for = 3600
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=max(1, valid_for - 60))

    async def _get_setup(self) -> object:
        self._ensure_not_throttled()
        if self._token is None:
            raise AtlanticAuthError("No Atlantic access token")
        try:
            async with self._request(
                "GET",
                API_ORIGIN + READ_PATH,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Accept": "application/json",
                },
            ) as response:
                if response.status == 401:
                    raise AtlanticAuthError("Atlantic session expired")
                if response.status == 429:
                    self._note_rate_limited(response)
                    raise AtlanticRateLimited("Atlantic read rate limited")
                if response.status != 200:
                    raise AtlanticError("Atlantic read unavailable")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise AtlanticError("Atlantic read connection failed") from None

    async def async_read(self) -> list[dict]:
        """Read only: log in if necessary, then retrieve the setup snapshot."""
        self._ensure_not_throttled()
        if self._token is None or datetime.now(timezone.utc) >= self._token_expiry:
            await self._authenticate()
        try:
            payload = await self._get_setup()
        except AtlanticAuthError:
            # One refresh, not an unbounded sequence of login attempts.
            self._token = None
            await self._authenticate()
            payload = await self._get_setup()

        try:
            devices = extract_devices(payload)
        except ValueError:
            raise AtlanticError("Unexpected Atlantic response schema") from None
        setup_id = parse_setup_id(payload)
        if setup_id != self._setup_id:
            self._setup_id = setup_id
            self._discovery_queue = None
            self._discovery_urls = frozenset()
            self.discovery_summary = {"state": "oczekiwanie", "results": {}, "cop_ready": False}
            self._consumption_due = datetime.min.replace(tzinfo=timezone.utc)
            self._consumption_disabled = False
            self.consumption_summary = {"state": "nie_sprawdzono"}
            self.energy_daily = {}  # Never mix accounts/setup IDs.
            self._monthly_probe_due = datetime.min.replace(tzinfo=timezone.utc)
            self._monthly_probe_disabled = False
            self.monthly_energy_summary = {"state": "nie_sprawdzono"}
            self._compressor_probe_due = datetime.min.replace(tzinfo=timezone.utc)
            self._compressor_probe_disabled = False
            self._compressor_cache = {}
            self.compressor_probe_summary = {"state": "nie_sprawdzono"}
            self._device_energy_due = datetime.min.replace(tzinfo=timezone.utc)
            self._device_energy_disabled = False
            self.device_energy_summary = {"state": "nie_sprawdzono"}
        # IDs come only from the authenticated account's setup snapshot.
        hosts = compressor_host_devices(devices)
        self._compressor_device_ids = {
            d["id"] for d in hosts[:2] if self._valid_device_id(d["id"])
        }
        # Require a unique actual pump (active circuit + flow) to prevent
        # querying unrelated devices, even those on the same account.
        energy_hosts = [
            d for d in hosts
            if {91, 112}.issubset(set(d.get("reported_capability_ids", [])))
            and self._valid_device_id(d["id"])
        ]
        self._device_energy_ids = (
            {energy_hosts[0]["id"]} if len(energy_hosts) == 1 else set()
        )
        self._compressor_setup_missing = {
            d["id"] for d in hosts[:2]
            if d["id"] in self._compressor_device_ids
            and not {24, 27, 51, 72}.issubset(set(d["reported_capability_ids"]))
        }
        # Cache only the most recent authenticated direct-read measurements.
        # Counters tolerate 16 minutes; instantaneous compressor state has a
        # much tighter 4-minute TTL and its vendor modificationDate is kept.
        now = datetime.now(timezone.utc)
        for device in hosts[:2]:
            cached = self._compressor_cache.get(device["id"])
            if cached is None:
                continue
            sampled_at, source = cached
            age = (now - sampled_at).total_seconds()
            if age < 0 or age > 960:
                continue
            for cap_id in (24, 27, 51, 72):
                if cap_id not in source.get("reported_capability_ids", []):
                    continue
                if cap_id in (51, 72) and age > 240:
                    continue
                if cap_id in device["reported_capability_ids"]:
                    continue
                value = source.get("values", {}).get(cap_id)
                if value is None:
                    continue
                device["values"][cap_id] = value
                stamp = source.get("updated_at", {}).get(cap_id)
                if type(stamp) is int:
                    device.setdefault("updated_at", {})[cap_id] = stamp
                device["reported_capability_ids"] = sorted(
                    set(device["reported_capability_ids"]) | {cap_id}
                )
        return devices

    async def async_probe_device_energy(self) -> None:
        """Optional safe device-level consumption schema test.

        Compare daily/monthly reports for exactly one authenticated heat pump.
        Run at most once per six hours. Only safe codes and record counts
        survive; producedQuantity alone never proves delivered heat.
        """
        now = datetime.now(timezone.utc)
        if self._device_energy_disabled or now < self._device_energy_due:
            return
        self._device_energy_due = now + timedelta(hours=6)
        if len(self._device_energy_ids) != 1 or self._token is None:
            self.device_energy_summary = {"state": "brak_jednoznacznej_pompy"}
            return
        device_id = next(iter(self._device_energy_ids))
        summaries: dict[str, dict] = {}
        # The monthly source is the actual heat-production candidate. A
        # daily 400/500 must never prevent examining the monthly response.
        # Only a 401 or 429 short-circuits to protect the Atlantic account.
        for period in ("monthly", "daily"):
            try:
                self._ensure_not_throttled()
                async with self._request(
                    "GET", self._device_energy_url(device_id, period),
                    headers={
                        "Authorization": "Bearer " + self._token,
                        "Accept": "application/json",
                    },
                ) as response:
                    if response.status == 429:
                        self._note_rate_limited(response)
                        summaries[period] = {
                            "state": "limit_zapytan", "http_status": 429,
                        }
                        break
                    if response.status == 401:
                        self._token = None
                        summaries[period] = {
                            "state": "brak_autoryzacji", "http_status": 401,
                        }
                        break
                    if response.status in (403, 404, 405):
                        summaries[period] = {
                            "state": "endpoint_niedostepny",
                            "http_status": response.status,
                        }
                        continue
                    if response.status != 200:
                        summaries[period] = {
                            "state": "blad_http", "http_status": response.status,
                        }
                        continue
                    payload = await response.json()
                details = summarize_consumptions(payload)
                summaries[period] = {
                    "state": details.get("state"),
                    "http_status": 200,
                    "serie": details.get("serie", 0),
                    "typy": details.get("typy", []),
                    "jednostki": details.get("jednostki", []),
                    "rekordy_zuzycia": details.get("okresy_z_energia_pobrana", 0),
                    "dodatnia_produkcja_niezweryfikowana":
                        details.get("okresy_z_dodatnia_produkcja", 0),
                    "kategorie": sorted({
                        d["kategoria_kod"] for d in details.get("serie_szczegoly", [])
                        if type(d.get("kategoria_kod")) is int
                    }),
                }
                if period == "monthly" and details.get("state") == "dostepna":
                    # Same already-fetched response, never another HTTP call.
                    # All numeric candidates are explicitly UNVERIFIED heat.
                    summaries[period]["audyt_surowych_kandydatow"] = (
                        summarize_production_candidates(payload)
                    )
            except (AtlanticRateLimited, aiohttp.ClientError, TimeoutError,
                    ValueError, TypeError, OverflowError, AtlanticError):
                summaries[period] = {"state": "blad_polaczenia"}
                break
        # Disable only when BOTH tested paths are explicitly unavailable;
        # HTTP 400 and 5xx can be parameter validation / transient failures.
        if all(summaries.get(p, {}).get("state") == "endpoint_niedostepny"
               for p in ("monthly", "daily")):
            self._device_energy_disabled = True

        monthly = summaries.get("monthly", {})
        daily = summaries.get("daily", {})
        # Keep the root status useful even when one period fails, while both
        # individual HTTP statuses remain visible for troubleshooting.
        chosen = next(
            (s for s in (monthly, daily) if s.get("state") in ("dostepna", "brak_danych")),
            monthly or daily,
        )
        self.device_energy_summary = {
            "state": chosen.get("state", "nie_sprawdzono"),
            "daily": daily,
            "monthly": monthly,
            "czy_produkcja_oznacza_cieplo": "niezweryfikowane",
        }

    async def async_probe_compressor_capabilities(self, devices: list[dict]) -> None:
        """Optional read-only device GET when setupviewv2 omits compressor data.

        Up to two GETs per fifteen minutes, for IDs from this authenticated
        account. Only known compressor capabilities enter telemetry. Neither
        raw measurements nor device identifiers enter diagnostic status.
        """
        now = datetime.now(timezone.utc)
        if self._compressor_probe_disabled or now < self._compressor_probe_due:
            return
        self._compressor_probe_due = now + timedelta(minutes=15)
        if self._token is None:
            self.compressor_probe_summary = {"state": "brak_sesji"}
            return
        hosts = [
            d for d in compressor_host_devices(devices)
            if d["id"] in self._compressor_device_ids
        ][:2]
        if not hosts:
            self.compressor_probe_summary = {"state": "brak_numerycznego_id_pompy"}
            return
        need_probe = [
            d for d in hosts if d["id"] in self._compressor_setup_missing
        ]
        if not need_probe:
            self.compressor_probe_summary = {"state": "parametry_juz_w_odczycie_glownym"}
            return

        gained = 0
        tried = 0
        for device in need_probe:
            try:
                self._ensure_not_throttled()
                async with self._request(
                    "GET", self._compressor_capabilities_url(device["id"]),
                    headers={
                        "Authorization": "Bearer " + self._token,
                        "Accept": "application/json",
                    },
                ) as response:
                    tried += 1
                    if response.status == 429:
                        self._note_rate_limited(response)
                        self.compressor_probe_summary = {"state": "limit_zapytan"}
                        return
                    if response.status in (403, 404, 405):
                        self._compressor_probe_disabled = True
                        self.compressor_probe_summary = {"state": "endpoint_niedostepny"}
                        return
                    if response.status == 401:
                        self._token = None
                        self.compressor_probe_summary = {"state": "brak_autoryzacji"}
                        return
                    if response.status != 200:
                        self.compressor_probe_summary = {"state": "blad_http"}
                        return
                    payload = await response.json()
                if not isinstance(payload, list) or len(payload) > 1024:
                    self.compressor_probe_summary = {"state": "niepoprawna_odpowiedz"}
                    return
                sanitized = extract_devices([{"devices": [
                    {"deviceId": device["id"], "capabilities": payload}
                ]}])
                if len(sanitized) != 1:
                    self.compressor_probe_summary = {"state": "niepoprawna_odpowiedz"}
                    return
                source = sanitized[0]
                allowed_ids = {24, 27, 51, 72}
                # Discard everything except compressor values before caching.
                source["values"] = {
                    cap: value for cap, value in source["values"].items()
                    if cap in allowed_ids
                }
                source["reported_capability_ids"] = [
                    cap for cap in source["reported_capability_ids"] if cap in allowed_ids
                ]
                source["updated_at"] = {
                    cap: stamp for cap, stamp in source.get("updated_at", {}).items()
                    if cap in allowed_ids
                }
                self._compressor_cache[device["id"]] = (now, source)
                for cap_id in (24, 27, 51, 72):
                    if cap_id not in source["reported_capability_ids"]:
                        continue
                    fresh_value = source["values"].get(cap_id)
                    if fresh_value is not None and device["values"].get(cap_id) is None:
                        gained += 1
                    old_timestamp = device.get("updated_at", {}).get(cap_id)
                    new_timestamp = source.get("updated_at", {}).get(cap_id)
                    if (
                        fresh_value is not None
                        and (device["values"].get(cap_id) is None
                             or (type(new_timestamp) is int
                                 and (type(old_timestamp) is not int
                                      or new_timestamp >= old_timestamp)))
                    ):
                        device["values"][cap_id] = fresh_value
                        if type(new_timestamp) is int:
                            device.setdefault("updated_at", {})[cap_id] = new_timestamp
                    device["reported_capability_ids"] = sorted(
                        set(device["reported_capability_ids"]) | {cap_id}
                    )
            except (AtlanticRateLimited, aiohttp.ClientError, TimeoutError,
                    ValueError, TypeError, OverflowError, AtlanticError):
                self.compressor_probe_summary = {"state": "blad_polaczenia"}
                return
        self.compressor_probe_summary = {
            "state": "uzupelniono" if gained else "brak_nowych_parametrow",
            "uzupelnione_parametry": gained,
            "sprawdzone_urzadzenia": tried,
        }


    async def async_probe_consumptions(self) -> None:
        """Optional 15-minute diagnostic GET; never affects normal telemetry.

        Only safe shape information is retained; no series, dates, amounts,
        account IDs or login secrets appear in diagnostics.
        """
        now = datetime.now(timezone.utc)
        if self._consumption_disabled or now < self._consumption_due:
            return
        self._consumption_due = now + timedelta(minutes=15)
        if self._setup_id is None:
            self.consumption_summary = {"state": "brak_id_instalacji"}
            return
        if self._token is None:
            self.consumption_summary = {"state": "brak_autoryzacji"}
            return
        try:
            self._ensure_not_throttled()
            async with self._request(
                "GET", self._consumption_url(),
                headers={
                    "Authorization": "Bearer " + (self._token or ""),
                    "Accept": "application/json",
                },
            ) as response:
                if response.status == 429:
                    self._note_rate_limited(response)
                    self.consumption_summary = {"state": "limit_zapytan"}
                    return
                if response.status in (403, 404):
                    self._consumption_disabled = True
                    self.consumption_summary = {
                        "state": "odmowa_dostepu" if response.status == 403
                        else "brak_endpointu"
                    }
                    return
                if response.status == 401:
                    self._token = None  # A normal setup poll will reauthenticate.
                    self.consumption_summary = {"state": "brak_autoryzacji"}
                    return
                if response.status != 200:
                    self.consumption_summary = {"state": "blad_http"}
                    return
                payload = await response.json()
                summary = summarize_consumptions(payload)
                self.energy_daily = (
                    extract_electricity_days(payload)
                    if summary.get("state") in ("dostepna", "brak_danych")
                    else {}
                )
                self.consumption_summary = summary
        except AtlanticRateLimited:
            self.consumption_summary = {"state": "limit_zapytan"}
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, OverflowError, AtlanticError):
            self.consumption_summary = {"state": "blad_polaczenia"}


    async def async_probe_monthly_energy(self) -> None:
        """Optional setup-only monthly GET, at most every six hours.

        The returned numeric energy values are never exported by this probe,
        and producedQuantity is NOT assumed to represent thermal heat.
        """
        now = datetime.now(timezone.utc)
        if self._monthly_probe_disabled or now < self._monthly_probe_due:
            return
        self._monthly_probe_due = now + timedelta(hours=6)
        if self._setup_id is None or self._token is None:
            self.monthly_energy_summary = {"state": "brak_id_lub_sesji"}
            return
        try:
            self._ensure_not_throttled()
            async with self._request(
                "GET", self._monthly_energy_url(),
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Accept": "application/json",
                },
            ) as response:
                if response.status == 429:
                    self._note_rate_limited(response)
                    self.monthly_energy_summary = {"state": "limit_zapytan"}
                    return
                if response.status in (403, 404, 405):
                    self._monthly_probe_disabled = True
                    self.monthly_energy_summary = {"state": "endpoint_niedostepny"}
                    return
                if response.status == 401:
                    self._token = None
                    self.monthly_energy_summary = {"state": "brak_autoryzacji"}
                    return
                if response.status != 200:
                    self.monthly_energy_summary = {"state": "blad_http"}
                    return
                payload = await response.json()
            self.monthly_energy_summary = monthly_energy_shape(payload)
            if self.monthly_energy_summary.get("state") == "dostepna":
                self.monthly_energy_summary["audyt_surowych_kandydatow"] = (
                    summarize_production_candidates(payload)
                )
        except AtlanticRateLimited:
            self.monthly_energy_summary = {"state": "limit_zapytan"}
        except (aiohttp.ClientError, TimeoutError, TypeError, ValueError,
                OverflowError, AtlanticError):
            self.monthly_energy_summary = {"state": "blad_polaczenia"}


    async def async_probe_energy_discovery(self, devices: list[dict]) -> None:
        """Opt-in, one extra GET per poll, at most six per client/setup lifetime.

        Only observed account devices; no arbitrary routes, refresh commands,
        automatic retries, raw payload storage or energy/COP publication.
        """
        selected = discovery_api.targets(devices)
        if not selected:
            self.discovery_summary["state"] = "brak_jednoznacznej_pompy"
            return
        if self._discovery_queue is None:
            self._discovery_queue = [discovery_api.Probe("catalogue", discovery_api.CATALOGUE_URL)]
            self.discovery_summary = {"state": "w_trakcie", "results": {}, "cop_ready": False}
        if not self._discovery_queue:
            return
        try:
            self._ensure_not_throttled()
        except AtlanticRateLimited:
            self.discovery_summary["state"] = "limit_zapytan"
            return
        if self._token is None:
            self.discovery_summary["state"] = "brak_autoryzacji"
            return
        probe = self._discovery_queue.pop(0)
        own_ids = {identifier for _, identifier in selected}
        if ((probe.target_id is not None and probe.target_id not in own_ids)
                or (probe.setup_id is not None and probe.setup_id != self._setup_id)):
            self._discovery_queue.clear()
            self.discovery_summary["state"] = "zmiana_zrodla_przerwano"
            return
        self._discovery_urls = frozenset((probe.url,))
        extra_ids = set()
        stop = False
        try:
            async with self._request("GET", probe.url, headers={
                "Authorization": "Bearer " + self._token, "Accept": "application/json",
            }) as response:
                status = response.status
                if status == 429:
                    self._note_rate_limited(response)
                if status == 401:
                    self._token = None
                if status in (401, 429):
                    stop = True
                if status != 200:
                    result = {"state": "blad_http", "http_status": status}
                else:
                    raw = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        raw.extend(chunk)
                        if len(raw) > discovery_api.MAX_BODY_BYTES:
                            raise ValueError("body limit")
                    payload = json.loads(raw)
                    if probe.key == "catalogue":
                        result, extra_ids = discovery_api.catalogue_summary(payload)
                    elif probe.key.startswith("capabilities_"):
                        reported = next((set(d.get("reported_capability_ids", []))
                                         for d in devices if d["id"] == probe.target_id), set())
                        result = discovery_api.capability_summary(payload, reported, self._discovery_requested_ids)
                    else:
                        result = discovery_api.history_summary(payload)
                    result["http_status"] = 200
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError,
                OverflowError, RecursionError, AtlanticError):
            result = {"state": "blad_odczytu_lub_formatu"}
        finally:
            self._discovery_urls = frozenset()
        result["api_observed_at"] = datetime.now(timezone.utc).isoformat()
        self.discovery_summary["results"][probe.key] = result
        if stop:
            self._discovery_queue.clear()
            self.discovery_summary["state"] = "przerwano_401_lub_429"
            return
        if probe.key == "catalogue":
            self._discovery_requested_ids = set(discovery_api.CORE_IDS) | extra_ids
            self._discovery_queue = discovery_api.build_plan(
                devices, self._setup_id, extra_ids, datetime.now(timezone.utc))
        self.discovery_summary["remaining_requests"] = len(self._discovery_queue)
        self.discovery_summary["state"] = (
            "w_trakcie" if self._discovery_queue else "zakonczono_sprawdz_wyniki")
