"""Invoked only by the offline initialization job, before migrations or app restart."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcrm.deployment_environment import write_runtime_environment

if __name__ == "__main__":
    write_runtime_environment(Path("/run/operator.env"), Path("/run/engcrm-settings/app.env"))
