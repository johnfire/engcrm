"""Chosen stages, provenance, consent, duplicates and auditing in PostgreSQL."""
import pytest
from fastapi import HTTPException

from gcrm.api.routers.api_record_edit import OrganizationFields, save_manual_organization
from gcrm.audit_context import audit_scope
from gcrm.db.connection import db
from gcrm.organization_state import PIPELINE_STAGES

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("stage", PIPELINE_STAGES)
def test_manual_business_persists_stage_and_never_overwrites_duplicate(clean_database, monkeypatch, stage):
    monkeypatch.setattr("gcrm.tools.db_organizations.geocode", lambda city, country: None)
    fields = OrganizationFields(name="Manual Academy", city="Augsburg", email="manual@academy.test",
                                pipeline_stage=stage, decision_maker="Ann", notes="Entered by hand")
    with audit_scope("owner@example.test", "user", "manual-stage-test"):
        created = save_manual_organization(fields, "manual_web")
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT pipeline_stage, status, source, decision_maker, notes FROM contacts WHERE id=%s",
                       (created["id"],))
        assert dict(cursor.fetchone()) == {"pipeline_stage": stage, "status": "none", "source": "manual_web",
                                          "decision_maker": "Ann", "notes": "Entered by hand"}
        cursor.execute("SELECT actor, actor_type, correlation_id FROM audit_log WHERE action='contact.created'")
        assert dict(cursor.fetchone()) == {"actor": "owner@example.test", "actor_type": "user",
                                          "correlation_id": "manual-stage-test"}
        cursor.execute("SELECT contact_id FROM consent_log WHERE contact_id=%s", (created["id"],))
        assert cursor.fetchone()["contact_id"] == created["id"]
    with pytest.raises(HTTPException) as failure:
        save_manual_organization(fields.model_copy(update={"pipeline_stage": "customer", "notes": "Overwrite"}), "manual_web")
    assert failure.value.status_code == 409 and failure.value.detail["existing_id"] == created["id"]
    with db() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT COUNT(*) AS count FROM contacts")
        assert cursor.fetchone()["count"] == 1
        cursor.execute("SELECT notes FROM contacts WHERE id=%s", (created["id"],))
        assert cursor.fetchone()["notes"] == "Entered by hand"
