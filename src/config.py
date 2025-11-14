import uuid


class PathsConfig:
    path_to_train_data = "../static/train/"
    url_train_data = "https://github.com/ods-ai-ml4sg/proj_news_viz/releases/download/data/rt.csv.gz"
    path_to_model = "../static/predict/"
    model_name = "model"
    encoder_name = "encoder_classes.npy"
    tokenizer_name = "tokenizer.json"


class ApplicationConfig:
    host = '0.0.0.0'
    port = 8000
    appName = 'predictor'


class BaseConfig:
    SECRET_KEY = uuid.uuid4().hex
    FLASK_APP = ApplicationConfig.appName


class DevelopementConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
