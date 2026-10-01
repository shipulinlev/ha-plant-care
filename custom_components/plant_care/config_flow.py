"""Config flows: the Plant Care hub and its plant subentries."""

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    AreaSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from .const import (
    CONF_AREA_ID,
    CONF_FEEDING_INTERVAL,
    CONF_LOCATION_TYPE,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_SPECIES_PID,
    CONF_SPECIES_SEARCH,
    CONF_WATERING_INTERVAL,
    CONF_WEATHER_ENTITY,
    DEFAULT_FEEDING_INTERVAL_DAYS,
    DEFAULT_WATERING_INTERVAL_DAYS,
    DOMAIN,
    SUBENTRY_TYPE_PLANT,
)
from .core.models import LocationType
from .openplantbook import (
    OpenPlantbookAuthError,
    OpenPlantbookClient,
    OpenPlantbookError,
    OpenPlantbookRateLimitError,
    SpeciesMatch,
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

PLANT_NAME_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): TextSelector(),
        vol.Optional(CONF_SPECIES_SEARCH): TextSelector(),
    }
)

_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(
        min=1, max=365, step=1, mode=NumberSelectorMode.BOX, unit_of_measurement="d"
    )
)

PLANT_DETAILS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_LOCATION_TYPE, default=LocationType.INDOOR.value
        ): SelectSelector(
            SelectSelectorConfig(
                options=[location.value for location in LocationType],
                translation_key=CONF_LOCATION_TYPE,
            )
        ),
        vol.Optional(CONF_AREA_ID): AreaSelector(),
        vol.Optional(CONF_SOIL_MOISTURE_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="sensor", device_class="moisture")
        ),
        vol.Optional(CONF_WEATHER_ENTITY): EntitySelector(
            EntitySelectorConfig(domain="weather")
        ),
        vol.Required(
            CONF_WATERING_INTERVAL, default=DEFAULT_WATERING_INTERVAL_DAYS
        ): _INTERVAL_SELECTOR,
        vol.Required(
            CONF_FEEDING_INTERVAL, default=DEFAULT_FEEDING_INTERVAL_DAYS
        ): _INTERVAL_SELECTOR,
    }
)


def _error_key(err: OpenPlantbookError) -> str:
    """Form error for a failed OpenPlantbook call."""
    if isinstance(err, OpenPlantbookAuthError):
        return "invalid_auth"
    if isinstance(err, OpenPlantbookRateLimitError):
        return "rate_limited"
    return "cannot_connect"


def _client_for(hass: HomeAssistant, data: Mapping[str, Any]) -> OpenPlantbookClient:
    return OpenPlantbookClient(
        async_get_clientsession(hass), data[CONF_CLIENT_ID], data[CONF_CLIENT_SECRET]
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
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self._show_hub_form(
            "reconfigure", user_input or dict(entry.data), errors
        )

    async def _async_check_credentials(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Form errors for the given credentials; empty when they work."""
        try:
            await _client_for(self.hass, user_input).async_authenticate()
        except OpenPlantbookError as err:
            return {"base": _error_key(err)}
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


class PlantSubentryFlow(ConfigSubentryFlow):
    """Add a plant: name and species search first, then the details."""

    def __init__(self) -> None:
        self._name = ""
        self._matches: list[SpeciesMatch] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Name the plant and optionally search OpenPlantbook for its species."""
        errors: dict[str, str] = {}
        if user_input is not None:
            search = user_input.get(CONF_SPECIES_SEARCH, "").strip()
            matches: list[SpeciesMatch] = []
            if search:
                try:
                    matches = await _client_for(
                        self.hass, self._get_entry().data
                    ).async_search(search)
                except OpenPlantbookError as err:
                    errors["base"] = _error_key(err)
                else:
                    if not matches:
                        errors[CONF_SPECIES_SEARCH] = "no_species_found"
            if not errors:
                self._name = user_input[CONF_NAME]
                self._matches = matches
                return await self.async_step_details()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                PLANT_NAME_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Species (from the search), location, area, sensors and intervals."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name, data={CONF_NAME: self._name, **user_input}
            )

        schema = PLANT_DETAILS_SCHEMA
        if self._matches:
            schema = schema.extend(
                {vol.Optional(CONF_SPECIES_PID): _species_selector(self._matches)}
            )
        return self.async_show_form(step_id="details", data_schema=schema)


def _species_selector(matches: list[SpeciesMatch]) -> SelectSelector:
    """Dropdown of search results; left empty means no species."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(
                    value=match.pid,
                    label=(
                        f"{match.display_pid} ({match.alias})"
                        if match.alias
                        else match.display_pid
                    ),
                )
                for match in matches
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
