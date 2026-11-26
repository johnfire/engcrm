"""Every third-party GitHub Action is pinned to an immutable commit, not a movable tag.

The deploy and release jobs hand secrets (the VPS SSH key, the Play upload credential, the
Android keystore) to these actions; a retagged action would otherwise run with them.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)", re.MULTILINE)
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def action_references():
    for workflow in WORKFLOWS:
        for reference in USES.findall(workflow.read_text()):
            if not reference.startswith("./"):
                yield workflow.name, reference


def test_the_workflows_were_found():
    assert WORKFLOWS and list(action_references())


def test_every_third_party_action_is_pinned_to_a_full_commit_sha():
    unpinned = [f"{name}: {reference}" for name, reference in action_references() if not PINNED.match(reference)]
    assert unpinned == []


def test_each_pin_keeps_its_human_readable_version_in_a_comment():
    """Dependabot reads the trailing `# vX` to propose updates, and people read it to review them."""
    for workflow in WORKFLOWS:
        for line in workflow.read_text().splitlines():
            if USES.match(line) and "@" in line and not line.strip().startswith("#"):
                assert re.search(r"@[0-9a-f]{40}\s+#\s*v\d", line), f"{workflow.name}: {line.strip()}"


def test_local_audit_snapshots_are_kept_out_of_the_docker_image():
    ignored = (ROOT / ".dockerignore").read_text().splitlines()
    assert "gcrm/ui/static/_layout_audit" in ignored
