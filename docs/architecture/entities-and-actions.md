# Plant entities and actions

Modules: `entity.py` (`PlantCareEntity`: `device_info`, `unique_id`), `sensor.py`, `binary_sensor.py`, `button.py`, `services.py`, `services.yaml`, `diagnostics.py`.

## Entities
| Platform | Entity | Purpose |
|---|---|---|
| `sensor` | `next_watering`, `next_feeding` | `device_class: timestamp` |
| `sensor` | `watering_status`, `feeding_status` | `device_class: enum` |
| `sensor` | `last_watered`, `last_fed` | `device_class: timestamp` |
| `binary_sensor` | `needs_water`, `needs_feeding` | for automations and notifications |
| `button` | `water`, `feed` | log care "now" |

All entities derive from `PlantCareEntity`: `has_entity_name = True`, `translation_key` = key, `unique_id = f"{subentry_id}_{key}"`, attached to the plant's device, unavailable while the coordinator has no plan for the plant. Platforms add each plant's entities with `async_add_entities(..., config_subentry_id=subentry_id)`, so HA removes them with the plant.

- `watering_status` attributes: `climate_status` (`ok` | `out_of_range` | `unknown`) and `explanation` (excluded from the recorder via `_unrecorded_attributes`).
- `needs_water`, `needs_feeding`: on while the watering/feeding status is `due` or `overdue`, off for `ok` and `soon`, unknown while nothing is scheduled (no care logged yet).
- Icons live in `icons.json` (per translation key, with state icons for the statuses).

## Actions
Every action takes one required `device_id` (a device selector filtered to `plant_care`), the way core integrations target a device; there is no `target`, so one call acts on one plant.
- `plant_care.water`, `plant_care.feed`: optional `when` for backdating; a time without a zone is local time, a future time is rejected. Same write path as the buttons (`coordinator.async_log_care`).
- `plant_care.move`: device + `area_id`; same effect as changing the device area in the UI (the coordinator follows the registry event).
- `plant_care.refresh_species`: drop the cached profile and the fetch-retry pause, then refresh, so the profile is fetched at once.
- Registered in `async_setup`, not in `async_setup_entry` (`services.py`).
- Errors: `ServiceValidationError` with a `translation_key` from the `exceptions` section of `strings.json`: `plant_not_found`, `hub_not_loaded`, `when_in_future`, `area_not_found`, `no_species`.

## Diagnostics
`diagnostics.py` gives config entry diagnostics: the hub data with `client_id` and `client_secret` redacted, and per plant (by `subentry_id`) its title, area, subentry data, care log and current plan, plus the cached profile of every species in use.

## README examples
Automation examples use the plant entities' `entity_id`s, never `device_id` (HA best practice). To log care now, examples press the plant's `button` (`button.press`) rather than calling `plant_care.water`, which needs a `device_id`. `tests/test_readme.py` loads every YAML block of the README's "Automation examples" section as an automation, so keep only automations there.
