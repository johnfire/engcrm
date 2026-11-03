"""Two things decided on 2026-11-03: cafes, restaurants, hotels, bakeries, butchers, gas
stations and supermarkets are not AI buyers, so no research scan searches for them; and
changing a stage from a list row must not throw the page back to the top."""
import re

from gcrm.api.templates import UI_DIR, templates
from gcrm.vertical import SCAN_LEVELS

NOT_TARGETS = re.compile(
    r"caf[eé]|restaurant|gasthof|gasthaus|gaststätte|wirtshaus|hotel|pension|bistro|imbiss|"
    r"bäcker|backstube|konditor|metzger|fleischer|supermarkt|lebensmitteleinzelhandel|tankstelle|kiosk",
    re.IGNORECASE,
)


def test_no_scan_level_searches_for_businesses_that_are_not_buyers():
    offending = {
        (level, term)
        for level, info in SCAN_LEVELS.items()
        for term in [info["label"], *info["maps_terms"]]
        if NOT_TARGETS.search(term)
    }
    assert offending == set()


def _render_stage_selects(**extra):
    template = templates.env.get_template("partials/deal_stage_selects.html")
    return template.render(
        deals=[{"id": 7, "offer": "consulting", "stage": "candidate"}],
        owner_name="Acme GmbH", active_offer="consulting",
        pipeline_stages=["candidate", "not_in_pipeline"], t=lambda key: key,
        request=type("R", (), {"url": type("U", (), {"path": "/organizations/", "query": "page=3"})()})(),
        **extra,
    )


def test_the_stage_select_saves_in_the_background_with_the_plain_submit_as_fallback():
    html = _render_stage_selects()
    # No script loaded (or it failed): the select still saves, as a normal form post.
    assert "window.keepPlaceSubmit ? keepPlaceSubmit(this.form) : this.form.submit()" in html
    assert 'action="/deals/7"' in html


def test_the_page_loads_the_keep_place_script_and_it_exists():
    base = (UI_DIR / "templates" / "base.html").read_text()
    script = UI_DIR / "static" / "keep-place.js"
    assert "/static/keep-place.js" in base
    source = script.read_text()
    # It must send the form, recolour the select, and fall back to a normal submit.
    assert "fetch(form.action" in source and "badge-stage-" in source and "form.submit()" in source


def test_the_script_reads_the_form_before_disabling_the_select():
    """A disabled field is left out of FormData, so disabling first would post no stage at all
    (the server reads a blank stage as 'no change')."""
    source = (UI_DIR / "static" / "keep-place.js").read_text()
    assert source.index("new FormData(form)") < source.index("select.disabled = true")
