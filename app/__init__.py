"""Create App"""

from os import getenv
from typing import Optional

from flask import Flask, redirect, url_for, request
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect

from app.utils import md


db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"


class MyIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login", next=request.url))


class UserAdmin(ModelView):
    column_list = ["username", "email", "role"]
    form_choices = {
        "role": [
            ("user", "User"),
            ("contributor", "Contributor"),
            ("moderator", "Moderator"),
            ("admin", "Admin"),
        ]
    }

    form_excluded_columns = ['password_hash']


def create_app(config_name: Optional[str] = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    admin = Admin(app, name="Site Admin", index_view=MyIndexView())
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
    from app.models import User, Post, Comment
    admin.add_view(UserAdmin(User, db.session))
    admin.add_view(UserAdmin(Post, db.session))
    admin.add_view(UserAdmin(Comment, db.session))
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(blog_bp)
    app.register_blueprint(pages_bp)
    with app.app_context():
        db.create_all()
    CSRFProtect(app)
    return app

from .models import User


@login_manager.user_loader
def load_user(user_id: int) -> None:
    return User.query.get(int(user_id))
