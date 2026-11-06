"""Read specific rendered forms for behavior-focused route assertions."""
from html.parser import HTMLParser


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.active_form = None

    def handle_starttag(self, tag, attributes):
        if tag == "form":
            self.active_form = {"attributes": dict(attributes), "selects": []}
            self.forms.append(self.active_form)
        elif tag == "select" and self.active_form is not None:
            self.active_form["selects"].append(dict(attributes))

    def handle_endtag(self, tag):
        if tag == "form":
            self.active_form = None


def read_form(html: str, action: str) -> dict:
    parser = FormParser()
    parser.feed(html)
    matches = [form for form in parser.forms if form["attributes"].get("action") == action]
    assert len(matches) == 1, f"Expected one rendered form posting to {action}"
    assert matches[0]["attributes"].get("method", "get").lower() == "post"
    return matches[0]
