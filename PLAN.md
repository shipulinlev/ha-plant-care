# PLAN.md — план и прогресс разработки

Статусы: `[ ]` не начато · `[~]` в работе · `[x]` готово (тесты, ruff и mypy зелёные) · `[-]` отменено.
Правила обновления описаны в `CLAUDE.md` (раздел «Обязательное правило: PLAN.md»).

**Текущая фаза:** 0. Каркас проекта
**Следующий шаг:** скелет `custom_components/plant_care/` (`manifest.json`, `const.py`, `__init__.py`, `hacs.json`)

---

## Фаза 0. Каркас проекта
- [x] Архитектурные концепты, `CLAUDE.md`, `README.md`, `PLAN.md`
- [x] `git init` (ветка `main`), `.gitignore`, `.gitattributes` (LF)
- [x] `pyproject.toml`: dev-зависимости через `[dependency-groups]`, настройки pytest, ruff и mypy (strict)
  - Среда разработки: Python 3.14.3, HA 2026.9.4 (через `pytest-homeassistant-custom-component==0.13.367`), ruff 0.16.9, mypy 2.3.1, pytest 9.0.3.
  - Запрет импорта `homeassistant` в `core/` и `tests/core/` задан правилом ruff `TID251` и проверен на пробных файлах.
- [x] Dev-контейнер для тестов интеграции и живого HA (плагин HA падает на Windows из-за `fcntl`)
  - `.devcontainer/` (образ `mcr.microsoft.com/devcontainers/python:3.14` + ffmpeg, libturbojpeg, libpcap), скрипты `scripts/setup`, `scripts/test`, `scripts/develop`.
  - Проверено: smoke-тест с фикстурой `hass` проходит, `scripts/develop` поднимает HA 2026.9.4 без ошибок, frontend отвечает 200.
  - Dev-конфиг HA без `default_config`: `go2rtc` требует бинарник.
- [ ] Скелет `custom_components/plant_care/`: `manifest.json`, `const.py`, пустой `__init__.py`, `hacs.json`
- [ ] Определить минимальную версию HA (subentries + одиночная config entry у device, ≥ 2026.07) и зафиксировать в `manifest.json` / `hacs.json`
- [ ] CI (GitHub Actions): pytest, ruff, mypy, hassfest, HACS validation

## Фаза 1. Ядро: модели и движок (без HA, TDD)
- [ ] `core/models.py`: `PlantConfig`, `SpeciesProfile`, `CareEvent`, `ClimateReading`, `CarePlan`, enum статусов
- [ ] Базовый интервал полива: медиана последних N интервалов, fallback на `initial_watering_interval_days`
- [ ] Климатический множитель по температуре и влажности относительно диапазона вида, с ограничением 0.5–1.5
- [ ] Учёт осадков для outdoor
- [ ] Приоритет датчика влажности почвы
- [ ] Подкормка: интервал + сезонный коэффициент (полушарие по широте)
- [ ] Расчёт статусов `ok/soon/due/overdue` и `explanation`
- [ ] Граничные случаи: нет истории, нет климата, нет профиля вида, события в будущем, дубли событий

## Фаза 2. Хранилище и внешние данные
- [ ] `storage.py`: `CareLog` на `Store` (версия, миграции, удаление истории растения)
- [ ] `storage.py`: кеш профилей OpenPlantbook с TTL
- [ ] `openplantbook.py`: OAuth2 client credentials, кеш токена, search, detail, обработка ошибок и лимитов
- [ ] Тесты клиента на `aioclient_mock`

## Фаза 3. Интеграция: flows и устройства
- [ ] Hub `ConfigFlow`: учётные данные OpenPlantbook (с проверкой), weather по умолчанию; single instance
- [ ] Options/reconfigure hub
- [ ] `PlantSubentryFlow.user`: имя, поиск вида, `location_type`, area, датчик почвы, интервалы
- [ ] `PlantSubentryFlow.reconfigure`
- [ ] Создание device на subentry с area; удаление subentry → удаление device и истории
- [ ] Переводы en/ru для всех flow

## Фаза 4. Климат и координатор
- [ ] `ClimateResolver`: датчики area (area сущности или её device), медиана, игнор unavailable
- [ ] `ClimateResolver`: weather + `weather.get_forecasts` для outdoor
- [ ] Реакция на смену area у device (`EVENT_DEVICE_REGISTRY_UPDATED`) → пересборка подписок
- [ ] `DataUpdateCoordinator`: таймер + события state + события CareLog
- [ ] Корректная выгрузка entry (отписка от всех listener-ов)

## Фаза 5. Сущности и сервисы
- [ ] `entity.py`: базовый класс с `device_info` и `unique_id`
- [ ] `sensor`: next/last watering/feeding, статусы
- [ ] `binary_sensor`: needs_water, needs_feeding
- [ ] `button`: water, feed
- [ ] Сервисы `water`, `feed`, `move`, `refresh_species` + `services.yaml` + переводы
- [ ] Диагностика (`diagnostics.py`) без секретов

## Фаза 6. Проверка на живом HA и релиз
- [ ] Ручной прогон на тестовом HA: добавить 2 indoor + 1 outdoor растение, переместить, отметить полив
- [ ] Примеры автоматизаций (уведомление «пора полить») в README
- [ ] Калибровка коэффициентов по реальным данным
- [ ] Первый релиз v0.1.0 (HACS custom repository)

## Бэклог / идеи (после v0.1)
- Lovelace-карточка «Сад» через websocket API
- Сущность `calendar` с планом ухода
- Учёт освещённости (`min/max_light_lux`) и рекомендации по месту
- Пересадка, опрыскивание, другие типы ухода
- Импорт и экспорт растений

## Журнал решений
| Дата | Решение | Причина |
|---|---|---|
| 2026-09-29 | Custom integration, не add-on | Нативная работа с area, device, сущностями и сервисами; работает на любом типе установки HA |
| 2026-09-29 | Растение = config subentry + device | Штатный CRUD в UI без своего фронтенда; area и перемещение даёт device registry |
| 2026-09-29 | Area хранится только в device registry | Один источник правды; перемещение штатными средствами HA |
| 2026-09-29 | Нормы вида из OpenPlantbook, интервалы из истории пользователя | OpenPlantbook отдаёт только диапазоны среды, интервалов полива и подкормки там нет |
| 2026-09-29 | Indoor: датчики area; outdoor: weather + осадки | Требование пользователя (сад и балкон) |
| 2026-09-29 | Движок в `core/` без зависимостей от HA | Быстрые детерминированные unit-тесты, простая калибровка |
| 2026-09-29 | Домен `plant_care` | Нет конфликта со встроенной интеграцией `plant` |
| 2026-09-29 | Dev-контейнер как основная среда | HA не работает на Windows нативно; контейнер ближе всего к реальному рантайму HA |
| 2026-09-29 | Python 3.14, dev-зависимости через PEP 735 `[dependency-groups]` | HA 2026.9 требует Python ≥ 3.14.2; интеграция не ставится как пакет, `pyproject.toml` нужен только для инструментов |
