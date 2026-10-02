# Plant entities and actions

Modules: `entity.py` (`PlantCareEntity`: `device_info`, `unique_id`), `sensor.py`, `binary_sensor.py`, `button.py`, `services.py`, `services.yaml`.

## Entities
| Platform | Entity | Purpose |
|---|---|---|
| `sensor` | `next_watering`, `next_feeding` | `device_class: timestamp` |
| `sensor` | `watering_status`, `feeding_status` | `device_class: enum` |
| `sensor` | `last_watered`, `last_fed` | `device_class: timestamp` |
| `binary_sensor` | `needs_water`, `needs_feeding` | for automations and notifications |
| `button` | `water`, `feed` | log care "now" |

All entities: `has_entity_name = True`, `translation_key`, `unique_id = f"{subentry_id}_{key}"`, attached to the plant's device.

## Actions
- `plant_care.water`, `plant_care.feed`: target the plant device, optional `when` for backdating.
- `plant_care.move`: device + `area_id`; same effect as changing the device area in the UI.
- `plant_care.refresh_species`: drop the cached profile so it is fetched again.
- Registered in `async_setup`, not in `async_setup_entry`.
- Errors: `ServiceValidationError` with a `translation_key`.

## README examples
Automation examples use the plant entities' `entity_id`s, never `device_id` (HA best practice).
