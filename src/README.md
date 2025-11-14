# FastAPI ML Service

Это FastAPI версия ML сервиса для предсказаний на основе текста и URL.

## Установка зависимостей

```bash
pip install -r ../requirements.txt
```

## Запуск приложения

### Способ 1: Через run.py

```bash
python run.py
```

### Способ 2: Через uvicorn напрямую

```bash
uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload
```

### Способ 3: Из корня проекта

```bash
cd /home/pavel/PycharmProjects/python-ml-service
python -m src.run
```

## API Endpoints

### GET /
Корневой endpoint для проверки работы сервиса

### GET /health
Health check endpoint

### POST /predictByUrl
Классификация текста по URL

**Параметры:**
- `analyseURL` (form-data): URL страницы для анализа

**Пример запроса:**
```bash
curl -X POST "http://localhost:8000/predictByUrl" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "analyseURL=https://example.com/article"
```

### POST /predictByText
Классификация текста

**Параметры:**
- `analyseTEXT` (form-data): Текст для анализа

**Пример запроса:**
```bash
curl -X POST "http://localhost:8000/predictByText" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "analyseTEXT=Ваш текст для анализа"
```

## Документация API

После запуска приложения автоматически доступна интерактивная документация:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Структура проекта

```
src/
├── __init__.py
├── app.py              # Основное FastAPI приложение
├── config.py           # Конфигурация приложения
├── run.py              # Скрипт для запуска
├── models/
│   ├── __init__.py
│   └── predict/
│       ├── __init__.py         # Загрузка моделей
│       └── model_predict.py    # Функции предсказания
└── README.md           # Этот файл
```

## Отличия от Flask версии

1. **Автоматическая документация**: FastAPI автоматически генерирует OpenAPI документацию
2. **Валидация данных**: Встроенная валидация с помощью Pydantic
3. **Async поддержка**: Возможность использовать асинхронные функции
4. **Типизация**: Улучшенная типизация параметров и ответов
5. **Производительность**: FastAPI работает быстрее благодаря использованию Starlette и Pydantic

