# mlwrap — FastAPI-обёртка для быстрого тестирования ML-моделей

Проектный документ. Описывает, что реализуется вместо текущего Flask-сервиса.

## 1. Зачем

Сейчас в репозитории лежит Flask-приложение, намертво сшитое с одной Keras-моделью
классификации новостей: модель грузится на импорте пакета (`app/models/predict/__init__.py`),
эндпоинты знают о ней по именам параметров формы, конфигурация — набор классов с путями,
метрик и аутентификации нет. Чтобы проверить другую модель, нужно править сам сервис.

Цель переписывания — получить каркас, в который модель «подкладывается» одним модулем:
пишем функции загрузки, инференса и сбора метрик, регистрируем их под именем модели,
и сразу получаем готовые HTTP-эндпоинты, аутентификацию, метрики Prometheus и лог запусков в БД.

## 2. Ключевые требования

1. Аутентификация выбирается при запуске: `none`, `httpbasic`, `jwt` — один флаг/переменная окружения.
2. Три базовые операции над моделью: загрузка, вызов инференса, сбор метрик.
3. Каждая операция — это отдельная функция в коде пользователя, регистрируемая по имени модели.
   Эндпоинты в сервисе уже готовы и общие для всех моделей.
4. Пакетный менеджер — PDM.
5. Docker-образ и docker-compose с базой данных и Prometheus.

## 3. Структура проекта

```
pyproject.toml            # PDM: зависимости, скрипты, конфиг ruff/mypy/pytest
Dockerfile                # multi-stage сборка на pdm
docker-compose.yml        # api + postgres + prometheus
docker/entrypoint.sh      # ожидание БД, миграции, запуск
deploy/prometheus/        # конфиг сбора метрик
alembic.ini, migrations/  # миграции БД
docs/DESIGN.md            # этот документ
src/mlwrap/
  app.py                  # фабрика FastAPI-приложения, lifespan
  config.py               # Settings (pydantic-settings, префикс MLWRAP_)
  cli.py                  # mlwrap serve|migrate|models|token|hash-password
  errors.py, schemas.py, logging.py
  registry/               # реестр моделей и рантайм
    spec.py               # ModelSpec — описание модели
    registry.py           # декораторы регистрации
    runtime.py            # состояние моделей, load/unload/predict
    discovery.py          # импорт модулей-плагинов
  security/               # провайдеры аутентификации
    base.py, users.py, none.py, basic.py, jwt.py, factory.py
  observability/
    metrics.py            # коллекторы Prometheus
    middleware.py         # request-id, логи, HTTP-метрики
  db/                     # SQLAlchemy 2.0 async
    models.py             # inference_log, model_event
    repository.py         # запись и агрегаты
    session.py            # engine/sessionmaker, зависимость
  api/
    deps.py, dynamic.py   # генерация типизированных роутов на модель
    routes/               # system, auth, models
  plugins/                # примеры моделей
tests/
```

## 4. Контракт плагина

Модель описывается тремя необязательно-связанными функциями, каждая регистрируется по имени модели.
Схемы запроса и ответа выводятся из аннотаций типов — они же попадают в OpenAPI.

```python
from pydantic import BaseModel
from mlwrap.registry import registry


class IrisRequest(BaseModel):
    features: list[float]


class IrisResponse(BaseModel):
    label: str
    proba: dict[str, float]


@registry.loader("iris", version="1.0.0", description="RandomForest на ирисах")
def load_iris(config: dict) -> Any:
    return joblib.load(config["path"])


@registry.predictor("iris")
def predict_iris(model: Any, payload: IrisRequest) -> IrisResponse:
    ...


@registry.metrics("iris")
def iris_metrics(model: Any) -> dict[str, float]:
    return {"n_estimators": model.n_estimators}


@registry.unloader("iris")          # необязательно
def unload_iris(model: Any) -> None:
    ...
```

Правила:

- обязателен только `predictor`; без `loader` модель считается «всегда готовой» (`model is None`);
- функции могут быть как `def`, так и `async def` — синхронные выполняются в пуле потоков,
  чтобы не блокировать event loop (типичная ML-библиотека блокирующая);
- `loader` принимает 0 или 1 аргумент; если аргумент есть, туда приходит per-model конфиг
  из `MLWRAP_MODELS_CONFIG`;
- тип второго аргумента `predictor` становится схемой запроса, возвращаемый тип — схемой ответа;
  если аннотаций нет, используется свободный JSON (`dict`).

Альтернатива для тех, кому ближе классы: `registry.register(...)` принимает готовые callables,
поэтому плагин можно собрать и из методов класса.

Подключение плагинов — переменная `MLWRAP_PLUGIN_MODULES` (список импортируемых модулей).
Модули из пакета `mlwrap.plugins` подхватываются автоматически.

## 5. Жизненный цикл модели

`ModelRuntime` хранит по каждой модели дескриптор: состояние (`unloaded → loading → ready | failed`),
объект модели, время и длительность загрузки, счётчики вызовов, последнюю ошибку.

- Загрузка идёт под персональной `asyncio.Lock`, параллельные запросы не дублируют работу.
- `MLWRAP_PRELOAD_MODELS` — список моделей, загружаемых на старте приложения.
- `MLWRAP_AUTO_LOAD=true` (по умолчанию) — незагруженная модель грузится при первом `predict`;
  при `false` запрос к незагруженной модели вернёт `409`.
- На `predict` навешен таймаут `MLWRAP_PREDICT_TIMEOUT_SECONDS` (0 — выключен).

## 6. Эндпоинты

Готовы заранее, работают для любой зарегистрированной модели.

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/` | информация о сервисе, режим аутентификации |
| GET | `/health/live`, `/health/ready` | проверки живости и готовности (включая БД) |
| GET | `/metrics` | метрики в формате Prometheus |
| POST | `/api/v1/auth/token` | выдача JWT (только в режиме `jwt`) |
| GET | `/api/v1/auth/me` | текущий субъект |
| GET | `/api/v1/models` | список моделей и их состояние |
| GET | `/api/v1/models/{name}` | карточка модели |
| GET | `/api/v1/models/{name}/schema` | JSON Schema запроса и ответа |
| POST | `/api/v1/models/{name}/load` | загрузка (`?force=true` — перезагрузка) |
| POST | `/api/v1/models/{name}/unload` | выгрузка |
| POST | `/api/v1/models/{name}/predict` | инференс |
| POST | `/api/v1/models/{name}/predict/batch` | пакетный инференс |
| GET | `/api/v1/models/{name}/metrics` | метрики модели: рантайм + пользовательские + агрегаты из БД |

Для каждой модели, известной на старте, дополнительно генерируется типизированный роут с тем же
путём и подставленными схемами — в Swagger видно реальное тело запроса и ответа, а не «любой JSON».
Модели, зарегистрированные позже, обслуживает общий роут.

Ответ инференса — конверт: `{"model", "version", "latency_ms", "request_id", "result"}`,
чтобы latency был виден сразу, без похода в Prometheus.

## 7. Аутентификация

Режим задаётся при запуске: `mlwrap serve --auth jwt` или `MLWRAP_AUTH_MODE=jwt`.
Провайдер выбирается один раз в фабрике приложения и подставляется зависимостью во все
защищённые роуты, поэтому в Swagger сразу появляется нужная схема авторизации.

- `none` — субъект `anonymous`, ничего не проверяется (для локальных прогонов).
- `basic` — `HTTPBasic`, пользователи из `MLWRAP_AUTH_USERS` (JSON `{"user": "password-или-bcrypt-хеш"}`),
  сравнение паролей константное по времени.
- `jwt` — `OAuth2PasswordBearer`, `/api/v1/auth/token` меняет логин/пароль из того же хранилища
  на HS256-токен с TTL; сторонние токены принимаются, если подписаны тем же секретом.

Если для `basic`/`jwt` не задан ни один пользователь (или для `jwt` нет секрета) — приложение
падает на старте, а не пускает всех подряд. `/metrics` по умолчанию открыт (его забирает
Prometheus изнутри сети), закрывается флагом `MLWRAP_METRICS_PROTECTED=true`.

## 8. Метрики

Собираются на трёх уровнях.

1. **Prometheus** (`/metrics`, `prometheus-client`):
   - `mlwrap_predict_total{model,status}`, `mlwrap_predict_latency_seconds{model}` (гистограмма),
     `mlwrap_predict_in_progress{model}`;
   - `mlwrap_model_loaded{model}`, `mlwrap_model_load_duration_seconds{model}`,
     `mlwrap_model_load_total{model,status}`;
   - `mlwrap_model_custom_metric{model,metric}` — то, что вернула функция `metrics` плагина;
   - HTTP-слой: `mlwrap_http_requests_total{method,path,status}`, `mlwrap_http_request_duration_seconds`.
2. **Рантайм-счётчики** в памяти — число вызовов, ошибок, время последнего вызова.
3. **Лог инференсов в БД** — из него считаются агрегаты (количество, доля ошибок, средняя и
   перцентильные задержки) для `/api/v1/models/{name}/metrics`.

Запись в БД выполняется фоновой задачей после ответа и никогда не роняет инференс:
ошибка записи только логируется.

## 9. База данных

PostgreSQL, SQLAlchemy 2.0 (async, asyncpg), миграции Alembic.

- `inference_log` — `id`, `model_name`, `model_version`, `status`, `latency_ms`, `error`,
  `request_id`, `principal`, `payload`, `result`, `created_at`.
  Тела запроса и ответа пишутся только при `MLWRAP_PERSIST_PAYLOADS=true`.
- `model_event` — события `load` / `unload` / `load_failed` с длительностью и деталями.

БД опциональна: без `MLWRAP_DATABASE_URL` сервис работает полностью, просто без истории и агрегатов.
Тесты гоняются на SQLite (aiosqlite), поэтому типы колонок выбраны портируемые.

## 10. Конфигурация

`pydantic-settings`, префикс `MLWRAP_`, поддержка `.env`. Основное:

| Переменная | По умолчанию | Значение |
|---|---|---|
| `MLWRAP_AUTH_MODE` | `none` | `none` / `basic` / `jwt` |
| `MLWRAP_AUTH_USERS` | `{}` | JSON с пользователями |
| `MLWRAP_JWT_SECRET`, `MLWRAP_JWT_TTL_MINUTES` | — / `60` | параметры токенов |
| `MLWRAP_PLUGIN_MODULES` | `[]` | модули с моделями |
| `MLWRAP_PRELOAD_MODELS` | `[]` | загрузить на старте |
| `MLWRAP_AUTO_LOAD` | `true` | ленивая загрузка при первом запросе |
| `MLWRAP_MODELS_CONFIG` | `{}` | JSON с настройками на модель |
| `MLWRAP_DATABASE_URL` | — | async DSN Postgres |
| `MLWRAP_PERSIST_PAYLOADS` | `false` | сохранять тела запросов/ответов |
| `MLWRAP_PREDICT_TIMEOUT_SECONDS` | `60` | таймаут инференса |

## 11. Docker и compose

- Dockerfile — двухстадийный: на первой стадии `pdm install --prod` собирает `.venv`,
  на вторую копируется только виртуальное окружение и код; запуск от непривилегированного пользователя,
  `HEALTHCHECK` на `/health/live`.
- `docker-compose.yml`: `api` (порт 8000), `postgres` (healthcheck `pg_isready`, том для данных),
  `prometheus` (порт 9090, скрейпит `api:8000/metrics`).
  Entrypoint ждёт БД, прогоняет `alembic upgrade head` и стартует uvicorn.

## 12. Тесты

pytest + httpx `ASGITransport`, БД — SQLite в файле теста. Покрываем:
регистрацию и вывод схем, три режима аутентификации, load/unload/predict/ошибки,
генерацию `/openapi.json` с динамическими роутами, отдачу `/metrics`, агрегаты из БД.

## 13. Вне рамок

Обучение моделей внутри сервиса, версионирование артефактов, очередь задач и распределённый
инференс, мультипроцессный режим Prometheus, Grafana-дашборды. Старая модель классификации
новостей и её артефакты удаляются — они остаются в истории git.
