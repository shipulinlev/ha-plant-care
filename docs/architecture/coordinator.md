# Coordinator (`coordinator.py`)

`PlantCareCoordinator`: one `DataUpdateCoordinator` per hub entry; `data` maps plant (subentry) id → `CarePlan`. It lives in `entry.runtime_data.coordinator` (`PlantCareRuntimeData` / `PlantCareConfigEntry` in `runtime.py`, next to the care log).

## One update
For every plant (`plants.py` turns a subentry into engine inputs):
- `PlantConfig` from the subentry data.
- Climate: indoor → area sensors of the plant's device area; outdoor → the plant's or the hub's weather entity plus `RainTracker` rain. See `climate.md`.
- Species profile: `ProfileCache`, refetched from OpenPlantbook when stale. A failed fetch is logged, the cache (if any) is used, and the next attempt waits `PROFILE_RETRY_AFTER` (1 h). The plant's range overrides go on top (`with_overrides`).
- `CareEngine.plan(...)` with the CareLog events, `now` and HA's latitude.

## Triggers
- Timer: every 30 min.
- State changes of every source entity (area sensors, soil sensors, weather entities): debounced `async_request_refresh`. The subscription is rebuilt after each update when the source set changed.
- Registry changes, immediate `async_refresh`: a device's area changed (a plant or a sensor's device moved), or an entity was created, removed, or changed area, device, device class or enabled state.
- Logged care: `async_log_care(event)` stores the event and refreshes; buttons and actions use it.
- Plant added, edited or removed: the hub reloads (update listener, see `data-model.md`).

## Unload
The base class shuts the coordinator down with the entry; `async_shutdown` also closes the state subscription. Registry listeners are tied to `entry.async_on_unload`. Tests check that no subscription is left open.
