"""Constants for the Plant Care integration."""

from typing import Final

DOMAIN: Final = "plant_care"

# Hub config entry: default weather entity for outdoor plants (optional).
# A plant subentry may override it with the same key.
CONF_WEATHER_ENTITY: Final = "weather_entity"

SUBENTRY_TYPE_PLANT: Final = "plant"

# Plant subentry data.
CONF_SPECIES_PID: Final = "species_pid"
CONF_LOCATION_TYPE: Final = "location_type"
CONF_SOIL_MOISTURE_ENTITY: Final = "soil_moisture_entity"
CONF_WATERING_INTERVAL: Final = "initial_watering_interval_days"
CONF_FEEDING_INTERVAL: Final = "feeding_interval_days"
# One-time handoff from the flow to device creation, then removed from the
# data: the area lives only in the device registry.
CONF_AREA_ID: Final = "area_id"
# File name of the uploaded photo in the photo folder (photos.py).
CONF_PHOTO: Final = "photo"

# Plant flow only (not stored).
CONF_SPECIES_SEARCH: Final = "species_search"
CONF_PHOTO_UPLOAD: Final = "photo_upload"
CONF_REMOVE_PHOTO: Final = "remove_photo"

DEFAULT_WATERING_INTERVAL_DAYS: Final = 7
DEFAULT_FEEDING_INTERVAL_DAYS: Final = 30

# Plant subentry data: optional species range overrides, as (min, max) pairs
# named like the SpeciesProfile fields they replace.
RANGE_OVERRIDES: Final = (
    ("min_temp", "max_temp"),
    ("min_env_humid", "max_env_humid"),
    ("min_soil_moist", "max_soil_moist"),
)
