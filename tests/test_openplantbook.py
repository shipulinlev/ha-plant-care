"""Tests for the OpenPlantbook API client."""

from datetime import timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import ClientConnectionError
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.plant_care.core.models import SpeciesProfile
from custom_components.plant_care.openplantbook import (
    BASE_URL,
    OpenPlantbookAuthError,
    OpenPlantbookClient,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
    SpeciesMatch,
)

TOKEN_URL = f"{BASE_URL}/token/"
SEARCH_URL = f"{BASE_URL}/plant/search"
PID = "abelia chinensis"
DETAIL_URL = f"{BASE_URL}/plant/detail/{PID}/"
TOKEN_LIFETIME = timedelta(hours=1)
TOKEN = {
    "access_token": "token-1",
    "expires_in": TOKEN_LIFETIME.total_seconds(),
    "token_type": "Bearer",
}
SEARCH_RESPONSE = {
    "count": 1,
    "next": None,
    "previous": None,
    "results": [
        {
            "pid": PID,
            "display_pid": "Abelia chinensis",
            "alias": "chinese abelia",
            "category": "Caprifoliaceae, Abelia",
        }
    ],
}
DETAIL_RESPONSE = {
    "pid": PID,
    "display_pid": "Abelia chinensis",
    "alias": "chinese abelia",
    "max_light_lux": 30000,
    "min_light_lux": 3500,
    "max_temp": 35,
    "min_temp": 8,
    "max_env_humid": 85,
    "min_env_humid": 30,
    "max_soil_moist": 60,
    "min_soil_moist": 15,
    "max_soil_ec": 2000,
    "min_soil_ec": 350,
}


@pytest.fixture
async def client(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> OpenPlantbookClient:
    """A client on the mocked HA session (the mock must exist first)."""
    return OpenPlantbookClient(async_get_clientsession(hass), "my-id", "my-secret")


def _calls(mock: AiohttpClientMocker, method: str, url: str) -> list[Any]:
    return [
        call
        for call in mock.mock_calls
        if call[0] == method and call[1].with_query(None) == URL(url)
    ]


async def test_authenticate_posts_client_credentials(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """The token is requested with the OAuth2 client credentials grant."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)

    await client.async_authenticate()

    (call,) = _calls(aioclient_mock, "post", TOKEN_URL)
    assert call[2] == {
        "grant_type": "client_credentials",
        "client_id": "my-id",
        "client_secret": "my-secret",
    }


async def test_search_returns_matches(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Search sends the text as alias with the bearer token and parses results."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(SEARCH_URL, params={"alias": "abelia"}, json=SEARCH_RESPONSE)

    matches = await client.async_search("abelia")

    assert matches == [
        SpeciesMatch(pid=PID, display_pid="Abelia chinensis", alias="chinese abelia")
    ]
    (call,) = _calls(aioclient_mock, "get", SEARCH_URL)
    assert call[3]["Authorization"] == "Bearer token-1"


async def test_get_profile_parses_ranges(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Detail is mapped onto the species ranges the engine uses."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, json=DETAIL_RESPONSE)

    profile = await client.async_get_profile(PID)

    assert profile == SpeciesProfile(
        min_temp=8,
        max_temp=35,
        min_env_humid=30,
        max_env_humid=85,
        min_soil_moist=15,
        max_soil_moist=60,
    )


async def test_get_profile_with_missing_ranges(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Absent or null ranges stay unknown."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, json={"pid": PID, "min_temp": 8, "max_temp": None})

    profile = await client.async_get_profile(PID)

    assert profile == SpeciesProfile(min_temp=8)


async def test_token_is_reused_until_expiry(
    client: OpenPlantbookClient,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """One token serves many calls and is renewed shortly before it expires."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, json=DETAIL_RESPONSE)

    await client.async_get_profile(PID)
    await client.async_get_profile(PID)
    assert len(_calls(aioclient_mock, "post", TOKEN_URL)) == 1

    freezer.tick(TOKEN_LIFETIME - timedelta(minutes=4))
    await client.async_get_profile(PID)
    assert len(_calls(aioclient_mock, "post", TOKEN_URL)) == 2


async def test_rejected_token_is_renewed_once(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 on an API call drops the token, re-authenticates and retries."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    statuses = iter([HTTPStatus.UNAUTHORIZED, HTTPStatus.OK])

    async def detail(method: str, url: URL, data: Any) -> AiohttpClientMockResponse:
        return AiohttpClientMockResponse(
            method, url, status=next(statuses), json=DETAIL_RESPONSE
        )

    aioclient_mock.get(DETAIL_URL, side_effect=detail)

    profile = await client.async_get_profile(PID)

    assert profile.min_temp == 8
    assert len(_calls(aioclient_mock, "post", TOKEN_URL)) == 2


async def test_unauthorized_after_renewal_is_auth_error(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A second 401 in a row is reported, not retried forever."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, status=HTTPStatus.UNAUTHORIZED)

    with pytest.raises(OpenPlantbookAuthError):
        await client.async_get_profile(PID)
    assert len(_calls(aioclient_mock, "get", DETAIL_URL)) == 2


@pytest.mark.parametrize(
    "status", [HTTPStatus.BAD_REQUEST, HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN]
)
async def test_bad_credentials_are_auth_error(
    client: OpenPlantbookClient,
    aioclient_mock: AiohttpClientMocker,
    status: HTTPStatus,
) -> None:
    """The token endpoint refusing the credentials is an auth error."""
    aioclient_mock.post(TOKEN_URL, status=status, json={"error": "invalid_client"})

    with pytest.raises(OpenPlantbookAuthError):
        await client.async_authenticate()


async def test_token_response_without_access_token_is_auth_error(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """A token response without a token is treated as failed authentication."""
    aioclient_mock.post(TOKEN_URL, json={"error": "invalid_client"})

    with pytest.raises(OpenPlantbookAuthError):
        await client.async_authenticate()


async def test_rate_limit_on_api_call(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """HTTP 429 from an endpoint is reported as a rate-limit error."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, status=HTTPStatus.TOO_MANY_REQUESTS)

    with pytest.raises(OpenPlantbookRateLimitError):
        await client.async_get_profile(PID)


async def test_rate_limit_on_token(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """HTTP 429 from the token endpoint is a rate-limit, not an auth error."""
    aioclient_mock.post(TOKEN_URL, status=HTTPStatus.TOO_MANY_REQUESTS)

    with pytest.raises(OpenPlantbookRateLimitError):
        await client.async_authenticate()


async def test_server_error(
    client: OpenPlantbookClient, aioclient_mock: AiohttpClientMocker
) -> None:
    """Other HTTP errors are generic client errors."""
    aioclient_mock.post(TOKEN_URL, json=TOKEN)
    aioclient_mock.get(DETAIL_URL, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    with pytest.raises(OpenPlantbookError) as err:
        await client.async_get_profile(PID)
    assert type(err.value) is OpenPlantbookError


@pytest.mark.parametrize("exc", [ClientConnectionError(), TimeoutError()])
async def test_network_errors(
    client: OpenPlantbookClient,
    aioclient_mock: AiohttpClientMocker,
    exc: Exception,
) -> None:
    """Connection problems and timeouts are generic client errors."""
    aioclient_mock.post(TOKEN_URL, exc=exc)

    with pytest.raises(OpenPlantbookError) as err:
        await client.async_authenticate()
    assert type(err.value) is OpenPlantbookError
