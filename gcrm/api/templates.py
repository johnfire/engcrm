"""Single Jinja2Templates instance shared by every router and the web app, so
the template directory and custom filters are configured in exactly one place."""
from pathlib import Path
from urllib.parse import quote_plus

from fastapi.templating import Jinja2Templates

UI_DIR = Path(__file__).parent.parent / "ui"


class AppTemplates(Jinja2Templates):
    """Preserve the application's established template call shape across Starlette versions."""

    def TemplateResponse(self, name: str, context: dict, **kwargs):
        """Render a template using the request stored in the route context."""
        request = context["request"]
        return super().TemplateResponse(request, name, context, **kwargs)


templates = AppTemplates(directory=str(UI_DIR / "templates"))
templates.env.filters["urlenc"] = quote_plus
