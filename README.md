# mlwrap

FastAPI-обёртка для быстрых тестов ML-моделей. Модель подключается тремя функциями —
загрузка, инференс, сбор метрик, — которые регистрируются в реестре по имени модели.
Эндпоинты, аутентификация, метрики Prometheus и журнал запусков в БД уже готовы.

**Справка по проекту: [mejustbear.github.io/python-ml-service](https://mejustbear.github.io/python-ml-service/)**
— устройство модулей, схема БД и перечень метрик с диаграммами. Исходники справки лежат
в [`docs/`](docs/):

| Раздел | О чём |
|---|---|
| [Обзор](docs/index.md) | слои сервиса, путь одного запроса, уровни наблюдаемости |
| [Модули mlwrap](docs/modules.md) | назначение пакетов, карта зависимостей, жизненный цикл модели |
| [База данных](docs/database.md) | таблицы `inference_log` и `model_event`, связи, агрегаты |
| [Метрики Prometheus](docs/metrics.md) | все коллекторы, метки, готовые PromQL-запросы |
| [Проектный документ](docs/DESIGN.md) | основная идея, ключевые требования и границы проекта |

## Быстрый старт

```bash
pdm install                      # зависимости и сам пакет в .venv
pdm install -G examples          # опционально: пример с scikit-learn
pdm run mlwrap serve             # http://localhost:8000/docs
```

Проверка на встроенной эхо-модели:

```bash
curl -s localhost:8000/api/v1/models | jq
curl -s -X POST localhost:8000/api/v1/models/echo/predict \
     -H 'Content-Type: application/json' \
     -d '{"text": "привет", "repeat": 2}' | jq
```

```json
{
  "model": "echo",
  "version": "1.0.0",
  "latency_ms": 0.167,
  "request_id": "0a8011dd72e94bb183d9606f063b4105",
  "result": { "text": "приветпривет", "length": 12, "calls": 1 }
}
```

## Как подключить свою модель

Создайте модуль и опишите функции — схемы запроса и ответа берутся из аннотаций,
поэтому в Swagger сразу появится нормальная форма запроса.

```python
# mymodels/ranker.py
from typing import Any

import joblib
from pydantic import BaseModel

from mlwrap.registry import registry


class RankRequest(BaseModel):
    query: str
    limit: int = 10


class RankResponse(BaseModel):
    items: list[str]
    scores: list[float]


@registry.loader("ranker", version="1.2.0", description="ранжирование выдачи")
def load(config: dict[str, Any]) -> Any:
    return joblib.load(config["path"])


@registry.predictor("ranker")
def predict(model: Any, payload: RankRequest) -> RankResponse:
    items, scores = model.rank(payload.query, payload.limit)
    return RankResponse(items=items, scores=scores)


@registry.metrics("ranker")
def metrics(model: Any) -> dict[str, float]:
    return {"index_size": float(model.index_size)}
```

Запуск с этой моделью:

```bash
MLWRAP_MODELS_CONFIG='{"ranker": {"path": "/models/ranker.joblib"}}' \
pdm run mlwrap serve --plugin mymodels.ranker --preload ranker
```

Что важно знать:

- обязателен только `predictor`; без `loader` модель считается всегда готовой;
- функции могут быть `def` или `async def` — синхронные выполняются в пуле потоков;
- `loader` принимает 0 или 1 аргумент (конфиг модели из `MLWRAP_MODELS_CONFIG`);
- есть и императивный вариант: `registry.register("name", predict=..., load=...)`.

## Эндпоинты

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | информация о сервисе |
| GET | `/health/live`, `/health/ready` | живость и готовность (включая БД и упавшие модели) |
| GET | `/metrics` | метрики Prometheus |
| POST | `/api/v1/auth/token` | выдача JWT (только в режиме `jwt`) |
| GET | `/api/v1/auth/me` | текущий субъект |
| GET | `/api/v1/models` | список моделей и их состояние |
| GET | `/api/v1/models/{name}` | карточка модели |
| GET | `/api/v1/models/{name}/schema` | JSON Schema запроса и ответа |
| POST | `/api/v1/models/{name}/load` | загрузка (`?force=true` — перезагрузка) |
| POST | `/api/v1/models/{name}/unload` | выгрузка |
| POST | `/api/v1/models/{name}/predict` | инференс |
| POST | `/api/v1/models/{name}/predict/batch` | пакетный инференс |
| GET | `/api/v1/models/{name}/metrics` | метрики модели: рантайм, пользовательские, агрегаты из БД |

Для моделей, известных на старте, дополнительно генерируются типизированные роуты по тем же
путям — они и попадают в OpenAPI с реальными схемами. Модели, зарегистрированные позже,
обслуживает общий роут со свободным JSON.

## Аутентификация

Режим выбирается при запуске одним флагом:

```bash
mlwrap serve --auth none
mlwrap serve --auth basic --user admin:secret
mlwrap serve --auth jwt --user admin:secret --jwt-secret "$(openssl rand -hex 32)"
```

Получить токен и сходить с ним:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/token \
        -d 'username=admin&password=secret' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/models
```

Пароли можно хранить bcrypt-хешем: `mlwrap hash-password` выведет хеш, который кладётся
в `MLWRAP_AUTH_USERS` вместо пароля. Если для `basic`/`jwt` не задан ни один пользователь,
сервис не стартует.

## Метрики

`/metrics` отдаёт:

- `mlwrap_predict_total{model,status}`, `mlwrap_predict_latency_seconds{model}`,
  `mlwrap_predict_in_progress{model}`, `mlwrap_predict_batch_size{model}`;
- `mlwrap_model_loaded{model}`, `mlwrap_model_load_duration_seconds{model}`,
  `mlwrap_model_load_total{model,status}`;
- `mlwrap_model_custom_metric{model,metric}` — то, что вернула функция `metrics` плагина;
- `mlwrap_http_requests_total{method,path,status}`, `mlwrap_http_request_duration_seconds`.

`GET /api/v1/models/{name}/metrics` дополнительно считает по журналу в БД количество вызовов,
долю ошибок и перцентили задержки.

Полный перечень с метками, бакетами и готовыми PromQL-запросами — в
[справке по метрикам](docs/metrics.md).

## Docker

```bash
docker compose up --build
```

Поднимутся три сервиса: `api` (8000), `postgres` (5433 снаружи) и `prometheus` (9090,
скрейпит `api:8000/metrics`). Порты на хосте переопределяются переменными `API_PORT`,
`POSTGRES_PORT`, `PROMETHEUS_PORT`. Миграции применяются в entrypoint перед стартом сервиса. Режим
аутентификации и прочие параметры задаются переменными окружения — см. `docker-compose.yml`
и `.env.example`:

```bash
MLWRAP_AUTH_MODE=jwt MLWRAP_AUTH_USERS='{"admin":"secret"}' \
MLWRAP_JWT_SECRET="$(openssl rand -hex 32)" docker compose up --build
```

## Конфигурация

Все настройки — переменные окружения с префиксом `MLWRAP_`, полный список с комментариями
в [.env.example](.env.example). Часто нужные:

| Переменная | По умолчанию | Значение |
|---|---|---|
| `MLWRAP_AUTH_MODE` | `none` | `none` / `basic` / `jwt` |
| `MLWRAP_AUTH_USERS` | `{}` | `{"login": "пароль-или-bcrypt-хеш"}` |
| `MLWRAP_JWT_SECRET` | — | секрет подписи токенов |
| `MLWRAP_PLUGIN_MODULES` | `[]` | модули с моделями |
| `MLWRAP_PRELOAD_MODELS` | `[]` | загрузить на старте |
| `MLWRAP_AUTO_LOAD` | `true` | ленивая загрузка при первом запросе |
| `MLWRAP_MODELS_CONFIG` | `{}` | настройки на модель |
| `MLWRAP_PREDICT_TIMEOUT_SECONDS` | `60` | таймаут инференса |
| `MLWRAP_DATABASE_URL` | — | без него сервис работает без журнала |
| `MLWRAP_PERSIST_PAYLOADS` | `false` | сохранять тела запросов и ответов |

## CLI

```
mlwrap serve             запуск сервиса (--auth, --user, --plugin, --preload, --reload)
mlwrap models            список зарегистрированных моделей
mlwrap migrate           применить миграции Alembic
mlwrap initdb            создать таблицы без Alembic
mlwrap token SUBJECT     выпустить JWT для отладки
mlwrap hash-password     bcrypt-хеш пароля
```

## Разработка

```bash
pdm run test        # pytest
pdm run lint        # ruff check
pdm run fmt         # ruff format
pdm run typecheck   # mypy
```

Тесты гоняются на SQLite (aiosqlite) и не требуют поднятой инфраструктуры.

Документация собирается MkDocs Material и публикуется на GitHub Pages воркфлоу
`.github/workflows/docs.yml` при пуше в `master`. Локально:

```bash
pdm install -G docs
pdm run docs          # mkdocs serve на http://localhost:8000
pdm run docs-build    # mkdocs build --strict
```
