"""Create App"""

from datetime import datetime, timezone
from os import getenv
from re import compile as re_compile, IGNORECASE, MULTILINE
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from flask import (
    Flask,
    redirect,
    make_response,
    url_for,
    render_template,
    abort,
    request,
)
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_apscheduler import APScheduler
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, logout_user, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from markupsafe import Markup

from app.utils import md


db: SQLAlchemy = SQLAlchemy()
scheduler = APScheduler()
app = Flask(__name__, instance_relative_config=True)
limiter = Limiter(key_func=get_remote_address, default_limits=[])
limiter.init_app(app)
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
_MD_INLINE_IMG = re_compile(
    r'!\[[^\]]*\]\(\s*<?([^)\s>]+)[^)]*?>?\s*\)', IGNORECASE
)
_MD_REF_IMG = re_compile(
    r'!\[[^\]]*\]\[([^\]]+)\]', IGNORECASE
)
_MD_REF_DEF = re_compile(
    r'^\s*\[([^\]]+)\]:\s*<?([^\s>]+)>?(?:\s+["\'(].*?[)"\'])?\s*$',
    IGNORECASE | MULTILINE
)


@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("429.html"), 429


@app.errorhandler(403)
def not_found(error):
    return render_template("403.html"), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    return render_template("csrf_error.html"), 400


@app.before_request
def block_banned():
    if current_user.is_authenticated and current_user.is_banned():
        logout_user()
        abort(403)


@app.route("/sitemap.xml")
def sitemap():
    from app.models import Post

    pages = []
    now = datetime.now().date().isoformat()
    host = getenv("HOST_DOMAIN")
    if host:
        pages.append([f"https://{host}/", now, "daily", 0.8])
    for post in Post.query.all():
        url = url_for("blog.view_post", slug=post.slug, _external=True)
        pages.append([url, post.timestamp.date().isoformat(), "weekly", 0.8])
    sitemap_xml = render_template("sitemap.xml", pages=pages)
    response = make_response(sitemap_xml)
    response.headers["Content-Type"] = "application/xml"
    return response


def first_img_abs(text: str | None) -> str | None:
    """
    Return the absolute URL of the first image found in HTML or Markdown.

    Rules:
    - Prefer the first <img src="..."> if present.
    - Otherwise search Markdown: inline ![alt](url "title") or reference-style ![alt][id] with [id]: url lines.
    - Skip data: URIs.
    - Resolve relative URLs against flask.request.url_root (if available).
    - Return None if nothing usable.
    """
    if not text:
        return None
    try:
        soup = BeautifulSoup(text, "html.parser")
        img = soup.find("img", src=True)
        if img:
            src = (img.get("src") or "").strip()
            if src and not src.lower().startswith("data:"):
                try:
                    from flask import request
                    base = request.url_root
                except Exception:
                    base = ""
                return urljoin(base, src)
    except Exception:
        pass
    ref_map: dict[str, str] = {}
    for m in _MD_REF_DEF.finditer(text):
        key = m.group(1).strip().lower()
        url = m.group(2).strip()
        if url and not url.lower().startswith("data:"):
            ref_map[key] = url
    m = _MD_INLINE_IMG.search(text)
    candidate = None
    if m:
        candidate = m.group(1).strip()
    if not candidate:
        m = _MD_REF_IMG.search(text)
        if m:
            ref_id = (m.group(1) or "").strip().lower()
            candidate = ref_map.get(ref_id)
    if not candidate or candidate.lower().startswith("data:"):
        return None
    try:
        from flask import request
        base = request.url_root
    except Exception:
        base = ""
    return urljoin(base, candidate)


class MyAdminView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin()

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("auth.login", next=request.url))


class ReportAdmin(ModelView):
    column_list = [
        "timestamp",
        "reporter.username",
        "post_id",
        "comment_id",
        "reason",
        "view",
        "remove",
        "handler",
        "status",
    ]
    column_labels = {"reporter.username": "Reporter", "view": "View"}

    def _get_handler(self):
        return str(current_user.username)

    def _get_timestamp(self):
        return str(datetime.now(timezone.utc))

    form_choices = {
        "status": [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("dismissed", "Dismissed"),
            ("actioned", "Actioned"),
        ],
    }
    form_columns = [
        "post",
        "comment",
        "reporter",
        "reason",
        "status",
    ]
    can_create = False
    can_edit = True
    can_delete = False

    def _view_link_formatter(self, context, model, name):
        return Markup(f'<a href="{model.target_url}" target="_blank">Link</a>')

    def _remove_content_formatter(self, context, model, name):
        url = ""
        if model.comment_id:
            url = url_for("blog.remove_comment", comment_id=model.comment_id)
        elif model.post_id:
            url = url_for("blog.delete_post", post_id=model.post_id)
        csrf = generate_csrf()
        return Markup(
            f"""
            <form action="{url}" method="post" style="display:inline;">
                <input type="hidden" name="csrf_token" value="{csrf}">
                <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Are you sure you want to delete this?');">Remove</button>
            </form>
        """
        )

    column_formatters = {
        "view": _view_link_formatter,
        "remove": _remove_content_formatter,
    }

    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_authority()

    def on_model_change(self, form, model, is_created):
        if not is_created:
            model.handler = current_user
            model.handled_at = datetime.now(timezone.utc)


class UserAdmin(ModelView):
    column_list = ["username", "email", "role"]
    form_choices = {
        "role": [
            ("banned", "Banned"),
            ("user", "User"),
            ("contributor", "Contributor"),
            ("moderator", "Moderator"),
            ("admin", "Admin"),
        ]
    }

    form_excluded_columns = ["password_hash"]

    def is_accessible(self):
        return current_user.is_authenticated and current_user.is_admin()


def create_app(config_name: Optional[str] = None) -> Flask:
    admin = Admin(app, name="Site Admin", index_view=MyAdminView())
    config_name = config_name or getenv("FLASK_CONFIG", "development")
    app.config.from_object(f"config.{config_name.capitalize()}Config")
    app.config.from_pyfile("config.py", silent=True)
    app.config.update(
        {
            "MAIL_SERVER": getenv("MAIL_SERVER"),
            "MAIL_PORT": int(getenv("MAIL_PORT")),
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": getenv("SMTP_USER"),
            "MAIL_DEFAULT_SENDER": getenv("SMTP_USER"),
            "MAIL_PASSWORD": getenv("SMTP_PASS"),
        }
    )
    app.config["JOBS"] = [
        {
            "id": "newsletter",
            "func": "app.tasks:send_weekly_top_post_email",
            "trigger": "cron",
            "day_of_week": "mon",
            "hour": 10,
            "minute": 0,
            "timezone": "America/New_York",
        },
        {
            "id": "bill_scraping",
            "func": "app.tasks:scrape_ma_bills",
            "trigger": "cron",
            "day_of_week": "mon",
            "hour": 2,
            "minute": 0,
            "timezone": "America/New_York",
        }
    ]
    app.jinja_env.filters["first_img_abs"] = first_img_abs
    scheduler.init_app(app)
    scheduler.start()
    mail = Mail(app)
    app.mail = mail
    app.jinja_env.filters["md"] = md
    
    # Register custom date formatting filters
    from app.filters import (
        format_date, format_date_time, format_date_short, smart_truncate
    )
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_date_time"] = format_date_time
    app.jinja_env.filters["format_date_short"] = format_date_short
    app.jinja_env.filters["smart_truncate"] = smart_truncate

    # Register utility filters
    from app.utils import render_img, postprocess_comment_html
    app.jinja_env.filters["render_img"] = render_img
    app.jinja_env.filters["postprocess_comment_html"] = postprocess_comment_html
    
    # Make unsubscribe token generation available in templates
    from .routes.account import generate_unsubscribe_token
    app.jinja_env.globals['generate_unsubscribe_token'] = generate_unsubscribe_token
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    from .routes.auth import auth_bp
    from .routes.blog import blog_bp
    from .routes.pages import pages_bp
    from .routes.social import social_bp
    from .routes.account import account_bp
    from .routes.analytics import analytics_bp
    from .routes.bills import bills_bp
    from app.models import User, Post, Comment, Report, Bill, NewsletterSubscription

    admin.add_view(UserAdmin(User, db.session))
    admin.add_view(UserAdmin(Post, db.session))
    admin.add_view(UserAdmin(Comment, db.session))
    admin.add_view(ReportAdmin(Report, db.session))
    
    # Add Bill admin view
    class BillAdmin(ModelView):
        column_list = ["bill_number", "title", "chamber", "status", "created_at", "last_scraped"]
        column_searchable_list = ["bill_number", "title"]
        column_filters = ["chamber", "status", "created_at"]
        form_excluded_columns = ["comments"]
        
        def is_accessible(self):
            return current_user.is_authenticated and current_user.is_authority()
    
    admin.add_view(BillAdmin(Bill, db.session))
    
    # Add NewsletterSubscription admin view
    class NewsletterAdmin(ModelView):
        column_list = ["email", "subscribed_at", "is_active"]
        column_searchable_list = ["email"]
        column_filters = ["is_active", "subscribed_at"]
        can_create = False
        can_edit = True
        can_delete = True
        
        def is_accessible(self):
            return current_user.is_authenticated and current_user.is_authority()
    
    admin.add_view(NewsletterAdmin(NewsletterSubscription, db.session))
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(blog_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(social_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(bills_bp)
    with app.app_context():
        db.create_all()
    CSRFProtect(app)
    return app


from .models import User


@login_manager.user_loader
def load_user(user_id: int) -> None:
    return User.query.get(int(user_id))
