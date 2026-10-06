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

**Requirements:** Home Assistant 2026.8 or newer.

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
| `binary_sensor.<plant>_needs_water` / `_needs_feeding` | `on` while watering or feeding is due or overdue |
| `button.<plant>_water` / `_feed` | log "watered" or "fed" now |

## Actions

Each action takes the plant device (`device_id`).

| Action | Description |
|---|---|
| `plant_care.water` | log a watering (optional `when` to backdate) |
| `plant_care.feed` | log a feeding (optional `when` to backdate) |
| `plant_care.move` | move a plant to another area |
| `plant_care.refresh_species` | refresh species data from OpenPlantbook |

## Automation examples

Create these under *Settings → Automations & scenes → Create automation → ⋮ → Edit in YAML*. Entity IDs come from the plant's name (a plant named *Monstera* has `binary_sensor.monstera_needs_water`); adjust them and the `notify` action to your setup.

`needs_water` and `needs_feeding` turn `on` when the care is due or overdue and stay `unknown` until the first watering or feeding is logged.

### Notify when any plant needs water

One automation for several plants. `mode: parallel` sends one message per plant even when two plants become due at the same moment.

```yaml
alias: Plants need water
mode: parallel
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.monstera_needs_water
      - binary_sensor.ficus_needs_water
    to: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: "🌿 {{ trigger.to_state.name }}"
```

### Morning summary

First create a group helper: *Settings → Devices & services → Helpers → Create helper → Group → Binary sensor group*, named *Plants need water*, with all `*_needs_water` sensors as members. The group is `on` while at least one plant needs water.

```yaml
alias: Morning watering summary
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.plants_need_water
    state: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: >-
        Water today:
        {{ expand('binary_sensor.plants_need_water')
           | selectattr('state', 'eq', 'on')
           | map(attribute='name') | join(', ') }}
```

### Log the watering from the notification

An actionable notification (Companion app): tapping *Watered* presses the plant's `water` button, which logs a watering now.

```yaml
alias: Monstera watering reminder
triggers:
  - trigger: state
    entity_id: binary_sensor.monstera_needs_water
    to: "on"
actions:
  - action: notify.mobile_app_phone
    data:
      message: "Time to water the monstera 🌿"
      data:
        actions:
          - action: MONSTERA_WATERED
            title: Watered
  - wait_for_trigger:
      - trigger: event
        event_type: mobile_app_notification_action
        event_data:
          action: MONSTERA_WATERED
    timeout: "12:00:00"
    continue_on_timeout: false
  - action: button.press
    target:
      entity_id: button.monstera_water
```

### Log the watering with an NFC tag

Stick a tag on the pot and scan it with the Companion app after watering.

```yaml
alias: Monstera watered (NFC tag)
triggers:
  - trigger: tag
    tag_id: monstera-pot
actions:
  - action: button.press
    target:
      entity_id: button.monstera_water
```

To log a watering that happened earlier, call `plant_care.water` with the plant device and `when` (for example from *Tools → Actions*).

## Development

Contributor rules are in [CLAUDE.md](CLAUDE.md), architecture in [docs/architecture/](docs/architecture/), the dev environment in [docs/development.md](docs/development.md); the roadmap and progress are in [PLAN.md](PLAN.md).

Development happens in the dev container (VS Code → *Reopen in Container*), because Home Assistant does not run natively on Windows.

```bash
scripts/test      # linters + tests
scripts/develop   # local HA with the integration at http://localhost:8123
```

## License

[MIT](LICENSE).
