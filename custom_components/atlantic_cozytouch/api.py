"""Minimal Atlantic HTTP client. There is intentionally no write-device API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


class AtlanticError(Exception):
    """The Atlantic service could not supply valid data."""


class AtlanticAuthError(AtlanticError):
    """Atlantic rejected the account credentials."""


class AtlanticRateLimited(AtlanticError):
    """Atlantic requested fewer requests."""


class AtlanticReadOnlyClient:
    """Only the vendor's token endpoint (POST) and setup endpoint (GET)."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None
        self._token_expiry = datetime.min.replace(tzinfo=timezone.utc)

    async def _authenticate(self) -> None:
        # The ONE permitted POST: exchange credentials for an access token.
        form = aiohttp.FormData(
            {
                "grant_type": "password",
                "scope": "openid",
                "username": "GA-PRIVATEPERSON/" + self._username,
                "password": self._password,
            }
        )
        try:
            async with self._session.post(
                API_ORIGIN + TOKEN_PATH,
                data=form,
                headers={"Authorization": "Basic " + ATLANTIC_PUBLIC_CLIENT_ID},
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS),
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    raise AtlanticError("Atlantic login redirected unexpectedly")
                if response.status in (400, 401, 403):
                    raise AtlanticAuthError("Atlantic login rejected")
                if response.status == 429:
                    raise AtlanticRateLimited("Atlantic login rate limited")
                if response.status != 200:
                    raise AtlanticError("Atlantic login service unavailable")
                body = await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise AtlanticError("Atlantic login connection failed") from exc

        if not isinstance(body, dict) or not isinstance(body.get("access_token"), str):
            raise AtlanticError("Atlantic returned no access token")

        self._token = body["access_token"]
        seconds = body.get("expires_in", 3600)
        try:
            valid_for = max(60, float(seconds))
        except (ValueError, TypeError):
            valid_for = 3600
        self._token_expiry = datetime.now(timezone.utc) + timedelta(seconds=max(1, valid_for - 60))
        # Password is kept by Home Assistant's config entry for later reauth.

    async def _get_setup(self) -> object:
        if self._token is None:
            raise AtlanticAuthError("No Atlantic access token")

        try:
            async with self._session.get(
                API_ORIGIN + READ_PATH,
                headers={
                    "Authorization": "Bearer " + self._token,
                    "Accept": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS),
                allow_redirects=False,
            ) as response:
                if response.status == 401:
                    raise AtlanticAuthError("Atlantic session expired")
                if response.status == 429:
                    raise AtlanticRateLimited("Atlantic read rate limited")
                if response.status != 200:
                    raise AtlanticError("Atlantic read unavailable")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise AtlanticError("Atlantic read connection failed") from exc

    async def async_read(self) -> list[dict]:
        """Fetch current measurements. Does not invoke any writable endpoint."""
        if self._token is None or datetime.now(timezone.utc) >= self._token_expiry:
            await self._authenticate()
        try:
            payload = await self._get_setup()
        except AtlanticAuthError:
            self._token = None
            await self._authenticate()
            payload = await self._get_setup()

        try:
            return extract_devices(payload)
        except ValueError as exc:
            raise AtlanticError("Unexpected Atlantic response schema") from exc
