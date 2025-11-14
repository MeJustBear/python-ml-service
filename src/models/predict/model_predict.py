import itertools
import requests
from bs4 import BeautifulSoup
import numpy as np

from src.models.predict import modelE, tokenizer, encoder


def predict_by_url(vgm_url: str, model=None, tokenizer_arg=None, encoder_arg=None):
    """
    Предсказание по URL страницы
    
    Args:
        vgm_url: URL страницы для анализа
        model: Модель для предсказания
        tokenizer_arg: Токенизатор для обработки текста
        encoder_arg: Энкодер для классов
        
    Returns:
        dict: Словарь с классами и вероятностями
    """
    # Используем глобальные значения, если не переданы параметры
    if model is None:
        model = modelE
    if tokenizer_arg is None:
        tokenizer_arg = tokenizer
    if encoder_arg is None:
        encoder_arg = encoder
    
    # Проверка, что модели загружены
    if model is None or tokenizer_arg is None or encoder_arg is None:
        raise ValueError("Модель, токенизатор или энкодер не загружены")
    
    html_text = requests.get(vgm_url).text
    
    soup = BeautifulSoup(html_text, 'html.parser')
    
    page_head = soup.find("h1", {"class": "article__heading"})
    page_summary = soup.find("div", {"class": "article__summary"})
    
    page_article = soup.find("div", {"class": "article__text"})
    if not (page_article is None):
        page_article = page_article.find_all("p")
    
    lines = [page_head.text, page_summary.text]
    if not (page_article is None):
        for par in page_article:
            lines.append(par.text)
    
    layers = predict_text(lines, model, tokenizer_arg, encoder_arg)
    
    return layers


def predict_text(lines, model=None, tokenizer_arg=None, encoder_arg=None):
    """
    Предсказание по тексту
    
    Args:
        lines: Список строк текста для анализа
        model: Модель для предсказания
        tokenizer_arg: Токенизатор для обработки текста
        encoder_arg: Энкодер для классов
        
    Returns:
        dict: Результаты предсказания
    """
    # Используем глобальные значения, если не переданы параметры
    if model is None:
        model = modelE
    if tokenizer_arg is None:
        tokenizer_arg = tokenizer
    if encoder_arg is None:
        encoder_arg = encoder
    
    # Проверка, что модели загружены
    if model is None or tokenizer_arg is None or encoder_arg is None:
        raise ValueError("Модель, токенизатор или энкодер не загружены")
    
    linesSeq = np.array(tokenizer_arg.texts_to_sequences(lines))
    linesSeq = np.array(list(itertools.chain.from_iterable(linesSeq)))
    
    maxlen = model.layers[0].input_shape[1]
    nClasses = model.layers[-1].output_shape[1]
    c = int(np.ceil(len(linesSeq) / maxlen))
    linesSeq = np.asarray(linesSeq, dtype=np.int32)
    
    linesSeq = np.resize(linesSeq, (c, int(maxlen)))
    
    layers = model.predict(linesSeq)
    layers = np.reshape(layers, (c, nClasses))
    layers = np.sum(layers, axis=0) / float(c)
    
    # Для predict_text возвращаем результат в виде словаря
    probabilities = [[], []]
    for i in range(len(layers)):
        probabilities[0].append(encoder_arg.classes_[i])
        probabilities[1].append(float(np.clip(np.round(layers[i] * 100.0), 0, 100)))
    
    return dict(zip(probabilities[0], probabilities[1]))

