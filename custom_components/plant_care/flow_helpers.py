"""Helpers shared by the hub and plant flows."""

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .openplantbook import (
    OpenPlantbookAuthError,
    OpenPlantbookClient,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
)


def form_error_key(err: OpenPlantbookError) -> str:
    """Form error for a failed OpenPlantbook call."""
    if isinstance(err, OpenPlantbookAuthError):
        return "invalid_auth"
    if isinstance(err, OpenPlantbookRateLimitError):
        return "rate_limited"
    return "cannot_connect"


def client_from_config(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> OpenPlantbookClient:
    return OpenPlantbookClient(
        async_get_clientsession(hass), data[CONF_CLIENT_ID], data[CONF_CLIENT_SECRET]
    )
