"""Async client for the OpenPlantbook API (species search and ranges)."""

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Final
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.util import dt as dt_util

from .core.models import SpeciesProfile

BASE_URL: Final = "https://open.plantbook.io/api/v1"
_TOKEN_URL: Final = f"{BASE_URL}/token/"
_REQUEST_TIMEOUT: Final = ClientTimeout(total=15)
# Renew the token this long before it expires, so it never lapses mid-request.
_TOKEN_RENEW_MARGIN: Final = timedelta(minutes=5)
_CREDENTIALS_REJECTED: Final = frozenset(
    {HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}
)
_PROFILE_FIELDS: Final = tuple(field.name for field in fields(SpeciesProfile))


class OpenPlantbookError(Exception):
    """OpenPlantbook is unreachable or answered with an error."""


class OpenPlantbookAuthError(OpenPlantbookError):
    """The client id or secret was rejected."""


class OpenPlantbookRateLimitError(OpenPlantbookError):
    """The API limit was exceeded (HTTP 429)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SpeciesMatch:
    """One species found by a search."""

    pid: str
    display_pid: str
    alias: str


class OpenPlantbookClient:
    """OpenPlantbook API with an OAuth2 client-credentials token cached in memory."""

    def __init__(
        self, session: ClientSession, client_id: str, client_secret: str
    ) -> None:
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expires = datetime.min.replace(tzinfo=dt_util.UTC)

    async def async_authenticate(self) -> None:
        """Get a new access token; also validates the credentials."""
        status, body = await self._request(
            "post",
            _TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            },
        )
        if status in _CREDENTIALS_REJECTED:
            raise OpenPlantbookAuthError
        if status >= HTTPStatus.BAD_REQUEST:
            raise OpenPlantbookError(f"Token request failed with HTTP {status}")
        if not isinstance(body, dict) or not body.get("access_token"):
            raise OpenPlantbookAuthError
        self._token = str(body["access_token"])
        self._token_expires = dt_util.utcnow() + timedelta(
            seconds=float(body.get("expires_in", 0))
        )

    async def async_search(self, text: str) -> list[SpeciesMatch]:
        """Species whose name matches the text."""
        body = await self._api_get(f"{BASE_URL}/plant/search", {"alias": text})
        return [
            SpeciesMatch(
                pid=row["pid"],
                display_pid=row.get("display_pid") or row["pid"],
                alias=row.get("alias") or "",
            )
            for row in body.get("results", [])
        ]

    async def async_get_profile(self, pid: str) -> SpeciesProfile:
        """Environment ranges of a species; unknown ranges are None."""
        body = await self._api_get(f"{BASE_URL}/plant/detail/{quote(pid, safe='')}/")
        return SpeciesProfile(
            **{name: _number(body.get(name)) for name in _PROFILE_FIELDS}
        )

    async def _api_get(
        self, url: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        # A token can be revoked before it expires: renew once on HTTP 401.
        for _ in range(2):
            if self._token is None or (
                dt_util.utcnow() >= self._token_expires - _TOKEN_RENEW_MARGIN
            ):
                await self.async_authenticate()
            status, body = await self._request(
                "get",
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            if status == HTTPStatus.UNAUTHORIZED:
                self._token = None
                continue
            if status == HTTPStatus.FORBIDDEN:
                raise OpenPlantbookAuthError
            if status >= HTTPStatus.BAD_REQUEST or not isinstance(body, dict):
                raise OpenPlantbookError(f"Request to {url} failed with HTTP {status}")
            return body
        raise OpenPlantbookAuthError

    async def _request(self, method: str, url: str, **kwargs: Any) -> tuple[int, Any]:
        """Send a request; return the status and the JSON body (None on errors)."""
        try:
            async with self._session.request(
                method, url, timeout=_REQUEST_TIMEOUT, **kwargs
            ) as response:
                if response.status == HTTPStatus.TOO_MANY_REQUESTS:
                    raise OpenPlantbookRateLimitError
                if response.status >= HTTPStatus.BAD_REQUEST:
                    return response.status, None
                return response.status, await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            raise OpenPlantbookError(f"Request to {url} failed: {err!r}") from err


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)
