# Быстрый старт FastAPI приложения

## 1. Установка зависимостей

```bash
cd /home/pavel/PycharmProjects/python-ml-service
pip install -r requirements.txt
```

## 2. Запуск приложения

### Простой запуск
```bash
python -m src.run
```

### С auto-reload (для разработки)
```bash
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

### Через Docker
```bash
docker-compose -f docker-compose.fastapi.yml up --build
```

## 3. Проверка работы

Откройте браузер:
- **API Docs (Swagger)**: http://localhost:8000/docs
- **Alternative Docs (ReDoc)**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

## 4. Быстрый тест

### Тест endpoint /predictByText

```bash
curl -X POST "http://localhost:8000/predictByText" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "analyseTEXT=Пример текста для анализа"
```

### Тест endpoint /predictByUrl

```bash
curl -X POST "http://localhost:8000/predictByUrl" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "analyseURL=https://example.com/article"
```

## 5. Тестирование через Python

```python
import requests

# Тест /predictByText
response = requests.post(
    "http://localhost:8000/predictByText",
    data={"analyseTEXT": "Текст для анализа"}
)
print("predictByText:", response.json())

# Тест /predictByUrl
response = requests.post(
    "http://localhost:8000/predictByUrl",
    data={"analyseURL": "https://example.com/article"}
)
print("predictByUrl:", response.json())
```

## 6. Интерактивное тестирование

1. Откройте http://localhost:8000/docs
2. Выберите endpoint (например, `/predictByText`)
3. Нажмите "Try it out"
4. Введите данные
5. Нажмите "Execute"

## Структура ответа

Оба endpoint возвращают JSON со словарем вероятностей:

```json
{
  "класс1": 75.0,
  "класс2": 25.0,
  "класс3": 12.5
}
```

## Возможные проблемы

### Ошибка: "Модель, токенизатор или энкодер не загружены"

Убедитесь, что в директории `static/predict/` присутствуют файлы:
- `model/` - директория с моделью
- `encoder_classes.npy` - файл энкодера
- `tokenizer.json` - файл токенизатора (может отсутствовать)

### Ошибка: "ModuleNotFoundError: No module named 'fastapi'"

Установите зависимости:
```bash
pip install -r requirements.txt
```

### Порт 8000 уже занят

Измените порт в `src/config.py` или запустите с другим портом:
```bash
uvicorn src.app:app --port 8001
```

## Сравнение с Flask

| Особенность | Flask (app/) | FastAPI (src/) |
|------------|--------------|----------------|
| Запуск | `python app/run.py` | `python -m src.run` |
| Документация | Нет | Автоматическая |
| Валидация | Ручная | Автоматическая |
| Производительность | Средняя | Высокая |
| Async поддержка | Ограниченная | Полная |

## Следующие шаги

1. Изучите [MIGRATION_GUIDE.md](../MIGRATION_GUIDE.md) для полного понимания отличий
2. Протестируйте API через Swagger UI
3. Интегрируйте с вашим фронтендом
4. Настройте production окружение

## Остановка приложения

- **При запуске через Python**: `Ctrl+C`
- **При запуске через Docker**: `docker-compose -f docker-compose.fastapi.yml down`

