"""Dump every web page to static HTML so its layout can be audited in a browser.

The template-rendering tests already render every page with realistic mock data;
this reuses them as a page factory rather than duplicating their fixtures.

    uv run python scripts/layout_audit.py

writes gcrm/ui/static/_layout_audit/ (gitignored), then open
http://localhost:8001/static/_layout_audit/runner.html in the browser preview and
run `runAll(PAGES, false)` for the plain pass and `runAll(PAGES, true)` for the
hostile-content pass. Both must come back with an empty `window.__results`.

The audit flags any element whose content spills outside its box without being
clipped or scrollable — the failure that makes one column's text land on top of
the next one. Line counts and row heights cannot see it.
"""
import json
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "gcrm" / "ui" / "static" / "_layout_audit"
PLUGIN = '''
import os, re
from starlette.testclient import TestClient
OUT = os.environ["DUMP_DIR"]
_orig, _seen = TestClient.request, set()
def request(self, method, url, *a, **kw):
    r = _orig(self, method, url, *a, **kw)
    try:
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            name = re.sub(r"[^a-zA-Z0-9]+", "_", str(url)).strip("_") or "root"
            if name not in _seen:
                _seen.add(name)
                open(os.path.join(OUT, f"page_{name}.html"), "w").write(r.text)
    except Exception:
        pass
    return r
TestClient.request = request
'''


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / "_dump_plugin.py").write_text(PLUGIN)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "-p", "_dump_plugin",
         "-m", "not integration and not e2e and not network"],
        cwd=HERE.parent,
        env={**__import__("os").environ, "DUMP_DIR": str(OUT), "PYTHONPATH": str(OUT)},
    )
    if result.returncode != 0:
        print("template tests failed — fix those before auditing layout")
        return result.returncode
    pages = sorted(p.name for p in OUT.glob("page_*.html"))
    (OUT / "pages.json").write_text(json.dumps(pages, indent=2))
    shutil.copy(HERE / "layout_audit_runner.html", OUT / "runner.html")
    print(f"{len(pages)} pages dumped to {OUT}")
    print("open /static/_layout_audit/runner.html and call runAll(PAGES, false) then runAll(PAGES, true)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
