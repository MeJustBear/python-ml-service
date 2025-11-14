# Постановка задачи: ML-сервис классификации новостей

## 1. Обзор проекта

### 1.1. Текущее состояние
Репозиторий содержит тестовый проект ML-сервиса для классификации новостных статей по категориям, построенный на Flask. Модель способна определять категорию текста с точностью ~99%.

### 1.2. Цель проекта
Трансформировать существующий прототип в production-ready backend сервис, соответствующий современным стандартам разработки корпоративных ML-решений.

---

## 2. Ожидаемый итоговый результат

### 2.1. Общее описание
**Backend сервис** для классификации новостных статей, который:
- Принимает на вход текст статьи или URL-ссылку на статью
- Обрабатывает входные данные с помощью предобученной ML-модели
- Возвращает результат классификации в структурированном формате (JSON)

### 2.2. Функциональные возможности
Сервис должен предоставлять следующие основные эндпоинты:

#### 2.2.1. Классификация по тексту
- **Эндпоинт:** `POST /api/v1/predict/text`
- **Описание:** Принимает текст статьи и возвращает вероятности принадлежности к каждой категории
- **Формат ответа:**
```json
{
  "request_id": "uuid",
  "timestamp": "2025-11-19T12:00:00Z",
  "predictions": {
    "Без политики": 50.7047,
    "Бывший СССР": 0.0,
    "Мероприятия RT": 0.0,
    "Мир": 0.0,
    "Наука": 49.2952,
    "Новости партнёров": 0.0,
    "Пресс-релизы": 0.0,
    "Россия": 0.0,
    "Спорт": 0.0,
    "Экономика": 0.0
  },
  "top_category": "Без политики",
  "confidence": 50.7047,
  "processing_time_ms": 156
}
```

#### 2.2.2. Классификация по URL
- **Эндпоинт:** `POST /api/v1/predict/url`
- **Описание:** Принимает URL статьи, извлекает текст и выполняет классификацию
- **Формат ответа:** Аналогичен классификации по тексту

#### 2.2.3. Служебные эндпоинты
- `GET /health` - проверка работоспособности сервиса
- `GET /ready` - проверка готовности к обработке запросов (модель загружена)
- `GET /metrics` - метрики Prometheus
- `GET /api/v1/categories` - список доступных категорий классификации

---

## 3. Система авторизации и безопасность

### 3.1. Требования
Доступ к API сервиса должен быть защищен системой авторизации на основе токенов.

### 3.2. Реализация авторизации

#### 3.2.1. JWT-токены (JSON Web Tokens)
- Использование JWT для аутентификации клиентов
- Срок действия токена: 24 часа (настраиваемый параметр)
- Refresh токены для продления сессии (срок действия: 30 дней)

#### 3.2.2. Эндпоинты авторизации
- `POST /api/v1/auth/register` - регистрация нового пользователя (API ключа)
- `POST /api/v1/auth/login` - получение access и refresh токенов
- `POST /api/v1/auth/refresh` - обновление access токена
- `POST /api/v1/auth/revoke` - отзыв токена

#### 3.2.3. Модель данных пользователей

Модель пользователя и модель api-ключей должны быть разделены для поддержки множества ключей на пользователя:

```python
User:
    - id: UUID (PK)
    - username: str (unique)
    - email: str (unique)
    - hashed_password: str
    - is_active: bool
    - is_admin: bool
    - created_at: datetime
    - updated_at: datetime

ApiKey:
    - id: UUID (PK)
    - user_id: UUID (FK -> User.id)
    - key: str (unique)
    - created_at: datetime
    - expires_at: datetime (optional)
    - revoked: bool (default: False)
```

Таким образом, у одного пользователя может быть несколько активных или отозванных api-ключей.

#### 3.2.4. Уровни доступа
- **Admin:** Полный доступ к API + управление пользователями
- **User:** Доступ к эндпоинтам классификации
- **Anonymous:** Доступ только к `/health` и `/docs`

#### 3.2.5. Rate limiting
- Ограничение количества запросов: 100 запросов/минуту для обычных пользователей
- Ограничение для админов: 1000 запросов/минуту
- HTTP 429 при превышении лимита

### 3.3. Полная схема моделей данных PostgreSQL

Ниже представлена полная структура всех ORM-моделей, которые должны быть реализованы в системе.

#### 3.3.1. User (Пользователи)
```python
User:
    - id: UUID (PK)
    - username: str (unique, indexed)
    - email: str (unique, indexed)
    - hashed_password: str
    - full_name: str (optional)
    - is_active: bool (default: True)
    - is_admin: bool (default: False)
    - is_verified: bool (default: False)
    - created_at: datetime (auto)
    - updated_at: datetime (auto)
    - last_login_at: datetime (nullable)
    
    # Relationships
    - api_keys: List[ApiKey]
    - predictions: List[PredictionLog]
```

**Индексы:**
- `ix_user_email` - для быстрого поиска по email
- `ix_user_username` - для быстрого поиска по username
- `ix_user_is_active` - для фильтрации активных пользователей

#### 3.3.2. ApiKey (API ключи)
```python
ApiKey:
    - id: UUID (PK)
    - user_id: UUID (FK -> User.id, indexed)
    - key: str (unique, indexed) # хешированный API ключ
    - name: str (optional) # описательное имя ключа ("Production API", "Dev Server")
    - prefix: str (8 chars) # первые 8 символов для отображения пользователю
    - scopes: str[] (JSONB) # массив разрешений ["predict:read", "predict:write"]
    - last_used_at: datetime (nullable)
    - usage_count: int (default: 0) # счетчик использований
    - rate_limit: int (default: 100) # персональный rate limit для ключа
    - created_at: datetime (auto)
    - expires_at: datetime (nullable) # опциональный срок действия
    - revoked_at: datetime (nullable)
    - is_revoked: bool (default: False, indexed)
    
    # Relationships
    - user: User
    - predictions: List[PredictionLog]
```

**Индексы:**
- `ix_apikey_key` - для быстрой проверки ключа
- `ix_apikey_user_id` - для получения всех ключей пользователя
- `ix_apikey_is_revoked` - для фильтрации активных ключей
- `ix_apikey_prefix` - для поиска ключей по префиксу

**Constraints:**
- CHECK: `expires_at > created_at` (если expires_at не NULL)

#### 3.3.3. PredictionLog (Лог классификаций)

**Основная модель для сохранения всех запросов и результатов классификации.**

```python
PredictionLog:
    - id: UUID (PK)
    - request_id: UUID (unique, indexed) # для трейсинга и корреляции с логами
    
    # User & Auth info
    - user_id: UUID (FK -> User.id, indexed, nullable)
    - api_key_id: UUID (FK -> ApiKey.id, indexed, nullable)
    
    # Request details
    - request_type: Enum['text', 'url'] (indexed)
    - input_text_hash: str (SHA256, indexed) # хеш текста для дедупликации
    - input_text_preview: str (500 chars) # первые 500 символов для отладки
    - input_url: str (nullable) # полный URL если был URL-запрос
    - text_length: int # длина входного текста
    
    # Response details
    - predictions: JSONB # полный JSON с вероятностями всех категорий
    - top_category: str (indexed) # категория с максимальной вероятностью
    - confidence: float # уверенность модели (max вероятность)
    - all_categories_count: int (default: 10) # количество категорий в ответе
    
    # Performance metrics
    - processing_time_ms: int # общее время обработки
    - model_inference_time_ms: int # только время работы модели
    - text_fetch_time_ms: int (nullable) # время загрузки текста (для URL)
    
    # Status & Error handling
    - status: Enum['success', 'error', 'timeout', 'invalid_input']
    - error_code: str (nullable) # код ошибки если была
    - error_message: str (nullable) # описание ошибки
    
    # Request metadata
    - ip_address: str (indexed) # IP адрес клиента
    - user_agent: str # User-Agent браузера/клиента
    - model_version: str (indexed) # версия модели, которая делала предсказание
    
    # Timestamps
    - created_at: datetime (auto, indexed) # партиционирование по этому полю
    
    # Relationships
    - user: User
    - api_key: ApiKey
```

**Индексы:**
- `ix_prediction_request_id` - для быстрого поиска по request_id
- `ix_prediction_user_id` - для получения истории пользователя
- `ix_prediction_api_key_id` - для аналитики по ключам
- `ix_prediction_created_at` - для запросов по времени
- `ix_prediction_status` - для фильтрации по статусу
- `ix_prediction_top_category` - для аналитики по категориям
- `ix_prediction_model_version` - для A/B тестирования моделей
- `ix_prediction_input_text_hash` - для поиска дубликатов
- `ix_prediction_request_type` - для раздельной аналитики text/url

**Составные индексы:**
- `ix_prediction_user_created` (user_id, created_at DESC) - для истории пользователя
- `ix_prediction_status_created` (status, created_at DESC) - для мониторинга ошибок

**Партиционирование:**
Таблица должна быть партиционирована по `created_at` (по месяцам) для оптимизации производительности при больших объемах данных.

```sql
-- Пример партиционирования
CREATE TABLE prediction_log_2025_11 PARTITION OF prediction_log
    FOR VALUES FROM ('2025-11-01') TO ('2025-12-01');
```

**Retention Policy:**
- Production данные: хранить 12 месяцев
- После 12 месяцев: архивировать в cold storage (S3) или удалять
- Агрегированная статистика: хранить бесконечно

#### 3.3.4. UserSession (Опциональная модель для сессий)

```python
UserSession:
    - id: UUID (PK)
    - user_id: UUID (FK -> User.id, indexed)
    - refresh_token_hash: str (unique, indexed)
    - access_token_jti: str (nullable) # JWT ID для отзыва
    - ip_address: str
    - user_agent: str
    - created_at: datetime (auto)
    - expires_at: datetime (indexed)
    - last_activity_at: datetime
    - is_active: bool (default: True, indexed)
    
    # Relationships
    - user: User
```

**Назначение:** Управление активными сессиями, возможность отзыва refresh токенов.

**Индексы:**
- `ix_session_user_id` - все сессии пользователя
- `ix_session_refresh_token` - проверка refresh токена
- `ix_session_is_active` - фильтрация активных сессий
- `ix_session_expires_at` - очистка истекших сессий

#### 3.3.5. AuditLog (Опциональная модель для аудита)

```python
AuditLog:
    - id: UUID (PK)
    - user_id: UUID (FK -> User.id, indexed, nullable)
    - action: str (indexed) # "login", "register", "api_key_created", "api_key_revoked"
    - resource_type: str # "user", "api_key", "prediction"
    - resource_id: UUID (nullable)
    - details: JSONB # дополнительная информация
    - ip_address: str (indexed)
    - user_agent: str
    - success: bool (indexed)
    - created_at: datetime (auto, indexed)
    
    # Relationships
    - user: User
```

**Назначение:** Детальный аудит важных действий в системе.

**Индексы:**
- `ix_audit_user_id` - история действий пользователя
- `ix_audit_action` - фильтрация по типу действия
- `ix_audit_created_at` - хронологический поиск
- `ix_audit_success` - поиск неудачных попыток

### 3.4. Диаграмма связей (ER Diagram)

```
┌─────────────────┐
│      User       │
│  - id (PK)      │
│  - username     │
│  - email        │
│  - is_admin     │
└────────┬────────┘
         │
         │ 1:N
         │
    ┌────┴────────────┬─────────────────┬────────────────┐
    │                 │                 │                │
    ▼                 ▼                 ▼                ▼
┌───────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────┐
│  ApiKey   │  │ PredictionLog│  │ UserSession │  │ AuditLog │
│ - id (PK) │  │  - id (PK)   │  │  - id (PK)  │  │- id (PK) │
│ - user_id │  │  - user_id   │  │  - user_id  │  │- user_id │
│ - key     │  │  - api_key_id│  │  - token    │  │- action  │
└─────┬─────┘  └──────▲───────┘  └─────────────┘  └──────────┘
      │               │
      │ 1:N           │
      └───────────────┘
```

### 3.5. Дополнительные эндпоинты для работы с данными

#### 3.5.1. История предсказаний пользователя
```
GET /api/v1/predictions/history
  - Query params: limit, offset, from_date, to_date, category, status
  - Response: список PredictionLog для текущего пользователя
```

#### 3.5.2. Статистика пользователя
```
GET /api/v1/predictions/stats
  - Response: агрегированная статистика (количество запросов, распределение по категориям, средняя уверенность)
```

#### 3.5.3. Получение конкретного предсказания
```
GET /api/v1/predictions/{request_id}
  - Response: детальная информация о конкретном запросе
```

#### 3.5.4. Управление API ключами
```
GET    /api/v1/api-keys           - список ключей пользователя
POST   /api/v1/api-keys           - создание нового ключа
DELETE /api/v1/api-keys/{key_id}  - отзыв ключа
PATCH  /api/v1/api-keys/{key_id}  - обновление настроек ключа
```

### 3.6. Соображения по производительности

#### 3.6.1. Оптимизация записи в PredictionLog
- **Async writes:** Запись в БД не должна блокировать ответ пользователю
- **Batch inserts:** Накопление и батчевая запись при высокой нагрузке
- **Background workers:** Celery/RQ для асинхронной записи

#### 3.6.2. Очистка старых данных
- **Автоматическое партиционирование:** Создание новых партиций каждый месяц
- **Scheduled job:** Удаление/архивация партиций старше 12 месяцев
- **Vacuum:** Регулярная очистка удаленных записей

#### 3.6.3. Кэширование
- **Redis:** Кэширование часто запрашиваемых статистик
- **TTL:** 5-15 минут для статистики
- **Invalidation:** Сброс кэша при новых предсказаниях

---

## 4. Мониторинг и наблюдаемость (Observability)

### 4.1. Логирование (ELK Stack)

#### 4.1.1. Компоненты
- **Elasticsearch:** Хранилище логов
- **Logstash:** Агрегация и обработка логов
- **Kibana:** Визуализация и анализ логов

#### 4.1.2. Структура логов
Все логи должны содержать следующие поля:
```json
{
  "timestamp": "2025-11-19T12:00:00.000Z",
  "level": "INFO|WARNING|ERROR|CRITICAL",
  "service": "ml-classifier",
  "environment": "production|staging|development",
  "request_id": "uuid",
  "user_id": "uuid",
  "endpoint": "/api/v1/classify/text",
  "method": "POST",
  "status_code": 200,
  "duration_ms": 156,
  "message": "Request processed successfully",
  "metadata": {
    "model_version": "1.0.0",
    "text_length": 1024,
    "error_details": null
  }
}
```

#### 4.1.3. Категории логов
1. **Application logs:** Основные события приложения
2. **Access logs:** HTTP запросы и ответы
3. **Error logs:** Ошибки и исключения
4. **Audit logs:** Действия пользователей (авторизация, изменение настроек)
5. **ML Model logs:** Специфичные для модели события (загрузка, предсказания, метрики)

#### 4.1.4. Уровни логирования
- **DEBUG:** Детальная информация для отладки (не в продакшене)
- **INFO:** Общие информационные сообщения
- **WARNING:** Предупреждения о потенциальных проблемах
- **ERROR:** Ошибки, требующие внимания
- **CRITICAL:** Критические ошибки, требующие немедленного вмешательства

### 4.2. Метрики и телеметрия (Prometheus + Grafana)

#### 4.2.1. Prometheus - сбор метрик
Экспорт метрик через `/metrics` endpoint

#### 4.2.2. Категории метрик

**A. HTTP метрики:**
- `http_requests_total` - общее количество запросов (по эндпоинтам, статус-кодам)
- `http_request_duration_seconds` - время обработки запросов (histogram)
- `http_requests_in_progress` - количество запросов в обработке

**B. Бизнес-метрики:**
- `classification_requests_total` - количество классификаций
- `classification_duration_seconds` - время классификации
- `classification_by_category` - распределение классификаций по категориям
- `classification_confidence_score` - средняя уверенность модели
- `classification_errors_total` - количество ошибок классификации

**C. Системные метрики:**
- `cpu_usage_percent` - использование CPU
- `memory_usage_bytes` - использование памяти
- `model_memory_usage_bytes` - память, занимаемая моделью

**D. Метрики базы данных:**
- `db_connection_pool_size` - текущий размер пула соединений
- `db_connection_pool_available` - доступные соединения в пуле
- `db_connection_pool_in_use` - используемые соединения
- `db_query_duration_seconds` - время выполнения запросов (histogram, по типам запросов)
- `db_queries_total` - общее количество запросов к БД (по типам: SELECT, INSERT, UPDATE)
- `db_connection_errors_total` - ошибки подключения к БД
- `db_transaction_duration_seconds` - время транзакций
- `db_slow_queries_total` - количество медленных запросов (> 1 сек)
- `prediction_log_writes_total` - количество записей в PredictionLog
- `prediction_log_write_errors_total` - ошибки записи в PredictionLog
- `prediction_log_table_size_bytes` - размер таблицы PredictionLog
- `prediction_log_records_total` - общее количество записей в PredictionLog

**F. Метрики авторизации:**
- `auth_attempts_total` - попытки авторизации (успешные/неуспешные)
- `active_users_total` - количество активных пользователей
- `active_api_keys_total` - количество активных API ключей
- `api_key_usage_total` - использование API ключей (по ключам)
- `token_refresh_total` - количество обновлений токенов
- `token_validation_errors_total` - ошибки валидации токенов
- `rate_limit_exceeded_total` - количество превышений rate limit (по пользователям)

**G. ML Model метрики:**
- `model_load_time_seconds` - время загрузки модели
- `model_inference_time_seconds` - время инференса (histogram)
- `model_version_info` - информация о версии модели (gauge)
- `model_predictions_total` - общее количество предсказаний
- `model_predictions_by_category` - распределение предсказаний по категориям
- `model_confidence_distribution` - распределение уверенности модели (histogram)
- `model_low_confidence_predictions_total` - предсказания с низкой уверенностью (< 60%)

**H. Бизнес-аналитика и данные:**
- `predictions_stored_total` - количество сохраненных предсказаний в БД
- `predictions_by_request_type` - распределение по типу запроса (text/url)
- `unique_users_daily` - уникальные пользователи за день
- `predictions_per_user` - среднее количество предсказаний на пользователя
- `text_length_distribution` - распределение длины входного текста (histogram)
- `url_fetch_failures_total` - неудачные попытки загрузки URL
- `cache_hits_total` - попадания в кэш (если используется кэширование по хешу)
- `cache_misses_total` - промахи кэша
- `duplicate_requests_total` - количество дубликатов запросов (по хешу текста)

#### 4.2.3. Grafana - визуализация
**Дашборды:**

1. **Service Overview:**
   - Общий health сервиса
   - RPS (requests per second)
   - Latency (p50, p95, p99)
   - Error rate
   - Active connections
   - Request status distribution

2. **ML Model Performance:**
   - Время инференса (p50, p95, p99)
   - Распределение уверенности модели
   - Распределение предсказаний по категориям
   - Throughput модели (predictions/sec)
   - Предсказания с низкой уверенностью
   - Версия модели и статус загрузки

3. **Database Performance:**
   - Connection pool status (available/in-use/total)
   - Query duration (by type: SELECT, INSERT, UPDATE)
   - Slow queries (> 1 sec)
   - Transaction duration
   - Database errors rate
   - PredictionLog table metrics:
     - Write rate (rows/sec)
     - Table size growth
     - Partition status
     - Query performance on historical data

4. **Infrastructure:**
   - CPU usage (%)
   - Memory usage (total/available)
   - Model memory footprint
   - Disk I/O
   - Network I/O

5. **Authentication & Security:**
   - Login attempts (success/failed)
   - Active users timeline
   - Active API keys
   - Token refresh rate
   - Rate limit violations (by user/IP)
   - Failed authentication attempts by IP
   - Suspicious activity detection

6. **Business Analytics:**
   - Daily/Weekly/Monthly predictions count
   - Unique users (daily/weekly/monthly)
   - Predictions by request type (text vs URL)
   - Top categories distribution
   - Average predictions per user
   - Text length distribution
   - URL fetch success rate
   - Peak usage hours
   - User growth trend

7. **Data Quality & Anomalies:**
   - Duplicate requests rate
   - Cache hit/miss ratio
   - Error rate by category
   - Unusual patterns detection
   - Input validation failures
   - Timeout rate

8. **Alerts Dashboard:**
   - Current active alerts
   - Alert history timeline
   - MTTR (Mean Time To Recovery)
   - Incident frequency by type

#### 4.2.4. Алертинг
**Критические алерты:**
- Service down (>5 минут недоступности)
- Error rate > 5%
- Response time p95 > 2 секунд
- Memory usage > 90%
- CPU usage > 80%
- DB connection pool exhausted

**Предупреждения:**
- Error rate > 1%
- Response time p95 > 1 секунда
- Memory usage > 70%
- Rate limit exceeded часто для одного пользователя

### 4.3. Трейсинг (опционально, но рекомендуется)
- **Jaeger** или **Zipkin** для distributed tracing
- Трассировка полного пути запроса через систему
- Идентификация узких мест в производительности

### 4.4. Качество работы сервиса (SLI/SLO)

#### 4.4.1. Service Level Indicators (SLI)
- **Availability:** % времени, когда сервис доступен
- **Latency:** % запросов, обработанных быстрее порога
- **Error Rate:** % запросов без ошибок
- **Throughput:** количество запросов в секунду

#### 4.4.2. Service Level Objectives (SLO)
- Availability: 99.5% (monthly)
- Latency p95: < 500ms для простых запросов
- Latency p95: < 2s для URL-классификации
- Error rate: < 0.1%
- Throughput: минимум 100 RPS

---

## 5. Тестирование

### 5.1. Принципы тестирования
- **Не тестируем качество предсказаний модели** (это отдельная задача Data Science)
- Тестируем функциональность сервиса и его компонентов
- Минимальное покрытие кода тестами: 80%

### 5.2. Типы тестов

#### 5.2.1. Unit Tests (Модульные тесты)

**A. Тесты утилит и вспомогательных функций:**
```python
# tests/unit/test_text_preprocessing.py
- test_text_cleaning()
- test_url_validation()
- test_text_extraction_from_html()
- test_tokenization()
```

**B. Тесты бизнес-логики:**
```python
# tests/unit/test_classification_service.py
- test_prepare_input_data()
- test_validate_classification_input()
- test_format_classification_output()
- test_calculate_confidence_score()
```

**C. Тесты авторизации:**
```python
# tests/unit/test_auth.py
- test_password_hashing()
- test_token_generation()
- test_token_validation()
- test_token_expiration()
- test_refresh_token_flow()
```

**D. Тесты моделей данных:**
```python
# tests/unit/test_models.py
- test_user_model_creation()
- test_user_model_validation()
- test_classification_result_model()
```

#### 5.2.2. Integration Tests (Интеграционные тесты)

**A. Тесты базы данных:**
```python
# tests/integration/test_database.py
- test_user_crud_operations()
- test_user_unique_constraints()
- test_api_key_crud_operations()
- test_api_key_cascade_delete()
- test_multiple_api_keys_per_user()
- test_prediction_log_creation()
- test_prediction_log_relationships()
- test_prediction_log_indexes_performance()
- test_transaction_rollback()
- test_concurrent_writes()
- test_connection_pool()
- test_connection_pool_exhaustion()
- test_query_performance_with_indexes()
- test_jsonb_queries_on_predictions()
```

**A2. Тесты моделей данных:**
```python
# tests/integration/test_models.py
- test_user_model_validation()
- test_user_password_hashing()
- test_api_key_prefix_generation()
- test_api_key_expiration_logic()
- test_api_key_revocation()
- test_prediction_log_text_hash_generation()
- test_prediction_log_jsonb_storage()
- test_user_session_creation()
- test_audit_log_recording()
```

**A3. Тесты партиционирования:**
```python
# tests/integration/test_partitioning.py
- test_prediction_log_partition_creation()
- test_prediction_log_partition_routing()
- test_query_performance_on_partitioned_table()
- test_old_partition_cleanup()
```

**B. Тесты внешних зависимостей:**
```python
# tests/integration/test_external_services.py
- test_url_fetching()
- test_url_parsing()
- test_network_timeout_handling()
- test_invalid_url_handling()
```

**C. Тесты загрузки модели:**
```python
# tests/integration/test_model_loading.py
- test_model_loads_successfully()
- test_model_initialization()
- test_model_prediction_pipeline()
- test_model_memory_usage()
```

#### 5.2.3. API Tests (End-to-End тесты API)

**A. Тесты эндпоинтов классификации:**
```python
# tests/api/test_classification_endpoints.py
- test_classify_text_success()
- test_classify_text_empty_input()
- test_classify_text_too_long()
- test_classify_text_special_characters()
- test_classify_text_saves_to_database()
- test_classify_url_success()
- test_classify_url_invalid()
- test_classify_url_unavailable()
- test_classify_url_timeout()
- test_classify_url_saves_to_database()
- test_get_categories()
- test_classification_response_format()
- test_classification_includes_request_id()
```

**A2. Тесты эндпоинтов истории предсказаний:**
```python
# tests/api/test_prediction_history.py
- test_get_prediction_history_authenticated()
- test_get_prediction_history_pagination()
- test_get_prediction_history_filter_by_date()
- test_get_prediction_history_filter_by_category()
- test_get_prediction_history_filter_by_status()
- test_get_prediction_by_request_id()
- test_get_prediction_not_found()
- test_get_prediction_unauthorized_access() # пользователь пытается получить чужой
- test_get_user_statistics()
- test_statistics_accuracy()
```

**A3. Тесты эндпоинтов управления API ключами:**
```python
# tests/api/test_api_keys.py
- test_create_api_key()
- test_create_api_key_with_name()
- test_create_api_key_with_expiration()
- test_create_api_key_with_custom_rate_limit()
- test_list_user_api_keys()
- test_list_shows_only_user_keys()
- test_revoke_api_key()
- test_revoke_already_revoked_key()
- test_revoke_other_user_key_forbidden()
- test_update_api_key_name()
- test_update_api_key_rate_limit()
- test_api_key_usage_tracking()
- test_api_key_last_used_update()
- test_expired_api_key_rejected()
```

**B. Тесты авторизации:**
```python
# tests/api/test_auth_endpoints.py
- test_register_new_user()
- test_register_duplicate_user()
- test_login_valid_credentials()
- test_login_invalid_credentials()
- test_token_refresh()
- test_token_revocation()
- test_unauthorized_access()
- test_expired_token()
```

**C. Тесты rate limiting:**
```python
# tests/api/test_rate_limiting.py
- test_rate_limit_enforcement()
- test_rate_limit_reset()
- test_rate_limit_different_users()
- test_admin_higher_rate_limit()
```

**D. Тесты служебных эндпоинтов:**
```python
# tests/api/test_service_endpoints.py
- test_health_check()
- test_readiness_check()
- test_metrics_endpoint()
- test_metrics_format()
```

#### 5.2.4. Performance Tests (Тесты производительности)

**A. Load Testing (Нагрузочное тестирование):**
```python
# tests/performance/test_load.py
- test_concurrent_requests() # 100 одновременных запросов
- test_sustained_load() # устойчивая нагрузка 50 RPS в течение 5 минут
- test_response_time_under_load()
- test_database_performance_under_load()
- test_prediction_log_write_performance()
- test_connection_pool_under_load()
```

**B. Stress Testing (Стресс-тестирование):**
```python
# tests/performance/test_stress.py
- test_maximum_throughput()
- test_graceful_degradation()
- test_recovery_after_overload()
- test_database_connection_exhaustion()
- test_prediction_log_table_growth()
```

**C. Spike Testing (Пиковые нагрузки):**
```python
# tests/performance/test_spike.py
- test_sudden_traffic_spike()
- test_rate_limiter_under_spike()
- test_database_spike_handling()
```

**D. Database Performance Tests:**
```python
# tests/performance/test_database_performance.py
- test_prediction_log_query_performance() # запросы к истории
- test_prediction_log_insert_batch_performance() # батчевые вставки
- test_index_effectiveness() # эффективность индексов
- test_partition_query_performance() # запросы к партициям
- test_large_dataset_query() # работа с большими объемами
- test_jsonb_query_performance() # производительность JSONB запросов
- test_concurrent_reads_writes() # одновременные чтение и запись
```

#### 5.2.5. Security Tests (Тесты безопасности)

```python
# tests/security/test_security.py
- test_sql_injection_prevention()
- test_xss_prevention()
- test_unauthorized_endpoint_access()
- test_token_tampering_detection()
- test_brute_force_protection()
- test_password_strength_validation()
- test_sensitive_data_not_logged()
```

#### 5.2.6. Error Handling Tests (Тесты обработки ошибок)

```python
# tests/error_handling/test_errors.py
- test_database_connection_failure()
- test_model_loading_failure()
- test_invalid_input_handling()
- test_timeout_handling()
- test_memory_overflow_protection()
- test_error_response_format()
```

### 5.3. Тестовое окружение

#### 5.3.1. Test Fixtures
- Фикстура с тестовой БД (PostgreSQL in Docker или SQLite in-memory)
- Фикстура с mock-моделью для быстрых тестов
- Фикстура с тестовыми пользователями
- Фикстура с тестовыми данными для классификации

#### 5.3.2. Mocking
- Mock внешних HTTP-запросов (для URL-классификации)
- Mock модели ML (для изоляции тестов сервиса от модели)
- Mock Prometheus и ELK для тестирования интеграций

#### 5.3.3. Test Data
- Набор тестовых текстов для различных категорий
- Набор некорректных входных данных
- Набор граничных случаев (пустой текст, очень длинный текст, спецсимволы)

### 5.4. CI/CD Integration

#### 5.4.1. Pre-commit проверки
- Линтинг (flake8, black, mypy)
- Unit tests
- Security checks (bandit)

#### 5.4.2. Pipeline этапы
1. **Lint & Format:** Проверка кода
2. **Unit Tests:** Быстрые тесты (< 2 мин)
3. **Integration Tests:** Тесты с БД и внешними зависимостями (< 5 мин)
4. **API Tests:** E2E тесты (< 10 мин)
5. **Security Scan:** Проверка безопасности
6. **Performance Tests:** Базовые тесты производительности (опционально)
7. **Build Docker Image**
8. **Deploy to Staging**
9. **Smoke Tests на Staging**
10. **Deploy to Production** (manual approval)

### 5.5. Coverage Requirements
- Overall code coverage: >= 80%
- Critical paths coverage: >= 95%
- Auth module coverage: >= 90%

---

## 6. Технологический стек

### 6.1. Core Framework
- **FastAPI 0.104+:** Современный асинхронный фреймворк
  - Автоматическая валидация с Pydantic
  - Встроенная OpenAPI документация
  - Высокая производительность
  - Нативная поддержка async/await

### 6.2. База данных
- **PostgreSQL 15+:** Основная СУБД
  - Хранение пользователей и метаданных
  - Журнал классификаций (опционально)
  - Connection pooling
  - Миграции через Alembic

### 6.3. ORM и валидация
- **SQLAlchemy 2.0+:** ORM для работы с PostgreSQL
- **Alembic:** Управление миграциями БД
- **Pydantic v2:** Валидация данных и сериализация

### 6.4. Авторизация и безопасность
- **python-jose:** JWT токены
- **passlib + bcrypt:** Хэширование паролей
- **python-multipart:** Обработка form data
- **slowapi:** Rate limiting middleware

### 6.5. Логирование (ELK Stack)
- **Elasticsearch 8.x:** Хранилище логов
- **Logstash 8.x:** Обработка и агрегация логов
- **Kibana 8.x:** Визуализация и анализ
- **python-logstash-async:** Асинхронная отправка логов

### 6.6. Метрики и мониторинг
- **Prometheus:** Сбор метрик
- **Grafana 10+:** Визуализация метрик и дашборды
- **prometheus-fastapi-instrumentator:** Интеграция FastAPI с Prometheus
- **psutil:** Системные метрики

### 6.7. ML Infrastructure
- **TensorFlow 2.7+:** Фреймворк для модели
- **NumPy, Pandas:** Обработка данных
- **BeautifulSoup4:** Парсинг HTML для URL-классификации
- **requests:** HTTP-клиент для загрузки статей

### 6.8. Тестирование
- **pytest:** Основной фреймворк для тестирования
- **pytest-asyncio:** Тестирование асинхронного кода
- **pytest-cov:** Измерение покрытия кода
- **httpx:** Асинхронный HTTP-клиент для тестов API
- **faker:** Генерация тестовых данных
- **locust** или **k6:** Performance/load testing

### 6.9. Development Tools
- **black:** Форматирование кода
- **flake8:** Линтинг
- **mypy:** Статическая типизация
- **isort:** Сортировка импортов
- **pre-commit:** Автоматизация проверок

### 6.10. Контейнеризация и оркестрация
- **Docker:** Контейнеризация приложения
- **Docker Compose:** Локальная разработка и тестирование
- **Multi-stage builds:** Оптимизация размера образа

### 6.11. Дополнительные инструменты
- **gunicorn + uvicorn:** Production ASGI-сервер
- **redis** (опционально): Кэширование и rate limiting
- **nginx** (опционально): Reverse proxy и load balancing

---

## 7. Подход к контрактам и абстракциям

### 7.1. Protocol-based контракты вместо ABC интерфейсов

В проекте используется современный подход с **Protocol** (PEP 544) вместо традиционных ABC интерфейсов:

**Ключевые преимущества:**
- ✅ **Структурная типизация** - не требует явного наследования
- ✅ **Гибкость** - любой класс с нужными методами удовлетворяет контракту
- ✅ **Pythonic** - соответствует философии Python (duck typing + type hints)
- ✅ **Базовые классы** - общая логика в базовых классах, а не дублируется
- ✅ **Легко тестируется** - проще создавать моки и fakes

**Паттерн:**
```python
# 1. Protocol (contracts/) - определяет контракт
from typing import Protocol

class UserRepositoryContract(Protocol):
    async def get_by_id(self, id: UUID): ...
    async def create(self, data: dict): ...

# 2. BaseClass (base/) - предоставляет общую логику
class BaseRepository:
    async def create(self, data: dict):
        # Общая реализация для всех репозиториев
        ...

# 3. ConcreteClass - наследует базовый класс
class UserRepository(BaseRepository):
    # Наследует create() из BaseRepository
    # Добавляет специфичные методы
    async def get_by_email(self, email: str):
        ...

# UserRepository автоматически удовлетворяет UserRepositoryContract!
```

### 7.2. Структура контрактов в проекте

```
app/core/domain/
├── entities/          # Pydantic модели (доменные сущности)
├── contracts/         # Protocol контракты (вместо interfaces/)
│   ├── repositories.py    # Контракты репозиториев
│   ├── services.py        # Контракты сервисов
│   └── ml_predictor.py    # Контракт ML предиктора
└── base/              # Базовые классы с общей логикой
    ├── base_repository.py # CRUD операции
    ├── base_service.py    # Общая логика сервисов
    └── base_entity.py     # Базовая сущность (если нужна)
```

### 7.3. Детальная документация

Полная документация по контрактам доступна в директории [`docs/contracts/`](./contracts/):

- **[README.md](./contracts/README.md)** - обзор и быстрый старт
- **[protocol_based_contracts.md](./contracts/protocol_based_contracts.md)** - детальное сравнение Protocol vs ABC
- **[base_classes.md](./contracts/base_classes.md)** - базовые классы с общей логикой
- **[implementation_examples.md](./contracts/implementation_examples.md)** - практические примеры реализации

---

## 8. Структура проекта

Проект организован по принципам **Onion Architecture** с четким разделением на слои.

```
python-ml-service/
├── app/                              # Основной код приложения (подробно)
│   ├── __init__.py
│   ├── main.py                       # FastAPI application entry point
│   │
│   ├── core/                         # CORE/DOMAIN LAYER (внутренний слой)
│   │   ├── __init__.py
│   │   │
│   │   ├── domain/                   # Доменные модели и контракты
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── entities/             # Доменные сущности (Pydantic models)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py           # UserEntity
│   │   │   │   ├── api_key.py        # ApiKeyEntity
│   │   │   │   ├── prediction.py     # PredictionEntity
│   │   │   │   └── session.py        # UserSessionEntity
│   │   │   │
│   │   │   ├── contracts/            # Protocol-based контракты
│   │   │   │   ├── __init__.py
│   │   │   │   ├── repositories.py   # Repository contracts (Protocol)
│   │   │   │   │   # UserRepositoryContract, ApiKeyRepositoryContract,
│   │   │   │   │   # PredictionRepositoryContract, etc.
│   │   │   │   ├── services.py       # Service contracts (Protocol)
│   │   │   │   └── ml_predictor.py  # ML Predictor contract (Protocol)
│   │   │   │
│   │   │   └── base/                 # Базовые классы с общей логикой
│   │   │       ├── __init__.py
│   │   │       ├── base_repository.py    # Базовый репозиторий с CRUD
│   │   │       └── base_entity.py        # Базовая сущность (если нужна)
│   │   │
│   │   ├── config/                   # Конфигурация приложения
│   │   │   ├── __init__.py
│   │   │   ├── settings.py           # Pydantic Settings (env vars)
│   │   │   ├── logging_config.py    # Структурированное логирование
│   │   │   └── security_config.py   # JWT, хэширование паролей
│   │   │
│   │   ├── exceptions/               # Кастомные исключения
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Базовые исключения
│   │   │   ├── auth_exceptions.py  # Исключения авторизации
│   │   │   ├── database_exceptions.py  # Исключения БД
│   │   │   └── ml_exceptions.py     # Исключения ML модели
│   │   │
│   │   └── utils/                    # Общие утилиты
│   │       ├── __init__.py
│   │       ├── text_processing.py   # Обработка текста
│   │       ├── validators.py        # Валидаторы
│   │       └── hashing.py           # Хэширование (SHA256, etc)
│   │
│   ├── infrastructure/                # INFRASTRUCTURE LAYER
│   │   ├── __init__.py
│   │   │
│   │   ├── database/                 # ВСЁ, что связано с БД
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── models/               # ORM модели (SQLAlchemy)
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py          # Базовая ORM модель
│   │   │   │   ├── user.py          # UserModel
│   │   │   │   ├── api_key.py       # ApiKeyModel
│   │   │   │   ├── prediction_log.py    # PredictionLogModel
│   │   │   │   ├── user_session.py  # UserSessionModel
│   │   │   │   └── audit_log.py     # AuditLogModel
│   │   │   │
│   │   │   ├── repositories/         # Реализации репозиториев
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base_repository.py   # Базовый репозиторий (наследует core/base)
│   │   │   │   ├── user_repository.py   # UserRepository
│   │   │   │   ├── api_key_repository.py    # ApiKeyRepository
│   │   │   │   ├── prediction_repository.py # PredictionRepository
│   │   │   │   ├── session_repository.py   # SessionRepository
│   │   │   │   └── audit_repository.py     # AuditRepository
│   │   │   │
│   │   │   ├── connection.py        # Database engine и connection
│   │   │   ├── session.py           # AsyncSession управление
│   │   │   └── migrations/          # Alembic миграции (симлинк на /alembic)
│   │   │
│   │   ├── ml/                       # ML Infrastructure
│   │   │   ├── __init__.py
│   │   │   ├── model_loader.py      # Загрузка модели TensorFlow
│   │   │   ├── preprocessor.py      # Препроцессинг текста
│   │   │   ├── predictor.py         # Реализация MLPredictorContract
│   │   │   └── model_cache.py        # Кэширование модели в памяти
│   │   │
│   │   └── external/                 # Внешние сервисы
│   │       ├── __init__.py
│   │       ├── url_fetcher.py       # HTTP клиент для загрузки URL
│   │       ├── elasticsearch_client.py  # Клиент для ELK
│   │       └── prometheus_client.py     # Клиент для Prometheus
│   │
│   ├── application/                  # APPLICATION LAYER (бизнес-логика)
│   │   ├── __init__.py
│   │   │
│   │   ├── services/                 # Сервисы приложения
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── classification_service.py    # Сервис классификации
│   │   │   │   # Включает ML логику: вызов predictor, препроцессинг,
│   │   │   │   # постпроцессинг, сохранение результатов
│   │   │   │
│   │   │   ├── auth_service.py              # Сервис авторизации
│   │   │   │   # Login, register, token management, API keys
│   │   │   │
│   │   │   ├── user_service.py              # Сервис управления пользователями
│   │   │   │   # CRUD операции через UserRepository
│   │   │   │
│   │   │   ├── prediction_history_service.py    # Сервис истории предсказаний
│   │   │   │   # Получение истории, статистики пользователя
│   │   │   │
│   │   │   ├── telemetry_service.py         # Сервис телеметрии
│   │   │   │   # Сбор метрик, отправка в Prometheus
│   │   │   │   # Включает middleware логику для метрик
│   │   │   │
│   │   │   └── logging_service.py           # Сервис логирования
│   │   │       # Структурированное логирование, отправка в ELK
│   │   │       # Включает middleware логику для логов
│   │   │
│   │   ├── dto/                      # Data Transfer Objects
│   │   │   ├── __init__.py
│   │   │   ├── classification_dto.py    # DTO для классификации
│   │   │   ├── auth_dto.py              # DTO для авторизации
│   │   │   └── user_dto.py               # DTO для пользователей
│   │   │
│   │   └── use_cases/                # Use Cases (опционально)
│   │       ├── __init__.py
│   │       ├── classify_text_use_case.py   # Use case: классификация текста
│   │       ├── classify_url_use_case.py    # Use case: классификация URL
│   │       └── get_user_stats_use_case.py  # Use case: статистика пользователя
│   │
│   ├── presentation/                  # PRESENTATION LAYER (API)
│   │   ├── __init__.py
│   │   │
│   │   ├── api/                       # REST API
│   │   │   ├── __init__.py
│   │   │   │
│   │   │   ├── v1/                    # API версия 1
│   │   │   │   ├── __init__.py
│   │   │   │   ├── router.py         # Главный роутер v1
│   │   │   │   │
│   │   │   │   ├── endpoints/        # Эндпоинты
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── auth.py       # POST /auth/login, /auth/register
│   │   │   │   │   ├── classification.py   # POST /predict/text, /predict/url
│   │   │   │   │   ├── predictions.py       # GET /predictions/history, /stats
│   │   │   │   │   ├── api_keys.py          # CRUD для API ключей
│   │   │   │   │   ├── users.py             # Управление пользователями
│   │   │   │   │   ├── admin.py             # Админские эндпоинты
│   │   │   │   │   └── health.py            # GET /health, /ready, /metrics
│   │   │   │   │
│   │   │   │   └── dependencies.py   # FastAPI dependencies для v1
│   │   │   │       # get_current_user, check_api_key, rate_limiter, etc.
│   │   │   │
│   │   │   └── middleware/           # FastAPI middleware
│   │   │       ├── __init__.py
│   │   │       ├── request_logging.py    # Логирование запросов
│   │   │       ├── metrics_collector.py  # Сбор метрик
│   │   │       ├── rate_limiter.py       # Rate limiting
│   │   │       ├── error_handler.py      # Глобальный обработчик ошибок
│   │   │       └── request_id.py         # Генерация request_id
│   │   │
│   │   └── schemas/                   # Pydantic schemas (request/response)
│   │       ├── __init__.py
│   │       ├── auth_schemas.py       # Login, Register, Token schemas
│   │       ├── classification_schemas.py  # ClassifyRequest, ClassifyResponse
│   │       ├── prediction_schemas.py     # PredictionHistory, Stats schemas
│   │       ├── user_schemas.py           # User, UserCreate, UserUpdate
│   │       ├── api_key_schemas.py        # ApiKey, ApiKeyCreate schemas
│   │       └── common_schemas.py         # Общие схемы (Pagination, etc)
│   │
│   └── containers/                    # DEPENDENCY INJECTION CONTAINERS
│       ├── __init__.py
│       ├── core_container.py         # Конфигурация, логирование, security
│       │   # Providers: Settings, Logger, PasswordHasher, JWTManager
│       │
│       ├── infrastructure_container.py   # БД, ML, внешние сервисы
│       │   # Providers: DatabaseEngine, SessionFactory, Repositories,
│       │   #           MLPredictor, URLFetcher
│       │
│       ├── service_container.py       # Бизнес-сервисы
│       │   # Providers: ClassificationService, AuthService, UserService
│       │   #           TelemetryService, LoggingService
│       │
│       └── application_container.py   # Главный контейнер
│           # Объединяет все контейнеры, создаёт FastAPI app
│
├── tests/                             # Tests
├── alembic/                           # Database migrations
├── monitoring/                        # Monitoring configuration
├── static/                            # Static files (ML model)
├── docs/                              # Documentation
├── scripts/                           # Utility scripts
├── .github/                           # GitHub Actions (CI/CD)
├── docker/                            # Docker files
├── docker-compose.yml
├── docker-compose.prod.yml
├── requirements.txt
├── requirements-dev.txt
├── requirements-test.txt
├── alembic.ini
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

### 8.1. Описание слоёв архитектуры

#### Core/Domain Layer (`app/core/`)
**Внутренний слой** - не зависит от других слоёв:
- `domain/entities/` - Доменные сущности (Pydantic модели)
- `domain/contracts/` - Protocol-based контракты
- `domain/base/` - Базовые классы с общей логикой
- `config/` - Конфигурация приложения
- `exceptions/` - Кастомные исключения
- `utils/` - Общие утилиты

#### Infrastructure Layer (`app/infrastructure/`)
**Реализация технических деталей** - зависит только от Core:
- `database/` - ВСЁ для БД:
  - `models/` - ORM модели (SQLAlchemy)
  - `repositories/` - Реализации репозиториев
  - `connection.py`, `session.py` - Управление соединениями
- `ml/` - ML инфраструктура (загрузка модели, предиктор)
- `external/` - Внешние сервисы (HTTP клиенты, API)

#### Application Layer (`app/application/`)
**Бизнес-логика** - зависит от Core и Infrastructure:
- `services/` - Все сервисы приложения:
  - `classification_service.py` - Классификация (включает ML логику)
  - `auth_service.py` - Авторизация
  - `user_service.py` - Управление пользователями
  - `prediction_history_service.py` - История предсказаний
  - `telemetry_service.py` - Телеметрия (метрики)
  - `logging_service.py` - Логирование (ELK)
- `dto/` - Data Transfer Objects
- `use_cases/` - Use Cases (опционально)

#### Presentation Layer (`app/presentation/`)
**HTTP API** - зависит от Application:
- `api/v1/endpoints/` - REST эндпоинты
- `api/middleware/` - FastAPI middleware
- `schemas/` - Pydantic schemas для request/response

#### Containers (`app/containers/`)
**Dependency Injection** - объединяет все слои:
- `core_container.py` - Core зависимости
- `infrastructure_container.py` - Infrastructure зависимости
- `service_container.py` - Application сервисы
- `application_container.py` - Главный контейнер

---

## 9. Этапы реализации

### Этап 1: Основа (Foundation)
- [ ] Миграция с Flask на FastAPI
- [ ] Настройка структуры проекта
- [ ] Базовая конфигурация
- [ ] Докеризация

### Этап 2: База данных
- [ ] Настройка PostgreSQL
- [ ] SQLAlchemy модели
- [ ] Alembic миграции
- [ ] Connection pooling

### Этап 3: Авторизация
- [ ] JWT аутентификация
- [ ] Модель пользователей
- [ ] Эндпоинты auth
- [ ] Rate limiting
- [ ] Middleware для проверки токенов

### Этап 4: ML Integration
- [ ] Рефакторинг загрузки модели
- [ ] Асинхронный inference
- [ ] Оптимизация производительности
- [ ] Обработка ошибок

### Этап 5: Логирование (ELK)
- [ ] Настройка Elasticsearch
- [ ] Настройка Logstash
- [ ] Настройка Kibana
- [ ] Структурированное логирование
- [ ] Интеграция с приложением

### Этап 6: Метрики (Prometheus + Grafana)
- [ ] Настройка Prometheus
- [ ] Экспорт метрик из приложения
- [ ] Настройка Grafana
- [ ] Создание дашбордов
- [ ] Настройка алертов

### Этап 7: Тестирование
- [ ] Unit tests
- [ ] Integration tests
- [ ] API tests
- [ ] Performance tests
- [ ] CI/CD pipeline

### Этап 8: Документация
- [ ] API документация (OpenAPI)
- [ ] Deployment guide
- [ ] Development guide
- [ ] Architecture documentation

### Этап 9: Оптимизация и Production-ready
- [ ] Performance tuning
- [ ] Security hardening
- [ ] Load balancing
- [ ] Backup strategy
- [ ] Disaster recovery plan

---

## 10. Метрики успеха

### 9.1. Технические метрики
- Availability: 99.5%+
- Response time p95: < 500ms
- Error rate: < 0.1%
- Test coverage: 80%+
- Zero critical security vulnerabilities

### 9.2. Качественные метрики
- Полная документация API
- Рабочие дашборды в Grafana
- Настроенный алертинг
- Автоматизированный CI/CD
- Воспроизводимые развертывания

---

## 11. Риски и ограничения

### 10.1. Технические риски
- **Производительность модели:** Большая модель (120M параметров) может быть медленной
  - *Митигация:* Кэширование, батчинг, оптимизация модели
  
- **Масштабируемость:** Модель в памяти может ограничить горизонтальное масштабирование
  - *Митигация:* Отдельный model-serving слой, TensorFlow Serving

- **Зависимость от внешних ресурсов:** URL-классификация зависит от доступности сайтов
  - *Митигация:* Таймауты, retry logic, graceful degradation

### 10.2. Операционные риски
- **Сложность инфраструктуры:** ELK + Prometheus + Grafana требуют ресурсов
  - *Митигация:* Начать с минимальной конфигурации, постепенно расширять

- **Стоимость хранения логов:** Elasticsearch может потреблять много места
  - *Митигация:* Политики ротации, индексы по датам, архивирование

### 10.3. Ограничения
- Сервис не включает переобучение модели (только inference)
- Поддержка только русскоязычных текстов
- Фиксированный набор категорий (10 категорий)

---

## 12. Дальнейшее развитие (Future Roadmap)

### 11.1. Краткосрочные улучшения (1-3 месяца)
- [ ] Redis для кэширования и rate limiting
- [ ] Batch prediction API
- [ ] Webhooks для асинхронных уведомлений
- [ ] Admin dashboard (UI)

### 11.2. Среднесрочные улучшения (3-6 месяцев)
- [ ] Model versioning и A/B тестирование
- [ ] Feedback loop (сбор обратной связи о качестве)
- [ ] Multi-model support
- [ ] Kubernetes deployment

### 11.3. Долгосрочные улучшения (6+ месяцев)
- [ ] AutoML pipeline для переобучения
- [ ] Multi-language support
- [ ] Real-time streaming classification
- [ ] GraphQL API

---

## 13. Заключение

Данная постановка задачи описывает трансформацию прототипа ML-сервиса в production-ready решение корпоративного уровня. Проект фокусируется на:

1. ✅ **Надежности:** через мониторинг, логирование и алертинг
2. ✅ **Безопасности:** через JWT авторизацию и rate limiting
3. ✅ **Наблюдаемости:** через ELK и Prometheus + Grafana
4. ✅ **Качестве:** через комплексное тестирование
5. ✅ **Масштабируемости:** через асинхронную архитектуру на FastAPI

Результатом будет полнофункциональный backend сервис, готовый к использованию в реальных условиях и соответствующий современным стандартам разработки enterprise-решений.

