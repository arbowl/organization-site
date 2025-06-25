from os import path, environ

basedir = path.abspath(path.dirname(__file__))

class Config:
    SECRET_KEY = environ.get("SECRET_KEY") or "12345"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = (
        environ.get("DEV_DATABASE_URL") or
        "sqlite:///" + path.join(basedir, "instance", "app.db")
    )


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = (
        environ.get("TEST_DATABASE_URI") or
        "sqlite:///" + path.join(basedir, "instance", "test.db")
    )


class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = (
        environ.get("DATABASE_URL") or
        "sqlite:///" + path.join(basedir, "instance", "app.db")
    )
    DEBUG = False
