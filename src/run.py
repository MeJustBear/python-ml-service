"""
Запуск FastAPI приложения
Использование: python run.py
"""
import uvicorn
from src import config

if __name__ == '__main__':
    uvicorn.run(
        "src.app:app",
        host=config.ApplicationConfig.host,
        port=config.ApplicationConfig.port,
        reload=config.DevelopementConfig.DEBUG
    )

