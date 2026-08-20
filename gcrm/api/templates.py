"""Single Jinja2Templates instance shared by every router and the web app, so
the template directory and custom filters are configured in exactly one place."""
import json
from pathlib import Path
from urllib.parse import quote_plus

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from gcrm.api.web_links import browsable_url
from gcrm.i18n import DEFAULT_LANGUAGE, translate

UI_DIR = Path(__file__).parent.parent / "ui"


def tojson_filter(value) -> Markup:
    """Serialize a value for embedding in a <script> block. Escapes the
    characters that would otherwise let embedded data break out of the tag
    (</script>, HTML comments) — plain json.dumps does not."""
    return Markup(
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


class AppTemplates(Jinja2Templates):
    """Preserve the application's established template call shape across Starlette versions."""

    def TemplateResponse(self, name: str, context: dict, **kwargs):
        """Render a template using the request stored in the route context.

        Also injects `t(key, **params)` — the i18n lookup for the current
        session's language — so no route handler needs to remember to pass
        it. Session-less contexts (rare — HTMX partials sometimes render
        outside a request-scoped session) fall back to English.
        """
        request = context["request"]
        language = DEFAULT_LANGUAGE
        try:
            language = request.session.get("ui_language", DEFAULT_LANGUAGE)
        except AssertionError:
            pass  # no SessionMiddleware in this context (shouldn't happen in prod)
        context.setdefault("t", lambda key, **params: translate(key, language, **params))
        return super().TemplateResponse(request, name, context, **kwargs)


templates = AppTemplates(directory=str(UI_DIR / "templates"))
templates.env.filters["urlenc"] = quote_plus
templates.env.filters["browsable_url"] = browsable_url
templates.env.filters["tojson"] = tojson_filter
