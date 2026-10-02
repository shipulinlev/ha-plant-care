"""Plant subentry flow: adding and editing a plant."""

from typing import Any

from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.const import CONF_NAME
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
    RANGE_OVERRIDES,
)
from .core.models import LocationType
from .flow_helpers import client_from_config, form_error_key
from .openplantbook import OpenPlantbookError, SpeciesMatch

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

_DETAILS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_LOCATION_TYPE, default=LocationType.INDOOR.value
        ): SelectSelector(
            SelectSelectorConfig(
                options=[location.value for location in LocationType],
                translation_key=CONF_LOCATION_TYPE,
            )
        ),
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

# The area is chosen once when adding; afterwards the plant moves with its device.
NEW_PLANT_DETAILS_SCHEMA = _DETAILS_SCHEMA.extend(
    {vol.Optional(CONF_AREA_ID): AreaSelector()}
)


def _range_selector(low: float, high: float, step: float, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=low,
            max=high,
            step=step,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement=unit,
        )
    )


_TEMP = _range_selector(-50, 60, 0.5, "°C")
_PERCENT = _range_selector(0, 100, 1, "%")
_RANGE_SELECTORS = (_TEMP, _PERCENT, _PERCENT)

# Species range overrides take precedence over OpenPlantbook values.
EDIT_PLANT_DETAILS_SCHEMA = _DETAILS_SCHEMA.extend(
    {
        vol.Optional(key): selector
        for pair, selector in zip(RANGE_OVERRIDES, _RANGE_SELECTORS, strict=True)
        for key in pair
    }
)

# Keys the details steps do not show: they are carried over or set elsewhere.
_NOT_IN_DETAILS = (CONF_NAME, CONF_SPECIES_PID, CONF_AREA_ID)


class PlantSubentryFlow(ConfigSubentryFlow):
    """Add or edit a plant: name and species search first, then the details."""

    def __init__(self) -> None:
        self._name = ""
        self._matches: list[SpeciesMatch] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Name the plant and optionally search OpenPlantbook for its species."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_accept_name(user_input)
            if not errors:
                return await self.async_step_details()
        return self._show_name_form("user", user_input, errors)

    async def async_step_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Species (from the search), location, area, sensors and intervals."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name, data={CONF_NAME: self._name, **user_input}
            )
        return self.async_show_form(
            step_id="details", data_schema=self._with_species(NEW_PLANT_DETAILS_SCHEMA)
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Rename the plant; a new search replaces its species."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_accept_name(user_input)
            if not errors:
                return await self.async_step_reconfigure_details()
        current = {CONF_NAME: self._get_reconfigure_subentry().data[CONF_NAME]}
        return self._show_name_form("reconfigure", user_input or current, errors)

    async def async_step_reconfigure_details(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit details and species range overrides."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _range_errors(user_input)
            if not errors:
                data = {CONF_NAME: self._name, **user_input}
                # Without a new search the species is kept; after one, the
                # dropdown decides (left empty removes the species).
                if not self._matches and CONF_SPECIES_PID in subentry.data:
                    data[CONF_SPECIES_PID] = subentry.data[CONF_SPECIES_PID]
                if CONF_AREA_ID in subentry.data:
                    data[CONF_AREA_ID] = subentry.data[CONF_AREA_ID]
                # The hub's update listener reloads the entry.
                return self.async_update_and_abort(
                    entry, subentry, title=self._name, data=data
                )

        current = user_input or {
            key: value
            for key, value in subentry.data.items()
            if key not in _NOT_IN_DETAILS
        }
        return self.async_show_form(
            step_id="reconfigure_details",
            data_schema=self.add_suggested_values_to_schema(
                self._with_species(EDIT_PLANT_DETAILS_SCHEMA), current
            ),
            errors=errors,
        )

    async def _async_accept_name(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Run the optional species search; keep name and matches when it works."""
        search = user_input.get(CONF_SPECIES_SEARCH, "").strip()
        matches: list[SpeciesMatch] = []
        if search:
            try:
                matches = await client_from_config(
                    self.hass, self._get_entry().data
                ).async_search(search)
            except OpenPlantbookError as err:
                return {"base": form_error_key(err)}
            if not matches:
                return {CONF_SPECIES_SEARCH: "no_species_found"}
        self._name = user_input[CONF_NAME]
        self._matches = matches
        return {}

    def _show_name_form(
        self,
        step_id: str,
        values: dict[str, Any] | None,
        errors: dict[str, str],
    ) -> SubentryFlowResult:
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(PLANT_NAME_SCHEMA, values),
            errors=errors,
        )

    def _with_species(self, schema: vol.Schema) -> vol.Schema:
        """Add the species dropdown when there are search results."""
        if not self._matches:
            return schema
        return schema.extend(
            {vol.Optional(CONF_SPECIES_PID): _species_selector(self._matches)}
        )


def _range_errors(user_input: dict[str, Any]) -> dict[str, str]:
    for low_key, high_key in RANGE_OVERRIDES:
        low, high = user_input.get(low_key), user_input.get(high_key)
        if low is not None and high is not None and low > high:
            return {"base": "invalid_range"}
    return {}


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
