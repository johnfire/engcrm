#!/bin/sh
set -eu
# One short, isolated root job prepares existing uploads and the private DSN
# directory. The web service mounts its credentials read-only and runs as 10001.
mkdir -p /data/card-images /run/engcrm-runtime
chown -R 10001:10001 /data/card-images /run/engcrm-runtime
chmod 0700 /run/engcrm-runtime
mkdir -p /data/backups
chown 0:0 /data/backups
chmod 0700 /data/backups
python /app/scripts/prepare_runtime_environment.py
# Compose reads this file on the host; retain the operator file's host owner.
chown "$(stat -c '%u:%g' /run/operator.env)" /run/engcrm-settings/app.env /run/engcrm-settings
chmod 0700 /run/engcrm-settings
