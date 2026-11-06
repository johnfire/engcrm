"""Deployment structure keeps owner credentials and capabilities out of the web app."""
from pathlib import Path

import yaml


def test_production_runtime_has_only_private_runtime_credentials():
    services = yaml.safe_load(Path("docker-compose.yml").read_text())["services"]
    app = services["app"]
    assert "DATABASE_URL" not in app["environment"]
    assert app["environment"]["DATABASE_URL_FILE"] == "/run/engcrm-runtime/database-dsn"
    assert app["env_file"] != ".env" and app["env_file"] != [".env"]
    assert "${ENGCRM_IMAGE:?" in app["image"]
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"]
    assert app["user"] == "10001:10001"
    assert app["security_opt"] == ["no-new-privileges:true"]
    assert "runtime-credentials:/run/engcrm-runtime:ro" in app["volumes"]
    assert services["migrate"]["profiles"] == ["tools"]
    assert services["migrate"]["env_file"] == ".env"
    assert services["initialize"]["network_mode"] == "none"


def test_image_scan_is_required_before_publishing_and_deploying_the_image():
    workflow = yaml.safe_load(Path(".github/workflows/backend.yml").read_text())
    steps = workflow["jobs"]["build-deploy"]["steps"]
    names = [step.get("name", "") for step in steps]
    assert names.index("Scan release image") < names.index("Publish tested image")
    deploy = next(step for step in steps if step.get("name") == "Deploy to VPS (pull + migrate + restart)")
    assert "set -eu" in deploy["with"]["script"]
    assert "uv run" not in deploy["with"]["script"]
    assert "script_stop" not in deploy["with"]
    assert "steps.publish.outputs.digest" in deploy["env"]["APP_IMAGE"]


def test_changes_to_deployment_inputs_trigger_the_release_checks():
    workflow = yaml.safe_load(Path(".github/workflows/backend.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert "infra/**" in triggers["push"]["paths"]
    assert "infra/**" in triggers["pull_request"]["paths"]
