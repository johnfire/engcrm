"""Run as the operator in the one-shot migration service, never in the web app."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gcrm.config import DATABASE_URL
from gcrm.runtime_credentials import provision_runtime_credentials


def main() -> None:
    subprocess.run([sys.executable, str(Path(__file__).with_name("migrate.py"))], check=True)
    target = Path(os.environ.get("RUNTIME_DATABASE_FILE", "/run/engcrm-runtime/database-dsn"))
    provision_runtime_credentials(DATABASE_URL, target)
    print("Migrations complete; separate runtime credentials are ready (secret not displayed).")


if __name__ == "__main__":
    main()
