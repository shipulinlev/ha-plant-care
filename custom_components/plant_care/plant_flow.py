"""Plant subentry flow: adding and editing a plant."""

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntryState,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectOptionDict,
    TextSelector,
)
import voluptuous as vol

from .const import (
    CONF_AREA_ID,
    CONF_PHOTO,
    CONF_PHOTO_UPLOAD,
    CONF_REMOVE_PHOTO,
    CONF_SPECIES_PID,
    CONF_SPECIES_SEARCH,
    RANGE_OVERRIDES,
)
from .coordinator import PlantCareCoordinator
from .core.models import SpeciesProfile
from .flow_helpers import client_from_config, form_error_key
from .openplantbook import OpenPlantbookError, SpeciesMatch
from .photos import InvalidPhoto, async_apply_photo
from .plant_schemas import (
    EDIT_PLANT_DETAILS_SCHEMA,
    NEW_PLANT_DETAILS_SCHEMA,
    PHOTO_SCHEMA,
    PLANT_NAME_SCHEMA,
    RANGE_KEYS,
    match_option,
    species_selector,
    with_species,
)


class PlantSubentryFlow(ConfigSubentryFlow):
    """Add a plant (name and species search, then details) or edit it in one form."""

    def __init__(self) -> None:
        self._name = ""
        self._matches: list[SpeciesMatch] = []
        # The edited plant's species profile, as shown in the edit form.
        self._profile: SpeciesProfile | None = None

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
        """Species (from the search), location, area, sensors, intervals, photo."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = await async_apply_photo(self.hass, user_input, None)
            except InvalidPhoto:
                errors = {CONF_PHOTO_UPLOAD: "invalid_photo"}
            else:
                return self.async_create_entry(
                    title=self._name, data={CONF_NAME: self._name, **data}
                )
        schema = with_species(
            NEW_PLANT_DETAILS_SCHEMA, [match_option(m) for m in self._matches]
        )
        return self.async_show_form(
            step_id="details",
            data_schema=self.add_suggested_values_to_schema(
                schema, _without_upload(user_input or {})
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit the whole plant in one form; a search adds species to pick from."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        if user_input is None:
            if entry.state is ConfigEntryState.LOADED:
                coordinator: PlantCareCoordinator = entry.runtime_data.coordinator
                self._profile = coordinator.species_profile(subentry.subentry_id)
            return self._show_edit_form(_prefill(subentry.data, self._profile), {})

        errors: dict[str, str]
        search = user_input.get(CONF_SPECIES_SEARCH, "").strip()
        if search:
            errors = await self._async_search(search)
            if not errors:
                user_input = {
                    key: value
                    for key, value in user_input.items()
                    if key != CONF_SPECIES_SEARCH
                }
        else:
            errors = _range_errors(user_input)
            if not errors:
                try:
                    data = await async_apply_photo(
                        self.hass, user_input, subentry.data.get(CONF_PHOTO)
                    )
                except InvalidPhoto:
                    errors = {CONF_PHOTO_UPLOAD: "invalid_photo"}
            if not errors:
                # Unchanged prefilled ranges keep following the species.
                data = {
                    key: value
                    for key, value in data.items()
                    if not _is_species_default(key, value, self._profile)
                }
                if CONF_AREA_ID in subentry.data:
                    data[CONF_AREA_ID] = subentry.data[CONF_AREA_ID]
                # The hub's update listener reloads the entry.
                return self.async_update_and_abort(
                    entry, subentry, title=data[CONF_NAME], data=data
                )
        return self._show_edit_form(_without_upload(user_input), errors)

    async def _async_accept_name(self, user_input: dict[str, Any]) -> dict[str, str]:
        """Run the optional species search; keep name and matches when it works."""
        errors = await self._async_search(
            user_input.get(CONF_SPECIES_SEARCH, "").strip()
        )
        if not errors:
            self._name = user_input[CONF_NAME]
        return errors

    async def _async_search(self, search: str) -> dict[str, str]:
        """Search OpenPlantbook (nothing for empty text); keep the matches."""
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
        self._matches = matches
        return {}

    def _show_edit_form(
        self, values: dict[str, Any], errors: dict[str, str]
    ) -> SubentryFlowResult:
        """The edit form: the current species and the search matches to pick from."""
        options = [match_option(match) for match in self._matches]
        plant = self._get_reconfigure_subentry().data
        current = plant.get(CONF_SPECIES_PID)
        if current and current not in {match.pid for match in self._matches}:
            label = (self._profile.display_pid if self._profile else None) or current
            options.insert(0, SelectOptionDict(value=current, label=label))
        species = (
            {vol.Optional(CONF_SPECIES_PID): species_selector(options)}
            if options
            else {}
        )
        remove = (
            {vol.Optional(CONF_REMOVE_PHOTO): BooleanSelector()}
            if CONF_PHOTO in plant
            else {}
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): TextSelector(),
                **species,
                vol.Optional(CONF_SPECIES_SEARCH): TextSelector(),
                **EDIT_PLANT_DETAILS_SCHEMA.schema,
                **PHOTO_SCHEMA,
                **remove,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, values),
            errors=errors,
        )

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


def _prefill(data: Mapping[str, Any], profile: SpeciesProfile | None) -> dict[str, Any]:
    """The plant's settings, with species values for ranges it does not override."""
    values = {
        key: value
        for key, value in data.items()
        if key not in (CONF_AREA_ID, CONF_PHOTO)
    }
    if profile is not None:
        for key in RANGE_KEYS:
            default = getattr(profile, key)
            if values.get(key) is None and default is not None:
                values[key] = default
    return values


def _without_upload(values: dict[str, Any]) -> dict[str, Any]:
    """Form values to show again: a used or rejected upload is gone."""
    return {key: value for key, value in values.items() if key != CONF_PHOTO_UPLOAD}


def _is_species_default(key: str, value: Any, profile: SpeciesProfile | None) -> bool:
    return key in RANGE_KEYS and profile is not None and value == getattr(profile, key)


def _range_errors(user_input: dict[str, Any]) -> dict[str, str]:
    for low_key, high_key in RANGE_OVERRIDES:
        low, high = user_input.get(low_key), user_input.get(high_key)
        if low is not None and high is not None and low > high:
            return {"base": "invalid_range"}
    return {}
