# CLAUDE.md

Руководство для Claude Code по работе в этом репозитории. Пользовательская документация лежит в `README.md`, план и прогресс разработки в `PLAN.md`.

## Обязательное правило: PLAN.md

`PLAN.md` — единственный источник правды о статусе разработки. **Обновляй его по ходу работы, а не в конце:**

- начал задачу — пометь её `[~]` (в работе);
- закончил и проверил (тесты зелёные) — пометь `[x]` и допиши короткую заметку, если по ходу что-то решили или поменяли;
- появилась новая задача, баг или техдолг — добавь пункт в нужную фазу или в раздел «Бэклог»;
- архитектурное решение изменилось — обнови раздел «Журнал решений» в `PLAN.md` и соответствующий раздел этого файла;
- перед началом работы прочитай `PLAN.md`, чтобы понять текущую фазу и следующий шаг.

Задачу нельзя отметить `[x]`, если по ней не пройдены `pytest`, `ruff` и `mypy`.

## Что это за проект

**Plant Care** — custom integration для Home Assistant (`custom_components/plant_care`, распространяется через HACS). Это **не** Supervisor add-on и **не** встроенная интеграция `plant`.

Функции:
1. CRUD растений через стандартный UI HA («Устройства и службы»).
2. Привязка растения к комнате (area HA) и перемещение между комнатами.
3. Оценка и планирование полива и подкормки с учётом климата: для комнатных растений по датчикам комнаты, для сада и балкона по погоде; плюс история ухода, которую ведёт пользователь, и нормы вида из OpenPlantbook.

Вне скоупа (пока): собственный фронтенд (панель, Lovelace-карточка), управление поливом (клапаны, насосы), распознавание растений по фото.

## Архитектура

### 1. Модель данных в HA
- Домен: `plant_care`.
- **Config entry (hub)**, одна на инсталляцию: учётные данные OpenPlantbook (`client_id`, `client_secret`) и `weather`-сущность по умолчанию для уличных растений.
- **Растение = config subentry** типа `plant`. Добавление идёт через шаг `user` subentry-flow, редактирование через `reconfigure`, удаление штатное.
- **Каждому растению соответствует один device**, привязанный к subentry (`config_subentry_id`). Все сущности растения относятся к этому device.
- Данные subentry: `name`, `species_pid` (OpenPlantbook PID, опционально), `location_type` (`indoor` | `outdoor`), `soil_moisture_entity` (опционально), `initial_watering_interval_days`, `feeding_interval_days`, overrides диапазонов вида.

### 2. Комната = area у device
- Area хранится **только** в device registry и **не дублируется** в данных subentry.
- Перемещение растения: пользователь меняет area у device в штатном UI или вызывает сервис `plant_care.move`, который делает то же самое.
- Интеграция слушает `EVENT_DEVICE_REGISTRY_UPDATED` и при смене area заново определяет источники климата.
- При создании растения area выбирается в subentry-flow (`AreaSelector`) и сразу записывается в device.

### 3. Источники климата (`climate.py`, `ClimateResolver`)
- **indoor**: сущности `sensor` в area растения с `device_class` `temperature` / `humidity`. Area сущности определяется по entity registry, а если её нет, то по area её device. Если датчиков несколько, берётся медиана. `unavailable`/`unknown` игнорируются.
- **outdoor**: `weather`-сущность (из hub, может переопределяться в растении). Текущие температура и влажность берутся из атрибутов, осадки из прогноза через сервис `weather.get_forecasts` (с `return_response`).
- **Датчик влажности почвы** растения, если задан, приоритетнее эвристики.
- Нет данных — это не ошибка: движок откатывается к базовому интервалу, `climate_status = unknown`.

### 4. Профиль вида (`openplantbook.py`, `SpeciesProfile`)
- Асинхронный клиент на `aiohttp` (сессия через `async_get_clientsession`). Авторизация: OAuth2 Client Credentials, токен кешируется до истечения.
- Эндпоинты: search (подбор вида в subentry-flow) и detail (профиль).
- Поля detail: `min/max_temp`, `min/max_env_humid`, `min/max_soil_moist`, `min/max_light_lux`, `min/max_soil_ec`.
- **Важно: OpenPlantbook НЕ отдаёт интервалы полива и подкормки.** Это только допустимые диапазоны среды. Интервалы берутся из истории пользователя и его настроек.
- Профили кешируются в `Store`, чтобы интеграция работала офлайн и не упиралась в лимиты API. Overrides из subentry перекрывают значения API.

### 5. История ухода (`storage.py`, `CareLog`)
- События `watered` / `fed` с timestamp (UTC) и `plant_id` (= `subentry_id`) хранятся в `homeassistant.helpers.storage.Store` с версионированием и миграциями.
- Не храним историю в state сущностей или в recorder.
- Запись события: `button`-сущности «Полил» / «Подкормил» и сервисы `plant_care.water` / `plant_care.feed` (поле `when` позволяет отметить задним числом).
- При удалении subentry его история удаляется.

### 6. Движок планирования (`core/engine.py`, `CareEngine`)
Чистый Python, **без импорта `homeassistant`**, детерминированный (текущее время передаётся параметром).
- **Базовый интервал полива** = медиана последних N (по умолчанию 5) интервалов из CareLog. Пока интервалов меньше 2, используется `initial_watering_interval_days`.
- **Климатический множитель**: насколько температура и влажность выходят за диапазон вида. Жарче или суше диапазона → интервал короче, прохладнее или влажнее → длиннее. Множитель ограничен (по умолчанию 0.5–1.5).
- **Outdoor**: осадки за прошедший период и по прогнозу сдвигают срок полива (дождь ≥ порога считается поливом).
- **Датчик почвы**: если влажность ниже `min_soil_moist`, полив нужен сейчас; если выше `max_soil_moist`, полив не нужен.
- **Подкормка**: интервал задаёт пользователь, плюс сезонный коэффициент (зимой пауза или удлинение; полушарие определяется по широте HA).
- Выход (`CarePlan`): `next_watering`, `next_feeding`, `watering_status` / `feeding_status` (`ok` | `soon` | `due` | `overdue`), `climate_status`, `explanation` (краткое объяснение расчёта для атрибутов).

### 7. Координатор (`coordinator.py`)
- Один `DataUpdateCoordinator` на config entry, пересчитывает `CarePlan` для всех растений.
- Триггеры: таймер (30 мин), изменение state климатических сущностей (`async_track_state_change_event`, подписки пересобираются при смене area), новая запись в CareLog, изменение subentry, смена area у device.
- Сетевые вызовы (OpenPlantbook, прогноз) идут не на каждый тик, а по своему TTL из кеша.

### 8. Сущности растения
| Платформа | Сущность | Назначение |
|---|---|---|
| `sensor` | `next_watering`, `next_feeding` | `device_class: timestamp` |
| `sensor` | `watering_status`, `feeding_status` | `device_class: enum` |
| `sensor` | `last_watered`, `last_fed` | `device_class: timestamp` |
| `binary_sensor` | `needs_water`, `needs_feeding` | для автоматизаций и уведомлений |
| `button` | `water`, `feed` | отметить уход «сейчас» |

Все сущности: `has_entity_name = True`, `translation_key`, `unique_id = f"{subentry_id}_{key}"`.

### 9. Сервисы
`plant_care.water`, `plant_care.feed` (target: device растения, опц. `when`), `plant_care.move` (device + `area_id`), `plant_care.refresh_species` (сбросить кеш профиля). Сервисы регистрируются в `async_setup`, а не в `async_setup_entry`.

## Структура репозитория

```
custom_components/plant_care/
  __init__.py          # async_setup (сервисы), async_setup_entry/unload, подписка на device registry
  manifest.json
  const.py
  config_flow.py       # PlantCareConfigFlow (hub) + PlantSubentryFlow (user / reconfigure)
  coordinator.py
  entity.py            # PlantCareEntity: device_info, unique_id
  sensor.py
  binary_sensor.py
  button.py
  services.py          # обработчики сервисов
  services.yaml
  climate.py           # ClimateResolver (имя не совпадает с платформой climate: платформу не регистрируем)
  openplantbook.py     # API-клиент
  storage.py           # CareLog + кеш профилей
  strings.json
  translations/en.json
  translations/ru.json
  core/                # чистая логика, не импортирует homeassistant
    models.py          # dataclasses: PlantConfig, SpeciesProfile, CareEvent, ClimateReading, CarePlan
    engine.py          # CareEngine
tests/
  core/                # unit-тесты движка, без HA
  ...                  # тесты интеграции на pytest-homeassistant-custom-component
hacs.json
pyproject.toml         # ruff, mypy, pytest
```

## Правила написания кода

### Общие
- Python 3.14 (минимум для HA 2026.9: 3.14.2); полная типизация. `from __future__ import annotations` не нужен (в 3.14 аннотации ленивые, PEP 649).
- `mypy` в strict-режиме для всего кода (настроено в `pyproject.toml`).
- `core/` и `tests/core/` не могут импортировать `homeassistant`: это проверяет ruff (правило `TID251`).
- Версия HA для разработки и тестов задаётся пином `pytest-homeassistant-custom-component` в `pyproject.toml`. Обновляем его осознанно и отмечаем это в `PLAN.md`.
- Код, идентификаторы, комментарии и docstrings на английском. Документация (`README.md`, `CLAUDE.md`, `PLAN.md`) на русском. Строки UI через переводы en + ru.
- Маленькие модули с одной ответственностью. Если файл перевалил за ~300 строк, это повод разделить.
- Никаких «на будущее» абстракций (YAGNI). Точки расширения описываем в `PLAN.md`, а не в коде.

### Home Assistant
- Только async. Никакого блокирующего I/O в event loop: HTTP через `aiohttp` из `async_get_clientsession`, файлы через `Store`.
- Типизированная config entry: `type PlantCareConfigEntry = ConfigEntry[PlantCareRuntimeData]`, данные рантайма в `entry.runtime_data`, а не в `hass.data`.
- Внутри интеграции растение идентифицируется по `subentry_id`, а не по имени и не по `entity_id`. В примерах автоматизаций (README) используем `entity_id` сущностей растения, а не `device_id`: так рекомендует HA best practices.
- Все тексты UI (flow, ошибки, сущности, сервисы) лежат в `strings.json` и `translations/*.json`. Хардкод строк в коде запрещён.
- Ошибки сети OpenPlantbook: в flow выводим понятную ошибку формы, в рантайме логируем и работаем по кешу. Не бросаем `ConfigEntryNotReady` из-за недоступного OpenPlantbook, если кеш есть.
- Ошибки сервисов: `ServiceValidationError` с `translation_key`.
- Учёт времени: всё в UTC (`dt_util.utcnow()`), локальное время только для отображения.
- Логирование через `_LOGGER = logging.getLogger(__name__)`, секреты не логируем.

### Актуальные API HA (проверено, 2026)
- Subentries: `ConfigFlow.async_get_supported_subentry_types()` → `{"plant": PlantSubentryFlow}`; в `reconfigure` использовать `self._get_entry()` и `self._get_reconfigure_subentry()`.
- С HA 2026.07 у device ровно одна config entry: читать `device.config_entry_id` / `device.config_subentry_id`; `device.config_entries_subentries` **устарел**. Для переноса используется `async_update_device(new_config_entry_id=..., new_config_subentry_id=...)`.
- При сомнениях в API HA сверяться с актуальной документацией (context7: `/home-assistant/developers.home-assistant`), а не с памятью.

### Тестирование (TDD)
- Сначала тест, потом реализация. Особенно это касается `core/engine.py`: каждый коэффициент и граничный случай покрывается тестом.
- `tests/core/` не использует HA и работает быстро.
- Тесты интеграции: `pytest-homeassistant-custom-component`, фикстура `hass`, `MockConfigEntry` с subentries, `aioclient_mock` для OpenPlantbook, без реальной сети.
- Обязательно покрыть: config flow и subentry flow (включая ошибки), смену area → пересчёт источников климата, сервисы, выгрузку entry без утечек подписок.

## Команды разработки

Основная среда — **dev-контейнер** (`.devcontainer/`: Python 3.14, venv в `/home/vscode/.venv`, порт 8123). HA не работает на Windows нативно (`homeassistant/runner.py` импортирует `fcntl`), поэтому тесты интеграции и живой HA запускаются только в контейнере.

```bash
# Поднять контейнер (VS Code: «Reopen in Container»; из терминала:)
npx -y @devcontainers/cli up --workspace-folder .

# Внутри контейнера
scripts/setup      # venv + dev-зависимости (выполняется автоматически при создании)
scripts/test       # ruff check, ruff format --check, mypy, pytest; аргументы передаются в pytest
scripts/develop    # живой HA на http://localhost:8123, интеграция грузится прямо из custom_components/
```

Выполнить команду в контейнере с хоста Windows (Git Bash; `MSYS_NO_PATHCONV=1` обязателен, иначе пути `/workspaces/...` искажаются):

```bash
MSYS_NO_PATHCONV=1 docker exec -u vscode -w /workspaces/ha-plants <container_id> scripts/test
# container_id: docker ps --filter label=devcontainer.local_folder --format '{{.ID}}'
```

На Windows без контейнера работают ruff, mypy и быстрые тесты движка:

```bash
py -3.14 -m venv .venv && source .venv/Scripts/activate && pip install --group dev
pytest tests/core -q -p no:homeassistant
ruff check . && ruff format --check . && mypy .
```

**Живой HA (`scripts/develop`):** конфиг берётся из `config/` (в git не попадает). При первом запуске туда копируется `.devcontainer/configuration.yaml`. В нём нет `default_config`: его зависимость `go2rtc` требует бинарника, которого в контейнере нет. Если нужна ещё какая-то интеграция HA, добавляй её в шаблон явно. Для чтения состояния и логов пользовательского (не dev) HA можно использовать HA MCP (`ha_get_logs`, `ha_get_state`). **Изменения в пользовательском HA делать только с его явного согласия.**

## Git
- Коммиты небольшие, по одной задаче из `PLAN.md`, сообщение в стиле Conventional Commits (`feat(engine): ...`).
- Коммитить только по просьбе пользователя.
