"""Atlantic HTTP client with an explicit two-operation allowlist.

No operation can mutate the device: POST is permitted only for OAuth login,
and GET only for reading the vendor's setup snapshot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import logging

import aiohttp

from .const import (
    API_ORIGIN,
    ATLANTIC_PUBLIC_CLIENT_ID,
    HTTP_TIMEOUT_SECONDS,
    READ_PATH,
    TOKEN_PATH,
)
from .readings import extract_devices

_LOGGER = logging.getLogger(__name__)

# An exact-method, exact-URL allowlist, not merely a hostname filter.
_ALLOWED_HTTP_OPERATIONS = frozenset(
    {
        ("POST", API_ORIGIN + TOKEN_PATH),  # Authentication, never device control.
        ("GET", API_ORIGIN + READ_PATH),   # Status/measurement snapshot.
    }
)
_MIN_THROTTLE_SECONDS = 300
_MAX_THROTTLE_SECONDS = 3600
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
        self._session = session
        self._username = username.strip()
        self._password = password
        self._token: str | None = None
        self._token_expiry = datetime.min.replace(tzinfo=timezone.utc)
        self._cooldown_until = datetime.min.replace(tzinfo=timezone.utc)

    def _request(self, method: str, url: str, **kwargs):
        """Reject all methods/routes except vendor login and snapshot read.

        The caller cannot override TLS verification, configure a proxy or
        enable HTTP redirects via request parameters.
        """
        if (method, url) not in _ALLOWED_HTTP_OPERATIONS:
            raise AtlanticError("Blocked operation outside read-only HTTP allowlist")
        if {"ssl", "proxy", "proxy_auth", "auth", "allow_redirects", "timeout"} & kwargs.keys():
            raise AtlanticError("Forbidden request transport override")

        options = dict(kwargs)
        options["timeout"] = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)
        options["allow_redirects"] = False

        if method == "POST":
            return self._session.post(url, **options)
        return self._session.get(url, **options)

    def _ensure_not_throttled(self) -> None:
        if datetime.now(timezone.utc) < self._cooldown_until:
            raise AtlanticRateLimited("Atlantic rate-limit cooldown active")

    def _note_rate_limited(self, response: object) -> None:
        """Respect Retry-After (seconds or HTTP date), clamped to 5–60 minutes."""
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
        # Handles malformed, negative, or huge values.
        if not (_MIN_THROTTLE_SECONDS <= wait <= _MAX_THROTTLE_SECONDS):
            wait = max(_MIN_THROTTLE_SECONDS, min(_MAX_THROTTLE_SECONDS, wait)) if wait == wait else _DEFAULT_THROTTLE_SECONDS
        self._cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=wait)

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
            return extract_devices(payload)
        except ValueError:
            raise AtlanticError("Unexpected Atlantic response schema") from None
