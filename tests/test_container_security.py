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


def test_every_service_the_deploy_waits_for_can_become_healthy_inside_the_wait():
    """`docker compose up --wait --wait-timeout 180` fails the deploy if a service is
    still 'starting' after 180s. The backup image's own check runs every 5 minutes, which
    can never pass in time, so the compose file must set a fast one."""
    workflow = Path(".github/workflows/backend.yml").read_text()
    wait = int(workflow.split("--wait-timeout ")[1].split()[0])
    waited_for = workflow.split("--wait-timeout ")[1].split("\n")[0].split()[1:]
    services = yaml.safe_load(Path("docker-compose.yml").read_text())["services"]
    for name in waited_for:
        check = services[name].get("healthcheck")
        assert check, f"{name} needs its own healthcheck: the image's default can be slower than the deploy wait"
        seconds = lambda text: int(str(text).rstrip("s"))  # noqa: E731
        first_pass = seconds(check.get("start_period", "0s")) + seconds(check["interval"]) + seconds(check["timeout"])
        assert first_pass * 2 < wait, f"{name} may need {first_pass}s to be healthy; the deploy waits {wait}s"
