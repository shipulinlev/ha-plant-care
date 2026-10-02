"""Config flow: the Plant Care hub (OpenPlantbook credentials, default weather)."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
)
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import CONF_WEATHER_ENTITY, DOMAIN, SUBENTRY_TYPE_PLANT
from .flow_helpers import client_from_config, form_error_key
from .openplantbook import OpenPlantbookError
from .plant_flow import PlantSubentryFlow

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

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Plants are subentries of the hub."""
        return {SUBENTRY_TYPE_PLANT: PlantSubentryFlow}

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
                # The entry's update listener reloads it.
                return self.async_update_and_abort(entry, data=user_input)

        return self._show_hub_form(
            "reconfigure", user_input or dict(entry.data), errors
        )

    async def _async_check_credentials(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Form errors for the given credentials; empty when they work."""
        try:
            await client_from_config(self.hass, user_input).async_authenticate()
        except OpenPlantbookError as err:
            return {"base": form_error_key(err)}
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
