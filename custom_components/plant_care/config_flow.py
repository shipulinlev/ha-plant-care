"""Config flow: the Plant Care hub (OpenPlantbook credentials, default weather)."""

from collections.abc import Mapping
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
            errors = await self._async_check_credentials(user_input)
            if not errors:
                return self.async_create_entry(title="Plant Care", data=user_input)

        return self._show_hub_form("user", user_input, errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change credentials or the default weather entity of the hub."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_check_credentials(user_input)
            if not errors:
                # Full replace, not data_updates: a cleared weather entity must
                # disappear from the data, and the form holds every hub key.
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self._show_hub_form(
            "reconfigure", user_input or dict(entry.data), errors
        )

    async def _async_check_credentials(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Form errors for the given credentials; empty when they work."""
        client = OpenPlantbookClient(
            async_get_clientsession(self.hass),
            user_input[CONF_CLIENT_ID],
            user_input[CONF_CLIENT_SECRET],
        )
        try:
            await client.async_authenticate()
        except OpenPlantbookAuthError:
            return {"base": "invalid_auth"}
        except OpenPlantbookRateLimitError:
            return {"base": "rate_limited"}
        except OpenPlantbookError:
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error while checking credentials")
            return {"base": "unknown"}
        return {}

    def _show_hub_form(
        self,
        step_id: str,
        values: Mapping[str, Any] | None,
        errors: dict[str, str],
    ) -> ConfigFlowResult:
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(HUB_SCHEMA, values),
            errors=errors,
            description_placeholders={"api_keys_url": OPENPLANTBOOK_URL},
        )
