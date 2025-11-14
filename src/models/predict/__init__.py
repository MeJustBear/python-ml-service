import json
import numpy as np
import os
import logging

from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.text import tokenizer_from_json
from sklearn.preprocessing import LabelEncoder

from src import config

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация переменных
modelE = None
tokenizer = None
encoder = None

# Загрузка модели, токенизатора и энкодера при инициализации
try:
    model_path = config.PathsConfig.path_to_model + config.PathsConfig.model_name
    if os.path.exists(model_path):
        modelE = load_model(model_path)
        logger.info(f"Модель успешно загружена из {model_path}")
    else:
        logger.warning(f"Модель не найдена по пути {model_path}")
except Exception as e:
    logger.error(f"Ошибка при загрузке модели: {e}")

try:
    tokenizer_path = config.PathsConfig.path_to_model + config.PathsConfig.tokenizer_name
    if os.path.exists(tokenizer_path):
        with open(tokenizer_path) as f:
            data = json.load(f)
            tokenizer = tokenizer_from_json(data)
        logger.info(f"Токенизатор успешно загружен из {tokenizer_path}")
    else:
        logger.warning(f"Токенизатор не найден по пути {tokenizer_path}")
except Exception as e:
    logger.error(f"Ошибка при загрузке токенизатора: {e}")

try:
    encoder_path = config.PathsConfig.path_to_model + config.PathsConfig.encoder_name
    if os.path.exists(encoder_path):
        encoder = LabelEncoder()
        encoder.classes_ = np.load(encoder_path)
        logger.info(f"Энкодер успешно загружен из {encoder_path}")
    else:
        logger.warning(f"Энкодер не найден по пути {encoder_path}")
except Exception as e:
    logger.error(f"Ошибка при загрузке энкодера: {e}")

