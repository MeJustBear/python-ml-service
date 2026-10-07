# База данных

В базе сервис хранит только историю: что вызывали, сколько это заняло и что происходило с
моделями. Сами модели в базе не живут — они описаны в реестре внутри процесса. Отсюда
главная особенность схемы: **таблицы связаны с моделями логически, по имени, без внешних
ключей**.

Стек: PostgreSQL, SQLAlchemy 2.0 в асинхронном режиме (`asyncpg`), миграции Alembic.
Тесты гоняются на SQLite через `aiosqlite`, поэтому типы колонок выбраны портируемые.

!!! note "База опциональна"
    Без `MLWRAP_DATABASE_URL` функция `build_database()` возвращает `None`, и сервис работает
    полностью — просто без истории и без агрегатов в `/api/v1/models/{name}/metrics`.
    `/health/ready` в этом режиме сообщает `database: disabled`, и это не считается ошибкой.

## Схема и отношения

```mermaid
erDiagram
    MODEL_REGISTRY {
        string name "ключ ModelSpec, в БД не хранится"
        string version "ModelSpec.version"
    }

    INFERENCE_LOG {
        uuid id PK "default uuid4 на стороне Python"
        string model_name "VARCHAR(128), индекс"
        string model_version "VARCHAR(64), NOT NULL, default ''"
        string status "VARCHAR(16), индекс: ok | error"
        float latency_ms "NOT NULL"
        int batch_size "NOT NULL, default 1"
        text error "NULL, 'код: сообщение'"
        string request_id "VARCHAR(64), NULL"
        string principal "VARCHAR(128), NULL"
        json payload "JSONB, NULL"
        json result "JSONB, NULL"
        timestamptz created_at "server_default now(), индекс"
    }

    MODEL_EVENT {
        uuid id PK "default uuid4 на стороне Python"
        string model_name "VARCHAR(128), индекс"
        string event "VARCHAR(32), индекс: load | unload | load_failed"
        float duration_ms "NULL"
        json details "JSONB, NULL"
        timestamptz created_at "server_default now(), индекс"
    }

    MODEL_REGISTRY ||..o{ INFERENCE_LOG : "model_name — связь по значению, без FK"
    MODEL_REGISTRY ||..o{ MODEL_EVENT : "model_name — связь по значению, без FK"
```

Пунктир на диаграмме не случаен. Между `inference_log` и `model_event` нет ни внешних ключей,
ни отношений — это два независимых журнала с общей точкой соприкосновения, колонкой
`model_name`. Решение осознанное:

- **Справочника моделей в БД нет.** Набор моделей задаётся кодом и переменными окружения и
  может меняться от запуска к запуску. Таблица-справочник пришлось бы синхронизировать с
  реестром при каждом старте, а при расхождении — решать, что делать со старыми записями.
- **Журнал переживает модель.** Модель можно переименовать, выгрузить, убрать из плагинов —
  история её вызовов должна остаться читаемой. Внешний ключ с `ON DELETE` такого не позволит.
- **Запись не должна падать.** Журнал пишется в фоне и по контракту никогда не роняет
  инференс. Любое ограничение целостности — это ещё один способ упасть на вставке.

Цена решения: за консистентность `model_name` никто не отвечает. Опечатка в имени модели даст
отдельную группу записей, и заметите вы это только при просмотре агрегатов.

## inference_log — журнал инференсов

Одна строка на один HTTP-запрос инференса, а не на один элемент пакета.

| Колонка | Тип | Содержимое |
|---|---|---|
| `id` | `UUID` PK | генерируется в Python (`default=uuid.uuid4`), серверного default нет |
| `model_name` | `VARCHAR(128)` | имя модели в реестре |
| `model_version` | `VARCHAR(64)` | `ModelSpec.version` на момент вызова |
| `status` | `VARCHAR(16)` | `ok` или `error` |
| `latency_ms` | `FLOAT` | для пакета — длительность **всего** пакета |
| `batch_size` | `INTEGER` | `1` для одиночного вызова, длина списка для пакетного |
| `error` | `TEXT` | только при `status='error'`, формат `код: сообщение` (например `prediction_timeout: Инференс модели 'iris' не уложился в 60.0 с`) |
| `request_id` | `VARCHAR(64)` | то же значение, что в заголовке `X-Request-Id` и в логах |
| `principal` | `VARCHAR(128)` | `Principal.subject`: логин, `sub` из токена или `anonymous` |
| `payload` | `JSONB` | тело запроса — только при `MLWRAP_PERSIST_PAYLOADS=true` |
| `result` | `JSONB` | ответ модели — там же |
| `created_at` | `TIMESTAMPTZ` | `server_default now()` — время базы, не приложения |

Индексы: `model_name`, `status`, `created_at` по отдельности плюс составной
`ix_inference_log_model_created (model_name, created_at)`. Последний закрывает основной шаблон
запроса — «последние N вызовов конкретной модели», именно так работает расчёт перцентилей.

### Что попадает в payload и result

Перед записью значения проходят через `to_jsonable()` (pydantic-модели, dataclass'ы,
numpy-массивы, `UUID`, `Decimal` разворачиваются в JSON-типы), а затем через `truncate()`.
Если `repr` значения длиннее `MLWRAP_PAYLOAD_MAX_CHARS` (по умолчанию 4000), в базу ляжет
заглушка:

```json
{ "truncated": true, "preview": "…первые 4000 символов…" }
```

По умолчанию `MLWRAP_PERSIST_PAYLOADS=false`, и обе колонки остаются `NULL` — тела запросов
легко могут содержать персональные данные, так что включать это нужно осознанно.

## model_event — события моделей

Пишется из `event_hook`, который `create_app()` подшивает к `ModelRuntime`, если база есть.

| Колонка | Тип | Содержимое |
|---|---|---|
| `id` | `UUID` PK | `default=uuid.uuid4` |
| `model_name` | `VARCHAR(128)` | имя модели |
| `event` | `VARCHAR(32)` | `load`, `unload` или `load_failed` |
| `duration_ms` | `FLOAT` | длительность загрузки; для `unload` — `NULL` |
| `details` | `JSONB` | `{"version": "1.0.0"}` для `load`, `{"error": "..."}` для `load_failed`, `NULL` для `unload` |
| `created_at` | `TIMESTAMPTZ` | `server_default now()` |

Индексы: `model_name`, `event`, `created_at`.

Таблица отвечает на вопросы вроде «когда модель последний раз перезагружали», «сколько раз
за сутки загрузка падала и с какой ошибкой», «не растёт ли время загрузки от релиза к релизу».
В отличие от `inference_log`, запись событий **не** отключается через
`MLWRAP_PERSIST_INFERENCES` — достаточно самого наличия базы.

## Кто и когда пишет

```mermaid
flowchart TD
    ok["predict / predict batch — успех"] -->|"BackgroundTasks, после ответа клиенту"| il[("inference_log<br/>status = ok")]
    err["predict / predict batch — MLWrapError"] -->|"синхронно: до фоновых задач дело не дойдёт"| ile[("inference_log<br/>status = error")]
    lo["ModelRuntime.load — успех"] -->|event_hook| me[("model_event<br/>event = load")]
    lf["ModelRuntime.load — исключение"] -->|event_hook| mef[("model_event<br/>event = load_failed")]
    un["ModelRuntime.unload"] -->|event_hook| meu[("model_event<br/>event = unload")]

    gate{"database is not None<br/>и MLWRAP_PERSIST_INFERENCES"} -.->|проверяется перед вставкой| il
    gate -.-> ile
```

Две детали, которые объясняют странности в коде:

1. **Успех пишется фоном, ошибка — сразу.** При успехе запись ставится в `BackgroundTasks`,
   чтобы задержка инференса не включала обращение к базе. При ошибке ответ формирует
   обработчик исключений FastAPI, и до фоновых задач дело не доходит, — поэтому
   `run_predict()` пишет строку синхронно, прямо в блоке `except`, и только потом
   перебрасывает исключение.
2. **Ошибка записи не ломает инференс.** Вся вставка обёрнута в `try/except Exception` с
   `logger.warning("db.inference_record_failed")`. Упавшая база означает потерю истории,
   но не отказ сервиса.

## Агрегаты для API

`GET /api/v1/models/{name}/metrics` возвращает блок `history`, который считает
`repository.inference_stats()` — двумя запросами.

```mermaid
flowchart LR
    q1["SELECT count(id),<br/>sum(CASE status='error'),<br/>min(created_at), max(created_at)<br/>WHERE model_name = :name"] --> out
    q2["SELECT latency_ms<br/>WHERE model_name = :name AND status = 'ok'<br/>ORDER BY created_at DESC<br/>LIMIT :window"] --> py["перцентили считаются в Python:<br/>statistics.fmean + выборка по индексу"] --> out
    out["total, errors, error_rate,<br/>first_at, last_at, window,<br/>latency_ms: avg / min / max / p50 / p95 / p99"]
```

```json
{
  "total": 1284,
  "errors": 7,
  "error_rate": 0.0055,
  "first_at": "2026-10-01T09:14:22.108391+00:00",
  "last_at": "2026-10-07T13:02:51.774010+00:00",
  "window": 1000,
  "latency_ms": {
    "avg": 12.431, "min": 4.102, "max": 318.77,
    "p50": 10.9, "p95": 24.6, "p99": 61.2
  }
}
```

Как это читать:

- `total` и `errors` считаются по **всей** истории модели, `error_rate` — их отношение,
  округлённое до четырёх знаков.
- Перцентили — только по последним `MLWRAP_STATS_WINDOW_SIZE` (по умолчанию 1000) **успешным**
  вызовам. Поле `window` показывает, сколько строк реально попало в выборку: если вызовов было
  меньше, там будет меньшее число.
- Задержки упавших вызовов в перцентили не входят намеренно — таймаут на 60 секунд иначе
  утащил бы p99 куда угодно.
- Пакетный вызов даёт в выборку одно значение — длительность всего пакета. Если вы активно
  пользуетесь batch-инференсом, перцентили из этого блока и
  `mlwrap_predict_latency_seconds` будут расходиться: Prometheus измеряет каждый элемент
  отдельно. Подробнее — в разделе [«Метрики»](metrics.md).

## Миграции и создание схемы

Единственная ревизия Alembic — `0001_initial`, она создаёт обе таблицы и все индексы.

```bash
mlwrap migrate                 # alembic upgrade head
mlwrap migrate --revision 0001 # конкретная ревизия
mlwrap initdb                  # metadata.create_all() без Alembic — для локальных прогонов
```

В Docker миграции накатывает `docker/entrypoint.sh` перед стартом uvicorn: он повторяет
`mlwrap migrate` до `MLWRAP_MIGRATE_RETRIES` раз (по умолчанию 10) с паузой в 2 секунды, пока
Postgres поднимается, и выходит с ошибкой, если так и не дождался. Поведение отключается
переменной `MLWRAP_RUN_MIGRATIONS=false`.

Есть и третий путь: `MLWRAP_DB_AUTO_CREATE=true` заставит `lifespan` вызвать `create_all()`
на старте приложения. По умолчанию выключено — в продакшене схемой должен управлять Alembic.

## Настройки и эксплуатация

| Переменная | По умолчанию | Значение |
|---|---|---|
| `MLWRAP_DATABASE_URL` | — | async DSN, например `postgresql+asyncpg://mlwrap:mlwrap@postgres:5432/mlwrap` |
| `MLWRAP_DB_POOL_SIZE` | `5` | размер пула; `max_overflow` берётся таким же |
| `MLWRAP_DB_ECHO` | `false` | логировать SQL |
| `MLWRAP_DB_AUTO_CREATE` | `false` | `create_all()` на старте вместо миграций |
| `MLWRAP_PERSIST_INFERENCES` | `true` | писать ли `inference_log` |
| `MLWRAP_PERSIST_PAYLOADS` | `false` | сохранять тела запросов и ответов |
| `MLWRAP_PAYLOAD_MAX_CHARS` | `4000` | порог усечения `payload` и `result` |
| `MLWRAP_STATS_WINDOW_SIZE` | `1000` | окно для перцентилей |

Два момента, о которых стоит помнить при долгой эксплуатации:

- **Чистки нет.** Ни партиционирования, ни retention в проекте не предусмотрено — таблицы
  растут линейно по числу запросов. Под нагрузкой заведите внешнее задание, удаляющее старые
  строки; составной индекс `(model_name, created_at)` для такого `DELETE` подходит.
- **Пул соединений общий с инференсом.** Каждая запись в журнал берёт сессию из того же пула.
  При очень высоком RPS и маленьком `MLWRAP_DB_POOL_SIZE` фоновые задачи начнут ждать
  соединение; на самих ответах это не скажется, но журнал будет отставать.

Параметры подключения для асинхронного движка `Database` подставляются по-разному в
зависимости от СУБД: для SQLite (`url.startswith("sqlite")`) `pool_size`, `max_overflow` и
`pool_pre_ping` не передаются вовсе — в aiosqlite они не применимы.
