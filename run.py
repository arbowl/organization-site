"""Run"""

from datetime import datetime, timezone, timedelta
from os import getenv

from flask import redirect, url_for, send_from_directory, request, session
from flask_login import logout_user, current_user

from app import create_app, db
from app.forms import SearchForm
from app.models import Notification, Visit

config_name = getenv("FLASK_CONFIG", "development")
app = create_app(config_name)
endpoints_to_ignore = [
    "static",
    "favicon",
    "analytics.dashboard",
]

@app.route('/robots.txt')
def robots():
    return send_from_directory(app.static_folder, 'robots.txt')


@app.before_request
def make_session_permanent():
    session.permanent = True
    app.permanent_session_lifetime = timedelta(minutes=30)


@app.before_request
def check_user_timeout():
    if current_user.is_authenticated and session.get('last_seen'):
        if datetime.now(timezone.utc) - session['last_seen'] > timedelta(minutes=30):
            logout_user()
            return redirect(url_for('auth.login'))
    session['last_seen'] = datetime.now(timezone.utc)


@app.before_request
def log_visit():
    if request.endpoint in endpoints_to_ignore or request.path.startswith("/admin"):
        return
    xff = request.headers.get("X-Forwarded-For", request.remote_addr)
    ip_address = xff.split(",")[0].strip()
    visit = Visit(
        path = request.path,
        referrer = request.referrer,
        utm_source = request.args.get("utm_source"),
        utm_medium = request.args.get("utm_medium"),
        utm_campaign = request.args.get("utm_campaign"),
        user_id = getattr(current_user, "id", None),
        ip_address = ip_address
    )
    db.session.add(visit)


@app.teardown_request
def commit_visit(exc):
    if exc is None:
        try:
            db.session.commit()
        except:
            db.session.rollback()


@app.context_processor
def inject_search_form():
    return {"search_form": SearchForm(meta={"csrf": False})}


@app.context_processor
def inject_unread_count():
    if current_user.is_authenticated:
        count = Notification.query.filter_by(recipient_id=current_user.id, read_at=None).count()
    else:
        count = 0
    return {"unread_count": count}


if __name__ == "__main__":
    host = getenv("HOST", "0.0.0.0")
    port = int(getenv("PORT", "5000"))
    debug_env = getenv("FLASK_DEBUG", "true").lower()
    debug = debug_env in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)
