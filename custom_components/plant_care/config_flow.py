"""Config flow: the Plant Care hub (OpenPlantbook credentials, default weather)."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import CONF_WEATHER_ENTITY, DOMAIN
from .openplantbook import (
    OpenPlantbookAuthError,
    OpenPlantbookClient,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
)

_LOGGER = logging.getLogger(__name__)

# Kept out of strings.json: hassfest rejects URLs in translations.
OPENPLANTBOOK_URL = "https://open.plantbook.io"

HUB_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): TextSelector(),
        vol.Required(CONF_CLIENT_SECRET): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_WEATHER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="weather")
        ),
    }
)


class PlantCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up the single Plant Care hub."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for OpenPlantbook credentials and check them."""
        errors: dict[str, str] = {}
        if user_input is not None:
            client = OpenPlantbookClient(
                async_get_clientsession(self.hass),
                user_input[CONF_CLIENT_ID],
                user_input[CONF_CLIENT_SECRET],
            )
            try:
                await client.async_authenticate()
            except OpenPlantbookAuthError:
                errors["base"] = "invalid_auth"
            except OpenPlantbookRateLimitError:
                errors["base"] = "rate_limited"
            except OpenPlantbookError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while checking credentials")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title="Plant Care", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(HUB_SCHEMA, user_input),
            errors=errors,
            description_placeholders={"api_keys_url": OPENPLANTBOOK_URL},
        )
