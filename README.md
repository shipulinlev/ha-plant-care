# Plant Care for Home Assistant

A Home Assistant custom integration that helps you look after house and garden plants: it keeps a list of plants by room, remembers waterings and feedings, and tells you when the next one is due, taking into account the temperature and humidity in the room or the weather outside.

> **Status:** early development, pre-v0.1.0. Progress is tracked in [PLAN.md](PLAN.md).

> [!WARNING]
> **AI-assisted project ("vibe coded").** This integration is designed and written largely by an AI coding assistant ([Claude Code](https://claude.com/claude-code)), with a human steering, reviewing and testing. Treat it as experimental: review the code before relying on it, and please report anything that looks wrong.

## Features

- **Plants in the standard HA UI.** Add, edit and delete plants under *Settings → Devices & services → Plant Care*. Each plant becomes its own device.
- **Rooms.** A plant is assigned to an existing HA area. To move a plant, change the device's area or call the `plant_care.move` action.
- **Smart care schedule.**
  - Species norms (temperature, air and soil humidity) come from [OpenPlantbook](https://open.plantbook.io).
  - The watering interval is learned from your watering history and adjusted for climate: water more often when it's hot and dry, less often when it's cool.
  - Indoor plants use temperature and humidity sensors in the same area.
  - Garden and balcony plants use a weather entity (`weather.*`); rain counts as watering.
  - If a plant has a soil moisture sensor, its readings take priority.
  - Feeding is scheduled from a configured interval, adjusted for the season.

## Installation

### HACS (recommended)
1. HACS → Integrations → ⋮ → Custom repositories → add this repository's URL, category *Integration*.
2. Install **Plant Care** and restart Home Assistant.

### Manual
Copy `custom_components/plant_care` to `<config>/custom_components/` and restart Home Assistant.

**Requirements:** Home Assistant 2026.7 or newer (the exact minimum version will be pinned before release).

## Configuration

1. Get a `client_id` and `client_secret` at [open.plantbook.io](https://open.plantbook.io) (API section).
2. *Settings → Devices & services → Add integration → Plant Care*, enter the credentials and optionally pick a weather entity for outdoor plants.
3. On the integration card click **Add plant**: name, species (OpenPlantbook search), indoor or outdoor, area, optional soil moisture sensor, initial watering interval and feeding interval.

## Plant entities

| Entity | Description |
|---|---|
| `sensor.<plant>_next_watering` | when the next watering is due |
| `sensor.<plant>_next_feeding` | when the next feeding is due |
| `sensor.<plant>_watering_status` / `_feeding_status` | `ok`, `soon`, `due`, `overdue` |
| `sensor.<plant>_last_watered` / `_last_fed` | last care event |
| `binary_sensor.<plant>_needs_water` / `_needs_feeding` | whether watering or feeding is due |
| `button.<plant>_water` / `_feed` | log "watered" or "fed" now |

## Actions

| Action | Description |
|---|---|
| `plant_care.water` | log a watering (optional `when` to backdate) |
| `plant_care.feed` | log a feeding |
| `plant_care.move` | move a plant to another area |
| `plant_care.refresh_species` | refresh species data from OpenPlantbook |

## Example automation

```yaml
alias: Watering reminder
triggers:
  - trigger: state
    entity_id: binary_sensor.monstera_needs_water
    to: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: "Time to water the monstera 🌿"
```

## Development

Architecture, coding rules and commands are in [CLAUDE.md](CLAUDE.md); the roadmap and progress are in [PLAN.md](PLAN.md).

Development happens in the dev container (VS Code → *Reopen in Container*), because Home Assistant does not run natively on Windows.

```bash
scripts/test      # linters + tests
scripts/develop   # local HA with the integration at http://localhost:8123
```

## License

Not chosen yet.
