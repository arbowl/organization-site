"""Run"""

from os import getenv

from app import create_app
from app.forms import SearchForm

config_name = getenv("FLASK_CONFIG", "development")
app = create_app(config_name)


@app.context_processor
def inject_search_form():
    return {"form": SearchForm(meta={"csrf": False})}

if __name__ == "__main__":
    host = getenv("HOST", "0.0.0.0")
    port = int(getenv("PORT", "5000"))
    debug_env = getenv("FLASK_DEBUG", "true").lower()
    debug = debug_env in ("1", "true", "yes")
    app.run(host=host, port=port, debug=debug)
