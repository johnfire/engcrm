"""Single Jinja2Templates instance shared by every router and the web app, so
the template directory and custom filters are configured in exactly one place."""
import json
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote_plus

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from gcrm.activity_types import activity_type
from gcrm.api.web_links import browsable_url
from gcrm.i18n import DEFAULT_LANGUAGE, translate
from gcrm.sources import label_key

UI_DIR = Path(__file__).parent.parent / "ui"


def eur(value) -> str:
    """An amount in euros, German style: 2.400,50 € (a whole amount drops the cents)."""
    amount = Decimal(str(value or 0))
    text = f"{amount:,.0f}" if amount == amount.to_integral_value() else f"{amount:,.2f}"
    return text.replace(",", "\u2009").replace(".", ",").replace("\u2009", ".") + " €"


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
templates.env.filters["eur"] = eur
templates.env.globals["activity_type"] = activity_type
templates.env.globals["source_label_key"] = lambda source: "source." + label_key(source)

# Cache-busting query param for /static assets, so a deploy that changes CSS/JS
# doesn't sit behind a browser's stale cached copy of a URL that never changes.
# Read once per process (mtime, not content hash — Docker's COPY sets it to
# build time, which already changes on every deploy).
_style_css = UI_DIR / "static" / "style.css"
templates.env.globals["static_version"] = str(int(_style_css.stat().st_mtime)) if _style_css.exists() else "0"
