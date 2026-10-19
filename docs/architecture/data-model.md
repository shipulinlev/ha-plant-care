# Data model: hub, plants, devices, rooms

Modules: `config_flow.py` (hub), `plant_flow.py` (plants), `flow_helpers.py`, `const.py` (all data keys).

## Hub and plants
- Domain `plant_care`.
- **Hub** = the config entry, exactly one per installation (`"single_config_entry": true` in the manifest). Data: `client_id`, `client_secret` (OpenPlantbook), optional `weather_entity` (default for outdoor plants). Created by the `user` step, edited by `reconfigure` (credentials are re-checked, entry reloaded).
- **Plant** = config subentry of type `plant`. Added by `user` → `details`, edited in the single `reconfigure` form, deleted the standard HA way.
- The edit form is prefilled with the plant's settings, its current species (labelled with the cached display name) and, for ranges without an override, the cached OpenPlantbook values. A search text resubmits the form with the matches added to the species dropdown; empty species removes it. On save, a range value equal to the shown species value is not stored, so only ranges the user actually changed become overrides. Without a loaded hub there is no cached profile, so nothing is prefilled from it.
- Plant subentry data: `name`, `species_pid` (optional), `location_type` (`indoor` | `outdoor`), `soil_moisture_entity` (optional), `weather_entity` (optional per-plant override of the hub default), `initial_watering_interval_days`, `feeding_interval_days`, optional species range overrides (`RANGE_OVERRIDES` in `const.py`, named like the `SpeciesProfile` fields they replace).
- The settings feed the engine's `CarePlan`, which also reports the effective intervals behind the next dates: `watering_interval` (initial or learned interval × climate multiplier) and `feeding_interval` (`feeding_interval_days` × season factor); see `engine.md`.
- Inside the integration a plant is identified by its `subentry_id` (also the CareLog `plant_id`), never by name or `entity_id`.
- Deleting a plant deletes its device and its care history.

## Plant flow behaviour
- Step one: name plus optional species search text. Search errors (`invalid_auth`, `rate_limited`, `cannot_connect`, field error `no_species_found`) keep the user on step one; an empty search continues without a species.
- Details: the species dropdown appears only after a search (left empty = no species). On edit, no new search keeps the current species; after a search the dropdown decides, so leaving it empty removes the species.
- A minimum override above its maximum is `invalid_range`.
- Saving an edit replaces the whole subentry data, so cleared optional fields disappear.

## Device and room
- Each plant has exactly one device, bound to its subentry (`config_subentry_id`), with `identifiers={(DOMAIN, subentry_id)}` and the plant's name. All plant entities belong to it. `devices.py` creates or renames the devices on every setup.
- **Device `model` = species name**: OpenPlantbook's readable `display_pid` from the profile cache, the `species_pid` while no name is cached (never fetched, or OpenPlantbook down), `None` for a plant without a species. Set on every setup and again after every coordinator refresh, since a refresh may fetch a profile. Only `species_pid` is stored in the subentry; the profile cache is the single home of the name.
- The hub entry has an update listener that reloads it, so adding, editing or deleting a plant applies immediately (devices, history pruning, later the coordinator).
- Deleting a plant: HA removes the subentry's device itself; setup prunes CareLog history of plants that no longer exist.
- **The room is the device's area.** The area lives only in the device registry; subentry data never holds it as lasting state.
- Moving a plant: the user changes the device area in the HA UI, or calls `plant_care.move`, which does the same. The integration listens to `EVENT_DEVICE_REGISTRY_UPDATED` and re-resolves climate sources on area change.
- **Area handoff:** HA creates the `subentry_id` only after a subentry flow finishes, so the add flow cannot write the device area itself. It stores the chosen area as a one-time `area_id` key in the subentry data; device creation applies it to the new device and removes the key. Only device creation reads `area_id`; the edit flow carries a still-pending `area_id` over unchanged.
