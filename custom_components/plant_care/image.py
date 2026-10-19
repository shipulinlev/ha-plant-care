"""The plant's photo: uploaded in the plant's settings, else the species photo."""

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PHOTO
from .coordinator import PlantCareCoordinator
from .entity import PlantCareEntity
from .photos import content_type, photo_path, photo_updated_at
from .plants import plant_subentries
from .runtime import PlantCareConfigEntry

# Entities only read coordinator data and local files.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PlantCareConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a photo entity to every plant, bound to its plant subentry."""
    coordinator = entry.runtime_data.coordinator
    for subentry in plant_subentries(entry):
        async_add_entities(
            [PlantPhoto(hass, coordinator, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class PlantPhoto(PlantCareEntity, ImageEntity):
    """The uploaded photo, served by HA's image proxy.

    Without an upload, the picture is the species photo URL from the cached
    OpenPlantbook profile, as on the next watering sensor; the entity then
    serves no image of its own. A photo change reloads the hub, so the
    uploaded photo is fixed for the entity's lifetime.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: PlantCareCoordinator,
        subentry: ConfigSubentry,
    ) -> None:
        PlantCareEntity.__init__(self, coordinator, subentry.subentry_id, "photo")
        ImageEntity.__init__(self, hass)
        name = subentry.data.get(CONF_PHOTO)
        self._path = photo_path(hass, name) if name else None
        if name and self._path:
            self._attr_content_type = content_type(name)

    async def async_added_to_hass(self) -> None:
        """Date the image (the entity's state) by the photo file."""
        await super().async_added_to_hass()
        if self._path:
            self._attr_image_last_updated = await self.hass.async_add_executor_job(
                photo_updated_at, self._path
            )

    @property
    def available(self) -> bool:
        """A photo does not depend on the care plan."""
        return self.coordinator.last_update_success

    @property
    def entity_picture(self) -> str | None:
        """The image proxy for an uploaded photo, else the species photo."""
        if self._path:
            return super().entity_picture
        profile = self.coordinator.species_profile(self._plant_id)
        return profile.image_url if profile else None

    def image(self) -> bytes | None:
        """The uploaded photo's bytes; None without one. Blocking."""
        if not self._path:
            return None
        try:
            return self._path.read_bytes()
        except OSError:
            return None
