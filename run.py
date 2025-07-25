"""Run"""

from os import getenv

from flask_login import current_user

from app import create_app
from app.forms import SearchForm
from app.models import Notification

config_name = getenv("FLASK_CONFIG", "development")
app = create_app(config_name)


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
