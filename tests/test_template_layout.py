"""Layout invariants that are cheap to check without a browser.

The expensive check — does any element's content spill out of its box and land
on top of the column next door — needs a real layout engine; see
scripts/layout_audit.py for that. What is worth pinning here is the structural
rule that made those spills possible in the first place, so a table added later
cannot quietly reintroduce the bug.
"""
import pathlib
import re

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "gcrm" / "ui" / "templates"

# The print sheet is a standalone A4 document with its own stylesheet — it is
# meant to be as wide as the paper, not to scroll.
EXEMPT = {"organizations_print.html"}


def _templates_with_tables():
    for path in sorted(TEMPLATES.rglob("*.html")):
        if path.name in EXEMPT:
            continue
        text = path.read_text()
        if "<table" in text:
            yield path, text


def test_every_table_lives_in_a_scroll_container():
    """A table wider than the window must scroll inside its own box. Without
    the wrapper it pushes the whole page sideways instead."""
    offenders = []
    for path, text in _templates_with_tables():
        for match in re.finditer(r"<table[^>]*>", text):
            before = text[:match.start()]
            # the wrapper is the element immediately enclosing the table
            if not re.search(r'<div class="table-scroll">\s*$', before):
                offenders.append(f"{path.relative_to(TEMPLATES)}:{before.count(chr(10)) + 1}")
    assert not offenders, (
        "table(s) not wrapped in <div class=\"table-scroll\">: " + ", ".join(offenders)
    )


def test_tables_exist_to_check():
    """Guard against the rule above passing because the glob found nothing."""
    assert len(list(_templates_with_tables())) >= 10
