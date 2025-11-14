from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import uvicorn

from src import config
from src.models.predict import model_predict as mp

# Создание FastAPI приложения
app = FastAPI(
    title=config.ApplicationConfig.appName,
    description="ML сервис для предсказаний на основе текста и URL",
    version="1.0.0"
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене укажите конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Корневой endpoint для проверки работы сервиса"""
    return {"message": "ML Service is running", "status": "ok"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.post("/predictByUrl")
async def classify_url(analyseURL: Optional[str] = Form(None)):
    """
    Классификация текста по URL
    
    Args:
        analyseURL: URL страницы для анализа
        
    Returns:
        dict: Словарь с предсказаниями и вероятностями
    """
    if not analyseURL:
        return JSONResponse(content={}, status_code=400)
    
    try:
        values = mp.predict_by_url(analyseURL)
        return JSONResponse(content=values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке URL: {str(e)}")


@app.post("/predictByText")
async def classify_text(analyseTEXT: Optional[str] = Form(None)):
    """
    Классификация текста
    
    Args:
        analyseTEXT: Текст для анализа
        
    Returns:
        dict: Словарь с предсказаниями и вероятностями
    """
    if not analyseTEXT:
        return JSONResponse(content={}, status_code=400)
    
    try:
        # Преобразуем текст в список строк
        lines = [analyseTEXT]
        values = mp.predict_text(lines)
        return JSONResponse(content=values)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при обработке текста: {str(e)}")


if __name__ == '__main__':
    uvicorn.run(
        "app:app",
        host=config.ApplicationConfig.host,
        port=config.ApplicationConfig.port,
        reload=config.DevelopementConfig.DEBUG
    )

