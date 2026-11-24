"""Account-scoped mobile sync device registration."""

from gcrm.audit_context import current_audit_context
from gcrm.db.connection import db
from gcrm.sync.contracts import DeviceRegistration


def register_sync_device(workspace_id: int, user_id: int, device: DeviceRegistration) -> bool:
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO mobile_sync_devices(workspace_id, user_id, device_id, server_environment,
                                            app_version, schema_version)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (workspace_id, user_id, device_id, server_environment) DO UPDATE
               SET app_version=EXCLUDED.app_version, schema_version=EXCLUDED.schema_version,
                   last_seen_at=clock_timestamp()
             WHERE mobile_sync_devices.revoked_at IS NULL
            RETURNING device_id
            """,
            (workspace_id, user_id, str(device.device_id), device.server_environment,
             device.app_version, device.schema_version),
        )
        if cursor.fetchone() is None:
            return False
        audit = current_audit_context()
        cursor.execute(
            "INSERT INTO audit_log(actor, actor_type, action, target, outcome, correlation_id) "
            "VALUES (%s,%s,'sync.device_registered',%s,'success',%s)",
            (audit.actor, audit.actor_type, f"device:{str(device.device_id)[-8:]}", audit.correlation_id),
        )
    return True
