# Care history (`storage.py`, `CareLog`)

- `watered` / `fed` events with a UTC timestamp and `plant_id` (= `subentry_id`), in a `Store` (`plant_care.care_log`, version 1): `{"plants": {plant_id: [{kind, at}]}}`. Times are normalized to UTC; events are kept oldest first; each add is saved immediately.
- History lives only in this store, not in entity state or the recorder.
- Events come from the `water` / `feed` buttons and the `plant_care.water` / `plant_care.feed` actions (`when` allows backdating).
- Deleting a plant deletes its history (`async_remove_plant`).
- Schema changes bump the store version and add a migration; there is no migration code before version 2.
