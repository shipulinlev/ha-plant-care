# Coordinator (`coordinator.py`)

- One `DataUpdateCoordinator` per hub entry; it recomputes the `CarePlan` of every plant.
- Runtime state lives in `entry.runtime_data` (`type PlantCareConfigEntry = ConfigEntry[PlantCareRuntimeData]`).
- Triggers: a 30 min timer, state changes of climate entities (`async_track_state_change_event`; subscriptions rebuilt on area change), new CareLog events, subentry changes, device area changes.
- Network calls (OpenPlantbook, forecasts) are served from caches with their own TTL, never made on every tick.
- Unloading the entry removes every listener and subscription.
