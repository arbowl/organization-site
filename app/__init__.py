"""Create App"""

from os import getenv
from typing import Optional

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

from app.utils import md


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


def create_app(config_name: Optional[str] = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    config_name = config_name or getenv("FLASK_CONFIG", "development")
    app.config.from_object(f"config.{config_name.capitalize()}Config")
    app.config.from_pyfile("config.py", silent=True)
    app.jinja_env.filters["md"] = md
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    from .routes.auth import auth_bp
    from .routes.blog import blog_bp
    from .routes.pages import pages_bp
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(blog_bp)
    app.register_blueprint(pages_bp)
    with app.app_context():
        db.create_all()
    return app

from .models import User


@login_manager.user_loader
def load_user(user_id: int) -> None:
    return User.query.get(int(user_id))
