# Climate sources (`climate.py`, `ClimateResolver`)

`climate.py` resolves readings for the engine. It is not the HA `climate` platform; that platform is never registered.

- **Indoor**: `sensor` entities in the plant's area with `device_class` `temperature` / `humidity`. An entity's area comes from the entity registry, falling back to its device's area. Several sensors → median. `unavailable` / `unknown` states are skipped.
- **Outdoor**: a `weather` entity (the plant's override, else the hub default). Current temperature and humidity from its attributes; precipitation from the forecast via the `weather.get_forecasts` action (`return_response`), aggregated per day before it reaches the engine.
- **Soil moisture sensor**, when the plant has one, is passed through and takes priority in the engine.
- Missing data is not an error: the engine falls back to the base interval with `climate_status = unknown`.
- Sources are re-resolved when a plant's device area changes (see `data-model.md`).
