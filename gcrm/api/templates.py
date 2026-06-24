"""Single Jinja2Templates instance shared by every router and the web app, so
the template directory and custom filters are configured in exactly one place."""
from pathlib import Path
from urllib.parse import quote_plus

from fastapi.templating import Jinja2Templates

UI_DIR = Path(__file__).parent.parent / "ui"
templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
templates.env.filters["urlenc"] = quote_plus
