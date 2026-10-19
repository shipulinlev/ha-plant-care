"""Form schemas of the plant flow: name, details, ranges, photo, species."""

from homeassistant.const import CONF_NAME
from homeassistant.helpers.selector import (
    AreaSelector,
    EntitySelector,
    EntitySelectorConfig,
    FileSelector,
    FileSelectorConfig,
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
    CONF_PHOTO_UPLOAD,
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
from .openplantbook import SpeciesMatch
from .photos import CONTENT_TYPES

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

PHOTO_SCHEMA = {
    vol.Optional(CONF_PHOTO_UPLOAD): FileSelector(
        FileSelectorConfig(accept=",".join(CONTENT_TYPES.values()))
    )
}

# The area is chosen once when adding; afterwards the plant moves with its device.
NEW_PLANT_DETAILS_SCHEMA = _DETAILS_SCHEMA.extend(
    {vol.Optional(CONF_AREA_ID): AreaSelector(), **PHOTO_SCHEMA}
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

RANGE_KEYS = tuple(key for pair in RANGE_OVERRIDES for key in pair)


def with_species(schema: vol.Schema, options: list[SelectOptionDict]) -> vol.Schema:
    """Add the species dropdown when there is a species to pick."""
    if not options:
        return schema
    return schema.extend({vol.Optional(CONF_SPECIES_PID): species_selector(options)})


def match_option(match: SpeciesMatch) -> SelectOptionDict:
    label = f"{match.display_pid} ({match.alias})" if match.alias else match.display_pid
    return SelectOptionDict(value=match.pid, label=label)


def species_selector(options: list[SelectOptionDict]) -> SelectSelector:
    """Species dropdown; left empty means no species."""
    return SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )
